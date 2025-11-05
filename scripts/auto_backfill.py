"""自适应批量回填脚本。

该脚本在 `scripts.backfill` 的能力之上，增加了：

1. Exchange 级别的自动分批与断点续跑；
2. 每只标的失败不会中断整个任务，错误信息写入进度文件；
3. 可选的失败重试与限速控制；
4. 进度文件默认位于 `state/backfill_progress.json`，可根据需要调整。

使用示例：

```bash
python -m scripts.auto_backfill \
    --exchange NYSE --exchange NASDAQ --exchange AMEX \
    --start 2015-11-03 --end 2025-11-03 \
    --sleep 0.2 --retry-failed
```

脚本会自动记录已完成的 symbol，下次运行会从断点继续。如需重新全量跑，可以删除进度文件或使用
`--reset-progress` 参数。
"""

from __future__ import annotations

import argparse
import json
import logging
import signal
import sys
import time
from pathlib import Path
from typing import Dict, List, Optional

from typing import cast

from requests import HTTPError
from tenacity import RetryError

from .api_client import EODHDClient
from .backfill import fetch_exchange_symbols, process_symbol


LOGGER = logging.getLogger("auto_backfill")


def setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        stream=sys.stdout,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="自动断点续跑的 EODHD 回填脚本")
    parser.add_argument(
        "--exchange",
        action="append",
        required=True,
        help="需要处理的交易所，可多次指定（例如 NYSE、NASDAQ、AMEX）",
    )
    parser.add_argument("--start", default="2015-11-03", help="起始日期 (YYYY-MM-DD)")
    parser.add_argument("--end", default="2025-11-03", help="结束日期 (YYYY-MM-DD)")
    parser.add_argument("--sleep", type=float, default=0.2, help="每只标的之间的休眠秒数")
    parser.add_argument(
        "--resume-file",
        default="state/backfill_progress.json",
        help="进度文件路径，默认写入 state/backfill_progress.json",
    )
    parser.add_argument(
        "--limit",
        type=int,
        help="调试用：限制每个交易所处理的前 N 只标的",
    )
    parser.add_argument(
        "--retry-failed",
        action="store_true",
        help="优先重试进度文件中标记失败的 symbol",
    )
    parser.add_argument(
        "--max-errors",
        type=int,
        default=100,
        help="累计失败超过该阈值后中止，默认 100",
    )
    parser.add_argument(
        "--reset-progress",
        action="store_true",
        help="忽略既有进度文件，从头开始跑",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="输出 debug 日志",
    )
    return parser.parse_args()


def load_progress(path: Path, reset: bool) -> Dict[str, Dict[str, object]]:
    if reset or not path.exists():
        return {}
    try:
        with path.open("r", encoding="utf-8") as fh:
            return json.load(fh)
    except json.JSONDecodeError:
        LOGGER.warning("进度文件 %s 无法解析，将忽略并重新创建", path)
        return {}


def save_progress(path: Path, data: Dict[str, Dict[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(".tmp")
    with tmp_path.open("w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    tmp_path.replace(path)


def truncate_error(exc: Exception, limit: int = 200) -> str:
    text = f"{exc.__class__.__name__}: {exc}"
    return text if len(text) <= limit else text[: limit - 3] + "..."


def process_queue(
    client: EODHDClient,
    symbols: List[str],
    start_idx: int,
    start_date: str,
    end_date: str,
    sleep_seconds: float,
    failed_map: Dict[str, Dict[str, object]],
    progress_entry: Dict[str, object],
    resume_path: Path,
    progress_store: Dict[str, Dict[str, object]],
    max_errors: int,
) -> None:
    error_count = progress_entry.get("error_count", 0)
    total = len(symbols)

    for idx in range(start_idx, total):
        symbol = symbols[idx]
        LOGGER.info(
            "[%s] %s/%s -> %s",
            progress_entry["exchange"],
            idx + 1,
            total,
            symbol,
        )
        try:
            process_symbol(client, symbol, start_date, end_date)
        except (HTTPError, RetryError) as exc:  # 已经重试仍失败
            error_count += 1
            failed_entry = failed_map.setdefault(symbol, {"attempts": 0})
            failed_entry["attempts"] = failed_entry.get("attempts", 0) + 1
            failed_entry["error"] = truncate_error(exc)
            LOGGER.error("符号 %s 失败 (累计错误 %s)：%s", symbol, error_count, failed_entry["error"])
        except Exception as exc:  # 处理时数据库/计算异常
            error_count += 1
            failed_entry = failed_map.setdefault(symbol, {"attempts": 0})
            failed_entry["attempts"] = failed_entry.get("attempts", 0) + 1
            failed_entry["error"] = truncate_error(exc)
            LOGGER.exception("符号 %s 遇到未预期异常，已跳过", symbol)
        else:
            if symbol in failed_map:
                failed_map.pop(symbol, None)
        finally:
            progress_entry["next_index"] = idx + 1
            progress_entry["error_count"] = error_count
            save_progress(resume_path, progress_store)
            time.sleep(sleep_seconds)

        if max_errors and error_count >= max_errors:
            raise RuntimeError(
                f"累计错误超过阈值 {max_errors}，建议检查日志后重跑或调整参数"
            )


def retry_failed_symbols(
    client: EODHDClient,
    symbols: List[str],
    start_date: str,
    end_date: str,
    sleep_seconds: float,
    failed_map: Dict[str, Dict[str, object]],
    progress_entry: Dict[str, object],
    resume_path: Path,
    progress_store: Dict[str, Dict[str, object]],
    max_errors: int,
) -> None:
    if not failed_map:
        return
    LOGGER.info(
        "[%s] 开始重试 %d 个历史失败 symbol",
        progress_entry["exchange"],
        len(failed_map),
    )
    retry_symbols = list(failed_map.keys())
    error_count = progress_entry.get("error_count", 0)

    for symbol in retry_symbols:
        LOGGER.info("重试 %s", symbol)
        try:
            process_symbol(client, symbol, start_date, end_date)
        except (HTTPError, RetryError) as exc:
            error_count += 1
            entry = failed_map.setdefault(symbol, {"attempts": 0})
            entry["attempts"] = entry.get("attempts", 0) + 1
            entry["error"] = truncate_error(exc)
            LOGGER.error("重试失败 %s (累计错误 %s)：%s", symbol, error_count, entry["error"])
        except Exception as exc:
            error_count += 1
            entry = failed_map.setdefault(symbol, {"attempts": 0})
            entry["attempts"] = entry.get("attempts", 0) + 1
            entry["error"] = truncate_error(exc)
            LOGGER.exception("重试过程中出现未预期异常：%s", symbol)
        else:
            failed_map.pop(symbol, None)
        finally:
            progress_entry["error_count"] = error_count
            save_progress(resume_path, progress_store)
            time.sleep(sleep_seconds)

        if max_errors and error_count >= max_errors:
            raise RuntimeError(
                f"累计错误超过阈值 {max_errors}，建议检查日志后重跑或调整参数"
            )


def main() -> None:
    args = parse_args()
    setup_logging(args.verbose)

    resume_path = Path(args.resume_file)
    progress_store: Dict[str, Dict[str, object]] = load_progress(resume_path, args.reset_progress)

    client = EODHDClient()
    stop_requested = False

    def handle_sigterm(signum, frame):  # type: ignore[arg-type]
        nonlocal stop_requested
        LOGGER.warning("收到信号 %s，完成当前 symbol 后安全退出", signum)
        stop_requested = True

    signal.signal(signal.SIGTERM, handle_sigterm)
    signal.signal(signal.SIGINT, handle_sigterm)

    for exchange in args.exchange:
        LOGGER.info("======== 处理交易所 %s ========", exchange)
        symbols = fetch_exchange_symbols(client, exchange)
        if args.limit:
            symbols = symbols[: args.limit]

        entry = progress_store.setdefault(
            exchange,
            {
                "exchange": exchange,
                "next_index": 0,
                "failed": {},
                "start": args.start,
                "end": args.end,
                "error_count": 0,
            },
        )

        failed_map = cast(Dict[str, Dict[str, object]], entry.setdefault("failed", {}))

        if args.retry_failed:
            retry_failed_symbols(
                client,
                symbols,
                args.start,
                args.end,
                args.sleep,
                failed_map,
                entry,
                resume_path,
                progress_store,
                args.max_errors,
            )

        if entry.get("next_index", 0) >= len(symbols):
            LOGGER.info("[%s] 已完成所有 symbol", exchange)
            continue

        try:
            process_queue(
                client,
                symbols,
                entry.get("next_index", 0),
                args.start,
                args.end,
                args.sleep,
                failed_map,
                entry,
                resume_path,
                progress_store,
                args.max_errors,
            )
        except RuntimeError as exc:
            LOGGER.error("[%s] 中断：%s", exchange, exc)
            break

        if stop_requested:
            LOGGER.warning("收到停止信号，提前结束循环")
            break

    LOGGER.info("任务完成，可查看 %s 获取详细进度", resume_path)


if __name__ == "__main__":
    main()
