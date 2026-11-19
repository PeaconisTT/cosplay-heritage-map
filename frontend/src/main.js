import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { SignatureCanvas } from './signatureCanvas.js';

const API_BASE_URL = 'http://localhost:8000/api/v1';

// ==========================================
// 1. Trạng thái Toàn cục (Global State)
// ==========================================
let currentViewMode = 'popup'; // 'popup' (Bong bóng nổi) | 'panel' (Panel bên trái)
let draftPinMarker = null;     // Marker cho Pin tạm thời khi click map
let signatureCanvasInstance = null;

// Quản lý bộ lọc đang kích hoạt
let activeFilter = {
  mode: 'ALL', // 'ALL' | 'EVENT' | 'IP' | 'COSPLAYER'
  value: ''
};

// Dữ liệu bộ lọc thực tế nạp từ Backend GET /pins/filters
let filterData = {
  events: [],
  works: [],
  letters: []
};

// ==========================================
// 2. Khởi tạo Bản đồ Leaflet 2D (L.CRS.Simple)
// ==========================================
const map = L.map('map', {
  crs: L.CRS.Simple,
  minZoom: -3,
  maxZoom: 3,
  zoomSnap: 0.5,
  zoomControl: false,
  attributionControl: false
});

// Đặt nút Zoom +/- ở góc dưới bên phải
L.control.zoom({ position: 'bottomright' }).addTo(map);

const mapBounds = [[0, 0], [3000, 3000]];
map.fitBounds(mapBounds);

const markersLayerGroup = L.layerGroup().addTo(map);

// ==========================================
// 3. Trợ giúp & Xử lý lỗi API
// ==========================================
async function parseApiError(response) {
  try {
    const errData = await response.json();
    if (typeof errData.detail === 'string') {
      return errData.detail;
    }
    if (Array.isArray(errData.detail)) {
      return errData.detail
        .map(err => {
          const field = err.loc ? err.loc[err.loc.length - 1] : 'Dữ liệu';
          return `- ${field}: ${err.msg}`;
        })
        .join('\n');
    }
    return JSON.stringify(errData);
  } catch {
    return `Lỗi kết nối Server (HTTP ${response.status})`;
  }
}

/**
 * Xây dựng URL truy vấn phân cụm kết hợp bán kính eps co giãn & bộ lọc thực tế
 */
function buildClusterApiUrl() {
  const currentZoom = map.getZoom();
  // Zoom càng sâu thì eps càng nhỏ để tự động tách cụm thành các chấm đơn lẻ
  const dynamicEps = Math.max(5, 100 / Math.pow(2, currentZoom)).toFixed(1);

  const params = new URLSearchParams({
    eps: dynamicEps,
    min_points: '2'
  });

  if (activeFilter.mode === 'EVENT' && activeFilter.value) {
    params.append('event_name', activeFilter.value);
  } else if (activeFilter.mode === 'IP' && activeFilter.value) {
    params.append('work_title', activeFilter.value);
  } else if (activeFilter.mode === 'COSPLAYER' && activeFilter.value) {
    params.append('alias_first_letter', activeFilter.value);
  }

  return `${API_BASE_URL}/pins/clusters?${params.toString()}`;
}

// ==========================================
// 4. Pin Tạm thời & Box Hành động Động (Action 1 Fix)
// ==========================================

function clearDraftPin() {
  if (draftPinMarker) {
    draftPinMarker.closePopup();
    map.removeLayer(draftPinMarker);
    draftPinMarker = null;
  }
}

function showDraftPin(x, y) {
  // Đóng các popup hoặc panel đang mở để tập trung vào vị trí click
  map.closePopup();
  closeAllDropdowns();

  const draftIcon = L.divIcon({
    html: `
      <div class="relative group cursor-pointer flex items-center justify-center">
        <div class="absolute w-8 h-8 rounded-full bg-rose-500/40 draft-pin-pulse"></div>
        <div class="w-6 h-6 bg-gradient-to-tr from-rose-600 to-amber-400 border-2 border-white rounded-full shadow-lg"></div>
        <div class="absolute -bottom-1.5 left-1/2 -translate-x-1/2 w-2 h-2 bg-rose-600 rotate-45 border-r border-b border-white"></div>
      </div>
    `,
    className: 'custom-draft-icon',
    iconSize: [32, 32],
    iconAnchor: [16, 28]
  });

  const popupContent = `
    <div class="draft-action-box p-3 bg-slate-900/95 backdrop-blur-md border border-slate-700 rounded-xl text-white shadow-2xl min-w-[210px]">
      <div class="flex items-center justify-between pb-1.5 mb-2 border-b border-slate-800">
        <span class="text-[11px] font-semibold text-amber-400 uppercase tracking-wider flex items-center gap-1">
          📍 Vị trí ghim tạm
        </span>
        <button type="button" data-action="close-draft-pin" class="btn-cancel-draft w-6 h-6 rounded-md flex items-center justify-center bg-slate-800 text-slate-300 border border-slate-700 hover:bg-rose-600 hover:border-rose-500 hover:text-white active:bg-rose-800 active:scale-95 transition-all duration-150 ease-out cursor-pointer text-xs" title="Hủy">✕</button>
      </div>
      <p class="text-xs text-slate-300 font-mono mb-2.5 bg-slate-950/70 px-2 py-1 rounded border border-slate-800">
        Tọa độ: (${x.toFixed(1)}, ${y.toFixed(1)})
      </p>
      <button type="button" data-action="create-draft-pin" class="btn-create-pin w-full bg-rose-600 text-white font-semibold text-xs py-2 px-3 rounded-lg shadow-lg shadow-rose-600/30 border border-rose-500/50 hover:bg-rose-700 hover:shadow-rose-700/40 active:bg-rose-800 active:scale-95 transition-all duration-150 ease-out cursor-pointer flex items-center justify-center gap-1.5">
        ➕ Tạo Pin Mới
      </button>
    </div>
  `;

  if (!draftPinMarker) {
    draftPinMarker = L.marker([y, x], { icon: draftIcon }).addTo(map);
  } else {
    draftPinMarker.setLatLng([y, x]);
  }

  draftPinMarker.bindPopup(popupContent, {
    className: 'dark-popup',
    closeButton: false,
    offset: [0, -22]
  }).openPopup();

  // Bắt sự kiện trên các nút bấm của Popup với disableClickPropagation
  draftPinMarker.off('popupopen');
  draftPinMarker.on('popupopen', () => {
    const popup = draftPinMarker.getPopup();
    const containerEl = popup ? popup.getElement() : null;
    if (!containerEl) return;

    // Chặn hoàn toàn lan truyền sự kiện click và scroll chuột trong Leaflet
    L.DomEvent.disableClickPropagation(containerEl);
    L.DomEvent.disableScrollPropagation(containerEl);

    // Gán trực tiếp với closest / data-action
    const btnCancel = containerEl.querySelector('[data-action="close-draft-pin"]');
    if (btnCancel) {
      btnCancel.onclick = (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        clearDraftPin();
      };
    }

    const btnCreate = containerEl.querySelector('[data-action="create-draft-pin"]');
    if (btnCreate) {
      btnCreate.onclick = (ev) => {
        ev.preventDefault();
        ev.stopPropagation();
        openModal(x, y);
      };
    }
  });
}

// Bắt sự kiện click vào vùng trống trên bản đồ Leaflet
map.on('click', (e) => {
  // Kiểm tra an toàn: nếu click rơi vào popup, action box, icon hoặc control thì KHÔNG xử lý tạo dời pin tạm
  if (e.originalEvent?.target?.closest('.leaflet-popup, .draft-action-box, .custom-cluster-icon, .custom-single-icon, .leaflet-control, #left-detail-panel')) {
    return;
  }
  showDraftPin(Number(e.latlng.lng), Number(e.latlng.lat));
});

// ==========================================
// 5. Left Panel & HTML Generators (Bố cục Ngang & Animation)
// ==========================================

function openLeftPanel(htmlContent, titleText = '📍 Chi tiết Tác phẩm') {
  const panel = document.getElementById('left-detail-panel');
  const titleEl = document.getElementById('left-panel-title');
  const bodyEl = document.getElementById('left-panel-body');
  if (!panel || !bodyEl) return;

  if (titleEl) titleEl.innerHTML = titleText;

  // Nếu panel đang mở, chạy animation chuyển cảnh mượt mà
  const isAlreadyOpen = panel.classList.contains('visible');
  if (isAlreadyOpen) {
    bodyEl.classList.remove('opacity-100', 'translate-y-0');
    bodyEl.classList.add('opacity-0', 'translate-y-1.5');
    setTimeout(() => {
      bodyEl.innerHTML = htmlContent;
      bodyEl.classList.remove('opacity-0', 'translate-y-1.5');
      bodyEl.classList.add('opacity-100', 'translate-y-0');
    }, 80);
  } else {
    bodyEl.innerHTML = htmlContent;
    panel.classList.remove('opacity-0', '-translate-x-6', 'scale-95', 'pointer-events-none', 'invisible');
    panel.classList.add('opacity-100', 'translate-x-0', 'scale-100', 'pointer-events-auto', 'visible');
  }
}

function closeLeftPanel() {
  const panel = document.getElementById('left-detail-panel');
  if (panel) {
    panel.classList.remove('opacity-100', 'translate-x-0', 'scale-100', 'pointer-events-auto', 'visible');
    panel.classList.add('opacity-0', '-translate-x-6', 'scale-95', 'pointer-events-none', 'invisible');
  }
}

function setViewMode(mode) {
  currentViewMode = mode;
  const btnPopup = document.getElementById('view-mode-popup');
  const btnPanel = document.getElementById('view-mode-panel');

  const activeClasses = ['bg-indigo-600', 'text-white', 'border-indigo-400', 'shadow-inner'];
  const inactiveClasses = [
    'bg-slate-800',
    'text-slate-100',
    'border-slate-600',
    'shadow-sm',
    'hover:bg-slate-700',
    'hover:border-indigo-400',
    'hover:text-white',
    'active:bg-indigo-950',
    'active:border-indigo-500',
    'active:text-indigo-200',
    'active:scale-95'
  ];

  if (mode === 'popup') {
    if (btnPopup) {
      btnPopup.classList.remove(...inactiveClasses);
      btnPopup.classList.add(...activeClasses);
    }
    if (btnPanel) {
      btnPanel.classList.remove(...activeClasses);
      btnPanel.classList.add(...inactiveClasses);
    }
  } else {
    if (btnPanel) {
      btnPanel.classList.remove(...inactiveClasses);
      btnPanel.classList.add(...activeClasses);
    }
    if (btnPopup) {
      btnPopup.classList.remove(...activeClasses);
      btnPopup.classList.add(...inactiveClasses);
    }
  }

  // Đóng cả Popup lẫn Panel đang mở để tránh chồng chéo giao diện
  map.closePopup();
  closeLeftPanel();
}

/**
 * Thumbnail nhỏ cho danh sách trong cụm tròn
 */
function buildClusterThumbnailHtml(pinData, backendOrigin) {
  const isPlaceholder = !pinData.media_url || pinData.media_url.includes('/placeholders/');

  if (isPlaceholder) {
    const initialChar = (pinData.character_name || '?').charAt(0).toUpperCase();
    return `
      <div class="w-9 h-9 rounded-lg border border-amber-500/40 bg-gradient-to-br from-slate-900 via-indigo-950 to-rose-950 flex items-center justify-center shrink-0 shadow-inner">
        <span class="text-xs font-serif font-bold text-amber-300">${initialChar}</span>
      </div>
    `;
  }

  return `<img src="${backendOrigin}${pinData.media_url}" alt="${pinData.character_name}" class="w-9 h-9 rounded-lg object-cover bg-slate-950 shrink-0 border border-slate-700" />`;
}

/**
 * Tạo khung hình ảnh nằm trọn bên phải (Cột phải của bố cục ngang)
 */
function buildRightMediaColumnHtml(pinData, backendOrigin, isPanel = false) {
  const isPlaceholder = !pinData.media_url || pinData.media_url.includes('/placeholders/');
  const colWidth = isPanel ? 'w-44' : 'w-40';
  const minHeight = isPanel ? 'min-h-[220px]' : 'min-h-[190px]';

  if (isPlaceholder) {
    const initialChar = (pinData.character_name || '?').charAt(0).toUpperCase();
    return `
      <div class="${colWidth} ${minHeight} shrink-0 self-stretch rounded-xl overflow-hidden border border-amber-500/30 bg-gradient-to-br from-slate-900 via-indigo-950 to-rose-950 flex flex-col items-center justify-center p-3 text-center relative">
        <div class="absolute inset-0 opacity-25 bg-[radial-gradient(#fbbf24_1px,transparent_1px)] [background-size:12px_12px]"></div>
        <div class="relative w-12 h-12 rounded-full border border-amber-400/60 bg-slate-950/70 flex items-center justify-center mb-2 shadow-inner">
          <span class="text-xl font-serif font-bold text-amber-300">${initialChar}</span>
        </div>
        <span class="relative text-[10px] uppercase tracking-widest text-amber-300/90 font-semibold leading-tight">✦ Heritage Pin ✦</span>
        <span class="relative text-[9px] text-slate-400 mt-1">Chứng thực chữ ký số</span>
      </div>
    `;
  }

  return `
    <div class="${colWidth} ${minHeight} shrink-0 self-stretch rounded-xl overflow-hidden border border-slate-700 bg-slate-950 flex items-center justify-center">
      <img 
        src="${backendOrigin}${pinData.media_url}" 
        alt="${pinData.character_name}"
        class="w-full h-full object-cover" 
      />
    </div>
  `;
}

/**
 * Tạo khung hiển thị Chữ ký số hóa bên cột trái
 */
function buildSignatureBoxHtml(pinData, backendOrigin) {
  const shortPinId = pinData.pixel_pin_id ? pinData.pixel_pin_id.slice(0, 10) : '';

  let sigContentHtml = '';
  if (pinData.signature_url) {
    sigContentHtml = `
      <div class="w-full h-14 bg-slate-950/80 rounded flex items-center justify-center p-1 border border-slate-800">
        <img 
          src="${backendOrigin}${pinData.signature_url}" 
          alt="Chữ ký ${pinData.cosplayer_name}" 
          class="w-full h-full object-contain filter drop-shadow" 
        />
      </div>
    `;
  } else {
    sigContentHtml = `
      <div class="w-full h-9 flex items-center justify-center text-[10px] text-emerald-400 font-mono bg-emerald-950/30 rounded border border-emerald-800/40">
        ✓ Đã ký xác thực C2PA
      </div>
    `;
  }

  return `
    <div class="rounded-lg border border-slate-700/80 bg-slate-950/90 p-2 flex flex-col gap-1.5 shadow-inner mt-auto">
      <div class="flex items-center justify-between text-[10px]">
        <span class="font-semibold text-rose-400 flex items-center gap-1">✍️ Chữ ký xác thực</span>
        ${shortPinId ? `<span class="font-mono text-[9px] text-slate-400 bg-slate-900 px-1.5 py-0.5 rounded border border-slate-800" title="${pinData.pixel_pin_id}">#${shortPinId}</span>` : ''}
      </div>
      ${sigContentHtml}
    </div>
  `;
}

/**
 * Xây dựng toàn bộ Card chi tiết Pin theo BỐ CỤC 2 CỘT NGANG (Horizontal Split Layout)
 */
function buildSinglePinHorizontalCard(pinData, backendOrigin, isPanel = false) {
  const verifiedBadge = pinData.is_verified
    ? `<span class="inline-block bg-amber-500/20 text-amber-400 border border-amber-500/40 text-[10px] px-1.5 py-0.5 rounded font-semibold shrink-0">✓ Verified</span>`
    : '';

  const categoryBadge = pinData.work_category
    ? `<span class="inline-block bg-indigo-500/20 text-indigo-300 border border-indigo-500/40 text-[10px] px-1.5 py-0.5 rounded font-semibold shrink-0">${pinData.work_category}</span>`
    : '';

  const eventHtml = pinData.event_name
    ? `<p class="text-[11px] text-amber-300/90 truncate">🎪 <span class="font-medium">${pinData.event_name}${pinData.event_year ? ` (${pinData.event_year})` : ''}</span></p>`
    : '';

  const messageHtml = pinData.message
    ? `<p class="text-[11px] text-slate-300 italic line-clamp-2 bg-slate-950/70 p-1.5 rounded border border-slate-800/80">"${pinData.message}"</p>`
    : '';

  const coordX = pinData.virtual_coord?.x ?? pinData.x ?? 0;
  const coordY = pinData.virtual_coord?.y ?? pinData.y ?? 0;

  return `
    <div class="flex flex-row items-stretch gap-3 w-full">
      <!-- Cột Bên Trái: Thông tin chi tiết + Khung Chữ ký đã ký -->
      <div class="flex-1 min-w-0 flex flex-col justify-between gap-2">
        <div class="space-y-1">
          <div class="flex items-start justify-between gap-1.5">
            <h3 class="font-bold text-base text-white truncate leading-snug">${pinData.character_name}</h3>
            <div class="flex items-center gap-1 shrink-0">
              ${categoryBadge}
              ${verifiedBadge}
            </div>
          </div>
          <p class="text-xs text-slate-300 truncate">📖 <span class="text-slate-100 font-medium">${pinData.work_title}</span></p>
          <p class="text-xs text-indigo-400 font-medium truncate">👤 <span class="text-white">${pinData.cosplayer_name}</span></p>
          ${eventHtml}
          ${messageHtml}
          <p class="text-[10px] text-slate-400 font-mono pt-1">Tọa độ: <span class="text-amber-400">(${Number(coordX).toFixed(1)}, ${Number(coordY).toFixed(1)})</span></p>
        </div>

        <!-- Khung Chữ ký đã ký -->
        ${buildSignatureBoxHtml(pinData, backendOrigin)}
      </div>

      <!-- Cột Bên Phải: Hiển thị trọn vẹn Hình ảnh tác phẩm / Placeholder nghệ thuật -->
      ${buildRightMediaColumnHtml(pinData, backendOrigin, isPanel)}
    </div>
  `;
}

/**
 * Hiển thị danh sách Cụm tròn trong Left Panel
 */
function renderClusterToPanel(clusterItem, backendOrigin) {
  const itemsListHtml = clusterItem.items.map((p, idx) => `
    <li class="btn-cluster-panel-item flex items-center gap-2.5 p-2 rounded-xl bg-slate-950/60 hover:bg-slate-800/90 hover:border-indigo-500/50 active:scale-[0.99] border border-slate-800 transition-all duration-150 cursor-pointer" data-idx="${idx}">
      ${buildClusterThumbnailHtml(p, backendOrigin)}
      <div class="min-w-0 flex-1">
        <div class="flex items-center justify-between gap-1">
          <p class="text-xs font-semibold text-white truncate">${p.character_name}</p>
          ${p.is_verified ? '<span class="text-[9px] text-amber-400 font-bold">✓</span>' : ''}
        </div>
        <p class="text-[11px] text-slate-400 truncate">${p.cosplayer_name} • ${p.work_title}</p>
      </div>
      <span class="text-xs text-slate-500 font-bold">›</span>
    </li>
  `).join('');

  const clusterHtml = `
    <div class="space-y-3">
      <div class="flex items-center justify-between bg-slate-950/70 p-2.5 rounded-xl border border-slate-800">
        <div>
          <span class="text-xs font-bold text-rose-500">Cụm ${clusterItem.count} Tác phẩm</span>
          <p class="text-[10px] text-slate-400">Tọa độ: (${Number(clusterItem.center.x).toFixed(1)}, ${Number(clusterItem.center.y).toFixed(1)})</p>
        </div>
        <button type="button" class="btn-zoom-cluster bg-slate-800 text-slate-100 border border-slate-600 shadow-sm hover:bg-slate-700 hover:border-indigo-400 hover:text-white active:bg-indigo-950 active:border-indigo-500 active:text-indigo-200 active:scale-95 transition-all duration-150 ease-out cursor-pointer text-xs px-2.5 py-1 rounded-lg font-medium" data-lat="${clusterItem.center.y}" data-lng="${clusterItem.center.x}">
          🔍 Phóng to +
        </button>
      </div>

      <p class="text-[11px] text-slate-400">Nhấn vào tác phẩm bên dưới để xem chi tiết:</p>
      <ul class="space-y-1.5 max-h-[calc(100vh-270px)] overflow-y-auto pr-1">
        ${itemsListHtml}
      </ul>
    </div>
  `;

  openLeftPanel(clusterHtml, `📍 Cụm ${clusterItem.count} Tác phẩm`);

  // Bắt sự kiện khi click vào từng item trong Cụm
  document.querySelectorAll('.btn-cluster-panel-item').forEach(itemEl => {
    itemEl.addEventListener('click', () => {
      const idx = parseInt(itemEl.getAttribute('data-idx'), 10);
      const selectedPin = clusterItem.items[idx];
      showPinInPanelFromCluster(clusterItem, selectedPin, backendOrigin);
    });
  });
}

function showPinInPanelFromCluster(clusterItem, pinData, backendOrigin) {
  const backBtnHtml = `
    <button type="button" class="btn-back-to-cluster mb-2.5 text-xs text-indigo-400 hover:text-indigo-300 active:text-indigo-200 font-medium flex items-center gap-1 cursor-pointer transition-colors duration-150">
      ← Quay lại danh sách cụm (${clusterItem.count})
    </button>
  `;
  const detailCardHtml = buildSinglePinHorizontalCard(pinData, backendOrigin, true);
  const fullHtml = backBtnHtml + detailCardHtml;

  openLeftPanel(fullHtml, `📍 ${pinData.character_name}`);

  const btnBack = document.querySelector('.btn-back-to-cluster');
  if (btnBack) {
    btnBack.onclick = () => {
      renderClusterToPanel(clusterItem, backendOrigin);
    };
  }
}

// ==========================================
// 6. Render Cụm & Pin lên Bản đồ Leaflet
// ==========================================

function renderClustersOnMap(clusters) {
  if (!Array.isArray(clusters) || clusters.length === 0) return;

  const backendOrigin = API_BASE_URL.replace('/api/v1', '');

  clusters.forEach(item => {
    if (typeof item.items === 'string') {
      try {
        item.items = JSON.parse(item.items);
      } catch {
        item.items = [];
      }
    }
    if (!Array.isArray(item.items)) item.items = [];

    const latLng = [item.center.y, item.center.x];

    if (item.type === 'cluster') {
      // A. Cụm tròn (Cluster Marker)
      const dynamicSize = Math.min(36 + item.count * 4, 72);
      const clusterIcon = L.divIcon({
        html: `<div class="cluster-marker cursor-pointer" style="width:${dynamicSize}px; height:${dynamicSize}px;">${item.count}</div>`,
        className: 'custom-cluster-icon',
        iconSize: [dynamicSize, dynamicSize],
        iconAnchor: [dynamicSize / 2, dynamicSize / 2]
      });

      const clusterMarker = L.marker(latLng, { icon: clusterIcon });

      const itemsListHtml = item.items
        .map(p => `
          <li class="flex items-center gap-2 py-1.5 border-b border-slate-800 last:border-none">
            ${buildClusterThumbnailHtml(p, backendOrigin)}
            <div class="min-w-0 flex-1">
              <p class="text-xs font-semibold text-white truncate">${p.character_name}</p>
              <p class="text-[11px] text-slate-400 truncate">${p.cosplayer_name} • ${p.work_title}</p>
            </div>
          </li>
        `)
        .join('');

      const clusterPopup = `
        <div class="p-3 bg-slate-900 text-white rounded-xl w-[260px]">
          <div class="flex items-center justify-between mb-2">
            <h3 class="font-bold text-sm text-rose-500">Cụm ${item.count} Tác phẩm</h3>
            <button type="button" class="btn-zoom-cluster bg-slate-800 text-slate-100 border border-slate-600 shadow-sm hover:bg-slate-700 hover:border-indigo-400 hover:text-white active:bg-indigo-950 active:border-indigo-500 active:text-indigo-200 active:scale-95 transition-all duration-150 ease-out cursor-pointer text-xs px-2 py-0.5 rounded" data-lat="${latLng[0]}" data-lng="${latLng[1]}">
              Phóng to +
            </button>
          </div>
          <ul class="max-h-44 overflow-y-auto pr-1">
            ${itemsListHtml}
          </ul>
        </div>
      `;

      clusterMarker.bindPopup(clusterPopup, { maxWidth: 280, className: 'dark-popup' });

      // Click vào Cụm: Phụ thuộc vào currentViewMode
      clusterMarker.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        clearDraftPin();
        closeAllDropdowns();

        if (currentViewMode === 'panel') {
          map.closePopup();
          renderClusterToPanel(item, backendOrigin);
        } else {
          closeLeftPanel();
          clusterMarker.openPopup();
        }
      });

      markersLayerGroup.addLayer(clusterMarker);

    } else {
      // B. Chấm tròn đơn lẻ (Single Pin Marker)
      const pinData = item.items[0] || {};

      const pinIcon = L.divIcon({
        html: `
          <div class="relative group cursor-pointer">
            <div class="w-6 h-6 bg-amber-400 border-2 border-white rounded-full shadow-lg transition-transform group-hover:scale-125"></div>
            <div class="absolute -bottom-1 left-1/2 -translate-x-1/2 w-2 h-2 bg-amber-400 rotate-45 border-r border-b border-white"></div>
          </div>
        `,
        className: 'custom-single-icon',
        iconSize: [24, 24],
        iconAnchor: [12, 24]
      });

      const singleMarker = L.marker(latLng, { icon: pinIcon });

      // Thẻ hiển thị bố cục 2 cột ngang cho Popup
      const horizontalCardHtml = buildSinglePinHorizontalCard(pinData, backendOrigin, false);

      const popupContent = `
        <div class="p-3 bg-slate-900 text-white rounded-2xl w-[390px] sm:w-[420px] shadow-2xl">
          ${horizontalCardHtml}
        </div>
      `;

      singleMarker.bindPopup(popupContent, {
        maxWidth: 460,
        minWidth: 380,
        className: 'dark-popup'
      });

      // Click vào Pin đơn lẻ: Phụ thuộc vào currentViewMode
      singleMarker.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        clearDraftPin();
        closeAllDropdowns();

        if (currentViewMode === 'panel') {
          map.closePopup();
          const panelCardHtml = buildSinglePinHorizontalCard(pinData, backendOrigin, true);
          openLeftPanel(panelCardHtml, `📍 ${pinData.character_name}`);
        } else {
          closeLeftPanel();
          singleMarker.openPopup();
        }
      });

      markersLayerGroup.addLayer(singleMarker);
    }
  });
}

async function loadMapClusters() {
  const btnReload = document.getElementById('btn-reload');
  if (btnReload) {
    btnReload.innerText = 'Đang tải...';
    btnReload.disabled = true;
  }

  markersLayerGroup.clearLayers();

  try {
    const url = buildClusterApiUrl();
    const response = await fetch(url);
    if (!response.ok) throw new Error(`Lỗi API: ${response.status}`);

    const clustersData = await response.json();
    renderClustersOnMap(clustersData);
  } catch (error) {
    console.error('Lỗi nạp dữ liệu bản đồ:', error);
  } finally {
    if (btnReload) {
      btnReload.innerHTML = '<span>🔄</span><span>Tải lại</span>';
      btnReload.disabled = false;
    }
  }
}

// ==========================================
// 7. Custom Dropdown & Logic Bộ lọc Thực tế (Action 2 & 3)
// ==========================================

function closeAllDropdowns() {
  document.querySelectorAll('.custom-dropdown-menu').forEach(menu => {
    menu.classList.remove('opacity-100', 'translate-y-0', 'pointer-events-auto', 'visible');
    menu.classList.add('opacity-0', '-translate-y-2.5', 'pointer-events-none', 'invisible');
  });
  document.querySelectorAll('.dropdown-chevron').forEach(chevron => {
    chevron.classList.remove('rotate-180');
  });
}

function toggleDropdown(menuEl, chevronEl) {
  const isOpen = menuEl.classList.contains('visible');
  closeAllDropdowns();

  if (!isOpen) {
    menuEl.classList.remove('opacity-0', '-translate-y-2.5', 'pointer-events-none', 'invisible');
    menuEl.classList.add('opacity-100', 'translate-y-0', 'pointer-events-auto', 'visible');
    if (chevronEl) chevronEl.classList.add('rotate-180');
  }
}

async function loadFilterOptions() {
  try {
    const res = await fetch(`${API_BASE_URL}/pins/filters`);
    if (!res.ok) return;
    filterData = await res.json();
    updateFilterDatalists();
    renderSubFilterUI();
  } catch (err) {
    console.warn('Lỗi nạp danh mục bộ lọc từ CSDL:', err);
  }
}

function updateFilterDatalists() {
  const eventDatalist = document.getElementById('event-name-datalist');
  const workDatalist = document.getElementById('work-title-datalist');

  if (eventDatalist && filterData.events) {
    eventDatalist.innerHTML = filterData.events
      .map(ev => `<option value="${ev}"></option>`).join('');
  }
  if (workDatalist && filterData.works) {
    workDatalist.innerHTML = filterData.works
      .map(w => `<option value="${w}"></option>`).join('');
  }
}

const MODE_LABELS = {
  ALL: '🌐 Tất cả tác phẩm',
  EVENT: '🎪 Map Sự kiện Fest',
  IP: '📖 Map Tác phẩm IP',
  COSPLAYER: '👤 Map Cosplayer (A-Z)'
};

function setupMainModeDropdown() {
  const trigger = document.getElementById('map-mode-trigger');
  const menu = document.getElementById('map-mode-menu');
  const chevron = trigger ? trigger.querySelector('.dropdown-chevron') : null;
  const label = document.getElementById('map-mode-label');

  if (!trigger || !menu) return;

  trigger.addEventListener('click', (e) => {
    e.stopPropagation();
    toggleDropdown(menu, chevron);
  });

  menu.querySelectorAll('.custom-dropdown-item').forEach(item => {
    item.addEventListener('click', (e) => {
      e.stopPropagation();
      const val = item.getAttribute('data-value');
      activeFilter.mode = val;
      activeFilter.value = '';

      if (label) label.textContent = MODE_LABELS[val] || val;

      // Cập nhật trạng thái active trong menu
      menu.querySelectorAll('.custom-dropdown-item').forEach(i => {
        const isCurrent = i.getAttribute('data-value') === val;
        const checkIcon = i.querySelector('.check-icon');
        if (isCurrent) {
          i.classList.add('bg-indigo-600/20', 'text-indigo-300', 'font-semibold');
          if (checkIcon) checkIcon.classList.remove('hidden');
        } else {
          i.classList.remove('bg-indigo-600/20', 'text-indigo-300', 'font-semibold');
          if (checkIcon) checkIcon.classList.add('hidden');
        }
      });

      closeAllDropdowns();
      renderSubFilterUI();
      loadMapClusters();
    });
  });
}

function renderSubFilterUI() {
  const container = document.getElementById('sub-filter-container');
  if (!container) return;

  if (activeFilter.mode === 'ALL') {
    container.classList.remove('opacity-100', 'translate-y-0', 'pointer-events-auto', 'visible');
    container.classList.add('opacity-0', '-translate-y-2.5', 'pointer-events-none', 'invisible');
    setTimeout(() => {
      if (activeFilter.mode === 'ALL') container.innerHTML = '';
    }, 200);
    return;
  }

  let items = [];
  let defaultLabel = '';
  let iconPrefix = '';

  if (activeFilter.mode === 'EVENT') {
    items = filterData.events || [];
    defaultLabel = `Tất cả sự kiện (${items.length})`;
    iconPrefix = '🎪';
  } else if (activeFilter.mode === 'IP') {
    items = filterData.works || [];
    defaultLabel = `Tất cả tác phẩm (${items.length})`;
    iconPrefix = '📖';
  } else if (activeFilter.mode === 'COSPLAYER') {
    items = filterData.letters || [];
    defaultLabel = `Tất cả ký tự (${items.length})`;
    iconPrefix = '🔤';
  }

  const currentDisplay = activeFilter.value
    ? `${iconPrefix} ${activeFilter.value}`
    : defaultLabel;

  const optionsHtml = `
    <button type="button" class="sub-dropdown-item w-full text-left px-3 py-2 rounded-lg text-sm text-slate-200 flex items-center justify-between transition-colors duration-150 cursor-pointer hover:bg-indigo-600/30 hover:text-white active:bg-indigo-600 active:text-white ${!activeFilter.value ? 'bg-indigo-600/20 text-indigo-300 font-semibold' : ''}" data-value="">
      <span>${defaultLabel}</span>
      <span class="sub-check-icon ${!activeFilter.value ? '' : 'hidden'} text-indigo-400">✓</span>
    </button>
    ${items.map(val => `
      <button type="button" class="sub-dropdown-item w-full text-left px-3 py-2 rounded-lg text-sm text-slate-200 flex items-center justify-between transition-colors duration-150 cursor-pointer hover:bg-indigo-600/30 hover:text-white active:bg-indigo-600 active:text-white ${activeFilter.value === val ? 'bg-indigo-600/20 text-indigo-300 font-semibold' : ''}" data-value="${val}">
        <span class="truncate pr-2">${iconPrefix} ${val}</span>
        <span class="sub-check-icon ${activeFilter.value === val ? '' : 'hidden'} text-indigo-400">✓</span>
      </button>
    `).join('')}
  `;

  container.innerHTML = `
    <div id="sub-filter-dropdown" class="relative custom-dropdown">
      <button id="sub-filter-trigger" type="button" class="custom-dropdown-trigger bg-slate-800 text-slate-100 border border-slate-600 shadow-sm hover:bg-slate-700 hover:border-indigo-400 hover:text-white active:bg-indigo-950 active:border-indigo-500 active:text-indigo-200 active:scale-95 transition-all duration-150 ease-out cursor-pointer text-sm rounded-xl px-3 py-2 flex items-center gap-2">
        <span id="sub-filter-label" class="flex items-center gap-1.5 whitespace-nowrap truncate max-w-[160px] sm:max-w-[200px]">
          ${currentDisplay}
        </span>
        <svg class="dropdown-chevron w-4 h-4 text-slate-400 transition-transform duration-200 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M19 9l-7 7-7-7"></path>
        </svg>
      </button>

      <div id="sub-filter-menu" class="custom-dropdown-menu absolute top-full left-0 mt-2 min-w-[220px] max-w-[280px] max-h-64 overflow-y-auto rounded-xl bg-slate-900/95 backdrop-blur-md border border-slate-700 shadow-2xl p-1.5 z-[1100] opacity-0 -translate-y-2.5 pointer-events-none invisible transition-all duration-200 ease-out">
        ${optionsHtml}
      </div>
    </div>
  `;

  // Hiển thị với hiệu ứng Fade-Down
  container.classList.remove('opacity-0', '-translate-y-2.5', 'pointer-events-none', 'invisible');
  container.classList.add('opacity-100', 'translate-y-0', 'pointer-events-auto', 'visible');

  // Gắn sự kiện cho Sub-filter Dropdown
  const subTrigger = document.getElementById('sub-filter-trigger');
  const subMenu = document.getElementById('sub-filter-menu');
  const subChevron = subTrigger ? subTrigger.querySelector('.dropdown-chevron') : null;
  const subLabel = document.getElementById('sub-filter-label');

  if (subTrigger && subMenu) {
    subTrigger.addEventListener('click', (e) => {
      e.stopPropagation();
      toggleDropdown(subMenu, subChevron);
    });

    subMenu.querySelectorAll('.sub-dropdown-item').forEach(item => {
      item.addEventListener('click', (e) => {
        e.stopPropagation();
        const val = item.getAttribute('data-value');
        activeFilter.value = val;

        if (subLabel) {
          subLabel.textContent = val ? `${iconPrefix} ${val}` : defaultLabel;
        }

        closeAllDropdowns();
        loadMapClusters();
      });
    });
  }
}

// ==========================================
// 8. Quản lý Modal Upload & Chữ ký tay Canvas (Fade + Zoom)
// ==========================================

function openModal(x, y) {
  document.getElementById('input-coord-x').value = x.toFixed(1);
  document.getElementById('input-coord-y').value = y.toFixed(1);
  updateFilterDatalists();
  if (signatureCanvasInstance) signatureCanvasInstance.clear();

  const modal = document.getElementById('upload-modal');
  const card = document.getElementById('upload-modal-card');
  if (!modal || !card) return;

  // Hiệu ứng Fade in + Zoom in mượt mà
  modal.classList.remove('opacity-0', 'pointer-events-none', 'invisible');
  modal.classList.add('opacity-100', 'pointer-events-auto', 'visible');

  card.classList.remove('opacity-0', 'scale-90', 'translate-y-3');
  card.classList.add('opacity-100', 'scale-100', 'translate-y-0');
}

function closeModal() {
  const modal = document.getElementById('upload-modal');
  const card = document.getElementById('upload-modal-card');

  if (modal && card) {
    // Hiệu ứng Fade out + Zoom out mượt mà
    modal.classList.remove('opacity-100', 'pointer-events-auto', 'visible');
    modal.classList.add('opacity-0', 'pointer-events-none', 'invisible');

    card.classList.remove('opacity-100', 'scale-100', 'translate-y-0');
    card.classList.add('opacity-0', 'scale-90', 'translate-y-3');
  }

  // Chờ 250ms cho animation hoàn tất mới reset form
  setTimeout(() => {
    document.getElementById('upload-pin-form').reset();
    if (signatureCanvasInstance) signatureCanvasInstance.clear();
  }, 250);

  clearDraftPin();
}

// Delegated click cho nút "Phóng to +" bên trong Popup Cụm tròn
document.addEventListener('click', (e) => {
  if (e.target && e.target.classList.contains('btn-zoom-cluster')) {
    const lat = parseFloat(e.target.getAttribute('data-lat'));
    const lng = parseFloat(e.target.getAttribute('data-lng'));
    map.closePopup();
    map.setView([lat, lng], Math.min(map.getZoom() + 1.5, 3));
  }
});

// Tự động cập nhật phân cụm khi người dùng Zoom bản đồ
map.on('zoomend', () => {
  loadMapClusters();
});

// Click ra ngoài đóng toàn bộ Custom Dropdowns
document.addEventListener('click', (e) => {
  if (!e.target.closest('.custom-dropdown')) {
    closeAllDropdowns();
  }
});

// Nhấn phím Escape đóng Dropdown, Modal, Panel hoặc Draft Pin
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') {
    closeAllDropdowns();
    closeModal();
    closeLeftPanel();
    clearDraftPin();
  }
});

// Click vào vùng backdrop tối ngoài modal card để đóng modal
document.getElementById('upload-modal')?.addEventListener('click', (e) => {
  if (e.target.id === 'upload-modal') {
    closeModal();
  }
});

// ==========================================
// 9. Khởi chạy Ứng dụng (DOMContentLoaded)
// ==========================================

document.addEventListener('DOMContentLoaded', () => {
  signatureCanvasInstance = new SignatureCanvas('signature-canvas');

  // Khởi tạo Custom Dropdown chọn chế độ bản đồ
  setupMainModeDropdown();

  // Toggle View Mode (Bong bóng vs Left Panel)
  const btnViewPopup = document.getElementById('view-mode-popup');
  const btnViewPanel = document.getElementById('view-mode-panel');
  if (btnViewPopup) btnViewPopup.addEventListener('click', () => setViewMode('popup'));
  if (btnViewPanel) btnViewPanel.addEventListener('click', () => setViewMode('panel'));

  // Nút đóng Left Panel
  const btnClosePanel = document.getElementById('btn-close-left-panel');
  if (btnClosePanel) btnClosePanel.addEventListener('click', closeLeftPanel);

  // Chọn màu từ Palette cố định
  document.querySelectorAll('.btn-color-swatch').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.btn-color-swatch').forEach(b => b.classList.remove('ring-2', 'ring-brand-500'));
      btn.classList.add('ring-2', 'ring-brand-500');
      signatureCanvasInstance.setColor(btn.getAttribute('data-color'));
    });
  });

  // Chọn màu từ Custom Color Picker
  const customColorInput = document.getElementById('input-custom-color');
  if (customColorInput) {
    customColorInput.addEventListener('input', (e) => {
      document.querySelectorAll('.btn-color-swatch').forEach(b => b.classList.remove('ring-2', 'ring-brand-500'));
      signatureCanvasInstance.setColor(e.target.value);
    });
  }

  document.getElementById('btn-clear-canvas').addEventListener('click', () => {
    signatureCanvasInstance.clear();
  });

  document.getElementById('btn-close-modal').addEventListener('click', closeModal);
  document.getElementById('btn-reload').addEventListener('click', loadMapClusters);

  // Submit Form Upload Pin
  document.getElementById('upload-pin-form').addEventListener('submit', async (e) => {
    e.preventDefault();

    if (signatureCanvasInstance.isEmpty()) {
      alert('Vui lòng ký tên trên khung Canvas!');
      return;
    }

    const btnSubmit = document.getElementById('btn-submit-pin');
    btnSubmit.disabled = true;
    btnSubmit.innerText = 'Đang xử lý...';

    try {
      const formData = new FormData();
      const fileInput = document.getElementById('input-file');

      if (fileInput.files.length > 0) {
        formData.append('file', fileInput.files[0]);
      }

      const characterName = document.getElementById('input-character-name').value.trim();
      const workTitle = document.getElementById('input-work-title').value.trim();
      const eventName = document.getElementById('input-event-name')?.value.trim();
      const message = document.getElementById('input-message')?.value.trim();

      formData.append('signature_canvas', signatureCanvasInstance.toBase64());
      formData.append('cosplayer_id', crypto.randomUUID());
      formData.append('cosplayer_name', document.getElementById('input-cosplayer-name').value.trim());
      formData.append('character_name', characterName);
      formData.append('work_title', workTitle);
      formData.append('work_category', document.getElementById('input-work-category').value);
      formData.append('coord_x', document.getElementById('input-coord-x').value);
      formData.append('coord_y', document.getElementById('input-coord-y').value);

      if (eventName) {
        formData.append('event_name', eventName);
      }
      if (message) {
        formData.append('message', message);
      }

      const response = await fetch(`${API_BASE_URL}/pins/upload`, {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        const detailedError = await parseApiError(response);
        throw new Error(detailedError);
      }

      const createdPin = await response.json();

      alert(`🎉 Đăng tải thành công Pin: ${createdPin.character_name}!`);
      closeModal();
      clearDraftPin();

      // Cập nhật lại danh sách bộ lọc thực tế và nạp lại bản đồ
      await loadFilterOptions();
      await loadMapClusters();

    } catch (error) {
      alert(`Lỗi:\n${error.message}`);
    } finally {
      btnSubmit.disabled = false;
      btnSubmit.innerText = 'Khởi tạo Pin & Lưu Chữ Ký';
    }
  });

  // Khởi động dữ liệu ban đầu
  loadFilterOptions();
  loadMapClusters();
});
