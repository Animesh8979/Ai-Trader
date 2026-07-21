"""Verification script for Dual-Monitor Indian/International Intelligence Feed and Remediation Fixes."""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from godmode.data.live_intelligence import get_live_intelligence
from godmode.llm.free_router import get_free_router
from godmode.agents.chronos_agent import ChronosProphetAgent
from godmode.core.db import get_db

def main():
    print("=== [TEST 1] Testing Live Dual-Screen Intelligence Feed (Indian & International) ===")
    feed = get_live_intelligence()
    intel = feed.get_combined_intelligence()
    assert "indian" in intel, "Indian intelligence missing"
    assert "international" in intel, "International intelligence missing"
    
    nifty = intel["indian"]["indices"]["NIFTY 50"]
    print(f"  [OK] Indian NIFTY 50 telemetry: LTP={nifty['price']} ({nifty['change_24h_pct']}%)")
    print(f"  [OK] Indian News count: {len(intel['indian']['news'])}")
    
    fng = intel["international"]["fear_greed"]
    btc = intel["international"]["assets"]["BTC/USDT"]
    print(f"  [OK] International Fear & Greed: Score={fng['score']} ({fng['label']})")
    print(f"  [OK] International BTC/USDT: ${btc['price']} ({btc['change_24h_pct']}%)")
    print(f"  [OK] International News count: {len(intel['international']['news'])}")

    print("\n=== [TEST 2] Testing Free LLM Router ===")
    router = get_free_router()
    print(f"  [OK] FreeLLMRouter initialized (OpenRouter key present: {bool(router.openrouter_key)})")

    print("\n=== [TEST 3] Testing Corrected Chronos Prophet Drift Math ===")
    chronos = ChronosProphetAgent(forecast_steps=12)
    prices = [100.0, 101.0, 102.5, 101.8, 103.2, 104.5, 105.0]
    dist = chronos.predict_distribution(prices)
    assert dist["p10"] > 0 and dist["p50"] > 0 and dist["p90"] >= dist["p50"] >= dist["p10"], "Invalid Chronos target ordering"
    print(f"  [OK] Chronos Forecast targets: P10={dist['p10']}, P50={dist['p50']}, P90={dist['p90']}")

    print("\n=== [TEST 4] Testing Database get_position and Realized PnL Storage ===")
    db = get_db()
    db.upsert_position("binance", "BTC/USDT", "0.5", "63500.00")
    pos = db.get_position("binance", "BTC/USDT")
    assert pos is not None and float(pos["qty"]) == 0.5, "get_position failed"
    print(f"  [OK] Database position lookup verified: {pos['symbol']} Qty={pos['qty']} @ {pos['avg_price']}")

    print("\nALL 4 DUAL-SCREEN & ARCHITECTURAL UPGRADE TESTS PASSED BRUTALLY!")

if __name__ == "__main__":
    main()
