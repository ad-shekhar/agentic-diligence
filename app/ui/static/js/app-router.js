// Agentic Diligence (AGD) - Enterprise Application Workspace Router & View Controllers
// Compliant with Phase 8 Enterprise Architecture & Multi-Page Deep Linking

let companiesList = [];
let currentCompanyId = null;
let currentPackageData = null;
let currentMetricsData = null;
let currentMatrixData = null;

// Initialize on DOM Ready
document.addEventListener("DOMContentLoaded", async () => {
  setupSidebarToggle();
  setupGlobalLinkInterceptor();
  setupUploadModal();
  await loadCompaniesList();
  
  // Route current path
  handleRoute(window.location.pathname);

  // Listen to browser Back/Forward
  window.addEventListener("popstate", () => {
    handleRoute(window.location.pathname);
  });
});

// Sidebar Collapsible
function setupSidebarToggle() {
  const btn = document.getElementById("btn-toggle-sidebar");
  const sidebar = document.getElementById("sidebar");
  if (btn && sidebar) {
    btn.addEventListener("click", () => {
      sidebar.classList.toggle("collapsed");
      if (sidebar.style.width === "68px") {
        sidebar.style.width = "250px";
      } else {
        sidebar.style.width = "68px";
      }
    });
  }
}

// Intercept all internal navigation links
function setupGlobalLinkInterceptor() {
  document.addEventListener("click", (e) => {
    const link = e.target.closest("a");
    if (!link) return;
    const href = link.getAttribute("href");
    if (!href || href.startsWith("http") || href.startsWith("#") || href.startsWith("mailto") || link.getAttribute("target") === "_blank") {
      return;
    }
    if (href.startsWith("/app")) {
      e.preventDefault();
      navigateTo(href);
    }
  });
}

function navigateTo(url) {
  if (window.location.pathname !== url) {
    window.history.pushState({}, "", url);
  }
  handleRoute(url);
}

// Toast Notifications
function showToast(message, type = "info") {
  const container = document.getElementById("toast-container");
  if (!container) return;
  const toast = document.createElement("div");
  toast.className = `toast toast-${type}`;
  toast.innerHTML = `<span>${type === 'success' ? '✓' : type === 'error' ? '✕' : 'ℹ'}</span> <span>${message}</span>`;
  container.appendChild(toast);
  setTimeout(() => {
    toast.style.opacity = "0";
    toast.style.transform = "translateY(10px)";
    setTimeout(() => toast.remove(), 200);
  }, 3500);
}

// Fetch all target companies
async function loadCompaniesList() {
  try {
    const res = await fetch("/api/v1/companies");
    if (res.ok) {
      companiesList = await res.json();
    } else {
      companiesList = [];
    }
  } catch (err) {
    console.warn("Could not load company catalog:", err);
    companiesList = [];
  }
  updateTargetSwitcher();
}

function updateTargetSwitcher() {
  const select = document.getElementById("topbar-target-select");
  if (!select) return;
  select.innerHTML = "";
  if (companiesList.length === 0) {
    select.innerHTML = '<option value="" disabled selected>No evaluations found</option>';
    return;
  }
  companiesList.forEach(c => {
    const opt = document.createElement("option");
    opt.value = c.id;
    opt.innerText = `${c.name} (${c.trace_count} traces)`;
    if (c.id === currentCompanyId) opt.selected = true;
    select.appendChild(opt);
  });

  select.onchange = () => {
    const newId = select.value;
    if (newId && newId !== currentCompanyId) {
      // Check current subpath
      const parts = window.location.pathname.split("/").filter(Boolean);
      let subroute = "overview";
      if (parts.length >= 4) subroute = parts[3];
      navigateTo(`/app/projects/${newId}/${subroute === 'overview' ? '' : subroute}`);
    }
  };
}

// Update Sidebar Active Evaluation Context
function updateSidebarProjectContext(companyId, companyName) {
  const section = document.getElementById("sidebar-active-project-section");
  const targetLabel = document.getElementById("sidebar-target-name");
  if (!section) return;

  if (!companyId) {
    section.style.display = "none";
    return;
  }

  section.style.display = "block";
  if (targetLabel) {
    targetLabel.innerText = (companyName || "TARGET AUDIT").toUpperCase();
  }

  // Update dynamic hrefs
  const base = `/app/projects/${companyId}`;
  document.getElementById("nav-proj-overview").href = base;
  document.getElementById("nav-proj-claims").href = `${base}/claims`;
  document.getElementById("nav-proj-autonomy").href = `${base}/autonomy`;
  document.getElementById("nav-proj-economics").href = `${base}/economics`;
  document.getElementById("nav-proj-dependencies").href = `${base}/dependencies`;
  document.getElementById("nav-proj-aibom").href = `${base}/aibom`;
  document.getElementById("nav-proj-evidence").href = `${base}/evidence`;
  document.getElementById("nav-proj-security").href = `${base}/security`;
  document.getElementById("nav-proj-defensibility").href = `${base}/defensibility`;
  document.getElementById("nav-proj-stress").href = `${base}/stress-test`;
  document.getElementById("nav-proj-comparison").href = `${base}/comparison`;
  document.getElementById("nav-proj-reports").href = `${base}/reports`;
}

// Highlight Active Sidebar Item
function highlightSidebar(routeKey) {
  document.querySelectorAll(".sidebar-item").forEach(item => {
    item.classList.remove("active");
    if (item.getAttribute("data-route") === routeKey) {
      item.classList.add("active");
    }
  });
}

// Update Topbar Breadcrumbs
function updateBreadcrumbs(crumbs) {
  const bc = document.getElementById("topbar-breadcrumbs");
  if (!bc) return;
  let html = '<a href="/app">Workspace</a>';
  crumbs.forEach((c, idx) => {
    html += ' <span class="divider">/</span> ';
    if (idx === crumbs.length - 1) {
      html += `<span class="current">${c.label}</span>`;
    } else {
      html += `<a href="${c.url}">${c.label}</a>`;
    }
  });
  bc.innerHTML = html;
}

// ==============================================================================
// MASTER ROUTE HANDLER
// ==============================================================================
async function handleRoute(path) {
  const container = document.getElementById("app-view-container");
  if (!container) return;

  const segments = path.split("/").filter(Boolean); // e.g. ['app'], ['app', 'projects'], ['app', 'projects', 'new'], ['app', 'projects', '123', 'claims']

  // Route 1: /app
  if (segments.length === 1 && segments[0] === "app") {
    highlightSidebar("overview");
    updateBreadcrumbs([{ label: "Overview" }]);
    renderOverviewView(container);
    return;
  }

  // Route 2: /app/projects
  if (segments.length === 2 && segments[1] === "projects") {
    highlightSidebar("projects");
    updateBreadcrumbs([{ label: "Projects" }]);
    renderProjectsCatalogView(container);
    return;
  }

  // Route 3: /app/projects/new
  if (segments.length === 3 && segments[1] === "projects" && segments[2] === "new") {
    highlightSidebar("new-project");
    updateBreadcrumbs([{ label: "Projects", url: "/app/projects" }, { label: "New Evaluation" }]);
    renderNewProjectView(container);
    return;
  }

  // Route 4: /app/integrations
  if (segments.length === 2 && segments[1] === "integrations") {
    highlightSidebar("integrations");
    updateBreadcrumbs([{ label: "Integrations & Adapters" }]);
    renderIntegrationsView(container);
    return;
  }

  // Route 5: /app/settings
  if (segments.length === 2 && segments[1] === "settings") {
    highlightSidebar("settings");
    updateBreadcrumbs([{ label: "Settings" }]);
    renderSettingsView(container);
    return;
  }

  // Route 6: /app/projects/{companyId}/[subroute]
  if (segments.length >= 3 && segments[1] === "projects") {
    const compId = segments[2];
    const subroute = segments[3] || "overview";

    currentCompanyId = compId;
    container.innerHTML = '<div style="padding: 40px; text-align: center;"><div class="badge badge-info">Loading target evaluation data...</div></div>';

    // Fetch Target Data if needed
    await ensureProjectLoaded(compId);
    const compName = currentPackageData?.company?.name || "Target Evaluation";
    updateSidebarProjectContext(compId, compName);
    updateTargetSwitcher();

    const baseProjUrl = `/app/projects/${compId}`;

    switch (subroute) {
      case "overview":
        highlightSidebar("project-overview");
        updateBreadcrumbs([{ label: "Projects", url: "/app/projects" }, { label: compName, url: baseProjUrl }, { label: "Overview" }]);
        renderProjectOverviewView(container, compId);
        break;
      case "claims":
        highlightSidebar("claims");
        updateBreadcrumbs([{ label: "Projects", url: "/app/projects" }, { label: compName, url: baseProjUrl }, { label: "1. Claim Matrix" }]);
        renderClaimsView(container, compId);
        break;
      case "autonomy":
        highlightSidebar("autonomy");
        updateBreadcrumbs([{ label: "Projects", url: "/app/projects" }, { label: compName, url: baseProjUrl }, { label: "2. Autonomy & HIR" }]);
        renderAutonomyView(container, compId);
        break;
      case "economics":
        highlightSidebar("economics");
        updateBreadcrumbs([{ label: "Projects", url: "/app/projects" }, { label: compName, url: baseProjUrl }, { label: "3. Unit Economics" }]);
        renderEconomicsView(container, compId);
        break;
      case "dependencies":
        highlightSidebar("dependencies");
        updateBreadcrumbs([{ label: "Projects", url: "/app/projects" }, { label: compName, url: baseProjUrl }, { label: "4. Dependencies & Cascades" }]);
        renderDependenciesView(container, compId);
        break;
      case "aibom":
        highlightSidebar("aibom");
        updateBreadcrumbs([{ label: "Projects", url: "/app/projects" }, { label: compName, url: baseProjUrl }, { label: "5. AIBOM (CycloneDX)" }]);
        renderAIBOMView(container, compId);
        break;
      case "evidence":
        highlightSidebar("evidence");
        updateBreadcrumbs([{ label: "Projects", url: "/app/projects" }, { label: compName, url: baseProjUrl }, { label: "6. Proof & Evidence Graph" }]);
        renderEvidenceView(container, compId);
        break;
      case "security":
        highlightSidebar("security");
        updateBreadcrumbs([{ label: "Projects", url: "/app/projects" }, { label: compName, url: baseProjUrl }, { label: "7. Tool Risk & Security" }]);
        renderSecurityView(container, compId);
        break;
      case "defensibility":
        highlightSidebar("defensibility");
        updateBreadcrumbs([{ label: "Projects", url: "/app/projects" }, { label: compName, url: baseProjUrl }, { label: "8. Moat & Defensibility" }]);
        renderDefensibilityView(container, compId);
        break;
      case "stress-test":
        highlightSidebar("stress-test");
        updateBreadcrumbs([{ label: "Projects", url: "/app/projects" }, { label: compName, url: baseProjUrl }, { label: "9. Stress Simulator" }]);
        renderStressTestView(container, compId);
        break;
      case "comparison":
        highlightSidebar("comparison");
        updateBreadcrumbs([{ label: "Projects", url: "/app/projects" }, { label: compName, url: baseProjUrl }, { label: "10. Comparison" }]);
        renderComparisonView(container, compId);
        break;
      case "reports":
        highlightSidebar("reports");
        updateBreadcrumbs([{ label: "Projects", url: "/app/projects" }, { label: compName, url: baseProjUrl }, { label: "11. Deal Memo & Reports" }]);
        renderReportsView(container, compId);
        break;
      default:
        renderProjectOverviewView(container, compId);
    }
    return;
  }

  // Fallback -> /app
  navigateTo("/app");
}

async function ensureProjectLoaded(compId) {
  if (currentPackageData && currentPackageData.company?.id === compId) {
    return;
  }
  try {
    const res = await fetch(`/api/v1/companies/${compId}/package`);
    if (res.ok) {
      currentPackageData = await res.json();
    } else {
      currentPackageData = null;
    }
  } catch (err) {
    console.error("Failed to fetch project package:", err);
    currentPackageData = null;
  }
}

// ==============================================================================
// VIEW CONTROLLER 1: WORKSPACE OVERVIEW (/app)
// ==============================================================================
function renderOverviewView(container) {
  const totalProjects = companiesList.length;
  const totalTraces = companiesList.reduce((acc, c) => acc + (c.trace_count || 0), 0);

  container.innerHTML = `
    <div style="margin-bottom: var(--space-8);">
      <div style="display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: var(--space-4);">
        <div>
          <h1 style="font-size: 1.75rem; margin-bottom: var(--space-1);">Workspace Overview</h1>
          <p style="margin: 0; color: var(--text-secondary);">Enterprise technical diligence cockpit for autonomous AI agent systems.</p>
        </div>
        <div style="display: flex; gap: var(--space-3);">
          <button id="btn-quick-ingest" class="btn btn-secondary"><span>↑</span> Ingest Telemetry</button>
          <a href="/app/projects/new" class="btn btn-primary"><span>+</span> New Evaluation Audit</a>
        </div>
      </div>
    </div>

    <!-- Workspace KPI Strip -->
    <div class="metric-grid">
      <div class="kpi-card">
        <div class="kpi-label">Diligence Projects</div>
        <div class="kpi-value">${totalProjects}</div>
        <div class="kpi-sub">${totalProjects} targets audited in catalog</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Telemetry Traces</div>
        <div class="kpi-value">${totalTraces}</div>
        <div class="kpi-sub">Normalized OTel v1.28.0 spans</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Active Collector</div>
        <div class="kpi-value" style="color: var(--color-success); font-size: 1.25rem;">ONLINE</div>
        <div class="kpi-sub">POST /v1/traces (SHA-256 enabled)</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Pricing Rate Card</div>
        <div class="kpi-value" style="font-size: 1.25rem;">v2026_09</div>
        <div class="kpi-sub">Standardized Sep 2026 LLM pricing</div>
      </div>
    </div>

    <!-- Quick Start Presets & Recent Projects Grid -->
    <div style="display: grid; grid-template-columns: 2fr 1fr; gap: var(--space-6); margin-bottom: var(--space-8);">
      <div class="panel-card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-4);">
          <h3>Recent Diligence Evaluations</h3>
          <a href="/app/projects" style="font-size: 0.8rem;">View All Projects →</a>
        </div>
        <div class="table-container" style="border: none;">
          <table class="data-table">
            <thead>
              <tr>
                <th>Target Company</th>
                <th>Traces</th>
                <th>Created</th>
                <th>Status</th>
                <th>Action</th>
              </tr>
            </thead>
            <tbody>
              ${companiesList.length === 0 ? '<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 30px;">No evaluations created yet. Launch one below!</td></tr>' : 
                companiesList.slice(0, 5).map(c => `
                  <tr>
                    <td><strong>${c.name}</strong></td>
                    <td><span class="badge badge-info font-mono">${c.trace_count} traces</span></td>
                    <td style="color: var(--text-muted);">${c.created_at ? new Date(c.created_at).toLocaleDateString() : 'Recent'}</td>
                    <td><span class="badge ${c.status === 'COMPLETED' ? 'badge-success' : 'badge-warning'}">${c.status}</span></td>
                    <td><a href="/app/projects/${c.id}" class="btn btn-sm btn-outline">Open Audit →</a></td>
                  </tr>
                `).join('')
              }
            </tbody>
          </table>
        </div>
      </div>

      <div class="panel-card">
        <h3 style="margin-bottom: var(--space-3);">Run Benchmark Preset</h3>
        <p style="font-size: 0.825rem; margin-bottom: var(--space-4);">Instantly launch an audit against a seeded ground-truth benchmark target:</p>
        <div style="display: flex; flex-direction: column; gap: var(--space-3);">
          <button class="btn btn-secondary btn-sm btn-quick-scenario" data-scenario="scenario_a" style="justify-content: flex-start; text-align: left;">
            <div>
              <div style="font-weight: 600;">AcmeAI (Scenario A)</div>
              <div style="font-size: 0.75rem; color: var(--text-muted);">Realistic benchmark with 26% human intervention</div>
            </div>
          </button>
          <button class="btn btn-secondary btn-sm btn-quick-scenario" data-scenario="scenario_b" style="justify-content: flex-start; text-align: left;">
            <div>
              <div style="font-weight: 600;">Company B (Scenario B)</div>
              <div style="font-size: 0.75rem; color: var(--text-muted);">Verified high automation (96% AI execution)</div>
            </div>
          </button>
          <button class="btn btn-secondary btn-sm btn-quick-scenario" data-scenario="scenario_c" style="justify-content: flex-start; text-align: left;">
            <div>
              <div style="font-weight: 600;">Company C (Scenario C)</div>
              <div style="font-size: 0.75rem; color: var(--text-muted);">Falsified pitch deck claims (80% human labor)</div>
            </div>
          </button>
        </div>
      </div>
    </div>
  `;

  // Attach quick scenario launch handlers
  container.querySelectorAll(".btn-quick-scenario").forEach(btn => {
    btn.addEventListener("click", async () => {
      const scenario = btn.getAttribute("data-scenario");
      btn.innerText = "Running benchmark...";
      btn.disabled = true;
      try {
        const res = await fetch(`/api/v1/scenarios/${scenario}/run?sample_size=100`);
        const data = await res.json();
        showToast(`Audit for ${data.company?.name} completed!`, "success");
        await loadCompaniesList();
        navigateTo(`/app/projects/${data.company?.id}`);
      } catch (err) {
        showToast("Error running benchmark: " + err.message, "error");
        btn.disabled = false;
      }
    });
  });

  const quickIngest = container.querySelector("#btn-quick-ingest");
  if (quickIngest) {
    quickIngest.addEventListener("click", () => {
      document.getElementById("modal-upload").classList.add("open");
    });
  }
}

// ==============================================================================
// VIEW CONTROLLER 2: PROJECT CATALOG (/app/projects)
// ==============================================================================
async function renderProjectsCatalogView(container) {
  container.innerHTML = '<div style="padding: 40px; text-align: center;"><div class="badge badge-info">Loading diligence projects...</div></div>';

  let projects = [];
  try {
    const res = await fetch("/api/v1/projects");
    if (res.ok) {
      projects = await res.json();
    }
  } catch (err) {
    console.error("Failed to load projects:", err);
  }

  container.innerHTML = `
    <div style="margin-bottom: var(--space-6); display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: var(--space-4);">
      <div>
        <h1 style="font-size: 1.75rem; margin-bottom: var(--space-1);">Diligence Projects Catalog</h1>
        <p style="margin: 0; color: var(--text-secondary);">Manage and audit target AI companies, evaluation runs, and evidence archives.</p>
      </div>
      <a href="/app/projects/new" class="btn btn-primary"><span>+</span> New Evaluation</a>
    </div>

    <div class="panel-card" style="margin-bottom: var(--space-6);">
      <div style="display: flex; justify-content: space-between; align-items: center; gap: var(--space-4); flex-wrap: wrap; margin-bottom: var(--space-4);">
        <input type="text" id="input-catalog-search" class="form-control" placeholder="Search target companies or systems..." style="width: 320px;">
        <div style="display: flex; gap: var(--space-2);" id="catalog-filter-group">
          <button class="btn btn-sm btn-outline active-filter" data-filter="ACTIVE">Active (${projects.filter(p => p.status === 'ACTIVE').length})</button>
          <button class="btn btn-sm btn-outline" data-filter="ALL">All (${projects.length})</button>
          <button class="btn btn-sm btn-outline" data-filter="ARCHIVED">Archived</button>
        </div>
      </div>

      <div class="table-container">
        <table class="data-table" id="table-catalog">
          <thead>
            <tr>
              <th>Diligence Project / Target</th>
              <th>Target System / Role</th>
              <th>Framework</th>
              <th>Ingested Traces</th>
              <th>Status</th>
              <th>Created Date</th>
              <th>Actions</th>
            </tr>
          </thead>
          <tbody id="catalog-tbody">
            ${projects.length === 0 ? '<tr><td colspan="7" style="text-align: center; color: var(--text-muted); padding: 40px;">No diligence projects found. Click "+ New Evaluation" to begin.</td></tr>' :
              projects.map(p => `
                <tr data-status="${p.status}">
                  <td>
                    <strong>${p.name}</strong>
                    <div style="font-size: 0.75rem; color: var(--text-muted);">${p.target_name || ''}</div>
                  </td>
                  <td style="font-size: 0.85rem;">${p.target_system || '--'}</td>
                  <td><span class="badge badge-info" style="font-size: 0.75rem;">${p.framework || 'OTel GenAI'}</span></td>
                  <td><span class="badge ${p.trace_count > 0 ? 'badge-success' : 'badge-warning'} font-mono">${p.trace_count} traces</span></td>
                  <td><span class="badge ${p.status === 'ACTIVE' ? 'badge-primary' : 'badge-outline'}">${p.status}</span></td>
                  <td style="color: var(--text-muted); font-size: 0.825rem;">${p.created_at ? new Date(p.created_at).toLocaleDateString() : 'Recent'}</td>
                  <td style="display: flex; gap: var(--space-2); align-items: center;">
                    <a href="/app/projects/${p.id}" class="btn btn-sm btn-primary">Open →</a>
                    <button class="btn btn-sm btn-outline btn-archive-proj" data-id="${p.id}" title="Archive Project" style="padding: var(--space-1) var(--space-2); color: var(--text-muted);">🗑</button>
                  </td>
                </tr>
              `).join('')
            }
          </tbody>
        </table>
      </div>
    </div>
  `;

  // Search filtering
  const searchInput = container.querySelector("#input-catalog-search");
  if (searchInput) {
    searchInput.addEventListener("input", (e) => {
      const q = e.target.value.toLowerCase();
      const rows = container.querySelectorAll("#catalog-tbody tr");
      rows.forEach(r => {
        const text = r.innerText.toLowerCase();
        r.style.display = text.includes(q) ? "" : "none";
      });
    });
  }

  // Filter tabs
  const filterBtns = container.querySelectorAll("#catalog-filter-group button");
  filterBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      filterBtns.forEach(b => b.classList.remove("active-filter"));
      btn.classList.add("active-filter");
      const f = btn.getAttribute("data-filter");
      const rows = container.querySelectorAll("#catalog-tbody tr");
      rows.forEach(r => {
        const st = r.getAttribute("data-status");
        if (f === "ALL" || !f) {
          r.style.display = "";
        } else {
          r.style.display = (st === f) ? "" : "none";
        }
      });
    });
  });

  // Archive buttons
  container.querySelectorAll(".btn-archive-proj").forEach(btn => {
    btn.addEventListener("click", async (e) => {
      e.stopPropagation();
      const pId = btn.getAttribute("data-id");
      if (confirm("Are you sure you want to archive this diligence project?")) {
        try {
          const res = await fetch(`/api/v1/projects/${pId}/archive`, { method: "POST" });
          if (res.ok) {
            showToast("Project archived successfully", "info");
            await loadCompaniesList();
            renderProjectsCatalogView(container);
          } else {
            throw new Error("Archival failed");
          }
        } catch (err) {
          showToast(err.message, "error");
        }
      }
    });
  });
}

// ==============================================================================
// VIEW CONTROLLER 3: NEW EVALUATION WIZARD (/app/projects/new)
// ==============================================================================
function renderNewProjectView(container) {
  container.innerHTML = `
    <div style="max-width: 800px; margin: 0 auto;">
      <div style="margin-bottom: var(--space-6);">
        <h1 style="font-size: 1.75rem; margin-bottom: var(--space-1);">Start a New Diligence Evaluation</h1>
        <p style="color: var(--text-secondary); margin: 0;">Configure a genuine custom target evaluation or run a calibrated ground-truth benchmark.</p>
      </div>

      <div class="panel-card" style="box-shadow: var(--shadow-lg);">
        <div style="margin-bottom: var(--space-6);">
          <label class="form-label">Step 1: Choose Evaluation Type</label>
          <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-4); margin-top: var(--space-2);">
            <label class="card" style="cursor: pointer; border: 2px solid var(--accent-primary); background: var(--bg-surface-2);" id="wiz-card-bench">
              <input type="radio" name="wiz_type" value="benchmark" checked style="margin-bottom: var(--space-2);">
              <h4 style="color: var(--accent-primary);">Ground-Truth Benchmark</h4>
              <p style="font-size: 0.8rem; margin: 0;">Evaluate against pre-seeded scenarios with known ground-truth outcomes.</p>
            </label>
            <label class="card" style="cursor: pointer; border: 1px solid var(--border-default);" id="wiz-card-custom">
              <input type="radio" name="wiz_type" value="custom" style="margin-bottom: var(--space-2);">
              <h4>Live OTel Ingestion Target</h4>
              <p style="font-size: 0.8rem; margin: 0;">Create a clean diligence container ready to receive live OpenTelemetry or MCP traces.</p>
            </label>
          </div>
        </div>

        <div id="wiz-sec-bench" style="margin-bottom: var(--space-6);">
          <div class="card" style="background: rgba(99, 133, 245, 0.08); border-color: rgba(99, 133, 245, 0.25); margin-bottom: var(--space-4); padding: var(--space-3) var(--space-4);">
            <span style="font-size: 0.8rem; color: var(--accent-primary); font-weight: 600;">ℹ️ SAMPLE BENCHMARK DATA DISCLOSURE:</span>
            <p style="font-size: 0.775rem; color: var(--text-secondary); margin: var(--space-1) 0 0 0;">
              Benchmark scenarios run against synthetic software flight recorder traces with calibrated ground-truth behavior.
            </p>
          </div>
          <div class="form-group">
            <label class="form-label" for="wiz-select-scenario">Select Benchmark Preset:</label>
            <select id="wiz-select-scenario" class="form-control">
              <option value="scenario_a" selected>AcmeAI Target (Scenario A — Realistic Overruns & 26% Human Intervention)</option>
              <option value="scenario_b">Company B (Scenario B — Verified High Automation 96% AI Execution)</option>
              <option value="scenario_c">Company C (Scenario C — Falsified Pitch Claims, 80% Human Dependency)</option>
              <option value="scenario_f">Company F (Scenario F — 98% Single-Provider OpenAI Vendor Lock-in)</option>
              <option value="scenario_i">Company I (Scenario I — Multi-Cloud Resilient Provider Distribution)</option>
              <option value="scenario_j">Company J (Scenario J — 90% Self-Hosted Local Weights & Defensible Moat)</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label" for="wiz-sample-size">Trace Sample Size:</label>
            <input type="number" id="wiz-sample-size" class="form-control" value="100" min="20" max="500">
          </div>
        </div>

        <div id="wiz-sec-custom" style="display: none; margin-bottom: var(--space-6);">
          <div class="card" style="background: rgba(57, 185, 165, 0.08); border-color: rgba(57, 185, 165, 0.25); margin-bottom: var(--space-4); padding: var(--space-3) var(--space-4);">
            <span style="font-size: 0.8rem; color: var(--accent-secondary); font-weight: 600;">🛡️ VERIFIABLE RUNTIME AUDIT CONTAINER:</span>
            <p style="font-size: 0.775rem; color: var(--text-secondary); margin: var(--space-1) 0 0 0;">
              Zero mock data will be injected. Create a clean project container ready for trace ingestion via OTel collector or file upload.
            </p>
          </div>
          <div class="form-group">
            <label class="form-label" for="wiz-custom-name">Target Company / Project Name:</label>
            <input type="text" id="wiz-custom-name" class="form-control" placeholder="e.g. NexusFlow AI">
          </div>
          <div class="form-group">
            <label class="form-label" for="wiz-custom-role">Agent System / Workload Description:</label>
            <input type="text" id="wiz-custom-role" class="form-control" placeholder="e.g. Autonomous Customer Support Tier-1">
          </div>
          <div class="form-group">
            <label class="form-label" for="wiz-custom-framework">Primary Agent Framework:</label>
            <select id="wiz-custom-framework" class="form-control">
              <option value="LangGraph / LangChain">LangGraph / LangChain</option>
              <option value="CrewAI Hierarchical">CrewAI Hierarchical Agent</option>
              <option value="Claude MCP Observer">Claude Desktop / MCP Observer</option>
              <option value="Custom OpenTelemetry">Custom In-House Python Loop</option>
            </select>
          </div>
          <div class="form-group">
            <label class="form-label" for="wiz-custom-scope">Assessment Scope / Stated Objectives:</label>
            <input type="text" id="wiz-custom-scope" class="form-control" placeholder="e.g. Verify stated 90% autonomy claim and unit economics">
          </div>
        </div>

        <div style="display: flex; justify-content: flex-end; gap: var(--space-3); border-top: 1px solid var(--border-default); padding-top: var(--space-5);">
          <a href="/app/projects" class="btn btn-secondary">Cancel</a>
          <button id="wiz-btn-submit" class="btn btn-primary btn-lg">Launch Evaluation Workspace →</button>
        </div>
      </div>
    </div>
  `;

  const rBench = container.querySelector('input[value="benchmark"]');
  const rCustom = container.querySelector('input[value="custom"]');
  const sBench = container.querySelector("#wiz-sec-bench");
  const sCustom = container.querySelector("#wiz-sec-custom");
  const cBench = container.querySelector("#wiz-card-bench");
  const cCustom = container.querySelector("#wiz-card-custom");

  rBench.addEventListener("change", () => {
    sBench.style.display = "block";
    sCustom.style.display = "none";
    cBench.style.borderColor = "var(--accent-primary)";
    cCustom.style.borderColor = "var(--border-default)";
  });

  rCustom.addEventListener("change", () => {
    sBench.style.display = "none";
    sCustom.style.display = "block";
    cCustom.style.borderColor = "var(--accent-primary)";
    cBench.style.borderColor = "var(--border-default)";
  });

  const submitBtn = container.querySelector("#wiz-btn-submit");
  submitBtn.addEventListener("click", async () => {
    submitBtn.innerText = "Initializing project...";
    submitBtn.disabled = true;

    try {
      if (rBench.checked) {
        const sc = container.querySelector("#wiz-select-scenario").value;
        const size = container.querySelector("#wiz-sample-size").value || 100;
        const res = await fetch(`/api/v1/scenarios/${sc}/run?sample_size=${size}`);
        if (!res.ok) throw new Error("Benchmark scenario run failed with status " + res.status);
        const data = await res.json();
        showToast("Benchmark evaluation successfully compiled!", "success");
        await loadCompaniesList();
        navigateTo(`/app/projects/${data.company?.id}`);
      } else {
        const targetName = container.querySelector("#wiz-custom-name").value.trim() || "Custom AI Target";
        const role = container.querySelector("#wiz-custom-role").value.trim() || targetName;
        const framework = container.querySelector("#wiz-custom-framework").value;
        const scope = container.querySelector("#wiz-custom-scope").value.trim();

        const res = await fetch("/api/v1/projects", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: `${targetName} Diligence`,
            target_name: targetName,
            target_system: role,
            framework: framework,
            target_type: "autonomous_agent",
            description: `Diligence audit container for ${targetName}.`,
            assessment_scope: scope
          })
        });

        if (!res.ok) {
          const errData = await res.json();
          throw new Error(errData.detail || "Failed to create project");
        }

        const proj = await res.json();
        showToast(`Project '${proj.name}' initialized!`, "success");
        await loadCompaniesList();
        navigateTo(`/app/projects/${proj.id}`);
      }
    } catch (err) {
      showToast("Error creating evaluation: " + err.message, "error");
      submitBtn.innerText = "Launch Evaluation Workspace →";
      submitBtn.disabled = false;
    }
  });
}

// VIEW CONTROLLER 4: PROJECT OVERVIEW (/app/projects/{id})
// ==============================================================================
function renderProjectOverviewView(container, compId) {
  if (!currentPackageData) {
    container.innerHTML = '<div class="panel-card" style="text-align: center; padding: 40px;"><p>Target evaluation data not found.</p><a href="/app/projects" class="btn btn-secondary">Return to Catalog</a></div>';
    return;
  }

  const p = currentPackageData;
  const comp = p.company || {};
  const intv = p.interventions || {};
  const econ = p.economics || {};
  const casc = p.cascades || {};
  const memo = p.memo || {};

  container.innerHTML = `
    <!-- Target Overview Header -->
    <div style="margin-bottom: var(--space-6); display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: var(--space-4);">
      <div>
        <div style="display: flex; align-items: center; gap: var(--space-3); margin-bottom: var(--space-1);">
          <h1 style="font-size: 1.75rem; margin: 0;">${comp.name}</h1>
          <span class="badge badge-success font-mono">${intv.total_traces || 0} Traces Audited</span>
        </div>
        <p style="margin: 0; color: var(--text-secondary);">Observation Window: ${p.observation_window || "Last 30 Days"} | Rate Card: ${p.report_metadata?.pricing_version || "v2026_09"}</p>
      </div>
      <div style="display: flex; gap: var(--space-3);">
        <a href="/app/projects/${compId}/claims" class="btn btn-secondary btn-sm">Inspect Claims Matrix →</a>
        <a href="/app/projects/${compId}/reports" class="btn btn-primary btn-sm">📄 Deal Memo & Downloads</a>
      </div>
    </div>

    <!-- Executive KPI Strip -->
    <div class="metric-grid">
      <div class="kpi-card">
        <div class="kpi-label">True Autonomy Rate</div>
        <div class="kpi-value" style="color: ${intv.autonomous_rate_pct < 80 ? 'var(--color-warning)' : 'var(--color-success)'};">${intv.autonomous_rate_pct ?? "--"}%</div>
        <div class="kpi-sub">${intv.human_intervention_rate_pct ?? "--"}% Human Help Rate (HIR)</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Cost Per Task (CPT)</div>
        <div class="kpi-value">$${Number(econ.telemetry_attributable_cost_per_task_usd || 0).toFixed(4)}</div>
        <div class="kpi-sub">Cost Status: ${econ.overall_cost_status || "MEASURED"}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Cascade Overrun</div>
        <div class="kpi-value">${casc.avg_cost_multiplier_on_failure || 1.0}x</div>
        <div class="kpi-sub">${casc.cascade_frequency_pct || 0}% tasks in retry loops</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Diligence Risk Score</div>
        <div class="kpi-value" style="color: ${memo.diligence_risk_score > 50 ? 'var(--color-danger)' : 'var(--color-success)'};">${memo.diligence_risk_score ?? "--"} / 100</div>
        <div class="kpi-sub">${memo.risk_classification || "MODERATE"} RISK (${memo.deal_verdict || "CONDITIONAL"})</div>
      </div>
    </div>

    <!-- Module Quick Navigation Cards (10 Analytical Engines) -->
    <div style="margin-bottom: var(--space-8);">
      <h3 style="margin-bottom: var(--space-4);">Analytical Diligence Modules</h3>
      <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: var(--space-4);">
        <a href="/app/projects/${compId}/claims" class="card" style="text-decoration: none;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2);">
            <h4 style="margin: 0; color: var(--text-primary);">1. Claim Verification</h4>
            <span class="badge badge-info">${(p.claims || []).length} Claims</span>
          </div>
          <p style="font-size: 0.8rem; margin: 0; color: var(--text-secondary);">Compares founder pitch statements against mathematical facts in software flight recorder logs.</p>
        </a>

        <a href="/app/projects/${compId}/autonomy" class="card" style="text-decoration: none;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2);">
            <h4 style="margin: 0; color: var(--text-primary);">2. Autonomy & Intervention</h4>
            <span class="badge badge-warning">${intv.autonomous_rate_pct}% Autonomous</span>
          </div>
          <p style="font-size: 0.8rem; margin: 0; color: var(--text-secondary);">Task segmentation, assisted task counts, and human latency delay heuristics.</p>
        </a>

        <a href="/app/projects/${compId}/economics" class="card" style="text-decoration: none;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2);">
            <h4 style="margin: 0; color: var(--text-primary);">3. Unit Economics</h4>
            <span class="badge badge-info">$${Number(econ.telemetry_attributable_cost_per_task_usd || 0).toFixed(4)}/task</span>
          </div>
          <p style="font-size: 0.8rem; margin: 0; color: var(--text-secondary);">Cost per task, token efficiency ratios, and automated evaluation Trust Tax overhead.</p>
        </a>

        <a href="/app/projects/${compId}/dependencies" class="card" style="text-decoration: none;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2);">
            <h4 style="margin: 0; color: var(--text-primary);">4. Dependencies & SPOF</h4>
            <span class="badge badge-warning">HHI: ${p.dependencies?.hhi_score || "--"}</span>
          </div>
          <p style="font-size: 0.8rem; margin: 0; color: var(--text-secondary);">Single points of failure, provider lock-in, and failure cascade multipliers.</p>
        </a>

        <a href="/app/projects/${compId}/aibom" class="card" style="text-decoration: none;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2);">
            <h4 style="margin: 0; color: var(--text-primary);">5. AIBOM (CycloneDX)</h4>
            <span class="badge badge-success">OWASP 1.6</span>
          </div>
          <p style="font-size: 0.8rem; margin: 0; color: var(--text-secondary);">Itemized supply chain inventory of foundation models, external tools, vector stores, and checkpoints.</p>
        </a>

        <a href="/app/projects/${compId}/evidence" class="card" style="text-decoration: none;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2);">
            <h4 style="margin: 0; color: var(--text-primary);">6. Proof & Evidence Graph</h4>
            <span class="badge badge-success">SHA-256 Provenance</span>
          </div>
          <p style="font-size: 0.8rem; margin: 0; color: var(--text-secondary);">Cryptographic chain of custody connecting high-level conclusions directly to raw telemetry spans.</p>
        </a>

        <a href="/app/projects/${compId}/security" class="card" style="text-decoration: none;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2);">
            <h4 style="margin: 0; color: var(--text-primary);">7. Tool Safety & Blast Radius</h4>
            <span class="badge badge-danger">Risk: ${p.tool_risk?.risk_level || "LOW"}</span>
          </div>
          <p style="font-size: 0.8rem; margin: 0; color: var(--text-secondary);">Privilege level classification auditing write actions, bash execution, and unconstrained access.</p>
        </a>

        <a href="/app/projects/${compId}/defensibility" class="card" style="text-decoration: none;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2);">
            <h4 style="margin: 0; color: var(--text-primary);">8. Moat & Defensibility</h4>
            <span class="badge badge-info">Moat: ${p.defensibility?.moat_score || "--"}/100</span>
          </div>
          <p style="font-size: 0.8rem; margin: 0; color: var(--text-secondary);">Proprietary scaffolding complexity, model weight sovereignty, and estimated replication cost.</p>
        </a>

        <a href="/app/projects/${compId}/stress-test" class="card" style="text-decoration: none;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2);">
            <h4 style="margin: 0; color: var(--text-primary);">9. Stress Simulator</h4>
            <span class="badge badge-warning">What-If Financials</span>
          </div>
          <p style="font-size: 0.8rem; margin: 0; color: var(--text-secondary);">Simulates volume surges (5x-10x), provider token price shocks (+25%), and human operator wages.</p>
        </a>

        <a href="/app/projects/${compId}/reports" class="card" style="text-decoration: none;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2);">
            <h4 style="margin: 0; color: var(--text-primary);">10. Deal Memo & Exports</h4>
            <span class="badge badge-primary">IC Memo & ZIP</span>
          </div>
          <p style="font-size: 0.8rem; margin: 0; color: var(--text-secondary);">Executive Investment Committee memo, PDF report, JSON package, and signed evidence bundle.</p>
        </a>
      </div>
    </div>
  `;
}

// ==============================================================================
// VIEW CONTROLLER 5: CLAIM VERIFICATION MATRIX (/app/projects/{id}/claims)
// ==============================================================================
async function renderClaimsView(container, compId) {
  let matrix = null;
  try {
    const res = await fetch(`/api/v1/companies/${compId}/claim-matrix`);
    if (res.ok) matrix = await res.json();
  } catch (err) {
    console.error(err);
  }

  const entries = matrix?.entries || [];
  const summary = matrix?.summary || { total_claims: 0, verified_count: 0, partially_verified_count: 0, contradicted_count: 0, insufficient_evidence_count: 0 };

  container.innerHTML = `
    <div style="margin-bottom: var(--space-6); display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: var(--space-4);">
      <div>
        <h1 style="font-size: 1.75rem; margin-bottom: var(--space-1);">Claim Verification Matrix</h1>
        <p style="margin: 0; color: var(--text-secondary);">Mathematical verification comparing founder pitch assertions against statistical lower/upper bounds in software logs.</p>
      </div>
      <div style="display: flex; gap: var(--space-2);" id="claim-filter-pills">
        <button class="btn btn-sm btn-outline active-filter" data-verdict="all">All (${summary.total_claims})</button>
        <button class="btn btn-sm btn-outline pill-verified" data-verdict="VERIFIED">Verified (${summary.verified_count})</button>
        <button class="btn btn-sm btn-outline pill-partial" data-verdict="PARTIALLY_VERIFIED">Partial (${summary.partially_verified_count})</button>
        <button class="btn btn-sm btn-outline pill-contradicted" data-verdict="CONTRADICTED">Contradicted (${summary.contradicted_count})</button>
      </div>
    </div>

    <div class="table-container">
      <table class="data-table" id="claims-view-table">
        <thead>
          <tr>
            <th style="width: 110px;">Claim ID</th>
            <th style="width: 140px;">Dimension</th>
            <th>Stated Founder Pitch Claim</th>
            <th style="width: 180px;">Audit Verdict</th>
            <th>Mathematical Verification Reason</th>
          </tr>
        </thead>
        <tbody>
          ${entries.length === 0 ? '<tr><td colspan="5" style="text-align: center; padding: 40px; color: var(--text-muted);">No claim matrix entries evaluated.</td></tr>' :
            entries.map(e => `
              <tr data-verdict="${e.verification_verdict}">
                <td class="font-mono"><strong>${e.claim_id}</strong></td>
                <td><span class="badge badge-info">${e.target_dimension}</span></td>
                <td><strong>${e.verbatim_claim_text}</strong></td>
                <td>
                  <span class="badge ${e.verification_verdict === 'VERIFIED' ? 'pill-verified' : e.verification_verdict === 'CONTRADICTED' ? 'pill-contradicted' : 'pill-partial'}">
                    ${e.verification_verdict}
                  </span>
                </td>
                <td style="font-size: 0.8rem; color: var(--text-secondary);">${e.verdict_reason}</td>
              </tr>
            `).join('')
          }
        </tbody>
      </table>
    </div>
  `;

  // Attach filter handler
  const filterBtns = container.querySelectorAll("#claim-filter-pills button");
  filterBtns.forEach(btn => {
    btn.addEventListener("click", () => {
      filterBtns.forEach(b => b.classList.remove("active-filter"));
      btn.classList.add("active-filter");
      const v = btn.getAttribute("data-verdict");
      const rows = container.querySelectorAll("#claims-view-table tbody tr");
      rows.forEach(r => {
        if (v === "all" || r.getAttribute("data-verdict") === v) {
          r.style.display = "";
        } else {
          r.style.display = "none";
        }
      });
    });
  });
}

// ==============================================================================
// VIEW CONTROLLER 6: AUTONOMY & INTERVENTION (/app/projects/{id}/autonomy)
// ==============================================================================
function renderAutonomyView(container, compId) {
  const p = currentPackageData || {};
  const intv = p.interventions || {};

  container.innerHTML = `
    <div style="margin-bottom: var(--space-6);">
      <h1 style="font-size: 1.75rem; margin-bottom: var(--space-1);">Autonomy & Human Intervention Analysis</h1>
      <p style="margin: 0; color: var(--text-secondary);">Task segmentation, intervention classification, and reaction latency heuristic analysis.</p>
    </div>

    <div class="metric-grid">
      <div class="kpi-card">
        <div class="kpi-label">Measured Autonomy Rate</div>
        <div class="kpi-value" style="color: ${intv.autonomous_rate_pct < 80 ? 'var(--color-warning)' : 'var(--color-success)'};">${intv.autonomous_rate_pct ?? "--"}%</div>
        <div class="kpi-sub">Bounded lower estimate (honest baseline)</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Human Intervention Rate (HIR)</div>
        <div class="kpi-value">${intv.human_intervention_rate_pct ?? "--"}%</div>
        <div class="kpi-sub">${intv.human_interventions || 0} assisted tasks observed</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Total Tasks Segmented</div>
        <div class="kpi-value">${intv.total_traces || 0}</div>
        <div class="kpi-sub">From ${intv.total_traces || 0} trace executions</div>
      </div>
    </div>

    <div class="panel-card" style="margin-bottom: var(--space-6);">
      <h3 style="margin-bottom: var(--space-3);">Task Segmentation Breakdown</h3>
      <p style="font-size: 0.85rem; margin-bottom: var(--space-4);">
        Agentic Diligence divides runtime traces into atomic tasks using inter-span gap analysis. If a gap exceeds the reaction threshold without telemetry, it is marked <code>[UNKNOWN]</code> rather than falsely assumed to be autonomous.
      </p>
      <div class="table-container">
        <table class="data-table">
          <thead>
            <tr>
              <th>Task Classification</th>
              <th>Observed Evidence Standard</th>
              <th>Task Count</th>
              <th>Percentage Share</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td><span class="badge badge-success">AUTONOMOUS</span></td>
              <td>Completed end-to-end with no human signal in telemetry spans.</td>
              <td class="font-mono">${(intv.total_traces || 0) - (intv.human_interventions || 0)}</td>
              <td><strong>${intv.autonomous_rate_pct ?? 0}%</strong></td>
            </tr>
            <tr>
              <td><span class="badge badge-danger">HUMAN EXPLICIT / INFERRED</span></td>
              <td>Human intervention recorded directly in spans or flagged by latency heuristic.</td>
              <td class="font-mono">${intv.human_interventions || 0}</td>
              <td><strong>${intv.human_intervention_rate_pct ?? 0}%</strong></td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  `;
}

// ==============================================================================
// VIEW CONTROLLER 7: UNIT ECONOMICS (/app/projects/{id}/economics)
// ==============================================================================
function renderEconomicsView(container, compId) {
  const p = currentPackageData || {};
  const econ = p.economics || {};

  container.innerHTML = `
    <div style="margin-bottom: var(--space-6);">
      <h1 style="font-size: 1.75rem; margin-bottom: var(--space-1);">Unit Economics & Cost Attribution</h1>
      <p style="margin: 0; color: var(--text-secondary);">Direct model expenditure, token efficiency ratios, and evaluation Trust Tax analysis.</p>
    </div>

    <div class="metric-grid">
      <div class="kpi-card">
        <div class="kpi-label">Cost Per Task (CPT)</div>
        <div class="kpi-value">$${Number(econ.telemetry_attributable_cost_per_task_usd || 0).toFixed(4)}</div>
        <div class="kpi-sub">Status: ${econ.overall_cost_status || "MEASURED"}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Monthly Run-Rate (Estimated)</div>
        <div class="kpi-value">$${Number(econ.estimated_monthly_spend_usd || 0).toLocaleString()}</div>
        <div class="kpi-sub">Based on observed trace volume</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Quality Check Trust Tax</div>
        <div class="kpi-value">${p.evaluation?.trust_tax_rate_pct ?? "--"}%</div>
        <div class="kpi-sub">Overhead spent on automated LLM judges</div>
      </div>
    </div>

    <div class="panel-card">
      <h3 style="margin-bottom: var(--space-3);">Token Economics & Model Expenditure</h3>
      <p style="font-size: 0.85rem; margin-bottom: var(--space-4);">Detailed pricing calculations using standardized v2026_09 provider rate cards:</p>
      <div class="table-container">
        <table class="data-table">
          <thead>
            <tr>
              <th>Provider / Model</th>
              <th>Prompt Tokens</th>
              <th>Completion Tokens</th>
              <th>Attributable Cost</th>
            </tr>
          </thead>
          <tbody>
            ${(p.dependencies?.providers || []).map(pr => `
              <tr>
                <td><strong>${pr.provider_name}</strong></td>
                <td class="font-mono">Observed in traces</td>
                <td class="font-mono">Observed in traces</td>
                <td class="font-mono" style="color: var(--accent-primary); font-weight: 600;">${pr.share_pct}% of Total Spend</td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

// ==============================================================================
// VIEW CONTROLLER 8: DEPENDENCIES & CASCADES (/app/projects/{id}/dependencies)
// ==============================================================================
function renderDependenciesView(container, compId) {
  const p = currentPackageData || {};
  const dep = p.dependencies || {};
  const casc = p.cascades || {};

  container.innerHTML = `
    <div style="margin-bottom: var(--space-6);">
      <h1 style="font-size: 1.75rem; margin-bottom: var(--space-1);">Provider Dependencies & Cascades</h1>
      <p style="margin: 0; color: var(--text-secondary);">Vendor concentration index (HHI), single points of failure (SPOF), and retry loop cost multipliers.</p>
    </div>

    <div class="metric-grid">
      <div class="kpi-card">
        <div class="kpi-label">Vendor Concentration (HHI)</div>
        <div class="kpi-value" style="color: ${dep.hhi_score > 6000 ? 'var(--color-danger)' : 'var(--color-success)'};">${dep.hhi_score ?? "--"}</div>
        <div class="kpi-sub">${dep.concentration_level || "MODERATE"} Concentration</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Cascade Overrun Multiplier</div>
        <div class="kpi-value">${casc.avg_cost_multiplier_on_failure || 1.0}x</div>
        <div class="kpi-sub">${casc.cascade_frequency_pct || 0}% tasks trapped in retry loops</div>
      </div>
    </div>

    <div class="panel-card">
      <h3 style="margin-bottom: var(--space-3);">Cloud & Model Providers Inventory</h3>
      <div class="table-container">
        <table class="data-table">
          <thead>
            <tr>
              <th>Provider</th>
              <th>Share of Workload</th>
              <th>Risk Classification</th>
            </tr>
          </thead>
          <tbody>
            ${(dep.providers || []).map(pr => `
              <tr>
                <td><strong>${pr.provider_name}</strong></td>
                <td><strong>${pr.share_pct}%</strong></td>
                <td><span class="badge ${pr.share_pct > 70 ? 'badge-danger' : 'badge-info'}">${pr.share_pct > 70 ? 'HIGH CONCENTRATION' : 'BALANCED'}</span></td>
              </tr>
            `).join('')}
          </tbody>
        </table>
      </div>
    </div>
  `;
}

// ==============================================================================
// VIEW CONTROLLER 9: AIBOM CYCLONEDX (/app/projects/{id}/aibom)
// ==============================================================================
function renderAIBOMView(container, compId) {
  const p = currentPackageData || {};
  const aibom = p.aibom || {};
  const models = aibom.models || [];
  const tools = aibom.tools || [];

  container.innerHTML = `
    <div style="margin-bottom: var(--space-6); display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: var(--space-4);">
      <div>
        <h1 style="font-size: 1.75rem; margin-bottom: var(--space-1);">AI Bill of Materials (AIBOM)</h1>
        <p style="margin: 0; color: var(--text-secondary);">Itemized software supply chain inventory exported to official OWASP CycloneDX 1.6.</p>
      </div>
      <div style="display: flex; gap: var(--space-3);">
        <a href="/api/v1/companies/${compId}/aibom/cyclonedx?spec_version=1.6" target="_blank" class="btn btn-outline btn-sm">
          <span>↓</span> Download CycloneDX 1.6 JSON
        </a>
      </div>
    </div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-6);">
      <div class="panel-card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-3);">
          <h3>Foundation Models</h3>
          <span class="badge badge-info">${models.length} Models</span>
        </div>
        <div class="table-container">
          <table class="data-table">
            <thead><tr><th>Model</th><th>Provider</th><th>Calls</th></tr></thead>
            <tbody>
              ${models.length === 0 ? '<tr><td colspan="3" style="text-align: center; color: var(--text-muted);">No models detected.</td></tr>' :
                models.map(m => `<tr><td><strong>${m.model_name}</strong></td><td>${m.provider_name}</td><td class="font-mono">${m.call_count}</td></tr>`).join('')
              }
            </tbody>
          </table>
        </div>
      </div>

      <div class="panel-card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-3);">
          <h3>External Tools & Sandboxes</h3>
          <span class="badge badge-warning">${tools.length} Tools</span>
        </div>
        <div class="table-container">
          <table class="data-table">
            <thead><tr><th>Tool Name</th><th>Type</th><th>Failure Rate</th></tr></thead>
            <tbody>
              ${tools.length === 0 ? '<tr><td colspan="3" style="text-align: center; color: var(--text-muted);">No tools detected.</td></tr>' :
                tools.map(t => `<tr><td><strong>${t.tool_name}</strong></td><td><span class="badge badge-info">${t.tool_type}</span></td><td class="font-mono">${t.failure_rate_pct}%</td></tr>`).join('')
              }
            </tbody>
          </table>
        </div>
      </div>
    </div>
  `;
}

// ==============================================================================
// VIEW CONTROLLER 10: EVIDENCE & PROVENANCE GRAPH (/app/projects/{id}/evidence)
// ==============================================================================
function renderEvidenceView(container, compId) {
  const p = currentPackageData || {};
  const records = p.evidence_records || [];

  container.innerHTML = `
    <div style="margin-bottom: var(--space-6);">
      <h1 style="font-size: 1.75rem; margin-bottom: var(--space-1);">Proof & Evidence Graph</h1>
      <p style="margin: 0; color: var(--text-secondary);">Verifiable chain of custody connecting diligence verdicts directly to raw trace IDs and SHA-256 digests.</p>
    </div>

    <div class="panel-card">
      <h3 style="margin-bottom: var(--space-3);">Auditable Evidence Records</h3>
      <div class="table-container">
        <table class="data-table">
          <thead>
            <tr>
              <th>Record ID</th>
              <th>Dimension</th>
              <th>Observed Value</th>
              <th>Trust Level</th>
              <th>Sample Size</th>
              <th>Provenance Digest</th>
            </tr>
          </thead>
          <tbody>
            ${records.length === 0 ? '<tr><td colspan="6" style="text-align: center; padding: 40px; color: var(--text-muted);">No evidence records anchored.</td></tr>' :
              records.map(r => `
                <tr>
                  <td class="font-mono"><strong>${r.record_id}</strong></td>
                  <td><span class="badge badge-info">${r.claim_category}</span></td>
                  <td><strong>${r.observed_value}</strong></td>
                  <td><span class="badge badge-success">${r.epistemic_trust_level}</span></td>
                  <td class="font-mono">n=${r.sample_size}</td>
                  <td class="font-mono" style="font-size: 0.725rem; color: var(--text-muted);">${(r.raw_payload_hash || '').substring(0, 20)}...</td>
                </tr>
              `).join('')
            }
          </tbody>
        </table>
      </div>
    </div>
  `;
}

// ==============================================================================
// VIEW CONTROLLER 11: TOOL SAFETY & SECURITY (/app/projects/{id}/security)
// ==============================================================================
function renderSecurityView(container, compId) {
  const p = currentPackageData || {};
  const risk = p.tool_risk || {};

  container.innerHTML = `
    <div style="margin-bottom: var(--space-6);">
      <h1 style="font-size: 1.75rem; margin-bottom: var(--space-1);">Tool Execution Risk & Blast Radius</h1>
      <p style="margin: 0; color: var(--text-secondary);">Auditing agent write permissions, database modification rights, and unconstrained execution privileges.</p>
    </div>

    <div class="metric-grid">
      <div class="kpi-card">
        <div class="kpi-label">Tool Risk Score</div>
        <div class="kpi-value" style="color: ${risk.tool_risk_score > 40 ? 'var(--color-danger)' : 'var(--color-success)'};">${risk.tool_risk_score ?? "--"} / 100</div>
        <div class="kpi-sub">Overall Hazard Level: ${risk.risk_level || "LOW"}</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Total Tool Invocations</div>
        <div class="kpi-value">${risk.total_tool_calls ?? 0}</div>
        <div class="kpi-sub">Observed in runtime traces</div>
      </div>
    </div>
  `;
}

// ==============================================================================
// VIEW CONTROLLER 12: MOAT & DEFENSIBILITY (/app/projects/{id}/defensibility)
// ==============================================================================
function renderDefensibilityView(container, compId) {
  const p = currentPackageData || {};
  const moat = p.defensibility || {};

  container.innerHTML = `
    <div style="margin-bottom: var(--space-6);">
      <h1 style="font-size: 1.75rem; margin-bottom: var(--space-1);">AI Moat & Defensibility Audit</h1>
      <p style="margin: 0; color: var(--text-secondary);">Proprietary scaffolding index vs. commodity prompt wrapper analysis.</p>
    </div>

    <div class="metric-grid">
      <div class="kpi-card">
        <div class="kpi-label">Moat Defensibility Score</div>
        <div class="kpi-value">${moat.moat_score ?? "--"} / 100</div>
        <div class="kpi-sub">${moat.moat_classification || "MODERATE"} DEFENSIBILITY</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Est. Time to Replicate</div>
        <div class="kpi-value">~${moat.estimated_replication_months ?? "--"} mos</div>
        <div class="kpi-sub">Engineering effort for competing team</div>
      </div>
      <div class="kpi-card">
        <div class="kpi-label">Est. Replication Cost</div>
        <div class="kpi-value">$${Number(moat.estimated_replication_cost_usd || 0).toLocaleString()}</div>
        <div class="kpi-sub">Total capital required to duplicate architecture</div>
      </div>
    </div>
  `;
}

// ==============================================================================
// VIEW CONTROLLER 13: STRESS SIMULATOR (/app/projects/{id}/stress-test)
// ==============================================================================
function renderStressTestView(container, compId) {
  const p = currentPackageData || {};
  const baseCost = Number(p.economics?.telemetry_attributable_cost_per_task_usd || 0.005);

  container.innerHTML = `
    <div style="margin-bottom: var(--space-6);">
      <h1 style="font-size: 1.75rem; margin-bottom: var(--space-1);">What-If Financial Stress Simulator</h1>
      <p style="margin: 0; color: var(--text-secondary);">Simulate volume surges, token price shocks, and human operator wage impacts on fully-loaded gross margins.</p>
    </div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-6);">
      <div class="panel-card">
        <h3 style="margin-bottom: var(--space-4);">Simulator Controls</h3>
        <div class="form-group">
          <label class="form-label">Task Volume Multiplier: <span id="val-vol" style="color: var(--accent-primary); font-weight: 700;">1.0x</span></label>
          <input type="range" id="sim-vol" min="1" max="10" step="0.5" value="1" style="width: 100%;">
        </div>
        <div class="form-group">
          <label class="form-label">Provider Token Price Shock: <span id="val-price" style="color: var(--color-warning); font-weight: 700;">0%</span></label>
          <input type="range" id="sim-price" min="-25" max="50" step="5" value="0" style="width: 100%;">
        </div>
        <div class="form-group">
          <label class="form-label">Human Operator Hourly Wage: <span id="val-wage" style="color: var(--text-primary); font-weight: 700;">$28/hr</span></label>
          <input type="range" id="sim-wage" min="15" max="60" step="1" value="28" style="width: 100%;">
        </div>
      </div>

      <div class="panel-card" style="background: var(--bg-surface-2);">
        <h3 style="margin-bottom: var(--space-4);">Projected Financial Impact</h3>
        <div style="display: flex; flex-direction: column; gap: var(--space-3);">
          <div style="display: flex; justify-content: space-between;">
            <span style="color: var(--text-secondary);">Stressed LLM Cost/Task:</span>
            <span class="font-mono" id="out-llm" style="font-weight: 700;">$${baseCost.toFixed(4)}</span>
          </div>
          <div style="display: flex; justify-content: space-between;">
            <span style="color: var(--text-secondary);">Stressed Fully-Loaded Cost:</span>
            <span class="font-mono" id="out-loaded" style="font-weight: 700; color: var(--accent-secondary);">$${(baseCost * 1.5).toFixed(4)}</span>
          </div>
          <div style="display: flex; justify-content: space-between;">
            <span style="color: var(--text-secondary);">Projected Gross Margin:</span>
            <span class="font-mono" id="out-margin" style="font-weight: 700; color: var(--color-success);">68.4%</span>
          </div>
        </div>
      </div>
    </div>
  `;

  // Attach simulator slider interactions
  const sVol = container.querySelector("#sim-vol");
  const sPrice = container.querySelector("#sim-price");
  const sWage = container.querySelector("#sim-wage");

  function recalc() {
    const vol = parseFloat(sVol.value);
    const priceShock = parseFloat(sPrice.value);
    const wage = parseFloat(sWage.value);

    container.querySelector("#val-vol").innerText = `${vol.toFixed(1)}x`;
    container.querySelector("#val-price").innerText = `${priceShock > 0 ? '+' : ''}${priceShock}%`;
    container.querySelector("#val-wage").innerText = `$${wage}/hr`;

    const stressedLlm = baseCost * (1 + priceShock / 100.0);
    const humanOverhead = (wage / 28.0) * 0.003;
    const fullyLoaded = stressedLlm + humanOverhead;
    const margin = Math.max(0, 100 - (fullyLoaded / 0.05) * 100);

    container.querySelector("#out-llm").innerText = `$${stressedLlm.toFixed(4)}`;
    container.querySelector("#out-loaded").innerText = `$${fullyLoaded.toFixed(4)}`;
    container.querySelector("#out-margin").innerText = `${margin.toFixed(1)}%`;
  }

  sVol.addEventListener("input", recalc);
  sPrice.addEventListener("input", recalc);
  sWage.addEventListener("input", recalc);
}

// ==============================================================================
// VIEW CONTROLLER 14: TARGET COMPARISON (/app/projects/{id}/comparison)
// ==============================================================================
function renderComparisonView(container, compId) {
  container.innerHTML = `
    <div style="margin-bottom: var(--space-6);">
      <h1 style="font-size: 1.75rem; margin-bottom: var(--space-1);">Head-to-Head Diligence Comparison</h1>
      <p style="margin: 0; color: var(--text-secondary);">Side-by-side comparative technical diligence audit between two AI agent targets.</p>
    </div>

    <div class="panel-card" style="margin-bottom: var(--space-6);">
      <div style="display: flex; gap: var(--space-4); align-items: flex-end; margin-bottom: var(--space-4);">
        <div class="form-group" style="flex: 1; margin: 0;">
          <label class="form-label">Target A (Current):</label>
          <input type="text" class="form-control" value="${currentPackageData?.company?.name || compId}" disabled>
        </div>
        <div class="form-group" style="flex: 1; margin: 0;">
          <label class="form-label" for="select-comp-b">Compare Against Target B:</label>
          <select id="select-comp-b" class="form-control">
            <option value="scenario_b">Company B (Verified High Automation 96% AI)</option>
            <option value="scenario_c">Company C (Falsified Pitch Claims, 80% Human)</option>
            <option value="scenario_f">Company F (98% Single-Provider Lock-in)</option>
            <option value="scenario_j">Company J (90% Self-Hosted Local Models)</option>
          </select>
        </div>
        <button id="btn-run-compare" class="btn btn-primary">Compare Targets →</button>
      </div>

      <div id="compare-results-container">
        <div style="padding: 30px; text-align: center; color: var(--text-muted);">
          Click "Compare Targets" to generate side-by-side dimensional audit.
        </div>
      </div>
    </div>
  `;

  const btn = container.querySelector("#btn-run-compare");
  btn.addEventListener("click", async () => {
    const targetB = container.querySelector("#select-comp-b").value;
    btn.innerText = "Comparing...";
    btn.disabled = true;

    try {
      const res = await fetch(`/api/v1/comparison?target_a=${compId}&target_b=${targetB}`);
      if (!res.ok) throw new Error("Comparison calculation failed");
      const data = await res.json();
      
      const resContainer = container.querySelector("#compare-results-container");
      resContainer.innerHTML = `
        <div style="margin-top: var(--space-4);">
          <h3 style="margin-bottom: var(--space-3);">${data.comparison_title || "Target Comparison Matrix"}</h3>
          <div class="table-container">
            <table class="data-table">
              <thead><tr><th>Dimension</th><th>Target A</th><th>Target B</th><th>Advantage</th></tr></thead>
              <tbody>
                ${(data.matrix || []).map(row => `
                  <tr>
                    <td><strong>${row.dimension}</strong></td>
                    <td class="font-mono">${row.target_a_value}</td>
                    <td class="font-mono">${row.target_b_value}</td>
                    <td><span class="badge badge-success">${row.advantage}</span></td>
                  </tr>
                `).join('')}
              </tbody>
            </table>
          </div>
        </div>
      `;
    } catch (err) {
      showToast("Error comparing targets: " + err.message, "error");
    } finally {
      btn.innerText = "Compare Targets →";
      btn.disabled = false;
    }
  });
}

// ==============================================================================
// VIEW CONTROLLER 15: DEAL MEMO & REPORTS (/app/projects/{id}/reports)
// ==============================================================================
function renderReportsView(container, compId) {
  const p = currentPackageData || {};
  const memo = p.memo || {};
  const pkgFiles = p.package_files || {};

  container.innerHTML = `
    <div style="margin-bottom: var(--space-6); display: flex; justify-content: space-between; align-items: flex-end; flex-wrap: wrap; gap: var(--space-4);">
      <div>
        <h1 style="font-size: 1.75rem; margin-bottom: var(--space-1);">Investment Committee Memo & Audit Packages</h1>
        <p style="margin: 0; color: var(--text-secondary);">Executive diligence recommendation, red flag taxonomy, and verifiable bundle exports.</p>
      </div>
      <div style="display: flex; gap: var(--space-2);">
        <a href="/api/v1/companies/${compId}/pdf" target="_blank" class="btn btn-primary btn-sm">📄 Download PDF Report</a>
        <a href="/api/v1/companies/${compId}/package" target="_blank" class="btn btn-secondary btn-sm">📦 JSON Package</a>
      </div>
    </div>

    <!-- Deal Memo Verdict Banner -->
    <div class="card" style="margin-bottom: var(--space-6); border-left: 5px solid ${memo.deal_verdict === 'BUY' ? 'var(--color-success)' : 'var(--color-warning)'}; background: var(--bg-surface-2);">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-2);">
        <h3 style="margin: 0;">Deal Recommendation: ${memo.deal_verdict || "CONDITIONAL"}</h3>
        <span class="badge badge-info">Risk Score: ${memo.diligence_risk_score || 50} / 100</span>
      </div>
      <p style="margin-bottom: var(--space-3); color: var(--text-primary); font-size: 0.95rem;">${memo.executive_verdict_summary || "Automated evaluation completed with findings."}</p>
    </div>

    <!-- Red / Yellow / Green Flags -->
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--space-6); margin-bottom: var(--space-8);">
      <div class="panel-card">
        <h4 style="color: var(--color-danger); margin-bottom: var(--space-3);">Critical Red Flags (${(memo.red_flags || []).length})</h4>
        <div style="display: flex; flex-direction: column; gap: var(--space-3);">
          ${(memo.red_flags || []).length === 0 ? '<p style="color: var(--text-muted); font-size: 0.85rem;">No critical red flags identified.</p>' :
            (memo.red_flags || []).map(rf => `
              <div style="padding: var(--space-3); background: var(--color-danger-bg); border-left: 3px solid var(--color-danger); border-radius: var(--radius-sm);">
                <div style="font-weight: 600; color: var(--color-danger); font-size: 0.85rem;">${rf.title}</div>
                <div style="font-size: 0.775rem; color: var(--text-secondary); margin-top: 2px;">${rf.detail}</div>
              </div>
            `).join('')
          }
        </div>
      </div>

      <div class="panel-card">
        <h4 style="color: var(--color-warning); margin-bottom: var(--space-3);">Operational Yellow Flags (${(memo.yellow_flags || []).length})</h4>
        <div style="display: flex; flex-direction: column; gap: var(--space-3);">
          ${(memo.yellow_flags || []).length === 0 ? '<p style="color: var(--text-muted); font-size: 0.85rem;">No operational warnings identified.</p>' :
            (memo.yellow_flags || []).map(yf => `
              <div style="padding: var(--space-3); background: var(--color-warning-bg); border-left: 3px solid var(--color-warning); border-radius: var(--radius-sm);">
                <div style="font-weight: 600; color: var(--color-warning); font-size: 0.85rem;">${yf.title}</div>
              </div>
            `).join('')
          }
        </div>
      </div>
    </div>
  `;
}

// ==============================================================================
// VIEW CONTROLLER 16: INTEGRATIONS & OTel ADAPTERS (/app/integrations)
// ==============================================================================
function renderIntegrationsView(container) {
  container.innerHTML = `
    <div style="margin-bottom: var(--space-6);">
      <h1 style="font-size: 1.75rem; margin-bottom: var(--space-1);">OpenTelemetry & Multi-Source Ingestion</h1>
      <p style="margin: 0; color: var(--text-secondary);">Direct trace ingestion gateways, MCP observer proxies, and browser extension bridges.</p>
    </div>

    <div style="display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: var(--space-6); margin-bottom: var(--space-8);">
      <div class="panel-card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-3);">
          <h3>OpenTelemetry HTTP/JSON</h3>
          <span class="badge badge-success">Active</span>
        </div>
        <p style="font-size: 0.85rem; margin-bottom: var(--space-3);">Direct ingestion endpoint adhering to OpenTelemetry GenAI Semantic Conventions v1.28.0.</p>
        <div style="background: var(--bg-surface-2); padding: var(--space-3); border-radius: var(--radius-md); font-family: var(--font-mono); font-size: 0.775rem; color: var(--accent-primary);">
          POST http://127.0.0.1:8000/v1/traces
        </div>
      </div>

      <div class="panel-card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-3);">
          <h3>Model Context Protocol (MCP)</h3>
          <span class="badge badge-success">Active</span>
        </div>
        <p style="font-size: 0.85rem; margin-bottom: var(--space-3);">Stdio and HTTP SSE proxy observer intercepting tool schemas, requests, and returned results.</p>
        <div style="background: var(--bg-surface-2); padding: var(--space-3); border-radius: var(--radius-md); font-family: var(--font-mono); font-size: 0.775rem; color: var(--accent-secondary);">
          agd-proxy --observe-stdio --port 8000
        </div>
      </div>

      <div class="panel-card">
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-3);">
          <h3>Browser Agent Extension</h3>
          <span class="badge badge-info">Bridge Ready</span>
        </div>
        <p style="font-size: 0.85rem; margin-bottom: var(--space-3);">DOM action auditor capturing human approval dialogs, DOM write events, and navigation hops.</p>
        <div style="background: var(--bg-surface-2); padding: var(--space-3); border-radius: var(--radius-md); font-family: var(--font-mono); font-size: 0.775rem; color: var(--color-warning);">
          POST /api/v1/evidence/ingest?source_type=browser
        </div>
      </div>
    </div>
  `;
}

// ==============================================================================
// VIEW CONTROLLER 17: SETTINGS (/app/settings)
// ==============================================================================
function renderSettingsView(container) {
  container.innerHTML = `
    <div style="max-width: 800px;">
      <div style="margin-bottom: var(--space-6);">
        <h1 style="font-size: 1.75rem; margin-bottom: var(--space-1);">Workspace Settings & Diagnostic Status</h1>
        <p style="margin: 0; color: var(--text-secondary);">System environment, rate cards, and storage diagnostics.</p>
      </div>

      <div class="panel-card" style="margin-bottom: var(--space-6);">
        <h3 style="margin-bottom: var(--space-4);">System Diagnostics</h3>
        <div style="display: flex; flex-direction: column; gap: var(--space-3); font-size: 0.85rem;">
          <div style="display: flex; justify-content: space-between; padding-bottom: var(--space-2); border-bottom: 1px solid var(--border-subtle);">
            <span style="color: var(--text-secondary);">Application Version:</span>
            <span class="font-mono">v0.1.0 Enterprise</span>
          </div>
          <div style="display: flex; justify-content: space-between; padding-bottom: var(--space-2); border-bottom: 1px solid var(--border-subtle);">
            <span style="color: var(--text-secondary);">Database Storage:</span>
            <span class="font-mono">SQLite WAL Mode (Durable Evidence Enabled)</span>
          </div>
          <div style="display: flex; justify-content: space-between; padding-bottom: var(--space-2); border-bottom: 1px solid var(--border-subtle);">
            <span style="color: var(--text-secondary);">Pricing Version:</span>
            <span class="font-mono">v2026_09 (Standardized Sep 2026 Rate Cards)</span>
          </div>
          <div style="display: flex; justify-content: space-between;">
            <span style="color: var(--text-secondary);">CycloneDX Specification:</span>
            <span class="font-mono">CycloneDX JSON 1.6 & 1.5</span>
          </div>
        </div>
      </div>
    </div>
  `;
}

// ==============================================================================
// TELEMETRY UPLOAD MODAL CONTROLLER
// ==============================================================================
function setupUploadModal() {
  const modal = document.getElementById("modal-upload");
  const openBtn = document.getElementById("btn-upload-traces-topbar");
  const closeBtn = document.getElementById("btn-close-upload-modal");
  const cancelBtn = document.getElementById("btn-cancel-upload");
  const submitBtn = document.getElementById("btn-submit-upload");
  const textarea = document.getElementById("textarea-traces");
  const feedback = document.getElementById("upload-feedback");

  if (!modal) return;

  if (openBtn) {
    openBtn.addEventListener("click", () => {
      modal.classList.add("open");
      if (feedback) feedback.style.display = "none";
    });
  }

  const close = () => modal.classList.remove("open");
  if (closeBtn) closeBtn.addEventListener("click", close);
  if (cancelBtn) cancelBtn.addEventListener("click", close);

  if (submitBtn) {
    submitBtn.addEventListener("click", async () => {
      const rawText = textarea.value.trim();
      if (!rawText) {
        alert("Please paste a valid OpenTelemetry JSON payload.");
        return;
      }

      submitBtn.innerText = "Ingesting...";
      submitBtn.disabled = true;

      try {
        const parsed = JSON.parse(rawText);
        const url = `/v1/traces${currentCompanyId ? '?company_id=' + currentCompanyId : ''}`;
        const res = await fetch(url, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(parsed)
        });

        const data = await res.json();
        if (res.ok) {
          showToast(`Ingestion Success! ${data.spans_count || 1} spans anchored.`, "success");
          close();
          textarea.value = "";
          await loadCompaniesList();
          if (currentCompanyId) {
            currentPackageData = null;
            handleRoute(window.location.pathname);
          }
        } else {
          throw new Error(data.error || "Ingestion rejected by server");
        }
      } catch (err) {
        if (feedback) {
          feedback.style.display = "block";
          feedback.style.background = "var(--color-danger-bg)";
          feedback.style.color = "var(--color-danger)";
          feedback.innerText = "Ingestion Error: " + err.message;
        }
      } finally {
        submitBtn.innerText = "Submit & Ingest Telemetry";
        submitBtn.disabled = false;
      }
    });
  }
}
