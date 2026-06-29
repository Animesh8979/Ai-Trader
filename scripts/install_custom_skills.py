import os
from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parent.parent
SKILLS_DIR = BASE_DIR / ".agents" / "skills"

SKILLS = {
    # -------------------------------------------------------------------------
    # GSD CORE WORKFLOW SKILLS
    # -------------------------------------------------------------------------
    "gsd-discuss": {
        "name": "GSD Discuss",
        "description": "Guides the discuss phase of Get Shit Done (GSD) workflow to align on requirements and trade-offs.",
        "content": """# GSD Discuss Skill

This skill governs the initial phase of the Get Shit Done workflow. The goal is to establish shared alignment, collect requirements, identify system boundaries, and surface any design constraints before writing code or plans.

## Workflow Protocol
1. **Clarify Intent**: Restate the user's request in first-principles terms. Identify what visual, mathematical, or operational parameters are requested.
2. **Surface Constraints**: Call out system limits, dependencies, API limits (e.g. Binance weight caps, Nvidia rate limits), and target configurations.
3. **Verify Pre-conditions**: Inspect current codebase configurations (e.g. SQLite schema, environment variables) to establish the baseline state.
4. **Identify Trade-offs**: Discuss architectural trade-offs (e.g., synchronous thread blocking vs asynchronous loop scheduling).
"""
    },
    "gsd-plan": {
        "name": "GSD Plan",
        "description": "Guides the plan phase of GSD workflow to write implementation plans and task lists.",
        "content": """# GSD Plan Skill

This skill governs the planning phase of the Get Shit Done workflow. It transforms alignment from the discuss phase into a concrete, spec-driven blueprint before any modifying code changes are applied.

## Planning Protocol
1. **Define Goals**: Clearly explain the target outcome and what is considered a verified success.
2. **Draft task.md**: Lay out a checkable task checklist (using `- [ ]` format) mapping items to component levels.
3. **Draft implementation_plan.md**: Group changes logically by components. Order dependencies first. Use `[MODIFY]`, `[NEW]`, and `[DELETE]` tags next to file paths.
4. **Write Verification Plan**: Define explicit automated commands (`pytest`) and manual verification steps (UI validations) to test the implementation.
"""
    },
    "gsd-execute": {
        "name": "GSD Execute",
        "description": "Guides the execute phase of GSD workflow to apply changes cleanly without stubs.",
        "content": """# GSD Execute Skill

This skill governs the execution phase of the Get Shit Done workflow. It enforces clean, production-ready coding practices, structural hygiene, and zero-slop edits.

## Execution Rules
1. **Zero Placeholder Code**: Never emit code containing `// TODO` or `pass` placeholders. All code blocks must be fully implemented, compilable, and production-ready.
2. **Incremental Edits**: Apply code changes incrementally using exact replace chunk tools (`replace_file_content` or `multi_replace_file_content`).
3. **Preserve Context**: Maintain all original comments, docstrings, and headers unless explicitly requested to alter them.
4. **Clean Workspaces**: Ensure all temporary scratch files are isolated in the conversation scratch directories, leaving the main repo root clean.
"""
    },
    "gsd-verify": {
        "name": "GSD Verify",
        "description": "Guides the verify phase of GSD workflow to execute test suites and verify outputs.",
        "content": """# GSD Verify Skill

This skill governs the verification phase of the Get Shit Done workflow. It guarantees all implemented changes have the desired effects and do not introduce regressions.

## Verification Protocol
1. **Automated Unit Tests**: Execute the full pytest suite using the project virtual environment launcher:
   `poetry run pytest` or `.venv\\Scripts\\pytest.exe`
2. **Sandbox Execution**: Run local sandbox test harnesses (e.g., `python scripts/sandbox_test.py`) to confirm execution loops finish without hanging or memory leaks.
3. **Log Audit**: Check SQLite decisions and metrics database tables to confirm transactions are logged correctly.
"""
    },
    "gsd-context-hygiene": {
        "name": "GSD Context Hygiene",
        "description": "Manages and preserves agent context size by cleaning chat threads and session state.",
        "content": """# GSD Context Hygiene Skill

This skill helps maintain clean agent context windows to prevent performance degradation ("context rot") as conversations grow.

## Hygiene Rules
1. **Isolate Tasks**: Spawn lightweight, specialized subagents for distinct research or debugging tasks using `invoke_subagent`.
2. **Clean Output**: Limit command log outputs (e.g., git log, test tracebacks) using paging flags (e.g. `git log -n 5` or `pytest -q`).
3. **Volatile Storage**: Avoid reading large database dumps or binaries directly. Query them with specific limits or grep filters.
"""
    },
    "gsd-worktree-isolation": {
        "name": "GSD Worktree Isolation",
        "description": "Manages Git worktree operations to isolate development tasks and maintain clean checkouts.",
        "content": """# GSD Worktree Isolation Skill

This skill governs the use of Git worktrees to isolate concurrent tasks, prevent merge conflicts, and preserve main checkout integrity.

## Worktree Guidelines
1. **Creation**: Mount fresh worktrees for new branches inside sandbox folders using:
   `git worktree add <path> <branch>`
2. **Execution**: Perform all modifying compiles and tests within the worktree boundaries.
3. **Cleanup**: Remove the worktree mount and prune state after shipping changes:
   `git worktree remove <path>` and `git worktree prune`
"""
    },
    "gsd-git-ship": {
        "name": "GSD Git Ship",
        "description": "Automates committing, pushing, and merging code changes safely using Git.",
        "content": """# GSD Git Ship Skill

This skill governs the Git commit and push pipeline to ensure clean, reviewable, and version-controlled history.

## shipping Protocol
1. **Inspect Status**: Check modified files using `git status` and `git diff` before adding changes.
2. **Structured Commits**: Commit changes using explicit conventional commits format (e.g. `feat(dashboard): ...` or `fix(risk): ...`).
3. **Push & Track**: Push to origin remote and track build states or test actions.
"""
    },
    "gsd-spec-writing": {
        "name": "GSD Spec Writing",
        "description": "Guides the generation of architectural, API, and workflow specifications.",
        "content": """# GSD Spec Writing Skill

This skill governs the authoring of technical specifications, architecture records, and API blueprints.

## Spec Guidelines
1. **Structured Layout**: Organize documents using standard headers (Context, Design, Alternatives, Security, Verification).
2. **State Specifications**: Define precise data structures, Pydantic models, or SQLite schemas.
3. **Mathematical Precision**: Use LaTeX delimiters for all quantitative trading models.
"""
    },
    "gsd-debug-loop": {
        "name": "GSD Debug Loop",
        "description": "Defines a repeatable, step-by-step loop for debugging software issues.",
        "content": """# GSD Debug Loop Skill

This skill outlines a rigorous debugging protocol to find root causes rather than applying temporary patches.

## Debugging Loop
1. **Gather Evidence**: List all observed facts, logs, and stack trace lines.
2. **Formulate Hypotheses**: Generate potential root causes and rank them by probability.
3. **Isolate & Test**: Write targeted mock scripts or test cases to attempt falsification of hypotheses.
4. **Verify Fix**: Apply the correction and rerun verification tests.
"""
    },
    "gsd-quality-audit": {
        "name": "GSD Quality Audit",
        "description": "Guides code reviews to identify concurrency leaks, security risks, and error handlers.",
        "content": """# GSD Quality Audit Skill

This skill governs codebase audits to enforce safety, security, and concurrency hygiene.

## Audit Checklist
1. **Concurrency**: Verify thread pools (ThreadPoolExecutor) do not cause deadlock or leak file descriptors.
2. **Error Handling**: Ensure try-catch loops in async event loops do not swallow exceptions silently.
3. **Secrets Isolation**: Confirm API credentials (Binance/Finnhub keys) are never logged or hardcoded.
"""
    },

    # -------------------------------------------------------------------------
    # QUANT TRADING & DEVELOPER CORE SKILLS
    # -------------------------------------------------------------------------
    "quant-indicators-calculation": {
        "name": "Quant Indicators Calculation",
        "description": "Calculates technical analysis indicators (VWAP, Bollinger Bands, EMA) programmatically using Pandas.",
        "content": """# Quant Indicators Calculation Skill

This skill governs programmatic calculation of market metrics using Pandas, eliminating LLM arithmetic hallucinations.

## Key Calculations
1. **VWAP (Volume Weighted Average Price)**:
   $$\\text{VWAP} = \\frac{\\sum (\\text{Price} \\times \\text{Volume})}{\\sum \\text{Volume}}$$
2. **Bollinger Bands**:
   $$\\text{Middle Band} = \\text{SMA}(N)$$
   $$\\text{Upper Band} = \\text{Middle Band} + k \\times \\sigma$$
   $$\\text{Lower Band} = \\text{Middle Band} - k \\times \\sigma$$
3. **Pivot Points**:
   $$P = \\frac{H + L + C}{3}, \\quad R_1 = 2P - L, \\quad S_1 = 2P - H$$
"""
    },
    "risk-desk-management": {
        "name": "Risk Desk Management",
        "description": "Manages leverage, exposure, drawdowns, and the system killswitch.",
        "content": """# Risk Desk Management Skill

This skill governs risk circuit breakers, limits calculation, and the emergency killswitch interface.

## Risk Desk Rules
1. **Hard Drawdown Cap**: If equity falls below $5\\%$ of starting peak, immediately halt all execution:
   `get_kill_switch().engage(reason="drawdown exceeded")`
2. **Exposure Limits**: Check gross exposure against configuration parameters before accepting trade proposals.
3. **Consecutive Losses**: Keep track of consecutive losing fills. Stop trading if the streak reaches $3$.
"""
    },
    "backtest-metrics-reporting": {
        "name": "Backtest Metrics Reporting",
        "description": "Compiles, parses, and formats NautilusTrader backtest results.",
        "content": """# Backtest Metrics Reporting Skill

This skill governs the parsing and compiling of backtest logs, Sharpe/Sortino ratios, and execution stats.

## Core Metrics
- **Sharpe Ratio**: Annualized return divided by annualized volatility.
- **Sortino Ratio**: Annualized return divided by downside deviation.
- **Win Rate**: Ratio of winning fills to total executed fills.
- **Max Drawdown**: Peak-to-trough decline percentage during the backtest window.
"""
    },
    "multi-timeframe-correlation": {
        "name": "Multi-Timeframe Correlation",
        "description": "Aligns market signals and news sentiment across multiple timeframes (1m, 15m, 1h).",
        "content": """# Multi-Timeframe Correlation Skill

This skill governs multi-timeframe fetching and signal correlation inside the live runner loops.

## Correlation Protocol
1. **Concurrent Fetching**: Query OHLCV candles for multiple granularities (e.g. `1m` and `15m`) concurrently via `asyncio.gather`.
2. **Trend Alignment**: Match micro-timeframe breakout signals against macro-timeframe moving averages.
3. **Sentiment Integration**: Weight news sentiment higher if macro trend shows matching direction.
"""
    },
    "binance-venue-onboarding": {
        "name": "Binance Venue Onboarding",
        "description": "Safely configures and onboard API keys for Binance Testnet/Mainnet.",
        "content": """# Binance Venue Onboarding Skill

This skill governs the integration of Binance Testnet or Mainnet credentials without exposure risk.

## Onboarding Security
1. **API Key Isolation**: Write API key pairs to `.env` variables (`BINANCE_API_KEY` and `BINANCE_API_SECRET`).
2. **Testnet Safeguard**: Ensure Mainnet key sets are inactive during paper/test runs. Use Binance Testnet base URLs.
3. **Connection Verification**: Run connection check queries to verify API latency and credentials validity.
"""
    },
    "parallel-agent-debate": {
        "name": "Parallel Agent Debate",
        "description": "Orchestrates multi-agent debates concurrently using thread pools to optimize latency.",
        "content": """# Parallel Agent Debate Skill

This skill governs the concurrent dispatch of LLM prompts for debate agents to minimize trading loop latency.

## Orchestration Guidelines
1. **Thread Isolation**: Dispatch non-dependent agent prompts (e.g. Bullish Researcher and Bearish Researcher) inside a `ThreadPoolExecutor` block.
2. **Latency Budget**: Limit LLM response timeouts to 15 seconds to prevent execution loop delays.
3. **Consensus Aggregation**: Combine debate logs into a single structured payload for the Trader and Risk agents.
"""
    },
    "db-schema-migrations": {
        "name": "DB Schema Migrations",
        "description": "Creates, checks, and migrates SQLite schemas for orders, fills, and decisions.",
        "content": """# DB Schema Migrations Skill

This skill governs schema management for the local SQLite database (`data/godmode.db`).

## Migration Steps
1. **Backup**: Copy the active SQLite db file before executing schema upgrades.
2. **Structured Tables**: Define tables for `orders`, `fills`, `decisions`, `agent_messages`, and `kill_events` with explicit types and indexes.
3. **Idempotence**: Write migration scripts containing `IF NOT EXISTS` flags to prevent execution crashes.
"""
    },
    "websocket-reconnect-handling": {
        "name": "WebSocket Reconnect Handling",
        "description": "Manages frontend WebSocket streams, reconnect intervals, and connection overlays.",
        "content": """# WebSocket Reconnect Handling Skill

This skill governs WebSocket streaming connection states on the dashboard frontend.

## State Logic
1. **Network Latency**: Measure client-to-server latency using HTTP header timestamps.
2. **Reconnection HUD**: Display a fullscreen severed connection warning if the socket closes.
3. **Reconnect Backoff**: Attempt reconnection every 5 seconds, restoring status telemetry upon open.
"""
    },
    "sentiment-news-hose": {
        "name": "Sentiment News Hose",
        "description": "Streams real-time crypto headlines from APIs with fallback strategies.",
        "content": """# Sentiment News Hose Skill

This skill governs news stream pipelines and real-time sentiment extraction.

## News Hose Protocol
1. **API Credentials**: Check for Finnhub or Alpaca news API keys in env variables.
2. **Graceful Fallback**: If keys are missing, automatically fall back to simulated/mock news streams to prevent trading bot crashes.
3. **Debate Stream**: Inject news headlines into the Sentiment Agent to inform trading debates.
"""
    },
    "onboarding-healthcheck": {
        "name": "Onboarding Healthcheck",
        "description": "Runs setup wizards, smoke tests, and environment diagnostics.",
        "content": """# Onboarding Healthcheck Skill

This skill governs system onboarding, credentials validation, and sandbox smoke test execution.

## Healthcheck Steps
1. **Setup Wizard**: Run `python scripts/setup_wizard.py` to configure folders, `.env`, and config paths.
2. **Smoke Test**: Run `python scripts/smoke_test.py` to verify API links, SQLite records, and model availability.
3. **Diagnostics Report**: Query active configuration parameters and print summary tables.
"""
    },

    # -------------------------------------------------------------------------
    # 10 MCP SERVERS INTEGRATION SPEC
    # -------------------------------------------------------------------------
    "mcp-servers-integration": {
        "name": "MCP Servers Integration",
        "description": "Guide for configuring and calling 10 MCP servers (GitHub, SQLite, Docker, Puppeteer, PostgreSQL, etc.).",
        "content": """# MCP Servers Integration Skill

This skill defines instructions for integrating, configuring, and invoking 10 distinct Model Context Protocol (MCP) servers to extend agent capabilities.

## Supported MCP Servers
1. **GitHub MCP**: Query repos, open pull requests, and audit code version histories.
2. **SQLite MCP**: Run SQL statements and inspect schema metrics on local databases.
3. **Docker MCP**: Manage local containers, check container statuses, and inspect image layers.
4. **Puppeteer MCP**: Render dynamic JavaScript websites, take screenshots, and extract text.
5. **PostgreSQL MCP**: Connect to and query enterprise PostgreSQL database instances.
6. **Brave-Search MCP**: Execute public web search queries and retrieve direct snippet lists.
7. **Google-Maps MCP**: Query coordinates, calculate travel routes, and inspect places metadata.
8. **Memory MCP**: Maintain semantic memory records across conversation boundaries.
9. **Fetch MCP**: Request raw HTML or JSON content from public REST APIs.
10. **File MCP**: Read and write files securely on local filesystem volumes.
"""
    },

    # -------------------------------------------------------------------------
    # 10 CUSTOM TERMINAL TOOLS SPEC
    # -------------------------------------------------------------------------
    "terminal-tools-suite": {
        "name": "Terminal Tools Suite",
        "description": "Guide for executing 10 custom CLI tools (agent-brain.ps1, run.bat, setup.ps1, etc.) inside the workspace.",
        "content": """# Terminal Tools Suite Skill

This skill acts as a command guide for executing the 10 custom developer tools in this workspace.

## Core CLI Tools
1. **run.bat**: CMD.exe launcher. Defaults to web dashboard when double-clicked.
2. **run.ps1**: PowerShell launcher. Forwards CLI arguments to the godmode CLI.
3. **setup.ps1**: PowerShell setup wizard. Installs virtual environments and configs.
4. **agent-brain.ps1**: Compiles, updates, and queries the project knowledge graph.
5. **sandbox_test.py**: Runs a simulated end-to-end paper trading loop.
6. **smoke_test.py**: Connectivity test validating model endpoints and API access.
7. **setup_wizard.py**: Interactive setup CLI configuring .env and config.yaml files.
8. **diagnostics.py**: Prints detailed reports on active environment settings.
9. **app.py**: Launches the FastAPI web server hosting dashboard templates.
10. **live_runner.py**: Executes the main autonomous multi-agent NautilusTrader loop.
"""
    }
}

def install():
    print("Initializing Custom Skills Installer...")
    
    # Create skills directory if not exist
    SKILLS_DIR.mkdir(parents=True, exist_ok=True)
    
    installed_count = 0
    for folder_name, data in SKILLS.items():
        skill_path = SKILLS_DIR / folder_name
        skill_path.mkdir(exist_ok=True)
        
        skill_file = skill_path / "SKILL.md"
        
        # Use a triple-quoted f-string. This is safe inside Python.
        full_content = f'''---
name: "{data['name']}"
description: "{data['description']}"
---
{data['content']}'''
        
        with open(skill_file, "w", encoding="utf-8") as f:
            f.write(full_content)
        
        print(f" -> Installed skill: {data['name']} at {skill_file.relative_to(BASE_DIR)}")
        installed_count += 1
        
    print(f"Success! {installed_count} custom skills installed successfully.")

if __name__ == "__main__":
    install()
