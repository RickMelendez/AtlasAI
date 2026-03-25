/**
 * App Component — Atlas AI
 *
 * Always-on design: mic is always capturing, Atlas always listens for
 * "Hey Atlas". Chat slides in from the right when opened.
 *
 * Fullscreen layout: centered orb, chat panel slides in from right edge.
 */

import { useEffect, useState, useCallback, useRef } from 'react'
import { useWebSocket } from './hooks/useWebSocket'
import { useAudioCapture } from './hooks/useAudioCapture'
import { useTTSPlayer } from './hooks/useTTSPlayer'
import { NeuralOrb } from './components/Orb/NeuralOrb'
import { ChatInterface } from './components/Chat/ChatInterface'
import type { Message } from './components/Chat/ChatInterface'
import './App.css'

// ── Constants ─────────────────────────────────────────────────────────────────
const PING_INTERVAL_MS = 10_000

// ── Component ─────────────────────────────────────────────────────────────────

function App() {
  const { isConnected, send, on, off } = useWebSocket()
  // Default to 'active' so the orb is always bright and visible at startup.
  const [assistantState, setAssistantState] = useState<string>('active')
  const [isChatOpen,     setIsChatOpen]     = useState(false)
  const [messages,       setMessages]       = useState<Message[]>([])

  const isChatOpenRef = useRef(false)

  // ── Helper: open/close chat panel ─────────────────────────────────────────
  const openChat = useCallback(() => {
    if (isChatOpenRef.current) return
    isChatOpenRef.current = true
    setIsChatOpen(true)
  }, [])

  const closeChat = useCallback(() => {
    isChatOpenRef.current = false
    setIsChatOpen(false)
  }, [])

  // ── Stable voice callbacks ────────────────────────────────────────────────
  const onWakeWord = useCallback((_w: string) => {
    setAssistantState('listening')
  }, [])

  const onRecording = useCallback((_size: number) => setAssistantState('thinking'),  [])
  const onTTSStart  = useCallback(() => setAssistantState('speaking'), [])
  const onTTSEnd    = useCallback(() => setAssistantState('active'),   [])

  // ── Voice capture — ALWAYS ON ─────────────────────────────────────────────
  const {
    mode:    audioMode,
    isCapturing,
    audioLevel,
  } = useAudioCapture({
    autoStart:          true,   // Always listening from app start
    onWakeWordDetected: onWakeWord,
    onRecordingSent:    onRecording,
  })

  // ── TTS playback ──────────────────────────────────────────────────────────
  useTTSPlayer({ onPlayStart: onTTSStart, onPlayEnd: onTTSEnd })

  // Sync orb state with audio mode.
  // When not capturing, keep orb 'active' (not 'inactive') so it stays visible.
  useEffect(() => {
    if (!isCapturing) return
    if (audioMode === 'wake_word')  setAssistantState('active')
    if (audioMode === 'recording')  setAssistantState('listening')
    if (audioMode === 'processing') setAssistantState('thinking')
  }, [audioMode, isCapturing])

  // ── WebSocket events ──────────────────────────────────────────────────────
  useEffect(() => {
    const onStateChanged = (data: any) => {
      if (data?.new_mode) setAssistantState(data.new_mode)
    }
    const onWakeWordEvt = (_data: any) => {
      setAssistantState('listening')
    }
    const onUICommand = (data: any) => {
      if (data?.action === 'dismiss') {
        closeChat()
        setAssistantState('active')
      } else if (data?.action === 'open_chat') {
        openChat()
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
      // Do NOT reset to 'active' here — TTS may be about to start.
      // State returns to 'active' only after audio finishes (onTTSEnd).
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
  }, [isConnected, on, off, send, closeChat, openChat])

  // ── Orb click: toggle chat ────────────────────────────────────────────────
  const handleOrbClick = useCallback(() => {
    if (isChatOpenRef.current) {
      closeChat()
    } else {
      openChat()
    }
  }, [openChat, closeChat])

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
      {/* Orb zone — centered in viewport */}
      <div className="orb-zone">
        <NeuralOrb
          state={assistantState as any}
          onClick={handleOrbClick}
          audioLevel={audioLevel}
        />
      </div>

      {/* Connection status dot */}
      <div
        className={`conn-dot ${isConnected ? 'conn-dot--on' : 'conn-dot--off'}`}
        title={isConnected ? 'Connected to Atlas backend' : 'Disconnected — backend may be offline'}
      />

      {/* Bottom-left HUD label */}
      <div className="atlas-label">
        <span className="atlas-label__name">Atlas AI</span>
        <span className="atlas-label__status">
          {isConnected ? 'sys.online' : 'sys.offline'}
        </span>
      </div>

      {/* Top-right corner decoration */}
      <div className="hud-corner" aria-hidden="true">
        <div className="hud-corner__line" />
        <div className="hud-corner__line" />
      </div>

      {/* State badge — centered bottom */}
      <div className="state-badge" data-state={assistantState}>
        {assistantState}
      </div>

      {/* Chat panel — slides in from right */}
      <div className={`chat-panel-wrapper ${isChatOpen ? 'open' : ''}`}>
        <ChatInterface
          messages={messages}
          onSendMessage={handleSendMessage}
          onClose={closeChat}
          audioMode={audioMode}
        />
      </div>
    </div>
  )
}

export default App
