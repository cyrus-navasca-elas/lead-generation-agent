# Lead Generation Agent — Development Plan

Companion to `docs/prd.md`. Locks technical decisions and lays out a build path for the MVP. Scope follows the PRD: ZoomInfo-driven discovery, LLM planning + summaries, scoring, Excel + JSON export. Plus a small UI for configuring ICPs and filters.

---

## 1. Locked Decisions

| Area | Decision |
|------|----------|
| Language | Python 3.11+ |
| Package manager | `uv` (lockfile + venv) |
| Backend | FastAPI + Uvicorn |
| Frontend | React + Vite (TypeScript), served standalone in dev, mounted as static files in prod |
| LLM | OpenAI (`gpt-4o-mini` for planning/extraction, `gpt-4o` for summaries — both env-configurable) |
| Data source | ZoomInfo only for MVP (outside sources deferred) |
| Tests | None for MVP (per user) |
| Persistence | Filesystem only — no DB |
| Run artifacts | `out/{run_id}/companies.xlsx`, `out/{run_id}/raw.json`, `out/{run_id}/run.log`, `out/{run_id}/manifest.json` |
| Run ID | `{YYYYMMDD-HHMMSS}-{ulid}` |
| Concurrency | `httpx.AsyncClient` + `asyncio.Semaphore` per ZoomInfo rate-limit |
| Dev cache | Optional on-disk cache of ZoomInfo responses at `cache/zoominfo/{sha256}.json` |
| Secrets | `.env` loaded via `pydantic-settings` |
| Scoring | Rules defined in `configs/scoring.yaml`; engine emits per-rule breakdown |
| Signal extraction | Hybrid — deterministic rules on structured ZoomInfo fields + LLM pass for free-text (description, news, scoops) |
| Dedup | By ZoomInfo company ID within a single run |
| Logging | `structlog` JSON to stdout + tee'd to `run.log` |

---

## 2. Architecture

```
                ┌──────────────────────┐
                │   React (Vite) SPA   │
                │  ICP/Filter Console  │
                └─────────┬────────────┘
                          │ REST/JSON
                          ▼
                ┌──────────────────────┐
                │      FastAPI         │
                │  /runs /icps /score  │
                └─────────┬────────────┘
                          │ async task
                          ▼
   ┌──────────────────────────────────────────────────┐
   │              Lead Generation Pipeline             │
   │                                                   │
   │  Planner ──► Retrieval ──► Enrichment ──►        │
   │  Signal Extractor ──► Scorer ──► Summarizer ──►  │
   │  Exporter (Excel + JSON)                          │
   └─────────┬───────────────────────────────┬────────┘
             │                               │
             ▼                               ▼
       ZoomInfo API                    OpenAI API
```

Runs execute as background tasks (`asyncio` task tracked by the API). Status polled by the UI.

---

## 3. Directory Layout

```
lead-generation-agent/
├── app/                          # Python backend
│   ├── api/
│   │   ├── __init__.py
│   │   ├── main.py               # FastAPI app factory
│   │   ├── deps.py               # Dependency injection
│   │   └── routes/
│   │       ├── runs.py           # POST /runs, GET /runs/{id}, GET /runs/{id}/artifacts
│   │       ├── icps.py           # CRUD on ICP YAMLs
│   │       ├── scoring.py        # GET/PUT scoring config
│   │       └── health.py
│   ├── core/
│   │   ├── config.py             # pydantic-settings
│   │   ├── logging.py            # structlog setup
│   │   └── ids.py                # run_id generator
│   ├── pipeline/
│   │   ├── planner.py            # LLM → SearchPlan
│   │   ├── retrieval.py          # ZoomInfo search/enrich orchestrator
│   │   ├── enrichment.py         # Scoops, tech, hiring lookups
│   │   ├── signals.py            # Deterministic + LLM signal extraction
│   │   ├── scoring.py            # Apply scoring.yaml → ScoredCompany
│   │   ├── summarizer.py         # LLM → ProspectSummary
│   │   ├── exporter.py           # openpyxl + json writers
│   │   └── runner.py             # End-to-end orchestrator
│   ├── clients/
│   │   ├── zoominfo.py           # Async httpx wrapper (auth, retry, cache)
│   │   └── openai_client.py      # Chat completions + JSON-mode helpers
│   ├── models/
│   │   ├── icp.py
│   │   ├── plan.py
│   │   ├── company.py
│   │   ├── contact.py
│   │   ├── signal.py
│   │   ├── score.py
│   │   └── run.py                # RunState, RunStatus, RunArtifacts
│   ├── store/
│   │   ├── runs.py               # In-memory + on-disk run state
│   │   └── icp_repo.py           # Reads/writes configs/icps/*.yaml
│   └── __init__.py
├── configs/
│   ├── icps/
│   │   ├── manufacturing-midmarket.yaml
│   │   └── _example.yaml
│   ├── scoring.yaml
│   └── llm-prompts/
│       ├── planner.md
│       ├── signal_extraction.md
│       └── summary.md
├── web/                          # React + Vite frontend
│   ├── package.json
│   ├── vite.config.ts
│   ├── tsconfig.json
│   ├── index.html
│   └── src/
│       ├── main.tsx
│       ├── App.tsx
│       ├── api/client.ts
│       ├── pages/
│       │   ├── NewRun.tsx
│       │   ├── RunDetail.tsx
│       │   └── IcpEditor.tsx
│       └── components/
│           ├── FilterForm.tsx
│           ├── RunStatusBadge.tsx
│           └── ScoreBreakdown.tsx
├── out/                          # Run artifacts (gitignored)
├── cache/                        # Dev-only API cache (gitignored)
├── docs/
│   ├── prd.md
│   └── development-plan.md
├── .env.example
├── .gitignore
├── pyproject.toml
├── uv.lock
└── README.md
```

---

## 4. Data Models (Pydantic)

Minimal sketches — full types defined in `app/models/`.

```python
class SearchPlan(BaseModel):
    industries: list[str]
    employee_min: int | None
    employee_max: int | None
    revenue_min: int | None
    revenue_max: int | None
    technologies: list[str]
    geographies: list[str]
    target_titles: list[str]
    rationale: str

class Company(BaseModel):
    zoominfo_id: str
    name: str
    industry: str | None
    employee_count: int | None
    revenue: int | None
    website: str | None
    technologies: list[str]
    description: str | None
    location: str | None

class Contact(BaseModel):
    zoominfo_id: str
    company_zoominfo_id: str
    name: str
    title: str | None
    department: str | None
    email: str | None
    phone: str | None

class Signal(BaseModel):
    key: str            # e.g. "uses_salesforce"
    label: str          # human readable
    source: str         # "zoominfo.tech" | "llm.description" | ...
    confidence: float

class ScoreBreakdown(BaseModel):
    rule_id: str
    label: str
    points: int

class ScoredCompany(BaseModel):
    company: Company
    signals: list[Signal]
    breakdown: list[ScoreBreakdown]
    total_score: int
    summary: ProspectSummary | None

class ProspectSummary(BaseModel):
    fit_reason: str
    pain_points: list[str]
    erp_relevance: str
    recommended_contacts: list[str]
    confidence: Literal["low", "medium", "high"]

class RunState(BaseModel):
    run_id: str
    status: Literal["queued", "planning", "retrieving", "enriching",
                    "scoring", "summarizing", "exporting", "done", "error"]
    objective: str
    icp_id: str | None
    filters: dict
    created_at: datetime
    finished_at: datetime | None
    counts: dict          # {"companies": 42, "contacts": 138}
    error: str | None
    artifacts: dict       # paths to xlsx/json/log
```

---

## 5. Component Design

### 5.1 Planner (`pipeline/planner.py`)
- Input: NL objective + optional ICP YAML + optional filter overrides from UI.
- Calls OpenAI with `response_format={"type": "json_object"}` against `configs/llm-prompts/planner.md`.
- Output: `SearchPlan`.
- Validates output via Pydantic; on validation failure, retry once with the error appended to the prompt.

### 5.2 ZoomInfo Client (`clients/zoominfo.py`)
- Async `httpx.AsyncClient` wrapper.
- Auth: PKI cert OR username/password — config-driven (`ZOOMINFO_AUTH_MODE`).
- Endpoints used (MVP):
  - `search/company`
  - `enrich/company`
  - `search/contact`
  - `enrich/contact`
  - `search/scoops` (hiring/funding/news)
- Retry on 429/5xx with exponential backoff (`tenacity`).
- Optional read-through disk cache when `DEV_CACHE_ENABLED=true`.
- Concurrency gated by `asyncio.Semaphore(ZOOMINFO_MAX_CONCURRENCY)`.

### 5.3 Retrieval Orchestrator (`pipeline/retrieval.py`)
- Takes `SearchPlan` → calls `search/company` → paginates up to configured cap (`MAX_COMPANIES`, default 50 for MVP).
- For each company: `enrich/company`, fan-out `search/contact` for the target titles, then `enrich/contact` on hits.
- Dedup by `zoominfo_id` inside the run.

### 5.4 Enrichment (`pipeline/enrichment.py`)
- Pulls Scoops (hiring, funding, expansion, tech change) for each company.
- Attached as raw blobs to the `Company` object for signal extraction.

### 5.5 Signal Extractor (`pipeline/signals.py`)
- Deterministic pass first:
  - Tech array contains target stack → `uses_<vendor>` signals.
  - Employee count in ICP range → `size_match`.
  - Multiple locations → `multi_location`.
  - Scoops include hiring titles like "RevOps", "ERP Administrator" → `hiring_*` signals.
- LLM pass second (single batched call per company): reads description + scoop summaries, returns additional signals as JSON.
- Signals merged + deduped by `key`.

### 5.6 Scoring Engine (`pipeline/scoring.py`)
- Loads `configs/scoring.yaml`:
  ```yaml
  max_score: 100
  rules:
    - id: uses_salesforce
      requires_signal: uses_salesforce
      points: 20
    - id: size_100_500
      condition: "100 <= employee_count <= 500"
      points: 15
    - id: industry_manufacturing
      condition: "industry == 'Manufacturing'"
      points: 15
    - id: hiring_revops
      requires_signal: hiring_revops
      points: 15
    - id: growth_over_20
      condition: "growth_rate > 0.2"
      points: 10
    - id: multi_location
      requires_signal: multi_location
      points: 10
  ```
- Conditions evaluated via a sandboxed expression (`asteval`) against a context dict — no `eval`.
- Output: list of `ScoreBreakdown` + total clamped to `max_score`.

### 5.7 Summarizer (`pipeline/summarizer.py`)
- For each scored company above a threshold (`MIN_SCORE_FOR_SUMMARY`, default 40), call OpenAI with company + signals + score breakdown.
- JSON-mode → `ProspectSummary`.
- Skipped companies still appear in export with empty summary.

### 5.8 Exporter (`pipeline/exporter.py`)
- Excel via `openpyxl`:
  - Sheet 1 — Companies (sorted by score desc).
  - Sheet 2 — Contacts.
  - Sheet 3 — Score Detail (one row per `ScoreBreakdown`).
- JSON: full `list[ScoredCompany]` + run manifest.
- Writes to `out/{run_id}/`.

### 5.9 Runner (`pipeline/runner.py`)
- Top-level `async def execute_run(run_id, request)`.
- Updates `RunState` between phases.
- Catches exceptions → status `error`, error string stored, partial artifacts preserved.

---

## 6. API Surface

| Method | Path | Purpose |
|--------|------|---------|
| `POST` | `/runs` | Create + start a run. Body: `{ objective, icp_id?, filters?, max_companies? }`. Returns `{ run_id }`. |
| `GET` | `/runs` | List runs (most recent N). |
| `GET` | `/runs/{run_id}` | Run state + counts. |
| `GET` | `/runs/{run_id}/artifacts/{name}` | Stream `companies.xlsx` / `raw.json` / `run.log`. |
| `GET` | `/icps` | List ICP configs. |
| `GET` | `/icps/{icp_id}` | Read one ICP. |
| `PUT` | `/icps/{icp_id}` | Create/update ICP (writes YAML). |
| `DELETE` | `/icps/{icp_id}` | Delete ICP YAML. |
| `GET` | `/scoring` | Current scoring config. |
| `PUT` | `/scoring` | Update scoring config (writes YAML, validates). |
| `GET` | `/health` | Liveness. |

CORS: allow `http://localhost:5173` (Vite dev) in dev; same-origin in prod.

---

## 7. Frontend (React + Vite)

Pages:

1. **New Run** (`/`)
   - Objective textarea.
   - ICP picker (dropdown of YAMLs) + "load" button.
   - Filter form (industries, employee min/max, revenue min/max, geographies, target titles, technologies). Pre-fills from ICP, overridable.
   - Max companies slider (10–100).
   - "Start Run" → POST `/runs` → redirect to run detail.

2. **Run Detail** (`/runs/:id`)
   - Status badge with live polling (2s) until terminal state.
   - Phase timeline.
   - Counts (companies discovered, contacts, qualified).
   - Download buttons for `companies.xlsx` and `raw.json`.
   - Inline preview table of top 20 scored companies with expandable score breakdown.

3. **ICP Editor** (`/icps`)
   - List view + form-based editor (no raw YAML required, but YAML view as a fallback).
   - Save → PUT `/icps/{id}`.

4. **Scoring Editor** (`/scoring`)
   - Table of rules with point editor.
   - Save → PUT `/scoring`.

State management: TanStack Query for fetching, no global store needed.

Styling: Tailwind CSS (lightweight, fast to set up).

---

## 8. Configuration

### `.env.example`
```
# OpenAI
OPENAI_API_KEY=
OPENAI_PLANNER_MODEL=gpt-4o-mini
OPENAI_SUMMARY_MODEL=gpt-4o

# ZoomInfo
ZOOMINFO_AUTH_MODE=pki        # or "password"
ZOOMINFO_USERNAME=
ZOOMINFO_PASSWORD=
ZOOMINFO_PRIVATE_KEY=
ZOOMINFO_CLIENT_ID=
ZOOMINFO_BASE_URL=https://api.zoominfo.com
ZOOMINFO_MAX_CONCURRENCY=5

# Pipeline
MAX_COMPANIES=50
MIN_SCORE_FOR_SUMMARY=40

# Dev
DEV_CACHE_ENABLED=false
LOG_LEVEL=INFO
```

### `configs/icps/_example.yaml`
```yaml
id: manufacturing-midmarket
label: Mid-Market Manufacturing on Legacy CRM
industries: [Manufacturing, Industrial Machinery]
employee_min: 100
employee_max: 500
revenue_min: 25000000
revenue_max: 500000000
geographies: [United States, Canada]
target_titles:
  - VP of Operations
  - Director of RevOps
  - CIO
  - VP of IT
  - Director of ERP
technologies_present: [Salesforce, NetSuite, Oracle]
technologies_absent: []
notes: >
  Companies likely outgrowing SF or running a legacy on-prem ERP.
```

---

## 9. Build Phases

### Phase 0 — Scaffold (Day 1)
1. `pyproject.toml` + `uv init`, dependencies: `fastapi`, `uvicorn[standard]`, `httpx`, `pydantic`, `pydantic-settings`, `pyyaml`, `structlog`, `openpyxl`, `pandas`, `openai`, `asteval`, `tenacity`, `python-ulid`.
2. Directory tree per §3.
3. `app/api/main.py` boots, `/health` works.
4. `app/core/config.py` loads `.env`.
5. `app/core/logging.py` configures structlog.
6. `web/` scaffolded via `npm create vite@latest web -- --template react-ts`, Tailwind added.
7. `.gitignore` covers `out/`, `cache/`, `.env`, `node_modules/`, `__pycache__/`.
8. `README.md` updated with run instructions.

### Phase 1 — Pipeline End-to-End on Stubs (Day 2)
1. Pydantic models in `app/models/`.
2. `clients/zoominfo.py` with a `FakeZoomInfoClient` returning fixture data alongside the real client (selected by env flag).
3. Implement planner → retrieval → signals (deterministic only) → scoring → exporter against fakes.
4. Runner wires phases together; `RunState` transitions logged.
5. `POST /runs` + `GET /runs/{id}` + artifact download.

### Phase 2 — Real Integrations (Day 3)
1. Real ZoomInfo auth + endpoints (`search/company`, `enrich/company`, contacts, scoops).
2. Real OpenAI planner + summarizer prompts.
3. LLM signal pass added to `signals.py`.
4. Retry/backoff + semaphore tuning.
5. Disk cache wired behind `DEV_CACHE_ENABLED`.

### Phase 3 — UI (Day 4)
1. API client + TanStack Query setup.
2. New Run page + Run Detail page with polling.
3. ICP editor (form + YAML fallback).
4. Scoring editor.
5. Score breakdown table on Run Detail.

### Phase 4 — Polish (Day 5)
1. Error surfaces in UI (run `error` state with message + log download).
2. Excel formatting (column widths, conditional fill on score).
3. Sort + filter on Run Detail preview table.
4. `make dev` / `uv run` scripts documented in README.

---

## 10. Initial Scaffold — Concrete Files to Create

The first commit after this plan should land:

- `pyproject.toml`, `uv.lock`
- `.env.example`, `.gitignore`
- `app/__init__.py`
- `app/api/main.py` (FastAPI app, `/health`)
- `app/api/routes/health.py`
- `app/core/config.py`, `app/core/logging.py`, `app/core/ids.py`
- `app/models/{run,plan,company,contact,signal,score,icp}.py` (skeletons)
- `app/pipeline/{planner,retrieval,enrichment,signals,scoring,summarizer,exporter,runner}.py` (NotImplementedError stubs)
- `app/clients/{zoominfo,openai_client}.py` (skeletons)
- `app/store/{runs,icp_repo}.py` (skeletons)
- `configs/scoring.yaml`, `configs/icps/_example.yaml`
- `configs/llm-prompts/{planner,signal_extraction,summary}.md`
- `web/` scaffold via Vite + Tailwind
- `README.md` (run instructions)

---

## 11. Out of Scope (MVP)

- Outside data sources beyond ZoomInfo.
- Tests.
- Auth / multi-user (single-user internal tool).
- Persistent DB / historical run search beyond filesystem listing.
- CRM push, outreach, scheduled runs.
- Cross-run dedup.

---

## 12. Open Questions (defer until needed)

1. ZoomInfo tier — which Scoops categories are licensed? Affects enrichment depth.
2. Should ICPs be versioned (git-tracked) or mutable? Current plan: git-tracked YAMLs, edits commit-friendly.
3. Excel branding (logo, headers) — needed for MVP or skip?
4. Deployment target — Docker on a VM, Fly.io, internal k8s? Defer until UI works.
