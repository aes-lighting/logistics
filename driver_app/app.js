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
const LOGIN_URL = "/api/auth/login";
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
  document.getElementById("btn-login").addEventListener("click", async () => {
    const email = document.getElementById("login-email-input").value.trim();
    const password = document.getElementById("login-password-input").value;
    const errorEl = document.getElementById("login-error");
    errorEl.classList.add("hidden");

    if (!email || !password) {
      errorEl.textContent = "Enter your email and password.";
      errorEl.classList.remove("hidden");
      return;
    }

    try {
      const resp = await fetch(LOGIN_URL, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email, password }),
      });
      const result = await resp.json();
      if (!resp.ok) {
        errorEl.textContent = result.error || "Login failed.";
        errorEl.classList.remove("hidden");
        return;
      }
      cacheUser({ role: result.role, name: result.name, email: result.email });
      showRoleMenu();
    } catch (e) {
      console.error("Login failed", e);
      errorEl.textContent = "Couldn't reach the server. Check your signal and try again.";
      errorEl.classList.remove("hidden");
    }
  });
}

async function logout() {
  try {
    await fetch(LOGOUT_URL, { method: "POST", credentials: "same-origin" });
  } catch (e) {
    console.warn("Logout request failed (probably offline) — clearing local session anyway.", e);
  }
  cacheUser(null);
  currentAppMode = null;
  document.getElementById("login-email-input").value = "";
  document.getElementById("login-password-input").value = "";
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
// A multi-step flow that requires being online throughout (like Start
// Delivery already does) — each step talks to the server immediately:
// scan page(s) -> confirm job/PO (auto-emails that job's PM) -> pallet
// count + one photo per pallet -> choose location(s), optionally split
// across several -> comment -> finalize (logs it and generates a
// printable QR code). There is no offline retry queue for this flow.

let incomingSessionId = null;
let incomingPageFiles = []; // local blobs, for thumbnail display only
let incomingJobGuess = null;
let incomingPoGuess = null;
let incomingPalletCount = 0;
let incomingPalletPhotoCount = 0;
let cachedLocations = null;
let cachedPms = null;

function startIncomingInventory() {
  incomingSessionId = null;
  incomingPageFiles = [];
  incomingJobGuess = null;
  incomingPoGuess = null;
  document.getElementById("incoming-thumb").innerHTML = "";
  document.getElementById("incoming-scanning-status").classList.add("hidden");
  document.getElementById("btn-incoming-done-scanning").disabled = true;
  show("screen-incoming-capture");
}

function initIncomingCaptureScreen() {
  document.getElementById("input-incoming").addEventListener("change", handleIncomingPage);
  document.getElementById("btn-cancel-incoming").addEventListener("click", () => {
    if (incomingPageFiles.length > 0 && !confirm("Discard this scan?")) return;
    goHome();
  });
  document.getElementById("btn-incoming-done-scanning").addEventListener("click", showIncomingConfirmScreen);
}

async function handleIncomingPage(fileInputEvent) {
  const file = fileInputEvent.target.files[0];
  if (!file) return;
  fileInputEvent.target.value = "";

  incomingPageFiles.push(file);
  const thumbContainer = document.getElementById("incoming-thumb");
  const img = document.createElement("img");
  img.className = "thumb";
  img.src = URL.createObjectURL(file);
  thumbContainer.appendChild(img);

  document.getElementById("incoming-scanning-status").classList.remove("hidden");
  document.getElementById("incoming-capture-btn-label").textContent = "Take Photo of Next Page";

  try {
    const formData = new FormData();
    formData.append("photo", file, "page.jpg");
    if (incomingSessionId) formData.append("session_id", incomingSessionId);

    const resp = await fetch("/api/incoming/scan_page", { method: "POST", credentials: "same-origin", body: formData });
    if (!resp.ok) throw new Error(`Scan failed with status ${resp.status}`);
    const result = await resp.json();

    incomingSessionId = result.session_id;
    if (result.job_number_guess) incomingJobGuess = result.job_number_guess;
    if (result.po_number_guess) incomingPoGuess = result.po_number_guess;

    document.getElementById("btn-incoming-done-scanning").disabled = false;
  } catch (e) {
    console.error("Scan page failed", e);
    alert("Couldn't reach the server to scan this page. Check your signal and try again.");
    incomingPageFiles.pop();
    thumbContainer.removeChild(thumbContainer.lastChild);
  } finally {
    document.getElementById("incoming-scanning-status").classList.add("hidden");
  }
}

function showIncomingConfirmScreen() {
  const thumbContainer = document.getElementById("confirm-thumbs");
  thumbContainer.innerHTML = "";
  incomingPageFiles.forEach((file) => {
    const img = document.createElement("img");
    img.className = "thumb";
    img.src = URL.createObjectURL(file);
    thumbContainer.appendChild(img);
  });

  const note = document.getElementById("ocr-guess-note");
  if (incomingJobGuess || incomingPoGuess) {
    note.textContent = "Detected from the slip — please confirm both are correct.";
    note.className = "ocr-note found";
  } else {
    note.textContent = "Nothing could be read automatically. Enter both manually, or flag this slip.";
    note.className = "ocr-note not-found";
  }
  document.getElementById("job-number-input").value = incomingJobGuess || "";
  document.getElementById("po-number-input").value = incomingPoGuess || "";
  document.getElementById("pm-picker-wrap").classList.add("hidden");

  show("screen-incoming-confirm");
}

async function loadPmPickerOptions() {
  const select = document.getElementById("pm-picker-select");
  if (!cachedPms) {
    try {
      const resp = await fetch("/api/inventory/pms", { credentials: "same-origin" });
      if (resp.ok) cachedPms = (await resp.json()).pms;
    } catch (e) {
      console.warn("Couldn't load PM list", e);
    }
  }
  if (!cachedPms) return;
  select.innerHTML = '<option value="">— Select a PM —</option>';
  cachedPms.forEach((pm) => {
    const opt = document.createElement("option");
    opt.value = pm.email;
    opt.textContent = `${pm.name} (${pm.email})`;
    select.appendChild(opt);
  });
}

function initIncomingConfirmScreen() {
  document.getElementById("btn-back-to-incoming-capture").addEventListener("click", () => show("screen-incoming-capture"));

  document.getElementById("btn-confirm-job").addEventListener("click", async () => {
    const jobNumber = document.getElementById("job-number-input").value.trim();
    const poNumber = document.getElementById("po-number-input").value.trim();
    const pmPickerVisible = !document.getElementById("pm-picker-wrap").classList.contains("hidden");
    const pmEmail = pmPickerVisible ? document.getElementById("pm-picker-select").value : "";

    if (!jobNumber) {
      alert("Enter a job number, or use Flag if this slip doesn't have one.");
      return;
    }
    if (pmPickerVisible && !pmEmail) {
      alert("Select which PM owns this job.");
      return;
    }

    try {
      const body = { session_id: incomingSessionId, job_number: jobNumber, po_number: poNumber, staff: getDriverName() };
      if (pmEmail) body.pm_email = pmEmail;

      const resp = await fetch("/api/incoming/confirm_job", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const result = await resp.json();

      if (!resp.ok) {
        if (result.error === "needs_pm") {
          document.getElementById("pm-picker-wrap").classList.remove("hidden");
          await loadPmPickerOptions();
          return;
        }
        throw new Error(result.error || `Failed with status ${resp.status}`);
      }

      incomingPalletCount = 0;
      incomingPalletPhotoCount = 0;
      document.getElementById("pallet-count-input").value = "";
      document.getElementById("pallet-photo-group").classList.add("hidden");
      document.getElementById("pallet-thumbs").innerHTML = "";
      document.getElementById("btn-pallets-continue").disabled = true;
      show("screen-incoming-pallets");
    } catch (e) {
      console.error("Confirm job failed", e);
      alert(`Couldn't confirm this job: ${e.message}. Check your signal and try again.`);
    }
  });

  document.getElementById("btn-open-flag").addEventListener("click", () => {
    document.getElementById("flag-reason-select").value = "Missing job number";
    document.getElementById("flag-note-input").value = "";
    show("screen-incoming-flag");
  });
}

// ---------- Pallets ----------

function initIncomingPalletsScreen() {
  document.getElementById("btn-pallets-back").addEventListener("click", () => {
    if (!confirm("Discard progress on this shipment?")) return;
    goHome();
  });

  document.getElementById("btn-set-pallet-count").addEventListener("click", () => {
    const count = parseInt(document.getElementById("pallet-count-input").value, 10);
    if (!count || count < 1) {
      alert("Enter a valid pallet count (1 or more).");
      return;
    }
    incomingPalletCount = count;
    incomingPalletPhotoCount = 0;
    document.getElementById("pallet-thumbs").innerHTML = "";
    document.getElementById("pallet-photo-group").classList.remove("hidden");
    document.getElementById("pallet-progress-hint").textContent = `0 of ${count} pallets photographed.`;
    document.getElementById("pallet-capture-btn-label").textContent = `Take Photo of Pallet 1`;
    document.getElementById("btn-pallets-continue").disabled = true;
  });

  document.getElementById("input-pallet-photo").addEventListener("change", async (e) => {
    const file = e.target.files[0];
    e.target.value = "";
    if (!file) return;

    try {
      const formData = new FormData();
      formData.append("session_id", incomingSessionId);
      formData.append("photo", file, "pallet.jpg");
      const resp = await fetch("/api/incoming/pallet_photo", { method: "POST", credentials: "same-origin", body: formData });
      if (!resp.ok) throw new Error(`Failed with status ${resp.status}`);

      incomingPalletPhotoCount++;
      const img = document.createElement("img");
      img.className = "thumb";
      img.src = URL.createObjectURL(file);
      document.getElementById("pallet-thumbs").appendChild(img);

      const hint = document.getElementById("pallet-progress-hint");
      if (incomingPalletPhotoCount >= incomingPalletCount) {
        hint.textContent = `All ${incomingPalletCount} pallet(s) photographed.`;
        document.getElementById("pallet-photo-group").classList.add("hidden");
        document.getElementById("btn-pallets-continue").disabled = false;
      } else {
        hint.textContent = `${incomingPalletPhotoCount} of ${incomingPalletCount} pallets photographed.`;
        document.getElementById("pallet-capture-btn-label").textContent = `Take Photo of Pallet ${incomingPalletPhotoCount + 1}`;
      }
    } catch (e) {
      console.error("Pallet photo failed", e);
      alert(`Couldn't upload that pallet photo: ${e.message}. Check your signal and try again.`);
    }
  });

  document.getElementById("btn-pallets-continue").addEventListener("click", () => {
    document.getElementById("location-rows").innerHTML = "";
    document.getElementById("incoming-comment-input").value = "";
    addLocationRow(true);
    show("screen-incoming-locations");
  });
}

// ---------- Locations + comment + finalize ----------

async function ensureLocationsLoaded() {
  if (cachedLocations) return;
  try {
    const resp = await fetch("/api/inventory/locations", { credentials: "same-origin" });
    if (resp.ok) cachedLocations = (await resp.json()).locations;
  } catch (e) {
    console.warn("Couldn't load locations list", e);
  }
}

async function addLocationRow(isFirst = false) {
  await ensureLocationsLoaded();
  const container = document.getElementById("location-rows");
  const row = document.createElement("div");
  row.className = "line-item-row";

  const select = document.createElement("select");
  select.className = "job-number-input location-row-select";
  select.innerHTML = '<option value="">— Location —</option>' + (cachedLocations || []).map((l) => `<option value="${l}">${l}</option>`).join("");

  const countInput = document.createElement("input");
  countInput.type = "number";
  countInput.min = "1";
  countInput.className = "job-number-input qty-input location-row-count";
  countInput.placeholder = "Count";
  if (isFirst) countInput.value = incomingPalletCount;

  row.appendChild(select);
  row.appendChild(countInput);

  if (!isFirst) {
    const removeBtn = document.createElement("button");
    removeBtn.type = "button";
    removeBtn.className = "line-item-remove";
    removeBtn.textContent = "\u00d7";
    removeBtn.addEventListener("click", () => {
      row.remove();
      updateLocationTotal();
    });
    row.appendChild(removeBtn);
  }

  select.addEventListener("change", updateLocationTotal);
  countInput.addEventListener("input", updateLocationTotal);

  container.appendChild(row);
  updateLocationTotal();
}

function updateLocationTotal() {
  const rows = [...document.querySelectorAll("#location-rows .line-item-row")];
  const total = rows.reduce((sum, row) => sum + (parseInt(row.querySelector(".location-row-count").value, 10) || 0), 0);
  const hint = document.getElementById("location-total-hint");
  const finalizeHint = document.getElementById("finalize-hint");
  const btn = document.getElementById("btn-finalize-incoming");

  const allLocationsPicked = rows.every((row) => row.querySelector(".location-row-select").value);
  const matches = total === incomingPalletCount && allLocationsPicked && rows.length > 0;

  hint.textContent = `${total} of ${incomingPalletCount} pallets assigned to a location.`;
  finalizeHint.textContent = matches ? "Ready to finish." : "Location counts must add up to the pallet count.";
  btn.disabled = !matches;
}

function initIncomingLocationsScreen() {
  document.getElementById("btn-locations-back").addEventListener("click", () => {
    if (!confirm("Discard progress on this shipment?")) return;
    goHome();
  });

  document.getElementById("btn-add-location-row").addEventListener("click", () => addLocationRow(false));

  document.getElementById("btn-finalize-incoming").addEventListener("click", async () => {
    const rows = [...document.querySelectorAll("#location-rows .line-item-row")];
    const locations = rows.map((row) => ({
      location: row.querySelector(".location-row-select").value,
      count: parseInt(row.querySelector(".location-row-count").value, 10),
    }));
    const comment = document.getElementById("incoming-comment-input").value.trim();

    try {
      const resp = await fetch("/api/incoming/finalize", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: incomingSessionId, pallet_count: incomingPalletCount, locations, comment }),
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result.error || `Failed with status ${resp.status}`);

      document.getElementById("incoming-done-sub").textContent =
        `Logged and the PM has been emailed. ${incomingPalletCount} pallet(s) recorded.`;
      const printBtn = document.getElementById("btn-print-qr");
      printBtn.classList.remove("hidden");
      printBtn.onclick = () => window.open(result.qr_pdf_url, "_blank");

      show("screen-incoming-done");
    } catch (e) {
      console.error("Finalize failed", e);
      alert(`Couldn't finish this shipment: ${e.message}. Check your signal and try again.`);
    }
  });
}

// ---------- Flag ----------

function initIncomingFlagScreen() {
  document.getElementById("btn-back-to-confirm").addEventListener("click", () => show("screen-incoming-confirm"));

  document.getElementById("btn-submit-flag").addEventListener("click", async () => {
    const reason = document.getElementById("flag-reason-select").value;
    const note = document.getElementById("flag-note-input").value.trim();

    try {
      const resp = await fetch("/api/incoming/flag", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: incomingSessionId, reason, note, staff: getDriverName() }),
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result.error || `Failed with status ${resp.status}`);

      document.getElementById("incoming-done-stamp").textContent = "FLAGGED";
      document.getElementById("incoming-done-sub").textContent = result.email_sent
        ? "The PM team has been emailed about this slip."
        : "Saved, but the alert email could not be sent — let the PM team know directly.";
      document.getElementById("btn-print-qr").classList.add("hidden");
      show("screen-incoming-done");
    } catch (e) {
      console.error("Flag failed", e);
      alert(`Couldn't submit this flag: ${e.message}. Check your signal and try again.`);
    }
  });
}

function initIncomingDoneScreen() {
  document.getElementById("btn-incoming-done-home").addEventListener("click", () => {
    document.getElementById("incoming-done-stamp").textContent = "LOGGED";
    goHome();
  });
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
      div.className = "pack-list-item";
      div.innerHTML = `
        <div class="queue-item-id">Job #${d.job_number} &mdash; ${d.delivery_date}${d.revision_count ? ` <span class="hint-inline">(rev. ${d.revision_count})</span>` : ""}</div>
        <div class="queue-item-meta">${d.receiver_name}</div>
        <div class="pack-list-actions">
          <button class="btn btn-secondary btn-compact revise-btn">Revise Ticket</button>
          <button class="btn btn-secondary btn-compact sendpm-btn">Send to PM</button>
          <button class="btn btn-primary btn-compact pack-btn">Pack / Check Inventory</button>
        </div>
      `;
      div.querySelector(".revise-btn").addEventListener("click", () => openReviseScreen(d));
      div.querySelector(".sendpm-btn").addEventListener("click", () => openSendToPmScreen(d));
      div.querySelector(".pack-btn").addEventListener("click", () => openPackScreen(d));
      listEl.appendChild(div);
    });
  } catch (e) {
    console.error("Failed to load ready-to-pack list", e);
    listEl.innerHTML = '<div class="queue-empty">Couldn\'t load — check your signal.</div>';
    countEl.textContent = "0";
  }
}

// ---------- Revise Ticket ----------

let reviseTargetId = null;
let reviseLineItemRowCount = 0;

function addReviseLineItemRow(item = {}) {
  const container = document.getElementById("revise-line-items");
  const row = document.createElement("div");
  row.className = "line-item-card";
  row.id = `revise-item-${reviseLineItemRowCount++}`;
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

function openReviseScreen(delivery) {
  reviseTargetId = delivery.id;
  document.getElementById("revise-job-number").textContent = delivery.job_number;
  document.getElementById("revise-line-items").innerHTML = "";
  document.getElementById("revise-status").textContent = "";
  const items = delivery.line_items && delivery.line_items.length ? delivery.line_items : [{}];
  items.forEach((item) => addReviseLineItemRow(item));
  show("screen-revise-ticket");
}

function initReviseScreen() {
  document.getElementById("btn-revise-back").addEventListener("click", goHome);
  document.getElementById("btn-revise-add-row").addEventListener("click", () => addReviseLineItemRow());

  document.getElementById("btn-revise-submit").addEventListener("click", async () => {
    const statusEl = document.getElementById("revise-status");
    const cards = [...document.querySelectorAll("#revise-line-items .line-item-card")];
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
      statusEl.className = "status-line-driver err";
      return;
    }

    try {
      const resp = await fetch(`/api/schedule/${reviseTargetId}/revise_ticket`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ line_items: lineItems }),
      });
      const result = await resp.json();
      if (!resp.ok) throw new Error(result.error || `Failed with status ${resp.status}`);

      statusEl.textContent = result.reset_to_pack
        ? "Saved — this was already packed, so it's back in Ready to Pack for re-verification. PM and warehouse notified."
        : "Saved — the PM and warehouse team have been notified.";
      statusEl.className = "status-line-driver ok";
      setTimeout(goHome, result.reset_to_pack ? 1600 : 900);
    } catch (e) {
      console.error("Revise ticket failed", e);
      statusEl.textContent = `Couldn't save: ${e.message}`;
      statusEl.className = "status-line-driver err";
    }
  });
}

// ---------- Send to PM ----------

let sendPmTargetId = null;

async function openSendToPmScreen(delivery) {
  sendPmTargetId = delivery.id;
  document.getElementById("sendpm-job-number").textContent = delivery.job_number;
  document.getElementById("sendpm-status").textContent = "";

  const select = document.getElementById("sendpm-select");
  select.innerHTML = '<option value="">— Select a PM —</option>';
  try {
    const resp = await fetch("/api/inventory/pms", { credentials: "same-origin" });
    if (resp.ok) {
      const result = await resp.json();
      result.pms.forEach((pm) => {
        const opt = document.createElement("option");
        opt.value = pm.email;
        opt.textContent = `${pm.name} (${pm.email})`;
        select.appendChild(opt);
      });
    }
  } catch (e) {
    console.warn("Couldn't load PM list", e);
  }

  show("screen-send-to-pm");
}

function initSendToPmScreen() {
  document.getElementById("btn-sendpm-back").addEventListener("click", goHome);

  document.getElementById("btn-sendpm-submit").addEventListener("click", async () => {
    const pmEmail = document.getElementById("sendpm-select").value;
    const statusEl = document.getElementById("sendpm-status");
    if (!pmEmail) {
      statusEl.textContent = "Select a PM first.";
      statusEl.className = "status-line-driver err";
      return;
    }
    try {
      const resp = await fetch(`/api/schedule/${sendPmTargetId}/send_to_pm`, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ pm_email: pmEmail }),
      });
      const result = await resp.json();
      if (!resp.ok || !result.sent) throw new Error(result.error || "Send failed");

      statusEl.textContent = "Sent.";
      statusEl.className = "status-line-driver ok";
      setTimeout(goHome, 800);
    } catch (e) {
      console.error("Send to PM failed", e);
      statusEl.textContent = `Couldn't send: ${e.message}`;
      statusEl.className = "status-line-driver err";
    }
  });
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
  initHomeScreen();
  initCaptureScreen();
  initCompleteScreen();
  initIncomingCaptureScreen();
  initIncomingConfirmScreen();
  initIncomingPalletsScreen();
  initIncomingLocationsScreen();
  initIncomingFlagScreen();
  initIncomingDoneScreen();
  initScheduledTicketScreen();
  initScheduledDoneScreen();
  initStartDeliveryScreen();
  initRoleMenu();
  initPackScreen();
  initPackDoneScreen();
  initReviseScreen();
  initSendToPmScreen();

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
