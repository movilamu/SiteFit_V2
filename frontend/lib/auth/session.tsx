'use client'

import * as React from 'react'
import { useRouter } from 'next/navigation'
import type { AuthSession, AuthUser } from '@supabase/supabase-js'

import { getSupabase } from '@/lib/supabase/client'
import { isSupabaseConfigured } from '@/lib/supabase/config'

export type AuthContextValue = {
  /** The signed-in user, or `null` when there is no session. */
  user: AuthUser | null
  /** The current Supabase session, or `null`. */
  session: AuthSession | null
  /** True while the session is still being read from the cookies. */
  loading: boolean
  /** True when this deployment has Supabase configured. */
  isConfigured: boolean
  /** End the session and return to the sign-in page. */
  signOut: () => Promise<void>
}

const AuthContext = React.createContext<AuthContextValue>({
  user: null,
  session: null,
  loading: false,
  isConfigured: isSupabaseConfigured,
  signOut: async () => {},
})

/**
 * Provide the Supabase session to the client components of the platform.
 *
 * The session is read once on mount and then kept up to date through
 * `onAuthStateChange`.  When Supabase is not configured there is no session
 * to read: `user` stays `null`, `loading` stays `false` and `isConfigured`
 * is `false`, so the application renders normally in local mode.
 */
export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter()
  const [session, setSession] = React.useState<AuthSession | null>(null)
  const [user, setUser] = React.useState<AuthUser | null>(null)
  const [loading, setLoading] = React.useState<boolean>(isSupabaseConfigured)

  React.useEffect(() => {
    if (!isSupabaseConfigured) {
      setLoading(false)
      return
    }

    const supabase = getSupabase()
    if (!supabase) {
      setLoading(false)
      return
    }

    let active = true

    supabase.auth
      .getSession()
      .then(({ data }) => {
        if (!active) return
        setSession(data.session)
        setUser(data.session?.user ?? null)
        setLoading(false)
      })
      .catch(() => {
        if (active) setLoading(false)
      })

    const { data: listener } = supabase.auth.onAuthStateChange(
      (_event, nextSession) => {
        if (!active) return
        setSession(nextSession)
        setUser(nextSession?.user ?? null)
        setLoading(false)
      },
    )

    return () => {
      active = false
      listener.subscription.unsubscribe()
    }
  }, [])

  const signOut = React.useCallback(async () => {
    const supabase = getSupabase()
    try {
      await supabase?.auth.signOut()
    } finally {
      setSession(null)
      setUser(null)
      router.push('/login')
      router.refresh()
    }
  }, [router])

  const value = React.useMemo<AuthContextValue>(
    () => ({
      user,
      session,
      loading,
      isConfigured: isSupabaseConfigured,
      signOut,
    }),
    [user, session, loading, signOut],
  )

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

/**
 * Read the current session.
 *
 * Outside an `AuthProvider` the hook returns the neutral state: no user, no
 * session and no loading.
 */
export function useAuth(): AuthContextValue {
  return React.useContext(AuthContext)
}
