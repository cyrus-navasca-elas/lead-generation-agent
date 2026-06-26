from __future__ import annotations

from pathlib import Path

import yaml

from app.models.icp import ICP


class ICPRepository:
    def __init__(self, root: Path):
        self.root = root
        self.root.mkdir(parents=True, exist_ok=True)

    def list_ids(self) -> list[str]:
        return sorted(
            p.stem for p in self.root.glob("*.yaml") if not p.stem.startswith("_")
        )

    def get(self, icp_id: str) -> ICP | None:
        path = self.root / f"{icp_id}.yaml"
        if not path.exists():
            return None
        data = yaml.safe_load(path.read_text())
        return ICP.model_validate(data)

    def save(self, icp: ICP) -> None:
        path = self.root / f"{icp.id}.yaml"
        path.write_text(yaml.safe_dump(icp.model_dump(), sort_keys=False))

    def delete(self, icp_id: str) -> bool:
        path = self.root / f"{icp_id}.yaml"
        if path.exists():
            path.unlink()
            return True
        return False
