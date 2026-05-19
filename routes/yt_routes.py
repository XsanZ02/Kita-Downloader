from flask import Blueprint, request, jsonify, send_file, Response, stream_with_context, render_template
import yt_dlp
import os
import re
import uuid
from utils.download_manager import DOWNLOAD_DIR, set_progress, get_progress, start_download_thread, sse_progress_generator

yt_bp = Blueprint('yt_bp', __name__)

def _extract_best_thumbnail(info: dict) -> str:
    if not isinstance(info, dict):
        return ''
    t = info.get('thumbnail')
    if isinstance(t, str) and t.startswith('http'):
        return t
    thumbnails = info.get('thumbnails')
    if isinstance(thumbnails, list):
        for thumb in reversed(thumbnails):
            url = thumb.get('url')
            if isinstance(url, str) and url.startswith('http'):
                return url
    return ''

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
        'http_headers': {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}
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

            thumbnail = _extract_best_thumbnail(info)
                
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
                'audio_formats': [
                    {'quality': '320', 'label': '320 kbps', 'ext': 'mp3', 'filesize': int((320 * 1000 / 8) * info.get('duration', 0))},
                    {'quality': '256', 'label': '256 kbps', 'ext': 'mp3', 'filesize': int((256 * 1000 / 8) * info.get('duration', 0))},
                    {'quality': '192', 'label': '192 kbps', 'ext': 'mp3', 'filesize': int((192 * 1000 / 8) * info.get('duration', 0))},
                    {'quality': '128', 'label': '128 kbps', 'ext': 'mp3', 'filesize': int((128 * 1000 / 8) * info.get('duration', 0))},
                ]
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
    set_progress(download_id, status='queued', percent=0, speed=None, eta=None)
    out_path = os.path.join(DOWNLOAD_DIR, f"yt_{download_id}")

    ua = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'}
    if fmt == 'mp3':
        valid_audio_qualities = ['128', '192', '256', '320']
        audio_quality = quality if quality in valid_audio_qualities else '192'
        ydl_opts = {'quiet': True, 'no_warnings': True, 'format': 'bestaudio/best', 'outtmpl': out_path + '.%(ext)s', 'postprocessors': [{'key': 'FFmpegExtractAudio', 'preferredcodec': 'mp3', 'preferredquality': audio_quality}], 'http_headers': ua}
    else:
        ydl_opts = {'quiet': True, 'no_warnings': True, 'format': f'bestvideo[height<={quality}][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best', 'outtmpl': out_path + '.%(ext)s', 'merge_output_format': 'mp4', 'http_headers': ua}

    start_download_thread(download_id, url, ydl_opts, fmt, out_path)
    return jsonify({'download_id': download_id}), 202

@yt_bp.route('/api/progress/stream/<download_id>', methods=['GET'])
def progress_stream(download_id):
    return Response(stream_with_context(sse_progress_generator(download_id)), mimetype='text/event-stream', headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no', 'Connection': 'keep-alive'})

@yt_bp.route('/api/progress/<download_id>', methods=['GET'])
def api_progress(download_id):
    st = get_progress(download_id)
    if not st: return jsonify({'error': 'download_id tidak ditemukan'}), 404
    return jsonify({'status': st.get('status'), 'percent': st.get('percent', 0), 'downloaded': st.get('downloaded'), 'total': st.get('total'), 'speed': st.get('speed'), 'eta': st.get('eta'), 'error': st.get('error')})

@yt_bp.route('/api/download-file/<download_id>', methods=['GET'])
def api_download_file(download_id):
    st = get_progress(download_id)
    if not st: return jsonify({'error': 'download_id tidak ditemukan'}), 404
    if st.get('status') != 'done' or not st.get('file_path'): return jsonify({'error': 'File belum siap'}), 409
    file_path = st['file_path']
    ext = st.get('ext') or ('mp3' if (st.get('download_name') or '').endswith('.mp3') else 'mp4')
    return send_file(file_path, as_attachment=True, download_name=st.get('download_name') or f"video.{ext}", mimetype='video/mp4' if ext == 'mp4' else 'audio/mpeg')