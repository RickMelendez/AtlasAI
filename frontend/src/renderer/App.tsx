/**
 * App Component — Atlas AI
 *
 * Always-on design: mic is always capturing, Atlas always listens for
 * "Hey Atlas". Chat opens automatically when the wake word is detected
 * or when the user clicks the orb.
 *
 * Window states:
 *   Orb only  → 200 × 200 px  (always visible, always on top)
 *   With chat → 420 × 660 px  (still always on top)
 *
 * Screen capture: starts automatically when Atlas is active, sending
 * frames to the backend so Claude can see what you're doing.
 */

import { useEffect, useState, useCallback, useRef } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import { useAudioCapture } from './hooks/useAudioCapture'
import { useTTSPlayer } from './hooks/useTTSPlayer'
import { OrbCanvas } from './components/Orb/OrbCanvas'
import { ChatInterface } from './components/Chat/ChatInterface'
import type { Message } from './components/Chat/ChatInterface'
import './App.css'

// ── Constants ─────────────────────────────────────────────────────────────────
const PING_INTERVAL_MS = 10_000

// ── Window dimensions ─────────────────────────────────────────────────────────
const ORB_W  = 200
const ORB_H  = 200
const CHAT_W = 420
const CHAT_H = 660

// ── Component ─────────────────────────────────────────────────────────────────

function App() {
  const { isConnected, send, on, off } = useWebSocket()
  // Default to 'active' so the orb is always bright and visible at startup.
  // It transitions to the correct state once audio capture initialises (or
  // stays 'active' if the mic is unavailable — better than an invisible orb).
  const [assistantState, setAssistantState] = useState<string>('active')
  const [isChatOpen,     setIsChatOpen]     = useState(false)
  const [messages,       setMessages]       = useState<Message[]>([])

  // Drag state
  const [isDragging, setIsDragging] = useState(false)
  const [dragOffset, setDragOffset] = useState({ x: 0, y: 0 })

  // Screen capture active ref (avoid stale closures)
  const screenCaptureActive = useRef(false)
  const isChatOpenRef = useRef(false)

  // ── Helper: open the chat panel + resize window ───────────────────────────
  const openChat = useCallback(async () => {
    if (isChatOpenRef.current) return
    isChatOpenRef.current = true
    setIsChatOpen(true)
    if (window.electronAPI) {
      await window.electronAPI.resizeWindow(CHAT_W, CHAT_H)
    }
  }, [])

  const closeChat = useCallback(async () => {
    isChatOpenRef.current = false
    setIsChatOpen(false)
    if (window.electronAPI) {
      await window.electronAPI.resizeWindow(ORB_W, ORB_H)
    }
  }, [])

  // ── Screen capture → WebSocket ────────────────────────────────────────────
  const startScreenCapture = useCallback(async () => {
    if (screenCaptureActive.current || !window.electronAPI) return
    screenCaptureActive.current = true
    await window.electronAPI.startScreenCapture()
    console.log('[App] 📸 Screen capture started')
  }, [])

  const stopScreenCapture = useCallback(async () => {
    if (!screenCaptureActive.current || !window.electronAPI) return
    screenCaptureActive.current = false
    await window.electronAPI.stopScreenCapture()
    console.log('[App] 📸 Screen capture stopped')
  }, [])

  // Handle "Open Chat" triggered from tray menu (main → renderer IPC push)
  useEffect(() => {
    if (!window.electronAPI?.onOpenChat) return
    const cleanup = window.electronAPI.onOpenChat(async () => {
      await openChat()
      await startScreenCapture()
    })
    return () => { cleanup() }
  }, [openChat, startScreenCapture])

  // Forward screen frames to backend via WebSocket.
  // Registered once at mount — IPC listener is independent of WS connection state.
  // The isConnected check happens at send-time inside the singleton.
  useEffect(() => {
    if (!window.electronAPI) return
    const cleanup = window.electronAPI.onScreenCaptureFrame((frame) => {
      send('screen_capture', {
        data:      frame.data,
        timestamp: frame.timestamp,
        format:    frame.format,
      })
    })
    return () => { cleanup() }
  }, [send])

  // ── Stable voice callbacks ────────────────────────────────────────────────
  const onWakeWord = useCallback(async (w: string) => {
    console.log('[App] 🗣️  Wake word:', w)
    setAssistantState('listening')
    // Show orb without opening chat — user must say "open chat mode"
    await window.electronAPI?.showOrbWindow()
  }, [])

  const onRecording = useCallback((_size: number) => setAssistantState('thinking'),  [])
  const onTTSStart  = useCallback(() => setAssistantState('speaking'), [])
  const onTTSEnd    = useCallback(() => setAssistantState('active'),   [])

  // ── Voice capture — ALWAYS ON ─────────────────────────────────────────────
  const {
    mode:    audioMode,
    isCapturing,
    audioLevel,
    startManualRecording,
    stopManualRecording,
  } = useAudioCapture({
    autoStart:          true,   // Always listening from app start
    onWakeWordDetected: onWakeWord,
    onRecordingSent:    onRecording,
  })

  // ── TTS playback ──────────────────────────────────────────────────────────
  useTTSPlayer({ onPlayStart: onTTSStart, onPlayEnd: onTTSEnd })

  // Sync orb state with audio mode, and stop screen capture when mic turns off.
  // When not capturing, keep orb 'active' (not 'inactive') so it stays visible —
  // 'inactive' is nearly invisible on most desktop backgrounds.
  useEffect(() => {
    if (!isCapturing) {
      stopScreenCapture()
      return
    }
    if (audioMode === 'wake_word')  setAssistantState('active')
    if (audioMode === 'recording')  setAssistantState('listening')
    if (audioMode === 'processing') setAssistantState('thinking')
  }, [audioMode, isCapturing, stopScreenCapture])

  // ── WebSocket events ──────────────────────────────────────────────────────
  useEffect(() => {
    const onStateChanged = (data: any) => {
      if (data?.new_mode) setAssistantState(data.new_mode)
    }
    const onWakeWordEvt = async (_data: any) => {
      setAssistantState('listening')
      await window.electronAPI?.showOrbWindow()
    }
    const onUICommand = async (data: any) => {
      if (data?.action === 'dismiss') {
        await closeChat()
        await window.electronAPI?.hideOrbWindow()
        setAssistantState('active')
      } else if (data?.action === 'open_chat') {
        await openChat()
        await startScreenCapture()
      }
    }
    const onAIResponse = (data: any) => {
      if (!data?.message) return
      setMessages(prev => [...prev, {
        id:        crypto.randomUUID(),
        content:   data.message,
        role:      'assistant' as const,
        timestamp: data.timestamp ? new Date(data.timestamp) : new Date(),
      }])
      setAssistantState('active')
    }
    // Imágenes inline de herramientas (screenshots de browser, etc.)
    const onToolScreenshot = (data: any) => {
      if (!data?.image) return
      setMessages(prev => [...prev, {
        id:        crypto.randomUUID(),
        content:   `__screenshot__:${data.image}`,
        role:      'tool_screenshot' as any,
        timestamp: new Date(),
      }])
    }

    on('state_changed',         onStateChanged)
    on('wake_word_detected',    onWakeWordEvt)
    on('ai_response_generated', onAIResponse)
    on('tool_screenshot',       onToolScreenshot)
    on('ui_command',            onUICommand)

    const ping = setInterval(() => { if (isConnected) send('ping', {}) }, PING_INTERVAL_MS)

    return () => {
      off('state_changed',         onStateChanged)
      off('wake_word_detected',    onWakeWordEvt)
      off('ai_response_generated', onAIResponse)
      off('tool_screenshot',       onToolScreenshot)
      off('ui_command',            onUICommand)
      clearInterval(ping)
    }
  }, [isConnected, on, off, send, closeChat, openChat, startScreenCapture])

  // ── Drag (from orb zone only) ─────────────────────────────────────────────
  const handleOrbMouseDown = useCallback(async (e: React.MouseEvent) => {
    if (!window.electronAPI) return
    const [wx, wy] = await window.electronAPI.getWindowPosition()
    setIsDragging(true)
    setDragOffset({ x: e.screenX - wx, y: e.screenY - wy })
  }, [])

  useEffect(() => {
    if (!isDragging) return
    const onMove = (e: MouseEvent) => {
      window.electronAPI?.setWindowPosition(
        e.screenX - dragOffset.x,
        e.screenY - dragOffset.y,
      )
    }
    const onUp = () => setIsDragging(false)
    window.addEventListener('mousemove', onMove)
    window.addEventListener('mouseup',   onUp)
    return () => {
      window.removeEventListener('mousemove', onMove)
      window.removeEventListener('mouseup',   onUp)
    }
  }, [isDragging, dragOffset])

  // ── Orb click: toggle chat ────────────────────────────────────────────────
  const handleOrbClick = useCallback(async () => {
    if (isDragging) return
    if (isChatOpenRef.current) {
      await closeChat()
    } else {
      await openChat()
      await startScreenCapture()
    }
  }, [isDragging, openChat, closeChat, startScreenCapture])

  // ── Send chat message ─────────────────────────────────────────────────────
  const handleSendMessage = useCallback((text: string) => {
    setMessages(prev => [...prev, {
      id:        crypto.randomUUID(),
      content:   text,
      role:      'user' as const,
      timestamp: new Date(),
    }])
    send('chat_message', { message: text })
    setAssistantState('thinking')
  }, [send])


  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="app">
      {/* Orb zone — always visible at top, draggable */}
      <div
        className="orb-zone"
        onMouseDown={handleOrbMouseDown}
        style={{ cursor: isDragging ? 'grabbing' : 'grab' }}
      >
        <OrbCanvas
          state={assistantState as any}
          onClick={handleOrbClick}
          audioLevel={audioLevel}
        />

        {/* Connection status dot */}
        <div
          className={`conn-dot ${isConnected ? 'conn-dot--on' : 'conn-dot--off'}`}
          title={isConnected ? 'Connected to Atlas backend' : 'Disconnected — backend may be offline'}
        />

      </div>

      {/* Chat panel — slides in below orb */}
      {isChatOpen && (
        <ChatInterface
          messages={messages}
          onSendMessage={handleSendMessage}
          onClose={closeChat}
          audioMode={audioMode}
          onMicClick={startManualRecording}
          onMicStop={stopManualRecording}
        />
      )}
    </div>
  )
}

export default App
