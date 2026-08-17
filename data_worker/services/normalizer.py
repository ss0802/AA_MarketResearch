import pandas as pd


REQUIRED_COLUMNS = {
    "Open",
    "High",
    "Low",
    "Close",
    "Volume",
}


def normalize_ohlcv(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str = "D",
) -> pd.DataFrame:
    """
    Convert a market-data DataFrame into the canonical
    AA_MarketResearch OHLCV format.

    Output columns:
        symbol
        timeframe
        date
        open
        high
        low
        close
        adj_close
        volume
    """

    if df is None or df.empty:
        raise ValueError(
            f"Cannot normalize empty data for {symbol}"
        )

    df = df.copy()

    # --------------------------------------------------
    # Handle yfinance MultiIndex columns
    # --------------------------------------------------

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # --------------------------------------------------
    # Validate required source columns
    # --------------------------------------------------

    missing = REQUIRED_COLUMNS - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required OHLCV columns: "
            f"{sorted(missing)}"
        )

    # --------------------------------------------------
    # Convert index into date column
    # --------------------------------------------------

    df = df.reset_index()

    date_column = None

    for candidate in ("Date", "Datetime"):
        if candidate in df.columns:
            date_column = candidate
            break

    if date_column is None:
        raise ValueError(
            "Could not find Date or Datetime column"
        )

    # --------------------------------------------------
    # Build canonical DataFrame
    # --------------------------------------------------

    normalized = pd.DataFrame(
        {
            "date": pd.to_datetime(
                df[date_column]
            ).dt.date,
            "open": df["Open"],
            "high": df["High"],
            "low": df["Low"],
            "close": df["Close"],
            "volume": df["Volume"],
        }
    )

    # Thinly traded auction candles occasionally arrive with High/Low values
    # that do not enclose Open and Close. Preserve Open/Close and repair only
    # the canonical candle envelope.
    normalized["high"] = normalized[["open", "high", "close"]].max(axis=1)
    normalized["low"] = normalized[["open", "low", "close"]].min(axis=1)

    if "Adj Close" in df.columns:
        normalized["adj_close"] = df["Adj Close"]
    else:
        normalized["adj_close"] = normalized["close"]

    invalid_adjusted = normalized["adj_close"].isna() | (normalized["adj_close"] <= 0)
    normalized.loc[invalid_adjusted, "adj_close"] = normalized.loc[
        invalid_adjusted, "close"
    ]

    # Yahoo can include empty, zero-volume placeholder sessions. They are not
    # candles and should not prevent the surrounding valid history importing.
    normalized = normalized.dropna(
        subset=["open", "high", "low", "close", "adj_close", "volume"]
    ).reset_index(drop=True)

    normalized["symbol"] = symbol.upper()
    normalized["timeframe"] = timeframe

    # --------------------------------------------------
    # Final column order
    # --------------------------------------------------

    normalized = normalized[
        [
            "symbol",
            "timeframe",
            "date",
            "open",
            "high",
            "low",
            "close",
            "adj_close",
            "volume",
        ]
    ]

    return normalized
