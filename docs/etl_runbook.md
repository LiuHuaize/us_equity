# EODHD 数据管道运行手册

> 基于 `docs/eodhd_plan.md` 的总体架构与 `docs/data_dictionary.md` 字段定义。本手册聚焦历史补数与日终增量的执行流程、输入输出、依赖关系、验证与重试策略，作为开发与运维的运行指南。

## 1. 历史补数流程（one-off）

### 1.1 执行概览

| 阶段 | 输入 | 处理 | 输出 | 依赖与检查 | 失败策略 |
| --- | --- | --- | --- | --- | --- |
| S1 获取标的清单 | EODHD `/exchange-symbol-list/{EXCHANGE}`（NASDAQ/NYSE/AMEX） | 先请求 `type=stock`、再请求 `type=etf`，合并去重并保存 `docs/samples/...` | `dim_symbol`（新增/更新） | 确认返回条数与官方数相符；去重后写库 | 请求失败 → 重试 3 次；仍失败记录 `etl_job_status` 并终止后续阶段 |
| S2 批量基本面 | `/bulk-fundamentals/{EXCHANGE}` | 每 1000 条分页，写入 `stg_fundamentals`（使用 `UpdatedAt`） | `stg_fundamentals`、`dim_symbol` 行业信息补全 | 校验非空字段（`General.Code`、`SharesStats`），记录缺失值统计 | 遇到 HTTP/解析错误 → 记录偏移量，重跑该分页；连续失败则终止流程 |
| S3 历史行情 | `/eod/{SYMBOL}` 按年/季度 | 将数据写入 `stg_eod_quotes` | `stg_eod_quotes` | 校验日期连续、字段齐备；确认最新日期覆盖至目标日 | 遇错误 → 标记 `symbol + date_range`，稍后重跑；若多次失败，记录于 `etl_job_status` |
| S4 企业行为 | `/div/{SYMBOL}`、`/splits/{SYMBOL}` | 收集历史分红、拆分，写入 `fact_corporate_actions` | `fact_corporate_actions` | 对齐历史关键事件（如 AAPL 2020 拆分） | 网络错误 → 重试；数据缺失 → 记录警告，继续流程 |
| S5 指标计算 | 集成 S2~S4 结果 | 计算换手、估值、多日涨跌（见数据字典），并刷新 ETF 周期收益视图 | `mart_daily_quotes`、`mart_etf_periodic_returns` | 抽样校验算式，确保数值合理（如 turnover ≤ 5）；抽查年度收益是否与累计收盘价一致 | 若缺基础数据导致空值 → 记录 `mart_daily_quotes` 的空值比例 |
| S6 QA 验证 | `mart_daily_quotes` | 随机抽样 50 条与原始接口对照 | QA 报告 | 记录差异并修复 | 如差异重大 → 回滚对应日期数据并重算 |

### 1.2 具体执行建议
- **进度记录**：`etl_job_status` 增加 `history_symbols` 子任务（记录当前 symbol 与执行阶段）。
- **节流策略**：控制每秒不超过 5 个请求，批量接口间隔 0.5s，单个 symbol 历史抓取间隔 0.1s。
- **数据落地**：对于历史大批量，可分批 `INSERT`（1,000 行/批）。必要时使用 `COPY` 提升速度。
- **重跑**：历史补数允许多次执行，采用 `UPSERT` 确保重复写入不会产生冲突。

### 1.3 执行计划表（建议）

| 阶段 | 目标标的 | 主要接口 | 批次策略 | 预估请求数 | 预估耗时 | 备注 |
| --- | --- | --- | --- | --- | --- | --- |
| P0 | 全部交易所列表 | `/exchange-symbol-list/NASDAQ` 等 | 每交易所 1 次 | ~3 | <5 分钟 | 初始化 `dim_symbol` |
| P1 | NASDAQ 股票/ETF 基本面 | `/bulk-fundamentals/NASDAQ` | 1000 条/批，共约 5 批 | ~5 | ~10 分钟 | 批间隔 1 秒，记录 `offset` |
| P2 | NYSE 股票/ETF 基本面 | `/bulk-fundamentals/NYSE` | 1000 条/批，共约 4 批 | ~4 | ~8 分钟 | 与 P1 串行或并行 |
| P3 | AMEX 股票/ETF 基本面 | `/bulk-fundamentals/AMEX` | 1000 条/批，共约 1 批 | ~1 | ~2 分钟 | |
| P4 | NASDAQ 历史行情（2014~今） | `/eod/{SYMBOL}` | 按 symbol×年度分段 | ~150k | 6–8 小时 | 每请求间隔 0.1 秒 |
| P5 | NYSE 历史行情 | `/eod/{SYMBOL}` | 同上 | ~120k | 5–7 小时 | 可按市值排序优先补数 |
| P6 | AMEX 历史行情 | `/eod/{SYMBOL}` | 同上 | ~30k | 2–3 小时 | |
| P7 | ETF 专项核对 | `/eod/{SYMBOL}` | ETF 列表逐一补全 | — | 1–2 小时 | 保证 ETF 与股票均覆盖 |
| P8 | 企业行为（全部标的） | `/div` & `/splits` | 每 symbol 1 次 | ~10k | ~1 小时 | 分红数据量较少 |
| P9 | 指标生成 + QA | DB 内部 | SQL 任务 | — | 1–2 小时 | 包括抽样校验 |

> **配额评估**：Professional 计划每日约 100k 请求。建议按交易所分批在多天运行（例如 NASDAQ 历史行情分 2 日完成），实时监控请求计数，超限前暂停等待额度恢复。

> **标的范围**：历史补数与日终流程同时拉取股票与 ETF，接口返回的其他类型会保留下来，由监控提示缺失指标或再做人工判断。

### 1.4 执行脚本
- 历史补数脚本：`python -m scripts.backfill --exchange NASDAQ --start 2014-01-01 --end 2024-12-31 --limit 100`
  - 支持 `--symbols` 指定列表、`--sleep` 控制节流、自动解析拆分比例并推导 ETF 股本（缺失时在日志中提示）。
- 批量导入后使用 `scripts.etl_loaders.log_null_metrics` 自动输出空值统计，允许首日 `volume_ratio` 为 1 条 NULL。

## 2. 日终增量流程（日常）

### 2.1 执行顺序

| 步骤 | 时间窗口（纽约时间） | 输入 | 输出/操作 | 验证 | 失败策略 |
| --- | --- | --- | --- | --- | --- |
| D1 批量行情 | 16:45 | `/eod-bulk-last-day/US` | Upsert 至 `stg_eod_quotes` | 检查记录数 ≥ 前一日；若少于 40k 给出告警 | 重试 3 次；仍失败则延迟 15 分钟再跑 |
| D2 基本面刷新 | 17:00 | `/bulk-fundamentals/{EXCHANGE}`（按日轮询） | 更新 `stg_fundamentals`、同步行业信息 | 对比 `UpdatedAt` 是否新于上次；记录更新数 | 请求失败 → 记录错误并保留旧数据，次日重跑 |
| D3 企业行为 | 17:05 | `/div/{SYMBOL}`、`/splits/{SYMBOL}`（最近 7 日） | 新增事件至 `fact_corporate_actions` | 确认当天事件数量；必要时人工核对 | 请求失败 → 重试；若仍失败，下一日 D3 会补抓 |
| D4 指标刷新 | 17:10 | 综合 `stg_*` 数据 | 更新 `mart_daily_quotes` 并调用 `refresh_mart_etf_periodic_returns` | 随机抽样当日 20 条校验涨跌幅、换手等；对比最近一年年度/月度收益 | 若空值异常增长 → 在日志提示并保留旧值 |
| D5 状态记录 | 17:15 | — | 更新 `etl_job_status` (`daily_update`, `ALL`) | 写入执行耗时、成功数、警告数 | 若写入失败需人工检查数据库连接 |

**脚本示例**：`python -m scripts.daily_update --refresh-fundamentals --lookback-days 90`
- 支持 `--limit-symbols` 用于抽样测试、`--skip-dividends` 加速调试。
- 脚本会对未入库的标的自动抓取 Fundamentals，解析拆分比率，并结合监控规则忽略首日 `volume_ratio` 的 NULL。

### 2.2 Cron 与日志

| 任务 | Cron 表达式 | 环境变量 | 日志文件 |
| --- | --- | --- | --- |
| `daily_update.py` | `45 16 * * 1-5 TZ=America/New_York` | `.env`（API、PG） | `/var/log/eodhd/daily_update.log` |
| `weekly_fundamentals.py`（可选） | `0 9 * * 6 TZ=America/New_York` | 同上 | `/var/log/eodhd/weekly_fundamentals.log` |

> 建议在脚本中使用 `logging` 模块输出 INFO/ERROR，并配合 `logrotate` 管理日志文件大小。

## 3. 验证与监控

- **数据完整性**：每日比较 `mart_daily_quotes` 最新日期的记录数与上一日差异，若下降 > 5% 触发告警。
- **字段范围**：设置 SQL 校验（例如 `pct_chg BETWEEN -0.9 AND 0.9`），超出范围记录警告。
- **重试机制**：所有 API 调用封装重试器（指数退避最多 3 次），失败时写入 `etl_job_status` 的 `message` 字段，方便追踪。
- **备份策略**：每日增量前可对 `mart_daily_quotes` 当日数据做临时备份（如 `COPY` 到 CSV），以便回滚。

### 3.1 历史补数监控指标

| 指标 | 说明 | 检查频率 | 正常阈值 | 异常处理 |
| --- | --- | --- | --- | --- |
| `dim_symbol` 新增数 | 每交易所新增 symbol 数量 | 每批同步后 | 与接口返回条数一致 | 差异 → 重拉该交易所列表 |
| `stg_eod_quotes` 日覆盖 | 每 symbol 已写入的日期数 | 每 1 小时 | ≥ 10 年 * 252 | 不足 → 标记补抓范围 |
| 空值比例 | `open/high/low/close/volume` NULL 占比 | 每批 | < 0.5% | 超出 → 记录 symbol，后续复核 |
| 重复记录 | `(symbol, date)` 主键冲突次数 | 按批 | 0 | >0 → 查找重复原因，调整 UPSERT |
| API 请求成功率 | 成功 / 总请求 | 实时 | ≥ 98% | 低于阈值 → 暂停补数，检查网络/配额 |

### 3.2 日终增量监控指标

| 指标 | 说明 | 检查频率 | 正常阈值 | 异常处理 |
| --- | --- | --- | --- | --- |
| 当日记录数 | `mart_daily_quotes` 当日行数 | 日次任务后 | ≥ 前一日 * 0.95 | 不足 → 重跑 D1/D4 |
| `pct_chg` 差异 | 与 API 直接计算对比 | 抽样 | 绝对误差 < 0.0005 | 超出 → 检查计算逻辑 |
| `turnover_rate` 异常 | >5 或 <0 值计数 | 每日 | 0 | 有值 → 检查股本缺失或成交量异常 |
| 日志错误数 | `ERROR` 级别日志条数 | 每日 | 0 | >0 → 人工排查并重试 |
| API 请求量 | 当日累计请求数 | 实时 | < 90% 配额 | 接近阈值 → 暂停非关键任务 |

## 4. 运行前检查清单

1. `.env` 配置正确（API Token、数据库连接、时区设置）。
2. PostgreSQL 服务运行正常，`psql` 可连接。
3. 虚拟环境已安装依赖（`requests`, `pandas`, `sqlalchemy`, `psycopg2-binary`, `python-dotenv`）。
4. 网络可访问 `https://eodhd.com/api/`。
5. `docs/samples/` 已更新至最新接口结构，确保字段不会缺失。

## 5. 运行后检查清单

1. `etl_job_status` 中对应任务状态为 `success` 且时间戳为当日。
2. `mart_daily_quotes` 最新交易日记录条数合理（≥ 40k）。
3. 日志无 ERROR，如有 WARN 需人工评估。
4. 随机抽样比对（可通过 SQL + curl）验证几个 symbol 的涨跌幅、换手率计算正确。

本手册将随开发迭代同步更新，任何流程调整或新增指标需在此文档记录，确保运维与开发一致执行。 
