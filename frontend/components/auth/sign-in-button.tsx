'use client'

import * as React from 'react'
import { LoaderCircle, LogIn } from 'lucide-react'

import { Button } from '@/components/ui/button'
import { Alert } from '@/components/ui/feedback'
import { getSupabase } from '@/lib/supabase/client'

export type SignInButtonProps = Omit<
  React.ComponentProps<typeof Button>,
  'children' | 'onClick' | 'onError'
> & {
  /** Where the user is sent once the sign-in has completed. */
  nextPath?: string
  /**
   * Called with the full message when the sign-in could not be started.
   * When it is provided the caller renders the message itself.
   */
  onError?: (message: string) => void
}

/**
 * The callback route exchanges the OAuth code for a session and then
 * forwards the user to `nextPath`.
 */
function buildRedirectTo(nextPath: string): string {
  const origin = window.location.origin
  return `${origin}/auth/callback?next=${encodeURIComponent(nextPath)}`
}

/**
 * "Continue with Google".
 *
 * The button starts the Supabase OAuth flow.  The browser redirect is
 * performed by this component rather than by the Supabase client so that a
 * failure can be reported honestly instead of silently leaving the user on
 * a blank page.
 */
export function SignInButton({
  nextPath = '/analyses',
  onError,
  variant = 'outline',
  size = 'lg',
  className,
  disabled,
  ...props
}: SignInButtonProps) {
  const [pending, setPending] = React.useState(false)
  const [reason, setReason] = React.useState<string | null>(null)

  const report = React.useCallback(
    (detail: string) => {
      setReason(detail)
      onError?.(`Google sign-in is not available: ${detail}`)
    },
    [onError],
  )

  const handleClick = async () => {
    const supabase = getSupabase()
    if (!supabase) {
      report('Supabase is not configured on this deployment.')
      return
    }

    setPending(true)
    try {
      const { data, error } = await supabase.auth.signInWithOAuth({
        provider: 'google',
        options: {
          redirectTo: buildRedirectTo(nextPath),
          skipBrowserRedirect: true,
        },
      })

      if (error) {
        report(error.message)
        return
      }
      if (!data?.url) {
        report('The sign-in provider did not return an authorisation URL.')
        return
      }

      window.location.assign(data.url)
    } catch (error) {
      report(
        error instanceof Error
          ? error.message
          : 'The sign-in request could not be sent.',
      )
    } finally {
      setPending(false)
    }
  }

  return (
    <div className="space-y-3">
      <Button
        type="button"
        variant={variant}
        size={size}
        className={className}
        onClick={handleClick}
        disabled={disabled || pending}
        aria-busy={pending}
        {...props}
      >
        {pending ? <LoaderCircle className="animate-spin" /> : <LogIn />}
        Continue with Google
      </Button>

      {reason && !onError ? (
        <Alert tone="danger" title="Google sign-in is not available">
          {reason}
        </Alert>
      ) : null}
    </div>
  )
}
