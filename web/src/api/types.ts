export type JobType = 'montage' | 'timelapse' | 'motion_playlist'
export type JobStatus = 'pending' | 'running' | 'completed' | 'failed' | 'cancelled'

export interface JobProgress {
  phase: string
  percent: number
  message: string
}

export interface Job {
  id: string
  type: JobType
  status: JobStatus
  camera: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  progress: JobProgress
  arguments: Record<string, unknown>
  output_file: string | null
  error: string | null
  log_file: string | null
  pid: number | null
}

export interface JobSummary {
  id: string
  type: JobType
  status: JobStatus
  camera: string
  created_at: string
  started_at: string | null
  completed_at: string | null
  progress: JobProgress
  output_file: string | null
  error: string | null
}

export interface JobCreate {
  type: JobType
  camera: string
  arguments: Record<string, unknown>
}

export interface FileInfo {
  name: string
  path: string
  size: number
  modified: string
  is_video: boolean
}

export interface Preset {
  id: string
  name: string
  type: JobType
  camera: string | null
  arguments: Record<string, unknown>
  created_at: string
}

export interface Config {
  default_camera: string | null
  default_base_url: string
  default_recordings_path: string
  default_encoder: string
  timezone: string
  latitude: number
  longitude: number
}
