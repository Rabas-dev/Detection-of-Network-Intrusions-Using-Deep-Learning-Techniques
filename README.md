# 🛡️ DeepNIDS — Deep-Learning Network Intrusion Detection

An interactive, classroom-ready demonstration of **detecting network intrusions
with deep learning**. A single FastAPI process hosts the PyTorch inference
pipeline *and* serves a premium, real-time dashboard — no Node, no npm, no
external datasets, no internet required.

![stack](https://img.shields.io/badge/stack-FastAPI%20%2B%20PyTorch%20%2B%20Vanilla%20JS-38bdf8)

---

## ✨ What it shows

- **Two deep-learning paradigms**, toggleable live:
  - **DNN Classifier** — supervised multi-class (Normal / DDoS / PortScan / BruteForce)
    with BatchNorm + Dropout.
  - **Autoencoder** — unsupervised anomaly detection; reconstruction error → anomaly score.
- **Live traffic visualizer** — packets stream through a "deep-learning firewall"
  gate, passing green or bursting red when blocked.
- **Attack Launchpad** — inject DDoS, Port Scan, or Brute Force traffic on demand.
- **Explainable AI** — per-packet, gradient-based feature attribution shows
  *why* the model flagged a flow (e.g. failed logins → Brute Force).
- **Training Playground** — retrain the network from scratch and watch the loss
  curve fall and accuracy climb, epoch by epoch, over a WebSocket.

The traffic is synthesized from NSL-KDD–inspired statistical profiles, so the
demo is fully self-contained and runs offline in seconds.

---

## 🚀 Quick start

```bash
# 1. (optional) create a virtual environment
python3 -m venv .venv && source .venv/bin/activate

# 2. install dependencies
pip install -r requirements.txt

# 3. run — one command
python main.py
```

Then open **http://localhost:8000**.

> First launch warms up both models in a couple of seconds; the status pill turns
> green ("Live") once the traffic feed connects.

---

## 🧪 Quality engineering (for the SQE course)

This project doubles as a Software-Quality-Engineering case study.

```bash
pip install -r requirements-dev.txt
pytest tests -q --cov=backend --cov=main --cov-report=term-missing
```

- **Layered test suite** — `tests/test_unit.py`, `test_integration.py`,
  `test_system.py` using **Boundary Value Analysis**, **Equivalence Partitioning**,
  and **decision-table** techniques.
- **Branch coverage** via `pytest-cov` (quality gate ≥ 75 %).
- **CI pipeline** — `.github/workflows/ci.yml` runs tests + coverage on every push.
- **In-app Quality Dashboard** — the **Quality & Testing** tab runs the test
  suite live, shows coverage, the model **confusion matrix**, per-class
  precision/recall/F1, latency percentiles, and ISO/IEC 25010 quality gates.
- **Docs** — [`docs/TEST_PLAN.md`](docs/TEST_PLAN.md) and
  [`docs/RTM.md`](docs/RTM.md) (Requirements Traceability Matrix).

| Quality gate | Threshold |
| --- | --- |
| All tests pass | 0 failures |
| Branch coverage | ≥ 75 % |
| Model macro-F1 | ≥ 0.90 |
| Inference p95 latency | < 5 ms |

---

## 🗂️ Project layout

```
main.py                     FastAPI app: WebSockets + static serving + REST
backend/
  simulator.py              Traffic profiles + canonical feature schema (source of truth)
  model.py                  PyTorch Autoencoder + DNN classifier
  trainer.py                Dataset synthesis, scaler, streamable live training
  pipeline.py               Real-time inference + Explainable-AI saliency
frontend/
  templates/index.html      Dashboard markup
  static/css/style.css      Glassmorphism design system
  static/js/charts.js        Bespoke canvas charts (zero dependencies)
  static/js/app.js           WebSocket controller + flow visualizer
tests/test_smoke.py         Backend smoke tests
```

## 🔌 API surface

| Route             | Type      | Purpose                                        |
| ----------------- | --------- | ---------------------------------------------- |
| `GET /`           | HTML      | Dashboard                                      |
| `GET /metrics`    | JSON      | Baseline metrics + feature/class metadata      |
| `POST /attack`    | JSON      | Switch live traffic profile `{ "mode": ... }`  |
| `POST /train/start` | JSON    | Hint to stream training over the socket        |
| `WS /ws/traffic`  | WebSocket | Live classification + XAI (~6 packets/sec)     |
| `WS /ws/train`    | WebSocket | Live per-epoch training metrics                |

---

## 🎓 Suggested demo flow

1. **Baseline** — open the dashboard; calm green flow, low metrics.
2. **Train** — open *Training Playground*, press **Train Model**, watch loss fall.
3. **DDoS** — press **Inject DDoS**; the firewall flares red, throughput spikes,
   threats counter climbs.
4. **Port Scan / Brute Force** — note how the **Explainable AI** bars shift to the
   features that define each attack (e.g. *Failed Logins* for brute force).
5. **Toggle model** — switch to the **Autoencoder** to contrast supervised
   classification with unsupervised anomaly detection.
