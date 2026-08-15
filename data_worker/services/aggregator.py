import pandas as pd


def aggregate_ohlcv(
    df: pd.DataFrame,
    timeframe: str,
) -> pd.DataFrame:
    """
    Aggregate canonical daily OHLCV data into
    weekly or monthly candles.

    timeframe:
        W = Weekly
        M = Monthly
    """

    if df is None or df.empty:
        raise ValueError("Cannot aggregate empty OHLCV data")

    if timeframe not in {"W", "M"}:
        raise ValueError(
            "Aggregation timeframe must be 'W' or 'M'"
        )

    required_columns = {
        "symbol",
        "date",
        "open",
        "high",
        "low",
        "close",
        "adj_close",
        "volume",
    }

    missing = required_columns - set(df.columns)

    if missing:
        raise ValueError(
            f"Missing required columns: {sorted(missing)}"
        )

    df = df.copy()

    df["date"] = pd.to_datetime(df["date"])

    df = df.sort_values(
        ["symbol", "date"]
    )

    if timeframe == "W":
        period = df["date"].dt.to_period("W-FRI")
    else:
        period = df["date"].dt.to_period("M")

    df["_period"] = period

    aggregated = (
        df.groupby(
            ["symbol", "_period"],
            sort=True,
        )
        .agg(
            date=("date", "max"),
            open=("open", "first"),
            high=("high", "max"),
            low=("low", "min"),
            close=("close", "last"),
            adj_close=("adj_close", "last"),
            volume=("volume", "sum"),
        )
        .reset_index()
    )

    aggregated["timeframe"] = timeframe

    aggregated["date"] = (
        pd.to_datetime(aggregated["date"]).dt.date
    )

    return aggregated[
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