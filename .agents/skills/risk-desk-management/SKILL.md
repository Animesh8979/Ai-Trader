---
name: "Risk Desk Management"
description: "Manages leverage, exposure, drawdowns, and the system killswitch."
---
# Risk Desk Management Skill

This skill governs risk circuit breakers, limits calculation, and the emergency killswitch interface.

## Risk Desk Rules
1. **Hard Drawdown Cap**: If equity falls below $5\%$ of starting peak, immediately halt all execution:
   `get_kill_switch().engage(reason="drawdown exceeded")`
2. **Exposure Limits**: Check gross exposure against configuration parameters before accepting trade proposals.
3. **Consecutive Losses**: Keep track of consecutive losing fills. Stop trading if the streak reaches $3$.
