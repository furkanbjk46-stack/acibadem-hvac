# -*- coding: utf-8 -*-
"""31.10.2026: okunamayan sayaç turu sonraki turu düşürmemeli; nem %0-100.

Sahada: "Canlı güç turu hatası: '<' not supported between 'float' and 'NoneType'"
(bir cihazın kWh'ı okunamayınca (None, zaman) saklanıyor, sonraki sayaç
turunda kwh < None → TÜM tur düşüyordu) ve portal formu nem 100,64 ile açılmıyordu.

    python test_canli_guc_bos_sayac.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import canli_guc as CG  # noqa: E402
import data_bridge as B  # noqa: E402

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


CIHAZ = [{"name": "TRDP-1", "ip": "x", "brand": "siemens"},
         {"name": "KOJEN-3", "ip": "y", "brand": "siemens", "uretim": True}]
# Sayaç turları 1, 3, 5 (sayac_her_n_tur=2). KOJEN-3'ün kWh'ı 1. sayaç turunda okunamıyor.
# Değerler güçle tutarlı: 240 kW × 30 sn = 2,0 kWh; 700 kW × 30 sn = 5,8333 kWh
KWH = {"TRDP-1": [1000.0, None, 1002.0, None, 1004.0], "KOJEN-3": [None, None, 500.0, None, 505.8333]}
tur_i = {"n": 0}

CG.cihazlar = lambda ayar=None: CIHAZ
CG.guc_oku = lambda dev, ayar=None, adres=None: 240.0 if dev["name"] == "TRDP-1" else 700.0
CG._sayac_oku = lambda dev: KWH[dev["name"]][tur_i["n"]]

ayar = dict(CG.VARSAYILAN_AYAR, sayac_her_n_tur=2, es_zamanli=1)
o = CG.Olcer(ayar)
sonuclar, hata = [], None
for i in range(5):
    tur_i["n"] = i
    CG.time.time = (lambda t=1000.0 + i * 15: t)
    try:
        sonuclar.append(o.tur())
    except Exception as e:
        hata = e
        break

c("kWh okunamayan turdan sonra tur DUSMUYOR", hata is None, repr(hata))
c("bes tur da sonuc uretti", len(sonuclar) == 5, len(sonuclar))
if len(sonuclar) == 5:
    k3 = [next(r for r in s if r["cihaz"] == "KOJEN-3") for s in sonuclar]
    t1 = [next(r for r in s if r["cihaz"] == "TRDP-1") for s in sonuclar]
    c("diger cihaz her turda okunuyor", all(r["kw"] == 240.0 for r in t1), t1)
    c("kojen guc register'i gosteriliyor", all(r["kw"] == 700.0 for r in k3), [r["kw"] for r in k3])
    c("son sayac turunda kojen sayac gucu hesaplandi ve register'la uyustu (~700 kW)",
      k3[4]["kw_sayac"] is not None and abs(k3[4]["kw_sayac"] - 700.0) < 0.5 and k3[4]["yontem"] == "register",
      (k3[4]["kw_sayac"], k3[4]["yontem"]))

c("nem 100,64 → 100", B.yuzde_kirp(100.64) == 100.0)
c("nem 96,43 aynen", B.yuzde_kirp(96.43) == 96.43)
c("nem eksi → 0", B.yuzde_kirp(-1.2) == 0.0)
c("nem bos → bos", B.yuzde_kirp("") == "" and B.yuzde_kirp(None) is None)
_p = open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "app_portal.py"), encoding="utf-8").read()
c("portal formu yuzde alanlarini 0-100'e kirpiyor", 'if _hf is not None and _hc.endswith("_Yuzde"):' in _p
  and "_hf = min(100.0, max(0.0, _hf))" in _p)

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)[:200]))
print("%d/%d PASS" % (sum(1 for x in T if x[1]), len(T)))
sys.exit(0 if all(x[1] for x in T) else 1)
