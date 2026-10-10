const API = "";

let yoyChart, hotspotChart, monthlyChart;

async function api(path, options) {
  const res = await fetch(API + path, options);
  if (!res.ok) {
    let detail = res.statusText;
    try { detail = (await res.json()).detail || detail; } catch (e) { /* keep statusText */ }
    throw new Error(detail);
  }
  return res.json();
}

function fmt(n, decimals = 0) {
  if (n === null || n === undefined) return "N/A";
  return Number(n).toLocaleString("en-US", { maximumFractionDigits: decimals, minimumFractionDigits: decimals });
}

function fmtTco2(n) { return fmt(n, 0); }

function changeText(pct) {
  if (pct === null || pct === undefined) return "no prior-year data";
  const arrow = pct >= 0 ? "\u25b2" : "\u25bc";
  return `${arrow} ${Math.abs(pct).toFixed(1)}% vs previous year`;
}

function setHealth(ok) {
  const el = document.getElementById("health-badge");
  el.textContent = ok ? "API connected" : "API unreachable";
  el.className = "health-badge " + (ok ? "ok" : "down");
}

async function loadDashboard() {
  try {
    const [yoy, intensity, hotspot, monthly] = await Promise.all([
      api("/api/analytics/yoy"),
      api("/api/analytics/intensity"),
      api("/api/analytics/hotspot"),
      api("/api/analytics/monthly"),
    ]);
    setHealth(true);
    renderKpis(yoy, intensity);
    renderYoy(yoy);
    renderHotspot(hotspot);
    renderMonthly(monthly);
  } catch (e) {
    setHealth(false);
    console.error(e);
  }
}

function renderKpis(yoy, intensity) {
  document.getElementById("kpi-yoy-year").textContent =
    `Total Emissions ${yoy.current_year} (tCO2e)`;
  document.getElementById("kpi-total").textContent = fmtTco2(yoy.current.total);
  const totalEl = document.getElementById("kpi-total-change");
  totalEl.textContent = changeText(yoy.change_pct.total);
  totalEl.className = "kpi-sub " + (yoy.change_pct.total >= 0 ? "up" : "down");

  document.getElementById("kpi-intensity").textContent = fmt(intensity.intensity_kgco2e_per_unit, 0);
  document.getElementById("kpi-intensity-sub").textContent =
    `${intensity.metric_name}: ${fmt(intensity.metric_value)} (${intensity.start_date} \u2192 ${intensity.end_date})`;

  document.getElementById("kpi-scope1").textContent = fmtTco2(yoy.current.scope_1);
  const s1El = document.getElementById("kpi-scope1-change");
  s1El.textContent = changeText(yoy.change_pct.scope_1);
  s1El.className = "kpi-sub " + (yoy.change_pct.scope_1 >= 0 ? "up" : "down");

  document.getElementById("kpi-scope2").textContent = fmtTco2(yoy.current.scope_2);
  const s2El = document.getElementById("kpi-scope2-change");
  s2El.textContent = changeText(yoy.change_pct.scope_2);
  s2El.className = "kpi-sub " + (yoy.change_pct.scope_2 >= 0 ? "up" : "down");
}

function renderYoy(yoy) {
  const ctx = document.getElementById("yoyChart");
  if (yoyChart) yoyChart.destroy();
  yoyChart = new Chart(ctx, {
    type: "bar",
    data: {
      labels: [String(yoy.previous_year), String(yoy.current_year)],
      datasets: [
        {
          label: "Scope 1 (Direct)",
          data: [yoy.previous.scope_1, yoy.current.scope_1].map(v => +(v / 1e6).toFixed(2)),
          backgroundColor: "#264653",
        },
        {
          label: "Scope 2 (Indirect)",
          data: [yoy.previous.scope_2, yoy.current.scope_2].map(v => +(v / 1e6).toFixed(2)),
          backgroundColor: "#2a9d8f",
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: {
        x: { stacked: true },
        y: { stacked: true, title: { display: true, text: "ktCO2e" } },
      },
    },
  });
}

function renderHotspot(hotspot) {
  const ctx = document.getElementById("hotspotChart");
  const top = hotspot.breakdown.slice(0, 8);
  const rest = hotspot.breakdown.slice(8);
  const labels = top.map(i => i.source);
  const data = top.map(i => i.share_pct);
  if (rest.length) {
    labels.push("Other");
    data.push(+rest.reduce((a, i) => a + i.share_pct, 0).toFixed(2));
  }
  const palette = ["#264653", "#2a9d8f", "#e9c46a", "#f4a261", "#e76f51", "#6a994e", "#8ecae6", "#bc6c25", "#adb5bd"];
  if (hotspotChart) hotspotChart.destroy();
  hotspotChart = new Chart(ctx, {
    type: "doughnut",
    data: {
      labels,
      datasets: [{ data, backgroundColor: palette.slice(0, labels.length), borderWidth: 1 }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      plugins: {
        legend: { position: "right", labels: { boxWidth: 12, font: { size: 10 } } },
        tooltip: {
          callbacks: {
            label: (item) => {
              const src = hotspot.breakdown[item.dataIndex];
              return src
                ? ` ${item.label}: ${item.parsed.toFixed(2)}% (${fmtTco2(src.emissions_tco2e)} tCO2e)`
                : ` Other: ${item.parsed.toFixed(2)}%`;
            },
          },
        },
      },
    },
  });
}

function renderMonthly(monthly) {
  const ctx = document.getElementById("monthlyChart");
  document.getElementById("monthly-year-label").textContent = `(${monthly.year})`;
  const div = (v) => +(v / 1e6).toFixed(2);
  if (monthlyChart) monthlyChart.destroy();
  monthlyChart = new Chart(ctx, {
    type: "line",
    data: {
      labels: monthly.months.map(m => m.month),
      datasets: [
        {
          label: "Scope 1",
          data: monthly.months.map(m => div(m.scope_1)),
          borderColor: "#264653", backgroundColor: "rgba(38,70,83,0.1)", tension: 0.3, fill: true,
        },
        {
          label: "Scope 2",
          data: monthly.months.map(m => div(m.scope_2)),
          borderColor: "#2a9d8f", backgroundColor: "rgba(42,157,143,0.1)", tension: 0.3, fill: true,
        },
        {
          label: "Scope 3",
          data: monthly.months.map(m => div(m.scope_3)),
          borderColor: "#e9c46a", backgroundColor: "rgba(233,196,106,0.1)", tension: 0.3, fill: true,
        },
        {
          label: "Total",
          data: monthly.months.map(m => div(m.total)),
          borderColor: "#e76f51", tension: 0.3, borderDash: [5, 4], fill: false,
        },
      ],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      animation: false,
      scales: { y: { title: { display: true, text: "ktCO2e" } } },
    },
  });
}

async function loadFactorOptions() {
  const [scopeSel, activitySel] = [document.getElementById("f-scope"), document.getElementById("f-activity")];
  const today = new Date().toISOString().slice(0, 10);
  const factors = await api(`/api/factors?scope=${scopeSel.value}&valid_on=${today}`);
  activitySel.innerHTML = "";
  for (const f of factors) {
    const opt = document.createElement("option");
    opt.value = f.activity;
    opt.textContent = `${f.activity} (${f.unit})`;
    opt.dataset.unit = f.unit;
    activitySel.appendChild(opt);
  }
  updateFactorPreview();
}

async function updateFactorPreview() {
  const activity = document.getElementById("f-activity").value;
  const date = document.getElementById("f-date").value;
  const box = document.getElementById("factor-preview");
  if (!activity || !date) { box.textContent = "Select an activity and date to preview the emission factor the engine will use."; return; }
  try {
    const f = await api(`/api/factors/resolve?activity=${encodeURIComponent(activity)}&on=${date}`);
    box.innerHTML = `Engine will use <strong>v${f.version}</strong> (${f.valid_from} \u2192 ${f.valid_to || "open"}): ` +
      `<strong>${fmt(f.co2e_per_unit, 4)} kgCO2e/${f.unit}</strong> &middot; source: ${f.source}`;
  } catch (e) {
    box.textContent = e.message;
  }
}

async function loadTables() {
  const [records, audit] = await Promise.all([
    api("/api/records?limit=10"),
    api("/api/audit-log?limit=10"),
  ]);

  const recBody = document.querySelector("#records-table tbody");
  recBody.innerHTML = "";
  for (const r of records) {
    const tr = document.createElement("tr");
    const tco2 = (r.effective_emissions / 1000).toLocaleString("en-US", { maximumFractionDigits: 0 });
    tr.innerHTML =
      `<td>${r.id}</td><td>${r.activity_date}</td><td><span class="badge calculated">S${r.scope}</span></td>` +
      `<td>${r.activity}</td><td>${r.section}</td><td>${fmt(r.quantity, 1)}</td><td>${r.unit}</td>` +
      `<td>${tco2}</td>` +
      `<td><span class="badge ${r.overridden ? "overridden" : "calculated"}">${r.overridden ? "overridden" : "calculated"}</span></td>` +
      `<td><button class="override-btn" data-id="${r.id}" data-overridden="${r.overridden}">${r.overridden ? "Revert" : "Override"}</button></td>`;
    recBody.appendChild(tr);
  }
  recBody.querySelectorAll(".override-btn").forEach(btn => {
    btn.addEventListener("click", () => onOverrideClick(btn));
  });

  const auditBody = document.querySelector("#audit-table tbody");
  auditBody.innerHTML = "";
  if (!audit.length) {
    auditBody.innerHTML = '<tr><td colspan="8">No overrides recorded yet.</td></tr>';
  }
  for (const a of audit) {
    const tr = document.createElement("tr");
    tr.innerHTML =
      `<td>${a.id}</td><td>${a.record_id}</td><td><span class="badge ${a.action.toLowerCase()}">${a.action}</span></td>` +
      `<td>${fmt(a.old_value_kgco2e, 0)}</td><td>${fmt(a.new_value_kgco2e, 0)}</td>` +
      `<td>${a.reason}</td><td>${a.changed_by}</td><td>${a.changed_at.replace("T", " ").slice(0, 19)}</td>`;
    auditBody.appendChild(tr);
  }
}

async function onOverrideClick(btn) {
  const id = btn.dataset.id;
  const overridden = btn.dataset.overridden === "true";
  try {
    if (overridden) {
      await api(`/api/records/${id}/override`, { method: "DELETE" });
    } else {
      const newValue = prompt(`Record #${id}: new emissions value (kgCO2e)`);
      if (newValue === null) return;
      const reason = prompt("Reason for the override:");
      if (reason === null) return;
      const changedBy = prompt("Your name / user id:", "dashboard.user");
      if (changedBy === null) return;
      await api(`/api/records/${id}/override`, {
        method: "PATCH",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ new_value_kgco2e: Number(newValue), reason, changed_by: changedBy }),
      });
    }
    await Promise.all([loadTables(), loadDashboard()]);
  } catch (e) {
    alert("Override failed: " + e.message);
  }
}

async function initForms() {
  const recordForm = document.getElementById("record-form");
  const scopeSel = document.getElementById("f-scope");
  const dateInput = document.getElementById("f-date");
  dateInput.value = new Date().toISOString().slice(0, 10);

  const metricNames = await api("/api/business-metrics/names");
  const nameSel = document.getElementById("m-name");
  for (const n of metricNames) {
    const opt = document.createElement("option");
    opt.value = n;
    opt.textContent = n;
    nameSel.appendChild(opt);
  }

  scopeSel.addEventListener("change", loadFactorOptions);
  document.getElementById("f-activity").addEventListener("change", updateFactorPreview);
  dateInput.addEventListener("change", updateFactorPreview);
  await loadFactorOptions();

  recordForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = document.getElementById("record-msg");
    msg.className = "msg";
    msg.textContent = "";
    const payload = {
      scope: Number(scopeSel.value),
      activity: document.getElementById("f-activity").value,
      section: document.getElementById("f-section").value,
      quantity: Number(document.getElementById("f-quantity").value),
      unit: document.getElementById("f-activity").selectedOptions[0].dataset.unit,
      activity_date: dateInput.value,
    };
    try {
      const rec = await api("/api/records", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      msg.className = "msg success";
      msg.textContent = `Saved record #${rec.id}: ${fmt(rec.emissions_kgco2e, 0)} kgCO2e ` +
        `(factor v used: ${fmt(rec.factor_value_used, 4)} kgCO2e/${rec.unit}).`;
      recordForm.reset();
      dateInput.value = new Date().toISOString().slice(0, 10);
      await Promise.all([loadTables(), loadDashboard()]);
    } catch (err) {
      msg.className = "msg error";
      msg.textContent = "Failed: " + err.message;
    }
  });

  const metricForm = document.getElementById("metric-form");
  metricForm.addEventListener("submit", async (e) => {
    e.preventDefault();
    const msg = document.getElementById("metric-msg");
    msg.className = "msg";
    msg.textContent = "";
    const payload = {
      date: document.getElementById("m-date").value,
      metric_name: nameSel.value,
      value: Number(document.getElementById("m-value").value),
      unit: document.getElementById("m-unit").value || "units",
    };
    try {
      const m = await api("/api/business-metrics", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      msg.className = "msg success";
      msg.textContent = `Saved metric: ${m.metric_name} = ${fmt(m.value)} ${m.unit} on ${m.date}.`;
      metricForm.reset();
      document.getElementById("m-date").value = new Date().toISOString().slice(0, 10);
      await loadDashboard();
    } catch (err) {
      msg.className = "msg error";
      msg.textContent = "Failed: " + err.message;
    }
  });
}

window.addEventListener("DOMContentLoaded", async () => {
  try {
    await initForms();
    await Promise.all([loadDashboard(), loadTables()]);
  } catch (e) {
    setHealth(false);
    console.error(e);
  }
});
