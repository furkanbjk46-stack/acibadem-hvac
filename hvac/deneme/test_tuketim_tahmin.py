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
c("önbellek imzası _ ile başlamıyor (Streamlit _ önekli argümanı hash'lemez)",
  re.search(r"def _gunluk_model_ozeti\(yil: int, hedef: str, veri_imzasi", kaynak))

# ── 9) Eski ML motoru tamamen kaldırıldı (30.10.2026) ──────────────────────
c("forecast_engine.py silindi", not os.path.exists(os.path.join(BURASI, "monthly_report", "forecast_engine.py")))
c("portal eski motoru çağırmıyor",
  not any(x in kaynak for x in ("ConsumptionForecastEngine", "_get_forecast_engine", "scenario_predict",
                                 "kart_ml_model", "kart_senaryo", "_durust_tahmin_verisi")))
import monthly_report  # noqa: E402
c("monthly_report paketi eski motor olmadan yükleniyor", not hasattr(monthly_report, "ConsumptionForecastEngine"))
_t6 = kaynak[kaynak.index("# ---------------- TAB 6"):]
c("Tahmin & Trend: ısıtma gazı seçeneği yok", "isitma_gaz" not in _t6)
c("Tahmin & Trend: yarın / 7 gün / 30 gün kartı var", "kart_tahmin_kisa_vade" in _t6 and "_ufuk_tahmini(" in _t6)

# ── 10) Yarın / 7 gün / 30 gün ─────────────────────────────────────────────
BUGUN = "2026-10-23"
u = PO.ufuk_tahmini(df, "toplam", 30, bugun=BUGUN, haric=[])
c("ufuk: hata yok, 30 gün, yarından başlar",
  u.get("hata") is None and len(u["gunler"]) == 30 and u["gunler"][0]["tarih"] == "2026-10-24", u.get("hata"))
c("ufuk toplamları: yarın = 1. gün, 7 gün = ilk 7, 30 gün = hepsi",
  abs(u["toplamlar"]["yarin"] - u["gunler"][0]["tahmin"]) < 1e-6
  and abs(u["toplamlar"]["hafta"] - sum(g["tahmin"] for g in u["gunler"][:7])) < 1e-6
  and abs(u["toplamlar"]["ay"] - sum(g["tahmin"] for g in u["gunler"])) < 1e-6)
c("hava tahmini yokken tüm günler 'ortalama'", all(g["hava"] == "ortalama" for g in u["gunler"])
  and u["hava_tahmin_gun"] == 0)
_paz = [g for g in u["gunler"] if pd.Timestamp(g["tarih"]).dayofweek == 6]
_hi = [g for g in u["gunler"] if pd.Timestamp(g["tarih"]).dayofweek < 5]
c("Pazar tahmini hafta içinden düşük (takvim etkisi)",
  np.mean([g["tahmin"] for g in _paz]) < np.mean([g["tahmin"] for g in _hi]))
# Sıcak hava dalgası tahmini: ilk 5 gün 32 °C → o günler belirgin yüksek
_sicak = {(pd.Timestamp("2026-10-24") + pd.Timedelta(days=i)).strftime("%Y-%m-%d"):
          {"Hava_Sicaklik_Ort_C": 32.0, "Hava_Sicaklik_Max_C": 36.0, "Hava_Sicaklik_Min_C": 27.0,
           "Hava_Durumu": "güneşli"} for i in range(5)}
uh = PO.ufuk_tahmini(df, "toplam", 30, hava_tahmin=_sicak, bugun=BUGUN, haric=[])
c("hava tahmini verilen günler 'tahmin' olarak işaretli", uh["hava_tahmin_gun"] == 5
  and [g["hava"] for g in uh["gunler"][:6]] == ["tahmin"] * 5 + ["ortalama"])
c("tahmin edilen sıcaklık modele girdi (32 °C)", abs(uh["gunler"][0]["sicaklik"] - 32.0) < 1e-9)
c("sıcak hava dalgası tüketimi artırır (CDD)", uh["toplamlar"]["yarin"] > u["toplamlar"]["yarin"] * 1.2,
  (uh["toplamlar"]["yarin"], u["toplamlar"]["yarin"]))
c("hava tahmini olmayan günler değişmez",
  abs(uh["gunler"][10]["tahmin"] - u["gunler"][10]["tahmin"]) < 1e-6)
us = PO.ufuk_tahmini(df, "sogutma", 30, hava_tahmin=_sicak, bugun=BUGUN, haric=[])
c("soğutma ufku: kWh, sıcakta artar", us.get("hata") is None and us["birim"] == "kWh"
  and us["gunler"][0]["tahmin"] > us["gunler"][10]["tahmin"])
c("ufuk: boş veri → hata metni", PO.ufuk_tahmini(pd.DataFrame(), "toplam")["hata"])
c("ufuk: bir yıldan az geçmiş → hata metni",
  PO.ufuk_tahmini(sentetik(bas="2026-03-01"), "toplam", bugun=BUGUN, haric=[])["hata"])
c("hava_tablosu: Hava_* → modelin adları",
  list(PO.hava_tablosu(_sicak).columns[:2]) == ["Tarih", "sicaklik_ort"] and PO.hava_tablosu({}) is None)

# ── 11) Rapor / PDF paketi (yalnız yeni model) ─────────────────────────────
rv = PO.rapor_verisi(df, 2026, alan=50000, haric=[])
c("rapor: 12 aylık tahmin, sapma yeni modelden",
  len(rv["monthly_forecast"]) == 12
  and rv["monthly_forecast"][2]["deviation_total_pct"] == r["aylar"][2]["sapma"])
c("rapor: eski trend sütunları yok", "prev_total" not in rv["monthly_forecast"][0])
c("rapor: yıllık özet gerçekleşen veriden",
  [y["year"] for y in rv["yearly_summary"]] == [2023, 2024, 2025, 2026]
  and rv["yearly_summary"][-1]["kwh_per_m2"] == rv["yearly_summary"][-1]["total_kwh"] / 50000)
c("tasarruf: tam yıl önceki tam yılla", PO.tasarruf(df, 2025)["prev_year"] == 2024)
c("tasarruf: kısmi yıl (2026, 296 gün) boş", PO.tasarruf(df, 2026) == {})

# ── 11b) Şebeke kuralı: 01.06.2026'dan beri Şebeke girilmemiş gün = toplam bilinmiyor ──
sk = df.copy()
_yeni = pd.to_datetime(sk["Tarih"]) >= "2026-06-01"
sk.loc[_yeni, "Sebeke_Tuketim_kWh"] = np.nan
sk.loc[_yeni, "Toplam_Hastane_Tuketim_kWh"] = sk.loc[_yeni, "Kojen_Uretim_kWh"]   # sahadaki durum
gk, rk = PO.birlestir(sk, haric=[])
c("şebekesiz yeni kural günlerinde toplam boş", gk.loc[gk["tarih"] >= "2026-06-01", "toplam"].isna().all())
c("01.06 öncesi toplam aynen", gk.loc[gk["tarih"] < "2026-06-01", "toplam"].notna().all())
c("soğutma etkilenmez", gk.loc[gk["tarih"] >= "2026-06-01", "sogutma"].notna().all())
c("kalite raporunda 'ŞEBEKE YOK'", any(b["tur"] == "ŞEBEKE YOK" for b in rk.bulgular))
_us = PO.ufuk_tahmini(sk, "toplam", 7, bugun=BUGUN, haric=[])
c("yalnız-kojen günleri tahmini aşağı çekmez (±%5)",
  abs(_us["toplamlar"]["hafta"] / u["toplamlar"]["hafta"] - 1) < 0.05,
  (_us["toplamlar"]["hafta"], u["toplamlar"]["hafta"]))
_ys = PO.yillik_ozet(sk)[-1]
c("yıllık özet: şebekesiz günler toplama katılmaz ve sayılır",
  _ys["sebeke_eksik_gun"] == int(_yeni.sum())
  and abs(_ys["total_kwh"] - sk.loc[pd.to_datetime(sk["Tarih"]).between("2026-01-01", "2026-05-31"),
                                    "Toplam_Hastane_Tuketim_kWh"].sum()) < 1)
_g15 = pd.to_datetime(sk["Tarih"]) == "2026-07-15"
sk.loc[_g15, "Sebeke_Tuketim_kWh"] = 30000.0       # kullanıcı Şebeke'yi girdi → portal Toplam'ı yeniden hesaplar
sk.loc[_g15, "Toplam_Hastane_Tuketim_kWh"] = 30000.0 + sk.loc[_g15, "Kojen_Uretim_kWh"]
c("Şebeke girilen gün kendiliğinden yeniden modele girer",
  PO.birlestir(sk, haric=[])[0].set_index("tarih").loc["2026-07-15", "toplam"] >= 30000)

# ── 12) Hava tahmini servisi (internete çıkmadan) ──────────────────────────
import hava_durumu as HD  # noqa: E402
_eski_getir, _eski_kd = HD._getir, HD.koordinat
_istenen = []
HD.koordinat = lambda: (41.1, 29.0)
HD._getir = lambda url: (_istenen.append(url) or {
    "time": ["2026-10-30", "2026-10-31", "2026-11-01"], "temperature_2m_mean": [15.0, 16.5, 14.0],
    "temperature_2m_max": [19, 20, 18], "temperature_2m_min": [11, 12, 10], "precipitation_sum": [0, 3, 0],
    "weather_code": [1, 61, 3]})
from datetime import date as _date  # noqa: E402
ht = HD.ileri_tahmin(16, bugun=_date(2026, 10, 30))
c("ileri_tahmin: bugün hariç, yarından itibaren", list(ht) == ["2026-10-31", "2026-11-01"], list(ht))
c("ileri_tahmin: 16 günlük, İstanbul saatiyle", "forecast_days=16" in _istenen[0] and "Europe%2FIstanbul" in _istenen[0])
c("ileri_tahmin: Hava_* biçiminde", ht["2026-10-31"]["Hava_Sicaklik_Ort_C"] == 16.5
  and ht["2026-10-31"]["Hava_Durumu"] == "yağmurlu")
HD._getir = lambda url: (_ for _ in ()).throw(OSError("internet yok"))
c("ileri_tahmin: internet yoksa boş sözlük", HD.ileri_tahmin(bugun=_date(2026, 10, 30)) == {})
HD.koordinat = lambda: None
c("ileri_tahmin: koordinat yoksa boş sözlük", HD.ileri_tahmin() == {})
HD._getir, HD.koordinat = _eski_getir, _eski_kd

hata = [x for x in T if not x[1]]
for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)[:300]))
print("%d/%d PASS" % (len(T) - len(hata), len(T)))
sys.exit(1 if hata else 0)
