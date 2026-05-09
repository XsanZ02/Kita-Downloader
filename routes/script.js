// ── State ──────────────────────────────────────────────────
let currentUrl = '';
let selectedQuality = '720';
let activeEventSource = null;

// ── Theme Toggle ───────────────────────────────────────────
const themeBtn = document.getElementById('themeToggle');

// Cek preferensi tema sebelumnya dari localStorage
if (localStorage.getItem('theme') === 'light') {
  document.documentElement.classList.add('light-mode');
  themeBtn.textContent = '☀️';
}

themeBtn.addEventListener('click', () => {
  document.documentElement.classList.toggle('light-mode');
  const isLightMode = document.documentElement.classList.contains('light-mode');
  themeBtn.textContent = isLightMode ? '☀️' : '🌙';
  localStorage.setItem('theme', isLightMode ? 'light' : 'dark');
});

// ── Paste URL ──────────────────────────────────────────────
async function pasteURL() {
  try {
    const text = await navigator.clipboard.readText();
    document.getElementById('urlInput').value = text;
  } catch {
    document.getElementById('urlInput').focus();
  }
}

// ── Process URL → fetch info ───────────────────────────────
async function processURL() {
  const url = document.getElementById('urlInput').value.trim();
  if (!url) return;

  hideError();
  document.getElementById('resultWrap').style.display = 'none';
  document.getElementById('playlistWrap').style.display = 'none';
  document.getElementById('btnProcess').disabled = true;
  document.getElementById('urlInput').disabled = true;
  document.getElementById('btnProcess').innerHTML = '<span class="spinner"></span>Memproses…';

  try {
    const res = await fetch('/yt/api/info', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url }),
    });

    const data = await res.json();

    if (!res.ok) {
      showError(data.error || 'Gagal memproses URL.');
      return;
    }

    currentUrl = url;

    if (data.type === 'playlist') {
      renderPlaylist(data);
    } else {
      renderResult(data);
    }

  } catch (err) {
    showError('Gagal terhubung ke server. Pastikan server berjalan.');
  } finally {
    document.getElementById('btnProcess').disabled = false;
    document.getElementById('urlInput').disabled = false;
    document.getElementById('btnProcess').innerHTML = 'Proses &rarr;';
  }
}

// ── Enter key shortcut ─────────────────────────────────────
document.getElementById('urlInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') processURL();
});

// ── Render video info ──────────────────────────────────────
function renderResult(data) {
  document.getElementById('thumbnail').src = data.thumbnail || '';
  document.getElementById('videoTitle').textContent = data.title || '';
  document.getElementById('videoChannel').textContent = data.channel || '';
  document.getElementById('durationBadge').textContent = formatDuration(data.duration || 0);

  const views = data.view_count ? `👁 ${formatNum(data.view_count)} tayangan` : '';
  const date  = data.upload_date ? `📅 ${formatDate(data.upload_date)}` : '';
  document.getElementById('statViews').textContent = views;
  document.getElementById('statDate').textContent  = date;

  // Quality buttons
  const grid = document.getElementById('qualityGrid');
  grid.innerHTML = '';
  const formats = data.formats || [];

  formats.forEach((f, i) => {
    const btn = document.createElement('button');
    btn.className = 'quality-btn' + (i === 0 ? ' active' : '');
    btn.dataset.quality = f.quality;

    const isHD = f.quality >= 1080;
    const size  = f.filesize ? ` · ${formatBytes(f.filesize)}` : '';

    if (isHD) {
      const hdBadge = document.createElement('span');
      hdBadge.className = 'hd-badge';
      hdBadge.textContent = 'HD';
      btn.appendChild(hdBadge);
    }
    const qLabel = document.createElement('span');
    qLabel.className = 'q-label';
    qLabel.textContent = f.label;
    btn.appendChild(qLabel);
    const qSub = document.createElement('span');
    qSub.className = 'q-sub';
    qSub.textContent = `${f.ext.toUpperCase()}${size}`;
    btn.appendChild(qSub);

    btn.addEventListener('click', () => {
      document.querySelectorAll('.quality-btn').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      selectedQuality = String(f.quality);
    });

    grid.appendChild(btn);
  });

  if (formats.length > 0) selectedQuality = String(formats[0].quality);

  // Reset progress
  document.getElementById('progressWrap').style.display = 'none';
  document.getElementById('progressBar').style.width = '0%';
  document.getElementById('progressLabel').textContent = '';
  document.getElementById('btnDlVideo').disabled = false;
  document.getElementById('btnDlMp3').disabled  = false;

  document.getElementById('resultWrap').style.display = 'block';

  saveHistory(currentUrl, data.title, data.thumbnail);
}

function renderPlaylist(data) {
  document.getElementById('playlistTitle').textContent = data.title || 'Playlist';
  document.getElementById('playlistCount').textContent = `${data.entries.length} Video`;
  
  const list = document.getElementById('playlistList');
  list.innerHTML = '';
  
  data.entries.forEach((item, idx) => {
    const div = document.createElement('div');
    div.className = 'playlist-item';
    div.innerHTML = `
      <div class="pl-info">
        <span class="pl-title">${idx + 1}. ${item.title}</span>
        <span class="pl-channel">${item.channel}</span>
      </div>
      <button class="btn-pl-process" onclick="document.getElementById('urlInput').value='${item.url}'; processURL();">Pilih</button>
    `;
    list.appendChild(div);
  });
  document.getElementById('playlistWrap').style.display = 'block';
  saveHistory(currentUrl, data.title, 'https://via.placeholder.com/48x27/272727/aaaaaa?text=PL');
}

// ── downloadFile() — SSE realtime version ─────────────────
async function downloadFile(fmt) {
  if (!currentUrl) return;

  // Tutup SSE sebelumnya jika ada
  if (activeEventSource) {
    activeEventSource.close();
    activeEventSource = null;
  }

  const btnVideo      = document.getElementById('btnDlVideo');
  const btnMp3        = document.getElementById('btnDlMp3');
  const progressWrap  = document.getElementById('progressWrap');
  const progressBar   = document.getElementById('progressBar');
  const progressLabel = document.getElementById('progressLabel');

  hideError();
  btnVideo.disabled = true;
  btnMp3.disabled   = true;
  progressWrap.style.display = 'block';
  progressBar.style.width    = '0%';
  progressLabel.textContent  = 'Menghubungkan…';

  try {
    // 1️⃣  Buat job download → dapat download_id
    const res = await fetch('/yt/api/download', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ url: currentUrl, format: fmt, quality: selectedQuality }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || 'Gagal memulai download');
    }

    const { download_id } = await res.json();

    // 2️⃣  Buka SSE stream untuk progress realtime
    activeEventSource = new EventSource(`/yt/api/progress/stream/${download_id}`);

    activeEventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const percent = data.percent ?? 0;
      progressBar.style.width = `${percent}%`;

      let label = '';
      if (data.status === 'queued') {
        label = 'Menunggu…';
      } else if (data.status === 'downloading') {
        label = `Mengunduh ${percent.toFixed(1)}%`;
        if (data.speed) label += ` · ${data.speed}`;
        if (data.eta)   label += ` · ETA ${formatETA(data.eta)}`;
      } else if (data.status === 'processing') {
        label = 'Memproses audio/video…';
      } else if (data.status === 'done') {
        label = 'Selesai! Menyimpan file…';
        progressBar.style.width = '100%';
      } else if (data.status === 'error') {
        label = `Error: ${data.error}`;
      }

      progressLabel.textContent = label;

      // 3️⃣  Jika selesai, trigger download file
      if (data.status === 'done') {
        activeEventSource.close();
        activeEventSource = null;
        setTimeout(() => triggerFileDownload(download_id), 400);
      }

      // 4️⃣  Jika error, tampilkan & re-enable tombol
      if (data.status === 'error') {
        activeEventSource.close();
        activeEventSource = null;
        showError(data.error || 'Terjadi kesalahan');
        resetButtons();
      }
    };

    // Tangani event custom 'error' dari server (named event)
    activeEventSource.addEventListener('error', (event) => {
      try {
        const data = JSON.parse(event.data || '{}');
        showError(data.error || 'Terjadi kesalahan pada server');
      } catch {
        showError('Terjadi kesalahan pada server');
      }
      activeEventSource.close();
      activeEventSource = null;
      resetButtons();
    });

    // SSE connection error (jaringan putus, dll)
    activeEventSource.onerror = (e) => {
      // Hanya tangani jika bukan event custom di atas
      if (activeEventSource) {
        activeEventSource.close();
        activeEventSource = null;
        showError('Koneksi terputus. Coba lagi.');
        resetButtons();
      }
    };

  } catch (err) {
    showError(err.message);
    resetButtons();
  }
}

// ── Trigger file download ke browser ──────────────────────
function triggerFileDownload(download_id) {
  const a = document.createElement('a');
  a.href = `/yt/api/download-file/${download_id}`;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(resetButtons, 1500);
}

// ── Helpers ────────────────────────────────────────────────
function resetButtons() {
  document.getElementById('btnDlVideo').disabled = false;
  document.getElementById('btnDlMp3').disabled   = false;
}

function showError(msg) {
  document.getElementById('errorText').textContent = msg;
  document.getElementById('errorBox').style.display = 'block';
}

function hideError() {
  document.getElementById('errorBox').style.display = 'none';
}

function formatETA(seconds) {
  if (seconds < 60) return `${seconds}d`;
  const m = Math.floor(seconds / 60);
  const s = seconds % 60;
  return `${m}m ${s}d`;
}

function formatDuration(sec) {
  if (!sec) return '';
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  const s = sec % 60;
  if (h > 0) return `${h}:${String(m).padStart(2,'0')}:${String(s).padStart(2,'0')}`;
  return `${m}:${String(s).padStart(2,'0')}`;
}

function formatNum(n) {
  if (!n) return '0';
  if (n >= 1_000_000) return (n / 1_000_000).toFixed(1) + 'Jt';
  if (n >= 1_000)     return (n / 1_000).toFixed(1) + 'Rb';
  return String(n);
}

function formatDate(d) {
  if (!d || d.length < 8) return d;
  return `${d.slice(6,8)}/${d.slice(4,6)}/${d.slice(0,4)}`;
}

function formatBytes(b) {
  if (!b) return '';
  if (b >= 1024*1024*1024) return (b/1024/1024/1024).toFixed(1)+' GB';
  if (b >= 1024*1024)      return (b/1024/1024).toFixed(0)+' MB';
  if (b >= 1024)           return (b/1024).toFixed(0)+' KB';
  return b + ' B';
}

// ── History ────────────────────────────────────────────────
function loadHistory() {
  const history = JSON.parse(localStorage.getItem('yt_history') || '[]');
  const wrap = document.getElementById('historyWrap');
  const list = document.getElementById('historyList');

  if (history.length === 0) {
    wrap.style.display = 'none';
    return;
  }

  list.innerHTML = '';
  history.forEach(item => {
    const div = document.createElement('div');
    div.className = 'history-item';
    div.onclick = () => {
      document.getElementById('urlInput').value = item.url;
      processURL();
    };
    div.innerHTML = `
      <img class="history-thumb" src="${item.thumbnail}" alt="thumb">
      <div class="history-info">
        <span class="history-text">${item.title}</span>
        <span class="history-url">${item.url}</span>
      </div>
      <button class="btn-remove-history" onclick="removeHistory(event, '${item.url}')" title="Hapus riwayat">✕</button>
    `;
    list.appendChild(div);
  });
  wrap.style.display = 'block';
}

function saveHistory(url, title, thumbnail) {
  let history = JSON.parse(localStorage.getItem('yt_history') || '[]');
  history = history.filter(item => item.url !== url); // Hapus jika sudah ada
  history.unshift({ url, title, thumbnail });         // Tambahkan ke paling atas
  if (history.length > 5) history.pop();              // Simpan maksimal 5 saja
  localStorage.setItem('yt_history', JSON.stringify(history));
  loadHistory();
}

function removeHistory(event, url) {
  event.stopPropagation(); // Mencegah klik merambat ke parent (yang memicu processURL)
  let history = JSON.parse(localStorage.getItem('yt_history') || '[]');
  history = history.filter(item => item.url !== url);
  localStorage.setItem('yt_history', JSON.stringify(history));
  loadHistory(); // Render ulang daftar
}

function clearAllHistory() {
  localStorage.removeItem('yt_history');
  loadHistory();
}

// Inisialisasi saat web dimuat
loadHistory();