import os
import tempfile
import threading
import time
import uuid
import json
import re
import yt_dlp
from flask import Blueprint, request, jsonify, Response, stream_with_context, send_file

# Membuat blueprint khusus untuk API platform selain YouTube
platform_api_bp = Blueprint('platform_api_bp', __name__)

DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "platform_downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

download_store = {}
download_store_lock = threading.Lock()

# ── BACKGROUND CLEANUP (Menghapus file lama agar RAM/Disk aman) ──
def cleanup_platform_files():
    while True:
        time.sleep(300)
        now = time.time()
        for f in os.listdir(DOWNLOAD_DIR):
            fpath = os.path.join(DOWNLOAD_DIR, f)
            if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > 600: # 10 menit
                try: os.remove(fpath)
                except: pass
        
        with download_store_lock:
            to_delete = [k for k, v in download_store.items() if now - v.get('last_updated', now) > 3600]
            for k in to_delete: del download_store[k]

threading.Thread(target=cleanup_platform_files, daemon=True).start()

# ── HELPER STATE MANAGEMENT ──
def _set_progress(download_id, **kwargs):
    with download_store_lock:
        cur = download_store.get(download_id, {})
        cur.update(kwargs)
        cur['last_updated'] = time.time()
        download_store[download_id] = cur

def _get_progress(download_id):
    with download_store_lock:
        return dict(download_store.get(download_id, {}))

# ── HELPER: FETCH INFO URL ──
def fetch_generic_info(url, platform_name):
    if not url:
        return jsonify({'error': 'URL tidak boleh kosong'}), 400
    
    ydl_opts = {'quiet': True, 'no_warnings': True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            fmt_ext = 'mp3' if platform_name == 'SoundRip MP3' else 'mp4'
            
            return jsonify({
                'type': 'video',
                'title': info.get('title', f'Video {platform_name}'),
                'thumbnail': info.get('thumbnail', ''),
                'channel': info.get('uploader', info.get('extractor', platform_name)),
                'duration': info.get('duration', 0),
                'formats': [{'quality': 'best', 'label': 'Audio Terbaik' if fmt_ext == 'mp3' else 'Kualitas Terbaik', 'ext': fmt_ext}]
            })
    except Exception as e:
        return jsonify({'error': f'Gagal memproses URL {platform_name}. Pastikan link publik dan valid.'}), 400

# ── HELPER: START DOWNLOAD PROCESS ──
def start_generic_download(url, fmt):
    if not url:
        return jsonify({'error': 'URL tidak valid'}), 400

    download_id = str(uuid.uuid4())
    _set_progress(download_id, status='queued', percent=0, speed=None, eta=None)
    out_path = os.path.join(DOWNLOAD_DIR, f"dl_{download_id}")

    def worker():
        try:
            _set_progress(download_id, status='downloading', percent=0)
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
                            percent = _get_progress(download_id).get('percent', 0)
                            
                    speed_str = None
                    if speed:
                        if speed >= 1024 * 1024: speed_str = f"{speed / 1024 / 1024:.1f} MB/s"
                        elif speed >= 1024: speed_str = f"{speed / 1024:.0f} KB/s"
                        else: speed_str = f"{speed:.0f} B/s"
                        
                    _set_progress(download_id, percent=round(min(max(percent, 0), 99.9), 2), speed=speed_str, eta=eta)
                elif d.get('status') == 'finished':
                    _set_progress(download_id, status='processing', percent=99.9, speed=None, eta=None)

            ydl_opts = {
                'quiet': True,
                'outtmpl': out_path + '.%(ext)s',
                'progress_hooks': [hook]
            }

            if fmt == 'mp3':
                ydl_opts.update({
                    'format': 'bestaudio/best',
                    'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '320'}]
                })
            else:
                ydl_opts.update({'format': 'best'})

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get('title', 'video')

            ext = 'mp3' if fmt == 'mp3' else info.get('ext', 'mp4')
            file_path = out_path + '.' + ext

            # Antisipasi jika nama file hasil tidak sesuai prediksi
            if not os.path.exists(file_path):
                for f in os.listdir(DOWNLOAD_DIR):
                    if f.startswith(os.path.basename(out_path)):
                        file_path = os.path.join(DOWNLOAD_DIR, f)
                        ext = file_path.split('.')[-1]
                        break

            safe_title = re.sub(r'[^\w\s-]', '', title)[:60].strip()
            dl_name = f"{safe_title}.{ext}"
            _set_progress(download_id, status='done', percent=100, file_path=file_path, download_name=dl_name, ext=ext)
            
        except Exception as e:
            _set_progress(download_id, status='error', error=str(e))

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({'download_id': download_id}), 202

# ── TIKTOK API ────────────────────────────────────────────────
@platform_api_bp.route('/tiktok/api/info', methods=['POST'])
def tiktok_info():
    return fetch_generic_info(request.get_json().get('url'), 'TikTok')

@platform_api_bp.route('/tiktok/api/download', methods=['POST'])
def tiktok_download():
    data = request.get_json()
    return start_generic_download(data.get('url'), data.get('format', 'mp4'))

# ── INSTAGRAM API ─────────────────────────────────────────────
@platform_api_bp.route('/ig/api/info', methods=['POST'])
def ig_info():
    return fetch_generic_info(request.get_json().get('url'), 'Instagram')

@platform_api_bp.route('/ig/api/download', methods=['POST'])
def ig_download():
    data = request.get_json()
    return start_generic_download(data.get('url'), data.get('format', 'mp4'))

# ── FACEBOOK API ──────────────────────────────────────────────
@platform_api_bp.route('/fb/api/info', methods=['POST'])
def fb_info():
    return fetch_generic_info(request.get_json().get('url'), 'Facebook')

@platform_api_bp.route('/fb/api/download', methods=['POST'])
def fb_download():
    data = request.get_json()
    return start_generic_download(data.get('url'), data.get('format', 'mp4'))

# ── MP3 UNIVERSAL API ─────────────────────────────────────────
@platform_api_bp.route('/mp3/api/info', methods=['POST'])
def mp3_info():
    return fetch_generic_info(request.get_json().get('url'), 'SoundRip MP3')

@platform_api_bp.route('/mp3/api/download', methods=['POST'])
def mp3_download():
    data = request.get_json()
    return start_generic_download(data.get('url'), 'mp3')

# ── GLOBAL PROGRESS STREAM (Dipakai oleh semua platform di atas) ──
@platform_api_bp.route('/platform/api/progress/stream/<download_id>', methods=['GET'])
def progress_stream(download_id):
    def generate():
        last_heartbeat = time.time()
        HEARTBEAT_INTERVAL = 15
        start = time.time()
        while True:
            if time.time() - start > 600: # Timeout 10 menit
                yield f"event: error\ndata: {json.dumps({'error': 'Timeout koneksi'})}\n\n"
                break
            st = _get_progress(download_id)
            if not st:
                yield f"event: error\ndata: {json.dumps({'error': 'ID download tidak ditemukan'})}\n\n"
                break
            
            payload = {
                'status': st.get('status'), 
                'percent': st.get('percent', 0), 
                'speed': st.get('speed'),
                'eta': st.get('eta'),
                'error': st.get('error')
            }
            yield f"data: {json.dumps(payload)}\n\n"
            
            if st.get('status') in ('done', 'error'): 
                break
                
            now = time.time()
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                yield ": heartbeat\n\n"
                last_heartbeat = now
                
            time.sleep(0.5)
    return Response(stream_with_context(generate()), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'})

@platform_api_bp.route('/platform/api/download-file/<download_id>', methods=['GET'])
def api_download_file(download_id):
    st = _get_progress(download_id)
    if not st or st.get('status') != 'done' or not st.get('file_path'):
        return jsonify({'error': 'File belum siap'}), 404
    
    file_path = st['file_path']
    ext = st.get('ext', 'mp4')
    dl_name = st.get('download_name', f"download.{ext}")
    mimetype = 'audio/mpeg' if ext == 'mp3' else 'video/mp4'
    
    return send_file(file_path, as_attachment=True, download_name=dl_name, mimetype=mimetype)