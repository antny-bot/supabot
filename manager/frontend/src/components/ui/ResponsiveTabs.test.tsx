import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import ResponsiveTabs from './ResponsiveTabs'
import SectionCard from './SectionCard'

describe('ResponsiveTabs', () => {
  it('renders tabs and notifies when the active tab changes', async () => {
    const user = userEvent.setup()
    const handleChange = vi.fn()

    render(
      <ResponsiveTabs
        tabs={[
          { id: 'display', label: 'Display' },
          { id: 'profile', label: 'Profile' },
          { id: 'security', label: 'Security' },
        ]}
        activeTab="display"
        onChange={handleChange}
      />,
    )

    expect(screen.getAllByRole('tab', { name: 'Display' })[0]).toHaveAttribute('aria-selected', 'true')

    await user.click(screen.getAllByRole('tab', { name: 'Security' })[0])

    expect(handleChange).toHaveBeenCalledWith('security')
  })

  it('renders all tab buttons with correct labels and attributes', () => {
    const tabs = [
      { id: 'tab1', label: 'Tab 1' },
      { id: 'tab2', label: 'Tab 2' },
      { id: 'tab3', label: '다중 시나리오 백테스트' },
    ]
    render(<ResponsiveTabs tabs={tabs} activeTab="tab3" onChange={() => {}} />)

    const tabElements = screen.getAllByRole('tab', { name: '다중 시나리오 백테스트' })
    expect(tabElements.length).toBeGreaterThanOrEqual(1)
    expect(tabElements[0]).toHaveAttribute('aria-selected', 'true')
  })
})

describe('SectionCard', () => {
  it('renders header metadata, actions, and content', () => {
    render(
      <SectionCard title="Monitoring" subtitle="Shared section shell" actions={<button type="button">Save</button>}>
        <div>Section body</div>
      </SectionCard>,
    )

    expect(screen.getByText('Monitoring')).toBeInTheDocument()
    expect(screen.getByText('Shared section shell')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Save' })).toBeInTheDocument()
    expect(screen.getByText('Section body')).toBeInTheDocument()
  })
})
