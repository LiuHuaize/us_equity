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
