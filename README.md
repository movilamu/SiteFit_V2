# Retail Site Intelligence & Site Selection Platform

A decision-support platform for ranking candidate retail locations inside a
defined geographic boundary. It is built for regional expansion managers,
corporate strategy teams, property teams, commercial real-estate consultants
and business owners.

The platform **ranks** sites against a stated set of requirements and
weights. It does not predict trading performance, and it does not replace
site visits, commercial due diligence or local market knowledge. Every
result it produces is accompanied by the evidence behind it and by the
limits of that evidence.

---

## Table of contents

- [What the platform does](#what-the-platform-does)
- [Architecture](#architecture)
- [The analytical model](#the-analytical-model)
- [Repository structure](#repository-structure)
- [Getting started](#getting-started)
- [Environment variables](#environment-variables)
- [Database](#database)
- [API](#api)
- [Frontend](#frontend)
- [Testing](#testing)
- [Data sources and their limits](#data-sources-and-their-limits)
- [Operational notes](#operational-notes)

---

## What the platform does

1. **Define the brief.** Business type, buy/lease/buy-or-lease, search area,
   business-specific requirements, parking, facilities and budgets. Every
   question comes from a configurable catalogue and every answer is
   editable.
2. **Filter and score.** Sites are filtered against hard requirements,
   normalised per criterion, weighted through the criteria hierarchy and
   aggregated with the selected method.
3. **Explain.** Every ranked site carries a narrative generated from the
   scoring engine's own output: the factors that separate it from the site
   below it, its requirement position, its cost position and the caveats.
4. **Compare.** Two to four sites side by side, with award labels shown only
   where the data supports them.
5. **Cost.** A cost breakdown in which every figure carries its provenance,
   and an incomplete cost picture is reported as incomplete.
6. **Property intelligence.** Live retrieval against public or
   operator-configured sources around the top three sites, with full
   attribution.
7. **Stress-test.** Weight perturbations, alternative aggregation methods
   and near-tie detection, translated into plain language.
8. **Report.** An executive decision report suitable for a strategy review.

---

## Architecture

```
   ┌────────────┐   ┌────────────┐   ┌────────────┐   ┌────────────┐
   │  Next.js   │──▶│  FastAPI   │──▶│  Supabase  │──▶│  PostGIS   │
   │  frontend  │   │    API     │   │  (data +   │   │  (spatial) │
   │  (Vercel)  │   │  (Render)  │   │   auth)    │   │            │
   └────────────┘   └────────────┘   └────────────┘   └────────────┘
                            │                                   ▲
                            │         ┌────────────┐           │
                            └────────▶│  Pipeline  │───────────┘
                                      │  ingestion │
                                      │ → scoring  │
                                      │ → precompute│
                                      └────────────┘
```

- **Frontend** — Next.js 16 (App Router, React 19, Tailwind 4, MapLibre GL).
  The browser never talks to the backend directly: every API call goes
  through the Next.js `/api` proxy, so the backend origin stays private and
  no CORS negotiation is needed in production.
- **API** — FastAPI. Every numerical result is computed here; the frontend
  never calculates a score.
- **Data** — Supabase (PostgreSQL + PostGIS). Analytical tables are written
  by service-role jobs; user-owned tables are protected by row-level
  security keyed on `auth.uid()`.
- **Pipeline** — Python ETL jobs ingest, normalise and precompute. The API
  serves rankings from the precomputed matrix, so scoring stays cheap
  enough to run on every weight change.

---

## The analytical model

The criteria hierarchy is defined once, in `scoring/criteria_hierarchy.py`,
and is the single source of truth for the interface, the API and the
scoring engine.

```
root
 └── category (8)          population · demographics · spending · accessibility
     └── subcategory (1)       competition · cannibalisation · site_and_property · risk
         └── criterion (28)        the scorable leaves
```

The pipeline is:

1. **Filter.** A requirement marked *hard* removes a site that fails it.
   Filtering happens before scoring so non-viable sites cannot skew the
   comparison.
2. **Normalise.** Raw values are clipped to the 5th/95th percentile of the
   observed candidate set and rescaled to 0–1. Cost criteria are inverted;
   a target-band criterion scores highest inside its ideal range and falls
   off linearly outside it.
3. **Weight.** Weights are set over the eight categories and optionally
   refined within a category. A leaf's global weight is the product of the
   level weights along its path.
4. **Aggregate.** Weighted sum (SAW), weighted product (WPM) or
   distance-to-ideal (TOPSIS).
5. **Penalise.** A missed *preference* reduces the site’s fit factor, which
   lowers its score by at most the disclosed penalty rate (25 % by
   default). A *flexible* requirement never changes the score.
6. **Stress-test.** Perturbed weights, alternative methods, near ties.

Requirement behaviours are never chosen silently. The user picks *hard*,
*preference* or *flexible*, and the interface states the consequence of
that choice.

### Documented analytical changes

Two corrections were made when the modules were consolidated. Both are
covered by deterministic tests.

| Change | Why | Test |
| --- | --- | --- |
| Weight alignment is now strict. A weight mapping that does not cover every matrix column raises an error instead of falling back to positional alignment. | The positional fallback silently applied a weight to a different criterion than the one it was written for. | `scoring/tests/test_score.py` |
| `apply_weights` normalises the weight vector to sum to 1.0 before dispatching to the aggregation method. | `distance_to_ideal` renormalised internally while the other two did not, so the same weight vector produced two different effective weightings. Ranking is unaffected; the discrepancy only affected internal callers. | `scoring/tests/test_score.py` |
| The rank-stability report aligns the perturbed weight vector to the matrix columns. | The perturbations were built from the mapping’s insertion order and applied positionally, so they analysed a different model from the one that produced the ranking. | `sensitivity/tests/test_stability.py` |
| The gravity model no longer uses `current_trading_performance` as an attractiveness proxy. | It is a currency amount; using it alongside floor areas put incommensurable values into the same exponent and made the cannibalisation metric meaningless. | `ingestion/generate_catchments.py` |
| The perturbation sampler is seeded by default. | A stability report is now reproducible rather than changing on every request. | `sensitivity/tests/test_stability.py` |

---

## Repository structure

```
/ingestion    Python ETL: the analysis grid, geospatial base, competitors,
              demographics, economics, accessibility, property, own estate,
              routing, catchments, gravity model, cannibalisation
/scoring      Criteria hierarchy, normalisation, hierarchical weight
              roll-up, aggregation, hard constraints, cost model, cost
              estimation, requirement evaluation, precompute, diagnostics
/elicitation  AHP pairwise elicitation, consistency ratio, swing weighting
/sensitivity  Critical thresholds, rank stability, near ties, rank
              reversal, Monte-Carlo rank distribution
/api          FastAPI service: sites, scoring, decomposition, requirements,
              explanations, properties, brokerage, data quality, reports,
              exports, projects, scenarios, sensitivity, elicitation
/analytics    Backtesting against the client's own trading performance
/frontend     Next.js application
/platform_env.py  The single place that reads the environment file
/tools        Operational scripts: schema audit, endpoint audit, workflow
              test, test sessions, migration application, security sweep
/infra        SQL migrations, monitoring documentation
/docs         Production setup guide and the setup checklist
```

---

## Getting started

### Prerequisites

- Python 3.11+
- Node.js 22+ and pnpm 12+
- A Supabase project (PostgreSQL with PostGIS)

### Backend

```bash
python -m venv .venv
source .venv/Scripts/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt

cp .env.example .env.local         # then fill in the values
uvicorn api.app.main:app --reload --port 8000
```

The API is then available at <http://127.0.0.1:8000>, with interactive
documentation at `/docs`.

The API, the scoring jobs and the ingestion jobs all read their
configuration through `platform_env.py`, which looks for `.env.local` and
then `.env` in the repository root. A variable that is already set in the
process environment always wins, so a deployment's own configuration takes
precedence over the file.

### Frontend

```bash
cd frontend
pnpm install
cp .env.example .env.local          # then fill in the values
pnpm dev
```

The frontend is then available at <http://localhost:3000>.

### Building the scoring matrix

The API serves rankings from a precomputed, normalised decision matrix. To
build one:

```bash
python -m scoring.precompute_matrix --persist
```

The matrix is assembled from the ingested tables, the hard constraints are
applied, the values are normalised and the result is published to Supabase
Storage. Criteria whose backing data is unavailable are excluded and their
weight is redistributed; the coverage is reported with every ranking.

### Data pipeline

```bash
python -m ingestion.analysis_units --around-sites
python -m ingestion.geospatial_base_etl
python -m ingestion.competitor_etl
python -m ingestion.demographic_etl --boundaries data/census_boundaries.geojson
python -m ingestion.economic_etl
python -m ingestion.accessibility_etl
python -m ingestion.property_etl
python -m ingestion.own_estate_etl
python -m ingestion.generate_catchments
python -m ingestion.verify_data
```

`ingestion.analysis_units` builds the analysis grid: it fills the pilot
area with real H3 resolution-8 cells — the tessellation has no gaps and no
overlapping cells — and writes each cell's polygon. The grid is a derived
spatial index, not a statement about the places it covers: the population,
the economy and the property attributes still have to come from their own
sources.

A Census 2011 ward usually spans several H3 cells. The demographic job
allocates it across them with the areal interpolation in
`ingestion/areal_interpolation.py`, which apportions the population and
lowers the confidence score in proportion to how fragmented the allocation
is. The `--boundaries` argument supplies the Census polygons (a CSV with a
`raw_geo_id` and a `geometry` column, or a GeoJSON FeatureCollection).
Without it only direct 1:1 matches are possible, and the job reports how
many records could not be allocated rather than silently dropping them.

### Checking a deployment

The `tools/` directory holds the scripts used to operate and to check the
platform:

```bash
python tools/audit_schema.py         # the live database against the migrations
python tools/audit_endpoints.py      # every endpoint, with and without a session
python tools/workflow_test.py        # the complete analytical workflow
python tools/make_test_session.py    # a real Supabase token for a test account
python tools/security_sweep.py       # committed credentials and unsafe constructs
```

### Local development with synthetic data

For working on the interface without a populated database:

```bash
python tools/make_dev_matrix.py     # writes data/dev/normalized_matrix_dev.csv
python tools/dev_server.py           # serves the API with that matrix
```

The generated values are random, carry no analytical meaning and are
written under `data/`, which is git-ignored. They are a development aid
only and must never be used as a production artefact.

---

## Environment variables

See `.env.example` for the full list. The essentials:

| Variable | Purpose |
| --- | --- |
| `SUPABASE_URL`, `SUPABASE_KEY` | Server-side data access. |
| `SUPABASE_SERVICE_ROLE_KEY` | Required by the ETL jobs and the user-owned tables. |
| `ORS_API_KEY` | Drive-time isochrones (OpenRouteService). |
| `NORMALIZED_MATRIX_FILE` | Local path to the normalised matrix. Optional when the matrix is published to Supabase. |
| `PROPERTY_SOURCE_URL` / `PROPERTY_SOURCE_FILE` | Enables the operator-configured property source. |
| `LLM_BASE_URL`, `LLM_API_KEY` | Enables the AI requirement builder. Without them the builder reports that it is unavailable and the manual form is used. |
| `FRONTEND_ORIGINS` | Browser origins allowed to call the API. |
| `SENTRY_DSN` | Error reporting. |

**No credential is committed to the repository.** The frontend reads
`NEXT_PUBLIC_SENTRY_DSN` and the API reads `SENTRY_DSN`; both are
environment variables, and no DSN appears in source control.

---

## Authentication

The platform authenticates through **Supabase Auth with the Google
provider only**. There is no email/password flow.

```
Browser  →  Google  →  Supabase Auth  →  authenticated application
```

* `frontend/proxy.ts` protects the application routes. When Supabase is
  not configured the routes stay open, so the platform remains usable in a
  local, unconfigured environment.
* `frontend/app/login/page.tsx` is the sign-in page.
* `frontend/app/auth/callback/route.ts` exchanges the OAuth code for a
  session and writes the session cookies.
* The API verifies the access token on every user-owned request
  (`api/app/core/auth.py`). The owner of a record is taken from the
  verified session, never from the request body.
* The analyses are persisted in Supabase. The browser is used only as a
  fallback when Supabase is not configured, and the interface says so
  plainly when that happens.

Setup instructions are in `docs/PRODUCTION_SETUP.md` and
`docs/SETUP_CHECKLIST.md`.

## Exports

| Format | Endpoint | Contents |
| --- | --- | --- |
| **PDF** | `POST /reports/export` | A paginated decision document: scope, shortlist, explanations, the exact weighting configuration, the cost analysis, the property and brokerage opportunities, the data quality limitations and the assumptions. |
| **CSV** | `POST /reports/export` | The ranked shortlist, the weighting configuration and the assumptions, in a spreadsheet-friendly form. |
| **Excel** | `POST /reports/export` | One workbook with a sheet per section: overview, shortlist, weights, requirements, cost analysis, property opportunities, data quality and sensitivity. |
| **JSON** | `POST /reports/export` | The complete report payload, for archiving. |

Every export contains the **exact** weighting configuration and
aggregation method that produced the ranking, so the result is
reproducible from the exported file alone.

`POST /export` is the separate *reproducible ranking export*: a
self-describing artefact that carries the ranking, the weight mapping
and the export metadata, and is archived in Supabase Storage.

## Property and brokerage intelligence

Both searches use a **source-adapter architecture**. Each source operates
independently, a failing source degrades to a reported status, and
nothing is ever fabricated.

| Kind | How it works |
| --- | --- |
| **Map data** | Commercial premises and shop units recorded in OpenStreetMap, read through the Overpass API. Labelled as map data, not as a broker listing. |
| **Licensed feed** | A property feed the operator is licensed to use, configured with `PROPERTY_SOURCE_URL` or `PROPERTY_SOURCE_FILE`. |
| **Manual navigation** | A portal that is **not** queried and **not** scraped. The platform provides a direct search link and states that the result was not retrieved automatically. |

The same three kinds apply to brokerage discovery, with agencies and
operators found in the map data and brokerage directories offered for
manual search.

Every external result carries its source, its retrieval timestamp and a
source status (`live_source`, `recently_retrieved`, `source_date_available`,
`source_date_unknown` or `unavailable`). Every outbound URL is checked so
that a misconfigured feed cannot make the server reach an internal
address.

## Cost engine

* Every monetary figure carries a provenance: `verified_listed`,
  `user_provided`, `estimated`, `calculated` or `unavailable`.
* An unknown component is reported as unavailable. It is never guessed.
* Estimation is **off by default**. When `COST_ESTIMATION_ENABLED` is
  turned on, the documented rules in `scoring/cost_estimation.py` fill a
  missing component, every estimated line is labelled `Estimated` and
  records the rule that produced it.
* The total cost of ownership over a configurable horizon is reported
  alongside the one-time, monthly and annual figures. When the horizon
  total cannot be completed, the known minimum is reported and the
  missing components are named.

## Configuration validation

`GET /health/config` returns the state of every integration: whether it
is configured, what happens if it is not, and which environment variable
fixes it. No credential value is ever returned. The **Settings** page
renders the same report.

## Database

Migrations live in `infra/sql/migrations` and are applied in order.

| Migration | Contents |
| --- | --- |
| `0001_init.sql` | The analytical schema: analysis units, demographics, economics, accessibility, competitors, own estate, property listings, spatial base, isochrones, candidate sites and catchments, the scoring matrix registry, saved scenarios and exports. |
| `0002_site_selection.sql` | The platform entities: site-selection projects, business requirements, facility requirements, parking requirements, financial requirements, cost assessments and lines, external property opportunities, source registry and reports. |

Row-level security is enabled throughout. The analytical tables are written
by service-role jobs; the user-owned tables carry an ownership policy
keyed on `auth.uid()`, so one user can never read another user’s
analysis, cost data or reports.

---

## API

The API is versioned by resource. The endpoints the interface depends on:

| Method | Path | Purpose |
| --- | --- | --- |
| `GET` | `/health`, `/health/ready` | Liveness and readiness. |
| `GET` | `/criteria` | The authoritative criteria hierarchy. |
| `POST` | `/criteria/rollup` | Roll category and leaf weights into global leaf weights. |
| `GET` | `/sites` | Candidate inventory, with optional hard-constraint filters. |
| `POST` | `/score` | Rank the sites for a weight configuration. |
| `GET` | `/sites/{id}/decomposition` | The per-criterion breakdown of a site’s score. |
| `GET` | `/requirements/catalog` | Business types, requirements, facilities, behaviours and budgets. |
| `POST` | `/requirements/evaluate` | Deterministic requirement evaluation per site. |
| `POST` | `/requirements/parse` | The AI requirement builder. Advisory only. |
| `POST` | `/explanations/site` | The "why this site?" explanation. |
| `GET` | `/properties/sources` | The external property sources and their status. |
| `POST` | `/properties/search` | Property and brokerage opportunities around the top sites. |
| `GET` | `/data-quality` | Coverage, freshness and the known limitations. |
| `POST` | `/reports/generate` | The executive decision report (JSON, Markdown or HTML). |
| `GET`/`POST` | `/scenarios` | Saved weight scenarios. |
| `POST` | `/export` | A reproducible export of the ranking and its weights. |
| `GET` | `/health/config` | The configuration validation report. |
| `GET`/`POST`/`PATCH`/`DELETE` | `/projects` | The signed-in user's site-selection analyses. |
| `GET` | `/brokerage/sources`, `/brokerage/search-sites` | Brokerage sources and the agencies found around the recommended sites. |
| `POST` | `/reports/export` | The executive report as PDF, CSV, Excel or JSON. |
| `GET` | `/sensitivity/*` | Thresholds, stability, near ties, rank-reversal risk, Monte-Carlo rank distribution and cross-method agreement. |
| `POST` | `/elicitation/ahp`, `/elicitation/swing` | AHP and swing weighting. |

### Scoring

`POST /score` accepts exactly one of two weight sources:

```jsonc
// Explicit leaf weights
{ "weights": { "resident_density": 0.4, "projected_growth": 0.6 },
  "method": "weighted_sum" }

// Or the executive form: category weights, optionally refined per category
{ "level_weights": {
    "category_weights": { "population": 0.3, "accessibility": 0.4 },
    "leaf_weights": { "population": { "resident_density": 0.7, "projected_growth": 0.3 } }
  },
  "method": "weighted_sum" }
```

The response reports the effective leaf weights, the criteria that could
not be scored, and the resulting coverage.

---

## Frontend

```
frontend/
  app/
    (workspace)/
      analyses/            analysis list, the workflow and the workspace
      methodology/         how the ranking is calculated
      data-quality/        coverage, freshness and limitations
      reports/             the report index
  components/
    ui/                    the design system
    shell/                 the application shell
    workflow/              the site-selection workflow
    workspace/             the analytical workspace
  lib/                     the API client, types, formatting and the brief model
```

### Design system

Light-first and enterprise-oriented. Colour carries *status*, not
decoration: green for strong, amber for attention, red for weak or failed,
blue for neutral information and grey for unavailable. Every status is
paired with a text label or an icon, so meaning never depends on colour
alone.

The tokens are defined once in `app/globals.css` and exposed through
Tailwind’s theme, so a component never hard-codes a colour value.

### Accessibility

- A skip link is the first focusable element on every page.
- Every control has an associated label; errors are announced with
  `role="alert"`.
- Status is never conveyed by colour alone.
- The map’s site markers are real buttons, so they are keyboard reachable
  and announced.
- Dialogs and tabs are built on Base UI, which supplies focus trapping and
  the correct ARIA relationships.
- The layout reflows to a single column on a phone; the analytical
  workspace prioritises a desktop but remains functional on a tablet.

---

## Testing

```bash
# Python
pip install -r requirements.txt
pytest -q

# Frontend
cd frontend
pnpm typecheck
pnpm lint
pnpm test
pnpm build
```

The Python suite covers the aggregation formulas, the strict weight
alignment, the hierarchical roll-up, the normalisation maths, the
requirement evaluation, the cost model, the rank-stability correction, the
demographic crosswalk and the API contract.

The frontend suite covers the weight helpers, the formatting rules
(including that a missing value is never rendered as zero), the brief
model, and the loading, empty, error and keyboard behaviours of the
workflow and the shortlist.

Both suites run in CI on every pull request.

---

## Data sources and their limits

These limitations are surfaced in the interface, in the API responses and
in the report. They are not hidden.

- **Census data is from 2011.** Demographic and household data derives from
  the Census of India 2011, the most recent complete enumeration. Growth
  since 2011 is estimated from trend data where it exists, not from a
  newer census.
- **OpenStreetMap coverage is uneven.** Competitive-set, accessibility and
  land-use data derive from OpenStreetMap. A site with few mapped features
  is not necessarily a site with no competition.
- **Property listing coverage is incomplete.** Listed rents, prices, unit
  sizes and tenure terms exist only where a public listing has been
  ingested. Where they are absent, the cost analysis reports the component
  as unavailable rather than estimating it.
- **Routing coverage is limited by the free tier.** Drive-time catchments
  come from OpenRouteService, whose free tier allows a limited number of
  requests per day.
- **Not every criterion is scorable in every release.** Criteria whose
  backing dataset has not been materialised are excluded from scoring, and
  the weight they carried is redistributed across the criteria that could
  be scored. The coverage is reported with every ranking.
- **There is no backtest until there is an own estate.** The model can be
  validated against trading performance only once the client’s own store
  records are present.

---

## Operational notes

- **Monitoring.** Sentry for application errors, with `send_default_pii`
  disabled so that demographic and site data can never be attached to an
  error report. Prometheus metrics are exposed at `/metrics`.
- **CORS.** Origins come from `FRONTEND_ORIGINS`. There is no placeholder
  production origin in the code.
- **Outbound requests.** The property search validates every outbound URL
  and refuses to contact a host that resolves to a non-public address, so a
  misconfigured feed cannot be turned into a request-forgery vector.
- **Degradation.** A failing external source degrades to a reported status.
  It never fails the request, and it is never presented as "nothing is
  available".
- **Build.** The frontend is built with the webpack pipeline
  (`next build --webpack`) so the Sentry source-map upload continues to
  work; Next 16 otherwise defaults to Turbopack, which the Sentry SDK does
  not yet support fully.

---

## Licence

Proprietary. All rights reserved.
