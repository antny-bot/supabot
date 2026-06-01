// -*- coding: utf-8 -*-
import { useEffect, useState } from 'react'
import { Play, Trash2, Plus, Layers, Loader2 } from 'lucide-react'

interface Template {
  id: number
  user_id: string
  name: string
  exchange: string
  ticker: string
  start_price: number
  end_price: number
  count: number
  budget: number
  created_at: string
}

export default function Templates() {
  const [templates, setTemplates] = useState<Template[]>([])
  const [loading, setLoading] = useState(true)
  const [actionLoadingId, setActionLoadingId] = useState<number | null>(null)
  
  // 폼 상태
  const [name, setName] = useState('')
  const [exchange, setExchange] = useState('upbit')
  const [ticker, setTicker] = useState('KRW-BTC')
  const [startPrice, setStartPrice] = useState('')
  const [endPrice, setEndPrice] = useState('')
  const [count, setCount] = useState('10')
  const [budget, setBudget] = useState('100000')
  const [formOpen, setFormOpen] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    loadTemplates()
  }, [])

  async function loadTemplates() {
    try {
      setLoading(true)
      const res = await fetch('/api/templates')
      if (res.ok) {
        const data = await res.json()
        setTemplates(data)
      } else {
        setError('템플릿을 불러오는 데 실패했습니다.')
      }
    } catch {
      setError('네트워크 오류가 발생했습니다.')
    } finally {
      setLoading(false)
    }
  }

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault()
    setError(null)

    if (!name.trim()) {
      setError('템플릿 이름을 입력해 주세요.')
      return
    }

    try {
      const res = await fetch('/api/templates', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          name: name.trim(),
          exchange,
          ticker: ticker.trim().toUpperCase(),
          start_price: parseFloat(startPrice),
          end_price: parseFloat(endPrice),
          count: parseInt(count),
          budget: parseFloat(budget),
        }),
      })

      if (res.ok) {
        // 폼 초기화
        setName('')
        setStartPrice('')
        setEndPrice('')
        setFormOpen(false)
        loadTemplates()
      } else {
        const data = await res.json()
        setError(data.error || '템플릿 생성 실패')
      }
    } catch {
      setError('네트워크 오류가 발생했습니다.')
    }
  }

  async function handleDelete(id: number) {
    if (!confirm('정말로 이 템플릿을 삭제하시겠습니까?')) return
    setError(null)
    setActionLoadingId(id)

    try {
      const res = await fetch(`/api/templates/${id}`, { method: 'DELETE' })
      if (res.ok) {
        loadTemplates()
      } else {
        const data = await res.json()
        setError(data.error || '템플릿 삭제 실패')
      }
    } catch {
      setError('네트워크 오류가 발생했습니다.')
    } finally {
      setActionLoadingId(null)
    }
  }

  async function handleExecute(id: number) {
    if (!confirm('이 템플릿으로 거미줄 분할 매수를 즉시 실행하시겠습니까?')) return
    setError(null)
    setActionLoadingId(id)

    try {
      const res = await fetch(`/api/templates/${id}/execute`, { method: 'POST' })
      const data = await res.json()
      if (res.ok) {
        alert(data.message || '거미줄 분할 주문이 성공적으로 가동되었습니다.')
      } else {
        setError(data.error || '실행 실패')
      }
    } catch {
      setError('네트워크 오류가 발생했습니다.')
    } finally {
      setActionLoadingId(null)
    }
  }

  return (
    <div className="space-y-6 max-w-screen-xl mx-auto px-4 pb-20">
      {/* 타이틀 및 템플릿 추가 버튼 */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-xl font-bold text-slate-900 dark:text-white flex items-center gap-2">
            <Layers className="text-indigo-600 dark:text-indigo-400" />
            거미줄 전략 템플릿
          </h2>
          <p className="text-xs text-slate-500 dark:text-slate-400 mt-1">
            자주 사용하는 거미줄 분할 매수 설정을 템플릿으로 저장하고 원클릭으로 실행합니다.
          </p>
        </div>
        <button
          onClick={() => setFormOpen(!formOpen)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors"
        >
          <Plus size={14} />
          템플릿 생성
        </button>
      </div>

      {error && (
        <div className="bg-rose-50 dark:bg-rose-950/20 border border-rose-200 dark:border-rose-900/50 rounded-xl p-3 text-xs text-rose-600 dark:text-rose-400">
          ⚠️ {error}
        </div>
      )}

      {/* 템플릿 작성 폼 */}
      {formOpen && (
        <form onSubmit={handleCreate} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 space-y-4 shadow-sm">
          <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-200 border-b border-slate-100 dark:border-slate-800 pb-2">신규 템플릿 작성</h3>
          
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <div className="space-y-1">
              <label className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">템플릿 이름</label>
              <input
                type="text"
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="예: 비트코인 3분할 매수"
                className="w-full px-3 py-1.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-xs text-slate-900 dark:text-white focus:outline-none focus:ring-1 focus:ring-indigo-500"
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">거래소</label>
                <select
                  value={exchange}
                  onChange={(e) => setExchange(e.target.value)}
                  className="w-full px-3 py-1.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-xs text-slate-900 dark:text-white focus:outline-none"
                >
                  <option value="upbit">Upbit</option>
                  <option value="bithumb">Bithumb</option>
                  <option value="kis">한투 (KIS)</option>
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">종목</label>
                <input
                  type="text"
                  value={ticker}
                  onChange={(e) => setTicker(e.target.value)}
                  placeholder="KRW-BTC"
                  className="w-full px-3 py-1.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-xs text-slate-900 dark:text-white focus:outline-none"
                  required
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">시작 가격</label>
                <input
                  type="number"
                  step="any"
                  value={startPrice}
                  onChange={(e) => setStartPrice(e.target.value)}
                  placeholder="예: 95000000"
                  className="w-full px-3 py-1.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-xs text-slate-900 dark:text-white focus:outline-none"
                  required
                />
              </div>
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">종료 가격</label>
                <input
                  type="number"
                  step="any"
                  value={endPrice}
                  onChange={(e) => setEndPrice(e.target.value)}
                  placeholder="예: 90000000"
                  className="w-full px-3 py-1.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-xs text-slate-900 dark:text-white focus:outline-none"
                  required
                />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">주문 개수 (분할 수)</label>
                <input
                  type="number"
                  value={count}
                  onChange={(e) => setCount(e.target.value)}
                  placeholder="10"
                  className="w-full px-3 py-1.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-xs text-slate-900 dark:text-white focus:outline-none"
                  required
                />
              </div>
              <div className="space-y-1">
                <label className="text-[11px] font-semibold text-slate-500 dark:text-slate-400">총 예산 (KRW)</label>
                <input
                  type="number"
                  value={budget}
                  onChange={(e) => setBudget(e.target.value)}
                  placeholder="100000"
                  className="w-full px-3 py-1.5 bg-slate-50 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 rounded-lg text-xs text-slate-900 dark:text-white focus:outline-none"
                  required
                />
              </div>
            </div>
          </div>

          <div className="flex justify-end gap-2 pt-2 border-t border-slate-100 dark:border-slate-800">
            <button
              type="button"
              onClick={() => setFormOpen(false)}
              className="px-3 py-1.5 bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 rounded-lg text-xs font-semibold hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
            >
              취소
            </button>
            <button
              type="submit"
              className="px-3 py-1.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors"
            >
              저장하기
            </button>
          </div>
        </form>
      )}

      {/* 로딩 표시 */}
      {loading ? (
        <div className="flex justify-center py-12">
          <Loader2 className="animate-spin text-slate-400" />
        </div>
      ) : templates.length === 0 ? (
        <div className="bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 p-12 text-center text-slate-400 dark:text-slate-500 text-xs">
          등록된 템플릿이 없습니다. 우측 상단의 '템플릿 생성' 버튼으로 추가해 보세요.
        </div>
      ) : (
        <>
          {/* 데스크톱 목록 뷰 (hidden md:block) */}
          <div className="hidden md:block bg-white dark:bg-slate-900 rounded-xl border border-slate-200 dark:border-slate-800 overflow-hidden shadow-sm">
            <table className="w-full text-sm">
              <thead>
                <tr className="text-xs text-slate-500 dark:text-slate-400 bg-slate-50 dark:bg-slate-900 border-b border-slate-100 dark:border-slate-800">
                  <th className="px-4 py-3 text-left font-medium">이름</th>
                  <th className="px-4 py-3 text-left font-medium">거래소</th>
                  <th className="px-4 py-3 text-left font-medium">종목</th>
                  <th className="px-4 py-3 text-right font-medium">시작 가격</th>
                  <th className="px-4 py-3 text-right font-medium">종료 가격</th>
                  <th className="px-4 py-3 text-right font-medium">분할 수</th>
                  <th className="px-4 py-3 text-right font-medium">총 예산</th>
                  <th className="px-4 py-3 text-center font-medium">액션</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                {templates.map((tpl) => (
                  <tr key={tpl.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/40 transition-colors">
                    <td className="px-4 py-3 font-semibold text-slate-800 dark:text-slate-200">{tpl.name}</td>
                    <td className="px-4 py-3">
                      <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-medium bg-slate-100 dark:bg-slate-800 text-slate-800 dark:text-slate-300 uppercase">
                        {tpl.exchange}
                      </span>
                    </td>
                    <td className="px-4 py-3 font-mono text-xs text-slate-700 dark:text-slate-300">{tpl.ticker}</td>
                    <td className="px-4 py-3 text-right font-mono text-xs text-slate-700 dark:text-slate-300">{tpl.start_price.toLocaleString()}원</td>
                    <td className="px-4 py-3 text-right font-mono text-xs text-slate-700 dark:text-slate-300">{tpl.end_price.toLocaleString()}원</td>
                    <td className="px-4 py-3 text-right font-mono text-xs text-slate-700 dark:text-slate-300">{tpl.count}회</td>
                    <td className="px-4 py-3 text-right font-semibold font-mono text-xs text-indigo-600 dark:text-indigo-400">{tpl.budget.toLocaleString()}원</td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-center gap-2">
                        <button
                          onClick={() => handleExecute(tpl.id)}
                          disabled={actionLoadingId !== null}
                          className="flex items-center gap-1 px-2.5 py-1 bg-emerald-600 hover:bg-emerald-700 text-white rounded text-xs font-medium disabled:opacity-50 transition-colors"
                        >
                          <Play size={12} />
                          가동
                        </button>
                        <button
                          onClick={() => handleDelete(tpl.id)}
                          disabled={actionLoadingId !== null}
                          className="p-1 text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-900/20 rounded disabled:opacity-50 transition-colors"
                        >
                          <Trash2 size={14} />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* 모바일 리스트 뷰 (block md:hidden) */}
          <div className="block md:hidden space-y-3">
            {templates.map((tpl) => (
              <div key={tpl.id} className="bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 rounded-xl p-4 shadow-sm space-y-3">
                <div className="flex items-center justify-between border-b border-slate-100 dark:border-slate-800 pb-2">
                  <div>
                    <h4 className="text-sm font-bold text-slate-800 dark:text-slate-200">{tpl.name}</h4>
                    <p className="text-[10px] text-slate-400 dark:text-slate-500 mt-0.5">
                      {tpl.exchange.toUpperCase()} • <span className="font-mono">{tpl.ticker}</span>
                    </p>
                  </div>
                  <button
                    onClick={() => handleDelete(tpl.id)}
                    disabled={actionLoadingId !== null}
                    className="p-1 text-slate-400 hover:text-rose-600 dark:hover:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-900/20 rounded disabled:opacity-50"
                  >
                    <Trash2 size={14} />
                  </button>
                </div>

                <div className="grid grid-cols-2 gap-2 text-xs">
                  <div>
                    <span className="text-[10px] text-slate-400">범위</span>
                    <p className="font-mono text-slate-700 dark:text-slate-300">
                      {tpl.start_price.toLocaleString()} ~ {tpl.end_price.toLocaleString()}원
                    </p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400">분할 수</span>
                    <p className="font-mono text-slate-700 dark:text-slate-300">{tpl.count}회</p>
                  </div>
                  <div>
                    <span className="text-[10px] text-slate-400">총 예산</span>
                    <p className="font-bold font-mono text-indigo-600 dark:text-indigo-400">{tpl.budget.toLocaleString()}원</p>
                  </div>
                </div>

                <button
                  onClick={() => handleExecute(tpl.id)}
                  disabled={actionLoadingId !== null}
                  className="w-full flex items-center justify-center gap-1.5 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-semibold shadow-sm transition-colors"
                >
                  <Play size={12} />
                  전략 즉시 가동
                </button>
              </div>
            ))}
          </div>
        </>
      )}
    </div>
  )
}
