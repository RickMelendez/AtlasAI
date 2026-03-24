/**
 * React Entry Point - Atlas AI
 *
 * Initialises Sentry error monitoring before the React tree renders,
 * then wraps the app with a Sentry ErrorBoundary so any unhandled
 * React error is captured automatically.
 */

import React from 'react'
import ReactDOM from 'react-dom/client'
import * as Sentry from '@sentry/react'
import { initSentry } from './sentry'
import App from './App'
import './index.css'

// Must be the very first call
initSentry()

// ── Reload interception ───────────────────────────────────────────────────────
// Intercept location.reload() and beforeunload so we can log a stack trace
// BEFORE the page tears down. This identifies whether the reload is triggered
// by:
//   a) Vite HMR client's WebSocket close handler (stack: setupWebSocket → close)
//   b) Vite HMR client's full-reload message handler (stack: handleMessage → full-reload)
//   c) Something in the React app itself
// The stack trace appears in the [Renderer:*] logs forwarded to main stdout.
if (import.meta.env.DEV) {
  if (import.meta.hot) {
    import.meta.hot.on('vite:beforeFullReload', (payload: unknown) => {
      console.warn('[Atlas] 🚨 vite:beforeFullReload — full-reload reached client! payload:', JSON.stringify(payload))
    })
    import.meta.hot.on('vite:ws:disconnect', () => {
      console.warn('[Atlas] 🚨 vite:ws:disconnect — HMR WebSocket dropped!')
    })
  }

  window.addEventListener('beforeunload', () => {
    console.warn('[Atlas] 🚨 beforeunload fired — page is about to navigate/reload')
  })
}

console.log('[Renderer] React app starting...')
console.log('[Renderer] Environment:', import.meta.env.MODE)

if (window.electronAPI) {
  console.log('[Renderer] Electron API available')
  console.log('[Renderer] System info:', window.electronAPI.getSystemInfo())
} else {
  console.warn('[Renderer] Electron API not available (running in browser?)')
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    {/* Sentry ErrorBoundary: catches render-time crashes and reports them */}
    <Sentry.ErrorBoundary
      fallback={({ error, resetError }) => (
        <div style={{
          display: 'flex', flexDirection: 'column', alignItems: 'center',
          justifyContent: 'center', height: '100vh', color: 'white',
          background: 'rgba(10,10,20,0.95)', gap: 12, padding: 24,
          fontFamily: 'system-ui', textAlign: 'center',
        }}>
          <div style={{ fontSize: 32 }}>⚠️</div>
          <div style={{ fontSize: 15, fontWeight: 600 }}>Something went wrong</div>
          <div style={{ fontSize: 12, color: 'rgba(255,255,255,0.5)', maxWidth: 280 }}>
            {(error as Error)?.message ?? 'Unknown error'}
          </div>
          <button
            onClick={resetError}
            style={{
              marginTop: 8, padding: '8px 20px', borderRadius: 8,
              border: '1px solid rgba(255,255,255,0.2)',
              background: 'rgba(255,255,255,0.08)', color: 'white',
              cursor: 'pointer', fontSize: 13,
            }}
          >
            Retry
          </button>
        </div>
      )}
    >
      <App />
    </Sentry.ErrorBoundary>
  </React.StrictMode>
)

console.log('[Renderer] React app rendered')
