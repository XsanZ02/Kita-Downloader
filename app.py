import os
from dotenv import load_dotenv
from flask import Flask, render_template, redirect, url_for, request, jsonify
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from urllib.parse import urlparse
from flask_wtf.csrf import CSRFProtect
from routes.yt_routes import yt_bp
from routes.main_routes import main_bp
from routes.platform_api_routes import platform_api_bp

# Muat variabel lingkungan dari file .env
load_dotenv()

app = Flask(__name__)

# 0. Konfigurasi Secret Key dan CSRF Protection
# Mengambil SECRET_KEY dari .env, dengan nilai bawaan (fallback) untuk local development
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'default-secret-key-untuk-development')
csrf = CSRFProtect(app)

# 0. Inisialisasi Keamanan Rate Limiter
limiter = Limiter(
    get_remote_address,
    app=app,
    default_limits=["200 per day", "20 per minute"],
    storage_uri="memory://"
)

# 0.5 Keamanan CORS & Pencegahan Hotlinking
@app.before_request
def restrict_api_access():
    # Hanya lindungi jalur API (info, download, dll)
    if '/api/' in request.path:
        origin = request.headers.get('Origin')
        referer = request.headers.get('Referer')
        
        # Mendapatkan domain dasar website kita (otomatis mendeteksi localhost/domain hosting)
        allowed_host = request.host_url
        
        # 1. Pengecekan Origin (biasanya dikirim oleh browser saat Fetch/AJAX)
        if origin and not origin.startswith(allowed_host.rstrip('/')):
            return jsonify({'error': 'Akses Ditolak: Cross-Origin Resource Sharing (CORS) tidak diizinkan.'}), 403
            
        # 2. Pengecekan Referer (mencegah orang menaruh link langsung di web lain)
        if referer:
            referer_domain = urlparse(referer).netloc
            allowed_domain = urlparse(allowed_host).netloc
            if referer_domain != allowed_domain:
                return jsonify({'error': 'Akses Ditolak: Invalid Referer.'}), 403

# 1. Registrasi Blueprint untuk YouTube Downloader
# Menggunakan url_prefix='/yt' agar semua rute di yt_routes.py diawali dengan /yt
# Ini sesuai dengan script.js Anda yang memanggil fetch('/yt/api/info')
app.register_blueprint(yt_bp, url_prefix='/yt')

# 2. Registrasi Blueprint untuk Halaman Utama web (home, about, dll)
# Karena tidak memakai url_prefix, rute di dalamnya akan diakses langsung di root '/'
app.register_blueprint(main_bp)

# 3. Registrasi Blueprint untuk API Platform Lain (TikTok, IG, FB, dll)
app.register_blueprint(platform_api_bp)

# 4. Custom Error Handler untuk 404 (Halaman Tidak Ditemukan)
@app.errorhandler(404)
def page_not_found(e):
    return render_template('404.html'), 404

# 5. Custom Error Handler untuk 429 (Terlalu Banyak Request)
@app.errorhandler(429)
def ratelimit_handler(e):
    # Kembalikan JSON jika yang terkena limit adalah API Fetch Javascript
    if request.path.endswith('/info') or request.path.endswith('/download'):
        return jsonify({'error': 'Terlalu banyak permintaan (Spam terdeteksi). Silakan tunggu beberapa menit.'}), 429
    return render_template('404.html'), 429

if __name__ == '__main__':
    # Menjalankan server Flask
    app.run(debug=True, host='0.0.0.0', port=5000)