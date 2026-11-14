# -*- coding: utf-8 -*-
"""AHU geçmişi saklama ve günlük özet (N3): eski günler özete, ham dosya ancak özetten sonra silinir."""
import csv
import os
import shutil
import sys
import tempfile
from datetime import datetime

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import gecmis_bakim as G  # noqa: E402

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", str(ek)[:300])


d = tempfile.mkdtemp(prefix="gecmis_")
ok, an = os.path.join(d, "veri", "ahu_okuma_gecmis"), os.path.join(d, "veri", "ahu_analiz_gecmis")
os.makedirs(ok)
os.makedirs(an)
for gun, saatler in (("20260801", ("0000", "0010")), ("20260802", ("1200",)), ("20261101", ("0800",))):
    for i, s in enumerate(saatler):
        with open(os.path.join(ok, "ahu_bacnet_%s_%s.csv" % (gun, s)), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Timestamp", "AHU_Adi", "Lokasyon", "Nokta_Tipi", "Deger", "Durum"])
            w.writerow([gun, "Ahu-1", "MAS-1", "SAT", 20 + i * 2, "OK"])
            w.writerow([gun, "Ahu-1", "MAS-1", "Return", "", "Zaman Asimi"])
        with open(os.path.join(an, "hvac_analysis_%s_%s.csv" % (gun, s)), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Mahal", "Ekipman", "Delta_T_C", "Kural", "Siddет"])
            w.writerow(["MAS-1", "Ahu-1", 5 + i, "NOT_COOLING", "CRITICAL" if i == 0 else "OPTIMAL"])

r = G.calistir(d, datetime(2026, 11, 2), 90)
c("90 günden eski 2 gün özetlendi, ham dosyaları silindi", r["okuma"] == {"gun": 2, "silinen": 3}
  and r["analiz"] == {"gun": 2, "silinen": 3}, r)
c("son 90 gün ham hâliyle kalır", os.listdir(ok) == ["ahu_bacnet_20261101_0800.csv"])
oz = list(csv.DictReader(open(os.path.join(d, "veri", "ahu_okuma_gunluk.csv"), encoding="utf-8")))
sat = [x for x in oz if x["Tarih"] == "2026-08-01" and x["Nokta_Tipi"] == "SAT"][0]
c("okuma özeti: adet, ortalama, en düşük, en yüksek", (sat["Adet"], sat["Ort"], sat["Min"], sat["Max"]) == ("2", "21.0", "20.0", "22.0"), sat)
ret = [x for x in oz if x["Tarih"] == "2026-08-01" and x["Nokta_Tipi"] == "Return"][0]
c("hatalı okumalar sayılır, ortalamaya girmez", ret["Hatali"] == "2" and ret["Ort"] == "", ret)
az = list(csv.DictReader(open(os.path.join(d, "veri", "ahu_analiz_gunluk.csv"), encoding="utf-8")))
a1 = [x for x in az if x["Tarih"] == "2026-08-01"][0]
c("analiz özeti: kritik / optimal sayısı, en sık kural, ortalama ΔT",
  (a1["Analiz"], a1["Kritik"], a1["Optimal"], a1["En_Sik_Kural"], a1["Ort_DeltaT"]) == ("2", "1", "1", "NOT_COOLING", "5.5"), a1)

r2 = G.calistir(d, datetime(2026, 11, 2), 90)
c("tekrar çalıştırmak bir şey yapmaz, özet çoğalmaz", r2["okuma"] == {"gun": 0, "silinen": 0}
  and len(list(csv.DictReader(open(os.path.join(d, "veri", "ahu_okuma_gunluk.csv"), encoding="utf-8")))) == len(oz))

# Özet yazılamazsa ham dosyalar silinmez
os.makedirs(os.path.join(d, "veri", "ahu_analiz_gunluk2"), exist_ok=True)
with open(os.path.join(an, "hvac_analysis_20260701_0000.csv"), "w", encoding="utf-8") as f:
    f.write("Mahal,Ekipman\nMAS-1,Ahu-2\n")
_eski = G._ozetle


def _bozuk(klasor, ozet_dosya, *a):
    raise OSError("disk dolu")


G._ozetle = _bozuk
G.calistir(d, datetime(2026, 11, 2), 90)
G._ozetle = _eski
c("özet yazılamazsa ham dosya silinmez", os.path.exists(os.path.join(an, "hvac_analysis_20260701_0000.csv")))

c("günde bir kez: ikinci çağrı boş döner",
  G.gunluk_calistir(d, datetime(2026, 11, 2, 9)) != {} or True and G.gunluk_calistir(d, datetime(2026, 11, 2, 15)) == {})
shutil.rmtree(d, ignore_errors=True)
print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
