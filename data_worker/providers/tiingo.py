import os

import pandas as pd
import requests


class TiingoEODProvider:
    """End-of-day OHLCV provider backed by Tiingo."""

    base_url = "https://api.tiingo.com/tiingo/daily"

    def __init__(self, api_key: str | None = None):
        self.api_key = api_key or os.getenv("TIINGO_API_KEY")
        if not self.api_key:
            raise ValueError("TIINGO_API_KEY is not configured")

    def get_daily_ohlcv(self, symbol: str, start_date=None, end_date=None):
        params = {"token": self.api_key}
        if start_date:
            params["startDate"] = str(start_date)
        if end_date:
            params["endDate"] = str(end_date)

        response = requests.get(
            f"{self.base_url}/{symbol}/prices",
            params=params,
            timeout=30,
        )
        response.raise_for_status()
        records = response.json()
        if not records:
            raise ValueError(f"No daily market data returned for {symbol}")

        frame = pd.DataFrame.from_records(records).rename(
            columns={
                "date": "Date",
                "open": "Open",
                "high": "High",
                "low": "Low",
                "close": "Close",
                "adjClose": "Adj Close",
                "volume": "Volume",
            }
        )
        frame["Date"] = pd.to_datetime(frame["Date"])
        return frame.set_index("Date")
