# -*- coding: utf-8 -*-
"""Isıtma talep / üretim — hesap ve ekran birbirini tutuyor mu?

Soğutma tarafında talep (AHU vanası × tasarım kapasitesi) ve üretim (chiller
yük yüzdesi × birim kW) yıllardır çalışıyor. Isıtma tarafı 19.10.2026'da
eklendi ve BİR FARKI var: kazanlarda chiller'ın "CALISMA YUZDELIK" noktasının
karşılığı YOK. Üretim bu yüzden kazanın kendi ΔT'sinden tahmin edilir
(oran = ΔT / tasarım ΔT, tavan 1.0) ve saha noktası eklendiğinde kendiliğinden
yüzdeye geçer.

Bu test üç şeyi korur:
  1) Hesabın kendisi — gerçek fonksiyonlarla, uydurma değerle değil.
  2) Yöntemin GÖRÜNÜR kalması — kullanıcı tahmini gerçek ölçüm sanmasın.
  3) Tek kaynak — kazan birim gücü ve tasarım ΔT'si ekranda KOPYALANMASIN;
     ayar beyaz listelerine eklenmiş olsun (eklenmezse ayar sessizce düşer).
"""
import json
import os
import re
import sys

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass

import ahu_collector as ac  # noqa: E402

PY = open(os.path.join(BURASI, "main_portal.py"), encoding="utf-8").read()
HTML = open(os.path.join(BURASI, "static", "index.html"), encoding="utf-8").read()

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


# ── 1) Kapasite dosyası ──────────────────────────────────────────────────
ISITMA_DOSYA = os.path.join(BURASI, "configs", "ahu_tasarim_isitma_kapasiteleri.json")
SOGUTMA_DOSYA = os.path.join(BURASI, "configs", "ahu_tasarim_kapasiteleri.json")

c("ısıtma kapasite dosyası var", os.path.exists(ISITMA_DOSYA))
ISITMA = json.load(open(ISITMA_DOSYA, encoding="utf-8")) if os.path.exists(ISITMA_DOSYA) else {}
SOGUTMA = json.load(open(SOGUTMA_DOSYA, encoding="utf-8"))

c("dosya adı ASCII (yama/zip yollarında bozulmasın)",
  os.path.basename(ISITMA_DOSYA).isascii(), os.path.basename(ISITMA_DOSYA))
c("dosya mahal → AHU → kW yapısında",
  all(isinstance(v, dict) and all(isinstance(x, (int, float)) for x in v.values())
      for v in ISITMA.values()))
c("kapasiteler pozitif", all(x > 0 for v in ISITMA.values() for x in v.values()))

# Isıtmada olup soğutmada hiç olmayan AHU = büyük olasılıkla yazım hatası
_tanimsiz = [f"{m}/{a}" for m, v in ISITMA.items() for a in v
             if a not in (SOGUTMA.get(m) or {})]
c("ısıtma listesindeki her AHU soğutma listesinde de var", not _tanimsiz, _tanimsiz)

# ── 2) Talep hesabı — gerçek fonksiyon ───────────────────────────────────
_mahal = next(iter(ISITMA)) if ISITMA else "MAS-1"
_ad, _qt = next(iter(ISITMA[_mahal].items()))

_rows = [
    {"Type": "AHU", "Location": _mahal, "Name": _ad,
     "Cool Valve (%)": 0, "Heat Valve (%)": 50},
]
c("talep = kapasite × vana (%%50 → yarısı)",
  abs(ac.talep_isitma_hesapla(_rows) - round(_qt * 0.5, 1)) < 0.2,
  (ac.talep_isitma_hesapla(_rows), _qt))

c("vana kapalıysa talep yok",
  ac.talep_isitma_hesapla([dict(_rows[0], **{"Heat Valve (%)": 0})]) == 0)

c("AHU olmayan satır talebe girmez",
  ac.talep_isitma_hesapla([dict(_rows[0], Type="Chiller")]) == 0)

c("tanımsız AHU talebe girmez (kapasite yoksa atlanır)",
  ac.talep_isitma_hesapla([dict(_rows[0], Name="Ahu-YOK")]) == 0)

# Isıtma talebi SOĞUTMA vanasına bakmaz, soğutma talebi ISITMA vanasına bakmaz
_karisik = [{"Type": "AHU", "Location": _mahal, "Name": _ad,
             "Cool Valve (%)": 100, "Heat Valve (%)": 0}]
c("soğutma vanası açıkken ısıtma talebi 0",
  ac.talep_isitma_hesapla(_karisik) == 0)
c("ısıtma vanası açıkken soğutma talebi 0",
  ac.talep_hesapla(_rows) == 0)

# İki talep AYNI yardımcıyı kullanır — formül iki kopya halinde yaşamasın
_kaynak = open(os.path.join(BURASI, "ahu_collector.py"), encoding="utf-8").read()
c("soğutma ve ısıtma talebi tek formülü paylaşıyor",
  _kaynak.count("def _ahu_talep_hesapla(") == 1
  and "_ahu_talep_hesapla(rows, AHU_TASARIM_KAPASITE_FILE" in _kaynak
  and "_ahu_talep_hesapla(rows, AHU_TASARIM_ISITMA_KAPASITE_FILE" in _kaynak)

# ── 3) Kazan üretimi — ΔT'den tahmin ─────────────────────────────────────
BIRIM = 1950.0
TASARIM_DT = ac._kazan_tasarim_dt()
c("tasarım ΔT kural motorundan geliyor (TARGET_DT_HEAT_EXCHANGER)",
  TASARIM_DT > 0 and "TARGET_DT_HEAT_EXCHANGER" in _kaynak, TASARIM_DT)

_ayar = json.load(open(os.path.join(BURASI, "configs", "chiller_fcu_ayarlari.json"),
                       encoding="utf-8"))
c("kazan ayarları dosyada", _ayar.get("kazan_adedi") and _ayar.get("kazan_birim_kw"),
  (_ayar.get("kazan_adedi"), _ayar.get("kazan_birim_kw")))
c("kazan birim gücü ayarlardan okunuyor, koda gömülü değil",
  "kazan_birim_kw" in _kaynak and "1950" not in _kaynak)
# Tasarım ΔT için AYRI bir ayar açılmadı — aynı eşik iki yerde durmasın
c("ayrı 'kazan tasarım ΔT' ayarı yok (tek kaynak)",
  "kazan_tasarim_dt" not in _ayar)

BIRIM = float(_ayar.get("kazan_birim_kw", 1950))


def _kapali_kazanlar(acik_n):
    """Verilen kazan dışındaki hepsini KAPALI yap (CSV'ye düşüp kirlenmesin)."""
    v = {f"KAZAN-{n} DURUM BILGISI": 0.0 for n in (1, 2, 3)}
    v[f"KAZAN-{acik_n} DURUM BILGISI"] = 1.0
    return v


_tam = dict(_kapali_kazanlar(1), **{"KAZAN-1 INLET": 60.0,
                                    "KAZAN-1 OUTLET": 60.0 + TASARIM_DT})
_s = ac.kazan_uretim_hesapla(_tam)
c("tasarım ΔT'de üretim = birim güç", abs(_s["uretilen_kw"] - BIRIM) < 1, _s)
c("tasarım ΔT'de yük %100", _s["ortalama_yuk_pct"] == 100.0, _s)
c("yöntem 'dt' olarak bildiriliyor", _s["yontem"] == "dt", _s)
c("çalışan adet 1", _s["calisan_adet"] == 1, _s)

_yarim = dict(_kapali_kazanlar(2), **{"KAZAN-2 INLET": 60.0,
                                      "KAZAN-2 OUTLET": 60.0 + TASARIM_DT / 2})
_s = ac.kazan_uretim_hesapla(_yarim)
c("yarı ΔT'de üretim yarı kapasite", abs(_s["uretilen_kw"] - BIRIM / 2) < 1, _s)

_asiri = dict(_kapali_kazanlar(3), **{"KAZAN-3 INLET": 60.0,
                                      "KAZAN-3 OUTLET": 60.0 + TASARIM_DT * 3})
_s = ac.kazan_uretim_hesapla(_asiri)
c("ΔT tasarımı aşsa bile üretim birim gücü GEÇEMEZ",
  abs(_s["uretilen_kw"] - BIRIM) < 1, _s)

_olu = dict(_kapali_kazanlar(1), **{"KAZAN-1 INLET": 60.0, "KAZAN-1 OUTLET": 60.2})
_s = ac.kazan_uretim_hesapla(_olu)
c("ΔT≈0 kazan üretime sayılmaz (0.5°C eşiği)",
  _s["uretilen_kw"] == 0 and _s["calisan_adet"] == 0, _s)
c("üretim yoksa yöntem None", _s["yontem"] is None, _s)

_hepsi_kapali = {f"KAZAN-{n} DURUM BILGISI": 0.0 for n in (1, 2, 3)}
_s = ac.kazan_uretim_hesapla(_hepsi_kapali)
c("tüm kazanlar kapalıyken üretim 0",
  _s["uretilen_kw"] == 0 and _s["calisan_adet"] == 0, _s)

# Üç kazan birlikte
_uc = {}
for n in (1, 2, 3):
    _uc[f"KAZAN-{n} DURUM BILGISI"] = 1.0
    _uc[f"KAZAN-{n} INLET"] = 60.0
    _uc[f"KAZAN-{n} OUTLET"] = 60.0 + TASARIM_DT
_s = ac.kazan_uretim_hesapla(_uc)
c("üç kazan tam yükte = 3 × birim güç", abs(_s["uretilen_kw"] - 3 * BIRIM) < 1, _s)

# Ayarlardaki adet, BACnet şablonundaki kazan sayısını AŞAMAZ
c("ayarlardaki kazan adedi şablon sınırını aşamaz (max 3)",
  "min(kazan_adedi, 3)" in _kaynak)

# Saha noktası eklendiğinde yüzdeye geçiş — ΔT yerine yüzde kullanılmalı
_yuzdeli = dict(_tam, **{"KAZAN-1 CALISMA YUZDELIK": 40.0})
_s = ac.kazan_uretim_hesapla(_yuzdeli)
c("yüzdelik nokta varsa ΔT yerine o kullanılır",
  abs(_s["uretilen_kw"] - BIRIM * 0.4) < 1 and _s["yontem"] == "yuzde", _s)

# Kazan açık ama sıcaklık okunamıyor → tam kapasite, ama yöntem bunu SÖYLEMELİ
_sicaksiz = {"KAZAN-1 DURUM BILGISI": 1.0,
             "KAZAN-2 DURUM BILGISI": 0.0, "KAZAN-3 DURUM BILGISI": 0.0}
_s = ac.kazan_uretim_hesapla(_sicaksiz)
c("sıcaklık okunamazsa tam kapasite sayılır ve yöntem 'kapasite' olur",
  abs(_s["uretilen_kw"] - BIRIM) < 1 and _s["yontem"] == "kapasite", _s)

# ── 4) Geçmiş kaydı — eski kayıtlar bozulmasın ───────────────────────────
import inspect  # noqa: E402

_imza = inspect.signature(ac.gecmis_kaydet).parameters
c("geçmiş kaydı ısıtma alanlarını alıyor",
  "isitma_uretilen_kw" in _imza and "isitma_talep_kw" in _imza)
c("ısıtma alanları opsiyonel (eski çağrı kırılmaz)",
  _imza["isitma_uretilen_kw"].default is None)
c("ekran eksik ısıtma değerini 0 değil null sayıyor",
  "typeof g.isitma_uretilen_kw === 'number') ? g.isitma_uretilen_kw : null" in HTML)

# ── 5) Analiz sonucuna bağlanıyor mu ─────────────────────────────────────
for _alan in ("uretilen_isitma_kw", "talep_isitma_kw", "calisan_kazan_adet",
              "kazan_ortalama_yuk_pct", "isitma_uretim_yontem"):
    c("analiz sonucunda: %s" % _alan, 'sonuc["%s"]' % _alan in _kaynak)

# ── 6) Sunucu → ekran tek kaynak ─────────────────────────────────────────
c("/api/ahu_tasarim_kapasiteleri ısıtma kapasitelerini döndürüyor",
  '"isitma_kapasiteleri": isitma_data' in PY)
c("uç nokta kazan birim gücünü döndürüyor", '"kazan_birim_kw": kazan_birim_kw' in PY)
c("uç nokta kazan tasarım ΔT'sini kural motorundan döndürüyor",
  'CONFIG.get("TARGET_DT_HEAT_EXCHANGER"' in PY)
c("ekran ısıtma kapasitelerini sunucudan alıyor",
  "data.isitma_kapasiteleri" in HTML)
c("ekran kazan birim gücünü sunucudan alıyor",
  "data.kazan_birim_kw" in HTML and "data.kazan_tasarim_dt" in HTML)
c("ekranda kazan birim gücü/tasarım ΔT kopyası yok",
  "1950" not in HTML and "_kazanTasarimDt = data.kazan_tasarim_dt" in HTML)

# Kazan ayarları İKİ beyaz listeye de girmiş olmalı; girmezse değer sessizce düşer
_num = re.search(r"numeric_keys = \[(.*?)\]", PY, re.S).group(1)
c("kazan ayarları sunucu beyaz listesinde",
  "kazan_adedi" in _num and "kazan_birim_kw" in _num)
_keys = re.search(r"const CHILLER_FCU_KEYS = \[(.*?)\]", HTML, re.S).group(1)
c("kazan ayarları ekran listesinde",
  "kazan_adedi" in _keys and "kazan_birim_kw" in _keys)
for _id in ("set_kazan_adedi", "set_kazan_birim_kw"):
    c("ayarlar formunda: %s" % _id, 'id="%s"' % _id in HTML)

# ── 7) Ekran: ısıtma kartı ve yöntem notu ────────────────────────────────
for _id in ("heat_kw_talep", "heat_kw_uretim", "heat_kw_not",
            "cool_kw_talep", "cool_kw_uretim", "heatingKwCard", "coolingKwCard"):
    c("ekranda alan: %s" % _id, 'id="%s"' % _id in HTML)

c("eski tek-başlıklı soğutma kabı kaldırıldı",
  "coolingKwContainer" not in HTML and 'id="talepUretimKwContainer"' in HTML)
c("kart güncelleme tek fonksiyondan",
  "function updateTalepUretimKw(" in HTML and "updateCoolingKw" not in HTML)

# Tahmin olduğu kullanıcıya YAZILMALI — "gerçek ölçüm" sanılmasın
c("ekranda yöntem notu var (ΔT tahmini)",
  "kazan ΔT'sinden tahmin" in HTML)
c("yüzdelik noktaya geçileceği not düşülmüş",
  "yüzdelik modülasyon" in HTML)
c("tam kapasite sayıldığı durum için uyarı var",
  "TAM KAPASİTE sayıldı" in HTML)
c("talebin yalnızca AHU'yu kapsadığı yazıyor",
  "Talep yalnızca AHU" in HTML)
c("ekran ΔT eşiği hesapla ile aynı (0.5)",
  "if (dt < 0.5) return;" in HTML and "if dt < 0.5:" in _kaynak)

# Isıtma grafiği soğutmadan ayrı (dört eğri bir grafikte okunmuyor)
c("ısıtma canlı grafiği ayrı", 'id="isitmaUretimTuketimChart"' in HTML
  and "isitmaUretimTuketimChart = _kwGrafikKur(" in HTML)
c("iki grafik aynı kurucuyu paylaşıyor", HTML.count("function _kwGrafikKur(") == 1)
c("ısıtma verisi yoksa grafik gizleniyor",
  "isitmaContainer.style.display = isitmaVeriVar ? 'block' : 'none'" in HTML)

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)))
_g = sum(1 for _, ok, _ in T if ok)
print("\n%d/%d PASS" % (_g, len(T)))
raise SystemExit(1 if _g != len(T) else 0)
