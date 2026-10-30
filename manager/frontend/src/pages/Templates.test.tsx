import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi, beforeEach } from 'vitest'
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
})
