# ETF FastAPI 服务部署指引

本文档说明如何在本机启动 `api.main:app` 服务、加载 PostgreSQL 聚合数据，并为前端提供 ETF 周期收益接口。

## 1. 运行环境

- Python 3.11+（建议与 ETL 共用 `.venv`）。
- 依赖包：

  ```bash
  pip install fastapi uvicorn[standard] asyncpg python-dotenv
  ```

- 环境变量：
  - `PGHOST` / `PGPORT` / `PGDATABASE` / `PGUSER` / `PGPASSWORD`
  - `API_AUTH_TOKEN`：可选，若设置则所有请求必须携带 `X-API-Token` 头。
  - `ETF_DEFAULT_RETURN_YEARS`：可选，控制统计接口默认回溯的年度数量（默认 10）。
  - `ETF_DEFAULT_BENCHMARK`：可选，累计收益对比接口的默认基准，默认为 `SPY.US`。
  - `API_CORS_ORIGINS`：可选，逗号分隔的允许跨域来源，默认包含 `http://localhost:5173` 与 `http://127.0.0.1:5173`。

## 2. 启动方式

```bash
uvicorn api.main:app --host 127.0.0.1 --port 8080
```

- 仅在本机监听，前端请通过 `http://127.0.0.1:8080` 访问。
- 建议在生产环境使用 `systemd`：

  ```ini
  [Unit]
  Description=ETF FastAPI Service

  [Service]
  WorkingDirectory=/root/us_equity
  EnvironmentFile=/root/us_equity/.env
  ExecStart=/root/us_equity/.venv/bin/uvicorn api.main:app --host 127.0.0.1 --port 8080
  Restart=on-failure

  [Install]
  WantedBy=multi-user.target
  ```

## 3. 接口概览

### 3.1 `GET /api/etfs/{symbol}/returns`

- 参数：
  - `period`：`year`（默认）或 `month`。
  - `limit`：返回的周期数量（年度 ≤30，月度建议 120）。
- 返回示例：

  ```json
  {
    "symbol": "SPY.US",
    "period": "year",
    "rows": [
      {
        "periodKey": "2024",
        "periodStart": "2024-01-01",
        "periodEnd": "2024-12-31",
        "tradingDays": 252,
        "totalReturnPct": 0.2421,
        "compoundReturnPct": 0.2399,
        "volatilityPct": 0.1825,
        "maxDrawdownPct": -0.1164
      }
    ]
  }
  ```

### 3.2 `GET /api/etfs/{symbol}/stats`

- 参数：`windowYears`（默认 10，范围 1–30）。
- 返回字段包含总收益、平均年化、最大回撤、波动率，以及最佳/最差年度。

### 3.3 `GET /api/etfs/{symbol}/performance`

- 参数：
  - `interval`：`day`（默认）、`month`、`year`，控制聚合粒度。
  - `years`：向后回溯的年份跨度（默认 10，范围 1–30）。
  - `benchmark`：可选，指定替代基准 symbol，默认取 `ETF_DEFAULT_BENCHMARK`。
- 返回示例：

  ```json
  {
    "symbol": "TECL.US",
    "benchmark": "SPY.US",
    "interval": "day",
    "startDate": "2015-11-03",
    "endDate": "2025-11-03",
    "points": [
      {
        "date": "2015-11-03",
        "etfValue": 1.0,
        "benchmarkValue": 1.0,
        "etfCumulativeReturnPct": 0.0,
        "benchmarkCumulativeReturnPct": 0.0,
        "spreadPct": 0.0
      }
    ]
  }
  ```

### 3.4 `GET /healthz`

- 健康检查端点，返回 `{ "status": "ok" }`。

## 4. 安全与访问控制

- 若设置了 `API_AUTH_TOKEN`，前端需在请求头携带 `X-API-Token: <token>`。
- 建议通过防火墙/Nginx 限制仅允许本机或受信网段访问 8080 端口。

## 5. 与前端集成

- `web` 项目新增 `.env.local`：

  ```bash
  VITE_API_BASE_URL=http://127.0.0.1:8080
  VITE_API_TOKEN=<可选，与 API_AUTH_TOKEN 匹配>
  ```

- 在前端封装请求工具时，统一追加 `X-API-Token` 头，并针对年度/月度详情分别调用：
  - `/api/etfs/{symbol}/returns?period=year&limit=10`
  - `/api/etfs/{symbol}/returns?period=month&limit=120`
  - `/api/etfs/{symbol}/stats?windowYears=10`
  - `/api/etfs/{symbol}/performance?interval=day&years=10`

- ETF 榜单详情页可先加载年度收益，待用户打开月度 Tab 时再并发请求月度数据与统计信息。

## 6. 后端数据刷新

- `scripts.backfill` / `scripts.daily_update` 已在写入 `mart_daily_quotes` 后调用 `refresh_mart_etf_periodic_returns`，确保新表及时更新。
- 如需手动刷新：

  ```sql
SELECT refresh_mart_etf_periodic_returns(NULL, NULL, NULL); -- 全量，默认最近 10 年
SELECT refresh_mart_etf_periodic_returns(ARRAY['SPY.US'], '2024-01-01', '2024-12-31'); -- 指定标的与时间窗口
SELECT period_type, COUNT(*) FROM mart_etf_periodic_returns GROUP BY period_type; -- 校验记录量
  ```

若后续扩展到公网环境，可在现有结构上增加反向代理、限速、监控等能力。当前版本仅面向同机访问，便于与 Vite 前端联调。 
