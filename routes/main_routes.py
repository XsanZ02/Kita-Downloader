from flask import Blueprint, render_template

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

@main_bp.route('/mp3')
def mp3():
    return render_template('downloader_platform.html', platform='SoundRip MP3', desc='Konversi audio dari ratusan platform menjadi format MP3 tinggi (320kbps).')

@main_bp.route('/tos')
def tos():
    content = [
        {"heading": "1. Ketentuan Penggunaan", "text": "Dengan mengakses situs web Kita.in, Anda setuju untuk mematuhi Syarat dan Ketentuan ini. Layanan ini disediakan secara gratis untuk penggunaan pribadi dan non-komersial."},
        {"heading": "2. Hak Cipta & Legalitas", "text": "Situs ini hanya berfungsi sebagai alat bantu peramban. Kami tidak menyimpan, meng-host, atau mendistribusikan file media apa pun di server kami. Segala risiko terkait hak cipta konten yang diunduh sepenuhnya menjadi tanggung jawab pengguna akhir."},
        {"heading": "3. Penyalahgunaan Layanan", "text": "Dilarang keras menggunakan script otomatis (bot) yang berlebihan untuk mengeksploitasi API kami. Kami berhak memblokir alamat IP yang terdeteksi melakukan spamming."}
    ]
    return render_template('legal.html', title='Terms of Service', last_updated='10 November 2024', content=content)

@main_bp.route('/privacy')
def privacy():
    content = [
        {"heading": "1. Pengumpulan Data Pribadi", "text": "Privasi Anda sangat penting bagi kami. Kita.in tidak meminta pendaftaran, tidak mengumpulkan alamat email, dan tidak menyimpan data identitas pribadi Anda."},
        {"heading": "2. Pencatatan Sistem (Logging)", "text": "Untuk alasan keamanan dan pencegahan serangan DDoS, sistem kami mencatat alamat IP pengunjung secara sementara (Rate Limiting). Data ini otomatis dihapus dan tidak pernah dijual ke pihak ketiga."},
        {"heading": "3. Penggunaan Penyimpanan Lokal", "text": "Kami menggunakan LocalStorage pada peramban Anda murni untuk menyimpan preferensi tema (Mode Gelap/Terang) dan riwayat unduhan agar Anda memiliki pengalaman pengguna yang lebih baik."}
    ]
    return render_template('legal.html', title='Privacy Policy', last_updated='10 November 2024', content=content)