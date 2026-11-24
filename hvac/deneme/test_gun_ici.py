# -*- coding: utf-8 -*-
"""Gün içi santral profili (A4, 24.11.2026).

    python hvac/deneme/test_gun_ici.py

Neden var: günlük sayaç "aynı gün ısıtma ve soğutma yüksek" der ama bunun aynı santralde mi
(kayıp) yoksa farklı zonlarda mı (normal) olduğunu söyleyemez. 10 dakikalık AHU okumaları
söyler. Bu test:
  1) özetin vana çakışmasını, yalnız ısıtma/soğutmayı, gece çalışmayı doğru saydığını,
     zaman aşımı okumalarını atladığını, işlenmiş günü yeniden işlemediğini,
  2) şüpheli günlerin "aynı santralde" / "yalnız zonlar arası" diye ayrıldığını,
  3) bulgu ve ölçümün (uygulama öncesi/sonrası) doğru karar verdiğini,
  4) alışkanlık profili, bulgu defteri, rapor metni ve portal bağlantısını,
  5) saha verisi varsa (_saha_deneme): bağımsız hesapla aynı sonucu
doğrular.
"""
import ast
import os
import shutil
import sys
import tempfile

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import logging
logging.disable(logging.CRITICAL)
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd

from tasarruf import gun_ici as GI

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


GEC = tempfile.mkdtemp(prefix="gun_ici_test_")
KL = os.path.join(GEC, "ahu_okuma_gecmis")
os.makedirs(KL)


def satirlar(zaman, ahu, lok, calis, sog, isi, durum="OK"):
    ts = zaman.strftime("%Y%m%d %H%M")
    return [[ts, ahu, lok, "Start/Stop", calis, durum], [ts, ahu, lok, "Cool Valve (%)", sog, durum],
            [ts, ahu, lok, "Heat Valve (%)", isi, durum], [ts, ahu, lok, "SAT (°C)", "16,5", durum]]


def gun_yaz(gun, cakisma_saat=2.0, a_lok="MAS-1", zaman_asimi=False, eksik=False):
    """AHU-A: 08:00'dan itibaren cakisma_saat kadar ısıtma+soğutma birlikte; gündüz çalışır.
    AHU-B: yalnız ısıtma (gündüz). AHU-C: yalnız soğutma (gündüz). AHU-D: 7/24 çalışır, vanalar kapalı.
    Aynı ad başka lokasyonda: MAS-2 AHU-A yalnız soğutma."""
    for dk in range(0, 24 * 60, 10):
        if eksik and dk % 60:
            continue
        z = pd.Timestamp(gun) + pd.Timedelta(minutes=dk)
        h = z.hour + z.minute / 60
        gunduz = 7 <= h < 19
        sat = []
        cak = 8 <= h < 8 + cakisma_saat
        sat += satirlar(z, "AHU-A", a_lok, int(gunduz), "40" if gunduz else "0", "35" if cak else "0")
        sat += satirlar(z, "AHU-B", "MAS-1", int(gunduz), "0", "50" if gunduz else "0")
        sat += satirlar(z, "AHU-C", "MAS-1", int(gunduz), "60" if gunduz else "0", "0")
        sat += satirlar(z, "AHU-D", "MAS-1", 1, "0", "0")
        sat += satirlar(z, "AHU-A", "MAS-2", int(gunduz), "30" if gunduz else "0", "0")
        if zaman_asimi and 8 <= h < 9:
            # zaman aşımı satırları vanayı açık gösterse de sayılmamalı
            sat += [[r[0], "AHU-C", "MAS-1", r[3], "90", "Zaman Asimi"] for r in satirlar(z, "AHU-C", "MAS-1", 1, 0, 0)]
        d = pd.DataFrame(sat, columns=["Timestamp", "AHU_Adi", "Lokasyon", "Nokta_Tipi", "Deger", "Durum"])
        if zaman_asimi and 8 <= h < 9:
            d = d[~((d["AHU_Adi"] == "AHU-C") & (d["Durum"] == "OK"))]
        d.to_csv(os.path.join(KL, f"ahu_bacnet_{z.strftime('%Y%m%d_%H%M')}.csv"), index=False, encoding="utf-8")


try:
    # ── 1) Gün özeti ─────────────────────────────────────────────────────
    gun_yaz("2026-11-01", cakisma_saat=2.0, zaman_asimi=True)
    oz1, bn1 = GI.gun_ozeti([os.path.join(KL, f) for f in os.listdir(KL)])
    a = oz1[(oz1["AHU"] == "AHU-A") & (oz1["Lokasyon"] == "MAS-1")].iloc[0]
    b = oz1[oz1["AHU"] == "AHU-B"].iloc[0]
    cc = oz1[oz1["AHU"] == "AHU-C"].iloc[0]
    d = oz1[oz1["AHU"] == "AHU-D"].iloc[0]
    a2 = oz1[(oz1["AHU"] == "AHU-A") & (oz1["Lokasyon"] == "MAS-2")].iloc[0]
    c("vana çakışması 2 saat", abs(a["cakisma_saat"] - 2.0) < 1e-9, a["cakisma_saat"])
    c("çakışma saatleri 'yalnız soğutma'dan düşülür", abs(a["sogutma_saat"] - 10.0) < 1e-9, a["sogutma_saat"])
    c("yalnız ısıtan santralde çakışma yok", b["cakisma_saat"] == 0 and abs(b["isitma_saat"] - 12) < 1e-9,
      (b["cakisma_saat"], b["isitma_saat"]))
    c("zaman aşımı okumaları atlanır (AHU-C 1 saat eksik)", abs(cc["sogutma_saat"] - 11.0) < 1e-9 and cc["okuma"] == 138,
      (cc["sogutma_saat"], cc["okuma"]))
    c("7/24 santralin gece oranı 1", d["gece"] == 1.0 and d["calisma"] == 1.0, (d["gece"], d["calisma"]))
    c("gündüz santralinin gece oranı 0", a["gece"] == 0.0, a["gece"])
    c("aynı ad iki lokasyonda ayrı santral", a2["cakisma_saat"] == 0 and abs(a2["sogutma_saat"] - 12) < 1e-9, a2.to_dict())
    c("bina: biri ısıtırken diğeri soğutuyor 12 saat", abs(bn1["karisik_saat"] - 12.0) < 1e-9, bn1)
    c("bina okuma zamanı 144", bn1["okuma_zamani"] == 144, bn1)

    vana_kapali_calismiyor = GI.gun_ozeti([])
    c("dosya yoksa özet yok, çökmez", vana_kapali_calismiyor == (None, None))

    # ── Önbellek: işlenmiş gün tekrar işlenmez, bugün işlenmez ──────────
    for g in pd.date_range("2026-11-02", "2026-11-14"):
        gun_yaz(g, cakisma_saat=2.0 if g.day % 2 == 0 else 0.0)
    oz_yol, bn_yol = os.path.join(GEC, "oz.csv"), os.path.join(GEC, "bn.csv")
    oz, bn = GI.ozetleri_guncelle(KL, oz_yol, bn_yol, bugun="20261114")
    c("bugün (14.11) işlenmez", oz["Tarih"].max() == pd.Timestamp("2026-11-13"), oz["Tarih"].max())
    c("13 gün özetlendi", oz["Tarih"].nunique() == 13 and len(bn) == 13, (oz["Tarih"].nunique(), len(bn)))
    zaman = os.path.getmtime(oz_yol)
    # işlenmiş bir günün dosyasını boz: yeniden işlenseydi değişirdi
    bozuk = os.path.join(KL, "ahu_bacnet_20261101_0800.csv")
    with open(bozuk, "w", encoding="utf-8") as f:
        f.write("bozuk")
    oz_b, bn_b = GI.ozetleri_guncelle(KL, oz_yol, bn_yol, bugun="20261114")
    c("işlenmiş gün yeniden işlenmez", os.path.getmtime(oz_yol) == zaman and len(oz_b) == len(oz), len(oz_b))
    oz2, bn2 = GI.ozetleri_guncelle(KL, oz_yol, bn_yol, bugun="20261115")
    c("ertesi gün yalnız yeni gün eklenir", oz2["Tarih"].nunique() == 14 and len(bn2) == 14, oz2["Tarih"].nunique())

    # ── 2) Şüpheli günlerin ayrılması ───────────────────────────────────
    sup = ["2026-11-02", "2026-11-03", "2026-11-04", "2026-11-05", "2026-10-01"]
    gp = GI.profil(oz2, bn2, supheli_gunler=sup)
    sp = gp["supheli"]
    c("şüpheli: 2 gün aynı santralde çakışma (çift günler)", sp["santralde_cakisma"] == 2, sp)
    c("şüpheli: 2 gün yalnız zonlar arası", sp["yalniz_zon"] == 2, sp)
    c("şüpheli: verisi olmayan gün ayrı sayılır", sp["veri_yok"] == 1 and sp["veri_var"] == 4, sp)
    g02 = [x for x in sp["gunler"] if x["tarih"] == "2026-11-02"][0]
    c("çakışan santral adı lokasyonla verilir", g02["santraller"] == ["MAS-1 AHU-A"], g02)

    # ── 3) Bulgular ─────────────────────────────────────────────────────
    bl = {x["kod"]: x for x in GI.bulgular(gp)}
    c("VANA_CAKISMASI bulgusu çıkar", "VANA_CAKISMASI" in bl, list(bl))
    c("vana bulgusunda yalnız çakışan santral", bl.get("VANA_CAKISMASI", {}).get("santraller") == ["MAS-1 AHU-A"],
      bl.get("VANA_CAKISMASI", {}).get("santraller"))
    c("gece bulgusunda yalnız 7/24 santral", bl.get("GECE_SUREKLI_CALISMA", {}).get("santraller") == ["MAS-1 AHU-D"],
      bl.get("GECE_SUREKLI_CALISMA", {}).get("santraller"))
    c("gün içi bulguda kWh uydurulmaz", all(x["tasarruf"] is None for x in bl.values()))
    az = GI.profil(oz2[oz2["Tarih"] <= "2026-11-03"], bn2[bn2["Tarih"] <= "2026-11-03"])
    c("5 günden az veride bulgu yok", GI.bulgular(az) == [], az["gun"])
    c("veri yoksa metin çökmez", GI.metin_satirlari(GI.profil(oz2.iloc[0:0], bn2.iloc[0:0])) ==
      ["Gün içi (10 dakikalık) santral verisi yok."])
    m = GI.metin_satirlari(gp)
    c("metin: tarih gg.aa.yyyy, sayı virgüllü", "01.11.2026" in m[0] and "," in m[1], m[:2])

    # ── Ölçüm: önce / sonra ─────────────────────────────────────────────
    gunler = pd.date_range("2026-09-01", "2026-10-31")
    sentetik = []
    for t in gunler:
        sonra = t > pd.Timestamp("2026-10-01")
        sentetik.append({"Tarih": t, "Lokasyon": "MAS-1", "AHU": "AHU-A", "okuma": 144, "calisma": 0.5,
                         "gece": 0.0 if sonra else 1.0, "cakisma_saat": 0.2 if sonra else 3.0,
                         "isitma_saat": 0, "sogutma_saat": 0})
        sentetik.append({"Tarih": t, "Lokasyon": "MAS-1", "AHU": "AHU-X", "okuma": 144, "calisma": 1.0,
                         "gece": 1.0, "cakisma_saat": 5.0, "isitma_saat": 0, "sogutma_saat": 0})
    so = pd.DataFrame(sentetik)
    o1 = GI.olc(so, "VANA_CAKISMASI", "2026-10-01", santraller=["MAS-1 AHU-A"])
    c("çakışma kalkınca 'doğrulandı'", o1["durum"] == "dogrulandi", o1)
    o2 = GI.olc(so, "VANA_CAKISMASI", "2026-10-01", santraller=["MAS-1 AHU-X"])
    c("değişmeyen santralde 'artis' (değişmedi)", o2["durum"] == "artis", o2)
    o3 = GI.olc(so, "GECE_SUREKLI_CALISMA", "2026-10-01", santraller=["MAS-1 AHU-A"])
    c("gece programı kurulunca 'doğrulandı'", o3["durum"] == "dogrulandi", o3)
    o4 = GI.olc(so, "VANA_CAKISMASI", "2026-10-28", santraller=["MAS-1 AHU-A"])
    c("sonrasında 7 günden az veri: bekliyor", o4["durum"] == "bekliyor", o4)
    o5 = GI.olc(so, "VANA_CAKISMASI", "2026-09-03", santraller=["MAS-1 AHU-A"])
    c("öncesinde veri yok: ölçülemez", o5["durum"] == "olculemez", o5)

    # ── 4) Bağlantılar: defter, alışkanlık, rapor ───────────────────────
    from tasarruf.bulgular import BulguDefteri
    from tasarruf import rapor as R
    df_yol = os.path.join(GEC, "bulgu.json")
    bd = BulguDefteri(df_yol)
    bd.profilden_guncelle({"donem": "2026-10", "bulgular": [dict(bl["VANA_CAKISMASI"], santraller=["MAS-1 AHU-A"])]})
    c("defter: gün içi bulgu ölçütü 'gun_ici'", bd.kayitlar["VANA_CAKISMASI"]["olcut"] == "gun_ici")
    bd.karar_ver("VANA_CAKISMASI", "uygulandi", uygulama_tarihi="2026-10-01",
                 bugun=pd.Timestamp("2026-11-20").date())
    c("defter: gün içi verisi verilmezse atlanır", bd.olcumleri_guncelle(pd.DataFrame()) == [] and
      bd.kayitlar["VANA_CAKISMASI"]["durum"] == "olculuyor")
    bd.olcumleri_guncelle(pd.DataFrame(), gun_ici=(so, None))
    r = bd.kayitlar["VANA_CAKISMASI"]
    c("defter: gün içi ölçümle 'doğrulandı'", r["durum"] == "dogrulandi", r.get("olcum"))
    c("ölçüm metni davranış dilinde", R.olcum_metni(r["olcum"]).startswith("Uygulandığı doğrulandı"),
      R.olcum_metni(r["olcum"]))
    c("ölçülebilirlik metni gün içi", R.olculebilirlik_metni(None, "gun_ici").startswith("Ölçülebilir"))
    bd.profilden_guncelle({"donem": "2026-11", "bulgular": [dict(bl["VANA_CAKISMASI"], santraller=["MAS-1 AHU-Z"])]})
    c("uygulanmış bulgunun santral listesi sabit kalır", bd.kayitlar["VANA_CAKISMASI"]["santraller"] == ["MAS-1 AHU-A"])

    # Alışkanlık profiline bağlanma: sentetik enerji verisiyle ES_ZAMANLI
    from tasarruf import aliskanlik as A
    tarih = pd.date_range("2025-10-01", "2026-11-13")
    rng = np.random.default_rng(3)
    Tg = 15 + 10 * np.sin((tarih.dayofyear - 110) / 365 * 2 * np.pi)
    toplam = 60000 + rng.normal(0, 800, len(tarih))
    en = pd.DataFrame({"Tarih": tarih.strftime("%Y-%m-%d"),
                       "Dis_Hava_Sicakligi_C": Tg.round(2),
                       "Kazan_Dogalgaz_m3": np.clip(1500 - 80 * Tg, 50, None) + rng.normal(0, 30, len(tarih)),
                       "Chiller_Tuketim_kWh": np.clip(400 * (Tg - 8), 300, None) + rng.normal(0, 100, len(tarih)),
                       "Toplam_Hastane_Tuketim_kWh": toplam, "Sebeke_Tuketim_kWh": toplam * 0.4,
                       "Kojen_Uretim_kWh": toplam * 0.6, "Chiller_Set_Temp_C": 7.5, "Chiller_Adet": 2,
                       "Su_Tuketimi_m3": 300 + rng.normal(0, 10, len(tarih))})
    yuksek = en["Tarih"].isin([str(x.date()) for x in pd.date_range("2026-11-01", "2026-11-13")] +
                              [str(x.date()) for x in pd.date_range("2026-04-01", "2026-04-10")])
    en.loc[yuksek, "Kazan_Dogalgaz_m3"] = 1500 + rng.normal(0, 40, int(yuksek.sum()))   # sabit değer "donmuş sayaç" sayılır
    en.loc[yuksek, "Chiller_Tuketim_kWh"] = 6000 + rng.normal(0, 150, int(yuksek.sum()))
    s0 = A.profil(en, 2026, 11, haric=[])
    ez = s0.get("es_zamanli") or {}
    c("sentetik: günlük şüphe en az 10 gün", ez.get("gun", 0) >= 10, ez.get("gun"))
    s1 = A.profil(en, 2026, 11, haric=[], gun_ici=(oz2, bn2))
    kod = {x["kod"]: x for x in s1["bulgular"]}
    c("profil gün içi özetini taşır", s1.get("gun_ici", {}).get("gun") == 14, s1.get("gun_ici", {}).get("gun"))
    c("çakışma görülen şüphede ES bulgusu 'Öneri' olur",
      kod.get("ES_ZAMANLI_ISITMA_SOGUTMA", {}).get("durum") == "aday", kod.get("ES_ZAMANLI_ISITMA_SOGUTMA"))
    c("ES önerisi santral adı verir", "MAS-1 AHU-A" in kod.get("ES_ZAMANLI_ISITMA_SOGUTMA", {}).get("oneri", ""))
    c("profil gün içi bulgularını ekler", "VANA_CAKISMASI" in kod and "GECE_SUREKLI_CALISMA" in kod, list(kod))
    oz_zon = oz2.assign(cakisma_saat=0.0)
    s2 = A.profil(en, 2026, 11, haric=[], gun_ici=(oz_zon, bn2))
    k2 = {x["kod"] for x in s2["bulgular"]}
    c("yalnız zon farkı (≥5 gün veri): ES bulgusu kalkar", "ES_ZAMANLI_ISITMA_SOGUTMA" not in k2, k2)
    c("ve vana bulgusu da çıkmaz", "VANA_CAKISMASI" not in k2, k2)
    oz_az = oz_zon[oz_zon["Tarih"] <= "2026-11-03"]
    s3 = A.profil(en, 2026, 11, haric=[], gun_ici=(oz_az, bn2[bn2["Tarih"] <= "2026-11-03"]))
    es3 = {x["kod"]: x for x in s3["bulgular"]}.get("ES_ZAMANLI_ISITMA_SOGUTMA", {})
    c("az gün içi veride ES 'doğrulama gerekli' kalır", es3.get("durum") == "dogrulama_gerekli", es3.get("durum"))
    s4 = A.profil(en, 2026, 11, haric=[])
    c("gün içi verilmezse eski davranış", "gun_ici" not in s4 and
      {x["kod"]: x for x in s4["bulgular"]}.get("ES_ZAMANLI_ISITMA_SOGUTMA", {}).get("durum") == "dogrulama_gerekli")
    rm = A.rapor_metni(s1)
    c("rapor metninde gün içi satırları", len(rm.get("gun_ici", [])) >= 3, rm.get("gun_ici"))
    c("gün içi yoksa rapor satırı boş", A.rapor_metni(s4).get("gun_ici") == [])

    ab = R.aylik_bolum(en, 2026, 11, defter=BulguDefteri(os.path.join(GEC, "b2.json")),
                       olculebilirlik=False, gun_ici=(oz2, bn2))
    vb = {x["kod"]: x for x in ab["bulgular"]}
    c("aylık bölüm: vana bulgusu ölçülebilir", (vb.get("VANA_CAKISMASI", {}).get("olculebilirlik") or "").startswith("Ölçülebilir"),
      vb.get("VANA_CAKISMASI"))

    # PDF
    try:
        from monthly_report.pdf_generator import ModernPDFReportGenerator as _G  # noqa
        pdf_var = True
    except Exception:
        pdf_var = False
    pdf_kod = open(os.path.join(BURASI, "monthly_report", "pdf_generator.py"), encoding="utf-8").read()
    c("PDF gün içi satırlarını yazar", 'm.get("gun_ici")' in pdf_kod)

    _ap = open(os.path.join(BURASI, "app_portal.py"), encoding="utf-8").read()
    try:
        ast.parse(_ap)
        c("app_portal.py sözdizimi geçerli", True)
    except SyntaxError as ex:
        c("app_portal.py sözdizimi geçerli", False, f"satır {ex.lineno}: {ex.msg}")
    c("portal gün içi özetini bölüme verir", "gun_ici=_gun_ici" in _ap and 'st.markdown("**Gün içi santral' in _ap)

    # ── 5) Saha verisi: bağımsız hesap ──────────────────────────────────
    saha = os.path.join(BURASI, "..", "..", "_saha_deneme", "veri", "ahu_okuma_gecmis")
    dosyalar = sorted(x for x in os.listdir(saha) if x.startswith("ahu_bacnet_20261029")) if os.path.isdir(saha) else []
    if dosyalar:
        yollar_ = [os.path.join(saha, x) for x in dosyalar]
        o, _ = GI.gun_ozeti(yollar_)
        ham = pd.concat([pd.read_csv(p, dtype=str) for p in yollar_])
        ham = ham[ham["Durum"] == "OK"]
        ham["v"] = pd.to_numeric(ham["Deger"].str.replace(",", "."), errors="coerce")
        top = 0
        for (ts, lok, ahu), x in ham.groupby(["Timestamp", "Lokasyon", "AHU_Adi"]):
            n = dict(zip(x["Nokta_Tipi"].str[:5], x["v"]))
            if n.get("Start", 0) >= 0.5 and n.get("Cool ", 0) > 10 and n.get("Heat ", 0) > 10:
                top += 1
        c("saha 29.10.2026: çakışma bağımsız hesapla aynı", abs(o["cakisma_saat"].sum() - top / 6) < 1e-9,
          (o["cakisma_saat"].sum(), top / 6))
        c("saha: 50'den fazla santral (lokasyon+ad)", len(o) > 50, len(o))
finally:
    shutil.rmtree(GEC, ignore_errors=True)

basarili = sum(1 for _, k, _ in T if k)
for ad, k, dt in T:
    print(("  OK  " if k else "  HATA") + f"  {ad}" + ("" if k else f"  → {dt}"))
print(f"\n{basarili}/{len(T)} geçti")
sys.exit(0 if basarili == len(T) else 1)
