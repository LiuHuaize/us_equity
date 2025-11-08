import Papa from 'papaparse'

import type {
  EtfRanking,
  OverlapRanking,
  PortfolioNavPoint,
  PortfolioSummary
} from '../types'

export async function loadEtfCsv(path: string): Promise<EtfRanking[]> {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`无法加载数据文件：${path}`)
  }

  const csvText = await response.text()
  const parsed = Papa.parse<Record<string, string>>(csvText, {
    header: true,
    skipEmptyLines: true
  })

  return parsed.data
    .map((row) => ({
      rank: Number(row.rank),
      symbol: row.symbol ?? '',
      name: row.name ?? '',
      start_date: row.start_date ?? '',
      end_date: row.end_date ?? '',
      holding_days: Number(row.holding_days),
      total_return: Number(row.total_return),
      annualized_return: Number(row.annualized_return)
    }))
    .filter(
      (row) =>
        Number.isFinite(row.rank) &&
        Number.isFinite(row.holding_days) &&
        Number.isFinite(row.total_return) &&
        Number.isFinite(row.annualized_return)
    )
}

export async function loadOverlapCsv(path: string): Promise<OverlapRanking[]> {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`无法加载数据文件：${path}`)
  }

  const csvText = await response.text()
  const parsed = Papa.parse<Record<string, string>>(csvText, {
    header: true,
    skipEmptyLines: true
  })

  return parsed.data
    .map((row) => ({
      rank: Number(row.rank),
      symbol: row.symbol ?? '',
      name: row.name ?? '',
      start_date_5y: row.start_date_5y ?? '',
      end_date_5y: row.end_date_5y ?? '',
      holding_days_5y: Number(row.holding_days_5y),
      total_return_5y: Number(row.total_return_5y),
      annualized_return_5y: Number(row.annualized_return_5y),
      start_date_10y: row.start_date_10y ?? '',
      end_date_10y: row.end_date_10y ?? '',
      holding_days_10y: Number(row.holding_days_10y),
      total_return_10y: Number(row.total_return_10y),
      annualized_return_10y: Number(row.annualized_return_10y)
    }))
    .filter((row) =>
      Number.isFinite(row.rank) &&
      Number.isFinite(row.holding_days_5y) &&
      Number.isFinite(row.total_return_5y) &&
      Number.isFinite(row.annualized_return_5y) &&
      Number.isFinite(row.holding_days_10y) &&
      Number.isFinite(row.total_return_10y) &&
      Number.isFinite(row.annualized_return_10y)
    )
}

export async function loadPortfolioSummaryCsv(path: string): Promise<PortfolioSummary[]> {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`无法加载数据文件：${path}`)
  }

  const csvText = await response.text()
  const parsed = Papa.parse<Record<string, string>>(csvText, {
    header: true,
    skipEmptyLines: true
  })

  return parsed.data
    .map((row) => ({
      key: row.key ?? '',
      label: row.label ?? row.key ?? '',
      startDate: row.start_date ?? '',
      endDate: row.end_date ?? '',
      tradingDays: Number(row.trading_days),
      cumulativeReturn: Number(row.cumulative_return),
      annualizedReturn: Number(row.annualized_return),
      annualizedVolatility: Number(row.annualized_volatility),
      maxDrawdown: Number(row.max_drawdown),
      maxDrawdownStart: row.max_drawdown_start ?? '',
      maxDrawdownEnd: row.max_drawdown_end ?? '',
      sharpeRatio: row.sharpe_ratio ? Number(row.sharpe_ratio) : null,
      calmarRatio: row.calmar_ratio ? Number(row.calmar_ratio) : null
    }))
    .filter(
      (row) =>
        row.key.length > 0 &&
        Number.isFinite(row.cumulativeReturn) &&
        Number.isFinite(row.annualizedReturn) &&
        Number.isFinite(row.annualizedVolatility) &&
        Number.isFinite(row.maxDrawdown)
    )
}

export async function loadPortfolioNavCsv(path: string): Promise<PortfolioNavPoint[]> {
  const response = await fetch(path)
  if (!response.ok) {
    throw new Error(`无法加载数据文件：${path}`)
  }

  const csvText = await response.text()
  const parsed = Papa.parse<Record<string, string>>(csvText, {
    header: true,
    skipEmptyLines: true
  })

  return parsed.data
    .map((row) => ({
      portfolio: row.portfolio ?? '',
      tradeDate: row.trade_date ?? '',
      nav: Number(row.nav),
      dailyReturn: row.daily_return ? Number(row.daily_return) : null,
      drawdown: Number(row.drawdown)
    }))
    .filter(
      (row) =>
        row.portfolio.length > 0 &&
        row.tradeDate.length > 0 &&
        Number.isFinite(row.nav) &&
        Number.isFinite(row.drawdown)
    )
}
