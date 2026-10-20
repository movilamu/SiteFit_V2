'use client'

import * as React from 'react'
import Link from 'next/link'
import {
  CircleAlert,
  CircleCheck,
  TriangleAlert,
  UserRound,
} from 'lucide-react'

import { AuthProvider, useAuth } from '@/lib/auth/session'
import { apiFetch } from '@/lib/api'
import { Badge, StatusDot } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card'
import { Alert, ErrorState, LoadingState } from '@/components/ui/feedback'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table'
import { isSupabaseConfigured } from '@/lib/supabase/config'

type ConfigStatus = 'ok' | 'warning' | 'error'

type ConfigCheck = {
  key: string
  label: string
  status: ConfigStatus
  detail: string
  variable?: string | null
  required?: boolean
}

type HealthConfigResponse = {
  environment: string
  valid: boolean
  checks: ConfigCheck[]
  error_count: number
  warning_count: number
}

/**
 * The status is carried by the label as well as by the colour, so the
 * meaning survives a monochrome screen and a colour-vision deficiency.
 */
function StatusBadge({ status }: { status: ConfigStatus }) {
  if (status === 'ok') {
    return (
      <Badge tone="success">
        <StatusDot tone="success" />
        <CircleCheck className="size-3" aria-hidden="true" />
        OK
      </Badge>
    )
  }
  if (status === 'warning') {
    return (
      <Badge tone="warning">
        <StatusDot tone="warning" />
        <TriangleAlert className="size-3" aria-hidden="true" />
        Warning
      </Badge>
    )
  }
  return (
    <Badge tone="danger">
      <StatusDot tone="danger" />
      <CircleAlert className="size-3" aria-hidden="true" />
      Error
    </Badge>
  )
}

export default function SettingsPage() {
  return (
    <AuthProvider>
      <SettingsContent />
    </AuthProvider>
  )
}

function SettingsContent() {
  const { user, loading: sessionLoading, isConfigured, signOut } = useAuth()
  const [config, setConfig] = React.useState<HealthConfigResponse | null>(null)
  const [error, setError] = React.useState<string | null>(null)
  const [loading, setLoading] = React.useState(true)
  const [signingOut, setSigningOut] = React.useState(false)

  const load = React.useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const response = await apiFetch<HealthConfigResponse>('/health/config')
      setConfig(response)
    } catch (requestError) {
      setError(
        requestError instanceof Error
          ? requestError.message
          : 'The configuration report could not be loaded.',
      )
    } finally {
      setLoading(false)
    }
  }, [])

  React.useEffect(() => {
    void load()
  }, [load])

  const handleSignOut = async () => {
    setSigningOut(true)
    try {
      await signOut()
    } finally {
      setSigningOut(false)
    }
  }

  return (
    <div className="mx-auto w-full max-w-[1100px] px-4 py-6 lg:px-8 lg:py-8">
      <header className="mb-6">
        <p className="section-eyebrow">Settings</p>
        <h1 className="text-ink mt-1.5 text-2xl font-semibold tracking-tight">
          Platform configuration
        </h1>
        <p className="text-ink-muted mt-1.5 max-w-3xl text-sm leading-relaxed">
          The state of the integrations the platform depends on, as reported
          by the API. The report never contains a secret value, only the name
          of the environment variable that has to be set.
        </p>
      </header>

      <div className="space-y-5">
        {!isConfigured ? (
          <Alert tone="warning" title="Local mode">
            The platform is running in local mode: Supabase is not configured,
            so sign-in is disabled and every analysis is stored in this
            browser only. Set NEXT_PUBLIC_SUPABASE_URL and
            NEXT_PUBLIC_SUPABASE_ANON_KEY to enable Google sign-in and shared
            analyses.
          </Alert>
        ) : null}

        <Card>
          <CardHeader>
            <CardTitle>Configuration validation</CardTitle>
            <CardDescription>
              Reported by <code className="font-mono">/api/health/config</code>.
            </CardDescription>
          </CardHeader>
          <CardContent className="p-0">
            {loading ? (
              <LoadingState label="Reading the configuration report…" />
            ) : error ? (
              <div className="p-4">
                <ErrorState
                  title="The configuration report is unavailable"
                  description={error}
                  onRetry={() => void load()}
                />
              </div>
            ) : config && config.checks.length > 0 ? (
              <>
                <div className="border-line flex flex-wrap items-center gap-x-4 gap-y-1 border-b px-5 py-3 text-xs">
                  <span className="text-ink-muted">
                    Environment{' '}
                    <span className="text-ink font-medium">{config.environment}</span>
                  </span>
                  <span className="text-ink-muted">
                    {config.error_count}{' '}
                    {config.error_count === 1 ? 'error' : 'errors'}
                  </span>
                  <span className="text-ink-muted">
                    {config.warning_count}{' '}
                    {config.warning_count === 1 ? 'warning' : 'warnings'}
                  </span>
                  <span className="text-ink-muted">
                    {config.valid
                      ? 'All required integrations are configured'
                      : 'At least one required integration is missing'}
                  </span>
                </div>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Integration</TableHead>
                      <TableHead>Status</TableHead>
                      <TableHead>Detail</TableHead>
                      <TableHead>Environment variable</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {config.checks.map((check) => (
                      <TableRow key={check.key}>
                        <TableCell>
                          <span className="text-ink block text-sm font-medium">
                            {check.label}
                          </span>
                          {check.required ? (
                            <span className="text-ink-subtle text-[11px]">
                              Required
                            </span>
                          ) : null}
                        </TableCell>
                        <TableCell>
                          <StatusBadge status={check.status} />
                        </TableCell>
                        <TableCell className="text-ink-muted text-xs leading-relaxed">
                          {check.detail}
                        </TableCell>
                        <TableCell>
                          {check.variable ? (
                            <code className="border-line bg-surface-muted text-ink-muted rounded border px-1.5 py-0.5 font-mono text-[11px]">
                              {check.variable}
                            </code>
                          ) : (
                            <span className="text-ink-subtle text-[11px]">
                              Not applicable
                            </span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </>
            ) : (
              <div className="px-5 py-6">
                <p className="text-ink-muted text-xs">
                  The API reported no configuration checks.
                </p>
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Account</CardTitle>
            <CardDescription>
              The account the analyses are saved against.
            </CardDescription>
          </CardHeader>
          <CardContent>
            {sessionLoading ? (
              <p className="text-ink-muted text-xs">Checking the session…</p>
            ) : user ? (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex min-w-0 items-center gap-2.5">
                  <span className="bg-surface-muted text-ink-muted flex size-8 shrink-0 items-center justify-center rounded-full">
                    <UserRound className="size-4" aria-hidden="true" />
                  </span>
                  <div className="min-w-0">
                    <p className="text-ink truncate text-sm font-medium">
                      {user.email ?? 'Signed in'}
                    </p>
                    <p className="text-ink-subtle text-[11px]">
                      Analyses are saved to your account and are visible only to
                      you.
                    </p>
                  </div>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={handleSignOut}
                  disabled={signingOut}
                >
                  Sign out
                </Button>
              </div>
            ) : isConfigured ? (
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="text-ink-muted text-xs">
                  Nobody is signed in on this device.
                </p>
                <Button
                  variant="outline"
                  size="sm"
                  nativeButton={false}
                  render={<Link href="/login" />}
                >
                  Sign in
                </Button>
              </div>
            ) : (
              <p className="text-ink-muted text-xs leading-relaxed">
                Sign-in is not configured on this deployment, so there is no
                account. Analyses are stored in this browser only.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  )
}
