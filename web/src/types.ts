export interface EtfRanking {
  rank: number
  symbol: string
  name: string
  start_date: string
  end_date: string
  holding_days: number
  total_return: number
  annualized_return: number
}

export interface OverlapRanking {
  rank: number
  symbol: string
  name: string
  start_date_5y: string
  end_date_5y: string
  holding_days_5y: number
  total_return_5y: number
  annualized_return_5y: number
  start_date_10y: string
  end_date_10y: string
  holding_days_10y: number
  total_return_10y: number
  annualized_return_10y: number
}

export type DatasetKey = 'fiveYear' | 'tenYear' | 'overlap'

export type DatasetType = 'single' | 'overlap'

export interface DatasetConfig {
  id: DatasetKey
  title: string
  description: string
  file: string
  type: DatasetType
}

export interface DatasetState<TData> {
  status: 'loading' | 'ready' | 'error'
  data: TData
  error?: string
}

export interface EtfPeriodReturn {
  periodKey: string
  periodStart: string
  periodEnd: string
  tradingDays: number
  totalReturnPct: number | null
  compoundReturnPct: number | null
  volatilityPct: number | null
  maxDrawdownPct: number | null
}

export interface EtfReturnSeries {
  symbol: string
  period: 'year' | 'month'
  rows: EtfPeriodReturn[]
}

export interface EtfReturnStats {
  symbol: string
  windowYears: number
  periods: number
  totalReturnPct: number | null
  averageAnnualReturnPct: number | null
  maxDrawdownPct: number | null
  averageVolatilityPct: number | null
  bestPeriodKey: string | null
  bestPeriodReturnPct: number | null
  worstPeriodKey: string | null
  worstPeriodReturnPct: number | null
  startDate: string
  endDate: string
}
