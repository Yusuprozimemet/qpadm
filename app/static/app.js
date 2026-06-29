"use strict";

let chart = null;

function $(id) { return document.getElementById(id); }

// ---- Run pipeline -------------------------------------------------------
$("run-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  const res = await fetch("/api/run", { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    alert("Could not start run: " + (err.detail || res.statusText));
    return;
  }
  const { job_id } = await res.json();
  $("job-progress").classList.remove("hidden");
  pollJob(job_id);
});

async function pollJob(jobId) {
  const tick = async () => {
    const res = await fetch(`/api/jobs/${jobId}`);
    if (!res.ok) return;
    const job = await res.json();
    $("bar").style.width = (job.progress || 0) + "%";
    $("job-step").textContent = `${job.status} — ${job.step || ""}`;

    if (job.status === "done" && job.result) {
      $("job-step").textContent = "done";
      renderResult(job.result);
    } else if (job.status === "error") {
      $("job-step").textContent = "error: " + (job.error || "unknown");
    } else {
      setTimeout(tick, 1500);
    }
  };
  tick();
}

// ---- Visualise existing log --------------------------------------------
$("parse-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const form = new FormData(e.target);
  const res = await fetch("/api/parse", { method: "POST", body: form });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    alert("Could not parse log: " + (err.detail || res.statusText));
    return;
  }
  renderResult(await res.json());
});

// ---- Render -------------------------------------------------------------
function renderResult(result) {
  $("results-card").classList.remove("hidden");

  // Verdict
  const verdict = $("verdict");
  if (result.feasible === true) {
    verdict.className = "good";
    verdict.textContent = `✓ Plausible model (p = ${fmt(result.p_value)}). Weights sum to a sensible mixture.`;
  } else if (result.feasible === false) {
    verdict.className = "poor";
    verdict.textContent = `✗ Model is a poor fit (p = ${fmt(result.p_value)}). Try different sources/references.`;
  } else {
    verdict.className = "unknown";
    verdict.textContent = "Could not determine model fit automatically — see raw output.";
  }

  // Table
  const tbody = $("coeff-table").querySelector("tbody");
  tbody.innerHTML = "";
  for (const c of result.coefficients) {
    const tr = document.createElement("tr");
    tr.innerHTML = `<td>${esc(c.source)}</td><td>${pct(c.weight)}</td><td>${c.std_error == null ? "—" : pct(c.std_error)}</td>`;
    tbody.appendChild(tr);
  }
  $("pval").textContent = result.p_value == null ? "" : `Model fit p-value: ${fmt(result.p_value)}`;

  // Chart
  drawChart(result.coefficients);

  // Raw
  $("raw-output").textContent = result.raw_output || "(no raw output)";
  $("results-card").scrollIntoView({ behavior: "smooth" });
}

function drawChart(coeffs) {
  const ctx = $("chart");
  const labels = coeffs.map((c) => c.source);
  const data = coeffs.map((c) => +(c.weight * 100).toFixed(1));
  if (chart) chart.destroy();
  chart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{
        data,
        backgroundColor: ["#4f9cf9", "#2ea043", "#f0883e", "#a371f7", "#f85149", "#56d4dd", "#e3b341"],
        borderColor: "#1a212b",
        borderWidth: 2,
      }],
    },
    options: {
      plugins: {
        legend: { position: "bottom", labels: { color: "#e6edf3" } },
        tooltip: { callbacks: { label: (c) => `${c.label}: ${c.parsed}%` } },
      },
    },
  });
}

// ---- helpers ------------------------------------------------------------
function fmt(x) { return x == null ? "n/a" : (+x).toPrecision(3); }
function pct(x) { return (x * 100).toFixed(1) + "%"; }
function esc(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }
