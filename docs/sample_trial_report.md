# 样例小规模试跑记录（2024-01-01 ~ 2024-01-10）

## 1. 试跑对象
- 股票：`AAPL.US`, `MSFT.US`, `SIRI.US`
- ETF：`SPY.US`, `ARKK.US`
- 时间范围：2024-01-01 至 2024-01-10（7 个交易日）
- 接口调用内容：`/fundamentals`, `/eod`, `/div`, `/splits`

## 2. 数据落库情况
- `dim_symbol`: 成功写入 5 条，ETF 无行业/板块字段（源数据为空）。
- `stg_fundamentals`: 每个标的插入 1 条最新快照，ETF (`SPY.US`, `ARKK.US`) 缺失 `SharesOutstanding`/`SharesFloat`；`SIRI.US` 缺失 `PERatio`。
- `stg_eod_quotes`: 每个标的写入 7 行日行情，字段与接口完全对齐。
- `fact_corporate_actions`: 分红数据成功记录（如 `AAPL.US` 在 2024-02-09 有 0.24 美元现金股息）；拆分接口返回的 `ratio` 为字符串（`"4:1"`），试跑时写入 numeric 列导致值为 NULL，随后已在 ETL 中解析为浮点（见第 4 节）。
- `mart_daily_quotes`: 共生成 35 条指标记录。首日 `pre_close`/`pct_chg`/`volume_ratio` 按预期为空，后续日期计算正确。

## 3. 指标验证
| Symbol | Rows | `pct_chg` 检查 | `turnover_rate` | 备注 |
| --- | --- | --- | --- | --- |
| `AAPL.US` | 7 | 与 API 直接计算一致（最大误差 < 1e-6） | 正常（约 0.3%–0.6%） | `volume_ratio` 首日缺值 |
| `MSFT.US` | 7 | 正常 | 正常（0.28%–0.34%） | 同上 |
| `SIRI.US` | 7 | 正常 | 正常（约 1%） | `pe` 缺失（无 `PERatio`） |
| `SPY.US` | 7 | 正常 | NULL（缺股本） | 需回填 ETF 股数或外部数据源 |
| `ARKK.US` | 7 | 正常 | NULL（缺股本） | 同上 |

抽样比对：以 `AAPL.US` 2024-01-03 为例，`close=184.25`，`pre_close=185.64` → `pct_chg=-0.75%`，与接口计算一致。

## 4. 发现的问题与处理建议
1. **拆分比例字段**：`/splits` 返回 `ratio` 或 `split` 字段（如 `"4.000000/1.000000"`），现已在 ETL 中解析为数值写入 `fact_corporate_actions.value`，方便后续复权与校验。
2. **ETF 股本缺失**：通过解析 `outstandingShares.annual/quarterly` 推导最新股本；若仍缺失，则在监控中提示并保持换手率、市值为空，待补充外部数据。
3. **空值监控**：`mart_daily_quotes` 首日 `volume_ratio` 为 NULL（无历史窗口），应在监控指标中排除首日或设置阈值。
4. **单位确认**：`SharesOutstanding` 为原始股数，若数据库字段使用“万股”需后续转换；试跑时保持原值（正数级别 10^9）。

## 5. 结论
样例试跑验证了 staging→mart 转换链路可用，主要剩余任务集中在 ETF 股本缺口与监控阈值调整；拆分比率解析已修复，可在此基础上编写历史补数脚本，并加入上述空值/异常监控。
