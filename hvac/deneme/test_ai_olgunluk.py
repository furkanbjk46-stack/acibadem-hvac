# -*- coding: utf-8 -*-
"""AI olgunluk puanı — kod ile belge/konfig tutarlılığı.

    python hvac/deneme/test_ai_olgunluk.py

Neden var: 20.09.2026'da fark edildi ki tanıtım belgelerindeki "%92 AI olgunluk"
rakamı ELLE yazılmıştı; kodun hesabı (ai_progress.py) bambaşkaydı ve "İleri AI"
kategorisi 0/20 idi. Bu test, iddia ile gerçeğin bir daha sessizce ayrışmasını
engeller:

  1) Puan koddan hesaplanabiliyor ve kategoriler tutarlı mı
  2) configs/ai_features.json'daki her "active: true" özelliğin kodda gerçek bir
     karşılığı var mı (yoksa puan şişirilmiş demektir)
  3) Belgelerde kodun üretemeyeceği bir puan yazıyor mu
"""
import json
import os
import re
import sys

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import logging
logging.disable(logging.CRITICAL)

import ai_progress as ap

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


# ── 1) Puan koddan hesaplanıyor ──────────────────────────────────────────
r = ap.calculate_ai_progress()
c("puan hesaplanabiliyor", isinstance(r.get("total_score"), int), r.get("total_score"))
_kat = r["categories"]
c("dört kategori de var", set(_kat) == {"data_maturity", "feedback", "feature_maturity", "advanced_ai"},
  list(_kat))
_toplam = sum(v["score"] for v in _kat.values())
c("toplam puan kategorilerin toplamıdır", _toplam == r["total_score"], (_toplam, r["total_score"]))
c("hiçbir kategori tavanını aşmıyor", all(v["score"] <= v["max"] for v in _kat.values()),
  {k: (v["score"], v["max"]) for k, v in _kat.items()})
c("puan 0-100 aralığında", 0 <= r["total_score"] <= 100, r["total_score"])

# ── 2) Aktif işaretlenen ileri özelliğin kodda karşılığı var mı ──────────
# "active: true" demek "bu yetenek sahada çalışıyor" demektir. Kanıt: ilgili
# modül/fonksiyon kodda gerçekten bulunmalı.
KANIT = {
    "prediction_model": [
        (os.path.join(BURASI, "monthly_report", "forecast_engine.py"), "class MLPredictor"),
        (os.path.join(BURASI, "monthly_report", "forecast_engine.py"), "def auto_train_if_needed"),
    ],
    "feedback_filtering": [
        # Geri bildirim SADECE kaydediliyorsa filtre yok demektir; gerçek filtre
        # kurulunca training_data'yı OKUYUP öneriyi değiştiren kod eklenmeli.
        (os.path.join(BURASI, "monthly_report", "savings_engine.py"), "def filtrele_geri_bildirimle"),
    ],
    "statistical_anomaly": [
        (os.path.join(BURASI, "monthly_report", "savings_engine.py"), "z_score"),
    ],
    "weather_api": [
        (os.path.join(BURASI, "data_collector.py"), "weather"),
    ],
}

_ozellikler = r["features"]
for _ad, _kanitlar in KANIT.items():
    _aktif = _ozellikler.get(_ad, {}).get("active", False)
    if not _aktif:
        c(f"[{_ad}] kapalı — puana eklenmiyor", True)
        continue
    _eksik = []
    for _yol, _iz in _kanitlar:
        try:
            with open(_yol, encoding="utf-8") as f:
                if _iz not in f.read():
                    _eksik.append(f"{os.path.basename(_yol)}:{_iz}")
        except Exception as e:
            _eksik.append(f"{os.path.basename(_yol)} okunamadı: {e}")
    c(f"[{_ad}] AKTİF işaretli ve kodda karşılığı var", not _eksik, _eksik)

# Geri bildirim: kaydediliyor mu, kullanılıyor mu? (durum tespiti — iddia kontrolü)
_se = open(os.path.join(BURASI, "monthly_report", "savings_engine.py"), encoding="utf-8").read()
_kaydediyor = "def learn_from_outcome" in _se
_kullaniyor = bool(re.search(r"for .* in self\.training_data|self\.training_data\[", _se))
c("geri bildirim kaydı var", _kaydediyor)
c("geri bildirim filtresi bayrağı, gerçek kullanımla tutarlı",
  _ozellikler["feedback_filtering"]["active"] == _kullaniyor,
  f"bayrak={_ozellikler['feedback_filtering']['active']} gercek_kullanim={_kullaniyor}")

# ── 3) Belgelerdeki puan iddiası koddan üretilebilir mi ──────────────────
# Kodun verebileceği EN YÜKSEK puan: tüm kategoriler tavanda + yalnızca gerçekten
# aktif ileri özellikler.
_ileri = ("statistical_anomaly", "weather_api", "prediction_model", "feedback_filtering")
_ileri_tavan = sum(v["points"] for k, v in _ozellikler.items() if k in _ileri and v["active"])
_temel_tavan = sum(v["points"] for k, v in _ozellikler.items() if k not in _ileri)
_mumkun_en_yuksek = 25 + 25 + _temel_tavan + _ileri_tavan

BELGELER = ["vizyon_raporu.html", "sistem_tanitim_raporu.html",
            "mekanik_zeka_sunum.html", "enerji_ve_verimlilik_sunum.html"]
_sisirilmis = []
for _b in BELGELER:
    _yol = os.path.join(BURASI, _b)
    if not os.path.exists(_yol):
        continue
    _metin = open(_yol, encoding="utf-8").read()
    for _m in re.finditer(r"%(\d{2,3})\s*(?:—|-)?\s*(?:AI )?(?:Otonom|olgunluk)", _metin, re.I):
        _deger = int(_m.group(1))
        if _deger > _mumkun_en_yuksek:
            _sisirilmis.append(f"{_b}: %{_deger} (kod en fazla %{_mumkun_en_yuksek} üretebilir)")
c("belgelerde kodun üretemeyeceği AI puanı yok", not _sisirilmis, _sisirilmis)

# ai_features.json varsa geçerli JSON olmalı ve tanınan anahtarlar içermeli
_af = os.path.join(BURASI, "configs", "ai_features.json")
if os.path.exists(_af):
    try:
        _veri = json.load(open(_af, encoding="utf-8"))
        c("ai_features.json geçerli JSON", True)
        _tanimsiz = [k for k in _veri if not k.startswith("_") and k not in ap._DEFAULT_FEATURES]
        c("ai_features.json'da tanımsız özellik yok", not _tanimsiz, _tanimsiz)
        _gerekce_yok = [k for k, v in _veri.items()
                        if not k.startswith("_") and isinstance(v, dict)
                        and not v.get("active") and not v.get("_neden")]
        c("kapalı her özelliğin gerekçesi yazılmış", not _gerekce_yok, _gerekce_yok)
    except Exception as e:
        c("ai_features.json geçerli JSON", False, str(e))

gecen = sum(1 for _, k, _ in T if k)
print("Hesaplanan puan: %d (%s) | kategoriler: %s" %
      (r["total_score"], r["level"], {k: v["score"] for k, v in _kat.items()}))
print("Kodun verebilecegi en yuksek puan: %d\n" % _mumkun_en_yuksek)
for ad, k, d in T:
    print(("PASS " if k else "FAIL ") + ad + ("" if k else "   [%s]" % (d,)))
print("\n%d/%d PASS" % (gecen, len(T)))
sys.exit(0 if gecen == len(T) else 1)
