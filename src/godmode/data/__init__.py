"""Market data, news, and sentiment providers.

A thin provider interface so desks can pull prices/candles and (later) news and
sentiment from free sources first, paid sources optionally. Phase 0 uses ccxt for
crypto market data.
"""
