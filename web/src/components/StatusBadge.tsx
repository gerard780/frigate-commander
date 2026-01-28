import type { JobStatus } from '../api/types'

interface StatusBadgeProps {
  status: JobStatus
  size?: 'sm' | 'md'
}

const statusConfig: Record<JobStatus, { label: string; classes: string }> = {
  pending: {
    label: 'Pending',
    classes: 'bg-gray-100 text-gray-700',
  },
  running: {
    label: 'Running',
    classes: 'bg-blue-100 text-blue-700',
  },
  completed: {
    label: 'Completed',
    classes: 'bg-green-100 text-green-700',
  },
  failed: {
    label: 'Failed',
    classes: 'bg-red-100 text-red-700',
  },
  cancelled: {
    label: 'Cancelled',
    classes: 'bg-yellow-100 text-yellow-700',
  },
}

export default function StatusBadge({ status, size = 'md' }: StatusBadgeProps) {
  const config = statusConfig[status]
  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm'

  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ${config.classes} ${sizeClasses}`}
    >
      {status === 'running' && (
        <span className="relative flex h-2 w-2 mr-1.5">
          <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-blue-400 opacity-75"></span>
          <span className="relative inline-flex rounded-full h-2 w-2 bg-blue-500"></span>
        </span>
      )}
      {config.label}
    </span>
  )
}
