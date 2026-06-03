"""Integration-level tests.

Exercise the full inference pipeline (scaler → model → XAI) against the traffic
simulator. The per-attack expectations form a decision table: a given attack
profile must map to its corresponding verdict for the supervised classifier.
"""

import numpy as np
import pytest

from backend.pipeline import analyze
from backend.simulator import (
    CLASS_NAMES,
    FEATURE_NAMES,
    N_FEATURES,
    NetworkSimulator,
    sample_features,
)

pytestmark = pytest.mark.integration


def _packet_for(label, rng):
    """Build a minimal packet dict from a pure-profile feature vector."""
    vec = sample_features(label, rng)
    return {
        "src_ip": "10.0.0.1", "dst_ip": "10.0.0.2", "dst_port": 80,
        "protocol": "TCP", "true_label": label,
        "features": {n: float(vec[i]) for i, n in enumerate(FEATURE_NAMES)},
        "feature_vector": vec,
    }


# ───────────────────────── decision table: profile → verdict ─────────────────────────
@pytest.mark.parametrize("label", CLASS_NAMES)
def test_classifier_predicts_each_profile_majority(hub, label):
    rng = np.random.default_rng(7)
    preds = [analyze(hub, _packet_for(label, rng), "classifier")["prediction"] for _ in range(60)]
    correct = sum(p == label for p in preds)
    # Profiles overlap slightly by design; require a clear majority.
    assert correct / len(preds) >= 0.7, f"{label}: only {correct}/60 correct"


# ───────────────────────── output contract ─────────────────────────
def test_classifier_output_contract(hub):
    rng = np.random.default_rng(3)
    res = analyze(hub, _packet_for("DDoS", rng), "classifier")
    assert res["prediction"] in CLASS_NAMES
    assert 0.0 <= res["confidence"] <= 1.0
    assert len(res["feature_contributions"]) == N_FEATURES
    assert abs(sum(res["probabilities"].values()) - 1.0) < 1e-3
    # contributions are a normalised attribution -> sum ≈ 1
    assert abs(sum(f["contribution"] for f in res["feature_contributions"]) - 1.0) < 1e-2


def test_autoencoder_output_contract(hub):
    rng = np.random.default_rng(4)
    res = analyze(hub, _packet_for("Normal", rng), "autoencoder")
    assert res["prediction"] in ("Normal", "Anomaly")
    assert res["probabilities"] is None
    assert res["anomaly_score"] >= 0.0


# ───────────────────────── anomaly score ordering ─────────────────────────
def test_attacks_have_higher_anomaly_score_than_normal(hub):
    rng = np.random.default_rng(11)
    normal = np.mean([analyze(hub, _packet_for("Normal", rng), "autoencoder")["anomaly_score"] for _ in range(40)])
    ddos = np.mean([analyze(hub, _packet_for("DDoS", rng), "autoencoder")["anomaly_score"] for _ in range(40)])
    assert ddos > normal


def test_simulator_mode_switch_changes_traffic(hub):
    sim = NetworkSimulator(seed=5)
    sim.set_mode("BruteForce")
    # over a window, brute-force should dominate the true labels
    labels = [sim.next_packet()["true_label"] for _ in range(60)]
    assert labels.count("BruteForce") > labels.count("Normal")


def test_invalid_mode_raises():
    sim = NetworkSimulator()
    with pytest.raises(ValueError):
        sim.set_mode("Phishing")
