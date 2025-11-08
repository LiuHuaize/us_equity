import type { ReactNode } from 'react'

import type { PortfolioSummary } from '../types'
import { formatPercent } from '../utils/format'

import './PortfolioSummaryCard.css'

interface PortfolioSummaryCardProps {
  summary: PortfolioSummary
  accent?: 'blue' | 'purple'
  children?: ReactNode
}

const METRICS: Array<{ key: keyof PortfolioSummary; label: string }> = [
  { key: 'cumulativeReturn', label: '累计收益' },
  { key: 'annualizedReturn', label: '年化收益' },
  { key: 'annualizedVolatility', label: '年化波动' },
  { key: 'maxDrawdown', label: '最大回撤' }
]

export function PortfolioSummaryCard({ summary, accent = 'blue', children }: PortfolioSummaryCardProps) {
  return (
    <div className={`portfolio-card portfolio-card--${accent}`}>
      <div className="portfolio-card__header">
        <div className="portfolio-card__title">{summary.label}</div>
        <div className="portfolio-card__dates">
          {summary.startDate} → {summary.endDate}
        </div>
      </div>
      <div className="portfolio-card__metrics">
        {METRICS.map((metric) => (
          <div key={metric.key} className="portfolio-card__metric">
            <div className="portfolio-card__metric-label">{metric.label}</div>
            <div className="portfolio-card__metric-value">
              {formatPercent(summary[metric.key] as number)}
            </div>
          </div>
        ))}
      </div>
      {children && <div className="portfolio-card__extra">{children}</div>}
    </div>
  )
}

