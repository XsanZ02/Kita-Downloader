import os
import uuid
import re
import yt_dlp
import subprocess
import json
from flask import Blueprint, request, jsonify, Response, stream_with_context, send_file
from utils.download_manager import DOWNLOAD_DIR, set_progress, get_progress, start_download_thread, sse_progress_generator
from urllib.parse import urlparse
import base64

# ── PATCH YT-DLP UNTUK DOMAIN THREADS.COM ──
def _apply_threads_patch():
    THREADS_VALID_URL = r'https?://(?:www\.)?threads\.(?:net|com)/(?:@[^/]+/post/|t/)(?P<id>[^/?#&]+)'
    try:
        from yt_dlp.extractor.threads import ThreadsIE
        ThreadsIE._VALID_URL = THREADS_VALID_URL
        ThreadsIE._VALID_URL_RE = re.compile(THREADS_VALID_URL)
        print("[Threads Patch] Real extractor berhasil di-patch.")
    except Exception as e:
        print(f"[Threads Patch] Real extractor gagal: {e}")
    try:
        from yt_dlp.extractor.lazy_extractors import ThreadsIE as LazyThreadsIE
        LazyThreadsIE._VALID_URL = THREADS_VALID_URL
        LazyThreadsIE._VALID_URL_RE = re.compile(THREADS_VALID_URL)
        print("[Threads Patch] Lazy extractor berhasil di-patch.")
    except ImportError:
        pass

_apply_threads_patch()

platform_api_bp = Blueprint('platform_api_bp', __name__)

# ── HELPER: EXTRACT THUMBNAIL VIA FFMPEG (UNTUK THREADS) ──
def _generate_thumbnail_with_ffmpeg(video_url: str) -> str:
    try:
        command = [
            'ffmpeg',
            '-ss', '00:00:00.000',  # Ambil frame pertama
            '-i', video_url,        # Input URL Video
            '-vframes', '1',        # Ambil 1 frame saja
            '-q:v', '2',            # Resolusi/kualitas tinggi
            '-c:v', 'mjpeg',        # Encode menjadi JPEG
            '-f', 'image2pipe',     # Outputkan langsung sebagai data stream
            '-'
        ]
        process = subprocess.run(command, capture_output=True, timeout=15)
        if process.returncode == 0 and process.stdout:
            b64_img = base64.b64encode(process.stdout).decode('utf-8')
            return f"data:image/jpeg;base64,{b64_img}"
    except Exception as e:
        print(f"[FFmpeg Thumbnail Error] {e}")
    return ''

# ── HELPER: EXTRACT BEST THUMBNAIL ──
def _extract_best_thumbnail(info: dict) -> str:
    if not isinstance(info, dict):
        return ''
    t = info.get('thumbnail')
    if isinstance(t, str) and t.startswith('http'):
        return t
    thumbnails = info.get('thumbnails')
    if isinstance(thumbnails, list):
        for thumb in reversed(thumbnails):
            if isinstance(thumb, dict) and isinstance(thumb.get('url'), str) and thumb['url'].startswith('http'):
                return thumb['url']
    return ''

# ── HELPER: DETEKSI APAKAH ENTRY ADALAH FOTO ──
def _is_photo_entry(info: dict) -> bool:
    if not info:
        return False
    formats = info.get('formats', [])
    for f in formats:
        ext = (f.get('ext') or '').lower()
        if ext in ('jpg', 'jpeg', 'png', 'webp'):
            return True
    if not info.get('duration'):
        has_video = any(f.get('vcodec', 'none') != 'none' for f in formats)
        if not has_video and formats:
            return True
    return False

# ── HELPER: FALLBACK THUMBNAIL (JIKA GAGAL MENDAPATKAN THUMBNAIL) ──
def _get_fallback_thumbnail(info: dict) -> str:
    if _is_photo_entry(info):
        return ''
    # Mencari URL video langsung
    video_url = info.get('url')
    if not video_url:
        for f in reversed(info.get('formats', [])):
            if f.get('vcodec', 'none') != 'none' and f.get('url'):
                video_url = f.get('url')
                break
    if video_url:
        return _generate_thumbnail_with_ffmpeg(video_url)
    return ''

# ── HELPER: SMART URL RESOLVER ──
def resolve_smart_url(url):
    if not url:
        return url

    url_match = re.search(r'(https?://[a-zA-Z0-9\-._~:/?#\[\]@!$&\'()*+,;=%]+)', url)
    if url_match:
        url = url_match.group(1)

    if 'threads.com' in url.lower() or 'threads.net' in url.lower():
        clean_url = url.split('?')[0].split('#')[0]
        match_post = re.search(r'(@[\w\.-]+/post/[\w-]+)', clean_url)
        if match_post:
            return f"https://www.threads.net/{match_post.group(1)}"
        match_short = re.search(r'/t/([\w-]+)', clean_url)
        if match_short:
            return f"https://www.threads.net/t/{match_short.group(1)}"
        return clean_url

    if 'spotify.com' in url.lower():
        try:
            import urllib.request
            req = urllib.request.Request(
                url,
                headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
            )
            html = urllib.request.urlopen(req, timeout=10).read().decode('utf-8')
            match = re.search(r'<title>(.*?)</title>', html, re.IGNORECASE)
            if match:
                title = match.group(1).replace('| Spotify', '').strip()
                for keyword in [
                    ' - song and lyrics by ', ' - Single by ',
                    ' - song by ', ' - EP by ', ' - Album by '
                ]:
                    title = title.replace(keyword, ' ')
                return f"ytsearch1:{title} audio"
        except Exception:
            pass

    return url

# ── HELPER: HEADERS PER PLATFORM ──
def _build_headers(platform_name: str, url: str = '') -> dict:
    base = {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        )
    }
    is_threads = 'threads.net' in url or 'threads.com' in url or platform_name == 'Threads'
    is_image_platform = platform_name == 'Image Downloader'

    if is_threads:
        base.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-US,en;q=0.5',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Dest': 'document',
            'Upgrade-Insecure-Requests': '1',
        })
    elif is_image_platform:
        base.update({
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
            'Accept-Language': 'en-US,en;q=0.9',
            'Sec-Fetch-Dest': 'document',
            'Sec-Fetch-Mode': 'navigate',
            'Sec-Fetch-Site': 'none',
            'Sec-Fetch-User': '?1',
            'Upgrade-Insecure-Requests': '1',
        })
    return base

# ── HELPER: FETCH INFO URL ──
def fetch_generic_info(url, platform_name):
    if not url:
        return jsonify({'error': 'URL tidak boleh kosong'}), 400

    slide_idx = None
    if 'slide_idx=' in url:
        match = re.search(r'slide_idx=(\d+)', url)
        if match:
            slide_idx = match.group(1)
        url = re.sub(r'[?&]slide_idx=\d+', '', url)

    original_url = url
    url = resolve_smart_url(url)

    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'http_headers': _build_headers(platform_name, url),
    }
    if slide_idx:
        ydl_opts['playlist_items'] = slide_idx

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            if info.get('_type') == 'playlist' and 'entries' in info:
                valid_entries = [e for e in info['entries'] if e]

                if slide_idx and valid_entries:
                    info = valid_entries[0]
                elif url.startswith('ytsearch') and valid_entries:
                    info = valid_entries[0]
                else:
                    entries = []
                    for idx, e in enumerate(valid_entries):
                        separator = '&' if '?' in original_url else '?'
                        slide_url = f"{original_url}{separator}slide_idx={idx + 1}"

                        is_photo = _is_photo_entry(e)
                        if is_photo:
                            ext_val = 'jpg'
                        else:
                            ext_val = e.get('ext') or 'mp4'
                            if ext_val == 'unknown_video':
                                ext_val = 'mp4'

                        entries.append({
                            'title': e.get('title') or f"Media {idx + 1}",
                            'url': slide_url,
                            'channel': e.get('uploader') or info.get('uploader', platform_name),
                            'ext': ext_val.upper(),
                            'is_photo': is_photo,
                        })

                    pl_thumb = _extract_best_thumbnail(info)
                    if not pl_thumb and valid_entries:
                        pl_thumb = _extract_best_thumbnail(valid_entries[0])
                        if not pl_thumb:
                            pl_thumb = _get_fallback_thumbnail(valid_entries[0])

                    return jsonify({
                        'type': 'playlist',
                        'title': info.get('title', f'Postingan {platform_name}'),
                        'entries': entries,
                        'thumbnail': pl_thumb
                    })

            duration = info.get('duration', 0)
            thumbnail = _extract_best_thumbnail(info)
            if not thumbnail:
                thumbnail = _get_fallback_thumbnail(info)

            formats_list = []

            if platform_name == 'SoundRip MP3':
                for br in [320, 256, 192, 128]:
                    approx_size = int((br * 1000 / 8) * duration) if duration else 0
                    formats_list.append({
                        'quality': str(br),
                        'label': f"{br} kbps",
                        'ext': 'mp3',
                        'filesize': approx_size
                    })
            else:
                if _is_photo_entry(info):
                    formats_list.append({
                        'quality': 'original',
                        'label': 'Foto Original',
                        'ext': 'jpg',
                        'filesize': 0
                    })
                else:
                    seen_heights = set()
                    for f in info.get('formats', []):
                        height = f.get('height')
                        if height and height > 0 and f.get('vcodec', 'none') != 'none':
                            if height not in seen_heights:
                                seen_heights.add(height)
                                formats_list.append({
                                    'quality': height,
                                    'label': f"{height}p",
                                    'ext': f.get('ext', 'mp4'),
                                    'filesize': f.get('filesize') or f.get('filesize_approx', 0)
                                })
                    formats_list = sorted(
                        formats_list,
                        key=lambda x: int(x['quality']) if str(x['quality']).isdigit() else 0,
                        reverse=True
                    )
                    if not formats_list:
                        formats_list.append({
                            'quality': 'best',
                            'label': 'Kualitas Terbaik',
                            'ext': 'mp4'
                        })

            return jsonify({
                'type': 'video',
                'title': info.get('title', f'Post {platform_name}'),
                'thumbnail': thumbnail,
                'channel': info.get('uploader', info.get('extractor', platform_name)),
                'duration': duration,
                'formats': formats_list,
                'is_photo': _is_photo_entry(info),
                'audio_formats': [
                    {'quality': '320', 'label': '320 kbps', 'ext': 'mp3', 'filesize': int((320 * 1000 / 8) * duration)},
                    {'quality': '256', 'label': '256 kbps', 'ext': 'mp3', 'filesize': int((256 * 1000 / 8) * duration)},
                    {'quality': '192', 'label': '192 kbps', 'ext': 'mp3', 'filesize': int((192 * 1000 / 8) * duration)},
                    {'quality': '128', 'label': '128 kbps', 'ext': 'mp3', 'filesize': int((128 * 1000 / 8) * duration)},
                ]
            })

    except Exception as e:
        err_msg = str(e)
        if 'Unsupported URL' in err_msg:
            return jsonify({'error': 'URL tidak didukung. Pastikan link dalam format publik yang valid.'}), 400
        if 'Unexpected response' in err_msg or 'yt-dlp -U' in err_msg:
            return jsonify({'error': 'Sistem perlu diupdate. Jalankan: pip install --upgrade yt-dlp'}), 400
        return jsonify({'error': f'Gagal memproses URL {platform_name}. Pastikan link publik dan valid.'}), 400

# ── HELPER: START DOWNLOAD PROCESS ──
def start_generic_download(url, fmt, quality='best'):
    if not url:
        return jsonify({'error': 'URL tidak valid'}), 400

    slide_idx = None
    if 'slide_idx=' in url:
        match = re.search(r'slide_idx=(\d+)', url)
        if match:
            slide_idx = match.group(1)
        url = re.sub(r'[?&]slide_idx=\d+', '', url)

    platform_name = _detect_platform(url)
    url = resolve_smart_url(url)

    download_id = str(uuid.uuid4())
    set_progress(download_id, status='queued', percent=0, speed=None, eta=None)
    out_path = os.path.join(DOWNLOAD_DIR, f"dl_{download_id}")

    ydl_opts = {
        'quiet': True,
        'outtmpl': out_path + '.%(ext)s',
        'http_headers': _build_headers(platform_name, url),
    }

    if slide_idx:
        ydl_opts['playlist_items'] = slide_idx

    if fmt == 'mp3':
        valid_audio_qualities = ['128', '192', '256', '320']
        audio_quality = quality if quality in valid_audio_qualities else '320'
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': audio_quality
            }]
        })
    elif fmt in ('jpg', 'jpeg', 'png', 'webp'):
        ydl_opts.update({
            'format': f'best[ext={fmt}]/best',
        })
    else:
        if quality and quality != 'best':
            ydl_opts.update({
                'format': f'bestvideo[height<={quality}]+bestaudio/best[height<={quality}]/best'
            })
        else:
            ydl_opts.update({'format': 'best'})

    start_download_thread(download_id, url, ydl_opts, fmt, out_path)
    return jsonify({'download_id': download_id}), 202

# ── HELPER: DETEKSI PLATFORM DARI URL ──
def _detect_platform(url: str) -> str:
    url_lower = url.lower()
    if 'threads.net' in url_lower or 'threads.com' in url_lower:
        return 'Threads'
    if 'instagram.com' in url_lower:
        return 'Instagram'
    if 'tiktok.com' in url_lower:
        return 'TikTok'
    if 'facebook.com' in url_lower or 'fb.watch' in url_lower:
        return 'Facebook'
    if 'twitter.com' in url_lower or 'x.com' in url_lower:
        return 'X (Twitter)'
    if 'xiaohongshu.com' in url_lower or 'xhslink.com' in url_lower:
        return 'Xiaohongshu'
    if 'freepik.com' in url_lower or 'pinterest.com' in url_lower or 'imgur.com' in url_lower:
        return 'Image Downloader'
    return 'Unknown'

# ── TIKTOK API ────────────────────────────────────────────────
@platform_api_bp.route('/tiktok/api/info', methods=['POST'])
def tiktok_info():
    return fetch_generic_info(request.get_json().get('url'), 'TikTok')

@platform_api_bp.route('/tiktok/api/download', methods=['POST'])
def tiktok_download():
    data = request.get_json()
    return start_generic_download(data.get('url'), data.get('format', 'mp4'), data.get('quality', 'best'))

# ── INSTAGRAM API ─────────────────────────────────────────────
@platform_api_bp.route('/ig/api/info', methods=['POST'])
def ig_info():
    return fetch_generic_info(request.get_json().get('url'), 'Instagram')

@platform_api_bp.route('/ig/api/download', methods=['POST'])
def ig_download():
    data = request.get_json()
    return start_generic_download(data.get('url'), data.get('format', 'mp4'), data.get('quality', 'best'))

# ── FACEBOOK API ──────────────────────────────────────────────
@platform_api_bp.route('/fb/api/info', methods=['POST'])
def fb_info():
    return fetch_generic_info(request.get_json().get('url'), 'Facebook')

@platform_api_bp.route('/fb/api/download', methods=['POST'])
def fb_download():
    data = request.get_json()
    return start_generic_download(data.get('url'), data.get('format', 'mp4'), data.get('quality', 'best'))

# ── X (TWITTER) API ───────────────────────────────────────────
@platform_api_bp.route('/tw/api/info', methods=['POST'])
def tw_info():
    return fetch_generic_info(request.get_json().get('url'), 'X (Twitter)')

@platform_api_bp.route('/tw/api/download', methods=['POST'])
def tw_download():
    data = request.get_json()
    return start_generic_download(data.get('url'), data.get('format', 'mp4'), data.get('quality', 'best'))

# ── THREADS API (INTEGRASI NODE.JS) ───────────────────────────
@platform_api_bp.route('/th/api/info', methods=['POST'])
def th_info():
    url = request.get_json().get('url')
    if not url: 
        return jsonify({'error': 'URL tidak boleh kosong'}), 400
    try:
        # Tambahkan timeout 15 detik agar proses Node.js tidak hang selamanya
        process = subprocess.run(['node', 'scraper.js', url], capture_output=True, text=True, check=True, timeout=15)
        out = json.loads(process.stdout.strip())
        
        if out.get('status') and out.get('result', {}).get('status'):
            res = out['result']
            is_video = res.get('type') == 'video'
            media_url = res.get('video') or res.get('image') or res.get('download')
            ext = 'mp4' if is_video else 'jpg'
            
            # Mendapatkan thumbnail
            thumbnail_url = ''
            if not is_video and media_url:
                thumbnail_url = media_url
            elif is_video and media_url:
                thumbnail_url = _generate_thumbnail_with_ffmpeg(media_url)

            return jsonify({
                'type': 'video' if is_video else 'photo',
                'title': 'Post Threads',
                'thumbnail': thumbnail_url,
                'channel': 'Threads User',
                'duration': 0,
                'formats': [{'quality': 'best', 'label': 'Kualitas Terbaik', 'ext': ext, 'filesize': 0}],
                'is_photo': not is_video,
                'audio_formats': [],
                'direct_url': media_url
            })
        return jsonify({'error': 'Gagal mengambil data Threads dari server.'}), 400
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Waktu habis saat menghubungi server Threads (Timeout).'}), 504
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@platform_api_bp.route('/th/api/download', methods=['POST'])
def th_download():
    data = request.get_json()
    url = data.get('url')
    fmt = data.get('format', 'mp4')
    quality = data.get('quality', 'best')
    direct_url = data.get('direct_url')

    if direct_url:
        return start_generic_download(direct_url, fmt, quality)

    try:
        # Tambahkan timeout 15 detik di sini juga
        process = subprocess.run(['node', 'scraper.js', url], capture_output=True, text=True, check=True, timeout=15)
        out = json.loads(process.stdout.strip())
        
        if out.get('status') and out.get('result', {}).get('status'):
            res = out['result']
            dl_url = res.get('video') or res.get('image') or res.get('download')
            return start_generic_download(dl_url, fmt, quality)
            
        return jsonify({'error': 'Gagal memproses URL Threads.'}), 400
    except subprocess.TimeoutExpired:
        return jsonify({'error': 'Waktu habis saat mengekstrak video (Timeout).'}), 504
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ── XIAOHONGSHU (REDNOTE) API ─────────────────────────────────
@platform_api_bp.route('/xhs/api/info', methods=['POST'])
def xhs_info():
    return fetch_generic_info(request.get_json().get('url'), 'Xiaohongshu')

@platform_api_bp.route('/xhs/api/download', methods=['POST'])
def xhs_download():
    data = request.get_json()
    return start_generic_download(data.get('url'), data.get('format', 'mp4'), data.get('quality', 'best'))

# ── IMAGE DOWNLOADER API ──────────────────────────────────────
@platform_api_bp.route('/img/api/info', methods=['POST'])
def img_info():
    return fetch_generic_info(request.get_json().get('url'), 'Image Downloader')

@platform_api_bp.route('/img/api/download', methods=['POST'])
def img_download():
    data = request.get_json()
    return start_generic_download(data.get('url'), data.get('format', 'jpg'), data.get('quality', 'best'))

# ── MP3 UNIVERSAL API ─────────────────────────────────────────
@platform_api_bp.route('/mp3/api/info', methods=['POST'])
def mp3_info():
    return fetch_generic_info(request.get_json().get('url'), 'SoundRip MP3')

@platform_api_bp.route('/mp3/api/download', methods=['POST'])
def mp3_download():
    data = request.get_json()
    return start_generic_download(data.get('url'), 'mp3', 'best')

# ── PROXY GAMBAR (Untuk ByPass CORS Thumbnail IG/FB) ──────────
@platform_api_bp.route('/api/proxy-image', methods=['GET'])
def proxy_image():
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'No URL provided'}), 400
        
    try:
        parsed_url = urlparse(url)
        valid_domains = ['fbcdn.net', 'instagram.com', 'twimg.com', 'xiaohongshu.com', 'xhscdn.com']
        if not any(domain in parsed_url.netloc for domain in valid_domains):
            return jsonify({'error': 'Akses Ditolak: Domain tidak diizinkan untuk Proxy.'}), 403
    except Exception:
        return jsonify({'error': 'Format URL tidak valid'}), 400

    try:
        import urllib.request
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
        resp = urllib.request.urlopen(req, timeout=10)
        return Response(resp.read(), mimetype=resp.headers.get('Content-Type', 'image/jpeg'))
    except Exception:
        return '', 404

# ── GLOBAL PROGRESS STREAM (Dipakai oleh semua platform di atas) ──
@platform_api_bp.route('/platform/api/progress/stream/<download_id>', methods=['GET'])
def progress_stream(download_id):
    return Response(
        stream_with_context(sse_progress_generator(download_id)),
        mimetype='text/event-stream',
        headers={
            'Cache-Control': 'no-cache',
            'X-Accel-Buffering': 'no',
            'Connection': 'keep-alive'
        }
    )

@platform_api_bp.route('/platform/api/download-file/<download_id>', methods=['GET'])
def api_download_file(download_id):
    st = get_progress(download_id)
    if not st or st.get('status') != 'done' or not st.get('file_path'):
        return jsonify({'error': 'File belum siap'}), 404

    file_path = st['file_path']
    ext = st.get('ext', 'mp4')
    dl_name = st.get('download_name', f"download.{ext}")

    ext_lower = ext.lower()
    if ext_lower == 'mp3':
        mimetype = 'audio/mpeg'
    elif ext_lower in ('jpg', 'jpeg'):
        mimetype = 'image/jpeg'
    elif ext_lower in ('png', 'webp'):
        mimetype = f'image/{ext_lower}'
    else:
        mimetype = 'video/mp4'

    return send_file(file_path, as_attachment=True, download_name=dl_name, mimetype=mimetype)