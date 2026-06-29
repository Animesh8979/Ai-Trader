import os
import time
from decimal import Decimal
from pathlib import Path
from typing import Optional

import pandas as pd
from rich.console import Console
from rich.table import Table

from nautilus_trader.backtest.engine import BacktestEngine
from nautilus_trader.model.identifiers import Venue, InstrumentId
from nautilus_trader.model.data import Bar, BarType
from nautilus_trader.model.enums import OmsType, AccountType
from nautilus_trader.model.objects import Money, Currency, Price, Quantity
from nautilus_trader.model.instruments import CurrencyPair

from godmode.core.config import Config, load_config
from godmode.core.logging import get_logger
from godmode.strategies.ema_crossover import EMACrossover, EMACrossoverConfig

log = get_logger("backtest.runner")
console = Console()


def map_timeframe(tf: str) -> str:
    """Map standard timeframe strings (e.g., '1h', '15m') to Nautilus specifications."""
    tf = tf.lower().strip()
    if tf in ("1m", "1min"):
        return "1-MINUTE"
    if tf in ("5m", "5min"):
        return "5-MINUTE"
    if tf in ("15m", "15min"):
        return "15-MINUTE"
    if tf in ("1h", "60m"):
        return "1-HOUR"
    if tf in ("1d", "daily"):
        return "1-DAY"
    
    # Generic mapping
    if "m" in tf:
        return f"{tf.replace('m', '')}-MINUTE"
    if "h" in tf:
        return f"{tf.replace('h', '')}-HOUR"
    if "d" in tf:
        return f"{tf.replace('d', '')}-DAY"
    
    return "1-HOUR"


def get_or_create_instrument(symbol: str, venue_name: str) -> CurrencyPair:
    """Helper to return a mock or dynamically constructed Spot currency pair instrument."""
    symbol_clean = symbol.replace("/", "").upper()
    venue_upper = venue_name.upper()
    inst_id = InstrumentId.from_str(f"{symbol_clean}.{venue_upper}")

    from nautilus_trader.test_kit.providers import TestInstrumentProvider

    # Attempt to load standard test kit mock instruments
    if symbol_clean == "BTCUSDT" and "BINANCE" in venue_upper:
        return TestInstrumentProvider.btcusdt_binance()
    if symbol_clean == "ETHUSDT" and "BINANCE" in venue_upper:
        return TestInstrumentProvider.ethusdt_binance()

    # Dynamic fallback constructor
    try:
        base, quote = symbol.split("/")
    except ValueError:
        base, quote = symbol_clean[:3], symbol_clean[3:]

    now_ns = int(time.time() * 1e9)
    return CurrencyPair(
        instrument_id=inst_id,
        raw_symbol=symbol_clean,
        base_currency=Currency.from_str(base),
        quote_currency=Currency.from_str(quote),
        price_precision=2,
        size_precision=6,
        price_increment=Price(0.01, 2),
        size_increment=Quantity(0.000001, 6),
        ts_event=now_ns,
        ts_init=now_ns,
    )


def run_backtest(
    strategy_name: str,
    data_path: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    config: Optional[Config] = None,
) -> int:
    """Runs a historical backtest for a strategy using NautilusTrader."""
    cfg = config or load_config()
    
    # 1. Verify data path
    p = Path(data_path)
    if not p.exists():
        console.print(f"[red]Error: Data file not found at {data_path}[/]")
        return 1

    console.print(f"[cyan]Loading historical data from {p.name}...[/]")
    try:
        df = pd.read_csv(p)
        df.columns = [c.lower() for c in df.columns]
    except Exception as exc:
        console.print(f"[red]Error parsing CSV file: {exc}[/]")
        return 1

    # Check required columns
    required = {"timestamp", "open", "high", "low", "close", "volume"}
    missing = required - set(df.columns)
    if missing:
        console.print(f"[red]Error: CSV is missing required columns: {missing}[/]")
        return 1

    # Apply date filters if provided
    if "timestamp" in df.columns:
        df["timestamp_dt"] = pd.to_datetime(df["timestamp"])
        if start_date:
            df = df[df["timestamp_dt"] >= pd.to_datetime(start_date)]
        if end_date:
            df = df[df["timestamp_dt"] <= pd.to_datetime(end_date)]

    if len(df) == 0:
        console.print("[yellow]Warning: No data rows found within date range.[/]")
        return 1

    # 2. Configure Backtest Engine
    engine = BacktestEngine()
    
    # Resolve starting equity and symbol
    crypto_cfg = cfg.markets.get("crypto")
    venue_name = crypto_cfg.venue if crypto_cfg else "binance_testnet"
    starting_equity = cfg.app.paper_starting_equity
    base_ccy = cfg.app.base_currency or "USDT"

    symbol = crypto_cfg.symbols[0] if (crypto_cfg and crypto_cfg.symbols) else "BTC/USDT"
    instrument = get_or_create_instrument(symbol, venue_name)

    # 2. Configure Backtest Engine
    engine = BacktestEngine()
    venue = instrument.id.venue

    engine.add_venue(
        venue=venue,
        oms_type=OmsType.NETTING,
        account_type=AccountType.CASH,
        starting_balances=[Money(starting_equity, Currency.from_str(base_ccy))],
    )

    # 3. Add Instrument
    engine.add_instrument(instrument)

    # 4. Parse & Load Bar Data
    timeframe = crypto_cfg.candle_timeframe if crypto_cfg else "1h"
    tf_mapped = map_timeframe(timeframe)
    bar_type_str = f"{instrument.id}-{tf_mapped}-LAST-EXTERNAL"
    bar_type = BarType.from_str(bar_type_str)

    console.print(f"Loading [yellow]{len(df)}[/] candles for [yellow]{instrument.id}[/]...")
    
    price_prec = instrument.price_precision
    size_prec = instrument.size_precision

    bars = []
    for _, row in df.iterrows():
        ts_ns = pd.to_datetime(row["timestamp_dt"]).value
        bar = Bar(
            bar_type=bar_type,
            open=Price(float(row["open"]), price_prec),
            high=Price(float(row["high"]), price_prec),
            low=Price(float(row["low"]), price_prec),
            close=Price(float(row["close"]), price_prec),
            volume=Quantity(float(row["volume"]), size_prec),
            ts_event=ts_ns,
            ts_init=ts_ns,
        )
        bars.append(bar)

    engine.add_data(bars)

    engine.sort_data()

    # 5. Add Strategy
    if strategy_name.lower() == "ema_crossover":
        strat_cfg = EMACrossoverConfig(
            instrument_id=instrument.id,
            bar_type=bar_type,
            trade_size=Decimal("0.05"),  # 5% of starting equity per trade in BTC units roughly (or trade size)
        )
        strategy = EMACrossover(strat_cfg)
        engine.add_strategy(strategy)
    elif strategy_name.lower() == "multi_agent":
        from godmode.strategies.multi_agent_strategy import MultiAgentStrategy, MultiAgentStrategyConfig
        strat_cfg = MultiAgentStrategyConfig(
            instrument_id=instrument.id,
            bar_type=bar_type,
            trade_size=Decimal("0.05"),
        )
        strategy = MultiAgentStrategy(strat_cfg)
        engine.add_strategy(strategy)
    else:
        console.print(f"[red]Error: Unknown strategy '{strategy_name}'[/]")
        return 1

    # 6. Execute Backtest
    console.print("[green]Starting backtest execution loop...[/]")
    start_time = time.perf_counter()
    engine.run()
    elapsed = time.perf_counter() - start_time
    console.print(f"[green]Backtest completed in {elapsed:.3f} seconds.[/]")

    # 7. Print Performance Summary
    _print_summary(engine, starting_equity, base_ccy)
    
    # Save backtest run to local database
    _record_run_in_db(starting_equity, engine, strategy_name, symbol)

    return 0


def _print_summary(engine: BacktestEngine, starting_equity: float, base_ccy: str) -> None:
    # Query final balance/equity
    final_equity = starting_equity
    try:
        eq = engine.portfolio.equity()
        if eq is not None:
            final_equity = float(eq)
    except Exception:
        pass

    realized_pnl = 0.0
    try:
        pnl_dict = engine.portfolio.realized_pnls()
        if pnl_dict:
            realized_pnl = sum(float(val) for val in pnl_dict.values())
    except Exception:
        pass

    table = Table(title="Godmode — Backtest Results")
    table.add_column("Metric", style="bold")
    table.add_column("Value")

    table.add_row("Starting Equity", f"{starting_equity:,.2f} {base_ccy}")
    table.add_row("Final Equity", f"{final_equity:,.2f} {base_ccy}")
    
    pnl_pct = (realized_pnl / starting_equity) * 100
    pnl_style = "green" if realized_pnl >= 0 else "red"
    table.add_row("Realized PnL", f"[{pnl_style}]{realized_pnl:+,.2f} {base_ccy} ({pnl_pct:+.2f}%)[/]")
    
    # Count total fills
    total_fills = engine.cache.orders_closed_count()
    table.add_row("Total Orders Filled", str(total_fills))

    console.print(table)


def _record_run_in_db(starting_equity: float, engine: BacktestEngine, strategy: str, symbol: str) -> None:
    try:
        from godmode.core.db import get_db
        db = get_db()
        run_id = db.start_run(mode="backtest", note=f"Strategy: {strategy} Symbol: {symbol}")
        
        final_equity = starting_equity
        try:
            eq = engine.portfolio.equity()
            if eq is not None:
                final_equity = float(eq)
        except Exception:
            pass

        db.record_metric("starting_equity", starting_equity)
        db.record_metric("final_equity", final_equity)
        db.record_metric("realized_pnl", final_equity - starting_equity)
        db.end_run(run_id, status="success")
    except Exception as exc:
        log.debug(f"Failed to record backtest run in DB: {exc}")
