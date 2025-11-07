import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import type { IndustryGroup } from '../types'
import { fetchIndustryGroups } from '../utils/api'
import { formatInteger, formatSymbol } from '../utils/format'

import './IndustryExplorerPage.css'

type LoadStatus = 'idle' | 'loading' | 'ready' | 'error'

interface IndustryLoadState {
  status: LoadStatus
  data: IndustryGroup[]
  error?: string
}

const MIN_STOCK_THRESHOLD = 40

function encodeSegment(value: string): string {
  return encodeURIComponent(value)
}

export function IndustryExplorerPage() {
  const [state, setState] = useState<IndustryLoadState>({ status: 'idle', data: [] })

  useEffect(() => {
    let active = true
    setState({ status: 'loading', data: [] })

    fetchIndustryGroups({ includeEtfs: false, minStockCount: MIN_STOCK_THRESHOLD, skipUncategorized: true })
      .then((groups) => {
        if (!active) return
        setState({ status: 'ready', data: groups })
      })
      .catch((error) => {
        if (!active) return
        setState({
          status: 'error',
          data: [],
          error: error instanceof Error ? error.message : String(error)
        })
      })

    return () => {
      active = false
    }
  }, [])

  const industries = useMemo(() => {
    const filtered = state.data.filter((group) => group.stockCount > MIN_STOCK_THRESHOLD)

    return filtered.sort((a, b) => {
      if (b.stockCount === a.stockCount) {
        return a.industry.localeCompare(b.industry, 'zh-CN')
      }
      return b.stockCount - a.stockCount
    })
  }, [state.data])

  const overview = useMemo(() => {
    const stockTotal = industries.reduce((total, group) => total + group.stockCount, 0)
    return { industries: industries.length, stocks: stockTotal }
  }, [industries])

  return (
    <div className="industry-page">
      <div className="industry-page__header">
        <div>
          <h1>二级行业概览</h1>
          <p>仅保留个股数量大于 40 且已剔除 ETF 的二级行业，共 {formatInteger(overview.industries)} 个。</p>
        </div>
        <div className="industry-page__summary">
          <div>
            <div className="industry-page__summary-label">符合条件子行业</div>
            <div className="industry-page__summary-value">{formatInteger(overview.industries)}</div>
          </div>
          <div>
            <div className="industry-page__summary-label">覆盖个股</div>
            <div className="industry-page__summary-value">{formatInteger(overview.stocks)}</div>
          </div>
        </div>
      </div>

      {state.status === 'loading' ? (
        <div className="industry-page__status">行业数据加载中...</div>
      ) : state.status === 'error' ? (
        <div className="industry-page__status industry-page__status--error">
          行业数据加载失败：{state.error}
        </div>
      ) : industries.length === 0 ? (
        <div className="industry-page__status">暂无行业数据</div>
      ) : (
        <div className="industry-page__grid">
          {industries.map((industry) => {
            const samples = industry.securities.slice(0, 6)
            const remaining = Math.max(0, industry.securities.length - samples.length)
            return (
              <article key={`${industry.sector}-${industry.industry}`} className="industry-card industry-card--single">
                <div className="industry-card__title-row">
                  <div className="industry-card__title">{industry.industry}</div>
                  <div className="industry-card__sector">{industry.sector}</div>
                </div>
                <div className="industry-card__stats">
                  <span>个股 {formatInteger(industry.stockCount)}</span>
                  {industry.otherCount > 0 ? <span>其他 {formatInteger(industry.otherCount)}</span> : null}
                </div>
                <div className="industry-card__samples">
                  {samples.map((security) => (
                    <span key={security.symbol} className="industry-row__chip">
                      {formatSymbol(security.symbol)}
                    </span>
                  ))}
                  {remaining > 0 ? (
                    <span className="industry-row__chip industry-row__chip--muted">+{remaining}</span>
                  ) : null}
                </div>
                <Link
                  className="industry-card__link"
                  to={`/industries/${encodeSegment(industry.sector)}/${encodeSegment(industry.industry)}`}
                >
                  查看全部个股
                </Link>
              </article>
            )
          })}
        </div>
      )}
    </div>
  )
}
