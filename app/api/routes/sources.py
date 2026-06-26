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
