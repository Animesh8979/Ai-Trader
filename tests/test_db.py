from godmode.core.db import Database


def test_insert_and_query(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    run_id = db.start_run("paper", "unit test")
    assert run_id >= 1

    order_id = db.insert(
        "orders",
        {
            "run_id": run_id,
            "client_order_id": "c1",
            "venue": "binance_testnet",
            "symbol": "BTC/USDT",
            "side": "buy",
            "type": "limit",
            "qty": "0.001",
            "price": "60000",
            "status": "new",
            "created_at": "t0",
            "updated_at": "t0",
        },
    )
    row = db.query_one("SELECT * FROM orders WHERE id=?", (order_id,))
    assert row["client_order_id"] == "c1"
    assert row["qty"] == "0.001"  # stored as text -> Decimal-safe
    db.close()


def test_metric_and_position_upsert(tmp_path):
    db = Database(tmp_path / "t.sqlite3")
    db.record_metric("equity", 123.45)
    assert db.query_one("SELECT value FROM metrics WHERE key='equity'")["value"] == 123.45

    db.upsert_position("v", "BTC/USDT", "0.5", "100")
    db.upsert_position("v", "BTC/USDT", "0.7", "110")  # same key -> update, not insert
    positions = db.query("SELECT * FROM positions WHERE symbol='BTC/USDT'")
    assert len(positions) == 1
    assert positions[0]["qty"] == "0.7"
    db.close()
