# -*- coding: utf-8 -*-
"""cloud_sync.sync_energy_data: INTEGER sütunlara '2.0' gitmesin.

Boş hücresi olan adet sütununu pandas float okur (2 → 2.0). Supabase'deki
integer sütunlar (Chiller_Adet, Kazan_Adet, Absorption_Chiller_Adet, Kojen_Adet)
'2.0'ı reddeder ve toplu insert TAMAMEN düşer — o lokasyonun enerji verisi
buluta hiç gitmez. Sahte istemciyle, internete çıkmadan test edilir.
"""
import csv
import os
import sys
import tempfile

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass
import logging  # noqa: E402
logging.disable(logging.CRITICAL)
import cloud_sync as CS  # noqa: E402

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


class Sorgu:
    def __init__(self, istemci, tablo):
        self.i, self.tablo = istemci, tablo

    def select(self, *a, **k): return self
    def eq(self, *a, **k): return self
    def range(self, *a, **k): return self
    def in_(self, *a, **k): return self
    def delete(self, *a, **k): return self

    def insert(self, kayitlar, *a, **k):
        self.i.gonderilen.extend(kayitlar)
        return self

    def execute(self):
        return type("Cevap", (), {"data": []})()


class SahteIstemci:
    def __init__(self):
        self.gonderilen = []

    def table(self, ad):
        return Sorgu(self, ad)


tmp = tempfile.mkdtemp()
yol = os.path.join(tmp, "energy_data.csv")
with open(yol, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=["Tarih", "Chiller_Adet", "Kazan_Adet", "Kojen_Adet",
                                      "Dis_Hava_Sicakligi_C", "Hava_Durumu", "Toplam_Hastane_Tuketim_kWh"])
    w.writeheader()
    w.writerow({"Tarih": "2026-09-20", "Chiller_Adet": 2, "Kazan_Adet": 0, "Kojen_Adet": 3,
                "Dis_Hava_Sicakligi_C": 19.88, "Hava_Durumu": "bulutlu", "Toplam_Hastane_Tuketim_kWh": 86626})
    w.writerow({"Tarih": "2026-09-21", "Chiller_Adet": "", "Kazan_Adet": "", "Kojen_Adet": "",   # donma temizliği
                "Dis_Hava_Sicakligi_C": "", "Hava_Durumu": "", "Toplam_Hastane_Tuketim_kWh": 61293})

eski = CS.DATA_FILE
CS.DATA_FILE = yol
ist = SahteIstemci()
try:
    n = CS.sync_energy_data(ist, "test")
finally:
    CS.DATA_FILE = eski

c("iki satır gönderildi", n == 2 and len(ist.gonderilen) == 2, (n, ist.gonderilen))
s1 = next(r for r in ist.gonderilen if r["Tarih"] == "2026-09-20")
s2 = next(r for r in ist.gonderilen if r["Tarih"] == "2026-09-21")
for sutun in ("Chiller_Adet", "Kazan_Adet", "Kojen_Adet"):
    c("%s tamsayı gidiyor (2.0 değil)" % sutun, type(s1[sutun]) is int, repr(s1[sutun]))
    c("%s boş gün None gidiyor" % sutun, s2[sutun] is None, repr(s2[sutun]))
c("ondalıklı ölçüm ondalık kalıyor (19.88)", s1["Dis_Hava_Sicakligi_C"] == 19.88)
c("metin sütunu bozulmuyor", s1["Hava_Durumu"] == "bulutlu")
c("hiçbir değer tam sayılı float değil",
  not any(isinstance(v, float) and v.is_integer() for r in ist.gonderilen for v in r.values()),
  [(k, v) for r in ist.gonderilen for k, v in r.items() if isinstance(v, float) and v.is_integer()])

hata = [x for x in T if not x[1]]
for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)[:300]))
print("%d/%d PASS" % (len(T) - len(hata), len(T)))
sys.exit(1 if hata else 0)
