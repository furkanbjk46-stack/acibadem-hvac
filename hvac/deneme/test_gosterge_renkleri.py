# -*- coding: utf-8 -*-
"""Gösterge okunabilirliği — ok yönü/rengi ve grafik yazıları.

KURAL: TÜKETİM ARTIŞI KÖTÜ HABERDİR.
Streamlit'in varsayılanı tersidir (artı delta yeşil), bu yüzden tüketim
kalemlerinde delta_color="inverse" verilir: ok yukarı -> KIRMIZI, aşağı ->
YEŞİL. Delta bir büyüklük değil de etiketse (birim fiyat, "2025→2026",
"Veri yok", kWh/m² değeri) renk anlam taşımamalı: "off".
Tasarruf bunun tersidir — artı tasarruf iyi haberdir, varsayılan kalır.

Ayrıca: eskiden CSS'te [data-testid="stMetricDelta"]{color:...!important}
vardı; Streamlit'in kırmızı/yeşilini eziyor, bütün oklar lacivert çıkıyordu.
Grafiklerde de lejant ve ipucu yazısı beyazdı — açık zeminde görünmüyordu.
Bu test ikisinin de geri gelmesini engeller.
"""
import ast
import os
import sys

BURASI = os.path.dirname(os.path.abspath(__file__))
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass
KAYNAK = open(os.path.join(BURASI, "app_portal.py"), encoding="utf-8").read()
AGAC = ast.parse(KAYNAK)

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


# ── st.metric çağrılarını topla ──────────────────────────────────────────
def _metin(dugum):
    """Etiketten okunabilen sabit parçayı çıkar (f-string olabilir)."""
    if isinstance(dugum, ast.Constant) and isinstance(dugum.value, str):
        return dugum.value
    if isinstance(dugum, ast.JoinedStr):
        return "".join(p.value for p in dugum.values
                       if isinstance(p, ast.Constant) and isinstance(p.value, str))
    return ""


metrikler = []
for d in ast.walk(AGAC):
    if not (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
            and d.func.attr == "metric"):
        continue
    kw = {k.arg: k.value for k in d.keywords}
    delta_var = len(d.args) >= 3 or "delta" in kw
    renk = kw.get("delta_color")
    if isinstance(renk, ast.Constant):
        _r = renk.value
    elif isinstance(renk, ast.IfExp):
        # delta_color="inverse" if ... else "off" — koşullu da açık bir seçimdir
        _r = _metin(renk.body) or "kosullu"
    elif renk is not None:
        _r = "kosullu"
    else:
        _r = None
    metrikler.append({
        "satir": d.lineno,
        "etiket": _metin(d.args[0]) if d.args else "",
        "delta": delta_var,
        "renk": _r,
    })

c("st.metric çağrıları bulundu", len(metrikler) >= 40, len(metrikler))

# Delta'sı olan her metrik ya açıkça renk belirtir ya da TASARRUF'tur
_belirsiz = [m for m in metrikler
             if m["delta"] and m["renk"] is None and "Tasarruf" not in m["etiket"]]
c("delta'lı her gösterge rengini açıkça seçer", not _belirsiz,
  [(m["satir"], m["etiket"]) for m in _belirsiz])

_tasarruf = [m for m in metrikler if "Tasarruf" in m["etiket"] and m["delta"]]
c("tasarruf göstergeleri varsayılanda (artış = yeşil)",
  _tasarruf and all(m["renk"] is None for m in _tasarruf),
  [(m["satir"], m["renk"]) for m in _tasarruf])

# Tüketim kalemleri ters renkte olmalı
_TUKETIM = ["Dünkü Tüketim", "Şebeke Tüketimi", "Soğutma Tüketimi",
            "Toplam Doğalgaz", "Beklenen Toplam", "Beklenen Şebeke",
            "Beklenen Sebeke"]
for _ad in _TUKETIM:
    # Etiketlerin başında emoji olabiliyor ("⚡ Dünkü Tüketim")
    _bul = [m for m in metrikler if _ad in m["etiket"] and m["delta"]]
    c("tüketim göstergesi ters renkte: %s" % _ad,
      _bul and all(m["renk"] == "inverse" for m in _bul),
      [(m["satir"], m["renk"]) for m in _bul])

# metric_yoy ortak yardımcısı (Toplam Hastane / Şebeke / Toplam Soğutma)
c("özet göstergeler ters renkte", 'f" {unit}", delta,\n                          delta_color="inverse")' in KAYNAK)

# Etiket niteliğindeki deltalar nötr
_ETIKET = ["Ort. Chiller Set", "Toplam Değişim", "Şebeke Değişim",
           "Chiller Değişim", "Toplam R² Skoru", "Beklenen Tüketim",
           "Sistem Sağlığı"]
for _ad in _ETIKET:
    _bul = [m for m in metrikler if _ad in m["etiket"] and m["delta"]]
    c("etiket deltası nötr: %s" % _ad,
      _bul and all(m["renk"] == "off" for m in _bul),
      [(m["satir"], m["renk"]) for m in _bul])

# ── CSS: delta rengi ezilmiyor ───────────────────────────────────────────
c("stMetricDelta rengi CSS ile ezilmiyor",
  '[data-testid="stMetricDelta"] {\n        color:' not in KAYNAK)
c("genel metin kuralı delta'yı dışarıda bırakır",
  'div:not([data-testid="stMetricDelta"]):not([data-testid="stMetricDelta"] *)' in KAYNAK)

# ── Grafik yazıları ──────────────────────────────────────────────────────
c("lejant/ipucu yazısı beyaz değil",
  "font=dict(color='white')" not in KAYNAK and 'font_color="white"' not in KAYNAK)
c("lejant yazısı koyu", KAYNAK.count("font=dict(color='#24324d')") >= 3,
  KAYNAK.count("font=dict(color='#24324d')"))
c("ipucu kutusu yazısı koyu", KAYNAK.count('font_color="#24324d"') >= 3,
  KAYNAK.count('font_color="#24324d"'))
c("eksen etiketleri koyu (5 eksen)",
  KAYNAK.count("tickfont=dict(color='#3a4660'") >= 5,
  KAYNAK.count("tickfont=dict(color='#3a4660'"))
c("eksen başlığı açık mavi bırakılmadı", "font=dict(color='#6da7ec')" not in KAYNAK)

# ── Bölüm kartları (dashboard + aylık birleşik rapor + tahmin & trend) ───
c("ortak kart yardımcısı var", "def _bolum_karti(" in KAYNAK
  and "@contextmanager" in KAYNAK)
c("kart biçimi TEK kuraldan geliyor", '[class*="st-key-kart_"] {' in KAYNAK
  and "border-radius: 14px !important" in KAYNAK)
c("kart içeriği taşmasın diye %100 genişlik",
  '[class*="st-key-kart_"] > div { width: 100% !important; }' in KAYNAK)
c("ölü .dash-section sınıfı kaldırıldı", ".dash-section {" not in KAYNAK)

# Kart anahtarlarını kaynaktan topla: hepsi "kart_" ile başlamalı
_kart_cagri = [d for d in ast.walk(AGAC)
               if isinstance(d, ast.Call) and isinstance(d.func, ast.Name)
               and d.func.id == "_bolum_karti"]
_anahtarlar = [a.args[0].value for a in _kart_cagri
               if a.args and isinstance(a.args[0], ast.Constant)]
c("tüm bölümler kart içinde", len(_anahtarlar) >= 19, len(_anahtarlar))
c("kart anahtarları 'kart_' ile başlar (CSS ona bakıyor)",
  all(k.startswith("kart_") for k in _anahtarlar),
  [k for k in _anahtarlar if not k.startswith("kart_")])
c("kart anahtarları benzersiz", len(set(_anahtarlar)) == len(_anahtarlar),
  [k for k in set(_anahtarlar) if _anahtarlar.count(k) > 1])

# Üç sekmenin de bölümleri karta alınmış olmalı
for _k in ("kart_dun_ozeti", "kart_m2_tuketim", "kart_maliyet_gunluk",      # dashboard
           "kart_birlesik_ozet", "kart_maliyet_aylik", "kart_oneriler",     # aylık rapor
           "kart_pdf_indir", "kart_ai_ilerleme", "kart_ml_egitim",
           "kart_tahmin_coklu_yil", "kart_tahmin_aylik", "kart_ml_model",   # tahmin & trend
           "kart_gelecek_ay", "kart_senaryo", "kart_tasarruf_ozeti"):
    c("kart var: %s" % _k, _k in _anahtarlar)

# ── Kıyas yılı yoksa "0 (kWh)" sütunu basılmaz ───────────────────────────
c("kıyas sütunları koşula bağlı (Tahmin & Trend)", "_kiyas_var = bool(" in KAYNAK)
c("kıyas sütunları koşula bağlı (Aylık Birleşik Rapor)", "_kiyas5 = bool(" in KAYNAK)
c("kıyas yokken sebebi yazılıyor",
  KAYNAK.count("en az iki TAM yıl") + KAYNAK.count("en az iki TAM yil") >= 2)
c("trend %0 iken ok nötr",
  KAYNAK.count('delta_color="inverse" if abs(') >= 4,
  KAYNAK.count('delta_color="inverse" if abs('))

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)))
_g = sum(1 for _, ok, _ in T if ok)
print("\n%d/%d PASS" % (_g, len(T)))
raise SystemExit(1 if _g != len(T) else 0)
