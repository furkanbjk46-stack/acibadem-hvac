# -*- coding: utf-8 -*-
"""Paket testi — doğrusu BİLİNEN yapay veriyle.

Yapay veri yalnız bu testte üretilir, dosyaya yazılmaz. Gerçek başarı ölçümü
sinama.py ile gerçek lokasyon verisinde yapılır.
"""
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
import veri_kalite  # noqa: E402
from gunluk_model import GunlukTahminModeli, birlestir, KOLONLAR  # noqa: E402

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


rnd = np.random.default_rng(7)
gun = pd.date_range("2023-01-01", "2026-08-31")
n = len(gun)
doy = gun.dayofyear.values
sic = 15 - 10 * np.cos(2 * np.pi * (doy - 15) / 365) + rnd.normal(0, 2.5, n)
yagmur = rnd.random(n) < 0.25
radyasyon = np.clip(4 - 2.5 * np.cos(2 * np.pi * (doy - 172) / 365) * -1, 0.5, None) * np.where(yagmur, 0.35, 1.0)
hasta = 400 + 30 * (gun.dayofweek < 5) + rnd.normal(0, 10, n)
cdd, hdd = np.clip(sic - 18, 0, None), np.clip(15 - sic, 0, None)
tuketim = 52000 + 1400 * cdd + 600 * hdd - 4000 * (gun.dayofweek >= 5) + 30 * hasta + rnd.normal(0, 800, n)
ges = 450 * radyasyon + rnd.normal(0, 40, n)
kojen = np.where((gun.month == 4) & (gun.year == 2026), 0.0, 42000.0)   # Nisan 2026 bakım
sebeke = tuketim - ges - kojen

ana = pd.DataFrame({"Tarih": gun.strftime("%Y-%m-%d"), "Toplam_Hastane_Tuketim_kWh": tuketim,
                    "Sebeke_Tuketim_kWh": sebeke, "Kojen_Uretim_kWh": kojen, "GES_Uretim_kWh": ges,
                    "Dis_Hava_Sicakligi_C": sic.round(2)})
hava = pd.DataFrame({"Tarih": ana.Tarih, "sicaklik_ort": sic, "yagis_mm": np.where(yagmur, 8.0, 0.0),
                     "bulut_yuzde": np.where(yagmur, 90.0, 20.0), "gunes_radyasyon": radyasyon,
                     "hava_durumu": np.where(yagmur, "yağmurlu", "güneşli")})
operasyon = pd.DataFrame({"Tarih": ana.Tarih, "hasta_sayisi": hasta})

# ── Veri kalitesi ──
bozuk = ana.copy()
bozuk.loc[100:115, "Dis_Hava_Sicakligi_C"] = 19.88                      # donmuş sensör
bozuk.loc[200, "Toplam_Hastane_Tuketim_kWh"] = 0                         # sıfır gün
bozuk.loc[201, "Toplam_Hastane_Tuketim_kWh"] = 2 * tuketim[201]          # iki gün birleşmiş
bozuk.loc[300:320, "Kojen_Uretim_kWh"] = np.nan                          # kojen kaybı
_, r = veri_kalite.kontrol(bozuk, KOLONLAR, haric=[{"bas": "2024-03-01", "son": "2024-03-31"}])
turler = {b["tur"] for b in r.bulgular}
for t in ("DONMUŞ SENSÖR", "SIFIR", "ÇİFT GÜN", "KOJEN YOK", "HARİÇ"):
    c("kalite: %s yakalanıyor" % t, t in turler, r.ozet())
_, r_temiz = veri_kalite.kontrol(ana, KOLONLAR)
c("kalite: temiz veride sahte bulgu yok", not r_temiz.bulgular, r_temiz.ozet())
c("lokasyon ayarı: Maslak Eylül 2026 hariç",
  veri_kalite.lokasyon_ayari("maslak")["haric"][0]["bas"] == "2026-09-01")

# ── Model: tüm ek verilerle ──
g, _ = birlestir(ana, hava, operasyon)
m = GunlukTahminModeli()
bilgi = m.egit(g, bitis=pd.Timestamp("2026-08-01"))
c("hasta sayısı özellik olarak seçildi", "hasta_sayisi" in m.secilen, m.secilen)
c("hava ek verisi seçildi", {"yagis_mm", "gunes_radyasyon"} <= set(m.secilen), m.secilen)
c("GES modeli kuruldu", bilgi["ges_modeli"])
t = m.ay_tahmini(2026, 8)
gercek = tuketim[(gun.year == 2026) & (gun.month == 8)].sum()
c("ağustos tüketimi %3 içinde", abs(t["tuketim"] - gercek) / gercek < 0.03,
  "tahmin %.0f gerçek %.0f" % (t["tuketim"], gercek))
c("enerji dengesi: şebeke = tüketim − GES − kojen",
  abs(t["sebeke"] - max(t["tuketim"] - t["ges"] - t["kojen"], 0)) < 1e-6)

# Yağmurlu günde GES düşük, şebeke yüksek (kojen sabitken)
iki = pd.DataFrame({"Tarih": ["2026-08-10", "2026-08-11"], "sicaklik_ort": [26, 26],
                    "yagis_mm": [0, 12], "bulut_yuzde": [15, 95], "gunes_radyasyon": [6.5, 1.5],
                    "hava_durumu": ["güneşli", "yağmurlu"]})
gt = m.gunluk_tahmin("2026-08-10", "2026-08-11", hava=iki)
c("yağmurlu günde GES daha düşük", gt.ges.iloc[1] < 0.6 * gt.ges.iloc[0], gt[["ges", "sebeke"]].round(0).to_dict())
c("yağmurlu günde şebeke daha yüksek", gt.sebeke.iloc[1] > gt.sebeke.iloc[0])

# Kojen planı
c("kojen kWh planı aynen kullanılıyor", m.ay_tahmini(2026, 8, kojen_plan_kwh=500000)["kojen"] == 500000)
c("kojen 0 gün planı → kojen 0", m.ay_tahmini(2026, 8, kojen_calisma_gun=0)["kojen"] == 0)
c("plan yokken kaynağı 'varsayım' yazıyor", t["kojen_kaynak"] == "varsayim")

# ── Hasta/ameliyat verisi BOŞ kalsa da çalışır ──
seyrek = operasyon.copy()
seyrek.loc[seyrek.index[:-60], "hasta_sayisi"] = np.nan        # yalnız son 60 gün dolu
g2, _ = birlestir(ana, None, seyrek)
m2 = GunlukTahminModeli()
m2.egit(g2, bitis=pd.Timestamp("2026-08-01"))
c("yetersiz dolu hasta verisi seçilmiyor", "hasta_sayisi" not in m2.secilen, m2.secilen)
c("ek veri olmadan da tahmin çıkıyor", m2.ay_tahmini(2026, 8)["tuketim"] > 0)
g3, _ = birlestir(ana.drop(columns=["GES_Uretim_kWh"]))
m3 = GunlukTahminModeli(); m3.egit(g3, bitis=pd.Timestamp("2026-08-01"))
c("GES sütunu yoksa GES = 0", m3.ay_tahmini(2026, 8)["ges"] == 0)

# ── Takvim (Gemini incelemesinden alınan, veriyle doğrulanan fikir) ──
import takvim  # noqa: E402
c("Kurban 2026 ilk gün tam tatil", takvim.tatil_degeri("2026-05-27") == 1.0)
c("bayram arifesi yarım gün", takvim.tatil_degeri("2026-05-26") == 0.5)
c("29 Ekim resmi tatil, 28 Ekim yarım", takvim.tatil_degeri("2026-10-29") == 1.0 and takvim.tatil_degeri("2026-10-28") == 0.5)
c("sıradan gün tatil değil", takvim.tatil_degeri("2026-10-21") == 0.0)
c("2023–2030 bayramları kapsanıyor", all(takvim.kapsiyor_mu(y) for y in range(2023, 2031)))

# ── Yeni kalite kuralları ──
kb = ana.copy()
kb.loc[400, "Sebeke_Tuketim_kWh"] = 0                                   # şebeke 0, toplam = kojen
kb.loc[401, "Toplam_Hastane_Tuketim_kWh"] = 0.4 * tuketim[401]          # ani düşük toplam
kb.loc[402, "Dis_Hava_Sicakligi_C"] = 0.0 if sic[402] > 14 else 30.0   # tek günlük sensör sıçraması
_, rk = veri_kalite.kontrol(kb, KOLONLAR)
tk = {b["tur"] for b in rk.bulgular}
c("kalite: ŞEBEKE 0 yakalanıyor", "ŞEBEKE 0" in tk, rk.ozet())
c("kalite: DÜŞÜK TOPLAM yakalanıyor", "DÜŞÜK TOPLAM" in tk, rk.ozet())
c("kalite: SENSÖR SIÇRAMA yakalanıyor", "SENSÖR SIÇRAMA" in tk, rk.ozet())

# ── Hedef seçimi ──
try:
    GunlukTahminModeli(hedef="yanlis"); c("bilinmeyen hedef reddediliyor", False)
except ValueError:
    c("bilinmeyen hedef reddediliyor", True)
gaz = ana.assign(Kazan_Dogalgaz_m3=np.clip(900 * hdd - 0.02 * kojen, 0, None))
gg, _ = birlestir(gaz, hava, None)
mg = GunlukTahminModeli(hedef="isitma_gaz"); mg.egit(gg, bitis=pd.Timestamp("2026-08-01"))
c("ısıtma gazında kojen planı özellik olarak seçiliyor", "kojen" in mg.secilen, mg.secilen)
c("ısıtma gazı kojen planını kullanıyor (planlı ≠ plansız)",
  mg.ay_tahmini(2026, 3, kojen_plan_kwh=0)["tuketim"] != mg.ay_tahmini(2026, 3, kojen_plan_kwh=1.3e6)["tuketim"])

hata = [x for x in T if not x[1]]
for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)))
print("%d/%d PASS" % (len(T) - len(hata), len(T)))
sys.exit(1 if hata else 0)
