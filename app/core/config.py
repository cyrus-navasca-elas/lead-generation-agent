from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # OpenAI
    openai_api_key: str = ""
    openai_planner_model: str = "gpt-4o-mini"
    openai_summary_model: str = "gpt-4o-mini"
    openai_extract_model: str = "gpt-4o-mini"
    openai_relevance_model: str = "gpt-4o-mini"

    # Tavily (web search)
    tavily_api_key: str = ""
    tavily_base_url: str = "https://api.tavily.com"

    # Enrichment
    scrape_top_k: int = 10
    score_blend_weight: float = 0.4
    enrich_max_concurrency: int = 5
    scrape_timeout_seconds: float = 8.0
    scrape_max_bytes: int = 30_000

    # ZoomInfo
    zoominfo_auth_mode: str = "pki"
    zoominfo_username: str = ""
    zoominfo_password: str = ""
    zoominfo_private_key: str = ""
    zoominfo_client_id: str = ""
    zoominfo_base_url: str = "https://api.zoominfo.com"
    zoominfo_max_concurrency: int = 5

    # Pipeline
    max_companies: int = 50
    min_score_for_summary: int = 40

    # CSLB
    cslb_csv_path: str = "data/MasterLicenseData.csv"
    cslb_db_path: str = "cache/cslb.sqlite"
    cslb_auto_ingest: bool = True
    cslb_large_bond_threshold: int = 25000

    # Modes
    use_fake_clients: bool = False
    dev_cache_enabled: bool = False

    # Misc
    log_level: str = "INFO"
    out_dir: str = "out"
    config_dir: str = "configs"

    @property
    def out_path(self) -> Path:
        return Path(self.out_dir).resolve()

    @property
    def config_path(self) -> Path:
        return Path(self.config_dir).resolve()

    @property
    def scoring_path(self) -> Path:
        return self.config_path / "scoring.yaml"

    @property
    def icps_path(self) -> Path:
        return self.config_path / "icps"

    @property
    def prompts_path(self) -> Path:
        return self.config_path / "llm-prompts"


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
