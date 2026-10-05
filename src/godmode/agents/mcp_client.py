"""Model Context Protocol (MCP) Client Wrapper.

Loads the MCP server registry and provides a unified interface for the AI agents 
to discover and invoke tools from external servers (Postgres, Memory, AlphaVantage, etc.).
"""

from __future__ import annotations

import json
import threading
import subprocess
import os
import sys
import atexit
from pathlib import Path
from typing import Any, Optional, Dict, List

from godmode.core.logging import get_logger

log = get_logger("agents.mcp_client")


def readline_with_timeout(stream, timeout: float) -> Optional[str]:
    result = [None]
    def target():
        try:
            result[0] = stream.readline()
        except Exception:
            pass
    t = threading.Thread(target=target)
    t.daemon = True
    t.start()
    t.join(timeout)
    return result[0]


class MCPRegistry:
    def __init__(self, registry_path: str = ".agents/mcp_registry.json"):
        self.registry_path = Path(registry_path)
        self.servers: dict[str, dict] = {}
        self._load()

    def _load(self) -> None:
        if not self.registry_path.exists():
            log.debug(f"MCP registry not found at {self.registry_path}")
            return

        try:
            with open(self.registry_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                self.servers = data.get("mcpServers", {})
            log.info(f"Loaded {len(self.servers)} MCP servers from registry.")
        except Exception as exc:
            log.debug(f"Failed to load MCP registry: {exc}")

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
    """Thread-safe MCP Client utilizing Thread-Local Storage (TLS) for connections.
    
    Spawns real stdio-based subprocesses on-demand and communicates via JSON-RPC 2.0.
    """
    _tls = threading.local()
    
    # Core active servers to connect at startup to keep memory/CPU low
    CORE_SERVERS = [
        "memory", "check", "network_ai", "ccxt", 
        "postgres", "financial_datasets", "verilexdata", "katzilla"
    ]

    def __init__(self, registry: Optional[MCPRegistry] = None):
        self.registry = registry or MCPRegistry()
        self._tool_to_server: Dict[str, str] = {}
        self._lock = threading.Lock()
        
        # Register atexit handler to kill child processes
        atexit.register(self.disconnect_all)

    @property
    def _active_connections(self) -> Dict[str, subprocess.Popen]:
        if not hasattr(self._tls, "connections"):
            self._tls.connections = {}
        return self._tls.connections

    def _get_process(self, name: str) -> Optional[subprocess.Popen]:
        """Get or spawn the subprocess for a given MCP server (thread-local)."""
        connections = self._active_connections
        proc = connections.get(name)
        
        # Check if process is still alive
        if proc is not None:
            if proc.poll() is None:
                return proc
            else:
                log.warning(f"MCP Server {name} process died. Restarting...")
                connections.pop(name, None)

        config = self.registry.get_server_config(name)
        if not config:
            log.warning(f"No configuration found for MCP server: {name}")
            return None

        # Sanitize command arguments
        command_args = config.get("args", [])
        sanitized_args = []
        for arg in command_args:
            # Strip @1.0.0 which causes npm target errors
            if "@1.0.0" in arg and not arg.startswith("http"):
                arg = arg.replace("@1.0.0", "")
            # Lowercase npm organization scoped packages (NPM forbids capitals)
            if arg.startswith("@") and not arg.startswith("http"):
                arg = arg.lower()
            sanitized_args.append(arg)

        command = [config["command"]] + sanitized_args
        log.info(f"Spawning MCP Server subprocess: {' '.join(command)}")

        try:
            # shell=True is mandatory on Windows to resolve command paths
            process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                shell=False,
                env=os.environ.copy()
            )

            # JSON-RPC Handshake: 1. Initialize
            init_req = {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "godmode-client", "version": "0.1.0"}
                }
            }
            process.stdin.write(json.dumps(init_req) + "\n")
            process.stdin.flush()

            # Read response (5.0s timeout to prevent hanging on slow npm installs)
            init_resp_line = readline_with_timeout(process.stdout, 5.0)
            if not init_resp_line:
                # Safe non-blocking check: only read if the process actually exited
                if process.poll() is not None:
                    err_msg = process.stderr.read()
                else:
                    err_msg = "Process is still alive or slow to respond, empty handshake."
                log.error(f"MCP Server {name} failed handshake. Stderr: {err_msg}")
                process.terminate()
                return None

            # 2. Send initialized notification
            initialized_notification = {
                "jsonrpc": "2.0",
                "method": "notifications/initialized"
            }
            process.stdin.write(json.dumps(initialized_notification) + "\n")
            process.stdin.flush()

            connections[name] = process
            return process

        except Exception as e:
            log.error(f"Failed to spawn MCP Server {name}: {e}")
            return None

    def connect_all(self) -> None:
        """Simulate or connect to all registered CORE MCP servers."""
        for name in self.CORE_SERVERS:
            if name in self.registry.list_servers():
                self._get_process(name)

    def disconnect_all(self) -> None:
        """Terminate all spawned child processes."""
        connections = getattr(self._tls, "connections", {})
        for name, proc in list(connections.items()):
            try:
                log.info(f"Terminating MCP Server subprocess: {name}")
                proc.terminate()
                proc.wait(timeout=2)
            except Exception:
                pass
        connections.clear()

    def get_available_tools(self) -> list[dict[str, Any]]:
        """Query active servers dynamically to discover available tools."""
        tools = []
        
        # Connect and query registered tools
        for name in self.registry.list_servers():
            # Only list tools for core servers to keep startup fast
            if name not in self.CORE_SERVERS:
                continue
                
            proc = self._get_process(name)
            if not proc:
                continue

            try:
                list_req = {
                    "jsonrpc": "2.0",
                    "id": 2,
                    "method": "tools/list",
                    "params": {}
                }
                proc.stdin.write(json.dumps(list_req) + "\n")
                proc.stdin.flush()

                # Read with 5.0s timeout
                resp_line = readline_with_timeout(proc.stdout, 5.0)
                if resp_line:
                    resp = json.loads(resp_line)
                    server_tools = resp.get("result", {}).get("tools", [])
                    for t in server_tools:
                        # Map tool name -> server name for routing
                        with self._lock:
                            self._tool_to_server[t["name"]] = name
                        
                        tools.append({
                            "type": "function",
                            "function": {
                                "name": t["name"],
                                "description": t.get("description", ""),
                                "parameters": t.get("inputSchema", {
                                    "type": "object",
                                    "properties": {}
                                })
                            }
                        })
            except Exception as e:
                log.debug(f"Failed to query tools from MCP Server {name}: {e}")

        # HONESTY RULE (FIX 14): if no real MCP servers connected, advertise NO
        # tools. Injecting fake tool definitions would invite the LLM to call
        # nonexistent capabilities and reason about their empty results as if
        # they were real observations. Empty list = "no tools available".
        if not tools:
            log.warning("No real MCP tools discovered; returning empty tool list.")
        
        return tools

    def call_tool(
        self,
        tool_name: str,
        arguments: dict,
        server_name: Optional[str] = None
    ) -> Any:
        """Execute a tool call against the appropriate MCP server."""
        try:
            # 1. Enforce Circuit Breaker limits for spend actions
            if tool_name == "hire_agent":
                bounty = arguments.get("bounty_usdc", 0.0)
                if not CircuitBreaker.authorize_spend(bounty):
                    return {"status": "error", "message": "Circuit breaker rejected spend: Limit exceeded."}
                return {"status": "success", "data": f"Agent hired for {bounty} USDC."}

            # 2. Determine target server
            target_server = server_name
            if not target_server:
                with self._lock:
                    target_server = self._tool_to_server.get(tool_name)

            if not target_server:
                log.warning(f"Could not resolve server for tool: {tool_name}. Executing simulated fallback.")
                return self._mock_fallback(tool_name, arguments)

            # 3. Spawn/Get subprocess
            proc = self._get_process(target_server)
            if not proc:
                log.warning(f"MCP Server {target_server} not available. Running fallback.")
                return self._mock_fallback(tool_name, arguments)

            # 4. Perform JSON-RPC tool execution
            call_req = {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {
                    "name": tool_name,
                    "arguments": arguments
                }
            }
            proc.stdin.write(json.dumps(call_req) + "\n")
            proc.stdin.flush()

            # Read with 5.0s timeout
            resp_line = readline_with_timeout(proc.stdout, 5.0)
            if not resp_line:
                log.error(f"MCP Server {target_server} returned empty stdout or timed out.")
                return self._mock_fallback(tool_name, arguments)

            resp = json.loads(resp_line)
            if "error" in resp:
                log.error(f"MCP Server {target_server} returned JSON-RPC error: {resp['error']}")
                return {"status": "error", "message": resp["error"]}

            # 5. Extract results
            content_list = resp.get("result", {}).get("content", [])
            if content_list:
                text_content = content_list[0].get("text", "")
                try:
                    # Attempt to parse parsed dict/JSON structure directly
                    return json.loads(text_content)
                except ValueError:
                    return text_content

            return resp.get("result", {})

        except Exception as e:
            log.error(f"Error executing MCP tool {tool_name}: {e}")
            return self._mock_fallback(tool_name, arguments)

    def _mock_fallback(self, tool_name: str, arguments: dict) -> Any:
        """HONEST fallback when MCP servers are offline — returns empty containers,
        NEVER fabricated data. Downstream callers must treat empties as "no signal".
        The system's conscience requires this: fabricated mock values would be
        reasoned about by the LLM as real market facts — violation of FIX 14.
        """
        log.info(f"MCP tool {tool_name} offline — returning empty (no fabricated data)")
        if tool_name == "get_whale_transfers":
            return {"transfers": []}
        if tool_name == "get_sec_filings_json":
            return {"filings": []}
        if tool_name == "query_database":
            return []
        if tool_name == "read_memory_graph":
            return {"observations": []}
        return {}

    def __del__(self) -> None:
        self.disconnect_all()
