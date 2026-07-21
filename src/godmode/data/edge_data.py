"""Edge Data Pipeline for Whales and Macro SEC data."""

import logging
from typing import Any, Dict, List, Optional
from godmode.agents.mcp_client import MCPClient

log = logging.getLogger("godmode.data.edge_data")

class EdgeDataPipeline:
    """Pipeline for integrating Whale Tracking and SEC filing data."""

    def __init__(self, mcp_client: Optional[MCPClient] = None):
        self.mcp_client = mcp_client or MCPClient()
        self.mcp_client.connect_all()

    def get_whale_movements(self, asset: str) -> List[Dict[str, Any]]:
        """
        Query verilexdata MCP server for whale movements.
        Focuses on known exchange hot wallets and tagged whale entities.
        Threshold: > $10,000,000 USD equivalent.
        Returns [] on any failure (NEVER fake data — honest failure only).
        """
        log.info(f"Fetching whale movements for {asset}...")
        try:
            result = self.mcp_client.call_tool(
                server_name="verilexdata",
                tool_name="get_whale_transfers",
                arguments={"asset": asset, "min_usd_value": 10000000, "wallet_type": "hot_or_tagged"}
            )
            return result.get("transfers", [])
        except Exception as e:
            log.warning(f"Failed to fetch whale movements (returning empty list): {e}")
            return []

    def get_sec_filings(self, ticker: str) -> List[Dict[str, Any]]:
        """
        Query katzilla MCP server for macro SEC data.
        Prioritizes 8-K and 13F filings. Extracts structured JSON payload.
        Returns [] on any failure (NEVER fake data — honest failure only).
        """
        log.info(f"Fetching SEC filings for {ticker}...")
        try:
            result = self.mcp_client.call_tool(
                server_name="katzilla",
                tool_name="get_sec_filings_json",
                arguments={"ticker": ticker, "filing_types": ["8-K", "13F"]}
            )
            return result.get("filings", [])
        except Exception as e:
            log.warning(f"Failed to fetch SEC filings (returning empty list): {e}")
            return []

    def get_macro_inflation_data(self) -> Dict[str, Any]:
        """
        Query katzilla MCP server for FRED inflation metrics.
        Returns {} on any failure (NEVER fake data — honest failure only).
        """
        try:
            result = self.mcp_client.call_tool(
                server_name="katzilla",
                tool_name="get_fred_metrics",
                arguments={"metrics": ["CPI", "PPI"]}
            )
            return result
        except Exception as e:
            log.warning(f"Failed to fetch FRED metrics (returning empty dict): {e}")
            return {}
