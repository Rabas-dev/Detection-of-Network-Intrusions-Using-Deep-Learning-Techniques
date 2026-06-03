"""Live inference pipeline with Explainable-AI feature attribution.

Given one simulated flow, the pipeline scales the features, runs them through
the selected model, and returns a rich result containing the predicted class,
confidence, the autoencoder anomaly score, and a per-feature contribution
score (a simplified, gradient-based saliency akin to SHAP) that powers the XAI
panel on the dashboard.
"""

from __future__ import annotations

import time
from typing import Dict, List

import numpy as np
import torch

from .simulator import CLASS_NAMES, FEATURE_NAMES
from .trainer import ModelHub


def _softmax(logits: np.ndarray) -> np.ndarray:
    z = logits - logits.max()
    e = np.exp(z)
    return e / (e.sum() + 1e-9)


def _classifier_saliency(hub: ModelHub, x_scaled: np.ndarray, target: int) -> np.ndarray:
    """Gradient * input saliency for the predicted class (|.|, normalised)."""
    xt = torch.tensor(x_scaled.reshape(1, -1), dtype=torch.float32, requires_grad=True)
    hub.classifier.eval()
    logits = hub.classifier(xt)
    score = logits[0, target]
    hub.classifier.zero_grad()
    score.backward()
    grad = xt.grad.detach().numpy().reshape(-1)
    contrib = np.abs(grad * x_scaled)
    total = contrib.sum()
    return contrib / total if total > 1e-9 else np.ones_like(contrib) / len(contrib)


def _autoencoder_attribution(hub: ModelHub, x_scaled: np.ndarray) -> tuple[float, np.ndarray]:
    """Return (anomaly_score, per-feature reconstruction error share)."""
    xt = torch.tensor(x_scaled.reshape(1, -1), dtype=torch.float32)
    hub.autoencoder.eval()
    with torch.no_grad():
        recon = hub.autoencoder(xt).numpy().reshape(-1)
    per_feature = (recon - x_scaled) ** 2
    mse = float(per_feature.mean())
    total = per_feature.sum()
    share = per_feature / total if total > 1e-9 else np.ones_like(per_feature) / len(per_feature)
    return mse, share


def analyze(hub: ModelHub, packet: dict, model_type: str = "classifier") -> dict:
    """Run a single packet through the chosen model and build a result dict.

    Parameters
    ----------
    model_type : "classifier" (supervised DNN) or "autoencoder" (anomaly).
    """
    t0 = time.perf_counter()
    raw = packet["feature_vector"]
    x_scaled = hub.transform(raw.reshape(1, -1))[0]

    # Anomaly score is always available (useful context in both views).
    anomaly_score, ae_share = _autoencoder_attribution(hub, x_scaled)
    anomaly_ratio = anomaly_score / (hub.ae_threshold + 1e-9)

    if model_type == "autoencoder":
        is_threat = anomaly_score > hub.ae_threshold
        label = "Anomaly" if is_threat else "Normal"
        # Confidence scales with how far past the threshold we are.
        confidence = float(min(0.99, anomaly_ratio / (anomaly_ratio + 1.0) + 0.05))
        contributions = ae_share
        probs = None
        target_idx = None
    else:
        xt = torch.tensor(x_scaled.reshape(1, -1), dtype=torch.float32)
        hub.classifier.eval()
        with torch.no_grad():
            logits = hub.classifier(xt).numpy().reshape(-1)
        probs = _softmax(logits)
        target_idx = int(probs.argmax())
        label = CLASS_NAMES[target_idx]
        confidence = float(probs[target_idx])
        is_threat = target_idx != 0  # anything but "Normal"
        contributions = _classifier_saliency(hub, x_scaled, target_idx)

    inference_ms = (time.perf_counter() - t0) * 1000.0

    # Top contributing features (sorted) for the XAI panel.
    order = np.argsort(contributions)[::-1]
    feature_contributions: List[dict] = [
        {
            "name": FEATURE_NAMES[i],
            "value": round(float(raw[i]), 3),
            "contribution": round(float(contributions[i]), 4),
        }
        for i in order
    ]

    return {
        "timestamp": time.time(),
        "model": model_type,
        "src_ip": packet["src_ip"],
        "dst_ip": packet["dst_ip"],
        "dst_port": packet["dst_port"],
        "protocol": packet["protocol"],
        "true_label": packet["true_label"],
        "prediction": label,
        "is_threat": bool(is_threat),
        "confidence": round(confidence, 4),
        "anomaly_score": round(float(anomaly_score), 5),
        "anomaly_threshold": round(float(hub.ae_threshold), 5),
        "anomaly_ratio": round(float(anomaly_ratio), 3),
        "probabilities": (
            {CLASS_NAMES[i]: round(float(probs[i]), 4) for i in range(len(CLASS_NAMES))}
            if probs is not None
            else None
        ),
        "feature_contributions": feature_contributions,
        "inference_ms": round(inference_ms, 3),
    }
