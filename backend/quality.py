"""Software-Quality-Engineering instrumentation.

Powers the in-app *Quality & Testing* dashboard:

    evaluate_model()  - confusion matrix + per-class precision/recall/F1
                        (quality assurance of the ML model itself)
    benchmark()       - inference latency percentiles + throughput
                        (performance testing of the detection path)
    run_test_suite()  - executes pytest with coverage in a subprocess and
                        parses JUnit + coverage.py JSON reports
                        (live automated-testing + coverage evidence)
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import time
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Dict, List

import numpy as np
from sklearn.metrics import confusion_matrix, precision_recall_fscore_support

from .pipeline import analyze
from .simulator import CLASS_NAMES, N_CLASSES, NetworkSimulator, sample_features
from .trainer import ModelHub

BASE_DIR = Path(__file__).resolve().parent.parent


# --------------------------------------------------------------------------- #
# Model quality — confusion matrix + per-class metrics                        #
# --------------------------------------------------------------------------- #
def evaluate_model(hub: ModelHub, n_per_class: int = 300, seed: int = 99) -> Dict:
    """Score the classifier on a fresh, held-out, balanced sample."""
    rng = np.random.default_rng(seed)
    X, y = [], []
    for idx, name in enumerate(CLASS_NAMES):
        for _ in range(n_per_class):
            X.append(sample_features(name, rng))
            y.append(idx)
    X = np.asarray(X, dtype=np.float32)
    y = np.asarray(y, dtype=np.int64)

    import torch

    Xs = hub.transform(X)
    hub.classifier.eval()
    with torch.no_grad():
        preds = hub.classifier(torch.from_numpy(Xs)).argmax(dim=1).numpy()

    cm = confusion_matrix(y, preds, labels=list(range(N_CLASSES)))
    prec, rec, f1, support = precision_recall_fscore_support(
        y, preds, labels=list(range(N_CLASSES)), zero_division=0
    )
    per_class = [
        {
            "label": CLASS_NAMES[i],
            "precision": round(float(prec[i]), 4),
            "recall": round(float(rec[i]), 4),
            "f1": round(float(f1[i]), 4),
            "support": int(support[i]),
        }
        for i in range(N_CLASSES)
    ]
    accuracy = float((preds == y).mean())
    return {
        "labels": CLASS_NAMES,
        "confusion_matrix": cm.tolist(),
        "per_class": per_class,
        "accuracy": round(accuracy, 4),
        "macro_f1": round(float(f1.mean()), 4),
        "samples": int(len(y)),
    }


# --------------------------------------------------------------------------- #
# Performance testing — latency percentiles + throughput                      #
# --------------------------------------------------------------------------- #
def benchmark(hub: ModelHub, n: int = 400) -> Dict:
    """Measure end-to-end inference latency over a mixed traffic sample."""
    sim = NetworkSimulator(seed=2024)
    packets = []
    per_mode = max(1, n // len(CLASS_NAMES))
    for mode in CLASS_NAMES:
        sim.set_mode(mode)
        for _ in range(per_mode):
            packets.append(sim.next_packet())

    # warm-up (exclude JIT/first-call costs from the measurement)
    for p in packets[:10]:
        analyze(hub, p, "classifier")

    samples = []
    for p in packets:
        t0 = time.perf_counter()
        analyze(hub, p, "classifier")
        samples.append((time.perf_counter() - t0) * 1000.0)

    arr = np.asarray(samples)
    mean = float(arr.mean())
    return {
        "count": len(samples),
        "mean_ms": round(mean, 4),
        "p50_ms": round(float(np.percentile(arr, 50)), 4),
        "p95_ms": round(float(np.percentile(arr, 95)), 4),
        "p99_ms": round(float(np.percentile(arr, 99)), 4),
        "max_ms": round(float(arr.max()), 4),
        "throughput_per_sec": round(1000.0 / mean, 1) if mean > 0 else None,
    }


# --------------------------------------------------------------------------- #
# Automated testing — run pytest + coverage, parse the reports                #
# --------------------------------------------------------------------------- #
def _parse_junit(path: Path) -> Dict:
    tree = ET.parse(path)
    root = tree.getroot()
    suite = root.find("testsuite") if root.tag == "testsuites" else root
    cases: List[Dict] = []
    for case in suite.findall("testcase"):
        status = "passed"
        if case.find("failure") is not None:
            status = "failed"
        elif case.find("error") is not None:
            status = "error"
        elif case.find("skipped") is not None:
            status = "skipped"
        cases.append(
            {
                "name": case.get("name"),
                "classname": case.get("classname", ""),
                "time": round(float(case.get("time", 0.0)), 3),
                "status": status,
            }
        )
    total = int(suite.get("tests", 0))
    failures = int(suite.get("failures", 0))
    errors = int(suite.get("errors", 0))
    skipped = int(suite.get("skipped", 0))
    return {
        "total": total,
        "passed": total - failures - errors - skipped,
        "failed": failures,
        "errors": errors,
        "skipped": skipped,
        "duration": round(float(suite.get("time", 0.0)), 2),
        "cases": cases,
    }


def _parse_coverage(path: Path) -> Dict:
    data = json.loads(path.read_text())
    files = []
    for fname, info in data.get("files", {}).items():
        summary = info.get("summary", {})
        files.append(
            {
                "file": fname,
                "coverage": round(float(summary.get("percent_covered", 0.0)), 1),
                "covered": summary.get("covered_lines", 0),
                "statements": summary.get("num_statements", 0),
            }
        )
    files.sort(key=lambda f: f["file"])
    return {
        "total": round(float(data["totals"]["percent_covered"]), 1),
        "covered_lines": data["totals"].get("covered_lines", 0),
        "num_statements": data["totals"].get("num_statements", 0),
        "files": files,
    }


def run_test_suite() -> Dict:
    """Run the full pytest suite with coverage; return a structured report."""
    junit = Path(tempfile.gettempdir()) / "nids_junit.xml"
    cov = Path(tempfile.gettempdir()) / "nids_cov.json"
    cmd = [
        sys.executable, "-m", "pytest", "tests", "-q", "-p", "no:cacheprovider",
        f"--junitxml={junit}",
        "--cov=backend", "--cov=main",
        f"--cov-report=json:{cov}",
    ]
    started = time.time()
    proc = subprocess.run(
        cmd, cwd=str(BASE_DIR), capture_output=True, text=True, timeout=600
    )
    report: Dict = {
        "exit_code": proc.returncode,
        "wall_time": round(time.time() - started, 2),
        "stdout_tail": "\n".join(proc.stdout.strip().splitlines()[-12:]),
    }
    try:
        report["tests"] = _parse_junit(junit)
    except Exception as exc:  # noqa: BLE001
        report["tests"] = {"error": str(exc)}
    try:
        report["coverage"] = _parse_coverage(cov)
    except Exception as exc:  # noqa: BLE001
        report["coverage"] = {"error": str(exc)}
    return report
