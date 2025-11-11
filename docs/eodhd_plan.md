# EODHD 美股与 ETF 数据入库方案

## 1. 项目目标
- 获取近 10 年（自 2014-01-01 起）所有美股与 ETF 的日度行情与基础数据。
- 使用 EODHD Professional ($99.99) 计划提供的 API，在 PostgreSQL 中建立统一数据仓库。
- 收盘后执行增量更新，保证指标字段在日级别准时刷新。

## 2. 技术栈与运行环境
- **编程语言**: Python 3（核心依赖：`requests`、`tenacity`、`psycopg2-binary`、`python-dotenv`、`pandas`、`sqlalchemy`）。
- **数据库**: PostgreSQL 15+。
- **调度**: Linux `cron`（本机定时触发脚本）。
- **依赖管理**: 推荐使用 `python -m venv .venv && source .venv/bin/activate` 创建虚拟环境，并通过 `pip install -r requirements.txt` 或直接安装上述依赖；敏感配置统一放在 `.env`（见仓库根目录示例）。

## 3. 数据源与 API

### 3.1 主要接口
| 用途 | Endpoint | 关键参数 | 说明 |
| --- | --- | --- | --- |
| 日线行情 | `https://eodhd.com/api/eod/{SYMBOL}` | `from`, `to`, `period=d`, `adjusted=1`, `fmt=json/csv` | 单标的历史行情，支持 20+ 年。 |
| 日线批量 | `https://eodhd.com/api/eod-bulk-last-day/US` | `date`(可选，默认最新交易日), `fmt` | 收盘后全市场最新行情。 |
| 基本面 | `https://eodhd.com/api/fundamentals/{SYMBOL}` | `fmt=json` | 返回 General、Highlights、SharesStats、Financials。 |
| 基本面批量 | `https://eodhd.com/api/bulk-fundamentals/{EXCHANGE}` | `api_token`, `offset`, `limit`, `symbols` | 按交易所批量拉取股票/ETF 基本面与股本。 |
| 交易所列表 | `https://eodhd.com/api/exchange-symbol-list/{EXCHANGE}` | `type=stock/etf`, `fmt=json` | 获取交易所全部标的代码及元数据。 |
| 分红 | `https://eodhd.com/api/div/{SYMBOL}` | `from`, `to`, `fmt=json` | 历史现金股息事件。 |
| 拆分 | `https://eodhd.com/api/splits/{SYMBOL}` | `from`, `to`, `fmt=json` | 股票拆分、合股事件。 |

### 3.2 API 使用策略
- 利用 Professional 计划较高配额，优先使用 Bulk 接口减少请求次数。
- 历史补数按交易所和时间分片，加入 `sleep` 控制以避免瞬时速率超标。
- 月度或季度重新跑 `bulk-fundamentals`，保持 TTM/股本数据新鲜度。
- **字段命名原则**：所有“原始层”表（`stg_*`）的列名与 EODHD 接口字段保持一致，确保增量更新时可直接 upsert；衍生指标在“指标层”表（`mart_*`）新增列。

## 4. 历史补数流程
1. **加载标的清单**  
   - 调用 `exchange-symbol-list/NASDAQ|NYSE|AMEX`（filter: `type in ['Common Stock','ETF']`）。  
   - 将所有 symbol 写入 `dim_symbol`，记录上市日期、交易所、是否 ETF。
2. **基础维度补全**  
   - 对每个 symbol 查询 `fundamentals`，写入 `stg_fundamentals`，保留与 API 字段一致的列。  
   - 若批量接口返回体积过大，可按 1,000 条分页。
3. **行情拉取**  
   - 从 2014-01-01 分片（按年份或季度）请求 `api/eod`，先写入 `stg_eod_quotes`，保留与接口一致的字段。  
   - 使用 SQL/脚本将 `stg_eod_quotes` 转换并合并到指标层 `mart_daily_quotes`，生成额外衍生字段。
4. **企业行为**  
   - 拉取 `div` 与 `splits`，保存至 `fact_corporate_actions` 并在脚本内生成每日 `adj_factor`。  
   - 确保按 `split_date` 对历史行情回填调整系数。
5. **衍生指标计算**  
   - 使用 pandas/SQL 计算 `pre_close`, `change_amt`, `pct_chg`, 多日涨跌、换手率、量比、估值指标等。  
   - 结果写入 `mart_daily_quotes` 对应列。
6. **验收**  
   - 检查每个 symbol 在目标时间段内是否无缺口。  
   - 对比随机样本与 EODHD 官网或其他数据源，确认数据正确性。

## 5. 日终增量流程
1. **触发时间**: 纽约时间 18:00（收盘后约 2 小时，自动适配夏令时）；通过 `scripts/run_daily_update.sh` 触发可复用脚本内的 `TZ="America/New_York"` 推导逻辑，避免在尚未收盘时传入未来日期导致批量接口返回空数组。若需健康检查可先设置 `DAILY_UPDATE_DRY_RUN=true`，观察日志与心跳后再取消。  
2. **批量行情更新**: 调用 `eod-bulk-last-day/US` 获取当日所有 symbol 行情，先 upsert 至 `stg_eod_quotes`，再刷新 `mart_daily_quotes`。  
   - 如在收盘前或空交易日触发，`fetch_bulk_quotes` 会返回空列表并记录 WARN，需等待下一时段或手动传入可用日期重跑。  
3. **基本面轮询**:  
   - 针对当天有交易的 symbol（或全量）按需查询 `fundamentals`，upsert 至 `stg_fundamentals`。  
   - 建议按交易所分批（每日一批）刷新，以降低请求量，并同步最新股本/估值至 `mart_daily_quotes`。  
4. **企业行为检查**: 当天调用 `div`、`splits`，若有新记录写入 `fact_corporate_actions` 并更新 `adj_factor`。  
5. **衍生指标刷新**: 重新计算并更新 `mart_daily_quotes` 的换手率、估值、多日收益率等字段。  
6. **日志记录**: 输出执行耗时、成功条数、失败 symbol 列表到本地日志文件（按日期滚动）。

## 6. 数据处理规则
- `pre_close`: 取当前 symbol 前一交易日 `close`（若缺失，使用 `adjusted_close` 作 fallback）。  
- `change_amt`: `close - pre_close`。  
- `pct_chg`: `change_amt / pre_close`。  
- `amount`: `volume * close / 1000`（如需千元单位，可在 SQL 中转换）。  
- `turnover_rate`: `volume / SharesOutstanding`；`turnover_rate_f`: `volume / SharesFloat`。  
- `volume_ratio`: 默认与过去 5 个交易日平均成交量比较；可按业务需求调整窗口。  
- `pe/pb/ps`: 使用 `stg_fundamentals` 中的 TTM 指标与 `close` 推算日度估值。  
- `total_mv`: `close * SharesOutstanding`；`circ_mv`: `close * SharesFloat`。  
- 多日涨跌（5、10、20、60 日）：基于 `adjusted_close` 计算累计收益率。
- 拆分比例：对 `fact_corporate_actions` 中的 `ratio` 字符串（如 `4:1`、`1/8`）解析为数值，便于后续复权及监控。
- ETF 股本：若 `SharesStats` 缺失股本，从 `outstandingShares.annual/quarterly` 取最新 `shares` 补充；仍缺失时在指标层保留 NULL 并记录监控。

## 7. PostgreSQL 数据库设计

### 7.1 `dim_symbol`
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `symbol` | `varchar(20)` | 代码（如 `AAPL.US`），主键。 |
| `name` | `varchar(200)` | 公司/基金名称。 |
| `exchange` | `varchar(20)` | 交易所代码（NASDAQ/NYSE/AMEX 等）。 |
| `asset_type` | `varchar(20)` | `Common Stock`、`ETF`。 |
| `sector` | `varchar(100)` | 行业。 |
| `industry` | `varchar(100)` | 子行业。 |
| `first_trade_date` | `date` | 上市首日。 |
| `is_active` | `boolean` | 是否在交易。 |
| `created_at` | `timestamp` | 记录创建时间。 |
| `updated_at` | `timestamp` | 最近更新时间。 |

### 7.2 `stg_eod_quotes`
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `symbol` | `varchar(20)` | 交易代码，来源于 Bulk 接口返回字段。 |
| `date` | `date` | 交易日期（接口字段 `date`）。 |
| `open` | `numeric(16,6)` | 接口字段 `open`。 |
| `high` | `numeric(16,6)` | 接口字段 `high`。 |
| `low` | `numeric(16,6)` | 接口字段 `low`。 |
| `close` | `numeric(16,6)` | 接口字段 `close`。 |
| `adjusted_close` | `numeric(16,6)` | 接口字段 `adjusted_close`。 |
| `volume` | `bigint` | 接口字段 `volume`。 |
| `created_at` | `timestamp` | 插入时间。 |
| `updated_at` | `timestamp` | 最近更新时间。 |
| 主键 | `primary key (symbol, date)` | 与接口字段一一对应，便于直接 upsert。 |

> 若未来接口新增字段（如 `change`, `change_p`, `previous_close`），按原字段名增列即可。

### 7.3 `stg_fundamentals`
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `symbol` | `varchar(20)` | 外键引用 `dim_symbol.symbol`。 |
| `FiscalYearEnd` | `varchar(10)` | 对应 `General.FiscalYearEnd`。 |
| `SharesOutstanding` | `numeric(20,4)` | 对应 `SharesStats.SharesOutstanding`。 |
| `SharesFloat` | `numeric(20,4)` | 对应 `SharesStats.SharesFloat`。 |
| `MarketCapitalization` | `numeric(20,4)` | 对应 `Highlights.MarketCapitalization`。 |
| `PERatio` | `numeric(18,6)` | 对应 `Highlights.PERatio`。 |
| `PriceBookMRQ` | `numeric(18,6)` | 对应 `Valuation.PriceBookMRQ`（如果返回）。 |
| `PriceSalesTTM` | `numeric(18,6)` | 对应 `Valuation.PriceSalesTTM`。 |
| `DividendYield` | `numeric(10,6)` | 对应 `Highlights.DividendYield`。 |
| `DividendShare` | `numeric(18,6)` | 对应 `Highlights.DividendShare`。 |
| `UpdatedAt` | `timestamp` | `General.UpdatedAt`。 |
| `Payload` | `jsonb` | 保存完整 `fundamentals` JSON。 |
| `created_at` | `timestamp` | 创建时间。 |
| `updated_at` | `timestamp` | 最近更新时间。 |
| 主键 | `primary key (symbol, "UpdatedAt")` | 以 API 更新时间作为版本键。 |

> 列名保持与接口字段大小写一致，使用双引号建表或通过视图统一；如需长期留存历史版本，可保留多条不同 `UpdatedAt`。

### 7.4 `fact_corporate_actions`
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `symbol` | `varchar(20)` | 外键引用 `dim_symbol`。 |
| `action_date` | `date` | 事件生效日期。 |
| `action_type` | `varchar(20)` | `dividend` / `split`。 |
| `value` | `numeric(18,6)` | 股息金额或拆分比例。 |
| `description` | `varchar(200)` | 事件说明。 |
| `currency` | `varchar(10)` | 股息货币，拆分则可空。 |
| `source_payload` | `jsonb` | 原始事件 JSON。 |
| `created_at` | `timestamp` | 创建时间。 |
| `updated_at` | `timestamp` | 更新时间。 |
| 主键 | `primary key (symbol, action_date, action_type)` | 保证唯一。 |

### 7.5 `mart_daily_quotes`
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `symbol` | `varchar(20)` | 外键引用 `dim_symbol`。 |
| `trade_date` | `date` | 对应 `stg_eod_quotes.date`。 |
| `open` | `numeric(16,6)` | 直接来自 `stg_eod_quotes.open`。 |
| `high` | `numeric(16,6)` | 同上。 |
| `low` | `numeric(16,6)` | 同上。 |
| `close` | `numeric(16,6)` | 同上。 |
| `adjusted_close` | `numeric(16,6)` | `stg_eod_quotes.adjusted_close`。 |
| `volume` | `bigint` | `stg_eod_quotes.volume`。 |
| `dividend` | `numeric(16,6)` | 来自企业行为或 Bulk 接口。 |
| `split_factor` | `numeric(16,6)` | 同上。 |
| `pre_close` | `numeric(16,6)` | 前收价。 |
| `change_amt` | `numeric(16,6)` | 涨跌额。 |
| `pct_chg` | `numeric(10,6)` | 涨跌幅。 |
| `amount` | `numeric(20,6)` | 成交额。 |
| `turnover_rate` | `numeric(12,6)` | 换手率（总股本）。 |
| `turnover_rate_f` | `numeric(12,6)` | 换手率（流通股）。 |
| `volume_ratio` | `numeric(12,6)` | 量比。 |
| `pe` | `numeric(18,6)` | 市盈率（按日价）。 |
| `pe_ttm` | `numeric(18,6)` | 市盈率（TTM 复核值）。 |
| `pb` | `numeric(18,6)` | 市净率。 |
| `ps` | `numeric(18,6)` | 市销率。 |
| `ps_ttm` | `numeric(18,6)` | 市销率 TTM。 |
| `dv_ratio` | `numeric(12,6)` | 股息率（%）。 |
| `dv_ttm` | `numeric(18,6)` | 股息 TTM。 |
| `total_share` | `numeric(20,4)` | 总股本（万股或按实际单位）。 |
| `free_share` | `numeric(20,4)` | 流通股。 |
| `total_mv` | `numeric(20,4)` | 总市值（`close * SharesOutstanding`）。 |
| `circ_mv` | `numeric(20,4)` | 流通市值。 |
| `pct_chg_5d` | `numeric(10,6)` | 5 日涨跌幅。 |
| `pct_chg_10d` | `numeric(10,6)` | 10 日涨跌幅。 |
| `pct_chg_20d` | `numeric(10,6)` | 20 日涨跌幅。 |
| `pct_chg_60d` | `numeric(10,6)` | 60 日涨跌幅。 |
| `created_at` | `timestamp` | 创建时间。 |
| `updated_at` | `timestamp` | 更新时间。 |
| 主键 | `primary key (symbol, trade_date)` | 唯一约束。 |
| 索引 | `index (trade_date)` | 支撑日期范围查询。 |

### 7.6 `etl_job_status`
| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `job_name` | `varchar(50)` | 任务名称（如 `history_load`, `daily_update`）。 |
| `symbol` | `varchar(20)` | 若任务分标的执行则记录；全量任务可为 `ALL`。 |
| `last_run_at` | `timestamp` | 最近执行时间。 |
| `status` | `varchar(20)` | `success` / `failed` / `running`。 |
| `message` | `text` | 错误或摘要信息。 |
| `duration_seconds` | `numeric(10,2)` | 执行耗时。 |
| 主键 | `primary key (job_name, symbol)` | 保证可覆盖重启恢复。 |

## 8. Python 项目结构建议
```
project_root/
├── docs/
│   └── eodhd_plan.md
├── scripts/
│   ├── api_client.py
│   ├── auto_backfill.py
│   ├── backfill.py
│   ├── config.py
│   ├── daily_update.py
│   ├── db.py
│   ├── etl_loaders.py
│   └── utils.py
├── config/
│   ├── settings.prod.toml
│   └── settings.dev.toml
├── requirements.txt / pyproject.toml
└── README.md
```

## 9. 调度方案（cron）
- 历史补数（一次性）：  
  `0 2 * * * cd /path/to/us_equity && /usr/bin/python3 -m scripts.backfill --start 2014-01-01 --exchange NASDAQ >> /var/log/eodhd_history.log 2>&1`
- 每日收盘增量：  
  `45 16 * * 1-5 TZ=America/New_York cd /path/to/us_equity && /usr/bin/python3 -m scripts.daily_update --refresh-fundamentals >> /var/log/eodhd_daily.log 2>&1`
- 每周基础信息刷新（示例）：  
  `0 3 * * 6 TZ=America/New_York cd /path/to/us_equity && /usr/bin/python3 -m scripts.daily_update --refresh-fundamentals --skip-dividends --lookback-days 0 >> /var/log/eodhd_fundamentals.log 2>&1`

## 10. 里程碑计划
1. **第 1 周**: 环境搭建、PostgreSQL 初始化、API client 与基础脚手架。  
接口场景验证: 按 stg_* 需求，手动调用每个核心 API（批量行情、fundamentals、企业行为）并保存示例响应，确认字段映射、分页策略与潜在缺失值。
数据字典落地: 结合接口示例编写字段说明文档（来源、类型、计算方式、空值处理），方便后续开发与校验。
ETL 流程设计: 细化“历史补数”与“日终增量”步骤，列出每个阶段的输入/输出表、依赖顺序及失败重试策略。
任务调度规划: 定义 cron 表达式、日志路径、运行顺序，拟定运行手册，确保部署时只需填入脚本即可执行。
2. **第 2 周**: 完成 `dim_symbol`、`fact_fundamentals`、`fact_corporate_actions` 历史补数。  
3. **第 3 周**: 拉取 10 年日线行情并完成衍生指标计算。  
4. **第 4 周**: 打通日终增量流程，配置 cron 与日志，进行验收测试。  
5. **后续维护**: 定期跑基础信息刷新并监控数据质量。
