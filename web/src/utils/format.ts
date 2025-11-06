const percentFormatter = new Intl.NumberFormat('zh-CN', {
  style: 'percent',
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
})

const decimalFormatter = new Intl.NumberFormat('zh-CN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2
})

const integerFormatter = new Intl.NumberFormat('zh-CN')

const shortPercentFormatter = new Intl.NumberFormat('zh-CN', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 1
})

const compactNumberFormatter = new Intl.NumberFormat('zh-CN', {
  notation: 'compact',
  maximumFractionDigits: 1
})

export function formatPercent(value: number): string {
  return percentFormatter.format(value)
}

export function formatCompactPercent(value: number): string {
  if (!Number.isFinite(value)) {
    return '-'
  }

  const percentValue = value * 100
  const absPercentValue = Math.abs(percentValue)

  if (absPercentValue < 1) {
    return `${decimalFormatter.format(percentValue)}%`
  }

  if (absPercentValue < 1000) {
    return `${shortPercentFormatter.format(percentValue)}%`
  }

  return `${compactNumberFormatter.format(percentValue)}%`
}

export function formatMultiple(value: number): string {
  return `${decimalFormatter.format(value)}×`
}

export function formatInteger(value: number): string {
  return integerFormatter.format(value)
}

export function formatSymbol(symbol: string): string {
  return symbol.replace('.US', '')
}
