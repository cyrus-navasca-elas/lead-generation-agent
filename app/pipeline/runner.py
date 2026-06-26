from __future__ import annotations

import logging
import traceback
from datetime import datetime, timezone
from pathlib import Path

from app.agents.enrich import EnrichAgent
from app.agents.relevance import RelevanceAgent
from app.clients.llm import LLMClient
from app.clients.scraper import Scraper
from app.clients.source import LeadSource
from app.clients.web_search import TavilyClient
from app.core.config import Settings
from app.core.logging import (
    attach_run_file_handler,
    detach_run_file_handler,
    get_logger,
)
from app.models.run import RunArtifacts, RunRequest, RunState
from app.models.score import ScoredCompany
from app.pipeline import exporter
from app.pipeline.enrichment import blend, enrich_top_k
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
        web_search: TavilyClient | None = None,
        scraper: Scraper | None = None,
        openai_client=None,
    ):
        self.settings = settings
        self.run_store = run_store
        self.icp_repo = icp_repo
        self.source = source
        self.llm = llm
        self.scoring_config = scoring_config
        self.web_search = web_search
        self.scraper = scraper
        self.openai_client = openai_client

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

        # --- Signals + Base Score ---
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
                    base_score=total,
                    total_score=total,
                )
            )
        scored.sort(key=lambda s: s.base_score, reverse=True)
        state.counts.companies_scored = len(scored)

        # --- Enrichment (web search + scrape + extract) ---
        filters = request.filters or {}
        top_k = int(filters.get("scrape_top_k") or self.settings.scrape_top_k)
        alpha = float(filters.get("score_blend_weight") or self.settings.score_blend_weight)

        enrich_ready = bool(
            self.web_search
            and self.web_search.ready
            and self.scraper
            and self.openai_client
            and self.settings.openai_api_key
        )
        if enrich_ready and top_k > 0:
            state.status = "enriching"
            await self.run_store.update(state)
            enrich_agent = EnrichAgent(
                self.settings, self.web_search, self.scraper, self.openai_client
            )
            relevance_agent = RelevanceAgent(self.settings, self.openai_client)
            icp = self.icp_repo.get(request.icp_id) if request.icp_id else None

            state.status = "relevance_scoring"
            await self.run_store.update(state)
            enrichment = await enrich_top_k(
                scored,
                enrich_agent=enrich_agent,
                relevance_agent=relevance_agent,
                objective=request.objective,
                icp=icp,
                top_k=top_k,
                max_concurrency=self.settings.enrich_max_concurrency,
            )

            enriched_count = 0
            relevance_count = 0
            for item in scored:
                key = item.company.zoominfo_id
                profile = enrichment.profiles.get(key)
                relevance = enrichment.relevance.get(key)
                if profile is not None:
                    item.enriched_profile = profile
                    if profile.confidence not in ("error", "none"):
                        enriched_count += 1
                    if profile.website and not item.company.website:
                        item.company.website = profile.website
                if relevance is not None:
                    item.relevance = relevance
                    relevance_count += 1
                    item.total_score = blend(item.base_score, relevance.score, alpha)
            state.counts.companies_enriched = enriched_count
            state.counts.companies_relevance_scored = relevance_count
            scored.sort(key=lambda s: s.total_score, reverse=True)
        else:
            log.info(
                "runner.enrich_skipped",
                tavily_ready=bool(self.web_search and self.web_search.ready),
                openai_ready=bool(self.settings.openai_api_key),
                top_k=top_k,
            )

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
