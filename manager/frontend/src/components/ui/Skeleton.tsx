import type { HTMLAttributes } from 'react'

export function Skeleton({ className = '', ...props }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`animate-pulse rounded-md bg-slate-200/80 dark:bg-slate-800/80 ${className}`}
      {...props}
    />
  )
}

export function StatCardSkeleton() {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900">
      <div className="flex items-center justify-between">
        <Skeleton className="h-4 w-20" />
        <Skeleton className="h-7 w-7 rounded-lg" />
      </div>
      <div className="mt-3">
        <Skeleton className="h-7 w-32" />
        <Skeleton className="mt-2 h-3.5 w-16" />
      </div>
    </div>
  )
}

export function TableRowSkeleton({ cols = 6 }: { cols?: number }) {
  return (
    <tr className="animate-pulse">
      {Array.from({ length: cols }).map((_, i) => (
        <td key={i} className="px-4 py-3.5">
          <Skeleton className="h-4 w-full max-w-[120px]" />
        </td>
      ))}
    </tr>
  )
}

export function CardSkeleton({ className = '' }: { className?: string }) {
  return (
    <div className={`space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm dark:border-slate-800 dark:bg-slate-900 ${className}`}>
      <div className="flex items-center justify-between">
        <Skeleton className="h-5 w-28" />
        <Skeleton className="h-4 w-12" />
      </div>
      <Skeleton className="h-24 w-full rounded-lg" />
      <div className="flex justify-between pt-1">
        <Skeleton className="h-3 w-20" />
        <Skeleton className="h-3 w-16" />
      </div>
    </div>
  )
}

export function TableSkeleton({
  rows = 5,
  cols = 6,
  showHeader = true,
  className = '',
}: {
  rows?: number
  cols?: number
  showHeader?: boolean
  className?: string
}) {
  return (
    <div className={`overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm dark:border-slate-800 dark:bg-slate-900 ${className}`}>
      {showHeader && (
        <div className="flex items-center justify-between border-b border-slate-100 p-4 dark:border-slate-800">
          <Skeleton className="h-5 w-32" />
          <div className="flex items-center gap-2">
            <Skeleton className="h-8 w-24 rounded-lg" />
            <Skeleton className="h-8 w-20 rounded-lg" />
          </div>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 font-semibold dark:border-slate-800 dark:bg-slate-900/80">
              {Array.from({ length: cols }).map((_, i) => (
                <th key={i} className="px-4 py-3">
                  <Skeleton className="h-3.5 w-16" />
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
            {Array.from({ length: rows }).map((_, i) => (
              <TableRowSkeleton key={i} cols={cols} />
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}

export function ChartSkeleton({
  height = 'h-60',
  title = true,
  className = '',
}: {
  height?: string
  title?: boolean
  className?: string
}) {
  return (
    <div className={`rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 ${className}`}>
      {title && (
        <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <Skeleton className="h-4 w-4 rounded" />
            <Skeleton className="h-4 w-32" />
          </div>
          <Skeleton className="h-3 w-16" />
        </div>
      )}
      <div className={`mt-4 flex w-full items-end gap-3 ${height}`}>
        {Array.from({ length: 8 }).map((_, i) => {
          const heights = ['h-24', 'h-40', 'h-32', 'h-48', 'h-28', 'h-52', 'h-36', 'h-44']
          return (
            <div key={i} className="flex flex-1 flex-col items-center gap-2">
              <Skeleton className={`w-full rounded-t ${heights[i % heights.length]}`} />
              <Skeleton className="h-2.5 w-8" />
            </div>
          )
        })}
      </div>
    </div>
  )
}

export function DonutChartSkeleton({
  title = true,
  className = '',
}: {
  title?: boolean
  className?: string
}) {
  return (
    <div className={`rounded-xl border border-slate-200 bg-white p-5 shadow-sm dark:border-slate-800 dark:bg-slate-900 ${className}`}>
      {title && (
        <div className="flex items-center justify-between border-b border-slate-100 pb-3 dark:border-slate-800">
          <div className="flex items-center gap-2">
            <Skeleton className="h-4 w-4 rounded" />
            <Skeleton className="h-4 w-28" />
          </div>
          <Skeleton className="h-3 w-12" />
        </div>
      )}
      <div className="mt-4 flex h-60 flex-col items-center justify-center gap-4">
        <Skeleton className="h-36 w-36 rounded-full" />
        <div className="flex flex-wrap justify-center gap-2">
          <Skeleton className="h-4 w-16 rounded-full" />
          <Skeleton className="h-4 w-14 rounded-full" />
          <Skeleton className="h-4 w-18 rounded-full" />
        </div>
      </div>
    </div>
  )
}

export function ListSkeleton({
  count = 4,
  className = '',
}: {
  count?: number
  className?: string
}) {
  return (
    <div className={`divide-y divide-slate-100 rounded-xl border border-slate-200 bg-white shadow-sm dark:divide-slate-800 dark:border-slate-800 dark:bg-slate-900 ${className}`}>
      {Array.from({ length: count }).map((_, i) => (
        <div key={i} className="flex items-center justify-between p-4">
          <div className="flex items-center gap-3">
            <Skeleton className="h-9 w-9 rounded-lg" />
            <div className="space-y-1.5">
              <Skeleton className="h-4 w-32" />
              <Skeleton className="h-3 w-20" />
            </div>
          </div>
          <Skeleton className="h-6 w-16 rounded-md" />
        </div>
      ))}
    </div>
  )
}

export function FormSkeleton({ className = '' }: { className?: string }) {
  return (
    <div className={`space-y-5 rounded-xl border border-slate-200 bg-white p-6 shadow-sm dark:border-slate-800 dark:bg-slate-900 ${className}`}>
      <div className="space-y-2">
        <Skeleton className="h-5 w-36" />
        <Skeleton className="h-3.5 w-60" />
      </div>
      <div className="space-y-4 pt-2">
        <div className="space-y-1.5">
          <Skeleton className="h-3.5 w-20" />
          <Skeleton className="h-9 w-full rounded-lg" />
        </div>
        <div className="space-y-1.5">
          <Skeleton className="h-3.5 w-24" />
          <Skeleton className="h-9 w-full rounded-lg" />
        </div>
        <div className="space-y-1.5">
          <Skeleton className="h-3.5 w-16" />
          <Skeleton className="h-20 w-full rounded-lg" />
        </div>
      </div>
      <div className="flex justify-end gap-2 pt-2">
        <Skeleton className="h-9 w-20 rounded-lg" />
        <Skeleton className="h-9 w-24 rounded-lg" />
      </div>
    </div>
  )
}

export function PageSkeleton() {
  return (
    <div className="space-y-5">
      {/* Page Header Skeleton */}
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Skeleton className="h-10 w-10 rounded-xl" />
          <Skeleton className="h-7 w-40" />
        </div>
        <Skeleton className="h-9 w-24 rounded-lg" />
      </div>

      {/* 4 Stat Cards */}
      <div className="grid grid-cols-2 gap-3 md:grid-cols-4 md:gap-4">
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
        <StatCardSkeleton />
      </div>

      {/* Main Content Area */}
      <div className="grid gap-4 md:grid-cols-12">
        <div className="md:col-span-8">
          <ChartSkeleton height="h-64" />
        </div>
        <div className="md:col-span-4">
          <CardSkeleton className="h-full" />
        </div>
      </div>
    </div>
  )
}
