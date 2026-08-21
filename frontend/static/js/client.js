let socket = null;
let currentItem = null;
let videoStream = null;
const video = document.getElementById('video-preview');
const canvas = document.getElementById('scan-canvas');
const ctx = canvas.getContext('2d', { willReadFrequently: true });

const STORAGE_KEY = 'lagerist_client_session';

function $(id) { return document.getElementById(id); }

function showStatus(msg, type = 'info') {
  const el = $('status');
  el.textContent = msg;
  el.className = `status ${type}`;
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 4000);
}

function saveSession(data) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({
      ...data,
      saved_at: Date.now(),
    }));
  } catch (e) {
    console.warn('localStorage not available', e);
  }
}

function loadSession() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const data = JSON.parse(raw);
    if (Date.now() - data.saved_at > 8 * 60 * 60 * 1000) {
      clearSession();
      return null;
    }
    return data;
  } catch (e) {
    return null;
  }
}

function clearSession() {
  try {
    localStorage.removeItem(STORAGE_KEY);
  } catch (e) {}
}

function getDisplayName() {
  const fromInput = $('client-name').value.trim();
  if (fromInput) return fromInput;
  const saved = loadSession();
  return saved ? saved.client_name : '';
}

function getCurrentTime() {
  const now = new Date();
  return `${String(now.getHours()).padStart(2, '0')}:${String(now.getMinutes()).padStart(2, '0')}`;
}

function formatDesc(template, name, time) {
  if (!name) return `${template} — ${time}`;
  return `${template} — ${name}, ${time}`;
}

const DESC_TEMPLATES = {
  neubetankung: (name, time) => {
    if (!name) return `Aktuell läuft eine Neubetankung, gestartet um ${time}`;
    return `Aktuell läuft eine Neubetankung, gestartet von ${name} um ${time}`;
  },
  erstbetankung: (name, time) => formatDesc('Erstbetankung daher sind keine weiteren einstellungen von nöten', name, time),
  test: (name, time) => formatDesc('Das ist ein Test aufgrund von: ', name, time),
  firmware: (name, time) => formatDesc('Aktuell läuft nur ein Firmware Update', name, time),
  firmware_nb: (name, time) => formatDesc('Aktuell läuft hier ein Firmware Update und eine Neubetankung', name, time),
};

function initDescTemplates() {
  document.querySelectorAll('.desc-template').forEach(btn => {
    btn.addEventListener('click', () => {
      const key = btn.dataset.text;
      if (DESC_TEMPLATES[key]) {
        $('item-desc').value = DESC_TEMPLATES[key](getDisplayName(), getCurrentTime());
        $('item-desc').focus();
      }
    });
  });
}

function getHostOrigin() {
  const addr = $('host-address').value.trim();
  return addr || window.location.origin;
}

function connectSocket(auto = false) {
  const origin = getHostOrigin();
  const token = $('session-token').value.trim();
  const name = $('client-name').value.trim() || 'Client';

  if (!token || !origin) {
    if (!auto) showStatus('Host-Adresse und Token erforderlich', 'error');
    return;
  }

  if (socket) socket.disconnect();
  socket = io(origin, { transports: ['websocket', 'polling'], timeout: 10000 });

  socket.on('connect', () => {
    socket.emit('client:join', { token, name });
  });

  socket.on('client:joined', () => {
    showStatus('Verbunden!', 'success');
    saveSession({ host_address: origin, session_token: token, client_name: name });
    $('login-card').classList.add('hidden');
    $('search-card').classList.remove('hidden');
    $('scanner-card').classList.remove('hidden');
    $('photo-fallback').classList.remove('hidden');
  });

  socket.on('session:error', (data) => {
    showStatus(data.message, 'error');
    clearSession();
    if (socket) socket.disconnect();
    $('login-card').classList.remove('hidden');
    $('search-card').classList.add('hidden');
    $('scanner-card').classList.add('hidden');
  });

  socket.on('item:found', (item) => {
    currentItem = item;
    showItem(item);
    stopCamera();
  });

  socket.on('item:not_found', (data) => {
    currentItem = null;
    $('not-found-code').textContent = data.code;
    $('item-card').classList.add('hidden');
    $('not-found-card').classList.remove('hidden');
    $('scanner-card').classList.add('hidden');
  });

  socket.on('item:updated', (item) => {
    if (currentItem && currentItem.code === item.code) {
      currentItem = item;
      showItem(item);
      showStatus('Aktualisiert', 'success');
    }
  });

  socket.on('disconnect', () => {
    showStatus('Verbindung getrennt', 'error');
    setTimeout(() => {
      const saved = loadSession();
      if (saved) {
        $('host-address').value = saved.host_address;
        $('session-token').value = saved.session_token;
        $('client-name').value = saved.client_name;
        connectSocket(true);
      }
    }, 3000);
  });
}

async function startCamera() {
  if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
    showStatus('Kamera nicht verfügbar – nutze Foto-Upload.', 'info');
    $('camera-hint').classList.remove('hidden');
    return;
  }
  try {
    // Try rear camera first, then any camera
    let constraints = { video: { facingMode: { ideal: 'environment' } } };
    try {
      videoStream = await navigator.mediaDevices.getUserMedia(constraints);
    } catch (e) {
      constraints = { video: true };
      videoStream = await navigator.mediaDevices.getUserMedia(constraints);
    }
    video.srcObject = videoStream;
    video.classList.remove('hidden');
    await video.play();
    requestAnimationFrame(scanLoop);
    $('camera-hint').classList.add('hidden');
  } catch (e) {
    console.error(e);
    showStatus('Kamera kann nicht gestartet werden. Nutze Foto-Upload oder manuelle Eingabe.', 'info');
    $('camera-hint').classList.remove('hidden');
    stopCamera();
  }
}

function stopCamera() {
  if (videoStream) {
    videoStream.getTracks().forEach(track => track.stop());
    videoStream = null;
  }
  video.pause();
  video.srcObject = null;
  video.classList.add('hidden');
}

function scanLoop() {
  if (!videoStream || video.paused || video.ended) return;
  if (video.readyState === video.HAVE_ENOUGH_DATA) {
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    ctx.drawImage(video, 0, 0, canvas.width, canvas.height);
    const imageData = ctx.getImageData(0, 0, canvas.width, canvas.height);
    const code = jsQR(imageData.data, imageData.width, imageData.height, { inversionAttempts: 'attemptBoth' });
    if (code && code.data) {
      handleScan(code.data);
      // throttle
      setTimeout(() => requestAnimationFrame(scanLoop), 1200);
      return;
    }
  }
  requestAnimationFrame(scanLoop);
}

function handleScan(raw) {
  let data = raw.trim();
  // If scanned data is a full URL like https://.../client?session=..., extract token
  const urlMatch = data.match(/[?&]session=([A-Za-z0-9_-]+)/);
  if (urlMatch && $('login-card').classList.contains('hidden') === false) {
    // This was the login QR
    $('session-token').value = urlMatch[1];
    $('host-address').value = data.split('?')[0].replace('/client', '');
    connectSocket();
    return;
  }
  if (urlMatch) {
    data = urlMatch[1];
  }
  if (!socket || !socket.connected) {
    showStatus('Nicht verbunden – bitte erst beitreten.', 'error');
    return;
  }
  socket.emit('client:scan', { code: data });
}

function showItem(item) {
  currentItem = item;
  $('edit-code').value = item.code;
  $('item-name').value = item.name || '';
  $('item-category-label').textContent = item.category || 'sonstiges';

  const isLaptop = item.category === 'laptop';
  $('laptop-fields').classList.toggle('hidden', !isLaptop);
  $('desc-templates').classList.toggle('hidden', !isLaptop);
  $('item-quantity').closest('.form-group').style.display = isLaptop ? 'none' : '';
  const unitLabel = $('item-unit').previousElementSibling;
  if (unitLabel) unitLabel.textContent = isLaptop ? 'Zustand' : 'Einheit';

  if (isLaptop) {
    $('item-desc').value = item.description || '';
    if (item.details) {
      $('item-t14-gen').value = item.details.t14_gen || '';
      $('item-owners').value = item.details.owners || '';
      $('item-sina-token').value = item.details.sina_token || '';
      $('item-notes').value = item.details.notes || '';
    } else {
      $('item-t14-gen').value = '';
      $('item-owners').value = '';
      $('item-sina-token').value = '';
      $('item-notes').value = '';
    }
  } else {
    $('item-desc').value = item.description || '';
    $('item-t14-gen').value = '';
    $('item-owners').value = '';
    $('item-sina-token').value = '';
    $('item-notes').value = '';
  }

  renderRmas(item.rmas || []);
  $('item-title').textContent = item.code;
  $('item-card').classList.remove('hidden');
  $('not-found-card').classList.add('hidden');
  $('scanner-card').classList.add('hidden');
}

function renderRmas(rmas) {
  const list = $('rma-list');
  list.innerHTML = '';
  for (const rma of rmas) {
    const li = document.createElement('li');
    li.innerHTML = `<strong>${escapeHtml(rma.rma_date)}</strong> <span>${escapeHtml(rma.description || '')}</span>`;
    list.appendChild(li);
  }
}

function escapeHtml(s) {
  return (s || '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[m]));
}

async function saveItem(e) {
  e.preventDefault();
  if (!currentItem) return;
  const code = currentItem.code;
  const category = currentItem.category || 'sonstiges';
  const body = {
    code,
    name: $('item-name').value,
    description: $('item-desc').value,
    location: $('item-location').value,
    quantity: parseFloat($('item-quantity').value) || 0,
    unit: $('item-unit').value,
  };

  if (category === 'laptop') {
    body.t14_gen = $('item-t14-gen').value;
    body.owners = $('item-owners').value;
    body.sina_token = $('item-sina-token').value;
    body.notes = $('item-notes').value;
  }

  if (socket && socket.connected) {
    socket.emit('client:update', body);
    showStatus('Wird gespeichert...', 'info');
  } else {
    showStatus('Keine Verbindung', 'error');
  }
}

function parseQrFromFile(file, callback) {
  const reader = new FileReader();
  reader.onload = (e) => {
    const img = new Image();
    img.onload = () => {
      const c = document.createElement('canvas');
      c.width = img.width;
      c.height = img.height;
      const cx = c.getContext('2d');
      cx.drawImage(img, 0, 0);
      const d = cx.getImageData(0, 0, c.width, c.height);
      const result = jsQR(d.data, d.width, d.height, { inversionAttempts: 'attemptBoth' });
      callback(result ? result.data : null);
    };
    img.src = e.target.result;
  };
  reader.readAsDataURL(file);
}

let searchCategory = '';

function initSearch() {
  document.querySelectorAll('#search-card .category-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('#search-card .category-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      searchCategory = btn.dataset.category;
      clientSearch($('client-search').value);
    });
  });

  $('client-search').addEventListener('input', (e) => clientSearch(e.target.value));
}

async function clientSearch(query) {
  const url = new URL(`${getHostOrigin()}/api/items`, window.location.origin);
  if (query) url.searchParams.set('search', query);
  try {
    const res = await fetch(url);
    let items = await res.json();
    if (searchCategory) {
      items = items.filter(i => (i.category || 'sonstiges') === searchCategory);
    }
    renderSearchResults(items);
  } catch (e) {
    // ignore
  }
}

function renderSearchResults(items) {
  const list = $('client-results');
  list.innerHTML = '';
  for (const item of items) {
    const li = document.createElement('li');
    li.innerHTML = `<strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.code)} · ${escapeHtml(item.category || 'sonstiges')} · ${escapeHtml(item.location || '')}</small>`;
    li.addEventListener('click', () => {
      socket.emit('client:scan', { code: item.code });
    });
    list.appendChild(li);
  }
}

$('btn-join').addEventListener('click', connectSocket);

$('btn-start-camera').addEventListener('click', startCamera);

$('btn-scan-photo').addEventListener('click', () => {
  $('obj-qr-file').click();
});

$('qr-file').addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (!file) return;
  parseQrFromFile(file, (data) => {
    if (!data) {
      showStatus('QR-Code nicht erkannt', 'error');
      return;
    }
    const urlMatch = data.match(/[?&]session=([A-Za-z0-9_-]+)/);
    if (urlMatch) {
      $('session-token').value = urlMatch[1];
      $('host-address').value = data.split('?')[0].replace('/client', '');
      connectSocket();
    } else {
      $('session-token').value = data;
    }
  });
});

$('obj-qr-file').addEventListener('change', (e) => {
  const file = e.target.files[0];
  if (!file) return;
  parseQrFromFile(file, (data) => {
    if (data) handleScan(data);
    else showStatus('QR-Code nicht erkannt', 'error');
  });
});

$('btn-manual-scan').addEventListener('click', () => {
  const code = $('manual-code').value.trim();
  if (code) handleScan(code);
});

$('item-form').addEventListener('submit', saveItem);

$('btn-new-scan').addEventListener('click', () => {
  stopCamera();
  $('item-card').classList.add('hidden');
  $('not-found-card').classList.add('hidden');
  $('scanner-card').classList.remove('hidden');
  $('photo-fallback').classList.remove('hidden');
});

$('btn-logout').addEventListener('click', () => {
  clearSession();
  stopCamera();
  if (socket) socket.disconnect();
  $('search-card').classList.add('hidden');
  $('scanner-card').classList.add('hidden');
  $('item-card').classList.add('hidden');
  $('not-found-card').classList.add('hidden');
  $('login-card').classList.remove('hidden');
  showStatus('Session beendet', 'info');
});

// Pre-fill from URL params
const params = new URLSearchParams(window.location.search);
if (params.get('session')) {
  $('session-token').value = params.get('session');
}
if (params.get('host')) {
  $('host-address').value = params.get('host');
}

initDescTemplates();
initSearch();

// Auto-connect if saved session exists
const savedSession = loadSession();
if (savedSession) {
  $('host-address').value = savedSession.host_address;
  $('session-token').value = savedSession.session_token;
  $('client-name').value = savedSession.client_name;
  showStatus('Versuche automatische Verbindung...', 'info');
  connectSocket(true);
}
