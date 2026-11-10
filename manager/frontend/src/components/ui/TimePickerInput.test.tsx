import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import TimePickerInput from './TimePickerInput'
import { normalizeTimeInput, isValidTimeInput } from '../strategy/strategyTypes'

describe('TimePickerInput & Time Normalization', () => {
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

    const { rerender } = render(
      <TimePickerInput value="1430" onChange={handleChange} aria-label="실행 시각" />,
    )

    const input = screen.getByLabelText('실행 시각')
    await user.click(input)
    await user.tab() // blur

    expect(handleChange).toHaveBeenCalledWith('14:30')
  })

  it('selects preset time when clicking quick chip', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()

    render(<TimePickerInput value="09:05" onChange={handleChange} />)

    const pmChip = screen.getByRole('button', { name: '14:30 (오후 매수)' })
    await user.click(pmChip)

    expect(handleChange).toHaveBeenCalledWith('14:30')
  })

  it('shows error message when time format is invalid', () => {
    render(<TimePickerInput value="25:99" onChange={() => {}} />)

    expect(screen.getByText(/HH:MM 형식\(00:00~23:59\)으로 입력하세요/)).toBeInTheDocument()
  })
})
