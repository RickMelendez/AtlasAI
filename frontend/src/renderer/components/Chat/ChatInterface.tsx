/**
 * ChatInterface — Atlas AI
 * Clean transcript feed. No bubbles, no mic button.
 * Atlas messages: left accent bar + monospace text.
 * User messages: right-aligned, italic, muted.
 */

import React, { useEffect, useRef, useState, useCallback } from 'react'
import type { AudioCaptureMode } from '../../hooks/useAudioCapture'
import { Loader }  from '../ui/loader'
import PromptInput from '../ui/prompt-input-dynamic-grow'
import './ChatInterface.css'

// ── Types ──────────────────────────────────────────────────────────────────────

export interface Message {
  id:        string
  content:   string
  role:      'user' | 'assistant'
  timestamp: Date
}

export interface ChatInterfaceProps {
  messages?:      Message[]
  onSendMessage?: (message: string) => void
  onClose?:       () => void
  audioMode?:     AudioCaptureMode
}

// ── Markdown helpers ───────────────────────────────────────────────────────────

function formatMessage(content: string): React.ReactNode {
  const parts = content.split(/(```[\s\S]*?```)/g)
  return parts.map((part, i) => {
    if (part.startsWith('```') && part.endsWith('```')) {
      const inner = part.slice(3, -3)
      const newlineIdx = inner.indexOf('\n')
      const lang = newlineIdx > 0 && newlineIdx < 20 && /^[a-zA-Z]+$/.test(inner.slice(0, newlineIdx).trim())
        ? inner.slice(0, newlineIdx).trim()
        : ''
      const code = lang ? inner.slice(newlineIdx + 1) : inner
      return <CodeBlock key={i} code={code} lang={lang} />
    }
    return <span key={i}>{formatInline(part)}</span>
  })
}

function formatInline(text: string): React.ReactNode[] {
  const nodes: React.ReactNode[] = []
  const parts = text.split(/(`[^`]+`)/g)
  parts.forEach((part, i) => {
    if (part.startsWith('`') && part.endsWith('`')) {
      nodes.push(<code key={i} className="msg-inline-code">{part.slice(1, -1)}</code>)
    } else {
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
          {copied ? 'copied' : 'copy'}
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
}) => {
  const messagesEndRef       = useRef<HTMLDivElement>(null)
  const messagesContainerRef = useRef<HTMLDivElement>(null)
  const [showScrollBtn, setShowScrollBtn] = useState(false)
  const [copiedId, setCopiedId]           = useState<string | null>(null)

  useEffect(() => {
    if (!showScrollBtn) {
      messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }
  }, [messages, showScrollBtn])

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

  const copyMessage = useCallback((id: string, text: string) => {
    navigator.clipboard.writeText(text)
    setCopiedId(id)
    setTimeout(() => setCopiedId(null), 1500)
  }, [])

  const isRecording  = audioMode === 'recording'
  const isProcessing = audioMode === 'processing'

  return (
    <div className="chat-panel">
      {/* Close */}
      <button className="chat-close" onClick={onClose} title="Close">
        <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round">
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
            <div className="chat-empty-dots">
              <span /><span /><span />
            </div>
          </div>
        ) : (
          messages.map(msg => {
            const isScreenshot = (msg.role as string) === 'tool_screenshot' || msg.content.startsWith('__screenshot__:')
            const screenshotB64 = isScreenshot ? msg.content.replace('__screenshot__:', '') : null

            if (isScreenshot && screenshotB64) {
              return (
                <div key={msg.id} className="msg msg--assistant">
                  <img
                    src={`data:image/jpeg;base64,${screenshotB64}`}
                    alt="Screenshot"
                    style={{ maxWidth: '100%', borderRadius: '6px', display: 'block' }}
                  />
                </div>
              )
            }

            if (msg.role === 'user') {
              return (
                <div key={msg.id} className="msg msg--user">
                  <div className="msg-text">{msg.content}</div>
                  <div className="msg-time">
                    {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </div>
                </div>
              )
            }

            // Assistant message
            const isThinking = isProcessing && msg === messages[messages.length - 1]
            return (
              <div key={msg.id} className="msg msg--assistant">
                <div className="msg-label">atlas</div>
                <div className="msg-text">
                  {isThinking ? <Loader variant="typing" size="sm" /> : formatMessage(msg.content)}
                </div>
                <div className="msg-time">
                  {msg.timestamp.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </div>
                {!isThinking && msg.content && (
                  <button
                    className={`msg-copy ${copiedId === msg.id ? 'msg-copy--done' : ''}`}
                    onClick={() => copyMessage(msg.id, msg.content)}
                    title="Copy"
                  >
                    {copiedId === msg.id ? (
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round"><polyline points="20 6 9 17 4 12"/></svg>
                    ) : (
                      <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/></svg>
                    )}
                  </button>
                )}
              </div>
            )
          })
        )}

        {/* Thinking indicator when processing with no pending bubble */}
        {isProcessing && (messages.length === 0 || messages[messages.length - 1]?.role === 'user') && (
          <div className="msg-thinking">
            <Loader variant="typing" size="sm" />
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {showScrollBtn && (
        <button className="scroll-to-bottom" onClick={scrollToBottom} title="Scroll to bottom">
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round"><polyline points="6 9 12 15 18 9"/></svg>
        </button>
      )}

      {/* ── Input area ────────────────────────────────────────────────────── */}
      <div className="chat-input-area">
        <div className="chat-input-row">
          <PromptInput
            placeholder={isRecording ? 'Listening…' : isProcessing ? 'Processing…' : 'Ask Atlas anything…'}
            onSubmit={onSendMessage}
            disabled={isRecording || isProcessing}
            glowIntensity={0.45}
          />
        </div>

        {(isRecording || isProcessing) && (
          <div className="voice-chip">
            {isRecording  && <><span className="chip-dot chip-dot--red"  />rec</>}
            {isProcessing && <><span className="chip-dot chip-dot--yellow"/>processing</>}
          </div>
        )}
      </div>
    </div>
  )
}
