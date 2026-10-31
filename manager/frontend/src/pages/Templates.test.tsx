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

    const createBtn = await screen.findByRole('button', { name: /단일 종목 템플릿/i })
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

  it('opens multi-ticker TOP N modal directly and submits full TOP N payload', async () => {
    const { createTemplate } = await import('../api/templates')
    const user = userEvent.setup()

    render(
      <ToastProvider>
        <Templates />
      </ToastProvider>,
    )

    const createBtn = await screen.findByRole('button', { name: /복수 종목/i })
    await user.click(createBtn)

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

    // 템플릿 이름 입력
    const nameInput = screen.getByPlaceholderText(/코스피 시총 TOP 10/i)
    await user.type(nameInput, '코스피 5~10위 회전 전략')

    // 1단계 -> 2단계 이동 (순위 이탈 판정)
    const nextBtn1 = screen.getByRole('button', { name: /다음 단계/i })
    await user.click(nextBtn1)
    expect(screen.getByText(/순위 이탈 안전장치/i)).toBeInTheDocument()

    // 2단계 -> 3단계 이동 (예산 플랜)
    const nextBtn2 = screen.getByRole('button', { name: /다음 단계/i })
    await user.click(nextBtn2)
    expect(screen.getByText(/예산 운용 방식 선택/i)).toBeInTheDocument()

    // 3단계 -> 4단계 이동 (주문 집행 & 최종 요약)
    const nextBtn3 = screen.getByRole('button', { name: /다음 단계/i })
    await user.click(nextBtn3)
    expect(screen.getByText(/전략 템플릿 최종 설정 요약/i)).toBeInTheDocument()

    // 4단계에서 최종 검토 후 저장
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

  it('supports rank preset chips and previous/next step wizard navigation in TOP N modal', async () => {
    const user = userEvent.setup()

    render(
      <ToastProvider>
        <Templates />
      </ToastProvider>,
    )

    const createBtn = await screen.findByRole('button', { name: /복수 종목/i })
    await user.click(createBtn)

    // 이름 미입력 상태에서 '다음 단계' 클릭 시 에러 발생 및 스텝 유지
    const nextBtn1 = screen.getByRole('button', { name: /다음 단계/i })
    await user.click(nextBtn1)
    expect(screen.getByText('템플릿 이름을 입력하세요.')).toBeInTheDocument()

    // 프리셋 칩 'TOP 20 (1~20위)' 클릭 시 시작/종료 순위 및 티커 변경
    const presetTop20 = screen.getByRole('button', { name: 'TOP 20 (1~20위)' })
    await user.click(presetTop20)
    expect(screen.getByText(/KOSPI_TOP20/)).toBeInTheDocument()

    // 이름 입력 후 다음 단계 이동
    const nameInput = screen.getByPlaceholderText(/코스피 시총 TOP 10/i)
    await user.type(nameInput, '테스트 TOP 20')
    await user.click(nextBtn1)

    // Step 2 도달 확인 및 '이전 단계' 클릭으로 Step 1 복귀
    expect(screen.getByText(/순위 이탈 안전장치/i)).toBeInTheDocument()
    const prevBtn = screen.getByRole('button', { name: /이전 단계/i })
    await user.click(prevBtn)
    expect(screen.getByText(/타겟 순위 구간 선택/i)).toBeInTheDocument()
  })
})
