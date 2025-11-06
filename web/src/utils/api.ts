import type { EtfReturnSeries, EtfReturnStats } from '../types'

const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL ?? 'http://127.0.0.1:8080').replace(/\/$/, '')
const API_TOKEN = import.meta.env.VITE_API_TOKEN

type QueryParams = Record<string, string | number | undefined>

async function request<T>(endpoint: string, params?: QueryParams): Promise<T> {
  const url = new URL(endpoint, API_BASE_URL)

  if (params) {
    for (const [key, value] of Object.entries(params)) {
      if (value === undefined || value === null) {
        continue
      }
      url.searchParams.set(key, String(value))
    }
  }

  const headers: HeadersInit = {}
  if (API_TOKEN) {
    headers['X-API-Token'] = API_TOKEN
  }

  const response = await fetch(url.toString(), { headers })
  if (!response.ok) {
    const text = await response.text()
    throw new Error(`API 请求失败 (${response.status}): ${text || response.statusText}`)
  }

  return (await response.json()) as T
}

export async function fetchEtfReturns(
  symbol: string,
  period: 'year' | 'month',
  limit: number
): Promise<EtfReturnSeries> {
  const encodedSymbol = encodeURIComponent(symbol)
  return request<EtfReturnSeries>(`/api/etfs/${encodedSymbol}/returns`, {
    period,
    limit
  })
}

export async function fetchEtfStats(symbol: string, windowYears: number): Promise<EtfReturnStats> {
  const encodedSymbol = encodeURIComponent(symbol)
  return request<EtfReturnStats>(`/api/etfs/${encodedSymbol}/stats`, {
    windowYears
  })
}
