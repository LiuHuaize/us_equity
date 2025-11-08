from datetime import date
from decimal import Decimal

import pytest

from scripts.etf_backtest import (
    PortfolioDefinition,
    PortfolioSeries,
    build_portfolio_series,
    compute_summary,
)


def test_build_portfolio_series_equal_weight() -> None:
    start = date(2020, 11, 3)
    end = date(2020, 11, 5)
    price_map = {
        "AAA.US": {
            date(2020, 11, 3): Decimal("100"),
            date(2020, 11, 4): Decimal("110"),
            date(2020, 11, 5): Decimal("121"),
        },
        "BBB.US": {
            date(2020, 11, 3): Decimal("200"),
            date(2020, 11, 4): Decimal("190"),
            date(2020, 11, 5): Decimal("209"),
        },
    }

    series = build_portfolio_series(("AAA.US", "BBB.US"), price_map, start, end)

    nav_values = [float(nav) for _, nav in series.nav_points]
    assert nav_values == pytest.approx([1.0, 1.025, 1.1275], rel=1e-6)
    assert series.max_drawdown == Decimal("0")
    assert len(series.daily_returns) == 3
    assert series.daily_returns[0] is None


def test_compute_summary_metrics() -> None:
    definition = PortfolioDefinition(key="test", label="测试组合", symbols=("AAA.US",))
    nav_points = [
        (date(2020, 1, 1), Decimal("1.0")),
        (date(2020, 1, 2), Decimal("1.1")),
        (date(2020, 1, 3), Decimal("1.0")),
    ]
    daily_returns = [None, Decimal("0.10"), Decimal("-0.090909")]
    drawdown_value = Decimal("-0.090909")
    series = PortfolioSeries(
        nav_points=nav_points,
        daily_returns=daily_returns,
        drawdowns=[Decimal("0"), Decimal("0"), drawdown_value],
        max_drawdown=drawdown_value,
        max_drawdown_start=date(2020, 1, 2),
        max_drawdown_end=date(2020, 1, 3),
    )

    summary = compute_summary(definition, series, risk_free_rate=0.0)

    assert summary.trading_days == 3
    assert summary.cumulative_return == pytest.approx(0.0, abs=1e-9)
    assert summary.annualized_return == pytest.approx(0.0, abs=1e-9)
    assert summary.annualized_volatility > 0
    assert summary.max_drawdown == pytest.approx(float(drawdown_value), rel=1e-6)
    assert summary.sharpe_ratio == pytest.approx(0.0, abs=1e-9)
    assert summary.calmar_ratio == pytest.approx(0.0, abs=1e-9)
