"""Indian Equity Adapter (Phase 3) built on Shoonya (Finvasia).

This adapter wraps the Shoonya (NorenRestApiPy) SDK to provide zero-brokerage
algorithmic trading on the Indian Stock Exchanges (NSE/BSE).
"""
import os
import time
import datetime
from decimal import Decimal
from typing import Optional, Dict, Any, List

from godmode.core.config import Config, load_config
from godmode.core.logging import get_logger
from godmode.core.money import D
from godmode.core.killswitch import get_kill_switch
from godmode.execution.adapter import BaseBrokerAdapter

log = get_logger("execution.indian_equity")

class ShoonyaConnectivityError(RuntimeError):
    pass

class ShoonyaAdapter(BaseBrokerAdapter):
    def __init__(self, venue: str = "shoonya", config: Optional[Config] = None):
        self.venue = venue
        self.config = config or load_config()
        self._api = None
        self._token_cache: Dict[tuple[str, str], str] = {}

    def _resolve_token(self, exchange: str, symbol: str) -> str:
        """Resolves a trading symbol like 'RELIANCE-EQ' to its numeric token ID."""
        cache_key = (exchange, symbol)
        if cache_key in self._token_cache:
            return self._token_cache[cache_key]
            
        log.info(f"Resolving Shoonya token for {exchange}:{symbol}...")
        try:
            res = self.api.searchscrip(exchange=exchange, searchtext=symbol)
        except Exception as exc:
            raise ShoonyaConnectivityError(f"Error calling searchscrip for {symbol}: {exc}")
            
        if not res or res.get('stat') != 'Ok' or 'values' not in res:
            base_symbol = symbol.split("-")[0]
            log.info(f"Exact search failed. Retrying search with base symbol: {base_symbol}...")
            try:
                res = self.api.searchscrip(exchange=exchange, searchtext=base_symbol)
            except Exception as exc:
                raise ShoonyaConnectivityError(f"Error calling searchscrip for {base_symbol}: {exc}")
                
        if res and res.get('stat') == 'Ok' and 'values' in res:
            for val in res['values']:
                if val.get('tsym') == symbol:
                    token = val.get('token')
                    if token:
                        self._token_cache[cache_key] = token
                        log.info(f"Resolved {exchange}:{symbol} to token {token}")
                        return token
            if res['values']:
                token = res['values'][0].get('token')
                if token:
                    self._token_cache[cache_key] = token
                    log.warning(f"No exact match for {symbol}. Falling back to first match: {res['values'][0].get('tsym')} (token: {token})")
                    return token
                    
        raise ShoonyaConnectivityError(f"Could not resolve Shoonya token for {exchange}:{symbol}. API response: {res}")

    def _maybe_creds(self) -> Optional[Dict[str, str]]:
        uid = os.environ.get("SHOONYA_USER_ID")
        pwd = os.environ.get("SHOONYA_PASSWORD")
        totp_secret = os.environ.get("SHOONYA_TOTP_SECRET")
        vendor_code = os.environ.get("SHOONYA_VENDOR_CODE")
        api_secret = os.environ.get("SHOONYA_API_SECRET")
        imei = os.environ.get("SHOONYA_IMEI", "abc1234")
        
        if all([uid, pwd, totp_secret, vendor_code, api_secret]):
            return {
                "uid": uid,
                "pwd": pwd,
                "totp": totp_secret,
                "vendor_code": vendor_code,
                "api_secret": api_secret,
                "imei": imei
            }
        return None

    def has_auth(self) -> bool:
        return self._maybe_creds() is not None

    def _require_auth(self) -> None:
        if not self.has_auth():
            raise ShoonyaConnectivityError(
                "Shoonya keys are missing. Please export SHOONYA_USER_ID, SHOONYA_PASSWORD, SHOONYA_TOTP_SECRET, SHOONYA_VENDOR_CODE, SHOONYA_API_SECRET."
            )

    @property
    def api(self):
        if self._api is None:
            self._api = self._build()
        return self._api

    def _build(self):
        try:
            from NorenRestApiPy.NorenApi import NorenApi
            import pyotp
        except ImportError:
            raise ShoonyaConnectivityError("NorenRestApiPy or pyotp is not installed. Run `pip install NorenRestApiPy pyotp`.")
            
        creds = self._maybe_creds()
        self._require_auth()
        
        class ShoonyaApi(NorenApi):
            def __init__(self):
                NorenApi.__init__(self, host="https://api.shoonya.com/NorenWClientTP/", websocket="wss://api.shoonya.com/NorenWSTP/")
                
        api = ShoonyaApi()
        
        # Generate TOTP
        totp = pyotp.TOTP(creds["totp"]).now()
        
        ret = api.login(
            userid=creds["uid"],
            password=creds["pwd"],
            twoFA=totp,
            vendor_code=creds["vendor_code"],
            api_secret=creds["api_secret"],
            imei=creds["imei"]
        )
        if ret is None or ret.get('stat') != 'Ok':
            raise ShoonyaConnectivityError(f"Shoonya login failed: {ret}")
            
        return api

    def fetch_price(self, symbol: str) -> Decimal:
        exchange, trading_symbol = self._split_symbol(symbol)
        token = self._resolve_token(exchange, trading_symbol)
        quote = self.api.get_quotes(exchange=exchange, token=token)
        if not quote or quote.get('stat') != 'Ok':
            raise ShoonyaConnectivityError(f"Failed to fetch price for {symbol}: {quote}")
        return D(str(quote.get('lp', '0')))

    def fetch_balance(self) -> dict:
        limits = self.api.get_limits()
        if not limits or limits.get('stat') != 'Ok':
            raise ShoonyaConnectivityError(f"Failed to fetch limits: {limits}")
        return limits

    def free_balance(self, currency: str = "INR") -> Decimal:
        bal = self.fetch_balance()
        # Shoonya returns cash available in 'cash' or 'marginused' etc.
        cash = bal.get("cash", "0")
        return D(str(cash))

    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> List[List[Any]]:
        """Maps CCXT format timeframe to Shoonya format and returns OHLCV array."""
        exchange, trading_symbol = self._split_symbol(symbol)
        token = self._resolve_token(exchange, trading_symbol)
        
        # Default map timeframe '1m' -> '1', '15m' -> '15'
        shoonya_tf = timeframe.replace("m", "")
        
        end_time = datetime.datetime.now().timestamp()
        # Roughly calculate start time to get enough candles
        start_time = end_time - (int(shoonya_tf) * 60 * limit * 2) 
        
        res = self.api.get_time_price_series(
            exchange=exchange, 
            token=token, 
            starttime=str(int(start_time)),
            endtime=str(int(end_time)),
            interval=shoonya_tf
        )
        
        if not res or not isinstance(res, list):
            raise ShoonyaConnectivityError(f"Failed to fetch historical data for {symbol}: {res}")
            
        candles = []
        # Shoonya returns dicts: stat, time, into, inth, intl, intc, v, intvwap
        # CCXT expects: [timestamp, open, high, low, close, volume]
        for row in reversed(res[:limit]):
            dt = datetime.datetime.strptime(row['time'], "%d-%m-%Y %H:%M:%S")
            ts = dt.timestamp() * 1000
            candles.append([
                ts,
                float(row['into']),
                float(row['inth']),
                float(row['intl']),
                float(row['intc']),
                float(row.get('v', 0))
            ])
        return candles

    def create_order(self, symbol: str, type: str, side: str, amount: str, params: Optional[Dict[str, Any]] = None) -> dict:
        ks = get_kill_switch()
        if ks.is_halted():
            raise RuntimeError(f"Order rejected: KillSwitch is engaged ({ks.reason()})")
        exchange, trading_symbol = self._split_symbol(symbol)
        
        # map 'buy' -> 'B', 'sell' -> 'S'
        bs_side = 'B' if side.lower() == 'buy' else 'S'
        
        # map 'market' -> 'MKT', 'limit' -> 'LMT'
        ord_type = 'MKT' if type.lower() == 'market' else 'LMT'
        
        price = params.get("price", 0) if params else 0
        
        ret = self.api.place_order(
            buy_or_sell=bs_side,
            product_type='C', # Cash & Carry by default, CNC
            exchange=exchange,
            tradingsymbol=trading_symbol,
            quantity=int(float(amount)),
            discloseqty=0,
            price_type=ord_type,
            price=price,
            trigger_price=None,
            retention='DAY',
            remarks=params.get("clientOrderId", "godmode") if params else "godmode"
        )
        if not ret or ret.get('stat') != 'Ok':
            raise ShoonyaConnectivityError(f"Failed to place order: {ret}")
            
        return ret

    def _split_symbol(self, symbol: str) -> tuple:
        """Splits 'NSE:RELIANCE-EQ' into ('NSE', 'RELIANCE-EQ').

        HONEST CONTRACT: callers MUST pass a venue-prefixed symbol ('NSE:...',
        'BSE:...', 'MCX:...'). Symbols without a venue prefix are rejected —
        defaulting to 'NSE' would silently route BSE orders to the wrong exchange
        (a FIX 14 violation — the system must NOT guess at execution time).
        """
        parts = symbol.split(":")
        if len(parts) == 2 and parts[0].strip().upper() in ("NSE", "BSE", "MCX", "CDS", "NFO"):
            return parts[0].strip().upper(), parts[1]
        raise ShoonyaConnectivityError(
            f"Symbol {symbol!r} must be venue-prefixed (e.g. 'NSE:RELIANCE-EQ', "
            f"'BSE:RELIANCE-EQ'). Missing venue prefix would risk routing to the "
            f"wrong exchange — refusing to guess."
        )

    def fetch_position_qty(self, symbol: str) -> Decimal:
        exchange, trading_symbol = self._split_symbol(symbol)
        positions = self.api.get_positions()
        if not positions or not isinstance(positions, list):
            return D("0")
        for pos in positions:
            if pos.get('tsym') == trading_symbol and pos.get('exch') == exchange:
                netqty = pos.get('netqty', '0')
                return D(str(netqty))
        return D("0")
