# -*- coding: utf-8 -*-
"""Alışkanlık profili + veri kalitesi kapısı (A2, 24.11.2026).

    python hvac/deneme/test_aliskanlik.py

Neden var: tasarruf önerisi lokasyonun nasıl kullanıldığını bilmiyordu. Profil
lokasyonun kendi verisinden alışkanlık çıkarır; yanlış rakam yanlış öneri demek.
Bu test:
  1) sentetik veride bilinen alışkanlıkları (pazar fazla ısıtma, sabit set,
     eş zamanlı ısıtma-soğutma, su artışı) doğru bulduğunu,
  2) veri kalitesi kapısının (kapsam, donmuş sayaç, kırılma) bulguyu
     durdurduğunu,
  3) gerçek veri (veri/energy_data.csv) varsa gün tipi ortalamalarının ham
     veriden bağımsız hesapla aynı çıktığını,
  4) ekran/PDF metninin ve PDF bölümünün üretildiğini
doğrular.
"""
import os
import sys

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import logging
logging.disable(logging.CRITICAL)
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from tasarruf import aliskanlik as A
from tuketim_tahmin.takvim import tatil_serisi

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


def sentetik(pazar_gaz_fazla=400.0, su_artis=0.0, set_sabit=True, gaz_don=False, su_bos=False):
    """2 yıllık günlük veri. Dış hava mevsimsel; tüketimler havadan türetilir."""
    gun = pd.date_range("2024-11-01", "2026-10-31", freq="D")
    rng = np.random.default_rng(7)
    doy = gun.dayofyear.values
    T_ = 15 - 10 * np.cos(2 * np.pi * (doy - 15) / 365) + rng.normal(0, 1.0, len(gun))
    hg = gun.dayofweek.values
    pazar = hg == 6
    gaz = np.clip(150 * (16 - T_), 0, None) + rng.normal(0, 30, len(gun))
    gaz = np.clip(gaz, 0, None) + np.where(pazar & (T_ < 16), pazar_gaz_fazla, 0)
    sog = 2500 + np.clip(600 * (T_ - 12), 0, None) + rng.normal(0, 100, len(gun))
    toplam = 60000 + 300 * np.abs(T_ - 16) - np.where(pazar, 6000, 0) + rng.normal(0, 500, len(gun))
    su = 450 - np.where(pazar, 100, 0) + rng.normal(0, 10, len(gun))
    son_ay = gun >= pd.Timestamp("2026-10-01")
    su = su * np.where(son_ay, 1 + su_artis, 1)
    if set_sabit:
        st = np.where(T_ >= 24, 7.0, 7.5)
    else:
        st = np.select([T_ < 10, T_ < 18, T_ < 24], [10.0, 9.0, 8.0], 6.5)
    df = pd.DataFrame({
        "Tarih": gun.strftime("%Y-%m-%d"),
        "Toplam_Hastane_Tuketim_kWh": toplam, "Sebeke_Tuketim_kWh": toplam * 0.4,
        "Kojen_Uretim_kWh": toplam * 0.6, "Chiller_Tuketim_kWh": sog,
        "Kazan_Dogalgaz_m3": gaz, "Su_Tuketimi_m3": su, "Chiller_Set_Temp_C": st,
        "Chiller_Adet": np.where(T_ > 20, 3, 1), "Dis_Hava_Sicakligi_C": T_.round(2),
    })
    if gaz_don:
        df.loc[df["Tarih"] >= "2026-03-01", "Kazan_Dogalgaz_m3"] = 777.0
    if su_bos:
        df.loc[df["Tarih"] >= "2026-01-01", "Su_Tuketimi_m3"] = np.nan
    return df


def kodlar(s):
    return {b["kod"]: b for b in s["bulgular"]}


# ── 1) Bilinen alışkanlıklar bulunuyor ───────────────────────────────────
s = A.profil(sentetik(su_artis=0.3), 2026, 10, haric=[])
k = kodlar(s)
c("pencere 12 ay", s["pencere"] == ["2025-11-01", "2026-10-31"], s["pencere"])
c("pazar fazla ısıtma bulundu", "HAFTA_SONU_ISITMA_PAZAR" in k, list(k))
if "HAFTA_SONU_ISITMA_PAZAR" in k:
    h = s["hafta_sonu_isitma"]["pazar"]
    c("pazar farkı ~400 m³/gün (hava eşleştirmeli)", 330 < h["fark"] < 470, h["fark"])
    ts = k["HAFTA_SONU_ISITMA_PAZAR"]["tasarruf"]
    c("tasarruf m³/ay = fark × 52/12", ts and abs(ts["deger"] - h["fark"] * 52 / 12) < 1, ts)
c("cumartesi fazla ısıtma YOK (öyle bir alışkanlık yok)", "HAFTA_SONU_ISITMA_CUMARTESI" not in k)
c("sabit set bulundu", "SET_DIS_HAVA" in k, list(k))
c("set tasarrufu genel katsayıyla ve açıkça yazılı",
  "SET_DIS_HAVA" in k and "genel katsayı" in k["SET_DIS_HAVA"]["tasarruf"]["aciklama"])
c("su artışı bulundu", any(x.startswith("SU_ARTISI") for x in k), list(k))
ez = s["es_zamanli"]
c("eş zamanlı ısıtma-soğutma doğrulama bekler, tasarruf yazmaz",
  ("ES_ZAMANLI_ISITMA_SOGUTMA" not in k) or (k["ES_ZAMANLI_ISITMA_SOGUTMA"]["durum"] == "dogrulama_gerekli"
                                             and k["ES_ZAMANLI_ISITMA_SOGUTMA"]["tasarruf"] is None))

s0 = A.profil(sentetik(pazar_gaz_fazla=0.0, set_sabit=False), 2026, 10, haric=[])
k0 = kodlar(s0)
c("alışkanlık yoksa pazar ısıtma bulgusu yok", not any(x.startswith("HAFTA_SONU") for x in k0), list(k0))
c("set dış havaya göre değişiyorsa set bulgusu yok", "SET_DIS_HAVA" not in k0, list(k0))
c("su artmadıysa su bulgusu yok", not any(x.startswith("SU_ARTISI") for x in k0), list(k0))

# Gün tipi: bayram ayrı
ht = s["haftalik"]["toplam"]
c("pazar tüketimi hafta içinden ~6.000 düşük", 5000 < ht["hafta_ici"] - ht["pazar"] < 7000,
  ht["hafta_ici"] - ht["pazar"])
c("bayram günleri ayrı sayıldı", ht["gun"]["tatil"] > 0, ht["gun"])

# ── 2) Veri kalitesi kapısı ──────────────────────────────────────────────
sd = A.profil(sentetik(gaz_don=True), 2026, 10, haric=[])
c("donmuş gaz sayacı yakalandı", any(x["tur"] == "DONMUŞ SAYAÇ" for x in sd["kalite"]["sorunlar"]),
  sd["kalite"]["sorunlar"])
c("donmuş gazdan sonra gaz ölçütü geçersiz", sd["kalite"]["gecerli"]["gaz"] is False, sd["kalite"]["kapsam"])
c("geçersiz ölçütten tasarruf yazılmaz",
  all(b["tasarruf"] is None for b in sd["bulgular"] if "gaz" in b["supheli_olcutler"]))
ss = A.profil(sentetik(su_bos=True, su_artis=0.3), 2026, 10, haric=[])
c("su kapsamı düşük → su ölçütü geçersiz", ss["kalite"]["gecerli"]["su"] is False, ss["kalite"]["kapsam"]["su"])
c("kapsamı düşük su için bulgu öneri değil",
  all(b["durum"] != "aday" for b in ss["bulgular"] if b["kod"].startswith("SU_")))

# Kırılma: 2026 yazında soğutma yarıya inerse yakalanır
dk = sentetik()
m = (dk["Tarih"] >= "2026-06-01") & (dk["Tarih"] <= "2026-09-30")
dk.loc[m, "Chiller_Tuketim_kWh"] *= 0.5
sk = A.profil(dk, 2026, 10, haric=[])
c("yazlar arası soğutma kırılması yakalanır",
  any(x["yil"] == 2026 and x["degisim"] < -0.25 for x in sk["kalite"]["kirilmalar"]), sk["kalite"]["kirilmalar"])
c("kırılma yoksa uyarı yok", s["kalite"]["kirilmalar"] == [], s["kalite"]["kirilmalar"])

kisa = sentetik().iloc[:40]
c("az veride profil yok, çökmez", "yetersiz" in A.profil(kisa, 2024, 12, haric=[]))

# ── 3) Gerçek veri: ham veriden bağımsız hesapla aynı ───────────────────
yol = os.path.join(BURASI, "veri", "energy_data.csv")
if os.path.exists(yol):
    ham = pd.read_csv(yol)
    if len(ham) > 400:
        bas, son = "2025-11-01", "2026-11-23"
        sg = A.profil(ham, 2026, 11, haric=[], bas=bas, son=son)
        r = ham.copy()
        r["Tarih"] = pd.to_datetime(r["Tarih"])
        r = r[(r["Tarih"] >= bas) & (r["Tarih"] <= son)].copy()
        tat = tatil_serisi(r["Tarih"]).values > 0
        hg = r["Tarih"].dt.dayofweek.values
        r["tip"] = np.select([tat, hg == 6, hg == 5], ["tatil", "pazar", "cumartesi"], "hafta_ici")
        uyum = True
        detay = []
        for ad, sutun in (("su", "Su_Tuketimi_m3"), ("gaz", "Kazan_Dogalgaz_m3"),
                          ("sogutma", "Chiller_Tuketim_kWh")):
            bag = r.groupby("tip")[sutun].mean()
            for tip in A.GUN_TIPLERI:
                pv, bv = sg["haftalik"][ad][tip], bag.get(tip)
                if pv is None or bv is None or abs(pv - bv) > 0.005 * abs(bv) + 0.01:
                    uyum = False
                    detay.append((ad, tip, pv, bv))
        c("gerçek veri: gün tipi ortalamaları bağımsız hesapla aynı", uyum, detay)
        setler = r.loc[pd.to_numeric(r["Chiller_Tuketim_kWh"], errors="coerce") > 0,
                       "Chiller_Set_Temp_C"].round(1).value_counts()
        c("gerçek veri: kullanılan set günleri aynı",
          sg["chiller"]["setler"] == {float(k_): int(v) for k_, v in setler.sort_index().items()},
          (sg["chiller"]["setler"], dict(setler)))

# ── 4) Rapor metni ve PDF ───────────────────────────────────────────────
mt = A.rapor_metni(s)
c("ritim tablosu 4 ölçüt", len(mt["ritim"]) == 4, len(mt["ritim"]))
c("sayılar Türkçe biçimde", A.tr_sayi(12345.6, 1) == "12.345,6")
c("tarih gg.aa.yyyy", mt["pencere"] == ["01.11.2025", "31.10.2026"], mt["pencere"])
c("yüzde Türkçe biçimde", A.tr_yuzde(-0.27) == "-%27" and A.tr_yuzde(0.18) == "+%18")
c("bulgular metne geçer", len(mt["bulgular"]) == len(s["bulgular"]))
c("veri şüpheli bulgu metinde belirtilir",
  any(b["tasarruf"] == "Veri kalitesi nedeniyle hesaplanmadı" for b in A.rapor_metni(sd)["bulgular"])
  or not any(b["durum"] == "veri_supheli" for b in sd["bulgular"]))
try:
    from monthly_report.pdf_generator import MonthlyReportPDFGenerator
    pdf = MonthlyReportPDFGenerator().generate(2026, 10, {"summary": {}}, {}, [], aliskanlik=mt)
    c("PDF alışkanlık bölümüyle üretilir", isinstance(pdf, bytes) and len(pdf) > 1000, len(pdf))
except Exception as e:
    c("PDF alışkanlık bölümüyle üretilir", False, repr(e))

_ap = open(os.path.join(BURASI, "app_portal.py"), encoding="utf-8").read()
c("aylık raporda Alışkanlıklar kartı var", '"kart_aliskanlik"' in _ap and "aliskanlik=_alis_metin" in _ap)
import ast
try:
    ast.parse(_ap)
    c("app_portal.py sözdizimi geçerli", True)
except SyntaxError as e:
    c("app_portal.py sözdizimi geçerli", False, f"satır {e.lineno}: {e.msg}")

basarili = sum(1 for _, k_, _ in T if k_)
for ad, k_, d in T:
    print(("  OK  " if k_ else "  HATA") + f"  {ad}" + ("" if k_ else f"  → {d}"))
print(f"\n{basarili}/{len(T)} geçti")
sys.exit(0 if basarili == len(T) else 1)
