// AES Logistics PM Portal

let currentUser = null;

function show(id) {
  document.querySelectorAll(".screen").forEach((el) => el.classList.add("hidden"));
  document.getElementById(id).classList.remove("hidden");
}

async function api(url, opts = {}) {
  const resp = await fetch(url, { credentials: "same-origin", ...opts });
  const body = await resp.json().catch(() => ({}));
  if (!resp.ok) {
    const err = new Error(body.error || `Request failed (${resp.status})`);
    err.status = resp.status;
    err.body = body;
    throw err;
  }
  return body;
}

// ---------- Login ----------

async function tryRestoreSession() {
  try {
    const me = await api("/api/auth/me");
    if (me.role === "pm" || me.role === "admin") {
      currentUser = me;
      showDashboard();
      return;
    }
  } catch (e) {
    // not logged in, or not a pm/admin session - show login
  }
  show("screen-login");
}

function initLogin() {
  document.getElementById("btn-login").addEventListener("click", async () => {
    const email = document.getElementById("login-email").value.trim();
    const password = document.getElementById("login-password").value;
    const errorEl = document.getElementById("login-error");
    errorEl.classList.add("hidden");

    try {
      const result = await api("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      if (result.role !== "pm" && result.role !== "admin") {
        errorEl.textContent = "This account doesn't have Project Management access.";
        errorEl.classList.remove("hidden");
        return;
      }
      currentUser = { role: result.role, email: result.email, name: result.name };
      showDashboard();
    } catch (e) {
      errorEl.textContent = e.message;
      errorEl.classList.remove("hidden");
    }
  });
}

async function logout() {
  await api("/api/auth/logout", { method: "POST" }).catch(() => {});
  currentUser = null;
  show("screen-login");
}

// ---------- Dashboard ----------

async function showDashboard() {
  document.getElementById("user-display").textContent = currentUser.name
    ? `${currentUser.name} (${currentUser.email})`
    : currentUser.email;
  show("screen-dashboard");
  await loadIcsSettings();
  await loadCalendarEvents();
  await loadDeliveries();
  await loadDriverDropdown();
}

function initDashboard() {
  document.getElementById("btn-logout").addEventListener("click", logout);
  document.getElementById("btn-save-ics").addEventListener("click", saveIcsUrl);
  document.getElementById("btn-create-delivery").addEventListener("click", createDelivery);
  document.getElementById("tab-btn-deliveries").addEventListener("click", () => switchTab("deliveries"));
  document.getElementById("tab-btn-inventory").addEventListener("click", () => switchTab("inventory"));
  document.getElementById("tab-btn-admin").addEventListener("click", () => switchTab("admin"));
}

function switchTab(tab) {
  document.getElementById("tab-deliveries").classList.toggle("hidden", tab !== "deliveries");
  document.getElementById("tab-inventory").classList.toggle("hidden", tab !== "inventory");
  document.getElementById("tab-admin").classList.toggle("hidden", tab !== "admin");
  document.getElementById("tab-btn-deliveries").classList.toggle("tab-active", tab === "deliveries");
  document.getElementById("tab-btn-inventory").classList.toggle("tab-active", tab === "inventory");
  document.getElementById("tab-btn-admin").classList.toggle("tab-active", tab === "admin");
  if (tab === "admin") {
    loadAdminUserList();
  }
  if (tab === "inventory") {
    loadInventory();
  }
}

// ---------- Inventory ----------

function initInventoryTab() {
  document.getElementById("btn-export-inventory").addEventListener("click", () => {
    window.open("/api/inventory/export", "_blank");
  });
}

async function loadInventory() {
  const tbody = document.getElementById("inventory-tbody");
  try {
    const result = await api("/api/inventory");
    if (result.entries.length === 0) {
      tbody.innerHTML = '<tr><td colspan="5" class="hint">Nothing checked in yet.</td></tr>';
      return;
    }
    tbody.innerHTML = "";
    result.entries.forEach((e) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${e.job_number}</td>
        <td>${e.location}</td>
        <td>${e.confirmed_by}</td>
        <td>${e.confirmed_at.slice(0, 19).replace("T", " ")}</td>
        <td></td>
      `;
      const btn = document.createElement("button");
      btn.className = "btn btn-secondary";
      btn.textContent = "Mark Shipped";
      btn.title = "Manually remove this from the active inventory count (e.g. a partial shipment already went out)";
      btn.addEventListener("click", async () => {
        if (!confirm(`Mark this Job #${e.job_number} entry at ${e.location} as shipped/removed?`)) return;
        try {
          await api(`/api/inventory/${e.id}/remove`, { method: "POST" });
          await loadInventory();
        } catch (err) {
          alert(`Couldn't remove: ${err.message}`);
        }
      });
      tr.lastElementChild.appendChild(btn);
      tbody.appendChild(tr);
    });
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="5" class="hint">Couldn't load inventory: ${e.message}</td></tr>`;
  }
}

// ---------- Admin Tools ----------

function initAdminTools() {
  document.getElementById("btn-admin-reg").addEventListener("click", async () => {
    const name = document.getElementById("admin-reg-name").value.trim();
    const email = document.getElementById("admin-reg-email").value.trim();
    const role = document.getElementById("admin-reg-role").value;
    const statusEl = document.getElementById("admin-reg-status");
    try {
      const result = await api("/api/auth/admin/register_user", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, email, role }),
      });
      statusEl.textContent = `${result.name} registered as ${result.role}. They log in with that email and the shared password.`;
      statusEl.className = "status-line ok";
      document.getElementById("admin-reg-name").value = "";
      document.getElementById("admin-reg-email").value = "";
      document.getElementById("admin-reg-role").value = "driver";
      loadAdminUserList();
      loadDriverDropdown();
    } catch (e) {
      statusEl.textContent = e.message;
      statusEl.className = "status-line err";
    }
  });
}

const ROLE_LABELS = { driver: "Driver / Warehouse", pm: "Project Manager", admin: "Admin" };

async function loadAdminUserList() {
  const tbody = document.getElementById("admin-user-list");
  try {
    const result = await api("/api/auth/users");
    tbody.innerHTML = result.users.length
      ? result.users.map((u) => `<tr><td>${u.name}</td><td>${u.email}</td><td>${ROLE_LABELS[u.role] || u.role}</td></tr>`).join("")
      : '<tr><td colspan="3" class="hint">No users registered yet.</td></tr>';
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="3" class="hint">Couldn't load: ${e.message}</td></tr>`;
  }
}

// ---------- Calendar sync ----------

async function loadIcsSettings() {
  try {
    const result = await api("/api/schedule/calendar/settings");
    document.getElementById("ics-url-input").value = result.ics_url || "";
  } catch (e) {
    console.error("Failed to load calendar settings", e);
  }
}

async function saveIcsUrl() {
  const url = document.getElementById("ics-url-input").value.trim();
  const statusEl = document.getElementById("ics-save-status");
  try {
    await api("/api/schedule/calendar/settings", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ics_url: url }),
    });
    statusEl.textContent = "Saved.";
    statusEl.className = "status-line ok";
    await loadCalendarEvents();
  } catch (e) {
    statusEl.textContent = e.message;
    statusEl.className = "status-line err";
  }
}

async function loadCalendarEvents() {
  const listEl = document.getElementById("calendar-events-list");
  try {
    const result = await api("/api/schedule/calendar/upcoming");
    if (result.events.length === 0) {
      listEl.innerHTML = '<div class="hint">No upcoming events found (or no calendar connected yet).</div>';
      return;
    }
    listEl.innerHTML = "";
    result.events.forEach((ev) => {
      const div = document.createElement("div");
      div.className = "list-item";
      const dateStr = new Date(ev.start_iso).toLocaleDateString();
      div.innerHTML = `
        <div>
          <div>${ev.title}</div>
          <div class="hint">${dateStr}</div>
        </div>
        ${ev.already_scheduled
          ? '<span class="status-badge status-completed">Set up</span>'
          : '<button class="btn btn-secondary btn-setup-event">Set Up Delivery</button>'}
      `;
      if (!ev.already_scheduled) {
        div.querySelector(".btn-setup-event").addEventListener("click", () => {
          prefillFromEvent(ev);
        });
      }
      listEl.appendChild(div);
    });
  } catch (e) {
    listEl.innerHTML = `<div class="hint">Couldn't load calendar events: ${e.message}</div>`;
  }
}

function prefillFromEvent(ev) {
  document.getElementById("new-calendar-event-uid").value = ev.uid;
  document.getElementById("new-delivery-date").value = ev.start_iso.slice(0, 10);
  document.getElementById("create-delivery-title").textContent = `Schedule Delivery — from "${ev.title}"`;
  document.getElementById("create-delivery-card").scrollIntoView({ behavior: "smooth" });
}

// ---------- Driver dropdown ----------

async function loadDriverDropdown() {
  const select = document.getElementById("new-assigned-driver");
  try {
    const result = await api("/api/schedule/drivers");
    select.innerHTML = '<option value="">— Select a driver —</option>';
    result.drivers.forEach((d) => {
      const opt = document.createElement("option");
      opt.value = d.name;
      opt.textContent = d.name;
      select.appendChild(opt);
    });
  } catch (e) {
    console.error("Failed to load driver list", e);
  }
}

// ---------- Create delivery ----------

async function createDelivery() {
  const statusEl = document.getElementById("create-delivery-status");
  const payload = {
    job_number: document.getElementById("new-job-number").value.trim(),
    delivery_date: document.getElementById("new-delivery-date").value,
    receiver_name: document.getElementById("new-receiver-name").value.trim(),
    receiver_email: document.getElementById("new-receiver-email").value.trim(),
    receiver_phone: document.getElementById("new-receiver-phone").value.trim(),
    pm_email: document.getElementById("new-pm-email").value.trim() || currentUser.email,
    site_address: document.getElementById("new-site-address").value.trim(),
    assigned_driver: document.getElementById("new-assigned-driver").value || null,
    calendar_event_uid: document.getElementById("new-calendar-event-uid").value || null,
    customer_name: document.getElementById("new-customer-name").value.trim(),
    customer_po: document.getElementById("new-customer-po").value.trim(),
    job_name: document.getElementById("new-job-name").value.trim(),
    delivery_method: document.getElementById("new-delivery-method").value.trim(),
  };

  try {
    await api("/api/schedule", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    statusEl.textContent = "Delivery scheduled.";
    statusEl.className = "status-line ok";
    ["new-job-number", "new-delivery-date", "new-receiver-name", "new-receiver-email", "new-receiver-phone",
     "new-site-address", "new-calendar-event-uid", "new-customer-name", "new-customer-po", "new-job-name", "new-delivery-method"]
      .forEach((id) => (document.getElementById(id).value = ""));
    document.getElementById("new-assigned-driver").value = "";
    document.getElementById("create-delivery-title").textContent = "Schedule a Delivery";
    await loadDeliveries();
    await loadCalendarEvents();
  } catch (e) {
    statusEl.textContent = e.message;
    statusEl.className = "status-line err";
  }
}

// ---------- Deliveries table ----------

let deliveriesCache = [];

async function loadDeliveries() {
  const tbody = document.getElementById("deliveries-tbody");
  try {
    const result = await api("/api/schedule");
    deliveriesCache = result.deliveries;
    if (deliveriesCache.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="hint">No deliveries scheduled yet.</td></tr>';
      return;
    }
    tbody.innerHTML = "";
    deliveriesCache.forEach((d) => {
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${d.job_number}</td>
        <td>${d.delivery_date}</td>
        <td>${d.receiver_name}</td>
        <td>${d.assigned_driver || '<span class="hint">Unassigned</span>'}</td>
        <td><span class="status-badge status-${d.status}">${d.status.replace("_", " ")}</span>${d.revision_count ? ` <span class="hint">(rev. ${d.revision_count})</span>` : ""}</td>
        <td>${d.ticket_filename ? "Uploaded" : "—"}</td>
        <td></td>
      `;
      const actionCell = tr.lastElementChild;
      if (d.status === "scheduled") {
        const uploadBtn = document.createElement("button");
        uploadBtn.className = "btn btn-secondary";
        uploadBtn.textContent = "Upload Ticket";
        uploadBtn.style.marginRight = "6px";
        uploadBtn.addEventListener("click", () => openUploadModal(d));
        actionCell.appendChild(uploadBtn);

        const genBtn = document.createElement("button");
        genBtn.className = "btn btn-secondary";
        genBtn.textContent = "Generate Ticket";
        genBtn.addEventListener("click", () => openGenerateModal(d));
        actionCell.appendChild(genBtn);
      } else {
        const btn = document.createElement("button");
        btn.className = "btn btn-secondary";
        btn.textContent = "View";
        btn.style.marginRight = "6px";
        btn.addEventListener("click", () => openViewModal(d));
        actionCell.appendChild(btn);

        // Revising is always allowed, at any stage — packing/en-route/completed
        // deliveries just get handled with extra care server-side (see the
        // reset_to_pack / stage-aware alert logic).
        const reviseBtn = document.createElement("button");
        reviseBtn.className = "btn btn-secondary";
        reviseBtn.textContent = "Revise";
        reviseBtn.style.marginRight = "6px";
        reviseBtn.addEventListener("click", () => openReviseModal(d));
        actionCell.appendChild(reviseBtn);
      }

      if (d.ticket_filename) {
        const sendBtn = document.createElement("button");
        sendBtn.className = "btn btn-secondary";
        sendBtn.textContent = "Send to PM";
        sendBtn.addEventListener("click", () => openSendToPmModal(d));
        actionCell.appendChild(sendBtn);
      }

      tbody.appendChild(tr);
    });
  } catch (e) {
    tbody.innerHTML = `<tr><td colspan="6" class="hint">Couldn't load deliveries: ${e.message}</td></tr>`;
  }
}

// ---------- Upload ticket modal ----------

let uploadTargetId = null;

function openUploadModal(delivery) {
  uploadTargetId = delivery.id;
  document.getElementById("upload-modal-job").textContent = delivery.job_number;
  document.getElementById("upload-ticket-file").value = "";
  document.getElementById("upload-modal-status").textContent = "";
  document.getElementById("upload-modal").classList.remove("hidden");
}

function initUploadModal() {
  document.getElementById("btn-upload-cancel").addEventListener("click", () => {
    document.getElementById("upload-modal").classList.add("hidden");
  });

  document.getElementById("btn-upload-submit").addEventListener("click", async () => {
    const fileInput = document.getElementById("upload-ticket-file");
    const statusEl = document.getElementById("upload-modal-status");
    if (!fileInput.files[0]) {
      statusEl.textContent = "Choose a file first.";
      statusEl.className = "status-line err";
      return;
    }
    const formData = new FormData();
    formData.append("ticket", fileInput.files[0]);
    try {
      await api(`/api/schedule/${uploadTargetId}/ticket`, { method: "POST", body: formData });
      document.getElementById("upload-modal").classList.add("hidden");
      await loadDeliveries();
    } catch (e) {
      statusEl.textContent = e.message;
      statusEl.className = "status-line err";
    }
  });
}

// ---------- Generate / Revise ticket modal ----------

let generateTargetId = null;
let generateMode = "generate"; // "generate" or "revise"
let lineItemRowCount = 0;

function addLineItemRow(item = {}) {
  const container = document.getElementById("generate-line-items");
  const rowId = `line-item-${lineItemRowCount++}`;
  const row = document.createElement("div");
  row.className = "line-item-card";
  row.id = rowId;
  row.innerHTML = `
    <div class="desc-row">
      <input type="text" class="desc-input" placeholder="Material / description" value="${item.description || ""}">
      <button type="button" class="line-item-remove">&times;</button>
    </div>
    <div class="line-item-grid">
      <label>Type<input type="text" class="type-input" value="${item.type || ""}"></label>
      <label>Qty<input type="text" class="qty-input" value="${item.quantity || ""}"></label>
      <label>Boxes<input type="text" class="boxes-input" value="${item.boxes || ""}"></label>
      <label>Model #<input type="text" class="model-input" value="${item.model_number || ""}"></label>
      <label>MFG<input type="text" class="mfg-input" value="${item.mfg || ""}"></label>
    </div>
  `;
  row.querySelector(".line-item-remove").addEventListener("click", () => row.remove());
  container.appendChild(row);
}

function openGenerateModal(delivery) {
  generateTargetId = delivery.id;
  generateMode = "generate";
  document.getElementById("generate-modal-title").textContent = "Generate Delivery Ticket";
  document.getElementById("btn-generate-submit").textContent = "Generate Ticket";
  document.getElementById("generate-modal-job").textContent = delivery.job_number;
  document.getElementById("generate-line-items").innerHTML = "";
  document.getElementById("generate-modal-status").textContent = "";
  addLineItemRow();
  document.getElementById("generate-modal").classList.remove("hidden");
}

function openReviseModal(delivery) {
  generateTargetId = delivery.id;
  generateMode = "revise";
  document.getElementById("generate-modal-title").textContent = "Revise Delivery Ticket";
  document.getElementById("btn-generate-submit").textContent = "Save Revision & Notify";
  document.getElementById("generate-modal-job").textContent = delivery.job_number;
  document.getElementById("generate-line-items").innerHTML = "";
  document.getElementById("generate-modal-status").textContent = "";
  const items = delivery.line_items && delivery.line_items.length ? delivery.line_items : [{}];
  items.forEach((item) => addLineItemRow(item));
  document.getElementById("generate-modal").classList.remove("hidden");
}

function initGenerateModal() {
  document.getElementById("btn-generate-add-row").addEventListener("click", () => addLineItemRow());

  document.getElementById("btn-generate-cancel").addEventListener("click", () => {
    document.getElementById("generate-modal").classList.add("hidden");
  });

  document.getElementById("btn-generate-submit").addEventListener("click", async () => {
    const statusEl = document.getElementById("generate-modal-status");
    const cards = [...document.querySelectorAll("#generate-line-items .line-item-card")];
    const lineItems = cards
      .map((card) => ({
        description: card.querySelector(".desc-input").value.trim(),
        quantity: card.querySelector(".qty-input").value.trim(),
        type: card.querySelector(".type-input").value.trim(),
        boxes: card.querySelector(".boxes-input").value.trim(),
        model_number: card.querySelector(".model-input").value.trim(),
        mfg: card.querySelector(".mfg-input").value.trim(),
      }))
      .filter((item) => item.description);

    if (lineItems.length === 0) {
      statusEl.textContent = "Add at least one item.";
      statusEl.className = "status-line err";
      return;
    }

    const endpoint = generateMode === "revise" ? "revise_ticket" : "generate_ticket";
    try {
      const result = await api(`/api/schedule/${generateTargetId}/${endpoint}`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ line_items: lineItems }),
      });
      document.getElementById("generate-modal").classList.add("hidden");
      if (generateMode === "revise" && result.reset_to_pack) {
        alert("This delivery had already been packed. Since the checked-off items no longer match, it has been reset and needs to be re-packed and re-verified before a driver can take it. The PM and warehouse have both been notified.");
      }
      await loadDeliveries();
    } catch (e) {
      statusEl.textContent = e.message;
      statusEl.className = "status-line err";
    }
  });
}

// ---------- Send to PM modal ----------

let sendPmTargetId = null;

async function openSendToPmModal(delivery) {
  sendPmTargetId = delivery.id;
  document.getElementById("send-pm-modal-job").textContent = delivery.job_number;
  document.getElementById("send-pm-status").textContent = "";

  const select = document.getElementById("send-pm-select");
  select.innerHTML = '<option value="">— Select a PM —</option>';
  try {
    const result = await api("/api/inventory/pms");
    result.pms.forEach((pm) => {
      const opt = document.createElement("option");
      opt.value = pm.email;
      opt.textContent = `${pm.name} (${pm.email})`;
      select.appendChild(opt);
    });
  } catch (e) {
    console.warn("Couldn't load PM list", e);
  }

  document.getElementById("send-pm-modal").classList.remove("hidden");
}

function initSendToPmModal() {
  document.getElementById("btn-send-pm-cancel").addEventListener("click", () => {
    document.getElementById("send-pm-modal").classList.add("hidden");
  });

  document.getElementById("btn-send-pm-submit").addEventListener("click", async () => {
    const pmEmail = document.getElementById("send-pm-select").value;
    const statusEl = document.getElementById("send-pm-status");
    if (!pmEmail) {
      statusEl.textContent = "Select a PM first.";
      statusEl.className = "status-line err";
      return;
    }
    try {
      const result = await api(`/api/schedule/${sendPmTargetId}/send_to_pm`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pm_email: pmEmail }),
      });
      if (result.sent) {
        statusEl.textContent = "Sent.";
        statusEl.className = "status-line ok";
        setTimeout(() => document.getElementById("send-pm-modal").classList.add("hidden"), 800);
      } else {
        statusEl.textContent = result.error || "Couldn't send — check email settings.";
        statusEl.className = "status-line err";
      }
    } catch (e) {
      statusEl.textContent = e.message;
      statusEl.className = "status-line err";
    }
  });
}

// ---------- View completed delivery modal ----------

function openViewModal(d) {
  const content = document.getElementById("view-modal-content");
  const fileUrl = (name) => `/api/schedule/${d.id}/file/${name}`;

  let html = `
    <div class="kv"><span>Job Number</span><strong>${d.job_number}</strong></div>
    <div class="kv"><span>Assigned Driver</span><strong>${d.assigned_driver || "—"}</strong></div>
    <div class="kv"><span>Ticket Source</span><strong>${d.ticket_source || "—"}</strong></div>
    <div class="kv"><span>Packed By</span><strong>${d.packed_by || "—"}</strong></div>
    <div class="kv"><span>Packed At</span><strong>${d.packed_at || "—"}</strong></div>
    <div class="kv"><span>Started (en route)</span><strong>${d.started_at || "—"}</strong></div>
    <div class="kv"><span>ETA at start</span><strong>${d.eta ? `${d.eta.duration_text} (${d.eta.distance_text})` : "Not available"}</strong></div>
    <div class="kv"><span>Signed By (receiver)</span><strong>${d.signed_by || "—"}</strong></div>
    <div class="kv"><span>Completed At</span><strong>${d.completed_at || "—"}</strong></div>
    <div class="kv"><span>Location</span><strong>${d.geotag ? `${d.geotag.latitude}, ${d.geotag.longitude}` : "Not available"}</strong></div>
  `;

  if (d.line_items && d.line_items.length) {
    html += `<p class="hint">Line Items:</p>`;
    d.line_items.forEach((item, i) => {
      const checked = d.line_item_checks && d.line_item_checks[i];
      html += `<div class="kv"><span>${checked ? "✅" : "⬜"} ${item.description}</span><strong>${item.quantity}</strong></div>`;
    });
  }

  if (d.ticket_filename) html += `<p class="hint">Ticket:</p><img src="${fileUrl(d.ticket_filename)}">`;
  if (d.packed_signature_filename) html += `<p class="hint">Packed By Signature:</p><img src="${fileUrl(d.packed_signature_filename)}">`;
  if (d.signature_filename) html += `<p class="hint">Receiver Signature:</p><img src="${fileUrl(d.signature_filename)}">`;
  (d.photo_filenames || []).forEach((p, i) => {
    html += `<p class="hint">Photo ${i + 1}:</p><img src="${fileUrl(p)}">`;
  });

  content.innerHTML = html;
  document.getElementById("view-modal").classList.remove("hidden");
}

function initViewModal() {
  document.getElementById("btn-view-close").addEventListener("click", () => {
    document.getElementById("view-modal").classList.add("hidden");
  });
}

// ---------- Boot ----------

initLogin();
initDashboard();
initUploadModal();
initGenerateModal();
initSendToPmModal();
initAdminTools();
initInventoryTab();
initViewModal();
tryRestoreSession();
