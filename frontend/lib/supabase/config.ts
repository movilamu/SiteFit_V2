/**
 * Supabase configuration.
 *
 * Only the two public, browser-safe values are read here.  No other
 * environment variable is consulted for Supabase: when either of them is
 * missing the platform runs in "local mode", where sign-in is disabled and
 * the analyses are kept in the browser.
 */

const configuredUrl = process.env.NEXT_PUBLIC_SUPABASE_URL?.trim() ?? ''
const configuredAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim() ?? ''

/** The Supabase project URL, or an empty string when it is not configured. */
export const supabaseUrl = configuredUrl

/**
 * The public (anon) Supabase key, or an empty string when it is not
 * configured.  It is safe to expose to the browser: the row-level security
 * policies in Supabase are what protect the data.
 */
export const supabaseAnonKey = configuredAnonKey

/**
 * True only when both the project URL and the anon key are present.
 *
 * Every consumer degrades gracefully when this is false, so the platform
 * stays usable in a local, unconfigured environment.
 */
export const isSupabaseConfigured =
  configuredUrl.length > 0 && configuredAnonKey.length > 0
