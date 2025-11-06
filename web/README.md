# ETF 排行前端应用

该目录包含基于 React + TypeScript + Vite 构建的单页应用，用于展示美股 ETF 排行榜及单只 ETF 的收益详情。数据来源为仓库同机部署的 FastAPI 服务（`api.main:app`）。

## 运行前提

1. 安装依赖：

   ```bash
   npm install
   ```

2. 配置环境变量，可在根目录下创建 `web/.env.local`：

   ```bash
   VITE_API_BASE_URL=http://127.0.0.1:8080
   # 若 FastAPI 启用了 Token 校验，则同步配置：
   VITE_API_TOKEN=your-token
   # 以下参数可按需覆盖默认值（分别对应年度/月份条数与统计窗口年数）
   # VITE_ETF_YEAR_LIMIT=10
   # VITE_ETF_MONTH_LIMIT=120
   # VITE_ETF_STATS_YEARS=10
   ```

3. FastAPI 服务已经在本机通过 `uvicorn api.main:app --host 127.0.0.1 --port 8080` 运行，并完成 `SELECT refresh_mart_etf_periodic_returns(NULL, NULL, NULL);` 的数据预热。

## 开发与构建

- 开发模式：

  ```bash
  npm run dev
  ```

- 生产构建：

  ```bash
  npm run build
  npm run preview   # 本地预览构建结果
  ```

## 功能说明

- 顶部导航提供 5 年榜单、10 年榜单以及双榜重合列表，数据仍来自 `public/data/*.csv`（由 ETL 脚本导出）。
- 点击榜单中的任意 ETF 行，会跳转至 `/etf/:symbol` 详情页：
  - 通过 `/api/etfs/{symbol}/returns?period=year` 获取年度收益；
  - 首次切换到“月度收益”标签时，再请求 `/api/etfs/{symbol}/returns?period=month`；
  - 统计卡片通过 `/api/etfs/{symbol}/stats?windowYears=10` 获取，汇总总收益、平均年化、最大回撤与波动率。
- 所有 API 请求自动携带 `X-API-Token`（如配置），失败时在页面提示错误信息。

如需进一步扩展图表或缓存策略，可参考 `src/utils/api.ts` 中的封装。欢迎在更新数据或部署前执行 `npm run build`，确保类型检查与产物无误。 
