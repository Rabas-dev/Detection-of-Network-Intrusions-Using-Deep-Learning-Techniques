"""Deep-learning Network Intrusion Detection System (classroom demo).

Package layout:
    simulator.py  - traffic profiles + canonical feature schema (source of truth)
    model.py      - PyTorch Autoencoder + DNN classifier architectures
    trainer.py    - dataset synthesis, scaler, and live (streamable) training
    pipeline.py   - real-time inference + Explainable-AI saliency
"""

__all__ = ["simulator", "model", "trainer", "pipeline"]
