# -*- coding: utf-8 -*-
"""
ENERJİ VE VERİMLİLİK PORTALI — TASARIM DİLİ (29.10.2026)
=========================================================

Kaynaklar (aynı görünüm için birebir alındı):
  · Başlık kartı ............ static/index.html + static/synapse_tema.css (Mekanik Zeka)
  · Sekmeler, KPI kartları .. merkez/pages/lokasyon_detay.py (Synapse lokasyon Dashboard'u)
  · Simgeler ................ synapse_ikonlar.py (merkez/ikonlar.py kopyası)
  · Yazı tipi ............... Inter — Mekanik Zeka ile aynı

YALNIZ GÖRÜNÜM: hiçbir değer hesaplanmaz / değiştirilmez / canlandırılmaz.
Kartlar, kendisine verilen metni olduğu gibi yazar.
"""
import html as _html

try:
    import synapse_ikonlar as IK
except Exception:              # simge modülü yoksa portal yine açılsın
    IK = None


def ikon(ad: str, boyut: int = 22, renk: str = None) -> str:
    return IK.ikon(ad, boyut, renk) if IK else ""


def renk(ad: str) -> str:
    return IK.renk(ad) if IK else "#2a78d6"


# ── Genel tema: yazı tipi, başlık, sekmeler, bölüm başlıkları, kartlar ──────
CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800;900&display=swap');
/* Yazı tipi: Mekanik Zeka ile aynı (Inter). Simge yazı tipleri hariç. */
html, body, .stApp, .stApp p, .stApp span, .stApp div, .stApp label, .stApp button,
.stApp input, .stApp textarea, .stApp select, .stApp h1, .stApp h2, .stApp h3, .stApp h4, .stApp li, .stApp td, .stApp th {
    font-family: Inter, system-ui, -apple-system, 'Segoe UI', sans-serif;
}
span[data-testid="stIconMaterial"], [data-testid="stExpanderToggleIcon"] span,
.material-symbols-rounded { font-family: 'Material Symbols Rounded' !important; }
.stApp { font-feature-settings: "tnum" 1; -webkit-font-smoothing: antialiased; }

/* ── BAŞLIK KARTI (Mekanik Zeka .header) ── */
@keyframes synAkis { 0% { background-position: 0% 50%; } 100% { background-position: 200% 50%; } }
@keyframes synYukselis { from { opacity: 0; transform: translateY(6px); } to { opacity: 1; transform: none; } }
@keyframes synCizgi { 0%, 100% { transform: scaleX(.35); opacity: .5; } 50% { transform: scaleX(1); opacity: 1; } }
@keyframes synNokta { 0%, 100% { opacity: 1; transform: scale(1); } 50% { opacity: .55; transform: scale(.8); } }
.syn-baslik { background: #ffffff; padding: 22px 30px 16px; border-radius: 14px; margin: 0 0 18px;
    border: 1px solid rgba(24,26,30,0.10);
    box-shadow: 0 1px 1px rgba(20,22,26,.05), 0 8px 18px -10px rgba(20,22,26,.22), inset 0 1px 0 rgba(255,255,255,.95); }
.syn-baslik-ust { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.syn-baslik h1 { margin: 0 0 4px !important; padding: 0 !important; display: flex; align-items: center; gap: 12px;
    font-size: 28px !important; font-weight: 800 !important; letter-spacing: 1px !important; line-height: 1.25 !important; }
.syn-baslik h1 .syn-metin {
    background: linear-gradient(90deg, #0f1f3d 0%, #133273 25%, #2a78d6 45%, #7fb2ee 50%, #2a78d6 55%, #133273 75%, #0f1f3d 100%);
    background-size: 200% 100%; -webkit-background-clip: text; background-clip: text;
    -webkit-text-fill-color: transparent; color: #0f1f3d !important;
    animation: synYukselis .8s ease-out both, synAkis 6s linear infinite; }
.syn-baslik .syn-alt { font-size: 12px !important; font-weight: 600 !important; letter-spacing: 2.5px !important;
    text-transform: uppercase; color: #2a78d6 !important; animation: synYukselis .8s .15s ease-out both; }
.syn-baslik .syn-dugmeler { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.syn-baslik a.syn-dugme { display: inline-flex; align-items: center; gap: 6px; padding: 8px 16px; text-decoration: none !important;
    background: #fafaf8; color: #24324d !important; font-weight: 600; font-size: 12px;
    border: 1px solid rgba(24,26,30,0.10); border-radius: 10px; transition: transform .15s, box-shadow .2s, border-color .2s; }
.syn-baslik a.syn-dugme:hover { color: #133273 !important; border-color: rgba(42,120,214,.45); background: #fff;
    transform: translateY(-1px); box-shadow: 0 6px 14px -8px rgba(19,50,115,.35); }
.syn-baslik a.syn-dugme span { color: inherit !important; }
.syn-durum { position: relative; margin-top: 14px; padding-top: 14px; display: flex; align-items: center;
    justify-content: space-between; gap: 12px; flex-wrap: wrap; }
.syn-durum::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 2px; border-radius: 2px;
    background: linear-gradient(90deg, transparent, #2a78d6, transparent); animation: synCizgi 3s ease-in-out infinite; }
.syn-durum .syn-hazir { display: flex; align-items: center; gap: 8px; font-weight: 600; font-size: 13px; color: #0f1f3d !important; }
.syn-durum .syn-nokta { width: 10px; height: 10px; border-radius: 50%; background: #0ca30c; animation: synNokta 1.6s ease-in-out infinite; }
.syn-durum .syn-bilgi { font-size: 11px; color: #46536b !important; font-weight: 600; letter-spacing: .4px; }

/* ── SEKMELER (Synapse lokasyon Dashboard'u) ── */
.stTabs [data-baseweb="tab-list"] { background: transparent !important; gap: 0 !important;
    border-bottom: 1px solid rgba(19,50,115,0.08) !important; }
.stTabs [data-baseweb="tab"] { background: transparent !important; padding: 10px 18px !important;
    text-transform: none !important; letter-spacing: 0 !important; border-bottom: 2px solid transparent; transition: color .2s; }
.stTabs [data-baseweb="tab"] p { display: inline-flex !important; align-items: center;
    text-transform: none !important; letter-spacing: 0 !important; font-size: 14px !important;
    font-weight: 600 !important; color: #24324d !important; }
.stTabs [data-baseweb="tab"]:hover p { color: #133273 !important; }
.stTabs [aria-selected="true"] { background: transparent !important;
    box-shadow: inset 0 -2px 0 #2a78d6, 0 2px 8px rgba(19,50,115,0.18) !important; }
.stTabs [aria-selected="true"] p { color: #2a78d6 !important; }
.stTabs [data-baseweb="tab-highlight"] { background-color: #2a78d6 !important; }

/* ── BÖLÜM BAŞLIĞI (Synapse .sec) ── */
.syn-sec { display: flex; align-items: center; gap: 7px; font-size: 12px !important; font-weight: 700 !important;
    letter-spacing: 1.4px !important; text-transform: uppercase; color: #133273 !important;
    padding: 4px 0 8px; margin: 16px 0 12px; border-bottom: 1px solid rgba(24,26,30,0.10); }
.syn-sec .syn-sec-not { margin-left: auto; font-size: 10px !important; font-weight: 500 !important;
    letter-spacing: .3px !important; text-transform: none; color: #46536b !important; }

/* ── KPI KARTI (Synapse .dz-kart): simge solda, değer yanında ── */
@keyframes synKartGir { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: none; } }
.syn-izgara { display: grid; grid-template-columns: repeat(auto-fill, minmax(var(--min, 210px), 1fr)); gap: 10px; margin-bottom: 6px; }
.syn-kart { background: #fff; border: 1px solid rgba(24,26,30,.10); border-radius: 16px; padding: 11px 15px;
    display: flex; align-items: center; gap: 12px; min-width: 0;
    box-shadow: 0 1px 1px rgba(20,22,26,.05), 0 10px 22px -12px rgba(20,22,26,.22);
    transition: transform .2s, box-shadow .2s; animation: synKartGir .5s ease-out both; }
.syn-kart:hover { transform: translateY(-2px); box-shadow: 0 2px 4px rgba(19,50,115,.06), 0 14px 30px -16px rgba(19,50,115,.28); }
.syn-kart .syn-ik { flex-shrink: 0; display: flex; }
.syn-kart .syn-ic { min-width: 0; }
.syn-kart .syn-et { font-size: 10px !important; letter-spacing: 1.2px; color: #46536b !important; font-weight: 600 !important;
    text-transform: uppercase; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.syn-kart .syn-dg { font-size: 26px !important; font-weight: 700 !important; color: #133273 !important; line-height: 1.15; margin-top: 1px;
    white-space: nowrap; }
.syn-kart .syn-br { font-size: 9.5px !important; font-weight: 500 !important; color: #46536b !important; margin-left: 3px; }
.syn-kart .syn-alt { font-size: 10px !important; color: #46536b !important; margin-top: 1px; }
.syn-kart .syn-alt.syn-iyi { color: #0a7d0a !important; font-weight: 700 !important; }
.syn-kart .syn-alt.syn-kotu { color: #c0392b !important; font-weight: 700 !important; }
.syn-izgara .syn-kart:nth-child(2) { animation-delay: .05s; } .syn-izgara .syn-kart:nth-child(3) { animation-delay: .10s; }
.syn-izgara .syn-kart:nth-child(4) { animation-delay: .15s; } .syn-izgara .syn-kart:nth-child(5) { animation-delay: .20s; }
.syn-izgara .syn-kart:nth-child(n+6) { animation-delay: .25s; }

/* st.metric de aynı kart dilinde görünsün (diğer sekmeler) */
[data-testid="stMetric"] { background: #fff; border: 1px solid rgba(24,26,30,.10); border-radius: 16px; padding: 11px 15px;
    box-shadow: 0 1px 1px rgba(20,22,26,.05), 0 10px 22px -12px rgba(20,22,26,.22); }
[data-testid="stMetricLabel"] p { font-size: 10px !important; letter-spacing: 1.2px !important; font-weight: 600 !important;
    text-transform: uppercase !important; color: #46536b !important; }
[data-testid="stMetricValue"] { font-size: 24px !important; font-weight: 700 !important; color: #133273 !important; }

@media (prefers-reduced-motion: reduce) {
    .syn-baslik *, .syn-durum::before, .syn-kart { animation: none !important; transition: none !important; }
    .syn-baslik h1 .syn-metin { -webkit-text-fill-color: #0f1f3d; background: none; }
}
</style>
"""

# Sekme sırası ile simge eşlemesi (Synapse simgeleri)
SEKMELER = [
    ("Enerji Diyagramı", "trdp"),
    ("Veri Girişi", "kayit"),
    ("Dashboard", "grafik"),
    ("PDF Rapor", "takvim"),
    ("Veri Görüntüleme", "verim"),
    ("Aylık Birleşik Rapor", "yonetim"),
    ("Tahmin & Trend", "zeka"),
]
SEKME_KAP = "enerji_sekmeler"


def sekme_css() -> str:
    """Sekme adlarının önüne Synapse'in hareketli simgeleri."""
    if not IK:
        return ""
    kurallar = "".join(
        IK.etiket_css('.st-key-%s [role="tab"]:nth-child(%d) p' % (SEKME_KAP, i + 1), simge, 16)
        for i, (_, simge) in enumerate(SEKMELER))
    return "<style>" + kurallar + "</style>"


def baslik_html(baslik: str, alt: str, durum: str, bilgi: str, dugmeler: list) -> str:
    """Mekanik Zeka başlık kartı. dugmeler: [(etiket, simge, href)]."""
    e = _html.escape
    d_html = "".join(
        '<a class="syn-dugme" href="%s" target="_top">%s<span>%s</span></a>'
        % (e(href, quote=True), ikon(simge, 15), e(etiket)) for etiket, simge, href in dugmeler)
    return (
        '<div class="syn-baslik"><div class="syn-baslik-ust"><div>'
        '<h1>%s<span class="syn-metin">%s</span></h1>'
        '<div class="syn-alt">%s</div></div>'
        '<div class="syn-dugmeler">%s</div></div>'
        '<div class="syn-durum"><div class="syn-hazir"><span class="syn-nokta"></span>%s</div>'
        '<div class="syn-bilgi">%s</div></div></div>'
        % (ikon("enerji", 30), e(baslik), e(alt), d_html, e(durum), e(bilgi)))


def bolum(baslik: str, simge: str = "", notu: str = "") -> str:
    """Synapse bölüm başlığı (ÖZET, KOJEN & KAYNAK gibi)."""
    e = _html.escape
    return ('<div class="syn-sec">%s%s%s</div>'
            % (ikon(simge, 16) if simge else "", e(baslik),
               '<span class="syn-sec-not">%s</span>' % e(notu) if notu else ""))


def kart(simge: str, etiket: str, deger: str, birim: str = "", alt: str = "", alt_sinif: str = "") -> str:
    """Synapse KPI kartı. Değer METİN olarak gelir, olduğu gibi yazılır."""
    e = _html.escape
    return ('<div class="syn-kart"><div class="syn-ik">%s</div><div class="syn-ic">'
            '<div class="syn-et">%s</div>'
            '<div class="syn-dg">%s<span class="syn-br">%s</span></div>%s</div></div>'
            % (ikon(simge, 30), e(etiket), e(deger), e(birim),
               '<div class="syn-alt %s">%s</div>' % (alt_sinif, e(alt)) if alt else ""))


def izgara(kartlar: list, min_px: int = 210) -> str:
    return '<div class="syn-izgara" style="--min:%dpx;">%s</div>' % (min_px, "".join(kartlar))


def degisim(pct, ters: bool = True):
    """(metin, sınıf). Tüketimde artış kötü (ters=True): ▲ kırmızı, ▼ yeşil."""
    if pct is None:
        return "", ""
    yukari = pct > 0
    sinif = ("syn-kotu" if yukari else "syn-iyi") if ters else ("syn-iyi" if yukari else "syn-kotu")
    return ("%s %%%s" % ("▲" if yukari else "▼", f"{abs(pct):.1f}".replace(".", ","))), sinif
