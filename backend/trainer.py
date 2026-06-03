"""Dataset synthesis, feature scaling, and live (streamable) training.

``ModelHub`` owns the two trained models plus the min-max scaler and exposes:

    quick_pretrain()  - silent warm-up at server start so inference works
                        immediately when the dashboard loads.
    stream_train(...) - a *generator* that re-initialises the classifier and
                        yields per-epoch metrics, so the frontend can animate
                        the loss/accuracy curves live in the Training Playground.
"""

from __future__ import annotations

import time
from typing import Dict, Iterator, Optional

import numpy as np
import torch
import torch.nn as nn
from sklearn.metrics import precision_score, recall_score

from .model import Autoencoder, DNNClassifier
from .simulator import (
    CLASS_NAMES,
    FEATURE_NAMES,
    N_CLASSES,
    N_FEATURES,
    sample_features,
)

_EPS = 1e-8


def build_dataset(n_per_class: int, seed: int = 7) -> tuple[np.ndarray, np.ndarray]:
    """Synthesise a balanced labelled dataset from the traffic profiles."""
    rng = np.random.default_rng(seed)
    rows, labels = [], []
    for class_idx, name in enumerate(CLASS_NAMES):
        for _ in range(n_per_class):
            rows.append(sample_features(name, rng))
            labels.append(class_idx)
    X = np.asarray(rows, dtype=np.float32)
    y = np.asarray(labels, dtype=np.int64)
    # shuffle
    perm = rng.permutation(len(y))
    return X[perm], y[perm]


class ModelHub:
    """Holds the scaler + both models and orchestrates training/inference."""

    def __init__(self) -> None:
        self.classifier = DNNClassifier(N_FEATURES, N_CLASSES)
        self.autoencoder = Autoencoder(N_FEATURES)
        self.scaler_min = np.zeros(N_FEATURES, dtype=np.float32)
        self.scaler_max = np.ones(N_FEATURES, dtype=np.float32)
        self.ae_threshold: float = 1.0
        self.metrics: Dict[str, float] = {}
        self.is_trained = False

    # ------------------------------------------------------------------ #
    # Scaling helpers                                                    #
    # ------------------------------------------------------------------ #
    def fit_scaler(self, X: np.ndarray) -> None:
        self.scaler_min = X.min(axis=0)
        self.scaler_max = X.max(axis=0)

    def transform(self, X: np.ndarray) -> np.ndarray:
        denom = (self.scaler_max - self.scaler_min) + _EPS
        scaled = (X - self.scaler_min) / denom
        return np.clip(scaled, 0.0, 1.0).astype(np.float32)

    # ------------------------------------------------------------------ #
    # Warm-up training (silent)                                          #
    # ------------------------------------------------------------------ #
    def quick_pretrain(self, n_per_class: int = 450) -> None:
        """Train both models quietly so the live feed is meaningful at boot."""
        for _ in self.stream_train(epochs=60, n_per_class=n_per_class, silent=True):
            pass
        self.is_trained = True

    # ------------------------------------------------------------------ #
    # Live, streamable training                                          #
    # ------------------------------------------------------------------ #
    def stream_train(
        self,
        epochs: int = 50,
        lr: float = 0.01,
        n_per_class: int = 450,
        batch_size: int = 64,
        silent: bool = False,
        seed: Optional[int] = None,
    ) -> Iterator[Dict[str, float]]:
        """Re-train both models from scratch, yielding metrics each epoch.

        Yields dicts of {epoch, total, loss, val_loss, accuracy, precision,
        recall, ae_loss, elapsed} suitable for direct JSON streaming.
        """
        if seed is not None:
            torch.manual_seed(seed)
            np.random.seed(seed)

        X, y = build_dataset(n_per_class)
        self.fit_scaler(X)
        Xs = self.transform(X)

        # train / validation split
        n_val = max(1, int(0.2 * len(y)))
        Xv, yv = Xs[:n_val], y[:n_val]
        Xt, yt = Xs[n_val:], y[n_val:]

        Xt_t = torch.from_numpy(Xt)
        yt_t = torch.from_numpy(yt)
        Xv_t = torch.from_numpy(Xv)
        yv_t = torch.from_numpy(yv)

        # Fresh weights so the demo shows learning from scratch.
        self.classifier = DNNClassifier(N_FEATURES, N_CLASSES)
        self.autoencoder = Autoencoder(N_FEATURES)

        clf_opt = torch.optim.Adam(self.classifier.parameters(), lr=lr)
        ae_opt = torch.optim.Adam(self.autoencoder.parameters(), lr=lr)
        ce_loss = nn.CrossEntropyLoss()
        mse_loss = nn.MSELoss()

        # Autoencoder learns "normal" only.
        normal_mask = yt == 0
        Xt_normal = Xt_t[torch.from_numpy(normal_mask)]

        start = time.time()
        n = len(yt)
        for epoch in range(1, epochs + 1):
            # ---- classifier: one mini-batch pass ----
            self.classifier.train()
            perm = torch.randperm(n)
            epoch_loss = 0.0
            n_batches = 0
            for i in range(0, n, batch_size):
                idx = perm[i : i + batch_size]
                if len(idx) < 2:  # BatchNorm needs >1 sample
                    continue
                clf_opt.zero_grad()
                logits = self.classifier(Xt_t[idx])
                loss = ce_loss(logits, yt_t[idx])
                loss.backward()
                clf_opt.step()
                epoch_loss += float(loss.item())
                n_batches += 1
            train_loss = epoch_loss / max(1, n_batches)

            # ---- autoencoder: reconstruct normal traffic ----
            self.autoencoder.train()
            ae_opt.zero_grad()
            recon = self.autoencoder(Xt_normal)
            ae_loss = mse_loss(recon, Xt_normal)
            ae_loss.backward()
            ae_opt.step()

            # ---- validation metrics ----
            self.classifier.eval()
            with torch.no_grad():
                val_logits = self.classifier(Xv_t)
                val_loss = float(ce_loss(val_logits, yv_t).item())
                preds = val_logits.argmax(dim=1).numpy()
            accuracy = float((preds == yv).mean())
            precision = float(
                precision_score(yv, preds, average="macro", zero_division=0)
            )
            recall = float(recall_score(yv, preds, average="macro", zero_division=0))

            if not silent:
                yield {
                    "epoch": epoch,
                    "total": epochs,
                    "loss": round(train_loss, 4),
                    "val_loss": round(val_loss, 4),
                    "accuracy": round(accuracy, 4),
                    "precision": round(precision, 4),
                    "recall": round(recall, 4),
                    "ae_loss": round(float(ae_loss.item()), 5),
                    "elapsed": round(time.time() - start, 2),
                }

        # ---- finalise: lock in eval mode + anomaly threshold ----
        self.classifier.eval()
        self.autoencoder.eval()
        with torch.no_grad():
            recon_all = self.autoencoder(Xt_normal)
            errs = ((recon_all - Xt_normal) ** 2).mean(dim=1).numpy()
        # threshold = mean + 3*std of normal reconstruction error
        self.ae_threshold = float(errs.mean() + 3.0 * errs.std() + _EPS)

        self.metrics = {
            "accuracy": round(accuracy, 4),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "val_loss": round(val_loss, 4),
            "ae_threshold": round(self.ae_threshold, 5),
            "train_samples": int(len(yt)),
            "features": N_FEATURES,
            "classes": CLASS_NAMES,
            "feature_names": FEATURE_NAMES,
        }
        self.is_trained = True
