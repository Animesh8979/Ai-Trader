#!/usr/bin/env python
import pathlib
import sys
import asyncio
import itertools
from decimal import Decimal
from unittest.mock import MagicMock, patch

# Ensure src/ is in the path
SRC = pathlib.Path(__file__).resolve().parents[1] / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from godmode.execution.live_runner import LiveRunner
from godmode.llm.provider import LLMResponse
from godmode.core.config import load_config
from godmode.core.killswitch import get_kill_switch
from godmode.core.db import get_db

async def run_sandbox():
    print("======================================================================")
    print(" STARTING GODMODE AGENT SANDBOX TEST RUN (ALPHA GENERATION PIPELINE) ")
    print("======================================================================\n")

    # Override config to use a tiny interval
    cfg = load_config()
    cfg.app.decision_interval_seconds = 2.0
    cfg.app.mode = "paper"

    # Reset/isolate test database file to not contaminate live data
    import godmode.core.paths as paths
    import godmode.core.db as db_mod
    orig_db_path = paths.DB_PATH
    paths.DB_PATH = pathlib.Path("data/sandbox_test_godmode.sqlite3")
    db_mod.reset_db_singleton()
    db = db_mod.get_db()
    db.init_schema()

    # Generate 30 realistic candles for 1m and 15m
    # timestamp, open, high, low, close, volume
    candles_1m = [[1700000000 + i * 60, 50000.0 + i * 10, 50050.0 + i * 10, 49950.0 + i * 10, 50020.0 + i * 10, 1.5] for i in range(30)]
    candles_15m = [[1700000000 + i * 900, 50000.0 + i * 50, 50100.0 + i * 50, 49900.0 + i * 50, 50050.0 + i * 50, 10.0] for i in range(30)]

    # Mocks
    mock_adapter = MagicMock()
    mock_adapter.fetch_balance.return_value = {
        "USDT": {"free": 50000.0, "total": 50000.0},
        "BTC": {"free": 0.0, "total": 0.0}
    }
    mock_adapter.exchange.fetch_ohlcv.side_effect = lambda symbol, timeframe, limit=30: (
        candles_1m if timeframe == "1m" else candles_15m
    )
    mock_adapter.exchange.create_order.return_value = {
        "id": "mock-order-id-12345",
        "symbol": "BTC/USDT",
        "type": "market",
        "side": "buy",
        "amount": 0.05,
        "price": 50310.0,
        "status": "closed",
    }

    # Cycles for mock responses
    json_responses = [
        # Tick 1
        {"outlook": "bullish", "indicators_summary": "VWAP supports upward trend. Bollinger Bands expanding.", "support": 49000.0, "resistance": 51000.0},
        {"sentiment_score": 0.75, "impact_summary": "Market sentiment is positive with high trading volume."},
        {"action": "buy", "size": 0.05, "stop_loss_pct": 2.0, "take_profit_pct": 5.0, "reason": "Programmatic TA signals a bullish breakout."},
        {"verdict": "approve", "reason": "Position size within exposure limits."},
        # Tick 2
        {"outlook": "neutral", "indicators_summary": "RSI consolidation near 55. Volume declining.", "support": 49500.0, "resistance": 51500.0},
        {"sentiment_score": 0.2, "impact_summary": "Macroeconomic reports neutral."},
        {"action": "hold", "size": 0.0, "stop_loss_pct": 0.0, "take_profit_pct": 0.0, "reason": "No clear breakout pattern identified."},
        {"verdict": "approve", "reason": "Hold requires no size."}
    ]
    json_cycle = itertools.cycle(json_responses)

    text_responses = [
        LLMResponse(text="- Strong VWAP support.\n- Bullish EMA cross.", model="mock-model", role="bull_researcher"),
        LLMResponse(text="- Resistance level close.\n- RSI near neutral.", model="mock-model", role="bear_researcher"),
        LLMResponse(text="- Moving averages positive.", model="mock-model", role="bull_researcher"),
        LLMResponse(text="- Volume dropping fast.", model="mock-model", role="bear_researcher")
    ]
    text_cycle = itertools.cycle(text_responses)

    def mock_complete_json(role, system, user, cycle_id=None, run_id=None, record=False):
        resp = next(json_cycle)
        if record and run_id is not None:
            db.insert("agent_messages", {
                "run_id": run_id,
                "ts": "2026-06-07T12:00:00Z",
                "cycle_id": cycle_id,
                "role": role,
                "model": "mock-model",
                "input_summary": f"system: {system[:50]} | user: {user[:50]}",
                "output_text": str(resp),
                "tokens_in": 100,
                "tokens_out": 50,
                "cost_usd": 0.001,
                "latency_ms": 150
            })
        return resp

    def mock_complete(role, messages, cycle_id=None, run_id=None, record=False):
        resp = next(text_cycle)
        if record and run_id is not None:
            db.insert("agent_messages", {
                "run_id": run_id,
                "ts": "2026-06-07T12:00:00Z",
                "cycle_id": cycle_id,
                "role": role,
                "model": "mock-model",
                "input_summary": str(messages)[:100],
                "output_text": resp.text,
                "tokens_in": 100,
                "tokens_out": 50,
                "cost_usd": 0.001,
                "latency_ms": 150
            })
        return resp

    mock_llm_client = MagicMock()
    mock_llm_client.complete_json.side_effect = mock_complete_json
    mock_llm_client.complete.side_effect = mock_complete

    # Patches
    patch_ks = patch("godmode.core.killswitch.KillSwitch.is_halted", return_value=False)
    patch_adapter = patch("godmode.execution.live_runner.CryptoCcxtAdapter", return_value=mock_adapter)
    patch_brain = patch("godmode.agents.brain.LLMClient", return_value=mock_llm_client)

    with patch_ks, patch_adapter, patch_brain:
        runner = LiveRunner(config=cfg)
        
        print("[INIT] Starting LiveRunner loop in background...")
        runner.start(note="Sandbox test run of upgraded pipeline.")

        # Wait for 5 seconds (allows 2 ticks to execute since interval is 2s)
        await asyncio.sleep(5.0)

        print("[CLEANUP] Stopping LiveRunner...")
        runner.stop()

    # Verify database entries
    orders = db.query("SELECT * FROM orders")
    fills = db.query("SELECT * FROM fills")
    decisions = db.query("SELECT * FROM decisions")
    agent_messages = db.query("SELECT * FROM agent_messages")
    positions = db.query("SELECT * FROM positions")

    print("\n======================================================================")
    print(" VERIFICATION REPORT ")
    print("======================================================================")
    print(f"Decisions Recorded: {len(decisions)}")
    for d in decisions:
        print(f"  - Time: {d['ts']} | Symbol: {d['symbol']} | Proposal: {d['proposal_json']} | Verdict: {d['risk_verdict']} | Action: {d['final_action']}")

    print(f"Orders Placed: {len(orders)}")
    for o in orders:
        print(f"  - Symbol: {o['symbol']} | Side: {o['side']} | Qty: {o['qty']} | Price: {o['price']} | Status: {o['status']}")

    print(f"Fills Logged: {len(fills)}")
    for f in fills:
        print(f"  - Symbol: {f['symbol']} | Side: {f['side']} | Qty: {f['qty']} | Price: {f['price']} | PnL: {f['realized_pnl']}")

    print(f"Active Positions in DB: {len(positions)}")
    for p in positions:
        print(f"  - Venue: {p['venue']} | Symbol: {p['symbol']} | Qty: {p['qty']} | Avg Price: {p['avg_price']}")

    print(f"Agent Debate Log Messages in DB: {len(agent_messages)}")

    # Restoring db
    paths.DB_PATH = orig_db_path
    db_mod.reset_db_singleton()

    # Clean up sandbox DB file
    sandbox_db = pathlib.Path("data/sandbox_test_godmode.sqlite3")
    if sandbox_db.exists():
        try:
            sandbox_db.unlink()
            pathlib.Path("data/sandbox_test_godmode.sqlite3-journal").unlink(missing_ok=True)
        except Exception as exc:
            print(f"Could not delete temporary database file: {exc}")

    # Integrity Assertions
    assert len(decisions) >= 2, f"Expected at least 2 decisions, got {len(decisions)}"
    assert len(orders) >= 1, f"Expected at least 1 order from the bullish buy decision, got {len(orders)}"
    assert len(fills) >= 1, f"Expected at least 1 fill log, got {len(fills)}"
    assert len(agent_messages) >= 8, f"Expected at least 8 agent messages in the debate (2 ticks * 4 roles), got {len(agent_messages)}"
    
    print("\n[SUCCESS] Sandbox test completed successfully! All database states and event loop metrics verified.")

if __name__ == "__main__":
    asyncio.run(run_sandbox())
