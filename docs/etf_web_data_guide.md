# 美股 ETF 排行数据与前端集成说明

> 本文梳理 EODHD 数据落地、排行榜计算脚本以及 Vite 前端的整体衔接方式，供运营和开发在更新、排查或扩展网站时参考。字段细节如需更深入说明，可结合 `docs/data_dictionary.md`、`docs/etl_runbook.md` 以及 `docs/etf_rankings_notes.md`。

## 1. 系统概览

- **数据来源**：EODHD Professional 计划提供的 REST API（行情、基本面、分红、拆分、交易所列表）。
- **数据落地**：`scripts/backfill.py` 与 `scripts/daily_update.py` 将原始数据写入 PostgreSQL（`stg_*`、`dim_symbol`、`fact_corporate_actions`、`mart_daily_quotes`）。
- **排行榜生成**：`python -m scripts.etf_rankings` 读取 `mart_daily_quotes`，计算 5 年、10 年收益及重合榜单，输出 CSV 至 `outputs/` 或指定目录。
- **前端展示**：`web/` 下 Vite + React 应用。榜单页面仍加载 `web/public/data/*.csv`，同时在 ETF 详情页通过 FastAPI (`/api/etfs/{symbol}/returns|stats`) 动态拉取年度、月度收益及统计指标。

## 2. 外部 API 与运行环境

| 场景 | Endpoint | 关键参数 | 说明 |
| --- | --- | --- | --- |
| 单标历史行情 | `/api/eod/{SYMBOL}` | `from`, `to`, `period=d`, `adjusted=1` | 回填历史；补数脚本按年度/季度分片调用。 |
| 收盘批量行情 | `/api/eod-bulk-last-day/US` | `date`(可选) | 日终更新主入口，返回当日全市场。 |
| 基本面单标 | `/api/fundamentals/{SYMBOL}` | — | 解析股本、估值、行业等字段，弥补缺失数据。 |
| 基本面批量 | `/api/bulk-fundamentals/{EXCHANGE}` | `offset`, `limit` | 周期性刷新，保持 `SharesStats` 等字段最新。 |
| 分红/拆分 | `/api/div/{SYMBOL}`、`/api/splits/{SYMBOL}` | `from`, `to` | 写入 `fact_corporate_actions`，供指标层使用。 |
| 交易所列表 | `/api/exchange-symbol-list/{EXCHANGE}` | `type=stock/etf` | 初始化或补全 `dim_symbol`。 |

运行脚本前需加载 `.env` 中的凭据：`EODHD_API_TOKEN`, `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER`, `PGPASSWORD`, `EODHD_TIMEOUT`（可选）。建议使用 `export $(grep -v '^#' .env | xargs)` 或在调度器内显式配置。

## 3. 数据库表与指标依赖关系

排行榜脚本主要依赖以下表：

- **`dim_symbol`**：记录标的基本信息（`symbol`, `name`, `exchange`, `asset_type`, `sector`, `industry`）。`scripts/etl_loaders.upsert_symbol` 会对 symbol 做规范化处理（优先 `PrimaryTicker`，否则拼接交易所后缀）。
- **`stg_eod_quotes`**：原始日行情，保留 `open`~`adjusted_close`、`volume` 等字段。指标层在刷新时通过 `mart_daily_quotes` 引用。
- **`stg_fundamentals`**：存储股本、估值、股息，含原始 `Payload`。脚本会从 `SharesStats`、`outstandingShares` 中推导股本，用于换手率和市值。
- **`fact_corporate_actions`**：记录分红（`dividend`）与拆分（`split`），拆分比会在刷新 mart 时参与复权和过滤逻辑。
- **`mart_daily_quotes`**：衍生指标层，包含 `total_return` 计算所需的 `adjusted_close`、`trade_date`、`SharesOutstanding` 等字段。排行榜 SQL 即基于此表窗口化计算。

更多字段与处理细节可参考 `docs/data_dictionary.md`。

## 4. 排行榜计算脚本

- **入口**：`python -m scripts.etf_rankings [--fudge-days N] [--csv-dir PATH] [--top-5y N] [--top-10y N]`。
- **核心逻辑**：
  - `fetch_period_performance(window_years=5|10)` 会：
    - 查找 `mart_daily_quotes` 最新交易日；
    - 依据窗口（5 年 / 10 年）向前回溯，确保首尾报价可用；
    - 计算持有天数、累计收益（`end_price/start_price - 1`）与年化收益（`(end_price/start_price)^(365.25/holding_days) - 1`）。
  - 交易日覆盖率阈值写死在 `MIN_TRADING_DAY_RATIO = 0.55`，并排除窗口内出现 `value < 1` 拆分的 ETF（见 `docs/etf_rankings_notes.md`）。
- **输出**：默认打印排行榜，同时可通过 `--csv-dir` 生成 `etf_rankings_5y.csv`、`etf_rankings_10y.csv`、`etf_rankings_overlap.csv`。仓库当前样例位于 `outputs/`（计算后手工拷贝到 `web/public/data/` 供前端食用）。
- **调试参数**：`--top` 兼容旧版用法；`--log-level DEBUG` 可观察 SQL 运行情况。

## 5. CSV 数据字典

### 5.1 `etf_rankings_5y.csv` / `etf_rankings_10y.csv`

| 字段 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- |
| `rank` | 整数 | `1` | 按累计收益降序排列；当传入 `--top` 时已截断。 |
| `symbol` | 字符串 | `USD.US` | 与 `dim_symbol.symbol` 对齐；前端展示时移除 `.US` 后缀。 |
| `name` | 字符串 | `ProShares Ultra Semiconductors` | 基金名称，来自 `dim_symbol.name`。 |
| `start_date` | 日期字符串 | `2020-11-03` | 窗口起始交易日，允许与窗口起点相差 `fudge_days`。 |
| `end_date` | 日期字符串 | `2025-11-03` | 窗口终止交易日（通常为最新交易日）。 |
| `holding_days` | 整数 | `1826` | `end_date - start_date` 的日历天数。 |
| `total_return` | 浮点 | `12.2041122296` | 累计收益倍数（终值/起始价 - 1）。 |
| `annualized_return` | 浮点 | `0.6756084003` | 年化收益率；前端使用 `%` 格式化。 |

### 5.2 `etf_rankings_overlap.csv`

| 字段 | 类型 | 示例 | 说明 |
| --- | --- | --- | --- |
| `rank` | 整数 | `1` | 同上，按照 5 年榜单顺序排序。 |
| `symbol` | 字符串 | `USD.US` | 同上。 |
| `name` | 字符串 | `ProShares Ultra Semiconductors` | 同上。 |
| `start_date_5y`/`end_date_5y` | 日期字符串 | `2020-11-03` | 5 年窗口对应的起止日。 |
| `holding_days_5y` | 整数 | `1826` | 5 年窗口持有天数。 |
| `total_return_5y` | 浮点 | `12.2041...` | 5 年累计收益。 |
| `annualized_return_5y` | 浮点 | `0.6756...` | 5 年年化收益率。 |
| `start_date_10y`/`end_date_10y` | 日期字符串 | `2015-11-03` | 10 年窗口对应的起止日。 |
| `holding_days_10y` | 整数 | `3653` | 10 年窗口持有天数。 |
| `total_return_10y` | 浮点 | `71.2489...` | 10 年累计收益。 |
| `annualized_return_10y` | 浮点 | `0.5341...` | 10 年年化收益率。 |

所有 CSV 均为 UTF-8 带表头格式，前端利用 `Papa.parse` 解析，`Number()` 转换数字列，并通过 `Number.isFinite` 过滤掉异常或缺失行。

## 6. Vite 前端数据结构

- **配置**：`web/src/App.tsx` 中定义 `DATASET_CONFIGS`，包含 `id`, `title`, `file`, `type`。对应类型在 `web/src/types.ts` 中声明（`DatasetConfig`, `DatasetKey`, `DatasetState`）。
- **数据加载**：
  - `web/src/utils/csv.ts` 提供 `loadEtfCsv` 与 `loadOverlapCsv`，二者使用 `fetch('/data/xxx.csv')`、`Papa.parse` 解析为对象数组。
  - 加载成功后，将状态设置为 `{ status: 'ready', data }`；失败时返回错误文本（显示在页面中）。
- **展示组件**：
  - `RankingTable`（单窗口榜单）与 `OverlapTable`（双窗口对比）负责渲染表格，并使用 `web/src/utils/format.ts` 将数值格式化（百分比、倍数、整数）。
  - 历史 top3 行应用 `ranking-table__row--top` 高亮样式。
- **路由**：`BrowserRouter` + `react-router-dom`，路径 `/five-year`、`/ten-year`、`/overlap` 分别加载对应数据集。默认跳转到 `/five-year`。
- **静态资源位置**：部署时需确保 CSV 位于构建产物的 `/data/` 目录（即 `web/public/data/`），Vite 构建会原样拷贝。

## 7. 数据更新与发布流程

1. **刷新数据库**：根据需要运行 `scripts.backfill`（历史）或 `scripts.daily_update`（日常）。保证 `mart_daily_quotes` 含最新交易日。
2. **生成排行榜**：执行 `python -m scripts.etf_rankings --csv-dir outputs`（或自定义目录）。复核日志与终端输出，关注“交易日覆盖”告警。
3. **校验 CSV**：
   - 打开 `outputs/*.csv`，确认表头、日期范围是否正确；
   - 可通过 `head`/`tail` 检查排名是否合理，必要时抽样与 SQL 比对。
4. **同步到前端**：将生成的 CSV 覆盖 `web/public/data/` 下同名文件。保持文件名不变以避免前端路由改动。
5. **本地预览**：在 `web/` 目录运行 `npm install`（首次）和 `npm run dev`（或 `npm run preview`）确认页面渲染正常、数值显示符合预期。
6. **构建发布**：执行 `npm run build` 生成 `dist/`，按部署策略上传静态文件。若使用 CDN，建议刷新缓存以确保新 CSV 生效。

## 8. 数据质量与注意事项

- **交易日覆盖率**：若 ETF 在窗口内停牌或仅有零星行情，脚本会因覆盖率不足被剔除。可参考 `docs/etf_rankings_notes.md` 调整阈值或补充成立日过滤。
- **拆分与复权**：脚本已排除 `value < 1` 的拆分事件；若后续新增其他类型（合股、并基等），需评估对收益计算的影响。
- **股本缺失**：部分 ETF `SharesOutstanding`/`SharesFloat` 仍可能为空，会导致换手率等指标为 NULL，但不影响收益榜单。若计划在前端增加估值或换手展示，需先完善股本数据。
- **数值精度**：CSV 中收益字段保留多位小数；前端格式化为百分比或“×”倍数，若用于导出报告，可在脚本侧控制保留位数。
- **时区与日期**：所有日期使用 UTC（与数据库一致）。若前端需要显示北京时间，可在组件中额外转换。
- **缓存策略**：生产环境若使用 CDN/浏览器缓存，建议在替换 CSV 后刷新缓存或追加版本参数（例如在 `DatasetConfig.file` 后附 `?v=20251105` 以确保新数据生效）。

## 9. 扩展建议

- **新增榜单**：若要增加 3 年/15 年等窗口，可复用 `fetch_period_performance`，添加新的 `DatasetConfig` 和 CSV 输出。
- **API 接口化**：如需改为动态接口，可在后端暴露 REST/GraphQL，返回与 CSV 等价的字段结构，前端再替换 `fetch` URL。
- **图表展示**：项目已引入 `recharts` 依赖，后续可基于当前数据集增添趋势或对比图，注意在加载阶段复用 `DatasetState`。

如对某字段或计算逻辑存在疑问，建议先查阅 `docs/data_dictionary.md` 与相关脚本，再在数据库中抽样验证。若仍有不确定，请在群内或 Issue 中确认后再调整。

## 10. ETF 详情页动态数据

- **接口依赖**：详情页调用 `GET /api/etfs/{symbol}/returns`（年度/首次加载、月度/按需加载）和 `GET /api/etfs/{symbol}/stats` 两类 REST 接口。默认分别请求 10 条年度、120 条月度记录，可通过 `VITE_ETF_YEAR_LIMIT`、`VITE_ETF_MONTH_LIMIT`、`VITE_ETF_STATS_YEARS` 调整。
- **请求节奏**：年度收益与统计指标在进入页面后即加载；月度收益在用户切换 Tab 时触发，避免首屏等待过长。所有请求自动附带 `X-API-Token` 头（如启用）。
- **数据回显**：收益表按 `period_key` 倒序展示，字段含总收益、复利收益、最大回撤、波动率与交易日。统计卡片显示总收益、平均年化、最大回撤、平均波动率及时间范围。
- **错误处理**：接口异常时直接在页面提示失败信息，方便排查。可在浏览器 DevTools 确认请求 URL 与返回码，必要时通过 `docs/api_server.md` 中 SQL 样例手动校验数据库。
