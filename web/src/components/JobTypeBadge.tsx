import type { JobType } from '../api/types'

interface JobTypeBadgeProps {
  type: JobType
  size?: 'sm' | 'md'
}

const typeConfig: Record<JobType, { label: string; classes: string }> = {
  montage: {
    label: 'Montage',
    classes: 'bg-purple-100 text-purple-700',
  },
  timelapse: {
    label: 'Timelapse',
    classes: 'bg-indigo-100 text-indigo-700',
  },
  motion_playlist: {
    label: 'Motion Playlist',
    classes: 'bg-teal-100 text-teal-700',
  },
}

export default function JobTypeBadge({ type, size = 'md' }: JobTypeBadgeProps) {
  const config = typeConfig[type]
  const sizeClasses = size === 'sm' ? 'px-2 py-0.5 text-xs' : 'px-2.5 py-1 text-sm'

  return (
    <span
      className={`inline-flex items-center rounded-full font-medium ${config.classes} ${sizeClasses}`}
    >
      {config.label}
    </span>
  )
}
