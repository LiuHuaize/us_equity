-- Aggregated ETF periodic return metrics (monthly & yearly)
-- Maintains last 10 years of data for use by API and dashboards.

CREATE TABLE IF NOT EXISTS mart_etf_periodic_returns (
    symbol                  VARCHAR(20)    NOT NULL,
    period_type             TEXT           NOT NULL CHECK (period_type IN ('month', 'year')),
    period_key              VARCHAR(10)    NOT NULL,
    period_start            DATE           NOT NULL,
    period_end              DATE           NOT NULL,
    trading_days            INTEGER        NOT NULL,
    total_return_pct        NUMERIC(18,8)  NOT NULL,
    compound_return_pct     NUMERIC(18,8)  NOT NULL,
    volatility_pct          NUMERIC(18,8),
    max_drawdown_pct        NUMERIC(18,8),
    created_at              TIMESTAMPTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at              TIMESTAMPTZ    NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (symbol, period_type, period_key)
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_mart_etf_periodic_returns_pk
    ON mart_etf_periodic_returns (symbol, period_type, period_key);

CREATE INDEX IF NOT EXISTS idx_mart_etf_periodic_returns_period
    ON mart_etf_periodic_returns (period_type, period_key);

CREATE INDEX IF NOT EXISTS idx_mart_etf_periodic_returns_symbol_period_start
    ON mart_etf_periodic_returns (symbol, period_type, period_start);


CREATE OR REPLACE FUNCTION refresh_mart_etf_periodic_returns(
    p_symbols TEXT[] DEFAULT NULL,
    p_start   DATE   DEFAULT NULL,
    p_end     DATE   DEFAULT NULL
) RETURNS VOID
LANGUAGE plpgsql
AS $$
DECLARE
    v_symbols TEXT[];
    v_start   DATE := COALESCE(p_start, (date_trunc('year', CURRENT_DATE) - INTERVAL '10 years')::DATE);
    v_end     DATE := COALESCE(p_end, CURRENT_DATE);
BEGIN
    IF v_end < v_start THEN
        RAISE EXCEPTION 'refresh_mart_etf_periodic_returns: end date % precedes start date %', v_end, v_start;
    END IF;

    IF p_symbols IS NULL OR array_length(p_symbols, 1) IS NULL THEN
        v_symbols := NULL;
    ELSE
        v_symbols := p_symbols;
    END IF;

    IF v_symbols IS NULL AND p_start IS NULL THEN
        DELETE FROM mart_etf_periodic_returns
        WHERE period_start < v_start;
    END IF;

    WITH base AS (
        SELECT
            mdq.symbol,
            mdq.trade_date,
            mdq.adjusted_close,
            mdq.pct_chg,
            DATE_TRUNC('month', mdq.trade_date)::DATE AS month_start,
            DATE_TRUNC('year', mdq.trade_date)::DATE  AS year_start
        FROM mart_daily_quotes mdq
        JOIN dim_symbol ds
          ON ds.symbol = mdq.symbol
        WHERE ds.asset_type = 'ETF'
          AND mdq.trade_date BETWEEN v_start AND v_end
          AND (v_symbols IS NULL OR mdq.symbol = ANY (v_symbols))
    ),
    periods AS (
        SELECT
            symbol,
            'month'::TEXT AS period_type,
            month_start   AS period_start,
            (month_start + INTERVAL '1 month - 1 day')::DATE AS period_end,
            trade_date,
            adjusted_close,
            pct_chg
        FROM base
        UNION ALL
        SELECT
            symbol,
            'year'::TEXT AS period_type,
            year_start    AS period_start,
            (year_start + INTERVAL '1 year - 1 day')::DATE AS period_end,
            trade_date,
            adjusted_close,
            pct_chg
        FROM base
    ),
    enriched AS (
        SELECT
            symbol,
            period_type,
            period_start,
            period_end,
            trade_date,
            adjusted_close,
            pct_chg,
            first_close,
            last_close,
            running_max,
            seq_in_period,
            CASE
                WHEN prev_adjusted_close IS NULL OR prev_adjusted_close <= 0
                     OR adjusted_close IS NULL OR adjusted_close <= 0 THEN NULL
                ELSE LN(adjusted_close / prev_adjusted_close)
            END AS log_return
        FROM (
            SELECT
                symbol,
                period_type,
                period_start,
                period_end,
                trade_date,
                adjusted_close,
                pct_chg,
                FIRST_VALUE(adjusted_close) OVER (
                    PARTITION BY symbol, period_type, period_start
                    ORDER BY trade_date
                ) AS first_close,
                LAST_VALUE(adjusted_close) OVER (
                    PARTITION BY symbol, period_type, period_start
                    ORDER BY trade_date
                    ROWS BETWEEN UNBOUNDED PRECEDING AND UNBOUNDED FOLLOWING
                ) AS last_close,
                MAX(adjusted_close) OVER (
                    PARTITION BY symbol, period_type, period_start
                    ORDER BY trade_date
                    ROWS BETWEEN UNBOUNDED PRECEDING AND CURRENT ROW
                ) AS running_max,
                LAG(adjusted_close) OVER (
                    PARTITION BY symbol, period_type
                    ORDER BY trade_date
                ) AS prev_adjusted_close,
                ROW_NUMBER() OVER (
                    PARTITION BY symbol, period_type, period_start
                    ORDER BY trade_date
                ) AS seq_in_period
            FROM periods
        ) enriched_base
    ),
    aggregated AS (
        SELECT
            symbol,
            period_type,
            CASE
                WHEN period_type = 'month' THEN TO_CHAR(period_start, 'YYYY-MM')
                ELSE TO_CHAR(period_start, 'YYYY')
            END AS period_key,
            period_start,
            period_end,
            COUNT(*)::INTEGER AS trading_days,
            (MAX(last_close) / NULLIF(MIN(first_close), 0) - 1)::NUMERIC(18,8) AS total_return_pct,
            (
                EXP(
                    COALESCE(
                        SUM(
                            CASE
                                WHEN seq_in_period > 1 THEN log_return
                                ELSE NULL
                            END
                        ),
                        0
                    )
                ) - 1
            )::NUMERIC(18,8) AS compound_return_pct,
            (
                CASE
                    WHEN COUNT(pct_chg) FILTER (WHERE pct_chg IS NOT NULL) > 1 THEN
                        STDDEV_SAMP(pct_chg) * SQRT(252.0)
                    ELSE NULL
                END
            )::NUMERIC(18,8) AS volatility_pct,
            MIN(
                CASE
                    WHEN running_max IS NULL OR running_max = 0 THEN NULL
                    ELSE adjusted_close / running_max - 1
                END
            )::NUMERIC(18,8) AS max_drawdown_pct
        FROM enriched
        GROUP BY symbol, period_type, period_start, period_end
        HAVING MIN(first_close) IS NOT NULL AND MAX(last_close) IS NOT NULL
    )
    INSERT INTO mart_etf_periodic_returns (
        symbol,
        period_type,
        period_key,
        period_start,
        period_end,
        trading_days,
        total_return_pct,
        compound_return_pct,
        volatility_pct,
        max_drawdown_pct,
        created_at,
        updated_at
    )
    SELECT
        symbol,
        period_type,
        period_key,
        period_start,
        period_end,
        trading_days,
        COALESCE(total_return_pct, compound_return_pct, 0)::NUMERIC(18,8) AS total_return_pct,
        compound_return_pct,
        volatility_pct,
        max_drawdown_pct,
        CURRENT_TIMESTAMP,
        CURRENT_TIMESTAMP
    FROM aggregated
    WHERE trading_days > 0
    ON CONFLICT (symbol, period_type, period_key)
    DO UPDATE SET
        period_start        = EXCLUDED.period_start,
        period_end          = EXCLUDED.period_end,
        trading_days        = EXCLUDED.trading_days,
        total_return_pct    = EXCLUDED.total_return_pct,
        compound_return_pct = EXCLUDED.compound_return_pct,
        volatility_pct      = EXCLUDED.volatility_pct,
        max_drawdown_pct    = EXCLUDED.max_drawdown_pct,
        updated_at          = CURRENT_TIMESTAMP;
END;
$$;

COMMENT ON FUNCTION refresh_mart_etf_periodic_returns(TEXT[], DATE, DATE)
    IS 'Recompute ETF monthly and yearly return aggregates, defaulting to the last 10 years.';
