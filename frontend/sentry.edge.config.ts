import * as Sentry from '@sentry/nextjs'

/**
 * Edge runtime error reporting.
 *
 * The DSN is read from the server environment; no credential is committed
 * to the repository.
 */
Sentry.init({
  dsn: process.env.SENTRY_DSN,
  environment: process.env.SENTRY_ENVIRONMENT ?? process.env.NODE_ENV,
  tracesSampleRate: Number(process.env.SENTRY_TRACES_SAMPLE_RATE ?? 0.1),
  // Demographic and site data privacy: never attach request payloads.
  sendDefaultPii: false,
})
