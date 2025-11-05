import type { OverlapRanking } from '../types'
import {
  formatInteger,
  formatMultiple,
  formatPercent,
  formatSymbol
} from '../utils/format'

import './RankingTable.css'

interface OverlapTableProps {
  data: OverlapRanking[]
}

export function OverlapTable({ data }: OverlapTableProps) {
  return (
    <div className="ranking-table">
      <table>
        <thead>
          <tr>
            <th rowSpan={2}>排名</th>
            <th rowSpan={2}>代码</th>
            <th rowSpan={2}>名称</th>
            <th colSpan={4}>5 年表现</th>
            <th colSpan={4}>10 年表现</th>
          </tr>
          <tr>
            <th>区间</th>
            <th>持有天数</th>
            <th>总收益</th>
            <th>年度化收益率</th>
            <th>区间</th>
            <th>持有天数</th>
            <th>总收益</th>
            <th>年度化收益率</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr key={row.rank} className={row.rank <= 3 ? 'ranking-table__row--top' : undefined}>
              <td>#{row.rank}</td>
              <td>{formatSymbol(row.symbol)}</td>
              <td>{row.name}</td>
              <td>
                <span>{row.start_date_5y}</span>
                <span className="ranking-table__dash">→</span>
                <span>{row.end_date_5y}</span>
              </td>
              <td>{formatInteger(row.holding_days_5y)}</td>
              <td>{formatMultiple(row.total_return_5y)}</td>
              <td>{formatPercent(row.annualized_return_5y)}</td>
              <td>
                <span>{row.start_date_10y}</span>
                <span className="ranking-table__dash">→</span>
                <span>{row.end_date_10y}</span>
              </td>
              <td>{formatInteger(row.holding_days_10y)}</td>
              <td>{formatMultiple(row.total_return_10y)}</td>
              <td>{formatPercent(row.annualized_return_10y)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
