# -*- coding: utf-8 -*-
"""Sabah analizi veri katmani — ag baglantisi YOK, AI cagrisi YOK.

Korunan davranis: EKSIK VERI ile SIFIR ayri seylerdir. 11.10.2026'da kojen
verisi girilmemis bir gun icin model "kojen arizali, derhal kontrol edilmeli"
dedi; ortada ariza degil veri eksikligi vardi. Oranlar ancak gereken
kalemlerin HEPSI girilmisse hesaplanir; ariza iddiasinin kaynagi yalnizca
mekanik ozetidir.
"""
import os
import sys

import pandas as pd

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)

import ai_veri as AV

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", ek)


M2 = 15000
TAM = pd.DataFrame([{
    "Toplam_Hastane_Tuketim_kWh": 58529.0,
    "Sebeke_Tuketim_kWh": 40000.0,
    "Kojen_Uretim_kWh": 18529.0,
    "Kojen_Dogalgaz_m3": 3744.0,
    "Kazan_Dogalgaz_m3": 1200.0,
    "Su_Tuketimi_m3": 310.0,
    "Chiller_Tuketim_kWh": 20000.0,
    "MCC_Tuketim_kWh": 9000.0,
    "Chiller_Set_Temp_C": 7.5,
    "Chiller_Load_Percent": 66.0,
}])

# ── 1) Tam veri: oranlar hesaplanir ──────────────────────────────────────
o = AV.gun_ozeti(TAM, M2)
c("tam veride yogunluk hesaplanir", o["yogunluk"] == round(58529 / 15000, 2), o["yogunluk"])
c("tam veride kojen verimi hesaplanir", o["kojen_verim"] == round(18529 / 3744, 2),
  o["kojen_verim"])
c("tam veride sebeke bagimliligi hesaplanir",
  o["sebeke_bag"] == round(40000 / 58529 * 100, 1), o["sebeke_bag"])
c("tam veride gaz verimi hesaplanir",
  o["gaz_verim"] == round(58529 / 4944, 2), o["gaz_verim"])
c("tam veride eksik kalem yok", o["eksik"] == [], o["eksik"])
c("chiller yuku okunur", o["chiller_yuk"] == 66.0)
c("sogutma payi hesaplanir", o["chiller_pay"] == round(20000 / 58529 * 100, 1))

# ── 2) KOJEN KOLONU YOK: sebeke orani HESAPLANMAZ ───────────────────────
# Kritik durum: payda yalnizca sebeke kalinca oran %100 cikiyor ve
# "kojen durdu/arizali" diye okunuyordu.
_eksik_kojen = TAM.drop(columns=["Kojen_Uretim_kWh", "Kojen_Dogalgaz_m3"])
o2 = AV.gun_ozeti(_eksik_kojen, M2)
c("kojen kolonu yoksa kalem 'girilmemis' sayilir", o2["var_kojen"] is False)
c("kojen yokken sebeke orani HESAPLANMAZ (%100 cikmasin)",
  o2["sebeke_bag"] is None, o2["sebeke_bag"])
c("kojen yokken kojen verimi HESAPLANMAZ", o2["kojen_verim"] is None)
c("eksik kalemler listelenir",
  "kojen" in o2["eksik"] and "kojen_gaz" in o2["eksik"], o2["eksik"])
c("elektrik girilmisse yogunluk yine hesaplanir", o2["yogunluk"] is not None)

# ── 3) KOLON VAR ama BOS (NaN) ───────────────────────────────────────────
_bos_kojen = TAM.copy()
_bos_kojen["Kojen_Uretim_kWh"] = None
o3 = AV.gun_ozeti(_bos_kojen, M2)
c("bos (NaN) kolon da 'girilmemis' sayilir", o3["var_kojen"] is False)
c("bos kojen ile sebeke orani hesaplanmaz", o3["sebeke_bag"] is None)

# ── 4) GERCEKTEN SIFIR: oran hesaplanir (bu bir veri, eksiklik degil) ───
_sifir_kojen = TAM.copy()
_sifir_kojen["Kojen_Uretim_kWh"] = 0.0
o4 = AV.gun_ozeti(_sifir_kojen, M2)
c("sifir uretim 'veri var' sayilir", o4["var_kojen"] is True)
c("sifir kojende sebeke orani %100 olarak HESAPLANIR",
  o4["sebeke_bag"] == 100.0, o4["sebeke_bag"])
c("sifir kojen eksik listesine girmez", "kojen" not in o4["eksik"], o4["eksik"])

# ── 5) Gune ait hic veri yok ────────────────────────────────────────────
o5 = AV.gun_ozeti(pd.DataFrame(), M2)
c("bos gun isaretlenir", o5["veri_yok_gun"] is True)
c("bos gunde hicbir oran hesaplanmaz",
  all(o5[k] is None for k in ("yogunluk", "kojen_verim", "sebeke_bag", "gaz_verim")))
c("bos gunde tum kalemler eksik", len(o5["eksik"]) == len(AV.KALEMLER))

# ── 6) Mekanik ozet ─────────────────────────────────────────────────────
c("heartbeat yoksa bu da soylenir",
  AV.mekanik_ozet({}) == ["lokasyondan durum gelmiyor"])
c("ariza yoksa 'Ariza yok'", AV.mekanik_ozet({"toplam_ariza": 0})[0] == "Arıza yok")
_m = AV.mekanik_ozet({"toplam_ariza": 2, "toplam_bakim": 1,
                      "arizali_cihazlar": [{"ad": "AHU-3 Fan"}]})
c("ariza sayisi ve cihaz adi gecer", "AHU-3 Fan" in _m[0] and "2" in _m[0], _m)
_m = AV.mekanik_ozet({"veri_alarm": {"toplam": 1, "kritik": 1,
                                     "mesajlar": ["TRDP-2 baglanti hatasi"]}})
c("veri alarmi mekanik ozete girer (eksik verinin SEBEBI)",
  any("TRDP-2" in s for s in _m), _m)
_m = AV.mekanik_ozet({"oto": {"metin": "Bekliyor", "sonuc": "gecis_yok",
                              "donem": "gunduz",
                              "setler": {"chiller": 7.5,
                                         "GUNDUZ_KOLLEKTOR_SET": 10.0,
                                         "GECE_KOLLEKTOR_SET": 12.0},
                              "dogrulama": {"sonuc": "uygulanmadi"},
                              "konum": {"kaynak": "varsayilan"}}})
c("oto-set durumu ozete girer", any("Oto-set" in s for s in _m), _m)
c("uygulanmayan set ayrica belirtilir",
  any("UYGULANMADI" in s for s in _m), _m)
c("yururlukteki setler ozete girer", any("chiller 7.5" in s for s in _m), _m)
c("varsayilan konum uyarisi ozete girer",
  any("VARSAYILAN" in s for s in _m), _m)
c("kisa surumde set detayi yazilmaz",
  not any("Yürürlükteki set" in s for s in AV.mekanik_ozet(
      {"oto": {"metin": "Bekliyor", "setler": {"chiller": 7.5}}}, tam=False)))

# ── 7) KIYAS: gecen hafta / gecen yil ayni gun ──────────────────────────
# Sabit esik bir hastanenin KENDI normalini sOylemez; 58.529 kWh tek basina
# ne iyi ne kotudur. Zemin: ayni haftanin gunu ve gecen yilin ayni gunu.
import datetime as _dt


def gun_satiri(tarih, kwh, dis=None, kojen=None, kojen_gaz=None, sebeke=None):
    s = {"Tarih": pd.Timestamp(tarih), "Toplam_Hastane_Tuketim_kWh": kwh}
    if dis is not None:
        s["Dis_Hava_Sicakligi_C"] = dis
    if kojen is not None:
        s["Kojen_Uretim_kWh"] = kojen
    if kojen_gaz is not None:
        s["Kojen_Dogalgaz_m3"] = kojen_gaz
    if sebeke is not None:
        s["Sebeke_Tuketim_kWh"] = sebeke
    return s


DUN = _dt.date(2026, 10, 10)
_satirlar = [
    gun_satiri(DUN, 58529, dis=21.1),
    gun_satiri(DUN - _dt.timedelta(days=7), 55000, dis=18.4),     # gecen hafta
    gun_satiri(DUN - _dt.timedelta(days=364), 52300, dis=17.0),   # gecen yil
]
DF = pd.DataFrame(_satirlar)
DF["Tarih"] = pd.to_datetime(DF["Tarih"])

k = AV.kiyas_noktalari(DF, DUN, M2)
c("iki kiyas noktasi uretilir", len(k) == 2, [x["ad"] for x in k])
_gh = next(x for x in k if "hafta" in x["ad"])
_gy = next(x for x in k if "yıl" in x["ad"])
c("gecen hafta ayni gun dogru tarih", _gh["tarih"] == DUN - _dt.timedelta(days=7))
c("gecen hafta degisimi yuzde olarak", _gh["degisim"] == round((58529-55000)/55000*100, 1),
  _gh["degisim"])
c("gecen yil ayni gun 364 gun once (ayni hafta gunu)",
  _gy["tarih"] == DUN - _dt.timedelta(days=364) and _gy["tarih"].weekday() == DUN.weekday())
c("gecen yil degisimi hesaplanir", _gy["degisim"] == round((58529-52300)/52300*100, 1))
c("dis hava farki tasinir (sicakken tuketim artisi sapma degildir)",
  _gh["dis_fark"] == round(21.1-18.4, 1), _gh["dis_fark"])
c("kiyas gununde veri yoksa 'veri yok' isaretlenir",
  AV.kiyas_noktalari(DF[DF["Tarih"].dt.date == DUN], DUN, M2)[0]["veri"] is False)
c("hedef gun bos ise kiyas uretilmez",
  AV.kiyas_noktalari(DF, _dt.date(2020, 1, 1), M2) == [])

# ── 8) TREND: son 7 gun / onceki 7 gun ──────────────────────────────────
_t_satir = []
for i in range(14):
    g = DUN - _dt.timedelta(days=i)
    # Son 7 gun daha yuksek tuketim, kojen verimi dusuyor, sebeke payi artiyor
    if i < 7:
        _t_satir.append(gun_satiri(g, 60000, kojen=10000, kojen_gaz=2500, sebeke=50000))
    else:
        _t_satir.append(gun_satiri(g, 50000, kojen=20000, kojen_gaz=4000, sebeke=30000))
DFT = pd.DataFrame(_t_satir)
DFT["Tarih"] = pd.to_datetime(DFT["Tarih"])

tr = AV.trend(DFT, DUN, 7)
c("elektrik trendi hesaplanir",
  tr["elektrik_gun"]["onceki"] == 50000.0 and tr["elektrik_gun"]["son"] == 60000.0, tr["elektrik_gun"])
c("elektrik artisi KOTU olarak isaretlenir",
  "kötü" in (tr["elektrik_gun"]["yon"] or ""), tr["elektrik_gun"]["yon"])
c("kojen verimi dususu yakalanir",
  tr["kojen_verim"]["onceki"] == 5.0 and tr["kojen_verim"]["son"] == 4.0, tr["kojen_verim"])
c("kojen verimi dususu KOTU", "kötü" in (tr["kojen_verim"]["yon"] or ""),
  tr["kojen_verim"]["yon"])
c("sebeke payi artisi KOTU", "kötü" in (tr["sebeke_bag"]["yon"] or ""),
  tr["sebeke_bag"])
c("kapsama gun sayisi bildirilir", tr["kapsama"] == 7, tr["kapsama"])

# Kucuk oynama "sabit" sayilmali (her %1 degisim haber degildir)
_sabit = pd.DataFrame([gun_satiri(DUN - _dt.timedelta(days=i),
                                  50000 if i >= 7 else 50500) for i in range(14)])
_sabit["Tarih"] = pd.to_datetime(_sabit["Tarih"])
c("esik alti oynama 'sabit'",
  AV.trend(_sabit, DUN, 7)["elektrik_gun"]["yon"] == "sabit",
  AV.trend(_sabit, DUN, 7)["elektrik_gun"])

# Veri eksikse trend UYDURULMAZ
_yarim = pd.DataFrame([gun_satiri(DUN - _dt.timedelta(days=i), 50000) for i in range(7)])
_yarim["Tarih"] = pd.to_datetime(_yarim["Tarih"])
_tr2 = AV.trend(_yarim, DUN, 7)
c("onceki pencere yoksa degisim None", _tr2["elektrik_gun"]["degisim"] is None, _tr2)
c("kojen kolonu yoksa kojen trendi None", _tr2["kojen_verim"]["son"] is None)

# ── 9) app_merkez bu moduldan okur (ikinci kopya olmasin) ───────────────
_mrk = open(os.path.join(BURASI, "app_merkez.py"), encoding="utf-8").read()
c("app_merkez ai_veri modulunu kullanir",
  "import ai_veri" in _mrk and "_aiv.mekanik_ozet" in _mrk)
c("eksik veri kurali prompt'a yazili",
  "VERİ KURALI" in _mrk and "SIFIR DEĞİLDİR" in _mrk)
c("prompt arizayi yalnizca mekanik satirina dayandirir",
  "Mekanik' satırındaki" in _mrk)
c("mekanik blok TUM kademelerde var", _mrk.count("_mekanik_blok(") >= 4,
  _mrk.count("_mekanik_blok("))
c("sebeke orani kojen yokken karttan HESAPLANMAZ",
  "kojen verisi girilmediği için oran HESAPLANMADI" in _mrk)
c("eksik kalemler prompt'ta listelenir", "VERİ GİRİLMEMİŞ KALEMLER" in _mrk)
c("kiyas ve trend analize giriyor",
  "_kiyas_blok(" in _mrk and "_trend_blok(" in _mrk
  and "kiyas_noktalari" in _mrk and "_aiv.trend(" in _mrk)
c("kiyas kurali prompt'ta (sabit esik ikincil, dis hava hesaba katilsin)",
  "KIYAS KURALI" in _mrk and "DIŞ HAVA farkını" in _mrk)
c("yonergede egilim maddesi var", "7 günlük trend" in _mrk)

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
raise SystemExit(1 if basarisiz else 0)
