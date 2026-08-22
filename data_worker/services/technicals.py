from decimal import Decimal, ROUND_HALF_UP

import numpy as np
import pandas as pd


CALCULATION_VERSION = "v1"


def _rma(series: pd.Series, length: int) -> pd.Series:
    """TradingView/Wilder moving average seeded with an initial SMA."""
    values = pd.to_numeric(series, errors="coerce").astype(float)
    result = pd.Series(np.nan, index=values.index, dtype=float)
    valid = values.dropna()
    if len(valid) < length:
        return result
    seed_position = valid.index[length - 1]
    result.loc[seed_position] = valid.iloc[:length].mean()
    alpha = 1.0 / length
    started = False
    previous = np.nan
    for index, value in values.items():
        if index == seed_position:
            previous = result.loc[index]
            started = True
        elif started and not np.isnan(value):
            previous = alpha * value + (1 - alpha) * previous
            result.loc[index] = previous
    return result


def _decimal(value, places="0.000001"):
    if value is None or pd.isna(value) or np.isinf(value):
        return None
    return Decimal(str(float(value))).quantize(Decimal(places), rounding=ROUND_HALF_UP)


def _status(value, positive, negative):
    if value is None or pd.isna(value):
        return ""
    return positive if value else negative


def calculate_technical_snapshot(frame: pd.DataFrame) -> dict:
    """Calculate one latest technical snapshot from canonical OHLCV bars."""
    if frame is None or frame.empty:
        raise ValueError("Cannot calculate technicals from empty OHLCV data")
    required = {"date", "open", "high", "low", "close", "volume"}
    missing = required - set(frame.columns)
    if missing:
        raise ValueError(f"Missing OHLCV columns: {sorted(missing)}")

    data = frame.copy().sort_values("date").reset_index(drop=True)
    for column in ("open", "high", "low", "close", "volume"):
        data[column] = pd.to_numeric(data[column], errors="coerce")
    if data[list(required - {"date"})].isna().any().any():
        raise ValueError("OHLCV contains non-numeric values")

    close, high, low = data["close"], data["high"], data["low"]
    previous_close = close.shift(1)
    true_range = pd.concat(
        [high - low, (high - previous_close).abs(), (low - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    atr14 = _rma(true_range, 14)

    delta = close.diff()
    average_gain = _rma(delta.clip(lower=0), 14)
    average_loss = _rma((-delta.clip(upper=0)), 14)
    rs = average_gain / average_loss.replace(0, np.nan)
    rsi14 = 100 - (100 / (1 + rs))
    rsi14 = rsi14.where(average_loss != 0, 100)

    up_move = high.diff()
    down_move = -low.diff()
    plus_dm = pd.Series(
        np.where((up_move > down_move) & (up_move > 0), up_move, 0.0),
        index=data.index,
    )
    minus_dm = pd.Series(
        np.where((down_move > up_move) & (down_move > 0), down_move, 0.0),
        index=data.index,
    )
    plus_di = 100 * _rma(plus_dm, 14) / atr14
    minus_di = 100 * _rma(minus_dm, 14) / atr14
    denominator = (plus_di + minus_di).replace(0, np.nan)
    dx = 100 * (plus_di - minus_di).abs() / denominator
    adx14 = _rma(dx, 14)

    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    macd_signal = macd.ewm(span=9, adjust=False).mean()

    bb_middle = close.rolling(20).mean()
    bb_deviation = close.rolling(20).std(ddof=0)
    bb_upper = bb_middle + 2 * bb_deviation
    bb_lower = bb_middle - 2 * bb_deviation

    kc_middle = close.ewm(span=20, adjust=False).mean()
    kc_upper = kc_middle + 2 * atr14
    kc_lower = kc_middle - 2 * atr14

    latest = data.index[-1]
    price = close.loc[latest]
    vwap = (high.loc[latest] + low.loc[latest] + price) / 3
    bb_width = bb_upper.loc[latest] - bb_lower.loc[latest]
    kc_width = kc_upper.loc[latest] - kc_lower.loc[latest]
    squeeze = bool(
        bb_upper.loc[latest] < kc_upper.loc[latest]
        and bb_lower.loc[latest] > kc_lower.loc[latest]
    ) if not any(pd.isna(value) for value in (
        bb_upper.loc[latest], bb_lower.loc[latest], kc_upper.loc[latest], kc_lower.loc[latest]
    )) else None

    rsi_value = rsi14.loc[latest]
    if pd.isna(rsi_value):
        rsi_status = ""
    elif rsi_value > 70:
        rsi_status = "Overbought"
    elif rsi_value > 50:
        rsi_status = "Upper Zone"
    elif rsi_value > 30:
        rsi_status = "Lower Zone"
    else:
        rsi_status = "Oversold"

    atr_value = atr14.loc[latest]
    adr_value = (high - low).rolling(20).mean().loc[latest]
    macd_value = macd.loc[latest]
    signal_value = macd_signal.loc[latest]
    adx_value = adx14.loc[latest]
    plus_value = plus_di.loc[latest]
    minus_value = minus_di.loc[latest]

    return {
        "as_of_date": pd.Timestamp(data.loc[latest, "date"]).date(),
        "price": _decimal(price),
        "sma20": _decimal(close.rolling(20).mean().loc[latest]),
        "sma50": _decimal(close.rolling(50).mean().loc[latest]),
        "sma100": _decimal(close.rolling(100).mean().loc[latest]),
        "sma150": _decimal(close.rolling(150).mean().loc[latest]),
        "sma200": _decimal(close.rolling(200).mean().loc[latest]),
        "sma250": _decimal(close.rolling(250).mean().loc[latest]),
        "atr14": _decimal(atr_value),
        "atr_pct": _decimal(atr_value / price, "0.00000001"),
        "adr20": _decimal(adr_value),
        "adr_pct": _decimal(adr_value / price, "0.00000001"),
        "macd": _decimal(macd_value),
        "macd_signal": _decimal(signal_value),
        "momentum": _status(macd_value > signal_value, "Bullish", "Bearish"),
        "vwap": _decimal(vwap),
        "vwap_status": _status(price > vwap, "Bullish", "Bearish"),
        "adx14": _decimal(adx_value),
        "trending": None if pd.isna(adx_value) else bool(adx_value > 20),
        "dmi_plus14": _decimal(plus_value),
        "dmi_minus14": _decimal(minus_value),
        "dmi_status": "" if pd.isna(plus_value) or pd.isna(minus_value) else _status(
            plus_value > minus_value, "Bullish", "Bearish"
        ),
        "rsi14": _decimal(rsi_value),
        "rsi_status": rsi_status,
        "bb20_upper": _decimal(bb_upper.loc[latest]),
        "bb20_middle": _decimal(bb_middle.loc[latest]),
        "bb20_lower": _decimal(bb_lower.loc[latest]),
        "bb20_width": _decimal(bb_width),
        "kc20_upper": _decimal(kc_upper.loc[latest]),
        "kc20_middle": _decimal(kc_middle.loc[latest]),
        "kc20_lower": _decimal(kc_lower.loc[latest]),
        "kc20_width": _decimal(kc_width),
        "bb_kc_ratio": _decimal(bb_width / kc_width, "0.00000001") if squeeze and kc_width else None,
        "is_squeeze": squeeze,
        "calculation_version": CALCULATION_VERSION,
    }
