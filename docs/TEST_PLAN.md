# Test Plan — DeepNIDS

**Project:** Detection of Network Intrusions Using Deep Learning Techniques
**Document type:** Software Test Plan (IEEE 829-style, condensed)
**Version:** 1.0

---

## 1. Introduction & objective

DeepNIDS is a deep-learning network-intrusion-detection system with a real-time
dashboard. This plan defines the strategy, scope, techniques, and quality gates
used to verify and validate the software and the embedded machine-learning
model. Quality is assessed against selected **ISO/IEC 25010** characteristics:
*functional suitability, performance efficiency, reliability,* and
*maintainability.*

## 2. Scope

**In scope:** model architectures, feature scaler, traffic-profile generator,
inference pipeline + XAI, REST/WebSocket API, and the trained model's predictive
quality.
**Out of scope:** front-end visual rendering (manually verified), third-party
libraries (PyTorch, FastAPI), and production-grade packet capture.

## 3. Test items (components under test)

| Component | File |
| --- | --- |
| Model architectures | `backend/model.py` |
| Traffic profiles + schema | `backend/simulator.py` |
| Training engine + scaler | `backend/trainer.py` |
| Inference + XAI | `backend/pipeline.py` |
| Quality instrumentation | `backend/quality.py` |
| API / WebSocket server | `main.py` |

## 4. Test levels

1. **Unit** (`tests/test_unit.py`) — components in isolation (white & black box).
2. **Integration** (`tests/test_integration.py`) — scaler → model → XAI pipeline.
3. **System** (`tests/test_system.py`) — end-to-end through the public HTTP /
   WebSocket API using an in-process ASGI TestClient.

## 5. Test-design techniques

| Technique | Where applied |
| --- | --- |
| **Boundary Value Analysis (BVA)** | Min-max scaler at 0, max, mid, below-, above-range; batch size = 1 boundary for BatchNorm |
| **Equivalence Partitioning (EP)** | Traffic profiles — each attack class is a partition with a defining feature (e.g. failed logins ⇒ Brute Force) |
| **Decision Table** | Attack profile → expected classifier verdict (one rule per class) |
| **State transition** | Simulator mode switching (`set_mode`) changing the emitted traffic |
| **Output-contract / black-box** | Probability vector sums to 1; attribution normalised; required JSON keys present |
| **Performance testing** | Latency percentiles (p50/p95/p99) + throughput over a mixed workload |
| **Model evaluation** | Confusion matrix + per-class precision/recall/F1 on held-out data |

## 6. Test environment

- Python 3.12+ (developed on 3.14), PyTorch (CPU), FastAPI, scikit-learn.
- Runner: `pytest` with `pytest-cov` (branch coverage).
- CI: GitHub Actions (`.github/workflows/ci.yml`) on every push / PR.
- Live evidence: in-app **Quality & Testing** dashboard tab.

## 7. Entry & exit criteria

**Entry:** code compiles/imports; dependencies installed; models can warm up.
**Exit (all must hold):**

| Quality gate | Threshold | Verified by |
| --- | --- | --- |
| All automated tests pass | 0 failures/errors | pytest |
| Branch coverage | ≥ 75 % | pytest-cov / CI `--cov-fail-under` |
| Model macro-F1 | ≥ 0.90 | `evaluate_model()` |
| Inference latency (p95) | < 5 ms | `benchmark()` |

## 8. How to run

```bash
pip install -r requirements-dev.txt
pytest tests -q --cov=backend --cov=main --cov-report=term-missing
```

Or run live from the dashboard: open the **Quality & Testing** tab → **Run All Checks**.

## 9. Deliverables

Test plan (this document), Requirements Traceability Matrix (`docs/RTM.md`),
automated test suite (`tests/`), coverage report, CI pipeline, and the in-app
quality dashboard.

## 10. Risks & mitigations

| Risk | Mitigation |
| --- | --- |
| Synthetic data over-separates classes (optimistic metrics) | Gaussian jitter overlaps partitions; majority-vote (≥70%) rather than 100% assertions |
| Training time slows the live test run | Small `n_per_class` in fixtures; session-scoped trained hub |
| Non-determinism in ML | Seeded RNGs in dataset, simulator, and evaluation |
