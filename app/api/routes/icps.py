from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.api.deps import AppContainer, container
from app.models.icp import ICP

router = APIRouter(prefix="/icps", tags=["icps"])


@router.get("", response_model=list[str])
async def list_icps(ctn: Annotated[AppContainer, Depends(container)]) -> list[str]:
    return ctn.icp_repo.list_ids()


@router.get("/{icp_id}", response_model=ICP)
async def get_icp(
    icp_id: str,
    ctn: Annotated[AppContainer, Depends(container)],
) -> ICP:
    icp = ctn.icp_repo.get(icp_id)
    if not icp:
        raise HTTPException(status_code=404, detail="icp not found")
    return icp


@router.put("/{icp_id}", response_model=ICP)
async def put_icp(
    icp_id: str,
    icp: ICP,
    ctn: Annotated[AppContainer, Depends(container)],
) -> ICP:
    if icp.id != icp_id:
        raise HTTPException(status_code=400, detail="icp.id must match path")
    ctn.icp_repo.save(icp)
    return icp


@router.delete("/{icp_id}", status_code=204)
async def delete_icp(
    icp_id: str,
    ctn: Annotated[AppContainer, Depends(container)],
) -> None:
    if not ctn.icp_repo.delete(icp_id):
        raise HTTPException(status_code=404, detail="icp not found")
