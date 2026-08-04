/**
 * App Component — Atlas AI
 *
 * Clean, professional dark desktop app with 3-zone layout:
 * - Fixed sidebar (64px) with navigation icons
 * - Main area with centered orb
 * - Sliding panels: Chat, Memory, Settings
 */

import { useEffect, useState, useCallback, useRef } from 'react'
import { MessageSquare, Brain, Settings, Moon } from 'lucide-react'
import { useWebSocket } from './hooks/useWebSocket'
import { useAudioCapture } from './hooks/useAudioCapture'
import { useTTSPlayer } from './hooks/useTTSPlayer'
import { NeuralOrb } from './components/Orb/NeuralOrb'
import { ChatInterface } from './components/Chat/ChatInterface'
import { MemoryPanel } from './components/Memory/MemoryPanel'
import { SettingsPanel } from './components/Settings/SettingsPanel'
import { Toast } from './components/ui/Toast'
import { withApiKeyHeader } from './services/apiKey'
import type { Message } from './components/Chat/ChatInterface'
import type { Memory } from './components/Memory/MemoryPanel'
import './App.css'

// ── Types ─────────────────────────────────────────────────────────────────────

type PanelType = 'chat' | 'memory' | 'settings' | null

interface StreamingMessage extends Message {
  streaming?: boolean
}

type WsEventType =
  | 'connected' | 'disconnected' | 'ping' | 'pong'
  | 'state_changed' | 'wake_word_detected'
  | 'ai_response_generated' | 'ai_response_chunk'
  | 'tts_audio' | 'tool_screenshot'
  | 'ui_command' | 'error_detected'
  | 'memories_updated' | 'stop_tts'

interface AIResponseChunkData {
  chunk: string
  done: boolean
}

interface StateChangedData {
  new_mode: string
}

interface UICommandData {
  action: string
}

interface AIResponseData {
  message: string
  timestamp?: string
  transcription?: string
}

interface ToolScreenshotData {
  image: string
}

interface ToastMessage {
  id: string
  type: 'success' | 'error' | 'info'
  message: string
}

// ── Constants ─────────────────────────────────────────────────────────────────

const PING_INTERVAL_MS = 10_000
const API_BASE = (import.meta.env.VITE_API_URL as string | undefined) ?? 'http://localhost:8000'

// ── Component ─────────────────────────────────────────────────────────────────

function App() {
  const { isConnected, send, on, off } = useWebSocket()

  const [assistantState, setAssistantState] = useState<string>('active')
  const [isSleeping, setIsSleeping] = useState(false)
  const [openPanel, setOpenPanel] = useState<PanelType>(null)
  const [messages, setMessages] = useState<StreamingMessage[]>([])
  const [memories, setMemories] = useState<Memory[]>([])
  const [toasts, setToasts] = useState<ToastMessage[]>([])

  const openPanelRef = useRef<PanelType>(null)
  const streamingMessageIdRef = useRef<string | null>(null)

  // ── Toast helper ──────────────────────────────────────────────────────────
  const showToast = useCallback((type: 'success' | 'error' | 'info', message: string) => {
    const id = crypto.randomUUID()
    setToasts(prev => [...prev, { id, type, message }])
    setTimeout(() => {
      setToasts(prev => prev.filter(t => t.id !== id))
    }, 3000)
  }, [])

  // ── Load memories on mount ────────────────────────────────────────────────
  useEffect(() => {
    fetch(`${API_BASE}/api/memories`, withApiKeyHeader())
      .then(r => r.json())
      .then(json => setMemories(json.memories ?? []))
      .catch(() => {/* backend not up yet — silent fail */})
  }, [])

  // ── Panel management ──────────────────────────────────────────────────────
  const openPanelByType = useCallback((panel: PanelType) => {
    if (panel === openPanel) return
    openPanelRef.current = panel
    setOpenPanel(panel)
  }, [openPanel])

  const closePanel = useCallback(() => {
    openPanelRef.current = null
    setOpenPanel(null)
  }, [])

  // ── Voice callbacks ───────────────────────────────────────────────────────
  const onWakeWord = useCallback((_w: string) => {
    stopPlaybackRef.current()   // barge-in: kill TTS when user starts talking
    setAssistantState('listening')
  }, [])

  const onRecording = useCallback((_size: number) => setAssistantState('thinking'), [])
  const onTTSStart = useCallback(() => setAssistantState('speaking'), [])
  const onTTSEnd = useCallback(() => setAssistantState('active'), [])

  // ── Voice capture — ALWAYS ON ────────────────────────────────────────────
  const {
    mode: audioMode,
    isCapturing,
    audioLevel,
  } = useAudioCapture({
    autoStart: true,
    onWakeWordDetected: onWakeWord,
    onRecordingSent: onRecording,
  })

  // ── TTS playback ──────────────────────────────────────────────────────────
  const { stopPlayback } = useTTSPlayer({ onPlayStart: onTTSStart, onPlayEnd: onTTSEnd })

  // Keep a stable ref so audio callbacks can access stopPlayback without stale closures
  const stopPlaybackRef = useRef(stopPlayback)
  useEffect(() => { stopPlaybackRef.current = stopPlayback }, [stopPlayback])

  // Sync orb state with audio mode + barge-in on VAD-triggered recording
  useEffect(() => {
    if (!isCapturing) return
    if (audioMode === 'wake_word') setAssistantState('active')
    if (audioMode === 'recording') {
      stopPlaybackRef.current()   // barge-in: VAD started recording → kill TTS
      setAssistantState('listening')
    }
    if (audioMode === 'processing') setAssistantState('thinking')
  }, [audioMode, isCapturing])

  // ── WebSocket events ──────────────────────────────────────────────────────
  useEffect(() => {
    const onStateChanged = (data: StateChangedData) => {
      if (!data?.new_mode) return
      setAssistantState(data.new_mode === 'paused' ? 'sleeping' : data.new_mode)
      setIsSleeping(data.new_mode === 'paused')
    }

    const onWakeWordEvt = (_data: unknown) => {
      setAssistantState('listening')
    }

    const onUICommand = (data: UICommandData) => {
      if (data?.action === 'dismiss') {
        closePanel()
        setAssistantState('active')
      } else if (data?.action === 'open_chat') {
        openPanelByType('chat')
      }
    }

    const onAIResponse = (data: AIResponseData) => {
      if (!data?.message) return

      // Clear any pending streaming message
      streamingMessageIdRef.current = null

      const ts = data.timestamp ? new Date(data.timestamp) : new Date()

      setMessages(prev => {
        const next = [...prev]
        // If this response came from voice (has transcription), show what the user said first
        if (data.transcription?.trim()) {
          next.push({
            id: crypto.randomUUID(),
            content: data.transcription.trim(),
            role: 'user',
            timestamp: ts,
          })
          // Auto-open chat when voice transcript arrives so user can see the exchange
          if (openPanelRef.current !== 'chat') {
            openPanelByType('chat')
          }
        }
        next.push({
          id: crypto.randomUUID(),
          content: data.message,
          role: 'assistant',
          timestamp: ts,
          streaming: false,
        })
        return next
      })
    }

    const onAIResponseChunk = (data: AIResponseChunkData) => {
      if (!data?.chunk) return

      setMessages(prev => {
        // Find or create streaming message
        if (!streamingMessageIdRef.current || !prev.find(m => m.id === streamingMessageIdRef.current)) {
          const newId = crypto.randomUUID()
          streamingMessageIdRef.current = newId
          return [...prev, {
            id: newId,
            content: data.chunk,
            role: 'assistant',
            timestamp: new Date(),
            streaming: true,
          }]
        }

        // Append chunk to streaming message
        return prev.map(m =>
          m.id === streamingMessageIdRef.current
            ? { ...m, content: m.content + data.chunk }
            : m
        )
      })

      // Mark as done if this is the last chunk
      if (data.done) {
        setMessages(prev => prev.map(m =>
          m.id === streamingMessageIdRef.current
            ? { ...m, streaming: false }
            : m
        ))
        streamingMessageIdRef.current = null
      }
    }

    const onToolScreenshot = (data: ToolScreenshotData) => {
      if (!data?.image) return
      setMessages(prev => [...prev, {
        id: crypto.randomUUID(),
        content: `__screenshot__:${data.image}`,
        role: 'tool_screenshot' as any,
        timestamp: new Date(),
      }])
    }

    const onStopTTS = (_data: unknown) => {
      stopPlaybackRef.current()
      setAssistantState('active')
    }

    const onMemoriesUpdated = async (_data: unknown) => {
      try {
        const res = await fetch(`${API_BASE}/api/memories`, withApiKeyHeader())
        if (res.ok) {
          const json = await res.json()
          setMemories(json.memories ?? [])
        }
      } catch (e) {
        console.warn('[App] Failed to refresh memories:', e)
      }
    }

    on('state_changed' as WsEventType, onStateChanged)
    on('wake_word_detected' as WsEventType, onWakeWordEvt)
    on('ai_response_generated' as WsEventType, onAIResponse)
    on('ai_response_chunk' as WsEventType, onAIResponseChunk)
    on('tool_screenshot' as WsEventType, onToolScreenshot)
    on('ui_command' as WsEventType, onUICommand)
    on('memories_updated' as WsEventType, onMemoriesUpdated)
    on('stop_tts' as WsEventType, onStopTTS)

    const ping = setInterval(() => {
      if (isConnected) send('ping', {})
    }, PING_INTERVAL_MS)

    return () => {
      off('state_changed' as WsEventType, onStateChanged)
      off('wake_word_detected' as WsEventType, onWakeWordEvt)
      off('ai_response_generated' as WsEventType, onAIResponse)
      off('ai_response_chunk' as WsEventType, onAIResponseChunk)
      off('tool_screenshot' as WsEventType, onToolScreenshot)
      off('ui_command' as WsEventType, onUICommand)
      off('memories_updated' as WsEventType, onMemoriesUpdated)
      off('stop_tts' as WsEventType, onStopTTS)
      clearInterval(ping)
    }
  }, [isConnected, on, off, send, closePanel, openPanelByType])

  // ── Orb click: toggle chat ────────────────────────────────────────────────
  const handleOrbClick = useCallback(() => {
    if (openPanelRef.current === 'chat') {
      closePanel()
    } else {
      openPanelByType('chat')
    }
  }, [openPanelByType, closePanel])

  // ── Send chat message ─────────────────────────────────────────────────────
  const handleSendMessage = useCallback((text: string, imageData?: string) => {
    // Intercept stop commands typed in chat — cut TTS immediately, no round trip
    const lower = text.trim().toLowerCase()
    const stopKeywords = ['stop', 'stop talking', 'stop it', 'shut up', 'be quiet', 'para', 'cállate', 'callate']
    if (stopKeywords.includes(lower)) {
      stopPlaybackRef.current()
      setAssistantState('active')
      return
    }
    setMessages(prev => [...prev, {
      id: crypto.randomUUID(),
      content: text,
      role: 'user',
      timestamp: new Date(),
    }])
    send('chat_message', { message: text, image_data: imageData ?? null })
    setAssistantState('thinking')
  }, [send])

  // ── Memory handlers ───────────────────────────────────────────────────────
  const handleForgetAll = useCallback(async () => {
    try {
      await fetch(`${API_BASE}/api/memories`, withApiKeyHeader({ method: 'DELETE' }))
      setMemories([])
      showToast('success', 'All memories cleared')
    } catch {
      showToast('error', 'Failed to clear memories')
    }
  }, [showToast])

  const handleDeleteMemory = useCallback(async (id: number) => {
    try {
      await fetch(`${API_BASE}/api/memories/${id}`, withApiKeyHeader({ method: 'DELETE' }))
      setMemories(prev => prev.filter(m => m.id !== id))
    } catch {
      showToast('error', 'Failed to delete memory')
    }
  }, [showToast])

  // ── Sleep toggle ──────────────────────────────────────────────────────────
  const handleSleepToggle = useCallback(() => {
    if (isSleeping) {
      send('resume', {})
      setIsSleeping(false)
      setAssistantState('active')
    } else {
      stopPlaybackRef.current()   // stop talking immediately when sleep pressed
      send('pause', {})
      setIsSleeping(true)
      setAssistantState('sleeping')
    }
  }, [isSleeping, send])

  // ── Settings save handler ─────────────────────────────────────────────────
  const handleSettingsSave = useCallback(() => {
    showToast('success', 'Settings saved')
    closePanel()
  }, [showToast, closePanel])

  // ── State label map ───────────────────────────────────────────────────────
  const STATE_LABELS: Record<string, string> = {
    active:    'Ready',
    listening: 'Listening…',
    thinking:  'Thinking…',
    speaking:  'Speaking…',
    sleeping:  'Sleeping…',
    paused:    'Sleeping…',
    inactive:  'Offline',
  }

  // ── Render ────────────────────────────────────────────────────────────────
  return (
    <div className="app-layout">
      {/* Sidebar */}
      <aside className="sidebar">
        <nav className="sidebar-nav">
          <button
            className={`sidebar-btn ${openPanel === 'chat' ? 'active' : ''}`}
            onClick={() => openPanelByType('chat')}
            title="Chat"
          >
            <MessageSquare size={20} />
          </button>
          <button
            className={`sidebar-btn ${openPanel === 'memory' ? 'active' : ''}`}
            onClick={() => openPanelByType('memory')}
            title="Memory"
          >
            <Brain size={20} />
          </button>
          <button
            className={`sidebar-btn ${openPanel === 'settings' ? 'active' : ''}`}
            onClick={() => openPanelByType('settings')}
            title="Settings"
          >
            <Settings size={20} />
          </button>
          <button
            className={`sidebar-btn ${isSleeping ? 'active' : ''}`}
            onClick={handleSleepToggle}
            title={isSleeping ? 'Wake Atlas' : 'Sleep mode'}
          >
            <Moon size={20} />
          </button>
        </nav>

        <div className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`}
          title={isConnected ? 'Connected to Atlas backend' : 'Disconnected from backend'}
        />
      </aside>

      {/* Main area */}
      <main className="main-area">
        {/* Orb — fills the entire main area */}
        <div className="orb-container">
          <div className="orb-wrap">
            <NeuralOrb
              state={assistantState as any}
              onClick={handleOrbClick}
              audioLevel={audioLevel}
            />
            <div className="state-badge" data-state={assistantState}>
              {STATE_LABELS[assistantState] ?? assistantState}
            </div>
          </div>
        </div>

        {/* Chat panel (slides in from right) */}
        <div className={`panel-overlay ${openPanel === 'chat' ? 'open' : ''}`}>
          <ChatInterface
            messages={messages}
            onSendMessage={handleSendMessage}
            onClose={closePanel}
            audioMode={audioMode}
          />
        </div>

        {/* Memory panel (slides in from right) */}
        <div className={`panel-overlay ${openPanel === 'memory' ? 'open' : ''}`}>
          {openPanel === 'memory' && (
            <MemoryPanel
              memories={memories}
              onForgetAll={handleForgetAll}
              onDeleteMemory={handleDeleteMemory}
            />
          )}
        </div>

        {/* Settings panel (slides in from right) */}
        <div className={`panel-overlay ${openPanel === 'settings' ? 'open' : ''}`}>
          {openPanel === 'settings' && (
            <SettingsPanel
              onClose={closePanel}
              onSave={handleSettingsSave}
            />
          )}
        </div>
      </main>

      {/* Toast notifications */}
      <div className="toast-container">
        {toasts.map(toast => (
          <Toast key={toast.id} type={toast.type} message={toast.message} />
        ))}
      </div>
    </div>
  )
}

export default App
