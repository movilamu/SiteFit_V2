import { withSentryConfig } from '@sentry/nextjs'

/**
 * API routes are proxied through Next.js under the `/api` prefix so the
 * backend origin is never exposed to the browser, no CORS negotiation is
 * required in production, and the proxy can never collide with a route in
 * the application itself.
 *
 * The proxy itself lives in `app/api/[...path]/route.ts` rather than in a
 * rewrite, so that it can turn an unreachable backend into an explicit
 * `502` with an actionable message instead of the opaque "Internal
 * Server Error" a rewrite produces.
 */
/** @type {import('next').NextConfig} */
const nextConfig = {
  /**
   * Hosts that may load the dev server's resources in development.
   * Next.js blocks cross-origin dev requests by default, which breaks the
   * development experience when the browser reaches the app through
   * `127.0.0.1` rather than `localhost`.
   */
  allowedDevOrigins: ['127.0.0.1', 'localhost'],
  typescript: {
    // Type errors must fail the build. A broken type contract is a
    // production defect, not a warning.
    ignoreBuildErrors: false,
  },
  images: {
    unoptimized: true,
  },
}

export default withSentryConfig(nextConfig, {
  // For all available options, see:
  // https://docs.sentry.io/platforms/javascript/guides/nextjs/manual-setup/

  org: "k-1a",

  project: "retail-site-frontend",

  // Only print logs for uploading source maps in CI
  silent: !process.env.CI,

  // Upload a larger set of source maps for prettier stack traces (increases build time)
  widenClientFileUpload: true,

  webpack: {
    // Enables automatic instrumentation for Vercel Cron Monitors. (Does not yet work with App Router route handlers.)
    // See the following for more information:
    // https://docs.sentry.io/platforms/javascript/guides/nextjs/manual-setup/

    // Automatically upload source maps for better error reporting in production
    automaticVercelMonitors: true,

    // Tree-shaking options for reducing bundle size
    treeshake: {
      // Automatically tree-shake Sentry logger statements to reduce bundle size
      removeDebugLogging: true,
    },
  },
});
