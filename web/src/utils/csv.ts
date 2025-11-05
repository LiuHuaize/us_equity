import Papa from 'papaparse'

import type { EtfRanking, OverlapRanking } from '../types'

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
