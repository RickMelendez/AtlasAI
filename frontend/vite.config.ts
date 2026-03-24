import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import electron from 'vite-plugin-electron'
import renderer from 'vite-plugin-electron-renderer'
import { resolve } from 'path'

// Timestamp of the last preload build. Replaces the old boolean preloadBuiltOnce flag.
// Problem: chokidar (Rollup's file watcher) emits spurious filesystem events on Windows
// ~1-2 s after the initial scan, triggering a second preload build. With the old boolean,
// the first build set it to true (skipping reload correctly), but the spurious second
// build then called options.reload() — reloading the renderer page and killing the
// WebSocket connection.
// Fix: skip any reload() call within 10 s of the first preload build. Legitimate preload
// hot-reloads (triggered by editing a preload file during development) always arrive
// well after that window.
let lastPreloadBuildTime = 0

// Timestamp of the last time Electron was spawned via startup().
// On Windows, chokidar (Rollup's file watcher) emits spurious filesystem events
// immediately after the initial file scan completes, causing the main-entry
// closeBundle hook to fire a second time ~1-2 s after the first launch.
// That second fire calls startup() again, which kills and re-spawns Electron —
// this is what DevTools reports as "page reloaded" and what causes WebSocket
// disconnect on the backend side.
// The guard below skips any startup() call that arrives within 10 s of the
// previous one.  Legitimate main-process hot-restarts (triggered by saving a
// source file while developing) always arrive well after that window.
let lastElectronStartTime = 0

// Minimum gap between two builds of the same entry to be considered legitimate.
const SPURIOUS_BUILD_GUARD_MS = 10_000

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [
    // ── Startup reload guard ───────────────────────────────────────────────────
    // vite-plugin-electron (and chokidar on Windows) can send a Vite HMR
    // "full-reload" to the renderer within the first few seconds of startup.
    // When the renderer receives this message, it calls window.location.reload(),
    // which closes the backend WebSocket and kills all audio/screen loops.
    // Fix: patch server.ws.send to suppress full-reload messages during the
    // first STARTUP_RELOAD_GUARD_MS milliseconds of the dev server lifetime.
    // Legitimate hot-reloads triggered by editing a source file always arrive
    // well after startup, so the guard window doesn't interfere with DX.
    {
      name: 'atlas-startup-reload-guard',
      configureServer(server) {
        const startTime = Date.now()
        const GUARD_MS = 15_000

        const block = (label: string, origSend: (...a: unknown[]) => void) =>
          (...args: unknown[]) => {
            const payload = args[0] as { type?: string } | undefined
            if (payload?.type === 'full-reload' && Date.now() - startTime < GUARD_MS) {
              console.log(`[atlas] 🛡️  Blocked spurious full-reload (${label}) at ${Date.now() - startTime}ms`)
              return
            }
            origSend(...args)
          }

        // Patch server.hot.send — used by vite-plugin-electron's options.reload() in Vite 5
        if (server.hot?.send) {
          const orig = (server.hot.send as (...a: unknown[]) => void).bind(server.hot)
          ;(server.hot as { send: (...a: unknown[]) => void }).send = block('hot', orig)
        }

        // Patch server.ws.send — used in Vite 4 and as belt-and-suspenders in Vite 5
        if (server.ws?.send) {
          const orig = (server.ws.send as (...a: unknown[]) => void).bind(server.ws)
          ;(server.ws as { send: (...a: unknown[]) => void }).send = block('ws', orig)
        }
      },
    },
    react(),
    electron([
      {
        // Main process entry point
        entry: 'src/main/index.ts',
        onstart(options) {
          const now = Date.now()
          if (lastElectronStartTime > 0 && now - lastElectronStartTime < SPURIOUS_BUILD_GUARD_MS) {
            // Spurious chokidar re-fire: the watcher emits a second build event
            // ~1-2 s after startup on Windows.  Ignore it so Electron is not
            // killed and restarted immediately after launching.
            console.log('[vite-plugin-electron] Skipping duplicate startup() call (within 10 s guard)')
            return
          }
          lastElectronStartTime = now
          // Unset ELECTRON_RUN_AS_NODE so Electron doesn't run in Node.js-only mode
          // (inherited from VS Code's Electron environment when running in the IDE)
          const env = { ...process.env }
          delete env.ELECTRON_RUN_AS_NODE
          options.startup(['.', '--no-sandbox'], { env })
        },
        vite: {
          build: {
            outDir: 'dist-electron/main',
            rollupOptions: {
              external: ['electron']
            }
          }
        }
      },
      {
        // Preload scripts
        entry: 'src/preload/index.ts',
        onstart(options) {
          const now = Date.now()
          const prev = lastPreloadBuildTime
          lastPreloadBuildTime = now

          if (prev === 0) {
            // First build: Electron hasn't started yet — reload not needed.
            return
          }
          if (now - prev < SPURIOUS_BUILD_GUARD_MS) {
            // Spurious chokidar re-fire within 10 s of the previous build: skip.
            console.log('[vite-plugin-electron] Skipping duplicate preload reload() (within 10 s guard)')
            return
          }
          // Legitimate hot-reload (preload file edited during development).
          options.reload()
        },
        vite: {
          build: {
            outDir: 'dist-electron/preload',
            rollupOptions: {
              external: ['electron']
            }
          }
        }
      }
    ]),
    renderer()
  ],
  resolve: {
    alias: {
      '@': resolve(__dirname, 'src'),
      '@main': resolve(__dirname, 'src/main'),
      '@renderer': resolve(__dirname, 'src/renderer'),
      '@preload': resolve(__dirname, 'src/preload')
    }
  },
  server: {
    port: 5173,
    hmr: {
      // Explicitly pin the HMR WebSocket to port 5173.
      // Without this, the Vite client derives the HMR host/port from
      // import.meta.url, which can resolve inconsistently inside Electron's
      // renderer when base = './' (set by vite-plugin-electron-renderer).
      // Pinning port ensures the ws:// URL is always ws://localhost:5173/.
      port: 5173,
    },
    watch: {
      // Prevent Vite's HMR file watcher from picking up the electron build
      // outputs (dist-electron/). Without this, Vite detects the preload
      // output file being written ~1-2 s after startup and sends a
      // full-reload to the renderer — disconnecting the backend WebSocket.
      // Use both glob AND absolute path forms for reliable Windows matching.
      ignored: [
        '**/dist-electron/**',
        '**/node_modules/**',
        resolve(__dirname, 'dist-electron'),
      ],
    },
  }
})
