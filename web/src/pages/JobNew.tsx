import { useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { createJob, listCameras, getConfig, listPresets, createPreset, getJobCloneData } from '../api/client'
import type { JobType, Preset } from '../api/types'

type FormData = {
  type: JobType
  camera: string
  // Common
  base_url: string
  recordings_path: string
  recordings_path_fallback: string
  dawntodusk: boolean
  dusktodawn: boolean
  date: string
  start_date: string
  end_date: string
  days: string
  start_time: string
  end_time: string
  // Montage
  encoder: string
  source: string
  pre_pad: string
  post_pad: string
  merge_gap: string
  labels_include: string
  labels_exclude: string
  min_score: string
  timelapse: string
  encode: boolean
  copy_only: boolean
  all_motion: boolean
  min_motion: string
  // Timelapse
  timelapse_speed: string
  frame_sample: string
  sample_interval: string
  fps: string
  scale: string
  cuda: boolean
  dawn_offset: string
  dusk_offset: string
  cq: string
  crf: string
  // Motion playlist
  limit: string
}

const defaultFormData: FormData = {
  type: 'montage',
  camera: '',
  base_url: 'http://127.0.0.1:5000',
  recordings_path: '',
  recordings_path_fallback: '',
  dawntodusk: true,
  dusktodawn: false,
  date: '',
  start_date: '',
  end_date: '',
  days: '',
  start_time: '',
  end_time: '',
  encoder: 'hevc_nvenc',
  source: 'disk',
  pre_pad: '5',
  post_pad: '5',
  merge_gap: '15',
  labels_include: '',
  labels_exclude: '',
  min_score: '',
  timelapse: '',
  encode: false,
  copy_only: true,
  all_motion: false,
  min_motion: '',
  timelapse_speed: '50',
  frame_sample: '',
  sample_interval: '60',
  fps: '20',
  scale: '',
  cuda: false,
  dawn_offset: '0',
  dusk_offset: '0',
  cq: '',
  crf: '',
  limit: '500',
}

export default function JobNew() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const [formData, setFormData] = useState<FormData>(defaultFormData)
  const [cameras, setCameras] = useState<string[]>([])
  const [presets, setPresets] = useState<Preset[]>([])
  const [submitting, setSubmitting] = useState(false)
  const [savingPreset, setSavingPreset] = useState(false)
  const [presetName, setPresetName] = useState('')
  const [showSavePreset, setShowSavePreset] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [showAdvanced, setShowAdvanced] = useState(false)

  // Get yesterday's date as default
  const yesterday = new Date()
  yesterday.setDate(yesterday.getDate() - 1)
  const yesterdayStr = yesterday.toISOString().split('T')[0]

  useEffect(() => {
    // Load cameras and config
    Promise.all([listCameras(), getConfig(), listPresets()])
      .then(([cams, cfg, pres]) => {
        setCameras(cams)
        setPresets(pres)

        // Apply config defaults
        setFormData((prev) => ({
          ...prev,
          base_url: cfg.default_base_url || prev.base_url,
          recordings_path: cfg.default_recordings_path || prev.recordings_path,
          encoder: cfg.default_encoder || prev.encoder,
          camera: cfg.default_camera || (cams.length > 0 ? cams[0] : ''),
          date: yesterdayStr,
        }))
      })
      .catch(console.error)

    // Check for type in URL params
    const typeParam = searchParams.get('type')
    if (typeParam && ['montage', 'timelapse', 'motion_playlist'].includes(typeParam)) {
      setFormData((prev) => ({ ...prev, type: typeParam as JobType }))
    }

    // Check for clone parameter - load job data to clone
    const cloneId = searchParams.get('clone')
    if (cloneId) {
      getJobCloneData(cloneId)
        .then((data) => {
          const args = data.arguments as Record<string, unknown>
          setFormData((prev) => ({
            ...prev,
            type: data.type as JobType,
            camera: data.camera,
            base_url: String(args.base_url || prev.base_url),
            recordings_path: String(args.recordings_path || prev.recordings_path),
            recordings_path_fallback: Array.isArray(args.recordings_path_fallback)
              ? args.recordings_path_fallback.join('\n')
              : '',
            dawntodusk: Boolean(args.dawntodusk),
            dusktodawn: Boolean(args.dusktodawn),
            date: String(args.date || ''),
            start_date: String(args.start_date || ''),
            end_date: String(args.end_date || ''),
            days: args.days ? String(args.days) : '',
            start_time: String(args.start_time || ''),
            end_time: String(args.end_time || ''),
            encoder: String(args.encoder || prev.encoder),
            source: String(args.source || prev.source),
            pre_pad: args.pre_pad ? String(args.pre_pad) : prev.pre_pad,
            post_pad: args.post_pad ? String(args.post_pad) : prev.post_pad,
            merge_gap: args.merge_gap ? String(args.merge_gap) : prev.merge_gap,
            labels_include: String(args.labels_include || ''),
            labels_exclude: String(args.labels_exclude || ''),
            min_score: args.min_score ? String(args.min_score) : '',
            timelapse: args.timelapse ? String(args.timelapse) : '',
            encode: Boolean(args.encode),
            copy_only: !Boolean(args.encode),
            all_motion: Boolean(args.all_motion),
            min_motion: args.min_motion ? String(args.min_motion) : '',
            timelapse_speed: args.timelapse ? String(args.timelapse) : prev.timelapse_speed,
            sample_interval: args.sample_interval ? String(args.sample_interval) : prev.sample_interval,
            frame_sample: args.frame_sample ? String(args.frame_sample) : '',
            fps: args.fps ? String(args.fps) : prev.fps,
            scale: String(args.scale || ''),
            cuda: Boolean(args.cuda),
            dawn_offset: args.dawn_offset ? String(args.dawn_offset) : '0',
            dusk_offset: args.dusk_offset ? String(args.dusk_offset) : '0',
            cq: args.cq ? String(args.cq) : '',
            crf: args.crf ? String(args.crf) : '',
            limit: args.limit ? String(args.limit) : prev.limit,
          }))
          // Expand advanced options when cloning
          setShowAdvanced(true)
        })
        .catch(console.error)
    }
  }, [searchParams, yesterdayStr])

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>
  ) => {
    const { name, value, type } = e.target
    setFormData((prev) => ({
      ...prev,
      [name]: type === 'checkbox' ? (e.target as HTMLInputElement).checked : value,
    }))
  }

  const handleTimeWindowChange = (mode: 'dawntodusk' | 'dusktodawn' | 'custom') => {
    setFormData((prev) => ({
      ...prev,
      dawntodusk: mode === 'dawntodusk',
      dusktodawn: mode === 'dusktodawn',
    }))
  }

  const loadPreset = (preset: Preset) => {
    setFormData((prev) => ({
      ...prev,
      type: preset.type,
      camera: preset.camera || prev.camera,
      ...Object.fromEntries(
        Object.entries(preset.arguments).map(([k, v]) => [k, String(v)])
      ),
    }))
  }

  const handleSavePreset = async () => {
    if (!presetName.trim()) return
    setSavingPreset(true)

    try {
      const args: Record<string, unknown> = {
        base_url: formData.base_url,
        recordings_path: formData.recordings_path || undefined,
        recordings_path_fallback: formData.recordings_path_fallback
          ? formData.recordings_path_fallback.split('\n').filter((p) => p.trim())
          : undefined,
        dawntodusk: formData.dawntodusk || undefined,
        dusktodawn: formData.dusktodawn || undefined,
        encoder: formData.encoder,
        source: formData.source,
      }

      if (formData.type === 'montage') {
        args.pre_pad = parseInt(formData.pre_pad)
        args.post_pad = parseInt(formData.post_pad)
        args.merge_gap = parseInt(formData.merge_gap)
        if (formData.labels_include) args.labels_include = formData.labels_include
      } else if (formData.type === 'timelapse') {
        args.timelapse = parseFloat(formData.timelapse_speed)
        args.sample_interval = formData.sample_interval ? parseFloat(formData.sample_interval) : undefined
        args.fps = parseInt(formData.fps)
        if (formData.scale) args.scale = formData.scale
        args.cuda = formData.cuda || undefined
      }

      const newPreset = await createPreset({
        name: presetName.trim(),
        type: formData.type,
        camera: formData.camera || null,
        arguments: args,
      })

      setPresets((prev) => [...prev, newPreset])
      setPresetName('')
      setShowSavePreset(false)
    } catch (err) {
      console.error('Failed to save preset:', err)
    } finally {
      setSavingPreset(false)
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    setSubmitting(true)
    setError(null)

    try {
      const args: Record<string, unknown> = {
        base_url: formData.base_url,
        progress: true,
      }

      // Recordings paths (common to montage and timelapse)
      if (formData.recordings_path) {
        args.recordings_path = formData.recordings_path
      }
      if (formData.recordings_path_fallback) {
        const fallbacks = formData.recordings_path_fallback
          .split('\n')
          .map((p) => p.trim())
          .filter((p) => p)
        if (fallbacks.length > 0) {
          args.recordings_path_fallback = fallbacks
        }
      }

      // Date handling
      if (formData.start_date && formData.end_date) {
        args.start_date = formData.start_date
        args.end_date = formData.end_date
      } else if (formData.date) {
        args.date = formData.date
      }

      if (formData.days) {
        args.days = parseInt(formData.days)
      }

      // Time window
      if (formData.dawntodusk) args.dawntodusk = true
      if (formData.dusktodawn) args.dusktodawn = true

      // Custom start/end time (for both montage and timelapse)
      if (formData.start_time) args.start_time = formData.start_time
      if (formData.end_time) args.end_time = formData.end_time

      if (formData.type === 'montage') {
        args.encoder = formData.encoder
        args.source = formData.source
        if (formData.pre_pad) args.pre_pad = parseInt(formData.pre_pad)
        if (formData.post_pad) args.post_pad = parseInt(formData.post_pad)
        if (formData.merge_gap) args.merge_gap = parseInt(formData.merge_gap)
        if (formData.labels_include) args.labels_include = formData.labels_include
        if (formData.labels_exclude) args.labels_exclude = formData.labels_exclude
        if (formData.min_score) args.min_score = parseFloat(formData.min_score)
        if (formData.timelapse) args.timelapse = parseFloat(formData.timelapse)
        // When copy_only is false, we need to encode
        if (!formData.copy_only) args.encode = true
        // All motion mode
        if (formData.all_motion) args.all_motion = true
        if (formData.min_motion) args.min_motion = parseInt(formData.min_motion)
      } else if (formData.type === 'timelapse') {
        args.encoder = formData.encoder
        args.source = formData.source
        if (formData.timelapse_speed) args.timelapse = parseFloat(formData.timelapse_speed)
        if (formData.frame_sample) args.frame_sample = parseFloat(formData.frame_sample)
        if (formData.sample_interval) args.sample_interval = parseFloat(formData.sample_interval)
        if (formData.fps) args.fps = parseInt(formData.fps)
        if (formData.scale) args.scale = formData.scale
        if (formData.cuda) args.cuda = true
        // Dawn/dusk offset for time window adjustment
        if (formData.dawn_offset && formData.dawn_offset !== '0') args.dawn_offset = parseInt(formData.dawn_offset)
        if (formData.dusk_offset && formData.dusk_offset !== '0') args.dusk_offset = parseInt(formData.dusk_offset)
        // Quality settings
        if (formData.cq) args.cq = parseInt(formData.cq)
        if (formData.crf) args.crf = parseInt(formData.crf)
      } else if (formData.type === 'motion_playlist') {
        if (formData.limit) args.limit = parseInt(formData.limit)
      }

      const job = await createJob({
        type: formData.type,
        camera: formData.camera,
        arguments: args,
      })

      navigate(`/jobs/${job.id}`)
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to create job')
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="max-w-3xl mx-auto">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">New Job</h1>
        <p className="mt-1 text-gray-600">Create a new montage or timelapse job</p>
      </div>

      {/* Presets */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4 mb-6">
        <div className="flex items-center justify-between mb-2">
          <h3 className="text-sm font-medium text-gray-700">Presets</h3>
          <button
            type="button"
            onClick={() => setShowSavePreset(!showSavePreset)}
            className="text-sm text-frigate-600 hover:text-frigate-700"
          >
            {showSavePreset ? 'Cancel' : '+ Save Current as Preset'}
          </button>
        </div>

        {showSavePreset && (
          <div className="flex gap-2 mb-3 p-3 bg-frigate-50 rounded-lg">
            <input
              type="text"
              value={presetName}
              onChange={(e) => setPresetName(e.target.value)}
              placeholder="Preset name..."
              className="flex-1 rounded-lg border-gray-300 text-sm focus:border-frigate-500 focus:ring-frigate-500"
            />
            <button
              type="button"
              onClick={handleSavePreset}
              disabled={savingPreset || !presetName.trim()}
              className="px-4 py-2 text-sm font-medium text-white bg-frigate-600 rounded-lg hover:bg-frigate-700 disabled:opacity-50"
            >
              {savingPreset ? 'Saving...' : 'Save'}
            </button>
          </div>
        )}

        {presets.length > 0 ? (
          <div className="flex flex-wrap gap-2">
            {presets.map((preset) => (
              <button
                key={preset.id}
                type="button"
                onClick={() => loadPreset(preset)}
                className="px-3 py-1.5 text-sm rounded-lg bg-gray-100 hover:bg-gray-200 transition-colors"
              >
                {preset.name}
              </button>
            ))}
          </div>
        ) : (
          <p className="text-sm text-gray-500">No presets saved. Configure your job and save it as a preset for quick reuse.</p>
        )}
      </div>

      <form onSubmit={handleSubmit} className="space-y-6">
        {/* Job Type */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Job Type</h2>
          <div className="grid grid-cols-3 gap-4">
            {(['montage', 'timelapse', 'motion_playlist'] as const).map((type) => (
              <button
                key={type}
                type="button"
                onClick={() => setFormData((prev) => ({ ...prev, type }))}
                className={`p-4 rounded-lg border-2 transition-colors ${
                  formData.type === type
                    ? 'border-frigate-500 bg-frigate-50'
                    : 'border-gray-200 hover:border-gray-300'
                }`}
              >
                <div className="font-medium text-gray-900 capitalize">
                  {type.replace('_', ' ')}
                </div>
                <div className="text-sm text-gray-500 mt-1">
                  {type === 'montage' && 'Animal detection clips'}
                  {type === 'timelapse' && 'Time-lapse video'}
                  {type === 'motion_playlist' && 'Motion events playlist'}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Camera Selection */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Camera</h2>
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">
              Select Camera
            </label>
            {cameras.length > 0 ? (
              <select
                name="camera"
                value={formData.camera}
                onChange={handleChange}
                className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                required
              >
                <option value="">Select a camera...</option>
                {cameras.map((cam) => (
                  <option key={cam} value={cam}>
                    {cam}
                  </option>
                ))}
              </select>
            ) : (
              <input
                type="text"
                name="camera"
                value={formData.camera}
                onChange={handleChange}
                placeholder="Enter camera name"
                className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                required
              />
            )}
          </div>
        </div>

        {/* Time Window */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Time Window</h2>
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium text-gray-700 mb-1">Date</label>
              <input
                type="date"
                name="date"
                value={formData.date}
                onChange={handleChange}
                className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
              />
              <p className="mt-1 text-sm text-gray-500">
                Or use date range below for multi-day jobs
              </p>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Start Date
                </label>
                <input
                  type="date"
                  name="start_date"
                  value={formData.start_date}
                  onChange={handleChange}
                  className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                />
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  End Date
                </label>
                <input
                  type="date"
                  name="end_date"
                  value={formData.end_date}
                  onChange={handleChange}
                  className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                />
              </div>
            </div>

            <div>
              <label className="block text-sm font-medium text-gray-700 mb-2">
                Time of Day
              </label>
              <div className="flex gap-4">
                <label className="flex items-center">
                  <input
                    type="radio"
                    checked={formData.dawntodusk}
                    onChange={() => handleTimeWindowChange('dawntodusk')}
                    className="text-frigate-600 focus:ring-frigate-500"
                  />
                  <span className="ml-2 text-sm text-gray-700">Dawn to Dusk (daytime)</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="radio"
                    checked={formData.dusktodawn}
                    onChange={() => handleTimeWindowChange('dusktodawn')}
                    className="text-frigate-600 focus:ring-frigate-500"
                  />
                  <span className="ml-2 text-sm text-gray-700">Dusk to Dawn (nighttime)</span>
                </label>
                <label className="flex items-center">
                  <input
                    type="radio"
                    checked={!formData.dawntodusk && !formData.dusktodawn}
                    onChange={() => handleTimeWindowChange('custom')}
                    className="text-frigate-600 focus:ring-frigate-500"
                  />
                  <span className="ml-2 text-sm text-gray-700">Full day / Custom</span>
                </label>
              </div>
            </div>

            {/* Custom time range - shown when not using dawn/dusk presets */}
            {!formData.dawntodusk && !formData.dusktodawn && (
              <div className="grid grid-cols-2 gap-4 pt-2">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Start Time (optional)
                  </label>
                  <input
                    type="time"
                    name="start_time"
                    value={formData.start_time}
                    onChange={handleChange}
                    className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    End Time (optional)
                  </label>
                  <input
                    type="time"
                    name="end_time"
                    value={formData.end_time}
                    onChange={handleChange}
                    className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                  />
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Type-specific options */}
        {formData.type === 'montage' && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Montage Options</h2>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Source
                  </label>
                  <select
                    name="source"
                    value={formData.source}
                    onChange={handleChange}
                    className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                  >
                    <option value="disk">Disk (local files)</option>
                    <option value="vod">VOD (stream from Frigate)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Encoder
                  </label>
                  <select
                    name="encoder"
                    value={formData.encoder}
                    onChange={handleChange}
                    className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                  >
                    <option value="hevc_nvenc">HEVC (NVENC)</option>
                    <option value="h264_nvenc">H.264 (NVENC)</option>
                    <option value="libx265">HEVC (Software)</option>
                    <option value="libx264">H.264 (Software)</option>
                  </select>
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Labels to Include (comma-separated)
                  </label>
                  <input
                    type="text"
                    name="labels_include"
                    value={formData.labels_include}
                    onChange={handleChange}
                    placeholder="blank = animals"
                    className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                  />
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Labels to Exclude (comma-separated)
                  </label>
                  <input
                    type="text"
                    name="labels_exclude"
                    value={formData.labels_exclude}
                    onChange={handleChange}
                    placeholder="e.g., person,car"
                    className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                  />
                </div>
              </div>

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Minimum Score (0.0 - 1.0)
                </label>
                <input
                  type="number"
                  name="min_score"
                  value={formData.min_score}
                  onChange={handleChange}
                  step="0.05"
                  min="0"
                  max="1"
                  placeholder="e.g., 0.7"
                  className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                />
                <p className="mt-1 text-sm text-gray-500">
                  Filter detections below this confidence threshold
                </p>
              </div>

              <div className="pt-2">
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    name="copy_only"
                    checked={formData.copy_only}
                    onChange={handleChange}
                    className="rounded border-gray-300 text-frigate-600 focus:ring-frigate-500"
                  />
                  <span className="ml-2 text-sm font-medium text-gray-700">
                    Copy mode (faster, no re-encoding)
                  </span>
                </label>
                <p className="mt-1 text-sm text-gray-500 ml-6">
                  When enabled, video streams are copied directly without re-encoding.
                  Disable to re-encode with the selected encoder settings.
                </p>
              </div>

              <div className="pt-2">
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    name="all_motion"
                    checked={formData.all_motion}
                    onChange={handleChange}
                    className="rounded border-gray-300 text-frigate-600 focus:ring-frigate-500"
                  />
                  <span className="ml-2 text-sm font-medium text-gray-700">
                    Capture all motion (ignore detection labels)
                  </span>
                </label>
                <p className="mt-1 text-sm text-gray-500 ml-6">
                  Include all motion events, even when no object was detected.
                  Useful for reviewing all activity without relying on AI detection.
                </p>
              </div>

              {formData.all_motion && (
                <div className="pt-2 ml-6">
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Minimum Motion Intensity
                  </label>
                  <input
                    type="number"
                    name="min_motion"
                    value={formData.min_motion}
                    onChange={handleChange}
                    min="0"
                    placeholder="e.g., 50"
                    className="block w-48 rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                  />
                  <p className="mt-1 text-sm text-gray-500">
                    Filter out low-activity segments. Higher values = more motion required.
                    Leave blank to include all motion.
                  </p>
                </div>
              )}
            </div>
          </div>
        )}

        {formData.type === 'timelapse' && (
          <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
            <h2 className="text-lg font-semibold text-gray-900 mb-4">Timelapse Options</h2>
            <div className="space-y-4">
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Source
                  </label>
                  <select
                    name="source"
                    value={formData.source}
                    onChange={handleChange}
                    className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                  >
                    <option value="disk">Disk (local files)</option>
                    <option value="vod">VOD (stream from Frigate)</option>
                  </select>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Sample Interval (seconds)
                  </label>
                  <input
                    type="number"
                    name="sample_interval"
                    value={formData.sample_interval}
                    onChange={handleChange}
                    min="1"
                    className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                  />
                  <p className="mt-1 text-sm text-gray-500">
                    Take 1 frame every N seconds
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Output FPS
                  </label>
                  <input
                    type="number"
                    name="fps"
                    value={formData.fps}
                    onChange={handleChange}
                    min="1"
                    max="60"
                    className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                  />
                </div>
              </div>

              <div className="grid grid-cols-2 gap-4">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Encoder
                  </label>
                  <select
                    name="encoder"
                    value={formData.encoder}
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
                    Scale (optional)
                  </label>
                  <input
                    type="text"
                    name="scale"
                    value={formData.scale}
                    onChange={handleChange}
                    placeholder="e.g., 1920:1080 or -2:720"
                    className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                  />
                </div>
              </div>

              {/* Dawn/Dusk Offsets - only relevant when using dawn/dusk time window */}
              {(formData.dawntodusk || formData.dusktodawn) && (
                <div className="grid grid-cols-2 gap-4 pt-2">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Dawn Offset (minutes)
                    </label>
                    <input
                      type="number"
                      name="dawn_offset"
                      value={formData.dawn_offset}
                      onChange={handleChange}
                      placeholder="0"
                      className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                    />
                    <p className="mt-1 text-sm text-gray-500">
                      Adjust dawn time (negative = earlier)
                    </p>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Dusk Offset (minutes)
                    </label>
                    <input
                      type="number"
                      name="dusk_offset"
                      value={formData.dusk_offset}
                      onChange={handleChange}
                      placeholder="0"
                      className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                    />
                    <p className="mt-1 text-sm text-gray-500">
                      Adjust dusk time (positive = later)
                    </p>
                  </div>
                </div>
              )}

              {/* Quality Settings */}
              <div className="grid grid-cols-2 gap-4 pt-2">
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    CQ (Constant Quality, NVENC)
                  </label>
                  <input
                    type="number"
                    name="cq"
                    value={formData.cq}
                    onChange={handleChange}
                    min="0"
                    max="51"
                    placeholder="e.g., 23"
                    className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                  />
                  <p className="mt-1 text-sm text-gray-500">
                    Lower = better quality (0-51)
                  </p>
                </div>
                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    CRF (Constant Rate Factor, software)
                  </label>
                  <input
                    type="number"
                    name="crf"
                    value={formData.crf}
                    onChange={handleChange}
                    min="0"
                    max="51"
                    placeholder="e.g., 23"
                    className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                  />
                  <p className="mt-1 text-sm text-gray-500">
                    Lower = better quality (0-51)
                  </p>
                </div>
              </div>

              <div className="pt-2">
                <label className="flex items-center">
                  <input
                    type="checkbox"
                    name="cuda"
                    checked={formData.cuda}
                    onChange={handleChange}
                    className="rounded border-gray-300 text-frigate-600 focus:ring-frigate-500"
                  />
                  <span className="ml-2 text-sm font-medium text-gray-700">
                    Use CUDA for frame extraction
                  </span>
                </label>
                <p className="mt-1 text-sm text-gray-500 ml-6">
                  Enable GPU-accelerated decoding when extracting frames
                </p>
              </div>
            </div>
          </div>
        )}

        {/* Advanced Options */}
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <button
            type="button"
            onClick={() => setShowAdvanced(!showAdvanced)}
            className="flex items-center text-sm font-medium text-gray-700"
          >
            <svg
              className={`w-4 h-4 mr-2 transition-transform ${showAdvanced ? 'rotate-90' : ''}`}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
            Advanced Options
          </button>

          {showAdvanced && (
            <div className="mt-4 space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">
                  Frigate Base URL
                </label>
                <input
                  type="url"
                  name="base_url"
                  value={formData.base_url}
                  onChange={handleChange}
                  className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                />
              </div>

              {(formData.type === 'montage' || formData.type === 'timelapse') && (
                <>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Recordings Path
                    </label>
                    <input
                      type="text"
                      name="recordings_path"
                      value={formData.recordings_path}
                      onChange={handleChange}
                      placeholder="/mnt/media/frigate/recordings"
                      className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                    />
                    <p className="mt-1 text-sm text-gray-500">
                      Primary path to Frigate recordings directory
                    </p>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Fallback Recordings Paths
                    </label>
                    <textarea
                      name="recordings_path_fallback"
                      value={formData.recordings_path_fallback}
                      onChange={handleChange}
                      rows={3}
                      placeholder={"/mnt/backup/frigate/recordings\n/mnt/nas/frigate/recordings"}
                      className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500 font-mono text-sm"
                    />
                    <p className="mt-1 text-sm text-gray-500">
                      Additional paths to check (one per line). Useful for multiple Frigate instances or NFS mounts.
                    </p>
                  </div>
                </>
              )}

              {formData.type === 'montage' && (
                <div className="grid grid-cols-3 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Pre-pad (seconds)
                    </label>
                    <input
                      type="number"
                      name="pre_pad"
                      value={formData.pre_pad}
                      onChange={handleChange}
                      min="0"
                      className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Post-pad (seconds)
                    </label>
                    <input
                      type="number"
                      name="post_pad"
                      value={formData.post_pad}
                      onChange={handleChange}
                      min="0"
                      className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-gray-700 mb-1">
                      Merge gap (seconds)
                    </label>
                    <input
                      type="number"
                      name="merge_gap"
                      value={formData.merge_gap}
                      onChange={handleChange}
                      min="0"
                      className="block w-full rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
                    />
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Error message */}
        {error && (
          <div className="bg-red-50 border border-red-200 rounded-lg p-4 text-red-700">
            {error}
          </div>
        )}

        {/* Submit */}
        <div className="flex justify-end gap-4">
          <button
            type="button"
            onClick={() => navigate('/jobs')}
            className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={submitting || !formData.camera}
            className="px-6 py-2 text-sm font-medium text-white bg-frigate-600 rounded-lg hover:bg-frigate-700 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {submitting ? 'Creating...' : 'Create Job'}
          </button>
        </div>
      </form>
    </div>
  )
}
