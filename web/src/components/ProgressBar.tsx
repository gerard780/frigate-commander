interface ProgressBarProps {
  percent: number
  label?: string
  showPercent?: boolean
  size?: 'sm' | 'md' | 'lg'
  color?: 'blue' | 'green' | 'yellow' | 'red'
}

const sizeClasses = {
  sm: 'h-1',
  md: 'h-2',
  lg: 'h-3',
}

const colorClasses = {
  blue: 'bg-frigate-500',
  green: 'bg-green-500',
  yellow: 'bg-yellow-500',
  red: 'bg-red-500',
}

export default function ProgressBar({
  percent,
  label,
  showPercent = true,
  size = 'md',
  color = 'blue',
}: ProgressBarProps) {
  const clampedPercent = Math.max(0, Math.min(100, percent))

  return (
    <div className="w-full">
      {(label || showPercent) && (
        <div className="flex justify-between text-sm mb-1">
          {label && <span className="text-gray-600">{label}</span>}
          {showPercent && (
            <span className="text-gray-500">{clampedPercent.toFixed(1)}%</span>
          )}
        </div>
      )}
      <div className={`w-full bg-gray-200 rounded-full overflow-hidden ${sizeClasses[size]}`}>
        <div
          className={`${colorClasses[color]} ${sizeClasses[size]} transition-all duration-300 ease-out`}
          style={{ width: `${clampedPercent}%` }}
        />
      </div>
    </div>
  )
}
