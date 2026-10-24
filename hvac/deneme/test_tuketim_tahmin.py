# -*- coding: utf-8 -*-
"""Günlük tahmin modeli — Enerji portalı bağlantısı (tuketim_tahmin/portal_ozet).

Sentetik veriyle çalışır; gerçek energy_data.csv'ye ve internete dokunmaz.
Asıl denetim: geçmiş ayın tahmini o ayın VERİSİNİ GÖRMEDEN yapılıyor mu
(eski portal sapmasının yanlışı buydu).
"""
import os
import re
import sys

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from tuketim_tahmin import portal_ozet as PO  # noqa: E402

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


def sentetik(bas="2023-01-01", son="2026-10-23", tohum=1):
    r = np.random.default_rng(tohum)
    t = pd.date_range(bas, son)
    gun = np.arange(len(t))
    sic = 15 + 10 * np.sin(2 * np.pi * (gun - 110) / 365.25) + r.normal(0, 2, len(t))
    cdd, hdd = np.clip(sic - 18, 0, None), np.clip(15 - sic, 0, None)
    hs = np.where(t.dayofweek == 6, -5000, np.where(t.dayofweek == 5, -3000, 0))
    toplam = 55000 + 2500 * cdd + 600 * hdd + hs + r.normal(0, 600, len(t))
    kojen = np.where(r.random(len(t)) < 0.7, 28000.0, 0.0)
    return pd.DataFrame({
        "Tarih": t.strftime("%Y-%m-%d"), "Toplam_Hastane_Tuketim_kWh": toplam,
        "Kojen_Uretim_kWh": kojen, "Sebeke_Tuketim_kWh": toplam - kojen,
        "Dis_Hava_Sicakligi_C": sic.round(2),
        "Chiller_Tuketim_kWh": 3000 + 1800 * cdd + r.normal(0, 300, len(t)),
        "Kazan_Dogalgaz_m3": np.clip(400 + 220 * hdd - 0.004 * kojen + r.normal(0, 40, len(t)), 0, None),
    })


df = sentetik()

# ── 1) Kopyalar: disa_aktarim paketiyle birebir ────────────────────────────
DIS = os.path.join(os.path.dirname(os.path.dirname(BURASI)), "disa_aktarim", "tuketim_tahmin")
if os.path.isdir(DIS):
    for ad in ("gunluk_model.py", "tahmin_motoru.py", "takvim.py", "veri_kalite.py", "sinama.py"):
        a = open(os.path.join(BURASI, "tuketim_tahmin", ad), encoding="utf-8").read()
        b = open(os.path.join(DIS, ad), encoding="utf-8").read()
        c("kopya disa_aktarim ile aynı: " + ad, a == b)
else:
    c("disa_aktarim yok (lokasyon) — kopya denetimi atlandı", True)

# ── 2) Yıl özeti ───────────────────────────────────────────────────────────
r = PO.yil_ozeti(df, 2026, "toplam", haric=[])
c("hata yok", r.get("hata") is None, r.get("hata"))
c("12 ay döner", len(r["aylar"]) == 12)
gecmis = [a for a in r["aylar"] if a["ay"] <= 9]
c("geçmiş aylar ileriye dönük", all(a["ileriye_donuk"] for a in gecmis))
c("gelecek aylar tüm veriyle", not r["aylar"][10]["ileriye_donuk"] and not r["aylar"][11]["ileriye_donuk"])
c("tam aylarda sapma var", all(a["sapma"] is not None for a in gecmis))
c("içinde bulunulan ay kısmi: sapma yok, gün sayısı notta",
  r["aylar"][9]["sapma"] is None and r["aylar"][9]["not"] == "23 gün", r["aylar"][9])
c("gelecek ayda gerçekleşen yok", r["aylar"][11]["gercek"] is None)
a = r["aylar"][2]
c("sapma = (gerçek − tahmin) / tahmin", abs(a["sapma"] - (a["gercek"] - a["tahmin"]) / a["tahmin"] * 100) < 1e-9)
c("sentetik veride ortalama sapma < %5", r["olcut"] and r["olcut"]["MAPE"] < 5, r["olcut"])
c("ölçüt 9 tam ay üzerinden", r["olcut"]["n"] == 9, r["olcut"])
c("birim kWh", r["birim"] == "kWh")

# ── 3) Sızıntı yok: ayın kendi verisi değişince o ayın tahmini DEĞİŞMEZ ───
bozuk = df.copy()
m = pd.to_datetime(bozuk["Tarih"]).dt.strftime("%Y-%m") == "2026-03"
bozuk.loc[m, "Toplam_Hastane_Tuketim_kWh"] *= 1.5
r2 = PO.yil_ozeti(bozuk, 2026, "toplam", haric=[])
c("Mart verisi %50 artınca Mart tahmini aynı (ay görülmeden tahmin)",
  abs(r2["aylar"][2]["tahmin"] - r["aylar"][2]["tahmin"]) < 1e-6,
  (r2["aylar"][2]["tahmin"], r["aylar"][2]["tahmin"]))
c("...ve Mart sapması büyür (gerçek değişti)", r2["aylar"][2]["sapma"] > 40, r2["aylar"][2]["sapma"])
c("Nisan tahmini Mart'ı görür (değişir)", r2["aylar"][3]["tahmin"] != r["aylar"][3]["tahmin"])

# ── 4) Hariç tutulan dönem ─────────────────────────────────────────────────
r3 = PO.yil_ozeti(df, 2026, "toplam", haric=[{"bas": "2026-09-01", "son": "2026-09-30", "neden": "test"}])
c("hariç ay: not 'hariç tutuldu', sapma yok",
  r3["aylar"][8]["not"] == "hariç tutuldu" and r3["aylar"][8]["sapma"] is None, r3["aylar"][8])
c("hariç ay ölçüte girmez", r3["olcut"]["n"] == 8, r3["olcut"])
c("hariç bulgusu kalite raporunda", any(b["tur"] == "HARİÇ" for b in r3["kalite"]))

# ── 5) Diğer hedefler ──────────────────────────────────────────────────────
rs = PO.yil_ozeti(df, 2026, "sogutma", haric=[])
c("soğutma: 12 ay, kWh", rs.get("hata") is None and len(rs["aylar"]) == 12 and rs["birim"] == "kWh")
rg = PO.yil_ozeti(df, 2026, "isitma_gaz", haric=[])
c("ısıtma gazı: m³", rg.get("hata") is None and rg["birim"] == "m³")
c("ısıtma gazında kojen girdi olarak seçildi", "kojen" in rg["ozellikler"], rg["ozellikler"])

# ── 6) Eksik / boş veri ────────────────────────────────────────────────────
c("boş tablo → hata metni", PO.yil_ozeti(pd.DataFrame(), 2026)["hata"])
c("hedef sütunu yok → hata metni",
  PO.yil_ozeti(df.drop(columns=["Kazan_Dogalgaz_m3"]), 2026, "isitma_gaz", haric=[])["hata"])
r_kisa = PO.yil_ozeti(sentetik(bas="2025-06-01"), 2026, "toplam", haric=[])
c("bir yıldan az geçmiş: ilk aylar 'yetersiz geçmiş'", r_kisa["aylar"][0]["not"] == "yetersiz geçmiş")
bos_ay = df.copy()
bos_ay.loc[pd.to_datetime(bos_ay["Tarih"]) >= "2026-10-01", "Kazan_Dogalgaz_m3"] = np.nan
c("ayda hedef verisi hiç yoksa not 'veri yok' (\"0 gün\" değil)",
  PO.yil_ozeti(bos_ay, 2026, "isitma_gaz", haric=[])["aylar"][9]["not"] == "veri yok")
try:
    PO.yil_ozeti(df, 2026, "yanlis")
    c("bilinmeyen hedef reddedilir", False)
except ValueError:
    c("bilinmeyen hedef reddedilir", True)

# ── 7) Gelecek ay + kojen planı ────────────────────────────────────────────
g20 = PO.gelecek_ay(df, 2026, 11, kojen_calisma_gun=20, haric=[])
c("kojen planı 20 gün → kaynak plan_gun", g20["kojen_kaynak"] == "plan_gun")
c("şebeke = tüketim − kojen (GES yok)", abs(g20["sebeke"] - (g20["tuketim"] - g20["kojen"])) < 1)
g0 = PO.gelecek_ay(df, 2026, 11, kojen_calisma_gun=0, haric=[])
c("kojen 0 gün → şebeke = tüketim", abs(g0["sebeke"] - g0["tuketim"]) < 1 and g0["kojen"] == 0)
gv = PO.gelecek_ay(df, 2026, 11, haric=[])
c("plan yok → son 90 günün düzeni", gv["kojen_kaynak"] == "varsayim" and gv["kojen"] > 0)

# ── 8) Ayar dosyası ve portal bağlantısı ───────────────────────────────────
c("configs/tuketim_tahmin.json okunuyor", isinstance(PO.haric_donemler(), list))
kaynak = open(os.path.join(BURASI, "app_portal.py"), encoding="utf-8").read()
c("portalda yeni model kartı var", 'kart_tahmin_gunluk_model' in kaynak)
c("eski model ay NUMARASIYLA eşlenir (eski adlar ASCII: Subat, Mayis)",
  '_eski = {f["month"]:' in kaynak and "_eski.get(_a['ay'])" in kaynak)
c("önbellek imzası _ ile başlamıyor (Streamlit _ önekli argümanı hash'lemez)",
  re.search(r"def _gunluk_model_ozeti\(yil: int, hedef: str, veri_imzasi", kaynak))

hata = [x for x in T if not x[1]]
for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)[:300]))
print("%d/%d PASS" % (len(T) - len(hata), len(T)))
sys.exit(1 if hata else 0)
