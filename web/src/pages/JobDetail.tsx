import { useEffect, useState, useRef } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { getJob, getJobLogs, cancelJob, deleteJob, retryJob, getFileUrl } from '../api/client'
import { useJobWebSocket } from '../hooks/useWebSocket'
import type { Job } from '../api/types'
import StatusBadge from '../components/StatusBadge'
import JobTypeBadge from '../components/JobTypeBadge'
import ProgressBar from '../components/ProgressBar'

function formatDate(dateString: string | null): string {
  if (!dateString) return '—'
  return new Date(dateString).toLocaleString()
}

function formatDuration(start: string | null, end: string | null): string {
  if (!start) return '—'
  const startDate = new Date(start)
  const endDate = end ? new Date(end) : new Date()
  const diffMs = endDate.getTime() - startDate.getTime()
  const seconds = Math.floor(diffMs / 1000)
  const minutes = Math.floor(seconds / 60)
  const hours = Math.floor(minutes / 60)

  if (hours > 0) return `${hours}h ${minutes % 60}m`
  if (minutes > 0) return `${minutes}m ${seconds % 60}s`
  return `${seconds}s`
}

export default function JobDetail() {
  const { id } = useParams<{ id: string }>()
  const navigate = useNavigate()
  const [job, setJob] = useState<Job | null>(null)
  const [logs, setLogs] = useState<string>('')
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [autoScroll, setAutoScroll] = useState(true)
  const logsEndRef = useRef<HTMLDivElement>(null)

  // WebSocket for real-time updates
  const { job: wsJob, connected } = useJobWebSocket(
    job?.status === 'running' ? id || null : null,
    {
      onUpdate: (updatedJob) => {
        setJob(updatedJob)
      },
    }
  )

  // Use WebSocket job if available
  const displayJob = wsJob || job

  useEffect(() => {
    async function fetchJob() {
      if (!id) return
      try {
        const data = await getJob(id)
        setJob(data)
      } catch (err) {
        setError('Job not found')
      } finally {
        setLoading(false)
      }
    }
    fetchJob()
  }, [id])

  // Fetch logs periodically
  useEffect(() => {
    if (!id) return
    const jobId = id  // Capture id for closure

    async function fetchLogs() {
      try {
        const data = await getJobLogs(jobId, 500)
        setLogs(data)
      } catch {
        // Logs might not exist yet
      }
    }

    fetchLogs()
    const interval = setInterval(fetchLogs, 2000)
    return () => clearInterval(interval)
  }, [id])

  // Auto-scroll logs
  useEffect(() => {
    if (autoScroll && logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: 'smooth' })
    }
  }, [logs, autoScroll])

  const handleCancel = async () => {
    if (!id || !confirm('Cancel this job?')) return
    try {
      await cancelJob(id)
      const updated = await getJob(id)
      setJob(updated)
    } catch (err) {
      console.error('Failed to cancel job:', err)
    }
  }

  const handleDelete = async () => {
    if (!id || !confirm('Delete this job and its logs?')) return
    try {
      await deleteJob(id)
      navigate('/jobs')
    } catch (err) {
      console.error('Failed to delete job:', err)
    }
  }

  const handleRetry = async () => {
    if (!id) return
    try {
      const newJob = await retryJob(id)
      navigate(`/jobs/${newJob.id}`)
    } catch (err) {
      console.error('Failed to retry job:', err)
    }
  }

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading...</div>
      </div>
    )
  }

  if (error || !displayJob) {
    return (
      <div className="flex flex-col items-center justify-center h-64">
        <div className="text-red-500 mb-4">{error || 'Job not found'}</div>
        <Link to="/jobs" className="text-frigate-600 hover:text-frigate-700">
          ← Back to Jobs
        </Link>
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex items-start justify-between">
        <div>
          <div className="flex items-center gap-3 mb-2">
            <JobTypeBadge type={displayJob.type} />
            <StatusBadge status={displayJob.status} />
            {connected && displayJob.status === 'running' && (
              <span className="text-xs text-green-600 flex items-center">
                <span className="w-2 h-2 bg-green-500 rounded-full mr-1 animate-pulse"></span>
                Live
              </span>
            )}
          </div>
          <h1 className="text-2xl font-bold text-gray-900">{displayJob.camera}</h1>
          <p className="text-gray-600">Job ID: {displayJob.id}</p>
        </div>
        <div className="flex gap-2">
          <Link
            to={`/jobs/new?clone=${displayJob.id}`}
            className="px-4 py-2 text-sm font-medium text-frigate-700 bg-frigate-100 rounded-lg hover:bg-frigate-200"
          >
            Clone
          </Link>
          {displayJob.status === 'running' && (
            <button
              onClick={handleCancel}
              className="px-4 py-2 text-sm font-medium text-yellow-700 bg-yellow-100 rounded-lg hover:bg-yellow-200"
            >
              Cancel
            </button>
          )}
          {['failed', 'cancelled'].includes(displayJob.status) && (
            <button
              onClick={handleRetry}
              className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-lg hover:bg-green-700"
            >
              Retry
            </button>
          )}
          {['completed', 'failed', 'cancelled'].includes(displayJob.status) && (
            <button
              onClick={handleDelete}
              className="px-4 py-2 text-sm font-medium text-red-700 bg-red-100 rounded-lg hover:bg-red-200"
            >
              Delete
            </button>
          )}
        </div>
      </div>

      {/* Progress */}
      {displayJob.status === 'running' && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Progress</h2>
          <ProgressBar
            percent={displayJob.progress.percent}
            label={displayJob.progress.phase}
            size="lg"
          />
          {displayJob.progress.message && (
            <p className="mt-2 text-sm text-gray-600 font-mono truncate">
              {displayJob.progress.message}
            </p>
          )}
        </div>
      )}

      {/* Error */}
      {displayJob.error && (
        <div className="bg-red-50 border border-red-200 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-red-900 mb-2">Error</h2>
          <p className="text-red-700">{displayJob.error}</p>
        </div>
      )}

      {/* Output File */}
      {displayJob.output_file && (
        <div className="bg-green-50 border border-green-200 rounded-xl p-6">
          <h2 className="text-lg font-semibold text-green-900 mb-2">Output</h2>
          <div className="flex items-center gap-4">
            <p className="text-green-700 font-mono text-sm truncate flex-1">
              {displayJob.output_file}
            </p>
            <a
              href={getFileUrl(displayJob.output_file.split('/').pop() || '')}
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 text-sm font-medium text-white bg-green-600 rounded-lg hover:bg-green-700"
            >
              View/Download
            </a>
          </div>
        </div>
      )}

      {/* Details */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Details</h2>
        <dl className="grid grid-cols-2 gap-4">
          <div>
            <dt className="text-sm font-medium text-gray-500">Created</dt>
            <dd className="text-sm text-gray-900">{formatDate(displayJob.created_at)}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Started</dt>
            <dd className="text-sm text-gray-900">{formatDate(displayJob.started_at)}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Completed</dt>
            <dd className="text-sm text-gray-900">{formatDate(displayJob.completed_at)}</dd>
          </div>
          <div>
            <dt className="text-sm font-medium text-gray-500">Duration</dt>
            <dd className="text-sm text-gray-900">
              {formatDuration(displayJob.started_at, displayJob.completed_at)}
            </dd>
          </div>
        </dl>
      </div>

      {/* Arguments */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Arguments</h2>
        <pre className="text-sm text-gray-700 bg-gray-50 rounded-lg p-4 overflow-x-auto">
          {JSON.stringify(displayJob.arguments, null, 2)}
        </pre>
      </div>

      {/* Logs */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Logs</h2>
          <label className="flex items-center text-sm text-gray-600">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={(e) => setAutoScroll(e.target.checked)}
              className="rounded border-gray-300 text-frigate-600 focus:ring-frigate-500 mr-2"
            />
            Auto-scroll
          </label>
        </div>
        <div className="bg-gray-900 rounded-lg p-4 h-96 overflow-y-auto font-mono text-sm">
          {logs ? (
            <pre className="text-green-400 whitespace-pre-wrap">{logs}</pre>
          ) : (
            <span className="text-gray-500">No logs yet...</span>
          )}
          <div ref={logsEndRef} />
        </div>
      </div>

      {/* Back link */}
      <div className="pt-4">
        <Link to="/jobs" className="text-frigate-600 hover:text-frigate-700">
          ← Back to Jobs
        </Link>
      </div>
    </div>
  )
}
