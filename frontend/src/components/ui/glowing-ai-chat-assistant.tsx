import React, { useEffect, useRef, useState } from 'react'
import { Bot, ChevronDown, Code, Info, Link, Mic, Paperclip, Send, X } from 'lucide-react'

const MODELS = [
  { id: 'gpt-4', label: 'GPT-4', provider: 'openai' },
  { id: 'gpt-4o', label: 'GPT-4o', provider: 'openai' },
  { id: 'claude-3-5-sonnet', label: 'Claude 3.5 Sonnet', provider: 'anthropic' },
  { id: 'claude-3-opus', label: 'Claude 3 Opus', provider: 'anthropic' },
] as const

type ModelId = (typeof MODELS)[number]['id']

const FloatingAiAssistant = () => {
  const [isChatOpen, setIsChatOpen] = useState(false)
  const [message, setMessage] = useState('')
  const [charCount, setCharCount] = useState(0)
  const [selectedModel, setSelectedModel] = useState<ModelId>('gpt-4')
  const [isModelOpen, setIsModelOpen] = useState(false)
  const maxChars = 2000
  const chatRef = useRef<HTMLDivElement | null>(null)
  const modelRef = useRef<HTMLDivElement | null>(null)

  const currentModel = MODELS.find((m) => m.id === selectedModel)!

  const handleInputChange = (e: React.ChangeEvent<HTMLTextAreaElement>) => {
    const value = e.target.value
    setMessage(value)
    setCharCount(value.length)
  }

  const handleSend = () => {
    if (message.trim()) {
      console.log('Sending message:', message)
      setMessage('')
      setCharCount(0)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      const target = event.target
      if (!(target instanceof Element)) return

      if (chatRef.current && !chatRef.current.contains(target)) {
        if (!target.closest('.floating-ai-button')) {
          setIsChatOpen(false)
        }
      }

      if (modelRef.current && !modelRef.current.contains(target)) {
        setIsModelOpen(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => {
      document.removeEventListener('mousedown', handleClickOutside)
    }
  }, [])

  return (
    <div
      className="fixed bottom-6 right-6 z-50"
      onMouseDown={(e) => e.stopPropagation()}
      onMouseMove={(e) => e.stopPropagation()}
      onMouseUp={(e) => e.stopPropagation()}
      onClick={(e) => e.stopPropagation()}
    >
      <button
        className={`floating-ai-button relative flex h-16 w-16 transform items-center justify-center rounded-full transition-all duration-500 ${isChatOpen ? 'rotate-90' : 'rotate-0'
          }`}
        onClick={() => setIsChatOpen(!isChatOpen)}
        style={{
          background: 'linear-gradient(135deg, rgba(99,102,241,0.8) 0%, rgba(168,85,247,0.8) 100%)',
          boxShadow: '0 0 20px rgba(139, 92, 246, 0.7), 0 0 40px rgba(124, 58, 237, 0.5), 0 0 60px rgba(109, 40, 217, 0.3)',
          border: '2px solid rgba(255, 255, 255, 0.2)',
        }}
      >
        <div className="absolute inset-0 rounded-full bg-gradient-to-b from-white/20 to-transparent opacity-30"></div>
        <div className="absolute inset-0 rounded-full border-2 border-white/10"></div>
        <div className="relative z-10">
          {isChatOpen ? <X className="h-8 w-8 text-white" /> : <Bot className="h-8 w-8 text-white" />}
        </div>
        <div className="absolute inset-0 rounded-full bg-indigo-500 opacity-20 animate-ping"></div>
      </button>

      {isChatOpen && (
        <div
          ref={chatRef}
          className="absolute bottom-20 right-0 w-max max-w-[500px] origin-bottom-right transition-all duration-300"
          style={{
            animation: 'floatingAiPopIn 0.3s cubic-bezier(0.175, 0.885, 0.32, 1.275) forwards',
          }}
        >
          <div className="relative flex flex-col overflow-hidden rounded-3xl border border-zinc-500/50 bg-gradient-to-br from-zinc-800/80 to-zinc-900/90 shadow-2xl backdrop-blur-3xl">
            <div className="flex items-center justify-between px-6 pb-2 pt-4">
              <div className="flex items-center gap-1.5">
                <div className="h-2 w-2 animate-pulse rounded-full bg-green-500"></div>
                <span className="text-xs font-medium text-zinc-400">AI Assistant</span>
              </div>
              <div className="flex items-center gap-2">
                {/* Model Selector Dropdown */}
                <div ref={modelRef} className="relative">
                  <button
                    onClick={() => setIsModelOpen((o) => !o)}
                    className="flex items-center gap-1 rounded-2xl bg-zinc-800/60 px-2.5 py-1 text-xs font-medium text-zinc-300 transition-colors hover:bg-zinc-700/60"
                  >
                    <span
                      className={`h-1.5 w-1.5 rounded-full ${currentModel.provider === 'openai' ? 'bg-indigo-400' : 'bg-amber-400'
                        }`}
                    />
                    {currentModel.label}
                    <ChevronDown
                      className={`h-3 w-3 text-zinc-500 transition-transform duration-200 ${isModelOpen ? 'rotate-180' : ''
                        }`}
                    />
                  </button>

                  {isModelOpen && (
                    <div className="absolute right-0 top-full z-50 mt-1.5 min-w-[180px] overflow-hidden rounded-xl border border-zinc-700/50 bg-zinc-900/95 py-1 shadow-xl backdrop-blur-sm">
                      {(['openai', 'anthropic'] as const).map((provider) => (
                        <div key={provider}>
                          <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-widest text-zinc-600">
                            {provider === 'openai' ? 'OpenAI' : 'Anthropic'}
                          </div>
                          {MODELS.filter((m) => m.provider === provider).map((model) => (
                            <button
                              key={model.id}
                              onClick={() => {
                                setSelectedModel(model.id)
                                setIsModelOpen(false)
                              }}
                              className={`flex w-full items-center gap-2 px-3 py-2 text-xs transition-colors hover:bg-zinc-800/80 ${selectedModel === model.id ? 'text-zinc-100' : 'text-zinc-400'
                                }`}
                            >
                              <span
                                className={`h-1.5 w-1.5 rounded-full ${model.provider === 'openai' ? 'bg-indigo-400' : 'bg-amber-400'
                                  } ${selectedModel === model.id ? 'opacity-100' : 'opacity-40'
                                  }`}
                              />
                              {model.label}
                              {selectedModel === model.id && (
                                <span className="ml-auto text-indigo-400">✓</span>
                              )}
                            </button>
                          ))}
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                <span className="rounded-2xl border border-red-500/20 bg-red-500/10 px-2 py-1 text-xs font-medium text-red-400">Pro</span>
                <button
                  onClick={() => setIsChatOpen(false)}
                  className="rounded-full p-1.5 transition-colors hover:bg-zinc-700/50"
                >
                  <X className="h-4 w-4 text-zinc-400" />
                </button>
              </div>
            </div>

            <div className="relative overflow-hidden">
              <textarea
                value={message}
                onChange={handleInputChange}
                onKeyDown={handleKeyDown}
                rows={4}
                className="min-h-[120px] w-full resize-none border-none bg-transparent px-6 py-4 text-base font-normal leading-relaxed text-zinc-100 outline-none placeholder-zinc-500"
                placeholder="What would you like to explore today? Ask anything, share ideas, or request assistance..."
                style={{ scrollbarWidth: 'none', msOverflowStyle: 'none' }}
              />
              <div
                className="pointer-events-none absolute inset-0 bg-gradient-to-t from-zinc-800/5 to-transparent"
                style={{ background: 'linear-gradient(to top, rgba(39, 39, 42, 0.05), transparent)' }}
              ></div>
            </div>

            <div className="px-4 pb-4">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2">
                  <div className="flex items-center gap-1.5 rounded-xl border border-zinc-700/50 bg-zinc-800/40 p-1">
                    <button className="group relative transform cursor-pointer rounded-lg border-none bg-transparent p-2.5 text-zinc-500 transition-all duration-300 hover:-rotate-3 hover:scale-105 hover:bg-zinc-800/80 hover:text-zinc-200">
                      <Paperclip className="h-4 w-4 transition-all duration-300 group-hover:scale-125 group-hover:-rotate-12" />
                      <div className="pointer-events-none absolute -top-10 left-1/2 -translate-x-1/2 transform whitespace-nowrap rounded-lg border border-zinc-700/50 bg-zinc-900/95 px-3 py-2 text-xs text-zinc-200 opacity-0 shadow-lg backdrop-blur-sm transition-all duration-300 group-hover:-translate-y-1 group-hover:opacity-100">
                        Upload files
                        <div className="absolute left-1/2 top-full h-0 w-0 -translate-x-1/2 transform border-l-4 border-r-4 border-t-4 border-transparent border-t-zinc-900/95"></div>
                      </div>
                    </button>

                    <button className="group relative transform cursor-pointer rounded-lg border-none bg-transparent p-2.5 text-zinc-500 transition-all duration-300 hover:rotate-6 hover:scale-105 hover:bg-zinc-800/80 hover:text-red-400">
                      <Link className="h-4 w-4 transition-all duration-300 group-hover:scale-125 group-hover:rotate-12" />
                      <div className="pointer-events-none absolute -top-10 left-1/2 -translate-x-1/2 transform whitespace-nowrap rounded-lg border border-zinc-700/50 bg-zinc-900/95 px-3 py-2 text-xs text-zinc-200 opacity-0 shadow-lg backdrop-blur-sm transition-all duration-300 group-hover:-translate-y-1 group-hover:opacity-100">
                        Web link
                        <div className="absolute left-1/2 top-full h-0 w-0 -translate-x-1/2 transform border-l-4 border-r-4 border-t-4 border-transparent border-t-zinc-900/95"></div>
                      </div>
                    </button>

                    <button className="group relative transform cursor-pointer rounded-lg border-none bg-transparent p-2.5 text-zinc-500 transition-all duration-300 hover:rotate-3 hover:scale-105 hover:bg-zinc-800/80 hover:text-green-400">
                      <Code className="h-4 w-4 transition-all duration-300 group-hover:scale-125 group-hover:-rotate-6" />
                      <div className="pointer-events-none absolute -top-10 left-1/2 -translate-x-1/2 transform whitespace-nowrap rounded-lg border border-zinc-700/50 bg-zinc-900/95 px-3 py-2 text-xs text-zinc-200 opacity-0 shadow-lg backdrop-blur-sm transition-all duration-300 group-hover:-translate-y-1 group-hover:opacity-100">
                        Code repo
                        <div className="absolute left-1/2 top-full h-0 w-0 -translate-x-1/2 transform border-l-4 border-r-4 border-t-4 border-transparent border-t-zinc-900/95"></div>
                      </div>
                    </button>

                    <button className="group relative transform cursor-pointer rounded-lg border-none bg-transparent p-2.5 text-zinc-500 transition-all duration-300 hover:-rotate-6 hover:scale-105 hover:bg-zinc-800/80 hover:text-purple-400">
                      <svg className="h-4 w-4 transition-all duration-300 group-hover:scale-125 group-hover:rotate-12" viewBox="0 0 24 24" fill="currentColor">
                        <path d="M15.852 8.981h-4.588V0h4.588c2.476 0 4.49 2.014 4.49 4.49s-2.014 4.491-4.49 4.491zM12.735 7.51h3.117c1.665 0 3.019-1.355 3.019-3.019s-1.354-3.019-3.019-3.019h-3.117V7.51zm0 1.471H8.148c-2.476 0-4.49-2.015-4.49-4.49S5.672 0 8.148 0h4.588v8.981zm-4.587-7.51c-1.665 0-3.019 1.355-3.019 3.019s1.354 3.02 3.019 3.02h3.117V1.471H8.148zm4.587 15.019H8.148c-2.476 0-4.49-2.014-4.49-4.49s2.014-4.49 4.49-4.49h4.588v8.98zM8.148 8.981c-1.665 0-3.019 1.355-3.019 3.019s1.355 3.019 3.019 3.019h3.117v-6.038H8.148zm7.704 0c-2.476 0-4.49 2.015-4.49 4.49s2.014 4.49 4.49 4.49 4.49-2.015 4.49-4.49-2.014-4.49-4.49-4.49zm0 7.509c-1.665 0-3.019-1.355-3.019-3.019s1.355-3.019 3.019-3.019 3.019 1.354 3.019 3.019-1.354 3.019-3.019 3.019zM8.148 24c-2.476 0-4.49-2.015-4.49-4.49s2.014-4.49 4.49-4.49h4.588V24H8.148zm3.117-1.471V16.49H8.148c-1.665 0-3.019 1.355-3.019 3.019s1.355 3.02 3.019 3.02h3.117z"></path>
                      </svg>
                      <div className="pointer-events-none absolute -top-10 left-1/2 -translate-x-1/2 transform whitespace-nowrap rounded-lg border border-zinc-700/50 bg-zinc-900/95 px-3 py-2 text-xs text-zinc-200 opacity-0 shadow-lg backdrop-blur-sm transition-all duration-300 group-hover:-translate-y-1 group-hover:opacity-100">
                        Design file
                        <div className="absolute left-1/2 top-full h-0 w-0 -translate-x-1/2 transform border-l-4 border-r-4 border-t-4 border-transparent border-t-zinc-900/95"></div>
                      </div>
                    </button>
                  </div>

                  <button className="group relative transform cursor-pointer rounded-lg border border-zinc-700/30 bg-transparent p-2.5 text-zinc-500 transition-all duration-300 hover:rotate-2 hover:scale-110 hover:border-red-500/30 hover:bg-zinc-800/80 hover:text-red-400">
                    <Mic className="h-4 w-4 transition-all duration-300 group-hover:scale-125 group-hover:-rotate-3" />
                    <div className="pointer-events-none absolute -top-10 left-1/2 -translate-x-1/2 transform whitespace-nowrap rounded-lg border border-zinc-700/50 bg-zinc-900/95 px-3 py-2 text-xs text-zinc-200 opacity-0 shadow-lg backdrop-blur-sm transition-all duration-300 group-hover:-translate-y-1 group-hover:opacity-100">
                      Voice input
                      <div className="absolute left-1/2 top-full h-0 w-0 -translate-x-1/2 transform border-l-4 border-r-4 border-t-4 border-transparent border-t-zinc-900/95"></div>
                    </div>
                  </button>
                </div>

                <div className="flex items-center gap-3">
                  <div className="text-xs font-medium text-zinc-500">
                    <span>{charCount}</span>/<span className="text-zinc-400">{maxChars}</span>
                  </div>

                  <button
                    onClick={handleSend}
                    className="group relative transform cursor-pointer rounded-xl border-none bg-gradient-to-r from-red-600 to-red-500 p-3 text-white shadow-lg transition-all duration-300 hover:-rotate-2 hover:scale-110 hover:animate-pulse hover:from-red-500 hover:to-red-400 hover:shadow-xl hover:shadow-red-500/30 active:scale-95"
                    style={{
                      boxShadow: '0 10px 15px -3px rgba(0, 0, 0, 0.1), 0 0 0 0 rgba(239, 68, 68, 0.4)',
                      animation: 'none',
                    }}
                    onMouseEnter={(e) => {
                      e.currentTarget.style.animation = 'floatingAiPing 1s cubic-bezier(0, 0, 0.2, 1) infinite'
                    }}
                    onMouseLeave={(e) => {
                      e.currentTarget.style.animation = 'none'
                    }}
                  >
                    <Send className="h-5 w-5 transition-all duration-300 group-hover:-translate-y-1 group-hover:translate-x-1 group-hover:rotate-12 group-hover:scale-110" />
                    <div className="absolute inset-0 scale-110 transform rounded-xl bg-gradient-to-r from-red-600 to-red-500 opacity-0 blur-lg transition-opacity duration-300 group-hover:opacity-50"></div>
                    <div className="absolute inset-0 overflow-hidden rounded-xl">
                      <div className="absolute inset-0 scale-0 transform rounded-xl bg-white/20 transition-transform duration-200 group-active:scale-100"></div>
                    </div>
                  </button>
                </div>
              </div>

              <div className="mt-3 flex items-center justify-between gap-6 border-t border-zinc-800/50 pt-3 text-xs text-zinc-500">
                <div className="flex items-center gap-2">
                  <Info className="h-3 w-3" />
                  <span>
                    Press <kbd className="rounded border border-zinc-600 bg-zinc-800 px-1.5 py-1 font-mono text-xs text-zinc-400 shadow-sm">Shift + Enter</kbd> for new line
                  </span>
                </div>

                <div className="flex items-center gap-1">
                  <div className="h-1.5 w-1.5 rounded-full bg-green-500"></div>
                  <span>All systems operational</span>
                </div>
              </div>
            </div>

            <div
              className="pointer-events-none absolute inset-0 rounded-3xl"
              style={{
                background: 'linear-gradient(135deg, rgba(239, 68, 68, 0.05), transparent, rgba(147, 51, 234, 0.05))',
              }}
            ></div>
          </div>
        </div>
      )}

      <style>
        {`
          @keyframes floatingAiPopIn {
            0% {
              opacity: 0;
              transform: scale(0.8) translateY(20px);
            }
            100% {
              opacity: 1;
              transform: scale(1) translateY(0);
            }
          }

          @keyframes floatingAiPing {
            75%, 100% {
              transform: scale(1.1);
              opacity: 0;
            }
          }

          .floating-ai-button:hover {
            transform: scale(1.1) rotate(5deg);
            box-shadow: 0 0 30px rgba(139, 92, 246, 0.9), 0 0 50px rgba(124, 58, 237, 0.7), 0 0 70px rgba(109, 40, 217, 0.5);
          }
        `}
      </style>
    </div>
  )
}

export { FloatingAiAssistant }
