# 数据字典（EODHD 接口对齐）

> 样例响应位于 `docs/samples/`：
> - `eod_aapl.json`：`/api/eod/{SYMBOL}` 历史行情
> - `eod_bulk_us_20240103.json`：`/api/eod-bulk-last-day/{COUNTRY}` 收盘批量
> - `fundamentals_aapl.json`：`/api/fundamentals/{SYMBOL}`
> - `dividends_aapl.json`：`/api/div/{SYMBOL}`
> - `splits_aapl.json`：`/api/splits/{SYMBOL}`
> - `exchange_nasdaq_page1.json`：`/api/exchange-symbol-list/{EXCHANGE}`（默认返回全量，可结合 `offset` 分页）
>

## dim_symbol（标的维表）

| 字段 | 来源 | 类型 | 说明及缺省处理 |
| --- | --- | --- | --- |
| `symbol` | `Code` (`exchange-symbol-list`) | `varchar(20)` | 主键；带交易所后缀（如 `AAPL.US`）。 |
| `name` | `Name` | `varchar(200)` | 标的名称。缺失可置空。 |
| `exchange` | `Exchange` | `varchar(20)` | 交易所缩写（NASDAQ/NYSE/AMEX 等）。 |
| `asset_type` | `Type` | `varchar(20)` | `Common Stock`、`ETF` 等，用于区分股票/基金。 |
| `sector` | `General.Sector` (`fundamentals`) | `varchar(100)` | 行业；接口可能为空，需允许 NULL。 |
| `industry` | `General.Industry` | `varchar(100)` | 子行业；同上。 |
| `first_trade_date` | 无直接字段 | `date` | 可用 `IPODate`（若存在）转换；缺失则 NULL。 |
| `is_active` | 自定义 | `boolean` | 默认 `true`；若 `IsDelisted=true` 更新为 `false`。 |
| `created_at`/`updated_at` | 系统填充 | `timestamptz` | 记录插入/更新时间。 |

## stg_eod_quotes（行情原始层）

| 字段 | 来源 | 类型 | 说明及缺省处理 |
| --- | --- | --- | --- |
| `symbol` | `code`（批量）/路径参数（单标） | `varchar(20)` | 与 `dim_symbol.symbol` 对齐。 |
| `date` | `date` | `date` | 交易日；若接口缺失视为异常需重试。 |
| `open` | `open` | `numeric(16,6)` | 开盘价。部分停牌日可能为 NULL。 |
| `high` | `high` | `numeric(16,6)` | 最高价。 |
| `low` | `low` | `numeric(16,6)` | 最低价。 |
| `close` | `close` | `numeric(16,6)` | 收盘价。 |
| `adjusted_close` | `adjusted_close` | `numeric(16,6)` | 复权收盘价；若接口返回 `null`（极少见）需回退到 `close`。 |
| `volume` | `volume` | `bigint` | 成交量；若为 0/NULL，后续换手率需特别处理。 |
| `created_at`/`updated_at` | 系统填充 | `timestamptz` | 记录 ETL 时间戳。 |

**分页策略**：`/api/eod/{SYMBOL}` 可按 `from`/`to` 分段拉取；`/api/eod-bulk-last-day/{COUNTRY}` 支持 `date` 参数但无分页，需按交易日循环调用。

## stg_fundamentals（基本面原始层）

| 字段 | 来源 JSON 路径 | 类型 | 说明及缺省处理 |
| --- | --- | --- | --- |
| `symbol` | `General.Code` | `varchar(20)` | 与 `dim_symbol` 对齐。 |
| `"FiscalYearEnd"` | `General.FiscalYearEnd` | `varchar(10)` | 财年截止月份，可为 NULL。 |
| `"SharesOutstanding"` | `SharesStats.SharesOutstanding` | `numeric(20,4)` | 总股本，分母用于换手率。 |
| `"SharesFloat"` | `SharesStats.SharesFloat` | `numeric(20,4)` | 流通股数。 |
| `"MarketCapitalization"` | `Highlights.MarketCapitalization` | `numeric(20,4)` | 总市值（美元）。 |
| `"PERatio"` | `Highlights.PERatio` | `numeric(18,6)` | 市盈率（TTM）。 |
| `"PriceBookMRQ"` | `Valuation.PriceBookMRQ` | `numeric(18,6)` | 市净率，部分 ETF 为空。 |
| `"PriceSalesTTM"` | `Valuation.PriceSalesTTM` | `numeric(18,6)` | 市销率 TTM。 |
| `"DividendYield"` | `Highlights.DividendYield` | `numeric(10,6)` | 股息率；若公司未分红返回 0/NULL。 |
| `"DividendShare"` | `Highlights.DividendShare` | `numeric(18,6)` | 每股股息（TTM）。 |
| `"UpdatedAt"` | `General.UpdatedAt` | `timestamptz` | 接口更新时间，作为主键维度。 |
| `"Payload"` | 整体对象 | `jsonb` | 原始 JSON；便于补充其他字段或重算。 |
| `created_at`/`updated_at` | 系统填充 | `timestamptz` | 记录 ETL 时间戳。 |

**刷新策略**：`bulk-fundamentals` 支持 `offset` 分页（1000 条颗粒度），建议按交易所拆分并记录 `UpdatedAt` 判定增量。

## fact_corporate_actions（企业行为事件）

| 字段 | 来源 | 类型 | 说明及缺省处理 |
| --- | --- | --- | --- |
| `symbol` | 路径参数 | `varchar(20)` | 事件标的。 |
| `action_date` | `date` (`/div` 或 `/splits` 返回) | `date` | 生效日期。 |
| `action_type` | 手动赋值 | `varchar(20)` | `dividend` 或 `split`。 |
| `value` | `value`（拆分为比例/股息金额） | `numeric(18,6)` | 拆分接口字段 `ratio` 解析为数值（如 `4:1` → 4.0）；股息接口 `value` 原值。 |
| `description` | `declared_date`/`notes`（若有） | `varchar(200)` | 无字段时可拼接来源字段。 |
| `currency` | `currency` (`/div`) | `varchar(10)` | 拆分通常为空。 |
| `source_payload` | 原始 JSON | `jsonb` | 保留完整事件。 |
| `created_at`/`updated_at` | 系统填充 | `timestamptz` | 记录写入时间。 |

**注意**：分红接口可能返回空数组（无分红）；拆分数据稀疏但可通过扩大 `from` 范围获取历史事件（示例含 2020 年 4-for-1 拆分）。

## mart_daily_quotes（指标层）

| 字段 | 计算来源 | 类型 | 说明 |
| --- | --- | --- | --- |
| `symbol`, `trade_date`, `open`~`adjusted_close`, `volume`, `dividend`, `split_factor` | 直接来自 `stg_eod_quotes`/`fact_corporate_actions` | 与 staging 同型 | 按日同步最新值。 |
| `pre_close` | 前一日 `close` | `numeric(16,6)` | 若前一日缺失，用前一日 `adjusted_close`。 |
| `change_amt` | `close - pre_close` | `numeric(16,6)` | 若 `pre_close` 为 NULL，则置 NULL 并记录异常。 |
| `pct_chg` | `change_amt / pre_close` | `numeric(10,6)` | `pre_close` 为 0 或缺失时置 NULL；绝对值 ≥ 10,000 的异常波动会被截断为 NULL。 |
| `amount` | `volume * close` | `numeric(20,6)` | 若 volume 为 NULL/0，置 NULL。 |
| `turnover_rate` | `volume / SharesOutstanding` | `numeric(12,6)` | `SharesOutstanding` 缺失则置 NULL（ETF 依赖 `outstandingShares` 推导）；绝对值 ≥ 1,000,000 时视为异常改写为 NULL。 |
| `turnover_rate_f` | `volume / SharesFloat` | `numeric(12,6)` | 同上，若缺则回退为 `SharesOutstanding`；绝对值 ≥ 1,000,000 时改写为 NULL。 |
| `volume_ratio` | `volume / SMA(volume, n)` | `numeric(12,6)` | 默认使用 5 日平均；不足窗口（如首日）置 NULL 并作为监控阈值豁免；绝对值 ≥ 1,000,000 的离群值截断为 NULL。 |
| `pe` | `close / (EarningsShareTTM)` | `numeric(18,6)` | 如需使用 `Highlights.DilutedEpsTTM`；缺失则 NULL。 |
| `pe_ttm` | `Highlights.PERatio` | `numeric(18,6)` | 直接来自 fundamentals。 |
| `pb` | `close / BookValuePerShare` 或 `PriceBookMRQ` | `numeric(18,6)` | 优先使用原值，缺失时重算。 |
| `ps` | `close / RevenuePerShareTTM` | `numeric(18,6)` | 按需要使用 `PriceSalesTTM` 或自算。 |
| `ps_ttm` | `PriceSalesTTM` | `numeric(18,6)` | 来自 fundamentals。 |
| `dv_ratio` | `DividendYield` | `numeric(12,6)` | % 值；无分红为 0/NULL。 |
| `dv_ttm` | `DividendShare` | `numeric(18,6)` | 同上。 |
| `total_share` | `SharesOutstanding` | `numeric(20,4)` | 如需换算为“万股”可在写入时除以 10,000。 |
| `free_share` | `SharesFloat` | `numeric(20,4)` | 同上。 |
| `total_mv` | `close * SharesOutstanding` | `numeric(20,4)` | 缺少股本时置 NULL。 |
| `circ_mv` | `close * SharesFloat` | `numeric(20,4)` | 同上。 |
| `pct_chg_5d/10d/20d/60d` | `(adj_close / adj_close.shift(n)) - 1` | `numeric(10,6)` | 数据不足窗口时置 NULL；绝对值 ≥ 10,000 的结果被截断为 NULL。 |
| `created_at`/`updated_at` | 系统填充 | `timestamptz` | 记录刷新时间。 |

## 分页与缺失值说明
- `exchange-symbol-list` 默认返回完整列表，可通过 `api_token=...&limit=1000&offset=0` 手动分页；接口示例显示 `limit` 未生效，需结合官方文档确认/通过 `offset` 分块。
- `eod-bulk-last-day` 无分页，若需历史数据需逐日拉取；数据集中 `exchange_short_name` 可用于过滤（计划中落地为 `dim_symbol.exchange`）。
- 基本面字段存在缺失：特别是 ETF 的 `SharesOutstanding`、`PERatio`、`PriceBookMRQ` 可能为 NULL，ETL 中通过 `outstandingShares` 节点推导股本，仍缺失则保留 NULL 并在监控中提示。
- 分红/拆分接口返回空数组代表无事件，ETL 应判定无需写入。

## 对应关系总览

| 数据集 | 对应表 | 主要字段映射 |
| --- | --- | --- |
| `/api/exchange-symbol-list/{EXCHANGE}` | `dim_symbol` | `Code → symbol`, `Name`, `Exchange`, `Type → asset_type` |
| `/api/eod/{SYMBOL}`、`/api/eod-bulk-last-day/{COUNTRY}` | `stg_eod_quotes` | `date/open/high/low/close/adjusted_close/volume` |
| `/api/fundamentals/{SYMBOL}`、`/api/bulk-fundamentals/{EXCHANGE}` | `stg_fundamentals` | `General`, `Highlights`, `Valuation`, `SharesStats` |
| `/api/div/{SYMBOL}` `/api/splits/{SYMBOL}` | `fact_corporate_actions` | `date/value/currency` + 类型标识 |
| 计算衍生成果 | `mart_daily_quotes` | 来自 staging + SQL/脚本计算 |

数据字典可作为 ETL、QA 与后续分析的统一参考，任何新增字段需同步更新此文档。 
