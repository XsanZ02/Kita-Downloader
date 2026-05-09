from flask import Blueprint, request, jsonify, send_file, Response, stream_with_context, render_template
import yt_dlp
import os
import tempfile
import re
import threading
import time
import uuid
import json

yt_bp = Blueprint('yt_bp', __name__)

DOWNLOAD_DIR = os.path.join(tempfile.gettempdir(), "youtube_downloads")
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def cleanup_old_files():
    while True:
        time.sleep(300)
        now = time.time()
        for f in os.listdir(DOWNLOAD_DIR):
            fpath = os.path.join(DOWNLOAD_DIR, f)
            if os.path.isfile(fpath) and now - os.path.getmtime(fpath) > 600:
                try:
                    os.remove(fpath)
                except Exception:
                    pass
            
            # Bersihkan state memori di download_store yang sudah lebih dari 1 jam
            with download_store_lock:
                to_delete = [
                    k for k, v in download_store.items()
                    if now - v.get('last_updated', now) > 3600
                ]
                for k in to_delete:
                    del download_store[k]

threading.Thread(target=cleanup_old_files, daemon=True).start()

download_store = {}
download_store_lock = threading.Lock()

def _set_progress(download_id, **kwargs):
    with download_store_lock:
        cur = download_store.get(download_id, {})
        cur.update(kwargs)
        cur['last_updated'] = time.time()
        download_store[download_id] = cur

def _get_progress(download_id):
    with download_store_lock:
        return dict(download_store.get(download_id, {}))

def is_valid_youtube_url(url):
    pattern = r'(https?://)?(www\.)?(youtube\.com|youtu\.be|music\.youtube\.com)'
    return bool(re.search(pattern, url))

@yt_bp.route('/')
def index():
    return render_template(
        'downloader_platform.html', 
        platform='YouTube', 
        desc='Download video YouTube hingga 4K atau ekstrak audio MP3 dengan cepat.'
    )

@yt_bp.route('/api/info', methods=['POST'])
def get_info():
    data = request.get_json()
    url = data.get('url', '').strip()

    if not url:
        return jsonify({'error': 'URL tidak boleh kosong'}), 400

    if not is_valid_youtube_url(url):
        return jsonify({'error': 'URL tidak valid. Masukkan link YouTube yang benar.'}), 400

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': 'in_playlist',
    }

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            if 'entries' in info:
                entries = []
                for e in info['entries']:
                    if e and e.get('id'):
                        entries.append({
                            'title': e.get('title', 'Video Tanpa Judul'),
                            'url': f"https://www.youtube.com/watch?v={e['id']}",
                            'channel': e.get('uploader', '') or e.get('channel', '')
                        })
                return jsonify({
                    'type': 'playlist',
                    'title': info.get('title', 'Playlist YouTube'),
                    'entries': entries
                })

            thumbnail = info.get('thumbnail', '')
            formats = info.get('formats', [])
            video_formats = []
            seen_heights = set()

            for f in formats:
                height = f.get('height')
                vcodec = f.get('vcodec', '')

                if vcodec and vcodec != 'none' and height and height > 0:
                    if height not in seen_heights:
                        seen_heights.add(height)
                        ext = f.get('ext', 'mp4')
                        video_formats.append({
                            'format_id': f.get('format_id'),
                            'quality': height,
                            'label': f"{height}p",
                            'ext': ext,
                            'filesize': f.get('filesize') or f.get('filesize_approx', 0),
                        })

            video_formats = sorted(video_formats, key=lambda x: x['quality'], reverse=True)
            allowed = [2160, 1440, 1080, 720, 480, 360, 240]
            filtered = [v for v in video_formats if v['quality'] in allowed]

            if not filtered or len(filtered) < 3:
                filtered = video_formats[:10]

            return jsonify({
                'type': 'video',
                'title': info.get('title', 'Video YouTube'),
                'channel': info.get('uploader', '') or info.get('channel', ''),
                'thumbnail': thumbnail,
                'duration': info.get('duration', 0),
                'like_count': info.get('like_count', 0),
                'view_count': info.get('view_count', 0),
                'upload_date': info.get('upload_date', ''),
                'formats': filtered[:6],
            })

    except yt_dlp.utils.DownloadError as e:
        msg = str(e)
        if 'Private' in msg or 'private' in msg:
            return jsonify({'error': 'Video ini bersifat privat dan tidak dapat diunduh.'}), 400
        if 'age' in msg.lower():
            return jsonify({'error': 'Video ini dibatasi usia dan tidak dapat diunduh tanpa login.'}), 400
        return jsonify({'error': 'Gagal memproses URL. Pastikan video masih tersedia.'}), 400
    except Exception as e:
        return jsonify({'error': f'Terjadi kesalahan: {str(e)}'}), 500

@yt_bp.route('/api/download', methods=['POST'])
def download_video():
    data = request.get_json()
    url = data.get('url', '').strip()
    fmt = data.get('format', 'mp4')
    quality = data.get('quality', '720')

    if not url or not is_valid_youtube_url(url):
        return jsonify({'error': 'URL tidak valid'}), 400

    download_id = str(uuid.uuid4())
    _set_progress(download_id, status='queued', percent=0, downloaded=0, total=None, speed=None, eta=None, file_path=None, download_name=None, ext=None, error=None)
    out_path = os.path.join(DOWNLOAD_DIR, f"yt_{download_id}")

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
                    _set_progress(download_id, percent=round(min(max(percent, 0), 99.9), 2), downloaded=downloaded, total=total, speed=speed_str, eta=eta)
                elif d.get('status') == 'finished':
                    _set_progress(download_id, percent=99.9, downloaded=d.get('downloaded_bytes'), total=d.get('total_bytes') or d.get('total_bytes_estimate'), speed=None, eta=None, status='processing')

            if fmt == 'mp3':
                ydl_opts = {'quiet': True, 'no_warnings': True, 'format': 'bestaudio/best', 'outtmpl': out_path + '.%(ext)s', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': '192'}], 'progress_hooks': [hook]}
            else:
                ydl_opts = {'quiet': True, 'no_warnings': True, 'format': f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best', 'outtmpl': out_path + '.%(ext)s', 'merge_output_format': 'mp4', 'progress_hooks': [hook]}

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get('title', 'video')

            ext = 'mp3' if fmt == 'mp3' else 'mp4'
            file_path = out_path + '.' + ext

            if not os.path.exists(file_path):
                for f in os.listdir(DOWNLOAD_DIR):
                    if f.startswith(os.path.basename(out_path)):
                        file_path = os.path.join(DOWNLOAD_DIR, f)
                        break

            safe_title = re.sub(r'[^\w\s-]', '', title)[:60].strip()
            dl_name = f"{safe_title}.{ext}"
            _set_progress(download_id, status='done', percent=100, file_path=file_path, download_name=dl_name, ext=ext, speed=None, eta=None, error=None)
        except Exception as e:
            _set_progress(download_id, status='error', percent=0, file_path=None, download_name=None, ext=None, error=str(e))

    threading.Thread(target=worker, daemon=True).start()
    return jsonify({'download_id': download_id}), 202

@yt_bp.route('/api/progress/stream/<download_id>', methods=['GET'])
def progress_stream(download_id):
    def generate():
        last_heartbeat = time.time()
        HEARTBEAT_INTERVAL = 15
        MAX_WAIT = 600
        start = time.time()
        while True:
            if time.time() - start > MAX_WAIT:
                yield f"event: error\ndata: {json.dumps({'error': 'Timeout'})}\n\n"
                break
            st = _get_progress(download_id)
            if not st:
                yield f"event: error\ndata: {json.dumps({'error': 'download_id tidak ditemukan'})}\n\n"
                break
            payload = {'status': st.get('status'), 'percent': st.get('percent', 0), 'downloaded': st.get('downloaded'), 'total': st.get('total'), 'speed': st.get('speed'), 'eta': st.get('eta'), 'error': st.get('error')}
            yield f"data: {json.dumps(payload)}\n\n"
            if st.get('status') in ('done', 'error'): break
            now = time.time()
            if now - last_heartbeat >= HEARTBEAT_INTERVAL:
                yield ": heartbeat\n\n"
                last_heartbeat = now
            time.sleep(0.5)
    return Response(stream_with_context(generate()), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'})

@yt_bp.route('/api/progress/<download_id>', methods=['GET'])
def api_progress(download_id):
    st = _get_progress(download_id)
    if not st: return jsonify({'error': 'download_id tidak ditemukan'}), 404
    return jsonify({'status': st.get('status'), 'percent': st.get('percent', 0), 'downloaded': st.get('downloaded'), 'total': st.get('total'), 'speed': st.get('speed'), 'eta': st.get('eta'), 'error': st.get('error')})

@yt_bp.route('/api/download-file/<download_id>', methods=['GET'])
def api_download_file(download_id):
    st = _get_progress(download_id)
    if not st: return jsonify({'error': 'download_id tidak ditemukan'}), 404
    if st.get('status') != 'done' or not st.get('file_path'): return jsonify({'error': 'File belum siap'}), 409
    file_path = st['file_path']
    ext = st.get('ext') or ('mp3' if (st.get('download_name') or '').endswith('.mp3') else 'mp4')
    return send_file(file_path, as_attachment=True, download_name=st.get('download_name') or f"video.{ext}", mimetype='video/mp4' if ext == 'mp4' else 'audio/mpeg')