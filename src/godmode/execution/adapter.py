"""Base interface for all execution adapters (Crypto, Equity)."""
from abc import ABC, abstractmethod
from decimal import Decimal
from typing import Optional, Dict, Any, List

class BaseBrokerAdapter(ABC):
    """Abstract Base Class for Broker execution adapters."""
    
    @abstractmethod
    def has_auth(self) -> bool:
        """Return True if API keys are configured."""
        pass
        
    @abstractmethod
    def fetch_price(self, symbol: str) -> Decimal:
        """Fetch latest price for symbol."""
        pass
        
    @abstractmethod
    def fetch_balance(self) -> dict:
        """Fetch raw portfolio balance."""
        pass
        
    @abstractmethod
    def free_balance(self, currency: str) -> Decimal:
        """Fetch free balance for a specific currency/asset."""
        pass

    @abstractmethod
    def fetch_ohlcv(self, symbol: str, timeframe: str, limit: int) -> List[List[Any]]:
        """Fetch historical OHLCV candles."""
        pass
        
    @abstractmethod
    def create_order(self, symbol: str, type: str, side: str, amount: str, params: Optional[Dict[str, Any]] = None) -> dict:
        """Place a live order."""
        pass

    @abstractmethod
    def fetch_position_qty(self, symbol: str) -> Decimal:
        """Fetch the net position quantity for a symbol."""
        pass
