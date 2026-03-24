/**
 * Sentry — Error monitoring for Atlas AI (renderer process)
 *
 * Captures:
 *  • Unhandled JS exceptions & promise rejections
 *  • React component errors (via ErrorBoundary in main.tsx)
 *  • Manual captures: Sentry.captureException(err), Sentry.captureMessage(msg)
 *
 * Setup:
 *  1. Create a project at https://sentry.io
 *  2. Copy the DSN and add it to frontend/.env:
 *       VITE_SENTRY_DSN=https://xxxx@oXXXX.ingest.sentry.io/YYYY
 *  3. npm install  (adds @sentry/react)
 */

import * as Sentry from '@sentry/react'

const DSN = import.meta.env.VITE_SENTRY_DSN as string | undefined

export function initSentry() {
  if (!DSN) {
    console.warn('[Sentry] VITE_SENTRY_DSN not set — error monitoring disabled')
    return
  }

  Sentry.init({
    dsn: DSN,

    // Release tracking (injected by Vite at build time, falls back to 'dev')
    release: (import.meta.env.VITE_APP_VERSION as string | undefined) ?? 'dev',

    environment: import.meta.env.MODE,   // 'development' | 'production'

    // Only send errors in production by default;
    // set VITE_SENTRY_DEBUG=true in .env to enable in dev
    enabled: import.meta.env.PROD || import.meta.env.VITE_SENTRY_DEBUG === 'true',

    // Sample 100% of errors (reduce for high-traffic apps)
    sampleRate: 1.0,

    // Performance traces — 10% in production to save quota
    tracesSampleRate: import.meta.env.PROD ? 0.1 : 0,

    beforeSend(event: Sentry.ErrorEvent) {
      // Strip any accidentally captured API keys from breadcrumbs/extras
      if (event.request?.headers) {
        delete event.request.headers['Authorization']
        delete event.request.headers['x-api-key']
      }
      return event
    },
  })

  console.log(`[Sentry] Initialized — env: ${import.meta.env.MODE}`)
}

/** Convenience: attach user context once connected */
export function setSentryUser(sessionId: string) {
  Sentry.setUser({ id: sessionId })
}

/** Convenience: capture an error with optional extras */
export function captureError(err: unknown, context?: Record<string, unknown>) {
  if (context) Sentry.setContext('atlas', context)
  Sentry.captureException(err)
}

/** Convenience: log a message at a given level */
export function captureMessage(
  msg: string,
  level: 'debug' | 'info' | 'warning' | 'error' = 'info',
) {
  Sentry.captureMessage(msg, level)
}

export { Sentry }
