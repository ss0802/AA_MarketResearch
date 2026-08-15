import yfinance as yf


class YahooFinanceProvider:
    """
    Market-data provider backed by Yahoo Finance.
    """

    def get_daily_ohlcv(self, symbol: str, period: str = "2y"):
        """
        Fetch daily OHLCV data for a symbol.

        Returns the raw yfinance DataFrame.
        Database persistence is deliberately handled elsewhere.
        """
        ticker = yf.Ticker(symbol)

        df = ticker.history(
            period=period,
            interval="1d",
            auto_adjust=False,
        )

        if df is None or df.empty:
            raise ValueError(
                f"No daily market data returned for {symbol}"
            )

        return df