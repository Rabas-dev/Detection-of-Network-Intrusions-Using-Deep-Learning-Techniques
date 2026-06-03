/* ════════════════════════════════════════════════════════════════════
   DeepNIDS — dashboard controller
   WebSocket streams · flow visualizer · XAI · training playground
   ════════════════════════════════════════════════════════════════════ */
(function () {
  "use strict";

  const $ = (sel) => document.querySelector(sel);
  const COLORS = {
    accent: "#38bdf8", indigo: "#818cf8", violet: "#a78bfa",
    safe: "#34d399", danger: "#fb5d7a", warn: "#fbbf24",
  };
  const reduceMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // Surface any uncaught error in the status pill instead of freezing silently.
  window.addEventListener("error", (e) => {
    const s = document.getElementById("conn-status");
    const p = document.getElementById("status-pill");
    if (s) s.textContent = "JS error — see console";
    if (p) { p.classList.remove("online"); p.classList.add("offline"); }
    console.error("[DeepNIDS] uncaught error:", e.message, e.filename, e.lineno);
  });

  const state = {
    model: "classifier",
    mode: "Normal",
    packets: 0,
    threats: 0,
    featureLabels: {},
    secBenign: 0,
    secThreat: 0,
    secCount: 0,
  };

  // ─────────────────────────── tabs ───────────────────────────
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => {
        t.classList.remove("is-active");
        t.setAttribute("aria-selected", "false");
      });
      tab.classList.add("is-active");
      tab.setAttribute("aria-selected", "true");
      const target = tab.dataset.tab;
      document.querySelectorAll(".panel").forEach((p) => {
        const on = p.id === `panel-${target}`;
        p.classList.toggle("is-active", on);
        p.hidden = !on;
      });
    });
  });

  // ─────────────────────── model toggle ───────────────────────
  document.querySelectorAll(".seg").forEach((seg) => {
    seg.addEventListener("click", () => {
      document.querySelectorAll(".seg").forEach((s) => s.classList.remove("is-active"));
      seg.classList.add("is-active");
      state.model = seg.dataset.model;
      if (trafficSocket && trafficSocket.readyState === 1) {
        trafficSocket.send(JSON.stringify({ model: state.model }));
      }
    });
  });

  // ─────────────────────── attack launchpad ───────────────────────
  document.querySelectorAll(".atk").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const mode = btn.dataset.attack;
      document.querySelectorAll(".atk").forEach((b) => b.classList.remove("is-active"));
      btn.classList.add("is-active");
      state.mode = mode;
      updateModeChip(mode);
      try {
        await fetch("/attack", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ mode }),
        });
      } catch (e) { /* socket fallback */
        if (trafficSocket && trafficSocket.readyState === 1)
          trafficSocket.send(JSON.stringify({ mode }));
      }
    });
  });

  function updateModeChip(mode) {
    const chip = $("#mode-chip");
    $("#current-mode-label").textContent = mode;
    chip.classList.toggle("attack", mode !== "Normal");
  }

  // ═══════════════════ flow visualizer ═══════════════════
  const flow = (() => {
    const canvas = $("#flow-canvas");
    let particles = [], bursts = [], gateFlash = 0, ambient = [];

    // ambient drifting motes for depth
    for (let i = 0; i < 18; i++) {
      ambient.push({ x: Math.random(), y: Math.random(), s: Math.random() * 1.4 + 0.4, v: Math.random() * 0.02 + 0.005 });
    }

    function spawn(isThreat) {
      if (particles.length > 80) particles.shift();
      particles.push({
        x: 0,
        y: 0.18 + Math.random() * 0.64,
        vx: 0.006 + Math.random() * 0.004,
        threat: isThreat,
        resolved: false,
        trail: [],
      });
    }

    function loop() {
      const { ctx, w, h } = DeepCharts.fitCanvas(canvas);
      ctx.clearRect(0, 0, w, h);
      const gateX = w * 0.6;

      // ambient
      ambient.forEach((m) => {
        m.x += m.v * 0.01;
        if (m.x > 1) m.x = 0;
        ctx.fillStyle = "rgba(56,189,248,0.10)";
        ctx.beginPath(); ctx.arc(m.x * w, m.y * h, m.s, 0, Math.PI * 2); ctx.fill();
      });

      // ── gate (deep-learning firewall) ──
      gateFlash *= 0.9;
      const gateCol = gateFlash > 0.05 ? COLORS.danger : COLORS.accent;
      const grd = ctx.createLinearGradient(gateX - 16, 0, gateX + 16, 0);
      grd.addColorStop(0, DeepCharts.hexToRgba(gateCol, 0));
      grd.addColorStop(0.5, DeepCharts.hexToRgba(gateCol, 0.35 + gateFlash * 0.5));
      grd.addColorStop(1, DeepCharts.hexToRgba(gateCol, 0));
      ctx.fillStyle = grd;
      ctx.fillRect(gateX - 16, 8, 32, h - 16);
      ctx.save();
      ctx.shadowColor = gateCol; ctx.shadowBlur = 18 + gateFlash * 24;
      ctx.strokeStyle = DeepCharts.hexToRgba(gateCol, 0.85);
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(gateX, 12); ctx.lineTo(gateX, h - 12); ctx.stroke();
      ctx.restore();
      // gate label
      ctx.font = "600 11px 'Outfit', sans-serif";
      ctx.fillStyle = DeepCharts.hexToRgba(gateCol, 0.8);
      ctx.textAlign = "center";
      ctx.fillText("DEEP-LEARNING FIREWALL", gateX, h - 4);

      // ── particles ──
      for (let i = particles.length - 1; i >= 0; i--) {
        const p = particles[i];
        p.x += p.vx;
        const px = p.x * w, py = p.y * h;
        p.trail.push([px, py]);
        if (p.trail.length > 9) p.trail.shift();

        if (!p.resolved && px >= gateX) {
          p.resolved = true;
          if (p.threat) {
            bursts.push({ x: gateX, y: py, r: 2, a: 1 });
            gateFlash = 1;
            particles.splice(i, 1);
            continue;
          }
        }
        if (px > w + 10) { particles.splice(i, 1); continue; }

        const col = p.threat ? COLORS.danger : (p.resolved ? COLORS.safe : COLORS.accent);
        // trail
        for (let t = 0; t < p.trail.length; t++) {
          const a = (t / p.trail.length) * 0.5;
          ctx.fillStyle = DeepCharts.hexToRgba(col, a);
          ctx.beginPath(); ctx.arc(p.trail[t][0], p.trail[t][1], 1.6, 0, Math.PI * 2); ctx.fill();
        }
        ctx.save();
        ctx.shadowColor = col; ctx.shadowBlur = 12;
        ctx.fillStyle = col;
        ctx.beginPath(); ctx.arc(px, py, 3.2, 0, Math.PI * 2); ctx.fill();
        ctx.restore();
      }

      // ── bursts ──
      for (let i = bursts.length - 1; i >= 0; i--) {
        const b = bursts[i];
        b.r += 1.6; b.a *= 0.92;
        if (b.a < 0.04) { bursts.splice(i, 1); continue; }
        ctx.strokeStyle = DeepCharts.hexToRgba(COLORS.danger, b.a);
        ctx.lineWidth = 2;
        ctx.beginPath(); ctx.arc(b.x, b.y, b.r, 0, Math.PI * 2); ctx.stroke();
      }

      requestAnimationFrame(loop);
    }
    requestAnimationFrame(loop);
    return { spawn, flashAlert: () => (gateFlash = 1) };
  })();

  // ═══════════════════ charts ═══════════════════
  const throughputChart = new DeepCharts.LineChart($("#throughput-canvas"), {
    series: [
      { key: "benign", color: COLORS.safe },
      { key: "threat", color: COLORS.danger },
    ],
    maxPoints: 60, yMin: 0,
  });
  const xaiChart = new DeepCharts.BarChart($("#xai-canvas"));
  const lossChart = new DeepCharts.LineChart($("#loss-canvas"), {
    series: [
      { key: "loss", color: COLORS.accent },
      { key: "val_loss", color: COLORS.violet },
    ],
    maxPoints: 120, yMin: 0,
  });
  const accChart = new DeepCharts.LineChart($("#acc-canvas"), {
    series: [
      { key: "accuracy", color: COLORS.accent, fill: false },
      { key: "precision", color: COLORS.violet, fill: false },
      { key: "recall", color: COLORS.safe, fill: false },
    ],
    maxPoints: 120, yMin: 0, yMax: 1.02,
  });

  // throughput aggregation: push one bucket per second
  setInterval(() => {
    throughputChart.push({ benign: state.secBenign, threat: state.secThreat });
    $("#kpi-pps").textContent = `${state.secCount} pps`;
    state.secBenign = 0; state.secThreat = 0; state.secCount = 0;
  }, 1000);

  // ═══════════════════ traffic socket ═══════════════════
  let trafficSocket = null;
  let bannerTimer = null;

  function connectTraffic() {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    trafficSocket = new WebSocket(`${proto}://${location.host}/ws/traffic?model=${state.model}`);

    trafficSocket.onopen = () => setStatus("online", "Live");
    trafficSocket.onclose = () => {
      setStatus("offline", "Reconnecting…");
      setTimeout(connectTraffic, 1500);
    };
    trafficSocket.onerror = () => trafficSocket.close();
    trafficSocket.onmessage = (ev) => handlePacket(JSON.parse(ev.data));
  }

  function setStatus(cls, text) {
    const pill = $("#status-pill");
    pill.classList.remove("online", "offline");
    if (cls) pill.classList.add(cls);
    $("#conn-status").textContent = text;
  }

  function handlePacket(res) {
    state.packets++;
    state.secCount++;
    const threat = res.is_threat;
    if (threat) { state.threats++; state.secThreat++; } else { state.secBenign++; }

    // KPIs
    $("#kpi-packets").textContent = state.packets.toLocaleString();
    $("#kpi-threats").textContent = state.threats.toLocaleString();
    $("#kpi-threat-rate").textContent =
      `${((state.threats / state.packets) * 100).toFixed(1)}% of traffic`;
    $("#kpi-latency").textContent = `${res.inference_ms.toFixed(2)} ms`;

    // flow particle
    flow.spawn(threat);

    // verdict + XAI
    renderVerdict(res);
    renderXAI(res);
    pushAlert(res);

    // threat banner + alert glow
    if (threat) {
      const banner = $("#threat-banner");
      $("#threat-banner-text").textContent =
        res.model === "autoencoder"
          ? `Anomaly detected · ${res.anomaly_ratio}× threshold`
          : `${res.prediction} attack blocked`;
      banner.hidden = false;
      $(".flow-wrap").classList.add("alert");
      flow.flashAlert();
      flashKpi();
      clearTimeout(bannerTimer);
      bannerTimer = setTimeout(() => {
        banner.hidden = true;
        $(".flow-wrap").classList.remove("alert");
      }, 1200);
    }
  }

  let kpiFlashLock = false;
  function flashKpi() {
    if (kpiFlashLock || reduceMotion) return;
    kpiFlashLock = true;
    const card = $("#kpi-threats-card");
    card.classList.add("flash-danger");
    setTimeout(() => { card.classList.remove("flash-danger"); kpiFlashLock = false; }, 600);
  }

  function renderVerdict(res) {
    const label = $("#pred-label");
    label.textContent = res.prediction;
    label.classList.toggle("threat", res.is_threat);
    label.classList.toggle("safe", !res.is_threat);
    $("#pred-confidence").textContent = `confidence ${(res.confidence * 100).toFixed(1)}%`;

    const container = $("#prob-bars");
    if (res.probabilities) {
      const entries = Object.entries(res.probabilities);
      // build rows once, then update widths
      if (container.children.length !== entries.length) {
        container.innerHTML = entries
          .map(
            ([k]) => `<div class="prob-row"><span>${k}</span>
              <div class="prob-track"><div class="prob-fill" data-k="${k}"></div></div>
              <span class="prob-pct" data-pct="${k}">0%</span></div>`
          )
          .join("");
      }
      entries.forEach(([k, v]) => {
        const fill = container.querySelector(`.prob-fill[data-k="${k}"]`);
        const pct = container.querySelector(`.prob-pct[data-pct="${k}"]`);
        fill.style.width = `${(v * 100).toFixed(1)}%`;
        fill.classList.toggle("threat", k !== "Normal");
        pct.textContent = `${(v * 100).toFixed(0)}%`;
      });
    } else {
      // autoencoder — show anomaly ratio gauge
      const ratio = Math.min(1, res.anomaly_ratio / 3);
      container.innerHTML = `<div class="prob-row"><span>Anomaly</span>
        <div class="prob-track"><div class="prob-fill ${res.is_threat ? "threat" : ""}" style="width:${(ratio * 100).toFixed(0)}%"></div></div>
        <span class="prob-pct">${res.anomaly_ratio}×</span></div>
        <div class="prob-row"><span>Threshold</span>
        <div class="prob-track"><div class="prob-fill" style="width:33%;opacity:.4"></div></div>
        <span class="prob-pct">1.0×</span></div>`;
    }
  }

  function renderXAI(res) {
    const top = res.feature_contributions.slice(0, 6);
    xaiChart.setData(
      top.map((f) => ({
        label: state.featureLabels[f.name] || f.name,
        value: f.contribution,
        color: res.is_threat ? COLORS.danger : COLORS.accent,
      }))
    );
  }

  const alertLog = $("#alert-log");
  function pushAlert(res) {
    if (!res.is_threat && Math.random() > 0.25) return; // keep log threat-heavy but alive
    const li = document.createElement("li");
    li.className = "alert-item" + (res.is_threat ? " threat" : "");
    const time = new Date().toLocaleTimeString([], { hour12: false });
    li.innerHTML = `
      <span class="alert-badge">${res.prediction}</span>
      <span class="alert-route">${res.src_ip} → ${res.dst_ip}:${res.dst_port} · ${res.protocol}</span>
      <span class="alert-time">${time}</span>`;
    alertLog.prepend(li);
    while (alertLog.children.length > 8) alertLog.lastChild.remove();
  }

  // ═══════════════════ training playground ═══════════════════
  const epochsRange = $("#epochs-range");
  epochsRange?.addEventListener("input", () => ($("#epochs-val").textContent = epochsRange.value));

  let trainSocket = null;
  $("#train-btn")?.addEventListener("click", startTraining);

  function startTraining() {
    if (trainSocket && trainSocket.readyState === 1) return;
    const epochs = parseInt(epochsRange.value, 10);
    const lr = parseFloat($("#lr-select").value);

    lossChart.reset(); accChart.reset();
    $("#train-log").innerHTML = "";
    $("#train-progress-fill").style.width = "0%";
    const btn = $("#train-btn");
    btn.disabled = true;
    $("#train-btn-label").textContent = "⏳ Training…";
    $("#train-status").textContent = `Training ${epochs} epochs at lr=${lr}…`;

    const proto = location.protocol === "https:" ? "wss" : "ws";
    trainSocket = new WebSocket(`${proto}://${location.host}/ws/train`);

    trainSocket.onopen = () => trainSocket.send(JSON.stringify({ epochs, lr }));
    trainSocket.onmessage = (ev) => {
      const msg = JSON.parse(ev.data);
      if (msg.event === "epoch") onEpoch(msg);
      else if (msg.event === "done") onTrainDone(msg);
    };
    trainSocket.onclose = () => finishTrainUI();
    trainSocket.onerror = () => { $("#train-status").textContent = "Connection error."; finishTrainUI(); };
  }

  function onEpoch(m) {
    lossChart.push({ loss: m.loss, val_loss: m.val_loss });
    accChart.push({ accuracy: m.accuracy, precision: m.precision, recall: m.recall });
    $("#train-progress-fill").style.width = `${(m.epoch / m.total) * 100}%`;
    $("#train-status").textContent =
      `Epoch ${m.epoch}/${m.total} · loss ${m.loss} · acc ${(m.accuracy * 100).toFixed(1)}%`;

    const li = document.createElement("li");
    li.innerHTML = `<strong>ep ${String(m.epoch).padStart(3, " ")}</strong> · ` +
      `loss ${m.loss} · val ${m.val_loss} · acc ${(m.accuracy * 100).toFixed(1)}%`;
    const log = $("#train-log");
    log.prepend(li);
    while (log.children.length > 40) log.lastChild.remove();
  }

  function onTrainDone(msg) {
    const m = msg.metrics || {};
    $("#m-accuracy").textContent = m.accuracy != null ? `${(m.accuracy * 100).toFixed(1)}%` : "—";
    $("#m-precision").textContent = m.precision != null ? `${(m.precision * 100).toFixed(1)}%` : "—";
    $("#m-recall").textContent = m.recall != null ? `${(m.recall * 100).toFixed(1)}%` : "—";
    $("#m-loss").textContent = m.val_loss != null ? m.val_loss.toFixed(3) : "—";
    $("#kpi-accuracy").textContent = m.accuracy != null ? `${(m.accuracy * 100).toFixed(1)}%` : "—";
    $("#train-status").textContent = `✅ Done — validation accuracy ${(m.accuracy * 100).toFixed(1)}%`;
  }

  function finishTrainUI() {
    const btn = $("#train-btn");
    btn.disabled = false;
    $("#train-btn-label").textContent = "▶ Train Model";
    trainSocket = null;
  }

  // ═══════════════════ quality & testing ═══════════════════
  function setGate(name, pass, detail) {
    const el = document.querySelector(`.gate[data-gate="${name}"]`);
    if (!el) return;
    el.classList.toggle("pass", pass === true);
    el.classList.toggle("fail", pass === false);
    el.querySelector(".gate-state").textContent = pass == null ? "○" : pass ? "✓" : "✕";
    el.querySelector(".gate-detail").textContent = detail;
  }

  async function runTests() {
    const btn = $("#run-tests-btn");
    btn.disabled = true;
    $("#run-tests-label").textContent = "⏳ Running pytest…";
    $("#test-list").innerHTML = `<li class="test-empty">Executing pytest with coverage… (this trains models, ~10s)</li>`;
    try {
      const r = await fetch("/quality/run-tests", { method: "POST" });
      const data = await r.json();
      const t = data.tests || {};
      $("#ts-passed").textContent = t.passed ?? "—";
      $("#ts-failed").textContent = (t.failed ?? 0) + (t.errors ?? 0);
      $("#ts-total").textContent = t.total ?? "—";
      $("#ts-time").textContent = data.wall_time ?? "—";

      const list = $("#test-list");
      list.innerHTML = "";
      (t.cases || []).forEach((c) => {
        const li = document.createElement("li");
        li.className = "test-item";
        li.innerHTML = `<span class="dot ${c.status}"></span>
          <span class="tname">${c.name}</span>
          <span class="ttime">${c.time}s</span>`;
        list.appendChild(li);
      });
      if (!list.children.length) list.innerHTML = `<li class="test-empty">No test cases parsed.</li>`;

      const allPass = (t.failed === 0 && t.errors === 0 && t.total > 0);
      setGate("tests", allPass, `${t.passed}/${t.total} passed`);

      if (data.coverage && data.coverage.total != null) renderCoverage(data.coverage);
    } catch (e) {
      $("#test-list").innerHTML = `<li class="test-empty">Test run failed: ${e}</li>`;
    } finally {
      btn.disabled = false;
      $("#run-tests-label").textContent = "▶ Run Test Suite";
    }
  }

  function renderCoverage(cov) {
    const ring = $("#cov-ring");
    ring.style.setProperty("--pct", cov.total);
    $("#cov-total").textContent = `${cov.total}%`;
    setGate("coverage", cov.total >= 75, `${cov.total}% covered`);
    const box = $("#cov-files");
    box.innerHTML = "";
    (cov.files || []).forEach((f) => {
      const short = f.file.replace(/^.*\//, "");
      const div = document.createElement("div");
      div.className = "cov-file";
      div.innerHTML = `<div class="cov-file-head"><span>${short}</span><span>${f.coverage}%</span></div>
        <div class="cov-file-track"><div class="cov-file-fill" style="width:${f.coverage}%"></div></div>`;
      box.appendChild(div);
    });
  }

  async function evaluateModel() {
    const btn = $("#eval-btn");
    btn.disabled = true; $("#eval-label").textContent = "⏳ Evaluating…";
    try {
      const data = await (await fetch("/quality/model-eval")).json();
      DeepCharts.drawConfusion($("#confusion-canvas"), data.labels, data.confusion_matrix);
      const tbody = $("#classmetrics");
      tbody.innerHTML = data.per_class
        .map((c) => `<tr><td>${c.label}</td><td>${c.precision.toFixed(3)}</td>
          <td>${c.recall.toFixed(3)}</td><td class="f1">${c.f1.toFixed(3)}</td><td>${c.support}</td></tr>`)
        .join("");
      setGate("accuracy", data.macro_f1 >= 0.9, `macro-F1 ${data.macro_f1.toFixed(3)}`);
    } catch (e) { /* ignore */ }
    finally { btn.disabled = false; $("#eval-label").textContent = "▶ Evaluate"; }
  }

  async function runBenchmark() {
    const btn = $("#bench-btn");
    btn.disabled = true; $("#bench-label").textContent = "⏳ Benchmarking…";
    try {
      const d = await (await fetch("/quality/benchmark")).json();
      $("#perf-p50").textContent = `${d.p50_ms} ms`;
      $("#perf-p95").textContent = `${d.p95_ms} ms`;
      $("#perf-p99").textContent = `${d.p99_ms} ms`;
      $("#perf-tput").textContent = `${Math.round(d.throughput_per_sec)}/s`;
      setGate("latency", d.p95_ms < 5, `p95 ${d.p95_ms} ms`);
    } catch (e) { /* ignore */ }
    finally { btn.disabled = false; $("#bench-label").textContent = "▶ Benchmark"; }
  }

  $("#run-tests-btn")?.addEventListener("click", runTests);
  $("#eval-btn")?.addEventListener("click", evaluateModel);
  $("#bench-btn")?.addEventListener("click", runBenchmark);
  $("#run-all-btn")?.addEventListener("click", async () => {
    await evaluateModel();
    await runBenchmark();
    await runTests();
  });

  // lazily evaluate model + benchmark the first time the Quality tab opens
  let qualityInit = false;
  document.querySelector('.tab[data-tab="quality"]')?.addEventListener("click", () => {
    if (qualityInit) return;
    qualityInit = true;
    evaluateModel();
    runBenchmark();
  });

  // ═══════════════════ bootstrap ═══════════════════
  async function init() {
    try {
      const r = await fetch("/metrics");
      const data = await r.json();
      state.featureLabels = data.feature_labels || {};
      state.mode = data.current_mode || "Normal";
      if (data.metrics && data.metrics.accuracy != null) {
        $("#kpi-accuracy").textContent = `${(data.metrics.accuracy * 100).toFixed(1)}%`;
        $("#m-accuracy").textContent = `${(data.metrics.accuracy * 100).toFixed(1)}%`;
        if (data.metrics.precision != null) $("#m-precision").textContent = `${(data.metrics.precision * 100).toFixed(1)}%`;
        if (data.metrics.recall != null) $("#m-recall").textContent = `${(data.metrics.recall * 100).toFixed(1)}%`;
        if (data.metrics.val_loss != null) $("#m-loss").textContent = data.metrics.val_loss.toFixed(3);
      }
    } catch (e) { /* metrics optional */ }
    connectTraffic();
  }

  init();
})();
