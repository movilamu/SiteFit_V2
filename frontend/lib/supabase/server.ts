import { createServerClient, type SetAllCookies } from '@supabase/ssr'
import { cookies } from 'next/headers'

import { isSupabaseConfigured, supabaseAnonKey, supabaseUrl } from './config'

/**
 * Create a Supabase client for a server component, a route handler or a
 * server action.
 *
 * The session is read from the request cookies and written back through the
 * same cookie store, so a refreshed token survives the response.  `null` is
 * returned when Supabase is not configured, which keeps the platform usable
 * in a local, unconfigured environment.
 */
export async function createSupabaseServerClient() {
  if (!isSupabaseConfigured) return null

  // Next 16: `cookies()` is asynchronous.
  const cookieStore = await cookies()

  return createServerClient(supabaseUrl, supabaseAnonKey, {
    cookies: {
      getAll() {
        return cookieStore.getAll()
      },
      setAll(cookiesToSet: Parameters<SetAllCookies>[0]) {
        try {
          cookiesToSet.forEach(({ name, value, options }) => {
            cookieStore.set(name, value, options)
          })
        } catch {
          // A Server Component cannot mutate cookies.  The proxy and the
          // route handler refresh the session instead, so this is safe.
        }
      },
    },
  })
}
