"""Real-time network traffic simulator.

This module is the *single source of truth* for the feature schema used across
the whole project. Both the training engine (``trainer.py``) and the live
inference pipeline (``pipeline.py``) import the canonical feature/class names
and the per-profile sampling logic from here, so the synthetic training data and
the live demo traffic are always perfectly aligned.

Four traffic profiles are modelled, each with a distinctive statistical
signature so the deep-learning model has something real to learn and the
Explainable-AI panel has something meaningful to show:

    Normal      - ordinary low-volume web/DNS browsing
    DDoS        - huge connection volume hammering a single target
    PortScan    - one source probing many hosts/ports (a "probe" attack)
    BruteForce  - repeated failed logins against one service
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Dict, List

import numpy as np

# --------------------------------------------------------------------------- #
# Canonical schema (NSL-KDD inspired, trimmed to the most demonstrative cols)  #
# --------------------------------------------------------------------------- #
FEATURE_NAMES: List[str] = [
    "duration",                     # connection length (s)
    "src_bytes",                    # bytes sent by the source
    "dst_bytes",                    # bytes returned by the destination
    "count",                        # connections to the same host (recent)
    "srv_count",                    # connections to the same service (recent)
    "dst_host_count",               # distinct destination hosts touched
    "srv_diff_host_rate",           # % of conns spread across different hosts
    "num_failed_logins",            # failed authentication attempts
    "same_srv_rate",               # % of conns to the same service
    "dst_host_same_src_port_rate",  # % of conns reusing the same source port
]

# Human-friendly labels for the dashboard.
FEATURE_LABELS: Dict[str, str] = {
    "duration": "Duration",
    "src_bytes": "Src Bytes",
    "dst_bytes": "Dst Bytes",
    "count": "Conn Count",
    "srv_count": "Service Count",
    "dst_host_count": "Dst Hosts",
    "srv_diff_host_rate": "Diff-Host Rate",
    "num_failed_logins": "Failed Logins",
    "same_srv_rate": "Same-Srv Rate",
    "dst_host_same_src_port_rate": "Same-Port Rate",
}

CLASS_NAMES: List[str] = ["Normal", "DDoS", "PortScan", "BruteForce"]
CLASS_INDEX: Dict[str, int] = {name: i for i, name in enumerate(CLASS_NAMES)}
N_FEATURES = len(FEATURE_NAMES)
N_CLASSES = len(CLASS_NAMES)

# Per-profile sampling ranges. Each entry is (low, high) for a uniform draw;
# gaussian jitter is added on top so the classes overlap a little (realistic,
# and it keeps the model honest rather than letting it memorise hard edges).
_PROFILES: Dict[str, Dict[str, tuple]] = {
    "Normal": {
        "duration": (0.0, 6.0),
        "src_bytes": (180, 3200),
        "dst_bytes": (200, 9000),
        "count": (1, 9),
        "srv_count": (1, 9),
        "dst_host_count": (1, 35),
        "srv_diff_host_rate": (0.0, 0.2),
        "num_failed_logins": (0, 0),
        "same_srv_rate": (0.7, 1.0),
        "dst_host_same_src_port_rate": (0.0, 0.3),
    },
    "DDoS": {
        "duration": (0.0, 1.0),
        "src_bytes": (0, 120),
        "dst_bytes": (0, 40),
        "count": (200, 511),
        "srv_count": (200, 511),
        "dst_host_count": (240, 255),
        "srv_diff_host_rate": (0.0, 0.1),
        "num_failed_logins": (0, 0),
        "same_srv_rate": (0.9, 1.0),
        "dst_host_same_src_port_rate": (0.85, 1.0),
    },
    "PortScan": {
        "duration": (0.0, 1.0),
        "src_bytes": (0, 60),
        "dst_bytes": (0, 60),
        "count": (8, 120),
        "srv_count": (1, 6),
        "dst_host_count": (200, 255),
        "srv_diff_host_rate": (0.7, 1.0),
        "num_failed_logins": (0, 0),
        "same_srv_rate": (0.0, 0.3),
        "dst_host_same_src_port_rate": (0.0, 0.2),
    },
    "BruteForce": {
        "duration": (1.0, 12.0),
        "src_bytes": (120, 600),
        "dst_bytes": (120, 600),
        "count": (5, 55),
        "srv_count": (5, 55),
        "dst_host_count": (1, 5),
        "srv_diff_host_rate": (0.0, 0.15),
        "num_failed_logins": (3, 16),
        "same_srv_rate": (0.8, 1.0),
        "dst_host_same_src_port_rate": (0.3, 0.7),
    },
}

_PROTOCOLS = {
    "Normal": ["TCP", "UDP", "TCP"],
    "DDoS": ["UDP", "TCP", "ICMP"],
    "PortScan": ["TCP", "TCP", "UDP"],
    "BruteForce": ["TCP", "TCP", "TCP"],
}

_COMMON_PORTS = [80, 443, 53, 22, 8080, 3306, 25, 110]


def sample_features(label: str, rng: np.random.Generator | None = None) -> np.ndarray:
    """Draw one feature vector matching the statistical profile of ``label``."""
    rng = rng or np.random.default_rng()
    profile = _PROFILES[label]
    vec = np.empty(N_FEATURES, dtype=np.float32)
    for i, name in enumerate(FEATURE_NAMES):
        low, high = profile[name]
        if high == low:
            value = float(low)
        else:
            value = float(rng.uniform(low, high))
            # gaussian jitter (~18% of the range) so the class partitions overlap
            # realistically — the model is strong but not trivially perfect.
            value += float(rng.normal(0.0, (high - low) * 0.18))
        vec[i] = max(0.0, value)
    return vec


def _rand_ip(rng: random.Random, kind: str = "ext") -> str:
    if kind == "int":
        return f"10.0.{rng.randint(0, 4)}.{rng.randint(2, 254)}"
    return f"{rng.randint(11, 223)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"


@dataclass
class NetworkSimulator:
    """Stateful generator of live network flows.

    The frontend changes ``mode`` via ``set_mode`` (wired to the attack
    launchpad). While an attack is active most packets carry that attack's
    signature, but a slice of background normal traffic is mixed in so the feed
    looks like a real network rather than a metronome.
    """

    mode: str = "Normal"
    seed: int = 1337
    _rng: np.random.Generator = field(init=False)
    _prng: random.Random = field(init=False)
    # A pinned victim host makes DDoS / brute-force look like a focused attack.
    _victim_ip: str = field(init=False, default="10.0.0.21")

    def __post_init__(self) -> None:
        self._rng = np.random.default_rng(self.seed)
        self._prng = random.Random(self.seed)

    def set_mode(self, mode: str) -> str:
        if mode not in CLASS_NAMES:
            raise ValueError(f"unknown mode '{mode}' (expected one of {CLASS_NAMES})")
        self.mode = mode
        if mode in ("DDoS", "BruteForce"):
            self._victim_ip = _rand_ip(self._prng, "int")
        return self.mode

    def _pick_label(self) -> str:
        """Choose this packet's true label given the active mode."""
        if self.mode == "Normal":
            return "Normal"
        # ~30% benign background traffic during an attack
        return "Normal" if self._prng.random() < 0.30 else self.mode

    def next_packet(self) -> dict:
        """Produce one richly-annotated network flow record."""
        label = self._pick_label()
        features = sample_features(label, self._rng)

        proto = self._prng.choice(_PROTOCOLS[label])
        if label == "Normal":
            src, dst = _rand_ip(self._prng, "int"), _rand_ip(self._prng, "ext")
            port = self._prng.choice(_COMMON_PORTS)
        elif label == "DDoS":
            src, dst = _rand_ip(self._prng, "ext"), self._victim_ip
            port = self._prng.choice([80, 443])
        elif label == "PortScan":
            src, dst = _rand_ip(self._prng, "ext"), _rand_ip(self._prng, "int")
            port = self._prng.randint(1, 9000)  # sequential-ish probing
        else:  # BruteForce
            src, dst = _rand_ip(self._prng, "ext"), self._victim_ip
            port = self._prng.choice([22, 3306, 3389])

        return {
            "src_ip": src,
            "dst_ip": dst,
            "dst_port": int(port),
            "protocol": proto,
            "true_label": label,
            "features": {name: float(features[i]) for i, name in enumerate(FEATURE_NAMES)},
            "feature_vector": features,
        }
