"""Unit-level tests (white-box + black-box).

Demonstrates classic test-design techniques:
  * Boundary Value Analysis (BVA) on the min-max scaler
  * Equivalence Partitioning (EP) on the traffic-profile generator
  * Structural checks on the network architectures
"""

import numpy as np
import pytest
import torch

from backend.model import Autoencoder, DNNClassifier
from backend.simulator import (
    CLASS_NAMES,
    FEATURE_NAMES,
    N_CLASSES,
    N_FEATURES,
    sample_features,
)
from backend.trainer import ModelHub, build_dataset

pytestmark = pytest.mark.unit


# ───────────────────────── model architecture ─────────────────────────
def test_autoencoder_reconstructs_input_shape():
    ae = Autoencoder(N_FEATURES)
    out = ae(torch.randn(8, N_FEATURES))
    assert out.shape == (8, N_FEATURES)


def test_classifier_emits_one_logit_per_class():
    clf = DNNClassifier(N_FEATURES, N_CLASSES)
    out = clf(torch.randn(8, N_FEATURES))
    assert out.shape == (8, N_CLASSES)


def test_classifier_handles_single_sample_in_eval_mode():
    # BVA: batch size = 1 is the lower boundary; BatchNorm must use running stats.
    clf = DNNClassifier(N_FEATURES, N_CLASSES).eval()
    out = clf(torch.randn(1, N_FEATURES))
    assert out.shape == (1, N_CLASSES)


# ───────────────────────── scaler: boundary value analysis ─────────────────────────
@pytest.fixture
def scaler():
    h = ModelHub()
    h.scaler_min = np.zeros(N_FEATURES, dtype=np.float32)
    h.scaler_max = np.full(N_FEATURES, 10.0, dtype=np.float32)
    return h


@pytest.mark.parametrize(
    "raw_value, expected",
    [
        (0.0, 0.0),    # exact lower boundary
        (10.0, 1.0),   # exact upper boundary
        (5.0, 0.5),    # nominal mid-range
        (-3.0, 0.0),   # below range -> clipped (invalid partition)
        (13.0, 1.0),   # above range -> clipped (invalid partition)
    ],
)
def test_transform_boundaries(scaler, raw_value, expected):
    x = np.full((1, N_FEATURES), raw_value, dtype=np.float32)
    scaled = scaler.transform(x)
    assert np.allclose(scaled, expected, atol=1e-6)
    assert scaled.min() >= 0.0 and scaled.max() <= 1.0


# ───────────────────────── profiles: equivalence partitioning ─────────────────────────
def _mean_feature(label, feature, n=400):
    rng = np.random.default_rng(0)
    idx = FEATURE_NAMES.index(feature)
    return np.mean([sample_features(label, rng)[idx] for _ in range(n)])


def test_all_features_are_non_negative():
    rng = np.random.default_rng(1)
    for label in CLASS_NAMES:
        for _ in range(50):
            assert (sample_features(label, rng) >= 0).all()


def test_normal_traffic_has_no_failed_logins():
    assert _mean_feature("Normal", "num_failed_logins") == pytest.approx(0.0, abs=1e-6)


def test_bruteforce_is_defined_by_failed_logins():
    # EP: the brute-force partition is characterised by many failed logins.
    assert _mean_feature("BruteForce", "num_failed_logins") > 3.0


def test_ddos_is_defined_by_high_connection_volume():
    assert _mean_feature("DDoS", "count") > 150.0


def test_portscan_is_defined_by_host_spreading():
    assert _mean_feature("PortScan", "srv_diff_host_rate") > 0.6


# ───────────────────────── dataset ─────────────────────────
def test_build_dataset_is_balanced_and_shaped():
    X, y = build_dataset(n_per_class=40)
    assert X.shape == (160, N_FEATURES)
    counts = np.bincount(y, minlength=N_CLASSES)
    assert (counts == 40).all()
