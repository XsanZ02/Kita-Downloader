// Logika Teks Dinamis Berdasarkan Halaman
function getShareText() {
  if (window.location.pathname === '/') {
    return `Cobain Pusat Unduhan Kita.in! Download video YouTube, TikTok, IG, FB gratis dan tanpa batas! 🚀\n\n`;
  }
  const toolName = document.title.split('-')[0].trim();
  return `Cobain alat download ${toolName} super cepat dan gratis di sini! 🚀\n\n`;
}

window.shareWhatsApp = function(e) {
  e.preventDefault();
  const text = encodeURIComponent(getShareText());
  const url = encodeURIComponent(window.location.href);
  window.open(`https://api.whatsapp.com/send?text=${text}${url}`, '_blank');
};

window.shareTwitter = function(e) {
  e.preventDefault();
  const text = encodeURIComponent(getShareText());
  const url = encodeURIComponent(window.location.href);
  window.open(`https://twitter.com/intent/tweet?text=${text}&url=${url}`, '_blank');
};

window.shareTelegram = function(e) {
  e.preventDefault();
  const text = encodeURIComponent(getShareText());
  const url = encodeURIComponent(window.location.href);
  window.open(`https://t.me/share/url?url=${url}&text=${text}`, '_blank');
};

window.shareFacebook = function(e) {
  e.preventDefault();
  const url = encodeURIComponent(window.location.href);
  window.open(`https://www.facebook.com/sharer/sharer.php?u=${url}`, '_blank');
};