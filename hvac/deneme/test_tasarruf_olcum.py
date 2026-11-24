# -*- coding: utf-8 -*-
"""Tasarruf bulgusu yaşam döngüsü + ölçüm (A3, 24.11.2026).

    python hvac/deneme/test_tasarruf_olcum.py

Neden var: "uygulandı" demek tasarruf demek değildir. Ölçüm, uygulama öncesi veriyle
eğitilen modelin "uygulanmasaydı" tahminini gerçekleşenle kıyaslar. Bu test:
  1) bulgu defterinin kimlik/karar/susturma kurallarını,
  2) ölçümün bilinen bir etkiyi doğru ölçtüğünü, değişiklik yokken "tasarruf"
     uydurmadığını (sentetik veri),
  3) gerçek veri varsa (veri/energy_data.csv): eklenmiş %10 etkinin toplamda
     yakalandığını, gürültülü kalemde (gaz) sonuç uydurulmadığını,
  4) rapor bölümünün ve PDF'in üretildiğini
doğrular.
"""
import json
import os
import shutil
import sys
import tempfile
from datetime import date

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import logging
logging.disable(logging.CRITICAL)
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from tasarruf import olcum as O
from tasarruf.bulgular import BulguDefteri

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


GEC = tempfile.mkdtemp(prefix="tasarruf_")
try:
    # ── 1) Bulgu defteri ─────────────────────────────────────────────────
    yol = os.path.join(GEC, "tasarruf_bulgulari.json")
    d = BulguDefteri(yol)
    bulgu = {"kod": "SET_DIS_HAVA", "baslik": "Set sabit", "kanit": "k", "oneri": "o",
             "tasarruf": {"deger": 1500.0, "birim": "kWh/ay", "aciklama": "a"}, "durum": "aday",
             "supheli_olcutler": []}
    profil = {"donem": "2026-09", "bulgular": [bulgu], "haftalik": {"sogutma": {"hafta_ici": 5000.0}}}
    g1 = d.profilden_guncelle(profil, bugun=date(2026, 10, 1), olculebilirlik_hesapla=lambda o: 0.30)
    profil2 = dict(profil, donem="2026-10")
    g2 = d.profilden_guncelle(profil2, bugun=date(2026, 11, 1), olculebilirlik_hesapla=lambda o: 0.30)
    c("aynı alışkanlık her ay TEK bulgu", len(d.kayitlar) == 1, list(d.kayitlar))
    c("görüldüğü dönemler birikir", d.kayitlar["SET_DIS_HAVA"]["donemler"] == ["2026-09", "2026-10"])
    c("yeni bulgu karar bekler", d.kayitlar["SET_DIS_HAVA"]["durum"] == "raporda")
    c("rapor bulguyu gösterir", g1 == ["SET_DIS_HAVA"] and g2 == ["SET_DIS_HAVA"])
    c("bulgu ölçeceği kalemi bilir", d.kayitlar["SET_DIS_HAVA"]["olcut"] == "sogutma")
    o = d.kayitlar["SET_DIS_HAVA"]["olculebilirlik"]
    c("küçük tasarruf (1500/150000 = %1) %30 payla ölçülemez", o["sonuc"] == "olculemez"
      and abs(o["beklenen_oran"] - 0.01) < 1e-9, o)

    for ad, kw in (("nedensiz ret reddedilir", {"karar": "reddedildi"}),
                   ("'diğer' notsuz reddedilir", {"karar": "reddedildi", "neden": "diger"}),
                   ("gelecek uygulama tarihi reddedilir", {"karar": "uygulandi", "uygulama_tarihi": "2099-01-01"}),
                   ("geçersiz karar reddedilir", {"karar": "belki"})):
        try:
            d.karar_ver("SET_DIS_HAVA", bugun=date(2026, 11, 2), **kw)
            c(ad, False)
        except ValueError:
            c(ad, True)

    d.karar_ver("SET_DIS_HAVA", "reddedildi", neden="uygulanamaz", bugun=date(2026, 11, 2))
    c("'uygulanamaz' 6 ay susturur", d.susturuldu_mu("SET_DIS_HAVA", date(2027, 3, 1))
      and not d.susturuldu_mu("SET_DIS_HAVA", date(2027, 6, 1)))
    g3 = d.profilden_guncelle(dict(profil, donem="2026-11"), bugun=date(2026, 12, 1))
    c("susturulan bulgu raporda gösterilmez", g3 == [], g3)
    c("susturulan bulgu karar bekleyenlerde yok", d.karar_bekleyenler(date(2026, 12, 1)) == [])
    d.profilden_guncelle(dict(profil, donem="2027-05"), bugun=date(2027, 6, 1))
    c("susturma bitince yeniden sorulur", d.kayitlar["SET_DIS_HAVA"]["durum"] == "raporda")

    d.karar_ver("SET_DIS_HAVA", "uygulandi", uygulama_tarihi="2027-06-01", bugun=date(2027, 6, 2))
    c("uygulandı → ölçülüyor", d.kayitlar["SET_DIS_HAVA"]["durum"] == "olculuyor")
    c("karar geçmişi tutulur", len(d.kayitlar["SET_DIS_HAVA"]["karar_gecmisi"]) == 2)
    d.profilden_guncelle(dict(profil, donem="2027-06"), bugun=date(2027, 7, 1))
    c("ölçülen bulgu yeni raporda karar beklemeye dönmez", d.kayitlar["SET_DIS_HAVA"]["durum"] == "olculuyor")
    c("defter dosyadan aynı okunur", BulguDefteri(yol).kayitlar == d.kayitlar)

    # Ölçüm sonucu deftere işlenir (sahte ölçüm işleviyle)
    d.olcumleri_guncelle(pd.DataFrame({"Tarih": []}),
                         olc=lambda df, o, u, g=None: {"durum": "dogrulandi", "olcut": o, "birim": "kWh",
                                                       "beklenen": 100.0, "gercek": 80.0, "tasarruf": 20.0,
                                                       "oran": 0.2, "hata_payi": 0.05})
    c("doğrulanan ölçüm durumu günceller", d.kayitlar["SET_DIS_HAVA"]["durum"] == "dogrulandi")
    c("özet doğrulanan tasarrufu taşır", d.ozet()["dogrulanan_tasarruf"][0]["tasarruf"] == 20.0)

    # ── 2) Ölçüm: sentetik veri ─────────────────────────────────────────
    gun = pd.date_range("2023-01-01", "2026-10-31", freq="D")
    rng = np.random.default_rng(3)
    doy = gun.dayofyear.values
    Tm = 15 - 10 * np.cos(2 * np.pi * (doy - 15) / 365) + rng.normal(0, 2, len(gun))
    toplam = 60000 + 400 * np.abs(Tm - 16) - np.where(gun.dayofweek == 6, 5000, 0) + rng.normal(0, 600, len(gun))
    sog = 2500 + np.clip(700 * (Tm - 14), 0, None) + rng.normal(0, 150, len(gun))
    sentetik = pd.DataFrame({"Tarih": gun.strftime("%Y-%m-%d"), "Toplam_Hastane_Tuketim_kWh": toplam,
                             "Sebeke_Tuketim_kWh": toplam * 0.4, "Kojen_Uretim_kWh": toplam * 0.6,
                             "Chiller_Tuketim_kWh": sog, "Dis_Hava_Sicakligi_C": Tm.round(2)})

    def etki(df, sutun, bas, oran):
        e = df.copy()
        m = (pd.to_datetime(e["Tarih"]) >= bas)
        e.loc[m, sutun] = e.loc[m, sutun] * (1 - oran)
        if sutun == "Toplam_Hastane_Tuketim_kWh":
            e.loc[m, "Sebeke_Tuketim_kWh"] = e.loc[m, "Toplam_Hastane_Tuketim_kWh"] - e.loc[m, "Kojen_Uretim_kWh"]
        return e

    p = O.olc(sentetik, "toplam", "2026-04-01", haric=[])
    c("değişiklik yokken 'doğrulandı' demez", p["durum"] == "belirsiz", (p["durum"], p.get("oran"), p.get("hata_payi")))
    c("hata payı küçük (sentetik toplam < %5)", p["hata_payi"] < 0.05, p["hata_payi"])
    r = O.olc(etki(sentetik, "Toplam_Hastane_Tuketim_kWh", "2026-04-01", 0.10), "toplam", "2026-04-01", haric=[])
    c("%10 tasarruf doğrulanır", r["durum"] == "dogrulandi", r["durum"])
    c("ölçülen ~%10", abs(r["oran"] - 0.10) < 0.03, r["oran"])
    r2 = O.olc(etki(sentetik, "Toplam_Hastane_Tuketim_kWh", "2026-04-01", -0.10), "toplam", "2026-04-01", haric=[])
    c("%10 artış 'artis' olarak görülür", r2["durum"] == "artis", r2["durum"])
    r3 = O.olc(etki(sentetik, "Chiller_Tuketim_kWh", "2026-07-01", 0.15), "sogutma", "2026-07-01", haric=[])
    c("soğutmada %15 tasarruf ~ölçülür", abs(r3.get("oran", 0) - 0.15) < 0.05, (r3["durum"], r3.get("oran")))
    b = O.olc(sentetik, "toplam", "2026-10-20", haric=[])
    c("ölçüm dönemi dolmadıysa bekler", b["durum"] == "bekliyor", b)
    e = O.olc(sentetik.iloc[:200], "toplam", "2023-06-01", haric=[])
    c("1 yıldan az geçmişte yalnız yerel (8 haftalık) yöntem kullanılır", e.get("yontem") == "yerel",
      e.get("yontem"))
    e2 = O.olc(sentetik.iloc[:70], "toplam", "2023-02-10", haric=[])
    c("hiç yöntem kurulamayacak kadar az geçmişte ölçülemez", e2["durum"] == "olculemez", e2.get("durum"))
    c("hata payı formülü: 2,5×RMS / en büyük hata / en az %2",
      abs(O.hata_payi([0.01, -0.01, 0.01, -0.01]) - 0.025) < 1e-9 and O.hata_payi([0.0, 0.0, 0.001]) == 0.02
      and O.hata_payi([0.0, 0.0, 0.0, 0.3]) >= 0.3)

    # ── 3) Gerçek veri ──────────────────────────────────────────────────
    gyol = os.path.join(BURASI, "veri", "energy_data.csv")
    if os.path.exists(gyol):
        ham = pd.read_csv(gyol)
        if len(ham) > 900 and pd.to_datetime(ham["Tarih"]).max() >= pd.Timestamp("2026-04-01"):
            g = O._gunluk(ham, haric=[])
            pl = O.olc(ham, "toplam", "2025-10-06", g=g, haric=[])
            c("gerçek veri: toplamda hata payı < %10", pl.get("hata_payi", 1) < 0.10, pl.get("hata_payi"))
            e10 = etki(ham.assign(**{c_: pd.to_numeric(ham[c_], errors="coerce") for c_ in
                                     ("Toplam_Hastane_Tuketim_kWh", "Kojen_Uretim_kWh")}),
                       "Toplam_Hastane_Tuketim_kWh", "2025-10-06", 0.10)
            e10 = e10[pd.to_datetime(e10["Tarih"]) < pd.Timestamp("2025-11-03")]
            r10 = O.olc(e10, "toplam", "2025-10-06", haric=[])
            c("gerçek veri: eklenen %10 tasarruf doğrulanır", r10["durum"] == "dogrulandi",
              (r10["durum"], r10.get("oran"), r10.get("hata_payi")))
            gz = O.olc(ham, "gaz", "2026-07-13", g=g, haric=[])
            c("gerçek veri: kojen dönüşünde gaz farkı öneriye yazılmaz", gz["durum"] == "olculemez",
              (gz["durum"], gz.get("aciklama")))

    # ── 4) Rapor bölümü ve PDF ──────────────────────────────────────────
    from tasarruf.rapor import aylik_bolum, olcum_metni, olculebilirlik_metni
    from tasarruf import aliskanlik as A
    sent2 = sentetik.copy()
    sent2["Kazan_Dogalgaz_m3"] = np.clip(150 * (16 - Tm), 0, None)
    sent2["Su_Tuketimi_m3"] = 450.0 + rng.normal(0, 5, len(gun))
    sent2["Chiller_Set_Temp_C"] = np.where(Tm >= 24, 7.0, 7.5)
    sent2["Chiller_Adet"] = 2
    d2 = BulguDefteri(os.path.join(GEC, "rapor.json"))
    m = aylik_bolum(sent2, 2026, 10, defter=d2, olculebilirlik=False)
    c("rapor bölümü üretilir", "bulgular" in m and "sonuclar" in m, list(m))
    c("rapor bulguları deftere yazılır", set(b["kod"] for b in m["bulgular"]) <= set(d2.kayitlar), list(d2.kayitlar))
    c("rapor bulgusu durum taşır", all(b.get("kayit_durum") for b in m["bulgular"]))
    c("ölçülebilirlik metni: gürültülü kalem açıkça yazılır",
      "Ölçülemez" in (olculebilirlik_metni({"pay": 0.6, "beklenen_oran": 0.01, "sonuc": "olculemez"}, "gaz") or ""))
    c("ölçüm metni Türkçe yüzdeyle",
      "+%20" in olcum_metni({"durum": "dogrulandi", "beklenen": 100.0, "gercek": 80.0, "birim": "kWh",
                             "oran": 0.2, "hata_payi": 0.05}))
    m["sonuclar"] = [{"Öneri": "Set", "Uygulama": "01.06.2027", "Tahmin edilen": "1.500 kWh/ay",
                      "Sonuç": "Tasarruf doğrulandı"}]
    try:
        from monthly_report.pdf_generator import MonthlyReportPDFGenerator
        pdf = MonthlyReportPDFGenerator().generate(2026, 10, {"summary": {}}, {}, [], aliskanlik=m)
        c("PDF bulgu durumu ve önceki sonuçlarla üretilir", isinstance(pdf, bytes) and len(pdf) > 1000)
    except Exception as ex:
        c("PDF bulgu durumu ve önceki sonuçlarla üretilir", False, repr(ex))

    _ap = open(os.path.join(BURASI, "app_portal.py"), encoding="utf-8").read()
    import ast
    try:
        ast.parse(_ap)
        c("app_portal.py sözdizimi geçerli", True)
    except SyntaxError as ex:
        c("app_portal.py sözdizimi geçerli", False, f"satır {ex.lineno}: {ex.msg}")
    c("karar ekranında alışkanlık bulguları var", "BulguDefteri()" in _ap and '"bd_uyg_' in _ap.replace("f\"bd_uyg_", "\"bd_uyg_"))
    c("rapor kartı defterli bölümü kullanır", "_aylik_bolum(load_data(), report_year, report_month" in _ap)
finally:
    shutil.rmtree(GEC, ignore_errors=True)

basarili = sum(1 for _, k, _ in T if k)
for ad, k, dt in T:
    print(("  OK  " if k else "  HATA") + f"  {ad}" + ("" if k else f"  → {dt}"))
print(f"\n{basarili}/{len(T)} geçti")
sys.exit(0 if basarili == len(T) else 1)
