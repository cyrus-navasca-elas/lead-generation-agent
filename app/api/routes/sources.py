from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from app.api.deps import AppContainer, container

router = APIRouter(prefix="/sources", tags=["sources"])


@router.get("")
async def list_sources(
    ctn: Annotated[AppContainer, Depends(container)],
) -> list[dict]:
    return [s.to_dict() for s in ctn.source_statuses()]


@router.get("/integrations")
async def integrations_status(
    ctn: Annotated[AppContainer, Depends(container)],
) -> dict:
    s = ctn.settings
    return {
        "openai_ready": bool(s.openai_api_key),
        "tavily_ready": ctn.web_search.ready,
        "use_fake_clients": s.use_fake_clients,
        "defaults": {
            "scrape_top_k": s.scrape_top_k,
            "score_blend_weight": s.score_blend_weight,
            "max_companies": s.max_companies,
        },
    }
