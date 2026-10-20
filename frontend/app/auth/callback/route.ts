import { NextResponse } from 'next/server'

import { createSupabaseServerClient } from '@/lib/supabase/server'

/**
 * Only a same-origin path is accepted as the post-sign-in destination, so a
 * crafted `next` value cannot turn the callback into an open redirect.
 */
function safeNextPath(value: string | null): string {
  if (!value) return '/analyses'
  if (!value.startsWith('/')) return '/analyses'
  if (value.startsWith('//')) return '/analyses'
  return value
}

function loginRedirect(
  origin: string,
  reason: string,
  next: string | null,
): NextResponse {
  const url = new URL('/login', origin)
  url.searchParams.set('error', reason)
  if (next) url.searchParams.set('next', next)
  return NextResponse.redirect(url)
}

/**
 * The OAuth callback.
 *
 * The authorisation code is exchanged for a session, the session cookies are
 * written to the response, and the user is forwarded to the page they came
 * from.  Every failure is reported on the sign-in page rather than on a
 * blank screen.
 */
export async function GET(request: Request) {
  const url = new URL(request.url)
  const code = url.searchParams.get('code')
  const next = url.searchParams.get('next')

  const providerError =
    url.searchParams.get('error_description') ?? url.searchParams.get('error')

  if (!code) {
    return loginRedirect(
      url.origin,
      providerError ?? 'The sign-in was not completed.',
      next,
    )
  }

  const supabase = await createSupabaseServerClient()
  if (!supabase) {
    return loginRedirect(
      url.origin,
      'Supabase is not configured on this deployment.',
      next,
    )
  }

  const { error } = await supabase.auth.exchangeCodeForSession(code)

  if (error) {
    return loginRedirect(url.origin, error.message, next)
  }

  return NextResponse.redirect(new URL(safeNextPath(next), url.origin))
}
