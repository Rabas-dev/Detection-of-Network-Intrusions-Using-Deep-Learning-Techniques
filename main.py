"""NIDS classroom demo - unified FastAPI server.

Single-process app: hosts the deep-learning inference pipeline *and* serves the
dashboard. Run it with one command:

    python main.py            # or: uvicorn main:app --reload

Then open http://localhost:8000
"""

from __future__ import annotations

import asyncio
import contextlib
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.pipeline import analyze
from backend.quality import benchmark, evaluate_model, run_test_suite
from backend.simulator import (
    CLASS_NAMES,
    FEATURE_LABELS,
    FEATURE_NAMES,
    NetworkSimulator,
)
from backend.trainer import ModelHub

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "frontend" / "static"
TEMPLATES_DIR = BASE_DIR / "frontend" / "templates"

# Live packets-per-second on the traffic feed.
TRAFFIC_INTERVAL = 0.16  # ~6 packets/sec

# Shared, process-wide state.
hub = ModelHub()
simulator = NetworkSimulator()


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Warm up both models in a worker thread so the event loop stays free.
    print("⚙️  Warming up deep-learning models (autoencoder + classifier)...")
    await asyncio.to_thread(hub.quick_pretrain)
    print(f"✅ Models ready. Validation accuracy: {hub.metrics.get('accuracy')}")
    yield


app = FastAPI(title="DeepNIDS", version="1.0.0", lifespan=lifespan)


# --------------------------------------------------------------------------- #
# HTTP API                                                                    #
# --------------------------------------------------------------------------- #
class AttackRequest(BaseModel):
    mode: str  # one of CLASS_NAMES


class TrainRequest(BaseModel):
    epochs: int = 50
    lr: float = 0.01


@app.post("/attack")
async def set_attack(req: AttackRequest) -> JSONResponse:
    """Switch the live traffic profile (wired to the attack launchpad)."""
    if req.mode not in CLASS_NAMES:
        return JSONResponse(
            {"ok": False, "error": f"unknown mode '{req.mode}'", "valid": CLASS_NAMES},
            status_code=400,
        )
    simulator.set_mode(req.mode)
    return JSONResponse({"ok": True, "mode": simulator.mode})


@app.get("/metrics")
async def get_metrics() -> JSONResponse:
    """Baseline model performance + schema metadata for the dashboard."""
    return JSONResponse(
        {
            "metrics": hub.metrics,
            "classes": CLASS_NAMES,
            "feature_names": FEATURE_NAMES,
            "feature_labels": FEATURE_LABELS,
            "current_mode": simulator.mode,
            "is_trained": hub.is_trained,
        }
    )


# --------------------------------------------------------------------------- #
# Quality-engineering API (powers the Quality & Testing dashboard)            #
# --------------------------------------------------------------------------- #
@app.get("/quality/model-eval")
async def quality_model_eval() -> JSONResponse:
    """Confusion matrix + per-class precision/recall/F1 on held-out data."""
    result = await asyncio.to_thread(evaluate_model, hub)
    return JSONResponse(result)


@app.get("/quality/benchmark")
async def quality_benchmark() -> JSONResponse:
    """Inference latency percentiles + throughput (performance test)."""
    result = await asyncio.to_thread(benchmark, hub)
    return JSONResponse(result)


@app.post("/quality/run-tests")
async def quality_run_tests() -> JSONResponse:
    """Execute the pytest suite with coverage and return a structured report."""
    result = await asyncio.to_thread(run_test_suite)
    return JSONResponse(result)


@app.post("/train/start")
async def train_start() -> JSONResponse:
    """The live training curve streams over the /ws/train WebSocket.

    This endpoint exists for completeness / scripting; the dashboard drives
    training through the socket so it can animate every epoch.
    """
    return JSONResponse(
        {"ok": True, "message": "Connect to /ws/train to stream live training metrics."}
    )


# --------------------------------------------------------------------------- #
# WebSocket: live traffic classification                                      #
# --------------------------------------------------------------------------- #
@app.websocket("/ws/traffic")
async def ws_traffic(websocket: WebSocket) -> None:
    await websocket.accept()
    # Per-connection model selection (default: supervised classifier).
    state = {"model": websocket.query_params.get("model", "classifier")}

    async def receiver() -> None:
        """Handle control messages (model toggle / attack mode) from the client."""
        try:
            while True:
                msg = await websocket.receive_json()
                if "model" in msg and msg["model"] in ("classifier", "autoencoder"):
                    state["model"] = msg["model"]
                if "mode" in msg and msg["mode"] in CLASS_NAMES:
                    simulator.set_mode(msg["mode"])
        except (WebSocketDisconnect, RuntimeError):
            pass

    async def sender() -> None:
        while True:
            packet = simulator.next_packet()
            result = analyze(hub, packet, state["model"])
            await websocket.send_json(result)
            await asyncio.sleep(TRAFFIC_INTERVAL)

    recv_task = asyncio.create_task(receiver())
    try:
        await sender()
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        recv_task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await recv_task


# --------------------------------------------------------------------------- #
# WebSocket: live training metrics                                            #
# --------------------------------------------------------------------------- #
@app.websocket("/ws/train")
async def ws_train(websocket: WebSocket) -> None:
    await websocket.accept()
    try:
        # Optional first message with hyper-parameters.
        try:
            params = await asyncio.wait_for(websocket.receive_json(), timeout=0.5)
        except (asyncio.TimeoutError, Exception):  # noqa: BLE001
            params = {}
        epochs = int(params.get("epochs", 50))
        lr = float(params.get("lr", 0.01))

        await websocket.send_json({"event": "start", "epochs": epochs, "lr": lr})

        # Run the blocking generator in a thread, bridging epochs onto the loop.
        loop = asyncio.get_running_loop()
        queue: asyncio.Queue = asyncio.Queue()

        def produce() -> None:
            for metric in hub.stream_train(epochs=epochs, lr=lr):
                loop.call_soon_threadsafe(queue.put_nowait, metric)
            loop.call_soon_threadsafe(queue.put_nowait, None)  # sentinel

        producer = asyncio.create_task(asyncio.to_thread(produce))
        while True:
            metric = await queue.get()
            if metric is None:
                break
            await websocket.send_json({"event": "epoch", **metric})
            await asyncio.sleep(0.04)  # let the curve breathe

        await producer
        await websocket.send_json({"event": "done", "metrics": hub.metrics})
    except (WebSocketDisconnect, RuntimeError):
        pass


# --------------------------------------------------------------------------- #
# Static assets + dashboard                                                   #
# --------------------------------------------------------------------------- #
@app.get("/")
async def index() -> FileResponse:
    return FileResponse(TEMPLATES_DIR / "index.html")


app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


if __name__ == "__main__":
    import uvicorn

    print("\n🛡️  DeepNIDS — Deep-Learning Network Intrusion Detection")
    print("   Open http://localhost:8000 in your browser.\n")
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
