/**
 * Screen Capture Service - Atlas AI Frontend
 *
 * Maneja la captura de pantalla usando Electron desktopCapturer.
 * Captura cada 3 segundos cuando el asistente está ACTIVE.
 */

import { desktopCapturer } from 'electron'

export interface CaptureOptions {
  quality?: number // 0-100, default 80
  format?: 'png' | 'jpeg' // default png
}

/**
 * Captura la pantalla principal y retorna como base64.
 *
 * @param options Opciones de captura (quality, format)
 * @returns Promise con imagen en base64, o null si falla
 */
export async function captureScreen(
  options: CaptureOptions = {}
): Promise<string | null> {
  const { quality = 80, format = 'png' } = options

  try {
    // Obtener lista de pantallas disponibles
    const sources = await desktopCapturer.getSources({
      types: ['screen'],
      thumbnailSize: {
        width: 1920,
        height: 1080,
      },
    })

    if (sources.length === 0) {
      console.error('[Capture] No screens found')
      return null
    }

    // Usar la primera pantalla (pantalla principal)
    const primaryScreen = sources[0]

    // Obtener thumbnail (captura)
    const thumbnail = primaryScreen.thumbnail

    // Convertir a base64 según el formato
    let base64: string

    if (format === 'jpeg') {
      base64 = thumbnail.toJPEG(quality).toString('base64')
    } else {
      base64 = thumbnail.toPNG().toString('base64')
    }

    console.log(`[Capture] Screen captured: ${base64.length} bytes`)
    return base64

  } catch (error) {
    console.error('[Capture] Error capturing screen:', error)
    return null
  }
}

/**
 * Clase para manejar captura continua de pantalla.
 */
export class ScreenCaptureManager {
  private intervalId: NodeJS.Timeout | null = null
  private isCapturing: boolean = false
  private captureInterval: number = 3000 // 3 segundos

  constructor(captureInterval: number = 3000) {
    this.captureInterval = captureInterval
  }

  /**
   * Inicia la captura continua de pantalla.
   *
   * @param callback Función a llamar con cada captura (base64)
   */
  start(callback: (screenshot: string) => void): void {
    if (this.isCapturing) {
      console.warn('[Capture] Already capturing')
      return
    }

    console.log(`[Capture] Starting continuous capture (every ${this.captureInterval}ms)`)
    this.isCapturing = true

    // Captura inmediata
    this.captureAndCallback(callback)

    // Captura continua
    this.intervalId = setInterval(() => {
      this.captureAndCallback(callback)
    }, this.captureInterval)
  }

  /**
   * Detiene la captura continua.
   */
  stop(): void {
    if (!this.isCapturing) {
      return
    }

    console.log('[Capture] Stopping continuous capture')

    if (this.intervalId) {
      clearInterval(this.intervalId)
      this.intervalId = null
    }

    this.isCapturing = false
  }

  /**
   * Verifica si está capturando actualmente.
   */
  isActive(): boolean {
    return this.isCapturing
  }

  /**
   * Captura pantalla y llama al callback con el resultado.
   */
  private async captureAndCallback(callback: (screenshot: string) => void): Promise<void> {
    try {
      const screenshot = await captureScreen({ quality: 80, format: 'jpeg' })

      if (screenshot) {
        callback(screenshot)
      }
    } catch (error) {
      console.error('[Capture] Error in capture callback:', error)
    }
  }
}
