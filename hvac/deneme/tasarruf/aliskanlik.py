# -*- coding: utf-8 -*-
"""
ALIŞKANLIK PROFİLİ — lokasyon nasıl kullanılıyor, tasarruf nerede?
=================================================================

A2 (24.11.2026, tasarım: merkez/sunum/tasarruf_ogrenme_tasarimi.html).

Eski öneri motoru (monthly_report/savings_engine.py) ayın TOPLAMINI geçen yılın
aynı ayıyla kıyaslar; lokasyonun nasıl kullanıldığını bilmez. Bu modül rapor
ayıyla biten 12 aylık pencerede lokasyonun kendi günlük verisinden şu
alışkanlıkları çıkarır:

  · Haftalık ritim   — hafta içi / cumartesi / pazar / tatil ortalamaları
  · Hafta sonu ısıtma — pazar (ve cumartesi) kazan gazı, AYNI DIŞ SICAKLIKTAKİ
                        hafta içi günlerine göre (hava eşleştirmeli kıyas)
  · Dış havaya tepki — chiller seti ve chiller adedi dış hava bandına göre
  · Eş zamanlı ısıtma-soğutma — aynı gün kazan ve soğutma birlikte yüksek
  · Kojen düzeni     — çalıştığı günlerin oranı
  · Su               — gün tipine göre taban; rapor ayında artış

VERİ KALİTESİ KAPISI: Tüketim Tahmini'nin kalite kontrolü (tuketim_tahmin/
veri_kalite.py: hariç dönem, sıfır gün, çift gün, kojen kaybı, donmuş sensör,
şebeke girilmemiş) aynen kullanılır; üstüne:
  · ölçüt kapsamı: pencerede ölçütün en az %70'i dolu olmalı
  · donmuş sayaç: gaz/su aynı sıfırdan büyük değeri 5+ gün tekrarlıyorsa o günler atılır
  · kırılma: yazlar arası soğutma/derece-gün oranı %25'ten fazla değiştiyse
    (sayaç ya da hesap kuralı değişikliği olabilir) uyarı
Kapıdan geçmeyen ölçütten bulgu ÜRETİLMEZ: bulgu "veri şüpheli" olarak
gösterilir, tasarruf rakamı yazılmaz. Yanlış bulgu güveni bir öneriden çok
kaybettirir.

Tasarruf rakamları lokasyonun kendi verisinden hesaplanır. Tek istisna chiller
seti: setin tüketime etkisi bu veriden ayrılamıyor (set neredeyse sabit), bu yüzden
genel katsayı (%2,5/°C) kullanılır ve metinde açıkça yazılır.
"""
from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

# ── ayarlar ──────────────────────────────────────────────────────────────
PENCERE_AY = 12
EN_AZ_KAPSAM = 0.70          # ölçütün penceredeki dolu gün oranı
DONMA_GUN = 5                # aynı değer art arda bu kadar gün → donmuş sayaç
KIRILMA_ORANI = 0.25         # yazlar arası soğutma/CDD değişimi
CDD_TABAN = 18.0             # soğutma derece-gün tabanı (°C)
ESLESME_TOL_C = 1.5          # hava eşleştirmesinde sıcaklık toleransı
ESLESME_GUN = 45             # hava eşleştirmesinde en fazla gün uzaklığı
ISITMA_T_UST = 16.0          # ısıtma kıyası bu dış sıcaklığın altındaki günlerde
HAFTA_SONU_ESIK = 0.05      # hafta sonu fazlası en az bu (A5: lokasyonun olağan farkı daha büyükse o)
SET_ARALIK_ESIK = 1.0        # chiller seti bantlar arası bu kadardan az değişiyorsa "tepki yok"
SU_ESIK = 0.15               # su artışı en az bu (A5: lokasyonun aylık olağan sapmasının 1,5 katı daha büyükse o)
SET_KATSAYI = 0.025          # chiller set +1 °C → soğutma enerjisi ~%2,5 (genel katsayı)
HAVA_BANTLARI = [(-50, 10, "<10 °C"), (10, 18, "10–18 °C"), (18, 24, "18–24 °C"), (24, 60, "≥24 °C")]
GUN_TIPLERI = {"hafta_ici": "Hafta içi", "cumartesi": "Cumartesi", "pazar": "Pazar", "tatil": "Bayram/tatil"}

OLCUTLER = {
    # ad: (başlık, birim)
    "toplam": ("Toplam tüketim", "kWh"),
    "sogutma": ("Soğutma", "kWh"),
    "gaz": ("Kazan doğalgazı", "m³"),
    "su": ("Su", "m³"),
}

HAM_SUTUN = {
    "su": "Su_Tuketimi_m3",
    "set": "Chiller_Set_Temp_C",
    "chiller_adet": "Chiller_Adet",
}


def tr_tarih(iso: str) -> str:
    """2026-10-31 → 31.10.2026"""
    try:
        return pd.Timestamp(iso).strftime("%d.%m.%Y")
    except Exception:
        return str(iso)


def tr_yuzde(oran: float) -> str:
    """Türkçe işaretli yüzde: +%18, -%10"""
    if oran is None:
        return "-"
    return ("+" if oran >= 0 else "-") + "%" + tr_sayi(abs(oran) * 100)


def tr_sayi(x, ondalik: int = 0) -> str:
    """Türkçe sayı: 12.345,6"""
    if x is None or (isinstance(x, float) and np.isnan(x)):
        return "-"
    s = f"{x:,.{ondalik}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


# ── hazırlık ─────────────────────────────────────────────────────────────
def hazirla(df: pd.DataFrame, haric: Optional[List[Dict]] = None):
    """energy_data → günlük çalışma tablosu + Tüketim Tahmini kalite raporu."""
    from tuketim_tahmin import portal_ozet
    from tuketim_tahmin.takvim import tatil_serisi

    g, kalite = portal_ozet.birlestir(df, haric=haric)
    t = pd.DataFrame({
        "tarih": pd.to_datetime(g["tarih"]).values,
        "toplam": g["toplam"].where(g["hedef_gecerli"]).values,
        "sogutma": g["sogutma"].values,
        "gaz": g["isitma_gaz"].values,
        "kojen": g["kojen"].values,
        "T": g["T"].values,
    })
    ham = df.copy()
    ham["Tarih"] = pd.to_datetime(ham["Tarih"], errors="coerce")
    ham = ham.dropna(subset=["Tarih"]).drop_duplicates("Tarih", keep="last").set_index("Tarih")
    for ad, sutun in HAM_SUTUN.items():
        t[ad] = (pd.to_numeric(ham[sutun], errors="coerce").reindex(t["tarih"]).values
                 if sutun in ham.columns else np.nan)
    tatil = tatil_serisi(t["tarih"]).values > 0
    hg = t["tarih"].dt.dayofweek
    t["gun_tipi"] = np.select([tatil, hg == 6, hg == 5], ["tatil", "pazar", "cumartesi"], "hafta_ici")
    return t.sort_values("tarih").reset_index(drop=True), kalite


def _kosu_maskesi(seri: pd.Series, n: int) -> pd.Series:
    """Aynı sıfırdan büyük değerin art arda n+ gün tekrarlandığı günler."""
    s = seri.round(3)
    grup = (s != s.shift()).cumsum()
    uzunluk = s.groupby(grup).transform("size")
    return (uzunluk >= n) & s.notna() & (s > 0)


# ── veri kalitesi kapısı ─────────────────────────────────────────────────
def veri_kalitesi(t: pd.DataFrame, pencere: pd.Series, kalite_raporu=None) -> Dict:
    """Pencere için ölçüt kapsamı, donmuş sayaç, kırılma. t'de donmuş günleri boşaltır."""
    bas, son = t.loc[pencere, "tarih"].min(), t.loc[pencere, "tarih"].max()
    sorunlar = []
    if kalite_raporu is not None:
        for b in kalite_raporu.bulgular:
            if pd.Timestamp(b["son"]) >= bas and pd.Timestamp(b["bas"]) <= son:
                sorunlar.append({"tur": b["tur"], "bas": b["bas"], "son": b["son"], "gun": b["gun"],
                                 "aciklama": b["aciklama"]})

    for ad in ("gaz", "su"):
        m = _kosu_maskesi(t[ad], DONMA_GUN) & pencere
        if m.any():
            t.loc[m, ad] = np.nan
            sorunlar.append({"tur": "DONMUŞ SAYAÇ", "bas": str(t.loc[m, "tarih"].min().date()),
                             "son": str(t.loc[m, "tarih"].max().date()), "gun": int(m.sum()),
                             "aciklama": f"{OLCUTLER[ad][0]} aynı değeri {DONMA_GUN}+ gün tekrarlıyor — o günler kullanılmadı"})

    n = int(pencere.sum())
    kapsam = {ad: (float(t.loc[pencere, ad].notna().sum()) / n if n else 0.0) for ad in OLCUTLER}
    kapsam["set"] = float(t.loc[pencere, "set"].notna().sum()) / n if n else 0.0
    kapsam["T"] = float(t.loc[pencere, "T"].notna().sum()) / n if n else 0.0
    gecerli = {ad: kapsam[ad] >= EN_AZ_KAPSAM for ad in kapsam}

    # Kırılma: yaz (Haz–Eyl) soğutma / CDD, ardışık yıllar
    yaz = t[t["tarih"].dt.month.isin([6, 7, 8, 9]) & t["sogutma"].notna() & t["T"].notna()].copy()
    yaz["cdd"] = (yaz["T"] - CDD_TABAN).clip(lower=0)
    yillik = yaz.groupby(yaz["tarih"].dt.year).agg(sog=("sogutma", "sum"), cdd=("cdd", "sum"), gun=("sogutma", "size"))
    yillik = yillik[(yillik["gun"] >= 60) & (yillik["cdd"] > 0)]
    oranlar = {int(y): float(r.sog / r.cdd) for y, r in yillik.iterrows()}
    kirilmalar = []
    yillar = sorted(oranlar)
    for a, b in zip(yillar, yillar[1:]):
        degisim = oranlar[b] / oranlar[a] - 1
        if abs(degisim) > KIRILMA_ORANI:
            kirilmalar.append({"olcut": "sogutma", "onceki_yil": a, "yil": b,
                               "onceki_oran": round(oranlar[a]), "oran": round(oranlar[b]),
                               "degisim": round(degisim, 3),
                               "aciklama": (f"Yaz soğutması derece-gün başına {tr_sayi(oranlar[a])} → "
                                            f"{tr_sayi(oranlar[b])} kWh ({tr_yuzde(degisim)}). Gerçek bir verimlilik "
                                            "değişikliği mi, sayaç/hesap değişikliği mi doğrulanmalı; "
                                            "bu iki yıl arasındaki kıyaslar yanıltıcı olabilir.")})
    return {"sorunlar": sorunlar, "kapsam": kapsam, "gecerli": gecerli,
            "yaz_sogutma_cdd": oranlar, "kirilmalar": kirilmalar}


# ── alışkanlık hesapları ─────────────────────────────────────────────────
def haftalik_ritim(p: pd.DataFrame) -> Dict:
    """Ölçüt başına gün tipi ortalamaları (pencere içinde)."""
    sonuc = {}
    for ad in OLCUTLER:
        ort = p.groupby("gun_tipi")[ad].mean()
        say = p.groupby("gun_tipi")[ad].count()
        sonuc[ad] = {tip: (float(ort[tip]) if tip in ort and say[tip] > 0 else None) for tip in GUN_TIPLERI}
        sonuc[ad]["gun"] = {tip: int(say.get(tip, 0)) for tip in GUN_TIPLERI}
    return sonuc


def hava_eslesmeli(p: pd.DataFrame, olcut: str, tip: str, t_ust: Optional[float] = None) -> Optional[Dict]:
    """tip günlerinin olcut değeri − aynı dış sıcaklıktaki (±1,5 °C, ±45 gün) hafta içi
    günlerinin ortalaması. Döner: gün sayısı, ortalama fark, referans ortalaması, pozitif oran."""
    d = p[p[olcut].notna() & p["T"].notna()]
    if t_ust is not None:
        d = d[d["T"] < t_ust]
    hedef = d[d["gun_tipi"] == tip]
    ref = d[d["gun_tipi"] == "hafta_ici"]
    farklar, refler = [], []
    for _, r in hedef.iterrows():
        aday = ref[((ref["T"] - r["T"]).abs() <= ESLESME_TOL_C)
                   & ((ref["tarih"] - r["tarih"]).dt.days.abs() <= ESLESME_GUN)]
        if len(aday) >= 3:
            farklar.append(float(r[olcut] - aday[olcut].mean()))
            refler.append(float(aday[olcut].mean()))
    if not farklar:
        return None
    ref_ort = float(np.mean(refler))
    fark = float(np.mean(farklar))
    return {"gun": len(farklar), "fark": fark, "referans": ref_ort,
            "fark_yuzde": (fark / ref_ort) if ref_ort > 0 else None,
            "pozitif_oran": float(np.mean([f > 0 for f in farklar]))}


def dogal_fark(p: pd.DataFrame, olcut: str, t_ust: Optional[float] = None) -> Optional[float]:
    """A5: lokasyonun kendi 'normal' farkı — her hafta içi gün (pzt..cum), aynı dış sıcaklıktaki
    diğer hafta içi günleriyle hava_eslesmeli kıyaslanır; en büyük |fark %| döner.
    Hafta sonu farkı bunu aşmıyorsa alışkanlık değil, günler arası olağan oynamadır."""
    if "gun_tipi" not in p.columns or p.empty:
        return None
    hg = p["tarih"].dt.dayofweek
    sonuc = []
    for g in range(5):
        q = p.copy()
        hedef = (q["gun_tipi"] == "hafta_ici") & (hg == g)
        q.loc[hedef, "gun_tipi"] = "_plasebo"
        h = hava_eslesmeli(q, olcut, "_plasebo", t_ust=t_ust)
        if h and h.get("fark_yuzde") is not None and h["gun"] >= 6:
            sonuc.append(abs(h["fark_yuzde"]))
    return float(max(sonuc)) if sonuc else None


def su_dogal_artis(onceki: pd.DataFrame, tip: str) -> Optional[float]:
    """A5: önceki aylarda aylık ortalamanın genel ortalamadan en büyük sapması (su, gün tipi)."""
    d = onceki[onceki["gun_tipi"] == tip]
    aylik = d.groupby(d["tarih"].dt.to_period("M"))["su"].mean().dropna()
    if len(aylik) < 4 or aylik.mean() <= 0:
        return None
    return float((aylik / aylik.mean() - 1).max())


def chiller_dis_hava(p: pd.DataFrame) -> Dict:
    d = p[p["set"].notna() & p["T"].notna() & (p["sogutma"].fillna(0) > 0)]
    bantlar = []
    for alt, ust, ad in HAVA_BANTLARI:
        b = d[(d["T"] >= alt) & (d["T"] < ust)]
        bantlar.append({"bant": ad, "gun": int(len(b)),
                        "set": float(b["set"].mean()) if len(b) else None,
                        "chiller_adet": float(b["chiller_adet"].mean()) if b["chiller_adet"].notna().any() else None,
                        "sogutma": float(b["sogutma"].mean()) if len(b) else None})
    setler = d["set"].round(1).value_counts().sort_index()
    return {"bantlar": bantlar, "setler": {float(k): int(v) for k, v in setler.items()}, "gun": int(len(d))}


def es_zamanli(p: pd.DataFrame, tum: pd.DataFrame, rapor_ayi: pd.Series) -> Optional[Dict]:
    """Kazan gazı kış ortancasının %30'undan, soğutma kış ortancasının 1,5 katından
    fazla olan günler (eşikler lokasyonun kendi verisinden, tüm geçmişten)."""
    kis = tum[tum["T"] < 10]
    if kis["gaz"].notna().sum() < 20 or kis["sogutma"].notna().sum() < 20:
        return None
    esik_gaz = 0.3 * float(kis["gaz"].median())
    esik_sog = 1.5 * float(kis["sogutma"].median())
    m = (p["gaz"] > esik_gaz) & (p["sogutma"] > esik_sog)
    return {"gun": int(m.sum()), "rapor_ayi_gun": int((m & rapor_ayi.loc[p.index]).sum()),
            "ort_T": float(p.loc[m, "T"].mean()) if m.any() else None,
            "esik_gaz": esik_gaz, "esik_sogutma": esik_sog,
            "ornek_gunler": [str(x.date()) for x in p.loc[m, "tarih"].tail(5)],
            "gunler": [str(x.date()) for x in p.loc[m, "tarih"]]}


def kojen_duzeni(p: pd.DataFrame) -> Optional[Dict]:
    k = p["kojen"]
    if k.notna().sum() == 0:
        return None
    calisiyor = k > 1000
    aylik = calisiyor.groupby(p["tarih"].dt.to_period("M")).mean()
    return {"calisan_oran": float(calisiyor[k.notna()].mean()),
            "aylik": {str(a): round(float(v), 2) for a, v in aylik.items()}}


# ── profil ───────────────────────────────────────────────────────────────
def profil(df: pd.DataFrame, yil: int, ay: int, ay_sayisi: int = PENCERE_AY,
           haric: Optional[List[Dict]] = None, bas: Optional[date] = None,
           son: Optional[date] = None, gun_ici=None, esik_carpani: Optional[Dict[str, float]] = None) -> Dict:
    """Rapor ayıyla biten ay_sayisi aylık pencerede alışkanlık profili + bulgu adayları.
    bas/son verilirse pencere onlardır (doğrulama için).
    gun_ici: (santral özeti, bina özeti) — tasarruf.gun_ici.ozetleri_guncelle() çıktısı (A4).
    esik_carpani: kural → çarpan (A5, tasarruf.ogrenme); tutmayan kuralın eşiği bu lokasyonda yükselir."""
    t, kalite_raporu = hazirla(df, haric=haric)
    ay_bas = pd.Timestamp(yil, ay, 1)
    ay_son = ay_bas + pd.offsets.MonthEnd(0)
    p_bas = pd.Timestamp(bas) if bas else (ay_bas - pd.DateOffset(months=ay_sayisi - 1))
    p_son = pd.Timestamp(son) if son else ay_son
    pencere = (t["tarih"] >= p_bas) & (t["tarih"] <= p_son)
    rapor_ayi = (t["tarih"] >= ay_bas) & (t["tarih"] <= ay_son)

    sonuc = {"donem": f"{yil:04d}-{ay:02d}", "pencere": [str(p_bas.date()), str(p_son.date())],
             "gun": int(pencere.sum()), "bulgular": []}
    if pencere.sum() < 60:
        sonuc["yetersiz"] = "Pencerede 60 günden az veri var; alışkanlık çıkarılamaz."
        return sonuc

    kalite = veri_kalitesi(t, pencere, kalite_raporu)
    sonuc["kalite"] = kalite
    p = t[pencere]

    sonuc["haftalik"] = haftalik_ritim(p)
    sonuc["hafta_sonu_isitma"] = {tip: hava_eslesmeli(p, "gaz", tip, t_ust=ISITMA_T_UST)
                                  for tip in ("cumartesi", "pazar")}
    sonuc["hafta_sonu_toplam"] = {tip: hava_eslesmeli(p, "toplam", tip) for tip in ("cumartesi", "pazar")}
    sonuc["chiller"] = chiller_dis_hava(p)
    sonuc["es_zamanli"] = es_zamanli(p, t, rapor_ayi)
    sonuc["kojen"] = kojen_duzeni(p)
    if gun_ici is not None:
        from tasarruf import gun_ici as GI
        ez = sonuc["es_zamanli"]
        sonuc["gun_ici"] = GI.profil(gun_ici[0], gun_ici[1], bas=max(p_bas, p_son - pd.Timedelta(days=GI.PENCERE_GUN - 1)),
                                     son=p_son, supheli_gunler=ez["gunler"] if ez else None)
    sonuc["esik_carpani"] = dict(esik_carpani or {})
    sonuc["esikler"] = {}
    sonuc["bulgular"] = _bulgular(sonuc, p, t, rapor_ayi, kalite)
    return sonuc


# ── bulgu adayları ───────────────────────────────────────────────────────
def _bulgu(kod, baslik, kanit, oneri, olcutler, kalite, tasarruf=None, durum="aday", not_=None):
    supheli = [o for o in olcutler if not kalite["gecerli"].get(o, False)]
    if supheli and durum == "aday":
        durum = "veri_supheli"
    return {"kod": kod, "baslik": baslik, "kanit": kanit, "oneri": oneri,
            "tasarruf": None if durum == "veri_supheli" else tasarruf,
            "durum": durum, "supheli_olcutler": supheli, "not": not_}


def _bulgular(s: Dict, p: pd.DataFrame, t: pd.DataFrame, rapor_ayi: pd.Series, kalite: Dict) -> List[Dict]:
    b = []

    # 1) Hafta sonu ısıtma: aynı dış sıcaklıkta hafta sonu kazan gazı hafta içinden fazla
    for tip in ("pazar", "cumartesi"):
        h = s["hafta_sonu_isitma"].get(tip)
        tp = s["hafta_sonu_toplam"].get(tip)
        if not h or h["gun"] < 6 or not h["fark_yuzde"]:
            continue
        carpan = s.get("esik_carpani", {}).get("HAFTA_SONU_ISITMA", 1.0)
        if "hafta_sonu" not in s["esikler"]:
            df_ = dogal_fark(p, "gaz", t_ust=ISITMA_T_UST)
            s["esikler"]["hafta_sonu"] = {"taban": HAFTA_SONU_ESIK, "dogal": df_, "carpan": carpan,
                                          "esik": max(HAFTA_SONU_ESIK, df_ or 0) * carpan}
        if h["fark_yuzde"] >= s["esikler"]["hafta_sonu"]["esik"] and h["pozitif_oran"] >= 0.6:
            ad = GUN_TIPLERI[tip]
            aylik = h["fark"] * 52 / 12
            tuk = ""
            if tp and tp.get("fark_yuzde") is not None:
                tuk = f" Aynı günlerde toplam elektrik tüketimi {tr_yuzde(tp['fark_yuzde'])}."
            b.append(_bulgu(
                f"HAFTA_SONU_ISITMA_{tip.upper()}",
                f"{ad} günleri kazan gazı hafta içinden yüksek",
                (f"Son 12 ayda dış hava {ISITMA_T_UST:.0f} °C altındaki {h['gun']} {ad.lower()} gününde kazan "
                 f"gazı, aynı dış sıcaklıktaki (±{tr_sayi(ESLESME_TOL_C, 1)} °C) hafta içi günlerinden fazla "
                 f"(fazla olan gün oranı: %{h['pozitif_oran'] * 100:.0f}); ortalama {tr_sayi(h['fark'])} m³/gün "
                 f"(%{h['fark_yuzde'] * 100:.0f}).{tuk}"
                 + (f" Bu lokasyonda hafta içi günler arası olağan fark %{s['esikler']['hafta_sonu']['dogal'] * 100:.0f}; "
                    f"fark bunu aşıyor." if s["esikler"]["hafta_sonu"]["dogal"] else "")),
                (f"{ad} ısıtma düzenini (poliklinik ve idari katların set/saatleri, kazan sıralaması) "
                 "gözden geçirin. Fark kısmen iç ısı kazancının (insan, cihaz) düşmesinden de olabilir."),
                ["gaz"], kalite,
                tasarruf={"deger": aylik, "birim": "m³/ay", "aciklama": "ısıtma sezonunda, fark tümüyle kapanırsa"}))

    # 2) Chiller seti dış havaya tepki vermiyor
    ch = s["chiller"]
    dolu = [x for x in ch["bantlar"] if x["gun"] >= 10 and x["set"] is not None]
    if len(dolu) >= 2:
        aralik = max(x["set"] for x in dolu) - min(x["set"] for x in dolu)
        serin = [x for x in dolu if x["bant"] in ("<10 °C", "10–18 °C")]
        set_esik = SET_ARALIK_ESIK / s.get("esik_carpani", {}).get("SET_DIS_HAVA", 1.0)
        s["esikler"]["set"] = {"esik": set_esik}
        if aralik < set_esik and serin and max(x["set"] for x in serin) <= 7.5:
            serin_gun = p[(p["T"] < 18) & (p["sogutma"] > 0) & p["set"].notna()]
            ay_sayisi = max(1.0, p["tarih"].dt.to_period("M").nunique())
            aylik_kwh = float(serin_gun["sogutma"].sum()) / ay_sayisi * SET_KATSAYI
            bant_metni = ", ".join(f"{x['bant']}: {tr_sayi(x['set'], 1)} °C" for x in dolu)
            setler = ", ".join(f"{tr_sayi(k, 1)} °C ({v} gün)" for k, v in ch["setler"].items())
            b.append(_bulgu(
                "SET_DIS_HAVA",
                "Chiller seti dış havaya göre değişmiyor",
                (f"Ortalama set dış hava bantlarına göre: {bant_metni}. Bantlar arası fark yalnız "
                 f"{tr_sayi(aralik, 1)} °C. Kullanılan setler: {setler}."),
                ("Dış hava 18 °C altındayken seti 1 °C yükseltmeyi değerlendirin (nem ve ameliyathane "
                 "koşulları izin veriyorsa; oto-set ayarlarıyla birlikte)."),
                ["sogutma", "set", "T"], kalite,
                tasarruf={"deger": aylik_kwh, "birim": "kWh/ay",
                          "aciklama": f"serin günlerde +1 °C; genel katsayı %{tr_sayi(SET_KATSAYI * 100, 1)}/°C"}))

    # 3) Eş zamanlı ısıtma-soğutma (günlük veri yalnız şüphe verir)
    ez = s["es_zamanli"]
    if ez and ez["gun"] >= 10:
        b.append(_bulgu(
            "ES_ZAMANLI_ISITMA_SOGUTMA",
            "Aynı gün hem ısıtma hem soğutma yüksek",
            (f"Son 12 ayda {ez['gun']} gün (rapor ayında {ez['rapor_ayi_gun']}) kazan gazı "
             f"{tr_sayi(ez['esik_gaz'])} m³ ve soğutma {tr_sayi(ez['esik_sogutma'])} kWh üzerinde; "
             f"bu günlerin ortalama dış sıcaklığı {tr_sayi(ez['ort_T'], 1)} °C."),
            ("Ara mevsimde santrallerde ısıtma ve soğutma vanalarının aynı anda açık olup olmadığı "
             "santral (AHU) okumalarıyla doğrulanmalı. Doğrulanmadan tasarruf hesaplanmaz."),
            ["gaz", "sogutma"], kalite, durum="dogrulama_gerekli"))
        sp = (s.get("gun_ici") or {}).get("supheli")
        if sp and sp["veri_var"]:
            es = b[-1]
            cak = [g for g in sp["gunler"] if g["tur"] == "santralde_cakisma"]
            es["kanit"] += (f" Bu günlerden {sp['veri_var']} tanesinin santral okuma verisi var: "
                            f"{len(cak)} gün aynı santralde ısıtma ve soğutma vanası birlikte açık, "
                            f"{sp['yalniz_zon']} gün yalnız farklı santraller ısıtıp soğutuyor.")
            if not cak and sp["veri_var"] >= 5:
                # Yeterli gün içi veri, şüpheyi zonlar arası farka indirdi: kayıp bulgusu değil.
                # Bulgu kalkar; açıklama gün içi satırlarında kalır.
                b.pop()
            elif not cak:
                pass                                  # birkaç gün yetmez, doğrulama gerekli kalır
            else:
                if es["durum"] == "dogrulama_gerekli":
                    es["durum"] = "aday"
                adlar = sorted({a for g in cak for a in g["santraller"]})
                es["oneri"] = ("Çakışma görülen günlerde şu santrallerin vana sıralamasını ve set değerlerini "
                               "kontrol edin: " + ", ".join(adlar[:10])
                               + (f" ve {len(adlar) - 10} santral daha" if len(adlar) > 10 else "") + ".")

    gp = s.get("gun_ici")
    if gp:
        from tasarruf import gun_ici as GI
        b.extend(GI.bulgular(gp, carpan=s.get("esik_carpani", {}).get("VANA_CAKISMASI", 1.0)))

    # 4) Su: rapor ayında gün tipine göre artış
    onceki = p[~rapor_ayi.loc[p.index]]
    bu_ay = p[rapor_ayi.loc[p.index]]
    for tip in ("hafta_ici", "pazar"):
        o = onceki.loc[onceki["gun_tipi"] == tip, "su"]
        y = bu_ay.loc[bu_ay["gun_tipi"] == tip, "su"]
        if o.count() >= 20 and y.count() >= 3 and o.mean() > 0:
            artis = y.mean() / o.mean() - 1
            dogal = su_dogal_artis(onceki, tip)
            su_esik = max(SU_ESIK, 1.5 * (dogal or 0)) * s.get("esik_carpani", {}).get("SU_ARTISI", 1.0)
            s["esikler"].setdefault("su", {})[tip] = {"dogal": dogal, "esik": su_esik}
            if artis > su_esik:
                gun_ay = 22 if tip == "hafta_ici" else 4.3
                b.append(_bulgu(
                    f"SU_ARTISI_{tip.upper()}",
                    f"Su tüketimi {GUN_TIPLERI[tip].lower()} günlerinde arttı",
                    (f"Rapor ayında {GUN_TIPLERI[tip].lower()} ortalaması {tr_sayi(y.mean())} m³/gün; "
                     f"önceki 11 ay {tr_sayi(o.mean())} m³/gün ({tr_yuzde(artis)})."),
                    "Kaçak, soğutma kulesi blöf ayarı ve sulama programını kontrol edin.",
                    ["su"], kalite,
                    tasarruf={"deger": (y.mean() - o.mean()) * gun_ay, "birim": "m³/ay",
                              "aciklama": "artış kapanırsa"}))
                break
    return b


# ── rapor metni (ekran ve PDF aynı metni kullanır) ───────────────────────
DURUM_ETIKET = {"aday": "Öneri", "dogrulama_gerekli": "Doğrulama gerekli", "veri_supheli": "Veri şüpheli"}


def rapor_metni(s: Dict) -> Dict:
    """Profil → ekranda/PDF'te gösterilecek tablo ve satırlar."""
    if s.get("yetersiz"):
        return {"ritim": [], "aliskanliklar": [], "kalite": [s["yetersiz"]], "bulgular": []}
    ritim = []
    for ad, (baslik, birim) in OLCUTLER.items():
        v = s["haftalik"][ad]
        if all(v.get(tip) is None for tip in GUN_TIPLERI):
            continue
        satir = {"Ölçüt": f"{baslik} ({birim}/gün)"}
        for tip, etiket in GUN_TIPLERI.items():
            satir[etiket] = tr_sayi(v.get(tip))
        ritim.append(satir)

    al = []
    for tip in ("pazar", "cumartesi"):
        h = s["hafta_sonu_isitma"].get(tip)
        if h and h.get("fark_yuzde") is not None:
            tutarli = h["pozitif_oran"] >= 0.6
            al.append(f"{GUN_TIPLERI[tip]} ısıtması (aynı dış sıcaklıktaki hafta içine göre, {h['gun']} gün): "
                      f"kazan gazı ortalama {tr_yuzde(h['fark_yuzde'])}, fazla olan gün oranı %{h['pozitif_oran'] * 100:.0f}"
                      + (" — tutarlı bir alışkanlık." if tutarli else " — tutarlı değil, birkaç gün ortalamayı etkiliyor."))
    for tip in ("pazar", "cumartesi"):
        h = s["hafta_sonu_toplam"].get(tip)
        if h and h.get("fark_yuzde") is not None:
            al.append(f"{GUN_TIPLERI[tip]} elektrik tüketimi aynı dış sıcaklıktaki hafta içine göre {tr_yuzde(h['fark_yuzde'])}.")
    ch = s["chiller"]
    dolu = [x for x in ch["bantlar"] if x["gun"] >= 5 and x["set"] is not None]
    if dolu:
        al.append("Chiller seti / adedi dış havaya göre: " + "; ".join(
            f"{x['bant']}: {tr_sayi(x['set'], 1)} °C, {tr_sayi(x['chiller_adet'], 1)} chiller ({x['gun']} gün)"
            for x in dolu) + ".")
    ez = s.get("es_zamanli")
    if ez:
        al.append(f"Aynı gün ısıtma ve soğutma yüksek: {ez['gun']} gün (rapor ayında {ez['rapor_ayi_gun']}).")
    gun_ici_satirlar = []
    if s.get("gun_ici") is not None:
        from tasarruf import gun_ici as GI
        gun_ici_satirlar = GI.metin_satirlari(s["gun_ici"])
    kj = s.get("kojen")
    if kj:
        al.append(f"Kojenin çalıştığı gün oranı: %{kj['calisan_oran'] * 100:.0f}.")

    k = s["kalite"]
    kalite = []
    for ad, ok in k["gecerli"].items():
        if not ok:
            ad_metin = OLCUTLER.get(ad, (ad,))[0] if ad in OLCUTLER else {"set": "Chiller seti", "T": "Dış hava"}.get(ad, ad)
            kalite.append(f"{ad_metin}: pencerede dolu gün oranı yalnız %{k['kapsam'][ad] * 100:.0f} — bu ölçütten bulgu üretilmedi.")
    for sr in k["sorunlar"]:
        kalite.append(f"[{sr['tur']}] {tr_tarih(sr['bas'])} – {tr_tarih(sr['son'])} ({sr['gun']} gün): {sr['aciklama']}")
    for kr in k["kirilmalar"]:
        kalite.append(f"[KIRILMA {kr['onceki_yil']}→{kr['yil']}] {kr['aciklama']}")

    bulgular = []
    for b in s["bulgular"]:
        ts = b.get("tasarruf")
        bulgular.append({
            "durum": DURUM_ETIKET.get(b["durum"], b["durum"]), "kod": b["kod"], "baslik": b["baslik"],
            "kanit": b["kanit"], "oneri": b["oneri"],
            "tasarruf": (f"~{tr_sayi(ts['deger'])} {ts['birim']} ({ts['aciklama']})" if ts else
                         ("Veri kalitesi nedeniyle hesaplanmadı" if b["durum"] == "veri_supheli" else None)),
        })
    return {"ritim": ritim, "aliskanliklar": al, "gun_ici": gun_ici_satirlar, "kalite": kalite, "bulgular": bulgular,
            "pencere": [tr_tarih(x) for x in s["pencere"]], "gun": s["gun"]}
