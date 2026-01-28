import { useEffect, useState } from 'react'
import { getConfig, updateConfig, listPresets, deletePreset, updatePreset } from '../api/client'
import type { Config, Preset } from '../api/types'

export default function Settings() {
  const [config, setConfig] = useState<Config | null>(null)
  const [presets, setPresets] = useState<Preset[]>([])
  const [loading, setLoading] = useState(true)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [editingPreset, setEditingPreset] = useState<Preset | null>(null)
  const [editName, setEditName] = useState('')

  useEffect(() => {
    Promise.all([getConfig(), listPresets()])
      .then(([cfg, pres]) => {
        setConfig(cfg)
        setPresets(pres)
      })
      .catch(console.error)
      .finally(() => setLoading(false))
  }, [])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value, type } = e.target
    setConfig((prev) => {
      if (!prev) return prev
      return {
        ...prev,
        [name]: type === 'number' ? parseFloat(value) : value,
      }
    })
    setSaved(false)
  }

  const handleSave = async () => {
    if (!config) return
    setSaving(true)
    try {
      await updateConfig(config)
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    } catch (error) {
      console.error('Failed to save config:', error)
    } finally {
      setSaving(false)
    }
  }

  const handleDeletePreset = async (id: string) => {
    if (!confirm('Delete this preset?')) return
    try {
      await deletePreset(id)
      setPresets((prev) => prev.filter((p) => p.id !== id))
    } catch (error) {
      console.error('Failed to delete preset:', error)
    }
  }

  const handleEditPreset = (preset: Preset) => {
    setEditingPreset(preset)
    setEditName(preset.name)
  }

  const handleSavePresetEdit = async () => {
    if (!editingPreset || !editName.trim()) return
    try {
      const updated = await updatePreset(editingPreset.id, { name: editName.trim() })
      setPresets((prev) => prev.map((p) => (p.id === updated.id ? updated : p)))
      setEditingPreset(null)
      setEditName('')
    } catch (error) {
      console.error('Failed to update preset:', error)
    }
  }

  const handleCancelEdit = () => {
    setEditingPreset(null)
    setEditName('')
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading...</div>
      </div>
    )
  }

  if (!config) {
    return (
      <div className="text-red-500">Failed to load configuration</div>
    )
  }

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Settings</h1>
        <p className="mt-1 text-gray-600">Configure default values and preferences</p>
      </div>

      {/* General Settings */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">General</h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Default Camera
            </label>
            <input
              type="text"
              name="default_camera"
              value={config.default_camera || ''}
              onChange={handleChange}
              placeholder="e.g., TapoC560WS"
              className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Frigate Base URL
            </label>
            <input
              type="url"
              name="default_base_url"
              value={config.default_base_url}
              onChange={handleChange}
              className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Recordings Path
            </label>
            <input
              type="text"
              name="default_recordings_path"
              value={config.default_recordings_path}
              onChange={handleChange}
              className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Default Encoder
            </label>
            <select
              name="default_encoder"
              value={config.default_encoder}
              onChange={handleChange}
              className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
            >
              <option value="hevc_nvenc">HEVC (NVENC)</option>
              <option value="h264_nvenc">H.264 (NVENC)</option>
              <option value="libx265">HEVC (Software)</option>
              <option value="libx264">H.264 (Software)</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Timezone
            </label>
            <input
              type="text"
              name="timezone"
              value={config.timezone}
              onChange={handleChange}
              placeholder="e.g., America/New_York"
              className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
            />
          </div>
        </div>
      </div>

      {/* Location Settings */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Location (for dawn/dusk calculation)</h2>
        <div className="grid grid-cols-2 gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Latitude
            </label>
            <input
              type="number"
              name="latitude"
              value={config.latitude}
              onChange={handleChange}
              step="0.0001"
              className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Longitude
            </label>
            <input
              type="number"
              name="longitude"
              value={config.longitude}
              onChange={handleChange}
              step="0.0001"
              className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
            />
          </div>
        </div>
      </div>

      {/* Presets */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Saved Presets</h2>
        {presets.length === 0 ? (
          <p className="text-gray-500">No presets saved. Create one from the New Job page.</p>
        ) : (
          <div className="space-y-3">
            {presets.map((preset) => (
              <div
                key={preset.id}
                className="flex items-center justify-between p-4 bg-gray-50 rounded-lg"
              >
                {editingPreset?.id === preset.id ? (
                  // Edit mode
                  <div className="flex-1 flex items-center gap-2">
                    <input
                      type="text"
                      value={editName}
                      onChange={(e) => setEditName(e.target.value)}
                      className="flex-1 rounded-lg border-gray-300 text-sm focus:border-frigate-500 focus:ring-frigate-500"
                      autoFocus
                    />
                    <button
                      onClick={handleSavePresetEdit}
                      disabled={!editName.trim()}
                      className="px-3 py-1.5 text-sm font-medium text-white bg-frigate-600 rounded-lg hover:bg-frigate-700 disabled:opacity-50"
                    >
                      Save
                    </button>
                    <button
                      onClick={handleCancelEdit}
                      className="px-3 py-1.5 text-sm font-medium text-gray-600 hover:text-gray-700"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  // View mode
                  <>
                    <div>
                      <h3 className="font-medium text-gray-900">{preset.name}</h3>
                      <p className="text-sm text-gray-500">
                        {preset.type} • {preset.camera || 'Any camera'}
                      </p>
                    </div>
                    <div className="flex items-center gap-3">
                      <button
                        onClick={() => handleEditPreset(preset)}
                        className="text-sm font-medium text-frigate-600 hover:text-frigate-700"
                      >
                        Edit
                      </button>
                      <button
                        onClick={() => handleDeletePreset(preset.id)}
                        className="text-sm font-medium text-red-600 hover:text-red-700"
                      >
                        Delete
                      </button>
                    </div>
                  </>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Save Button */}
      <div className="flex items-center justify-end gap-4">
        {saved && (
          <span className="text-green-600 text-sm flex items-center">
            <svg className="w-5 h-5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
            </svg>
            Settings saved
          </span>
        )}
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-6 py-2 text-sm font-medium text-white bg-frigate-600 rounded-lg hover:bg-frigate-700 disabled:opacity-50"
        >
          {saving ? 'Saving...' : 'Save Settings'}
        </button>
      </div>
    </div>
  )
}
