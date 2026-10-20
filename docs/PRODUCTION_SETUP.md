# Production setup

A complete, technically precise guide to configuring every external
service the Retail Site Intelligence & Site Selection Platform depends on.

Every variable name, command, endpoint and table name in this document is
taken from the implementation. If you change the code, change this
document too.

**Contents**

1. [Architecture and what runs where](#1-architecture-and-what-runs-where)
2. [Supabase](#2-supabase)
3. [Google OAuth](#3-google-oauth)
4. [Groq](#4-groq)
5. [OpenRouteService](#5-openrouteservice)
6. [OpenStreetMap and Overpass](#6-openstreetmap-and-overpass)
7. [Property and brokerage sources](#7-property-and-brokerage-sources)
8. [The scoring matrix](#8-the-scoring-matrix)
9. [Vercel (frontend)](#9-vercel-frontend)
10. [Render (backend)](#10-render-backend)
11. [Monitoring](#11-monitoring)
12. [Free-tier summary](#12-free-tier-summary)
13. [Verifying the installation](#13-verifying-the-installation)

---

## 1. Architecture and what runs where

Three deployable pieces plus a scheduled pipeline.

| Piece | Where it runs | What it does |
| --- | --- | --- |
| **Frontend** | Vercel (Next.js 16) | The user interface. It never talks to the backend directly: every API call goes through the Next.js `/api` proxy, which keeps the backend origin private and removes the need for CORS in production. |
| **Backend** | Render (FastAPI) | Every numerical result. It owns the scoring matrix, the requirement evaluation, the cost model, the property and brokerage searches, the exports and the session verification. |
| **Database** | Supabase (PostgreSQL + PostGIS) | The candidate inventory, the analytical tables and the user-owned analyses. |
| **Pipeline** | GitHub Actions (scheduled) | Ingestion and the precompute job. These run on the free GitHub Actions allowance. |

The environment variables fall into three places:

* **Backend** — `.env.local` in the repository root locally, and the Render
  environment variables in production.
* **Frontend** — `frontend/.env.local` locally, and the Vercel environment
  variables in production.
* **Supabase dashboard** — the Google provider credentials. No environment
  variable holds the Google client id or secret, because they must never
  reach a server environment that gets logged.

The full, commented list of variables is in `.env.example` (backend) and
`frontend/.env.example` (frontend). This document explains what each one
is for and where it goes.

### 1.1 How the environment file is found

Every part of the project — the API, the scoring jobs and the ingestion
jobs — reads its configuration through one module, `platform_env.py` at the
repository root.  It looks for `.env.local` in the repository root first
and then `.env`, and it **never overwrites** a variable that is already
present in the process environment.

That ordering is what lets the same code run locally from a file and in
production from the platform's environment variables: on Render and on
Vercel the platform's variables win, and locally the file is used.

Start the API from the repository root so that the file is found:

```bash
python -m uvicorn api.app.main:app --host 127.0.0.1 --port 8000
```

`GET /health/config` reports the state of every integration, so a missing
or misnamed variable is visible immediately rather than as a failure
somewhere else.

---

## 2. Supabase

Supabase is the authoritative data store. It holds the candidate inventory,
the analytical tables and the user-owned analyses, and it provides the
authentication the platform uses.

### 2.1 Create the project

1. Sign in at <https://supabase.com> and create a project.
2. Choose a strong database password and keep it — you will need it for
   the migrations and for the ingestion jobs.
3. Note the **project reference**, the part of the URL between `https://`
   and `.supabase.co`. The project URL is
   `https://<project-ref>.supabase.co`.

### 2.2 Enable PostGIS

The spatial tables use PostGIS geometry columns.

1. Open **Database → Extensions** in the Supabase dashboard.
2. Enable `postgis`. The migrations also call
   `CREATE EXTENSION IF NOT EXISTS pgcrypto`, which Supabase enables by
   default.

### 2.3 Run the migrations

There are five migrations, in `infra/sql/migrations`, and they must be
applied **in order**:

| Migration | What it creates |
| --- | --- |
| `0001_init.sql` | The analytical schema: `analysis_units`, `demographic_data`, `economic_data`, `accessibility_data`, `competitor_locations`, `own_estate_locations`, `property_listings`, `spatial_boundaries`, `land_use_polygons`, `road_network`, `isochrone_cache`, `ors_daily_usage`, `candidate_sites`, `candidate_catchments`, `normalized_matrix_versions`, `saved_scenarios`, `export_records`. Row-level security is enabled on all of them. |
| `0002_site_selection.sql` | The platform entities: `site_selection_projects`, `business_types`, `project_business_requirements`, `project_facility_requirements`, `project_parking_requirements`, `project_financial_requirements`, `project_cost_assessments`, `project_cost_lines`, `external_sources`, `property_opportunities`, `project_reports`, `project_saved_comparisons`. |
| `0003_authentication_and_artefacts.sql` | The authenticated-user layer: `user_profiles`, `project_rankings`, `project_comparisons`, `brokerage_opportunities`, `data_quality_snapshots`, `project_reports`. It also adds `confirmed_at` and `brief_version` to `site_selection_projects`, adds the requirement columns the API writes, and drops the duplicated `requirements` JSONB column in favour of the relational tables. It seeds the `business_types` catalogue. |
| `0004_reconcile_live_schema.sql` | Brings a database that already has the platform tables in line with the analytical schema. It creates the analytical tables when they are missing, adds the columns the application reads (`candidate_sites.site_id`, `candidate_sites.category`, `project_financial_requirements.budgets`), reconciles `export_records` with the shape the API writes, adds `user_id` to `saved_scenarios`, and enables row-level security on the analytical tables with owner policies on the user-owned ones. It is additive: no table is dropped and no existing row is modified. |
| `0005_spatial_functions.sql` | The `compute_catchment_overlap` PostGIS function, which the catchment job calls to count the competitors and the own-estate stores inside a site's drive-time catchment. The definition is held in `ingestion/competitor_overlap.py` and applied here verbatim, so the code and the schema cannot drift apart. |

**Apply them with the Supabase SQL editor** (the simplest route):

1. Open **SQL Editor → New query**.
2. Open `infra/sql/migrations/0001_init.sql`, paste the whole file, and
   run it.
3. Repeat for `0002_site_selection.sql`,
   `0003_authentication_and_artefacts.sql`,
   `0004_reconcile_live_schema.sql` and
   `0005_spatial_functions.sql`.

The migrations are idempotent (`IF NOT EXISTS`, `ON CONFLICT DO UPDATE`), so
re-running one is safe.  `0004` in particular is written to be applied to
a database that already has some of the tables, and to be safe to apply
twice.

**Or with the Supabase CLI**, which is the better choice for repeatability:

```bash
npm install -g supabase
supabase login
supabase link --project-ref <project-ref>
supabase db push --include-all      # applies everything in infra/sql/migrations
```

### 2.4 The API keys

**Project Settings → API Keys** gives you:

| Key | Where it goes | Notes |
| --- | --- | --- |
| `anon` key | `SUPABASE_ANON_KEY` (backend) and `NEXT_PUBLIC_SUPABASE_ANON_KEY` (frontend) | Browser-safe by design. It only carries the `anon` role. |
| `service_role` key | `SUPABASE_SERVICE_ROLE_KEY` (backend) | Server-only. It bypasses row-level security, so it must never reach the browser. It is required by the scheduled ingestion jobs. |
| JWT secret | `SUPABASE_JWT_SECRET` (backend, optional) | Used to verify an access token locally. Modern projects sign with RS256 and publish their keys, which the API fetches and caches; the secret is a fallback. |

Set, in the **backend** environment:

```
SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_KEY=<the anon key, or the service key for server-only deployments>
SUPABASE_SERVICE_ROLE_KEY=<the service_role key>
SUPABASE_ANON_KEY=<the anon key>
```

And in the **frontend** environment:

```
NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<the anon key>
```

### 2.5 Enable Google authentication

See [Google OAuth](#3-google-oauth) — the Google credentials are entered
here, in the Supabase dashboard.

### 2.6 Set the Site URL and the redirect URLs

**Authentication → URL Configuration**:

| Field | Development | Production |
| --- | --- | --- |
| Site URL | `http://localhost:3000` | `https://your-app.vercel.app` |
| Redirect URLs | `http://localhost:3000/auth/callback` | `https://your-app.vercel.app/auth/callback` |

Add both the development and the production URL. Supabase accepts several.

The callback path is fixed: the platform's route handler lives at
`frontend/app/auth/callback/route.ts` and exchanges the OAuth code for a
session. The `next` query parameter carries the page the user was trying
to reach.

### 2.7 Verify the row-level security

Row-level security is what stops one user reading another user's
analyses. The policies key off `auth.uid()`, which Supabase sets from the
signed-in JWT.

**Check that the policies exist:**

```sql
select tablename, policyname, cmd, qual
from pg_policies
where schemaname = 'public'
  and tablename in (
    'site_selection_projects', 'project_rankings', 'project_comparisons',
    'project_reports', 'brokerage_opportunities', 'data_quality_snapshots',
    'user_profiles', 'saved_scenarios', 'export_records'
  )
order by tablename, policyname;
```

You should see one policy per table, named `*_owner_policy`, with a
`qual` of the form `(auth.uid() = user_id)`.

**Check that a row is not readable without a session:**

```sql
-- Run this while signed out of the SQL editor (the service role bypasses
-- RLS, so use the SQL editor as the `postgres` role and confirm that a
-- direct REST call without a token returns nothing):
```

```bash
curl -s "https://<project-ref>.supabase.co/rest/v1/site_selection_projects?select=id,name" \
  -H "apikey: <the anon key>" \
  | head -c 400
```

The expected result is `[]` — the anon role has no policy that grants it
access to another user's rows.

**Check that a user cannot read another user's row even with a valid
session.** Sign in as user A, note a project id, then sign in as user B
and try to read it:

```bash
curl -s "https://<project-ref>.supabase.co/rest/v1/site_selection_projects?id=eq.<user-A-project-id>&select=id,name" \
  -H "apikey: <the anon key>" \
  -H "Authorization: Bearer <user-B's access token>"
```

The expected result is `[]`.

The API enforces the same boundary independently: `api/app/core/auth.py`
verifies the access token and `api/app/routers/projects.py` writes
`user_id` from the verified session, never from the request body.

### 2.8 Storage buckets

Two buckets are used, both created on demand by the code but easier to
create explicitly:

| Bucket | Default | Holds |
| --- | --- | --- |
| `scoring-matrices` | `SCORING_MATRIX_STORAGE_BUCKET` | The published normalised decision matrices. |
| `exports` | `SUPABASE_EXPORT_BUCKET` | The reproducible ranking export artefacts. |

Create them under **Storage → New bucket**, or let the code create them.

---

## 3. Google OAuth

The platform authenticates through **Supabase Auth with the Google
provider only**. There is no email/password flow.

Google credentials are configured in **two** places, and both are required.

### 3.1 Google Cloud Console

1. Open <https://console.cloud.google.com> and create or select a project.
2. Open **APIs & Services → OAuth consent screen**. Choose
   **External**, fill in the application name, the support email and the
   developer contact email, and add the scopes you need — the platform
   only needs the basic profile and email scopes, which Google enables by
   default for sign-in.
3. Open **APIs & Services → Credentials → Create credentials → OAuth
   client ID**.
4. Choose **Web application**.

Then set:

| Google field | Value |
| --- | --- |
| **Authorised JavaScript origins** | `http://localhost:3000` and `https://your-app.vercel.app` |
| **Authorised redirect URIs** | `https://<project-ref>.supabase.co/auth/v1/callback` |

The redirect URI is **Supabase's** callback, not your frontend's. Supabase
receives the Google response and then redirects back to your frontend's
`/auth/callback`. The Supabase dashboard shows the exact URL to copy; it
is under **Authentication → Sign In / Providers → Google → Callback URL**.

### 3.2 Supabase dashboard

**Authentication → Sign In / Providers → Google**:

1. Turn the Google provider **on**.
2. Paste the Google **Client ID** and **Client Secret**.
3. Leave the rest at its default.

That is the only place the Google credentials are entered. There is
deliberately **no environment variable** for them: they must never be
shipped to the browser, and keeping them in the Supabase dashboard means
they are never present in a `.env` file, a CI log or a build artefact.

### 3.3 How the pieces fit together

```
Browser                Supabase                 Google
   |                      |                       |
   |-- signInWithOAuth -->|                       |
   |                      |--- OAuth request --->|
   |                      |<-- authorisation ----|
   |<-- redirect to /auth/callback?code=... --|
   |
   |-- exchangeCodeForSession(code) -->|
   |<-- session cookies + access token
```

The frontend's `signInWithOAuth` uses the PKCE flow, so no client secret
ever reaches the browser. The route handler at
`frontend/app/auth/callback/route.ts` exchanges the code on the server and
writes the session cookies through the cookie store.

### 3.4 Disabling the provider

If the Google provider is left disabled, the sign-in attempt fails. The
platform reports this honestly: the login page shows *"Google sign-in is
not available: …"* with the provider's message, and the manual workflow
remains fully usable.

---

## 4. Groq

Groq provides two bounded capabilities:

* the **requirement builder**, which interprets a natural-language brief
  into a draft of structured requirements;
* the **explanation writer**, which restates deterministic results as a
  paragraph.

Neither can change a score, a weight, a cost or a database record.

### 4.1 Create the key

1. Sign in at <https://console.groq.com> and accept the terms.
2. Open **API Keys** and create a key.
3. Set it in the **backend** environment only:

```
GROQ_API_KEY=<your-groq-key>
```

The key is a secret. It must never appear in `NEXT_PUBLIC_*` variables, in
the frontend bundle, in a screenshot or in a commit.

### 4.2 Model configuration

| Variable | Default | Purpose |
| --- | --- | --- |
| `GROQ_BASE_URL` | `https://api.groq.com/openai/v1` | The API base. Change it only if you use a compatible endpoint. |
| `GROQ_MODEL` | `qwen/qwen3.8-27b` | The model that interprets a requirement brief. |
| `GROQ_EXPLANATION_MODEL` | `qwen/qwen3.8-27b` | The model that writes the explanation. |
| `GROQ_TIMEOUT_SECONDS` | `30` | The request timeout. |

### 4.3 Rate limits

The free tier is rate limited per model and per minute. The platform
handles this explicitly: a `429` becomes a typed `AIRateLimitError`, the
API returns `429`, and the interface says *"The language-model provider is
rate limiting this client. Please try again shortly."* The manual
requirement form is always available, so a rate limit never blocks the
workflow.

### 4.4 What happens without a key

`GET /health/config` reports the builder as a **warning**, not an error,
and explains that the manual form is used instead. The `POST
/requirements/parse` endpoint returns `503` with an actionable message.

---

## 5. OpenRouteService

OpenRouteService generates the drive-time catchments (isochrones) around
each candidate site.

### 5.1 Create the key

1. Sign in at <https://openrouteservice.org/dev/#/signup>.
2. Create a key from **Dashboard → Keys**.
3. Set it in the **backend** environment:

```
ORS_API_KEY=<your-openrouteservice-key>
```

### 5.2 Free-tier limitation

The free allowance is a fixed number of requests per day. The platform
therefore:

* keeps a soft cap of 2 000 requests per day, below the published
  allowance, in the ingestion job;
* records the usage in the `ors_daily_usage` table, keyed by the UTC date;
* caches every isochrone in `isochrone_cache`, keyed by
  `(lat, lon, profile, range_value)`, so a regenerated catchment is not
  re-requested.

### 5.3 What happens when it is unavailable

Existing catchments remain usable. Only *new* catchments cannot be
generated, and the data quality report says so:

> "Drive-time catchments (OpenRouteService): Not configured, so catchments
> cannot be regenerated. Existing catchments remain usable."

---

## 6. OpenStreetMap and Overpass

The competitive set, the accessibility metrics, the property map data and
the brokerage discovery all read from OpenStreetMap through the Overpass
API.

```
OVERPASS_URL=https://overpass-api.de/api/interpreter
```

There is no key. The endpoint is configurable so that a self-hosted
Overpass instance can be used instead of the public one.

**Requirements and limits:**

* the requests carry a `User-Agent` identifying the platform;
* the public instance rate-limits. A `429` is surfaced as a **source
  status** — *"The map data source is rate limiting this client. Try
  again shortly."* — and never as a failed request;
* the response is parsed defensively: an element without coordinates, or
  without a name, is skipped rather than rendered.

**Legal position.** OpenStreetMap's data is published under the
Open Database Licence. The platform reads it through the documented
Overpass API and attributes it in the interface. It does not scrape the
OpenStreetMap website.

---

## 7. Property and brokerage sources

The property and brokerage searches use a **source-adapter architecture**.
Each source is queried independently, and a failing source degrades to a
reported status rather than failing the search.

### 7.1 The three kinds of source

| Kind | How it works | Configured by |
| --- | --- | --- |
| **Map data** (automated) | Reads commercial premises, shop units and operators/agents from OpenStreetMap through Overpass. | Always available. |
| **Licensed feed** (automated) | Reads a property feed the operator is licensed to use. It may be JSON or CSV. | `PROPERTY_SOURCE_URL` or `PROPERTY_SOURCE_FILE`. |
| **Manual navigation** | The portal is **not** queried and **not** scraped. The platform provides a direct search link and states that the result was not retrieved automatically. | `PROPERTY_MANUAL_SOURCES` / `BROKERAGE_MANUAL_SOURCES`. |

### 7.2 The licensed feed

```
PROPERTY_SOURCE_URL=https://your-feed.example.com/listings.json
PROPERTY_SOURCE_FILE=/opt/data/listings.csv
PROPERTY_REQUEST_TIMEOUT=15
```

The feed may return a JSON array, or a JSON object with a `listings` or
`results` array. The fields are matched loosely, so most feeds work
without transformation. The recognised aliases are, for example:

| Field | Accepted names |
| --- | --- |
| title | `title`, `name`, `property_name`, `property name`, `headline` |
| location | `location`, `address`, `locality`, `site_address`, `area_name` |
| area | `area_sqft`, `area`, `built_up_area`, `carpet_area` |
| purchase price | `purchase_price`, `price`, `sale_price`, `asking_price` |
| monthly rent | `monthly_rent`, `rent`, `lease_rent`, `rent_per_month` |
| broker | `broker_name`, `broker`, `agency`, `agent`, `brokerage` |
| listing URL | `source_url`, `url`, `listing_url`, `link` |

**If the feed is not configured**, the source reports *"No property feed
is configured"* and the map-data and manual sources remain available.

### 7.3 The manual sources

These are the portals that publish no API, or whose terms forbid
automated access. The platform does not scrape them. It gives the user a
direct search link instead.

```
PROPERTY_MANUAL_SOURCES=
  key|Example Property Portal|https://portal.example.com|https://portal.example.com/search?q={q}&lat={lat}&lon={lon}|Search this portal for premises near the recommended location.
  ||
  key2|Another Portal|https://another.example.com||Open the portal and search the area manually.
```

The format is:

```
key | Name | Homepage | Search URL template | Instructions
```

Entries are separated by `||`. In the search URL template, `{lat}`,
`{lon}` and `{q}` are replaced with the location and the search term.

The same format is used for brokerages:

```
BROKERAGE_MANUAL_SOURCES=
  key|Example Retail Agents|https://agents.example.com|https://agents.example.com/find?lat={lat}&lon={lon}|Search this directory for agents covering the recommended area.
```

**Legal position.** Nothing is scraped. The platform links to the source
and attributes it; the user does the searching. This is the difference
between a "live source" and a "source to search manually", and the
interface labels them differently.

### 7.4 The safety guard

Every outbound URL is validated by `assert_safe_url` in
`api/app/domain/property_sources.py`:

* only `http` and `https` are permitted;
* the host must not resolve to a loopback, link-local, private,
  reserved, multicast or unspecified address.

A misconfigured feed therefore cannot be used to make the server issue
requests to internal services.

---

## 8. The scoring matrix

Every ranking is computed from a **precomputed normalised decision
matrix**: one row per candidate site, one column per criterion leaf, with
values in `[0, 1]`.

### 8.1 Building and publishing it

```bash
python -m scoring.precompute_matrix --persist
```

| Flag | Effect |
| --- | --- |
| `--persist` | Publishes the matrix to Supabase Storage and records the version in `normalized_matrix_versions`. |
| `--output <path>` | Also writes the matrix to a local file (`.parquet` or `.csv`). |

Without `--persist` the job builds the matrix and reports what it found,
which is useful for validating the pipeline.

### 8.2 How the API resolves it

`api/app/core/matrix_store.py` resolves the matrix in this order:

1. a matrix injected into the process (`set_in_memory_matrix`);
2. `NORMALIZED_MATRIX_FILE`, if it is set;
3. the most recent version in `normalized_matrix_versions`, downloaded
   from Supabase Storage.

If none of them yields a matrix, the ranking endpoints return `503` with
an actionable message. They never return an empty ranking, which could be
mistaken for "no sites qualify".

### 8.3 The ingestion jobs

The scheduled jobs live in `.github/workflows/ingest.yml` and
`precompute.yml`. They run on the free GitHub Actions allowance.

```bash
python -m ingestion.analysis_units --around-sites
python -m ingestion.geospatial_base_etl --subregion chennai
python -m ingestion.competitor_etl
python -m ingestion.demographic_etl --file-path data/census_2011_pca.xlsx
python -m ingestion.demographic_etl --boundaries data/census_boundaries.geojson
python -m ingestion.economic_etl --input data/hces_2023_24.csv
python -m ingestion.accessibility_etl --res 8
python -m ingestion.property_etl --file-path data/property_listings.csv
python -m ingestion.own_estate_etl --file-path data/own_estate.csv
python -m ingestion.generate_catchments --profile driving-car --short-minutes 10 --long-minutes 15
python -m ingestion.verify_data --counts-only
```

`--boundaries` is what allows a Census ward that spans several H3 cells
to be apportioned across them by the areal interpolation. Without it,
only direct 1:1 matches are possible, and the job reports how many
records could not be allocated.

`ingestion.analysis_units` builds the analysis grid itself.  It fills the
pilot area with **real H3 resolution-8 cells** — the tessellation has no
gaps and no overlapping cells — and writes each cell's polygon, so the
areal interpolation and the spatial joins can use it.  The grid is a
derived spatial index, not a statement about the places it covers: the
population, the economy and the property attributes still have to come
from their own sources.

Two of the jobs need a source file that is not public:

* the **demographic** job needs the Census of India 2011 Primary Census
  Abstract, district-wise with the unit geometry
  (`DDW_PCA3302_2011_MDDS_with_UI.xlsx` for Tamil Nadu);
* the **economic** job needs the Household Consumption Expenditure Survey
  extract.

When those files are not available the criteria that depend on them have
no data, and the platform says so: the ranking reports the reduced
coverage, the data-quality panel names the missing sources, and the
export carries the same disclosure.  Nothing is estimated in their place.

### 8.4 The operational tools

The `tools/` directory holds the scripts used to operate and to check the
platform.  They are not part of the application and nothing in the
application depends on them.

| Tool | What it does |
| --- | --- |
| `tools/audit_schema.py` | Compares the live database with the migrations: which tables and columns exist, and which are missing. |
| `tools/audit_endpoints.py` | Calls every endpoint in the OpenAPI schema with no token, an invalid token and a real token, and reports the status of each. |
| `tools/workflow_test.py` | Drives the complete analytical workflow against a running API and asserts the shape of every response. |
| `tools/make_test_session.py` | Creates a test account and returns a real Supabase access token, so the authenticated paths can be exercised without a browser. |
| `tools/apply_migration.py` | Applies a migration file to a Supabase project. |
| `tools/security_sweep.py` | Scans the repository for committed credentials and unsafe constructs. |
| `tools/make_dev_matrix.py`, `tools/dev_server.py` | Build a synthetic matrix and run the API against it, for development without a database. |

---

## 9. Vercel (frontend)

### 9.1 Import the project

1. Sign in at <https://vercel.com> and import the repository.
2. Set **Framework Preset** to **Next.js**.
3. Set the **Root Directory** to `frontend`.
4. Leave **Install Command** as `pnpm install` and **Build Command** as
   `pnpm build`.

The build uses the webpack pipeline (`next build --webpack`) because the
Sentry source-map upload needs it; Next 16 otherwise defaults to
Turbopack, which the Sentry SDK does not yet support fully.

### 9.2 Environment variables

Set these in **Project Settings → Environment Variables**. Choose the
environment: **Production**, **Preview** and **Development** are separate.

| Variable | Production | Preview | Development |
| --- | --- | --- | --- |
| `API_BASE_URL` | `https://<your-backend>.onrender.com` | the same | `http://127.0.0.1:8000` |
| `NEXT_PUBLIC_SUPABASE_URL` | `https://<project-ref>.supabase.co` | the same | the same |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | the anon key | the same | the same |
| `NEXT_PUBLIC__DSN` | the browser DSN | optional | leave empty |
| `NEXT_PUBLIC_SENTRY_ENVIRONMENT` | `production` | `preview` | `development` |

**Leave `NEXT_PUBLIC_API_BASE_URL` empty.** The same-origin `/api` proxy
is then used, which keeps the backend origin private and removes CORS from
production entirely.

### 9.3 After changing a variable

A change to a `NEXT_PUBLIC_*` variable requires a **redeploy** — the
value is baked into the build. Vercel prompts you to redeploy; do not
skip it.

### 9.4 The deploy hook

For the ingestion pipeline to publish a new matrix and for the platform to
notice it, nothing is needed: the API reads the matrix from Supabase
Storage on every request (cached), so a new matrix takes effect without a
frontend redeploy.

---

## 10. Render (backend)

### 10.1 Create the service

1. Sign in at <https://render.com> and create a **Web Service**.
2. Connect the repository.
3. Set the **Root Directory** to the repository root.
4. Set the runtime to **Python**.

### 10.2 Build and start commands

| Setting | Value |
| --- | --- |
| Build command | `pip install -r requirements.txt` |
| Start command | `uvicorn api.app.main:app --host 0.0.0.0 --port $PORT` |

### 10.3 Environment variables

Add these under **Environment**:

```
ENVIRONMENT=production
LOG_LEVEL=INFO

SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_KEY=<the anon key>
SUPABASE_SERVICE_ROLE_KEY=<the service_role key>
SUPABASE_ANON_KEY=<the anon key>

FRONTEND_ORIGINS=https://your-app.vercel.app
ALLOW_DEV_CORS=false
ALLOW_ANONYMOUS_API=false

NORMALIZED_MATRIX_FILE=            # leave empty: the matrix is read from Supabase Storage
SCORING_MATRIX_VERSIONS_TABLE=normalized_matrix_versions
SCORING_MATRIX_STORAGE_BUCKET=scoring-matrices
SUPABASE_EXPORT_BUCKET=exports

GROQ_API_KEY=<your-groq-key>
GROQ_MODEL=qwen/qwen3.8-27b

ORS_API_KEY=<your-openrouteservice-key>
OVERPASS_URL=https://overpass-api.de/api/interpreter

PROPERTY_SOURCE_URL=
PROPERTY_MANUAL_SOURCES=key|Example Portal|https://portal.example.com|https://portal.example.com/search?q={q}&lat={lat}&lon={lon}|Search this portal for premises near the location.
BROKERAGE_MANUAL_SOURCES=key|Example Retail Agents|https://agents.example.com|https://agents.example.com/find?lat={lat}&lon={lon}|Search this directory for agents covering the area.

SENTRY_DSN=<your-sentry-dsn>
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
ENABLE_METRICS=true

OUTBOUND_TIMEOUT_SECONDS=12
PROPERTY_SEARCH_TIMEOUT_SECONDS=10
MAX_PROPERTY_RESULTS=25
COST_ESTIMATION_ENABLED=false
COST_HORIZON_MONTHS=60
```

### 10.4 Health check

Set the health check path to:

```
/health/ready
```

It returns `200` when the scoring matrix is resolvable and `503` when it
is not. Use `/health` instead if you want a check that only proves the
process is alive.

### 10.5 CORS

`FRONTEND_ORIGINS` is the list of browser origins allowed to call the
API. In production set it to the Vercel origin and set
`ALLOW_DEV_CORS=false`, so the localhost origins are not accepted.

The frontend uses the same-origin proxy, so CORS is only exercised by
direct API calls.

---

## 11. Monitoring

**Grafana is not used.** The platform relies on free, self-hosted or
platform-native facilities only.

| Facility | What it monitors | Where to configure | Free-tier limitation |
| --- | --- | --- | --- |
| **Sentry** | Application errors, on both the backend and the browser. PII capture is disabled explicitly, so no demographic or site data is ever attached to an error report. | `SENTRY_DSN` (backend), `NEXT_PUBLIC_SENTRY_DSN` (frontend). | The free tier has a monthly event allowance and a low trace sample rate. `SENTRY_TRACES_SAMPLE_RATE` defaults to `0.1` for that reason. |
| **Prometheus metrics** | Request count, latency and error rate, exposed at `/metrics` by `prometheus-fastapi-instrumentator`. | `ENABLE_METRICS=true`. | There is no hosted Prometheus in the free tier. Point a free scraper at it — for example the Grafana Cloud free tier, an Uptime Kuma instance, or your own collector — or read it with `curl`. The endpoint is public on Render, so restrict it at the platform level. |
| **Structured logs** | Every request is timed, and any request slower than one second is logged as a warning. The format is `%(asctime)s [%(levelname)s] %(name)s: %(message)s`. | `LOG_LEVEL`. | Render keeps a limited number of log lines on the free tier; the log stream is the primary debugging tool. |
| **Health endpoints** | `/health` (liveness), `/health/ready` (readiness), `/health/integrations` (configuration fingerprint), `/health/config` (full configuration validation). | None. | — |
| **Uptime monitoring** | Any free uptime service can poll `/health/ready`. | The service of your choice. | Free tiers usually poll every five minutes. |

The alert thresholds worth acting on are documented in
`infra/monitoring/README.md`.

---

## 12. Free-tier summary

| Service | Free tier | Limitation | Consequence |
| --- | --- | --- | --- |
| Supabase | Yes (2 free projects) | 500 MB database, 1 GB file storage, project pauses after a week of inactivity | A paused project needs a manual wake-up. |
| Vercel | Yes (Hobby) | 100 GB bandwidth per month, serverless function limits | The analytical traffic is light. |
| Render | Yes (Web Service) | 750 free instance-hours per month, spins down when idle | The first request after an idle period is slow. Use the free Postgres-less setup with Supabase. |
| Groq | Yes | Rate limited per model per minute | Handled as a retryable 429; the manual form always works. |
| OpenRouteService | Yes | A fixed number of requests per day | The platform keeps a 2 000/day soft cap and caches every isochrone. |
| OpenStreetMap / Overpass | Free, no account | The public instance is rate limited | A 429 is reported as a source status. |
| Sentry | Yes | A monthly event allowance | The trace sample rate is kept low. |
| GitHub Actions | Yes (2 000 minutes for a free account) | The scheduled ingestion jobs consume the allowance | The jobs are scheduled daily, not on every commit. |
| Google OAuth | Yes | No usage limit on the sign-in flow | None. |

**No paid service is required to run the platform.**

---

## 13. Verifying the installation

### 13.1 The backend

```bash
curl http://127.0.0.1:8000/health
```

```json
{
  "status": "ok",
  "service": "retail-site-intelligence-api",
  "version": "2.0.0",
  "environment": "development",
  "uptime_seconds": 12.4
}
```

```bash
curl http://127.0.0.1:8000/health/config
```

This is the same report the **Settings** page renders. Each check has a
status of `ok`, `warning` or `error`, a plain-language explanation and
the environment variable that fixes it. No credential value is ever
returned.

| Check key | What it confirms |
| --- | --- |
| `supabase` | The project URL and a server-side key are configured. |
| `supabase_auth` | Sessions can be verified, so Google sign-in will work. |
| `scoring_matrix` | The normalised matrix can be resolved. |
| `groq` | The AI requirement builder is available. |
| `ors` | Drive-time catchments can be generated. |
| `property_source` | A licensed property feed is configured. |
| `property_manual` | Property portals are available for manual search. |
| `brokerage_manual` | Brokerage directories are available for manual search. |
| `cost_estimation` | Whether cost components may be estimated. |
| `sentry` | Error reporting is configured. |
| `metrics` | The Prometheus endpoint is exposed. |
| `anonymous_api` | Whether unauthenticated access is permitted. This is an **error** in production. |

### 13.2 The tests

```bash
pip install -r requirements.txt
python -m pytest -q
```

### 13.3 The frontend

```bash
cd frontend
pnpm install
pnpm typecheck
pnpm lint
pnpm test
pnpm build
```

### 13.4 The complete workflow

1. Start the backend and the frontend.
2. Open `http://localhost:3000`. Without Supabase configured the platform
   opens in local mode and says so.
3. With Supabase configured you are redirected to `/login`. Click
   **Continue with Google**.
4. Create a new analysis: choose a business type, buy/lease, the search
   area, the requirements, the parking, the facilities and the budgets.
5. Review, then confirm. The analysis is saved to Supabase.
6. The workspace opens with the ranking, the map, the explanation, the
   comparison, the cost analysis, the property and brokerage
   intelligence, the scenarios, the sensitivity analysis and the data
   quality report.
7. Generate the report and export it as PDF, CSV and Excel.
8. Sign out, sign in again, and reopen the analysis from the list.
