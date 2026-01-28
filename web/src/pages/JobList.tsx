import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listJobs, deleteJob, cancelJob, retryJob, listCameras } from '../api/client'
import type { JobSummary, JobStatus, JobType } from '../api/types'
import StatusBadge from '../components/StatusBadge'
import JobTypeBadge from '../components/JobTypeBadge'
import ProgressBar from '../components/ProgressBar'

function formatDate(dateString: string): string {
  return new Date(dateString).toLocaleString()
}

export default function JobList() {
  const [jobs, setJobs] = useState<JobSummary[]>([])
  const [cameras, setCameras] = useState<string[]>([])
  const [loading, setLoading] = useState(true)
  const [filters, setFilters] = useState<{
    status?: JobStatus
    type?: JobType
    camera?: string
  }>({})

  useEffect(() => {
    listCameras().then(setCameras).catch(console.error)
  }, [])

  useEffect(() => {
    async function fetchJobs() {
      try {
        const data = await listJobs({
          status: filters.status,
          type: filters.type,
          camera: filters.camera,
          limit: 50,
        })
        setJobs(data)
      } catch (error) {
        console.error('Failed to fetch jobs:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchJobs()
    const interval = setInterval(fetchJobs, 3000)
    return () => clearInterval(interval)
  }, [filters])

  const handleCancel = async (id: string) => {
    if (!confirm('Cancel this job?')) return
    try {
      await cancelJob(id)
      setJobs((prev) =>
        prev.map((j) => (j.id === id ? { ...j, status: 'cancelled' as JobStatus } : j))
      )
    } catch (error) {
      console.error('Failed to cancel job:', error)
    }
  }

  const handleDelete = async (id: string) => {
    if (!confirm('Delete this job and its logs?')) return
    try {
      await deleteJob(id)
      setJobs((prev) => prev.filter((j) => j.id !== id))
    } catch (error) {
      console.error('Failed to delete job:', error)
    }
  }

  const handleRetry = async (id: string) => {
    try {
      const newJob = await retryJob(id)
      setJobs((prev) => [
        {
          id: newJob.id,
          type: newJob.type,
          status: newJob.status,
          camera: newJob.camera,
          created_at: newJob.created_at,
          started_at: newJob.started_at,
          completed_at: newJob.completed_at,
          progress: newJob.progress,
          output_file: newJob.output_file,
          error: newJob.error,
        },
        ...prev,
      ])
    } catch (error) {
      console.error('Failed to retry job:', error)
    }
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Jobs</h1>
          <p className="mt-1 text-gray-600">View and manage all jobs</p>
        </div>
        <Link
          to="/jobs/new"
          className="inline-flex items-center px-4 py-2 rounded-lg bg-frigate-600 text-white font-medium hover:bg-frigate-700 transition-colors"
        >
          <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 4v16m8-8H4" />
          </svg>
          New Job
        </Link>
      </div>

      {/* Filters */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-4">
        <div className="flex flex-wrap gap-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Status</label>
            <select
              value={filters.status || ''}
              onChange={(e) =>
                setFilters((prev) => ({
                  ...prev,
                  status: (e.target.value || undefined) as JobStatus | undefined,
                }))
              }
              className="block w-40 rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
            >
              <option value="">All</option>
              <option value="pending">Pending</option>
              <option value="running">Running</option>
              <option value="completed">Completed</option>
              <option value="failed">Failed</option>
              <option value="cancelled">Cancelled</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Type</label>
            <select
              value={filters.type || ''}
              onChange={(e) =>
                setFilters((prev) => ({
                  ...prev,
                  type: (e.target.value || undefined) as JobType | undefined,
                }))
              }
              className="block w-40 rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
            >
              <option value="">All</option>
              <option value="montage">Montage</option>
              <option value="timelapse">Timelapse</option>
              <option value="motion_playlist">Motion Playlist</option>
            </select>
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Camera</label>
            <select
              value={filters.camera || ''}
              onChange={(e) =>
                setFilters((prev) => ({ ...prev, camera: e.target.value || undefined }))
              }
              className="block w-48 rounded-lg border-gray-300 shadow-sm focus:border-frigate-500 focus:ring-frigate-500"
            >
              <option value="">All Cameras</option>
              {cameras.map((cam) => (
                <option key={cam} value={cam}>
                  {cam}
                </option>
              ))}
            </select>
          </div>
        </div>
      </div>

      {/* Jobs Table */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 overflow-hidden">
        {loading ? (
          <div className="flex items-center justify-center h-64">
            <div className="text-gray-500">Loading...</div>
          </div>
        ) : jobs.length === 0 ? (
          <div className="flex flex-col items-center justify-center h-64 text-gray-500">
            <svg className="w-12 h-12 mb-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2" />
            </svg>
            <p>No jobs found</p>
          </div>
        ) : (
          <table className="w-full">
            <thead className="bg-gray-50">
              <tr className="text-left text-sm text-gray-500 border-b border-gray-200">
                <th className="px-6 py-3 font-medium">Type</th>
                <th className="px-6 py-3 font-medium">Camera</th>
                <th className="px-6 py-3 font-medium">Status</th>
                <th className="px-6 py-3 font-medium">Progress</th>
                <th className="px-6 py-3 font-medium">Created</th>
                <th className="px-6 py-3 font-medium">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {jobs.map((job) => (
                <tr key={job.id} className="hover:bg-gray-50">
                  <td className="px-6 py-4">
                    <JobTypeBadge type={job.type} size="sm" />
                  </td>
                  <td className="px-6 py-4 font-medium text-gray-900">{job.camera}</td>
                  <td className="px-6 py-4">
                    <StatusBadge status={job.status} size="sm" />
                  </td>
                  <td className="px-6 py-4 w-64">
                    {job.status === 'running' ? (
                      <ProgressBar percent={job.progress.percent} size="sm" showPercent />
                    ) : job.status === 'completed' ? (
                      <span className="text-sm text-green-600">100%</span>
                    ) : job.error ? (
                      <span className="text-sm text-red-600 truncate block max-w-xs" title={job.error}>
                        {job.error}
                      </span>
                    ) : (
                      <span className="text-sm text-gray-500">—</span>
                    )}
                  </td>
                  <td className="px-6 py-4 text-sm text-gray-500">{formatDate(job.created_at)}</td>
                  <td className="px-6 py-4">
                    <div className="flex items-center gap-2">
                      <Link
                        to={`/jobs/${job.id}`}
                        className="text-sm font-medium text-frigate-600 hover:text-frigate-700"
                      >
                        View
                      </Link>
                      {job.status === 'running' && (
                        <button
                          onClick={() => handleCancel(job.id)}
                          className="text-sm font-medium text-yellow-600 hover:text-yellow-700"
                        >
                          Cancel
                        </button>
                      )}
                      {['failed', 'cancelled'].includes(job.status) && (
                        <button
                          onClick={() => handleRetry(job.id)}
                          className="text-sm font-medium text-green-600 hover:text-green-700"
                        >
                          Retry
                        </button>
                      )}
                      {['completed', 'failed', 'cancelled'].includes(job.status) && (
                        <button
                          onClick={() => handleDelete(job.id)}
                          className="text-sm font-medium text-red-600 hover:text-red-700"
                        >
                          Delete
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
