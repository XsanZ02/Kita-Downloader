(function() {

// ── State ──────────────────────────────────────────────────
const state = {
  currentUrl: '',
  selectedQuality: '720',
  activeEventSource: null,
  currentData: null,
  currentFormatType: 'mp4'
};

// ── Deteksi Platform API Secara Dinamis ────────────────────
const currentPath = window.location.pathname;
let API_INFO = '/yt/api/info';
let API_DOWNLOAD = '/yt/api/download';
let API_STREAM = '/yt/api/progress/stream/';
let API_FILE = '/yt/api/download-file/';

const pathMatch = currentPath.match(/^\/(tiktok|ig|fb|tw|th|mp3|xhs|img)/);
if (pathMatch) {
  const platform = pathMatch[1];
  API_INFO = `/${platform}/api/info`;
  API_DOWNLOAD = `/${platform}/api/download`;
  API_STREAM = `/platform/api/progress/stream/`;
  API_FILE = `/platform/api/download-file/`;
}

// ── Theme Toggle ───────────────────────────────────────────
const themeBtn = document.getElementById('themeToggle');

// Cek preferensi tema dari localStorage atau preferensi sistem OS
const savedTheme = localStorage.getItem('theme');
const prefersLight = window.matchMedia('(prefers-color-scheme: light)').matches;

if (savedTheme === 'light' || (!savedTheme && prefersLight)) {
  document.documentElement.classList.add('light-mode');
  themeBtn.textContent = '☀️';
} else {
  themeBtn.textContent = '🌙';
}

themeBtn.addEventListener('click', () => {
  document.documentElement.classList.toggle('light-mode');
  const isLightMode = document.documentElement.classList.contains('light-mode');
  themeBtn.textContent = isLightMode ? '☀️' : '🌙';
  localStorage.setItem('theme', isLightMode ? 'light' : 'dark');
});

// Deteksi perubahan tema sistem secara real-time
window.matchMedia('(prefers-color-scheme: light)').addEventListener('change', e => {
  if (!localStorage.getItem('theme')) {
    document.documentElement.classList.toggle('light-mode', e.matches);
    if (themeBtn) themeBtn.textContent = e.matches ? '☀️' : '🌙';
  }
});

// ── Sticky Navbar Scroll Listener ────────────────────────────
window.addEventListener('scroll', () => {
  const nav = document.getElementById('topNav');
  if (nav) {
    if (window.scrollY > 20) nav.classList.add('scrolled');
    else nav.classList.remove('scrolled');
  }
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

// ── Fill Example ───────────────────────────────────────────
function fillExample() {
  const hintSpan = document.querySelector('.example-hint span');
  if (hintSpan) document.getElementById('urlInput').value = hintSpan.textContent.trim();
}

// ── Process URL → fetch info ───────────────────────────────
let loadingInterval;
let textRotatorInterval;

function startFakeLoading() {
  const texts = ["Mengambil metadata...", "Mengekstrak format audio/video...", "Menyiapkan kualitas terbaik...", "Hampir selesai..."];
  let tIdx = 0;
  document.getElementById('loadingTextRotator').textContent = texts[0];
  textRotatorInterval = setInterval(() => {
    tIdx = (tIdx + 1) % texts.length;
    document.getElementById('loadingTextRotator').textContent = texts[tIdx];
  }, 1200);

  let progress = 0;
  document.getElementById('fakeProgressBar').style.width = '0%';
  document.getElementById('loadingOverlay').style.display = 'flex';

  loadingInterval = setInterval(() => {
    if(progress < 85) {
      progress += Math.random() * 12; // Lompatan acak
      if(progress > 85) progress = 85;
      document.getElementById('fakeProgressBar').style.width = progress + '%';
    }
  }, 400);
}

function stopFakeLoading() {
  clearInterval(loadingInterval);
  clearInterval(textRotatorInterval);
  document.getElementById('fakeProgressBar').style.width = '100%';
  setTimeout(() => {
    document.getElementById('loadingOverlay').style.display = 'none';
  }, 300);
}

async function processURL() {
  const url = document.getElementById('urlInput').value.trim();
  if (!url) return;

  document.getElementById('resultWrap').style.display = 'none';
  document.getElementById('playlistWrap').style.display = 'none';
  document.getElementById('btnProcess').disabled = true;
  document.getElementById('urlInput').disabled = true;
  
  startFakeLoading();

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

  try {
    const res = await fetch(API_INFO, {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
      },
      body: JSON.stringify({ url }),
    });

    const data = await res.json();

    if (!res.ok) {
      showError(data.error || 'Gagal memproses URL.');
      return;
    }

    state.currentUrl = url;

    if (data.type === 'playlist') {
      renderPlaylist(data);
    } else {
      renderResult(data);
    }

  } catch (err) {
    showError('Gagal terhubung ke server. Pastikan server berjalan.');
  } finally {
    stopFakeLoading();
    document.getElementById('btnProcess').disabled = false;
    document.getElementById('urlInput').disabled = false;
  }
}

// ── Enter key shortcut ─────────────────────────────────────
document.getElementById('urlInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') processURL();
});

// ── Helper: Image Proxy ────────────────────────────────────
function getProxyUrl(url) {
  if (!url) return '';
  if (url.startsWith('data:')) return url;
  // Melewati proxy untuk CDN yang ketat terhadap CORS (Instagram/FB/X/Xiaohongshu)
  if (url.includes('fbcdn.net') || url.includes('instagram.com') || url.includes('twimg.com') || url.includes('xhscdn.com') || url.includes('xiaohongshu.com')) {
    return `/api/proxy-image?url=${encodeURIComponent(url)}`;
  }
  return url;
}

// ── Render video info ──────────────────────────────────────
function renderResult(data) {
  state.currentData = data;
  state.currentFormatType = 'mp4';
  
  if (data.formats && data.formats.length > 0 && data.formats[0].ext === 'mp3') {
    state.currentFormatType = 'mp3';
  }

  document.getElementById('thumbnail').src = getProxyUrl(data.thumbnail);
  document.getElementById('videoTitle').textContent = data.title || '';
  document.getElementById('videoChannel').textContent = data.channel || '';
  document.getElementById('durationBadge').textContent = formatDuration(data.duration || 0);

  const views = data.view_count ? `👁 ${formatNum(data.view_count)} tayangan` : '';
  const date  = data.upload_date ? `📅 ${formatDate(data.upload_date)}` : '';
  document.getElementById('statViews').textContent = views;
  document.getElementById('statDate').textContent  = date;

  renderQualities(data.formats, state.currentFormatType);

  // Reset progress
  document.getElementById('progressWrap').style.display = 'none';
  document.getElementById('progressBar').style.width = '0%';
  document.getElementById('progressBar').textContent = '';
  document.getElementById('progressLabel').textContent = '';
  document.getElementById('btnDlVideo').disabled = false;
  document.getElementById('btnDlMp3').disabled  = false;
  document.getElementById('btnDlThumb').disabled = false;

  document.getElementById('resultWrap').style.display = 'block';

  saveHistory(state.currentUrl, data.title, data.thumbnail);
}

function renderQualities(formats, fmtType) {
  const grid = document.getElementById('qualityGrid');
  if (!grid) return;
  grid.innerHTML = '';
  
  if (!formats || formats.length === 0) return;

  formats.forEach((f, i) => {
    const btn = document.createElement('button');
    btn.className = 'quality-btn' + (i === 0 ? ' active' : '');
    btn.dataset.quality = f.quality;

    const isHD = f.quality >= 1080;
    const size  = f.filesize ? ` · ${formatBytes(f.filesize)}` : '';

    if (isHD && fmtType !== 'mp3') {
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
      state.selectedQuality = String(f.quality);
    });

    grid.appendChild(btn);
  });

  state.selectedQuality = String(formats[0].quality);
}

function renderPlaylist(data) {
  document.getElementById('playlistTitle').textContent = data.title || 'Playlist';
  document.getElementById('playlistCount').textContent = `${data.entries.length} Video`;
  
  const list = document.getElementById('playlistList');
  list.innerHTML = '';
  
  data.entries.forEach((item, idx) => {
    const div = document.createElement('div');
    div.className = 'playlist-item';
    const extBadge = item.ext ? `<span style="font-size: 0.7rem; background: var(--overlay); padding: 2px 6px; border-radius: 4px; margin-left: 8px; color: var(--accent); vertical-align: middle;">${item.ext}</span>` : '';
    div.innerHTML = `
      <div class="pl-info">
        <span class="pl-title">${idx + 1}. ${item.title}${extBadge}</span>
        <span class="pl-channel">${item.channel}</span>
      </div>
      <button class="btn-pl-process" onclick="document.getElementById('urlInput').value='${item.url}'; processURL();">Pilih</button>
    `;
    list.appendChild(div);
  });
  document.getElementById('playlistWrap').style.display = 'block';
    
    const thumbUrl = data.thumbnail || 'https://via.placeholder.com/48x27/272727/aaaaaa?text=PL';
    saveHistory(state.currentUrl, data.title, thumbUrl);
}

// ── downloadFile() — SSE realtime version ─────────────────
async function downloadFile(fmt) {
  if (!state.currentUrl) return;

  // ── LOGIKA BARU: Intercept klik pertama untuk menampilkan Bitrate MP3 ──
  if (fmt === 'mp3' && state.currentFormatType !== 'mp3') {
    if (state.currentData && state.currentData.audio_formats) {
      renderQualities(state.currentData.audio_formats, 'mp3');
      state.currentFormatType = 'mp3';
      showToast('Pilih bitrate audio di atas, lalu klik Unduh MP3 lagi.', 'success');
      return;
    }
  } else if (fmt !== 'mp3' && state.currentFormatType === 'mp3') {
    if (state.currentData && state.currentData.formats) {
      renderQualities(state.currentData.formats, 'mp4');
      state.currentFormatType = 'mp4';
      showToast('Pilih resolusi video di atas, lalu klik tombol Unduh lagi.', 'success');
      return;
    }
  }

  // Tutup SSE sebelumnya jika ada
  if (state.activeEventSource) {
    state.activeEventSource.close();
    state.activeEventSource = null;
  }

  const btnVideo      = document.getElementById('btnDlVideo');
  const btnMp3        = document.getElementById('btnDlMp3');
  const progressWrap  = document.getElementById('progressWrap');
  const progressBar   = document.getElementById('progressBar');
  const progressLabel = document.getElementById('progressLabel');

  btnVideo.disabled = true;
  btnMp3.disabled   = true;
  progressWrap.style.display = 'block';
  progressBar.style.width    = '0%';
  progressBar.textContent    = '';
  progressLabel.textContent  = 'Menghubungkan…';

  const csrfToken = document.querySelector('meta[name="csrf-token"]')?.getAttribute('content');

  try {
    // 1️⃣  Buat job download → dapat download_id
    const res = await fetch(API_DOWNLOAD, {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'X-CSRFToken': csrfToken
      },
      body: JSON.stringify({ url: state.currentUrl, format: fmt, quality: state.selectedQuality }),
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.error || 'Gagal memulai download');
    }

    const { download_id } = await res.json();

    // 2️⃣  Buka SSE stream untuk progress realtime
    state.activeEventSource = new EventSource(`${API_STREAM}${download_id}`);

    state.activeEventSource.onmessage = (event) => {
      const data = JSON.parse(event.data);
      const percent = data.percent ?? 0;
      progressBar.style.width = `${percent}%`;
      
      // Tampilkan tulisan persentase hanya jika bar sudah cukup lebar (> 5%)
      if (percent >= 5) {
        progressBar.textContent = `${percent.toFixed(1)}%`;
      } else {
        progressBar.textContent = '';
      }

      let label = '';
      if (data.status === 'queued') {
        label = 'Menunggu…';
      } else if (data.status === 'downloading') {
        label = `Mengunduh ${percent.toFixed(1)}%`;
        if (data.speed) label += ` · ${data.speed}`;
        if (data.eta)   label += ` · ETA ${formatETA(data.eta)}`;
      } else if (data.status === 'processing') {
        label = 'Memproses audio/video…';
        progressBar.textContent = 'Memproses...';
      } else if (data.status === 'done') {
        label = 'Selesai! Menyimpan file…';
        progressBar.style.width = '100%';
        progressBar.textContent = '100%';
      } else if (data.status === 'error') {
        label = `Error: ${data.error}`;
      }

      progressLabel.textContent = label;

      // 3️⃣  Jika selesai, trigger download file
      if (data.status === 'done') {
        state.activeEventSource.close();
        state.activeEventSource = null;
        setTimeout(() => triggerFileDownload(download_id), 400);
      }

      // 4️⃣  Jika error, tampilkan & re-enable tombol
      if (data.status === 'error') {
        state.activeEventSource.close();
        state.activeEventSource = null;
        showError(data.error || 'Terjadi kesalahan');
        resetButtons();
      }
    };

    // Tangani event custom 'error' dari server (named event)
    state.activeEventSource.addEventListener('error', (event) => {
      try {
        const data = JSON.parse(event.data || '{}');
        showError(data.error || 'Terjadi kesalahan pada server');
      } catch {
        showError('Terjadi kesalahan pada server');
      }
      state.activeEventSource.close();
      state.activeEventSource = null;
      resetButtons();
    });

    // SSE connection error (jaringan putus, dll)
    state.activeEventSource.onerror = (e) => {
      // Hanya tangani jika bukan event custom di atas
      if (state.activeEventSource) {
        state.activeEventSource.close();
        state.activeEventSource = null;
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
  a.href = `${API_FILE}${download_id}`;
  a.style.display = 'none';
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  setTimeout(resetButtons, 1500);
}

// ── Download Thumbnail Image ────────────────────────────────
async function downloadThumbnail() {
  const url = document.getElementById('thumbnail').src;
  if (!url) return;
  try {
    const res = await fetch(url);
    const blob = await res.blob();
    const blobUrl = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = blobUrl;
    a.download = `Thumbnail_${Date.now()}.jpg`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    window.URL.revokeObjectURL(blobUrl);
  } catch (e) {
    // Jika diblokir oleh CORS (misal dari YouTube), buka di tab baru dengan aman
    window.open(url, '_blank');
  }
}

// ── Helpers ────────────────────────────────────────────────
function resetButtons() {
  document.getElementById('btnDlVideo').disabled = false;
  document.getElementById('btnDlMp3').disabled   = false;
}

function showError(msg) {
  showToast(msg, 'error');
}

// ── Fungsi Menampilkan Toast Notification Modern ────────────
function showToast(message, type) {
  const container = document.getElementById('toastContainer');
  if (!container) return; // Fallback aman jika elemen tidak ada
  
  const toast = document.createElement('div');
  toast.className = `toast ${type}`;
  
  // Ikon dinamis berdasarkan status
  const icon = type === 'success' 
    ? `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path><polyline points="22 4 12 14.01 9 11.01"></polyline></svg>`
    : `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line></svg>`;

  toast.innerHTML = `${icon} <span>${message}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.classList.add('hide');
    toast.addEventListener('animationend', () => toast.remove());
  }, 4000);
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

function timeAgo(ms) {
  const diff = Math.floor((Date.now() - ms) / 1000);
  if (diff < 60) return 'Baru saja';
  if (diff < 3600) return `${Math.floor(diff/60)} mnt lalu`;
  if (diff < 86400) return `${Math.floor(diff/3600)} jam lalu`;
  if (diff < 172800) return 'Kemarin';
  return `${Math.floor(diff/86400)} hari lalu`;
}

// ── History ────────────────────────────────────────────────
function loadHistory() {
  const history = JSON.parse(localStorage.getItem('kita_history') || '[]');
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
    const safeTime = item.timestamp ? timeAgo(item.timestamp) : '';
    div.innerHTML = `
        <img class="history-thumb" src="${getProxyUrl(item.thumbnail)}" alt="thumb" referrerpolicy="no-referrer">
      <div class="history-info">
        <span class="history-text">${item.title}</span>
        <div class="history-meta">
          <span class="history-url">${item.url.substring(0, 30)}...</span>
          <span class="history-time">${safeTime}</span>
        </div>
      </div>
      <button class="btn-remove-history" onclick="removeHistory(event, '${item.url}')" title="Hapus riwayat">✕</button>
    `;
    list.appendChild(div);
  });
  wrap.style.display = 'block';
}

function saveHistory(url, title, thumbnail) {
  let history = JSON.parse(localStorage.getItem('kita_history') || '[]');
  history = history.filter(item => item.url !== url); // Hapus jika sudah ada
  history.unshift({ url, title, thumbnail, timestamp: Date.now() }); // Simpan waktu saat ini
  if (history.length > 5) history.pop();              // Simpan maksimal 5 saja
  localStorage.setItem('kita_history', JSON.stringify(history));
  loadHistory();
}

function removeHistory(event, url) {
  event.stopPropagation(); // Mencegah klik merambat ke parent (yang memicu processURL)
  let history = JSON.parse(localStorage.getItem('kita_history') || '[]');
  history = history.filter(item => item.url !== url);
  localStorage.setItem('kita_history', JSON.stringify(history));
  loadHistory(); // Render ulang daftar
}

function clearAllHistory() {
  localStorage.removeItem('kita_history');
  loadHistory();
}

// Inisialisasi saat web dimuat
loadHistory();

// ── Expose fungsi publik ke window (untuk pemanggilan onClick di HTML) ──
window.pasteURL = pasteURL;
window.fillExample = fillExample;
window.processURL = processURL;
window.downloadFile = downloadFile;
window.downloadThumbnail = downloadThumbnail;
window.removeHistory = removeHistory;
window.clearAllHistory = clearAllHistory;

})();