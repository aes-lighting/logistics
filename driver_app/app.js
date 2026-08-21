// AES Logistics driver app
// Vanilla JS, no build step. Stores deliveries locally in IndexedDB until synced.

const DB_NAME = "aes_logistics";
const DB_VERSION = 2;
const STORE = "deliveries";
const INCOMING_STORE = "incoming_queue";
const UPLOAD_URL = "/api/upload";

let db = null;
let currentDelivery = null; // in-progress delivery draft, held in memory until "Complete"
let currentIncomingScan = null; // { previewId, file, jobNumberGuess } for the Incoming Inventory flow
let currentUser = null; // { role: "driver", name } or { role: "admin", email } or { role: "pm", email, name }
let currentAppMode = null; // "warehouse" or "drivers" - which half of the driver-role app is showing

const ME_URL = "/api/auth/me";
const DRIVER_LOGIN_URL = "/api/auth/driver_login";
const ADMIN_LOGIN_URL = "/api/auth/admin_login";
const PM_LOGIN_URL = "/api/auth/pm_login";
const LOGOUT_URL = "/api/auth/logout";

// ---------- IndexedDB helpers ----------

function openDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const database = req.result;
      if (!database.objectStoreNames.contains(STORE)) {
        database.createObjectStore(STORE, { keyPath: "id" });
      }
      if (!database.objectStoreNames.contains(INCOMING_STORE)) {
        database.createObjectStore(INCOMING_STORE, { keyPath: "id" });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function dbPut(record, storeName = STORE) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, "readwrite");
    tx.objectStore(storeName).put(record);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

function dbDelete(id, storeName = STORE) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, "readwrite");
    tx.objectStore(storeName).delete(id);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

function dbGetAll(storeName = STORE) {
  return new Promise((resolve, reject) => {
    const tx = db.transaction(storeName, "readonly");
    const req = tx.objectStore(storeName).getAll();
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

// ---------- Utilities ----------

function uuid() {
  if (crypto.randomUUID) return crypto.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (c) => {
    const r = (Math.random() * 16) | 0;
    const v = c === "x" ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function show(screenId) {
  document.querySelectorAll(".screen").forEach((el) => el.classList.add("hidden"));
  document.getElementById(screenId).classList.remove("hidden");
}

function getDriverName() {
  return currentUser ? (currentUser.name || currentUser.email) : null;
}

function cacheUser(user) {
  currentUser = user;
  if (user) {
    localStorage.setItem("aes_cached_user", JSON.stringify(user));
  } else {
    localStorage.removeItem("aes_cached_user");
  }
}

function getCachedUser() {
  const raw = localStorage.getItem("aes_cached_user");
  return raw ? JSON.parse(raw) : null;
}

// ---------- Login ----------

function initLoginScreen() {
  document.getElementById("btn-login-driver").addEventListener("click", async () => {
    const name = document.getElementById("login-name-input").value.trim();
    const code = document.getElementById("login-code-input").value.trim();
    const errorEl = document.getElementById("login-error");
    errorEl.classList.add("hidden");

    if (!name || !code) {
      errorEl.textContent = "Enter your name and a code.";
      errorEl.classList.remove("hidden");
      return;
    }

    try {
      const resp = await fetch(DRIVER_LOGIN_URL, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name, code }),
      });
      const result = await resp.json();
      if (!resp.ok) {
        errorEl.textContent = result.error || "Login failed.";
        errorEl.classList.remove("hidden");
        return;
      }
      cacheUser({ role: "driver", name: result.name });
      showRoleMenu();
    } catch (e) {
      console.error("Driver login failed", e);
      errorEl.textContent = "Couldn't reach the server. Check your signal and try again.";
      errorEl.classList.remove("hidden");
    }
  });

  document.getElementById("btn-goto-admin-login").addEventListener("click", () => show("screen-admin-login"));
}

function initAdminLoginScreen() {
  document.getElementById("btn-login-admin").addEventListener("click", async () => {
    const email = document.getElementById("admin-login-email-input").value.trim();
    const password = document.getElementById("admin-login-password-input").value;
    const errorEl = document.getElementById("admin-login-error");
    errorEl.classList.add("hidden");

    try {
      const resp = await fetch(ADMIN_LOGIN_URL, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const result = await resp.json();
      if (resp.ok) {
        cacheUser({ role: "admin", email: result.email });
        showRoleMenu();
        return;
      }

      // Not an admin — try PM credentials before giving up.
      const pmResp = await fetch(PM_LOGIN_URL, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const pmResult = await pmResp.json();
      if (pmResp.ok) {
        cacheUser({ role: "pm", email: pmResult.email, name: pmResult.name });
        showRoleMenu();
        return;
      }

      errorEl.textContent = result.error || "Login failed.";
      errorEl.classList.remove("hidden");
    } catch (e) {
      console.error("Admin/PM login failed", e);
      errorEl.textContent = "Couldn't reach the server. Check your signal and try again.";
      errorEl.classList.remove("hidden");
    }
  });

  document.getElementById("btn-goto-driver-login").addEventListener("click", () => show("screen-login"));
}

async function logout() {
  try {
    await fetch(LOGOUT_URL, { method: "POST", credentials: "same-origin" });
  } catch (e) {
    console.warn("Logout request failed (probably offline) — clearing local session anyway.", e);
  }
  cacheUser(null);
  currentAppMode = null;
  document.getElementById("login-name-input").value = "";
  document.getElementById("login-code-input").value = "";
  show("screen-login");
}

// ---------- Role menu ----------

const ROLE_TILE_DEFS = {
  drivers: { icon: "\u{1F69A}", label: "Driver", sub: "Delivery photos & tickets" },
  warehouse: { icon: "\u{1F4E6}", label: "Warehouse", sub: "Incoming & outgoing inventory" },
  "pm-redirect": { icon: "\u{1F5C2}\uFE0F", label: "Project Management", sub: "Access to everything" },
};

function showRoleMenu() {
  const modes = ["drivers", "warehouse"];
  if (currentUser && (currentUser.role === "admin" || currentUser.role === "pm")) {
    modes.push("pm-redirect");
  }

  const container = document.getElementById("role-menu-tiles");
  container.innerHTML = "";
  modes.forEach((mode) => {
    const def = ROLE_TILE_DEFS[mode];
    const div = document.createElement("div");
    div.className = "role-tile";
    div.innerHTML = `
      <div class="role-tile-icon">${def.icon}</div>
      <div class="role-tile-label">${def.label}</div>
      <div class="role-tile-sub">${def.sub}</div>
    `;
    div.addEventListener("click", () => handleRoleTileClick(mode));
    container.appendChild(div);
  });

  show("screen-role-menu");
}

function handleRoleTileClick(mode) {
  if (mode === "pm-redirect") {
    window.location.href = "/pm";
    return;
  }
  currentAppMode = mode; // "warehouse" or "drivers"
  goHome();
}

function initRoleMenu() {
  document.getElementById("btn-role-menu-logout").addEventListener("click", logout);
}

// ---------- Screen: home ----------

async function goHome() {
  document.getElementById("driver-name-display").textContent = getDriverName() || "";

  const showDrivers = currentAppMode === "drivers";
  const showWarehouse = currentAppMode === "warehouse";
  document.getElementById("section-drivers").classList.toggle("hidden", !showDrivers);
  document.getElementById("section-warehouse").classList.toggle("hidden", !showWarehouse);

  if (showDrivers) {
    await refreshQueue();
    await refreshScheduledList();
  }
  if (showWarehouse) {
    await refreshIncomingQueue();
    await refreshPackList();
  }
  show("screen-home");
}

async function refreshQueue() {
  const all = await dbGetAll();
  const pending = all.filter((d) => d.status === "completed" || d.status === "sync_failed");

  const list = document.getElementById("queue-list");
  const countEl = document.getElementById("queue-count");
  const syncBtn = document.getElementById("btn-sync");

  countEl.textContent = pending.length;
  syncBtn.disabled = pending.length === 0;

  if (pending.length === 0) {
    list.innerHTML = '<div class="queue-empty">No deliveries waiting to sync.</div>';
    return;
  }

  list.innerHTML = "";
  pending
    .sort((a, b) => new Date(b.completed_at) - new Date(a.completed_at))
    .forEach((d) => {
      const ticketCount = d.photos.filter((p) => p.type === "ticket").length;
      const palletCount = d.photos.filter((p) => p.type === "pallet").length;
      const div = document.createElement("div");
      div.className = "queue-item";
      div.innerHTML = `
        <div>
          <div class="queue-item-id">${d.id.slice(0, 8)}</div>
          <div class="queue-item-meta">${ticketCount} ticket, ${palletCount} pallet photo(s)</div>
        </div>
        <div class="queue-item-status ${d.status === "sync_failed" ? "status-failed" : "status-completed"}">
          ${d.status === "sync_failed" ? "Retry" : "Ready"}
        </div>
      `;
      list.appendChild(div);
    });
}

function initHomeScreen() {
  document.getElementById("btn-new-delivery").addEventListener("click", startNewDelivery);
  document.getElementById("btn-incoming-inventory").addEventListener("click", startIncomingInventory);
  document.getElementById("btn-change-driver").addEventListener("click", logout);
  document.getElementById("btn-logout").addEventListener("click", logout);
  document.getElementById("btn-sync").addEventListener("click", syncAll);
  document.getElementById("btn-incoming-retry").addEventListener("click", retryIncomingQueue);
  document.getElementById("btn-switch-role").addEventListener("click", showRoleMenu);
}

const SCHEDULE_MINE_URL = "/api/schedule/driver/mine";

let currentStartDelivery = null;

async function refreshScheduledList() {
  const listEl = document.getElementById("scheduled-list");
  const countEl = document.getElementById("scheduled-count");
  try {
    const resp = await fetch(SCHEDULE_MINE_URL, { credentials: "same-origin" });
    if (!resp.ok) throw new Error(`status ${resp.status}`);
    const result = await resp.json();
    const deliveries = result.deliveries || [];
    countEl.textContent = deliveries.length;

    if (deliveries.length === 0) {
      listEl.innerHTML = '<div class="queue-empty">No deliveries assigned to you right now.</div>';
      return;
    }
    listEl.innerHTML = "";
    deliveries.forEach((d) => {
      const div = document.createElement("div");
      div.className = "queue-item";
      div.style.cursor = "pointer";
      const statusLabel = d.status === "en_route" ? "En Route — Continue" : "Start";
      div.innerHTML = `
        <div>
          <div class="queue-item-id">Job #${d.job_number} &mdash; ${d.delivery_date}</div>
          <div class="queue-item-meta">${d.receiver_name}</div>
        </div>
        <div class="queue-item-status status-completed">${statusLabel}</div>
      `;
      div.addEventListener("click", () => {
        if (d.status === "en_route") {
          openScheduledTicket(d);
        } else {
          openStartDeliveryScreen(d);
        }
      });
      listEl.appendChild(div);
    });
  } catch (e) {
    console.error("Failed to load my deliveries", e);
    listEl.innerHTML = '<div class="queue-empty">Couldn\'t load your deliveries — check your signal.</div>';
    countEl.textContent = "0";
  }
}

// ---------- Start Delivery (SMS + ETA to receiver) ----------

function openStartDeliveryScreen(delivery) {
  currentStartDelivery = delivery;
  document.getElementById("start-job-number").textContent = delivery.job_number;
  document.getElementById("start-receiver-name").textContent = delivery.receiver_name;
  document.getElementById("start-site-address").textContent = delivery.site_address || "(not on file)";
  document.getElementById("start-delivery-result").textContent = "";
  document.getElementById("btn-start-delivery-go").classList.remove("hidden");
  document.getElementById("btn-start-delivery-continue").classList.add("hidden");
  show("screen-start-delivery");
}

function initStartDeliveryScreen() {
  document.getElementById("btn-start-delivery-cancel").addEventListener("click", () => {
    currentStartDelivery = null;
    goHome();
  });

  document.getElementById("btn-start-delivery-continue").addEventListener("click", () => {
    openScheduledTicket(currentStartDelivery);
  });

  document.getElementById("btn-start-delivery-go").addEventListener("click", async () => {
    const btn = document.getElementById("btn-start-delivery-go");
    const resultEl = document.getElementById("start-delivery-result");
    btn.disabled = true;
    resultEl.textContent = "Getting your location…";

    const getLocation = () =>
      new Promise((resolve) => {
        if (!("geolocation" in navigator)) return resolve(null);
        navigator.geolocation.getCurrentPosition(
          (pos) => resolve({ latitude: pos.coords.latitude, longitude: pos.coords.longitude }),
          () => resolve(null),
          { enableHighAccuracy: true, timeout: 10000 }
        );
      });

    const coords = await getLocation();
    resultEl.textContent = "Notifying receiver…";

    try {
      const resp = await fetch(`/api/schedule/${currentStartDelivery.id}/start`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(coords || {}),
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result.error || `Failed with status ${resp.status}`);

      let msg = result.sms_sent ? "Receiver has been texted that you're on the way." : "Started — but the text to the receiver could not be sent.";
      if (result.eta) msg += ` ETA: ${result.eta.duration_text}.`;
      resultEl.textContent = msg;

      currentStartDelivery.status = "en_route";
      btn.classList.add("hidden");
      document.getElementById("btn-start-delivery-continue").classList.remove("hidden");
    } catch (e) {
      console.error("Start delivery failed", e);
      resultEl.textContent = `Couldn't start this delivery: ${e.message}`;
      btn.disabled = false;
    }
  });
}

function initScheduledTicketScreen() {
  document.getElementById("btn-scheduled-cancel").addEventListener("click", () => {
    const hasProgress = scheduledPhotos.length > 0 || sigHasStroke || anyScheduledCheckboxChecked();
    if (hasProgress && !confirm("Discard progress on this delivery?")) return;
    currentScheduledDelivery = null;
    goHome();
  });

  document.getElementById("scheduled-signed-by-input").addEventListener("input", updateScheduledCompleteState);

  document.getElementById("input-scheduled-photo").addEventListener("change", (e) => {
    const file = e.target.files[0];
    if (!file) return;
    scheduledPhotos.push(file);
    renderScheduledPhotoThumbs();
    updateScheduledCompleteState();
    e.target.value = "";
  });

  document.getElementById("btn-clear-signature").addEventListener("click", clearSignatureCanvas);

  document.getElementById("btn-scheduled-complete").addEventListener("click", submitScheduledCompletion);

  initSignatureCanvas();
}

function anyScheduledCheckboxChecked() {
  return [...document.querySelectorAll("#scheduled-checkoff-items input[type=\"checkbox\"]")].some((cb) => cb.checked);
}

function allScheduledItemsChecked() {
  const checkboxes = document.querySelectorAll("#scheduled-checkoff-items input[type=\"checkbox\"]");
  if (checkboxes.length === 0) return false;
  return [...checkboxes].every((cb) => cb.checked);
}

function renderScheduledPhotoThumbs() {
  const container = document.getElementById("scheduled-photo-thumbs");
  container.innerHTML = "";
  scheduledPhotos.forEach((file) => {
    const img = document.createElement("img");
    img.className = "thumb";
    img.src = URL.createObjectURL(file);
    container.appendChild(img);
  });
  document.getElementById("scheduled-photos-dot").dataset.filled = scheduledPhotos.length >= 2 ? "true" : "false";
}

function initSignatureCanvas() {
  const canvas = document.getElementById("signature-canvas");

  function pos(e) {
    const rect = canvas.getBoundingClientRect();
    const point = e.touches ? e.touches[0] : e;
    return { x: point.clientX - rect.left, y: point.clientY - rect.top };
  }

  function start(e) {
    e.preventDefault();
    sigDrawing = true;
    const p = pos(e);
    sigCtx.beginPath();
    sigCtx.moveTo(p.x, p.y);
  }
  function move(e) {
    if (!sigDrawing) return;
    e.preventDefault();
    const p = pos(e);
    sigCtx.lineTo(p.x, p.y);
    sigCtx.stroke();
    sigHasStroke = true;
    updateScheduledCompleteState();
  }
  function end() {
    sigDrawing = false;
  }

  canvas.addEventListener("pointerdown", start);
  canvas.addEventListener("pointermove", move);
  window.addEventListener("pointerup", end);
  canvas.addEventListener("touchstart", start, { passive: false });
  canvas.addEventListener("touchmove", move, { passive: false });
  canvas.addEventListener("touchend", end);
}

function setUpSignatureCanvasSize() {
  const canvas = document.getElementById("signature-canvas");
  canvas.width = canvas.clientWidth;
  canvas.height = canvas.clientHeight;
  sigCtx = canvas.getContext("2d");
  sigCtx.lineWidth = 2.5;
  sigCtx.lineCap = "round";
  sigCtx.strokeStyle = "#14171C";
}

function clearSignatureCanvas() {
  if (!sigCtx) return;
  const canvas = document.getElementById("signature-canvas");
  sigCtx.clearRect(0, 0, canvas.width, canvas.height);
  sigHasStroke = false;
  updateScheduledCompleteState();
}

function updateScheduledCompleteState() {
  const checked = allScheduledItemsChecked();
  const signedByFilled = document.getElementById("scheduled-signed-by-input").value.trim().length > 0;
  const btn = document.getElementById("btn-scheduled-complete");
  const hint = document.getElementById("scheduled-complete-hint");

  const ready = checked && scheduledPhotos.length >= 2 && sigHasStroke && signedByFilled;
  btn.disabled = !ready;
  hint.textContent = ready
    ? "Ready to complete and send."
    : "Check off every item as unloaded, add 2+ photos, enter the receiver's name, and get a signature to complete.";
}

function openScheduledTicket(delivery) {
  currentScheduledDelivery = delivery;
  scheduledPhotos = [];
  scheduledGeotag = null;
  sigHasStroke = false;

  document.getElementById("scheduled-job-number").textContent = delivery.job_number;
  document.getElementById("scheduled-ticket-image").src = `/api/schedule/${delivery.id}/file/${delivery.ticket_filename}`;
  document.getElementById("scheduled-signed-by-input").value = delivery.receiver_name || "";
  document.getElementById("scheduled-photo-thumbs").innerHTML = "";
  document.getElementById("scheduled-photos-dot").dataset.filled = "false";
  document.getElementById("scheduled-geo-status").textContent = "Getting location…";

  const itemsContainer = document.getElementById("scheduled-checkoff-items");
  itemsContainer.innerHTML = "";
  if (delivery.line_items && delivery.line_items.length > 0) {
    delivery.line_items.forEach((item, i) => {
      const label = document.createElement("label");
      label.className = "checkoff-row";
      label.innerHTML = `
        <input type="checkbox" class="scheduled-item-checkbox" data-index="${i}">
        <span>${item.description}${item.quantity ? ` &mdash; qty ${item.quantity}` : ""} (unloaded)</span>
      `;
      itemsContainer.appendChild(label);
    });
  } else {
    const label = document.createElement("label");
    label.className = "checkoff-row";
    label.innerHTML = `
      <input type="checkbox" id="scheduled-overall-checkbox">
      <span>All items on this ticket have been checked and are correct</span>
    `;
    itemsContainer.appendChild(label);
  }
  itemsContainer.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    cb.addEventListener("change", updateScheduledCompleteState);
  });

  show("screen-scheduled-ticket");
  setUpSignatureCanvasSize();
  updateScheduledCompleteState();

  const geoStatus = document.getElementById("scheduled-geo-status");
  if ("geolocation" in navigator) {
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        scheduledGeotag = { latitude: pos.coords.latitude, longitude: pos.coords.longitude };
        geoStatus.textContent = `Location captured (${pos.coords.latitude.toFixed(5)}, ${pos.coords.longitude.toFixed(5)}).`;
      },
      (err) => {
        console.warn("Geolocation failed", err);
        geoStatus.textContent = "Location not available (permission denied or unsupported) — completing without it.";
      },
      { enableHighAccuracy: true, timeout: 10000 }
    );
  } else {
    geoStatus.textContent = "Location not supported on this device — completing without it.";
  }
}

async function submitScheduledCompletion() {
  const btn = document.getElementById("btn-scheduled-complete");
  btn.disabled = true;
  btn.textContent = "Sending…";

  try {
    const canvas = document.getElementById("signature-canvas");
    const signatureBlob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));

    const formData = new FormData();
    formData.append("signed_by", document.getElementById("scheduled-signed-by-input").value.trim());
    if (scheduledGeotag) formData.append("geotag", JSON.stringify(scheduledGeotag));
    formData.append("signature", signatureBlob, "signature.png");
    scheduledPhotos.forEach((file, i) => formData.append("photos", file, `photo_${i + 1}.jpg`));

    const itemCheckboxes = document.querySelectorAll("#scheduled-checkoff-items .scheduled-item-checkbox");
    if (itemCheckboxes.length > 0) {
      const checks = [...itemCheckboxes].sort((a, b) => a.dataset.index - b.dataset.index).map((cb) => cb.checked);
      formData.append("unload_item_checks", JSON.stringify(checks));
    } else {
      formData.append("checkoff_confirmed", "true");
    }

    const resp = await fetch(`/api/schedule/${currentScheduledDelivery.id}/complete`, {
      method: "POST",
      credentials: "same-origin",
      body: formData,
    });
    const result = await resp.json();
    if (!resp.ok) throw new Error(result.error || `Failed with status ${resp.status}`);

    document.getElementById("scheduled-done-sub").textContent =
      `Sent to the PM and to ${currentScheduledDelivery.receiver_name} for Job #${currentScheduledDelivery.job_number}.`;
    currentScheduledDelivery = null;
    show("screen-scheduled-done");
  } catch (e) {
    console.error("Complete scheduled delivery failed", e);
    alert(`Couldn't send this delivery: ${e.message}. Check your signal and try again — nothing has been lost.`);
    btn.disabled = false;
  } finally {
    btn.textContent = "Complete & Send";
  }
}

function initScheduledDoneScreen() {
  document.getElementById("btn-scheduled-done-home").addEventListener("click", goHome);
}

// ---------- Screen: capture ----------

function startNewDelivery() {
  currentDelivery = {
    id: uuid(),
    driver: getDriverName(),
    status: "in_progress",
    started_at: new Date().toISOString(),
    completed_at: null,
    photos: [], // { id, type, blob, filename, captured_at }
  };
  renderCaptureScreen();
  show("screen-capture");
}

function renderCaptureScreen() {
  renderThumbs("ticket");
  renderThumbs("pallet");
  updateCompleteButtonState();
}

function renderThumbs(type) {
  const container = document.getElementById(`${type}-thumbs`);
  container.innerHTML = "";
  currentDelivery.photos
    .filter((p) => p.type === type)
    .forEach((p) => {
      const img = document.createElement("img");
      img.className = "thumb";
      img.src = URL.createObjectURL(p.blob);
      container.appendChild(img);
    });

  const groupHeader = container.closest(".photo-group").querySelector(".req-dot");
  const hasAny = currentDelivery.photos.some((p) => p.type === type);
  groupHeader.dataset.filled = hasAny ? "true" : "false";
}

function updateCompleteButtonState() {
  const hasTicket = currentDelivery.photos.some((p) => p.type === "ticket");
  const hasPallet = currentDelivery.photos.some((p) => p.type === "pallet");
  const btn = document.getElementById("btn-complete-delivery");
  const hint = document.getElementById("complete-hint");
  btn.disabled = !(hasTicket && hasPallet);
  hint.textContent = btn.disabled
    ? "Add at least 1 ticket photo and 1 pallet/box photo to complete."
    : "Ready to complete this delivery.";
}

function handlePhotoCapture(type, fileInputEvent) {
  const file = fileInputEvent.target.files[0];
  if (!file) return;

  const index = currentDelivery.photos.filter((p) => p.type === type).length + 1;
  const filename = `${currentDelivery.id}_${type}_${Date.now()}_${index}.jpg`;

  currentDelivery.photos.push({
    id: uuid(),
    type,
    blob: file,
    filename,
    captured_at: new Date().toISOString(),
  });

  renderCaptureScreen();
  fileInputEvent.target.value = ""; // allow retaking the same shot again
}

function initCaptureScreen() {
  document.getElementById("input-ticket").addEventListener("change", (e) => handlePhotoCapture("ticket", e));
  document.getElementById("input-pallet").addEventListener("change", (e) => handlePhotoCapture("pallet", e));

  document.getElementById("btn-cancel-delivery").addEventListener("click", () => {
    if (currentDelivery.photos.length > 0) {
      const ok = confirm("Discard this delivery's photos?");
      if (!ok) return;
    }
    currentDelivery = null;
    goHome();
  });

  document.getElementById("btn-complete-delivery").addEventListener("click", async () => {
    currentDelivery.status = "completed";
    currentDelivery.completed_at = new Date().toISOString();
    await dbPut(currentDelivery);
    currentDelivery = null;
    show("screen-complete");
  });
}

// ---------- Screen: complete ----------

function initCompleteScreen() {
  document.getElementById("btn-back-home").addEventListener("click", goHome);
}

// ---------- Incoming Inventory (packing slips) ----------
// Unlike deliveries, this flow normally talks to the server immediately
// (needs signal) so the OCR'd job number can be shown back for
// confirmation/editing before anything is filed. If any step fails due to
// signal, the item is saved locally with a status and shown in a retry
// queue on Home, same idea as the delivery sync queue.
//
// Statuses:
//   pending_scan    - photo taken, scan upload hasn't succeeded yet (auto-retries)
//   scanned         - scan succeeded, waiting on a human to confirm/edit the
//                     job number or flag it (NOT auto-retried — needs review)
//   pending_confirm - human already chose a job number, but the confirm
//                     request failed (auto-retries, no human input needed)
//   pending_flag    - human already chose to flag, but the flag request
//                     failed (auto-retries, no human input needed)

const SCAN_URL = "/api/incoming/scan";
const CONFIRM_URL = "/api/incoming/confirm";
const FLAG_URL = "/api/incoming/flag";

function startIncomingInventory() {
  currentIncomingScan = null;
  document.getElementById("incoming-thumb").innerHTML = "";
  document.getElementById("incoming-scanning-status").classList.add("hidden");
  show("screen-incoming-capture");
}

function initIncomingCaptureScreen() {
  document.getElementById("input-incoming").addEventListener("change", handleIncomingPhoto);
  document.getElementById("btn-cancel-incoming").addEventListener("click", goHome);
}

async function handleIncomingPhoto(fileInputEvent) {
  const file = fileInputEvent.target.files[0];
  if (!file) return;

  const thumbContainer = document.getElementById("incoming-thumb");
  thumbContainer.innerHTML = "";
  const img = document.createElement("img");
  img.className = "thumb";
  img.src = URL.createObjectURL(file);
  thumbContainer.appendChild(img);

  document.getElementById("incoming-scanning-status").classList.remove("hidden");
  fileInputEvent.target.value = "";

  // Persist immediately so the photo is never lost even if the scan fails
  // or the app is closed before it succeeds.
  const record = {
    id: uuid(),
    status: "pending_scan",
    photoBlob: file,
    previewId: null,
    jobNumberGuess: null,
    jobNumberConfirmed: null,
    flagReason: null,
    flagNote: null,
    createdAt: new Date().toISOString(),
  };
  await dbPut(record, INCOMING_STORE);

  const ok = await attemptScan(record);
  document.getElementById("incoming-scanning-status").classList.add("hidden");

  if (ok) {
    currentIncomingScan = record;
    showIncomingConfirmScreen();
  } else {
    alert("No signal — this photo is saved and will scan automatically once you're back online. You'll find it under Incoming Inventory — Pending.");
    goHome();
  }
}

/** Tries the scan upload for a pending_scan record. Returns true/false, updates + saves the record either way. */
async function attemptScan(record) {
  try {
    const formData = new FormData();
    formData.append("photo", record.photoBlob, "slip.jpg");
    const resp = await fetch(SCAN_URL, { method: "POST", credentials: "same-origin", body: formData });
    if (!resp.ok) throw new Error(`Scan failed with status ${resp.status}`);
    const result = await resp.json();

    record.status = "scanned";
    record.previewId = result.preview_id;
    record.jobNumberGuess = result.job_number_guess;
    await dbPut(record, INCOMING_STORE);
    return true;
  } catch (e) {
    console.error("Scan attempt failed", e);
    record.status = "pending_scan";
    await dbPut(record, INCOMING_STORE);
    return false;
  }
}

let cachedLocations = null;

async function populateLocationSelect() {
  const select = document.getElementById("incoming-location-select");
  if (!cachedLocations) {
    try {
      const resp = await fetch("/api/inventory/locations", { credentials: "same-origin" });
      if (resp.ok) {
        const result = await resp.json();
        cachedLocations = result.locations;
      }
    } catch (e) {
      console.warn("Couldn't load location list (offline?) — using last known list if any.", e);
    }
  }
  if (!cachedLocations) return; // offline on first-ever load with nothing cached yet; select stays at placeholder

  select.innerHTML = '<option value="">— Select a location —</option>';
  cachedLocations.forEach((loc) => {
    const opt = document.createElement("option");
    opt.value = loc;
    opt.textContent = loc;
    select.appendChild(opt);
  });
}

function showIncomingConfirmScreen() {
  const thumb = document.getElementById("confirm-thumb");
  thumb.src = URL.createObjectURL(currentIncomingScan.photoBlob);

  const note = document.getElementById("ocr-guess-note");
  const input = document.getElementById("job-number-input");

  if (currentIncomingScan.jobNumberGuess) {
    note.textContent = `Job number detected: ${currentIncomingScan.jobNumberGuess} — please confirm it's correct.`;
    note.className = "ocr-note found";
    input.value = currentIncomingScan.jobNumberGuess;
  } else {
    note.textContent = "No job number could be read automatically. Enter it manually, or flag this slip.";
    note.className = "ocr-note not-found";
    input.value = "";
  }

  populateLocationSelect();
  document.getElementById("incoming-location-select").value = currentIncomingScan.locationConfirmed || "";

  show("screen-incoming-confirm");
  input.focus();
}

function initIncomingConfirmScreen() {
  document.getElementById("btn-back-to-incoming-capture").addEventListener("click", () => {
    // The record stays in the queue as "scanned" — nothing is lost, it can
    // be reopened from Home later.
    currentIncomingScan = null;
    goHome();
  });

  document.getElementById("btn-confirm-file").addEventListener("click", async () => {
    const jobNumber = document.getElementById("job-number-input").value.trim();
    const location = document.getElementById("incoming-location-select").value;
    if (!jobNumber) {
      alert("Enter a job number, or use Flag if this slip doesn't have one.");
      return;
    }
    if (!location) {
      alert("Select which warehouse/location this is going to.");
      return;
    }
    currentIncomingScan.jobNumberConfirmed = jobNumber;
    currentIncomingScan.locationConfirmed = location;
    currentIncomingScan.status = "pending_confirm";
    await dbPut(currentIncomingScan, INCOMING_STORE);

    const result = await attemptConfirm(currentIncomingScan);
    if (result.ok) {
      document.getElementById("incoming-done-stamp").textContent = "FILED";
      document.getElementById("incoming-done-sub").textContent = `Filed to Job_${result.jobNumber} (${location}).`;
      currentIncomingScan = null;
      show("screen-incoming-done");
    } else {
      alert("No signal — saved. This will file automatically once you're back online (Incoming Inventory — Pending).");
      currentIncomingScan = null;
      goHome();
    }
  });

  document.getElementById("btn-open-flag").addEventListener("click", () => {
    document.getElementById("flag-thumb").src = document.getElementById("confirm-thumb").src;
    document.getElementById("flag-reason-select").value = "Missing job number";
    document.getElementById("flag-note-input").value = "";
    show("screen-incoming-flag");
  });
}

/** Tries the confirm call for a pending_confirm record. Returns { ok, jobNumber }. Deletes record from queue on success. */
async function attemptConfirm(record) {
  try {
    const resp = await fetch(CONFIRM_URL, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        preview_id: record.previewId,
        job_number: record.jobNumberConfirmed,
        location: record.locationConfirmed,
        staff: getDriverName(),
      }),
    });
    if (!resp.ok) throw new Error(`Confirm failed with status ${resp.status}`);
    const result = await resp.json();
    await dbDelete(record.id, INCOMING_STORE);
    return { ok: true, jobNumber: result.job_number };
  } catch (e) {
    console.error("Confirm attempt failed", e);
    record.status = "pending_confirm";
    await dbPut(record, INCOMING_STORE);
    return { ok: false };
  }
}

function initIncomingFlagScreen() {
  document.getElementById("btn-back-to-confirm").addEventListener("click", () => show("screen-incoming-confirm"));

  document.getElementById("btn-submit-flag").addEventListener("click", async () => {
    const reason = document.getElementById("flag-reason-select").value;
    const note = document.getElementById("flag-note-input").value.trim();

    currentIncomingScan.flagReason = reason;
    currentIncomingScan.flagNote = note;
    currentIncomingScan.status = "pending_flag";
    await dbPut(currentIncomingScan, INCOMING_STORE);

    const result = await attemptFlag(currentIncomingScan);
    if (result.ok) {
      document.getElementById("incoming-done-stamp").textContent = "FLAGGED";
      document.getElementById("incoming-done-sub").textContent = result.emailSent
        ? "The PM team has been emailed about this slip."
        : "Saved, but the alert email could not be sent — let the PM team know directly.";
      currentIncomingScan = null;
      show("screen-incoming-done");
    } else {
      alert("No signal — saved. This will submit automatically once you're back online (Incoming Inventory — Pending).");
      currentIncomingScan = null;
      goHome();
    }
  });
}

/** Tries the flag call for a pending_flag record. Returns { ok, emailSent }. Deletes record from queue on success. */
async function attemptFlag(record) {
  try {
    const resp = await fetch(FLAG_URL, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        preview_id: record.previewId,
        reason: record.flagReason,
        note: record.flagNote,
        staff: getDriverName(),
      }),
    });
    if (!resp.ok) throw new Error(`Flag failed with status ${resp.status}`);
    const result = await resp.json();
    await dbDelete(record.id, INCOMING_STORE);
    return { ok: true, emailSent: result.email_sent };
  } catch (e) {
    console.error("Flag attempt failed", e);
    record.status = "pending_flag";
    await dbPut(record, INCOMING_STORE);
    return { ok: false };
  }
}

function initIncomingDoneScreen() {
  document.getElementById("btn-incoming-done-home").addEventListener("click", goHome);
}

// ---------- Incoming Inventory: Home screen queue ----------

const INCOMING_STATUS_LABELS = {
  pending_scan: "Waiting for signal",
  scanned: "Needs review",
  pending_confirm: "Filing (will retry)",
  pending_flag: "Flagging (will retry)",
};

async function refreshIncomingQueue() {
  const all = await dbGetAll(INCOMING_STORE);

  const list = document.getElementById("incoming-queue-list");
  const countEl = document.getElementById("incoming-queue-count");
  const retryBtn = document.getElementById("btn-incoming-retry");

  countEl.textContent = all.length;
  const hasAutoRetryable = all.some((r) => r.status === "pending_scan" || r.status === "pending_confirm" || r.status === "pending_flag");
  retryBtn.disabled = !hasAutoRetryable;

  if (all.length === 0) {
    list.innerHTML = '<div class="queue-empty">Nothing waiting.</div>';
    return;
  }

  list.innerHTML = "";
  all
    .sort((a, b) => new Date(b.createdAt) - new Date(a.createdAt))
    .forEach((record) => {
      const div = document.createElement("div");
      div.className = "queue-item";
      const needsReview = record.status === "scanned";
      div.innerHTML = `
        <div>
          <div class="queue-item-id">${record.id.slice(0, 8)}</div>
          <div class="queue-item-meta">${INCOMING_STATUS_LABELS[record.status] || record.status}</div>
        </div>
        <div class="queue-item-status ${needsReview ? "status-failed" : "status-completed"}">
          ${needsReview ? "Review" : "Pending"}
        </div>
      `;
      if (needsReview) {
        div.style.cursor = "pointer";
        div.addEventListener("click", () => {
          currentIncomingScan = record;
          showIncomingConfirmScreen();
        });
      }
      list.appendChild(div);
    });
}

async function retryIncomingQueue() {
  const statusEl = document.getElementById("incoming-retry-status");
  const all = await dbGetAll(INCOMING_STORE);
  const retryable = all.filter((r) => r.status === "pending_scan" || r.status === "pending_confirm" || r.status === "pending_flag");

  if (retryable.length === 0) return;

  let succeeded = 0;
  let stillFailing = 0;

  for (const record of retryable) {
    statusEl.textContent = `Retrying ${succeeded + stillFailing + 1} of ${retryable.length}...`;

    if (record.status === "pending_scan") {
      const ok = await attemptScan(record);
      if (ok) succeeded++; else stillFailing++;
    } else if (record.status === "pending_confirm") {
      const result = await attemptConfirm(record);
      if (result.ok) succeeded++; else stillFailing++;
    } else if (record.status === "pending_flag") {
      const result = await attemptFlag(record);
      if (result.ok) succeeded++; else stillFailing++;
    }
  }

  statusEl.textContent = `${succeeded} of ${retryable.length} went through${stillFailing ? `, ${stillFailing} still waiting for signal` : ""}.`;
  await refreshIncomingQueue();
}

// ---------- Outgoing Inventory (Warehouse packing/checkoff/signature) ----------

let currentPackDelivery = null;
let packSigCtx = null;
let packSigHasStroke = false;
let packSigDrawing = false;

async function refreshPackList() {
  const listEl = document.getElementById("pack-list");
  const countEl = document.getElementById("pack-count");
  try {
    const resp = await fetch("/api/schedule/warehouse/ready_to_pack", { credentials: "same-origin" });
    if (!resp.ok) throw new Error(`status ${resp.status}`);
    const result = await resp.json();
    const deliveries = result.deliveries || [];
    countEl.textContent = deliveries.length;

    if (deliveries.length === 0) {
      listEl.innerHTML = '<div class="queue-empty">Nothing waiting to be packed.</div>';
      return;
    }
    listEl.innerHTML = "";
    deliveries.forEach((d) => {
      const div = document.createElement("div");
      div.className = "queue-item";
      div.style.cursor = "pointer";
      div.innerHTML = `
        <div>
          <div class="queue-item-id">Job #${d.job_number} &mdash; ${d.delivery_date}</div>
          <div class="queue-item-meta">${d.receiver_name}</div>
        </div>
        <div class="queue-item-status status-completed">Pack</div>
      `;
      div.addEventListener("click", () => openPackScreen(d));
      listEl.appendChild(div);
    });
  } catch (e) {
    console.error("Failed to load ready-to-pack list", e);
    listEl.innerHTML = '<div class="queue-empty">Couldn\'t load — check your signal.</div>';
    countEl.textContent = "0";
  }
}

function openPackScreen(delivery) {
  currentPackDelivery = delivery;
  packSigHasStroke = false;

  document.getElementById("pack-job-number").textContent = delivery.job_number;
  document.getElementById("pack-ticket-image").src = `/api/schedule/${delivery.id}/file/${delivery.ticket_filename}`;
  document.getElementById("pack-packed-by-input").value = "";

  const itemsContainer = document.getElementById("pack-line-items");
  itemsContainer.innerHTML = "";

  if (delivery.line_items && delivery.line_items.length > 0) {
    delivery.line_items.forEach((item, i) => {
      const label = document.createElement("label");
      label.className = "checkoff-row";
      label.innerHTML = `
        <input type="checkbox" class="pack-item-checkbox" data-index="${i}">
        <span>${item.description}${item.quantity ? ` &mdash; qty ${item.quantity}` : ""}</span>
      `;
      itemsContainer.appendChild(label);
    });
  } else {
    const label = document.createElement("label");
    label.className = "checkoff-row";
    label.innerHTML = `
      <input type="checkbox" id="pack-overall-checkbox">
      <span>All items have been checked and packed correctly</span>
    `;
    itemsContainer.appendChild(label);
  }

  itemsContainer.querySelectorAll('input[type="checkbox"]').forEach((cb) => {
    cb.addEventListener("change", updatePackCompleteState);
  });

  show("screen-pack-ticket");
  setUpPackSignatureCanvasSize();
  updatePackCompleteState();
}

function initPackScreen() {
  document.getElementById("btn-pack-cancel").addEventListener("click", () => {
    const hasProgress = packSigHasStroke || document.getElementById("pack-packed-by-input").value.trim().length > 0;
    if (hasProgress && !confirm("Discard progress on this order?")) return;
    currentPackDelivery = null;
    goHome();
  });

  document.getElementById("pack-packed-by-input").addEventListener("input", updatePackCompleteState);
  document.getElementById("btn-pack-clear-signature").addEventListener("click", clearPackSignatureCanvas);
  document.getElementById("btn-pack-complete").addEventListener("click", submitPackCompletion);

  initPackSignatureCanvas();
}

function initPackSignatureCanvas() {
  const canvas = document.getElementById("pack-signature-canvas");

  function pos(e) {
    const rect = canvas.getBoundingClientRect();
    const point = e.touches ? e.touches[0] : e;
    return { x: point.clientX - rect.left, y: point.clientY - rect.top };
  }
  function start(e) {
    e.preventDefault();
    packSigDrawing = true;
    const p = pos(e);
    packSigCtx.beginPath();
    packSigCtx.moveTo(p.x, p.y);
  }
  function move(e) {
    if (!packSigDrawing) return;
    e.preventDefault();
    const p = pos(e);
    packSigCtx.lineTo(p.x, p.y);
    packSigCtx.stroke();
    packSigHasStroke = true;
    updatePackCompleteState();
  }
  function end() {
    packSigDrawing = false;
  }

  canvas.addEventListener("pointerdown", start);
  canvas.addEventListener("pointermove", move);
  window.addEventListener("pointerup", end);
  canvas.addEventListener("touchstart", start, { passive: false });
  canvas.addEventListener("touchmove", move, { passive: false });
  canvas.addEventListener("touchend", end);
}

function setUpPackSignatureCanvasSize() {
  const canvas = document.getElementById("pack-signature-canvas");
  canvas.width = canvas.clientWidth;
  canvas.height = canvas.clientHeight;
  packSigCtx = canvas.getContext("2d");
  packSigCtx.lineWidth = 2.5;
  packSigCtx.lineCap = "round";
  packSigCtx.strokeStyle = "#14171C";
}

function clearPackSignatureCanvas() {
  if (!packSigCtx) return;
  const canvas = document.getElementById("pack-signature-canvas");
  packSigCtx.clearRect(0, 0, canvas.width, canvas.height);
  packSigHasStroke = false;
  updatePackCompleteState();
}

function allPackItemsChecked() {
  const checkboxes = document.querySelectorAll("#pack-line-items input[type=\"checkbox\"]");
  if (checkboxes.length === 0) return false;
  return [...checkboxes].every((cb) => cb.checked);
}

function updatePackCompleteState() {
  const packedByFilled = document.getElementById("pack-packed-by-input").value.trim().length > 0;
  const btn = document.getElementById("btn-pack-complete");
  const hint = document.getElementById("pack-complete-hint");

  const ready = allPackItemsChecked() && packedByFilled && packSigHasStroke;
  btn.disabled = !ready;
  hint.textContent = ready
    ? "Ready to confirm packed and signed."
    : "Check off all items, enter your name, and sign to finish.";
}

async function submitPackCompletion() {
  const btn = document.getElementById("btn-pack-complete");
  btn.disabled = true;
  btn.textContent = "Submitting…";

  try {
    const canvas = document.getElementById("pack-signature-canvas");
    const signatureBlob = await new Promise((resolve) => canvas.toBlob(resolve, "image/png"));

    const formData = new FormData();
    formData.append("packed_by", document.getElementById("pack-packed-by-input").value.trim());
    formData.append("signature", signatureBlob, "packed_signature.png");

    const itemCheckboxes = document.querySelectorAll("#pack-line-items .pack-item-checkbox");
    if (itemCheckboxes.length > 0) {
      const checks = [...itemCheckboxes].sort((a, b) => a.dataset.index - b.dataset.index).map((cb) => cb.checked);
      formData.append("line_item_checks", JSON.stringify(checks));
    } else {
      formData.append("checkoff_confirmed", "true");
    }

    const resp = await fetch(`/api/schedule/${currentPackDelivery.id}/pack`, {
      method: "POST",
      credentials: "same-origin",
      body: formData,
    });
    const result = await resp.json();
    if (!resp.ok) throw new Error(result.error || `Failed with status ${resp.status}`);

    currentPackDelivery = null;
    show("screen-pack-done");
  } catch (e) {
    console.error("Pack completion failed", e);
    alert(`Couldn't complete packing: ${e.message}. Check your signal and try again — nothing has been lost.`);
    btn.disabled = false;
  } finally {
    btn.textContent = "Confirm Packed & Sign";
  }
}

function initPackDoneScreen() {
  document.getElementById("btn-pack-done-home").addEventListener("click", goHome);
}

// ---------- Sync ----------

async function syncAll() {
  const statusEl = document.getElementById("sync-status");
  const all = await dbGetAll();
  const pending = all.filter((d) => d.status === "completed" || d.status === "sync_failed");

  if (pending.length === 0) return;

  let succeeded = 0;
  let failed = 0;

  for (const delivery of pending) {
    statusEl.textContent = `Syncing ${succeeded + failed + 1} of ${pending.length}...`;
    try {
      await uploadDelivery(delivery);
      await dbDelete(delivery.id);
      succeeded++;
    } catch (e) {
      console.error("Sync failed for delivery", delivery.id, e);
      delivery.status = "sync_failed";
      await dbPut(delivery);
      failed++;
    }
  }

  statusEl.textContent = `Synced ${succeeded} of ${pending.length}${failed ? `, ${failed} failed (will retry)` : ""}.`;
  await refreshQueue();
}

async function uploadDelivery(delivery) {
  const formData = new FormData();

  const metadata = {
    delivery_id: delivery.id,
    driver: delivery.driver,
    completed_at: delivery.completed_at,
    photos: delivery.photos.map((p) => ({
      filename: p.filename,
      type: p.type,
      captured_at: p.captured_at,
    })),
  };
  formData.append("metadata", JSON.stringify(metadata));

  delivery.photos.forEach((p) => {
    formData.append(p.filename, p.blob, p.filename);
  });

  const resp = await fetch(UPLOAD_URL, { method: "POST", credentials: "same-origin", body: formData });
  if (!resp.ok) {
    throw new Error(`Upload failed with status ${resp.status}`);
  }
  return resp.json();
}

// ---------- Boot ----------

async function boot() {
  db = await openDB();
  initLoginScreen();
  initAdminLoginScreen();
  initHomeScreen();
  initCaptureScreen();
  initCompleteScreen();
  initIncomingCaptureScreen();
  initIncomingConfirmScreen();
  initIncomingFlagScreen();
  initIncomingDoneScreen();
  initScheduledTicketScreen();
  initScheduledDoneScreen();
  initStartDeliveryScreen();
  initRoleMenu();
  initPackScreen();
  initPackDoneScreen();

  try {
    const resp = await fetch(ME_URL, { credentials: "same-origin" });
    if (resp.ok) {
      const identity = await resp.json();
      cacheUser(identity);
      showRoleMenu();
    } else {
      // Explicitly not logged in (401) - clear any stale cache and require login.
      cacheUser(null);
      show("screen-login");
    }
  } catch (e) {
    // Network error (offline) - fall back to the last known session so the
    // app still works for capturing deliveries without signal. This is only
    // a convenience for an already-logged-in device; a first login still
    // requires being online.
    console.warn("Couldn't reach server to verify login (offline?). Using cached session if available.", e);
    const cached = getCachedUser();
    if (cached) {
      currentUser = cached;
      showRoleMenu();
    } else {
      show("screen-login");
    }
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("service-worker.js").catch((e) => console.warn("SW registration failed", e));
  }
}

boot();
