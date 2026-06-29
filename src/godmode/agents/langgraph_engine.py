import logging
from typing import Dict, Any, Optional
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END

logger = logging.getLogger(__name__)

# 1. Define the strictly typed State
class TradingState(TypedDict):
    asset: str
    action: str  # 'BUY' or 'SELL'
    quantity: float
    current_price: float
    risk_approved: bool
    qa_approved: bool # NEW: Adversarial QA Flag
    human_approved: bool
    execution_result: Optional[str]

# 2. Node: Analyze Market
def analyze_market(state: TradingState) -> Dict[str, Any]:
    logger.info(f"NODE [1]: Analyzing market for {state['asset']}")
    return {"current_price": 45000.0}

# 3. Node: Validate Risk (Math check)
def validate_risk(state: TradingState) -> Dict[str, Any]:
    logger.info(f"NODE [2]: Validating mathematical risk limits for {state['action']} {state['quantity']} {state['asset']}")
    is_safe = state['quantity'] * state['current_price'] < 100000.0 
    return {"risk_approved": is_safe}

# 4. Node: Hostile Adversarial QA (Logic check)
def adversarial_qa(state: TradingState) -> Dict[str, Any]:
    logger.info("NODE [3]: Initiating Hostile Red-Team Critique.")
    # Here, you would call a secondary LLM with strict instructions to try and DISPROVE the trade thesis.
    # We simulate a deterministic pass here. If this fails, the graph halts before the human ever sees it.
    simulated_llm_eval = True
    if simulated_llm_eval:
        logger.info("QA PASSED: The trade thesis survived the adversarial attack.")
    else:
        logger.warning("QA FAILED: Flaws detected in the logic. Halting execution.")
    
    return {"qa_approved": simulated_llm_eval}

# 5. Node: Human Checkpoint (Interrupt)
def human_approval(state: TradingState) -> Dict[str, Any]:
    logger.info("NODE [4]: Human has explicitly approved this trade.")
    return {"human_approved": True}

# 6. Node: Execute Trade
def execute_trade(state: TradingState) -> Dict[str, Any]:
    logger.info(f"NODE [5]: EXECUTING LIVE TRADE -> {state['action']} {state['quantity']} {state['asset']}")
    return {"execution_result": "ORDER_FILLED"}

# Conditional Edge Router
def should_execute(state: TradingState) -> str:
    if not state.get("risk_approved"):
        logger.warning("ROUTING: Risk validation failed mathematically. Halting graph.")
        return END
    
    if not state.get("qa_approved"):
        logger.warning("ROUTING: Adversarial QA failed the logical check. Halting graph.")
        return END
    
    # Route to human approval ONLY if math and logic both survive.
    return "human_approval"

# 7. Build the Deterministic Graph
def build_trading_graph():
    workflow = StateGraph(TradingState)

    workflow.add_node("analyze_market", analyze_market)
    workflow.add_node("validate_risk", validate_risk)
    workflow.add_node("adversarial_qa", adversarial_qa)
    workflow.add_node("human_approval", human_approval)
    workflow.add_node("execute_trade", execute_trade)

    workflow.add_edge(START, "analyze_market")
    workflow.add_edge("analyze_market", "validate_risk")
    workflow.add_edge("validate_risk", "adversarial_qa")
    
    workflow.add_conditional_edges(
        "adversarial_qa",
        should_execute,
        {
            "human_approval": "human_approval",
            END: END
        }
    )
    
    workflow.add_edge("human_approval", "execute_trade")
    workflow.add_edge("execute_trade", END)

    from langgraph.checkpoint.memory import MemorySaver
    memory = MemorySaver()
    
    app = workflow.compile(
        checkpointer=memory,
        interrupt_before=["human_approval"]
    )
    return app

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    graph = build_trading_graph()
    
    config = {"configurable": {"thread_id": "trade-session-002"}}
    initial_state = {
        "asset": "ETH/USD",
        "action": "BUY",
        "quantity": 2.0,
        "current_price": 0.0,
        "risk_approved": False,
        "qa_approved": False,
        "human_approved": False,
        "execution_result": None
    }
    
    print("\n--- INITIATING ADVERSARIAL WORKFLOW ---")
    for event in graph.stream(initial_state, config):
        for k, v in event.items():
            print(f"Executed Node: {k}")
            
    state_snapshot = graph.get_state(config)
    if state_snapshot.next:
        print("\n[!] WORKFLOW FROZEN: Both Math & Logic Passed. Human Checkpoint Triggered.")
        print(f"Pending Node: {state_snapshot.next[0]}")
