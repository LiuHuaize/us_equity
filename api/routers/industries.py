from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, status

from ..deps import get_db_connection, verify_api_token
from ..schemas import IndustryGroup, IndustrySecurity


router = APIRouter(
    prefix="/industries",
    tags=["industries"],
    dependencies=[Depends(verify_api_token)],
)

_FALLBACK_LABEL = "未分类"


def _normalize_query_value(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or _FALLBACK_LABEL


def _classify_asset_type(asset_type: Optional[str]) -> str:
    if not asset_type:
        return "other"

    normalized = asset_type.strip().lower()
    if not normalized:
        return "other"

    if "etf" in normalized or "exchange traded fund" in normalized:
        return "etf"

    if "stock" in normalized or normalized in {"equity", "adr", "common stock"}:
        return "stock"

    return "other"


@router.get(
    "",
    response_model=List[IndustryGroup],
    summary="按行业/板块聚合的标的清单",
)
async def list_industries(
    sector: Optional[str] = Query(default=None, description="行业大类（sector）"),
    industry: Optional[str] = Query(default=None, description="子行业（industry）"),
    include_etfs: bool = Query(default=True, description="是否包含 ETF 信息"),
    min_stock_count: int = Query(
        default=0,
        ge=0,
        le=10000,
        description="最小个股数量过滤（仅统计股票/ADR/Equity 等）",
    ),
    skip_uncategorized: bool = Query(
        default=True,
        description="是否自动排除 sector/industry 为空的记录",
    ),
    conn: asyncpg.Connection = Depends(get_db_connection),
) -> List[IndustryGroup]:
    conditions = ["is_active IS DISTINCT FROM FALSE"]
    values: List[str] = []
    param_index = 1

    sector_value = _normalize_query_value(sector)
    industry_value = _normalize_query_value(industry)

    if sector_value is not None:
        conditions.append(f"COALESCE(NULLIF(sector, ''), '{_FALLBACK_LABEL}') = ${param_index}")
        values.append(sector_value)
        param_index += 1

    if industry_value is not None:
        conditions.append(f"COALESCE(NULLIF(industry, ''), '{_FALLBACK_LABEL}') = ${param_index}")
        values.append(industry_value)
        param_index += 1

    where_clause = " AND ".join(conditions)

    rows = await conn.fetch(
        f"""
        SELECT
            COALESCE(NULLIF(sector, ''), '{_FALLBACK_LABEL}') AS sector_name,
            COALESCE(NULLIF(industry, ''), '{_FALLBACK_LABEL}') AS industry_name,
            symbol,
            name,
            exchange,
            asset_type
        FROM dim_symbol
        WHERE {where_clause}
        ORDER BY sector_name, industry_name, symbol
        """,
        *values,
    )

    if not rows:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="未找到行业数据")

    group_map: Dict[Tuple[str, str], Dict[str, Any]] = {}

    for row in rows:
        sector_label = row["sector_name"]
        industry_label = row["industry_name"]
        key = (sector_label, industry_label)
        bucket = _classify_asset_type(row["asset_type"])

        if not include_etfs and bucket == "etf":
            continue

        group = group_map.setdefault(
            key,
            {
                "sector": sector_label,
                "industry": industry_label,
                "securities": [],
                "counts": {"total": 0, "etf": 0, "stock": 0, "other": 0},
            },
        )

        security = IndustrySecurity(
            symbol=row["symbol"],
            name=row["name"],
            exchange=row["exchange"],
            asset_type=row["asset_type"],
        )
        group["securities"].append(security)

        counts = group["counts"]
        counts["total"] += 1
        counts[bucket] += 1

    result: List[IndustryGroup] = []
    for (sector_label, industry_label) in sorted(group_map.keys(), key=lambda item: (item[0], item[1])):
        group = group_map[(sector_label, industry_label)]
        counts = group["counts"]

        if skip_uncategorized and industry_value is None and industry_label == _FALLBACK_LABEL:
            continue

        if counts["stock"] < min_stock_count:
            continue
        result.append(
            IndustryGroup(
                sector=sector_label,
                industry=industry_label,
                total_symbols=counts["total"],
                etf_count=counts["etf"],
                stock_count=counts["stock"],
                other_count=counts["other"],
                securities=group["securities"],
            )
        )

    return result
