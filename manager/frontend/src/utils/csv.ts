/**
 * CSV 내보내기 공통 유틸리티
 * 엑셀 호환 한글 인코딩(UTF-8 BOM) 포함
 */
export interface CsvColumn<T = any> {
  label: string
  key: keyof T | string
  format?: (value: any, row: T) => string | number
}

export function exportToCsv<T = any>(
  filename: string,
  columns: CsvColumn<T>[],
  rows: T[],
) {
  if (!rows || rows.length === 0) {
    alert('내보낼 데이터가 없습니다.')
    return
  }

  const headerRow = columns.map((col) => `"${col.label.replace(/"/g, '""')}"`).join(',')

  const bodyRows = rows.map((row: any) =>
    columns
      .map((col) => {
        let val = row[col.key]
        if (col.format) {
          val = col.format(val, row)
        }
        if (val === null || val === undefined) {
          val = ''
        }
        const strVal = String(val).replace(/"/g, '""')
        return `"${strVal}"`
      })
      .join(','),
  )

  const csvContent = '\uFEFF' + [headerRow, ...bodyRows].join('\r\n')
  const blob = new Blob([csvContent], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.setAttribute('href', url)
  link.setAttribute('download', `${filename}_${new Date().toISOString().slice(0, 10)}.csv`)
  document.body.appendChild(link)
  link.click()
  document.body.removeChild(link)
  URL.revokeObjectURL(url)
}
