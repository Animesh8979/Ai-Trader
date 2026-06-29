import asyncio
import json
from datetime import datetime
from pathlib import Path
from typing import List, Set

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from godmode.core import paths
from godmode.core.config import load_config
from godmode.core.db import get_db
from godmode.core.killswitch import get_kill_switch
from godmode.core.logging import get_logger

log = get_logger("dashboard")

# Paths
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="Godmode Trading Agent — Dashboard")

# Mount Static & Templates
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Connection Pool for WebSockets
class ConnectionManager:
    def __init__(self):
        self.active_connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.discard(websocket)

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        payload = json.dumps(message, default=str)
        tasks = [connection.send_text(payload) for connection in self.active_connections]
        await asyncio.gather(*tasks, return_exceptions=True)


manager = ConnectionManager()


# Background Loop to Broadcast Updates
async def broadcast_status_loop():
    """Periodically check system state and broadcast changes to WebSocket clients."""
    last_halted = None
    last_position_hash = None
    
    while True:
        try:
            status = _get_system_status()
            
            # Simple hash to check if positions or status changed
            position_hash = hash(frozenset(
                (pos["symbol"], pos["qty"], pos["unrealized_pnl"]) for pos in status["positions"]
            ))
            
            # Broadcast on state shift or every 3 seconds
            if status["halted"] != last_halted or position_hash != last_position_hash:
                last_halted = status["halted"]
                last_position_hash = position_hash
                await manager.broadcast({
                    "type": "status",
                    "payload": status
                })
        except Exception as exc:
            log.debug(f"Error in broadcast status loop: {exc}")
            
        await asyncio.sleep(2.0)


import re
from pydantic import BaseModel
from typing import Optional
from fastapi import BackgroundTasks

ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub('', text)

class BacktestRequest(BaseModel):
    strategy: str
    data_path: str
    start: Optional[str] = None
    end: Optional[str] = None

def run_backtest_thread(strategy: str, data: str, start: Optional[str], end: Optional[str]):
    from godmode.backtest.runner import run_backtest
    try:
        run_backtest(
            strategy_name=strategy,
            data_path=data,
            start_date=start,
            end_date=end
        )
    except Exception as exc:
        log.error(f"Backtest run failed: {exc}")

@app.on_event("startup")
async def startup_event():
    asyncio.create_task(broadcast_status_loop())
    
    # Intercept all logs and pipe them over WebSocket connections
    from loguru import logger
    
    def websocket_sink(message):
        record = message.record
        text = strip_ansi(record["message"])
        level = record["level"].name.lower()
        comp = record.get("extra", {}).get("component", "system")
        try:
            loop = asyncio.get_running_loop()
            asyncio.run_coroutine_threadsafe(
                manager.broadcast({
                    "type": "log",
                    "source": comp,
                    "text": text,
                    "level": level
                }),
                loop
            )
        except RuntimeError:
            pass
        except Exception:
            pass

    logger.add(websocket_sink, level="INFO")


# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def get_dashboard(request: Request):
    return templates.TemplateResponse(request, "index.html", {})


@app.get("/api/status")
def get_status_api():
    return _get_system_status()


@app.get("/api/orders")
def get_orders_api():
    db = get_db()
    return db.query("SELECT * FROM orders ORDER BY id DESC LIMIT 50")


@app.get("/api/fills")
def get_fills_api():
    db = get_db()
    return db.query("SELECT * FROM fills ORDER BY id DESC LIMIT 50")


@app.get("/api/decisions")
def get_decisions_api():
    db = get_db()
    return db.query("SELECT * FROM decisions ORDER BY id DESC LIMIT 50")


@app.get("/api/agent_messages")
def get_agent_messages_api():
    db = get_db()
    return db.query("SELECT * FROM agent_messages ORDER BY id DESC LIMIT 50")


@app.get("/api/kill_events")
def get_kill_events_api():
    db = get_db()
    return db.query("SELECT * FROM kill_events ORDER BY id DESC LIMIT 50")


@app.post("/api/backtest/run")
def run_backtest_api(req: BacktestRequest, background_tasks: BackgroundTasks):
    data_path = Path(req.data_path)
    if not data_path.exists():
        return {"status": "error", "message": f"Candle data file not found: {req.data_path}"}
    
    background_tasks.add_task(
        run_backtest_thread,
        req.strategy,
        req.data_path,
        req.start,
        req.end
    )
    return {"status": "ok", "message": "Backtest initiated successfully"}


@app.post("/api/stop")
def trigger_stop_api():
    ks = get_kill_switch()
    ks.engage(reason="Emergency halt via Dashboard UI", source="ui")
    return {"status": "ok", "halted": True}


@app.post("/api/resume")
def trigger_resume_api():
    ks = get_kill_switch()
    ks.reset(source="ui")
    return {"status": "ok", "halted": False}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    
    # Send welcome logs
    await websocket.send_text(json.dumps({
        "type": "log",
        "source": "system",
        "text": "Connected to Godmode WebSocket stream.",
        "level": "success"
    }))
    
    # Broadcast recent audit items
    try:
        db = get_db()
        audits = db.query("SELECT * FROM audit ORDER BY id DESC LIMIT 15")
        for audit in reversed(audits):
            try:
                payload = json.loads(audit["payload_json"])
                msg = f"{audit['event_type']} - {payload.get('reason', payload)}"
                level = "warn" if "halt" in audit["event_type"] or "stop" in audit["event_type"] else "info"
                await websocket.send_text(json.dumps({
                    "type": "log",
                    "source": "audit",
                    "text": msg,
                    "level": level
                }))
            except Exception:
                pass
    except Exception:
        pass

    try:
        while True:
            # Keep socket open and listen for any client messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket)


# --- Helpers ---

def _get_system_status() -> dict:
    cfg = load_config()
    ks = get_kill_switch()
    db = get_db()

    # Query active positions from SQLite database
    positions = []
    try:
        rows = db.query("SELECT * FROM positions")
        for r in rows:
            qty_val = float(r["qty"])
            if qty_val != 0.0:
                positions.append({
                    "symbol": r["symbol"],
                    "qty": qty_val,
                    "avg_price": float(r["avg_price"]),
                    "unrealized_pnl": 0.0  # Placeholder unless mark price is updated
                })
    except Exception:
        pass

    # Fetch recent metrics & realized PnL
    equity = cfg.app.paper_starting_equity
    realized_pnl = 0.0
    try:
        run_metric = db.query_one("SELECT value FROM metrics WHERE key='final_equity' ORDER BY id DESC LIMIT 1")
        if run_metric:
            equity = float(run_metric["value"])
        
        pnl_metric = db.query_one("SELECT value FROM metrics WHERE key='realized_pnl' ORDER BY id DESC LIMIT 1")
        if pnl_metric:
            realized_pnl = float(pnl_metric["value"])
    except Exception:
        pass

    # Sum of absolute position value
    gross_exposure = 0.0
    for pos in positions:
        gross_exposure += abs(pos["qty"] * pos["avg_price"])

    # Load history points from metrics for Chart.js
    history = []
    try:
        pts = db.query("SELECT ts, value FROM metrics WHERE key='final_equity' ORDER BY id DESC LIMIT 30")
        for pt in reversed(pts):
            t_str = datetime.fromisoformat(pt["ts"]).strftime("%H:%M:%S")
            history.append({
                "time": t_str,
                "equity": float(pt["value"]),
                "exposure": 0.0 # simple default
            })
    except Exception:
        pass

    return {
        "mode": cfg.mode,
        "base_currency": cfg.app.base_currency or "USDT",
        "halted": ks.is_halted(),
        "halt_reason": ks.reason(),
        "equity": equity,
        "realized_pnl": realized_pnl,
        "gross_exposure": gross_exposure,
        "positions": positions,
        "history": history
    }
