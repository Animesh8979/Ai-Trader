"""Lightweight crypto connectivity adapter (Phase 0) built on ccxt.

This is NOT the production execution engine — that arrives in Phase 1 (NautilusTrader).
Its job is to prove, end-to-end, that the user's TESTNET keys work: connect, read live
prices, read the (fake) balance, and place + immediately cancel a tiny non-marketable
order. Everything here runs against exchange *testnets* (fake money, real prices).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

from godmode.core.config import Config, load_config
from godmode.core.logging import get_logger
from godmode.core.money import D

log = get_logger("execution.crypto")

# venue name -> ccxt exchange id
SUPPORTED_VENUES = {
    "binance_testnet": "binance",
    "bybit_testnet": "bybit",
}


class CryptoConnectivityError(RuntimeError):
    pass


@dataclass
class VenueCreds:
    api_key: str
    api_secret: str


class CryptoCcxtAdapter:
    def __init__(self, venue: str, config: Optional[Config] = None):
        if venue not in SUPPORTED_VENUES:
            raise CryptoConnectivityError(
                f"Unsupported crypto venue '{venue}'. Supported: {list(SUPPORTED_VENUES)}"
            )
        self.venue = venue
        self.config = config or load_config()
        self._exchange = None

    # -- credentials ------------------------------------------------------ #
    def _maybe_creds(self) -> Optional[VenueCreds]:
        """Return creds if present, else None (so public data works keyless)."""
        s = self.config.secrets
        if self.venue == "binance_testnet" and s.has_binance_testnet():
            return VenueCreds(s.binance_testnet_api_key, s.binance_testnet_api_secret)
        if self.venue == "bybit_testnet" and s.has_bybit_testnet():
            return VenueCreds(s.bybit_testnet_api_key, s.bybit_testnet_api_secret)
        return None

    def has_auth(self) -> bool:
        return self._maybe_creds() is not None

    def _require_auth(self) -> None:
        if not self.has_auth():
            raise CryptoConnectivityError(
                f"{self.venue} keys are missing. Run `godmode setup` to add them."
            )

    # -- exchange handle -------------------------------------------------- #
    @property
    def exchange(self):
        if self._exchange is None:
            self._exchange = self._build()
        return self._exchange

    def _build(self):
        try:
            import ccxt
        except Exception as exc:  # noqa: BLE001
            raise CryptoConnectivityError(f"ccxt is not installed: {exc}")

        config: dict = {"enableRateLimit": True, "options": {"defaultType": "spot"}}
        creds = self._maybe_creds()
        if creds:  # public endpoints (price, markets) work without keys
            config["apiKey"] = creds.api_key
            config["secret"] = creds.api_secret

        klass = getattr(ccxt, SUPPORTED_VENUES[self.venue])
        ex = klass(config)
        ex.set_sandbox_mode(True)  # route to the testnet endpoints
        return ex

    # -- read ------------------------------------------------------------- #
    def load_markets(self) -> dict:
        return self.exchange.load_markets()

    def fetch_price(self, symbol: str) -> Decimal:
        ticker = self.exchange.fetch_ticker(symbol)
        last = ticker.get("last") or ticker.get("close") or ticker.get("bid")
        if last is None:
            raise CryptoConnectivityError(f"No price returned for {symbol}")
        return D(str(last))

    def fetch_balance(self) -> dict:
        self._require_auth()
        return self.exchange.fetch_balance()

    def free_balance(self, currency: str) -> Decimal:
        bal = self.fetch_balance()
        free = (bal.get("free") or {}).get(currency)
        return D(str(free)) if free is not None else D("0")

    # -- write (probe only) ---------------------------------------------- #
    def place_and_cancel_probe(self, symbol: str, min_notional: Decimal = D("12")) -> dict:
        """Place a tiny non-marketable limit BUY (10% below market) then cancel it.

        Proves order placement + cancellation work without any real fill risk.
        """
        self._require_auth()
        self.exchange.load_markets()
        price = self.fetch_price(symbol)
        limit_price = price * D("0.90")  # 10% below market -> rests on the book, won't fill
        qty = min_notional / limit_price

        amount_str = self.exchange.amount_to_precision(symbol, float(qty))
        price_str = self.exchange.price_to_precision(symbol, float(limit_price))
        client_order_id = "gm-" + uuid.uuid4().hex[:16]

        order = self.exchange.create_order(
            symbol,
            "limit",
            "buy",
            float(amount_str),
            float(price_str),
            {"clientOrderId": client_order_id},
        )
        order_id = order.get("id")
        self.exchange.cancel_order(order_id, symbol)
        return {
            "client_order_id": client_order_id,
            "order_id": order_id,
            "symbol": symbol,
            "limit_price": price_str,
            "amount": amount_str,
            "canceled": True,
        }
