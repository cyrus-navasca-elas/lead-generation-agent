from __future__ import annotations

import asyncio
import json
from pathlib import Path

from app.models.run import RunState, RunSummary


class RunStore:
    """In-memory primary store with manifest.json mirroring per run."""

    def __init__(self, out_dir: Path):
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self._runs: dict[str, RunState] = {}
        self._lock = asyncio.Lock()
        self._load_from_disk()

    def _load_from_disk(self) -> None:
        for manifest in self.out_dir.glob("*/manifest.json"):
            try:
                data = json.loads(manifest.read_text())
                state = RunState.model_validate(data)
                self._runs[state.run_id] = state
            except Exception:
                continue

    async def create(self, state: RunState) -> None:
        async with self._lock:
            self._runs[state.run_id] = state
            self._persist(state)

    async def update(self, state: RunState) -> None:
        async with self._lock:
            self._runs[state.run_id] = state
            self._persist(state)

    def get(self, run_id: str) -> RunState | None:
        return self._runs.get(run_id)

    def list_recent(self, limit: int = 50) -> list[RunSummary]:
        items = sorted(
            self._runs.values(), key=lambda r: r.created_at, reverse=True
        )[:limit]
        return [
            RunSummary(
                run_id=r.run_id,
                status=r.status,
                objective=r.objective,
                source=r.source,
                created_at=r.created_at,
                finished_at=r.finished_at,
                counts=r.counts,
            )
            for r in items
        ]

    def run_dir(self, run_id: str) -> Path:
        return self.out_dir / run_id

    def _persist(self, state: RunState) -> None:
        run_dir = self.run_dir(state.run_id)
        run_dir.mkdir(parents=True, exist_ok=True)
        (run_dir / "manifest.json").write_text(
            json.dumps(state.model_dump(mode="json"), indent=2, default=str)
        )
