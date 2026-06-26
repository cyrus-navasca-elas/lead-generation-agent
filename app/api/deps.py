from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from fastapi import Request

from app.clients.cslb import CSLBClient
from app.clients.cslb_ingest import ensure_db
from app.clients.llm import LLMClient, build_llm_client
from app.clients.source import LeadSource
from app.core.config import Settings, get_settings
from app.core.logging import get_logger
from app.models.company import SourceName
from app.pipeline.runner import Pipeline
from app.pipeline.scoring import ScoringConfig, load_scoring_config
from app.store.icp_repo import ICPRepository
from app.store.runs import RunStore

log = get_logger(__name__)


class SourceStatus:
    def __init__(self, name: SourceName, ready: bool, detail: dict):
        self.name = name
        self.ready = ready
        self.detail = detail

    def to_dict(self) -> dict:
        return {"name": self.name, "ready": self.ready, **self.detail}


class AppContainer:
    def __init__(self, settings: Settings):
        self.settings = settings
        self.run_store = RunStore(out_dir=settings.out_path)
        self.icp_repo = ICPRepository(root=settings.icps_path)
        self.llm: LLMClient = build_llm_client(settings)
        self.scoring: ScoringConfig = load_scoring_config(settings.scoring_path)

        # ZoomInfo client is in-progress (no API access yet) — intentionally
        # not registered in `sources`, so `POST /runs source=zoominfo` returns
        # a 400. The /sources endpoint still surfaces it with ready=false.
        self.sources: dict[SourceName, LeadSource] = {}
        self._cslb_row_count = 0
        self._init_cslb()

    def _init_cslb(self) -> None:
        csv_path = Path(self.settings.cslb_csv_path)
        db_path = Path(self.settings.cslb_db_path)
        if self.settings.cslb_auto_ingest:
            try:
                self._cslb_row_count = ensure_db(csv_path, db_path)
            except Exception as exc:
                log.warning("cslb.ingest_failed", error=str(exc))
                self._cslb_row_count = 0
        elif db_path.exists():
            import sqlite3

            try:
                conn = sqlite3.connect(db_path)
                self._cslb_row_count = int(
                    conn.execute("SELECT COUNT(*) FROM licenses").fetchone()[0]
                )
                conn.close()
            except Exception:
                self._cslb_row_count = 0

        if db_path.exists():
            self.sources["cslb"] = CSLBClient(db_path)

    def source_statuses(self) -> list[SourceStatus]:
        statuses: list[SourceStatus] = []
        statuses.append(
            SourceStatus(
                "zoominfo",
                ready=False,
                detail={
                    "mode": "in_progress",
                    "reason": "In progress — awaiting ZoomInfo API access.",
                },
            )
        )
        cslb_db = Path(self.settings.cslb_db_path)
        statuses.append(
            SourceStatus(
                "cslb",
                ready="cslb" in self.sources and self._cslb_row_count > 0,
                detail={
                    "row_count": self._cslb_row_count,
                    "db_path": str(cslb_db),
                    "reason": None
                    if self._cslb_row_count > 0
                    else "CSLB CSV not ingested; check CSLB_CSV_PATH.",
                },
            )
        )
        return statuses

    def build_pipeline(self, source: SourceName) -> Pipeline:
        if source not in self.sources:
            raise KeyError(source)
        return Pipeline(
            settings=self.settings,
            run_store=self.run_store,
            icp_repo=self.icp_repo,
            source=self.sources[source],
            llm=self.llm,
            scoring_config=self.scoring,
        )


@lru_cache(maxsize=1)
def get_container() -> AppContainer:
    return AppContainer(get_settings())


def container(request: Request) -> AppContainer:
    return request.app.state.container
