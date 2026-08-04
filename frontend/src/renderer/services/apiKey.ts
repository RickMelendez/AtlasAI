/**
 * Shared-secret key sent to the backend when ATLAS_API_KEY is configured
 * there (see backend/.env.example). Empty by default for local dev, where
 * the backend accepts unauthenticated requests.
 */
export const ATLAS_API_KEY = (import.meta.env.VITE_ATLAS_API_KEY as string | undefined) || ''

/** Adds the X-Atlas-Key header to a fetch init, if a key is configured. */
export function withApiKeyHeader(init: RequestInit = {}): RequestInit {
  if (!ATLAS_API_KEY) return init
  return {
    ...init,
    headers: {
      ...(init.headers || {}),
      'X-Atlas-Key': ATLAS_API_KEY,
    },
  }
}

/**
 * Appends the key as a `?key=` query param, if configured.
 * Browsers' native WebSocket API can't set custom headers, so the key
 * travels as a query param on the connect URL instead (matches the
 * backend's verify_websocket_key in auth.py).
 */
export function appendApiKeyParam(wsUrl: string): string {
  if (!ATLAS_API_KEY) return wsUrl
  const separator = wsUrl.includes('?') ? '&' : '?'
  return `${wsUrl}${separator}key=${encodeURIComponent(ATLAS_API_KEY)}`
}
