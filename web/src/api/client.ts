import type { Job, JobCreate, JobSummary, FileInfo, Preset, Config } from './types'

const API_BASE = '/api'

async function fetchJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  if (!response.ok) {
    const error = await response.text()
    throw new Error(error || `HTTP ${response.status}`)
  }
  return response.json()
}

// Jobs API
export async function createJob(job: JobCreate): Promise<Job> {
  return fetchJson<Job>(`${API_BASE}/jobs`, {
    method: 'POST',
    body: JSON.stringify(job),
  })
}

export async function listJobs(params?: {
  status?: string
  type?: string
  camera?: string
  limit?: number
  offset?: number
}): Promise<JobSummary[]> {
  const searchParams = new URLSearchParams()
  if (params?.status) searchParams.set('status', params.status)
  if (params?.type) searchParams.set('type', params.type)
  if (params?.camera) searchParams.set('camera', params.camera)
  if (params?.limit) searchParams.set('limit', params.limit.toString())
  if (params?.offset) searchParams.set('offset', params.offset.toString())

  const query = searchParams.toString()
  return fetchJson<JobSummary[]>(`${API_BASE}/jobs${query ? `?${query}` : ''}`)
}

export async function getJob(id: string): Promise<Job> {
  return fetchJson<Job>(`${API_BASE}/jobs/${id}`)
}

export async function deleteJob(id: string, cancel = true): Promise<void> {
  await fetch(`${API_BASE}/jobs/${id}?cancel=${cancel}`, { method: 'DELETE' })
}

export async function cancelJob(id: string): Promise<void> {
  await fetch(`${API_BASE}/jobs/${id}/cancel`, { method: 'POST' })
}

export async function retryJob(id: string): Promise<Job> {
  return fetchJson<Job>(`${API_BASE}/jobs/${id}/retry`, { method: 'POST' })
}

export async function getJobLogs(id: string, tail = 200): Promise<string> {
  const data = await fetchJson<{ logs: string }>(`${API_BASE}/jobs/${id}/logs?tail=${tail}`)
  return data.logs
}

export async function getJobCloneData(id: string): Promise<{
  type: string
  camera: string
  arguments: Record<string, unknown>
}> {
  return fetchJson(`${API_BASE}/jobs/${id}/clone`)
}

// Files API
export async function listFiles(params?: {
  sort?: string
  desc?: boolean
  videos_only?: boolean
}): Promise<FileInfo[]> {
  const searchParams = new URLSearchParams()
  if (params?.sort) searchParams.set('sort', params.sort)
  if (params?.desc !== undefined) searchParams.set('desc', params.desc.toString())
  if (params?.videos_only) searchParams.set('videos_only', 'true')

  const query = searchParams.toString()
  return fetchJson<FileInfo[]>(`${API_BASE}/files${query ? `?${query}` : ''}`)
}

export function getFileUrl(filename: string, download = false): string {
  return `${API_BASE}/files/${encodeURIComponent(filename)}${download ? '?download=true' : ''}`
}

export function getThumbnailUrl(filename: string): string {
  return `${API_BASE}/files/${encodeURIComponent(filename)}/thumbnail`
}

export async function deleteFile(filename: string): Promise<void> {
  await fetch(`${API_BASE}/files/${encodeURIComponent(filename)}`, { method: 'DELETE' })
}

// Config API
export async function getConfig(): Promise<Config> {
  return fetchJson<Config>(`${API_BASE}/config`)
}

export async function updateConfig(config: Config): Promise<Config> {
  return fetchJson<Config>(`${API_BASE}/config`, {
    method: 'PUT',
    body: JSON.stringify(config),
  })
}

// Cameras API
export async function listCameras(): Promise<string[]> {
  const data = await fetchJson<{ cameras: string[] }>(`${API_BASE}/cameras`)
  return data.cameras
}

// Presets API
export async function listPresets(): Promise<Preset[]> {
  return fetchJson<Preset[]>(`${API_BASE}/presets`)
}

export async function createPreset(preset: Omit<Preset, 'id' | 'created_at'>): Promise<Preset> {
  return fetchJson<Preset>(`${API_BASE}/presets`, {
    method: 'POST',
    body: JSON.stringify(preset),
  })
}

export async function deletePreset(id: string): Promise<void> {
  await fetch(`${API_BASE}/presets/${id}`, { method: 'DELETE' })
}

export async function updatePreset(
  id: string,
  preset: Partial<Omit<Preset, 'id' | 'created_at'>>
): Promise<Preset> {
  return fetchJson<Preset>(`${API_BASE}/presets/${id}`, {
    method: 'PUT',
    body: JSON.stringify(preset),
  })
}

// Health API
export async function healthCheck(): Promise<{ status: string; running_jobs: number }> {
  return fetchJson<{ status: string; running_jobs: number }>(`${API_BASE}/health`)
}

// YouTube API
export async function getYouTubeStatus(): Promise<{
  configured: boolean
  authenticated: boolean
  setup_needed: boolean
  auth_needed: boolean
}> {
  return fetchJson(`${API_BASE}/youtube/status`)
}

export async function listYouTubeAccounts(): Promise<{
  accounts: Array<{ name: string; file: string }>
  default: string
}> {
  return fetchJson(`${API_BASE}/youtube/accounts`)
}

export async function uploadToYouTube(params: {
  filename: string
  title: string
  description?: string
  tags?: string
  category?: string
  privacy?: string
  account?: string
}): Promise<{
  status: string
  message: string
  url?: string
  error?: string
}> {
  const searchParams = new URLSearchParams()
  searchParams.set('filename', params.filename)
  searchParams.set('title', params.title)
  if (params.description) searchParams.set('description', params.description)
  if (params.tags) searchParams.set('tags', params.tags)
  if (params.category) searchParams.set('category', params.category)
  if (params.privacy) searchParams.set('privacy', params.privacy)
  if (params.account) searchParams.set('account', params.account)

  const response = await fetch(`${API_BASE}/youtube/upload?${searchParams}`, {
    method: 'POST',
  })
  return response.json()
}
