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
  onSelect?: (row: EtfRanking) => void
}

export function RankingTable({ data, onSelect }: RankingTableProps) {
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
          {data.map((row) => {
            const isTop = row.rank <= 3
            const isClickable = Boolean(onSelect)
            const classNames = [
              isTop ? 'ranking-table__row--top' : undefined,
              isClickable ? 'ranking-table__row--clickable' : undefined
            ]
              .filter(Boolean)
              .join(' ')

            return (
              <tr
                key={row.rank}
                className={classNames || undefined}
                onClick={
                  onSelect
                    ? () => {
                        onSelect(row)
                      }
                    : undefined
                }
                onKeyDown={
                  onSelect
                    ? (event) => {
                        if (event.key === 'Enter' || event.key === ' ') {
                          event.preventDefault()
                          onSelect(row)
                        }
                      }
                    : undefined
                }
                role={onSelect ? 'button' : undefined}
                tabIndex={onSelect ? 0 : undefined}
              >
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
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
