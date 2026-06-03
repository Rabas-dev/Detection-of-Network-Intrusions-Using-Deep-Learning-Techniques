"""PyTorch model architectures for the intrusion-detection demo.

Two complementary models are provided so the audience can toggle between the
two dominant paradigms in deep-learning NIDS:

    Autoencoder   - *unsupervised* anomaly detection. Trained only on normal
                    traffic; the reconstruction error becomes an anomaly score.
    DNNClassifier - *supervised* multi-class classification (Normal / DDoS /
                    PortScan / BruteForce) with BatchNorm + Dropout.
"""

from __future__ import annotations

import torch
import torch.nn as nn


class Autoencoder(nn.Module):
    """Symmetric fully-connected autoencoder with a 4-unit bottleneck."""

    def __init__(self, n_features: int):
        super().__init__()
        self.encoder = nn.Sequential(
            nn.Linear(n_features, 16),
            nn.ReLU(inplace=True),
            nn.Linear(16, 8),
            nn.ReLU(inplace=True),
            nn.Linear(8, 4),  # bottleneck / latent code
            nn.ReLU(inplace=True),
        )
        self.decoder = nn.Sequential(
            nn.Linear(4, 8),
            nn.ReLU(inplace=True),
            nn.Linear(8, 16),
            nn.ReLU(inplace=True),
            nn.Linear(16, n_features),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.decoder(self.encoder(x))

    def encode(self, x: torch.Tensor) -> torch.Tensor:
        return self.encoder(x)


class DNNClassifier(nn.Module):
    """Multi-layer perceptron classifier with batch-norm and dropout."""

    def __init__(self, n_features: int, n_classes: int):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(n_features, 64),
            nn.BatchNorm1d(64),
            nn.ReLU(inplace=True),
            nn.Dropout(0.30),
            nn.Linear(64, 32),
            nn.BatchNorm1d(32),
            nn.ReLU(inplace=True),
            nn.Dropout(0.20),
            nn.Linear(32, n_classes),
        )

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        return self.net(x)
