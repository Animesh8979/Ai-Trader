#!/usr/bin/env python3
"""
Unit Test Suite for smart-thinking skill (test_skill.py)
Validates all 19 cognitive modes, CLI flags, JSON output, and edge case resilience.
Pure Python standard library (unittest).
"""

import os
import sys
import json
import tempfile
import unittest
import subprocess
from pathlib import Path

# Add scripts directory to path
SCRIPTS_DIR = Path(__file__).resolve().parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from smart_thinking_engine import SmartThinkingEngine, ModeResult


class TestSmartThinkingEngine(unittest.TestCase):
    def setUp(self):
        self.engine = SmartThinkingEngine()
        self.test_problem = "Eliminate file lock contention in concurrent background workers"

    def test_all_19_modes_exist(self):
        self.assertEqual(len(self.engine.MODES), 19)
        for i in range(1, 20):
            self.assertIn(i, self.engine.MODES)
            name, focus = self.engine.MODES[i]
            self.assertTrue(isinstance(name, str) and len(name) > 0)
            self.assertTrue(isinstance(focus, str) and len(focus) > 0)

    def test_run_mode_1_lateral(self):
        res = self.engine.run_mode(1, self.test_problem)
        self.assertEqual(res.mode_id, 1)
        self.assertEqual(res.mode_name, "Lateral Thinking")
        self.assertIn("orthogonal_inversions", res.analysis)
        self.assertTrue(len(res.actionable_verdict) > 0)

    def test_run_mode_2_systems(self):
        res = self.engine.run_mode(2, self.test_problem)
        self.assertEqual(res.mode_id, 2)
        self.assertEqual(res.mode_name, "Systems Thinking")
        self.assertIn("feedback_loops", res.analysis)
        self.assertIn("cascade_risk_score", res.analysis)

    def test_run_mode_3_dialectical(self):
        res = self.engine.run_mode(3, self.test_problem)
        self.assertEqual(res.mode_id, 3)
        self.assertEqual(res.mode_name, "Dialectical Thinking")
        self.assertIn("thesis", res.analysis)
        self.assertIn("antithesis", res.analysis)
        self.assertIn("synthesis", res.analysis)

    def test_run_mode_4_first_principles(self):
        res = self.engine.run_mode(4, self.test_problem)
        self.assertEqual(res.mode_id, 4)
        self.assertEqual(res.mode_name, "First-Principles")
        self.assertIn("physical_invariants", res.analysis)
        self.assertIn("cultural_dogmas", res.analysis)

    def test_run_mode_5_metacognitive(self):
        res = self.engine.run_mode(5, self.test_problem)
        self.assertEqual(res.mode_id, 5)
        self.assertEqual(res.mode_name, "Metacognitive")
        self.assertIn("detected_biases", res.analysis)
        self.assertIn("root_cause_vs_symptom", res.analysis)

    def test_run_mode_6_inversion(self):
        res = self.engine.run_mode(6, self.test_problem)
        self.assertEqual(res.mode_id, 6)
        self.assertEqual(res.mode_name, "Inversion (Jacobi)")
        self.assertIn("failure_guarantees", res.analysis)
        self.assertIn("inversion_prescriptions", res.analysis)

    def test_run_mode_7_pre_mortem(self):
        res = self.engine.run_mode(7, self.test_problem)
        self.assertEqual(res.mode_id, 7)
        self.assertEqual(res.mode_name, "Pre-Mortem Analysis")
        self.assertIn("probable_root_causes", res.analysis)

    def test_run_mode_8_critical_falsification(self):
        res = self.engine.run_mode(8, self.test_problem)
        self.assertEqual(res.mode_id, 8)
        self.assertEqual(res.mode_name, "Critical Falsification")
        self.assertIn("popperian_falsification_tests", res.analysis)

    def test_run_mode_9_divergent_ideation(self):
        res = self.engine.run_mode(9, self.test_problem)
        self.assertEqual(res.mode_id, 9)
        self.assertEqual(res.mode_name, "Divergent Ideation")
        self.assertTrue(len(res.analysis["candidates"]) >= 4)

    def test_run_mode_10_convergent_pruning(self):
        res = self.engine.run_mode(10, self.test_problem)
        self.assertEqual(res.mode_id, 10)
        self.assertEqual(res.mode_name, "Convergent Pruning")
        self.assertIn("evaluations", res.analysis)

    def test_run_mode_11_bayesian_updating(self):
        ctx = {"prior": 0.4, "likelihood_ratio": 9.0}
        res = self.engine.run_mode(11, self.test_problem, ctx)
        self.assertEqual(res.mode_id, 11)
        self.assertEqual(res.mode_name, "Bayesian Updating")
        self.assertEqual(res.analysis["prior_probability"], 0.4)
        # Prior odds = 0.4 / 0.6 = 0.6667; Post odds = 0.6667 * 9 = 6.0; Post prob = 6 / 7 = 0.8571
        self.assertAlmostEqual(res.analysis["posterior_probability"], 0.8571, places=3)

    def test_run_mode_12_triz_contradiction(self):
        res = self.engine.run_mode(12, self.test_problem)
        self.assertEqual(res.mode_id, 12)
        self.assertEqual(res.mode_name, "TRIZ Contradiction")
        self.assertIn("triz_principles_applied", res.analysis)

    def test_run_mode_13_analogical_mapping(self):
        res = self.engine.run_mode(13, self.test_problem)
        self.assertEqual(res.mode_id, 13)
        self.assertEqual(res.mode_name, "Analogical Mapping")
        self.assertIn("source_domain", res.analysis)

    def test_run_mode_14_adversarial_red_team(self):
        res = self.engine.run_mode(14, self.test_problem)
        self.assertEqual(res.mode_id, 14)
        self.assertEqual(res.mode_name, "Adversarial Red Team")
        self.assertIn("attack_vectors", res.analysis)

    def test_run_mode_15_fermi_slicing(self):
        ctx = {"items": 50000, "item_size_bytes": 512}
        res = self.engine.run_mode(15, self.test_problem, ctx)
        self.assertEqual(res.mode_id, 15)
        self.assertEqual(res.mode_name, "Fermi / Slicing")
        expected_mb = (50000 * 512) / (1024 * 1024)
        self.assertAlmostEqual(res.analysis["baseline_ram_mb"], round(expected_mb, 2))

    def test_run_mode_16_morphological_matrix(self):
        res = self.engine.run_mode(16, self.test_problem)
        self.assertEqual(res.mode_id, 16)
        self.assertEqual(res.mode_name, "Morphological Matrix")
        self.assertIn("parameters", res.analysis)
        self.assertIn("optimal_combination", res.analysis)

    def test_run_mode_17_ooda_loop(self):
        res = self.engine.run_mode(17, self.test_problem)
        self.assertEqual(res.mode_id, 17)
        self.assertEqual(res.mode_name, "OODA Loop")
        self.assertIn("observe", res.analysis)
        self.assertIn("act", res.analysis)

    def test_run_mode_18_counterfactual(self):
        res = self.engine.run_mode(18, self.test_problem)
        self.assertEqual(res.mode_id, 18)
        self.assertEqual(res.mode_name, "Counterfactual")
        self.assertIn("counterfactual_scenario", res.analysis)

    def test_run_mode_19_minimalist_razor(self):
        res = self.engine.run_mode(19, self.test_problem)
        self.assertEqual(res.mode_id, 19)
        self.assertEqual(res.mode_name, "Minimalist Razor")
        self.assertIn("decision_ladder_eval", res.analysis)
        self.assertEqual(len(res.analysis["decision_ladder_eval"]), 7)

    def test_run_all(self):
        results = self.engine.run_all(self.test_problem)
        self.assertEqual(len(results), 19)
        for i, res in enumerate(results, 1):
            self.assertEqual(res.mode_id, i)

    def test_invalid_mode_raises(self):
        with self.assertRaises(ValueError):
            self.engine.run_mode(0, self.test_problem)
        with self.assertRaises(ValueError):
            self.engine.run_mode(20, self.test_problem)

    def test_cli_execution_mode(self):
        engine_script = SCRIPTS_DIR / "smart_thinking_engine.py"
        cmd = [sys.executable, str(engine_script), "--mode", "3", "--problem", "Cache invalidation race", "--json"]
        proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
        data = json.loads(proc.stdout)
        self.assertEqual(data["mode_id"], 3)
        self.assertEqual(data["mode_name"], "Dialectical Thinking")

    def test_cli_execution_run_all_and_output(self):
        engine_script = SCRIPTS_DIR / "smart_thinking_engine.py"
        with tempfile.TemporaryDirectory() as tmpdir:
            out_file = Path(tmpdir) / "output.json"
            cmd = [sys.executable, str(engine_script), "--run-all", "--json", "--output", str(out_file)]
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)
            self.assertTrue(out_file.exists())
            data = json.loads(out_file.read_text(encoding="utf-8"))
            self.assertEqual(len(data), 19)

    def test_unicode_and_special_characters(self):
        unicode_problem = "解决系统死锁: High throughput Ω=2πf, λ-calculus, \u26a0 file lock trap"
        res = self.engine.run_mode(1, unicode_problem)
        self.assertIn(unicode_problem, res.analysis["apparent_constraint"])


if __name__ == "__main__":
    unittest.main()
