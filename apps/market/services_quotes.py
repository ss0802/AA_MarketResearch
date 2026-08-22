from decimal import Decimal

import pandas as pd
import yfinance as yf
from django.utils import timezone

from .management.commands.ingest_tradeable import yahoo_symbol


def fetch_yahoo_intraday_quotes(instruments):
    """Return the latest available delayed one-minute quote for each Symbol id."""
    instruments = list(instruments)
    if not instruments:
        return {}
    provider_codes = {instrument.id: yahoo_symbol(instrument) for instrument in instruments}
    frame = yf.download(
        tickers=list(provider_codes.values()), period="1d", interval="1m", group_by="ticker",
        auto_adjust=False, prepost=False, progress=False, threads=True, timeout=10,
    )
    quotes = {}
    for instrument in instruments:
        code = provider_codes[instrument.id]
        try:
            if isinstance(frame.columns, pd.MultiIndex):
                ticker_frame = frame[code] if code in frame.columns.get_level_values(0) else frame.xs(code, axis=1, level=1)
            else:
                ticker_frame = frame
            prices = ticker_frame["Close"].dropna()
            if prices.empty:
                continue
            quote_time = prices.index[-1]
            if hasattr(quote_time, "to_pydatetime"):
                quote_time = quote_time.to_pydatetime()
            if timezone.is_naive(quote_time):
                quote_time = timezone.make_aware(quote_time, timezone.get_current_timezone())
            quotes[instrument.id] = {"price": Decimal(str(prices.iloc[-1])), "quote_time": quote_time}
        except (KeyError, TypeError, ValueError):
            continue
    return quotes
