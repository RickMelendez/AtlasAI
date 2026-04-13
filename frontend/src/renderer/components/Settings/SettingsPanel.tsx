/**
 * SettingsPanel Component — Configuration form
 */

import React, { useState, useEffect, useCallback } from 'react'
import { X } from 'lucide-react'
import './SettingsPanel.css'

export interface SettingsValues {
  anthropic_api_key: string
  elevenlabs_api_key: string
  elevenlabs_voice_id: string
  notion_api_key: string
  tts_provider?: string
}

export interface SettingsPanelProps {
  onClose: () => void
  onSave: () => void
}

export const SettingsPanel: React.FC<SettingsPanelProps> = ({ onClose, onSave }) => {
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [values, setValues] = useState<SettingsValues>({
    anthropic_api_key: '',
    elevenlabs_api_key: '',
    elevenlabs_voice_id: '',
    notion_api_key: '',
    tts_provider: 'elevenlabs',
  })
  const [error, setError] = useState<string | null>(null)

  // Fetch settings on mount
  useEffect(() => {
    const fetchSettings = async () => {
      try {
        setLoading(true)
        const response = await fetch('/api/settings')
        if (!response.ok) throw new Error('Failed to fetch settings')
        const data: SettingsValues = await response.json()
        setValues(data)
        setError(null)
      } catch (err) {
        console.error('[SettingsPanel] Error fetching settings:', err)
        setError('Failed to load settings')
      } finally {
        setLoading(false)
      }
    }

    fetchSettings()
  }, [])

  const handleChange = useCallback((field: keyof SettingsValues, value: string) => {
    setValues(prev => ({ ...prev, [field]: value }))
  }, [])

  const handleSave = useCallback(async () => {
    try {
      setSaving(true)
      setError(null)

      const response = await fetch('/api/settings', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(values),
      })

      if (!response.ok) throw new Error('Failed to save settings')

      onSave()
    } catch (err) {
      console.error('[SettingsPanel] Error saving settings:', err)
      setError('Failed to save settings')
    } finally {
      setSaving(false)
    }
  }, [values, onSave])

  const maskApiKey = (key: string): string => {
    if (!key || key.length < 8) return key
    return `${key.slice(0, 8)}...`
  }

  if (loading) {
    return (
      <div className="settings-panel">
        <div className="settings-header">
          <h2 className="settings-title">Settings</h2>
          <button className="settings-close" onClick={onClose} title="Close">
            <X size={18} />
          </button>
        </div>
        <div className="settings-loading">Loading settings...</div>
      </div>
    )
  }

  return (
    <div className="settings-panel">
      {/* Header */}
      <div className="settings-header">
        <h2 className="settings-title">Settings</h2>
        <button className="settings-close" onClick={onClose} title="Close">
          <X size={18} />
        </button>
      </div>

      {/* Content */}
      <div className="settings-content">
        {error && <div className="settings-error">{error}</div>}

        {/* AI Keys Section */}
        <div className="settings-section">
          <h3 className="settings-section-title">AI Keys</h3>

          <div className="form-group">
            <label htmlFor="anthropic_key" className="form-label">Anthropic API Key</label>
            <input
              id="anthropic_key"
              type="password"
              className="form-input"
              value={values.anthropic_api_key}
              onChange={e => handleChange('anthropic_api_key', e.target.value)}
              placeholder="sk-ant-..."
            />
            {values.anthropic_api_key && (
              <div className="form-hint">{maskApiKey(values.anthropic_api_key)}</div>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="elevenlabs_key" className="form-label">ElevenLabs API Key</label>
            <input
              id="elevenlabs_key"
              type="password"
              className="form-input"
              value={values.elevenlabs_api_key}
              onChange={e => handleChange('elevenlabs_api_key', e.target.value)}
              placeholder="sk-..."
            />
            {values.elevenlabs_api_key && (
              <div className="form-hint">{maskApiKey(values.elevenlabs_api_key)}</div>
            )}
          </div>

          <div className="form-group">
            <label htmlFor="elevenlabs_voice" className="form-label">ElevenLabs Voice ID</label>
            <input
              id="elevenlabs_voice"
              type="text"
              className="form-input"
              value={values.elevenlabs_voice_id}
              onChange={e => handleChange('elevenlabs_voice_id', e.target.value)}
              placeholder="e.g., 21m00Tcm4TlvDq8ikWAM"
            />
          </div>
        </div>

        {/* Integrations Section */}
        <div className="settings-section">
          <h3 className="settings-section-title">Integrations</h3>

          <div className="form-group">
            <label htmlFor="notion_key" className="form-label">Notion API Key</label>
            <input
              id="notion_key"
              type="password"
              className="form-input"
              value={values.notion_api_key}
              onChange={e => handleChange('notion_api_key', e.target.value)}
              placeholder="ntn_..."
            />
            {values.notion_api_key && (
              <div className="form-hint">{maskApiKey(values.notion_api_key)}</div>
            )}
          </div>
        </div>

        {/* Voice Section */}
        <div className="settings-section">
          <h3 className="settings-section-title">Voice</h3>

          <div className="form-group">
            <label htmlFor="tts_provider" className="form-label">TTS Provider</label>
            <select
              id="tts_provider"
              className="form-input"
              value={values.tts_provider || 'elevenlabs'}
              onChange={e => handleChange('tts_provider', e.target.value)}
            >
              <option value="elevenlabs">ElevenLabs</option>
              <option value="edge-tts">Edge TTS</option>
            </select>
          </div>
        </div>
      </div>

      {/* Footer */}
      <div className="settings-footer">
        <button
          className="btn btn-secondary"
          onClick={onClose}
          disabled={saving}
        >
          Cancel
        </button>
        <button
          className="btn btn-primary"
          onClick={handleSave}
          disabled={saving}
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  )
}
