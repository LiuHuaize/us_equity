import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'

import type { IndustryGroup, IndustrySecurity } from '../types'
import { fetchIndustryGroups } from '../utils/api'
import { formatInteger, formatSymbol } from '../utils/format'

import './IndustryDetailPage.css'

type LoadStatus = 'loading' | 'ready' | 'error'

interface DetailState {
  status: LoadStatus
  data: IndustryGroup | null
  error?: string
}

function decodeParam(value: string | undefined): string {
  if (!value) return ''
  try {
    return decodeURIComponent(value)
  } catch {
    return value
  }
}

export function IndustryDetailPage() {
  const params = useParams<{ sector: string; industry: string }>()
  const sector = decodeParam(params.sector)
  const industry = decodeParam(params.industry)
  const navigate = useNavigate()

  const [state, setState] = useState<DetailState>({ status: 'loading', data: null })

  useEffect(() => {
    if (!sector || !industry) {
      setState({ status: 'error', data: null, error: '缺少板块参数' })
      return
    }

    let active = true
    setState({ status: 'loading', data: null })

    fetchIndustryGroups({ sector, industry, includeEtfs: false, minStockCount: 0, skipUncategorized: false })
      .then((groups) => {
        if (!active) return
        const payload = groups[0] ?? null
        if (!payload) {
          setState({ status: 'error', data: null, error: '未找到对应的行业数据' })
        } else {
          setState({ status: 'ready', data: payload })
        }
      })
      .catch((error) => {
        if (!active) return
        setState({
          status: 'error',
          data: null,
          error: error instanceof Error ? error.message : String(error)
        })
      })

    return () => {
      active = false
    }
  }, [sector, industry])

  const sortedSecurities = useMemo(() => {
    if (!state.data) {
      return [] as IndustrySecurity[]
    }
    return [...state.data.securities].sort((a, b) => formatSymbol(a.symbol).localeCompare(formatSymbol(b.symbol), 'zh-CN'))
  }, [state.data])

  const summary = state.data
    ? [{ label: '个股数量', value: formatInteger(state.data.stockCount) }]
    : []

  const handleBack = () => {
    navigate('/industries')
  }

  return (
    <div className="industry-detail">
      <div className="industry-detail__header">
        <div>
          <button type="button" className="industry-detail__back" onClick={handleBack}>
            行业板块
          </button>
          <span className="industry-detail__breadcrumb">/ {sector}</span>
          <h1>{industry || '未分类'}</h1>
          {state.data ? (
            <p>仅展示普通股票/ADR，共 {formatInteger(state.data.stockCount)} 只，ETF 已剔除。</p>
          ) : (
            <p>加载行业构成中...</p>
          )}
        </div>
        <button type="button" className="industry-detail__back industry-detail__back--outline" onClick={handleBack}>
          返回行业列表
        </button>
      </div>

      {summary.length ? (
        <div className="industry-detail__summary">
          {summary.map((item) => (
            <div key={item.label}>
              <div className="industry-detail__summary-label">{item.label}</div>
              <div className="industry-detail__summary-value">{item.value}</div>
            </div>
          ))}
        </div>
      ) : null}

      {state.status === 'loading' ? (
        <div className="industry-detail__status">行业成分加载中...</div>
      ) : state.status === 'error' ? (
        <div className="industry-detail__status industry-detail__status--error">
          行业成分加载失败：{state.error}
        </div>
      ) : sortedSecurities.length === 0 ? (
        <div className="industry-detail__status">该行业暂无标的</div>
      ) : (
        <div className="industry-detail__table">
          <table>
            <thead>
              <tr>
                <th>代码</th>
                <th>名称</th>
                <th>交易所</th>
              </tr>
            </thead>
            <tbody>
              {sortedSecurities.map((security) => (
                <tr key={security.symbol}>
                  <td>{formatSymbol(security.symbol)}</td>
                  <td>{security.name || '—'}</td>
                  <td>{security.exchange || '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
