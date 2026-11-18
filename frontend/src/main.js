import L from 'leaflet';
import 'leaflet/dist/leaflet.css';
import { SignatureCanvas } from './signatureCanvas.js';

const API_BASE_URL = 'http://localhost:8000/api/v1';

// 1. Khởi tạo Bản đồ Leaflet 2D không-địa-lý (L.CRS.Simple)
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
let signatureCanvasInstance = null;

// Bộ nhớ danh sách gợi ý cho Combobox Nhân vật & Tác phẩm
const characterSet = new Set();
const workTitleSet = new Set();

function updateComboboxDatalists() {
  const charDatalist = document.getElementById('character-datalist');
  const workDatalist = document.getElementById('work-title-datalist');

  if (charDatalist) {
    charDatalist.innerHTML = Array.from(characterSet)
      .map(item => `<option value="${item}"></option>`).join('');
  }
  if (workDatalist) {
    workDatalist.innerHTML = Array.from(workTitleSet)
      .map(item => `<option value="${item}"></option>`).join('');
  }
}

/**
 * Trích xuất thông điệp lỗi chi tiết từ FastAPI (hỗ trợ cả string lẫn mảng 422 validation)
 */
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
 * Tạo khung hiển thị hình ảnh hoặc Placeholder nghệ thuật mặc định cho Pin đơn lẻ
 */
function buildPinMediaHtml(pinData, backendOrigin) {
  const isPlaceholder = !pinData.media_url || pinData.media_url.includes('/placeholders/');

  if (isPlaceholder) {
    const initialChar = (pinData.character_name || '?').charAt(0).toUpperCase();
    return `
      <div class="relative w-full h-36 rounded-lg mb-2 overflow-hidden border border-amber-500/30 bg-gradient-to-br from-slate-900 via-indigo-950 to-rose-950 flex flex-col items-center justify-center p-3 text-center">
        <div class="absolute inset-0 opacity-20 bg-[radial-gradient(#fbbf24_1px,transparent_1px)] [background-size:12px_12px]"></div>
        <div class="relative w-12 h-12 rounded-full border border-amber-400/60 bg-slate-950/60 flex items-center justify-center mb-1.5 shadow-inner">
          <span class="text-lg font-serif font-bold text-amber-300">${initialChar}</span>
        </div>
        <span class="relative text-[10px] uppercase tracking-widest text-amber-300/90 font-semibold">✦ Heritage Pin ✦</span>
        <span class="relative text-[9px] text-slate-400 mt-0.5">Chứng thực chữ ký số</span>
      </div>
    `;
  }

  return `
    <div class="relative overflow-hidden rounded-lg mb-2 border border-slate-700 bg-slate-950">
      <img 
        src="${backendOrigin}${pinData.media_url}" 
        alt="${pinData.character_name}"
        class="w-full h-36 object-contain bg-slate-950" 
      />
    </div>
  `;
}

/**
 * Tạo ảnh thumbnail thu nhỏ (hoặc biểu tượng nghệ thuật) trong danh sách Cụm tròn
 */
function buildClusterThumbnailHtml(pinData, backendOrigin) {
  const isPlaceholder = !pinData.media_url || pinData.media_url.includes('/placeholders/');

  if (isPlaceholder) {
    const initialChar = (pinData.character_name || '?').charAt(0).toUpperCase();
    return `
      <div class="w-8 h-8 rounded border border-amber-500/40 bg-gradient-to-br from-slate-900 via-indigo-950 to-rose-950 flex items-center justify-center shrink-0">
        <span class="text-xs font-serif font-bold text-amber-300">${initialChar}</span>
      </div>
    `;
  }

  return `<img src="${backendOrigin}${pinData.media_url}" alt="${pinData.character_name}" class="w-8 h-8 rounded object-cover bg-slate-950 shrink-0" />`;
}

/**
 * Xây dựng URL truy vấn phân cụm với bán kính eps co giãn theo mức Zoom
 */
function buildClusterApiUrl() {
  const currentZoom = map.getZoom();
  // Zoom càng sâu thì eps càng nhỏ để tự động tách cụm thành các chấm đơn lẻ
  const dynamicEps = Math.max(5, 100 / Math.pow(2, currentZoom)).toFixed(1);

  const params = new URLSearchParams({
    eps: dynamicEps,
    min_points: '2'
  });

  return `${API_BASE_URL}/pins/clusters?${params.toString()}`;
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
      btnReload.innerText = 'Tải lại Bản đồ';
      btnReload.disabled = false;
    }
  }
}

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

    // Lưu tên nhân vật & tác phẩm vào Combobox
    item.items.forEach(p => {
      if (p.character_name) characterSet.add(p.character_name);
      if (p.work_title) workTitleSet.add(p.work_title);
    });

    if (item.type === 'cluster') {
      // ==========================================
      // A. Cụm tròn (Cluster Marker)
      // ==========================================
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
            <div class="min-w-0">
              <p class="text-xs font-semibold text-white truncate">${p.character_name}</p>
              <p class="text-[11px] text-slate-400 truncate">${p.cosplayer_name} • ${p.work_title}</p>
            </div>
          </li>
        `)
        .join('');

      const clusterPopup = `
        <div class="p-3 bg-slate-900 text-white rounded-xl w-[240px]">
          <div class="flex items-center justify-between mb-2">
            <h3 class="font-bold text-sm text-brand-500">Cụm ${item.count} Tác phẩm</h3>
            <button type="button" class="btn-zoom-cluster text-[11px] bg-slate-800 hover:bg-slate-700 text-amber-400 px-2 py-0.5 rounded cursor-pointer" data-lat="${latLng[0]}" data-lng="${latLng[1]}">
              Phóng to +
            </button>
          </div>
          <ul class="max-h-44 overflow-y-auto pr-1">
            ${itemsListHtml}
          </ul>
        </div>
      `;

      clusterMarker.bindPopup(clusterPopup, { maxWidth: 260, className: 'dark-popup' });

      // Chặn nổi bọt sự kiện click để không mở nhầm Modal Upload
      clusterMarker.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        clusterMarker.openPopup();
      });

      markersLayerGroup.addLayer(clusterMarker);

    } else {
      // ==========================================
      // B. Chấm tròn đơn lẻ (Single Pin Marker)
      // ==========================================
      const pinData = item.items[0];
      const verifiedBadge = pinData.is_verified
        ? `<span class="inline-block bg-amber-500/20 text-amber-400 border border-amber-500/40 text-[10px] px-1.5 py-0.5 rounded font-semibold shrink-0">✓ Verified</span>`
        : '';

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

      const popupContent = `
        <div class="p-2.5 bg-slate-900 text-white rounded-xl w-[230px]">
          ${buildPinMediaHtml(pinData, backendOrigin)}
          <div class="flex items-center justify-between gap-1 mb-1">
            <h3 class="font-bold text-sm text-white truncate">${pinData.character_name}</h3>
            ${verifiedBadge}
          </div>
          <p class="text-xs text-slate-400 truncate mb-1">📖 ${pinData.work_title}</p>
          <p class="text-xs text-brand-500 font-medium truncate">👤 ${pinData.cosplayer_name}</p>
          <p class="text-[10px] text-slate-500 font-mono mt-1.5 pt-1.5 border-t border-slate-800">
            Tọa độ: (${Number(item.center.x).toFixed(1)}, ${Number(item.center.y).toFixed(1)})
          </p>
        </div>
      `;

      singleMarker.bindPopup(popupContent, { maxWidth: 260, className: 'dark-popup' });

      // Chặn nổi bọt sự kiện click để không mở nhầm Modal Upload
      singleMarker.on('click', (e) => {
        L.DomEvent.stopPropagation(e);
        singleMarker.openPopup();
      });

      markersLayerGroup.addLayer(singleMarker);
    }
  });

  updateComboboxDatalists();
}

// Xử lý nút "Phóng to +" bên trong Popup Cụm tròn
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

// ==========================================
// 3. Quản lý Modal Upload & Chữ ký tay Canvas
// ==========================================
function openModal(x, y) {
  document.getElementById('input-coord-x').value = x.toFixed(1);
  document.getElementById('input-coord-y').value = y.toFixed(1);
  document.getElementById('upload-modal').classList.remove('hidden');
  updateComboboxDatalists();
  if (signatureCanvasInstance) signatureCanvasInstance.clear();
}

function closeModal() {
  document.getElementById('upload-modal').classList.add('hidden');
  document.getElementById('upload-pin-form').reset();
  if (signatureCanvasInstance) signatureCanvasInstance.clear();
}

// Click vào vùng trống trên bản đồ để mở Modal tạo Pin mới
map.on('click', (e) => {
  openModal(e.latlng.lng, e.latlng.lat);
});

document.addEventListener('DOMContentLoaded', () => {
  signatureCanvasInstance = new SignatureCanvas('signature-canvas');

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

      formData.append('signature_canvas', signatureCanvasInstance.toBase64());
      formData.append('cosplayer_id', crypto.randomUUID());
      formData.append('cosplayer_name', document.getElementById('input-cosplayer-name').value);
      formData.append('character_name', characterName);
      formData.append('work_title', workTitle);
      formData.append('work_category', document.getElementById('input-work-category').value);
      formData.append('coord_x', document.getElementById('input-coord-x').value);
      formData.append('coord_y', document.getElementById('input-coord-y').value);

      const response = await fetch(`${API_BASE_URL}/pins/upload`, {
        method: 'POST',
        body: formData
      });

      if (!response.ok) {
        const detailedError = await parseApiError(response);
        throw new Error(detailedError);
      }

      const createdPin = await response.json();

      characterSet.add(characterName);
      workTitleSet.add(workTitle);
      updateComboboxDatalists();

      alert(`🎉 Đăng tải thành công Pin: ${createdPin.character_name}!`);
      closeModal();
      loadMapClusters();

    } catch (error) {
      alert(`Lỗi:\n${error.message}`);
    } finally {
      btnSubmit.disabled = false;
      btnSubmit.innerText = 'Khởi tạo Pin & Lưu Chữ Ký';
    }
  });

  loadMapClusters();
});