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

export function formatPercent(value: number): string {
  return percentFormatter.format(value)
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
