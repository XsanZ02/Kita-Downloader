import os
import tempfile
import threading
import time
import json
import re
import yt_dlp
import redis

# Direktori tersentralisasi untuk semua unduhan
DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "kita_downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Inisialisasi koneksi Redis (Default: localhost, db 0)
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
USE_REDIS = False
local_store = {}
local_store_lock = threading.Lock()

try:
    redis_client = redis.from_url(REDIS_URL, decode_responses=True)
    redis_client.ping()  # Tes koneksi ke Redis
    USE_REDIS = True
    print("✅ Berhasil terhubung ke Redis!")
except Exception as e:
    print(f"⚠️ Redis tidak ditemukan. Menggunakan memori lokal (Fallback).")
    USE_REDIS = False

def set_progress(download_id, **kwargs):
    if USE_REDIS:
        try:
            key = f"dl_progress:{download_id}"
            data = redis_client.get(key)
            cur = json.loads(data) if data else {}
            
            cur.update(kwargs)
            cur['last_updated'] = time.time()
            
            # Simpan ke Redis dengan TTL 600 detik (10 menit)
            redis_client.setex(key, 600, json.dumps(cur))
        except Exception:
            pass
    else:
        with local_store_lock:
            cur = local_store.get(download_id, {})
            cur.update(kwargs)
            cur['last_updated'] = time.time()
            local_store[download_id] = cur

def get_progress(download_id):
    if USE_REDIS:
        try:
            key = f"dl_progress:{download_id}"
            data = redis_client.get(key)
            return json.loads(data) if data else {}
        except Exception:
            return {}
    else:
        with local_store_lock:
            return dict(local_store.get(download_id, {}))

# Daemon thread terpusat untuk membersihkan file fisik usang
def _cleanup_daemon():
    while True:
        time.sleep(120)  # Cek setiap 2 menit
        now = time.time()
        for f in os.listdir(DOWNLOAD_DIR):
            fpath = os.path.join(DOWNLOAD_DIR, f)
            if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > 300:  # 5 menit
                try:
                    os.remove(fpath)
                except Exception:
                    pass

        if not USE_REDIS:
            with local_store_lock:
                to_delete = [k for k, v in local_store.items() if now - v.get('last_updated', now) > 600]
                for k in to_delete:
                    del local_store[k]

threading.Thread(target=_cleanup_daemon, daemon=True).start()

# Worker terpusat untuk yt-dlp
def start_download_thread(download_id, url, ydl_opts, fmt, out_path):
    def worker():
        try:
            set_progress(download_id, status='downloading', percent=0)

            def hook(d):
                if d.get('status') == 'downloading':
                    downloaded = d.get('downloaded_bytes') or 0
                    total = d.get('total_bytes') or d.get('total_bytes_estimate') or None
                    speed = d.get('speed')
                    eta = d.get('eta')
                    percent = 0.0
                    if total and downloaded:
                        try:
                            percent = float(downloaded) / float(total) * 100.0
                        except Exception:
                            percent = get_progress(download_id).get('percent', 0)
                    speed_str = None
                    if speed:
                        if speed >= 1024 * 1024: speed_str = f"{speed / 1024 / 1024:.1f} MB/s"
                        elif speed >= 1024: speed_str = f"{speed / 1024:.0f} KB/s"
                        else: speed_str = f"{speed:.0f} B/s"
                    
                    set_progress(
                        download_id, percent=round(min(max(percent, 0), 99.9), 2),
                        speed=speed_str, eta=eta, downloaded=downloaded, total=total
                    )
                elif d.get('status') == 'finished':
                    set_progress(download_id, status='processing', percent=99.9, speed=None, eta=None)

            ydl_opts['progress_hooks'] = [hook]

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)

                # Bypass otomatis jika bentuknya playlist (Spotify/XHS)
                if info.get('_type') == 'playlist' and 'entries' in info:
                    valid_entries = [e for e in info['entries'] if e]
                    if valid_entries:
                        info = valid_entries[0]

                title = info.get('title', 'video')

            if fmt == 'mp3':
                ext = 'mp3'
            elif fmt in ('jpg', 'jpeg', 'png', 'webp'):
                ext = fmt
            else:
                ext = info.get('ext', 'mp4')

            file_path = out_path + '.' + ext

            # Cari file hasil jika berbeda dari yang diprediksi
            if not os.path.exists(file_path):
                for f in os.listdir(DOWNLOAD_DIR):
                    if f.startswith(os.path.basename(out_path)):
                        file_path = os.path.join(DOWNLOAD_DIR, f)
                        ext = file_path.rsplit('.', 1)[-1]
                        break

            safe_title = re.sub(r'[^\w\s-]', '', title)[:60].strip()
            dl_name = f"{safe_title}.{ext}"
            
            set_progress(download_id, status='done', percent=100, file_path=file_path, download_name=dl_name, ext=ext)

        except Exception as e:
            set_progress(download_id, status='error', error=str(e))

    threading.Thread(target=worker, daemon=True).start()

# Generator terpusat untuk SSE HTTP
def sse_progress_generator(download_id):
    last_heartbeat = time.time()
    HEARTBEAT_INTERVAL = 15
    start = time.time()
    while True:
        if time.time() - start > 600:
            yield f"event: error\ndata: {json.dumps({'error': 'Timeout koneksi'})}\n\n"
            break
        st = get_progress(download_id)
        if not st:
            yield f"event: error\ndata: {json.dumps({'error': 'ID download tidak ditemukan'})}\n\n"
            break
        payload = {'status': st.get('status'), 'percent': st.get('percent', 0), 'speed': st.get('speed'), 'eta': st.get('eta'), 'error': st.get('error'), 'downloaded': st.get('downloaded'), 'total': st.get('total')}
        yield f"data: {json.dumps(payload)}\n\n"
        if st.get('status') in ('done', 'error'): break
        now = time.time()
        if now - last_heartbeat >= HEARTBEAT_INTERVAL:
            yield ": heartbeat\n\n"
            last_heartbeat = now
        time.sleep(0.5)