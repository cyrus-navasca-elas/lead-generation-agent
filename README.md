# Lead Generation Agent

AI-driven lead discovery for an agentic ERP platform.

Two data sources:

- **ZoomInfo** — primary source for B2B firmographic + tech-stack data.
  Listed as "in progress" in the UI; client wiring lands once API access is
  granted.
- **CSLB** — California State Licensing Board contractor data
  (`data/MasterLicenseData.csv`, ~244k rows). Ingested into
  `cache/cslb.sqlite` at startup. Used as a permanent complementary source
  for California construction-trades prospects.

See `docs/prd.md`, `docs/secondary_prd.md`, and `docs/development-plan.md`
for full context.

## Setup

```bash
uv sync
cp .env.example .env   # leave USE_FAKE_CLIENTS=true to run end-to-end on stubs
```

First boot ingests the CSLB CSV (~30s). Subsequent boots reuse the SQLite
DB unless the CSV is updated.

## Run the API (dev)

```bash
uv run uvicorn app.api.main:app --reload --port 8000
```

Endpoints:
- `GET  /health`
- `GET  /sources` — list available data sources and their readiness
- `POST /runs` — body: `{ "objective": "...", "source": "zoominfo" | "cslb", "icp_id": "..." }`
- `GET  /runs`
- `GET  /runs/{run_id}`
- `GET  /runs/{run_id}/artifacts/{name}` — `companies.xlsx`, `raw.json`, `run.log`
- `GET/PUT/DELETE /icps/{icp_id}`
- `GET/PUT /scoring`

Artifacts land in `out/{run_id}/`.

## Smoke tests

```bash
uv run python -m app.scripts.smoke_cslb    # CSLB path (real SQLite)
```

## Layout

- `app/`            FastAPI backend + pipeline
- `app/clients/`    `source.LeadSource` Protocol + ZoomInfo / CSLB / LLM clients
- `configs/`        scoring rules, ICPs, LLM prompts
- `data/`           CSLB master license CSV
- `cache/`          generated SQLite DB (gitignored)
- `out/`            run artifacts (gitignored)
- `docs/`           PRD + secondary PRD + dev plan
- `web/`            React + Vite SPA (added in Phase 3)
