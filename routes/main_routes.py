from flask import Blueprint, render_template, request, jsonify, current_app, Response
from flask_mail import Message

# Membuat blueprint baru bernama 'main_bp'
main_bp = Blueprint('main_bp', __name__)

@main_bp.route('/')
def index():
    # Merender template utama, pastikan ada file 'home.html' di dalam folder templates/
    return render_template('home.html')

@main_bp.route('/about')
def about():
    # Contoh halaman lain, merender 'about.html' dari folder templates/
    return render_template('about.html')

@main_bp.route('/tiktok')
def tiktok():
    return render_template('downloader_platform.html', platform='TikTok', desc='Download video TikTok tanpa watermark dengan kualitas HD.')

@main_bp.route('/ig')
def ig():
    return render_template('downloader_platform.html', platform='Instagram', desc='Download Reels, IGTV, dan Postingan Instagram.')

@main_bp.route('/fb')
def fb():
    return render_template('downloader_platform.html', platform='Facebook', desc='Download video publik dari Facebook dengan mudah.')

@main_bp.route('/tw')
def tw():
    return render_template('downloader_platform.html', platform='X (Twitter)', desc='Download video dan GIF dari X (Twitter) dengan resolusi tinggi.')

@main_bp.route('/th')
def th():
    return render_template('downloader_platform.html', platform='Threads', desc='Download video dan gambar dari Threads secara gratis.')

@main_bp.route('/xhs')
def xhs():
    return render_template('downloader_platform.html', platform='Xiaohongshu', desc='Download video dan foto tanpa watermark dari Xiaohongshu (Rednote).')

@main_bp.route('/img')
def img():
    return render_template('downloader_platform.html', platform='Image Downloader', desc='Download gambar publik resolusi tinggi dari Pinterest, Freepik, Imgur, dan lainnya.')

@main_bp.route('/mp3')
def mp3():
    return render_template('downloader_platform.html', platform='SoundRip MP3', desc='Konversi lagu dari Spotify, Apple Music, SoundCloud, YouTube Music dan 1000+ platform lainnya menjadi format MP3 kualitas tinggi (320kbps).')

@main_bp.route('/tos')
def tos():
    content = [
        {"heading": "1. Ketentuan Penggunaan", "text": "Dengan mengakses situs web Kita.in, Anda setuju untuk mematuhi Syarat dan Ketentuan ini. Layanan ini disediakan secara gratis untuk penggunaan pribadi dan non-komersial."},
        {"heading": "2. Hak Cipta & Legalitas", "text": "Situs ini hanya berfungsi sebagai alat bantu peramban. Kami tidak menyimpan, meng-host, atau mendistribusikan file media apa pun di server kami. Segala risiko terkait hak cipta konten yang diunduh sepenuhnya menjadi tanggung jawab pengguna akhir."},
        {"heading": "3. Penyalahgunaan Layanan", "text": "Dilarang keras menggunakan script otomatis (bot) yang berlebihan untuk mengeksploitasi API kami. Kami berhak memblokir alamat IP yang terdeteksi melakukan spamming."}
    ]
    return render_template('legal.html', title='Terms of Service', last_updated='10 November 2024', content=content)

@main_bp.route('/contact', methods=['GET', 'POST'])
def contact():
    if request.method == 'POST':
        data = request.get_json()
        name = data.get('name')
        email = data.get('email')
        message = data.get('message')
        
        if not name or not email or not message:
            return jsonify({'error': 'Semua kolom wajib diisi!'}), 400
            
        try:
            msg = Message(subject=f"Pesan Baru dari {name} (Kita.in)",
                          sender=current_app.config.get('MAIL_USERNAME'),
                          recipients=['kitajokiin03@gmail.com'])
            msg.body = f"Nama: {name}\nEmail: {email}\n\nPesan:\n{message}"
            current_app.mail.send(msg)
            return jsonify({'success': 'Pesan berhasil dikirim!'}), 200
        except Exception as e:
            return jsonify({'error': f'Gagal mengirim pesan. Pastikan konfigurasi email benar.'}), 500
            
    return render_template('contact.html', title='Contact Us')

@main_bp.route('/privacy')
def privacy():
    content = [
        {"heading": "1. Pengumpulan Data Pribadi", "text": "Privasi Anda sangat penting bagi kami. Kita.in tidak meminta pendaftaran, tidak mengumpulkan alamat email, dan tidak menyimpan data identitas pribadi Anda."},
        {"heading": "2. Pencatatan Sistem (Logging)", "text": "Untuk alasan keamanan dan pencegahan serangan DDoS, sistem kami mencatat alamat IP pengunjung secara sementara (Rate Limiting). Data ini otomatis dihapus dan tidak pernah dijual ke pihak ketiga."},
        {"heading": "3. Penggunaan Penyimpanan Lokal", "text": "Kami menggunakan LocalStorage pada peramban Anda murni untuk menyimpan preferensi tema (Mode Gelap/Terang) dan riwayat unduhan agar Anda memiliki pengalaman pengguna yang lebih baik."}
    ]
    return render_template('legal.html', title='Privacy Policy', last_updated='10 November 2024', content=content)

# ── SEO: ROBOTS.TXT & SITEMAP.XML ─────────────────────────────

@main_bp.route('/robots.txt')
def robots_txt():
    """Memberikan instruksi kepada robot Google (Crawler)."""
    lines = [
        "User-agent: *",
        "Allow: /",
        f"Sitemap: {request.host_url.rstrip('/')}/sitemap.xml"
    ]
    return Response("\n".join(lines), mimetype="text/plain")

@main_bp.route('/sitemap.xml')
def sitemap_xml():
    """Membuat peta situs otomatis untuk di-submit ke Google Search Console."""
    pages = [
        '/', '/yt', '/tiktok', '/ig', '/fb', '/tw', '/th', '/xhs', '/img', '/mp3',
        '/about', '/contact', '/privacy', '/tos'
    ]
    
    xml = ['<?xml version="1.0" encoding="UTF-8"?>']
    xml.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    
    for page in pages:
        loc = f"{request.host_url.rstrip('/')}{page}"
        xml.append('  <url>')
        xml.append(f'    <loc>{loc}</loc>')
        priority = '1.0' if page in ['/', '/yt', '/tiktok', '/ig', '/mp3'] else ('0.8' if len(page) <= 4 else '0.5')
        xml.append(f'    <priority>{priority}</priority>')
        xml.append('  </url>')
        
    xml.append('</urlset>')
    return Response("\n".join(xml), mimetype="application/xml")