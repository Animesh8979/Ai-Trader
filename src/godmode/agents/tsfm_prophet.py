"""ChronosProphet v2 — Time-series forecasting with optional HF Chronos-2 model.

Default path: pure-Python GBM (zero-dep, CPU, instant).
Optional path: loads HuggingFace `amazon/chronos-bolt-mini` via the official
`chronos-forecasting` package and calls `predict_quantiles(...)` for P10/P50/P90.

Set CHRONOS_USE_HF=1 (and `pip install chronos-forecasting torch`) to enable.
"""

from __future__ import annotations

import math
import os
from typing import Any, Dict, List, Optional

from godmode.core.logging import get_logger

log = get_logger("agents.tsfm_prophet")


class ChronosProphetV2:
    """Probabilistic forecaster with HF Chronos-Bolt fallback to GBM."""

    def __init__(
        self,
        forecast_steps: int = 5,
        use_hf_model: Optional[bool] = None,
        hf_model_id: str = "amazon/chronos-bolt-mini",
    ):
        self.forecast_steps = forecast_steps
        self.hf_model_id = hf_model_id
        self._hf_pipeline = None
        if use_hf_model is None:
            use_hf_model = os.environ.get("CHRONOS_USE_HF", "0") == "1"
        if use_hf_model:
            self._try_load_hf_model()

    def _try_load_hf_model(self) -> None:
        try:
            # HONEST API: chronos-forecasting ships the actual Chronos pipelines
            from chronos import BaseChronosPipeline  # type: ignore

            log.info(f"[ChronosProphet] Loading {self.hf_model_id} via chronos-forecasting...")
            self._hf_pipeline = BaseChronosPipeline.from_pretrained(
                self.hf_model_id,
                device_map="cpu",
                torch_dtype="auto",
            )
            log.info(f"[ChronosProphet] {self.hf_model_id} loaded successfully.")
        except Exception as exc:
            log.warning(
                f"[ChronosProphet] HF load failed ({exc}). "
                "Need `pip install chronos-forecasting torch`. Falling back to GBM."
            )
            self._hf_pipeline = None

    def predict_distribution(self, prices: List[float]) -> Dict[str, float]:
        """Return P10, P50, P90 forecast + uncertainty spread."""
        if len(prices) < 5:
            last = prices[-1] if prices else 0.0
            return {"p10": last, "p50": last, "p90": last,
                    "uncertainty": 0.0, "source": "default"}

        if self._hf_pipeline is not None:
            try:
                return self._predict_hf(prices)
            except Exception as exc:
                log.warning(f"[ChronosProphet] HF inference failed, fallback to GBM: {exc}")

        return self._predict_gbm(prices)

    def _predict_hf(self, prices: List[float]) -> Dict[str, float]:
        # HONEST CHRONOS-2/BOLT API: pipeline.predict_quantiles returns
        # (quantiles, mean). Quantiles tensor shape is (batch, n_quantiles, horizon).
        import torch  # type: ignore

        context = torch.tensor(prices[-512:], dtype=torch.float32)
        quantiles, mean = self._hf_pipeline.predict_quantiles(
            context.unsqueeze(0),
            prediction_length=self.forecast_steps,
            quantile_levels=[0.1, 0.5, 0.9],
        )
        # quantiles shape: (1, 3, horizon). Take the last horizon step.
        q_1d = quantiles[0]  # (3, horizon)
        p10 = float(q_1d[0, -1].item())
        p50 = float(q_1d[1, -1].item())
        p90 = float(q_1d[2, -1].item())
        uncertainty = (p90 - p10) / max(p50, 1e-9)
        log.info(
            f"[ChronosProphet V2 HF] last={prices[-1]:.2f} p10={p10:.2f} "
            f"p50={p50:.2f} p90={p90:.2f} model={self.hf_model_id}"
        )
        return {
            "p10": round(p10, 4), "p50": round(p50, 4), "p90": round(p90, 4),
            "uncertainty": round(uncertainty, 4),
            "source": "hf_" + self.hf_model_id.replace("/", "_"),
        }

    def _predict_gbm(self, prices: List[float]) -> Dict[str, float]:
        last_price = prices[-1]
        log_returns: List[float] = []
        for i in range(1, len(prices)):
            if prices[i - 1] > 0 and prices[i] > 0:
                log_returns.append(math.log(prices[i] / prices[i - 1]))
        if not log_returns:
            return {"p10": last_price, "p50": last_price, "p90": last_price,
                    "uncertainty": 0.0, "source": "gbm"}

        n = len(log_returns)
        mean_return = sum(log_returns) / n
        variance = sum((r - mean_return) ** 2 for r in log_returns) / max(1, n - 1)
        volatility = math.sqrt(variance)

        t = self.forecast_steps
        drift_adj = mean_return * t
        vol_adj = volatility * math.sqrt(t)
        p50 = last_price * math.exp(drift_adj)
        p90 = last_price * math.exp(drift_adj + 1.28 * vol_adj)
        p10 = last_price * math.exp(drift_adj - 1.28 * vol_adj)
        uncertainty = (p90 - p10) / max(p50, 1e-9)

        log.info(
            f"[ChronosProphet V2 GBM] last={last_price:.2f} "
            f"p10={p10:.2f} p50={p50:.2f} p90={p90:.2f}"
        )
        return {
            "p10": round(p10, 4), "p50": round(p50, 4), "p90": round(p90, 4),
            "uncertainty": round(uncertainty, 4), "source": "gbm",
        }


_chronos_v2_singleton: Optional[ChronosProphetV2] = None


def get_chronos_prophet() -> ChronosProphetV2:
    global _chronos_v2_singleton
    if _chronos_v2_singleton is None:
        _chronos_v2_singleton = ChronosProphetV2()
    return _chronos_v2_singleton