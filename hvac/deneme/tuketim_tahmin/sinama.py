# -*- coding: utf-8 -*-
"""
DÜRÜST SINAMA — modelin hiç görmediği ayları ne kadar tuttuğu
============================================================

Portaldaki "Sapma" sütunu modelin EĞİTİMDE GÖRDÜĞÜ aylarla kıyaslanır; o sayı
başarı ölçüsü değildir. Burada her hedef ay için model yalnızca O AYDAN ÖNCEKİ
veriyle eğitilir ve o ay tahmin edilir (ileriye dönük / walk-forward).

Hedef ay olarak yalnız VERİSİ TEMİZ aylar alınır (veri_kalite.kontrol):
hariç tutulan, kojeni kayıp, sıfır/çift günlü aylar ölçüme girmez — bozuk
"gerçek" değerle kıyaslamak modeli haksız yere iyi ya da kötü gösterir.

Ölçütler (ASHRAE Guideline 14, aylık kalibre model):
    NMBE (net sapma) ±%5 içinde,  CV(RMSE) ≤ %15.   MAPE ve en kötü ay da verilir.

Kullanım:
    python sinama.py gunluk.csv --lokasyon maslak
    python sinama.py gunluk.csv --lokasyon maslak --hava hava.csv --operasyon operasyon.csv --ay 18
"""
from __future__ import annotations

import argparse
import calendar
import warnings
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

import veri_kalite
from gunluk_model import GunlukTahminModeli, birlestir
from tahmin_motoru import TuketimTahminModeli

warnings.filterwarnings("ignore")


def olcutler(gercek, tahmin) -> Dict[str, float]:
    g, t = np.asarray(gercek, float), np.asarray(tahmin, float)
    e = g - t
    nmbe = e.sum() / g.sum() * 100
    cv = np.sqrt(np.mean(e ** 2)) / g.mean() * 100
    return {"n": int(len(g)), "MAPE": float(np.mean(np.abs(e) / g) * 100), "NMBE": float(nmbe),
            "CVRMSE": float(cv), "en_kotu": float(np.max(np.abs(e) / g) * 100),
            "ashrae_g14": bool(abs(nmbe) <= 5 and cv <= 15)}


def temiz_aylar(g: pd.DataFrame) -> pd.DataFrame:
    """Hedef olabilecek aylar: ayın en az (gün−1)'i geçerli."""
    a = g.assign(yil=g["tarih"].dt.year, ay=g["tarih"].dt.month).groupby(["yil", "ay"]).agg(
        gecerli=("hedef_gecerli", "sum"), toplam=("toplam", "sum"), gun=("tarih", "count")).reset_index()
    a["ay_gun"] = [calendar.monthrange(int(y), int(m))[1] for y, m in zip(a.yil, a.ay)]
    return a[(a.gecerli >= a.ay_gun - 1) & (a.gun == a.ay_gun)]


def ileriye_donuk_sinama(gunluk: pd.DataFrame, son_ay: int = 15, lokasyon: Optional[str] = None,
                         hava: Optional[pd.DataFrame] = None, operasyon: Optional[pd.DataFrame] = None,
                         kolonlar: Optional[Dict] = None) -> Dict:
    ayar = veri_kalite.lokasyon_ayari(lokasyon) if lokasyon else {}
    g, rapor = birlestir(gunluk, hava, operasyon, kolonlar, haric=ayar.get("haric"))
    hedefler = temiz_aylar(g).sort_values(["yil", "ay"]).tail(son_ay)
    ham = gunluk.copy()

    satir: List[Dict] = []
    for h in hedefler.itertuples(index=False):
        y, a = int(h.yil), int(h.ay)
        bas = pd.Timestamp(y, a, 1)
        # Mevcut portal modeli (ham veriyle, portalda olduğu gibi)
        eski = TuketimTahminModeli(kolonlar=kolonlar)
        ham_once = ham[pd.to_datetime(ham[eski.k["tarih"]]) < bas]
        if not eski.egit(ham_once).get("basarili"):
            continue
        eski_t = eski.tahmin_gecmisten(ham_once, y, a)["toplam_kwh"]
        # Yeni günlük model (temiz veriyle)
        m = GunlukTahminModeli()
        m.egit(g, bitis=bas)
        t = m.ay_tahmini(y, a)
        # Basit kural: geçen yılın aynı ayı (geçerli günlerden, gün sayısına ölçekli)
        gy = g[(g.tarih.dt.year == y - 1) & (g.tarih.dt.month == a) & g.hedef_gecerli]
        if len(gy) < 20 or t["tuketim_gecen_yil_duzeltmeli"] is None:
            continue
        gercek_gun = g[(g.tarih >= bas) & (g.tarih.dt.month == a) & (g.tarih.dt.year == y)]
        # Kojen planı biliniyormuş gibi (ayın gerçek çalışma günü) — şebeke dengesinin asıl ölçüsü
        kj_gun = float((gercek_gun.kojen > 1000).sum()) if gercek_gun.kojen.notna().any() else 0.0
        t_plan = m.ay_tahmini(y, a, kojen_calisma_gun=kj_gun)
        satir.append({"yil": y, "ay": a, "gercek": float(h.toplam), "portal_ml": eski_t,
                      "sebeke_tahmin_plan": t_plan["sebeke"], "kojen_tahmin_plan": t_plan["kojen"],
                      "gecen_yil": gy.toplam.sum() / len(gy) * h.ay_gun,
                      "gunluk_model": t["tuketim_gunluk_model"],
                      "gecen_yil_duzeltmeli": t["tuketim_gecen_yil_duzeltmeli"],
                      "birlesik": t["tuketim"],
                      "kojen_gercek": gercek_gun.kojen.sum(min_count=1), "kojen_tahmin": t["kojen"],
                      "sebeke_gercek": gercek_gun.sebeke.sum(min_count=1), "sebeke_tahmin": t["sebeke"],
                      "ozellikler": ",".join(m.secilen) or "-"})
    tab = pd.DataFrame(satir)
    yontemler = ["portal_ml", "gecen_yil", "gunluk_model", "gecen_yil_duzeltmeli", "birlesik"]
    sonuc = {"aylar": tab, "kalite": rapor, "olcut": {y: olcutler(tab.gercek, tab[y]) for y in yontemler}}
    v = tab[tab["sebeke_gercek"].notna() & (tab["sebeke_gercek"] > 0)]
    if len(v) >= 3:
        sonuc["olcut"]["sebeke"] = olcutler(v["sebeke_gercek"], v["sebeke_tahmin"])
        sonuc["olcut"]["sebeke_plan"] = olcutler(v["sebeke_gercek"], v["sebeke_tahmin_plan"])
        # Kojen kWh planı kusursuz bilinseydi: şebeke = birleşik tüketim − kojen (GES yok)
        sonuc["olcut"]["sebeke_plan_kwh"] = olcutler(
            v["sebeke_gercek"], (v["birlesik"] - v["kojen_gercek"].fillna(0)).clip(lower=0))
    v = tab[tab["kojen_gercek"].notna() & (tab["kojen_gercek"] > 0)]
    if len(v) >= 3:
        sonuc["olcut"]["kojen_plan"] = olcutler(v["kojen_gercek"], v["kojen_tahmin_plan"])
    return sonuc


ADLAR = {"portal_ml": "Portaldaki ML (aylık GBM, ham veri)",
         "gecen_yil": "Basit: geçen yılın aynı ayı",
         "gunluk_model": "Günlük model (derece-gün + takvim)",
         "gecen_yil_duzeltmeli": "Geçen yıl, hava + seviye düzeltmeli",
         "birlesik": "BİRLEŞİK (önerilen)",
         "sebeke": "  └ şebeke, kojen planı YOKKEN",
         "sebeke_plan": "  └ şebeke, kojen çalışma günü verilince",
         "sebeke_plan_kwh": "  └ şebeke, kojen kWh planı verilince",
         "kojen_plan": "  └ kojen, çalışma günü verilince"}


def yazdir(s: Dict) -> None:
    print("VERİ KALİTESİ:\n" + s["kalite"].ozet() + "\n")
    print("İleriye dönük sınama — her ay yalnız ÖNCEKİ veriyle eğitildi, %d temiz ay:" % len(s["aylar"]))
    for ad, o in s["olcut"].items():
        print("  %-40s MAPE %5.1f%%  NMBE %+5.1f%%  CV(RMSE) %5.1f%%  en kötü %5.1f%%  G14: %s"
              % (ADLAR[ad], o["MAPE"], o["NMBE"], o["CVRMSE"], o["en_kotu"], "GEÇER" if o["ashrae_g14"] else "KALIR"))
    print("\nAy ay hata  (gerçek − tahmin) / tahmin:")
    for r in s["aylar"].itertuples(index=False):
        f = lambda t: (r.gercek - t) / t * 100
        print("  %d-%02d  gerçek %10.0f | portal ML %+6.1f%% | geçen yıl %+6.1f%% | birleşik %+6.1f%%"
              % (r.yil, r.ay, r.gercek, f(r.portal_ml), f(r.gecen_yil), f(r.birlesik)))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("csv")
    p.add_argument("--lokasyon")
    p.add_argument("--hava")
    p.add_argument("--operasyon")
    p.add_argument("--ay", type=int, default=15)
    a = p.parse_args()
    oku = lambda yol: pd.read_csv(yol) if yol else None
    yazdir(ileriye_donuk_sinama(pd.read_csv(a.csv), a.ay, a.lokasyon, oku(a.hava), oku(a.operasyon)))
