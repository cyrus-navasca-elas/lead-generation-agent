from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path

from app.clients.llm import LLMClient
from app.clients.source import LeadSource
from app.core.config import Settings
from app.core.logging import (
    attach_run_file_handler,
    detach_run_file_handler,
    get_logger,
)
from app.models.run import RunArtifacts, RunRequest, RunState
from app.models.score import ScoredCompany
from app.pipeline import exporter
from app.pipeline.planner import plan_search
from app.pipeline.retrieval import retrieve
from app.pipeline.scoring import ScoringConfig, score_company
from app.pipeline.signals import extract_signals
from app.pipeline.summarizer import summarize_scored
from app.store.icp_repo import ICPRepository
from app.store.runs import RunStore

log = get_logger(__name__)


class Pipeline:
    def __init__(
        self,
        settings: Settings,
        run_store: RunStore,
        icp_repo: ICPRepository,
        source: LeadSource,
        llm: LLMClient,
        scoring_config: ScoringConfig,
    ):
        self.settings = settings
        self.run_store = run_store
        self.icp_repo = icp_repo
        self.source = source
        self.llm = llm
        self.scoring_config = scoring_config

    async def execute(self, state: RunState, request: RunRequest) -> None:
        run_dir = self.run_store.run_dir(state.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        log_path = run_dir / "run.log"
        handler = attach_run_file_handler(state.run_id, log_path)

        try:
            await self._run_phases(state, request, run_dir)
        except Exception as exc:
            log.exception("runner.failed", run_id=state.run_id)
            state.status = "error"
            state.error = f"{type(exc).__name__}: {exc}\n{traceback.format_exc()}"
            state.finished_at = datetime.now(timezone.utc)
            await self.run_store.update(state)
        finally:
            detach_run_file_handler(handler)
            logging.shutdown()

    async def _run_phases(
        self,
        state: RunState,
        request: RunRequest,
        run_dir: Path,
    ) -> None:
        state.started_at = datetime.now(timezone.utc)

        # --- Plan ---
        state.status = "planning"
        await self.run_store.update(state)

        icp = self.icp_repo.get(request.icp_id) if request.icp_id else None
        plan = await plan_search(
            self.llm,
            objective=request.objective,
            icp=icp,
            filters=request.filters,
            source=request.source,
        )
        state.counts.companies_planned = self.settings.max_companies
        log.info("runner.planned", rationale=plan.rationale)

        # --- Retrieve + Enrich ---
        state.status = "retrieving"
        await self.run_store.update(state)
        max_companies = request.max_companies or self.settings.max_companies
        retrieval = await retrieve(
            self.source,
            plan,
            max_companies=max_companies,
            max_concurrency=self.settings.zoominfo_max_concurrency,
        )
        state.counts.companies_retrieved = len(retrieval.companies)
        state.counts.contacts_retrieved = sum(
            len(v) for v in retrieval.contacts_by_company.values()
        )

        state.status = "enriching"
        await self.run_store.update(state)
        # Enrichment is folded into retrieve() for Phase 1; transition exists
        # so the UI sees the phase progression.

        # --- Signals + Score ---
        state.status = "scoring"
        await self.run_store.update(state)
        scored: list[ScoredCompany] = []
        for company in retrieval.companies:
            signals = extract_signals(
                company,
                large_bond_threshold=self.settings.cslb_large_bond_threshold,
            )
            total, breakdown = score_company(company, signals, self.scoring_config)
            scored.append(
                ScoredCompany(
                    company=company,
                    contacts=retrieval.contacts_by_company.get(company.zoominfo_id, []),
                    signals=signals,
                    breakdown=breakdown,
                    total_score=total,
                )
            )
        scored.sort(key=lambda s: s.total_score, reverse=True)
        state.counts.companies_scored = len(scored)

        # --- Summarize ---
        state.status = "summarizing"
        await self.run_store.update(state)
        summarized_count = await summarize_scored(
            self.llm,
            scored,
            min_score=self.settings.min_score_for_summary,
        )
        state.counts.companies_summarized = summarized_count

        # --- Export ---
        state.status = "exporting"
        await self.run_store.update(state)
        excel_path = run_dir / "companies.xlsx"
        json_path = run_dir / "raw.json"
        manifest_path = run_dir / "manifest.json"
        exporter.write_excel(scored, excel_path)
        exporter.write_json(scored, plan, state, json_path)

        state.artifacts = RunArtifacts(
            excel=excel_path.name,
            json_export=json_path.name,
            log="run.log",
            manifest=manifest_path.name,
        )
        state.status = "done"
        state.finished_at = datetime.now(timezone.utc)
        await self.run_store.update(state)
        log.info("runner.done", run_id=state.run_id, scored=len(scored))
