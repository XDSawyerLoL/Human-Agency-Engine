from __future__ import annotations

# Compatibility shim: the public import path stays stable while World Eye v2
# performs geography-aware duplicate fusion and diversified scenario selection.
from .evidence_scenario_fusion_v2 import EvidenceScenarioFusion

__all__ = ["EvidenceScenarioFusion"]
