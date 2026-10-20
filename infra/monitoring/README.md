# Monitoring

The platform's observability stack is deliberately small: two pieces that
answer the two questions an operator actually asks.

## Error tracking — Sentry

- **API.** `api/app/main.py` initialises Sentry once at start-up, with
  `send_default_pii=False` so that demographic and candidate-site data can
  never be attached to an error report. The DSN comes from `SENTRY_DSN`.
- **Frontend.** `frontend/sentry.client.config.ts`,
  `sentry.server.config.ts` and `sentry.edge.config.ts` read
  `NEXT_PUBLIC_SENTRY_DSN` and `SENTRY_DSN`. No DSN is committed to the
  repository.
- **Reported context.** Only the status, the route and the error message
  are captured. Request bodies, site attributes and cost figures are not.

## Metrics — Prometheus

`prometheus-fastapi-instrumentator` exposes `/metrics` when
`ENABLE_METRICS` is true. The API also records a server-side
`X-Response-Time-Ms` header on every request and logs any request that
takes longer than one second.

Recommended scrape configuration:

```yaml
scrape_configs:
  - job_name: retail-site-api
    metrics_path: /metrics
    static_configs:
      - targets: ["<api-host>:8000"]
```

## Health endpoints

| Endpoint | Purpose | Behaviour |
| --- | --- | --- |
| `GET /health` | Liveness. | Always 200 while the process is running. It does not depend on any external service, so a database outage never causes the platform to be restarted. |
| `GET /health/ready` | Readiness. | 200 when the normalised scoring matrix is available, 503 when it is not. Every ranking endpoint depends on that matrix. |
| `GET /health/integrations` | Configuration fingerprint. | Lists which integrations are configured. It never returns a credential. |

## Alert thresholds

These are the thresholds worth alerting on. They are derived from the
platform's own behaviour rather than from generic defaults.

| Signal | Threshold | Why |
| --- | --- | --- |
| `/health/ready` returning 503 | for 2 consecutive checks | The API cannot serve a ranking without the matrix. |
| `X-Response-Time-Ms` p95 | above 300 ms | The matrix is designed for sub-100 ms scoring; a p95 above 300 ms means the matrix is far larger than expected or the host is under-resourced. |
| `POST /score` failure rate | above 1 % over 15 minutes | A scoring failure is either a malformed weight request (a user problem) or a corrupted matrix (an operational problem). |
| `POST /properties/search` source statuses | any source reporting `rate_limited` for 30 minutes | The OpenStreetMap Overpass free tier enforces a daily budget. |
| `ors_daily_usage.request_count` | above 2 000 in a day | The ingestion job keeps a soft cap of 2 000, below the 2 500 daily limit, so the cap must not be exceeded. |
| `GET /data-quality` overall grade | below `fair` | The ranking's evidence base has degraded; the results should not be presented without the caveats. |

## On-call notes

- The scoring matrix is the single point of failure for the analytical
  endpoints. Rebuild it with `python -m scoring.precompute_matrix
  --persist`.
- The matrix version is recorded in `normalized_matrix_versions`, together
  with the number of sites in and out, the number excluded by hard
  constraints and the criteria that were scored.
- If a ranking looks wrong, check the coverage reported with it first: a
  low coverage means most of the configured criteria had no data in the
  current release, which is a data problem rather than a scoring problem.
- `/health/ready` and `/data-quality` are the two endpoints to check
  first when a user reports that the results have changed.
