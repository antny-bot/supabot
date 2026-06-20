import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react'

interface PaginationProps {
  currentPage: number
  totalPages: number
  pageSize: number
  totalCount: number
  onPageChange: (page: number) => void
  onPageSizeChange?: (size: number) => void
  pageSizeOptions?: number[]
}

export default function Pagination({
  currentPage,
  totalPages,
  pageSize,
  totalCount,
  onPageChange,
  onPageSizeChange,
  pageSizeOptions = [10, 20, 50, 100],
}: PaginationProps) {
  if (totalPages <= 1 && !onPageSizeChange) return null

  // Calculate the page range to display (up to 5 page numbers centered around current page)
  const getPageNumbers = () => {
    const range = []
    const start = Math.max(1, currentPage - 2)
    const end = Math.min(totalPages, currentPage + 2)

    for (let i = start; i <= end; i++) {
      range.push(i)
    }
    return range
  }

  const pageNumbers = getPageNumbers()

  return (
    <div className="flex flex-col sm:flex-row items-center justify-between gap-4 border-t border-slate-100 bg-slate-50 px-4 py-3 dark:border-slate-800 dark:bg-slate-900 text-xs text-slate-500 dark:text-slate-400">
      {/* Left side: total count and optional page size selector */}
      <div className="flex items-center gap-3">
        {onPageSizeChange && (
          <div className="flex items-center gap-1.5">
            <span>목록 개수:</span>
            <select
              value={pageSize}
              onChange={(e) => onPageSizeChange(Number(e.target.value))}
              className="rounded border border-slate-200 bg-white px-2 py-1 outline-none dark:border-slate-700 dark:bg-slate-800 text-slate-700 dark:text-slate-300 focus:border-primary-500"
            >
              {pageSizeOptions.map((opt) => (
                <option key={opt} value={opt}>
                  {opt}개씩
                </option>
              ))}
            </select>
          </div>
        )}
        <span>
          전체 <span className="font-semibold text-slate-700 dark:text-slate-300">{totalCount.toLocaleString()}</span>건
        </span>
      </div>

      {/* Right side: navigation buttons */}
      <div className="flex items-center gap-1">
        {/* First page */}
        <button
          onClick={() => onPageChange(1)}
          disabled={currentPage === 1}
          className="rounded-lg border border-slate-200 bg-white p-1.5 transition-colors hover:bg-slate-50 disabled:opacity-30 disabled:hover:bg-white dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700/50"
          title="첫 페이지"
        >
          <ChevronsLeft size={14} />
        </button>

        {/* Previous page */}
        <button
          onClick={() => onPageChange(Math.max(1, currentPage - 1))}
          disabled={currentPage === 1}
          className="rounded-lg border border-slate-200 bg-white p-1.5 transition-colors hover:bg-slate-50 disabled:opacity-30 disabled:hover:bg-white dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700/50"
        >
          <ChevronLeft size={14} />
        </button>

        {/* Page numbers */}
        <div className="flex gap-1 mx-1">
          {pageNumbers[0] > 1 && <span className="px-1.5 py-1 text-slate-400">...</span>}
          {pageNumbers.map((num) => (
            <button
              key={num}
              onClick={() => onPageChange(num)}
              className={`min-w-[28px] h-7 rounded-lg text-center font-medium transition-colors ${
                currentPage === num
                  ? 'bg-indigo-600 text-white dark:bg-indigo-500'
                  : 'border border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300 dark:hover:bg-slate-700/50'
              }`}
            >
              {num}
            </button>
          ))}
          {pageNumbers[pageNumbers.length - 1] < totalPages && <span className="px-1.5 py-1 text-slate-400">...</span>}
        </div>

        {/* Next page */}
        <button
          onClick={() => onPageChange(Math.min(totalPages, currentPage + 1))}
          disabled={currentPage === totalPages}
          className="rounded-lg border border-slate-200 bg-white p-1.5 transition-colors hover:bg-slate-50 disabled:opacity-30 disabled:hover:bg-white dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700/50"
        >
          <ChevronRight size={14} />
        </button>

        {/* Last page */}
        <button
          onClick={() => onPageChange(totalPages)}
          disabled={currentPage === totalPages}
          className="rounded-lg border border-slate-200 bg-white p-1.5 transition-colors hover:bg-slate-50 disabled:opacity-30 disabled:hover:bg-white dark:border-slate-700 dark:bg-slate-800 dark:hover:bg-slate-700/50"
          title="마지막 페이지"
        >
          <ChevronsRight size={14} />
        </button>
      </div>
    </div>
  )
}
