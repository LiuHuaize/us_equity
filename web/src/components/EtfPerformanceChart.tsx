import { useMemo } from 'react'
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis
} from 'recharts'

import type { EtfPerformancePoint, PerformanceInterval } from '../types'
import { formatCompactPercent, formatPercent, formatSymbol } from '../utils/format'

interface EtfPerformanceChartProps {
  symbol: string
  benchmark: string
  interval: PerformanceInterval
  points: EtfPerformancePoint[]
}

interface ChartDatum {
  date: string
  label: string
  etfReturn: number
  benchmarkReturn: number
  etfScaled: number
  benchmarkScaled: number
}

function formatDateLabel(dateText: string, interval: PerformanceInterval): string {
  if (interval === 'year') {
    return dateText.slice(0, 4)
  }
  if (interval === 'month') {
    return dateText.slice(0, 7)
  }
  return dateText
}

const EPSILON = 1e-6

const MAX_TICK_COUNT = 7

const POSITIVE_SCALE_POINTS = [
  { value: 0, position: 0 },
  { value: 1, position: 0.5 },
  { value: 2, position: 0.6 },
  { value: 3, position: 0.7 },
  { value: 5, position: 0.85 },
  { value: 10, position: 1 }
] as const

type ScalePoint = (typeof POSITIVE_SCALE_POINTS)[number]

function interpolateValue(value: number, start: ScalePoint, end: ScalePoint): number {
  if (Math.abs(end.value - start.value) <= EPSILON) {
    return start.position
  }

  const ratio = (value - start.value) / (end.value - start.value)
  return start.position + ratio * (end.position - start.position)
}

function interpolatePosition(position: number, start: ScalePoint, end: ScalePoint): number {
  if (Math.abs(end.position - start.position) <= EPSILON) {
    return start.value
  }

  const ratio = (position - start.position) / (end.position - start.position)
  return start.value + ratio * (end.value - start.value)
}

function scalePositiveValue(value: number): number {
  if (value <= 0) {
    return 0
  }

  let previous: ScalePoint = POSITIVE_SCALE_POINTS[0]
  for (let index = 1; index < POSITIVE_SCALE_POINTS.length; index += 1) {
    const current = POSITIVE_SCALE_POINTS[index]
    if (value <= current.value + EPSILON) {
      return interpolateValue(value, previous, current)
    }
    previous = current
  }

  const last: ScalePoint = POSITIVE_SCALE_POINTS[POSITIVE_SCALE_POINTS.length - 1]
  const preLast: ScalePoint = POSITIVE_SCALE_POINTS[POSITIVE_SCALE_POINTS.length - 2]
  const slope = (last.position - preLast.position) / (last.value - preLast.value)
  return last.position + (value - last.value) * slope
}

function unscalePositiveValue(position: number): number {
  if (position <= 0) {
    return 0
  }

  let previous: ScalePoint = POSITIVE_SCALE_POINTS[0]
  for (let index = 1; index < POSITIVE_SCALE_POINTS.length; index += 1) {
    const current = POSITIVE_SCALE_POINTS[index]
    if (position <= current.position + EPSILON) {
      return interpolatePosition(position, previous, current)
    }
    previous = current
  }

  const last: ScalePoint = POSITIVE_SCALE_POINTS[POSITIVE_SCALE_POINTS.length - 1]
  const preLast: ScalePoint = POSITIVE_SCALE_POINTS[POSITIVE_SCALE_POINTS.length - 2]
  const slope = (last.value - preLast.value) / (last.position - preLast.position)
  return last.value + (position - last.position) * slope
}

function scaleReturn(value: number): number {
  if (!Number.isFinite(value) || Math.abs(value) <= EPSILON) {
    return 0
  }
  return value > 0 ? scalePositiveValue(value) : -scalePositiveValue(Math.abs(value))
}

function unscaleReturn(position: number): number {
  if (!Number.isFinite(position) || Math.abs(position) <= EPSILON) {
    return 0
  }
  return position > 0 ? unscalePositiveValue(position) : -unscalePositiveValue(Math.abs(position))
}

function selectPositiveCap(maxValue: number): number {
  if (maxValue <= 0) {
    return 0
  }

  if (maxValue <= 1) {
    const steps = Math.ceil(maxValue / 0.1)
    return Math.max(0.1, steps * 0.1)
  }

  const candidates = [1, 2, 3, 5, 10, 20, 30, 50, 100]
  for (const candidate of candidates) {
    if (maxValue <= candidate + EPSILON) {
      return candidate
    }
  }

  const exponent = Math.ceil(Math.log10(maxValue))
  return Math.pow(10, exponent)
}

function collectPositiveTicks(limit: number): number[] {
  if (limit <= 0) {
    return []
  }

  const ticks: number[] = []

  if (limit <= 1 + EPSILON) {
    const baseTicks = [0.05, 0.1, 0.2, 0.5, 1]
    for (const tick of baseTicks) {
      if (tick <= limit + EPSILON) {
        ticks.push(tick)
      }
    }
    if (ticks.length === 0 || Math.abs(ticks[ticks.length - 1] - limit) > EPSILON) {
      ticks.push(Number(limit.toFixed(6)))
    }
    return ticks
  }

  const candidates = [1, 2, 3, 5, 10, 20, 30, 50, 100]
  for (const candidate of candidates) {
    if (candidate > limit + EPSILON) {
      break
    }
    ticks.push(candidate)
  }

  if (ticks.length === 0 || ticks[ticks.length - 1] < limit - EPSILON) {
    ticks.push(limit)
  }

  return ticks
}

function selectTickSubset(values: number[], maxCount: number): number[] {
  if (values.length <= maxCount) {
    return values
  }

  const targetSize = Math.min(maxCount, values.length)
  const selected = new Set<number>()

  selected.add(0)
  selected.add(values.length - 1)

  const zeroIndex = values.findIndex((value) => Math.abs(value) <= EPSILON)
  if (zeroIndex >= 0) {
    selected.add(zeroIndex)
  }

  if (selected.size < targetSize) {
    const segments = targetSize - selected.size
    const interval = segments > 0 ? (values.length - 1) / (segments + 1) : 0

    for (let index = 1; selected.size < targetSize && index <= segments + 1; index += 1) {
      const candidate = Math.round(index * interval)
      selected.add(Math.min(values.length - 1, Math.max(0, candidate)))
    }
  }

  if (selected.size < targetSize) {
    for (let index = 0; index < values.length && selected.size < targetSize; index += 1) {
      selected.add(index)
    }
  }

  return Array.from(selected)
    .sort((a, b) => a - b)
    .map((index) => values[index])
}

export function EtfPerformanceChart({ symbol, benchmark, interval, points }: EtfPerformanceChartProps) {
  const filteredPoints = useMemo<EtfPerformancePoint[]>(() => {
    if (interval !== 'month' || points.length === 0) {
      return points
    }

    const latestDate = new Date(points[points.length - 1].date)
    const cutoff = new Date(latestDate)
    cutoff.setFullYear(cutoff.getFullYear() - 1)

    return points.filter((point) => {
      const pointDate = new Date(point.date)
      return pointDate >= cutoff
    })
  }, [interval, points])

  const { chartData, minReturn, maxReturn } = useMemo(() => {
    const data: ChartDatum[] = []
    let minVal = Number.POSITIVE_INFINITY
    let maxVal = Number.NEGATIVE_INFINITY

    for (const point of filteredPoints) {
      const etfReturn = point.etfCumulativeReturnPct
      const benchmarkReturn = point.benchmarkCumulativeReturnPct

      minVal = Math.min(minVal, etfReturn, benchmarkReturn)
      maxVal = Math.max(maxVal, etfReturn, benchmarkReturn)

      data.push({
        date: point.date,
        label: formatDateLabel(point.date, interval),
        etfReturn,
        benchmarkReturn,
        etfScaled: scaleReturn(etfReturn),
        benchmarkScaled: scaleReturn(benchmarkReturn)
      })
    }

    if (!Number.isFinite(minVal) || !Number.isFinite(maxVal)) {
      minVal = 0
      maxVal = 0
    }

    return {
      chartData: data,
      minReturn: minVal,
      maxReturn: maxVal
    }
  }, [filteredPoints, interval])

  const { domain, ticks } = useMemo(() => {
    if (chartData.length === 0) {
      return {
        domain: [0, 0],
        ticks: [0]
      }
    }

    const positiveCap = selectPositiveCap(Math.max(maxReturn, 0))
    const negativeCap = minReturn < 0 ? -selectPositiveCap(Math.abs(minReturn)) : 0

    if (positiveCap === 0 && negativeCap === 0) {
      return {
        domain: [0, 0],
        ticks: [0]
      }
    }

    const positiveTicks = collectPositiveTicks(positiveCap)
    const negativeTicks = collectPositiveTicks(Math.abs(negativeCap))
      .map((tick) => -tick)
      .reverse()

    const tickValues = [...negativeTicks, 0, ...positiveTicks]
    const scaledTicks = tickValues.map((tick) => scaleReturn(tick))
    const limitedTicks = selectTickSubset(scaledTicks, MAX_TICK_COUNT)

    return {
      domain: [scaleReturn(negativeCap), scaleReturn(positiveCap)] as [number, number],
      ticks: limitedTicks
    }
  }, [chartData, maxReturn, minReturn])

  return (
    <div className="etf-performance-chart">
      <ResponsiveContainer width="100%" height={400}>
        <LineChart data={chartData} margin={{ top: 16, right: 32, left: 16, bottom: 20 }}>
          <CartesianGrid stroke="rgba(71, 85, 105, 0.35)" strokeDasharray="3 3" />
          <XAxis
            dataKey="date"
            tickFormatter={(value: string) => formatDateLabel(value, interval)}
            minTickGap={20}
            stroke="rgba(226, 232, 240, 0.7)"
          />
          <YAxis
            tickFormatter={(value: number) => formatCompactPercent(unscaleReturn(value))}
            stroke="rgba(226, 232, 240, 0.7)"
            width={80}
            allowDecimals
            domain={domain}
            ticks={ticks}
            tickMargin={8}
          />
          <Tooltip
            contentStyle={{
              background: 'rgba(15, 23, 42, 0.88)',
              borderRadius: 12,
              border: '1px solid rgba(99, 102, 241, 0.35)',
              color: '#e2e8f0'
            }}
            formatter={(_value: number, name: string, item: { payload?: ChartDatum }) => {
              const record = item?.payload

              if (!record) {
                return ['-', name]
              }

              if (name === 'etfReturn') {
                return [formatPercent(record.etfReturn), `${formatSymbol(symbol)} 累计收益`]
              }
              if (name === 'benchmarkReturn') {
                return [formatPercent(record.benchmarkReturn), `${formatSymbol(benchmark)} 累计收益`]
              }

              return [String(_value), name]
            }}
            labelFormatter={(value: string) => formatDateLabel(value, interval)}
          />
          <Legend
            verticalAlign="top"
            height={36}
            formatter={(value: string) => {
              if (value === 'etfReturn') {
                return `${formatSymbol(symbol)} 累计收益`
              }
              if (value === 'benchmarkReturn') {
                return `${formatSymbol(benchmark)} 累计收益`
              }
              return value
            }}
          />
          <ReferenceLine y={0} stroke="rgba(148, 163, 184, 0.6)" strokeDasharray="4 4" />
          <Line type="monotone" dataKey="etfScaled" name="etfReturn" stroke="#38bdf8" dot={false} strokeWidth={2} />
          <Line
            type="monotone"
            dataKey="benchmarkScaled"
            name="benchmarkReturn"
            stroke="#a855f7"
            dot={false}
            strokeWidth={2}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
