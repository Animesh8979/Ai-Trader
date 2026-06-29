import pytest
from unittest.mock import MagicMock, patch
from decimal import Decimal

from godmode.agents.brain import MultiAgentBrain


def test_multi_agent_brain_decision_flow():
    # Setup mocks
    mock_client = MagicMock()
    
    # Configure mock responses for the LLM agents
    mock_client.complete_json.side_effect = [
        # 1. Technical Analyst
        {"outlook": "bullish", "indicators_summary": "RSI oversold", "support": 50000.0, "resistance": 60000.0},
        # 2. Sentiment Analyst
        {"sentiment_score": 0.8, "impact_summary": "Positive ETF inflows"},
        # 3. Trader
        {"action": "buy", "size": 0.05, "stop_loss_pct": 2.0, "take_profit_pct": 5.0, "reason": "strong bull case"},
        # 4. Risk Manager
        {"verdict": "approve", "reason": "within limits"}
    ]
    
    # Configure mock text responses for researchers
    mock_client.complete.side_effect = [
        # Bull researcher argument
        MagicMock(text="- Bull case points"),
        # Bear researcher argument
        MagicMock(text="- Bear case points")
    ]
    
    brain = MultiAgentBrain(client=mock_client)
    
    # Inputs
    symbol = "BTC/USDT"
    price_data = {"close": 55000.0}
    portfolio_state = {"timestamp": "2026-06-05T12:00:00Z", "equity": 100000.0}
    news_feed = ["Good news"]
    
    # Execute orchestrator pipeline
    proposal = brain.decide_trade(
        symbol=symbol,
        price_data=price_data,
        portfolio_state=portfolio_state,
        news_feed=news_feed
    )
    
    # Assertions
    assert proposal["action"] == "buy"
    assert proposal["size"] == 0.05
    assert proposal["reason"] == "strong bull case"
    
    # Verify exact agent flow count
    assert mock_client.complete_json.call_count == 4
    assert mock_client.complete.call_count == 2


def test_multi_agent_brain_risk_rejection():
    mock_client = MagicMock()
    
    mock_client.complete_json.side_effect = [
        # Technical
        {"outlook": "bullish", "indicators_summary": "Bullish trend", "support": 50000.0, "resistance": 60000.0},
        # Sentiment
        {"sentiment_score": 0.2, "impact_summary": "Neutral news"},
        # Trader (proposes buy)
        {"action": "buy", "size": 0.8, "stop_loss_pct": 5.0, "take_profit_pct": 10.0, "reason": "high leverage buy"},
        # Risk Manager (rejects due to excessive size)
        {"verdict": "reject", "reason": "exceeds maximum exposure limit"}
    ]
    mock_client.complete.side_effect = [
        MagicMock(text="Bull case"),
        MagicMock(text="Bear case")
    ]
    
    brain = MultiAgentBrain(client=mock_client)
    
    proposal = brain.decide_trade(
        symbol="BTC/USDT",
        price_data={"close": 55000.0},
        portfolio_state={"timestamp": "2026-06-05T12:00:00Z", "equity": 100000.0},
        news_feed=[]
    )
    
    # Assert action is overridden to hold due to risk rejection
    assert proposal["action"] == "hold"
    assert "Rejected by Risk Agent" in proposal["reason"]
