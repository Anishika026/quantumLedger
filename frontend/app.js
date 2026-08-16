const STAGE_DEFS = {
  input: {
    icon: "◆", color: "var(--cyan)", title: "Transaction Data Input",
    desc: "Amount, device, location, IP, merchant, time, and historical behaviour captured.",
  },
  preprocessing: {
    icon: "⚙", color: "var(--cyan)", title: "Preprocessing",
    desc: "Cleaning, normalization, and feature engineering applied to raw fields.",
  },
  xgboost: {
    icon: "△", color: "var(--cyan)", title: "XGBoost Model",
    desc: "Gradient-boosted trees predict a fraud risk score in [0, 1] and classify risk.",
  },
  quantum: {
    icon: "⬡", color: "var(--violet)", title: "Quantum Model (PennyLane VQC)",
    desc: "A 4-qubit variational circuit re-evaluates uncertain transactions.",
  },
  blockchain: {
    icon: "⛓", color: "var(--blue)", title: "Blockchain Audit & Logging",
    desc: "Transaction hash + decision + timestamp written to a tamper-evident hash-chained ledger.",
  },
};
const STAGE_ORDER = ["input", "preprocessing", "xgboost", "quantum", "blockchain"];

const $ = (id) => document.getElementById(id);
const fmt = (n, d = 3) => (typeof n === "number" ? n.toFixed(d) : n);
const fmtTime = (ts) => new Date(ts * 1000).toLocaleTimeString();
const shortHash = (h) => h ? `${h.slice(0, 10)}…${h.slice(-6)}` : "";

let processedCount = 0;
let liveSimulationState = false;
let livePollTimer = null;
let lastSeenTransactionId = null;
let processingInFlight = false;

function renderSkeleton() {
  const container = $("pipeline-flow");
  if (!container) return;
  container.innerHTML = STAGE_ORDER.map((key) => {
    const def = STAGE_DEFS[key];
    return `
      <div class="stage-node" id="node-${key}" style="--node-color:${def.color}">
        <div class="connector"><div class="connector-fill"></div></div>
        <div class="node-icon">${def.icon}</div>
        <div class="node-body">
          <p class="node-title">${def.title} <span class="node-badge" id="badge-${key}"></span></p>
          <p class="node-desc">${def.desc}</p>
          <div class="node-detail" id="detail-${key}"></div>
        </div>
      </div>`;
  }).join("");
}

function updateProcessedCount() {
  const el = $("processed-count");
  if (el) el.textContent = String(processedCount);
}

function setStatusMessage(message, type = "info") {
  const box = $("sim-status-box");
  const text = $("sim-status-text");
  if (!box || !text) return;
  box.className = `status-box ${type}`;
  text.textContent = message;
}

function updateSimulationButton() {
  const simBtn = $("sim-toggle-btn");
  if (!simBtn) return;
  simBtn.innerHTML = liveSimulationState
    ? '<span class="btn-icon">■</span> Stop Simulation'
    : '<span class="btn-icon">●</span> Start Simulation';
  simBtn.classList.toggle("active", liveSimulationState);
}

async function refreshSimulatorStatus() {
  try {
    const res = await fetch("/api/simulator-status");
    const data = await res.json();
    if (!data.ok) return;
    liveSimulationState = Boolean(data.is_live);
    updateSimulationButton();
    setStatusMessage(
      liveSimulationState ? "Live simulator is active." : "Simulator is offline. Existing CSV data will be used for manual tests.",
      liveSimulationState ? "good" : "info"
    );
    return data;
  } catch (err) {
    console.warn("Unable to refresh simulator status:", err);
  }
}

function startLivePoll() {
  if (livePollTimer) clearInterval(livePollTimer);
  livePollTimer = setInterval(async () => {
    await pollLiveTransaction();
  }, 5000);
}

function stopLivePoll() {
  if (livePollTimer) {
    clearInterval(livePollTimer);
    livePollTimer = null;
  }
}

async function pollLiveTransaction() {
  if (!liveSimulationState || processingInFlight) return;
  try {
    const res = await fetch("/api/next-transaction");
    const data = await res.json();
    if (!data.ok || !data.transaction) return;
    const txn = data.transaction;
    if (!txn.transaction_id || txn.transaction_id === lastSeenTransactionId) return;

    lastSeenTransactionId = txn.transaction_id;
    await processTransaction(txn);
    processedCount += 1;
    updateProcessedCount();
    setStatusMessage("Processing newest live transaction from CSV.", "good");
  } catch (err) {
    console.warn("Live transaction poll failed:", err);
  }
}

async function startSimulation() {
  try {
    const res = await fetch("/api/simulator/start", { method: "POST" });
    const data = await res.json();
    liveSimulationState = true;
    updateSimulationButton();
    setStatusMessage(data.message || "Live simulation started.", "good");
    startLivePoll();
  } catch (err) {
    alert(`Unable to start simulator: ${err.message}`);
  }
}

async function stopSimulation() {
  try {
    const res = await fetch("/api/simulator/stop", { method: "POST" });
    const data = await res.json();
    liveSimulationState = false;
    lastSeenTransactionId = null;
    updateSimulationButton();
    stopLivePoll();
    setStatusMessage(data.message || "Live simulation stopped.", "info");
  } catch (err) {
    alert(`Unable to stop simulator: ${err.message}`);
  }
}

async function runExistingTest() {
  if (processingInFlight) return;
  processingInFlight = true;
  try {
    const res = await fetch("/api/next-transaction");
    const data = await res.json();
    if (!data.ok) throw new Error(data.error || "No existing transaction found in CSV.");

    alert(data.message || "Simulator is not running. Using the latest existing CSV transaction as mock data.");
    setStatusMessage("Using existing CSV transaction for this test.", "info");

    await processTransaction(data.transaction);
    processedCount += 1;
    updateProcessedCount();
  } catch (err) {
    alert(`Test run failed: ${err.message}`);
  } finally {
    processingInFlight = false;
  }
}

async function processTransaction(txn) {
  resetPipeline();
  await submitTransactionPayload(txn);
}

async function submitTransactionPayload(payload) {
  const runBtn = $("run-test-btn");
  if (runBtn) runBtn.disabled = true;
  try {
    const res = await fetch("/api/predict", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const data = await res.json();
    if (!data.ok) throw new Error(data.error);
    await animateStages(data.result.stages, data.result.decision_stage);
    renderDecision(data.result);
    await refreshLedger();
  } catch (err) {
    alert(`Pipeline error: ${err.message}`);
  } finally {
    if (runBtn) runBtn.disabled = false;
  }
}

function renderDetail(stageKey, detail) {
  const el = $(`detail-${stageKey}`);
  if (!el) return;
  if (stageKey === "input") {
    el.innerHTML = Object.entries(detail).map(([k, v]) =>
      `<div class="kv"><span>${k}</span><span>${v}</span></div>`).join("");
  } else if (stageKey === "preprocessing") {
    el.innerHTML = `
      <div class="kv"><span>amount_deviation</span><span>${fmt(detail.amount_deviation, 2)}×</span></div>
      <div class="kv"><span>is_night_txn</span><span>${detail.is_night_txn}</span></div>
      <div class="kv"><span>is_high_value</span><span>${detail.is_high_value}</span></div>
      <div class="kv"><span>velocity_risk</span><span>${fmt(detail.velocity_risk, 2)}</span></div>
      <div class="kv"><span>device_risk</span><span>${fmt(detail.device_risk, 2)}</span></div>`;
  } else if (stageKey === "xgboost") {
    el.innerHTML = `
      <div class="kv"><span>risk_score</span><span>${fmt(detail.risk_score, 4)}</span></div>
      <div class="kv"><span>risk_band</span><span class="band-pill band-${detail.risk_band}">${detail.risk_band}</span></div>
      <div class="kv"><span>thresholds (T1 / T2)</span><span>${detail.thresholds.T1} / ${detail.thresholds.T2}</span></div>`;
  } else if (stageKey === "quantum") {
    el.innerHTML = `
      <div class="kv"><span>quantum_score</span><span>${fmt(detail.quantum_score, 4)}</span></div>
      <div class="kv"><span>expectation ⟨Z₀⟩</span><span>${fmt(detail.expectation_value, 4)}</span></div>
      <div class="kv"><span>verdict</span><span>${detail.verdict}</span></div>
      <div class="kv"><span>circuit</span><span>${detail.n_qubits} qubits × ${detail.n_layers} layers</span></div>
      ${renderQCircuit(detail)}`;
  } else if (stageKey === "blockchain") {
    el.innerHTML = `
      <div class="kv"><span>block #</span><span>${detail.block_index}</span></div>
      <div class="kv"><span>block hash</span><span>${shortHash(detail.block_hash)}</span></div>
      <div class="kv"><span>prev hash</span><span>${shortHash(detail.previous_hash)}</span></div>
      <div class="kv"><span>txn hash</span><span>${shortHash(detail.transaction_hash)}</span></div>
      <div class="kv"><span>timestamp</span><span>${fmtTime(detail.timestamp)}</span></div>`;
  }
}

function renderQCircuit(detail) {
  const angles = detail.angles_rad || [];
  const labels = detail.features_used || [];
  const wires = angles.map((a, i) => `
    <div class="qwire">
      <span class="qwire-label">q${i}</span>
      <div class="qwire-line">
        <div class="qgate" style="left:18%">RY</div>
        <div class="qgate" style="left:55%">RZ</div>
        <div class="qgate" style="left:86%">●</div>
      </div>
      <span class="qwire-label" title="${labels[i] || ''}">${fmt(a, 2)}rad</span>
    </div>`).join("");
  return `<div class="qcircuit">${wires}</div>`;
}

function resetPipeline() {
  const container = $("pipeline-flow");
  if (!container) return;
  STAGE_ORDER.forEach((key) => {
    const node = $(`node-${key}`);
    if (!node) return;
    node.classList.remove("active", "filled", "pulse", "pending-skip");
    const badge = $(`badge-${key}`);
    const detail = $(`detail-${key}`);
    if (badge) badge.textContent = "";
    if (detail) detail.innerHTML = "";
  });
}

async function animateStages(stages, decisionStage) {
  for (const stage of stages) {
    const key = stage.stage;
    const node = $(`node-${key}`);
    if (!node) continue;
    await sleep(320);
    node.classList.add("active", "pulse");
    const badge = $(`badge-${key}`);
    if (badge) badge.textContent = "processed";
    renderDetail(key, stage.detail);
    setTimeout(() => node.classList.remove("pulse"), 1100);
    if (key !== "blockchain") node.classList.add("filled");
  }
  if (decisionStage === "xgboost") {
    const quantumNode = $("node-quantum");
    if (quantumNode) quantumNode.classList.add("pending-skip");
    const quantumBadge = $("badge-quantum");
    if (quantumBadge) quantumBadge.textContent = "skipped — not uncertain";
  }
}

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }

function renderDecision(result) {
  const card = $("decision-card");
  const approve = result.decision === "APPROVE";
  card.className = `decision-card ${approve ? "approve" : "block"}`;
  card.innerHTML = `
    <div class="decision-content">
      <div class="decision-verdict ${approve ? "approve" : "block"}">
        <span>${approve ? "✓" : "✕"}</span> ${approve ? "Transaction Approved" : "Transaction Blocked"}
      </div>
      <div class="decision-sub">${result.transaction_id} · decided at <strong>${result.decision_stage.toUpperCase()}</strong> stage · ${result.latency_ms}ms</div>
      <div class="decision-grid">
        <div class="decision-stat"><div class="label">XGBoost score</div><div class="value">${fmt(result.xgboost_score, 4)}</div></div>
        <div class="decision-stat"><div class="label">Risk band</div><div class="value"><span class="band-pill band-${result.risk_band}">${result.risk_band}</span></div></div>
        <div class="decision-stat"><div class="label">Final score</div><div class="value">${fmt(result.final_score, 4)}</div></div>
        <div class="decision-stat"><div class="label">Block #</div><div class="value">${result.block.index}</div></div>
      </div>
    </div>`;
}

async function refreshLedger() {
  const res = await fetch("/api/audit-log?limit=25");
  const data = await res.json();
  const el = $("ledger-table");
  if (!data.blocks.length) {
    el.innerHTML = `<div class="ledger-empty">No blocks yet — the genesis block is written on the first transaction.</div>`;
    return;
  }
  el.innerHTML = data.blocks.map((b) => `
    <div class="ledger-row">
      <div class="row-top">
        <span>#${b.index} · ${b.transaction_id}</span>
        <span class="row-decision ${b.decision}">${b.decision}</span>
      </div>
      <div class="row-hash">${shortHash(b.hash)}</div>
      <div class="row-meta"><span>score ${b.risk_score ?? "—"} · via ${b.stage}</span><span>${fmtTime(b.timestamp)}</span></div>
    </div>`).join("");
}

$("verify-btn").addEventListener("click", async () => {
  const res = await fetch("/api/audit-log/verify");
  const data = await res.json();
  const chip = $("chain-status");
  if (data.valid) {
    chip.innerHTML = `<span class="dot dot-good"></span> Ledger verified · ${data.blocks} blocks`;
  } else {
    chip.innerHTML = `<span class="dot dot-bad"></span> Tamper detected at block ${data.broken_at_index}`;
  }
});

$("run-test-btn").addEventListener("click", async () => {
  await runExistingTest();
});

$("sim-toggle-btn").addEventListener("click", async () => {
  if (liveSimulationState) {
    await stopSimulation();
  } else {
    await startSimulation();
  }
});

renderSkeleton();
updateProcessedCount();
refreshSimulatorStatus();
refreshLedger();
