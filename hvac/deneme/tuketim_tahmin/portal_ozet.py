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
from gunluk_model import GunlukTahminModeli, birlestir, KOLONLAR
from sinama import olcutler

warnings.filterwarnings("ignore", module="sklearn")

AYARLAR = os.path.join(os.path.dirname(_BURASI), "configs", "tuketim_tahmin.json")
HEDEF_ADI = {"toplam": "Toplam tüketim", "sogutma": "Soğutma (chiller)", "isitma_gaz": "Isıtma gazı (kazan)"}
HEDEF_BIRIM = {"toplam": "kWh", "sogutma": "kWh", "isitma_gaz": "m³"}
AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
         "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
EN_AZ_EGITIM_GUN = 365     # bir yıldan az geçmişle mevsim öğrenilemez


def haric_donemler() -> List[Dict]:
    try:
        with open(AYARLAR, encoding="utf-8") as f:
            return json.load(f).get("haric") or []
    except Exception:
        return []


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
        tam = len(gunler) == ay_gun and len(gecerli) >= ay_gun - 1
        gercek = float(gecerli[hedef].sum() / len(gecerli) * ay_gun) if tam else (
            float(gunler[hedef].sum()) if gunler[hedef].notna().any() else None)
        notu = ""
        if any(pd.Timestamp(h["bas"]) <= bas + pd.Timedelta(days=ay_gun - 1) and pd.Timestamp(h["son"]) >= bas
               for h in haric):
            notu = "hariç tutuldu"
        elif len(gunler) and gunler[hedef].notna().sum() == 0:
            notu = "veri yok"
        elif len(gunler) and not tam:
            notu = ("%d gün" % gunler[hedef].notna().sum()) if len(gunler) < ay_gun else "veri sorunlu, ölçüme girmedi"
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
