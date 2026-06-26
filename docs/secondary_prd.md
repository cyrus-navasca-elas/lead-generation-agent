# Secondary PRD — CSLB Lead Source

Companion to `docs/prd.md`. Adds California State Licensing Board (CSLB)
contractor data as a permanent complementary lead source for the agentic ERP
platform. Originally introduced because ZoomInfo API access was pending; kept
post-ZoomInfo because the construction-trades data is not well covered by
ZoomInfo and represents a distinct vertical.

## Purpose

Discover California construction-trades businesses (electrical, plumbing,
HVAC, general building, solar, etc.) that are operationally ripe for a
unified ERP — multi-classification scope, active bonds and workers' comp,
recent license reissues, and Corp/LLC-scale entities.

## Inputs

* Same NL objective + ICP shape as the ZoomInfo flow.
* New `source: "cslb"` field on the run request.
* New optional `cslb` block on the ICP / SearchPlan with:
  * `classifications` — CSLB license codes (e.g. `C-10`, `B`, `C-36`,
    `HAZ`). Codes are matched with and without hyphens.
  * `business_types` — `Sole Owner`, `Corporation`, `Limited Liability`,
    `Partnership`, `JointVenture`.
  * `counties` — California county names.
  * `min_bond_amount` — integer dollars; filters on `CBAmount`.
  * `primary_status` — defaults to `["CLEAR"]`.

## Data Source

CSLB master license export — `data/MasterLicenseData.csv`, ~244k rows,
50 columns. License-centric, no employee count, no tech stack, no
individual decision makers beyond the license-holder name + business
phone.

Ingested into `cache/cslb.sqlite` on app startup; refreshed automatically
when the CSV mtime is newer than the DB mtime.

## Outputs

Same artifacts as ZoomInfo runs:

* **Excel**: Companies sheet gains License #, Business Type, Bond Amount,
  License Status, License Expires columns (populated for CSLB rows; empty
  for ZoomInfo rows). Industry column carries the human-readable
  classification labels (e.g. "General Building / Electrical").
* **Contacts sheet**: one row per company, with the license holder as the
  sole contact, title "Licensee", phone only.
* **Score Detail**: same per-rule breakdown shape.
* **JSON**: full structured payload, mirroring the ZoomInfo run shape.

## Scoring

Shared `configs/scoring.yaml`. CSLB-specific rules added:

| Rule | Points | Trigger |
|------|-------:|---------|
| `corp_or_llc` | 10 | Corporation or Limited Liability entity |
| `has_contractor_bond` | 5 | Active CBNumber |
| `large_bond` | 10 | CBAmount ≥ `CSLB_LARGE_BOND_THRESHOLD` (default $25k) |
| `multi_classification` | 15 | ≥ 2 classifications |
| `clear_status` | 5 | PrimaryStatus == CLEAR |
| `has_workers_comp` | 5 | WCInsuranceCompany present |
| `recent_reissue` | 5 | ReissueDate within last 24 months |
| `expiring_soon` | 5 | ExpirationDate within next 6 months |

ZoomInfo rules (`uses_salesforce`, `uses_legacy_erp`, `industry_manufacturing`,
etc.) naturally skip for CSLB rows because their `requires_signal` keys do
not exist. The same is true in reverse.

## Out of Scope (MVP)

* Outside enrichment (LinkedIn / web scraping for individual contacts).
* Non-California state license boards.
* Cross-source deduplication.
* Real-time CSLB feed (the file is a manual refresh artifact for now).
* Recent-news / scoops equivalent — CSLB has no analog.

## Success Metric

Number of qualified contractors per run that hold:

* `primary_status == CLEAR`,
* an active contractor bond,
* and at least 2 classifications — i.e. operationally mature trades
  businesses with the breadth that typically benefits from a unified ERP.

## Risks

* CSV is a snapshot — licenses go inactive between refreshes. Scoring
  includes `clear_status` so stale rows are deprioritized; the
  `expiration_date >= today` filter prevents fully expired licenses from
  appearing.
* Classification taxonomy quirks — both `C-10` and `C10` appear in the raw
  data; both forms are normalized to a canonical hyphen-free upper form
  in the SQLite `classifications_norm` column.
* Bond and WC fields are sparsely populated in some rows; signals
  gracefully skip when the underlying value is absent.
