from __future__ import annotations

import asyncio
import mimetypes
from typing import Annotated

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from fastapi.responses import FileResponse

from app.api.deps import AppContainer, container
from app.core.ids import new_run_id
from app.core.logging import get_logger
from app.models.run import RunRequest, RunState, RunSummary

router = APIRouter(prefix="/runs", tags=["runs"])
log = get_logger(__name__)

ALLOWED_ARTIFACTS = {"companies.xlsx", "raw.json", "run.log", "manifest.json"}


@router.post("", response_model=RunState, status_code=202)
async def create_run(
    request: RunRequest,
    background_tasks: BackgroundTasks,
    ctn: Annotated[AppContainer, Depends(container)],
) -> RunState:
    run_id = new_run_id()
    state = RunState(
        run_id=run_id,
        objective=request.objective,
        source=request.source,
        icp_id=request.icp_id,
        filters=request.filters,
    )
    await ctn.run_store.create(state)

    try:
        pipeline = ctn.build_pipeline(request.source)
    except KeyError:
        raise HTTPException(
            status_code=400,
            detail=f"unknown source '{request.source}'",
        )

    background_tasks.add_task(_execute_run, pipeline, state, request)
    log.info(
        "runs.created",
        run_id=run_id,
        source=request.source,
        objective=request.objective,
    )
    return state


async def _execute_run(pipeline, state: RunState, request: RunRequest) -> None:
    try:
        await pipeline.execute(state, request)
    except Exception:
        log.exception("runs.execute_failed", run_id=state.run_id)


@router.get("", response_model=list[RunSummary])
async def list_runs(
    ctn: Annotated[AppContainer, Depends(container)],
) -> list[RunSummary]:
    return ctn.run_store.list_recent()


@router.get("/{run_id}", response_model=RunState)
async def get_run(
    run_id: str,
    ctn: Annotated[AppContainer, Depends(container)],
) -> RunState:
    state = ctn.run_store.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="run not found")
    return state


@router.get("/{run_id}/artifacts/{name}")
async def get_artifact(
    run_id: str,
    name: str,
    ctn: Annotated[AppContainer, Depends(container)],
) -> FileResponse:
    if name not in ALLOWED_ARTIFACTS:
        raise HTTPException(status_code=400, detail="unknown artifact")
    state = ctn.run_store.get(run_id)
    if not state:
        raise HTTPException(status_code=404, detail="run not found")
    path = ctn.run_store.run_dir(run_id) / name
    if not path.exists():
        raise HTTPException(status_code=404, detail="artifact not produced yet")
    media_type, _ = mimetypes.guess_type(path.name)
    return FileResponse(
        path,
        media_type=media_type or "application/octet-stream",
        filename=name,
    )
