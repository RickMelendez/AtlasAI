/**
 * useAudioCapture Hook — Captura de micrófono para Atlas AI
 *
 * Maneja todo el ciclo de audio de voz:
 *
 *  FASE 1 — Wake word detection:
 *    Captura PCM raw (Int16, 16kHz, mono) en chunks pequeños y los envía
 *    al backend via WebSocket para que Porcupine detecte "Hey Atlas".
 *    También permite detección local mediante VAD (umbral de energía).
 *
 *  FASE 2 — Speech recording:
 *    Cuando se detecta la wake word (del backend o manual), graba el
 *    speech del usuario hasta detectar silencio, y envía el blob completo
 *    como `audio_command` para que Whisper lo transcriba.
 *
 * Flujo:
 *   getUserMedia → AudioContext (16kHz) → ScriptProcessor
 *     → [mode: WAKE_WORD] → chunks PCM base64 → WS "audio_chunk"
 *     → backend detecta wake word → WS "wake_word_detected"
 *     → [mode: RECORDING] → MediaRecorder graba WebM
 *     → silencio detectado → WS "audio_command" con blob base64
 *     → backend STT + AI + TTS → WS "tts_audio" → useTTSPlayer
 */

import { useEffect, useState, useCallback, useRef } from 'react'
import { wsService } from '../services/websocket'

// ── Types ─────────────────────────────────────────────────────────────────────

export type AudioCaptureMode = 'idle' | 'wake_word' | 'recording' | 'processing'

export interface UseAudioCaptureOptions {
  /** Auto-iniciar captura de micrófono al montar el hook. Default: false */
  autoStart?: boolean
  /**
   * Umbral de energía RMS para detectar silencio (0-1).
   * Por debajo de este valor se considera silencio. Default: 0.01
   */
  silenceThreshold?: number
  /**
   * Duración mínima de silencio para terminar la grabación (ms). Default: 1500
   */
  silenceDuration?: number
  /**
   * Duración máxima de una grabación (ms). Default: 15000
   */
  maxRecordingDuration?: number
  /** Callback cuando se detecta la wake word. */
  onWakeWordDetected?: (wakeWord: string) => void
  /** Callback cuando termina una grabación y se envía al backend. */
  onRecordingSent?: (audioBlobSize: number) => void
}

export interface UseAudioCaptureReturn {
  /** Inicia la captura de micrófono */
  startCapture: () => Promise<boolean>
  /** Detiene toda la captura */
  stopCapture: () => void
  /** Activa manualmente el modo de grabación (sin wake word) */
  startManualRecording: () => void
  /** Detiene manualmente la grabación activa */
  stopManualRecording: () => void
  /** Modo actual del audio capture */
  mode: AudioCaptureMode
  /** Si el micrófono está activo */
  isCapturing: boolean
  /** Nivel de audio actual (0-1, para VU meter en UI) */
  audioLevel: number
  /** Error si ocurrió alguno */
  error: Error | null
}

// ── PCM helpers ───────────────────────────────────────────────────────────────

/**
 * Safe base64 encoder for Uint8Array.
 * Avoids btoa(String.fromCharCode(...bytes)) which can overflow the JS call
 * stack when the spread creates thousands of function arguments.
 */
function uint8ToBase64(bytes: Uint8Array): string {
  let s = ''
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i])
  return btoa(s)
}

/**
 * Calcula la energía RMS de un buffer Float32.
 * Útil para detectar silencio vs voz.
 */
function calculateRMS(buffer: Float32Array): number {
  let sum = 0
  for (let i = 0; i < buffer.length; i++) {
    sum += buffer[i] * buffer[i]
  }
  return Math.sqrt(sum / buffer.length)
}

// ── Hook ──────────────────────────────────────────────────────────────────────

export function useAudioCapture(
  options: UseAudioCaptureOptions = {}
): UseAudioCaptureReturn {
  const {
    autoStart = false,
    silenceThreshold = 0.015,
    silenceDuration = 1500,
    maxRecordingDuration = 15000,
    onWakeWordDetected,
    onRecordingSent,
  } = options

  const [mode, setMode] = useState<AudioCaptureMode>('idle')
  const [isCapturing, setIsCapturing] = useState(false)
  const [audioLevel, setAudioLevel] = useState(0)
  const [error, setError] = useState<Error | null>(null)

  // Refs para recursos de audio (no causan re-renders)
  const audioContextRef = useRef<AudioContext | null>(null)
  const streamRef = useRef<MediaStream | null>(null)
  const analyserRef = useRef<AnalyserNode | null>(null)
  const analyserIntervalRef = useRef<number | null>(null)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const recordedChunksRef = useRef<Blob[]>([])
  const silenceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const maxRecordingTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const modeRef              = useRef<AudioCaptureMode>('idle') // shadow state en ref para closures
  const isCapturingRef       = useRef(false)                    // ref guard to prevent double-start race
  const audioLevelRef        = useRef(0)                        // last committed audioLevel value
  const recordingStartTimeRef = useRef<number>(0)               // timestamp when recording started
  const graceActiveRef       = useRef(false)                     // true during post-wake-word grace period
  const graceTimerRef        = useRef<ReturnType<typeof setTimeout> | null>(null)
  const pcmBufferRef         = useRef<number[]>([])             // int16 samples accumulator para Porcupine
  const visibilityHandlerRef  = useRef<(() => void) | null>(null) // cleanup for visibilitychange listener
  const recognitionRef        = useRef<any>(null)                 // Web Speech API SpeechRecognition instance
  const speechApiFailedRef    = useRef(false)                     // true after permanent failure (network/not-allowed)

  // Sync mode → modeRef
  const updateMode = useCallback((newMode: AudioCaptureMode) => {
    modeRef.current = newMode
    setMode(newMode)
  }, [])

  // ── Terminar grabación y enviar al backend ─────────────────────────────────

  const finishRecording = useCallback(() => {
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }

    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
    if (maxRecordingTimerRef.current) {
      clearTimeout(maxRecordingTimerRef.current)
      maxRecordingTimerRef.current = null
    }
    if (graceTimerRef.current) {
      clearTimeout(graceTimerRef.current)
      graceTimerRef.current = null
    }
    graceActiveRef.current = false

    updateMode('processing')
  }, [updateMode])

  // ── Iniciar grabación de speech ────────────────────────────────────────────

  const startRecording = useCallback(() => {
    if (!streamRef.current) {
      console.warn('[AudioCapture] Cannot record: no active stream')
      return
    }

    console.log('[AudioCapture] 🔴 Starting speech recording...')
    recordedChunksRef.current = []

    // MediaRecorder graba el stream en WebM/Opus (bien soportado en Chrome/Electron)
    const mediaRecorder = new MediaRecorder(streamRef.current, {
      mimeType: 'audio/webm;codecs=opus',
    })

    mediaRecorder.ondataavailable = (e) => {
      if (e.data.size > 0) {
        recordedChunksRef.current.push(e.data)
      }
    }

    mediaRecorder.onstop = async () => {
      const chunks = recordedChunksRef.current
      if (chunks.length === 0) {
        console.warn('[AudioCapture] No audio recorded')
        updateMode('wake_word')
        return
      }

      const blob = new Blob(chunks, { type: 'audio/webm;codecs=opus' })
      const durationMs = Date.now() - recordingStartTimeRef.current
      console.log(`[AudioCapture] 📦 Recording complete: ${blob.size} bytes (${durationMs}ms)`)

      if (durationMs < 1000) {
        console.warn(`[AudioCapture] ⚠️  Too short (${durationMs}ms < 1000ms) — discarding`)
        updateMode('wake_word')
        return
      }

      // Leer como ArrayBuffer y codificar en base64
      const arrayBuffer = await blob.arrayBuffer()
      const b64 = uint8ToBase64(new Uint8Array(arrayBuffer))

      // Guard: only send if WS is connected — otherwise the audio is silently dropped
      if (!wsService.isConnected()) {
        console.warn('[AudioCapture] ⚠️  WS not connected — audio_command dropped, returning to wake_word')
        updateMode('wake_word')
        return
      }

      // Enviar al backend para Whisper
      wsService.send('audio_command', {
        audio: b64,
        format: 'webm',
        timestamp: Date.now(),
      })

      console.log('[AudioCapture] ✅ audio_command sent to backend')
      onRecordingSent?.(blob.size)

      // Volver a escuchar wake word
      updateMode('wake_word')

      // Restart SpeechRecognition now that we're back in wake_word mode
      if (recognitionRef.current && isCapturingRef.current) {
        try { recognitionRef.current.start() } catch (_) {}
      }
    }

    recordingStartTimeRef.current = Date.now()
    mediaRecorder.start(100) // Chunks cada 100ms
    mediaRecorderRef.current = mediaRecorder

    // Grace period: disable silence detection for 2s after recording starts.
    // Gives user time to pause after wake word before speaking their command.
    graceActiveRef.current = true
    if (graceTimerRef.current) clearTimeout(graceTimerRef.current)
    graceTimerRef.current = setTimeout(() => {
      graceActiveRef.current = false
      graceTimerRef.current = null
      console.log('[AudioCapture] Grace period ended — silence detection active')
    }, 2000)

    updateMode('recording')

    // Timeout máximo de grabación
    maxRecordingTimerRef.current = setTimeout(() => {
      console.log('[AudioCapture] Max recording duration reached, stopping...')
      finishRecording()
    }, maxRecordingDuration)
  }, [updateMode, onRecordingSent, maxRecordingDuration, finishRecording])

  // ── AnalyserNode: audio level + VAD (replaces deprecated ScriptProcessorNode) ──
  // ScriptProcessorNode crashes the Electron renderer on Windows with exit code
  // -1073741819 (STATUS_ACCESS_VIOLATION). AnalyserNode is stable, modern, and
  // supported everywhere. We poll it at 100ms for VU meter and VAD.

  const setupAudioProcessor = useCallback(
    (audioContext: AudioContext, source: MediaStreamAudioSourceNode) => {
      const analyser = audioContext.createAnalyser()
      analyser.fftSize = 2048
      analyser.smoothingTimeConstant = 0.3
      source.connect(analyser)
      analyserRef.current = analyser

      const data = new Float32Array(analyser.fftSize)

      const intervalId = window.setInterval(() => {
        analyser.getFloatTimeDomainData(data)
        const rms = calculateRMS(data)

        const newLevel = Math.min(1, rms * 10)
        if (Math.abs(newLevel - audioLevelRef.current) > 0.02) {
          audioLevelRef.current = newLevel
          setAudioLevel(newLevel)
        }

        if (modeRef.current === 'recording') {
          const elapsed = Date.now() - recordingStartTimeRef.current

          // Skip silence detection during grace period (2s after recording starts)
          // and enforce minimum 2s recording duration
          if (!graceActiveRef.current && elapsed >= 2000) {
            if (rms < silenceThreshold) {
              if (!silenceTimerRef.current) {
                silenceTimerRef.current = setTimeout(() => {
                  console.log('[AudioCapture] 🤫 Silence detected, finishing recording...')
                  finishRecording()
                  silenceTimerRef.current = null
                }, silenceDuration)
              }
            } else if (silenceTimerRef.current) {
              clearTimeout(silenceTimerRef.current)
              silenceTimerRef.current = null
            }
          }
        }

        // ── Enviar PCM chunks al backend para detección de wake word (Porcupine) ──
        // Resamplear de la tasa nativa del AudioContext a 16kHz via decimación lineal,
        // acumular en pcmBufferRef, y enviar en frames de 512 muestras (requerido por Porcupine).
        if (modeRef.current === 'wake_word' && wsService.isConnected()) {
          const nativeRate = audioContext.sampleRate
          const targetRate = 16000
          const ratio = nativeRate / targetRate
          const outLen = Math.floor(data.length / ratio)
          for (let i = 0; i < outLen; i++) {
            const src = data[Math.round(i * ratio)]
            pcmBufferRef.current.push(Math.max(-32768, Math.min(32767, Math.round(src * 32767))))
          }
          while (pcmBufferRef.current.length >= 512) {
            const frame = pcmBufferRef.current.splice(0, 512)
            const int16 = new Int16Array(frame)
            wsService.send('audio_chunk', { audio: uint8ToBase64(new Uint8Array(int16.buffer)) })
          }
        }
      }, 100)

      analyserIntervalRef.current = intervalId
    },
    [silenceThreshold, silenceDuration, finishRecording]
  )

  // ── startCapture ──────────────────────────────────────────────────────────

  const startCapture = useCallback(async (): Promise<boolean> => {
    // Use ref (not state) to guard against stale-closure double-start
    if (isCapturingRef.current) {
      console.log('[AudioCapture] Already capturing')
      return true
    }
    isCapturingRef.current = true  // lock immediately, before any await
    speechApiFailedRef.current = false  // reset on each fresh start

    try {
      console.log('[AudioCapture] 🎤 Requesting microphone access...')

      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          channelCount: 1,        // Mono
          sampleRate: 16000,      // 16kHz requerido por Porcupine y Whisper
          echoCancellation: true,
          noiseSuppression: true,
          autoGainControl: true,
        },
      })

      streamRef.current = stream

      // Usar la tasa nativa del sistema — forzar 16kHz puede crashear drivers de
      // Windows. El resampling a 16kHz para Porcupine se hace en JS dentro del
      // polling de AnalyserNode (pcmBufferRef). Whisper acepta cualquier tasa.
      const audioContext = new AudioContext()
      audioContextRef.current = audioContext

      const source = audioContext.createMediaStreamSource(stream)
      setupAudioProcessor(audioContext, source)

      // ── Web Speech API: browser-native wake word detection ─────────────────
      // Chromium/Electron has built-in SpeechRecognition — no API key needed.
      // Detects "hey atlas" / "atlas" locally; tells backend via wake_word_trigger.
      const SpeechRecognitionAPI =
        (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition
      if (SpeechRecognitionAPI) {
        const recognition = new SpeechRecognitionAPI()
        recognition.continuous     = true
        recognition.interimResults = true
        recognition.lang           = 'en-US'

        const WAKE_TRIGGERS = ['atlas', 'hey atlas', 'hello atlas', 'hola atlas']

        recognition.onresult = (event: any) => {
          if (modeRef.current !== 'wake_word') return
          const transcript = Array.from(event.results as any[])
            .map((r: any) => r[0].transcript)
            .join('')
            .toLowerCase()
            .trim()
          if (WAKE_TRIGGERS.some(w => transcript.includes(w))) {
            console.log(`[AudioCapture] 🗣️  Wake word via SpeechRecognition: "${transcript}"`)
            recognition.stop()   // pause during recording
            onWakeWordDetected?.('hey atlas')
            startRecording()
            if (wsService.isConnected()) {
              wsService.send('wake_word_trigger', { wake_word: 'hey atlas' })
            }
          }
        }

        recognition.onerror = (event: any) => {
          if (event.error === 'aborted') return      // expected on recognition.stop()
          if (event.error === 'not-allowed' || event.error === 'network') {
            // Permanent failure — stop retrying to prevent infinite loop
            speechApiFailedRef.current = true
            console.warn(`[AudioCapture] SpeechRecognition permanently failed (${event.error}), falling back to backend wake word`)
            return
          }
          if (event.error !== 'no-speech') {
            console.warn('[AudioCapture] SpeechRecognition error:', event.error)
          }
        }

        recognition.onend = () => {
          // Don't restart after permanent failure or when not in wake_word mode
          if (speechApiFailedRef.current) return
          if (modeRef.current === 'wake_word' && isCapturingRef.current) {
            try { recognition.start() } catch (_) {}
          }
        }

        recognitionRef.current = recognition
        recognition.start()
        console.log('[AudioCapture] 🧠 Web Speech API wake word detection active')
      } else {
        console.warn('[AudioCapture] SpeechRecognition not available — using backend-only detection')
      }

      // Resume AudioContext if Chromium suspends it when the window is hidden.
      // setBackgroundThrottling(false) in main.ts prevents CPU throttling, but
      // AudioContext can still auto-suspend on visibilitychange in some builds.
      const onVisibility = () => {
        if (audioContextRef.current?.state === 'suspended') {
          audioContextRef.current.resume()
        }
      }
      document.addEventListener('visibilitychange', onVisibility)
      visibilityHandlerRef.current = onVisibility

      setIsCapturing(true)
      setError(null)
      updateMode('wake_word')

      console.log('[AudioCapture] ✅ Mic capture started, listening for wake word...')
      return true

    } catch (err) {
      isCapturingRef.current = false  // release lock on failure
      const e = err as Error
      console.error('[AudioCapture] Failed to start capture:', e)
      setError(e)
      return false
    }
  }, [setupAudioProcessor, updateMode])

  // ── stopCapture ───────────────────────────────────────────────────────────

  const stopCapture = useCallback(() => {
    console.log('[AudioCapture] Stopping audio capture...')

    // Stop MediaRecorder
    if (mediaRecorderRef.current && mediaRecorderRef.current.state !== 'inactive') {
      mediaRecorderRef.current.stop()
    }
    mediaRecorderRef.current = null

    // Stop AnalyserNode polling interval and disconnect
    if (analyserIntervalRef.current !== null) {
      clearInterval(analyserIntervalRef.current)
      analyserIntervalRef.current = null
    }
    if (analyserRef.current) {
      analyserRef.current.disconnect()
      analyserRef.current = null
    }

    // Close AudioContext
    if (audioContextRef.current) {
      audioContextRef.current.close()
      audioContextRef.current = null
    }

    // Stop mic stream tracks
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((t) => t.stop())
      streamRef.current = null
    }

    // Clear timers
    if (silenceTimerRef.current) {
      clearTimeout(silenceTimerRef.current)
      silenceTimerRef.current = null
    }
    if (maxRecordingTimerRef.current) {
      clearTimeout(maxRecordingTimerRef.current)
      maxRecordingTimerRef.current = null
    }
    if (graceTimerRef.current) {
      clearTimeout(graceTimerRef.current)
      graceTimerRef.current = null
    }
    graceActiveRef.current = false

    // Remove visibilitychange listener
    if (visibilityHandlerRef.current) {
      document.removeEventListener('visibilitychange', visibilityHandlerRef.current)
      visibilityHandlerRef.current = null
    }

    // Stop Web Speech API recognition
    if (recognitionRef.current) {
      try { recognitionRef.current.abort() } catch (_) {}
      recognitionRef.current = null
    }

    pcmBufferRef.current = []       // descartar muestras PCM pendientes
    isCapturingRef.current = false  // release lock so startCapture can run again
    setIsCapturing(false)
    setAudioLevel(0)
    updateMode('idle')
    console.log('[AudioCapture] Capture stopped')
  }, [updateMode])

  // ── Manual recording controls ─────────────────────────────────────────────

  const startManualRecording = useCallback(() => {
    if (modeRef.current === 'recording') return
    if (!isCapturing) {
      console.warn('[AudioCapture] Cannot record: microphone not started')
      return
    }
    console.log('[AudioCapture] Manual recording triggered')
    startRecording()
  }, [isCapturing, startRecording])

  const stopManualRecording = useCallback(() => {
    if (modeRef.current === 'recording') {
      finishRecording()
    }
  }, [finishRecording])

  // ── Listen for wake_word_detected from backend ────────────────────────────

  useEffect(() => {
    const handleWakeWord = (data: { wake_word: string }) => {
      if (modeRef.current !== 'wake_word') return

      console.log(`[AudioCapture] 🗣️  Wake word from backend: '${data.wake_word}'`)
      onWakeWordDetected?.(data.wake_word)
      startRecording()
    }

    wsService.on('wake_word_detected', handleWakeWord)
    return () => wsService.off('wake_word_detected', handleWakeWord)
  }, [onWakeWordDetected, startRecording])

  // ── Auto-start ────────────────────────────────────────────────────────────
  // Delay slightly so the Electron window fully renders before getUserMedia fires.
  // Without this, the Windows mic-permission dialog can steal focus before the
  // orb canvas even paints once, making the window look like it disappeared.

  useEffect(() => {
    if (!autoStart) return
    const timer = setTimeout(() => { startCapture() }, 800)
    return () => {
      clearTimeout(timer)
      stopCapture()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  return {
    startCapture,
    stopCapture,
    startManualRecording,
    stopManualRecording,
    mode,
    isCapturing,
    audioLevel,
    error,
  }
}
