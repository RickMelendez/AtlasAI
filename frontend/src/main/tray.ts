/**
 * System Tray Module - Atlas AI
 *
 * Maneja el icono en el system tray (barra de tareas) y su menú contextual.
 * El icono siempre está visible y permite:
 * - Mostrar/ocultar el orb
 * - Abrir settings (placeholder)
 * - Cerrar la aplicación
 */

import { Tray, Menu, nativeImage, BrowserWindow } from 'electron'
import { join } from 'path'
import { existsSync } from 'fs'
import { showOrbWindow, quitApp, sendToRenderer } from './index'

let tray: Tray | null = null

/**
 * Crea el icono del system tray y su menú contextual
 */
export function createTrayIcon(): Tray {
  console.log('[Tray] Creating system tray icon...')

  try {
    // Rutas de íconos
    const base = join(__dirname, '../../public/assets/icons')
    const icoPath = join(base, 'orb-icon.ico')
    const pngPath = join(base, 'orb-icon.png')

    // Elegir el mejor ícono según plataforma/archivos disponibles
    let iconPath = pngPath
    if (process.platform === 'win32' && existsSync(icoPath)) {
      iconPath = icoPath
    } else if (existsSync(pngPath)) {
      iconPath = pngPath
    }

    console.log('[Tray] Loading icon from:', iconPath)

    // Crear imagen nativa del icono
    let icon = nativeImage.createFromPath(iconPath)

    // Verificar que el icono existe
    if (icon.isEmpty()) {
      throw new Error(`Icon not found at path: ${iconPath}`)
    }

    // Redimensionar icono para system tray (16x16 en la mayoría de sistemas)
    // Windows taskbar tray prefers small sizes to stay crisp
    icon = icon.resize({ width: 16, height: 16 })

    // Crear el tray
    tray = new Tray(icon)

    // Configurar tooltip (texto que aparece al hover)
    tray.setToolTip('Atlas AI Visual Companion')

    // Crear menú contextual
    const contextMenu = Menu.buildFromTemplate([
      {
        label: 'Show Atlas',
        type: 'normal',
        click: () => {
          console.log('[Tray] "Show Atlas" clicked')
          showOrbWindow()
        },
      },
      {
        label: 'Open Chat',
        type: 'normal',
        click: () => {
          console.log('[Tray] "Open Chat" clicked')
          showOrbWindow()
          sendToRenderer('ipc-open-chat')
        },
      },
      {
        type: 'separator',
      },
      {
        label: 'Open DevTools',
        type: 'normal',
        click: () => {
          const win = BrowserWindow.getAllWindows()[0]
          if (win) win.webContents.openDevTools({ mode: 'detach' })
        },
      },
      {
        type: 'separator',
      },
      {
        label: 'Quit Atlas AI',
        type: 'normal',
        click: () => {
          console.log('[Tray] "Quit" clicked')
          quitApp()
        },
      },
    ])

    // Asignar el menú contextual al tray
    tray.setContextMenu(contextMenu)

    // Event listeners del tray
    tray.on('click', () => {
      console.log('[Tray] Tray icon clicked')
      // Left click always brings the orb to the front
      showOrbWindow()
    })

    tray.on('right-click', () => {
      console.log('[Tray] Tray icon right-clicked')
      // El menú contextual se muestra automáticamente
    })

    tray.on('double-click', () => {
      console.log('[Tray] Tray icon double-clicked')
      showOrbWindow()
    })

    console.log('[Tray] System tray icon created successfully')

    return tray
  } catch (error) {
    // Don't crash the app if tray icon fails — just log and continue without tray
    console.error('[Tray] Error creating system tray icon (app will still run):', error)
    console.warn('[Tray] Running without system tray icon. Make sure orb-icon.ico exists in public/assets/icons/')
    // Return a dummy Tray to satisfy the return type — caller checks for null/undefined itself
    return null as unknown as Tray
  }
}

/**
 * Destruye el tray icon
 */
export function destroyTray(): void {
  if (tray) {
    console.log('[Tray] Destroying system tray icon')
    tray.destroy()
    tray = null
  }
}

/**
 * Actualiza el tooltip del tray
 */
export function updateTrayTooltip(text: string): void {
  if (tray) {
    tray.setToolTip(text)
  }
}

/**
 * Actualiza el icono del tray (para reflejar diferentes estados)
 */
export function updateTrayIcon(iconName: string): void {
  if (!tray) return

  try {
    const iconPath = join(
      __dirname,
      `../../public/assets/icons/${iconName}.png`
    )
    let icon = nativeImage.createFromPath(iconPath)

    if (!icon.isEmpty()) {
      icon = icon.resize({ width: 16, height: 16 })
      tray.setImage(icon)
      console.log('[Tray] Icon updated to:', iconName)
    }
  } catch (error) {
    console.error('[Tray] Error updating icon:', error)
  }
}

