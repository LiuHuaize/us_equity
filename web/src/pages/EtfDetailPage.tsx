import { useEffect, useMemo, useState } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'

import type { EtfPeriodReturn, EtfReturnStats } from '../types'
import { fetchEtfReturns, fetchEtfStats } from '../utils/api'
import { formatInteger, formatPercent, formatSymbol } from '../utils/format'

import './EtfDetailPage.css'

type LoadStatus = 'idle' | 'loading' | 'ready' | 'error'

interface LoadState<T> {
  status: LoadStatus
  data: T
  error?: string
}

const DEFAULT_YEAR_LIMIT = Number(import.meta.env.VITE_ETF_YEAR_LIMIT ?? 10) || 10
const DEFAULT_MONTH_LIMIT = Number(import.meta.env.VITE_ETF_MONTH_LIMIT ?? 120) || 120
const DEFAULT_STATS_WINDOW = Number(import.meta.env.VITE_ETF_STATS_YEARS ?? 10) || 10

type EnrichedPeriodReturn = EtfPeriodReturn & { cumulativeReturnPct: number | null }

function computeCumulativeReturns(rows: EtfPeriodReturn[]): EnrichedPeriodReturn[] {
  const sorted = [...rows].sort((a, b) => new Date(a.periodStart).getTime() - new Date(b.periodStart).getTime())
  let cumulativeFactor = 1

  const enrichedAsc = sorted.map((row) => {
    let cumulative: number | null = null

    if (row.totalReturnPct !== null) {
      cumulativeFactor *= 1 + row.totalReturnPct
      cumulative = cumulativeFactor - 1
    } else if (cumulativeFactor !== 1) {
      cumulative = cumulativeFactor - 1
    }

    return {
      ...row,
      cumulativeReturnPct: cumulative
    }
  })

  return enrichedAsc.sort((a, b) => new Date(b.periodStart).getTime() - new Date(a.periodStart).getTime())
}

function formatPercentOrDash(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '—'
  }
  return formatPercent(value)
}

function formatIntegerOrDash(value: number | null | undefined): string {
  if (value === null || value === undefined) {
    return '—'
  }
  return formatInteger(value)
}

export function EtfDetailPage() {
  const { symbol: rawSymbol } = useParams<{ symbol: string }>()
  const symbol = rawSymbol ?? ''
  const navigate = useNavigate()
  const location = useLocation()
  const locationState = location.state as { name?: string } | undefined
  const displayName = locationState?.name

  const [activeTab, setActiveTab] = useState<'year' | 'month'>('year')

  const [annualState, setAnnualState] = useState<LoadState<EnrichedPeriodReturn[]>>({
    status: 'idle',
    data: []
  })
  const [monthlyState, setMonthlyState] = useState<LoadState<EnrichedPeriodReturn[]>>({
    status: 'idle',
    data: []
  })
  const [statsState, setStatsState] = useState<LoadState<EtfReturnStats | null>>({
    status: 'idle',
    data: null
  })

  useEffect(() => {
    if (!symbol) {
      return
    }

    let cancelled = false
    setAnnualState({ status: 'loading', data: [] })

    fetchEtfReturns(symbol, 'year', DEFAULT_YEAR_LIMIT)
      .then((series) => {
        if (cancelled) return
        const rows = computeCumulativeReturns(series.rows)
        setAnnualState({ status: 'ready', data: rows })
      })
      .catch((error) => {
        if (cancelled) return
        setAnnualState({ status: 'error', data: [], error: error instanceof Error ? error.message : String(error) })
      })

    return () => {
      cancelled = true
    }
  }, [symbol])

  useEffect(() => {
    if (!symbol) {
      return
    }

    let cancelled = false
    setStatsState({ status: 'loading', data: null })

    fetchEtfStats(symbol, DEFAULT_STATS_WINDOW)
      .then((stats) => {
        if (cancelled) return
        setStatsState({ status: 'ready', data: stats })
      })
      .catch((error) => {
        if (cancelled) return
        setStatsState({ status: 'error', data: null, error: error instanceof Error ? error.message : String(error) })
      })

    return () => {
      cancelled = true
    }
  }, [symbol])

  useEffect(() => {
    if (activeTab !== 'month' || !symbol) {
      return
    }

    setMonthlyState((prev) => {
      if (prev.status !== 'idle') {
        return prev
      }
      return { status: 'loading', data: [] }
    })
  }, [activeTab, symbol])

  useEffect(() => {
    if (!symbol || monthlyState.status !== 'loading') {
      return
    }

    let cancelled = false

    fetchEtfReturns(symbol, 'month', DEFAULT_MONTH_LIMIT)
      .then((series) => {
        if (cancelled) return
        const rows = computeCumulativeReturns(series.rows)
        setMonthlyState({ status: 'ready', data: rows })
      })
      .catch((error) => {
        if (cancelled) return
        setMonthlyState({ status: 'error', data: [], error: error instanceof Error ? error.message : String(error) })
      })

    return () => {
      cancelled = true
    }
  }, [symbol, monthlyState.status])

  useEffect(() => {
    setActiveTab('year')
    setMonthlyState({ status: 'idle', data: [] })
  }, [symbol])

  const activeState = activeTab === 'year' ? annualState : monthlyState

  const summaryMetrics = useMemo(() => {
    if (statsState.status !== 'ready' || !statsState.data) {
      return null
    }

    const stats = statsState.data
    return [
      {
        label: `${stats.windowYears}年总收益`,
        value: formatPercentOrDash(stats.totalReturnPct)
      },
      {
        label: `${stats.windowYears}年平均年化`,
        value: formatPercentOrDash(stats.averageAnnualReturnPct)
      },
      {
        label: '最大回撤',
        value: formatPercentOrDash(stats.maxDrawdownPct)
      },
      {
        label: '统计周期',
        value: `${stats.startDate} → ${stats.endDate}`
      }
    ]
  }, [statsState])

  if (!symbol) {
    return (
      <div className="etf-detail">
        <div className="etf-detail__empty">未提供有效的标的代码。</div>
      </div>
    )
  }

  return (
    <div className="etf-detail">
      <div className="etf-detail__header">
        <button className="etf-detail__back" type="button" onClick={() => navigate(-1)}>
          返回
        </button>
        <div className="etf-detail__title">
          <h1>
            {formatSymbol(symbol)}
            {displayName ? <span className="etf-detail__subtitle">{displayName}</span> : null}
          </h1>
          {statsState.status === 'ready' && statsState.data ? (
            <p className="etf-detail__range">
              数据区间：{statsState.data.startDate} → {statsState.data.endDate}
            </p>
          ) : null}
        </div>
      </div>

      {summaryMetrics ? (
        <div className="etf-detail__summary">
          {summaryMetrics.map((item) => (
            <div key={item.label} className="etf-detail__summary-card">
              <div className="etf-detail__summary-label">{item.label}</div>
              <div className="etf-detail__summary-value">{item.value}</div>
            </div>
          ))}
        </div>
      ) : statsState.status === 'loading' ? (
        <div className="etf-detail__status">统计指标加载中...</div>
      ) : statsState.status === 'error' ? (
        <div className="etf-detail__status etf-detail__status--error">
          统计指标加载失败：{statsState.error}
        </div>
      ) : null}

      <div className="etf-detail__tabs">
        <button
          className={activeTab === 'year' ? 'etf-detail__tab etf-detail__tab--active' : 'etf-detail__tab'}
          type="button"
          onClick={() => setActiveTab('year')}
        >
          年度收益
        </button>
        <button
          className={activeTab === 'month' ? 'etf-detail__tab etf-detail__tab--active' : 'etf-detail__tab'}
          type="button"
          onClick={() => setActiveTab('month')}
        >
          月度收益
        </button>
      </div>

      <div className="etf-detail__table">
        {activeState.status === 'loading' ? (
          <div className="etf-detail__status">数据加载中...</div>
        ) : activeState.status === 'error' ? (
          <div className="etf-detail__status etf-detail__status--error">
            数据加载失败：{activeState.error}
          </div>
        ) : activeState.status === 'ready' && activeState.data.length > 0 ? (
          <table>
            <thead>
              <tr>
                <th>{activeTab === 'year' ? '年份' : '月份'}</th>
                <th>总收益</th>
                <th>累计收益</th>
                <th>最大回撤</th>
                <th>分析天数</th>
              </tr>
            </thead>
            <tbody>
              {activeState.data.map((row) => (
                <tr key={row.periodKey}>
                  <td>{row.periodKey}</td>
                  <td>{formatPercentOrDash(row.totalReturnPct)}</td>
                  <td>{formatPercentOrDash(row.cumulativeReturnPct)}</td>
                  <td>{formatPercentOrDash(row.maxDrawdownPct)}</td>
                  <td>{formatIntegerOrDash(row.tradingDays)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        ) : (
          <div className="etf-detail__status">暂无数据</div>
        )}
      </div>
    </div>
  )
}
