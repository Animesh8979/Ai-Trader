"""Model Context Protocol (MCP) Client Wrapper.

Loads the MCP server registry and provides a unified interface for the AI agents 
to discover and invoke tools from external servers (Postgres, Memory, AlphaVantage, etc.).
"""

from __future__ import annotations

import json
import threading
from pathlib import Path
from typing import Any, Optional

from godmode.core.logging import get_logger

log = get_logger("agents.mcp_client")


class MCPRegistry:
    def __init__(self, registry_path: str = ".agents/mcp_registry.json"):
        self.registry_path = Path(registry_path)
        self.servers: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.registry_path.exists():
            log.warning(f"MCP registry not found at {self.registry_path}")
            return

        try:
            with open(self.registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.servers = data.get("mcpServers", {})
            log.info(f"Loaded {len(self.servers)} MCP servers from registry.")
        except Exception as exc:
            log.error(f"Failed to load MCP registry: {exc}")

    def get_server_config(self, name: str) -> Optional[dict]:
        return self.servers.get(name)

    def list_servers(self) -> list[str]:
        return list(self.servers.keys())


class CircuitBreaker:
    """Hard-coded limits for API spending to prevent LLM hallucination drains."""
    MAX_DAILY_USDC = 10.0
    _current_spend = 0.0
    _lock = threading.Lock()

    @classmethod
    def authorize_spend(cls, amount: float) -> bool:
        with cls._lock:
            if cls._current_spend + amount > cls.MAX_DAILY_USDC:
                log.error(f"CIRCUIT BREAKER TRIGGERED: Attempted to spend {amount} USDC. Daily limit {cls.MAX_DAILY_USDC} reached.")
                return False
            cls._current_spend += amount
            return True


class MCPClient:
    """Thread-safe MCP Client utilizing Thread-Local Storage (TLS) for connections."""
    _tls = threading.local()

    def __init__(self, registry: Optional[MCPRegistry] = None):
        self.registry = registry or MCPRegistry()

    @property
    def _active_connections(self):
        if not hasattr(self._tls, "connections"):
            self._tls.connections = {}
            self.connect_all() # Lazy-init for worker threads
        return self._tls.connections

    def connect_all(self):
        """Simulate connecting to all registered MCP servers. (Thread-safe)"""
        for name, config in self.registry.servers.items():
            if not hasattr(self._tls, "connections"):
                self._tls.connections = {}
            if name not in self._tls.connections:
                log.info(f"Connecting to MCP Server (Thread {threading.get_ident()}): {name}")
                self._tls.connections[name] = "connected"

    def get_available_tools(self) -> list[dict[str, Any]]:
        """Returns a list of tools formatted for LLM function calling."""
        tools = []
        if "postgres" in self._active_connections:
            tools.append({
                "type": "function",
                "function": {
                    "name": "query_database",
                    "description": "Run read-only SQL queries against the internal Godmode PostgreSQL database (fills, orders).",
                    "parameters": {
                        "type": "object",
                        "properties": {"query": {"type": "string"}},
                        "required": ["query"]
                    }
                }
            })
        if "memory" in self._active_connections:
            tools.append({
                "type": "function",
                "function": {
                    "name": "read_memory_graph",
                    "description": "Query the persistent memory knowledge graph for past trading rules and mistakes.",
                    "parameters": {
                        "type": "object",
                        "properties": {"topic": {"type": "string"}},
                        "required": ["topic"]
                    }
                }
            })
        if "alphavantage" in self._active_connections:
             tools.append({
                "type": "function",
                "function": {
                    "name": "get_macro_economic_data",
                    "description": "Fetch real-time macro economic indicators from AlphaVantage.",
                    "parameters": {
                        "type": "object",
                        "properties": {"indicator": {"type": "string"}},
                        "required": ["indicator"]
                    }
                }
            })
        if "network_ai" in self._active_connections:
            tools.append({
                "type": "function",
                "function": {
                    "name": "write_blackboard",
                    "description": "Post arguments to the shared Network-AI blackboard.",
                    "parameters": {
                        "type": "object",
                        "properties": {"data": {"type": "string"}},
                        "required": ["data"]
                    }
                }
            })
        if "octodamus" in self._active_connections:
            tools.append({
                "type": "function",
                "function": {
                    "name": "get_oracle_consensus",
                    "description": "Get the 11-signal BUY/SELL/HOLD consensus for crypto.",
                    "parameters": {
                        "type": "object",
                        "properties": {"symbol": {"type": "string"}},
                        "required": ["symbol"]
                    }
                }
            })
        if "swarmwage" in self._active_connections:
            tools.append({
                "type": "function",
                "function": {
                    "name": "hire_agent",
                    "description": "Hire an external agent via Swarmwage.",
                    "parameters": {
                        "type": "object",
                        "properties": {"task": {"type": "string"}, "bounty_usdc": {"type": "number"}},
                        "required": ["task", "bounty_usdc"]
                    }
                }
            })
        return tools

    def call_tool(self, tool_name: str, arguments: dict) -> str:
        """Simulate executing an MCP tool, with hard-coded interceptors."""
        # Trigger lazy initialization of TLS connections for this thread
        _ = self._active_connections
        
        log.info(f"Executing MCP Tool: {tool_name} with args {arguments} on Thread {threading.get_ident()}")
        
        # Hard-coded interceptor for financial drain flaw
        if tool_name == "hire_agent":
            bounty = arguments.get("bounty_usdc", 0.0)
            if not CircuitBreaker.authorize_spend(bounty):
                return json.dumps({"status": "error", "message": "Circuit breaker rejected spend: Limit exceeded."})
            return json.dumps({"status": "success", "data": f"Agent hired for {bounty} USDC."})

        if tool_name == "query_database":
            return json.dumps({"status": "success", "data": [{"result": "Mock data from Postgres MCP"}]})
        elif tool_name == "read_memory_graph":
            return json.dumps({"status": "success", "data": "Mock memory: Always enforce strict stop-loss in bear markets."})
        elif tool_name == "get_macro_economic_data":
            return json.dumps({"status": "success", "data": {"inflation": "3.1%", "rates": "5.25%"}})
        elif tool_name == "write_blackboard":
            return json.dumps({"status": "success", "data": "Written to shared blackboard."})
        elif tool_name == "get_oracle_consensus":
            return json.dumps({"status": "success", "data": "Consensus: BUY (9/11 confluence)"})
        else:
            return json.dumps({"status": "error", "message": f"Tool {tool_name} not found or server disconnected."})
