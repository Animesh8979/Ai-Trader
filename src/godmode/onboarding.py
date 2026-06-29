"""Interactive setup wizard (`godmode setup`).

Walks a non-technical user through:
  * picking one or more AI providers and pasting the API key (with the exact URL)
  * picking a free crypto TESTNET and pasting its key/secret
  * writing everything safely into .env (secrets are never echoed back)
  * optionally running the smoke test to confirm it all works

Everything defaults to the safe paper-trading mode.
"""

from __future__ import annotations

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Confirm, Prompt

from godmode.core import paths
from godmode.core.config import load_config
from godmode.core.envfile import update_env_file

console = Console()

# provider key -> (label, env var, where to get it)
PROVIDERS = {
    "1": ("anthropic", "Claude (Anthropic)", "ANTHROPIC_API_KEY",
          "https://console.anthropic.com/  ->  API Keys"),
    "2": ("gemini", "Gemini (Google AI Studio)", "GEMINI_API_KEY",
          "https://aistudio.google.com/app/apikey"),
    "3": ("openai", "OpenAI", "OPENAI_API_KEY",
          "https://platform.openai.com/api-keys"),
}

# venue key -> (label, (key env, secret env), where to get it)
VENUES = {
    "1": ("binance_testnet", "Binance Spot Testnet (recommended)",
          ("BINANCE_TESTNET_API_KEY", "BINANCE_TESTNET_API_SECRET"),
          "https://testnet.binance.vision/  (log in with GitHub, then 'Generate HMAC_SHA256 Key')"),
    "2": ("bybit_testnet", "Bybit Testnet",
          ("BYBIT_TESTNET_API_KEY", "BYBIT_TESTNET_API_SECRET"),
          "https://testnet.bybit.com/  ->  API Management  ->  Create New Key"),
}

_DISCLAIMER = (
    "[bold]Welcome to the Godmode Trading Agent setup.[/]\n\n"
    "This bot defaults to [bold green]paper trading[/] — simulated money, real prices. "
    "No real funds are ever at risk until you explicitly switch to live mode much later.\n\n"
    "[yellow]Honest note:[/] no trading bot can guarantee profits. This project's edge is "
    "discipline, risk control, and reliability — not magic returns.\n\n"
    "You only need [bold]one[/] AI provider key and [bold]one[/] free crypto testnet key to begin."
)


def _configure_providers(updates: dict[str, str]) -> list[str]:
    chosen: list[str] = []
    console.print("\n[bold underline]Step 1 — AI provider(s)[/]")
    console.print("You can add more than one (extras act as automatic fallbacks).\n")
    for code, (_, label, _env, url) in PROVIDERS.items():
        console.print(f"  [cyan]{code}[/]  {label}   [dim]{url}[/]")
    console.print("  [cyan]0[/]  Skip for now\n")

    while True:
        code = Prompt.ask("Pick a provider to add", choices=["0", "1", "2", "3"], default="1")
        if code == "0":
            break
        pid, label, env_var, url = PROVIDERS[code]
        console.print(f"\nGet your key here: [link]{url}[/]")
        key = Prompt.ask(f"Paste your {label} API key", password=True).strip()
        if key:
            updates[env_var] = key
            chosen.append(pid)
            console.print(f"[green]✓ {label} key saved.[/]")
        if not Confirm.ask("Add another AI provider?", default=False):
            break
    return chosen


def _configure_venue(updates: dict[str, str]) -> str:
    console.print("\n[bold underline]Step 2 — Free crypto testnet[/]")
    console.print("Fake money, real prices. This is where the bot will practice.\n")
    for code, (_, label, _envs, url) in VENUES.items():
        console.print(f"  [cyan]{code}[/]  {label}   [dim]{url}[/]")
    console.print("  [cyan]0[/]  Skip for now\n")

    code = Prompt.ask("Pick a testnet", choices=["0", "1", "2"], default="1")
    if code == "0":
        return ""
    venue, label, (key_env, secret_env), url = VENUES[code]
    console.print(f"\nCreate a key here: [link]{url}[/]")
    api_key = Prompt.ask(f"Paste your {label} API key", password=True).strip()
    api_secret = Prompt.ask(f"Paste your {label} API secret", password=True).strip()
    if api_key and api_secret:
        updates[key_env] = api_key
        updates[secret_env] = api_secret
        console.print(f"[green]✓ {label} keys saved.[/]")
    return venue


def run_setup_wizard() -> int:
    from godmode.core.bootstrap import ensure_utf8_console

    ensure_utf8_console()
    console.print(Panel(_DISCLAIMER, title="godmode setup", border_style="cyan"))

    updates: dict[str, str] = {"GODMODE_MODE": "paper"}
    providers = _configure_providers(updates)
    venue = _configure_venue(updates)

    update_env_file(paths.ENV_FILE, updates)
    console.print(f"\n[green]Saved configuration to[/] {paths.ENV_FILE}")

    # Summary (never prints secrets)
    summary = Table_summary(providers, venue)
    console.print(summary)

    load_config(reload=True)  # refresh cache so a follow-up smoke test sees the new keys

    if Confirm.ask("\nRun the connectivity smoke test now? (recommended)", default=True):
        from godmode.diagnostics import run_smoke_test

        return run_smoke_test()

    console.print(
        "\nWhen you're ready, run:  [bold]godmode smoke[/]   (or)   [bold]py scripts/smoke_test.py[/]"
    )
    return 0


def Table_summary(providers: list[str], venue: str) -> Panel:
    lines = [
        f"AI providers : [green]{', '.join(providers) if providers else 'none yet'}[/]",
        f"Crypto venue : [green]{venue or 'none yet'}[/]",
        "Mode         : [bold green]paper[/] (safe)",
    ]
    if not providers:
        lines.append("[yellow]Tip:[/] add an AI key later by re-running `godmode setup`.")
    if not venue:
        lines.append("[yellow]Tip:[/] add a testnet later by re-running `godmode setup`.")
    return Panel("\n".join(lines), title="Configured", border_style="green")
