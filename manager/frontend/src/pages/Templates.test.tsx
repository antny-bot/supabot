import { cleanup, render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest'
import { MemoryRouter } from 'react-router-dom'
import { ToastProvider } from '../contexts/ToastContext'
import Templates from './Templates'

vi.mock('../api/templates', () => ({
  fetchTemplates: vi.fn().mockResolvedValue([]),
  createTemplate: vi.fn().mockResolvedValue({}),
  updateTemplate: vi.fn().mockResolvedValue({}),
  deleteTemplate: vi.fn().mockResolvedValue({}),
  archiveTemplate: vi.fn().mockResolvedValue({ ok: true, message: '보관되었습니다.' }),
  restoreTemplate: vi.fn().mockResolvedValue({ ok: true, message: '복원되었습니다.' }),
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
      <MemoryRouter>
        <ToastProvider>
          <Templates />
        </ToastProvider>
      </MemoryRouter>,
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

    // TOSS에서도 동일하게 동작 및 클릭 선택 확인
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
      <MemoryRouter>
        <ToastProvider>
          <Templates />
        </ToastProvider>
      </MemoryRouter>,
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
      <MemoryRouter>
        <ToastProvider>
          <Templates />
        </ToastProvider>
      </MemoryRouter>,
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

  it('does not auto-submit or close modal when entering step 4 during multi-ticker template edit', async () => {
    const { fetchTemplates, updateTemplate } = await import('../api/templates')
    vi.mocked(fetchTemplates).mockResolvedValueOnce([
      {
        id: 'tpl-top-1',
        name: '기존 시총 TOP 10 전략',
        exchange: 'toss',
        ticker: 'KOSPI_TOP10',
        budget: 3000000,
        count: 10,
        start_price: 0,
        end_price: 0,
        strategy_type: 'kospi_top_dca',
        params: {
          market: 'KOSPI',
          rank_start: 1,
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
        },
      } as any,
    ])

    const user = userEvent.setup()

    render(
      <MemoryRouter>
        <ToastProvider>
          <Templates />
        </ToastProvider>
      </MemoryRouter>,
    )

    // 수정 버튼 클릭하여 모달 오픈
    const editBtn = await screen.findByTitle('수정')
    await user.click(editBtn)
    expect(screen.getByText('복수 종목 전략 템플릿 수정')).toBeInTheDocument()

    // 1 -> 2 -> 3 -> 4단계로 이동
    await user.click(screen.getByRole('button', { name: /다음 단계/i }))
    await user.click(screen.getByRole('button', { name: /다음 단계/i }))
    await user.click(screen.getByRole('button', { name: /다음 단계/i }))

    // 4단계 도달 시 자동 확정(updateTemplate)이 일어나지 않고 모달이 열린 상태여야 함
    expect(screen.getByText(/전략 템플릿 최종 설정 요약/i)).toBeInTheDocument()
    expect(updateTemplate).not.toHaveBeenCalled()

    // 4단계 입력창에서 Enter를 눌러도 자동 확정되지 않아야 함
    const timeInput = screen.getByLabelText('매일 실행 시각')
    await user.clear(timeInput)
    await user.type(timeInput, '09:15{Enter}')
    expect(updateTemplate).not.toHaveBeenCalled()
    expect(screen.getByText('복수 종목 전략 템플릿 수정')).toBeInTheDocument()

    // 명시적으로 저장 버튼 클릭 시에만 확정 및 저장 호출
    const saveBtn = screen.getByRole('button', { name: /수정 저장하기/i })
    await user.click(saveBtn)
    expect(updateTemplate).toHaveBeenCalledTimes(1)
  })

  it('formats amount inputs with thousand commas in single template modal and sends clean numbers', async () => {
    const { createTemplate } = await import('../api/templates')
    const user = userEvent.setup()

    render(
      <MemoryRouter>
        <ToastProvider>
          <Templates />
        </ToastProvider>
      </MemoryRouter>,
    )

    const createBtn = await screen.findByRole('button', { name: /단일 종목 템플릿/i })
    await user.click(createBtn)

    expect(screen.getByText('단일 종목 전략 템플릿 만들기')).toBeInTheDocument()

    // 템플릿 이름 입력
    const nameInput = screen.getByPlaceholderText(/비트코인 매일 5만원/i)
    await user.type(nameInput, '비트코인 거미줄')

    // 투자 예산 입력 시 콤마 표시 검증
    const budgetInput = screen.getByLabelText('투자 예산') as HTMLInputElement
    await user.clear(budgetInput)
    await user.type(budgetInput, '1500000')
    expect(budgetInput.value).toBe('1,500,000')

    // 시작/종료 가격 입력 시 콤마 표시 검증
    const startPriceInput = screen.getByLabelText('시작 가격') as HTMLInputElement
    await user.clear(startPriceInput)
    await user.type(startPriceInput, '80000000')
    expect(startPriceInput.value).toBe('80,000,000')

    const endPriceInput = screen.getByLabelText('종료 가격') as HTMLInputElement
    await user.clear(endPriceInput)
    await user.type(endPriceInput, '90000000')
    expect(endPriceInput.value).toBe('90,000,000')

    // 폼 저장 시 숫자로 파싱되어 createTemplate에 전달되는지 확인
    const submitBtn = screen.getByRole('button', { name: /저장하기/i })
    await user.click(submitBtn)

    expect(createTemplate).toHaveBeenCalledWith(
      expect.objectContaining({
        name: '비트코인 거미줄',
        budget: 1500000,
        start_price: 80000000,
        end_price: 90000000,
      })
    )
  })

  it('correctly updates RSI range when modifying an RSI strategy template', async () => {
    const { fetchTemplates, updateTemplate } = await import('../api/templates')
    vi.mocked(fetchTemplates).mockResolvedValueOnce([
      {
        id: 77,
        user_id: 'u1',
        name: '비트코인 RSI 순환',
        exchange: 'upbit',
        ticker: 'KRW-BTC',
        strategy_type: 'rsitrade',
        start_price: 0,
        end_price: 0,
        count: 10,
        budget: 2000000,
        is_holding: false,
        created_at: 1700000000,
        params: {
          buy_rsi_range: '35-40',
          sell_rsi_range: '65-75',
          weighted: false,
        },
      } as any,
    ])

    const user = userEvent.setup()

    render(
      <MemoryRouter>
        <ToastProvider>
          <Templates />
        </ToastProvider>
      </MemoryRouter>,
    )

    // 수정 버튼 클릭
    const editBtn = await screen.findByTitle('수정')
    await user.click(editBtn)
    expect(screen.getByText('단일 종목 전략 템플릿 수정')).toBeInTheDocument()

    // 기존 RSI 확인 및 30-35로 변경
    const buyRsiInput = screen.getByPlaceholderText('25-30') as HTMLInputElement
    expect(buyRsiInput.value).toBe('35-40')
    await user.clear(buyRsiInput)
    await user.type(buyRsiInput, '30-35')

    // 수정 저장
    const saveBtn = screen.getByRole('button', { name: /저장하기/i })
    await user.click(saveBtn)

    expect(updateTemplate).toHaveBeenCalledWith(
      77,
      expect.objectContaining({
        strategy_type: 'rsitrade',
        params: expect.objectContaining({
          buy_rsi_range: '30-35',
          sell_rsi_range: '65-75',
        }),
      })
    )
  })

  it('disables archive button when strategy is active, and provides restore/delete in archived tab', async () => {
    const user = userEvent.setup()
    const { fetchTemplates } = await import('../api/templates')
    ;(fetchTemplates as any).mockResolvedValueOnce([
      {
        id: 88,
        user_id: 'test_user',
        name: '실행중인 전략',
        exchange: 'kis',
        ticker: '005930',
        start_price: 50000,
        end_price: 70000,
        count: 10,
        budget: 1000000,
        strategy_type: 'grid',
        created_at: '2026-01-01T00:00:00',
        params: {
          strategy_status: 'active',
          schedule_enabled: true,
        },
      },
      {
        id: 99,
        user_id: 'test_user',
        name: '보관된 전략',
        exchange: 'kis',
        ticker: '000660',
        start_price: 150000,
        end_price: 200000,
        count: 10,
        budget: 2000000,
        strategy_type: 'grid',
        created_at: '2026-01-01T00:00:00',
        params: {
          is_archived: true,
          strategy_status: 'paused',
        },
      },
    ])

    render(
      <MemoryRouter>
        <ToastProvider>
          <Templates />
        </ToastProvider>
      </MemoryRouter>,
    )

    // 1. 운용 전략 탭: 실행 중인 전략 카드의 보관 버튼은 disabled
    const archiveBtn = await screen.findByTitle('실행 중인 전략은 보관할 수 없습니다. 먼저 중지(OFF)하세요.')
    expect(archiveBtn).toBeInTheDocument()
    expect(archiveBtn).toBeDisabled()

    // 2. 보관함 탭으로 전환
    const archiveTabBtn = screen.getByRole('button', { name: /보관함/i })
    await user.click(archiveTabBtn)

    // 3. 보관함 탭에서는 '보관된 전략'이 렌더링되고 복원 및 영구 삭제 버튼이 제공됨
    expect(await screen.findByText('보관된 전략')).toBeInTheDocument()
    const restoreBtn = screen.getByRole('button', { name: /복원/i })
    const permanentDeleteBtn = screen.getByRole('button', { name: /영구 삭제/i })
    expect(restoreBtn).toBeInTheDocument()
    expect(permanentDeleteBtn).toBeInTheDocument()
  })
})
