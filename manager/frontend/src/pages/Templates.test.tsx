import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { ToastProvider } from '../contexts/ToastContext'
import Templates from './Templates'

vi.mock('../api/templates', () => ({
  fetchTemplates: vi.fn().mockResolvedValue([]),
  createTemplate: vi.fn().mockResolvedValue({}),
  updateTemplate: vi.fn().mockResolvedValue({}),
  deleteTemplate: vi.fn().mockResolvedValue({}),
  duplicateTemplate: vi.fn().mockResolvedValue({}),
  executeTemplate: vi.fn().mockResolvedValue({}),
}))

vi.mock('../api/stockCache', () => ({
  fetchStockCache: vi.fn().mockResolvedValue([
    { name: '고려아연', code: '010130', updated_at: '2026-01-01T00:00:00' },
    { name: '고려제강', code: '002240', updated_at: '2026-01-01T00:00:00' },
    { name: '삼성전자', code: '005930', updated_at: '2026-01-01T00:00:00' },
  ]),
}))

describe('Templates stock cache combobox', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  afterEach(() => {
    cleanup()
  })

  it('filters stock list on typing when exchange is KIS or Toss and selects on click or Enter when 1 match', async () => {
    const user = userEvent.setup()

    render(
      <ToastProvider>
        <Templates />
      </ToastProvider>,
    )

    const createBtn = await screen.findByRole('button', { name: /신규 전략 템플릿/i })
    await user.click(createBtn)

    const exchangeSelect = screen.getByLabelText('거래소')
    await user.selectOptions(exchangeSelect, 'kis')

    const tickerInput = screen.getByLabelText('종목 코드 (티커)') as HTMLInputElement
    expect(tickerInput.value).toBe('')

    // '고려' 입력 시 2개 종목 필터링
    await user.type(tickerInput, '고려')
    const listbox = screen.getByRole('listbox', { name: '종목 검색 결과' })
    const options = within(listbox).getAllByRole('option')
    expect(options).toHaveLength(2)
    expect(within(listbox).getByText('고려아연')).toBeInTheDocument()
    expect(within(listbox).getByText('고려제강')).toBeInTheDocument()
    expect(within(listbox).queryByText('삼성전자')).not.toBeInTheDocument()

    // '아연' 추가 입력 시 1개 종목만 남고 Enter 입력 시 즉시 종목 코드 반영
    await user.type(tickerInput, '아연{Enter}')
    expect(tickerInput.value).toBe('010130')
    expect(screen.getByText('고려아연')).toBeInTheDocument()
    expect(screen.queryByRole('listbox', { name: '종목 검색 결과' })).not.toBeInTheDocument()

    // 토스증권에서도 동일하게 동작 및 클릭 선택 확인
    await user.selectOptions(exchangeSelect, 'toss')
    await user.clear(tickerInput)
    await user.type(tickerInput, '고려')
    const tossListbox = screen.getByRole('listbox', { name: '종목 검색 결과' })
    await user.click(within(tossListbox).getByText('고려제강'))
    expect(tickerInput.value).toBe('002240')
    expect(screen.getByText('고려제강')).toBeInTheDocument()
  })

  it('switches modal layout when kospi_top_dca is selected and submits full TOP N payload', async () => {
    const { createTemplate } = await import('../api/templates')
    const user = userEvent.setup()

    render(
      <ToastProvider>
        <Templates />
      </ToastProvider>,
    )

    const createBtn = await screen.findByRole('button', { name: /신규 전략 템플릿/i })
    await user.click(createBtn)

    const strategySelect = screen.getByLabelText('전략 유형')
    await user.selectOptions(strategySelect, 'kospi_top_dca')

    // 종목 코드 입력창 대신 대상 시장 드롭다운과 TOP N 전용 섹션이 표시되어야 함
    expect(screen.queryByLabelText('종목 코드 (티커)')).not.toBeInTheDocument()
    const marketSelect = screen.getByLabelText('대상 시장') as HTMLSelectElement
    expect(marketSelect.value).toBe('KOSPI')

    // 순위 구간을 5위 ~ 10위로 변경 시 자동 티커가 KOSPI_TOP5_10으로 표시됨
    const rankStartInput = screen.getByLabelText('타겟 시작 순위')
    const rankEndInput = screen.getByLabelText('타겟 종료 순위')
    await user.clear(rankStartInput)
    await user.type(rankStartInput, '5')
    await user.clear(rankEndInput)
    await user.type(rankEndInput, '10')
    expect(screen.getByText(/KOSPI_TOP5_10/)).toBeInTheDocument()

    // 템플릿 이름 입력 후 저장
    const nameInput = screen.getByPlaceholderText(/코스피 시총 TOP 10/i)
    await user.type(nameInput, '코스피 5~10위 회전 전략')

    const saveBtn = screen.getByRole('button', { name: /저장하기/i })
    await user.click(saveBtn)

    expect(createTemplate).toHaveBeenCalledWith(
      expect.objectContaining({
        name: '코스피 5~10위 회전 전략',
        exchange: 'toss',
        ticker: 'KOSPI_TOP5_10',
        count: 6,
        strategy_type: 'kospi_top_dca',
        params: expect.objectContaining({
          market: 'KOSPI',
          rank_start: 5,
          rank_end: 10,
          top_n: 10,
          exclude_preferred: true,
          upper_exit_mode: 'sell_on_any_exit',
          exit_rank_buffer: 2,
          exit_confirm_days: 2,
          sell_split_days: 5,
          budget_mode: 'monthly',
          monthly_budget: 3000000,
          trading_days_per_month: 20,
          cycle_alloc_mode: 'one_share',
          sell_proceeds_mode: 'keep_cash',
          order_price_mode: 'limit_current',
          schedule_enabled: true,
          is_dry_run: false,
          schedule_time: '09:10',
        }),
      }),
    )
  })
})
