import { useEffect, useState } from 'react'
import { NavLink, Navigate, Route, Routes, useNavigate } from 'react-router-dom'

import './App.css'
import { OverlapTable } from './components/OverlapTable'
import { RankingTable } from './components/RankingTable'
import { loadEtfCsv, loadOverlapCsv } from './utils/csv'
import type {
  DatasetConfig,
  DatasetKey,
  DatasetState,
  EtfRanking,
  OverlapRanking
} from './types'
import { EtfDetailPage } from './pages/EtfDetailPage'
import { IndustryDetailPage } from './pages/IndustryDetailPage'
import { IndustryExplorerPage } from './pages/IndustryExplorerPage'

const DATASET_CONFIGS: DatasetConfig[] = [
  {
    id: 'fiveYear',
    title: '五年榜单',
    description: '',
    file: '/data/etf_rankings_5y.csv',
    type: 'single'
  },
  {
    id: 'tenYear',
    title: '十年榜单',
    description: '',
    file: '/data/etf_rankings_10y.csv',
    type: 'single'
  },
  {
    id: 'overlap',
    title: '重合榜单',
    description: '',
    file: '/data/etf_rankings_overlap.csv',
    type: 'overlap'
  }
]

const DATASET_CONFIG_MAP = DATASET_CONFIGS.reduce<Record<DatasetKey, DatasetConfig>>(
  (acc, config) => {
    acc[config.id] = config
    return acc
  },
  {} as Record<DatasetKey, DatasetConfig>
)

function DatasetPage({ datasetId }: { datasetId: DatasetKey }) {
  const config = DATASET_CONFIG_MAP[datasetId]
  const navigate = useNavigate()
  const [state, setState] = useState<DatasetState<EtfRanking[] | OverlapRanking[]>>({
    status: 'loading',
    data: []
  })

  useEffect(() => {
    let active = true
    setState({ status: 'loading', data: [] })

    const loader = config.type === 'overlap' ? loadOverlapCsv : loadEtfCsv

    loader(config.file)
      .then((data) => {
        if (!active) return
        setState({ status: 'ready', data })
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
  }, [config])

  return (
    <div className="dataset-page">
      <h1 className="dataset-page__title">{config.title}</h1>
      {state.status === 'loading' ? (
        <div className="dataset-page__status">加载数据中...</div>
      ) : state.status === 'error' ? (
        <div className="dataset-page__status dataset-page__status--error">
          数据加载失败：{state.error}
        </div>
      ) : (
        <div className="dataset-page__table">
          {config.type === 'overlap' ? (
            <OverlapTable data={state.data as OverlapRanking[]} />
          ) : (
            <RankingTable
              data={state.data as EtfRanking[]}
              onSelect={(row) =>
                navigate(`/etf/${row.symbol}`, {
                  state: { name: row.name }
                })
              }
            />
          )}
        </div>
      )}
    </div>
  )
}

function App() {
  return (
    <div className="app">
      <header className="top-bar">
        <div className="top-bar__title">美股 ETF 排行数据</div>
        <nav className="top-bar__nav">
          <NavLink
            to="/five-year"
            className={({ isActive }) =>
              isActive ? 'top-bar__link top-bar__link--active' : 'top-bar__link'
            }
          >
            五年榜单
          </NavLink>
          <NavLink
            to="/ten-year"
            className={({ isActive }) =>
              isActive ? 'top-bar__link top-bar__link--active' : 'top-bar__link'
            }
          >
            十年榜单
          </NavLink>
          <NavLink
            to="/overlap"
            className={({ isActive }) =>
              isActive ? 'top-bar__link top-bar__link--active' : 'top-bar__link'
            }
          >
            双榜重合
          </NavLink>
          <NavLink
            to="/industries"
            className={({ isActive }) =>
              isActive ? 'top-bar__link top-bar__link--active' : 'top-bar__link'
            }
          >
            行业板块
          </NavLink>
        </nav>
      </header>

      <main className="main-content">
        <Routes>
          <Route path="/" element={<Navigate to="/five-year" replace />} />
          <Route path="/five-year" element={<DatasetPage datasetId="fiveYear" />} />
          <Route path="/ten-year" element={<DatasetPage datasetId="tenYear" />} />
          <Route path="/overlap" element={<DatasetPage datasetId="overlap" />} />
          <Route path="/industries" element={<IndustryExplorerPage />} />
          <Route path="/industries/:sector/:industry" element={<IndustryDetailPage />} />
          <Route path="/etf/:symbol" element={<EtfDetailPage />} />
          <Route path="*" element={<Navigate to="/five-year" replace />} />
        </Routes>
      </main>
    </div>
  )
}

export default App
