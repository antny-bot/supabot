const colorMap: Record<string, string> = {
  // user status
  active:   'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400',
  pending:  'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  inactive: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
  blocked:  'bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-400',
  deleted:  'bg-slate-200 text-slate-500 dark:bg-slate-800/60 dark:text-slate-500',
  // order status
  wait:            'bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-400',
  partial:         'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  done:            'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/30 dark:text-emerald-400',
  cancel:          'bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-400',
  pending_reorder: 'bg-violet-100 text-violet-800 dark:bg-violet-900/30 dark:text-violet-400',
  stoploss:        'bg-rose-200 text-rose-900 dark:bg-rose-900/40 dark:text-rose-300',
  // side (한국식: 매수=빨강/up, 매도=파랑/down)
  bid: 'bg-up-50 text-up-600 dark:bg-up-600/20 dark:text-up-400',
  ask: 'bg-down-50 text-down-600 dark:bg-down-600/20 dark:text-down-400',
  // event level
  error:   'bg-rose-100 text-rose-800 dark:bg-rose-900/30 dark:text-rose-400',
  warning: 'bg-amber-100 text-amber-800 dark:bg-amber-900/30 dark:text-amber-400',
  info:    'bg-sky-100 text-sky-800 dark:bg-sky-900/30 dark:text-sky-400',
  // exchange
  upbit:   'bg-orange-100 text-orange-800 dark:bg-orange-900/30 dark:text-orange-400',
  bithumb: 'bg-teal-100 text-teal-800 dark:bg-teal-900/30 dark:text-teal-400',
  kis:     'bg-primary-100 text-primary-800 dark:bg-primary-900/30 dark:text-primary-400',
}

const labelMap: Record<string, string> = {
  active: '활성', pending: '대기', inactive: '비활성', blocked: '차단', deleted: '삭제',
  wait: '대기', partial: '부분체결', done: '완료', cancel: '취소',
  pending_reorder: '재주문대기', stoploss: '손절',
  bid: '매수', ask: '매도',
  error: '오류', warning: '경고', info: '정보',
}

interface BadgeProps {
  value: string
  label?: string
  className?: string
}

export default function Badge({ value, label, className = '' }: BadgeProps) {
  const color = colorMap[value] ?? 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300'
  const text = label ?? labelMap[value] ?? value
  return (
    <span className={`inline-flex items-center whitespace-nowrap px-2 py-0.5 rounded-md text-app-caption font-medium ${color} ${className}`}>
      {text}
    </span>
  )
}
