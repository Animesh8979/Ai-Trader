# Learning Journal

## [2026-07-07] Upgrading simulated MCP client to Stdio JSON-RPC client

*   **Task**: Implement a zero-dependency, thread-safe Model Context Protocol (MCP) client using subprocess stdout/stdin pipes.
*   **What Went Wrong**:
    1.  **NPM Target Errors**: NPM failed to download packages that used pinned versions (`@1.0.0`) in the registry JSON file.
    2.  **Capital Letter Errors**: NPM rejected scoped package names with capital letters (e.g. `@Nayshins/mcp-server-ccxt`).
    3.  **Readline Hanging**: `process.stdout.readline()` blocked indefinitely on slow npm installations, causing the agent threads to freeze.
    4.  **Stdout EOF Handling**: `process.stderr.read()` blocked forever if the subprocess ended but the parent cmd shell was still running.
    5.  **Signature Mismatch**: In-code `call_tool` was called with `server_name` keyword arguments by data pipelines, which didn't match the mock signature and caused silent TypeErrors.
*   **What the Fix Was**:
    1.  **Command Sanitization**: Automatically strip `@1.0.0` version strings and convert scoped `@` package names to lowercase inside `mcp_client.py`.
    2.  **Threaded Timeout Stream**: Implemented a zero-dependency `readline_with_timeout` helper using python daemon threads to enforce a 5.0-second timeout on pipe reads.
    3.  **Safe Non-blocking Stderr Checks**: Only read stderr if `process.poll()` confirms the child shell process has exited.
    4.  **Aligned call_tool signature**: Updated `call_tool` to accept optional `server_name` and parse JSON return strings into dicts/lists directly.

## [2026-07-12] Dual-Screen Institutional Terminal & Adversarial Swarm Remediation

*   **Task**: Implement dual-screen Bloomberg/Cyberpunk UI for Indian (NSE/BSE) vs International (Crypto/Macro) markets, integrate free LLM routing, and fix 7 architectural/mathematical flaws discovered by agent swarm.
*   **What Went Wrong**:
    1.  **Chronos Variance Math**: Discrete log return sample mean already includes Ito drift; subtracting `0.5 * variance` double-subtracted drift.
    2.  **Realized PnL Recording**: Fills recorded `"0.0"` hardcoded PnL, blinding Reflection self-calibration and daily loss circuit breakers.
    3.  **Reducing Order Sizing**: Closing/reducing orders with fixed `0.05` size could accidentally flip net position.
*   **What the Fix Was**:
    1.  **Corrected Log-Return Drift**: Fixed `ChronosProphetAgent` drift to `mean_return * t`.
    2.  **Exact FIFO/LIFO Realized PnL**: Added `db.get_position` and exact `realized_pnl` computation on closing fills.
    3.  **Clamped Reducing Orders**: Clamped reducing order quantity to `min(0.05, abs(position_qty))`.
    4.  **Free-Tier LLM Router**: Created `godmode.llm.free_router` supporting OpenRouter Free Models, Groq Free Tier, and Gemini Free Tier with zero-crash fallback.
