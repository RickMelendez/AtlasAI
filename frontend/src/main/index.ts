/**
 * Electron Main Process - Atlas AI
 *
 * Este es el proceso principal de Electron que maneja:
 * - Creación de la ventana del orb (transparente, frameless, always on top)
 * - System tray icon y menú
 * - Lifecycle de la aplicación
 * - IPC communication con el renderer process
 */

import { app, BrowserWindow, ipcMain, screen, session } from 'electron'
import { join } from 'path'
import { existsSync } from 'fs'
import { createTrayIcon, destroyTray } from './tray'
import { ScreenCaptureManager } from './capture'

// Singleton de captura de pantalla
const screenCapture = new ScreenCaptureManager(3000)

// Manejar entorno de desarrollo vs producción
const isDev = process.env.NODE_ENV === 'development'

// Variable global para la ventana del orb
let orbWindow: BrowserWindow | null = null

/**
 * Resolve best icon path for current platform.
 * - On Windows, prefer .ico for proper taskbar appearance
 * - Fallback to PNG during development
 */
function getIconPath(): string | undefined {
  const base = join(__dirname, '../../public/assets/icons')
  const ico = join(base, 'orb-icon.ico')
  const png = join(base, 'orb-icon.png')

  if (process.platform === 'win32') {
    if (existsSync(ico)) return ico
    if (existsSync(png)) return png
    return undefined
  }

  return existsSync(png) ? png : undefined
}

/**
 * Crea la ventana del orb (transparente, flotante, always on top)
 */
function createOrbWindow(): BrowserWindow {
  console.log('[Main] Creating orb window...')

  // Position the orb at the bottom-right corner of the primary display
  const { width: sw, height: sh } = screen.getPrimaryDisplay().workAreaSize
  const ORB_SIZE = 200
  const MARGIN   = 24
  const startX = sw - ORB_SIZE - MARGIN
  const startY = sh - ORB_SIZE - MARGIN

  const window = new BrowserWindow({
    width:  ORB_SIZE,
    height: ORB_SIZE,
    x: startX,
    y: startY,
    transparent: true, // Ventana transparente
    frame: false, // Sin frame/borde
    skipTaskbar: true, // No aparece en taskbar
    resizable: false, // No redimensionable
    maximizable: false,
    minimizable: false,
    show: false, // No mostrar hasta que esté lista
    icon: getIconPath(), // Taskbar icon (Win uses .ico if available)
    webPreferences: {
      preload: join(__dirname, '../preload/index.js'),
      nodeIntegration: false,
      contextIsolation: true,
    },
  })

  // Cargar el renderer process
  if (isDev) {
    // En desarrollo, cargar desde la URL real del dev server (evita puertos hardcodeados).
    const devServerUrl = process.env.VITE_DEV_SERVER_URL || 'http://localhost:5173'
    window.loadURL(devServerUrl)
    // NOTE: DevTools intentionally NOT auto-opened — it steals focus from the orb window.
    // Open manually via tray menu → "Open DevTools" if needed.
  } else {
    // En producción, cargar desde los archivos buildeados
    window.loadFile(join(__dirname, '../../dist/index.html'))
  }

  // Keep audio + WebSocket alive even when window is hidden (tray mode).
  // Without this, Chromium throttles/suspends the renderer after ~5s hidden,
  // killing the AudioContext and breaking wake word detection.
  window.once('ready-to-show', () => {
    window.webContents.setBackgroundThrottling(false)
    console.log('[Main] Orb window ready (hidden — waiting for wake word)')
    // Do NOT call window.show() here — Atlas starts in tray, appears on "Hey Atlas"
  })

  // Forward ALL renderer console output to main process stdout.
  // Without this we're debugging blind — renderer logs are only visible in DevTools.
  const LEVEL = ['V', 'I', 'W', 'E']
  window.webContents.on('console-message', (_e, level, message, line, source) => {
    const tag = LEVEL[level] ?? level
    const short = source?.split('/').pop() ?? source
    console.log(`[Renderer:${tag}] ${message}  (${short}:${line})`)
  })

  // Log renderer navigation / crash — helps diagnose spurious reloads
  window.webContents.on('did-start-navigation', (_event, url, _isInPlace, isMainFrame) => {
    if (isMainFrame) console.log('[Main] ⚠️  Renderer navigating:', url)
  })
  window.webContents.on('render-process-gone', (_event, details) => {
    console.log('[Main] ❌ Renderer crashed:', JSON.stringify(details))
    // Auto-recover: reload the renderer after a short pause
    setTimeout(() => {
      if (orbWindow && !orbWindow.isDestroyed()) {
        console.log('[Main] Reloading renderer after crash...')
        orbWindow.webContents.reload()
      }
    }, 1500)
  })

  // Logging de eventos
  window.on('closed', () => {
    console.log('[Main] Orb window closed')
    orbWindow = null
  })

  window.on('focus', () => {
    console.log('[Main] Orb window focused')
  })

  window.on('blur', () => {
    console.log('[Main] Orb window blurred')
  })

  return window
}

/**
 * Muestra u oculta la ventana del orb
 */
function toggleOrbWindow() {
  if (!orbWindow) {
    orbWindow = createOrbWindow()
    return
  }

  if (orbWindow.isVisible()) {
    console.log('[Main] Hiding orb window')
    orbWindow.hide()
  } else {
    console.log('[Main] Showing orb window')
    orbWindow.show()
  }
}

/**
 * Muestra la ventana del orb y la lleva al frente.
 * Siempre hace show() + focus() + setAlwaysOnTop para garantizar
 * que la ventana sea visible aunque ya estuviera "visible" pero oculta.
 */
export function showOrbWindow() {
  if (!orbWindow) {
    orbWindow = createOrbWindow()
    return
  }
  // If renderer crashed, reload it first
  if (orbWindow.webContents.isCrashed()) {
    console.log('[Main] Renderer is crashed — reloading before show')
    orbWindow.webContents.reload()
  }
  if (!orbWindow.isVisible()) {
    orbWindow.show()
  }
  orbWindow.moveTop()
  orbWindow.focus()
  console.log('[Main] Orb window brought to front')
}

/**
 * Oculta la ventana del orb
 */
export function hideOrbWindow() {
  if (orbWindow && orbWindow.isVisible()) {
    orbWindow.hide()
  }
}

/**
 * Envía un evento IPC al renderer (main → renderer push).
 * Usado por el tray para comandos UI que el renderer debe ejecutar.
 */
export function sendToRenderer(channel: string, data?: unknown): void {
  if (orbWindow && !orbWindow.isDestroyed()) {
    orbWindow.webContents.send(channel, data)
  }
}

/**
 * Cierra completamente la aplicación
 */
export function quitApp() {
  console.log('[Main] Quitting application...')
  app.quit()
}

// ============================================================================
// App Lifecycle Events
// ============================================================================

/**
 * Cuando Electron ha terminado de inicializar
 */
app.whenReady().then(() => {
  console.log('[Main] App is ready')

  // Auto-grant media permissions (microphone, camera, screen capture) so that
  // getUserMedia() in the renderer works immediately without a native OS dialog.
  // Without this, the Windows permission dialog appears ~800ms after startup
  // (when useAudioCapture fires), which can cause the renderer to navigate and
  // drop the backend WebSocket connection.
  session.defaultSession.setPermissionRequestHandler((_wc, permission, callback) => {
    const ALLOWED = ['media', 'display-capture', 'desktopCapture']
    callback(ALLOWED.includes(permission))
  })

  // Create the orb window immediately on startup — don't wait for tray click
  orbWindow = createOrbWindow()

  // Crear el system tray icon
  createTrayIcon()

  // En macOS, re-crear ventana cuando se clickea el dock icon
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      orbWindow = createOrbWindow()
    }
  })

  console.log('[Main] Initialization complete')
  console.log('[Main] Orb window created and always-on-top')
})

/**
 * Cuando todas las ventanas están cerradas
 */
app.on('window-all-closed', () => {
  // En macOS, las apps suelen seguir corriendo aunque no tengan ventanas
  // Pero en Atlas, queremos mantener el tray icon activo
  console.log('[Main] All windows closed')

  // NO cerrar la app automáticamente, mantener el tray icon activo
  // El usuario debe usar "Quit" del menú del tray para cerrar la app
})

/**
 * Antes de que la app se cierre
 */
app.on('before-quit', () => {
  console.log('[Main] App is about to quit')
  destroyTray()
})

// ============================================================================
// IPC Handlers (comunicación con el renderer process)
// ============================================================================

/**
 * Handler para toggle de la ventana del orb
 */
ipcMain.handle('toggle-orb-window', () => {
  toggleOrbWindow()
})

/**
 * Handler para mostrar la ventana del orb
 */
ipcMain.handle('show-orb-window', () => {
  showOrbWindow()
})

/**
 * Handler para ocultar la ventana del orb
 */
ipcMain.handle('hide-orb-window', () => {
  hideOrbWindow()
})

/**
 * Handler para cerrar la aplicación
 */
ipcMain.handle('quit-app', () => {
  quitApp()
})

/**
 * Handler para mover la ventana del orb
 */
ipcMain.handle('set-window-position', (_event, x: number, y: number) => {
  if (orbWindow) {
    orbWindow.setPosition(Math.round(x), Math.round(y))
  }
})

/**
 * Handler para obtener la posición actual de la ventana
 */
ipcMain.handle('get-window-position', () => {
  if (orbWindow) {
    return orbWindow.getPosition()
  }
  return [0, 0]
})

/**
 * Handler para redimensionar la ventana (expand/collapse).
 * The window always stays on top — we only change its size, never hide it.
 */
ipcMain.handle('resize-window', (_event, width: number, height: number) => {
  if (!orbWindow) return
  const [x, y] = orbWindow.getPosition()
  const [currentWidth, currentHeight] = orbWindow.getSize()

  // Expand from the center of the orb (top portion stays fixed)
  const newX = x - Math.floor((width - currentWidth) / 2)
  // Keep Y the same so orb stays in place and chat grows downward
  const newY = y - Math.floor((height - currentHeight) / 2)

  orbWindow.setSize(width, height, true)
  orbWindow.setPosition(newX, newY, true)
})

/**
 * Handler para configurar always on top.
 */
ipcMain.handle('set-always-on-top', (_event, flag: boolean) => {
  if (orbWindow) {
    orbWindow.setAlwaysOnTop(flag)
  }
})

// ============================================================================
// Screen Capture IPC Handlers
// ============================================================================

/**
 * Inicia la captura continua de pantalla.
 * El renderer (React) pasa un session_id para que el main process
 * pueda enviar las capturas via WebSocket a través del backend.
 */
ipcMain.handle('start-screen-capture', (_event) => {
  if (screenCapture.isActive()) {
    console.log('[Main] Screen capture already running')
    return { success: false, error: 'Already capturing' }
  }

  screenCapture.start((screenshot: string) => {
    // Enviar screenshot al renderer para que lo mande por WebSocket
    if (orbWindow && !orbWindow.isDestroyed()) {
      try {
        orbWindow.webContents.send('screen-capture-frame', {
          data: screenshot,
          timestamp: Date.now(),
          format: 'jpeg',
        })
      } catch {
        // Render frame disposed during HMR reload — skip this frame, next will succeed
      }
    }
  })

  console.log('[Main] Screen capture started')
  return { success: true }
})

/**
 * Detiene la captura continua de pantalla.
 */
ipcMain.handle('stop-screen-capture', (_event) => {
  screenCapture.stop()
  console.log('[Main] Screen capture stopped')
  return { success: true }
})

/**
 * Captura un único frame de pantalla y lo retorna.
 * Útil para capturas bajo demanda.
 */
ipcMain.handle('capture-screen-once', async (_event) => {
  const { captureScreen } = await import('./capture')
  const screenshot = await captureScreen({ quality: 80, format: 'jpeg' })
  if (screenshot) {
    return { success: true, data: screenshot, timestamp: Date.now() }
  }
  return { success: false, error: 'Capture failed' }
})

/**
 * Verifica si la captura está activa.
 */
ipcMain.handle('is-screen-capture-active', (_event) => {
  return { active: screenCapture.isActive() }
})

// ============================================================================
// Error Handling
// ============================================================================

process.on('uncaughtException', (error) => {
  console.error('[Main] Uncaught exception:', error)
})

process.on('unhandledRejection', (error) => {
  console.error('[Main] Unhandled rejection:', error)
})
