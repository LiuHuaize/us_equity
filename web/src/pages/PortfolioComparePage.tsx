import { useEffect, useMemo, useState } from 'react'
import { Area, AreaChart, CartesianGrid, Line, LineChart, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'

import type { PortfolioNavPoint, PortfolioSummary } from '../types'
import { loadPortfolioNavCsv, loadPortfolioSummaryCsv } from '../utils/csv'
import { formatPercent } from '../utils/format'
import { PortfolioSummaryCard } from '../components/PortfolioSummaryCard'

import './PortfolioComparePage.css'

interface LoadState<T> {
  status: 'loading' | 'ready' | 'error'
  data: T
  error?: string
}

const SUMMARY_CSV_PATH = '/data/portfolio_summary.csv'
const NAV_CSV_PATH = '/data/portfolio_nav.csv'

const TARGET_PORTFOLIOS: Record<string, { label: string; accent: 'blue' | 'purple'; color: string }> = {
  top10_10y: { label: '10年榜前10', accent: 'blue', color: '#4cc9f0' },
  top10_5y: { label: '5年榜前10', accent: 'purple', color: '#b5179e' }
}

interface PortfolioMember {
  symbol: string
  name: string
  weight: number
}

const DEFAULT_WEIGHT = 0.1

const PORTFOLIO_COMPOSITION: Record<string, PortfolioMember[]> = {
  top10_10y: [
    { symbol: 'GBTC', name: 'Grayscale Bitcoin Trust (BTC)', weight: DEFAULT_WEIGHT },
    { symbol: 'USD', name: 'ProShares Ultra Semiconductors', weight: DEFAULT_WEIGHT },
    { symbol: 'TECL', name: 'Direxion Daily Technology Bull 3X Shares', weight: DEFAULT_WEIGHT },
    { symbol: 'SOXL', name: 'Direxion Daily Semiconductor Bull 3X Shares', weight: DEFAULT_WEIGHT },
    { symbol: 'TQQQ', name: 'ProShares UltraPro QQQ', weight: DEFAULT_WEIGHT },
    { symbol: 'ROM', name: 'ProShares Ultra Technology', weight: DEFAULT_WEIGHT },
    { symbol: 'QLD', name: 'ProShares Ultra QQQ', weight: DEFAULT_WEIGHT },
    { symbol: 'SMH', name: 'VanEck Semiconductor ETF', weight: DEFAULT_WEIGHT },
    { symbol: 'SOXX', name: 'iShares Semiconductor ETF', weight: DEFAULT_WEIGHT },
    { symbol: 'SPXL', name: 'Direxion Daily S&P500 Bull 3X Shares', weight: DEFAULT_WEIGHT }
  ],
  top10_5y: [
    { symbol: 'USD', name: 'ProShares Ultra Semiconductors', weight: DEFAULT_WEIGHT },
    { symbol: 'ERX', name: 'Direxion Daily Energy Bull 2X Shares', weight: DEFAULT_WEIGHT },
    { symbol: 'DIG', name: 'ProShares Ultra Oil & Gas', weight: DEFAULT_WEIGHT },
    { symbol: 'GBTC', name: 'Grayscale Bitcoin Trust (BTC)', weight: DEFAULT_WEIGHT },
    { symbol: 'TECL', name: 'Direxion Daily Technology Bull 3X Shares', weight: DEFAULT_WEIGHT },
    { symbol: 'URA', name: 'Global X Uranium ETF', weight: DEFAULT_WEIGHT },
    { symbol: 'GUSH', name: 'Direxion Daily S&P Oil & Gas Exp. & Prod. Bull 2X Shares', weight: DEFAULT_WEIGHT },
    { symbol: 'SPXL', name: 'Direxion Daily S&P500 Bull 3X Shares', weight: DEFAULT_WEIGHT },
    { symbol: 'FAS', name: 'Direxion Daily Financial Bull 3X Shares', weight: DEFAULT_WEIGHT },
    { symbol: 'UPRO', name: 'ProShares UltraPro S&P500', weight: DEFAULT_WEIGHT }
  ]
}

interface MetricCompareRow {
  label: string
  key: keyof PortfolioSummary
  formatter?: (value: number) => string
}

const METRIC_ROWS: MetricCompareRow[] = [
  { label: '累计收益', key: 'cumulativeReturn', formatter: formatPercent },
  { label: '年化收益', key: 'annualizedReturn', formatter: formatPercent },
  { label: '年化波动', key: 'annualizedVolatility', formatter: formatPercent },
  { label: '最大回撤', key: 'maxDrawdown', formatter: formatPercent },
  { label: 'Sharpe', key: 'sharpeRatio' },
  { label: 'Calmar', key: 'calmarRatio' }
]

function groupNavByPortfolio(points: PortfolioNavPoint[]): Record<string, PortfolioNavPoint[]> {
  const grouped = points.reduce<Record<string, PortfolioNavPoint[]>>((acc, point) => {
    if (!acc[point.portfolio]) {
      acc[point.portfolio] = []
    }
    acc[point.portfolio].push(point)
    return acc
  }, {})

  return Object.fromEntries(
    Object.entries(grouped).map(([key, list]) => [
      key,
      list.sort((a, b) => new Date(a.tradeDate).getTime() - new Date(b.tradeDate).getTime())
    ])
  )
}

function formatValue(value: number | null | undefined, formatter?: (value: number) => string): string {
  if (value === null || value === undefined) {
    return '—'
  }
  if (formatter) {
    return formatter(value)
  }
  if (!Number.isFinite(value)) {
    return '—'
  }
  return value.toFixed(2)
}

function buildSeries(
  navData: Record<string, PortfolioNavPoint[]>,
  keys: string[],
  field: 'nav' | 'drawdown'
) {
  const dateSet = new Set<string>()
  keys.forEach((key) => {
    navData[key]?.forEach((point) => dateSet.add(point.tradeDate))
  })
  const dates = Array.from(dateSet).sort((a, b) => new Date(a).getTime() - new Date(b).getTime())

  const lookup: Record<string, Record<string, PortfolioNavPoint>> = {}
  keys.forEach((key) => {
    const collection: Record<string, PortfolioNavPoint> = {}
    navData[key]?.forEach((point) => {
      collection[point.tradeDate] = point
    })
    lookup[key] = collection
  })

  return dates.map((tradeDate) => {
    const row: Record<string, string | number> = { tradeDate }
    keys.forEach((key) => {
      const match = lookup[key]?.[tradeDate]
      if (match) {
        row[key] = field === 'nav' ? match.nav : match.drawdown
      }
    })
    return row
  })
}

const dateTickFormatter = (value: string) => value.slice(0, 10)

const percentTickFormatter = (value: number) => formatPercent(value)

interface SimpleTooltipPayload {
  dataKey?: string | number
  value?: number | string
  color?: string
  name?: string
}

interface SimpleTooltipProps {
  active?: boolean
  payload?: SimpleTooltipPayload[]
  label?: string | number
}

function NavTooltipContent({ active, payload, label }: SimpleTooltipProps) {
  if (!active || !payload?.length) {
    return null
  }
  return (
    <div className="portfolio-chart__tooltip">
      <div className="portfolio-chart__tooltip-date">{String(label ?? '')}</div>
      {payload.map((item) => {
        if (!item.dataKey) return null
        return (
          <div key={item.dataKey} className="portfolio-chart__tooltip-row">
            <span>{TARGET_PORTFOLIOS[item.dataKey]?.label ?? item.name}</span>
            <strong>{Number(item.value ?? 0).toFixed(2)}</strong>
          </div>
        )
      })}
    </div>
  )
}

function DrawdownTooltipContent({ active, payload, label }: SimpleTooltipProps) {
  if (!active || !payload?.length) {
    return null
  }
  return (
    <div className="portfolio-chart__tooltip">
      <div className="portfolio-chart__tooltip-date">{String(label ?? '')}</div>
      {payload.map((item) => {
        if (!item.dataKey) return null
        return (
          <div key={item.dataKey} className="portfolio-chart__tooltip-row">
            <span>{TARGET_PORTFOLIOS[item.dataKey]?.label ?? item.name}</span>
            <strong>{formatPercent(Number(item.value ?? 0))}</strong>
          </div>
        )
      })}
    </div>
  )
}

export function PortfolioComparePage() {
  const [summaryState, setSummaryState] = useState<LoadState<PortfolioSummary[]>>({
    status: 'loading',
    data: []
  })
  const [navState, setNavState] = useState<LoadState<Record<string, PortfolioNavPoint[]>>>(
    { status: 'loading', data: {} }
  )

  useEffect(() => {
    let active = true
    setSummaryState({ status: 'loading', data: [] })
    loadPortfolioSummaryCsv(SUMMARY_CSV_PATH)
      .then((rows) => {
        if (!active) return
        setSummaryState({ status: 'ready', data: rows })
      })
      .catch((error) => {
        if (!active) return
        setSummaryState({
          status: 'error',
          data: [],
          error: error instanceof Error ? error.message : String(error)
        })
      })
    return () => {
      active = false
    }
  }, [])

  useEffect(() => {
    let active = true
    setNavState({ status: 'loading', data: {} })
    loadPortfolioNavCsv(NAV_CSV_PATH)
      .then((points) => {
        if (!active) return
        setNavState({ status: 'ready', data: groupNavByPortfolio(points) })
      })
      .catch((error) => {
        if (!active) return
        setNavState({
          status: 'error',
          data: {},
          error: error instanceof Error ? error.message : String(error)
        })
      })
    return () => {
      active = false
    }
  }, [])

  const selectedSummaries = useMemo(() => {
    if (summaryState.status !== 'ready') {
      return []
    }
    return summaryState.data.filter((item) => TARGET_PORTFOLIOS[item.key])
  }, [summaryState])

  const navSeries = useMemo(() => {
    if (navState.status !== 'ready') {
      return [] as Array<Record<string, string | number>>
    }
    const keys = selectedSummaries.map((item) => item.key)
    if (keys.length === 0) {
      return []
    }
    return buildSeries(navState.data, keys, 'nav')
  }, [navState, selectedSummaries])

  const drawdownSeries = useMemo(() => {
    if (navState.status !== 'ready') {
      return [] as Array<Record<string, string | number>>
    }
    const keys = selectedSummaries.map((item) => item.key)
    if (keys.length === 0) {
      return []
    }
    return buildSeries(navState.data, keys, 'drawdown')
  }, [navState, selectedSummaries])

  return (
    <div className="portfolio-page">
      <div className="portfolio-page__header">
        <div>
          <h1>榜单组合对比</h1>
          <p>固定使用 10 年榜前 10 与 5 年榜前 10 两套组合，区间 2020-11-03 → 2025-11-03。</p>
        </div>
      </div>

      {summaryState.status === 'loading' ? (
        <div className="portfolio-page__status">回测摘要加载中...</div>
      ) : summaryState.status === 'error' ? (
        <div className="portfolio-page__status portfolio-page__status--error">
          回测摘要加载失败：{summaryState.error}
        </div>
      ) : (
        <div className="portfolio-page__cards">
          {selectedSummaries.map((summary) => (
            <PortfolioSummaryCard
              key={summary.key}
              summary={summary}
              accent={TARGET_PORTFOLIOS[summary.key]?.accent ?? 'blue'}
            >
              <div className="portfolio-page__extra-metrics">
                <div>
                  <span>Sharpe</span>
                  <strong>{formatValue(summary.sharpeRatio)}</strong>
                </div>
                <div>
                  <span>Calmar</span>
                  <strong>{formatValue(summary.calmarRatio)}</strong>
                </div>
              </div>
            </PortfolioSummaryCard>
          ))}
        </div>
      )}

      {selectedSummaries.length ? (
        <div className="portfolio-page__section">
          <h2>组合成分（各 10% 等权）</h2>
          <div className="portfolio-composition">
            {selectedSummaries.map((summary) => (
              <div key={summary.key} className="portfolio-composition__card">
                <div className="portfolio-composition__title">{summary.label}</div>
                <table>
                  <thead>
                    <tr>
                      <th>ETF</th>
                      <th>名称</th>
                      <th>权重</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(PORTFOLIO_COMPOSITION[summary.key] ?? []).map((item) => (
                      <tr key={item.symbol}>
                        <td>{item.symbol}</td>
                        <td>{item.name}</td>
                        <td>{formatPercent(item.weight)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            ))}
          </div>
        </div>
      ) : null}

      {summaryState.status === 'ready' && selectedSummaries.length === 2 ? (
        <div className="portfolio-page__section">
          <h2>核心指标对比</h2>
          <div className="portfolio-compare-table">
            <table>
              <thead>
                <tr>
                  <th>指标</th>
                  {selectedSummaries.map((summary) => (
                    <th key={summary.key}>{summary.label}</th>
                  ))}
                  <th>差值（后-前）</th>
                </tr>
              </thead>
              <tbody>
                {METRIC_ROWS.map((metric) => {
                  const first = selectedSummaries[0][metric.key as keyof PortfolioSummary] as number | null
                  const second = selectedSummaries[1][metric.key as keyof PortfolioSummary] as number | null
                  const diff =
                    first !== null && second !== null && first !== undefined && second !== undefined
                      ? second - first
                      : null
                  return (
                    <tr key={metric.key as string}>
                      <td>{metric.label}</td>
                      <td>{formatValue(first, metric.formatter)}</td>
                      <td>{formatValue(second, metric.formatter)}</td>
                      <td>{formatValue(diff, metric.formatter)}</td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : null}

      {navState.status === 'ready' && selectedSummaries.length === 2 ? (
        <div className="portfolio-page__section">
          <h2>净值走势</h2>
          <div className="portfolio-page__charts">
            <div className="portfolio-page__chart">
              <div className="portfolio-page__chart-title">组合净值</div>
              <ResponsiveContainer width="100%" height={320}>
                <LineChart data={navSeries} margin={{ top: 16, right: 24, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
                  <XAxis dataKey="tradeDate" tickFormatter={dateTickFormatter} minTickGap={32} stroke="rgba(255,255,255,0.4)" />
                  <YAxis stroke="rgba(255,255,255,0.4)" />
                  <Tooltip content={<NavTooltipContent />} />
                  <Legend />
                  {selectedSummaries.map((summary) => (
                    <Line
                      key={summary.key}
                      type="monotone"
                      dataKey={summary.key}
                      name={summary.label}
                      stroke={TARGET_PORTFOLIOS[summary.key]?.color}
                      strokeWidth={2}
                      dot={false}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
            <div className="portfolio-page__chart">
              <div className="portfolio-page__chart-title">最大回撤轨迹</div>
              <ResponsiveContainer width="100%" height={240}>
                <AreaChart data={drawdownSeries} margin={{ top: 16, right: 24, left: 0, bottom: 0 }}>
                  <CartesianGrid stroke="rgba(255,255,255,0.08)" strokeDasharray="3 3" />
                  <XAxis dataKey="tradeDate" tickFormatter={dateTickFormatter} minTickGap={32} stroke="rgba(255,255,255,0.4)" />
                  <YAxis tickFormatter={percentTickFormatter} stroke="rgba(255,255,255,0.4)" />
                  <Tooltip content={<DrawdownTooltipContent />} />
                  <Legend />
                  {selectedSummaries.map((summary) => (
                    <Area
                      key={summary.key}
                      type="monotone"
                      dataKey={summary.key}
                      name={summary.label}
                      stroke={TARGET_PORTFOLIOS[summary.key]?.color}
                      fill={TARGET_PORTFOLIOS[summary.key]?.color}
                      fillOpacity={0.2}
                    />
                  ))}
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      ) : navState.status === 'loading' ? (
        <div className="portfolio-page__status">净值数据加载中...</div>
      ) : navState.status === 'error' ? (
        <div className="portfolio-page__status portfolio-page__status--error">
          净值数据加载失败：{navState.error}
        </div>
      ) : null}

      {summaryState.status === 'ready' && selectedSummaries.length === 2 ? (
        <div className="portfolio-page__section">
          <h2>回测结论</h2>
          <div className="portfolio-page__analysis">
            <p>
              5 年榜组合在 2020-2025 区间累计收益与年化收益全面领先，同时最大回撤与波动显著低于 10 年榜组合，Sharpe/Calmar 也更高。
              10 年榜组合集中持有杠杆科技/加密类 ETF，在 2021-2022 年经历超过 70% 的深度回撤，而 5 年榜组合中的能源、金融杠杆 ETF
              提供了额外趋势跟随，回撤控制更佳。
            </p>
          </div>
        </div>
      ) : null}
    </div>
  )
}
