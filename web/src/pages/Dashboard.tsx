import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { listJobs, healthCheck } from '../api/client'
import type { JobSummary } from '../api/types'
import StatusBadge from '../components/StatusBadge'
import JobTypeBadge from '../components/JobTypeBadge'
import ProgressBar from '../components/ProgressBar'

function formatRelativeTime(dateString: string): string {
  const date = new Date(dateString)
  const now = new Date()
  const diffMs = now.getTime() - date.getTime()
  const diffMins = Math.floor(diffMs / 60000)
  const diffHours = Math.floor(diffMins / 60)
  const diffDays = Math.floor(diffHours / 24)

  if (diffMins < 1) return 'just now'
  if (diffMins < 60) return `${diffMins}m ago`
  if (diffHours < 24) return `${diffHours}h ago`
  if (diffDays < 7) return `${diffDays}d ago`
  return date.toLocaleDateString()
}

export default function Dashboard() {
  const [recentJobs, setRecentJobs] = useState<JobSummary[]>([])
  const [runningJobs, setRunningJobs] = useState<JobSummary[]>([])
  const [stats, setStats] = useState({ running: 0, completed: 0, failed: 0 })
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function fetchData() {
      try {
        const [jobs, health] = await Promise.all([
          listJobs({ limit: 10 }),
          healthCheck(),
        ])

        setRecentJobs(jobs)
        setRunningJobs(jobs.filter((j) => j.status === 'running'))

        // Calculate stats from recent jobs
        const completed = jobs.filter((j) => j.status === 'completed').length
        const failed = jobs.filter((j) => j.status === 'failed').length
        setStats({ running: health.running_jobs, completed, failed })
      } catch (error) {
        console.error('Failed to fetch dashboard data:', error)
      } finally {
        setLoading(false)
      }
    }

    fetchData()
    const interval = setInterval(fetchData, 5000)
    return () => clearInterval(interval)
  }, [])

  if (loading) {
    return (
      <div className="flex items-center justify-center h-64">
        <div className="text-gray-500">Loading...</div>
      </div>
    )
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Dashboard</h1>
        <p className="mt-1 text-gray-600">
          Manage your Frigate montage and timelapse jobs
        </p>
      </div>

      {/* Stats */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center">
            <div className="p-3 rounded-full bg-blue-100">
              <svg className="w-6 h-6 text-blue-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
              </svg>
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-500">Running Jobs</p>
              <p className="text-2xl font-semibold text-gray-900">{stats.running}</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center">
            <div className="p-3 rounded-full bg-green-100">
              <svg className="w-6 h-6 text-green-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 13l4 4L19 7" />
              </svg>
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-500">Completed (Recent)</p>
              <p className="text-2xl font-semibold text-gray-900">{stats.completed}</p>
            </div>
          </div>
        </div>

        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <div className="flex items-center">
            <div className="p-3 rounded-full bg-red-100">
              <svg className="w-6 h-6 text-red-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>
            <div className="ml-4">
              <p className="text-sm font-medium text-gray-500">Failed (Recent)</p>
              <p className="text-2xl font-semibold text-gray-900">{stats.failed}</p>
            </div>
          </div>
        </div>
      </div>

      {/* Quick Actions */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <h2 className="text-lg font-semibold text-gray-900 mb-4">Quick Actions</h2>
        <div className="flex flex-wrap gap-3">
          <Link
            to="/jobs/new?type=montage"
            className="inline-flex items-center px-4 py-2 rounded-lg bg-purple-600 text-white font-medium hover:bg-purple-700 transition-colors"
          >
            <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
            New Montage
          </Link>
          <Link
            to="/jobs/new?type=timelapse"
            className="inline-flex items-center px-4 py-2 rounded-lg bg-indigo-600 text-white font-medium hover:bg-indigo-700 transition-colors"
          >
            <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            New Timelapse
          </Link>
          <Link
            to="/files"
            className="inline-flex items-center px-4 py-2 rounded-lg bg-gray-100 text-gray-700 font-medium hover:bg-gray-200 transition-colors"
          >
            <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M5 19a2 2 0 01-2-2V7a2 2 0 012-2h4l2 2h4a2 2 0 012 2v1M5 19h14a2 2 0 002-2v-5a2 2 0 00-2-2H9a2 2 0 00-2 2v5a2 2 0 01-2 2z" />
            </svg>
            Browse Files
          </Link>
        </div>
      </div>

      {/* Running Jobs */}
      {runningJobs.length > 0 && (
        <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
          <h2 className="text-lg font-semibold text-gray-900 mb-4">Running Jobs</h2>
          <div className="space-y-4">
            {runningJobs.map((job) => (
              <Link
                key={job.id}
                to={`/jobs/${job.id}`}
                className="block p-4 rounded-lg border border-gray-200 hover:border-frigate-300 hover:bg-frigate-50/50 transition-colors"
              >
                <div className="flex items-center justify-between mb-2">
                  <div className="flex items-center gap-3">
                    <JobTypeBadge type={job.type} size="sm" />
                    <span className="font-medium text-gray-900">{job.camera}</span>
                  </div>
                  <StatusBadge status={job.status} size="sm" />
                </div>
                <ProgressBar
                  percent={job.progress.percent}
                  label={job.progress.message || job.progress.phase}
                  size="sm"
                />
              </Link>
            ))}
          </div>
        </div>
      )}

      {/* Recent Jobs */}
      <div className="bg-white rounded-xl shadow-sm border border-gray-200 p-6">
        <div className="flex items-center justify-between mb-4">
          <h2 className="text-lg font-semibold text-gray-900">Recent Jobs</h2>
          <Link
            to="/jobs"
            className="text-sm font-medium text-frigate-600 hover:text-frigate-700"
          >
            View all →
          </Link>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full">
            <thead>
              <tr className="text-left text-sm text-gray-500 border-b border-gray-200">
                <th className="pb-3 font-medium">Type</th>
                <th className="pb-3 font-medium">Camera</th>
                <th className="pb-3 font-medium">Status</th>
                <th className="pb-3 font-medium">Created</th>
                <th className="pb-3"></th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-100">
              {recentJobs.map((job) => (
                <tr key={job.id} className="hover:bg-gray-50">
                  <td className="py-3">
                    <JobTypeBadge type={job.type} size="sm" />
                  </td>
                  <td className="py-3 font-medium text-gray-900">{job.camera}</td>
                  <td className="py-3">
                    <StatusBadge status={job.status} size="sm" />
                  </td>
                  <td className="py-3 text-sm text-gray-500">
                    {formatRelativeTime(job.created_at)}
                  </td>
                  <td className="py-3 text-right">
                    <Link
                      to={`/jobs/${job.id}`}
                      className="text-sm font-medium text-frigate-600 hover:text-frigate-700"
                    >
                      View
                    </Link>
                  </td>
                </tr>
              ))}
              {recentJobs.length === 0 && (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-gray-500">
                    No jobs yet. Create one to get started!
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}
