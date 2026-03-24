/**
 * ChatInterface — Atlas AI
 *
 * Full-featured chat panel with markdown rendering, copy buttons,
 * scroll-to-bottom, image paste, and file attachments.
 */

import React, { useEffect, useRef, useState, useCallback } from 'react'
import type { AudioCaptureMode } from '../../hooks/useAudioCapture'
import { Loader }   from '../ui/loader'
import PromptInput  from '../ui/prompt-input-dynamic-grow'
import './ChatInterface.css'

// ── Types ──────────────────────────────────────────────────────────────────────

export interface Message {
  id:        string
  content:   string
  role:      'user' | 'assistant'
  timestamp: Date
}

export interface ChatInterfaceProps {
  messages?:       Message[]
  onSendMessage?:  (message: string) => void
  onClose?:        () => void
  audioMode?:      AudioCaptureMode
  onMicClick?:     () => void
  onMicStop?:      () => void
}

// ── Markdown helpers ───────────────────────────────────────────────────────────

/** Parse a simple subset of markdown into React nodes. */
function formatMessage(content: string): React.ReactNode {
  // Split by code blocks first (```...```)
  const parts = content.split(/(```[\s\S]*?```)/g)

  return parts.map((part, i) => {
    // Code block
    if (part.startsWith('```') && part.endsWith('```')) {
      const inner = part.slice(3, -3)
      // Extract optional language hint from first line
      const newlineIdx = inner.indexOf('\n')
      const lang = newlineIdx > 0 && newlineIdx < 20 && /^[a-zA-Z]+$/.test(inner.slice(0, newlineIdx).trim())
        ? inner.slice(0, newlineIdx).trim()
        : ''
      const code = lang ? inner.slice(newlineIdx + 1) : inner

      return <CodeBlock key={i} code={code} lang={lang} />
    }

    // Inline formatting
    return <span key={i}>{formatInline(part)}</span>
  })
}

function formatInline(text: string): React.ReactNode[] {
  // Process inline code, bold, and italic
  const nodes: React.ReactNode[] = []
  // Split by inline code first
  const parts = text.split(/(`[^`]+`)/g)
  parts.forEach((part, i) => {
    if (part.startsWith('`') && part.endsWith('`')) {
      nodes.push(<code key={i} className="msg-inline-code">{part.slice(1, -1)}</code>)
    } else {
      // Bold: **text**
      const boldParts = part.split(/(\*\*[^*]+\*\*)/g)
      boldParts.forEach((bp, j) => {
        if (bp.startsWith('**') && bp.endsWith('**')) {
          nodes.push(<strong key={`${i}-${j}`}>{bp.slice(2, -2)}</strong>)
        } else {
          nodes.push(bp)
        }
      })
    }
  })
  return nodes
}

/** Code block with copy button */
function CodeBlock({ code, lang }: { code: string; lang: string }) {
  const [copied, setCopied] = useState(false)

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(code)
    setCopied(true)
    setTimeout(() => setCopied(false), 1500)
  }, [code])

  return (
    <div className="code-block">
      <div className="code-block-header">
        {lang && <span className="code-block-lang">{lang}</span>}
        <button className="code-block-copy" onClick={handleCopy}>
          {copied ? 'Copied!' : 'Copy'}
        </button>
      </div>
      <pre><code>{code}</code></pre>
    </div>
  )
}

// ── Component ──────────────────────────────────────────────────────────────────

export const ChatInterface: React.FC<ChatInterfaceProps> = ({
  messages      = [],
  onSendMessage,
  onClose,
  audioMode     = 'idle',
  onMicClick,
  onMicStop,
}) => {
  const messagesEndRef       = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  const [copiedId, setCopiedId]           = useState<string | null>(null)

  // Auto-scroll only when near bottom (don't steal scroll when reading history)
  useEffect(() => {
    if (!showScrollBtn) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, showScrollBtn])

  // Track scroll position
  const handleScroll = useCallback(() => {
    const el = messagesContainerRef.current
    if (!el) return
    const atBottom = el.scrollHeight - el.scrollTop - el.clientHeight < 60
    setShowScrollBtn(!atBottom)
  }, [])

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    setShowScrollBtn(false)
  }, [])

  // Copy message text
  const copyMessage = useCallback((id: string, text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 1500)
  }, [])

  const isRecording  = audioMode === 'recording'
  const isProcessing = audioMode === 'processing'
  const isListening  = audioMode === 'wake_word'

  return (
    <div className="chat-panel">
      {/* Close */}
      <button className="chat-close" onClick={onClose} title="Close chat">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
          <line x1="18" y1="6" x2="6" y2="18"/>
          <line x1="6"  y1="6" x2="18" y2="18"/>
        </svg>
      </button>

      {/* ── Messages ──────────────────────────────────────────────────────── */}
      <div
        className="chat-messages"
        ref={messagesContainerRef}
        onScroll={handleScroll}
      >
        {messages.length === 0 ? (
          <div className="chat-empty">
            <p className="chat-empty-title">Hi, I'm Atlas</p>
            <p className="chat-empty-sub">Say "Hey Atlas" to speak, or type below</p>
          </div>
        ) : (
          messages.map(msg => {
            const isScreenshot = (msg.role as string) === 'tool_screenshot' || msg.content.startsWith('__screenshot__:')
            const screenshotB64 = isScreenshot ? msg.content.replace('__screenshot__:', '') : null

            return (
              <div key={msg.id} className={`msg msg--${isScreenshot ? 'screenshot' : msg.role}`}>
                <div className="msg-bubble-wrap">
                  <div className="msg-bubble">
                    {isScreenshot && screenshotB64 ? (
                      <img
                        src={`data:image/jpeg;base64,${screenshotB64}`}
                        alt="Browser screenshot"
                        style={{ maxWidth: '100%', borderRadius: '8px', display: 'block' }}
                      />
                    ) : msg.role === 'assistant' && isProcessing && msg === messages[messages.length - 1] ? (
                      <Loader variant="typing" size="sm" />
                    ) : msg.role === 'assistant' ? (
                      formatMessage(msg.content)
                    ) : (
                      msg.content
                    )}
                  </div>

                  {/* Copy button for assistant messages */}
                  {msg.role === 'assistant' && !isScreenshot && msg.content && (
                    <button
                      className={`msg-copy ${copiedId === msg.id ? 'msg-copy--done' : ''}`}
                      onClick={() => copyMessage(msg.id, msg.content)}
                      title="Copy message"
                    >
                      {copiedId === msg.id ? (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <polyline points="20 6 9 17 4 12"/>
                        </svg>
                      ) : (
                        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                          <rect x="9" y="9" width="13" height="13" rx="2" ry="2"/>
                          <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>
                        </svg>
                      )}
                    </button>
                  )}
                </div>

                <div className="msg-time">
                  {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </div>
              </div>
            )
          })
        )}

        {/* Inline "thinking" indicator when processing with no pending bubble yet */}
        {isProcessing && (messages.length === 0 || messages[messages.length - 1]?.role === 'user') && (
          <div className="msg msg--assistant">
            <div className="msg-bubble msg-bubble--thinking">
              <Loader variant="typing" size="sm" />
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Scroll-to-bottom button */}
      {showScrollBtn && (
        <button className="scroll-to-bottom" onClick={scrollToBottom} title="Scroll to bottom">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <polyline points="6 9 12 15 18 9"/>
          </svg>
        </button>
      )}

      {/* ── Input area ────────────────────────────────────────────────────── */}
      <div className="chat-input-area">
        <div className="chat-input-row">
          {/* Mic button — push-to-talk */}
          <button
            className={`mic-btn ${isRecording ? 'mic-btn--recording' : isProcessing ? 'mic-btn--processing' : ''}`}
            onClick={isRecording ? onMicStop : onMicClick}
            title={isRecording ? 'Stop recording' : isProcessing ? 'Processing…' : 'Click to speak'}
            disabled={isProcessing}
          >
            {isRecording && <span className="mic-pulse-ring" />}
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 1a3 3 0 0 0-3 3v8a3 3 0 0 0 6 0V4a3 3 0 0 0-3-3z"/>
              <path d="M19 10v2a7 7 0 0 1-14 0v-2"/>
              <line x1="12" y1="19" x2="12" y2="23"/>
              <line x1="8" y1="23" x2="16" y2="23"/>
            </svg>
          </button>

          <PromptInput
            placeholder={isRecording ? 'Recording…' : isProcessing ? 'Processing…' : 'Ask Atlas anything…'}
            onSubmit={onSendMessage}
            disabled={isRecording || isProcessing}
            glowIntensity={0.55}
          />
        </div>

        {/* Voice status chip — shows recording / processing state */}
        {(isRecording || isProcessing) && (
          <div className="voice-chip">
            {isRecording  && <><span className="chip-dot chip-dot--red"  />Recording…</>}
            {isProcessing && <><span className="chip-dot chip-dot--yellow"/>Processing…</>}
          </div>
        )}
      </div>
    </div>
  )
}
