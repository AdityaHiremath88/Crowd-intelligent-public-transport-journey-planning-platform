import { Info, TriangleAlert } from 'lucide-react'

export default function Notice({
  children,
  tone = 'info',
  title,
}: {
  children: React.ReactNode
  tone?: 'info' | 'warning'
  title?: string
}) {
  const Icon = tone === 'warning' ? TriangleAlert : Info
  return (
    <div className={`notice notice-${tone}`} role="status">
      <Icon size={18} aria-hidden="true" />
      <div>{title && <strong>{title}</strong>}<div>{children}</div></div>
    </div>
  )
}


