import type { EtfRanking } from '../types'
import {
  formatInteger,
  formatMultiple,
  formatPercent,
  formatSymbol
} from '../utils/format'

import './RankingTable.css'

interface RankingTableProps {
  data: EtfRanking[]
}

export function RankingTable({ data }: RankingTableProps) {
  return (
    <div className="ranking-table">
      <table>
        <thead>
          <tr>
            <th>排名</th>
            <th>代码</th>
            <th>名称</th>
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
                <span>{row.start_date}</span>
                <span className="ranking-table__dash">→</span>
                <span>{row.end_date}</span>
              </td>
              <td>{formatInteger(row.holding_days)}</td>
              <td>{formatMultiple(row.total_return)}</td>
              <td>{formatPercent(row.annualized_return)}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
