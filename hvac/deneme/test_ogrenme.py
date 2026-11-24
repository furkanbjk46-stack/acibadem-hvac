# -*- coding: utf-8 -*-
"""Öğrenme: kural güveni, lokasyona özel eşik, susturma, Synapse özeti (A5, 24.11.2026).

    python hvac/deneme/test_ogrenme.py

Neden var: öğrenme "kaç öneriye evet dendi"den değil ölçülen sonuçtan beslenmeli;
tutmayan kural o lokasyonda alta inmeli, sonra susmalı; aynı nedenle reddedilen bulgu
tekrar sorulmamalı; hafta sonu farkı lokasyonun günler arası olağan farkını aşmıyorsa
alışkanlık sayılmamalı. Bu test:
  1) kural özetini (güven, seviye, eşik çarpanı) bilinen geçmişlerle,
  2) defterin karar kurallarını (ölçüm geçmişi, aynı neden, kural susturma),
  3) lokasyona özel eşiği ve öğrenilen çarpanı sentetik veriyle,
  4) rapor bölümünü, heartbeat özetini ve Synapse kartını
doğrular.
"""
import ast
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

from tasarruf import ogrenme as OG
from tasarruf import aliskanlik as A
from tasarruf import bulgular as BL
from tasarruf.bulgular import BulguDefteri

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


def kayit(kod, durum, kararlar=(), gecmis=()):
    return {"kod": kod, "durum": durum, "karar_gecmisi": [dict(k) for k in kararlar],
            "olcum_gecmisi": [{"durum": d} for d in gecmis]}


UYG = {"karar": "uygulandi"}


def red(n):
    return {"karar": "reddedildi", "neden": n}


GEC = tempfile.mkdtemp(prefix="ogrenme_test_")
try:
    # ── 1) Kural özeti ──────────────────────────────────────────────────
    c("kural adı gün tipi ekini atar", OG.kural_adi("HAFTA_SONU_ISITMA_PAZAR") == "HAFTA_SONU_ISITMA"
      and OG.kural_adi("SU_ARTISI_HAFTA_ICI") == "SU_ARTISI" and OG.kural_adi("SET_DIS_HAVA") == "SET_DIS_HAVA")
    oz = OG.kural_ozeti([kayit("SET_DIS_HAVA", "raporda")])
    c("kanıt yokken 'yeni', güven %50", oz["SET_DIS_HAVA"]["seviye"] == "yeni" and oz["SET_DIS_HAVA"]["guven"] == 0.5)
    oz = OG.kural_ozeti([kayit("HAFTA_SONU_ISITMA_PAZAR", "dogrulandi", [UYG]),
                         kayit("HAFTA_SONU_ISITMA_CUMARTESI", "dogrulandi", [UYG])])
    k = oz["HAFTA_SONU_ISITMA"]
    c("iki gün tipi aynı kural sayılır", k["dogrulandi"] == 2 and len(k["bulgular"]) == 2, k)
    c("iki doğrulama → 'yüksek'", k["seviye"] == "yuksek" and abs(k["guven"] - 0.75) < 1e-9, k)
    oz = OG.kural_ozeti([kayit("SET_DIS_HAVA", "tutmadi", [UYG, UYG], gecmis=["artis"])])
    k = oz["SET_DIS_HAVA"]
    c("iki tutmadı (biri geçmişte) → 'düşük'", k["tutmadi"] == 2 and k["seviye"] == "dusuk", k)
    c("eşik çarpanı 1,25²", abs(k["esik_carpani"] - 1.5625) < 1e-9, k["esik_carpani"])
    oz = OG.kural_ozeti([kayit("SET_DIS_HAVA", "reddedildi", [UYG, red("veri_yanlis"), UYG], gecmis=["artis", "artis"])])
    c("2 tutmadı + 1 veri yanlış → 'susturuldu'", oz["SET_DIS_HAVA"]["seviye"] == "susturuldu", oz["SET_DIS_HAVA"])
    oz = OG.kural_ozeti([kayit("SU_ARTISI_PAZAR", "reddedildi", [red("uygulanamaz"), red("uygulanamaz")]),
                         kayit("SU_ARTISI_HAFTA_ICI", "olculemez", [UYG])])
    c("'uygulanamaz' ve 'ölçülemez' güveni etkilemez", oz["SU_ARTISI"]["seviye"] == "yeni"
      and oz["SU_ARTISI"]["esik_carpani"] == 1.0, oz["SU_ARTISI"])
    oz = OG.kural_ozeti([kayit("VANA_CAKISMASI", "belirsiz", [UYG], gecmis=["dogrulandi"])])
    c("doğrulandı + belirsiz → güven %71, 'orta' (2 başarı gerekir)", abs(oz["VANA_CAKISMASI"]["guven"] - 2.5 / 3.5) < 1e-9
      and oz["VANA_CAKISMASI"]["seviye"] == "orta", oz["VANA_CAKISMASI"])
    oz = OG.kural_ozeti([kayit("X", "tutmadi", [UYG], gecmis=["artis"] * 9)])
    c("eşik çarpanı en fazla 3", oz["X"]["esik_carpani"] == 3.0)
    c("bozuk kayıt atlanır", OG.kural_ozeti([None, {}, {"kod": ""}]) == {})

    # sıralama
    oz = OG.kural_ozeti([kayit("SET_DIS_HAVA", "tutmadi", [UYG], gecmis=["artis"]),
                         kayit("SU_ARTISI_PAZAR", "dogrulandi", [UYG], gecmis=["dogrulandi"]),
                         kayit("VANA_CAKISMASI", "tutmadi", [UYG], gecmis=["artis", "artis"])])
    bl = [{"kod": "SET_DIS_HAVA", "durum": "Öneri", "tasarruf": "x"},
          {"kod": "ES_ZAMANLI_ISITMA_SOGUTMA", "durum": "Doğrulama gerekli", "tasarruf": None},
          {"kod": "GECE_SUREKLI_CALISMA", "durum": "Öneri", "tasarruf": None},
          {"kod": "SU_ARTISI_PAZAR", "durum": "Öneri", "tasarruf": "y"},
          {"kod": "VANA_CAKISMASI", "durum": "Öneri", "tasarruf": None}]
    sr = [b["kod"] for b in OG.sirala(bl, oz)]
    c("sıralama: güvenli önce, düşük sonda, susturulan yok",
      sr == ["SU_ARTISI_PAZAR", "GECE_SUREKLI_CALISMA", "ES_ZAMANLI_ISITMA_SOGUTMA", "SET_DIS_HAVA"], sr)
    g = OG.guven_metni(oz, "SET_DIS_HAVA")
    c("güven metni sonuçları ve düşük seviyeyi söyler", g and "%" in g and "2 tutmadı" in g and "alta indi" in g
      and "katına" in g, g)
    c("yeni kuralda güven metni yok", OG.guven_metni(oz, "GECE_SUREKLI_CALISMA") is None)
    c("synapse özeti yalnız kanıtlı kurallar", {x["kural"] for x in OG.synapse_ozeti(oz)} ==
      {"SET_DIS_HAVA", "SU_ARTISI", "VANA_CAKISMASI"})

    # ── 2) Defter ───────────────────────────────────────────────────────
    yol = os.path.join(GEC, "defter.json")
    d = BulguDefteri(yol)
    bulgu = lambda kod: {"kod": kod, "baslik": kod, "kanit": "k", "oneri": "o", "durum": "aday"}
    d.profilden_guncelle({"donem": "2026-01", "bulgular": [bulgu("SET_DIS_HAVA"), bulgu("SU_ARTISI_PAZAR"),
                                                           bulgu("HAFTA_SONU_ISITMA_PAZAR")]},
                         bugun=date(2026, 1, 31))
    d.karar_ver("SET_DIS_HAVA", "uygulandi", uygulama_tarihi="2026-02-01", bugun=date(2026, 2, 1))
    d.kayitlar["SET_DIS_HAVA"]["olcum"] = {"durum": "artis", "olcut": "sogutma"}
    d.kayitlar["SET_DIS_HAVA"]["durum"] = "tutmadi"
    d.karar_ver("SET_DIS_HAVA", "uygulandi", uygulama_tarihi="2026-09-01", bugun=date(2026, 9, 1))
    r = d.kayitlar["SET_DIS_HAVA"]
    c("yeniden uygulamada önceki ölçüm geçmişe yazılır", [o["durum"] for o in r.get("olcum_gecmisi", [])] == ["artis"]
      and r["olcum"] is None, r.get("olcum_gecmisi"))
    c("geçmiş ölçüm güvene sayılır", d.ogrenme()["SET_DIS_HAVA"]["tutmadi"] == 1)

    d.karar_ver("SU_ARTISI_PAZAR", "reddedildi", neden="zaten_yapiliyor", bugun=date(2026, 2, 1))
    c("'zaten yapılıyor' 6 ay susturur", d.kayitlar["SU_ARTISI_PAZAR"].get("susturma_bitis") == "2026-08-02",
      d.kayitlar["SU_ARTISI_PAZAR"].get("susturma_bitis"))
    d.karar_ver("HAFTA_SONU_ISITMA_PAZAR", "reddedildi", neden="veri_yanlis", bugun=date(2026, 2, 1))
    c("ilk 'veri yanlış' susturmaz", not d.kayitlar["HAFTA_SONU_ISITMA_PAZAR"].get("susturma_bitis"))
    d.karar_ver("HAFTA_SONU_ISITMA_PAZAR", "reddedildi", neden="veri_yanlis", bugun=date(2026, 9, 1))
    c("aynı nedenle ikinci ret 1 yıl susturur",
      d.kayitlar["HAFTA_SONU_ISITMA_PAZAR"].get("susturma_bitis") == "2027-09-01",
      d.kayitlar["HAFTA_SONU_ISITMA_PAZAR"].get("susturma_bitis"))
    c("'veri yanlış' eşiği yükseltir", d.ogrenme()["HAFTA_SONU_ISITMA"]["esik_carpani"] > 1.0)
    d.karar_ver("SU_ARTISI_PAZAR", "reddedildi", neden="diger", notlar="a", bugun=date(2026, 9, 1))
    d.karar_ver("SU_ARTISI_PAZAR", "reddedildi", neden="diger", notlar="b", bugun=date(2026, 9, 2))
    c("'diğer' tekrarı uzun susturmaz", not d.kayitlar["SU_ARTISI_PAZAR"].get("susturma_bitis"))

    # Kural düzeyinde susturma: tutmayan kuralın yeni bulgusu sorulmaz
    d2 = BulguDefteri(os.path.join(GEC, "d2.json"))
    d2.kayitlar["SET_DIS_HAVA"] = dict(kayit("SET_DIS_HAVA", "tutmadi", [UYG, UYG, UYG], gecmis=["artis", "artis"]),
                                      kimlik="SET_DIS_HAVA", donemler=[], baslik="s")
    gos = d2.profilden_guncelle({"donem": "2026-10", "bulgular": [bulgu("SET_DIS_HAVA"), bulgu("SU_ARTISI_PAZAR")]},
                                bugun=date(2026, 10, 31))
    c("susturulan kuralın bulgusu raporda gösterilmez", "SET_DIS_HAVA" not in gos and "SU_ARTISI_PAZAR" in gos, gos)
    d2.kayitlar["SET_DIS_HAVA"]["durum"] = "raporda"
    d2.kayitlar["SET_DIS_HAVA"]["olcum_gecmisi"].append({"durum": "artis"})   # 3 tutmadı geçmişte kalır
    c("susturulan kural karar listesinde yok", all(x["kod"] != "SET_DIS_HAVA" for x in d2.karar_bekleyenler()))

    # ── 3) Lokasyona özel eşik ──────────────────────────────────────────
    def sentetik(pazar_fazla=0.12, carsamba_fazla=0.0):
        gun = pd.date_range("2024-11-01", "2026-10-31", freq="D")
        rng = np.random.default_rng(11)
        T_ = 15 - 10 * np.cos(2 * np.pi * (gun.dayofyear.values - 15) / 365) + rng.normal(0, 1.0, len(gun))
        hg = gun.dayofweek.values
        gaz = np.clip(150 * (16 - T_), 0, None) + rng.normal(0, 20, len(gun))
        gaz = np.clip(gaz, 0, None) * np.where((hg == 6) & (T_ < 16), 1 + pazar_fazla, 1)
        gaz = gaz * np.where((hg == 2) & (T_ < 16), 1 + carsamba_fazla, 1)
        sog = 2500 + np.clip(600 * (T_ - 12), 0, None) + rng.normal(0, 100, len(gun))
        top = 60000 + 300 * np.abs(T_ - 16) - np.where(hg == 6, 6000, 0) + rng.normal(0, 500, len(gun))
        return pd.DataFrame({"Tarih": gun.strftime("%Y-%m-%d"), "Toplam_Hastane_Tuketim_kWh": top,
                             "Sebeke_Tuketim_kWh": top * 0.4, "Kojen_Uretim_kWh": top * 0.6,
                             "Chiller_Tuketim_kWh": sog, "Kazan_Dogalgaz_m3": gaz,
                             "Su_Tuketimi_m3": 450 + rng.normal(0, 10, len(gun)),
                             "Chiller_Set_Temp_C": np.where(T_ >= 24, 7.0, 7.5),
                             "Chiller_Adet": np.where(T_ > 20, 3, 1), "Dis_Hava_Sicakligi_C": T_.round(2)})

    sa = A.profil(sentetik(), 2026, 10, haric=[])
    kod = {b["kod"] for b in sa["bulgular"]}
    hs = sa["esikler"].get("hafta_sonu") or {}
    c("sakin lokasyon: doğal fark küçük, eşik %5", hs.get("dogal") is not None and hs["dogal"] < 0.05
      and abs(hs["esik"] - 0.05) < 1e-9, hs)
    c("sakin lokasyon: pazar +%12 bulgu olur", "HAFTA_SONU_ISITMA_PAZAR" in kod, kod)
    so = A.profil(sentetik(carsamba_fazla=0.25), 2026, 10, haric=[])
    hs2 = so["esikler"].get("hafta_sonu") or {}
    c("oynak lokasyon: çarşamba farkı doğal farkı büyütür", (hs2.get("dogal") or 0) > 0.15, hs2)
    c("oynak lokasyon: pazar +%12 alışkanlık sayılmaz",
      "HAFTA_SONU_ISITMA_PAZAR" not in {b["kod"] for b in so["bulgular"]}, [b["kod"] for b in so["bulgular"]])
    sc = A.profil(sentetik(), 2026, 10, haric=[], esik_carpani={"HAFTA_SONU_ISITMA": 3.0})
    c("öğrenilen çarpan (×3) bulguyu kaldırır", "HAFTA_SONU_ISITMA_PAZAR" not in {b["kod"] for b in sc["bulgular"]},
      sc["esikler"].get("hafta_sonu"))
    c("set kuralı çarpanla sıkılaşır", A.profil(sentetik(), 2026, 10, haric=[],
                                                esik_carpani={"SET_DIS_HAVA": 2.0})["esikler"]["set"]["esik"] == 0.5)
    c("pazar bulgusu olağan farkı metinde söyler",
      "olağan fark" in [b for b in sa["bulgular"] if b["kod"] == "HAFTA_SONU_ISITMA_PAZAR"][0]["kanit"])

    # ── 4) Rapor bölümü ─────────────────────────────────────────────────
    from tasarruf import rapor as R
    df = sentetik()
    d3 = BulguDefteri(os.path.join(GEC, "d3.json"))
    d3.kayitlar["HAFTA_SONU_ISITMA_CUMARTESI"] = dict(
        kayit("HAFTA_SONU_ISITMA_CUMARTESI", "dogrulandi", [UYG], gecmis=["dogrulandi"]),
        kimlik="HAFTA_SONU_ISITMA_CUMARTESI", donemler=[], baslik="Cumartesi")
    d3.kayitlar["SU_ARTISI_HAFTA_ICI"] = dict(
        kayit("SU_ARTISI_HAFTA_ICI", "reddedildi", [dict(red("veri_yanlis"), tarih="2026-10-05", notlar="sayaç değişti")]),
        kimlik="SU_ARTISI_HAFTA_ICI", donemler=[], baslik="Su")
    m = R.aylik_bolum(df, 2026, 10, defter=d3, olculebilirlik=False)
    pz = [b for b in m["bulgular"] if b["kod"] == "HAFTA_SONU_ISITMA_PAZAR"]
    c("rapor: pazar bulgusu cumartesinin sonucundan güven alır", pz and pz[0].get("guven")
      and "%75" in pz[0]["guven"], pz[0].get("guven") if pz else m["bulgular"])
    c("rapor: en fazla 5 bulgu", len(m["bulgular"]) <= OG.EN_FAZLA_BULGU)
    c("rapor: 'veri yanlış' reddi veri kalitesine düşer",
      any("veri yanlış" in x and "sayaç değişti" in x and "05.10.2026" in x for x in m["kalite"]), m["kalite"][-2:])
    c("rapor: lokasyon eşiği öğrenilenlerde", any("Hafta sonu ısıtma eşiği" in x for x in m["ogrenme"]), m["ogrenme"])
    m2 = R.aylik_bolum(df.iloc[:30], 2026, 10, defter=BulguDefteri(os.path.join(GEC, "d4.json")), olculebilirlik=False)
    c("az veride bölüm çökmez", m2.get("alt_bulgular") == [] and m2.get("ogrenme") == [])

    # PDF
    try:
        from monthly_report.pdf_generator import MonthlyReportPDFGenerator
        m["alt_bulgular"] = [{"baslik": "Düşük öncelikli örnek"}]
        pdf = MonthlyReportPDFGenerator().generate(2026, 10, {"summary": {}}, {}, [], aliskanlik=m)
        c("PDF güven ve öğrenilenlerle üretilir", isinstance(pdf, bytes) and len(pdf) > 1000)
    except Exception as ex:
        c("PDF güven ve öğrenilenlerle üretilir", False, repr(ex))

    # ── Heartbeat özeti ─────────────────────────────────────────────────
    import cloud_sync
    eski = BL.varsayilan_yol
    try:
        BL.varsayilan_yol = lambda: os.path.join(GEC, "yok.json")
        c("heartbeat: defter yoksa boş", cloud_sync._tasarruf_ozet() == {})
        d5 = BulguDefteri(os.path.join(GEC, "d5.json"))
        d5.kayitlar = {
            "SET_DIS_HAVA": dict(kayit("SET_DIS_HAVA", "dogrulandi", [UYG]), kimlik="SET_DIS_HAVA",
                                 olcum={"durum": "dogrulandi", "olcut": "sogutma", "birim": "kWh", "tasarruf": 1234.4}),
            "VANA_CAKISMASI": dict(kayit("VANA_CAKISMASI", "dogrulandi", [UYG]), kimlik="VANA_CAKISMASI",
                                   olcum={"durum": "dogrulandi", "olcut": "gun_ici", "tasarruf": None}),
            "SU_ARTISI_PAZAR": dict(kayit("SU_ARTISI_PAZAR", "raporda"), kimlik="SU_ARTISI_PAZAR")}
        d5.kaydet()
        BL.varsayilan_yol = lambda: os.path.join(GEC, "d5.json")
        hb = cloud_sync._tasarruf_ozet()
        c("heartbeat: sayılar", hb.get("bulgu") == 3 and hb.get("dogrulandi") == 2 and hb.get("karar_bekleyen") == 1, hb)
        c("heartbeat: doğrulanan kWh (gün içi kWh sayılmaz)", hb.get("dogrulanan_tasarruf") == {"kWh": 1234}, hb)
        c("heartbeat: küçük (<1 KB)", len(json.dumps(hb, ensure_ascii=False)) < 1024, len(json.dumps(hb)))
        hb_kod = open(os.path.join(BURASI, "cloud_sync.py"), encoding="utf-8").read()
        c("heartbeat tasarruf özetini gönderir", '_ozet["tasarruf"] = _tasarruf_ozet()' in hb_kod)
    finally:
        BL.varsayilan_yol = eski

    # ── Synapse kartı ───────────────────────────────────────────────────
    sys.path.insert(0, os.path.join(BURASI, "..", "..", "merkez"))
    import ana_ekran_cark_demo as AE
    sh = AE.saha_ozeti({"tasarruf": hb}, {})
    c("Synapse: tasarruf özeti karta girer", sh.get("ts") and sh["ts"]["dog"] == 2 and sh["ts"]["acik"] == 1
      and "1.234 kWh" in sh["ts"]["alt"], sh.get("ts"))
    c("Synapse: özet yoksa eski kart", AE.saha_ozeti({"geri_bildirim": {"kayit": 3}}, {}).get("ts") is None)
    ae_kod = open(os.path.join(BURASI, "..", "..", "merkez", "ana_ekran_cark_demo.py"), encoding="utf-8").read()
    c("Synapse: 'Tasarruf bulguları' kartı", "'Tasarruf bulguları'" in ae_kod)

    _ap = open(os.path.join(BURASI, "app_portal.py"), encoding="utf-8").read()
    try:
        ast.parse(_ap)
        c("app_portal.py sözdizimi geçerli", True)
    except SyntaxError as ex:
        c("app_portal.py sözdizimi geçerli", False, f"satır {ex.lineno}: {ex.msg}")
    c("portal güven ve öğrenilenleri gösterir", "_b.get(\"guven\")" in _ap and "Bu lokasyondan öğrenilenler" in _ap)
finally:
    shutil.rmtree(GEC, ignore_errors=True)

basarili = sum(1 for _, k, _ in T if k)
for ad, k, dt in T:
    print(("  OK  " if k else "  HATA") + f"  {ad}" + ("" if k else f"  → {dt}"))
print(f"\n{basarili}/{len(T)} geçti")
sys.exit(0 if basarili == len(T) else 1)
