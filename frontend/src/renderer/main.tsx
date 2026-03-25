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

console.log('[Renderer] React app starting...')
console.log('[Renderer] Environment:', import.meta.env.MODE)

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
          <div style={{ fontSize: 32 }}>!</div>
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
