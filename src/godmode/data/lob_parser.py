from dataclasses import dataclass
from typing import List, Tuple, Optional

@dataclass
class LOBState:
    best_bid_price: float
    best_bid_vol: float
    best_ask_price: float
    best_ask_vol: float

class LOBParser:
    def __init__(self):
        self.prev_state: Optional[LOBState] = None

    def process_snapshot(self, bids: List[Tuple[float, float]], asks: List[Tuple[float, float]]) -> dict:
        """
        Process a depth snapshot to compute Order Flow Imbalance (OFI), VWAP, etc.
        bids: list of (price, volume) sorted descending by price (best bid first)
        asks: list of (price, volume) sorted ascending by price (best ask first)
        """
        if not bids or not asks:
            return {
                'ofi': 0.0,
                'vwap': 0.0,
                'microprice': 0.0,
                'mid_price': 0.0
            }

        best_bid_price, best_bid_vol = bids[0]
        best_ask_price, best_ask_vol = asks[0]

        # Calculate OFI (Order Flow Imbalance)
        ofi = 0.0
        if self.prev_state is not None:
            # Bid side OFI (Delta W)
            if best_bid_price > self.prev_state.best_bid_price:
                delta_w = best_bid_vol
            elif best_bid_price == self.prev_state.best_bid_price:
                delta_w = best_bid_vol - self.prev_state.best_bid_vol
            else:
                delta_w = -self.prev_state.best_bid_vol
                
            # Ask side OFI (Delta V)
            if best_ask_price < self.prev_state.best_ask_price:
                delta_v = best_ask_vol
            elif best_ask_price == self.prev_state.best_ask_price:
                delta_v = best_ask_vol - self.prev_state.best_ask_vol
            else:
                delta_v = -self.prev_state.best_ask_vol
                
            ofi = delta_w - delta_v
            
        self.prev_state = LOBState(best_bid_price, best_bid_vol, best_ask_price, best_ask_vol)

        # Calculate Depth VWAP
        total_vol = sum(v for p, v in bids) + sum(v for p, v in asks)
        if total_vol > 0:
            vwap = (sum(p * v for p, v in bids) + sum(p * v for p, v in asks)) / total_vol
        else:
            vwap = 0.0

        # Microprice (volume-weighted mid-price)
        if (best_bid_vol + best_ask_vol) > 0:
            microprice = (best_bid_price * best_ask_vol + best_ask_price * best_bid_vol) / (best_bid_vol + best_ask_vol)
        else:
            microprice = (best_bid_price + best_ask_price) / 2.0

        return {
            'ofi': ofi,
            'vwap': vwap,
            'microprice': microprice,
            'mid_price': (best_bid_price + best_ask_price) / 2.0
        }

if __name__ == "__main__":
    # Quick local test
    parser = LOBParser()
    
    # Snapshot 1
    bids1 = [(100.0, 10), (99.0, 50)]
    asks1 = [(101.0, 10), (102.0, 40)]
    print("Tick 1:", parser.process_snapshot(bids1, asks1))
    
    # Snapshot 2: bid volume increases at same price (OFI should be +5)
    bids2 = [(100.0, 15), (99.0, 50)]
    asks2 = [(101.0, 10), (102.0, 40)]
    print("Tick 2:", parser.process_snapshot(bids2, asks2))
