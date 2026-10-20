import { NextResponse, type NextRequest } from 'next/server'

/**
 * The API proxy.
 *
 * Every call the browser makes to `/api/...` is forwarded here to the
 * backend.  The backend origin therefore never reaches the browser, no
 * CORS negotiation is needed in production, and the proxy cannot collide
 * with a route in the application itself.
 *
 * The proxy owns the failure behaviour as well as the success behaviour:
 * when the backend cannot be reached the request fails with a `502` and
 * a message that names the origin, rather than the opaque "Internal
 * Server Error" a bare rewrite produces.  A backend that answers slowly
 * produces a `504`.
 */

const API_BASE = (
  process.env.API_BASE_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  'http://127.0.0.1:8000'
).replace(/\/+$/, '')

const TIMEOUT_MS = Number(process.env.API_PROXY_TIMEOUT_MS ?? 30_000)

/** The request is never cached: the API is the source of truth. */
export const dynamic = 'force-dynamic'

type RouteContext = { params: Promise<{ path: string[] }> }

function upstreamError(status: number, detail: string) {
  return NextResponse.json({ detail }, { status })
}

async function proxy(request: NextRequest, context: RouteContext) {
  const { path } = await context.params

  const target = `${API_BASE}/${path.map((segment) => encodeURIComponent(segment)).join('/')}${request.nextUrl.search}`

  const headers = new Headers()

  // The bearer token is what the API verifies, so it is forwarded
  // unchanged.  Nothing else from the browser is forwarded: the browser
  // must not be able to set headers the backend would trust.
  const authorization = request.headers.get('authorization')
  if (authorization) headers.set('authorization', authorization)

  const contentType = request.headers.get('content-type')
  if (contentType) headers.set('content-type', contentType)

  headers.set('accept', request.headers.get('accept') ?? 'application/json')

  const method = request.method
  let body: ArrayBuffer | undefined
  if (method !== 'GET' && method !== 'HEAD') {
    body = await request.arrayBuffer()
  }

  const controller = new AbortController()
  const timer = setTimeout(() => controller.abort(), TIMEOUT_MS)

  let upstream: Response
  try {
    upstream = await fetch(target, {
      method,
      headers,
      body,
      signal: controller.signal,
      cache: 'no-store',
      redirect: 'manual',
    })
  } catch (error) {
    clearTimeout(timer)
    const aborted = error instanceof Error && error.name === 'AbortError'
    if (aborted) {
      return upstreamError(
        504,
        `The API did not respond within ${TIMEOUT_MS} ms. The site selection service is slow or overloaded.`,
      )
    }
    return upstreamError(
      502,
      `The site selection API could not be reached at ${API_BASE}. Check that the backend service is running and that API_BASE_URL is correct.`,
    )
  }
  clearTimeout(timer)

  const payload = await upstream.arrayBuffer()

  const responseHeaders = new Headers()
  const upstreamType = upstream.headers.get('content-type')
  if (upstreamType) responseHeaders.set('content-type', upstreamType)

  // The report exports are downloaded as files, so their disposition
  // header has to survive the proxy.
  const disposition = upstream.headers.get('content-disposition')
  if (disposition) responseHeaders.set('content-disposition', disposition)

  return new NextResponse(payload, {
    status: upstream.status,
    statusText: upstream.statusText,
    headers: responseHeaders,
  })
}

export const GET = proxy
export const POST = proxy
export const PUT = proxy
export const PATCH = proxy
export const DELETE = proxy
export const HEAD = proxy
export const OPTIONS = proxy
