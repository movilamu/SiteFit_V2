# Setup checklist

A step-by-step checklist for deploying the Retail Site Intelligence &
Site Selection Platform.

Every value below uses the exact variable name the code reads.

---

## 1. What accounts do I need?

| Account | Needed for | Free? |
| --- | --- | --- |
| **Supabase** | The database, PostGIS, authentication and file storage | Yes |
| **Google Cloud** | The OAuth client used for Google sign-in | Yes |
| **Groq** | The AI requirement builder and the explanation writer | Yes |
| **OpenRouteService** | Drive-time catchments | Yes, with a daily limit |
| **Vercel** | The frontend | Yes (Hobby) |
| **Render** | The backend | Yes (with an idle spin-down) |
| **Sentry** *(optional)* | Error tracking | Yes |
| **GitHub** | The scheduled ingestion jobs | Yes |

**No paid service is required.**

---

## 2. Where do I create each account?

| Account | URL |
| --- | --- |
| Supabase | <https://supabase.com/dashboard> |
| Google Cloud | <https://console.cloud.google.com> |
| Groq | <https://console.groq.com/keys> |
| OpenRouteService | <https://openrouteservice.org/dev/#/signup> |
| Vercel | <https://vercel.com/dashboard> |
| Render | <https://render.com/dashboard> |
| Sentry | <https://sentry.io> |

---

## 3. Which API keys do I need, and where do I get each one?

| Key | Where it comes from | Goes in |
| --- | --- | --- |
| Supabase anon key | Supabase → Project Settings → API Keys | `SUPABASE_ANON_KEY` (backend) and `NEXT_PUBLIC_SUPABASE_ANON_KEY` (frontend) |
| Supabase service-role key | Supabase → Project Settings → API Keys | `SUPABASE_SERVICE_ROLE_KEY` (backend **only**) |
| Supabase JWT secret | Supabase → Project Settings → API Keys | `SUPABASE_JWT_SECRET` (backend, optional) |
| Google client id and secret | Google Cloud → APIs & Services → Credentials | **Supabase dashboard** → Authentication → Sign In / Providers → Google. *Not* an environment variable. |
| Groq API key | <https://console.groq.com/keys> | `GROQ_API_KEY` (backend **only**) |
| OpenRouteService key | <https://openrouteservice.org/dev/#/signup> | `ORS_API_KEY` (backend **only**) |
| Sentry DSN | Sentry → Project → Settings → Client Keys | `SENTRY_DSN` (backend) and `NEXT_PUBLIC_SENTRY_DSN` (frontend) |

---

## 4. Where does each environment variable go?

### Backend — a local `.env.local` in the repository root in development, Render environment variables in production

The API, the scoring jobs and the ingestion jobs all read the file through
`platform_env.py`, which looks for `.env.local` and then `.env` in the
repository root.  A variable that is already set in the process
environment always wins, so the platform's own configuration takes
precedence over the file.  The full list is in `.env.example`.

```
ENVIRONMENT=production
LOG_LEVEL=INFO

SUPABASE_URL=https://<project-ref>.supabase.co
SUPABASE_KEY=<anon key>
SUPABASE_SERVICE_ROLE_KEY=<service_role key>
SUPABASE_ANON_KEY=<anon key>
SUPABASE_JWT_SECRET=<jwt secret>          # optional
SUPABASE_EXPORT_BUCKET=exports

FRONTEND_ORIGINS=https://your-app.vercel.app
ALLOW_DEV_CORS=false
ALLOW_ANONYMOUS_API=false

NORMALIZED_MATRIX_FILE=                     # empty: read the matrix from Supabase Storage
SCORING_MATRIX_VERSIONS_TABLE=normalized_matrix_versions
SCORING_MATRIX_STORAGE_BUCKET=scoring-matrices

GROQ_API_KEY=<groq key>
GROQ_MODEL=qwen/qwen3.8-27b
GROQ_EXPLANATION_MODEL=qwen/qwen3.8-27b
GROQ_TIMEOUT_SECONDS=30

ORS_API_KEY=<openrouteservice key>
OVERPASS_URL=https://overpass-api.de/api/interpreter

PROPERTY_SOURCE_URL=
PROPERTY_SOURCE_FILE=
PROPERTY_REQUEST_TIMEOUT=15
PROPERTY_MANUAL_SOURCES=key|Example Portal|https://portal.example.com|https://portal.example.com/search?q={q}&lat={lat}&lon={lon}|Search this portal for premises near the location.
BROKERAGE_MANUAL_SOURCES=key|Example Retail Agents|https://agents.example.com|https://agents.example.com/find?lat={lat}&lon={lon}|Search this directory for agents covering the area.

COST_ESTIMATION_ENABLED=false
COST_HORIZON_MONTHS=60

SENTRY_DSN=<sentry dsn>
SENTRY_ENVIRONMENT=production
SENTRY_TRACES_SAMPLE_RATE=0.1
ENABLE_METRICS=true

OUTBOUND_TIMEOUT_SECONDS=12
PROPERTY_SEARCH_TIMEOUT_SECONDS=10
MAX_PROPERTY_RESULTS=25
```

### Frontend — `frontend/.env.local` in development, Vercel environment variables in production

```
API_BASE_URL=https://<your-backend>.onrender.com
NEXT_PUBLIC_API_BASE_URL=                    # leave EMPTY: use the same-origin proxy

NEXT_PUBLIC_SUPABASE_URL=https://<project-ref>.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=<anon key>

NEXT_PUBLIC_SENTRY_DSN=<sentry dsn>
NEXT_PUBLIC_SENTRY_ENVIRONMENT=production
NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE=0.1
```

### Supabase dashboard

| Setting | Value |
| --- | --- |
| Authentication → URL Configuration → Site URL | `https://your-app.vercel.app` |
| Authentication → URL Configuration → Redirect URLs | `https://your-app.vercel.app/auth/callback` and `http://localhost:3000/auth/callback` |
| Authentication → Sign In / Providers → Google | Enabled, with the Google client id and secret |
| Database → Extensions | `postgis` enabled |
| Storage | `scoring-matrices` and `exports` buckets |

---

## 5. Which variables are public and which are secret?

**Public** — these reach the browser and are safe to expose, because
they only ever carry the `anon` role:

* `NEXT_PUBLIC_SUPABASE_URL`
* `NEXT_PUBLIC_SUPABASE_ANON_KEY`
* `NEXT_PUBLIC_API_BASE_URL` (leave empty)
* `NEXT_PUBLIC_SENTRY_DSN`
* `NEXT_PUBLIC_SENTRY_ENVIRONMENT`
* `NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE`

**Secret** — server only. Never put these in a `NEXT_PUBLIC_*` variable,
a client component, a commit, a screenshot or a document:

* `SUPABASE_SERVICE_ROLE_KEY`
* `SUPABASE_JWT_SECRET`
* `GROQ_API_KEY`
* `ORS_API_KEY`
* `SENTRY_DSN`
* `PROPERTY_SOURCE_URL` (it may embed a credential)
* The database password

The configuration report at `GET /health/config` never returns a value
for any variable — only whether it is set and what to do about it.

---

## 6. Which migrations must I run, and how?

Three, in order:

1. `infra/sql/migrations/0001_init.sql`
2. `infra/sql/migrations/0002_site_selection.sql`
3. `infra/sql/migrations/0003_authentication_and_artefacts.sql`
4. `infra/sql/migrations/0004_reconcile_live_schema.sql`
5. `infra/sql/migrations/0005_spatial_functions.sql`

**Through the SQL editor:** open each file, paste it whole, run it.

**Through the CLI:**

```bash
npm install -g supabase
supabase login
supabase link --project-ref <project-ref>
supabase db push --include-all
```

Then confirm the row-level security is in place:

```sql
select tablename, policyname from pg_policies
where schemaname = 'public' order by tablename;
```

Every user-owned table should have one `*_owner_policy`.

---

## 7. Which Google OAuth settings must I change?

**Google Cloud → APIs & Services → OAuth consent screen**

* Application type: **External**
* Application name, support email and developer contact email

**Google Cloud → APIs & Services → Credentials → Create credentials → OAuth
client ID → Web application**

| Field | Value |
| --- | --- |
| Authorised JavaScript origins | `http://localhost:3000`<br>`https://your-app.vercel.app` |
| Authorised redirect URIs | `https://<project-ref>.supabase.co/auth/v1/callback` |

**Supabase → Authentication → Sign In / Providers → Google**

* Enable the provider
* Paste the client id and the client secret
* Copy the **Callback URL** shown there into Google's authorised redirect
  URIs — it is normally the URL above

**Supabase → Authentication → URL Configuration**

* Site URL: `https://your-app.vercel.app`
* Redirect URLs: add `https://your-app.vercel.app/auth/callback` and
  `http://localhost:3000/auth/callback`

---

## 8. How do I configure Groq?

1. Create a key at <https://console.groq.com/keys>.
2. Set `GROQ_API_KEY` in the **backend** environment.
3. Optionally set `GROQ_MODEL` and `GROQ_EXPLANATION_MODEL`.

Check it:

```bash
curl http://127.0.0.1:8000/health/config | grep -A3 groq
```

`"status": "ok"` means the builder is available. A `warning` means the
manual requirement form is used instead — everything else still works.

---

## 9. How do I configure OpenRouteService?

1. Create a key at <https://openrouteservice.org/dev/#/signup>.
2. Set `ORS_API_KEY` in the **backend** environment.
3. Run the ingestion to generate the catchments:

```bash
python -m ingestion.generate_catchments --profile driving-car --short-minutes 10 --long-minutes 15
```

The daily request count is tracked in the `ors_daily_usage` table.

---

## 10. How do I configure the property and brokerage sources?

**Automated feed** (only if you are licensed to use one):

```bash
PROPERTY_SOURCE_URL=https://your-feed.example.com/listings.json
# or
PROPERTY_SOURCE_FILE=/opt/data/listings.csv
```

**Manual navigation** — the portals that are not queried automatically:

```bash
PROPERTY_MANUAL_SOURCES=key|Example Portal|https://portal.example.com|https://portal.example.com/search?q={q}&lat={lat}&lon={lon}|Search this portal for premises near the location.||key2|Another Portal|https://another.example.com||Open the portal and search the area manually.
BROKERAGE_MANUAL_SOURCES=key|Example Retail Agents|https://agents.example.com|https://agents.example.com/find?lat={lat}&lon={lon}|Search this directory for agents covering the area.
```

Format: `key | Name | Homepage | Search URL template | Instructions`, entries
separated by `||`. In the template, `{lat}`, `{lon}` and `{q}` are
substituted.

Nothing is scraped. The platform links to the source and labels it as a
manual source.

---

## 11. How do I build and publish the scoring matrix?

```bash
pip install -r requirements.txt
python -m scoring.precompute_matrix --persist
```

This needs `SUPABASE_URL` and a server-side key. It writes the matrix to
the `scoring-matrices` bucket and records the version in
`normalized_matrix_versions`.

Check it:

```bash
curl http://127.0.0.1:8000/health/ready
```

`"status": "ready"` means the matrix resolves.

---

## 12. How do I deploy the frontend?

1. Vercel → **Add New → Project** → import the repository.
2. Root directory: `frontend`.
3. Framework preset: Next.js. Build command: `pnpm build`.
4. Add the environment variables (Production and Preview).
5. Deploy.
6. Add the Vercel URL to the Supabase redirect URLs and to Google's
   authorised JavaScript origins.

**A change to a `NEXT_PUBLIC_*` variable needs a redeploy.** Vercel
prompts for it; do not skip it.

---

## 13. How do I deploy the backend?

1. Render → **New → Web Service** → connect the repository.
2. Root directory: the repository root. Runtime: Python.
3. Build command: `pip install -r requirements.txt`
4. Start command: `uvicorn api.app.main:app --host 0.0.0.0 --port $PORT`
5. Health check path: `/health/ready`
6. Add the environment variables.
7. Deploy, then set `API_BASE_URL` on Vercel to the Render URL and
   redeploy the frontend.

---

## 14. How do I test the Google sign-in?

1. Open the frontend.
2. Without a session you are redirected to `/login`.
3. Click **Continue with Google**.
4. You should return to the page you came from, signed in, with your
   name in the sidebar footer.
5. Sign out from the same place, then sign in again.

If the provider is disabled, the login page shows the provider's error
rather than a blank screen. If Supabase is not configured at all, the
login page explains what to set and links back to the analyses.

---

## 15. How do I test the complete workflow?

- [ ] Create a new analysis and choose a business type.
- [ ] Choose buy, lease or buy-or-lease.
- [ ] Set the search area on the map and check the radius.
- [ ] Enter the business requirements and change at least one importance
      level.
- [ ] Set the parking requirement and choose the behaviour explicitly.
- [ ] Classify the facilities.
- [ ] Enter the budgets and choose what happens when one is exceeded.
- [ ] Try the AI requirement builder with a sentence, and confirm the
      interpretation is shown as editable fields before it is applied.
- [ ] Review, then confirm. The analysis is saved.
- [ ] The workspace opens: the ranking, the map, the explanation, the
      comparison, the cost analysis, the property and brokerage
      intelligence, the scenarios, the sensitivity analysis and the data
      quality report.
- [ ] Create a scenario, change the weights, and confirm the ranking
      changes are shown.
- [ ] Generate the report and export it as PDF, CSV and Excel. Confirm the
      export contains the exact weights.
- [ ] Sign out, sign in again, and reopen the analysis from the list.

---

## 16. Go-live checklist

- [ ] `ALLOW_ANONYMOUS_API=false` in production.
- [ ] `ALLOW_DEV_CORS=false` in production.
- [ ] `FRONTEND_ORIGINS` contains only the production frontend origin.
- [ ] `COST_ESTIMATION_ENABLED` is decided deliberately. It is `false` by
      default, and while it is off no cost component is ever estimated.
- [ ] Every secret is in the platform's environment, never in the
      repository.
- [ ] The Google client secret is in the Supabase dashboard, not in an
      environment variable.
- [ ] All five migrations have been applied, in order.
- [ ] The row-level security check returns the expected result.
- [ ] `GET /health/config` reports no `error` entries.
- [ ] The scoring matrix has been published and `/health/ready` returns
      `ready`.
- [ ] The ingestion jobs have run at least once, or the platform is
      operating on the existing data release.
- [ ] Sentry is configured, with the trace sample rate kept low.
- [ ] An uptime check polls `/health/ready`.
- [ ] The data quality report has been read, and the known limitations
      are understood by the people who will use the recommendations.
- [ ] Everyone using the platform understands that it is decision support,
      not a prediction, and that site visits and commercial due diligence
      remain necessary.
