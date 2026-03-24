/**
 * useScreenCapture Hook - Hook de React para captura de pantalla
 *
 * Maneja la captura continua de pantalla via Electron IPC,
 * y envía los frames al backend a través del WebSocket.
 *
 * @example
 * // En un componente que se monta cuando el asistente está ACTIVE:
 * function AssistantActive() {
 *   const { isCapturing, lastCaptureTime, error } = useScreenCapture({
 *     autoStart: true,  // Empieza a capturar automáticamente
 *     sendViaWebSocket: true,  // Envía cada frame al backend
 *   })
 *   return <div>Capturing: {isCapturing ? 'Yes' : 'No'}</div>
 * }
 */

import { useEffect, useState, useCallback, useRef } from 'react'
import { wsService } from '../services/websocket'

export interface ScreenCaptureFrame {
  data: string       // Base64 encoded JPEG
  timestamp: number  // Unix ms
  format: string     // 'jpeg'
}

export interface UseScreenCaptureOptions {
  /** Callback cuando se recibe un nuevo frame. Recibe base64 de la imagen. */
  onFrame?: (frame: ScreenCaptureFrame) => void

  /** Auto-iniciar cuando el hook se monta. Default: false */
  autoStart?: boolean

  /**
   * Si true, cada frame se envía al backend via WebSocket automáticamente.
   * Default: true
   */
  sendViaWebSocket?: boolean
}

export interface UseScreenCaptureReturn {
  /** Inicia la captura continua */
  startCapture: () => Promise<boolean>

  /** Detiene la captura */
  stopCapture: () => Promise<boolean>

  /** Captura un único frame bajo demanda y lo retorna como base64 */
  captureOnce: () => Promise<string | null>

  /** true si la captura está activa */
  isCapturing: boolean

  /** Timestamp del último frame capturado (ms) */
  lastCaptureTime: number | null

  /** Último frame capturado */
  lastFrame: ScreenCaptureFrame | null

  /** Error si ocurrió alguno */
  error: Error | null
}

/**
 * Hook para controlar la captura de pantalla desde React.
 *
 * Flujo de datos:
 *   Electron main process (desktopCapturer)
 *     → IPC 'screen-capture-frame' event
 *       → preload onScreenCaptureFrame listener
 *         → este hook (onFrame callback + WebSocket)
 */
export function useScreenCapture(
  options: UseScreenCaptureOptions = {}
): UseScreenCaptureReturn {
  const { onFrame, autoStart = false, sendViaWebSocket = true } = options

  const [isCapturing, setIsCapturing] = useState(false)
  const [lastCaptureTime, setLastCaptureTime] = useState<number | null>(null)
  const [lastFrame, setLastFrame] = useState<ScreenCaptureFrame | null>(null)
  const [error, setError] = useState<Error | null>(null)

  // Ref para la función de cleanup del listener IPC
  const ipcCleanupRef = useRef<(() => void) | null>(null)

  /**
   * Procesa un nuevo frame recibido del main process.
   */
  const handleFrame = useCallback(
    (frame: ScreenCaptureFrame) => {
      setLastFrame(frame)
      setLastCaptureTime(frame.timestamp)
      setError(null)

      // Enviar al backend via WebSocket si está habilitado
      if (sendViaWebSocket && wsService.isConnected()) {
        wsService.send('screen_capture', {
          screenshot_data: frame.data,
          timestamp: frame.timestamp,
          format: frame.format,
        })
      }

      // Llamar al callback externo si se proveyó
      if (onFrame) {
        try {
          onFrame(frame)
        } catch (err) {
          console.error('[useScreenCapture] Error in onFrame callback:', err)
          setError(err as Error)
        }
      }
    },
    [onFrame, sendViaWebSocket]
  )

  /**
   * Inicia la captura continua de pantalla.
   */
  const startCapture = useCallback(async (): Promise<boolean> => {
    if (!window.electronAPI) {
      console.warn('[useScreenCapture] Electron API not available (web mode?)')
      return false
    }

    try {
      const result = await window.electronAPI.startScreenCapture()

      if (result?.success) {
        setIsCapturing(true)
        setError(null)
        console.log('[useScreenCapture] Capture started')
        return true
      } else {
        const errMsg = result?.error ?? 'Failed to start screen capture'
        console.error('[useScreenCapture]', errMsg)
        // If already capturing, that's okay — treat as success
        if (errMsg === 'Already capturing') {
          setIsCapturing(true)
          return true
        }
        setError(new Error(errMsg))
        return false
      }
    } catch (err) {
      const e = err as Error
      console.error('[useScreenCapture] startCapture error:', e)
      setError(e)
      return false
    }
  }, [])

  /**
   * Detiene la captura continua.
   */
  const stopCapture = useCallback(async (): Promise<boolean> => {
    if (!window.electronAPI) return false

    try {
      const result = await window.electronAPI.stopScreenCapture()

      if (result?.success) {
        setIsCapturing(false)
        console.log('[useScreenCapture] Capture stopped')
        return true
      }

      return false
    } catch (err) {
      console.error('[useScreenCapture] stopCapture error:', err)
      setError(err as Error)
      return false
    }
  }, [])

  /**
   * Captura un único frame bajo demanda.
   */
  const captureOnce = useCallback(async (): Promise<string | null> => {
    if (!window.electronAPI) return null

    try {
      const result = await window.electronAPI.captureScreenOnce()

      if (result?.success && result.data) {
        const frame: ScreenCaptureFrame = {
          data: result.data,
          timestamp: result.timestamp,
          format: 'jpeg',
        }
        handleFrame(frame)
        return result.data
      }

      return null
    } catch (err) {
      console.error('[useScreenCapture] captureOnce error:', err)
      setError(err as Error)
      return null
    }
  }, [handleFrame])

  // Registrar listener IPC para frames entrantes del main process
  useEffect(() => {
    if (!window.electronAPI?.onScreenCaptureFrame) {
      console.warn('[useScreenCapture] onScreenCaptureFrame IPC not available')
      return
    }

    // Suscribirse a frames del main process
    const cleanup = window.electronAPI.onScreenCaptureFrame(handleFrame)
    ipcCleanupRef.current = cleanup

    return () => {
      if (ipcCleanupRef.current) {
        ipcCleanupRef.current()
        ipcCleanupRef.current = null
      }
    }
  }, [handleFrame])

  // Auto-start si está habilitado
  useEffect(() => {
    if (autoStart) {
      startCapture()
    }

    return () => {
      // Cleanup: detener captura cuando el componente se desmonta
      if (autoStart) {
        stopCapture()
      }
    }
  }, [autoStart]) // eslint-disable-line react-hooks/exhaustive-deps — only on mount

  return {
    startCapture,
    stopCapture,
    captureOnce,
    isCapturing,
    lastCaptureTime,
    lastFrame,
    error,
  }
}
