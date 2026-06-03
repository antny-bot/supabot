import { AlertCircle } from 'lucide-react'

export default function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="flex items-center gap-3 rounded-xl border border-rose-200 bg-rose-50 p-4 text-app-body-sm text-rose-700 dark:border-rose-800 dark:bg-rose-900/20 dark:text-rose-400">
      <AlertCircle size={16} className="shrink-0" />
      <span>{message}</span>
    </div>
  )
}
