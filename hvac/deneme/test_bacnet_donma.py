# -*- coding: utf-8 -*-
"""data_bridge BACnet korumaları — Maslak'ın 21.09–23.10.2026 donmasını canlandırır.

1) Bayat BACnet dosyası artık KULLANILMAZ: alanlar boş, adetler 0 değil boş.
2) Geçmişte kalmış donmuş bloklar boşaltılır; ilk gün (gerçek okuma), elle
   girilmiş aylık veriler ve tüketim (kWh) sütunları korunur.
Gerçek dosyalara dokunmaz: her şey geçici klasörde.
"""
import csv
import os
import sys
import tempfile
from datetime import datetime, timedelta

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass
import logging  # noqa: E402
logging.disable(logging.CRITICAL)
import data_bridge as DB  # noqa: E402

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


tmp = tempfile.mkdtemp()

# ── 1) Tazelik ──
bc = os.path.join(tmp, "hedefli.csv")
with open(bc, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["Timestamp", "Device_ID", "Point_Name", "Value", "Status"])
    w.writeheader()
    w.writerow({"Timestamp": "2026-09-21 07:05:07", "Device_ID": 1, "Point_Name": "DIS HAVA", "Value": 19.88, "Status": "OK"})
    w.writerow({"Timestamp": "2026-09-21 07:05:07", "Device_ID": 1, "Point_Name": "CH-1 DURUM BILGISI", "Value": 1.0, "Status": "OK"})
eski = DB.BACNET_CSV
DB.BACNET_CSV = bc
c("33 gün eski BACnet dosyası KULLANILMIYOR", DB.read_bacnet_csv(simdi=datetime(2026, 10, 24, 7, 10)) == {})
taze = DB.read_bacnet_csv(simdi=datetime(2026, 9, 21, 7, 10))
c("aynı sabahki dosya kullanılıyor", taze.get("DIS HAVA") == 19.88, taze)
from datetime import timedelta as _td  # noqa: E402
_okuma = datetime(2026, 9, 21, 7, 5, 7)
_esik = DB.BACNET_TAZELIK_SAAT
c("eşik: sınırdan 1 saat önce taze, 1 saat sonra bayat",
  DB.read_bacnet_csv(simdi=_okuma + _td(hours=_esik - 1)) != {}
  and DB.read_bacnet_csv(simdi=_okuma + _td(hours=_esik + 1)) == {}, _esik)
# 30.10.2026: sayaçlar 23:59, köprü 00:05 — o günün 07:05 BACnet okumasını kullanır (~17 sa)
c("köprü gece 00:05'te o günün 07:05 BACnet okumasını kullanır",
  DB.read_bacnet_csv(simdi=datetime(2026, 9, 22, 0, 5)).get("DIS HAVA") == 19.88)
DB.BACNET_CSV = eski

satir = DB.build_daily_row("2026-10-23", {}, None)
c("BACnet yokken dış hava BOŞ", satir["Dis_Hava_Sicakligi_C"] == "", satir["Dis_Hava_Sicakligi_C"])
c("BACnet yokken chiller adedi BOŞ (eskiden 0 yazılıyordu)", satir["Chiller_Adet"] == "", satir["Chiller_Adet"])
c("BACnet yokken kazan / absorption adedi BOŞ", satir["Kazan_Adet"] == "" and satir["Absorption_Chiller_Adet"] == "")
satir2 = DB.build_daily_row("2026-09-20", taze, None)
c("BACnet varken adet hesaplanıyor", satir2["Chiller_Adet"] == 1 and satir2["Dis_Hava_Sicakligi_C"] == 19.88, satir2["Chiller_Adet"])

# ── 2) Geçmiş donmanın temizliği ──
ec = os.path.join(tmp, "energy_data.csv")
alanlar = ["Tarih", "Dis_Hava_Sicakligi_C", "Chiller_Set_Temp_C", "Chiller_Adet", "Kazan_Adet",
           "Chiller_Load_Percent", "Mas1_Isitma_Temp", "Toplam_Hastane_Tuketim_kWh"]
with open(ec, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=alanlar)
    w.writeheader()
    # Elle girilmiş aylık ortalama: Temmuz 2024 tamamı tek değer
    for i in range(31):
        w.writerow({"Tarih": "2024-07-%02d" % (i + 1), "Dis_Hava_Sicakligi_C": "26.7", "Chiller_Set_Temp_C": "7.0",
                    "Chiller_Adet": "4", "Kazan_Adet": "0", "Chiller_Load_Percent": "70.0",
                    "Mas1_Isitma_Temp": "60.0", "Toplam_Hastane_Tuketim_kWh": str(75000 + i)})
    # Nisan sonu kısa blok (aynı ay içinde) — elle girilmiş olabilir, dokunulmamalı
    for i in range(4):
        w.writerow({"Tarih": "2026-04-%02d" % (27 + i), "Dis_Hava_Sicakligi_C": "14.0", "Chiller_Set_Temp_C": "7.5",
                    "Chiller_Adet": "2", "Kazan_Adet": "0", "Chiller_Load_Percent": "50.0",
                    "Mas1_Isitma_Temp": "80.0", "Toplam_Hastane_Tuketim_kWh": "56728"})
    # Gerçek değişen günler, sonra 20.09 gerçek okuma + 21.09–23.10 donmuş kopyalar
    bas = datetime(2026, 9, 10)
    for i in range(44):
        g = bas + timedelta(days=i)
        donuk = g >= datetime(2026, 9, 20)
        w.writerow({"Tarih": g.strftime("%Y-%m-%d"),
                    "Dis_Hava_Sicakligi_C": "19.88" if donuk else "%.2f" % (22 - i * 0.2),
                    "Chiller_Set_Temp_C": "7.5", "Chiller_Adet": "2", "Kazan_Adet": "0",
                    "Chiller_Load_Percent": "66.5" if donuk else "%.1f" % (70 + i % 4),
                    "Mas1_Isitma_Temp": "91.12" if donuk else "%.2f" % (80 + i % 5),
                    "Toplam_Hastane_Tuketim_kWh": str(60000 + i * 13)})

def oku():
    with open(ec, newline="", encoding="utf-8") as f:
        return {r["Tarih"]: r for r in csv.DictReader(f)}

once = oku()
r = DB.donmus_bacnet_temizle(yol=ec, yedek_dizin=tmp)
sonra = oku()
c("33 donmuş gün temizlendi (21.09 → 23.10)", r.get("temizlenen_gun") == 33 and r["bas"] == "2026-09-21"
  and r["son"] == "2026-10-23", r)
c("bloğun ilk günü (20.09, gerçek okuma) korunuyor", sonra["2026-09-20"]["Dis_Hava_Sicakligi_C"] == "19.88")
c("donmuş günlerde dış hava boş", sonra["2026-10-01"]["Dis_Hava_Sicakligi_C"] == "")
c("donmuş günlerde chiller adedi ve set de boş (aynı bayat dosyadan)",
  sonra["2026-10-01"]["Chiller_Adet"] == "" and sonra["2026-10-01"]["Chiller_Set_Temp_C"] == "")
c("tüketim (kWh) sütununa DOKUNULMADI",
  all(once[t]["Toplam_Hastane_Tuketim_kWh"] == sonra[t]["Toplam_Hastane_Tuketim_kWh"] for t in once))
c("elle girilmiş aylık ortalama (Temmuz 2024) korunuyor",
  all(sonra["2024-07-%02d" % d]["Dis_Hava_Sicakligi_C"] == "26.7" for d in range(1, 32)))
c("ay içi kısa blok (27–30 Nisan) korunuyor ve raporlanıyor",
  sonra["2026-04-29"]["Dis_Hava_Sicakligi_C"] == "14.0" and "2026-04-27..2026-04-30" in r.get("dokunulmayan", []), r)
c("tam ay blokları rapora bile yazılmıyor", not any(x.startswith("2024-07") for x in r.get("dokunulmayan", [])))
c("donma öncesi değişen günler aynen", sonra["2026-09-15"] == once["2026-09-15"])
c("yedek alındı", any(f.startswith("energy_data_yedek_bacnet_donma_") for f in os.listdir(tmp)))
c("ikinci çalıştırma bir şey bulmuyor (idempotent)", DB.donmus_bacnet_temizle(yol=ec, yedek_dizin=tmp)["temizlenen_gun"] == 0)
c("satır sayısı değişmedi", len(sonra) == len(once))

# ── Kojen adedi (KOJEN-1..4 DURUM BILGISI) ──
k = DB.build_daily_row("2026-10-24", {"DIS HAVA": 15.0, "KOJEN-1 DURUM BILGISI": 1.0, "KOJEN-2 DURUM BILGISI": 0.0,
                                      "KOJEN-3 DURUM BILGISI": 1.0, "KOJEN-4 DURUM BILGISI": 1.0}, None)
c("kojen adedi çalışanları sayıyor (3/4)", k["Kojen_Adet"] == 3, k["Kojen_Adet"])
k0 = DB.build_daily_row("2026-10-24", {"DIS HAVA": 15.0, "KOJEN-1 DURUM BILGISI": 0.0, "KOJEN-2 DURUM BILGISI": 0.0}, None)
c("hepsi kapalıysa 0 (gerçek bilgi)", k0["Kojen_Adet"] == 0, k0["Kojen_Adet"])
c("kojen noktası şablonda yoksa BOŞ (0 değil)",
  DB.build_daily_row("2026-10-24", {"DIS HAVA": 15.0}, None)["Kojen_Adet"] == "")
c("BACnet bayatken kojen adedi BOŞ", DB.build_daily_row("2026-10-24", {}, None)["Kojen_Adet"] == "")
c("Kojen_Adet şemada ve donma temizliğinde",
  "Kojen_Adet" in DB.ENERGY_SCHEMA and "Kojen_Adet" in DB.BACNET_SUTUNLARI)
_kaynak = open(os.path.join(BURASI, "app_portal.py"), encoding="utf-8").read()
c("portal SCHEMA ve NUMERIC_COLS Kojen_Adet içeriyor (yoksa portal SİLER)",
  _kaynak.count('"Kojen_Adet"') >= 2)
c("Supabase SQL'i hazır", os.path.exists(os.path.join(BURASI, "..", "..", "merkez", "energy_data_kojen_adet.sql")))

hata = [x for x in T if not x[1]]
for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)[:300]))
print("%d/%d PASS" % (len(T) - len(hata), len(T)))
sys.exit(1 if hata else 0)
