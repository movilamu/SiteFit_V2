import { createBrowserClient } from '@supabase/ssr'
import type { SupabaseClient } from '@supabase/supabase-js'

import { isSupabaseConfigured, supabaseAnonKey, supabaseUrl } from './config'

let browserClient: SupabaseClient | null = null

/**
 * Return the browser Supabase client.
 *
 * `null` is returned when Supabase is not configured, or when the module is
 * evaluated outside a browser (server rendering, a route handler, a test).
 * The platform must keep working without a Supabase project, so this never
 * throws.
 */
export function getSupabaseClient(): SupabaseClient | null {
  if (!isSupabaseConfigured) return null
  if (typeof window === 'undefined') return null
  if (!browserClient) {
    browserClient = createBrowserClient(supabaseUrl, supabaseAnonKey)
  }
  return browserClient
}

/**
 * Named accessor for the browser client.
 *
 * `getSupabase()?.auth.getSession()` is the pattern used by the API client
 * and by the project store to read the current session.
 */
export function getSupabase(): SupabaseClient | null {
  return getSupabaseClient()
}
