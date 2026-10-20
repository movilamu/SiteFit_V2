'use client'

import * as React from 'react'
import Link from 'next/link'
import { LogIn, LogOut, UserRound } from 'lucide-react'
import type { AuthUser } from '@supabase/supabase-js'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { AuthProvider, useAuth } from '@/lib/auth/session'

/** The best display name the provider gave us. */
function displayName(user: AuthUser): string {
  const metadata = user.user_metadata as
    | { full_name?: string; name?: string }
    | undefined
  return metadata?.full_name || metadata?.name || user.email || 'Signed in'
}

/**
 * The header control that shows who is signed in.
 *
 * The provider is mounted here so the menu is self-contained and behaves
 * correctly wherever it is placed in the shell.  When the shell already
 * provides an `AuthProvider` the inner one simply shadows it with the same
 * session.
 */
export function UserMenu() {
  return (
    <AuthProvider>
      <UserMenuContent />
    </AuthProvider>
  )
}

function UserMenuContent() {
  const { user, loading, isConfigured, signOut } = useAuth()
  const [signingOut, setSigningOut] = React.useState(false)

  if (!isConfigured) {
    return (
      <Badge tone="outline" className="text-ink-subtle">
        Local mode
      </Badge>
    )
  }

  if (loading) {
    return (
      <span className="text-ink-subtle text-[11px] whitespace-nowrap">
        Checking session…
      </span>
    )
  }

  if (!user) {
    return (
      <Button
        size="sm"
        variant="ghost"
        className="text-ink-muted hover:text-ink"
        nativeButton={false}
        render={<Link href="/login" />}
      >
        <LogIn />
        Sign in
      </Button>
    )
  }

  const handleSignOut = async () => {
    setSigningOut(true)
    try {
      await signOut()
    } finally {
      setSigningOut(false)
    }
  }

  return (
    <div className="flex items-center gap-1.5">
      <span
        className="text-ink-muted flex min-w-0 items-center gap-1.5 text-[12px]"
        title={user.email ?? undefined}
      >
        <UserRound className="text-ink-subtle size-3.5 shrink-0" aria-hidden="true" />
        <span className="max-w-[18ch] truncate">{displayName(user)}</span>
      </span>
      <Button
        type="button"
        size="sm"
        variant="ghost"
        className="text-ink-muted hover:text-ink"
        onClick={handleSignOut}
        disabled={signingOut}
      >
        <LogOut />
        Sign out
      </Button>
    </div>
  )
}
