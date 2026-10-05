"""Deterministic CSV backtest runner.

Loads OHLCV candles from a CSV file, replays a strategy's signals bar by bar,
simulates fills at each bar's close with explicit fee drag, and records the run
plus its headline metrics into SQLite so the dashboard can chart performance.

Exit-code contract (CLI-friendly): 0 = success, 1 = failure. The `runs` row is
always closed out (`success` / `failed`) even when the simulation raises.
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import pandas as pd

from godmode.core.db import get_db
from godmode.core.logging import get_logger
from godmode.core.money import D, ZERO

log = get_logger("backtest")

_TIMEFRAME_UNITS = {"m": "MINUTE", "h": "HOUR", "d": "DAY"}

_REQUIRED_COLUMNS = {"timestamp", "open", "high", "low", "close", "volume"}

_SUPPORTED_STRATEGIES = ("ema_crossover",)


def map_timeframe(timeframe: str) -> str:
    """Map ccxt-style timeframes ("1h", "15m", "4h", "1d") to run-label form."""
    tf = str(timeframe).strip().lower()
    if len(tf) >= 2 and tf[-1] in _TIMEFRAME_UNITS and tf[:-1].isdigit():
        return f"{int(tf[:-1])}-{_TIMEFRAME_UNITS[tf[-1]]}"
    raise ValueError(f"unsupported timeframe {timeframe!r} (expected e.g. '1h', '15m', '1d')")


def _ema_crossover_signals(close: pd.Series, fast: int = 9, slow: int = 21) -> pd.Series:
    """Return +1 on fast-EMA crossing above slow-EMA, -1 on crossing below."""
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    position = (ema_fast > ema_slow).astype(int)
    return position.diff().fillna(0)


def _signals_for(strategy_name: str, frame: pd.DataFrame) -> pd.Series:
    if strategy_name not in _SUPPORTED_STRATEGIES:
        raise ValueError(
            f"unknown strategy {strategy_name!r}; supported: {', '.join(_SUPPORTED_STRATEGIES)}"
        )
    return _ema_crossover_signals(frame["close"].astype(float))


def _load_candles(data_path: Union[str, Path], start_date: Optional[str]) -> pd.DataFrame:
    path = Path(data_path)
    if not path.exists():
        raise FileNotFoundError(f"candle data not found: {path}")
    frame = pd.read_csv(path)
    missing = _REQUIRED_COLUMNS - set(frame.columns)
    if missing:
        raise ValueError(f"CSV missing required columns: {sorted(missing)}")
    frame["timestamp"] = pd.to_datetime(frame["timestamp"])
    numeric_cols = ["open", "high", "low", "close", "volume"]
    frame[numeric_cols] = frame[numeric_cols].apply(pd.to_numeric, errors="coerce")
    frame = frame.dropna(subset=["close"])
    frame = frame.sort_values("timestamp").reset_index(drop=True)
    if start_date is not None:
        frame = frame[frame["timestamp"] >= pd.Timestamp(start_date)].reset_index(drop=True)
    if frame.empty:
        raise ValueError(f"no candles found in {path.name} on/after {start_date or 'start'}")
    return frame


def run_backtest(
    strategy_name: str = "ema_crossover",
    data_path: Union[str, Path] = "",
    start_date: Optional[str] = None,
    starting_equity: float = 100_000.0,
    fee_bps: float = 10.0,
    invest_fraction: float = 0.95,
) -> int:
    """Replay `strategy_name` over the candles in `data_path` and persist results.

    Accounting model: entries deploy `invest_fraction` of available cash at the
    signal bar's close; exits realize PnL net of taker fees on both legs; any
    open position at the end is marked to the final close.
    """
    if not data_path:
        raise ValueError("data_path is required")

    db = get_db()
    note = f"{strategy_name} {Path(data_path).name}"
    if start_date:
        note += f" from {start_date}"
    run_id = db.start_run("backtest", note=note)

    try:
        frame = _load_candles(data_path, start_date)
        signals = _signals_for(strategy_name, frame)

        fee_rate = D(str(fee_bps)) / D(10_000)
        invest_frac = D(str(invest_fraction))
        if invest_frac < ZERO:
            invest_frac = ZERO
        elif invest_frac > D(1):
            invest_frac = D(1)
        cash = D(str(starting_equity))
        start_equity = cash
        qty = ZERO
        avg_entry = ZERO
        realized = ZERO
        peak_equity = cash
        max_drawdown = ZERO
        num_trades = 0
        last_close = ZERO

        for row in frame.itertuples(index=True):
            px = D(str(row.close))
            last_close = px
            signal = int(signals.iloc[row.Index])

            if signal > 0 and qty == 0 and cash > 0:
                notional = cash * invest_frac
                fee = notional * fee_rate
                bought = (notional - fee) / px
                if bought > 0:
                    cash -= notional
                    qty = bought
                    avg_entry = px
                    num_trades += 1
            elif signal < 0 and qty > 0:
                gross = qty * px
                fee = gross * fee_rate
                cash += gross - fee
                realized += (px - avg_entry) * qty - fee
                qty = ZERO
                avg_entry = ZERO

            equity = cash + qty * px
            if equity > peak_equity:
                peak_equity = equity
            if peak_equity > 0:
                drawdown = (peak_equity - equity) / peak_equity * D(100)
                if drawdown > max_drawdown:
                    max_drawdown = drawdown

        final_equity = cash + qty * last_close
        total_return = ZERO if start_equity == 0 else (
            (final_equity - start_equity) / start_equity * D(100)
        )

        db.record_metric("starting_equity", float(start_equity))
        db.record_metric("final_equity", float(final_equity))
        db.record_metric("realized_pnl", float(realized))
        db.record_metric("total_return_pct", float(total_return))
        db.record_metric("max_drawdown_pct", float(max_drawdown))
        db.record_metric("num_trades", float(num_trades))
        db.end_run(run_id, status="success")
        log.info(
            f"backtest {strategy_name} finished: equity {start_equity} -> {final_equity} "
            f"({float(total_return):.2f}%), trades={num_trades}, max_dd={float(max_drawdown):.2f}%"
        )
        return 0
    except Exception as exc:
        log.error(f"backtest failed: {exc}")
        try:
            db.end_run(run_id, status="failed")
        except Exception:
            pass
        return 1
