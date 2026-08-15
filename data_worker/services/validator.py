import pandas as pd


REQUIRED_COLUMNS = [
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


def validate_ohlcv(df: pd.DataFrame) -> pd.DataFrame:
    """
    Validate a canonical AA_MarketResearch OHLCV DataFrame.

    Returns the DataFrame unchanged when valid.
    Raises ValueError when invalid data is found.
    """

    if df is None or df.empty:
        raise ValueError("OHLCV data is empty")

    # Required columns
    missing = set(REQUIRED_COLUMNS) - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    # Null values
    if df[REQUIRED_COLUMNS].isna().any().any():
        raise ValueError("OHLCV data contains null values")

    # OHLC candle integrity
    invalid_high = (
        (df["high"] < df["open"])
        | (df["high"] < df["close"])
        | (df["high"] < df["low"])
    )

    if invalid_high.any():
        raise ValueError("Invalid OHLC data: high is inconsistent")

    invalid_low = (
        (df["low"] > df["open"])
        | (df["low"] > df["close"])
        | (df["low"] > df["high"])
    )

    if invalid_low.any():
        raise ValueError("Invalid OHLC data: low is inconsistent")

    # Prices should be positive
    price_columns = [
        "open",
        "high",
        "low",
        "close",
        "adj_close",
    ]

    if (df[price_columns] <= 0).any().any():
        raise ValueError("OHLCV contains non-positive prices")

    # Volume cannot be negative
    if (df["volume"] < 0).any():
        raise ValueError("OHLCV contains negative volume")

    # Duplicate candles
    duplicates = df.duplicated(
        subset=["symbol", "timeframe", "date"]
    )

    if duplicates.any():
        raise ValueError(
            "Duplicate symbol/timeframe/date candles found"
        )

    # Allowed timeframes
    allowed_timeframes = {"D", "W", "M"}

    invalid_timeframes = ~df["timeframe"].isin(
        allowed_timeframes
    )

    if invalid_timeframes.any():
        raise ValueError("Invalid timeframe found")

    return df