'use client'

import * as React from 'react'
import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { ArrowLeft, Building2, ShieldCheck } from 'lucide-react'

import { SignInButton } from '@/components/auth/sign-in-button'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Alert, Skeleton } from '@/components/ui/feedback'
import { isSupabaseConfigured } from '@/lib/supabase/config'

/**
 * Only a same-origin path is accepted as the post-sign-in destination, so a
 * crafted link cannot turn the sign-in page into an open redirect.
 */
function normaliseNext(value: string | null): string {
  if (!value) return '/analyses'
  if (!value.startsWith('/')) return '/analyses'
  if (value.startsWith('//')) return '/analyses'
  return value
}

export default function LoginPage() {
  return (
    <main className="bg-canvas flex min-h-screen items-center justify-center px-4 py-10">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center gap-2.5">
          <span className="bg-primary text-primary-foreground flex size-8 shrink-0 items-center justify-center rounded-lg text-[13px] font-bold">
            <Building2 className="size-4" aria-hidden="true" />
          </span>
          <span className="min-w-0">
            <span className="text-ink block text-[13px] leading-tight font-semibold tracking-tight">
              Site Intelligence
            </span>
            <span className="text-ink-subtle block text-[10px] tracking-[0.14em] uppercase">
              Retail expansion
            </span>
          </span>
        </div>

        <React.Suspense fallback={<LoginSkeleton />}>
          <LoginPanel />
        </React.Suspense>
      </div>
    </main>
  )
}

function LoginSkeleton() {
  return (
    <Card>
      <CardContent className="space-y-3">
        <Skeleton className="h-5 w-32" />
        <Skeleton className="h-9 w-full" />
        <Skeleton className="h-3 w-48" />
      </CardContent>
    </Card>
  )
}

function LoginPanel() {
  const searchParams = useSearchParams()
  const nextPath = normaliseNext(searchParams.get('next'))
  const callbackError = searchParams.get('error')

  const [error, setError] = React.useState<string | null>(null)
  const message = error ?? (callbackError ? `Google sign-in is not available: ${callbackError}` : null)

  return (
    <Card>
      <CardHeader>
        <CardTitle>Sign in</CardTitle>
        <CardDescription>
          Use your work Google account to open the site-selection workspace.
          Your analyses are private to your account.
        </CardDescription>
      </CardHeader>

      <CardContent className="space-y-4">
        {isSupabaseConfigured ? (
          <>
            {message ? (
              <Alert tone="danger" title="Sign-in failed">
                {message}
              </Alert>
            ) : null}

            <SignInButton nextPath={nextPath} onError={setError} />

            <p className="text-ink-subtle flex items-start gap-1.5 text-[11px] leading-relaxed">
              <ShieldCheck className="mt-0.5 size-3.5 shrink-0" aria-hidden="true" />
              <span>
                Access is granted through Supabase Auth. No password is stored by
                this platform.
              </span>
            </p>

            <div className="border-line border-t pt-3">
              <Button
                variant="ghost"
                size="sm"
                className="text-ink-muted hover:text-ink"
                nativeButton={false}
                render={<Link href="/analyses" />}
              >
                <ArrowLeft />
                Back to analyses
              </Button>
            </div>
          </>
        ) : (
          <>
            <Alert tone="warning" title="Sign-in is not configured">
              Sign-in is not configured. Set NEXT_PUBLIC_SUPABASE_URL and
              NEXT_PUBLIC_SUPABASE_ANON_KEY.
            </Alert>

            <p className="text-ink-muted text-xs leading-relaxed">
              The platform is running in local mode: the workspace is open and
              every analysis is stored in this browser only.
            </p>

            <div className="border-line border-t pt-3">
              <Button
                variant="outline"
                size="sm"
                nativeButton={false}
                render={<Link href="/analyses" />}
              >
                <ArrowLeft />
                Back to analyses
              </Button>
            </div>
          </>
        )}
      </CardContent>
    </Card>
  )
}
