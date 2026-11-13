import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, cleanup } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TimePickerInput from './TimePickerInput'
import {
  normalizeTimeInput,
  isValidTimeInput,
} from '../strategy/strategyTypes'

describe('TimePickerInput & Time Normalization', () => {
  beforeEach(() => {
    cleanup()
  })

  it('normalizes various input formats correctly', () => {
    // 4자리 연속 숫자
    expect(normalizeTimeInput('1430')).toBe('14:30')
    expect(normalizeTimeInput('0905')).toBe('09:05')
    // 3자리 숫자
    expect(normalizeTimeInput('905')).toBe('09:05')
    expect(normalizeTimeInput('930')).toBe('09:30')
    // 한글 형식
    expect(normalizeTimeInput('14시 30분')).toBe('14:30')
    expect(normalizeTimeInput('14시')).toBe('14:00')
    // 콜론 형식
    expect(normalizeTimeInput('14:30')).toBe('14:30')
    expect(normalizeTimeInput('9:5')).toBe('09:05')
    // 1~2자리 시간만
    expect(normalizeTimeInput('14')).toBe('14:00')
    expect(normalizeTimeInput('9')).toBe('09:00')

    // 유효성 검사
    expect(isValidTimeInput('14:30')).toBe(true)
    expect(isValidTimeInput('00:00')).toBe(true)
    expect(isValidTimeInput('23:59')).toBe(true)
    expect(isValidTimeInput('24:00')).toBe(false)
    expect(isValidTimeInput('14:60')).toBe(false)
    expect(isValidTimeInput('1430')).toBe(false) // 정규화 전 원본은 isValid=false
  })

  it('auto-corrects 1430 to 14:30 on blur', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()

    render(
      <TimePickerInput value="1430" onChange={handleChange} aria-label="실행 시각" />,
    )

    const input = screen.getByLabelText('실행 시각')
    await user.click(input)
    await user.tab() // blur

    expect(handleChange).toHaveBeenCalledWith('14:30')
  })

  it('supports custom presets via props', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()

    render(
      <TimePickerInput
        value="09:05"
        onChange={handleChange}
        presets={[
          { label: '14:30 (오후 매수)', time: '14:30' },
          { label: '09:05 (장시작 직후)', time: '09:05' },
        ]}
      />
    )

    const pmChip = screen.getByRole('button', { name: '14:30 (오후 매수)' })
    await user.click(pmChip)

    expect(handleChange).toHaveBeenCalledWith('14:30')
  })

  it('renders buy recommended presets (1st: 15:10, 2nd: 09:40, 3rd: 10:30) and selects one', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()

    render(<TimePickerInput value="15:10" onChange={handleChange} presetCategory="buy" />)

    // 매수 1순위 추천 칩 확인 및 클릭
    const chip1510 = screen.getByRole('button', { name: /15:10/ })
    expect(chip1510).toBeInTheDocument()
    await user.click(chip1510)
    expect(handleChange).toHaveBeenCalledWith('15:10')

    // 매수 2순위, 3순위도 노출되는지 확인
    expect(screen.getByRole('button', { name: /09:40/ })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /10:30/ })).toBeInTheDocument()

    // 15:10 선택 시 매수 1순위 가이드 텍스트 표시 확인
    expect(screen.getByText(/매수 1순위 추천: 종가 추세 형성/)).toBeInTheDocument()
  })

  it('renders sell recommended presets (1st: 09:20, 2nd: 11:15, 3rd: 15:10) and supports tab switching', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()

    render(<TimePickerInput value="" onChange={handleChange} presetCategory="all" showTabSelector={true} />)

    // 기본 매수 탭 -> 매도 추천 탭으로 전환
    const sellTab = screen.getByRole('button', { name: /매도 추천/ })
    await user.click(sellTab)

    // 매도 1순위(09:20), 2순위(11:15), 3순위(15:10) 노출 확인
    const chip0920 = screen.getByRole('button', { name: /09:20/ })
    expect(chip0920).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /11:15/ })).toBeInTheDocument()

    await user.click(chip0920)
    expect(handleChange).toHaveBeenCalledWith('09:20')
  })

  it('displays sell recommendation reason when sell time is entered', () => {
    render(<TimePickerInput value="09:20" onChange={() => {}} />)

    expect(screen.getByText(/매도 1순위 추천: 거래량 폭발/)).toBeInTheDocument()
  })

  it('shows error message when time format is invalid', () => {
    render(<TimePickerInput value="25:99" onChange={() => {}} />)

    expect(screen.getByText(/HH:MM 형식\(00:00~23:59\)으로 입력하세요/)).toBeInTheDocument()
  })
})
