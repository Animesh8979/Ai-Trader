# 🚀 START HERE — Godmode Trading Agent

Welcome! This guide is written for **non-coders**. Follow it top to bottom.

> **The honest truth first:** No trading bot can promise profits — anyone who says so is
> lying. This project's whole goal is to be **safe, disciplined, and reliable** so that it
> survives long enough to *maybe* make money. It starts in **paper mode** (fake money, real
> prices). No real money is ever at risk until *you* deliberately turn it on, much later.

---

## What you need (5 minutes)

- A **Windows PC** (you have one ✅) with **Python 3.10+** already installed.
- **One** AI key — Claude *or* Gemini (free tiers exist). The wizard gives you the link.
- **One** free crypto **testnet** account (fake money). The wizard gives you the link.

You do **not** need to know how to code.

---

## Step 1 — One-time setup

1. Open **PowerShell** in this folder:
   right-click the `Ai trader` folder → **“Open in Terminal”** (or open PowerShell and
   `cd` into it).
2. Run:

   ```powershell
   ./setup.ps1
   ```

   This creates a private Python environment, installs everything, and then launches the
   **setup wizard**.

   > If Windows blocks the script, run this once, then try again:
   > `Set-ExecutionPolicy -Scope Process -Bypass`

3. The **wizard** will ask you to:
   - pick an AI provider and paste its key (it shows you exactly where to get it), and
   - pick a free crypto testnet and paste its key + secret.

   Your keys are saved privately in a file called `.env` and are **never** shared or shown again.

---

## Step 2 — Check everything works

The wizard offers to run a **smoke test** automatically. You can also run it any time:

```powershell
./run.ps1 smoke
```

You'll get a little table. **Green = good.** It connects to the testnet, reads a live
price, checks your (fake) balance, places + cancels a tiny harmless test order, and pings
your AI. If something is red, the message tells you what to fix (usually a wrong key —
just run `./run.ps1 setup` again).

---

## Everyday commands

| What you want | Command |
|---|---|
| Re-run setup / change keys | `./run.ps1 setup` |
| Test that things work | `./run.ps1 smoke` |
| See current status | `./run.ps1 status` |
| **STOP everything now** (emergency) | `./run.ps1 stop` |
| Allow trading again | `./run.ps1 resume` |

> 🛑 **The STOP button:** `./run.ps1 stop` instantly halts all trading and the halt
> *survives restarts*. It works by creating a file named `data/STOP`. You can even create
> or delete that file by hand. Nothing trades while it exists. A real web **STOP button**
> arrives with the dashboard in a later phase.

---

## Where things live

```
config/        settings you can tweak (risk limits, which markets, which AI models)
data/          your local database, logs, and audit trail (private)
.env           your secret keys (private — never share this file)
src/godmode/   the actual program
```

- **Risk limits** (how much it can ever risk) live in `config/config.yaml`. They are
  enforced no matter what the AI "wants".
- **Which AI model** each part of the bot uses lives in `config/models.yaml` — change a
  line there to switch from Claude to Gemini.

---

## What happens next (the roadmap)

You're at the end of **Phase 0** (foundations + a working, safe pipe). Coming up:

1. **Phase 1** — backtesting on historical data + the deterministic risk engine.
2. **Phase 2** — the multi-agent “brain” trading on the crypto testnet (paper money).
3. **Phase 3** — the live **dashboard** with charts and a big STOP button.
4. **Phase 4** — add the other markets (prediction markets, stocks, forex).
5. **Phase 5** — a careful, gated switch to real money with tiny amounts.

Questions or something red you can't fix? Re-run `./run.ps1 setup`, or check the newest
file in `data/logs/`.
