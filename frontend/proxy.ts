import { createServerClient, type SetAllCookies } from '@supabase/ssr'
import { NextResponse, type NextRequest } from 'next/server'

import {
  isSupabaseConfigured,
  supabaseAnonKey,
  supabaseUrl,
} from '@/lib/supabase/config'

/**
 * Route protection.
 *
 * The analytical workspaces are only available to a signed-in user.  The
 * check is deliberately optimistic: the session is read from the request
 * cookies, which keeps the proxy fast and free of database round-trips.
 * The authoritative check happens in the API, which verifies the bearer
 * token on every request.
 *
 * When Supabase is not configured the platform runs in local mode and every
 * route stays open, so the application remains fully usable without a
 * Supabase project.
 */
export async function proxy(request: NextRequest) {
  if (!isSupabaseConfigured) {
    return NextResponse.next()
  }

  let response = NextResponse.next({ request })

  const supabase = createServerClient(supabaseUrl, supabaseAnonKey, {
    cookies: {
      getAll() {
        return request.cookies.getAll()
      },
      setAll(cookiesToSet: Parameters<SetAllCookies>[0]) {
        cookiesToSet.forEach(({ name, value }) => {
          request.cookies.set(name, value)
        })
        response = NextResponse.next({ request })
        cookiesToSet.forEach(({ name, value, options }) => {
          response.cookies.set(name, value, options)
        })
      },
    },
  })

  let session = null
  try {
    const { data } = await supabase.auth.getSession()
    session = data.session
  } catch {
    session = null
  }

  if (!session) {
    const loginUrl = request.nextUrl.clone()
    loginUrl.pathname = '/login'
    loginUrl.search = ''
    loginUrl.searchParams.set('next', request.nextUrl.pathname)
    return NextResponse.redirect(loginUrl)
  }

  return response
}

export const config = {
  matcher: [
    '/analyses',
    '/analyses/:path*',
    '/methodology',
    '/methodology/:path*',
    '/data-quality',
      '/settings',
    '/data-quality/:path*',
    '/reports',
    '/reports/:path*',
  ],
}
