# 🚀 Kita.in - All-in-One Media Downloader

Aplikasi web pengunduh media sosial super cepat berbasis Python Flask dan `yt-dlp`. Mendukung pengunduhan video dan ekstraksi audio (MP3) dari berbagai platform populer.

## ✨ Fitur Utama
- **Multi-Platform:** Mendukung YouTube, TikTok (Tanpa Watermark), Instagram (Reels, IGTV, Post), dan Facebook.
- **Universal MP3:** Konversi media menjadi format audio MP3 berkualitas tinggi.
- **Real-Time Progress Tracking:** Menggunakan *Server-Sent Events (SSE)* untuk menampilkan status, kecepatan unduh (MB/s), dan estimasi waktu (ETA) secara langsung tanpa *polling* yang membebani server.
- **Smart UI/UX:** Antarmuka modern dengan sistem *Grid Cards* dan dukungan *Dark Mode* / *Light Mode* yang otomatis menyesuaikan dengan preferensi sistem operasi perangkat pengguna.
- **Aman & Efisien:** Dilengkapi dengan perlindungan *Rate Limiting* (Anti-Spam), perlindungan CORS & CSRF, serta sistem *Garbage Collector* otomatis di *background thread* untuk membersihkan file usang agar RAM dan *Storage* server tetap lega.

## 🛠️ Teknologi yang Digunakan
- **Backend:** Python 3, Flask, Flask-Limiter, Flask-WTF
- **Engine Unduhan:** `yt-dlp`, FFmpeg
- **Frontend:** HTML5, CSS3, Vanilla JavaScript (ES6)

## ⚙️ Cara Menjalankan Secara Lokal (Localhost)

### 1. Persyaratan Sistem
- Python 3.10 atau versi lebih baru.
- **FFmpeg** (Wajib diinstal dan ditambahkan ke *Environment Variables / PATH* sistem operasi Anda untuk proses penggabungan video dan konversi audio).

### 2. Instalasi
*Clone* repository ini ke komputer Anda:
```bash
git clone https://github.com/XsanZ02/Kita-Downloader.git
cd Kita-Downloader
```

Instal semua *library* Python yang dibutuhkan melalui terminal:
```bash
pip install -r requirements.txt
```

### 3. Jalankan Aplikasi
Jalankan server Flask dengan perintah:
```bash
python app.py
```
Aplikasi web kini dapat diakses melalui browser Anda di alamat `http://localhost:5000`.

## 🔒 Deployment (Production Server)
Jika Anda ingin meng-online-kan (hosting) aplikasi ini ke VPS Linux (Ubuntu), pastikan untuk:
1. Mengganti `SECRET_KEY` pada file `app.py` dengan string acak yang kuat.
2. Tidak menggunakan server bawaan Flask, melainkan menggunakan *WSGI server* yang kuat seperti **Gunicorn**.
3. Melapisi aplikasi dengan *Reverse Proxy* seperti **Nginx** beserta sertifikat SSL (HTTPS).

---
*Dibuat untuk memberikan kemudahan akses pengunduhan media digital secara gratis dan aman.*