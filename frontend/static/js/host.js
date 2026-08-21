const socket = io();
let sessionUrl = '';
let sessionToken = '';
let currentItem = null;

function $(id) { return document.getElementById(id); }

function showStatus(msg, type = 'info') {
  const el = $('status');
  el.textContent = msg;
  el.className = `status ${type}`;
  el.classList.remove('hidden');
  setTimeout(() => el.classList.add('hidden'), 4000);
}

function updateSessionUI(data) {
  sessionToken = data.token;
  sessionUrl = data.url;
  const protocol = data.protocol || 'http';
  const hostUrl = `${protocol}://${data.host_ip}:${data.host_port}/host`;
  $('host-url').textContent = hostUrl;
  $('host-url').href = hostUrl;
  $('client-url').textContent = sessionUrl;
  $('session-token').textContent = sessionToken;
  $('session-qr').innerHTML = `<img src="/api/qr?data=${encodeURIComponent(sessionUrl)}" alt="Session QR">`;
}

async function loadSession() {
  try {
    const res = await fetch('/api/session');
    const data = await res.json();
    updateSessionUI(data);
  } catch (e) {
    showStatus('Session konnte nicht geladen werden', 'error');
  }
}

function getDisplayName() {
  return 'Host';
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

function initCategoryButtons() {
  document.querySelectorAll('.category-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.category-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      $('item-category').value = btn.dataset.category;
      toggleCategoryFields(btn.dataset.category);
    });
  });
}

function toggleCategoryFields(category) {
  const isLaptop = category === 'laptop';
  $('laptop-fields').classList.toggle('hidden', !isLaptop);
  $('desc-templates').classList.toggle('hidden', !isLaptop);
  // For laptop: hide quantity/unit
  $('item-quantity').closest('.form-group').style.display = isLaptop ? 'none' : '';
  $('item-unit').closest('.form-group').style.display = isLaptop ? 'none' : '';
}

async function loadItems(search = '') {
  const url = new URL('/api/items', window.location.origin);
  if (search) url.searchParams.set('search', search);
  try {
    const res = await fetch(url);
    const items = await res.json();
    renderItems(items);
  } catch (e) {
    showStatus('Bestand konnte nicht geladen werden', 'error');
  }
}

function renderItems(items) {
  const tbody = $('items-table').querySelector('tbody');
  tbody.innerHTML = '';
  for (const item of items) {
    const tr = document.createElement('tr');
    const rmaCount = item.rmas ? item.rmas.length : 0;
    const rmaText = rmaCount > 0 ? `${rmaCount} RMA${rmaCount > 1 ? 's' : ''}` : '—';
    tr.innerHTML = `
      <td>${escapeHtml(item.code)}</td>
      <td>${escapeHtml(item.name)}</td>
      <td>${escapeHtml(item.category || 'sonstiges')}</td>
      <td>${escapeHtml(item.location || '')}</td>
      <td>${item.category === 'laptop' ? rmaText : `${item.quantity} ${escapeHtml(item.unit || '')}`}</td>
      <td class="actions">
        <button data-code="${escapeHtml(item.code)}" class="btn-edit">Bearbeiten</button>
        <button data-code="${escapeHtml(item.code)}" class="btn-qr secondary">QR</button>
        <button data-code="${escapeHtml(item.code)}" class="btn-delete danger">Löschen</button>
      </td>
    `;
    tbody.appendChild(tr);
  }

  tbody.querySelectorAll('.btn-edit').forEach(b => b.addEventListener('click', () => editItem(b.dataset.code)));
  tbody.querySelectorAll('.btn-qr').forEach(b => b.addEventListener('click', () => showItemQr(b.dataset.code)));
  tbody.querySelectorAll('.btn-delete').forEach(b => b.addEventListener('click', () => deleteItem(b.dataset.code)));
}

function escapeHtml(s) {
  return (s || '').replace(/[&<>"']/g, m => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;','\'':'&#39;'}[m]));
}

async function editItem(code) {
  try {
    const res = await fetch(`/api/items/${encodeURIComponent(code)}`);
    const item = await res.json();
    if (item.error) return;
    currentItem = item;
    $('edit-code').value = item.code;
    $('item-code').value = item.code;
    $('item-name').value = item.name;
    $('item-category').value = item.category || 'sonstiges';

    document.querySelectorAll('.category-btn').forEach(b => {
      b.classList.toggle('active', b.dataset.category === (item.category || 'sonstiges'));
    });
    toggleCategoryFields(item.category || 'sonstiges');

    $('item-location').value = item.location || '';
    $('item-quantity').value = item.quantity || 0;
    $('item-unit').value = item.unit || '';

    if (item.category === 'laptop') {
      $('item-desc').value = item.description || '';
      if (item.details) {
        $('item-t14-gen').value = item.details.t14_gen || '';
        $('item-owners').value = item.details.owners || '';
        $('item-notes').value = item.details.notes || '';
      } else {
        $('item-t14-gen').value = '';
        $('item-owners').value = '';
        $('item-notes').value = '';
      }
    } else {
      $('item-desc').value = item.description || '';
      $('item-t14-gen').value = '';
      $('item-owners').value = '';
      $('item-notes').value = '';
    }

    renderRmas(item.rmas || []);
    showItemQr(item.code);
    window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
  } catch (e) {
    showStatus('Objekt konnte nicht geladen werden', 'error');
  }
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

function showItemQr(code) {
  const img = document.createElement('img');
  img.src = `/api/items/${encodeURIComponent(code)}/qr?box_size=12`;
  const qr = $('item-qr');
  qr.innerHTML = '';
  qr.appendChild(img);
  qr.classList.remove('hidden');
  $('item-qr-actions').classList.remove('hidden');
  $('btn-download-qr').onclick = () => {
    const a = document.createElement('a');
    a.href = img.src;
    a.download = `qr-${code}.png`;
    a.click();
  };
}

async function deleteItem(code) {
  if (!confirm(`Objekt ${code} löschen?`)) return;
  try {
    const res = await fetch(`/api/items/${encodeURIComponent(code)}`, { method: 'DELETE' });
    if (res.ok) {
      showStatus('Objekt gelöscht', 'success');
      resetForm();
      loadItems($('search-items').value);
    } else {
      showStatus('Löschen fehlgeschlagen', 'error');
    }
  } catch (e) {
    showStatus('Löschen fehlgeschlagen', 'error');
  }
}

function resetForm() {
  $('item-form').reset();
  $('edit-code').value = '';
  $('item-category').value = 'sonstiges';
  document.querySelectorAll('.category-btn').forEach(b => {
    b.classList.toggle('active', b.dataset.category === 'sonstiges');
  });
  toggleCategoryFields('sonstiges');
  $('rma-list').innerHTML = '';
  $('item-qr').classList.add('hidden');
  $('item-qr-actions').classList.add('hidden');
  currentItem = null;
}

async function saveItem(e) {
  e.preventDefault();
  const code = $('item-code').value.trim();
  const editCode = $('edit-code').value;
  const category = $('item-category').value;

  const body = {
    name: $('item-name').value,
    category,
    description: $('item-desc').value,
    location: $('item-location').value,
    quantity: parseFloat($('item-quantity').value) || 0,
    unit: $('item-unit').value,
  };

  if (category === 'laptop') {
    body.t14_gen = $('item-t14-gen').value;
    body.owners = $('item-owners').value;
    body.notes = $('item-notes').value;
  }

  try {
    let res;
    if (editCode) {
      res = await fetch(`/api/items/${encodeURIComponent(editCode)}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    } else {
      body.code = code;
      res = await fetch('/api/items', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      });
    }
    if (res.ok) {
      showStatus('Gespeichert', 'success');
      resetForm();
      loadItems($('search-items').value);
    } else {
      showStatus('Speichern fehlgeschlagen', 'error');
    }
  } catch (err) {
    showStatus('Speichern fehlgeschlagen', 'error');
  }
}

async function addRma() {
  if (!currentItem) {
    showStatus('Bitte zuerst ein Objekt auswählen', 'error');
    return;
  }
  const date = prompt('RMA-Datum (z.B. 2025-01-15):');
  if (!date) return;
  const desc = prompt('RMA-Beschreibung (optional):') || '';
  try {
    const res = await fetch(`/api/items/${encodeURIComponent(currentItem.code)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rma_date: date, rma_description: desc }),
    });
    if (res.ok) {
      showStatus('RMA hinzugefügt', 'success');
      editItem(currentItem.code);
    } else {
      showStatus('RMA konnte nicht gespeichert werden', 'error');
    }
  } catch (e) {
    showStatus('RMA konnte nicht gespeichert werden', 'error');
  }
}

function renderClients(clients) {
  const list = $('client-list');
  list.innerHTML = '';
  if (clients.length === 0) {
    list.innerHTML = '<li>Noch keine Clients verbunden.</li>';
    return;
  }
  for (const c of clients) {
    const li = document.createElement('li');
    li.textContent = `${c.name} (letzter Scan: ${c.last_scan || '—'})`;
    list.appendChild(li);
  }
}

function logScan(data) {
  const list = $('scan-log');
  const li = document.createElement('li');
  const status = data.found ? 'gefunden' : 'nicht gefunden';
  li.textContent = `${new Date().toLocaleTimeString()} — ${data.code} von ${data.sid} ${status}`;
  list.prepend(li);
}

async function loadScans() {
  try {
    const res = await fetch('/api/scans');
    const scans = await res.json();
    renderScans(scans);
  } catch (e) {
    console.warn('Scan-Verlauf konnte nicht geladen werden', e);
  }
}

function renderScans(scans) {
  const list = $('scan-log');
  list.innerHTML = '';
  for (const scan of scans) {
    const li = document.createElement('li');
    const status = scan.found ? 'gefunden' : 'nicht gefunden';
    const time = new Date(scan.scanned_at).toLocaleTimeString();
    li.textContent = `${time} — ${escapeHtml(scan.code)} von ${escapeHtml(scan.client_name)} ${status}`;
    list.appendChild(li);
  }
}

async function exportCsv() {
  window.open('/api/csv/export');
}

async function importCsv(file) {
  const form = new FormData();
  form.append('file', file);
  try {
    const res = await fetch('/api/csv/import', { method: 'POST', body: form });
    const data = await res.json();
    if (data.labels_url) {
      showStatus(`${data.imported} Einträge importiert. Etiketten-PDF wird vorbereitet...`, 'success');
      setTimeout(() => window.open(data.labels_url), 800);
    } else {
      showStatus(`${data.imported} Einträge importiert`, 'success');
    }
    loadItems();
  } catch (e) {
    showStatus('Import fehlgeschlagen', 'error');
  }
}

// API helper for generic QR data
async function generateQrData(data) {
  const res = await fetch('/api/qr?data=' + encodeURIComponent(data));
  return res.blob();
}

socket.on('connect', () => {
  socket.emit('host:join');
});

socket.on('session:updated', (data) => {
  updateSessionUI(data);
});

socket.on('clients:changed', (clients) => renderClients(clients));

socket.on('item:updated', () => loadItems($('search-items').value));
socket.on('item:deleted', () => loadItems($('search-items').value));

socket.on('scan:result', (data) => logScan(data));

let showingCaQr = false;
let sessionQrHtml = '';

async function checkCa() {
  try {
    const res = await fetch('/api/ca', { method: 'GET' });
    if (res.ok) {
      const caUrl = new URL('/api/ca', window.location.origin).href;
      $('btn-toggle-ca').classList.remove('hidden');
      $('ca-hint').classList.remove('hidden');
      $('btn-toggle-ca').onclick = () => toggleCaQr(caUrl);
    }
  } catch (e) {
    // CA not available
  }
}

function toggleCaQr(caUrl) {
  showingCaQr = !showingCaQr;
  const qr = $('session-qr');
  const label = $('qr-label');
  const link = $('ca-link');
  const btn = $('btn-toggle-ca');

  if (showingCaQr) {
    sessionQrHtml = qr.innerHTML;
    qr.innerHTML = `<img src="/api/qr?data=${encodeURIComponent(caUrl)}" alt="CA QR">`;
    label.textContent = 'Root-CA herunterladen (QR scannen)';
    link.classList.remove('hidden');
    btn.textContent = 'Session QR';
  } else {
    qr.innerHTML = sessionQrHtml;
    label.textContent = 'Client-Session';
    link.classList.add('hidden');
    btn.textContent = 'Root-CA QR';
  }
}

$('btn-regenerate').addEventListener('click', async () => {
  try {
    await fetch('/api/session/regenerate', { method: 'POST' });
    showStatus('Neuer Token generiert', 'success');
  } catch (e) {
    showStatus('Fehler', 'error');
  }
});

$('btn-copy-url').addEventListener('click', () => {
  navigator.clipboard.writeText(sessionUrl).then(() => showStatus('URL kopiert', 'success'));
});

$('btn-refresh').addEventListener('click', () => loadItems($('search-items').value));
$('search-items').addEventListener('input', (e) => loadItems(e.target.value));
$('item-form').addEventListener('submit', saveItem);
$('btn-cancel').addEventListener('click', resetForm);
$('btn-export-csv').addEventListener('click', exportCsv);
$('btn-add-rma').addEventListener('click', addRma);

$('btn-import-csv').addEventListener('click', () => $('csv-file').click());
$('csv-file').addEventListener('change', (e) => {
  if (e.target.files[0]) importCsv(e.target.files[0]);
});

// Initialize
loadSession();
loadItems();
loadScans();
checkCa();
initDescTemplates();
initCategoryButtons();
