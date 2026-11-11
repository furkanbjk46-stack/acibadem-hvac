# -*- coding: utf-8 -*-
"""İnternetsiz çalışma (11.11.2026, Maslak): sayfalar internetteki kaynağı beklemez,
kütüphaneler yerelde, dış hava internet yokken gerçek bir kaynaktan gelir. Ağ kullanmaz."""
import os
import re
import sys

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import logging  # noqa: E402
logging.disable(logging.CRITICAL)

T = []


def c(ad, kosul, ek=""):
    T.append((ad, bool(kosul), ek))


def oku(*p):
    return open(os.path.join(BURASI, *p), encoding="utf-8").read()


# ── Mekanik Zeka arayüzü ─────────────────────────────────────────────────
idx = oku("static", "index.html")
dis = re.findall(r'<(?:script|link)[^>]+(?:src|href)="(https?://[^"]+)"', idx)
c("index.html internetten betik/stil yüklemez", dis == [], dis)
yerel = re.findall(r'<(?:script src|link rel="stylesheet" href)="/static/vendor/([^"]+)"', idx)
c("index.html kütüphaneleri static/vendor'dan yükler",
  set(yerel) == {"fontawesome-all.css", "chart.umd.min.js", "xlsx.full.min.js", "html2canvas.min.js",
                 "jspdf.umd.min.js", "jspdf.plugin.autotable.min.js"}, yerel)
_fa = oku("static", "vendor", "fontawesome-all.css")
c("Font Awesome CSS: yazı tipleri gömülü, dışarıya adres yok",
  _fa.count("data:font/woff2;base64,") == _fa.count("@font-face") > 0 and "../webfonts" not in _fa
  and not re.search(r"url\((?!data:)", _fa))
c("Font Awesome JS sürümü kullanılmaz (animasyonlu Synapse simgelerini engelliyordu)",
  "fontawesome-all.min.js" not in idx)
for ad in yerel:
    yol = os.path.join(BURASI, "static", "vendor", ad)
    c("vendor/%s var ve dolu" % ad, os.path.exists(yol) and os.path.getsize(yol) > 30000,
      os.path.getsize(yol) if os.path.exists(yol) else "yok")
c("Chart.js sürümü 4.4.1", "4.4.1" in oku("static", "vendor", "chart.umd.min.js")[:5000] or
  "4.4.1" in oku("static", "vendor", "chart.umd.min.js"))
c("açılış adımları ayrı ayrı korunur (bir grafik hatası diğerlerini durdurmaz)",
  "[loadLocations, checkConnection, initChart, initUretimTuketimChart, loadUretimTuketimGecmis]" in idx
  and "try { adim(); }" in idx)

import guncelleme_yayinla as GY  # noqa: E402
c("vendor dosyaları yama ile gönderilebilir (.js)", all(GY.yayinlanabilir_mi("static/vendor/" + a) for a in yerel))

# ── Ana sayfa / giriş sayfası (main_portal) ──────────────────────────────
mp = oku("main_portal.py")
ns = {"re": re}
exec(mp[mp.index("_INTERNET_KAYNAK_SATIRI = re.compile("):mp.index("def _load_or_create_portal_html")], ns)
portal = oku("static", "portal.html")
temiz = ns["_internetsiz_html"](portal)
c("portal.html sunulurken internet adresleri ayıklanır (dosyaya dokunmadan)",
  re.search(r"https://(fonts|images|cdnjs)", portal) and not re.search(r"https://(fonts|images|cdnjs)", temiz))
ornek = ('<head>\n  <link rel="preconnect" href="https://fonts.googleapis.com">\n'
         '  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" rel="stylesheet">\n'
         '<style>\n  @import url(\'https://fonts.googleapis.com/css2?family=Inter&display=swap\');\n'
         '  .a { background-image: url(\'https://images.unsplash.com/x.jpg?w=1\'); color: red; }\n</style>')
t = ns["_internetsiz_html"](ornek)
c("Google Fonts satırları ve @import silinir", "googleapis" not in t)
c("Font Awesome CSS → yerel CSS", '/static/vendor/fontawesome-all.css' in t and "cdnjs" not in t)
c("tanınmayan arka plan fotoğrafı kaldırılır, diğer stil kalır", "unsplash" not in t and "color: red" in t)
_bil = ns["_internetsiz_html"]("<head></head><style>.a{background-image:url('https://images.unsplash.com/photo-1581094794329-c8112a89af12?w=1000');}</style>")
c("bilinen fotoğraf gömülü kopyaya bağlanır ve görsel CSS'i eklenir",
  "var(--gorsel-photo-1581094794329-c8112a89af12)" in _bil and "/static/vendor/portal_gorseller.css" in _bil and "unsplash" not in _bil)
_gc = oku("static", "vendor", "portal_gorseller.css")
c("görsel CSS'inde iki fotoğraf da gömülü", _gc.count("data:image/jpeg;base64,") == 2 and "https://images" not in _gc)
c("üretilen giriş sayfası şablonu da internetsiz sunulur", "_internetsiz_html(_portal_html_oku())" in mp)
c("ikinci sayfa şablonunda Google Fonts yok",
  mp.count("fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800") == 0)

# ── Dış hava yedeği (ahu_collector) ──────────────────────────────────────
import ahu_collector as AC  # noqa: E402
import hava_durumu as HD  # noqa: E402

_eski_synapse, _eski_csv = HD._synapse_hava, AC._enerji_nokta_csv_oku
HD._synapse_hava = lambda b, s, tahmin: {b: {"Hava_Sicaklik_Ort_C": 9.6}}
AC._enerji_nokta_csv_oku = lambda nokta, csv_yolu=None: 6.4
c("1) canlı BACnet sensörü varsa o", AC._oat_yedek({"DIS HAVA": 11.2}) == (11.2, "BACnet dış hava sensörü (canlı)"))
c("2) sensör yoksa Synapse günlük ortalama", AC._oat_yedek({}) == (9.6, "Synapse günlük ortalama"))
HD._synapse_hava = lambda b, s, tahmin: {}
c("3) Synapse de yoksa 07:05 BACnet okuması", AC._oat_yedek(None) == (6.4, "BACnet 07:05 okuması"))
AC._enerji_nokta_csv_oku = lambda nokta, csv_yolu=None: None
c("4) hiçbiri yoksa 20 °C", AC._oat_yedek(None) == (20.0, "varsayılan"))
c("saçma sensör değeri (ör. 999) kullanılmaz", AC._oat_yedek({"DIS HAVA": 999})[1] != "BACnet dış hava sensörü (canlı)")
HD._synapse_hava, AC._enerji_nokta_csv_oku = _eski_synapse, _eski_csv
_ac = oku("ahu_collector.py")
c("analizde dış hava canlı BACnet okumasından SONRA alınır",
  _ac.index("enerji_verileri = energy_verileri_oku(enerji_config)") < _ac.index("oat = _oat_cek(enerji_verileri=enerji_verileri)"))
_sahte = AC.urllib.request.urlopen
AC.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError("timed out"))
c("internet yoksa _oat_cek yedeğe düşer", AC._oat_cek(41.1, 29.0, {"DIS HAVA": 8.8}) == 8.8)
AC.urllib.request.urlopen = _sahte

# ── Hava: internet yokken her istekte zaman aşımı beklenmez ──────────────
import urllib.request as _ur  # noqa: E402
_sayac = {"n": 0}
_eski_uo = _ur.urlopen


def _asim(*a, **k):
    _sayac["n"] += 1
    raise OSError("timed out")


_ur.urlopen = _asim
HD._INTERNET["yok_bitis"] = 0.0
for _ in range(3):
    try:
        HD._getir("https://api.open-meteo.com/v1/forecast?x=1")
    except OSError:
        pass
c("internet yoksa yalnız ilk istek denenir; sonrakiler beklemeden yedek yola geçer", _sayac["n"] == 1, _sayac)
c("internet bekleme süresi kısa (≤ 6 sn) ve başarısızlık 30 dk hatırlanır",
  HD.INTERNET_ZAMAN_ASIMI <= 6 and HD.INTERNET_YOK_SN == 1800)
HD._INTERNET["yok_bitis"] = 0.0
_ur.urlopen = _eski_uo

hata = [x for x in T if not x[1]]
for ad, ok, ek in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(ek)[:300]))
print("%d/%d PASS" % (len(T) - len(hata), len(T)))
sys.exit(1 if hata else 0)
