import * as Sentry from '@sentry/nextjs'

/**
 * Client-side error reporting.
 *
 * The DSN is read from the environment; no credential is committed to the
 * repository.  PII capture is disabled explicitly so that demographic and
 * candidate-site data can never be attached to an error report.
 */
Sentry.init({
  dsn: process.env.NEXT_PUBLIC_SENTRY_DSN,
  environment: process.env.NEXT_PUBLIC_SENTRY_ENVIRONMENT ?? process.env.NODE_ENV,
  tracesSampleRate: Number(process.env.NEXT_PUBLIC_SENTRY_TRACES_SAMPLE_RATE ?? 0.1),
  replaysSessionSampleRate: 0,
  replaysOnErrorSampleRate: 0,
  // Demographic and site data privacy: never attach user information.
  sendDefaultPii: false,
  beforeSend(event) {
    if (event.user) {
      delete event.user.ip_address
      delete event.user.email
      delete event.user.username
    }
    return event
  },
})
