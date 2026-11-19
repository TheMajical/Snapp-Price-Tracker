// Snapp Price Tracker - Modern Frontend Controller v2.1

let hourlyChartInstance = null;
let dateComparisonChartInstance = null;
let leafletMap = null;
let homeMarker = null;
let workMarker = null;
let altMarkers = [];

let activeDirection = "home_to_work"; // "home_to_work" | "work_to_home" | "all"
let activeComparisonServiceId = "1";
let currentTableSort = { column: "time", order: "desc" };

let currentConfig = {
  routes: {
    home: { name: "خانه", lat: 35.7007, lng: 51.3950 },
    work: { name: "محل کار اصلی", lat: 35.7575, lng: 51.4100 },
    work_alternatives: []
  }
};

// Set Chart.js Defaults for Clean Persian Typography safely
try {
  if (window.Chart && Chart.defaults && Chart.defaults.font) {
    Chart.defaults.font.family = "'Vazirmatn', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif";
    Chart.defaults.font.size = 12;
    Chart.defaults.color = "#94a3b8";
  }
} catch (e) {
  console.warn("Chart.js font initialization notice:", e);
}

document.addEventListener("DOMContentLoaded", () => {
  initMap();
  loadStatus();
  loadConfig();
  checkLocalStorageLocations();
  loadDistinctDates();
  loadHourlyChart();
  loadDateComparisonChart();
  loadRecentTable();
  loadOriginsComparison();
  updateExportLinks();

  // Poll status periodically every 30 seconds
  setInterval(() => {
    loadStatus();
    loadOriginsComparison();
  }, 30000);
});

// Toast Utility
function showToast(message, isError = false) {
  const toast = document.getElementById("toast");
  if (!toast) return;
  toast.innerText = message;
  toast.className = "toast active" + (isError ? " error" : "");
  setTimeout(() => {
    toast.className = "toast";
  }, 4000);
}

// Modal Handlers
function openModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.add("active");
}

function closeModal(id) {
  const modal = document.getElementById(id);
  if (modal) modal.classList.remove("active");
}

function copySnippet(text) {
  navigator.clipboard.writeText(text).then(() => {
    showToast("دستور با موفقیت کپی شد!");
  });
}

// --- Direction Switcher (Morning / Evening / All) ---
function setActiveDirection(dir) {
  activeDirection = dir;

  const btnHw = document.getElementById("dir-btn-home-work");
  const btnWh = document.getElementById("dir-btn-work-home");
  const btnAll = document.getElementById("dir-btn-all");

  if (btnHw) btnHw.classList.remove("active");
  if (btnWh) btnWh.classList.remove("active");
  if (btnAll) btnAll.classList.remove("active");

  const morningCard = document.getElementById("morning-route-card");
  const eveningCard = document.getElementById("evening-route-card");
  const originsSection = document.getElementById("origins-comparison-section");
  const hourlyRouteSelect = document.getElementById("hourly-route-select");
  const dateRouteSelect = document.getElementById("date-chart-route-select");
  const tableRouteFilter = document.getElementById("table-route-filter");
  const focusText = document.getElementById("direction-focus-text");

  if (dir === "home_to_work") {
    if (btnHw) btnHw.classList.add("active");
    if (focusText) focusText.innerText = "نمای متمرکز: مسیر رفت به سرکار (صبح)";
    
    // Show only morning card (full width focus)
    if (morningCard) {
      morningCard.classList.remove("hide-direction");
      morningCard.classList.add("direction-expanded");
    }
    if (eveningCard) {
      eveningCard.classList.add("hide-direction");
      eveningCard.classList.remove("direction-expanded");
    }
    // Origin comparison is for returning from work -> hide in morning mode
    if (originsSection) originsSection.classList.add("hide-direction");

    if (hourlyRouteSelect) hourlyRouteSelect.value = "home_to_work";
    if (dateRouteSelect) dateRouteSelect.value = "home_to_work";
    if (tableRouteFilter) tableRouteFilter.value = "home_to_work";

  } else if (dir === "work_to_home") {
    if (btnWh) btnWh.classList.add("active");
    if (focusText) focusText.innerText = "نمای متمرکز: مسیر برگشت به خانه و مقایسه نقاط اطراف (عصر)";

    // Show evening card & comparison section prominently
    if (morningCard) {
      morningCard.classList.add("hide-direction");
      morningCard.classList.remove("direction-expanded");
    }
    if (eveningCard) {
      eveningCard.classList.remove("hide-direction");
      eveningCard.classList.add("direction-expanded");
    }
    if (originsSection) originsSection.classList.remove("hide-direction");

    if (hourlyRouteSelect) hourlyRouteSelect.value = "work_to_home";
    if (dateRouteSelect) dateRouteSelect.value = "work_to_home";
    if (tableRouteFilter) tableRouteFilter.value = "work_to_home";

  } else {
    if (btnAll) btnAll.classList.add("active");
    if (focusText) focusText.innerText = "نمای جامع: پایش هر دو مسیر و تمام نقاط اطراف هم‌زمان";

    // Show both cards
    if (morningCard) {
      morningCard.classList.remove("hide-direction", "direction-expanded");
    }
    if (eveningCard) {
      eveningCard.classList.remove("hide-direction", "direction-expanded");
    }
    if (originsSection) originsSection.classList.remove("hide-direction");

    if (hourlyRouteSelect) hourlyRouteSelect.value = "all";
    if (tableRouteFilter) tableRouteFilter.value = "all";
  }

  loadHourlyChart();
  loadDateComparisonChart();
  loadRecentTable();
  updateExportLinks();
}

function updateExportLinks() {
  const routeParam = activeDirection === "all" ? "all" : activeDirection;
  const sortParam = `${currentTableSort.column}_${currentTableSort.order}`;
  const csvBtn = document.getElementById("btn-export-csv");
  const jsonBtn = document.getElementById("btn-export-json");
  if (csvBtn) csvBtn.href = `/api/export?format=csv&route=${routeParam}&sort_by=${sortParam}`;
  if (jsonBtn) jsonBtn.href = `/api/export?format=json&route=${routeParam}&sort_by=${sortParam}`;
}

// --- LocalStorage Location Backup & Sync ---
function saveRoutesToLocalStorage(routes) {
  try {
    localStorage.setItem("snapp_saved_routes", JSON.stringify(routes));
  } catch (e) {
    console.warn("Could not save routes to localStorage:", e);
  }
}

function checkLocalStorageLocations() {
  try {
    const saved = localStorage.getItem("snapp_saved_routes");
    if (!saved) return;
    const routes = JSON.parse(saved);
    if (!routes || !routes.home || !routes.work) return;

    // Check if current server routes differ from saved
    const serverHome = currentConfig.routes?.home || {};
    const isDefault = (serverHome.lat === 35.7007 && serverHome.lng === 51.3950);
    const hasAlternatives = (routes.work_alternatives && routes.work_alternatives.length > 0);

    if (isDefault && (routes.home.lat !== 35.7007 || hasAlternatives)) {
      const container = document.getElementById("restore-banner-container");
      if (container) {
        container.innerHTML = `
          <div class="restore-banner">
            <div class="restore-banner-content">
              <i class="fa-solid fa-cloud-arrow-down" style="color: #38bdf8; font-size: 18px;"></i>
              <div>
                <strong>لوکیشن‌های قبلی شما در این مرورگر موجود است:</strong>
                <span>خانه، محل کار و ${routes.work_alternatives ? routes.work_alternatives.length : 0} نقطه جایگزین</span>
              </div>
            </div>
            <div>
              <button class="btn btn-sm btn-primary" onclick="restoreFromLocalStorage()">
                <i class="fa-solid fa-rotate-left"></i> بازیابی خودکار با ۱ کلیک
              </button>
            </div>
          </div>
        `;
      }
    }
  } catch (e) {
    console.error("Error checking localStorage locations:", e);
  }
}

async function restoreFromLocalStorage() {
  try {
    const saved = localStorage.getItem("snapp_saved_routes");
    if (!saved) return;
    const routes = JSON.parse(saved);

    const res = await fetch("/api/locations/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ routes: routes })
    });
    const data = await res.json();
    if (data.success) {
      showToast("لوکیشن‌های شما با موفقیت بازیابی شدند!");
      const container = document.getElementById("restore-banner-container");
      if (container) container.innerHTML = "";
      loadConfig();
    }
  } catch (e) {
    showToast("خطا در بازیابی: " + e, true);
  }
}

function exportLocationsBackup() {
  window.location.href = "/api/locations/export";
  showToast("فایل پشتیبان لوکیشن‌ها دریافت شد.");
}

function triggerImportLocations() {
  const fileInput = document.getElementById("locations-import-file");
  if (fileInput) fileInput.click();
}

async function handleLocationsFileSelect(event) {
  const file = event.target.files[0];
  if (!file) return;

  try {
    const text = await file.text();
    const parsed = JSON.parse(text);
    const routes = parsed.routes || parsed;

    if (!routes.home || !routes.work) {
      showToast("فرمت فایل نامعتبر است: اطلاعات خانه و کار یافت نشد.", true);
      return;
    }

    const res = await fetch("/api/locations/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ routes: routes })
    });
    const data = await res.json();
    if (data.success) {
      saveRoutesToLocalStorage(routes);
      showToast("لوکیشن‌ها با موفقیت از فایل بارگذاری و ذخیره شدند!");
      loadConfig();
    } else {
      showToast("خطا در بارگذاری: " + (data.detail || "نامشخص"), true);
    }
  } catch (e) {
    showToast("خطا در خواندن فایل JSON: " + e, true);
  }
}

// --- Initialize Leaflet Map ---
function initMap() {
  const defaultHome = [35.7007, 51.3950];
  const defaultWork = [35.7575, 51.4100];

  leafletMap = L.map("map").setView(defaultHome, 12);

  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: "© OpenStreetMap"
  }).addTo(leafletMap);

  const homeIcon = L.divIcon({
    className: "custom-map-icon home-icon",
    html: '<div style="background-color: #22c55e; color: white; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 10px rgba(34,197,94,0.6);"><i class="fa-solid fa-house"></i></div>',
    iconSize: [32, 32],
    iconAnchor: [16, 16]
  });

  const workIcon = L.divIcon({
    className: "custom-map-icon work-icon",
    html: '<div style="background-color: #3b82f6; color: white; width: 32px; height: 32px; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 10px rgba(59,130,246,0.6);"><i class="fa-solid fa-briefcase"></i></div>',
    iconSize: [32, 32],
    iconAnchor: [16, 16]
  });

  homeMarker = L.marker(defaultHome, { draggable: true, icon: homeIcon }).addTo(leafletMap);
  workMarker = L.marker(defaultWork, { draggable: true, icon: workIcon }).addTo(leafletMap);

  homeMarker.bindPopup("<b>موقعیت خانه (Home)</b><br>سنجاق را بکشید تا جابجا شود.");
  workMarker.bindPopup("<b>موقعیت محل کار (Work)</b><br>سنجاق را بکشید تا جابجا شود.");

  homeMarker.on("dragend", updateCoordsDisplay);
  workMarker.on("dragend", updateCoordsDisplay);

  updateCoordsDisplay();
}

function updateCoordsDisplay() {
  if (!homeMarker || !workMarker) return;
  const h = homeMarker.getLatLng();
  const w = workMarker.getLatLng();

  const mapHomeEl = document.getElementById("map-home-coords");
  const mapWorkEl = document.getElementById("map-work-coords");
  if (mapHomeEl) mapHomeEl.innerText = `${h.lat.toFixed(4)}, ${h.lng.toFixed(4)}`;
  if (mapWorkEl) mapWorkEl.innerText = `${w.lat.toFixed(4)}, ${w.lng.toFixed(4)}`;

  const cfgHLat = document.getElementById("cfg-home-lat");
  const cfgHLng = document.getElementById("cfg-home-lng");
  const cfgWLat = document.getElementById("cfg-work-lat");
  const cfgWLng = document.getElementById("cfg-work-lng");

  if (cfgHLat) cfgHLat.value = h.lat.toFixed(5);
  if (cfgHLng) cfgHLng.value = h.lng.toFixed(5);
  if (cfgWLat) cfgWLat.value = w.lat.toFixed(5);
  if (cfgWLng) cfgWLng.value = w.lng.toFixed(5);
}

function getAltIcon(index) {
  return L.divIcon({
    className: "custom-map-icon alt-icon",
    html: `<div style="background-color: #f59e0b; color: white; width: 30px; height: 30px; border-radius: 50%; display: flex; align-items: center; justify-content: center; box-shadow: 0 0 10px rgba(245,158,11,0.7); font-weight: bold; font-size: 13px;"><i class="fa-solid fa-person-walking"></i></div>`,
    iconSize: [30, 30],
    iconAnchor: [15, 15]
  });
}

function renderAltMarkers() {
  if (!leafletMap) return;

  altMarkers.forEach(m => leafletMap.removeLayer(m));
  altMarkers = [];

  const alternatives = currentConfig.routes?.work_alternatives || [];
  const countEl = document.getElementById("map-alt-count");
  if (countEl) countEl.innerText = `${alternatives.length} نقطه`;

  alternatives.forEach((alt, idx) => {
    const lat = alt.lat || (currentConfig.routes.work.lat + (idx + 1) * 0.002);
    const lng = alt.lng || (currentConfig.routes.work.lng + (idx + 1) * 0.002);

    const marker = L.marker([lat, lng], {
      draggable: true,
      icon: getAltIcon(idx + 1)
    }).addTo(leafletMap);

    marker.bindPopup(`<b>${alt.name || `نقطه ${idx + 1} اطراف کار`}</b><br>سنجاق را بکشید تا تغییر مکان دهد.`);

    marker.on("dragend", () => {
      const pos = marker.getLatLng();
      alt.lat = parseFloat(pos.lat.toFixed(5));
      alt.lng = parseFloat(pos.lng.toFixed(5));
      renderAltPointsList();
      saveCoordinatesFromMap();
    });

    altMarkers.push(marker);
  });

  renderAltPointsList();
}

function calculateHaversineMeters(lat1, lon1, lat2, lon2) {
  const R = 6371000;
  const toRad = deg => (deg * Math.PI) / 180;
  const dLat = toRad(lat2 - lat1);
  const dLon = toRad(lon2 - lon1);
  const a = Math.sin(dLat / 2) * Math.sin(dLat / 2) +
            Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) *
            Math.sin(dLon / 2) * Math.sin(dLon / 2);
  const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
  return Math.round(R * c);
}

function renderAltPointsList() {
  const container = document.getElementById("alt-points-list-container");
  if (!container) return;

  const alternatives = currentConfig.routes?.work_alternatives || [];
  if (alternatives.length === 0) {
    container.innerHTML = `
      <div style="color: var(--text-dim); font-size: 13px; padding: 12px 0; text-align: center;">
        <i class="fa-solid fa-circle-info"></i> هنوز نقطه جایگزینی اطراف محل کار ثبت نشده است. با دکمه <strong>«+ افزودن نقطه جدید اطراف کار روی نقشه»</strong> می‌توانید نقاطی مانند سر خیابان اصلی، خروجی مترو یا تقاطع‌ها را برای مقایسه اضافه کنید.
      </div>`;
    return;
  }

  const workLat = currentConfig.routes?.work?.lat || 35.7575;
  const workLng = currentConfig.routes?.work?.lng || 51.4100;

  let html = '';
  alternatives.forEach((alt, idx) => {
    const distMeters = calculateHaversineMeters(workLat, workLng, alt.lat, alt.lng);
    html += `
      <div class="alt-point-row">
        <div class="alt-point-info">
          <span style="background-color: #f59e0b; color: white; width: 24px; height: 24px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 11px; font-weight: bold;">
            ${idx + 1}
          </span>
          <input type="text" class="alt-point-name-input" value="${alt.name || ''}" 
                 onchange="updateAltPointName('${alt.id}', this.value)" 
                 placeholder="نام این نقطه (مثلاً: خروجی مترو)">
          <span class="alt-point-coords">${alt.lat.toFixed(4)}, ${alt.lng.toFixed(4)}</span>
          <span style="font-size: 12px; color: var(--text-dim);">(${distMeters.toLocaleString('fa-IR')} متر پیاده‌روی تا کار اصلی)</span>
        </div>
        <div>
          <button class="btn btn-sm btn-ghost" style="color: #ef4444;" onclick="removeWorkAltMarker('${alt.id}')" title="حذف این نقطه">
            <i class="fa-solid fa-trash"></i> حذف
          </button>
        </div>
      </div>
    `;
  });
  container.innerHTML = html;
}

function addNewWorkAltMarker() {
  if (!currentConfig.routes) currentConfig.routes = {};
  if (!currentConfig.routes.work_alternatives) currentConfig.routes.work_alternatives = [];

  const alternatives = currentConfig.routes.work_alternatives;
  const newIdx = alternatives.length + 1;
  const workLat = currentConfig.routes.work?.lat || 35.7575;
  const workLng = currentConfig.routes.work?.lng || 51.4100;

  const angle = (newIdx * 1.6) % (2 * Math.PI);
  const offsetLat = Math.sin(angle) * 0.0022;
  const offsetLng = Math.cos(angle) * 0.0025;

  const newAlt = {
    id: `alt_${Date.now()}`,
    name: `نقطه ${newIdx} اطراف کار`,
    lat: parseFloat((workLat + offsetLat).toFixed(5)),
    lng: parseFloat((workLng + offsetLng).toFixed(5)),
    enabled: true
  };

  alternatives.push(newAlt);
  renderAltMarkers();
  updateRouteSelectDropdown();
  saveCoordinatesFromMap();
  showToast(`نقطه جدید (${newAlt.name}) اضافه شد. سنجاق نارنجی را روی نقشه جابجا کنید.`);
}

function removeWorkAltMarker(id) {
  if (!currentConfig.routes?.work_alternatives) return;
  currentConfig.routes.work_alternatives = currentConfig.routes.work_alternatives.filter(a => a.id !== id);
  renderAltMarkers();
  updateRouteSelectDropdown();
  saveCoordinatesFromMap();
  showToast("نقطه با موفقیت حذف شد.");
}

function updateAltPointName(id, newName) {
  const alt = currentConfig.routes?.work_alternatives?.find(a => a.id === id);
  if (alt && newName.trim()) {
    alt.name = newName.trim();
    updateRouteSelectDropdown();
    saveCoordinatesFromMap();
  }
}

function saveCoordinatesFromMap() {
  const h = homeMarker.getLatLng();
  const w = workMarker.getLatLng();

  currentConfig.routes.home.lat = parseFloat(h.lat.toFixed(5));
  currentConfig.routes.home.lng = parseFloat(h.lng.toFixed(5));
  currentConfig.routes.work.lat = parseFloat(w.lat.toFixed(5));
  currentConfig.routes.work.lng = parseFloat(w.lng.toFixed(5));

  saveRoutesToLocalStorage(currentConfig.routes);

  fetch("/api/config", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ routes: currentConfig.routes })
  })
  .then(res => res.json())
  .then(data => {
    if (data.success) {
      showToast("مختصات جدید با موفقیت ذخیره شد.");
      loadOriginsComparison();
    }
  })
  .catch(err => showToast("خطا در ذخیره مختصات: " + err, true));
}

// --- Load Application Status ---
async function loadStatus() {
  try {
    const res = await fetch("/api/status");
    const data = await res.json();

    const badge = document.getElementById("token-status-badge");
    if (data.has_access_token) {
      badge.innerHTML = '<span class="status-dot success"></span> <span>توکن فعال و معتبر</span>';
    } else {
      badge.innerHTML = '<span class="status-dot warning"></span> <span>توکن تنظیم نشده است</span>';
    }

    if (data.server_time) {
      const parts = data.server_time.split(" ");
      document.getElementById("server-time-text").innerText = parts[1] || data.server_time;
    }

    const secEl = document.getElementById("stat-security-status");
    if (secEl) {
      if (data.is_password_protected) {
        secEl.innerHTML = '<span class="text-success"><i class="fa-solid fa-lock"></i> دارای رمز عبور</span>';
      } else {
        secEl.innerHTML = '<span style="color: var(--accent-morning);"><i class="fa-solid fa-lock-open"></i> عمومی (بدون رمز)</span>';
      }
    }

    const sStatus = data.scheduler_status;
    document.getElementById("stat-total-records").innerText = (sStatus.total_checks || 0).toLocaleString("fa-IR") + " استعلام";
    
    if (sStatus.last_check) {
      document.getElementById("stat-last-poll").innerText = sStatus.last_check;
    }

    if (sStatus.status === "error") {
      document.getElementById("stat-scheduler-status").innerHTML = `<span class="danger">خطا: ${sStatus.last_error || 'نامشخص'}</span>`;
    } else {
      document.getElementById("stat-scheduler-status").innerHTML = `<span class="text-success">فعال (پایش خودکار هر ۱۰ دقیقه)</span>`;
    }
  } catch (e) {
    console.error("Error loading status:", e);
  }
}

// --- Load Configuration ---
async function loadConfig() {
  try {
    const res = await fetch("/api/config");
    currentConfig = await res.json();

    const home = currentConfig.routes?.home || {};
    const work = currentConfig.routes?.work || {};

    if (homeMarker && home.lat && home.lng) {
      homeMarker.setLatLng([home.lat, home.lng]);
    }
    if (workMarker && work.lat && work.lng) {
      workMarker.setLatLng([work.lat, work.lng]);
    }
    updateCoordsDisplay();

    renderAltMarkers();
    updateRouteSelectDropdown();
    loadOriginsComparison();

    const c = currentConfig.schedules?.continuous_24_7 || currentConfig.schedules?.morning || {};
    const intervalEl = document.getElementById("cfg-247-interval");
    if (intervalEl) {
      intervalEl.value = c.interval_minutes || 10;
    }
  } catch (err) {
    console.error("Failed to load config:", err);
  }
}

function updateRouteSelectDropdown() {
  const select = document.getElementById("hourly-route-select");
  if (!select) return;
  const currentVal = select.value;
  select.innerHTML = `
    <option value="home_to_work">خانه به کار</option>
    <option value="work_to_home">کار اصلی به خانه</option>
  `;
  const alternatives = currentConfig.routes?.work_alternatives || [];
  alternatives.forEach(alt => {
    const opt = document.createElement("option");
    opt.value = `work_alt_${alt.id}_to_home`;
    opt.innerText = `${alt.name || alt.id} به خانه`;
    select.appendChild(opt);
  });
  const allOpt = document.createElement("option");
  allOpt.value = "all";
  allOpt.innerText = "همه مسیرها";
  select.appendChild(allOpt);

  if (currentVal && Array.from(select.options).some(o => o.value === currentVal)) {
    select.value = currentVal;
  }
}

// --- Origin Comparison Section (Work vs Alternatives) ---
function switchComparisonService(serviceId) {
  activeComparisonServiceId = String(serviceId);

  // Update Active Tab Styling
  const tabCards = document.querySelectorAll(".service-tab-card");
  tabCards.forEach(t => t.classList.remove("active"));
  const activeCard = document.getElementById(`srv-tab-${serviceId}`);
  if (activeCard) activeCard.classList.add("active");

  const noticeName = document.getElementById("active-service-notice-name");
  if (noticeName) {
    if (serviceId === "1") noticeName.innerText = "اسنپ (به صرفه)";
    else if (serviceId === "2") noticeName.innerText = "اسنپ اکوپلاس (ویژه)";
    else if (serviceId === "24") noticeName.innerText = "سفر اشتراکی";
  }

  // Show Loading indicator on grid
  const grid = document.getElementById("origins-comparison-grid");
  if (grid) {
    grid.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 30px; grid-column: 1 / -1;"><i class="fa-solid fa-circle-notch fa-spin"></i> در حال دریافت مقایسه قیمت‌ها...</div>';
  }

  loadOriginsComparison();
}

async function loadOriginsComparison() {
  try {
    const res = await fetch(`/api/compare-origins?service_id=${activeComparisonServiceId}`);
    const data = await res.json();
    const grid = document.getElementById("origins-comparison-grid");
    if (!grid) return;

    if (!data.success || !data.origins || data.origins.length === 0) {
      grid.innerHTML = '<div style="color: var(--text-dim); text-align: center; padding: 20px;">داده‌ای برای مقایسه یافت نشد.</div>';
      return;
    }

    grid.innerHTML = "";
    data.origins.forEach((o, idx) => {
      const card = document.createElement("div");
      card.className = "origin-card" + (o.is_main ? " is-main" : "") + (o.is_cheapest ? " is-cheapest" : "");

      const badgeCheapest = o.is_cheapest 
        ? '<div class="origin-badge-cheapest"><i class="fa-solid fa-trophy"></i> ارزان‌ترین مبدأ هم‌اکنون</div>' 
        : '';

      const icon = o.is_main 
        ? '<i class="fa-solid fa-briefcase" style="color: #3b82f6;"></i>' 
        : `<span style="background-color: #f59e0b; color: white; width: 22px; height: 22px; border-radius: 50%; display: inline-flex; align-items: center; justify-content: center; font-size: 11px; font-weight: bold;">${idx}</span>`;

      const distText = o.is_main 
        ? "مبدأ پایه (محل کار اصلی)" 
        : `${(o.distance_meters || 0).toLocaleString("fa-IR")} متر پیاده‌روی تا کار اصلی`;

      const priceFormatted = o.price > 0 ? `${o.price.toLocaleString("fa-IR")} تومان` : "در انتظار استعلام زنده...";

      let savingsBadge = '';
      if (o.is_main) {
        savingsBadge = '<span class="origin-savings-badge neutral">مبنای مقایسه</span>';
      } else if (o.price > 0) {
        if (o.diff_vs_main > 0) {
          savingsBadge = `<span class="origin-savings-badge positive"><i class="fa-solid fa-arrow-down"></i> ${o.diff_vs_main.toLocaleString("fa-IR")} تومان ارزان‌تر (${o.savings_pct}٪)</span>`;
        } else if (o.diff_vs_main < 0) {
          savingsBadge = `<span class="origin-savings-badge negative"><i class="fa-solid fa-arrow-up"></i> ${Math.abs(o.diff_vs_main).toLocaleString("fa-IR")} تومان گران‌تر</span>`;
        } else {
          savingsBadge = '<span class="origin-savings-badge neutral">قیمت برابر با کار اصلی</span>';
        }
      }

      const latestTime = o.latest?.timestamp ? o.latest.timestamp.substring(11, 16) : '--:--';
      const isSurge = o.latest?.is_surge === 1;
      const surgeStatus = isSurge 
        ? '<span style="color: #ef4444;"><i class="fa-solid fa-bolt"></i> گرانی تقاضا (Surge)</span>' 
        : '<span style="color: #22c55e;">عادی</span>';

      const serviceTitle = formatServiceName(o.service_id, o.service_title);

      card.innerHTML = `
        ${badgeCheapest}
        <div>
          <div class="origin-header">
            <div class="origin-title-box">
              <h4>${icon} ${o.name}</h4>
              <div class="origin-distance">${distText}</div>
            </div>
          </div>

          <div style="font-size: 11px; color: var(--text-dim); margin-top: 4px;">
            <i class="fa-solid fa-tag"></i> سرویس: <strong style="color: var(--text-main);">${serviceTitle}</strong>
          </div>

          <div class="origin-price-box">
            <span class="origin-price-val">${priceFormatted}</span>
          </div>

          <div style="margin-bottom: 12px;">
            ${savingsBadge}
          </div>
        </div>

        <div class="origin-card-footer">
          <div>
            <span>وضعیت: ${surgeStatus}</span>
            <span style="display: block; font-size: 11px; color: var(--text-dim); margin-top: 3px;">آخرین استعلام: ${latestTime}</span>
          </div>
          <button class="btn btn-sm btn-outline" onclick="triggerCheck('${o.route_key}')" title="استعلام مجدد قیمت برای این نقطه">
            <i class="fa-solid fa-rotate"></i> استعلام
          </button>
        </div>
      `;
      grid.appendChild(card);
    });

  } catch (err) {
    console.error("Error loading origins comparison:", err);
  }
}

async function triggerCheckAllWorkOrigins(e) {
  const btn = (e && e.currentTarget) || (typeof event !== "undefined" ? event?.currentTarget : null) || document.querySelector(".panel-controls .btn-primary");
  const originalHtml = btn ? btn.innerHTML : null;
  if (btn) {
    btn.innerHTML = '<i class="fa-solid fa-spinner fa-spin"></i> در حال استعلام تمام مبادی...';
    btn.disabled = true;
  }
  showToast("در حال ارسال درخواست استعلام هم‌زمان اسنپ برای تمام مبادی اطراف کار...");
  
  try {
    const res = await fetch("/api/check-now", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ route_key: "all_work_origins" })
    });
    const data = await res.json();
    if (data.success) {
      showToast("تمام استعلام‌ها با موفقیت دریافت و مقایسه گردید!");
      loadOriginsComparison();
      loadRecentTable();
      loadHourlyChart();
    } else {
      showToast("خطا در استعلام گروهی: " + (data.error || "نامشخص"), true);
    }
  } catch (e) {
    showToast("خطای اتصال: " + e, true);
  } finally {
    if (btn && originalHtml) {
      btn.innerHTML = originalHtml;
      btn.disabled = false;
    }
  }
}

// --- Save Token ---
async function handleTokenSubmit(event) {
  event.preventDefault();
  const access = document.getElementById("input-access-token").value.trim();
  const refresh = document.getElementById("input-refresh-token").value.trim();

  try {
    const res = await fetch("/api/auth/token", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ access_token: access, refresh_token: refresh })
    });
    const data = await res.json();
    if (data.success) {
      showToast("توکن با موفقیت ذخیره شد!");
      closeModal("auth-modal");
      loadStatus();
    } else {
      showToast("خطا در ثبت توکن: " + (data.detail || "نامشخص"), true);
    }
  } catch (e) {
    showToast("خطا در ارتباط با سرور: " + e, true);
  }
}

// --- Test Current Token ---
async function testCurrentToken() {
  showToast("در حال ارسال درخواست استعلام به اسنپ...");
  try {
    const res = await fetch("/api/check-now", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ route_key: "home_to_work" })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`موفقیت‌آمیز! قیمت جاری اسنپ: ${data.eco_price.toLocaleString("fa-IR")} تومان`);
      loadStatus();
      loadHourlyChart();
      loadRecentTable();
      loadOriginsComparison();
    } else {
      showToast("خطا در استعلام: " + (data.error || "لطفا توکن خود را بررسی کنید"), true);
    }
  } catch (e) {
    showToast("خطای شبکه: " + e, true);
  }
}

// --- Save Config Form ---
async function handleConfigSubmit(event) {
  event.preventDefault();
  const intervalVal = parseInt(document.getElementById("cfg-247-interval")?.value || "10", 10);
  const pwdVal = document.getElementById("cfg-password")?.value?.trim();

  const newConfig = {
    routes: {
      home: {
        name: "خانه",
        lat: parseFloat(document.getElementById("cfg-home-lat").value),
        lng: parseFloat(document.getElementById("cfg-home-lng").value)
      },
      work: {
        name: "محل کار اصلی",
        lat: parseFloat(document.getElementById("cfg-work-lat").value),
        lng: parseFloat(document.getElementById("cfg-work-lng").value)
      },
      work_alternatives: currentConfig.routes?.work_alternatives || []
    },
    schedules: {
      continuous_24_7: {
        enabled: true,
        interval_minutes: intervalVal
      }
    }
  };

  if (pwdVal) {
    newConfig.security = { password: pwdVal };
  }

  saveRoutesToLocalStorage(newConfig.routes);

  try {
    const res = await fetch("/api/config", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(newConfig)
    });
    const data = await res.json();
    if (data.success) {
      showToast("تنظیمات با موفقیت ذخیره گردید.");
      closeModal("config-modal");
      loadConfig();
      loadStatus();
    }
  } catch (e) {
    showToast("خطا در ذخیره تنظیمات: " + e, true);
  }
}

// --- Trigger Single Route Check ---
async function triggerCheck(routeKey) {
  const isMorning = routeKey === 'home_to_work';
  showToast(`در حال استعلام نرخ اسنپ برای ${isMorning ? 'مسیر خانه به سرکار' : 'مسیر سرکار به خانه'}...`);
  try {
    const res = await fetch("/api/check-now", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ route_key: routeKey })
    });
    const data = await res.json();
    if (data.success) {
      showToast(`قیمت دریافت شد: ${data.eco_price.toLocaleString("fa-IR")} تومان`);
      loadHourlyChart();
      loadDateComparisonChart();
      loadRecentTable();
      loadOriginsComparison();
    } else {
      showToast("خطا: " + (data.error || "خطای ناشناخته"), true);
    }
  } catch (e) {
    showToast("خطای اتصال: " + e, true);
  }
}

// --- Load Dates List into Dropdown ---
async function loadDistinctDates() {
  try {
    const res = await fetch("/api/distinct-dates");
    const data = await res.json();
    const select = document.getElementById("hourly-date-select");
    if (!select) return;
    select.innerHTML = '<option value="all">تمام روزها (میانگین کلی)</option>';
    (data.dates || []).forEach(d => {
      const opt = document.createElement("option");
      opt.value = d;
      opt.innerText = d;
      select.appendChild(opt);
    });
  } catch (e) {
    console.error("Error loading dates:", e);
  }
}

// --- Load High-Resolution 15-Minute Timeline Chart & Recommendation ---
async function loadHourlyChart() {
  const routeSelect = document.getElementById("hourly-route-select");
  const dateSelect = document.getElementById("hourly-date-select");
  const srvSelect = document.getElementById("hourly-service-select");
  const invSelect = document.getElementById("hourly-interval-select");

  const route = routeSelect ? routeSelect.value : "home_to_work";
  const dateStr = dateSelect ? dateSelect.value : "all";
  const serviceId = srvSelect ? srvSelect.value : "1";
  const intervalMinutes = invSelect ? parseInt(invSelect.value, 10) : 15;

  try {
    const res = await fetch(`/api/analytics?route=${route}&date_str=${dateStr}&service_id=${serviceId}&interval_minutes=${intervalMinutes}`);
    const data = await res.json();

    const curve = data.timeline_curve || [];
    const rec = data.best_time_recommendation || {};

    // Dynamic Recommendation Banner
    const recTitleEl = document.getElementById("recommendation-title");
    const recDescEl = document.getElementById("recommendation-desc");

    if (rec.has_data) {
      const bestTimeStr = rec.cheapest_time_formatted || rec.cheapest_hour_formatted || "--:--";
      const peakTimeStr = rec.peak_time_formatted || rec.peak_hour_formatted || "--:--";

      recTitleEl.innerText = 
        `💡 بهترین ساعت حرکت (${rec.route_name_fa}): ساعت ${bestTimeStr} (${rec.window_label})`;
      recDescEl.innerText = 
        `میانگین کرایه در ارزان‌ترین بازه: ${rec.lowest_avg_price.toLocaleString("fa-IR")} تومان با صرفه‌جویی ${rec.savings_percentage}٪ نسبت به اوج گرانی: ${rec.peak_avg_price.toLocaleString("fa-IR")} تومان (ساعت ${peakTimeStr}) — بر اساس ${rec.total_datapoints.toLocaleString("fa-IR")} استعلام ثبت‌شده.`;
    } else {
      recTitleEl.innerText = "درحال جمع‌آوری داده‌های استعلام برای تحلیل هوشمند...";
      recDescEl.innerText = rec.message || "با ثبت نمونه‌های بیشتر در ساعات مختلف، بهترین زمان حرکت با کمترین هزینه محاسبه خواهد شد.";
    }

    // High-Resolution Timeline Generation:
    // Generate all intervals for 24 hours (e.g. for interval 15: 00:00, 00:15, 00:30, 00:45, ... up to 23:45 = 96 points)
    const labels = [];
    const avgPrices = [];
    const minPrices = [];
    const maxPrices = [];

    const slotsPerHour = Math.max(1, Math.round(60 / intervalMinutes));
    for (let h = 0; h < 24; h++) {
      for (let s = 0; s < slotsPerHour; s++) {
        const m = s * intervalMinutes;
        const timeLabel = `${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`;
        labels.push(timeLabel);

        const match = curve.find(item => item.hour === h && item.minute_slot === m);
        if (match) {
          avgPrices.push(match.avg_price);
          minPrices.push(match.min_price);
          maxPrices.push(match.max_price);
        } else {
          avgPrices.push(null);
          minPrices.push(null);
          maxPrices.push(null);
        }
      }
    }

    renderHourlyChart(labels, avgPrices, minPrices, maxPrices, intervalMinutes);
  } catch (e) {
    console.error("Failed to load timeline analytics:", e);
  }
}

function renderHourlyChart(labels, avgPrices, minPrices, maxPrices, intervalMinutes) {
  const canvas = document.getElementById("hourlyChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (hourlyChartInstance) {
    hourlyChartInstance.destroy();
  }

  // Adjust point radius based on point count
  const ptRadius = labels.length > 50 ? 2.5 : 4;

  hourlyChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: [
        {
          label: "میانگین کرایه (تومان)",
          data: avgPrices,
          borderColor: "#22c55e",
          backgroundColor: "rgba(34, 197, 94, 0.15)",
          borderWidth: 2.5,
          tension: 0.35,
          fill: true,
          pointBackgroundColor: "#22c55e",
          pointRadius: ptRadius,
          pointHoverRadius: 6,
          spanGaps: true
        },
        {
          label: "سقف گرانی (Surge)",
          data: maxPrices,
          borderColor: "rgba(239, 68, 68, 0.75)",
          borderWidth: 1.5,
          borderDash: [4, 4],
          pointRadius: ptRadius > 2 ? 2 : 0,
          pointHoverRadius: 5,
          fill: false,
          spanGaps: true
        },
        {
          label: "کف قیمت (ارزان‌ترین)",
          data: minPrices,
          borderColor: "rgba(59, 130, 246, 0.75)",
          borderWidth: 1.5,
          borderDash: [3, 3],
          pointRadius: ptRadius > 2 ? 2 : 0,
          pointHoverRadius: 5,
          fill: false,
          spanGaps: true
        }
      ]
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: {
        mode: 'index',
        intersect: false,
      },
      plugins: {
        legend: {
          labels: {
            color: "#94a3b8",
            font: { family: "'Vazirmatn', sans-serif", size: 12 }
          }
        },
        tooltip: {
          rtl: true,
          textDirection: 'rtl',
          backgroundColor: 'rgba(15, 23, 42, 0.96)',
          titleColor: '#f8fafc',
          bodyColor: '#e2e8f0',
          borderColor: 'rgba(255, 255, 255, 0.12)',
          borderWidth: 1,
          padding: 12,
          boxPadding: 6,
          titleFont: {
            family: "'Vazirmatn', sans-serif",
            size: 13,
            weight: '700'
          },
          bodyFont: {
            family: "'Vazirmatn', sans-serif",
            size: 12,
            weight: '400'
          },
          callbacks: {
            title: function(items) {
              return items.length ? `ساعت ${items[0].label} (بازه ۱۵ دقیقه‌ای)` : '';
            },
            label: function(context) {
              const val = context.parsed.y;
              if (val === null || val === undefined) return '';
              return ` ${context.dataset.label}: ${val.toLocaleString("fa-IR")} تومان`;
            }
          }
        }
      },
      scales: {
        x: {
          ticks: {
            color: "#64748b",
            font: { family: "'Vazirmatn', sans-serif" },
            maxTicksLimit: 24, // Display ticks every 1-2 hours on axis, but hover checks all 15-min points
            callback: function(val, index) {
              const lbl = labels[index] || "";
              // Show only round hours on x-axis to keep axis clean
              return lbl.endsWith(":00") ? lbl : "";
            }
          },
          grid: { color: "rgba(255, 255, 255, 0.05)" }
        },
        y: {
          ticks: {
            color: "#64748b",
            font: { family: "'Vazirmatn', sans-serif" },
            callback: function(val) {
              return (val / 1000).toLocaleString("fa-IR") + "k";
            }
          },
          grid: { color: "rgba(255, 255, 255, 0.05)" }
        }
      }
    }
  });
}

// --- Load Multi-Date Comparison Chart ---
async function loadDateComparisonChart() {
  const routeSelect = document.getElementById("date-chart-route-select");
  const route = routeSelect ? routeSelect.value : (activeDirection === "work_to_home" ? "work_to_home" : "home_to_work");

  try {
    const datesRes = await fetch(`/api/distinct-dates?route=${route}`);
    const datesData = await datesRes.json();
    const recentDates = (datesData.dates || []).slice(0, 5);

    if (recentDates.length === 0) return;

    const datasets = [];
    const colors = ["#38bdf8", "#f43f5e", "#a855f7", "#eab308", "#22c55e"];

    // 15-minute resolution timeline (96 points)
    const labels = [];
    for (let h = 0; h < 24; h++) {
      for (let m = 0; m < 60; m += 15) {
        labels.push(`${h.toString().padStart(2, '0')}:${m.toString().padStart(2, '0')}`);
      }
    }

    for (let i = 0; i < recentDates.length; i++) {
      const d = recentDates[i];
      const res = await fetch(`/api/analytics?route=${route}&date_str=${d}&service_id=1&interval_minutes=15`);
      const dData = await res.json();
      const curve = dData.timeline_curve || [];

      const prices = [];
      for (let h = 0; h < 24; h++) {
        for (let m = 0; m < 60; m += 15) {
          const item = curve.find(x => x.hour === h && x.minute_slot === m);
          prices.push(item ? item.avg_price : null);
        }
      }

      datasets.push({
        label: `تاریخ ${d}`,
        data: prices,
        borderColor: colors[i % colors.length],
        borderWidth: 2,
        tension: 0.35,
        fill: false,
        pointRadius: 2,
        spanGaps: true
      });
    }

    renderDateComparisonChart(labels, datasets);

  } catch (e) {
    console.error("Error loading date comparison chart:", e);
  }
}

function renderDateComparisonChart(labels, datasets) {
  const canvas = document.getElementById("dateComparisonChart");
  if (!canvas) return;
  const ctx = canvas.getContext("2d");
  if (dateComparisonChartInstance) {
    dateComparisonChartInstance.destroy();
  }

  dateComparisonChartInstance = new Chart(ctx, {
    type: "line",
    data: {
      labels: labels,
      datasets: datasets
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        legend: {
          labels: {
            color: "#94a3b8",
            font: { family: "'Vazirmatn', sans-serif", size: 12 }
          }
        },
        tooltip: {
          rtl: true,
          textDirection: 'rtl',
          backgroundColor: 'rgba(15, 23, 42, 0.96)',
          titleColor: '#f8fafc',
          bodyColor: '#e2e8f0',
          borderColor: 'rgba(255, 255, 255, 0.12)',
          borderWidth: 1,
          padding: 12,
          boxPadding: 6,
          titleFont: {
            family: "'Vazirmatn', sans-serif",
            size: 13,
            weight: '700'
          },
          bodyFont: {
            family: "'Vazirmatn', sans-serif",
            size: 12,
            weight: '400'
          },
          callbacks: {
            title: function(items) {
              return items.length ? `ساعت ${items[0].label} (بازه ۱۵ دقیقه‌ای)` : '';
            },
            label: function(context) {
              const val = context.parsed.y;
              if (val === null || val === undefined) return '';
              return ` ${context.dataset.label}: ${val.toLocaleString("fa-IR")} تومان`;
            }
          }
        }
      },
      scales: {
        x: {
          ticks: {
            color: "#64748b",
            font: { family: "'Vazirmatn', sans-serif" },
            maxTicksLimit: 24,
            callback: function(val, index) {
              const lbl = labels[index] || "";
              return lbl.endsWith(":00") ? lbl : "";
            }
          },
          grid: { color: "rgba(255, 255, 255, 0.05)" }
        },
        y: {
          ticks: {
            color: "#64748b",
            font: { family: "'Vazirmatn', sans-serif" },
            callback: (val) => (val / 1000).toLocaleString("fa-IR") + "k"
          },
          grid: { color: "rgba(255, 255, 255, 0.05)" }
        }
      }
    }
  });
}

// Clean Service Title Resolver (Returns actual API name, zero hardcoded guessing)
function formatServiceName(serviceId, serviceTitle) {
  const sid = String(serviceId || "").trim();
  if (sid === "1") return "اسنپ (به صرفه)";
  if (sid === "2") return "اسنپ اکوپلاس (ویژه)";
  if (sid === "24") return "سفر اشتراکی (تا ۱۰ دقیقه انتظار)";
  if (sid === "3") return "اسنپ باکس (پیک موتوری)";
  if (sid === "4") return "اسنپ بایک (موتور مسافر)";
  if (serviceTitle && !serviceTitle.includes("رز") && !serviceTitle.includes("بانوان")) {
    return serviceTitle.trim();
  }
  return sid ? `سرویس ${sid}` : "اسنپ (به صرفه)";
}

// --- Table Sorting & Filtering Controller ---
function toggleTableSort(column) {
  if (currentTableSort.column === column) {
    currentTableSort.order = currentTableSort.order === "asc" ? "desc" : "asc";
  } else {
    currentTableSort.column = column;
    currentTableSort.order = column === "price" || column === "raw_fare" ? "asc" : "desc";
  }

  // Update UI sort icons
  const icons = ["time", "price", "raw_fare", "surge"];
  icons.forEach(col => {
    const el = document.getElementById(`th-sort-icon-${col}`);
    if (el) {
      if (col === currentTableSort.column) {
        el.className = currentTableSort.order === "asc" ? "fa-solid fa-sort-up text-success" : "fa-solid fa-sort-down text-success";
      } else {
        el.className = "fa-solid fa-sort";
      }
    }
  });

  // Sync Dropdown
  const sortSelect = document.getElementById("table-sort-select");
  if (sortSelect) {
    const val = `${currentTableSort.column}_${currentTableSort.order}`;
    if (Array.from(sortSelect.options).some(o => o.value === val)) {
      sortSelect.value = val;
    }
  }

  loadRecentTable();
  updateExportLinks();
}

function onTableSortSelectChange(val) {
  const parts = val.split("_");
  if (parts.length >= 2) {
    currentTableSort.column = parts[0];
    currentTableSort.order = parts[1];

    const icons = ["time", "price", "raw_fare", "surge"];
    icons.forEach(col => {
      const el = document.getElementById(`th-sort-icon-${col}`);
      if (el) {
        if (col === currentTableSort.column) {
          el.className = currentTableSort.order === "asc" ? "fa-solid fa-sort-up text-success" : "fa-solid fa-sort-down text-success";
        } else {
          el.className = "fa-solid fa-sort";
        }
      }
    });

    loadRecentTable();
    updateExportLinks();
  }
}

// --- Load Recent Records Table ---
async function loadRecentTable() {
  const routeFilter = document.getElementById("table-route-filter")?.value || "all";
  const srvFilter = document.getElementById("table-service-filter")?.value || "all";
  const sortParam = `${currentTableSort.column}_${currentTableSort.order}`;

  try {
    const res = await fetch(`/api/prices?limit=50&route=${routeFilter}&service_id=${srvFilter}&sort_by=${sortParam}`);
    const data = await res.json();
    const tbody = document.getElementById("prices-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    const prices = data.prices || [];
    if (prices.length === 0) {
      tbody.innerHTML = '<tr><td colspan="7" class="text-center" style="padding: 24px; color: var(--text-dim);"><i class="fa-solid fa-inbox" style="font-size: 24px; display: block; margin-bottom: 8px;"></i>هیچ رکوردی با فیلتر انتخابی یافت نشد. می‌توانید از دکمه «بارگذاری داده‌های نمونه» استفاده نمایید.</td></tr>';
      return;
    }

    // Update Live Commute Cards
    const morningLatest = prices.find(p => p.route_key === "home_to_work");
    const eveningLatest = prices.find(p => p.route_key === "work_to_home");

    if (morningLatest) {
      document.getElementById("morning-current-price").innerText = morningLatest.price.toLocaleString("fa-IR");
    }
    if (eveningLatest) {
      document.getElementById("evening-current-price").innerText = eveningLatest.price.toLocaleString("fa-IR");
    }

    prices.forEach(p => {
      const tr = document.createElement("tr");
      const timeFormatted = `${(p.hour || 0).toString().padStart(2, '0')}:${(p.minute || 0).toString().padStart(2, '0')} (${p.date_str})`;

      const isSurge = p.is_surge === 1;
      const surgeBadge = isSurge 
        ? `<span class="badge badge-surge">گرانی (+${Math.round((p.surge_ratio - 1) * 100)}٪)</span>`
        : `<span class="badge badge-normal">عادی</span>`;

      let routeDisplay = 'سایر';
      if (p.route_key === 'home_to_work') {
        routeDisplay = '<span style="color: #22c55e;"><i class="fa-solid fa-sun"></i> خانه ➔ کار</span>';
      } else if (p.route_key === 'work_to_home') {
        routeDisplay = '<span style="color: #3b82f6;"><i class="fa-solid fa-briefcase"></i> کار اصلی ➔ خانه</span>';
      } else {
        routeDisplay = `<span style="color: #f59e0b;"><i class="fa-solid fa-person-walking"></i> ${p.origin_name || 'اطراف کار'} ➔ خانه</span>`;
      }

      const serviceName = formatServiceName(p.service_id, p.service_title);

      tr.innerHTML = `
        <td><strong>${timeFormatted}</strong></td>
        <td>${routeDisplay}</td>
        <td><span style="font-weight: 600;">${serviceName}</span></td>
        <td><strong style="color: var(--text-main); font-size: 14px;">${p.price.toLocaleString("fa-IR")} تومان</strong></td>
        <td>${(p.raw_fare || p.price).toLocaleString("fa-IR")} تومان</td>
        <td>${surgeBadge}</td>
        <td>${p.eta || '---'}</td>
      `;
      tbody.appendChild(tr);
    });

  } catch (e) {
    console.error("Error loading recent prices:", e);
  }
}

// --- Seed High-Resolution Demo Data ---
async function seedSampleData() {
  showToast("در حال تولید داده‌های تفکیکی ۱۵ دقیقه‌ای برای تمام سرویس‌ها (Eco، Plus، Carpooling)...");
  try {
    const res = await fetch("/api/seed-demo-data", { method: "POST" });
    const data = await res.json();
    if (data.success) {
      showToast(`با موفقیت ${data.records_added} رکورد تفکیکی ۱۵ دقیقه‌ای برای تحلیل افزوده شد!`);
      loadStatus();
      loadConfig();
      loadDistinctDates();
      loadHourlyChart();
      loadDateComparisonChart();
      loadRecentTable();
      loadOriginsComparison();
    }
  } catch (e) {
    showToast("خطا در بارگذاری داده‌های نمونه: " + e, true);
  }
}
