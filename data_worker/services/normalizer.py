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

    normalized["symbol"] = symbol.upper()
    normalized["timeframe"] = timeframe

    if "Adj Close" in df.columns:
        normalized["adj_close"] = df["Adj Close"]
    else:
        normalized["adj_close"] = df["Close"]

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