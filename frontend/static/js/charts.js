/* ════════════════════════════════════════════════════════════════════
   DeepNIDS — bespoke canvas charts (zero dependencies, offline-safe)
   Crisp on HiDPI, gradient fills, soft glow, smooth animation.
   ════════════════════════════════════════════════════════════════════ */
(function (global) {
  "use strict";

  const FONT = "11px 'JetBrains Mono', monospace";
  const reduceMotion = global.matchMedia &&
    global.matchMedia("(prefers-reduced-motion: reduce)").matches;

  /* keep the backing store matched to the CSS box × devicePixelRatio */
  function fitCanvas(canvas) {
    const dpr = global.devicePixelRatio || 1;
    const rect = canvas.getBoundingClientRect();
    const w = Math.max(1, Math.floor(rect.width));
    const h = Math.max(1, Math.floor(rect.height));
    if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
      canvas.width = w * dpr;
      canvas.height = h * dpr;
    }
    const ctx = canvas.getContext("2d");
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    return { ctx, w, h };
  }

  function hexToRgba(hex, a) {
    const n = parseInt(hex.slice(1), 16);
    return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`;
  }

  /* ───────────────────── LineChart ───────────────────── */
  /* opts: { series:[{key,color,fill?}], maxPoints, yMin?, yMax?, smooth? } */
  class LineChart {
    constructor(canvas, opts) {
      this.canvas = canvas;
      this.opts = Object.assign({ maxPoints: 80, smooth: true }, opts);
      this.series = this.opts.series;
      this.data = {};
      this.series.forEach((s) => (this.data[s.key] = []));
      this.pad = { l: 38, r: 14, t: 14, b: 22 };
      this._dirty = true;
      this._loop();
    }
    reset() {
      this.series.forEach((s) => (this.data[s.key] = []));
      this._dirty = true;
    }
    push(values) {
      this.series.forEach((s) => {
        const arr = this.data[s.key];
        if (s.key in values) arr.push(values[s.key]);
        if (arr.length > this.opts.maxPoints) arr.shift();
      });
      this._dirty = true;
    }
    _bounds() {
      let lo = this.opts.yMin, hi = this.opts.yMax;
      if (lo == null || hi == null) {
        let mn = Infinity, mx = -Infinity;
        this.series.forEach((s) =>
          this.data[s.key].forEach((v) => { if (v < mn) mn = v; if (v > mx) mx = v; })
        );
        if (mn === Infinity) { mn = 0; mx = 1; }
        if (mn === mx) { mn -= 0.5; mx += 0.5; }
        const padv = (mx - mn) * 0.12;
        lo = lo != null ? lo : mn - padv;
        hi = hi != null ? hi : mx + padv;
      }
      return { lo, hi };
    }
    _loop() {
      const tick = () => {
        if (this._dirty) { this._draw(); this._dirty = false; }
        requestAnimationFrame(tick);
      };
      requestAnimationFrame(tick);
      // redraw on resize
      global.addEventListener("resize", () => (this._dirty = true));
    }
    _draw() {
      const { ctx, w, h } = fitCanvas(this.canvas);
      ctx.clearRect(0, 0, w, h);
      const { l, r, t, b } = this.pad;
      const pw = w - l - r, ph = h - t - b;
      const { lo, hi } = this._bounds();
      const yOf = (v) => t + ph - ((v - lo) / (hi - lo)) * ph;
      const maxLen = this.opts.maxPoints;
      const xOf = (i) => l + (maxLen <= 1 ? 0 : (i / (maxLen - 1)) * pw);

      // grid + y labels
      ctx.font = FONT;
      ctx.textBaseline = "middle";
      ctx.lineWidth = 1;
      for (let g = 0; g <= 4; g++) {
        const yv = lo + ((hi - lo) * g) / 4;
        const y = yOf(yv);
        ctx.strokeStyle = "rgba(255,255,255,0.05)";
        ctx.beginPath(); ctx.moveTo(l, y); ctx.lineTo(w - r, y); ctx.stroke();
        ctx.fillStyle = "rgba(138,149,176,0.7)";
        ctx.textAlign = "right";
        ctx.fillText(yv.toFixed(yv >= 10 ? 0 : 2), l - 6, y);
      }

      this.series.forEach((s) => {
        const arr = this.data[s.key];
        if (arr.length < 2) return;
        const pts = arr.map((v, i) => [xOf(i + (maxLen - arr.length)), yOf(v)]);

        // area fill
        if (s.fill !== false) {
          const grad = ctx.createLinearGradient(0, t, 0, t + ph);
          grad.addColorStop(0, hexToRgba(s.color, 0.28));
          grad.addColorStop(1, hexToRgba(s.color, 0));
          ctx.beginPath();
          ctx.moveTo(pts[0][0], t + ph);
          this._trace(ctx, pts);
          ctx.lineTo(pts[pts.length - 1][0], t + ph);
          ctx.closePath();
          ctx.fillStyle = grad;
          ctx.fill();
        }

        // line with glow
        ctx.save();
        ctx.shadowColor = hexToRgba(s.color, 0.6);
        ctx.shadowBlur = 10;
        ctx.strokeStyle = s.color;
        ctx.lineWidth = 2.2;
        ctx.lineJoin = "round";
        ctx.beginPath();
        ctx.moveTo(pts[0][0], pts[0][1]);
        this._trace(ctx, pts);
        ctx.stroke();
        ctx.restore();

        // leading dot
        const last = pts[pts.length - 1];
        ctx.fillStyle = s.color;
        ctx.beginPath(); ctx.arc(last[0], last[1], 3, 0, Math.PI * 2); ctx.fill();
      });
    }
    _trace(ctx, pts) {
      if (!this.opts.smooth || pts.length < 3) {
        for (let i = 1; i < pts.length; i++) ctx.lineTo(pts[i][0], pts[i][1]);
        return;
      }
      for (let i = 1; i < pts.length - 1; i++) {
        const xc = (pts[i][0] + pts[i + 1][0]) / 2;
        const yc = (pts[i][1] + pts[i + 1][1]) / 2;
        ctx.quadraticCurveTo(pts[i][0], pts[i][1], xc, yc);
      }
      const n = pts.length;
      ctx.quadraticCurveTo(pts[n - 1][0], pts[n - 1][1], pts[n - 1][0], pts[n - 1][1]);
    }
  }

  /* ───────────────────── BarChart (horizontal, animated) ───────────────────── */
  class BarChart {
    constructor(canvas) {
      this.canvas = canvas;
      this.items = [];     // {label, value, color}
      this.display = [];    // animated current values
      this._raf = null;
      global.addEventListener("resize", () => this._render());
    }
    setData(items) {
      this.items = items;
      if (this.display.length !== items.length) {
        this.display = items.map(() => 0);
      }
      this._animate();
    }
    _animate() {
      if (this._raf) cancelAnimationFrame(this._raf);
      const step = () => {
        let moving = false;
        this.items.forEach((it, i) => {
          const target = it.value;
          const cur = this.display[i];
          const next = reduceMotion ? target : cur + (target - cur) * 0.18;
          if (Math.abs(target - next) > 0.001) moving = true;
          this.display[i] = next;
        });
        this._render();
        if (moving) this._raf = requestAnimationFrame(step);
      };
      step();
    }
    _render() {
      const { ctx, w, h } = fitCanvas(this.canvas);
      ctx.clearRect(0, 0, w, h);
      const n = this.items.length;
      if (!n) return;
      const labelW = 116;
      const padX = 12, padY = 6;
      const rowH = (h - padY * 2) / n;
      const barH = Math.min(16, rowH * 0.55);
      const maxV = Math.max(...this.items.map((d) => d.value), 0.0001);
      const trackX = labelW + 8;
      const trackW = w - trackX - 44;

      ctx.font = FONT;
      ctx.textBaseline = "middle";
      this.items.forEach((it, i) => {
        const cy = padY + i * rowH + rowH / 2;
        // label
        ctx.fillStyle = "rgba(233,238,249,0.8)";
        ctx.textAlign = "left";
        ctx.fillText(it.label, padX, cy);
        // track
        ctx.fillStyle = "rgba(255,255,255,0.06)";
        roundRect(ctx, trackX, cy - barH / 2, trackW, barH, barH / 2);
        ctx.fill();
        // value bar
        const frac = Math.max(0, Math.min(1, this.display[i] / maxV));
        const bw = Math.max(2, trackW * frac);
        const grad = ctx.createLinearGradient(trackX, 0, trackX + trackW, 0);
        grad.addColorStop(0, hexToRgba(it.color, 0.55));
        grad.addColorStop(1, it.color);
        ctx.save();
        ctx.shadowColor = hexToRgba(it.color, 0.55);
        ctx.shadowBlur = 8;
        ctx.fillStyle = grad;
        roundRect(ctx, trackX, cy - barH / 2, bw, barH, barH / 2);
        ctx.fill();
        ctx.restore();
        // value text
        ctx.fillStyle = "rgba(138,149,176,0.9)";
        ctx.textAlign = "left";
        ctx.fillText((it.value * 100).toFixed(0) + "%", trackX + trackW + 8, cy);
      });
    }
  }

  function roundRect(ctx, x, y, w, h, r) {
    r = Math.min(r, h / 2, w / 2);
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }

  /* ───────────────────── Confusion matrix heatmap ───────────────────── */
  function drawConfusion(canvas, labels, matrix) {
    const { ctx, w, h } = fitCanvas(canvas);
    ctx.clearRect(0, 0, w, h);
    const n = labels.length;
    const margin = { l: 84, t: 22, r: 14, b: 56 };
    const gw = w - margin.l - margin.r;
    const gh = h - margin.t - margin.b;
    const cw = gw / n, ch = gh / n;
    const max = Math.max(1, ...matrix.flat());

    ctx.font = "10px 'JetBrains Mono', monospace";
    for (let i = 0; i < n; i++) {
      for (let j = 0; j < n; j++) {
        const v = matrix[i][j];
        const frac = v / max;
        const onDiag = i === j;
        const base = onDiag ? "#34d399" : "#fb5d7a";
        const x = margin.l + j * cw, y = margin.t + i * ch;
        ctx.fillStyle = v === 0 ? "rgba(255,255,255,0.03)" : hexToRgba(base, 0.12 + frac * 0.8);
        roundRect(ctx, x + 2, y + 2, cw - 4, ch - 4, 6);
        ctx.fill();
        ctx.fillStyle = frac > 0.4 ? "#06121c" : "rgba(233,238,249,0.85)";
        ctx.textAlign = "center"; ctx.textBaseline = "middle";
        ctx.fillText(String(v), x + cw / 2, y + ch / 2);
      }
    }
    // axis labels
    ctx.fillStyle = "rgba(138,149,176,0.9)";
    ctx.textBaseline = "middle";
    for (let i = 0; i < n; i++) {
      ctx.textAlign = "right";
      ctx.fillText(labels[i], margin.l - 8, margin.t + i * ch + ch / 2);
      ctx.save();
      ctx.translate(margin.l + i * cw + cw / 2, margin.t + gh + 10);
      ctx.rotate(-Math.PI / 9);
      ctx.textAlign = "right";
      ctx.fillText(labels[i], 0, 0);
      ctx.restore();
    }
    ctx.fillStyle = "rgba(138,149,176,0.6)";
    ctx.textAlign = "center";
    ctx.fillText("Predicted →", margin.l + gw / 2, h - 6);
    ctx.save();
    ctx.translate(12, margin.t + gh / 2); ctx.rotate(-Math.PI / 2);
    ctx.fillText("Actual →", 0, 0); ctx.restore();
  }

  global.DeepCharts = { LineChart, BarChart, drawConfusion, fitCanvas, hexToRgba };
})(window);
