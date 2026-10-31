# -*- coding: utf-8 -*-
"""Günlük hava verisi: modül, data_bridge bağlantısı, portal şeması, tutarlılık alarmı.

İnternete ÇIKMAZ: servis cevabı taklit edilir. Gerçek dosyalara dokunmaz.
"""
import csv
import os
import re
import sys
import tempfile
from datetime import date, timedelta

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass
import logging  # noqa: E402
logging.disable(logging.CRITICAL)
import hava_durumu as HD  # noqa: E402
import data_bridge as DB  # noqa: E402
import veri_alarm as VA  # noqa: E402

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


def sahte_cevap(bas, gun_sayisi, kod=61, yagis=4.0):
    gunler = [(bas + timedelta(days=i)).isoformat() for i in range(gun_sayisi)]
    n = len(gunler)
    return {"time": gunler, "temperature_2m_mean": [15.0] * n, "temperature_2m_max": [20.0] * n,
            "temperature_2m_min": [10.0] * n, "relative_humidity_2m_mean": [70] * n,
            "precipitation_sum": [yagis] * n, "cloud_cover_mean": [80] * n,
            "shortwave_radiation_sum": [7.2] * n, "wind_speed_10m_mean": [9.0] * n,
            "weather_code": [kod] * n}


istekler = []


def taklit_getir(url):
    istekler.append(url)
    if "archive" in url:
        b = re.search(r"start_date=([\d-]+)", url).group(1)
        s = re.search(r"end_date=([\d-]+)", url).group(1)
        b, s = date.fromisoformat(b), date.fromisoformat(s)
        return sahte_cevap(b, (s - b).days + 1)
    gecmis = int(re.search(r"past_days=(\d+)", url).group(1))
    return sahte_cevap(BUGUN - timedelta(days=gecmis - 1), gecmis + 1, kod=0, yagis=0.0)


BUGUN = date(2026, 10, 24)
HD._getir = taklit_getir
HD.koordinat = lambda: (41.1273, 29.0246)

# ── Modül ──
v = HD.gunluk_hava("2026-09-01", "2026-10-23", bugun=BUGUN)
c("eski + yakın günler birlikte geliyor (53 gün)", len(v) == 53, len(v))
c("eski günler arşivden, yakın günler tahmin servisinden",
  any("archive" in u for u in istekler) and any("past_days" in u for u in istekler), istekler)
c("radyasyon MJ → kWh/m² (7,2 MJ = 2 kWh)", v["2026-09-01"]["Hava_Gunes_Radyasyon_kWh_m2"] == 2.0)
c("4 mm yağmur → 'yağmurlu'", v["2026-09-01"]["Hava_Durumu"] == "yağmurlu")
c("çisenti (<1 mm) 'yağmurlu' sayılmıyor", HD.durum_metni(61, 0.3) == "bulutlu")
c("kar kodu → 'karlı'", HD.durum_metni(73, 2) == "karlı")
c("sütun adları şablonla tutarlı", set(v["2026-09-01"]) == set(HD.INTERNET_SUTUNLARI))
HD._getir = lambda url: (_ for _ in ()).throw(OSError("internet yok"))
c("internet yokken istisna atmaz, boş döner", HD.gunluk_hava("2026-10-01", "2026-10-02", bugun=BUGUN) == {})
HD._getir = taklit_getir
HD.koordinat = lambda: None
c("koordinat yoksa boş döner", HD.gunluk_hava("2026-10-01", "2026-10-02", bugun=BUGUN) == {})
HD.koordinat = lambda: (41.1273, 29.0246)

# ── Şema: üç yerde aynı liste ──
c("data_bridge şemasında hava sütunları var", all(s in DB.ENERGY_SCHEMA for s in HD.HAVA_SUTUNLARI))
kaynak = open(os.path.join(BURASI, "app_portal.py"), encoding="utf-8").read()
c("portal SCHEMA hava sütunlarını içeriyor (yoksa her açılışta SİLER)",
  "SCHEMA = SCHEMA + _HAVA_SUTUNLARI" in kaynak and "from hava_durumu import HAVA_SUTUNLARI" in kaynak)
c("portal sayısal hava sütunlarını sayıya çeviriyor", "] + _HAVA_SAYISAL" in kaynak)
sql = open(os.path.join(BURASI, "..", "..", "merkez", "energy_data_hava_sutunlari.sql"), encoding="utf-8").read()
c("Supabase SQL'i her sütunu ekliyor", all('"%s"' % s in sql for s in HD.HAVA_SUTUNLARI))
c("nem BACnet noktası eşleşmiş", DB.BACNET_MAP.get("DIS HAVA NEM") == "Dis_Hava_Nem_Yuzde")
satir = DB.build_daily_row("2026-10-23", {"DIS HAVA": 16.4, "DIS HAVA NEM": 71.5}, None)
c("günlük satıra nem sensörü yazılıyor", satir["Dis_Hava_Nem_Yuzde"] == 71.5)
c("nem donma korumasında", "Dis_Hava_Nem_Yuzde" in DB.BACNET_SUTUNLARI and "Dis_Hava_Nem_Yuzde" in DB.DONMA_OLCUMLERI)

# ── data_bridge.hava_doldur ──
tmp = tempfile.mkdtemp()
ec = os.path.join(tmp, "energy_data.csv")
with open(ec, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["Tarih", "Dis_Hava_Sicakligi_C", "Toplam_Hastane_Tuketim_kWh"])
    w.writeheader()
    for i in range(30):
        w.writerow({"Tarih": (date(2026, 9, 24) + timedelta(days=i)).isoformat(),
                    "Dis_Hava_Sicakligi_C": "17.5", "Toplam_Hastane_Tuketim_kWh": str(60000 + i)})
istekler.clear()
r = DB.hava_doldur(yol=ec, bugun=BUGUN)
with open(ec, newline="", encoding="utf-8") as f:
    sat = list(csv.DictReader(f))
c("tüm boş günler dolduruldu (30 gün)", r["doldurulan"] == 30, r)
c("bina sensörüne ve tüketime dokunulmadı",
  sat[0]["Dis_Hava_Sicakligi_C"] == "17.5" and sat[5]["Toplam_Hastane_Tuketim_kWh"] == "60005")
c("geçmiş TEK arşiv isteğiyle (gün gün değil)", sum("archive" in u for u in istekler) == 1, istekler)
c("ikinci çalıştırma bir şey istemiyor", DB.hava_doldur(yol=ec, bugun=BUGUN)["doldurulan"] == 0)
HD._getir = lambda url: (_ for _ in ()).throw(OSError("internet yok"))
with open(ec, "a", newline="", encoding="utf-8") as f:
    f.write("2026-10-24,18.0,61000" + "," * len(HD.INTERNET_SUTUNLARI) + "\n")
c("internet yokken dosya bozulmaz", DB.hava_doldur(yol=ec, bugun=date(2026, 10, 25))["doldurulan"] == 0)
HD._getir = taklit_getir

# ── Sensör ↔ internet tutarlılığı ──
def tutarlilik(sensor, nem):
    yol = os.path.join(tmp, "t.csv")
    with open(yol, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Tarih", "Dis_Hava_Sicakligi_C", "Dis_Hava_Nem_Yuzde",
                                          "Hava_Sicaklik_Min_C", "Hava_Sicaklik_Max_C", "Hava_Nem_Ort_Yuzde"])
        w.writeheader()
        for i, (s, n) in enumerate(zip(sensor, nem)):
            w.writerow({"Tarih": "2026-10-%02d" % (i + 1), "Dis_Hava_Sicakligi_C": s, "Dis_Hava_Nem_Yuzde": n,
                        "Hava_Sicaklik_Min_C": 10, "Hava_Sicaklik_Max_C": 20, "Hava_Nem_Ort_Yuzde": 70})
    return VA.sensor_tutarlilik_alarmlari(energy_csv=yol)

c("sağlıklı sensörde uyarı yok", tutarlilik([12, 15, 18, 9, 21], [65, 72, 80, 60, 75]) == [])
a = tutarlilik([35, 36, 34, 15, 38], [70, 70, 70, 70, 70])
c("sıcaklık 4/5 gün tutmuyor → UYARI", len(a) == 1 and "Dış hava sensörü" in a[0]["mesaj"], a)
a = tutarlilik([15] * 5, [5, 8, 6, 70, 4])
c("nem 4/5 gün tutmuyor → UYARI", len(a) == 1 and "nem" in a[0]["mesaj"], a)
c("tek günlük sapma uyarı vermez", tutarlilik([35, 15, 15, 15, 15], [70] * 5) == [])
c("hava sütunları yoksa (eski dosya) sessiz", VA.sensor_tutarlilik_alarmlari(energy_csv=ec) == [])

# ── Veri girişi formu: hava alanları + Kojen Adet ──
c("formda her hava sütununun alanı var",
  all('"%s"' % s in kaynak for s in HD.HAVA_SUTUNLARI) and "_HAVA_FORM_ALANLARI" in kaynak)
c("formda Kojen Adet alanı var ve kaydediliyor",
  'key="entry_kojen_count"' in kaynak and '"Kojen_Adet": int(kojen_count)' in kaynak)
c("boş hava alanı kaydedilmiyor (internet değeri korunur)", "if _deger is not None:" in kaynak)
c("hava alanları 0 değil BOŞ başlıyor", "_hf = None if _hv is None or pd.isna(_hv) else float(_hv)" in kaynak
  and "st.session_state[_hk] = _hf" in kaynak)
c("hava durumu seçenekleri hava_durumu.py ile aynı",
  all(HD.durum_metni(k, 5) in ["", "güneşli", "bulutlu", "yağmurlu", "karlı", "sisli"] for k in (0, 2, 45, 61, 73)))

hata = [x for x in T if not x[1]]
for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)[:300]))
print("%d/%d PASS" % (len(T) - len(hata), len(T)))
sys.exit(1 if hata else 0)
