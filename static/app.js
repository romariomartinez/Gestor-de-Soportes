const MONTHS = [
  ["", "Todos"],
  ["1", "Enero"],
  ["2", "Febrero"],
  ["3", "Marzo"],
  ["4", "Abril"],
  ["5", "Mayo"],
  ["6", "Junio"],
  ["7", "Julio"],
  ["8", "Agosto"],
  ["9", "Septiembre"],
  ["10", "Octubre"],
  ["11", "Noviembre"],
  ["12", "Diciembre"],
];

const state = {
  user: null,
  permissions: new Set(),
  eps: [],
  settings: {},
  supabase: null,
  activeView: "dashboard",
  supportFilters: {},
  quickFilters: {},
  supportsPage: 1,
  supportsLimit: 10,
  years: [],
  uploadResults: [],
  cutCycle: null,
};

const COLORS = ["#1457e8", "#09a3b8", "#1f9d64", "#76b94a", "#f4a62a", "#e2455a", "#7566df", "#8793a6"];

const $ = (selector, root = document) => root.querySelector(selector);
const $$ = (selector, root = document) => Array.from(root.querySelectorAll(selector));

function icon(name) {
  const icons = {
    dashboard: '<path d="M4 13h6V4H4v9Zm10 7h6V4h-6v16ZM4 20h6v-4H4v4Z"/>',
    upload: '<path d="M12 16V4m0 0 4 4m-4-4-4 4"/><path d="M4 16v3a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-3"/>',
    table: '<path d="M4 5h16v14H4z"/><path d="M4 10h16M10 5v14"/>',
    building: '<path d="M4 20h16"/><path d="M6 20V5h8v15"/><path d="M14 10h4v10M9 8h2M9 12h2M9 16h2"/>',
    chart: '<path d="M4 19V5"/><path d="M4 19h16"/><path d="M8 16v-4M12 16V8M16 16v-7"/>',
    users: '<path d="M16 21v-2a4 4 0 0 0-4-4H7a4 4 0 0 0-4 4v2"/><circle cx="9.5" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87"/><path d="M16 3.13a4 4 0 0 1 0 7.75"/>',
    settings: '<path d="M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7Z"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1-2.83 2.83l-.06-.06A1.65 1.65 0 0 0 15 19.4a1.65 1.65 0 0 0-1 .6 1.65 1.65 0 0 0-.4 1.08V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 8.6 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.6 15a1.65 1.65 0 0 0-.6-1 1.65 1.65 0 0 0-1.08-.4H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 8.6a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.6a1.65 1.65 0 0 0 1-.6 1.65 1.65 0 0 0 .4-1.08V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9c.4.2.78.52 1 .9.22.38.34.82.33 1.26V11a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.24.6Z"/>',
    logout: '<path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"/><path d="m16 17 5-5-5-5"/><path d="M21 12H9"/>',
    refresh: '<path d="M20 11a8.1 8.1 0 0 0-15.5-2M4 4v5h5"/><path d="M4 13a8.1 8.1 0 0 0 15.5 2M20 20v-5h-5"/>',
    bell: '<path d="M18 8a6 6 0 0 0-12 0c0 7-3 7-3 9h18c0-2-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/>',
    cloud: '<path d="M17.5 19a4.5 4.5 0 0 0 .5-8.97A6 6 0 0 0 6.3 8.5 4.5 4.5 0 0 0 6.5 17H9"/><path d="M12 12v8m0-8-3 3m3-3 3 3"/>',
    file: '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/><path d="M8 13h8M8 17h5"/>',
    download: '<path d="M12 3v12m0 0 4-4m-4 4-4-4"/><path d="M4 17v3h16v-3"/>',
    plus: '<path d="M12 5v14M5 12h14"/>',
    x: '<path d="M18 6 6 18M6 6l12 12"/>',
    edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5Z"/>',
    trash: '<path d="M3 6h18"/><path d="M8 6V4h8v2"/><path d="M6 6l1 15h10l1-15"/><path d="M10 11v6M14 11v6"/>',
    eye: '<path d="M2 12s3.5-7 10-7 10 7 10 7-3.5 7-10 7S2 12 2 12Z"/><circle cx="12" cy="12" r="3"/>',
    fullscreen: '<path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M16 3h3a2 2 0 0 1 2 2v3"/><path d="M8 21H5a2 2 0 0 1-2-2v-3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/>',
    save: '<path d="M19 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h11l5 5v11a2 2 0 0 1-2 2Z"/><path d="M17 21v-8H7v8"/><path d="M7 3v5h8"/>',
  };
  return `<svg class="icon" viewBox="0 0 24 24" aria-hidden="true">${icons[name] || icons.file}</svg>`;
}

function renderIcons(root = document) {
  $$("[data-icon]", root).forEach((el) => {
    el.innerHTML = icon(el.dataset.icon);
  });
}

function escapeHtml(value) {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}

function qs(params) {
  const search = new URLSearchParams();
  Object.entries(params || {}).forEach(([key, value]) => {
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      search.set(key, value);
    }
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}

async function api(path, options = {}) {
  const fetchOptions = {
    method: options.method || "GET",
    credentials: "same-origin",
    headers: options.headers || {},
  };
  if (options.body !== undefined) {
    fetchOptions.headers["Content-Type"] = "application/json";
    fetchOptions.body = JSON.stringify(options.body);
  }
  if (options.formData) {
    fetchOptions.body = options.formData;
  }

  const response = await fetch(path, fetchOptions);
  const type = response.headers.get("Content-Type") || "";
  if (!response.ok) {
    let message = response.statusText;
    if (type.includes("application/json")) {
      const data = await response.json();
      message = data.error || message;
    }
    throw new Error(message);
  }
  if (type.includes("application/json")) {
    return response.json();
  }
  return response.blob();
}

function toast(message, kind = "success") {
  const item = document.createElement("div");
  item.className = `toast ${kind}`;
  item.textContent = message;
  $("#toastStack").appendChild(item);
  setTimeout(() => item.remove(), 4200);
}

function has(permission) {
  return !permission || state.permissions.has(permission);
}

function initials(name) {
  return String(name || "U")
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((part) => part[0])
    .join("")
    .toUpperCase();
}

function formatNumber(value) {
  return new Intl.NumberFormat("es-CO").format(value || 0);
}

function formatDate(value) {
  if (!value) return "Pendiente";
  const [year, month, day] = value.split("-");
  return `${day}/${month}/${year}`;
}

function formatDateTime(value) {
  if (!value) return "";
  return value.replace("T", " ").slice(0, 16);
}

function statusClass(status) {
  if (status === "pendiente_revision") return "pending";
  if (status === "duplicado") return "duplicate";
  if (status === "eliminado") return "deleted";
  return "";
}

function statusLabel(status) {
  return {
    guardado: "Guardado",
    pendiente_revision: "Pendiente revisión",
    duplicado: "Duplicado",
    eliminado: "Eliminado",
  }[status] || status || "Sin estado";
}

function collectForm(form) {
  const data = {};
  new FormData(form).forEach((value, key) => {
    data[key] = value;
  });
  return data;
}

function epsOptions(selected = "") {
  const options = ['<option value="">Todas</option>'];
  state.eps
    .filter((eps) => eps.active)
    .forEach((eps) => {
      options.push(`<option value="${escapeHtml(eps.name)}" ${eps.name === selected ? "selected" : ""}>${escapeHtml(eps.name)}</option>`);
    });
  return options.join("");
}

function monthOptions(selected = "") {
  return MONTHS.map(([value, label]) => `<option value="${value}" ${String(selected) === value ? "selected" : ""}>${label}</option>`).join("");
}

function corteOptions(selected = "") {
  return [
    ["", "Todos"],
    ["1", "Corte 1"],
    ["2", "Corte 2"],
    ["3", "Corte 3"],
  ]
    .map(([value, label]) => `<option value="${value}" ${String(selected) === value ? "selected" : ""}>${label}</option>`)
    .join("");
}

function corteFormOptions(selected = "") {
  return [
    ["", "Seleccionar corte"],
    ["1", "Corte 1"],
    ["2", "Corte 2"],
    ["3", "Corte 3"],
  ]
    .map(([value, label]) => `<option value="${value}" ${String(selected) === value ? "selected" : ""}>${label}</option>`)
    .join("");
}

function yearOptions(selected = "") {
  const years = state.years.length ? state.years : [new Date().getFullYear()];
  return ['<option value="">Todos</option>']
    .concat(years.map((year) => `<option value="${year}" ${String(selected) === String(year) ? "selected" : ""}>${year}</option>`))
    .join("");
}

function setAppVisible(visible) {
  $("#loginScreen").classList.toggle("hidden", visible);
  $("#appShell").classList.toggle("hidden", !visible);
}

async function bootstrapApp(session) {
  state.user = session.user;
  state.permissions = new Set(session.permissions || []);
  $("#userName").textContent = state.user.name;
  $("#userRole").textContent = state.user.role;
  $("#userAvatar").textContent = initials(state.user.name);
  $$(".nav-item").forEach((btn) => {
    btn.classList.toggle("hidden", !has(btn.dataset.permission));
  });
  setAppVisible(true);
  await loadSettings();
  await loadEps();
  await loadDashboard();
  buildSupportFilters();
  bindPermissionVisibility();
  renderIcons();
}

function bindPermissionVisibility() {
  $("#newEpsBtn").classList.toggle("hidden", !has("manage_eps"));
  $("#newUserBtn").classList.toggle("hidden", !has("manage_users"));
}

async function loadSettings() {
  const data = await api("/api/settings");
  state.settings = data.settings || {};
  $("#systemName").textContent = state.settings.system_name || "Soportes EPS";
  $("#companyName").textContent = state.settings.company_name || "Gestor de Radicaciones";
  if (state.settings.primary_color) {
    document.documentElement.style.setProperty("--primary", state.settings.primary_color);
  }
  state.supportsLimit = Number(state.settings.page_size || 10);
}

async function loadSupabaseStatus() {
  if (!has("configure")) return;
  try {
    state.supabase = await api("/api/supabase/status");
  } catch {
    state.supabase = { enabled: false, last_sync: { ok: false, message: "No se pudo consultar Supabase." } };
  }
}

async function loadEps() {
  const data = await api("/api/eps");
  state.eps = data.items || [];
}

async function loadDashboard() {
  const topFilters = {
    year: $("#topYear").value || "",
    month: $("#topMonth").value || "",
    ...state.quickFilters,
  };
  const data = await api(`/api/dashboard${qs(topFilters)}`);
  state.years = data.years || [];
  renderTopFilters();
  renderStats(data.stats);
  renderEpsChart(data.by_eps || []);
  renderRecentSupports(data.recent || []);
  buildQuickFilters();
  renderIcons();
}

function renderTopFilters() {
  const yearSelect = $("#topYear");
  const monthSelect = $("#topMonth");
  const selectedYear = yearSelect.value;
  const selectedMonth = monthSelect.value;
  yearSelect.innerHTML = yearOptions(selectedYear);
  monthSelect.innerHTML = monthOptions(selectedMonth);
}

function renderStats(stats) {
  const items = [
    ["Total soportes", stats.total_supports, "PDFs almacenados", "file", "#7566df"],
    ["EPS registradas", stats.eps_total, "Catálogo activo", "building", "#1f9d64"],
    ["Cargados hoy", stats.today_count, "Nuevas radicaciones", "upload", "#09a3b8"],
    ["Cargados este mes", stats.month_count, "Actividad del periodo", "chart", "#f4a62a"],
    ["Pendientes revisión", stats.pending, "Completar datos", "settings", "#e2455a"],
  ];
  $("#statGrid").innerHTML = items
    .map(
      ([label, value, helper, iconName, color]) => `
      <article class="stat-card">
        <div class="stat-icon" style="background:${color}">${icon(iconName)}</div>
        <div>
          <span>${label}</span>
          <strong>${formatNumber(value)}</strong>
          <small>${helper}</small>
        </div>
      </article>`
    )
    .join("");
}

function renderEpsChart(rows) {
  const total = rows.reduce((sum, row) => sum + row.total, 0);
  if (!total) {
    $("#epsChart").innerHTML = `<div class="empty-state">${icon("chart")}<p>Aún no hay soportes cargados.</p></div>`;
    return;
  }
  let acc = 0;
  const segments = rows.map((row, index) => {
    const start = (acc / total) * 100;
    acc += row.total;
    const end = (acc / total) * 100;
    return `${COLORS[index % COLORS.length]} ${start}% ${end}%`;
  });
  $("#epsChart").innerHTML = `
    <div class="donut" style="background: conic-gradient(${segments.join(",")})"></div>
    <div class="legend">
      ${rows
        .map(
          (row, index) => `
          <div class="legend-row">
            <span class="swatch" style="background:${COLORS[index % COLORS.length]}"></span>
            <span>${escapeHtml(row.label)}</span>
            <strong>${formatNumber(row.total)}</strong>
          </div>`
        )
        .join("")}
    </div>`;
}

function supportActions(row) {
  const deleteButton = has("delete_support")
    ? `<button class="mini-btn" title="Eliminar" data-action="delete" data-id="${row.id}">${icon("trash")}</button>`
    : "";
  const editButton = has("edit_support")
    ? `<button class="mini-btn" title="Editar datos" data-action="edit" data-id="${row.id}">${icon("edit")}</button>`
    : "";
  return `
    <div class="row-actions">
      <button class="mini-btn" title="Ver PDF" data-action="view" data-id="${row.id}">${icon("eye")}</button>
      <button class="mini-btn" title="Descargar PDF" data-action="download" data-id="${row.id}">${icon("download")}</button>
      ${editButton}
      ${deleteButton}
    </div>`;
}

function supportsTable(rows, compact = false) {
  if (!rows.length) return `<div class="empty-state">${icon("file")}<p>No hay soportes para mostrar.</p></div>`;
  if (compact) {
    return `
      <div class="table-shell compact-table">
        <table>
          <thead>
            <tr>
              <th>EPS</th>
              <th>No. Radicado</th>
              <th>Corte</th>
              <th>Facturas</th>
              <th>Fecha radicación</th>
              <th>Subido por</th>
            </tr>
          </thead>
          <tbody>
            ${rows
              .map(
                (row) => `
                <tr>
                  <td><span class="badge-dot">${escapeHtml(row.eps_name || "Sin EPS")}</span></td>
                  <td>${escapeHtml(row.radicado || "Pendiente")}</td>
                  <td>${escapeHtml(row.corte_label || "Sin corte")}</td>
                  <td>${formatNumber(row.invoice_count || 0)}</td>
                  <td>${formatDate(row.radication_date)}</td>
                  <td>${escapeHtml(row.uploaded_by_name)}</td>
                </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>`;
  }
  return `
    <div class="table-shell">
      <table>
        <thead>
          <tr>
            <th>EPS</th>
            <th>No. Radicado</th>
            <th>Factura</th>
            <th>Corte</th>
            <th>Facturas</th>
            <th>Fecha radicación</th>
            <th>Fecha carga</th>
            <th>Usuario</th>
            <th>Estado</th>
            ${compact ? "" : "<th>Acciones</th>"}
          </tr>
        </thead>
        <tbody>
          ${rows
            .map(
              (row) => `
              <tr>
                <td><span class="badge-dot">${escapeHtml(row.eps_name || "Sin EPS")}</span></td>
                <td>${escapeHtml(row.radicado || "Pendiente")}</td>
                <td>${escapeHtml(row.factura || "Sin dato")}</td>
                <td>${escapeHtml(row.corte_label || "Sin corte")}</td>
                <td>${formatNumber(row.invoice_count || 0)}</td>
                <td>${formatDate(row.radication_date)}</td>
                <td>${formatDateTime(row.uploaded_at)}</td>
                <td>${escapeHtml(row.uploaded_by_name)}</td>
                <td><span class="status-pill ${statusClass(row.status)}">${statusLabel(row.status)}</span></td>
                ${compact ? "" : `<td>${supportActions(row)}</td>`}
              </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
}

function renderRecentSupports(rows) {
  $("#recentSupports").innerHTML = supportsTable(rows, true);
}

function buildQuickFilters() {
  const form = $("#quickFilters");
  form.innerHTML = `
    <label>EPS<select name="eps">${epsOptions(state.quickFilters.eps || "")}</select></label>
    <label>Año<select name="year">${yearOptions(state.quickFilters.year || "")}</select></label>
    <label>Mes<select name="month">${monthOptions(state.quickFilters.month || "")}</select></label>
    <label>Corte<select name="corte">${corteOptions(state.quickFilters.corte || "")}</select></label>
    <div class="filter-actions">
      <button class="btn primary" type="submit">Buscar</button>
      <button class="btn secondary" type="button" data-clear-quick>Limpiar</button>
    </div>`;
  renderIcons(form);
}

function buildSupportFilters() {
  const form = $("#supportFilters");
  const f = state.supportFilters;
  form.innerHTML = `
    <label>EPS<select name="eps">${epsOptions(f.eps || "")}</select></label>
    <label>Año<select name="year">${yearOptions(f.year || "")}</select></label>
    <label>Mes<select name="month">${monthOptions(f.month || "")}</select></label>
    <label>Corte<select name="corte">${corteOptions(f.corte || "")}</select></label>
    <div class="filter-actions">
      <button class="btn primary" type="submit">Buscar</button>
      <button class="btn secondary" type="button" data-clear-filters>Limpiar</button>
    </div>`;
}

async function loadSupports() {
  const params = { ...state.supportFilters, page: state.supportsPage, limit: state.supportsLimit };
  const data = await api(`/api/supports${qs(params)}`);
  renderSupports(data);
  renderIcons($("#supportsTable"));
}

function renderSupports(data) {
  const totalPages = Math.max(1, Math.ceil(data.total / data.limit));
  $("#supportsTable").innerHTML = `
    ${supportsTable(data.items || [])}
    <div class="pagination">
      <span>${formatNumber(data.total)} soportes encontrados</span>
      <div class="toolbar">
        <button class="btn secondary" data-page="prev" ${data.page <= 1 ? "disabled" : ""}>Anterior</button>
        <strong>Página ${data.page} de ${totalPages}</strong>
        <button class="btn secondary" data-page="next" ${data.page >= totalPages ? "disabled" : ""}>Siguiente</button>
      </div>
    </div>`;
}

async function uploadFiles(files) {
  const pdfs = Array.from(files || []).filter((file) => file.type === "application/pdf" || file.name.toLowerCase().endsWith(".pdf"));
  if (!pdfs.length) {
    toast("Selecciona uno o más archivos PDF.", "warning");
    return;
  }
  const formData = new FormData();
  pdfs.forEach((file) => formData.append("files", file, file.name));
  $("#uploadResults").classList.remove("empty-state");
  $("#uploadResults").innerHTML = `<div class="alert">${icon("upload")}<div>Procesando ${pdfs.length} PDF. Leyendo texto y extrayendo datos...</div></div>`;
  try {
    const data = await api("/api/supports/upload", { method: "POST", formData });
    state.uploadResults = data.results || [];
    renderUploadResults();
    await loadDashboard();
    toast("Carga procesada.", "success");
    const pending = state.uploadResults.find((result) => result.item && result.status === "pendiente_revision");
    if (pending) openSupportModal(pending.item, pending.missing || []);
  } catch (error) {
    toast(error.message, "danger");
  }
}

function renderUploadResults() {
  const container = $("#uploadResults");
  if (!state.uploadResults.length) {
    container.className = "upload-results empty-state";
    container.innerHTML = `${icon("file")}<p>Los PDFs cargados aparecerán aquí con sus datos detectados y alertas de revisión.</p>`;
    return;
  }
  container.className = "upload-results";
  container.innerHTML = state.uploadResults
    .map((result) => {
      if (result.status === "duplicado") {
        return `
          <div class="upload-result">
            <div class="alert danger">${icon("file")}<div><strong>${escapeHtml(result.filename)}</strong><br>${escapeHtml(result.message)} Duplicado por ${escapeHtml(result.duplicate?.reason || "coincidencia")}.</div></div>
          </div>`;
      }
      if (result.status === "rechazado") {
        return `
          <div class="upload-result">
            <div class="alert danger">${icon("file")}<div><strong>${escapeHtml(result.filename)}</strong><br>${escapeHtml(result.message)}</div></div>
          </div>`;
      }
      const item = result.item || {};
      const missing = result.missing || [];
      return `
        <div class="upload-result">
          <div class="upload-result-head">
            <div>
              <strong>${escapeHtml(result.filename)}</strong>
              <span class="status-pill ${statusClass(result.status)}">${statusLabel(result.status)}</span>
            </div>
            <button class="btn ${missing.length ? "primary" : "secondary"}" data-review-id="${item.id}">
              ${missing.length ? "Completar datos" : "Editar"}
            </button>
          </div>
          <div class="${missing.length ? "alert" : "alert success"}">
            ${icon(missing.length ? "settings" : "save")}
            <div>${escapeHtml(result.message)}${missing.length ? " Campos pendientes: " + missing.join(", ") : ""}</div>
          </div>
          <div class="extracted-grid">
            <div><span>EPS</span>${escapeHtml(item.eps_name || "Pendiente")}</div>
            <div><span>Corte</span>${escapeHtml(item.corte_label || "Sin corte")}</div>
            <div><span>Fecha radicación</span>${formatDate(item.radication_date)}</div>
            <div><span>Facturas detectadas</span>${formatNumber(item.invoice_count || 0)}</div>
            <div><span>Radicado</span>${escapeHtml(item.radicado || "Pendiente")}</div>
            <div><span>Factura</span>${escapeHtml(item.factura || "Sin dato")}</div>
          </div>
        </div>`;
    })
    .join("");
  renderIcons(container);
}

function epsDatalist() {
  return `<datalist id="epsNames">${state.eps.map((eps) => `<option value="${escapeHtml(eps.name)}"></option>`).join("")}</datalist>`;
}

function supportFormHtml(item, missing = []) {
  const missingClass = (name) => (missing.includes(name) ? "required-missing" : "");
  return `
    <div class="alert ${missing.length ? "" : "success"}">
      ${icon(missing.length ? "settings" : "save")}
      <div>${missing.length ? "No se detectaron todos los datos obligatorios. Completa los campos resaltados." : "Puedes corregir o confirmar la información extraída."}</div>
    </div>
    ${epsDatalist()}
    <label class="${missingClass("eps_name")}">EPS *
      <input name="eps_name" list="epsNames" value="${escapeHtml(item.eps_name || "")}" required>
    </label>
    <label class="${missingClass("radication_date")}">Fecha radicación *
      <input type="date" name="radication_date" value="${escapeHtml(item.radication_date || "")}" required>
    </label>
    <label class="${missingClass("corte")}">Corte *
      <select name="corte" required>${corteFormOptions(item.corte || "")}</select>
    </label>
    <label>Facturas detectadas
      <input type="number" min="0" name="invoice_count" value="${escapeHtml(item.invoice_count || 0)}">
    </label>
    <label>No. Radicado
      <input name="radicado" value="${escapeHtml(item.radicado || "")}" placeholder="RAD-2026-0001">
    </label>
    <label>No. Factura
      <input name="factura" value="${escapeHtml(item.factura || "")}" placeholder="FE-000000">
    </label>
    <label>NIT EPS
      <input name="nit_eps" value="${escapeHtml(item.nit_eps || "")}">
    </label>
    <label>Valor radicado
      <input name="valor_radicado" value="${escapeHtml(item.valor_radicado || "")}" placeholder="$ 0">
    </label>
    <label>Observaciones
      <textarea name="observations">${escapeHtml(item.observations || "")}</textarea>
    </label>
    <div class="form-actions">
      <button type="button" class="btn secondary close-modal" data-close="supportModal">Cancelar</button>
      <button type="submit" class="btn primary">${icon("save")}Guardar soporte</button>
    </div>`;
}

async function openSupportModal(item, missing = []) {
  const fresh = item.path ? item : (await api(`/api/supports/${item.id}`)).item;
  if (!missing.length && fresh.status === "pendiente_revision") {
    if (!fresh.eps_name) missing.push("eps_name");
    if (!fresh.radication_date) missing.push("radication_date");
    if (!fresh.corte) missing.push("corte");
  }
  $("#supportModalTitle").textContent = fresh.status === "pendiente_revision" ? "Completar datos del soporte" : "Editar datos del soporte";
  $("#supportForm").dataset.id = fresh.id;
  $("#supportForm").innerHTML = supportFormHtml(fresh, missing);
  $("#reviewPdfFrame").src = `/api/supports/${fresh.id}/file`;
  $("#supportModal").classList.remove("hidden");
  renderIcons($("#supportModal"));
}

async function saveSupport(event) {
  event.preventDefault();
  const id = event.currentTarget.dataset.id;
  try {
    await api(`/api/supports/${id}`, { method: "PUT", body: collectForm(event.currentTarget) });
    toast("Soporte guardado.", "success");
    closeModal("supportModal");
    await loadEps();
    await loadDashboard();
    if (state.activeView === "supports") await loadSupports();
    state.uploadResults = state.uploadResults.map((result) =>
      result.item?.id === Number(id) ? { ...result, status: "guardado", missing: [], message: "Datos guardados correctamente.", item: { ...result.item, ...collectForm(event.currentTarget), status: "guardado" } } : result
    );
    renderUploadResults();
  } catch (error) {
    toast(error.message, "danger");
  }
}

function openPdf(row) {
  $("#pdfTitle").textContent = row.original_filename || "Soporte PDF";
  $("#pdfFrame").src = `/api/supports/${row.id}/file`;
  $("#pdfDownloadLink").href = `/api/supports/${row.id}/download`;
  $("#pdfModal").classList.remove("hidden");
}

function closeModal(id) {
  const modal = $(`#${id}`);
  modal.classList.add("hidden");
  $$("iframe", modal).forEach((frame) => (frame.src = "about:blank"));
}

async function deleteSupport(id) {
  if (!confirm("¿Eliminar este soporte? Quedará registrado en el historial.")) return;
  try {
    await api(`/api/supports/${id}`, { method: "DELETE" });
    toast("Soporte eliminado.", "success");
    await loadDashboard();
    await loadSupports();
  } catch (error) {
    toast(error.message, "danger");
  }
}

async function downloadZip() {
  try {
    const blob = await api(`/api/supports/zip${qs(state.supportFilters)}`);
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `soportes_eps_${new Date().toISOString().slice(0, 10)}.zip`;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    toast("ZIP generado.", "success");
  } catch (error) {
    toast(error.message, "warning");
  }
}

function renderEpsTable() {
  const canManage = has("manage_eps");
  if (!state.eps.length) {
    $("#epsTable").innerHTML = `<div class="empty-state">${icon("building")}<p>No hay EPS registradas.</p></div>`;
    return;
  }
  $("#epsTable").innerHTML = `
    <div class="table-shell">
      <table>
        <thead><tr><th>EPS</th><th>NIT</th><th>Código</th><th>Soportes</th><th>Estado</th>${canManage ? "<th>Acciones</th>" : ""}</tr></thead>
        <tbody>
          ${state.eps
            .map(
              (eps) => `
              <tr>
                <td><span class="badge-dot" style="--primary:${escapeHtml(eps.color || "#1457e8")}">${escapeHtml(eps.name)}</span></td>
                <td>${escapeHtml(eps.nit || "")}</td>
                <td>${escapeHtml(eps.code || "")}</td>
                <td>${formatNumber(eps.support_count)}</td>
                <td><span class="status-pill ${eps.active ? "" : "deleted"}">${eps.active ? "Activa" : "Inactiva"}</span></td>
                ${
                  canManage
                    ? `<td><div class="row-actions">
                        <button class="mini-btn" title="Editar" data-eps-edit="${eps.id}">${icon("edit")}</button>
                        <button class="mini-btn" title="Desactivar" data-eps-delete="${eps.id}">${icon("trash")}</button>
                      </div></td>`
                    : ""
                }
              </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
  renderIcons($("#epsTable"));
}

function openEpsModal(eps = null) {
  $("#epsModalTitle").textContent = eps ? "Editar EPS" : "Nueva EPS";
  $("#epsForm").dataset.id = eps?.id || "";
  $("#epsForm").innerHTML = `
    <label>Nombre<input name="name" value="${escapeHtml(eps?.name || "")}" required></label>
    <label>NIT<input name="nit" value="${escapeHtml(eps?.nit || "")}"></label>
    <label>Código interno<input name="code" value="${escapeHtml(eps?.code || "")}"></label>
    <label>Color<input type="color" name="color" value="${escapeHtml(eps?.color || "#1769e0")}"></label>
    <label>Logo URL<input name="logo_url" value="${escapeHtml(eps?.logo_url || "")}"></label>
    <label>Alias de detección<textarea name="aliases" placeholder="Separados por coma">${escapeHtml(eps?.aliases || "")}</textarea></label>
    <label><span>Activa</span><select name="active"><option value="true" ${eps?.active !== 0 ? "selected" : ""}>Sí</option><option value="false" ${eps?.active === 0 ? "selected" : ""}>No</option></select></label>
    <div class="form-actions">
      <button type="button" class="btn secondary close-modal" data-close="epsModal">Cancelar</button>
      <button type="submit" class="btn primary">${icon("save")}Guardar</button>
    </div>`;
  $("#epsModal").classList.remove("hidden");
  renderIcons($("#epsModal"));
}

async function saveEps(event) {
  event.preventDefault();
  const data = collectForm(event.currentTarget);
  data.active = data.active === "true";
  const id = event.currentTarget.dataset.id;
  try {
    await api(id ? `/api/eps/${id}` : "/api/eps", { method: id ? "PUT" : "POST", body: data });
    toast("EPS guardada.", "success");
    closeModal("epsModal");
    await loadEps();
    renderEpsTable();
    buildSupportFilters();
    buildQuickFilters();
  } catch (error) {
    toast(error.message, "danger");
  }
}

async function loadUsers() {
  const data = await api("/api/users");
  renderUsers(data.items || []);
}

function renderUsers(users) {
  $("#usersTable").innerHTML = `
    <div class="table-shell">
      <table>
        <thead><tr><th>Nombre</th><th>Correo</th><th>Rol</th><th>Estado</th><th>Creado</th><th>Acciones</th></tr></thead>
        <tbody>
          ${users
            .map(
              (user) => `
              <tr>
                <td>${escapeHtml(user.name)}</td>
                <td>${escapeHtml(user.email)}</td>
                <td>${escapeHtml(user.role)}</td>
                <td><span class="status-pill ${user.active ? "" : "deleted"}">${user.active ? "Activo" : "Inactivo"}</span></td>
                <td>${formatDateTime(user.created_at)}</td>
                <td><div class="row-actions">
                  <button class="mini-btn" data-user-edit="${user.id}" title="Editar">${icon("edit")}</button>
                  <button class="mini-btn" data-user-delete="${user.id}" title="Desactivar">${icon("trash")}</button>
                </div></td>
              </tr>`
            )
            .join("")}
        </tbody>
      </table>
    </div>`;
  $("#usersTable").dataset.users = JSON.stringify(users);
  renderIcons($("#usersTable"));
}

function openUserModal(user = null) {
  $("#userModalTitle").textContent = user ? "Editar usuario" : "Nuevo usuario";
  $("#userForm").dataset.id = user?.id || "";
  $("#userForm").innerHTML = `
    <label>Nombre<input name="name" value="${escapeHtml(user?.name || "")}" required></label>
    <label>Correo<input name="email" type="email" value="${escapeHtml(user?.email || "")}" required></label>
    <label>Rol
      <select name="role">
        ${["Administrador", "Digitador", "Consulta"].map((role) => `<option value="${role}" ${user?.role === role ? "selected" : ""}>${role}</option>`).join("")}
      </select>
    </label>
    <label>Contraseña${user ? " nueva" : ""}<input name="password" type="password" ${user ? "" : "required"}></label>
    <label>Estado<select name="active"><option value="true" ${user?.active !== 0 ? "selected" : ""}>Activo</option><option value="false" ${user?.active === 0 ? "selected" : ""}>Inactivo</option></select></label>
    <div class="form-actions">
      <button type="button" class="btn secondary close-modal" data-close="userModal">Cancelar</button>
      <button type="submit" class="btn primary">${icon("save")}Guardar</button>
    </div>`;
  $("#userModal").classList.remove("hidden");
  renderIcons($("#userModal"));
}

async function saveUser(event) {
  event.preventDefault();
  const data = collectForm(event.currentTarget);
  data.active = data.active === "true";
  const id = event.currentTarget.dataset.id;
  try {
    await api(id ? `/api/users/${id}` : "/api/users", { method: id ? "PUT" : "POST", body: data });
    toast("Usuario guardado.", "success");
    closeModal("userModal");
    await loadUsers();
  } catch (error) {
    toast(error.message, "danger");
  }
}

async function loadReports() {
  const selectedYear = $("#topYear").value || "";
  const selectedMonth = $("#topMonth").value || "";
  const [reports, audit, cortes] = await Promise.all([
    api("/api/reports"),
    api("/api/audit"),
    api(`/api/cortes${qs({ year: selectedYear, month: selectedMonth })}`),
  ]);
  renderBarList("#reportEps", reports.by_eps || []);
  renderBarList("#reportUsers", reports.by_user || []);
  renderBarList("#reportYears", reports.by_year || []);
  $("#reportIndicators").innerHTML = `
    <div class="indicator"><span>Soportes pendientes</span><strong>${formatNumber(reports.pending)}</strong></div>
    <div class="indicator"><span>Duplicados detectados</span><strong>${formatNumber(reports.duplicates)}</strong></div>`;
  renderCutReport(cortes);
  renderAudit(audit.items || []);
}

function renderCutReport(data) {
  const cycle = data.cycle || {};
  state.cutCycle = cycle;
  $("#cutCycleLabel").textContent = `Mes de trabajo: ${cycle.label || ""}`;
  $("#reportCuts").innerHTML = (data.items || [])
    .map((item) => {
      const max = Math.max(1, ...item.eps.map((row) => row.invoice_total));
      return `
        <section class="cut-card">
          <div class="cut-head">
            <strong>${escapeHtml(item.label)}</strong>
            <span>${escapeHtml(item.detail)}</span>
            <em>${formatNumber(item.invoice_total || 0)} facturas en ${formatNumber(item.support_total || 0)} soportes</em>
          </div>
          <div class="bar-list">
            ${
              item.eps.length
                ? item.eps
                    .map(
                      (row) => `
                      <button class="cut-eps-row" data-cut-search="${item.id}" data-cut-eps="${escapeHtml(row.label)}">
                        <span>${escapeHtml(row.label)}</span>
                        <strong>${formatNumber(row.invoice_total)} fac.</strong>
                        <small>${formatNumber(row.support_total)} soportes</small>
                        <i style="width:${Math.max(6, (row.invoice_total / max) * 100)}%"></i>
                      </button>`
                    )
                    .join("")
                : `<div class="empty-state small-empty">${icon("file")}<p>Sin EPS asignadas a este corte.</p></div>`
            }
          </div>
        </section>`;
    })
    .join("");
  renderIcons($("#reportCuts"));
}

function renderBarList(selector, rows) {
  const max = Math.max(1, ...rows.map((row) => row.total));
  $(selector).innerHTML = rows.length
    ? rows
        .map(
          (row) => `
          <div class="bar-item">
            <div class="bar-meta"><span>${escapeHtml(row.label)}</span><strong>${formatNumber(row.total)}</strong></div>
            <div class="bar-track"><div class="bar-fill" style="width:${Math.max(4, (row.total / max) * 100)}%"></div></div>
          </div>`
        )
        .join("")
    : `<div class="empty-state">${icon("chart")}<p>Sin datos todavía.</p></div>`;
}

function renderAudit(rows) {
  $("#auditTable").innerHTML = rows.length
    ? `
      <div class="table-shell">
        <table>
          <thead><tr><th>Fecha</th><th>Usuario</th><th>Acción</th><th>Entidad</th><th>Detalle</th><th>IP</th></tr></thead>
          <tbody>
            ${rows
              .map(
                (row) => `
                <tr>
                  <td>${formatDateTime(row.created_at)}</td>
                  <td>${escapeHtml(row.user_name || "Sistema")}</td>
                  <td>${escapeHtml(row.action)}</td>
                  <td>${escapeHtml(row.entity_type)} ${row.entity_id || ""}</td>
                  <td>${escapeHtml(row.details || "")}</td>
                  <td>${escapeHtml(row.ip_address || "")}</td>
                </tr>`
              )
              .join("")}
          </tbody>
        </table>
      </div>`
    : `<div class="empty-state">${icon("file")}<p>Sin acciones registradas.</p></div>`;
}

function renderSettingsForm() {
  const supabase = state.supabase || {};
  const sync = supabase.last_sync || {};
  const supabaseStatus = supabase.enabled ? "Conectado" : "Sin configurar";
  const supabaseClass = supabase.enabled ? (sync.ok === false ? "alert" : "alert success") : "alert";
  $("#settingsForm").innerHTML = `
    <label>Nombre del sistema<input name="system_name" value="${escapeHtml(state.settings.system_name || "")}"></label>
    <label>Nombre de la empresa<input name="company_name" value="${escapeHtml(state.settings.company_name || "")}"></label>
    <label>Color principal<input type="color" name="primary_color" value="${escapeHtml(state.settings.primary_color || "#1457e8")}"></label>
    <label>Registros por página<input type="number" min="5" max="100" name="page_size" value="${escapeHtml(state.settings.page_size || "10")}"></label>
    <div class="${supabaseClass}">
      ${icon("cloud")}
      <div>
        <strong>Supabase: ${escapeHtml(supabaseStatus)}</strong><br>
        ${escapeHtml(sync.message || (supabase.enabled ? `Bucket: ${supabase.bucket || "soportes-eps"}` : "Configura el archivo .env para activar respaldo remoto."))}
      </div>
    </div>
    <div class="form-actions">
      <button id="syncSupabaseBtn" class="btn secondary" type="button" ${supabase.enabled ? "" : "disabled"}>${icon("refresh")}Sincronizar Supabase</button>
    </div>
    <div class="form-actions"><button class="btn primary" type="submit">${icon("save")}Guardar configuración</button></div>`;
  renderIcons($("#settingsForm"));
  const syncButton = $("#syncSupabaseBtn");
  if (syncButton) syncButton.addEventListener("click", syncSupabase);
}

async function saveSettings(event) {
  event.preventDefault();
  try {
    await api("/api/settings", { method: "PUT", body: collectForm(event.currentTarget) });
    toast("Configuración guardada.", "success");
    await loadSettings();
    await loadSupabaseStatus();
    renderSettingsForm();
  } catch (error) {
    toast(error.message, "danger");
  }
}

async function syncSupabase() {
  const button = $("#syncSupabaseBtn");
  if (button) button.disabled = true;
  try {
    const result = await api("/api/supabase/sync", { method: "POST", body: {} });
    state.supabase = { ...(state.supabase || {}), last_sync: result.synced || { ok: true, message: "Sincronizado." } };
    toast("Supabase sincronizado.", "success");
    renderSettingsForm();
  } catch (error) {
    toast(error.message, "danger");
    await loadSupabaseStatus();
    renderSettingsForm();
  }
}

async function showView(name) {
  state.activeView = name;
  $$(".nav-item").forEach((btn) => btn.classList.toggle("active", btn.dataset.view === name));
  $$(".view").forEach((view) => view.classList.remove("active"));
  $(`#${name}View`).classList.add("active");
  const titles = {
    dashboard: ["Dashboard", "Panel principal"],
    upload: ["Subir soportes", "Carga y extracción"],
    supports: ["Consultar soportes", "Listado documental"],
    eps: ["EPS", "Catálogo"],
    reports: ["Reportes", "Indicadores e historial"],
    users: ["Usuarios", "Roles y accesos"],
    settings: ["Configuración", "Sistema"],
  };
  $("#viewTitle").textContent = titles[name][0];
  $("#viewEyebrow").textContent = titles[name][1];

  if (name === "dashboard") await loadDashboard();
  if (name === "supports") await loadSupports();
  if (name === "eps") {
    await loadEps();
    renderEpsTable();
  }
  if (name === "users") await loadUsers();
  if (name === "reports") await loadReports();
  if (name === "settings") {
    await loadSettings();
    await loadSupabaseStatus();
    renderSettingsForm();
  }
}

function debounce(fn, delay = 350) {
  let timer;
  return (...args) => {
    clearTimeout(timer);
    timer = setTimeout(() => fn(...args), delay);
  };
}

function bindEvents() {
  $("#loginForm").addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const session = await api("/api/login", { method: "POST", body: collectForm(event.currentTarget) });
      await bootstrapApp(session);
      toast("Sesión iniciada.", "success");
    } catch (error) {
      toast(error.message, "danger");
    }
  });

  $$(".demo-users button").forEach((button) => {
    button.addEventListener("click", () => {
      const [email, password] = button.dataset.demo.split("|");
      $("#loginForm [name=email]").value = email;
      $("#loginForm [name=password]").value = password;
    });
  });

  $("#logoutBtn").addEventListener("click", async () => {
    await api("/api/logout", { method: "POST" });
    setAppVisible(false);
  });

  $$(".nav-item").forEach((button) => {
    button.addEventListener("click", () => showView(button.dataset.view).catch((error) => toast(error.message, "danger")));
  });

  document.addEventListener("click", async (event) => {
    const close = event.target.closest(".close-modal");
    if (close) closeModal(close.dataset.close);

    const go = event.target.closest("[data-go]");
    if (go) showView(go.dataset.go).catch((error) => toast(error.message, "danger"));

    const review = event.target.closest("[data-review-id]");
    if (review) {
      const id = Number(review.dataset.reviewId);
      const result = state.uploadResults.find((item) => item.item?.id === id);
      openSupportModal(result?.item || { id }, result?.missing || []).catch((error) => toast(error.message, "danger"));
    }

    const supportAction = event.target.closest("[data-action]");
    if (supportAction) {
      const id = Number(supportAction.dataset.id);
      const data = await api(`/api/supports/${id}`);
      const item = data.item;
      if (supportAction.dataset.action === "view") openPdf(item);
      if (supportAction.dataset.action === "download") window.location.href = `/api/supports/${id}/download`;
      if (supportAction.dataset.action === "edit") openSupportModal(item, []);
      if (supportAction.dataset.action === "delete") deleteSupport(id);
    }

    const pageButton = event.target.closest("[data-page]");
    if (pageButton) {
      state.supportsPage += pageButton.dataset.page === "next" ? 1 : -1;
      await loadSupports();
    }

    const epsEdit = event.target.closest("[data-eps-edit]");
    if (epsEdit) openEpsModal(state.eps.find((eps) => eps.id === Number(epsEdit.dataset.epsEdit)));

    const epsDelete = event.target.closest("[data-eps-delete]");
    if (epsDelete && confirm("¿Desactivar esta EPS?")) {
      await api(`/api/eps/${epsDelete.dataset.epsDelete}`, { method: "DELETE" });
      await loadEps();
      renderEpsTable();
      toast("EPS desactivada.", "success");
    }

    const userEdit = event.target.closest("[data-user-edit]");
    if (userEdit) {
      const users = JSON.parse($("#usersTable").dataset.users || "[]");
      openUserModal(users.find((user) => user.id === Number(userEdit.dataset.userEdit)));
    }

    const userDelete = event.target.closest("[data-user-delete]");
    if (userDelete && confirm("¿Desactivar este usuario?")) {
      await api(`/api/users/${userDelete.dataset.userDelete}`, { method: "DELETE" });
      await loadUsers();
      toast("Usuario desactivado.", "success");
    }

    const clearQuick = event.target.closest("[data-clear-quick]");
    if (clearQuick) {
      state.quickFilters = {};
      buildQuickFilters();
      await loadDashboard();
    }

    const clearFilters = event.target.closest("[data-clear-filters]");
    if (clearFilters) {
      state.supportFilters = {};
      state.supportsPage = 1;
      buildSupportFilters();
      await loadSupports();
    }

    const cutSearch = event.target.closest("[data-cut-search]");
    if (cutSearch) {
      const cycle = state.cutCycle || {};
      state.supportFilters = {
        eps: cutSearch.dataset.cutEps,
        year: cycle.year || $("#topYear").value || new Date().getFullYear(),
        month: cycle.month || $("#topMonth").value || new Date().getMonth() + 1,
        corte: cutSearch.dataset.cutSearch,
      };
      state.supportsPage = 1;
      buildSupportFilters();
      await showView("supports");
    }
  });

  $("#topYear").addEventListener("change", () =>
    (state.activeView === "reports" ? loadReports() : loadDashboard()).catch((error) => toast(error.message, "danger"))
  );
  $("#topMonth").addEventListener("change", () =>
    (state.activeView === "reports" ? loadReports() : loadDashboard()).catch((error) => toast(error.message, "danger"))
  );
  $("#refreshBtn").addEventListener("click", () => showView(state.activeView).catch((error) => toast(error.message, "danger")));
  $("#refreshAuditBtn").addEventListener("click", () => loadReports().catch((error) => toast(error.message, "danger")));

  $("#quickFilters").addEventListener("submit", async (event) => {
    event.preventDefault();
    state.quickFilters = collectForm(event.currentTarget);
    state.supportFilters = { ...state.quickFilters };
    buildSupportFilters();
    await loadDashboard();
    await showView("supports");
  });

  $("#supportFilters").addEventListener("submit", async (event) => {
    event.preventDefault();
    state.supportFilters = collectForm(event.currentTarget);
    state.supportsPage = 1;
    await loadSupports();
  });

  $("#supportFilters").addEventListener(
    "input",
    debounce(async () => {
      state.supportFilters = collectForm($("#supportFilters"));
      state.supportsPage = 1;
      await loadSupports();
    }, 450)
  );

  $("#zipBtn").addEventListener("click", downloadZip);
  $("#supportForm").addEventListener("submit", saveSupport);
  $("#epsForm").addEventListener("submit", saveEps);
  $("#userForm").addEventListener("submit", saveUser);
  $("#settingsForm").addEventListener("submit", saveSettings);

  $("#newEpsBtn").addEventListener("click", () => openEpsModal());
  $("#newUserBtn").addEventListener("click", () => openUserModal());

  $("#selectFilesBtn").addEventListener("click", () => $("#fileInput").click());
  $("#fileInput").addEventListener("change", (event) => uploadFiles(event.target.files));
  $("#clearUploadResults").addEventListener("click", () => {
    state.uploadResults = [];
    renderUploadResults();
  });

  const dropzone = $("#dropzone");
  ["dragenter", "dragover"].forEach((name) => {
    dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.add("dragover");
    });
  });
  ["dragleave", "drop"].forEach((name) => {
    dropzone.addEventListener(name, (event) => {
      event.preventDefault();
      dropzone.classList.remove("dragover");
    });
  });
  dropzone.addEventListener("drop", (event) => uploadFiles(event.dataTransfer.files));
  dropzone.addEventListener("click", (event) => {
    if (!event.target.closest("button")) $("#fileInput").click();
  });

  $("#fullscreenPdfBtn").addEventListener("click", () => {
    const frame = $("#pdfFrame");
    if (frame.requestFullscreen) frame.requestFullscreen();
  });
}

async function boot() {
  renderIcons();
  bindEvents();
  try {
    const session = await api("/api/session");
    if (session.authenticated) {
      await bootstrapApp(session);
    } else {
      setAppVisible(false);
    }
  } catch {
    setAppVisible(false);
  }
}

boot();
