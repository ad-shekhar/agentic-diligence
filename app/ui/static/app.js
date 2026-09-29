// Agentic Diligence Dashboard Logic

let currentReportData = null;
let currentCompanyId = null;

document.addEventListener("DOMContentLoaded", () => {
  setupTabs();
  setupScenarioPicker();
  setupClaimFilters();
  setupDrawer();
  setupUploadModal();
  setupComparison();
  setupStressSimulatorControls();
  
  // Initial load: run default benchmark (scenario_a)
  loadScenario("scenario_a");
});

// Tab Navigation
function setupTabs() {
  const tabs = document.querySelectorAll(".tab-btn");
  tabs.forEach(btn => {
    btn.addEventListener("click", () => {
      tabs.forEach(t => t.classList.remove("active"));
      document.querySelectorAll(".tab-content").forEach(c => c.classList.remove("active"));
      
      btn.classList.add("active");
      const targetId = btn.getAttribute("data-tab");
      const targetEl = document.getElementById(targetId);
      if (targetEl) targetEl.classList.add("active");
    });
  });
}

// Scenario Picker
function setupScenarioPicker() {
  const select = document.getElementById("scenario-select");
  const runBtn = document.getElementById("btn-run-scenario");
  
  runBtn.addEventListener("click", () => {
    loadScenario(select.value);
  });
  
  select.addEventListener("change", () => {
    loadScenario(select.value);
  });
}

async function loadScenario(scenarioName) {
  try {
    document.getElementById("target-name-badge").innerText = `Running ${scenarioName}...`;
    const res = await fetch(`/api/v1/scenarios/${scenarioName}/run`, { credentials: "same-origin" });
    if (!res.ok) throw new Error(`Server returned ${res.status}`);
    const data = await res.json();
    renderReport(data);
  } catch (err) {
    console.error("Failed to load scenario:", err);
    alert(`Error loading scenario ${scenarioName}: ${err.message}`);
  }
}

// Render the Entire Diligence Package
function renderReport(data) {
  currentReportData = data;
  currentCompanyId = data.company?.id;

  // Header Badges
  document.getElementById("target-name-badge").innerText = `Target: ${data.company?.name || "N/A"}`;
  document.getElementById("observation-window-badge").innerText = `Window: ${data.observation_window || "Last 30 Days"}`;
  document.getElementById("pricing-badge").innerText = `Pricing: ${data.report_metadata?.pricing_version || "v2026_09"}`;

  // KPI Strip
  const intRes = data.interventions || {};
  document.getElementById("kpi-autonomy").innerText = `${intRes.autonomous_rate_pct ?? "--"}%`;
  document.getElementById("kpi-hir").innerText = `${intRes.human_intervention_rate_pct ?? "--"}% Human Intervention (HIR)`;

  const econ = data.economics || {};
  document.getElementById("kpi-cost").innerText = `$${Number(econ.telemetry_attributable_cost_per_task_usd || 0).toFixed(4)}`;
  document.getElementById("kpi-cost-status").innerText = `Status: ${econ.overall_cost_status || "MEASURED"}`;

  const casc = data.cascades || {};
  document.getElementById("kpi-cascade").innerText = `${casc.avg_cost_multiplier_on_failure || 1.0}x`;
  document.getElementById("kpi-cascade-pct").innerText = `${casc.cascade_frequency_pct || 0}% Traces in Recovery Loops`;

  const evalRes = data.evaluation || {};
  document.getElementById("kpi-trust-tax").innerText = `${evalRes.trust_tax_rate_pct ?? "--"}%`;
  document.getElementById("kpi-eval-coverage").innerText = `Coverage: ${evalRes.eval_coverage_pct ?? "--"}% of Traces`;

  const dep = data.dependencies || {};
  document.getElementById("kpi-hhi").innerText = dep.hhi_score ?? "--";
  const primaryShare = dep.providers && dep.providers[0] ? dep.providers[0].share_pct : "--";
  document.getElementById("kpi-vendor-share").innerText = `${primaryShare}% Primary Share`;

  // Render Tabs
  renderClaimMatrix(data.claims || []);
  renderAIBOM(data.aibom || {});
  renderCascadesAndSPOF(data.cascades || {}, data.dependencies || {});
  renderEvidenceGraph(data.evidence_records || []);
  renderToolRisk(data.tool_risk || {});
  renderDefensibility(data.defensibility || {});
  renderStressTest(data.stress_test || {});
  renderDiligenceMemo(data.memo || {});
  
  // Download Links
  setupDownloadLinks(data);
}

// 1. Claim Verification Matrix
function renderClaimMatrix(claims) {
  const tbody = document.getElementById("claims-tbody");
  tbody.innerHTML = "";

  let counts = { all: claims.length, VERIFIED: 0, PARTIALLY_VERIFIED: 0, CONTRADICTED: 0 };

  claims.forEach((c, idx) => {
    const status = c.verification_status || "UNVERIFIED";
    if (counts[status] !== undefined) counts[status]++;

    const tr = document.createElement("tr");
    tr.className = `claim-row status-filter-${status}`;
    
    let statusClass = "status-unverified";
    let statusLabel = status;
    if (status === "VERIFIED") {
      statusClass = "status-verified";
    } else if (status === "PARTIALLY_VERIFIED") {
      statusClass = "status-partial";
      statusLabel = "PARTIAL";
    } else if (status === "CONTRADICTED") {
      statusClass = "status-contradicted";
    }

    tr.innerHTML = `
      <td><span class="meta-tag" style="text-transform: capitalize;">${c.category || "General"}</span></td>
      <td><strong>${escapeHtml(c.claim_text)}</strong><br/><span style="font-size: 11px; color: var(--text-dim);">${escapeHtml(c.source || "")}</span></td>
      <td>
        <span style="font-family: var(--font-mono); font-size: 12px; color: #E2E8F0;">${escapeHtml(c.observed_value || "N/A")}</span>
        <div style="font-size: 11px; color: var(--text-dim); margin-top: 3px;">${escapeHtml(c.verification_reason || "")}</div>
      </td>
      <td><span class="status-pill ${statusClass}">${statusLabel}</span></td>
      <td><span class="meta-tag">${c.confidence || "High"}</span></td>
      <td><button class="btn btn-sm btn-outline btn-inspect" data-index="${idx}">Inspect ↗</button></td>
    `;

    tbody.appendChild(tr);
  });

  document.getElementById("count-all").innerText = counts.all;
  document.getElementById("count-verified").innerText = counts.VERIFIED;
  document.getElementById("count-partial").innerText = counts.PARTIALLY_VERIFIED;
  document.getElementById("count-contradicted").innerText = counts.CONTRADICTED;

  // Add click listeners to inspect buttons
  document.querySelectorAll(".btn-inspect").forEach(btn => {
    btn.addEventListener("click", () => {
      const idx = parseInt(btn.getAttribute("data-index"), 10);
      openClaimDrawer(claims[idx]);
    });
  });
}

function setupClaimFilters() {
  const pills = document.querySelectorAll("#claim-filters .pill");
  pills.forEach(pill => {
    pill.addEventListener("click", () => {
      pills.forEach(p => p.classList.remove("active"));
      pill.classList.add("active");
      const filter = pill.getAttribute("data-filter");
      
      const rows = document.querySelectorAll(".claim-row");
      rows.forEach(r => {
        if (filter === "all" || r.classList.contains(`status-filter-${filter}`)) {
          r.style.display = "";
        } else {
          r.style.display = "none";
        }
      });
    });
  });
}

// Claim Detail Drawer
function setupDrawer() {
  const drawer = document.getElementById("claim-drawer");
  const overlay = document.getElementById("drawer-overlay");
  const closeBtn = document.getElementById("drawer-close");

  const close = () => {
    drawer.classList.remove("active");
    overlay.classList.remove("active");
  };

  closeBtn.addEventListener("click", close);
  overlay.addEventListener("click", close);
}

function openClaimDrawer(claim) {
  const drawer = document.getElementById("claim-drawer");
  const overlay = document.getElementById("drawer-overlay");

  document.getElementById("drawer-category").innerText = (claim.category || "General").toUpperCase();
  document.getElementById("drawer-title").innerText = claim.claim_text;

  const status = claim.verification_status || "UNVERIFIED";
  const badge = document.getElementById("drawer-status-badge");
  badge.className = `status-pill ${status === "VERIFIED" ? "status-verified" : (status === "PARTIALLY_VERIFIED" ? "status-partial" : "status-contradicted")}`;
  badge.innerText = status;

  document.getElementById("drawer-confidence-badge").innerText = `Confidence: ${claim.confidence || "High"}`;
  document.getElementById("drawer-status-reason").innerText = claim.verification_reason || "";

  document.getElementById("drawer-claim-text").innerText = claim.claim_text;
  document.getElementById("drawer-source").innerText = `Source: ${claim.source || "Pitch Deck"}`;

  // Find linked evidence record
  const evd = (currentReportData.evidence_records || []).find(e => 
    e.claim_summary?.toLowerCase().includes(claim.category?.toLowerCase()) ||
    claim.claim_text.includes(e.claim_summary) ||
    e.claim_summary === claim.claim_text
  ) || (currentReportData.evidence_records || [])[0] || {};

  document.getElementById("drawer-observed-fact").innerText = evd.observed_fact || claim.observed_value || "Observed in telemetry traces.";
  document.getElementById("drawer-derived-metric").innerText = evd.derived_metric_summary || "Autonomous completion rate & unit costs calculated deterministically.";
  document.getElementById("drawer-methodology").innerText = evd.verification_method || "Deterministic span aggregation & boundary thresholds.";
  document.getElementById("drawer-datasource").innerText = evd.data_source_description || "OpenTelemetry GenAI trace spans.";
  document.getElementById("drawer-limitations").innerText = evd.limitations || "Only instrumented spans in the observation window were evaluated.";

  drawer.classList.add("active");
  overlay.classList.add("active");
}

// 2. AIBOM Explorer
function renderAIBOM(bom) {
  document.getElementById("aibom-id-badge").innerText = `BOM ID: ${bom.bom_id || "BOM-ACTIVE"}`;
  
  // Models Table
  const modelsTbody = document.getElementById("models-tbody");
  modelsTbody.innerHTML = "";
  const models = bom.models || [];
  document.getElementById("models-count").innerText = models.length;

  models.forEach(m => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${escapeHtml(m.model_name)}</strong> ${m.is_primary ? '<span class="status-pill status-verified" style="font-size: 9px;">PRIMARY</span>' : ''}</td>
      <td>${escapeHtml(m.provider_name)}</td>
      <td><span class="meta-tag">${m.hosting_type}</span></td>
      <td style="font-family: var(--font-mono);">${Number(m.total_prompt_tokens).toLocaleString()}</td>
      <td style="font-family: var(--font-mono);">${Number(m.total_completion_tokens).toLocaleString()}</td>
      <td style="font-family: var(--font-mono); color: #38BDF8;">$${Number(m.measured_cost_usd).toFixed(4)}</td>
    `;
    modelsTbody.appendChild(tr);
  });

  // Tools Table
  const toolsTbody = document.getElementById("tools-tbody");
  toolsTbody.innerHTML = "";
  const tools = bom.tools || [];
  document.getElementById("tools-count").innerText = tools.length;

  tools.forEach(t => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><code>${escapeHtml(t.tool_name)}</code></td>
      <td><span class="meta-tag">${t.tool_type}</span></td>
      <td style="font-family: var(--font-mono);">${t.call_count}</td>
      <td style="font-family: var(--font-mono); color: ${t.failure_count > 0 ? '#F87171' : '#CBD5E1'};">${t.failure_count}</td>
      <td style="font-family: var(--font-mono);">${t.failure_rate_pct}%</td>
      <td style="font-family: var(--font-mono);">${t.avg_latency_ms}ms</td>
    `;
    toolsTbody.appendChild(tr);
  });

  // Vector Stores
  const vsContainer = document.getElementById("vector-stores-list");
  vsContainer.innerHTML = "";
  (bom.vector_stores || []).forEach(vs => {
    const div = document.createElement("div");
    div.className = "tag-item";
    div.innerHTML = `
      <div class="tag-item-title">System: ${escapeHtml(vs.system_name)}</div>
      <div class="tag-item-sub">Embedding: ${escapeHtml(vs.embedding_model || "unspecified")} | Usage: ${vs.usage_count} spans</div>
    `;
    vsContainer.appendChild(div);
  });
  if ((bom.vector_stores || []).length === 0) {
    vsContainer.innerHTML = `<span style="color: var(--text-dim); font-size: 12px;">No dedicated vector database spans observed.</span>`;
  }

  // Human Checkpoints
  const hcContainer = document.getElementById("human-checkpoints-list");
  hcContainer.innerHTML = "";
  (bom.human_checkpoints || []).forEach(hc => {
    const div = document.createElement("div");
    div.className = "tag-item";
    div.innerHTML = `
      <div class="tag-item-title">${escapeHtml(hc.checkpoint_type)}</div>
      <div class="tag-item-sub">Detection: ${escapeHtml(hc.detection_method)} | Triggers: ${hc.trigger_count} | Avg Reaction: ${hc.avg_reaction_time_seconds}s</div>
    `;
    hcContainer.appendChild(div);
  });
  if ((bom.human_checkpoints || []).length === 0) {
    hcContainer.innerHTML = `<span style="color: var(--text-dim); font-size: 12px;">No human checkpoint spans detected.</span>`;
  }
}

// 3. Cascades & Potential SPOFs
function renderCascadesAndSPOF(casc, dep) {
  document.getElementById("cascade-statement").innerText = casc.economic_impact_statement || "No failure cascades detected.";
  const badge = document.getElementById("cascade-stat-badge");
  if ((casc.cascade_frequency_pct || 0) > 0) {
    badge.innerText = `${casc.cascade_frequency_pct}% Cascading (${casc.avg_cost_multiplier_on_failure}x cost multiplier)`;
    badge.className = "status-pill status-partial";
  } else {
    badge.innerText = "0% Cascades (Clean Execution)";
    badge.className = "status-pill status-verified";
  }

  // Visual flow box
  const flowBox = document.getElementById("cascade-flow-visual");
  flowBox.innerHTML = `
    <div class="flow-step">
      <div class="flow-step-name">1. Orchestrator Agent</div>
      <div class="flow-step-meta">Workflow Start</div>
    </div>
    <div class="flow-arrow">→</div>
    <div class="flow-step">
      <div class="flow-step-name">2. LLM Call #1</div>
      <div class="flow-step-meta">Initial Generation</div>
    </div>
    <div class="flow-arrow">→</div>
    <div class="flow-step" style="border-color: #EF4444;">
      <div class="flow-step-name" style="color: #F87171;">3. Tool Call [FAIL]</div>
      <div class="flow-step-meta">504 Gateway Timeout</div>
    </div>
    <div class="flow-arrow">→</div>
    <div class="flow-step" style="border-color: #F59E0B;">
      <div class="flow-step-name" style="color: #FBBF24;">4. Retry LLM Call</div>
      <div class="flow-step-meta">+150% Prompt Tokens</div>
    </div>
    <div class="flow-arrow">→</div>
    <div class="flow-step">
      <div class="flow-step-name">5. Fallback Tool</div>
      <div class="flow-step-meta">Knowledge Docs</div>
    </div>
    <div class="flow-arrow">→</div>
    <div class="flow-step">
      <div class="flow-step-name">6. Human Review</div>
      <div class="flow-step-meta">Escalation Gap: 3.3s</div>
    </div>
  `;

  // SPOF Table
  const spofTbody = document.getElementById("spof-tbody");
  spofTbody.innerHTML = "";
  const spofs = dep.potential_spofs || [];

  spofs.forEach(s => {
    const tr = document.createElement("tr");
    const isMitigated = (s.risk_status || "").includes("MITIGATED");
    const riskBadge = `<span class="status-pill ${isMitigated ? 'status-partial' : 'status-contradicted'}">${s.risk_status}</span>`;

    tr.innerHTML = `
      <td><strong>${escapeHtml(s.component_name)}</strong></td>
      <td><span class="meta-tag">${s.component_type}</span></td>
      <td style="font-family: var(--font-mono);">${s.dependency_share_pct}%</td>
      <td>${s.fallback_observed ? '<span style="color: #10B981;">✓ Observed in Spans</span>' : '<span style="color: #EF4444;">✗ No Fallback Observed</span>'}</td>
      <td>${s.fallback_tested ? '<span style="color: #10B981;">✓ Exercised</span>' : '<span style="color: var(--text-dim);">Untested</span>'}</td>
      <td><span style="font-size: 11px; color: var(--text-dim);">${escapeHtml(s.failure_evidence ? s.failure_evidence.join("; ") : "None")}</span></td>
      <td>${riskBadge}</td>
    `;
    spofTbody.appendChild(tr);
  });

  if (spofs.length === 0) {
    spofTbody.innerHTML = `<tr><td colspan="7" style="color: var(--text-dim); text-align: center;">No critical component dependencies exceeding 65% share detected.</td></tr>`;
  }
}

// 4. Auditable Evidence Graph
function renderEvidenceGraph(records) {
  const tbody = document.getElementById("evidence-tbody");
  tbody.innerHTML = "";

  records.forEach(e => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><code style="color: var(--accent-cyan); font-weight: 700;">${e.evidence_code}</code></td>
      <td><span class="meta-tag" style="color: #38BDF8;">${e.evidence_type}</span></td>
      <td><span class="meta-tag">${e.confidence || "High"}</span></td>
      <td><strong>${escapeHtml(e.claim_summary)}</strong></td>
      <td>
        <div>${escapeHtml(e.observed_fact)}</div>
        <div style="font-size: 11px; color: var(--text-dim); margin-top: 4px;"><strong>Derived:</strong> ${escapeHtml(e.derived_metric_summary || "")}</div>
      </td>
      <td>
        <div>${escapeHtml(e.verification_method)}</div>
        <div style="font-size: 10px; color: var(--text-dim); margin-top: 2px;">Source: ${escapeHtml(e.data_source_description)}</div>
      </td>
    `;
    tbody.appendChild(tr);
  });
}

// 5. Cryptographic Chain-of-Custody Manifest
function renderManifest(manifest) {
  document.getElementById("manifest-id-val").innerText = `Manifest ID: ${manifest.manifest_id || "MAN-ACTIVE"}`;
  
  const p1 = manifest.pipeline_stages?.["1_telemetry_input"] || {};
  document.getElementById("manifest-input-hash").innerText = p1.aggregate_telemetry_sha256 || "--";
  document.getElementById("manifest-trace-count").innerText = `Traces Analyzed: ${p1.trace_count || 0}`;

  const p2 = manifest.pipeline_stages?.["2_normalization"] || {};
  document.getElementById("manifest-norm-ver").innerText = p2.version || "v0.1.0-norm";

  const p3 = manifest.pipeline_stages?.["3_deterministic_analysis"] || {};
  document.getElementById("manifest-engine-ver").innerText = p3.version || "v0.1.0-engine";

  const p4 = manifest.pipeline_stages?.["4_pricing_model"] || {};
  document.getElementById("manifest-pricing-ver").innerText = p4.table_version || "v2026_09";

  const p5 = manifest.pipeline_stages?.["5_evidence_graph"] || {};
  document.getElementById("manifest-evidence-hash").innerText = p5.evidence_graph_sha256 || "--";

  const seal = manifest.chain_of_custody_seal || {};
  document.getElementById("manifest-master-seal").innerText = seal.digest || "--";

  // Artifacts Table
  const tbody = document.getElementById("artifacts-tbody");
  tbody.innerHTML = "";
  const artifacts = manifest.artifacts || {};

  Object.entries(artifacts).forEach(([key, art]) => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${art.filename}</strong></td>
      <td><span class="meta-tag">${art.mime_type}</span></td>
      <td><code class="hash-box" style="display: inline-block;">${art.sha256}</code></td>
    `;
    tbody.appendChild(tr);
  });

  // Copy Manifest JSON button
  document.getElementById("btn-copy-manifest").onclick = () => {
    navigator.clipboard.writeText(JSON.stringify(manifest, null, 2));
    alert("Chain-of-Custody Manifest JSON copied to clipboard!");
  };
}

// Setup Download Links
function setupDownloadLinks(data) {
  const companySlug = data.company?.name.toLowerCase().replace(/\s+/g, '_').replace(/[()]/g, '') || "target";

  const setDl = (elemId, filename, mime, content) => {
    const el = document.getElementById(elemId);
    if (!el) return;
    const blob = new Blob([content], { type: mime });
    el.href = URL.createObjectURL(blob);
    el.download = filename;
  };

  setDl("dl-json", `diligence_package_${companySlug}.json`, "application/json", JSON.stringify(data, null, 2));
  setDl("dl-aibom-native", `aibom_native_${companySlug}.json`, "application/json", JSON.stringify(data.aibom || {}, null, 2));
  setDl("dl-manifest", `audit_manifest_${companySlug}.json`, "application/json", JSON.stringify(data.audit_manifest || {}, null, 2));

  // CycloneDX export
  const btnExportCDX = document.getElementById("btn-export-cyclonedx");
  if (btnExportCDX) {
    btnExportCDX.onclick = async () => {
      if (!currentCompanyId) return;
      const res = await fetch(`/api/v1/companies/${currentCompanyId}/aibom/cyclonedx`);
      const cdx = await res.json();
      const blob = new Blob([JSON.stringify(cdx, null, 2)], { type: "application/json" });
      const a = document.createElement("a");
      a.href = URL.createObjectURL(blob);
      a.download = `aibom_cyclonedx_${companySlug}.json`;
      a.click();
    };
  }

  // PDF direct link
  const pdfLink = document.getElementById("dl-pdf");
  if (pdfLink && currentCompanyId) {
    pdfLink.href = `/api/v1/companies/${currentCompanyId}/pdf`;
  }
}

// Setup Upload Modal
function setupUploadModal() {
  const modal = document.getElementById("upload-modal");
  const openBtn = document.getElementById("btn-open-upload");
  const closeBtn = document.getElementById("modal-close");
  const cancelBtn = document.getElementById("btn-cancel-upload");
  const dropzone = document.getElementById("dropzone");
  const fileInput = document.getElementById("file-input");
  const submitBtn = document.getElementById("btn-submit-upload");
  const targetNameInput = document.getElementById("upload-target-name");

  let selectedFile = null;

  openBtn.addEventListener("click", () => modal.classList.add("active"));
  const closeModal = () => {
    modal.classList.remove("active");
    selectedFile = null;
    document.getElementById("selected-file-name").innerText = "";
    submitBtn.disabled = true;
  };

  closeBtn.addEventListener("click", closeModal);
  cancelBtn.addEventListener("click", closeModal);

  dropzone.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length > 0) {
      selectedFile = e.target.files[0];
      document.getElementById("selected-file-name").innerText = `Selected: ${selectedFile.name} (${(selectedFile.size / 1024).toFixed(1)} KB)`;
      submitBtn.disabled = false;
    }
  });

  submitBtn.addEventListener("click", async () => {
    if (!selectedFile) return;
    const targetName = targetNameInput.value.trim() || "Uploaded AI Target";
    submitBtn.innerText = "Ingesting & Analyzing...";
    submitBtn.disabled = true;

    try {
      const text = await selectedFile.text();
      const payload = JSON.parse(text);

      const res = await fetch("/api/v1/telemetry/upload", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          company_name: targetName,
          payload: payload
        })
      });

      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      closeModal();
      renderReport(data);
      alert(`Diligence package generated for ${targetName}!`);
    } catch (err) {
      alert(`Error parsing telemetry: ${err.message}`);
    } finally {
      submitBtn.innerText = "Process & Verify Traces";
      submitBtn.disabled = false;
    }
  });
}

function escapeHtml(text) {
  if (!text) return "";
  return String(text)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

// Setup Download Links
function setupDownloadLinks(data) {
  const compId = data.company?.id;
  if (!compId) return;
  
  const dlPdf = document.getElementById("dl-pdf");
  if (dlPdf) dlPdf.href = `/api/v1/companies/${compId}/pdf`;
  
  const dlBundle = document.getElementById("dl-bundle");
  if (dlBundle) dlBundle.href = `/api/v1/companies/${compId}/bundle`;

  const dlMemo = document.getElementById("dl-memo");
  if (dlMemo) dlMemo.href = `/api/v1/companies/${compId}/memo`;

  const dlJson = document.getElementById("dl-json");
  if (dlJson) dlJson.href = `/api/v1/companies/${compId}/package`;
  
  const dlAibomNative = document.getElementById("dl-aibom-native");
  if (dlAibomNative) dlAibomNative.href = `/api/v1/companies/${compId}/aibom`;
  
  const dlCyclonedx = document.getElementById("dl-cyclonedx");
  if (dlCyclonedx) dlCyclonedx.href = `/api/v1/companies/${compId}/aibom/cyclonedx`;
  
  const dlManifest = document.getElementById("dl-manifest");
  if (dlManifest) dlManifest.href = `/api/v1/companies/${compId}/manifest`;
}

// 6. Tool Risk & Privilege Audit
function renderToolRisk(risk) {
  const scoreEl = document.getElementById("tool-risk-score");
  if (scoreEl) scoreEl.innerText = risk.tool_risk_score ?? "--";
  
  const invEl = document.getElementById("tool-total-invocations");
  if (invEl) invEl.innerText = risk.total_tool_calls ?? "--";
  
  const perTraceEl = document.getElementById("tool-per-trace-sub");
  if (perTraceEl) perTraceEl.innerText = `${risk.tool_invocation_rate_per_trace ?? "--"} calls / trace`;
  
  const failRateEl = document.getElementById("tool-failure-rate");
  if (failRateEl) failRateEl.innerText = `${risk.tool_failure_rate_pct ?? "--"}%`;
  
  const failCountEl = document.getElementById("tool-failures-count");
  if (failCountEl) failCountEl.innerText = `${risk.tool_failure_count ?? 0} failures`;
  
  const highPrivEl = document.getElementById("tool-high-priv-rate");
  if (highPrivEl) highPrivEl.innerText = `${risk.high_or_critical_privilege_pct ?? "--"}%`;
  
  const unconstEl = document.getElementById("tool-unconstrained-traces");
  if (unconstEl) unconstEl.innerText = risk.unconstrained_execution_traces_count ?? 0;

  const levelBadge = document.getElementById("tool-risk-level-badge");
  if (levelBadge) {
    const lvl = risk.risk_level || "LOW";
    levelBadge.innerText = `Risk Level: ${lvl}`;
    levelBadge.className = `status-badge ${lvl === "CRITICAL" ? "status-contradicted" : (lvl === "ELEVATED" ? "status-partially-verified" : "status-verified")}`;
  }

  const tbody = document.getElementById("tool-inventory-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  (risk.tool_inventory || []).forEach(item => {
    const tr = document.createElement("tr");
    const privClass = item.privilege_level === "CRITICAL" ? "status-contradicted" : (item.privilege_level === "HIGH" ? "status-partially-verified" : "status-verified");
    tr.innerHTML = `
      <td><strong>${escapeHtml(item.tool_name)}</strong></td>
      <td><span class="status-badge ${privClass}">${item.privilege_level}</span></td>
      <td>${item.invocation_count}</td>
      <td>${item.error_count}</td>
      <td>${item.error_rate_pct}%</td>
      <td>${item.avg_latency_ms} ms</td>
    `;
    tbody.appendChild(tr);
  });
}

// 7. Comparative Diligence Audit
function setupComparison() {
  const btn = document.getElementById("btn-run-compare");
  if (!btn) return;

  btn.addEventListener("click", async () => {
    const targetA = document.getElementById("compare-target-a").value;
    const targetB = document.getElementById("compare-target-b").value;

    btn.innerText = "Comparing...";
    btn.disabled = true;

    try {
      const res = await fetch("/api/v1/comparison/scenarios", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ scenario_a: targetA, scenario_b: targetB, sample_size: 250 })
      });
      if (!res.ok) throw new Error(await res.text());
      const data = await res.json();
      renderComparisonResults(data);
    } catch (err) {
      alert(`Comparison failed: ${err.message}`);
    } finally {
      btn.innerText = "Run Comparative Audit";
      btn.disabled = false;
    }
  });
}

function renderComparisonResults(data) {
  const container = document.getElementById("compare-results-container");
  if (container) container.style.display = "block";

  const winners = data.dimension_winners || {};
  const winAuto = document.getElementById("winner-autonomy");
  if (winAuto) winAuto.innerText = winners.autonomy || "--";
  
  const winEcon = document.getElementById("winner-economics");
  if (winEcon) winEcon.innerText = winners.economics || "--";
  
  const winRes = document.getElementById("winner-resilience");
  if (winRes) winRes.innerText = winners.resilience || "--";
  
  const winGov = document.getElementById("winner-gov");
  if (winGov) winGov.innerText = winners.governance_and_safety || "--";

  const thA = document.getElementById("th-target-a");
  if (thA) thA.innerText = data.target_a?.name || "Target A";
  
  const thB = document.getElementById("th-target-b");
  if (thB) thB.innerText = data.target_b?.name || "Target B";

  const tbody = document.getElementById("compare-matrix-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  (data.matrix || []).forEach(row => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${escapeHtml(row.dimension)}</strong></td>
      <td style="color: #8892b0;">${escapeHtml(row.metric)}</td>
      <td>${escapeHtml(row.target_a_value)}</td>
      <td>${escapeHtml(row.target_b_value)}</td>
      <td style="font-family: monospace;">${escapeHtml(row.delta)}</td>
      <td><span class="status-badge status-verified">${escapeHtml(row.advantage)}</span></td>
    `;
    tbody.appendChild(tr);
  });
}

// 8. Defensibility & Moat Audit
function renderDefensibility(moat) {
  const scoreEl = document.getElementById("kpi-moat-score");
  if (scoreEl) scoreEl.innerText = `${moat.moat_score ?? "--"} / 100`;

  const classBadge = document.getElementById("moat-class-badge");
  const classSub = document.getElementById("kpi-moat-class");
  const mClass = moat.moat_classification || "COMMODITY_WRAPPER";
  if (classBadge) {
    classBadge.innerText = mClass.replace(/_/g, " ");
    classBadge.className = `status-badge ${mClass.includes("MOAT") || mClass.includes("COMPOUND") ? "status-verified" : (mClass.includes("LIGHT") ? "status-partially-verified" : "status-contradicted")}`;
  }
  if (classSub) classSub.innerText = `Classification: ${mClass.replace(/_/g, " ")}`;

  const scaffEl = document.getElementById("kpi-scaffolding-score");
  if (scaffEl) scaffEl.innerText = `${moat.scaffolding_complexity_score ?? "--"} / 25`;
  const spansPerTraceEl = document.getElementById("kpi-spans-per-trace");
  if (spansPerTraceEl) spansPerTraceEl.innerText = `${moat.breakdown?.avg_spans_per_trace ?? "--"} spans / trace`;

  const sovEl = document.getElementById("kpi-sovereignty-score");
  if (sovEl) sovEl.innerText = `${moat.weight_sovereignty_score ?? "--"} / 25`;
  const selfHostedRatioEl = document.getElementById("kpi-selfhosted-ratio");
  if (selfHostedRatioEl) selfHostedRatioEl.innerText = `${moat.breakdown?.self_hosted_llm_ratio_pct ?? "--"}% self-hosted/open`;

  const toolEl = document.getElementById("kpi-tool-score");
  if (toolEl) toolEl.innerText = `${moat.tool_integration_score ?? "--"} / 25`;
  const connEl = document.getElementById("kpi-connectors-count");
  if (connEl) connEl.innerText = `${moat.breakdown?.enterprise_connectors_count ?? 0} enterprise connectors`;

  const repMosEl = document.getElementById("kpi-replication-months");
  if (repMosEl) repMosEl.innerText = `~${moat.estimated_replication_months ?? "--"} mos`;
  const repCostEl = document.getElementById("kpi-replication-cost");
  if (repCostEl) repCostEl.innerText = `$${Number(moat.estimated_replication_cost_usd || 0).toLocaleString()} Capital Est.`;

  const narrativeBox = document.getElementById("moat-narrative-box");
  if (narrativeBox) narrativeBox.innerText = moat.verdict_summary || "No assessment generated.";

  const flywheelSub = document.getElementById("moat-flywheel-sub");
  if (flywheelSub) flywheelSub.innerText = `Data Flywheel: ${moat.data_flywheel_score ?? "--"} / 25`;

  const tbody = document.getElementById("moat-breakdown-tbody");
  if (!tbody) return;
  tbody.innerHTML = "";

  const b = moat.breakdown || {};
  const rows = [
    {
      dim: "Scaffolding Hierarchy",
      val: `${b.hierarchy_ratio_pct ?? 0}% nested spans`,
      bench: "> 60% for multi-agent loops",
      imp: b.hierarchy_ratio_pct >= 60 ? "Deep cognitive agent structure" : "Shallow orchestration"
    },
    {
      dim: "Model Sovereignty",
      val: `${b.self_hosted_llm_ratio_pct ?? 0}% self-hosted weights (${b.unique_models_utilized ?? 0} models)`,
      bench: "> 20% self-hosted or multi-vendor",
      imp: b.self_hosted_llm_ratio_pct > 0 ? "Tangible model sovereignty" : "100% cloud API dependency"
    },
    {
      dim: "Proprietary Connectors",
      val: `${b.enterprise_connectors_count ?? 0} / ${b.unique_tools_count ?? 0} custom enterprise tools`,
      bench: "> 50% custom enterprise tools",
      imp: b.enterprise_connectors_count > 0 ? "High enterprise integration switching barrier" : "Standard public web tooling"
    },
    {
      dim: "Continuous Evaluation Loop",
      val: `${b.evaluation_coverage_pct ?? 0}% evaluation coverage`,
      bench: "> 40% automated eval instrumentation",
      imp: b.evaluation_coverage_pct >= 40 ? "Active data flywheel improving agent over time" : "Unmonitored runtime operations"
    },
    {
      dim: "Replication Barrier",
      val: `~${moat.estimated_replication_months ?? 0} engineering months`,
      bench: "> 6 months for venture defensibility",
      imp: moat.estimated_replication_months >= 6 ? "High competitor replication friction" : "Rapidly clonable commodity wrapper"
    }
  ];

  rows.forEach(r => {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td><strong>${escapeHtml(r.dim)}</strong></td>
      <td style="font-family: monospace;">${escapeHtml(r.val)}</td>
      <td style="color: #8892b0;">${escapeHtml(r.bench)}</td>
      <td>${escapeHtml(r.imp)}</td>
    `;
    tbody.appendChild(tr);
  });
}

// 9. What-If Stress Testing Simulator
let stressDebounceTimeout = null;

function setupStressSimulatorControls() {
  const sliderVol = document.getElementById("slider-volume");
  const sliderShock = document.getElementById("slider-price-shock");
  const sliderWage = document.getElementById("slider-labor-rate");
  const sliderPrice = document.getElementById("slider-customer-price");
  const btnReset = document.getElementById("btn-reset-stress");

  if (!sliderVol || !sliderShock || !sliderWage || !sliderPrice) return;

  const onControlChange = () => {
    document.getElementById("lbl-volume").innerText = `${sliderVol.value}x`;
    document.getElementById("lbl-price-shock").innerText = `${Number(sliderShock.value) > 0 ? "+" : ""}${sliderShock.value}%`;
    document.getElementById("lbl-labor-rate").innerText = `$${sliderWage.value}/hr`;
    document.getElementById("lbl-customer-price").innerText = `$${Number(sliderPrice.value).toFixed(3)}`;

    if (stressDebounceTimeout) clearTimeout(stressDebounceTimeout);
    stressDebounceTimeout = setTimeout(() => {
      triggerStressRecalculation();
    }, 250);
  };

  sliderVol.addEventListener("input", onControlChange);
  sliderShock.addEventListener("input", onControlChange);
  sliderWage.addEventListener("input", onControlChange);
  sliderPrice.addEventListener("input", onControlChange);

  if (btnReset) {
    btnReset.addEventListener("click", () => {
      sliderVol.value = 1.0;
      sliderShock.value = 0;
      sliderWage.value = 28;
      sliderPrice.value = 0.05;
      onControlChange();
    });
  }
}

async function triggerStressRecalculation() {
  if (!currentCompanyId) return;

  const vol = parseFloat(document.getElementById("slider-volume").value);
  const shock = parseFloat(document.getElementById("slider-price-shock").value);
  const wage = parseFloat(document.getElementById("slider-labor-rate").value);
  const price = parseFloat(document.getElementById("slider-customer-price").value);

  try {
    const res = await fetch(`/api/v1/companies/${currentCompanyId}/stress-test`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        volume_multiplier: vol,
        provider_price_shock_pct: shock,
        human_hourly_wage_usd: wage,
        target_customer_price_per_task_usd: price
      })
    });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();
    renderStressTest(data);
  } catch (err) {
    console.error("Stress recalculation failed:", err);
  }
}

function renderStressTest(stress) {
  const strsd = stress.stressed_economics || {};
  const base = stress.baseline_economics || {};
  const verdict = stress.vulnerability_verdict || {};

  const grossEl = document.getElementById("stress-gross-margin");
  if (grossEl) {
    const gm = strsd.gross_margin_pct ?? 0;
    grossEl.innerText = `${gm}%`;
    grossEl.style.color = gm >= 70 ? "#4ade80" : (gm >= 40 ? "#fbbf24" : "#f87171");
  }

  const baseEl = document.getElementById("stress-base-margin");
  if (baseEl) baseEl.innerText = `Baseline: ${base.gross_margin_pct ?? "--"}%`;

  const unitCostEl = document.getElementById("stress-unit-cost");
  if (unitCostEl) unitCostEl.innerText = `$${Number(strsd.fully_loaded_cost_per_task_usd || 0).toFixed(4)}`;

  const laborCostEl = document.getElementById("stress-labor-cost");
  if (laborCostEl) laborCostEl.innerText = `Labor: $${Number(strsd.human_labor_cost_per_task_usd || 0).toFixed(4)} / task`;

  const spendEl = document.getElementById("stress-monthly-spend");
  if (spendEl) spendEl.innerText = `$${Number(strsd.monthly_total_cost_usd || 0).toLocaleString(undefined, { maximumFractionDigits: 0 })}`;

  const tasksEl = document.getElementById("stress-monthly-tasks");
  if (tasksEl) tasksEl.innerText = `${Number(strsd.monthly_tasks || 0).toLocaleString()} tasks / month`;

  const targetPriceEl = document.getElementById("stress-target-price");
  if (targetPriceEl) targetPriceEl.innerText = `$${Number(strsd.price_for_70pct_margin_usd || 0).toFixed(4)}`;

  const verdictBadge = document.getElementById("stress-verdict-badge");
  const verdictTitle = document.getElementById("stress-verdict-title");
  const verdictDetail = document.getElementById("stress-verdict-detail");
  if (verdictBadge) {
    const st = verdict.status || "SUSTAINABLE_SOFTWARE_MARGINS";
    verdictBadge.innerText = st.replace(/_/g, " ");
    verdictBadge.className = `status-badge ${st.includes("NEGATIVE") ? "status-contradicted" : (st.includes("COMPRESSION") ? "status-partially-verified" : "status-verified")}`;
  }
  if (verdictTitle) verdictTitle.innerText = verdict.status?.replace(/_/g, " ") || "Margin Health";
  if (verdictDetail) verdictDetail.innerText = verdict.statement || "";

  // Render Matrices
  const grids = stress.sensitivity_grids || {};
  const tbodyVol = document.getElementById("matrix-volume-shock-tbody");
  if (tbodyVol) {
    tbodyVol.innerHTML = "";
    (grids.volume_and_price_shock_margins || []).forEach(row => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.volume_multiple)} (${Number(row.monthly_tasks).toLocaleString()} tasks)</strong></td>
        <td style="color: ${row.shock_minus20pct >= 70 ? '#4ade80' : (row.shock_minus20pct >= 40 ? '#fbbf24' : '#f87171')}">${row.shock_minus20pct}%</td>
        <td style="color: ${row.shock_0pct >= 70 ? '#4ade80' : (row.shock_0pct >= 40 ? '#fbbf24' : '#f87171')}">${row.shock_0pct}%</td>
        <td style="color: ${row.shock_25pct >= 70 ? '#4ade80' : (row.shock_25pct >= 40 ? '#fbbf24' : '#f87171')}">${row.shock_25pct}%</td>
        <td style="color: ${row.shock_50pct >= 70 ? '#4ade80' : (row.shock_50pct >= 40 ? '#fbbf24' : '#f87171')}">${row.shock_50pct}%</td>
      `;
      tbodyVol.appendChild(tr);
    });
  }

  const tbodyHir = document.getElementById("matrix-hir-wage-tbody");
  if (tbodyHir) {
    tbodyHir.innerHTML = "";
    (grids.hir_and_wage_margins || []).forEach(row => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong>${escapeHtml(row.hir_rate_pct)} HIR</strong></td>
        <td style="color: ${row.wage_usd20 >= 70 ? '#4ade80' : (row.wage_usd20 >= 40 ? '#fbbf24' : '#f87171')}">${row.wage_usd20}%</td>
        <td style="color: ${row.wage_usd30 >= 70 ? '#4ade80' : (row.wage_usd30 >= 40 ? '#fbbf24' : '#f87171')}">${row.wage_usd30}%</td>
        <td style="color: ${row.wage_usd45 >= 70 ? '#4ade80' : (row.wage_usd45 >= 40 ? '#fbbf24' : '#f87171')}">${row.wage_usd45}%</td>
      `;
      tbodyHir.appendChild(tr);
    });
  }
}

// 10. Investment Committee Diligence Memo
function renderDiligenceMemo(memo) {
  const badge = document.getElementById("memo-deal-verdict-badge");
  const verdict = memo.deal_verdict || "RECOMMENDED";
  if (badge) {
    badge.innerText = verdict.replace(/_/g, " ");
    badge.className = `status-badge ${verdict === "RECOMMENDED" ? "status-verified" : (verdict.includes("CONDITIONAL") ? "status-partially-verified" : "status-contradicted")}`;
  }

  const riskScoreEl = document.getElementById("memo-risk-score");
  if (riskScoreEl) riskScoreEl.innerText = memo.diligence_risk_score ?? "--";

  const riskClassEl = document.getElementById("memo-risk-class");
  if (riskClassEl) riskClassEl.innerText = `${memo.risk_classification || "MODERATE"} RISK`;

  const dealTitleEl = document.getElementById("memo-deal-title");
  if (dealTitleEl) dealTitleEl.innerText = verdict.replace(/_/g, " ");

  const dealSummaryEl = document.getElementById("memo-deal-summary");
  if (dealSummaryEl) dealSummaryEl.innerText = memo.executive_verdict_summary || "";

  const flags = memo.flags_summary || {};
  const cRed = document.getElementById("count-red-flags");
  if (cRed) cRed.innerText = flags.red_flags_count ?? 0;
  const cYellow = document.getElementById("count-yellow-flags");
  if (cYellow) cYellow.innerText = flags.yellow_flags_count ?? 0;
  const cGreen = document.getElementById("count-green-flags");
  if (cGreen) cGreen.innerText = flags.green_flags_count ?? 0;

  // Render Flag Cards
  const flagsContainer = document.getElementById("memo-flags-container");
  if (flagsContainer) {
    flagsContainer.innerHTML = "";
    
    (memo.red_flags || []).forEach(f => {
      const card = document.createElement("div");
      card.className = "flag-item-card border-red";
      card.innerHTML = `
        <div class="flag-item-header">
          <span class="flag-item-title" style="color: #f87171;">[!] ${escapeHtml(f.title)}</span>
          <span class="status-badge status-contradicted">${escapeHtml(f.category)}</span>
        </div>
        <p class="flag-item-detail">${escapeHtml(f.detail)}</p>
      `;
      flagsContainer.appendChild(card);
    });

    (memo.yellow_flags || []).forEach(f => {
      const card = document.createElement("div");
      card.className = "flag-item-card border-yellow";
      card.innerHTML = `
        <div class="flag-item-header">
          <span class="flag-item-title" style="color: #fbbf24;">[?] ${escapeHtml(f.title)}</span>
          <span class="status-badge status-partially-verified">${escapeHtml(f.category)}</span>
        </div>
        <p class="flag-item-detail">${escapeHtml(f.detail)}</p>
      `;
      flagsContainer.appendChild(card);
    });

    (memo.green_flags || []).forEach(f => {
      const card = document.createElement("div");
      card.className = "flag-item-card border-green";
      card.innerHTML = `
        <div class="flag-item-header">
          <span class="flag-item-title" style="color: #4ade80;">[✓] ${escapeHtml(f.title)}</span>
          <span class="status-badge status-verified">${escapeHtml(f.category)}</span>
        </div>
        <p class="flag-item-detail">${escapeHtml(f.detail)}</p>
      `;
      flagsContainer.appendChild(card);
    });
  }

  // Render Remediation Playbook Table
  const tbodyRem = document.getElementById("memo-remediation-tbody");
  if (tbodyRem) {
    tbodyRem.innerHTML = "";
    (memo.remediation_playbook || []).forEach(item => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td><strong style="color: #58a6ff;">${escapeHtml(item.priority)}</strong></td>
        <td><strong>${escapeHtml(item.initiative)}</strong></td>
        <td style="color: #cbd5e1;">${escapeHtml(item.action)}</td>
        <td style="font-family: var(--font-mono); font-size: 11px; color: #4ade80;">${escapeHtml(item.kpi_target)}</td>
      `;
      tbodyRem.appendChild(tr);
    });
  }
}
