"""End-to-end smoke test of the CSLB lead generation pipeline.

Usage:
    uv run python -m app.scripts.smoke_cslb
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

from app.api.deps import get_container
from app.core.ids import new_run_id
from app.core.logging import configure_logging
from app.models.run import RunRequest, RunState


async def main() -> int:
    configure_logging("INFO")
    container = get_container()

    if "cslb" not in container.sources:
        print("CSLB source not available — did the CSV ingest run?")
        return 2

    pipeline = container.build_pipeline("cslb")

    request = RunRequest(
        objective=(
            "Find mid-sized California electrical contractors with active bonds "
            "and multiple classifications that may be ready for an ERP overhaul."
        ),
        source="cslb",
        icp_id="cslb-electrical-midmarket",
    )
    state = RunState(
        run_id=new_run_id(),
        objective=request.objective,
        source="cslb",
        icp_id=request.icp_id,
    )
    await container.run_store.create(state)
    await pipeline.execute(state, request)

    final = container.run_store.get(state.run_id)
    print(json.dumps(final.model_dump(mode="json"), indent=2, default=str))

    failures: list[str] = []
    if final.status != "done":
        failures.append(f"status={final.status}")
    if final.counts.companies_retrieved < 5:
        failures.append(f"companies_retrieved={final.counts.companies_retrieved}")

    run_dir = Path(final.artifacts.excel).parent if final.artifacts.excel else None
    excel_path = container.run_store.run_dir(final.run_id) / "companies.xlsx"
    if not excel_path.exists():
        failures.append("excel artifact missing")

    if failures:
        print("SMOKE FAILED:", failures)
        return 1

    print(f"SMOKE OK — {final.counts.companies_retrieved} CSLB companies, "
          f"{final.counts.companies_summarized} summarized.")
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
