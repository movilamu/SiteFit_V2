'use client'

import * as Sentry from '@sentry/nextjs'
import { useEffect } from 'react'
import { AlertTriangle, RefreshCw } from 'lucide-react'

import { Button } from '@/components/ui/button'

/**
 * The application-wide error boundary.
 *
 * A failure is reported to Sentry without any payload, and the user is
 * shown a plain explanation and a way to recover.  The page is rendered
 * with the application's own stylesheet so it matches the rest of the
 * product.
 */
export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string }
  reset?: () => void
}) {
  useEffect(() => {
    Sentry.captureException(error)
  }, [error])

  return (
    <html lang="en">
      <body style={{ margin: 0, fontFamily: 'inherit' }}>
        <main
          style={{
            minHeight: '100vh',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '2rem',
            background: '#f4f6f8',
            color: '#111820',
          }}
        >
          <div
            style={{
              maxWidth: '32rem',
              background: '#ffffff',
              border: '1px solid #e0e4ea',
              borderRadius: '0.75rem',
              padding: '2rem',
            }}
          >
            <span
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                justifyContent: 'center',
                width: '2.5rem',
                height: '2.5rem',
                borderRadius: '0.5rem',
                background: '#fdeceb',
                color: '#b42318',
                marginBottom: '1rem',
              }}
            >
              <AlertTriangle size={20} aria-hidden="true" />
            </span>
            <h1 style={{ fontSize: '1.125rem', fontWeight: 600, margin: '0 0 0.5rem' }}>
              Something went wrong
            </h1>
            <p
              style={{
                fontSize: '0.8125rem',
                lineHeight: 1.6,
                color: '#57616f',
                margin: '0 0 1.25rem',
              }}
            >
              The page could not be displayed. The failure has been recorded. Try
              again, and if it persists contact the platform team with the time
              it occurred.
            </p>
            <Button type="button" onClick={() => reset?.()}>
              <RefreshCw />
              Try again
            </Button>
            {error.digest ? (
              <p style={{ marginTop: '1.25rem', fontSize: '0.6875rem', color: '#8a94a3' }}>
                Reference: {error.digest}
              </p>
            ) : null}
          </div>
        </main>
      </body>
    </html>
  )
}
