"""End-to-end connectivity smoke test (Phase 0 deliverable).

Proves the whole pipe works before we build anything on top:
  1. config loads, mode + venue resolved
  2. crypto market data (public): connect to the configured testnet, read a live price
  3. auth: read the (fake) testnet balance
  4. order round-trip (best effort): place + cancel a tiny non-marketable order
  5. LLM (best effort): a one-token ping to the configured model

Stages 1-3 must pass for an overall PASS; 4-5 are bonus and only warn on failure.
Designed to give a non-technical user a clear, friendly report.
"""

from __future__ import annotations

from typing import Optional

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from godmode.core.config import Config, load_config
from godmode.core.logging import setup_logging

console = Console()


class _Report:
    def __init__(self) -> None:
        self.rows: list[tuple[str, str, str]] = []
        self.critical_ok = True

    def add(self, stage: str, status: str, detail: str, *, critical: bool = False) -> None:
        self.rows.append((stage, status, detail))
        if critical and status != "PASS":
            self.critical_ok = False

    def render(self) -> None:
        table = Table(title="Godmode — Connectivity Smoke Test", expand=True)
        table.add_column("Stage", style="bold")
        table.add_column("Result", justify="center")
        table.add_column("Detail", overflow="fold")
        style = {"PASS": "green", "WARN": "yellow", "FAIL": "red"}
        for stage, status, detail in self.rows:
            mark = {"PASS": "✓ PASS", "WARN": "⚠ WARN", "FAIL": "✗ FAIL"}.get(status, status)
            table.add_row(stage, f"[{style.get(status,'white')}]{mark}[/]", detail)
        console.print(table)


def run_smoke_test(
    *,
    place_probe: bool = True,
    ping_llm: bool = True,
    config: Optional[Config] = None,
) -> int:
    """Run the smoke test. Returns 0 on overall pass, 1 otherwise."""
    from godmode.core.bootstrap import ensure_utf8_console

    ensure_utf8_console()
    setup_logging()
    report = _Report()
    cfg = config or load_config()

    # --- Stage 1: config ---------------------------------------------------
    crypto = cfg.markets.get("crypto")
    venue = crypto.venue if crypto else "(none)"
    symbol = crypto.symbols[0] if (crypto and crypto.symbols) else "BTC/USDT"
    providers = cfg.secrets.configured_llm_providers()
    report.add(
        "Config",
        "PASS",
        f"mode={cfg.mode}  venue={venue}  symbol={symbol}  llm={providers or 'none'}",
        critical=True,
    )

    # --- Stages 2-4: crypto ------------------------------------------------
    if crypto and crypto.enabled:
        try:
            from godmode.execution.crypto_ccxt import CryptoCcxtAdapter

            adapter = CryptoCcxtAdapter(venue, config=cfg)
            try:
                price = adapter.fetch_price(symbol)
                report.add("Market data", "PASS", f"{symbol} last = {price}", critical=True)
            except Exception as exc:  # noqa: BLE001
                report.add("Market data", "FAIL", f"{type(exc).__name__}: {exc}", critical=True)

            try:
                quote = crypto.quote_currency or "USDT"
                free = adapter.free_balance(quote)
                report.add("Auth / balance", "PASS", f"free {quote} = {free}", critical=True)
            except Exception as exc:  # noqa: BLE001
                report.add(
                    "Auth / balance",
                    "FAIL",
                    f"{type(exc).__name__}: {exc} (check your testnet keys)",
                    critical=True,
                )

            if place_probe:
                try:
                    info = adapter.place_and_cancel_probe(symbol)
                    report.add(
                        "Order round-trip",
                        "PASS",
                        f"placed+canceled {info['amount']} {symbol} @ {info['limit_price']}",
                    )
                except Exception as exc:  # noqa: BLE001
                    report.add(
                        "Order round-trip",
                        "WARN",
                        f"{type(exc).__name__}: {exc} (often just an empty testnet balance)",
                    )
        except Exception as exc:  # noqa: BLE001
            report.add("Crypto venue", "FAIL", f"{type(exc).__name__}: {exc}", critical=True)
    else:
        report.add("Crypto venue", "WARN", "crypto market disabled in config.yaml")

    # --- Stage 5: LLM ------------------------------------------------------
    if ping_llm:
        if providers:
            try:
                from godmode.llm import LLMClient

                resp = LLMClient(cfg).ping()
                report.add(
                    "LLM ping",
                    "PASS",
                    f"{resp.model} -> '{resp.text.strip()[:40]}' ({resp.latency_ms} ms)",
                )
            except Exception as exc:  # noqa: BLE001
                report.add("LLM ping", "WARN", f"{type(exc).__name__}: {exc}")
        else:
            report.add("LLM ping", "WARN", "no LLM key configured (run `godmode setup`)")

    # --- Result ------------------------------------------------------------
    report.render()
    if report.critical_ok:
        console.print(
            Panel.fit(
                "[bold green]SMOKE TEST PASSED[/]\nThe core pipe works. You're ready for the next phase.",
                border_style="green",
            )
        )
        return 0
    console.print(
        Panel.fit(
            "[bold red]SMOKE TEST FAILED[/]\nFix the FAIL rows above, then run `godmode smoke` again.\n"
            "Most issues are missing/incorrect keys — run `godmode setup` to re-enter them.",
            border_style="red",
        )
    )
    return 1
