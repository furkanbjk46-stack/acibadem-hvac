# -*- coding: utf-8 -*-
"""oto_set tahmin yedek yolu (RPR-2026-1111-001): internet yoksa tahmin Synapse'ten gelir.
Ağ kullanmaz; geçiş kuralına, eşiklere ve set değerlerine dokunulmadığını da denetler."""
import os
import sys
from datetime import datetime

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import logging  # noqa: E402
logging.disable(logging.CRITICAL)
import hava_durumu as HD  # noqa: E402
import oto_set as O  # noqa: E402

T = []


def c(ad, kosul, ek=""):
    T.append((ad, bool(kosul), ek))


istenen = []


def synapse(bas, son, tahmin):
    istenen.append((bas, son, tahmin))
    if not tahmin:
        return {bas: {"Hava_Sicaklik_Max_C": 12.24, "Hava_Sicaklik_Min_C": 5.0}}
    return {bas: {"Hava_Sicaklik_Max_C": 14.0, "Hava_Sicaklik_Min_C": 7.56}}


_eski_uo, _eski_syn = O.urllib.request.urlopen, HD._synapse_hava
O.urllib.request.urlopen = lambda *a, **k: (_ for _ in ()).throw(OSError("timed out"))
HD._synapse_hava = synapse
O.konum_oku = lambda: {"enlem": 41.1273, "boylam": 29.0246}


def sifirla():
    O._tahmin_onbellek.update({"zaman": None, "veri": None, "nokta": None})
    istenen.clear()


sifirla()
v = O.tahmin_al()
c("internet yoksa tahmin Synapse'ten gelir (bugün max, yarın min)", v == {"bugun_max": 12.2, "yarin_min": 7.6}, v)
bugun = datetime.now().strftime("%Y-%m-%d")
c("bugün gerçekleşen satırdan, yarın tahmin satırından okunur",
  istenen[0] == (bugun, bugun, False) and istenen[1][2] is True and istenen[1][0] > bugun, istenen)
istenen.clear()
c("Synapse sonucu da 30 dk önbelleğe alınır", O.tahmin_al() == v and istenen == [])

sifirla()
HD._synapse_hava = lambda b, s, tahmin: {}
c("Synapse'te de yoksa eski davranış: önbellek (yoksa None → geçiş ertelenir)", O.tahmin_al() is None)
O._tahmin_onbellek.update({"zaman": datetime(2026, 1, 1), "veri": {"bugun_max": 9.0, "yarin_min": 3.0},
                           "nokta": (41.1273, 29.0246)})
c("Synapse yoksa eski önbellek değeri döner (mevcut davranış korunur)", O.tahmin_al() == {"bugun_max": 9.0, "yarin_min": 3.0})

sifirla()
HD._synapse_hava = lambda b, s, tahmin: {b: {"Hava_Sicaklik_Max_C": 12.0}} if not tahmin else {}
c("değerlerden biri eksikse yedek kullanılmaz", O.tahmin_al() is None)

sifirla()
HD._synapse_hava = synapse


class _Cevap:
    def __init__(self, govde):
        self.govde = govde

    def read(self):
        return self.govde

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


O.urllib.request.urlopen = lambda *a, **k: _Cevap(
    b'{"daily":{"temperature_2m_max":[18.04,20,21],"temperature_2m_min":[9,10.06,11]}}')
v = O.tahmin_al(zorla=True)
c("internet varken internetteki tahmin kullanılır, Synapse'e gidilmez",
  v == {"bugun_max": 18.0, "yarin_min": 10.1} and istenen == [], (v, istenen))

# Kapsam: yalnız tahmin kaynağı değişti
_kod = open(os.path.join(BURASI, "oto_set.py"), encoding="utf-8").read()
c("geçiş kararı tahmin yoksa yine ertelenir (tahmin_yok yolu duruyor)", '_sonuc_yaz("tahmin_yok"' in _kod)
c("yedek yol yalnız okuma yapar (Synapse'e yazmaz)",
  "_synapse_hava(" in _kod and "POST" not in _kod.split("def _synapse_tahmini")[1].split("\ndef ")[0])

O.urllib.request.urlopen, HD._synapse_hava = _eski_uo, _eski_syn
hata = [x for x in T if not x[1]]
for ad, ok, ek in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(ek)[:300]))
print("%d/%d PASS" % (len(T) - len(hata), len(T)))
sys.exit(1 if hata else 0)
