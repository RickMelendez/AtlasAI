/**
 * useTTSPlayer Hook — Reproducción de audio TTS de Atlas AI
 *
 * Escucha el evento "tts_audio" del WebSocket (que llega después de que
 * ElevenLabs sintetiza la respuesta de Atlas) y lo reproduce en el navegador.
 *
 * Características:
 * - Decodifica el audio base64 MP3 recibido del backend
 * - Crea un Blob URL temporal y lo reproduce con la Web Audio API
 * - Cola de reproducción: si llegan varios audios, se reproducen en orden
 * - Estado de reproducción en tiempo real (para animar el orb)
 * - Cleanup automático de recursos al desmontar
 *
 * @example
 * function AssistantOrb() {
 *   const { isPlaying, currentText, volume } = useTTSPlayer({
 *     onPlayStart: (text) => setOrbMode('speaking'),
 *     onPlayEnd: () => setOrbMode('active'),
 *   })
 *   return <OrbComponent isSpeaking={isPlaying} />
 * }
 */

import { useEffect, useState, useCallback, useRef } from 'react'
import { wsService } from '../services/websocket'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface TTSAudioPayload {
  audio_b64?: string   // MP3 codificado en base64 — undefined when ElevenLabs not configured
  format: string       // "mp3"
  text?: string        // Texto original (para mostrar en UI y fallback speechSynthesis)
}

export interface TTSQueueItem {
  audio_b64: string
  text?: string
  id: string
}

export interface UseTTSPlayerOptions {
  /** Volumen de reproducción (0-1). Default: 1.0 */
  volume?: number
  /** Callback cuando empieza a reproducir un audio. */
  onPlayStart?: (text?: string) => void
  /** Callback cuando termina de reproducir. */
  onPlayEnd?: () => void
  /** Callback si ocurre un error de reproducción. */
  onError?: (error: Error) => void
}

export interface UseTTSPlayerReturn {
  /** Si Atlas está hablando actualmente */
  isPlaying: boolean
  /** Texto del audio que se está reproduciendo */
  currentText: string | null
  /** Número de audios en la cola esperando reproducirse */
  queueSize: number
  /** Volumen actual (0-1) */
  volume: number
  /** Detener la reproducción actual e limpiar la cola */
  stopPlayback: () => void
  /** Controla el volumen (0-1) */
  setVolume: (vol: number) => void
  /** Reproduce un audio manualmente (base64 MP3) */
  playAudio: (audio_b64: string, text?: string) => void
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useTTSPlayer(
  options: UseTTSPlayerOptions = {}
): UseTTSPlayerReturn {
  const { volume: initialVolume = 1.0, onPlayStart, onPlayEnd, onError } = options

  const [isPlaying, setIsPlaying] = useState(false)
  const [currentText, setCurrentText] = useState<string | null>(null)
  const [queueSize, setQueueSize] = useState(0)
  const [volume, setVolumeState] = useState(initialVolume)

  const audioRef = useRef<HTMLAudioElement | null>(null)
  const queueRef = useRef<TTSQueueItem[]>([])
  const isPlayingRef = useRef(false)
  const volumeRef = useRef(initialVolume)
  const blobUrlRef = useRef<string | null>(null)

  // ── Cleanup de Blob URL anterior ─────────────────────────────────────────

  const cleanupBlobUrl = useCallback(() => {
    if (blobUrlRef.current) {
      URL.revokeObjectURL(blobUrlRef.current)
      blobUrlRef.current = null
    }
  }, [])

  // ── Procesar cola de reproducción ─────────────────────────────────────────

  const processQueue = useCallback(async () => {
    if (isPlayingRef.current || queueRef.current.length === 0) return

    const item = queueRef.current.shift()!
    setQueueSize(queueRef.current.length)

    isPlayingRef.current = true
    setIsPlaying(true)
    setCurrentText(item.text ?? null)

    try {
      // Decodificar base64 → Uint8Array → Blob → Blob URL
      const binaryStr = atob(item.audio_b64)
      const bytes = new Uint8Array(binaryStr.length)
      for (let i = 0; i < binaryStr.length; i++) {
        bytes[i] = binaryStr.charCodeAt(i)
      }

      const blob = new Blob([bytes], { type: 'audio/mpeg' })
      cleanupBlobUrl()
      const url = URL.createObjectURL(blob)
      blobUrlRef.current = url

      // Crear elemento de audio y reproducir
      const audio = new Audio(url)
      audio.volume = volumeRef.current
      audioRef.current = audio

      onPlayStart?.(item.text)

      await new Promise<void>((resolve, reject) => {
        audio.onended = () => resolve()
        audio.onerror = (e) => reject(new Error(`Audio playback error: ${e}`))
        audio.play().catch(reject)
      })

    } catch (err) {
      const e = err as Error
      console.error('[TTSPlayer] Playback error:', e)
      onError?.(e)
    } finally {
      cleanupBlobUrl()
      audioRef.current = null
      isPlayingRef.current = false
      setIsPlaying(false)
      setCurrentText(null)

      onPlayEnd?.()

      // Continuar con la cola si hay más items
      if (queueRef.current.length > 0) {
        // Small delay between utterances for natural pacing
        setTimeout(() => processQueue(), 200)
      }
    }
  }, [onPlayStart, onPlayEnd, onError, cleanupBlobUrl])

  // ── playAudio: agregar a la cola ──────────────────────────────────────────

  const playAudio = useCallback(
    (audio_b64: string, text?: string) => {
      const item: TTSQueueItem = {
        audio_b64,
        text,
        id: `${Date.now()}-${Math.random()}`,
      }

      queueRef.current.push(item)
      setQueueSize(queueRef.current.length)

      console.log(
        `[TTSPlayer] 🔊 Queued audio: "${text?.slice(0, 40) ?? '(no text)'}..."`
      )

      // Si no hay nada reproduciendo, iniciar
      if (!isPlayingRef.current) {
        processQueue()
      }
    },
    [processQueue]
  )

  // ── stopPlayback ──────────────────────────────────────────────────────────

  const stopPlayback = useCallback(() => {
    // Limpiar cola
    queueRef.current = []
    setQueueSize(0)

    // Parar audio actual
    if (audioRef.current) {
      audioRef.current.pause()
      audioRef.current.src = ''
      audioRef.current = null
    }

    cleanupBlobUrl()
    isPlayingRef.current = false
    setIsPlaying(false)
    setCurrentText(null)

    console.log('[TTSPlayer] Playback stopped')
  }, [cleanupBlobUrl])

  // ── setVolume ─────────────────────────────────────────────────────────────

  const setVolume = useCallback((vol: number) => {
    const clamped = Math.max(0, Math.min(1, vol))
    volumeRef.current = clamped
    setVolumeState(clamped)

    if (audioRef.current) {
      audioRef.current.volume = clamped
    }
  }, [])

  // ── Suscribirse a eventos tts_audio del WebSocket ─────────────────────────

  useEffect(() => {
    const handleTTSAudio = (data: TTSAudioPayload) => {
      if (!data.audio_b64) {
        // ElevenLabs not configured — fall back to browser speechSynthesis
        if (data.text && window.speechSynthesis) {
          console.log('[TTSPlayer] 🔊 Using browser speechSynthesis fallback')
          window.speechSynthesis.cancel()   // clear any pending utterance
          const utt = new SpeechSynthesisUtterance(data.text)
          utt.rate   = 1.05
          utt.pitch  = 1.0
          utt.volume = volumeRef.current
          isPlayingRef.current = true
          setIsPlaying(true)
          setCurrentText(data.text)
          onPlayStart?.(data.text)
          utt.onend = () => {
            isPlayingRef.current = false
            setIsPlaying(false)
            setCurrentText(null)
            onPlayEnd?.()
          }
          window.speechSynthesis.speak(utt)
        } else {
          console.warn('[TTSPlayer] Received tts_audio with no audio data and no text fallback')
        }
        return
      }

      console.log(
        `[TTSPlayer] ← tts_audio received (${data.audio_b64.length} b64 chars)`
      )
      playAudio(data.audio_b64, data.text)
    }

    wsService.on('tts_audio', handleTTSAudio)

    return () => {
      wsService.off('tts_audio', handleTTSAudio)
    }
  }, [playAudio])

  // ── Cleanup al desmontar ──────────────────────────────────────────────────

  useEffect(() => {
    return () => {
      stopPlayback()
    }
  }, [stopPlayback])

  return {
    isPlaying,
    currentText,
    queueSize,
    volume,
    stopPlayback,
    setVolume,
    playAudio,
  }
}
