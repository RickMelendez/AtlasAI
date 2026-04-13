/**
 * MemoryPanel Component — Display and manage stored memories
 */

import React, { useCallback } from 'react'
import { Trash2 } from 'lucide-react'
import './MemoryPanel.css'

export interface Memory {
  id: number
  content: string
  source: string
  created_at: string
}

export interface MemoryPanelProps {
  memories: Memory[]
  onForgetAll: () => void
  onDeleteMemory: (id: number) => void
}

export const MemoryPanel: React.FC<MemoryPanelProps> = ({
  memories,
  onForgetAll,
  onDeleteMemory,
}) => {
  const handleDeleteClick = useCallback((id: number) => {
    onDeleteMemory(id)
  }, [onDeleteMemory])

  const handleForgetAllClick = useCallback(() => {
    if (confirm('Are you sure you want to forget everything? This cannot be undone.')) {
      onForgetAll()
    }
  }, [onForgetAll])

  const formatDate = (dateStr: string): string => {
    try {
      const date = new Date(dateStr)
      return date.toLocaleDateString([], { month: 'short', day: 'numeric', year: 'numeric' })
    } catch {
      return 'Unknown date'
    }
  }

  return (
    <div className="memory-panel">
      {/* Header */}
      <div className="memory-header">
        <h2 className="memory-title">Memory</h2>
        <button
          className="memory-forget-btn"
          onClick={handleForgetAllClick}
          title="Forget all memories"
        >
          Clear All
        </button>
      </div>

      {/* Content */}
      <div className="memory-content">
        {memories.length === 0 ? (
          <div className="memory-empty">
            <p>No memories yet.</p>
            <p className="memory-empty-hint">Tell Atlas to "remember" something.</p>
          </div>
        ) : (
          <div className="memory-list">
            {memories.map(memory => (
              <div key={memory.id} className="memory-card">
                <div className="memory-card-content">
                  <p className="memory-text">{memory.content}</p>
                  <div className="memory-meta">
                    <span className="memory-date">{formatDate(memory.created_at)}</span>
                    {memory.source && (
                      <span className="memory-source">{memory.source}</span>
                    )}
                  </div>
                </div>
                <button
                  className="memory-delete-btn"
                  onClick={() => handleDeleteClick(memory.id)}
                  title="Delete memory"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
