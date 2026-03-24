/**
 * Preload Script - Atlas AI
 *
 * Este script actúa como un puente seguro entre el main process (Electron)
 * y el renderer process (React). Expone APIs específicas de manera controlada.
 *
 * IMPORTANTE: Este script corre en un contexto con acceso a Node.js pero
 * también puede comunicarse con el renderer. Usa contextBridge para exponer
 * APIs de forma segura.
 */

import { contextBridge, ipcRenderer } from 'electron'

/**
 * APIs expuestas al renderer process de forma segura
 */
const electronAPI = {
  /**
   * Muestra u oculta la ventana del orb
   */
  toggleOrbWindow: () => ipcRenderer.invoke('toggle-orb-window'),

  /**
   * Muestra la ventana del orb
   */
  showOrbWindow: () => ipcRenderer.invoke('show-orb-window'),

  /**
   * Oculta la ventana del orb
   */
  hideOrbWindow: () => ipcRenderer.invoke('hide-orb-window'),

  /**
   * Cierra la aplicación
   */
  quitApp: () => ipcRenderer.invoke('quit-app'),

  /**
   * Mueve la ventana a una posición específica
   */
  setWindowPosition: (x: number, y: number) => ipcRenderer.invoke('set-window-position', x, y),

  /**
   * Obtiene la posición actual de la ventana
   */
  getWindowPosition: () => ipcRenderer.invoke('get-window-position'),

  /**
   * Redimensiona la ventana
   */
  resizeWindow: (width: number, height: number) => ipcRenderer.invoke('resize-window', width, height),

  /**
   * Configura si la ventana siempre está en top
   */
  setAlwaysOnTop: (flag: boolean) => ipcRenderer.invoke('set-always-on-top', flag),

  /**
   * Obtiene información del sistema
   */
  getSystemInfo: () => ({
    platform: process.platform,
    arch: process.arch,
    version: process.version,
  }),

  // ── Screen Capture APIs ────────────────────────────────────────────────────

  /**
   * Inicia la captura continua de pantalla (cada 3s).
   * Los frames se emiten via el evento 'screen-capture-frame'.
   */
  startScreenCapture: () => ipcRenderer.invoke('start-screen-capture'),

  /**
   * Detiene la captura continua de pantalla.
   */
  stopScreenCapture: () => ipcRenderer.invoke('stop-screen-capture'),

  /**
   * Captura un único frame bajo demanda.
   */
  captureScreenOnce: () => ipcRenderer.invoke('capture-screen-once'),

  /**
   * Verifica si la captura de pantalla está activa.
   */
  isScreenCaptureActive: () => ipcRenderer.invoke('is-screen-capture-active'),

  /**
   * Suscribe un callback al evento de nuevo frame de captura.
   * El callback recibe: { data: string, timestamp: number, format: string }
   *
   * @returns Función de cleanup para desuscribirse
   */
  onScreenCaptureFrame: (callback: (frame: { data: string; timestamp: number; format: string }) => void) => {
    const handler = (_event: Electron.IpcRendererEvent, frame: { data: string; timestamp: number; format: string }) => {
      callback(frame)
    }
    ipcRenderer.on('screen-capture-frame', handler)
    // Retorna cleanup function
    return () => ipcRenderer.removeListener('screen-capture-frame', handler)
  },

  /**
   * Suscribe un callback al evento de "Open Chat" enviado desde el tray.
   * @returns Función de cleanup para desuscribirse
   */
  onOpenChat: (callback: () => void) => {
    const handler = () => callback()
    ipcRenderer.on('ipc-open-chat', handler)
    return () => ipcRenderer.removeListener('ipc-open-chat', handler)
  },
}

/**
 * Expone las APIs al renderer process bajo window.electronAPI
 */
contextBridge.exposeInMainWorld('electronAPI', electronAPI)

/**
 * Log de inicialización
 */
console.log('[Preload] Preload script loaded')
console.log('[Preload] Platform:', process.platform)
console.log('[Preload] Node version:', process.version)

// TypeScript types para el renderer process
export type ElectronAPI = typeof electronAPI

// Declarar tipos globales para que TypeScript los reconozca en el renderer
declare global {
  interface Window {
    electronAPI: ElectronAPI & {
      // Screen capture (tipado explícito para mejor DX en el renderer)
      startScreenCapture: () => Promise<{ success: boolean; error?: string }>
      stopScreenCapture: () => Promise<{ success: boolean; error?: string }>
      captureScreenOnce: () => Promise<{ success: boolean; data?: string; timestamp?: number } | null>
      isScreenCaptureActive: () => Promise<{ active: boolean }>
      onScreenCaptureFrame: (
        callback: (frame: { data: string; timestamp: number; format: string }) => void
      ) => () => void
    onOpenChat: (callback: () => void) => () => void
    }
  }
}
