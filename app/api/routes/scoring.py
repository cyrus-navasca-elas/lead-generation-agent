from __future__ import annotations

from typing import Annotated, Any

import yaml
from fastapi import APIRouter, Body, Depends, HTTPException

from app.api.deps import AppContainer, container
from app.pipeline.scoring import load_scoring_config

router = APIRouter(prefix="/scoring", tags=["scoring"])


@router.get("")
async def get_scoring(
    ctn: Annotated[AppContainer, Depends(container)],
) -> dict[str, Any]:
    return yaml.safe_load(ctn.settings.scoring_path.read_text())


@router.put("")
async def put_scoring(
    ctn: Annotated[AppContainer, Depends(container)],
    config: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    path = ctn.settings.scoring_path
    backup_text = path.read_text() if path.exists() else None
    path.write_text(yaml.safe_dump(config, sort_keys=False))
    try:
        ctn.scoring = load_scoring_config(path)
    except Exception as exc:
        if backup_text is not None:
            path.write_text(backup_text)
        raise HTTPException(status_code=400, detail=f"invalid scoring config: {exc}")
    return config
