"""MarketKnowledgeGraph — NetworkX-based causal/correlation graph.

Nodes: assets, events, entities, indicators.
Edges: CORRELATED_WITH, CAUSES, HEDGES, LEADS, LAGS.

Feeds the Sentiment Analyst with 2nd-degree queries:
"How does DXY affect BTC?" → graph traversal returns path chain.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

from godmode.core.logging import get_logger

log = get_logger("data.knowledge_graph")

try:
    import networkx as nx  # type: ignore
except ImportError:
    nx = None
    log.warning("networkx not installed — knowledge graph disabled.")


class MarketKnowledgeGraph:
    """DiGraph of market relationships for causal queries."""

    def __init__(self):
        if nx is None:
            self.graph = None
            return
        self.graph = nx.DiGraph()
        self._seed_default_graph()

    def _seed_default_graph(self) -> None:
        """Seed well-known macro relationships at init."""
        edges = [
            ("DXY", "BTC", "CORRELATED_WITH", -0.6),
            ("DXY", "GOLD", "CORRELATED_WITH", -0.7),
            ("DXY", "NIFTY", "CORRELATED_WITH", -0.4),
            ("US10Y", "DXY", "CAUSES", 0.7),
            ("FED_RATE", "US10Y", "CAUSES", 0.8),
            ("FED_RATE", "BTC", "CORRELATED_WITH", -0.5),
            ("FED_RATE", "NIFTY", "CAUSES", -0.4),
            ("BTC", "ETH", "CORRELATED_WITH", 0.85),
            ("BTC", "SOL", "CORRELATED_WITH", 0.70),
            ("ETH", "SOL", "CORRELATED_WITH", 0.65),
            ("NIFTY", "BANKNIFTY", "CORRELATED_WITH", 0.88),
            ("NIFTY", "RELIANCE", "CAUSES", 0.30),
            ("GOLD", "BTC", "CORRELATED_WITH", 0.40),
            ("OIL", "NIFTY", "CORRELATED_WITH", -0.30),
            ("USDC_DOM", "BTC", "CAUSES", 0.45),
            ("CRUDE_OIL", "INR", "CORRELATED_WITH", -0.60),
        ]
        for src, dst, rel, weight in edges:
            self.add_edge(src, dst, relation=rel, weight=weight)

    def add_node(self, node_id: str, node_type: str = "asset", metadata: Optional[Dict] = None) -> None:
        if self.graph is None:
            return
        self.graph.add_node(node_id, type=node_type, **(metadata or {}))

    def add_edge(self, src: str, dst: str, relation: str = "CORRELATED_WITH", weight: float = 0.5) -> None:
        if self.graph is None:
            return
        self.graph.add_edge(src, dst, relation=relation, weight=weight)

    def query_path(self, src: str, dst: str, max_depth: int = 3) -> Optional[List[Tuple[str, str, str, float]]]:
        """Find shortest path src → dst, return list of (node_a, node_b, relation, weight)."""
        if self.graph is None or src not in self.graph or dst not in self.graph:
            return None
        try:
            path = nx.shortest_path(self.graph, src, dst)
        except Exception:
            return None

        edges_out: List[Tuple[str, str, str, float]] = []
        for i in range(len(path) - 1):
            edge_data = self.graph.get_edge_data(path[i], path[i + 1]) or {}
            edges_out.append((path[i], path[i + 1], edge_data.get("relation", "?"), edge_data.get("weight", 0)))
        return edges_out

    def explain_path(self, src: str, dst: str) -> str:
        """Return a natural-language explanation of the causal chain."""
        path = self.query_path(src, dst)
        if not path:
            return f"No known path between {src} and {dst}."
        chain = []
        for src_n, dst_n, relation, weight in path:
            w_phrase = f"({abs(weight):.2f})" if weight else ""
            sign = "positive" if weight >= 0 else "negative"
            chain.append(f"{src_n} --[{relation} {sign} {w_phrase}]--> {dst_n}")
        return " | ".join(chain)

    def second_degree_effects(self, node: str) -> List[str]:
        """Return nodes reachable from `node` through 2 hops."""
        if self.graph is None or node not in self.graph:
            return []
        effects: List[str] = []
        for neighbor in self.graph.successors(node):
            effects.append(neighbor)
            for grandchild in self.graph.successors(neighbor):
                if grandchild not in effects and grandchild != node:
                    effects.append(grandchild)
        return effects


_kg_singleton: Optional[MarketKnowledgeGraph] = None


def get_knowledge_graph() -> MarketKnowledgeGraph:
    global _kg_singleton
    if _kg_singleton is None:
        _kg_singleton = MarketKnowledgeGraph()
    return _kg_singleton