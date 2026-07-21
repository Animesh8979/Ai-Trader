"""Command-line interface: `godmode <command>`.

Commands available now (Phase 0):
    setup       interactive setup wizard (keys + testnet)
    smoke       connectivity smoke test
    status      show mode + kill-switch + config
    stop        ENGAGE the kill switch (halt trading)
    resume      clear the kill switch
    version     print version

Forward-looking stubs (wired up in later phases): run, dashboard.
"""

from __future__ import annotations

import argparse
import sys

from godmode import __version__
from godmode.core.logging import setup_logging


def _cmd_setup(_args) -> int:
    from godmode.onboarding import run_setup_wizard

    return run_setup_wizard()


def _cmd_smoke(args) -> int:
    from godmode.diagnostics import run_smoke_test

    return run_smoke_test(place_probe=not args.no_order, ping_llm=not args.no_llm)


def _cmd_status(_args) -> int:
    from rich.console import Console
    from rich.table import Table

    from godmode.core.config import load_config
    from godmode.core.killswitch import get_kill_switch

    cfg = load_config()
    status = get_kill_switch().status()

    table = Table(title="Godmode — Status")
    table.add_column("Key", style="bold")
    table.add_column("Value")
    table.add_row("mode", cfg.mode)
    table.add_row("halted", "[red]YES[/]" if status["halted"] else "[green]no[/]")
    if status["reason"]:
        table.add_row("halt reason", str(status["reason"].get("reason")))
    table.add_row("heartbeat age (s)", str(status["heartbeat_age_seconds"]))
    table.add_row("LLM providers", ", ".join(cfg.secrets.configured_llm_providers()) or "none")
    table.add_row("enabled markets", ", ".join(cfg.enabled_markets().keys()) or "none")

    Console().print(table)
    return 0


def _cmd_stop(args) -> int:
    from godmode.core.killswitch import get_kill_switch

    get_kill_switch().engage(args.reason, source="cli")
    print(f"Kill switch ENGAGED: {args.reason}")
    return 0


def _cmd_resume(_args) -> int:
    from godmode.core.killswitch import get_kill_switch

    get_kill_switch().reset(source="cli")
    print("Kill switch cleared. Trading may resume.")
    return 0


def _cmd_version(_args) -> int:
    print(f"godmode-trader {__version__}")
    return 0


def _cmd_run(_args) -> int:
    import asyncio
    from godmode.execution.live_runner import LiveRunner
    from godmode.core.logging import setup_logging

    setup_logging()
    
    runner = LiveRunner()
    
    # Run loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    try:
        runner.start("Live execution loop initiated via CLI run command.")
        print("\n======================================================================")
        print(" Godmode Trading Agent — Live execution loop is running.")
        print(" Press Ctrl+C to terminate the process.")
        print("======================================================================\n")
        loop.run_forever()
    except KeyboardInterrupt:
        print("\nCtrl+C detected. Shutting down LiveRunner...")
        runner.stop()
    finally:
        loop.close()
    return 0


def _cmd_dashboard(args) -> int:
    import uvicorn
    from godmode.dashboard.app import app

    host = getattr(args, "host", "127.0.0.1")
    port = getattr(args, "port", 8000)
    print(f"Launching Godmode Dashboard on http://{host}:{port} ...")
    uvicorn.run(app, host=host, port=port)
    return 0



_DISPATCH = {
    "setup": _cmd_setup,
    "smoke": _cmd_smoke,
    "status": _cmd_status,
    "stop": _cmd_stop,
    "resume": _cmd_resume,
    "run": _cmd_run,
    "dashboard": _cmd_dashboard,
    "version": _cmd_version,
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="godmode",
        description="Godmode Trading Agent — precise, automated, reliable (paper-first).",
    )
    parser.add_argument("--version", action="store_true", help="print version and exit")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("setup", help="interactive setup wizard (keys, testnet)")

    smoke = sub.add_parser("smoke", help="run the connectivity smoke test")
    smoke.add_argument("--no-llm", action="store_true", help="skip the LLM ping")
    smoke.add_argument("--no-order", action="store_true", help="skip the order round-trip probe")

    sub.add_parser("status", help="show mode + kill-switch + config status")

    stop = sub.add_parser("stop", help="ENGAGE the kill switch (halt all trading)")
    stop.add_argument("--reason", default="manual stop via CLI")

    sub.add_parser("resume", help="clear the kill switch")
    sub.add_parser("run", help="(Phase 2) run the autonomous trading loop")
    
    dashboard = sub.add_parser("dashboard", help="launch the local web dashboard")
    dashboard.add_argument("--host", default="127.0.0.1", help="dashboard server host")
    dashboard.add_argument("--port", type=int, default=8000, help="dashboard server port")

    sub.add_parser("version", help="print version")
    return parser



def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()
    args = parser.parse_args(argv)
    from godmode.core.bootstrap import ensure_utf8_console
    from godmode.core.binance_guard import enforce as enforce_binance_testnet

    enforce_binance_testnet()
    ensure_utf8_console()
    setup_logging()

    if getattr(args, "version", False) and not args.command:
        return _cmd_version(args)
    if not args.command:
        parser.print_help()
        return 0
    return _DISPATCH[args.command](args)


if __name__ == "__main__":
    raise SystemExit(main())
