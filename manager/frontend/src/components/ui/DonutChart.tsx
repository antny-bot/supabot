import type { ReactNode } from 'react'
import {
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip as RechartsTooltip,
} from 'recharts'

export interface DonutChartDataItem {
  name: string
  value: number
  [key: string]: any
}

export const DEFAULT_DONUT_COLORS = [
  '#6366f1',
  '#10b981',
  '#f59e0b',
  '#ec4899',
  '#8b5cf6',
  '#06b6d4',
  '#3b82f6',
]

export interface DonutChartProps {
  data: DonutChartDataItem[]
  colors?: string[]
  innerRadius?: number
  outerRadius?: number
  paddingAngle?: number
  dataKey?: string
  nameKey?: string
  tooltipFormatter?: (val: number, name?: string) => [ReactNode, ReactNode]
  showLegend?: boolean
  legendFormatter?: (value: string) => ReactNode
  emptyMessage?: string
  height?: number | string
  className?: string
  animationDuration?: number
  label?: ((props: any) => string | ReactNode) | boolean
  labelLine?: boolean
}

export default function DonutChart({
  data,
  colors = DEFAULT_DONUT_COLORS,
  innerRadius = 45,
  outerRadius = 65,
  paddingAngle = 3,
  dataKey = 'value',
  nameKey = 'name',
  tooltipFormatter,
  showLegend = true,
  legendFormatter,
  emptyMessage = '표시할 데이터가 없습니다.',
  height = '100%',
  className = '',
  animationDuration = 600,
  label,
  labelLine = false,
}: DonutChartProps) {
  if (!data || data.length === 0 || data.every((d) => !d[dataKey])) {
    return (
      <div className={`flex h-full items-center justify-center text-xs text-slate-400 ${className}`}>
        {emptyMessage}
      </div>
    )
  }

  return (
    <div className={`w-full ${className}`} style={{ height }}>
      <ResponsiveContainer width="100%" height="100%">
        <PieChart>
          <Pie
            data={data}
            cx="50%"
            cy="50%"
            innerRadius={innerRadius}
            outerRadius={outerRadius}
            paddingAngle={paddingAngle}
            dataKey={dataKey}
            nameKey={nameKey}
            stroke="none"
            strokeWidth={0}
            animationDuration={animationDuration}
            label={label}
            labelLine={labelLine}
          >
            {data.map((_, index) => (
              <Cell
                key={`donut-cell-${index}`}
                fill={colors[index % colors.length]}
                stroke="none"
              />
            ))}
          </Pie>

          <RechartsTooltip
            formatter={tooltipFormatter as any}
            contentStyle={{
              backgroundColor: 'rgba(15, 23, 42, 0.95)',
              border: 'none',
              borderRadius: '8px',
              color: '#fff',
              fontSize: '12px',
            }}
          />

          {showLegend && (
            <Legend
              verticalAlign="bottom"
              iconSize={8}
              formatter={
                legendFormatter ||
                ((value) => (
                  <span className="text-xs text-slate-600 dark:text-slate-300 whitespace-nowrap break-keep">
                    {value}
                  </span>
                ))
              }
            />
          )}
        </PieChart>
      </ResponsiveContainer>
    </div>
  )
}
