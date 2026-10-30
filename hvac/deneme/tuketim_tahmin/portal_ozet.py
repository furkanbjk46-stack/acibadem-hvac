# -*- coding: utf-8 -*-
"""Enerji portalı ↔ günlük tahmin modeli köprüsü.

Portalın eski "Sapma" sütunu modelin EĞİTİMDE GÖRDÜĞÜ aylarla kıyaslanıyordu;
o sayı başarı ölçüsü değildi. Burada geçmiş her ay için model YALNIZ O AYDAN
ÖNCEKİ veriyle eğitilir (ileriye dönük) — gösterilen sapma, modelin o ayı
önceden ne kadar tutturacağıdır. Gelecek aylar tüm veriyle eğitilen modelden.

Sapma işareti portalla aynı: (gerçek − tahmin) / tahmin.
"""
from __future__ import annotations

import calendar
import json
import os
import warnings
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

from . import _BURASI  # noqa: F401 — sys.path ayarı
from gunluk_model import GunlukTahminModeli, KOLONLAR, ENERJI_HAVA_SUTUNLARI
from gunluk_model import birlestir as _birlestir
from sinama import olcutler

warnings.filterwarnings("ignore", module="sklearn")

AYARLAR = os.path.join(os.path.dirname(_BURASI), "configs", "tuketim_tahmin.json")
HEDEF_ADI = {"toplam": "Toplam tüketim", "sogutma": "Soğutma (chiller)", "isitma_gaz": "Isıtma gazı (kazan)"}
HEDEF_BIRIM = {"toplam": "kWh", "sogutma": "kWh", "isitma_gaz": "m³"}
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
         "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
EN_AZ_EGITIM_GUN = 365     # bir yıldan az geçmişle mevsim öğrenilemez
OLCUM_ORANI = 0.8          # bitmiş ay, günlerinin en az %80'i geçerliyse sapma ölçümüne girer


def haric_donemler() -> List[Dict]:
    try:
        with open(AYARLAR, encoding="utf-8") as f:
            return json.load(f).get("haric") or []
    except Exception:
        return []


try:
    from enerji_hesap import YENI_KURAL_BASLANGIC
except Exception:                                   # paket başka programda tek başına
    YENI_KURAL_BASLANGIC = "2026-06-01"


def birlestir(df: pd.DataFrame, haric: Optional[List[Dict]] = None):
    """gunluk_model.birlestir + Şebeke kuralı.

    01.06.2026'dan beri Hastane Genel = Şebeke (ELLE girilir) + Kojen. Şebeke
    henüz girilmemiş günde Toplam yalnız kojendir (Haziran 2026 ort. 2.145 kWh/gün)
    — gerçek tüketim değil. Bu günlerin TOPLAM'ı boş sayılır: modele girmez,
    "gerçekleşen" olarak da gösterilmez. Soğutma (chiller sayaçları) etkilenmez.
    """
    g, rapor = _birlestir(df, haric=haric)
    eksik = (g["tarih"] >= pd.Timestamp(YENI_KURAL_BASLANGIC)) & g["sebeke"].isna() & g["toplam"].notna()
    g["sebeke_eksik"] = eksik.values
    if eksik.any():
        g.loc[eksik, "toplam"] = np.nan
        rapor.ekle("ŞEBEKE YOK", g.loc[eksik, "tarih"].min().date(), g.loc[eksik, "tarih"].max().date(),
                   int(eksik.sum()), "Şebeke elle girilmemiş — toplam tüketim bilinmiyor, modele girmedi")
    return g, rapor


def _kojen_gun(gunler: pd.DataFrame) -> Optional[float]:
    return float((gunler["kojen"] > 1000).sum()) if gunler["kojen"].notna().any() else None


def yil_ozeti(df: pd.DataFrame, yil: int, hedef: str = "toplam",
              haric: Optional[List[Dict]] = None) -> Dict:
    """Seçilen yılın 12 ayı: tahmin, gerçekleşen, sapma + ölçütler."""
    if hedef not in HEDEF_ADI:
        raise ValueError(hedef)
    if df is None or df.empty or KOLONLAR["toplam"] not in df.columns:
        return {"hata": "Tüketim verisi yok."}
    haric = haric if haric is not None else haric_donemler()
    g, rapor = birlestir(df, haric=haric)
    if g[hedef].notna().sum() == 0:
        return {"hata": "%s verisi yok." % HEDEF_ADI[hedef]}
    son_tarih = g["tarih"].max()
    ilk_tarih = g.loc[g[hedef].notna(), "tarih"].min()

    modeller: Dict[pd.Timestamp, GunlukTahminModeli] = {}

    def model(bitis: pd.Timestamp) -> GunlukTahminModeli:
        if bitis not in modeller:
            m = GunlukTahminModeli(hedef=hedef)
            m.egit(g, bitis=bitis)
            modeller[bitis] = m
        return modeller[bitis]

    aylar = []
    for ay in range(1, 13):
        bas = pd.Timestamp(yil, ay, 1)
        ay_gun = calendar.monthrange(yil, ay)[1]
        if (bas - ilk_tarih).days < EN_AZ_EGITIM_GUN:
            aylar.append({"ay": ay, "ad": AYLAR[ay - 1], "tahmin": None, "gercek": None,
                          "gercek_gun": 0, "tam": False, "sapma": None, "not": "yetersiz geçmiş"})
            continue
        gunler = g[(g["tarih"] >= bas) & (g["tarih"] < bas + pd.Timedelta(days=ay_gun))]
        gecerli = gunler[gunler["hedef_gecerli"] & gunler[hedef].notna()]
        # Geçmiş ay: o aya kadarki veriyle; gelecek/ içinde bulunulan ay: tüm veriyle
        bitis = min(bas, son_tarih + pd.Timedelta(days=1))
        m = model(bitis)
        # Isıtma gazında kojen planı girdidir; geçmiş ayda plan = gerçekleşen
        # çalışma günü (işletme bunu ay başında bilir). Toplamda tüketimi değiştirmez.
        kj = _kojen_gun(gunler) if len(gunler) == ay_gun else None
        t = m.ay_tahmini(yil, ay, kojen_calisma_gun=kj)
        # 30.10.2026: ayın en az %80'i geçerliyse ölçülür (eskiden gün−1). Tek tük bozuk gün
        # (kalite kontrolü ayıklar) ayı ölçümden düşürmesin; gerçekleşen = geçerli günlerin
        # ortalaması × ay günü.
        ay_bitti = len(gunler) == ay_gun
        tam = ay_bitti and len(gecerli) >= OLCUM_ORANI * ay_gun
        sb_eksik = int(gunler["sebeke_eksik"].sum()) if hedef == "toplam" and "sebeke_eksik" in gunler else 0
        if tam:
            gercek = float(gecerli[hedef].sum() / len(gecerli) * ay_gun)
        elif not ay_bitti and gunler[hedef].notna().any() and not sb_eksik:
            gercek = float(gunler[hedef].sum())              # içinde bulunulan ay: şimdiye kadarki
        else:
            gercek = None                                    # bitmiş ama ölçülemeyen ay: kısmi toplam yanıltır
        notu = ""
        if any(pd.Timestamp(h["bas"]) <= bas + pd.Timedelta(days=ay_gun - 1) and pd.Timestamp(h["son"]) >= bas
               for h in haric):
            notu = "hariç tutuldu"
        elif sb_eksik and not tam:
            notu = "Şebeke girilmemiş: %d gün" % sb_eksik
        elif len(gunler) and gunler[hedef].notna().sum() == 0:
            notu = "veri yok"
        elif len(gunler) and not ay_bitti:
            notu = "%d gün" % gunler[hedef].notna().sum()
        elif ay_bitti and not tam:
            notu = "yalnız %d/%d gün geçerli" % (len(gecerli), ay_gun)
        elif tam and len(gecerli) < ay_gun:
            notu = "%d/%d gün" % (len(gecerli), ay_gun)
        aylar.append({
            "ay": ay, "ad": AYLAR[ay - 1], "tahmin": float(t["tuketim"]), "gercek": gercek,
            "gercek_gun": int(gunler[hedef].notna().sum()), "tam": tam,
            "sapma": (gercek - t["tuketim"]) / t["tuketim"] * 100 if tam and t["tuketim"] > 0 else None,
            "ileriye_donuk": bitis == bas, "not": notu,
            "sebeke": float(t["sebeke"]), "kojen": float(t["kojen"]), "kojen_kaynak": t["kojen_kaynak"],
        })

    olculen = [a for a in aylar if a["sapma"] is not None]
    olcut = (olcutler([a["gercek"] for a in olculen], [a["tahmin"] for a in olculen])
             if len(olculen) >= 3 else None)
    son = modeller[max(modeller)] if modeller else None
    return {"hata": None, "hedef": hedef, "birim": HEDEF_BIRIM[hedef], "aylar": aylar, "olcut": olcut,
            "ozellikler": (["derece-gün", "hafta sonu", "tatil", "mevsim"] + list(son.secilen)) if son else [],
            "kalite": rapor.bulgular, "son_veri": str(son_tarih.date())}


def gelecek_ay(df: pd.DataFrame, yil: int, ay: int, kojen_calisma_gun: Optional[float] = None,
               haric: Optional[List[Dict]] = None) -> Dict:
    """Toplam tüketim + kaynak dağılımı (kojen planı verilirse şebeke ona göre)."""
    g, _ = birlestir(df, haric=haric if haric is not None else haric_donemler())
    m = GunlukTahminModeli(hedef="toplam")
    m.egit(g)
    return m.ay_tahmini(yil, ay, kojen_calisma_gun=kojen_calisma_gun)


# ── Kısa vade: yarın / 7 gün / 30 gün ──────────────────────────────────────
UFUKLAR = (("yarin", "Yarın", 1), ("hafta", "7 gün", 7), ("ay", "30 gün", 30))
# hava_durumu.ileri_tahmin() sütun adları → modelin hava adları
_HAVA_ADLARI = {dis: ic for ic, dis in ENERJI_HAVA_SUTUNLARI.items()}


def hava_tablosu(hava_tahmin: Optional[Dict[str, dict]]) -> Optional[pd.DataFrame]:
    """{'YYYY-AA-GG': {Hava_...: değer}} → gunluk_tahmin'in beklediği tablo."""
    if not hava_tahmin:
        return None
    satirlar = []
    for t, v in sorted(hava_tahmin.items()):
        s = {"Tarih": t}
        for dis, ic in _HAVA_ADLARI.items():
            if v.get(dis) is not None and v.get(dis) != "":
                s[ic] = v[dis]
        satirlar.append(s)
    return pd.DataFrame(satirlar)


def ufuk_tahmini(df: pd.DataFrame, hedef: str = "toplam", gun: int = 30,
                 hava_tahmin: Optional[Dict[str, dict]] = None, bugun=None,
                 haric: Optional[List[Dict]] = None) -> Dict:
    """Yarından itibaren `gun` günün günlük tahmini.

    hava_tahmin: hava_durumu.ileri_tahmin() çıktısı (16 güne kadar). Verilen
    günlerde gerçek hava tahmini kullanılır; kalan günlerde model o takvim
    gününün geçmiş ortalama sıcaklığına (klimatoloji) düşer — her satırda
    "hava" alanı hangisinin kullanıldığını söyler.
    """
    if hedef not in HEDEF_ADI:
        raise ValueError(hedef)
    if df is None or df.empty or KOLONLAR["toplam"] not in df.columns:
        return {"hata": "Tüketim verisi yok."}
    g, _ = birlestir(df, haric=haric if haric is not None else haric_donemler())
    if g[hedef].notna().sum() == 0:
        return {"hata": "%s verisi yok." % HEDEF_ADI[hedef]}
    if (g["tarih"].max() - g.loc[g[hedef].notna(), "tarih"].min()).days < EN_AZ_EGITIM_GUN:
        return {"hata": "Bir yıldan az geçmiş var; mevsim öğrenilemez."}
    m = GunlukTahminModeli(hedef=hedef)
    m.egit(g)
    bugun = pd.Timestamp(bugun or pd.Timestamp.today()).normalize()
    bas = bugun + pd.Timedelta(days=1)
    son = bas + pd.Timedelta(days=gun - 1)
    sonuc = m.gunluk_tahmin(bas, son, hava=hava_tablosu(hava_tahmin))
    tahminli = set((hava_tahmin or {}).keys())
    gunler = [{"tarih": t.strftime("%Y-%m-%d"), "tahmin": float(v), "sicaklik": float(s),
               "hava": "tahmin" if t.strftime("%Y-%m-%d") in tahminli else "ortalama"}
              for t, v, s in zip(sonuc["tarih"], sonuc["tuketim"], sonuc["T"])]
    toplamlar = {k: float(sum(x["tahmin"] for x in gunler[:n])) for k, _, n in UFUKLAR if n <= gun}
    return {"hata": None, "hedef": hedef, "birim": HEDEF_BIRIM[hedef], "gunler": gunler,
            "toplamlar": toplamlar, "hava_tahmin_gun": sum(1 for x in gunler if x["hava"] == "tahmin"),
            "son_veri": str(g["tarih"].max().date())}


# ── Gerçekleşen veriden özetler (model değil) ──────────────────────────────
def _toplam(d: pd.DataFrame, sutun: str) -> float:
    return float(pd.to_numeric(d[sutun], errors="coerce").fillna(0).sum()) if sutun in d.columns else 0.0


def yillik_ozet(df: pd.DataFrame, alan: float = 0) -> List[Dict]:
    """Yıl yıl gerçekleşen toplam / şebeke / chiller (180 günden az yıllar atlanır, son yıl hariç)."""
    if df is None or df.empty or "Tarih" not in df.columns:
        return []
    t = pd.to_datetime(df["Tarih"], errors="coerce")
    d = df.assign(_yil=t.dt.year).dropna(subset=["_yil"])
    # Şebeke girilmemiş yeni kural günü: toplam bilinmiyor (bkz. birlestir) → toplamdan çıkar
    sb = (pd.to_numeric(d[KOLONLAR["sebeke"]], errors="coerce") if KOLONLAR["sebeke"] in d.columns
          else pd.Series(np.nan, index=d.index))
    d["_eksik"] = (t.loc[d.index] >= pd.Timestamp(YENI_KURAL_BASLANGIC)) & sb.isna()
    sonuc = []
    a = alan if alan and alan > 0 else 1
    for yil in sorted(d["_yil"].unique()):
        yd = d[d["_yil"] == yil]
        if len(yd) < 180 and yil != d["_yil"].max():
            continue
        toplam = _toplam(yd[~yd["_eksik"]], KOLONLAR["toplam"])
        sonuc.append({"year": int(yil), "days": int(len(yd)), "total_kwh": toplam,
                      "grid_kwh": _toplam(yd, KOLONLAR["sebeke"]),
                      "chiller_kwh": _toplam(yd, KOLONLAR["sogutma"]),
                      "kwh_per_m2": toplam / a, "sebeke_eksik_gun": int(yd["_eksik"].sum())})
    return sonuc


def tasarruf(df: pd.DataFrame, yil: int) -> Dict:
    """Tam yılı (300+ gün) bir önceki tam yılla kıyaslar; kısmi yılda boş döner."""
    oz = yillik_ozet(df)
    tam = [o for o in oz if o["days"] >= 300]
    yillar = [o["year"] for o in tam]
    if yil not in yillar or yillar.index(yil) == 0:
        return {}
    bu, once = tam[yillar.index(yil)], tam[yillar.index(yil) - 1]
    pt, ct, pg, cg = once["total_kwh"], bu["total_kwh"], once["grid_kwh"], bu["grid_kwh"]
    return {"year": yil, "prev_year": once["year"], "expected_total": pt, "curr_total": ct,
            "savings_total_kwh": pt - ct, "savings_total_pct": (pt - ct) / pt * 100 if pt > 0 else 0,
            "expected_grid": pg, "curr_grid": cg,
            "savings_grid_kwh": pg - cg, "savings_grid_pct": (pg - cg) / pg * 100 if pg > 0 else 0}


def rapor_verisi(df: pd.DataFrame, yil: int, alan: float = 0,
                 haric: Optional[List[Dict]] = None) -> Dict:
    """Aylık Birleşik Rapor ekranı ve PDF için tahmin paketi — yalnız günlük model."""
    oz = yil_ozeti(df, yil, "toplam", haric=haric)
    aylik = []
    for a in ([] if oz.get("hata") else oz["aylar"]):
        if a["tahmin"] is None:
            continue
        aylik.append({"month": a["ay"], "month_name": a["ad"], "forecast_total": a["tahmin"],
                      "actual_total": a["gercek"], "actual_days": a["gercek_gun"],
                      "is_partial": bool(a["gercek"] is not None and not a["tam"]),
                      "deviation_total_pct": a["sapma"]})
    return {"yearly_summary": yillik_ozet(df, alan), "monthly_forecast": aylik,
            "savings": tasarruf(df, yil), "building_area": alan or 0,
            "olcut": None if oz.get("hata") else oz.get("olcut"),
            "yontem_notu": ("Tahmin: günlük model (hava + takvim + kojen). Geçmiş her ay yalnız o aydan "
                            "önceki veriyle tahmin edilir; sapma = (gerçek − tahmin) / tahmin.")}
