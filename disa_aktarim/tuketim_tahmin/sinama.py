# -*- coding: utf-8 -*-
"""
DÜRÜST SINAMA — modelin hiç görmediği ayları ne kadar tuttuğu
============================================================

Ekrandaki "Sapma" sütunu modelin EĞİTİMDE GÖRDÜĞÜ aylarla kıyaslanır; o sayı
başarı ölçüsü değildir. Burada her hedef ay için model yalnızca O AYDAN ÖNCEKİ
veriyle eğitilir ve o ay tahmin edilir (ileriye dönük / walk-forward). Aynı
aylar için iki basit yöntem de hesaplanır; ML ancak bunları geçerse değer katar.

Ölçütler (ASHRAE Guideline 14, aylık kalibre model):
    NMBE      (net sapma, yön dahil)        ±%5 içinde
    CV(RMSE)  (dağılım)                       ≤ %15
MAPE ve en kötü ay da raporlanır.

Kullanım:
    python sinama.py gunluk_veri.csv            # son 15 tam ay
    python sinama.py gunluk_veri.csv --ay 24
"""
from __future__ import annotations

import argparse
import calendar
from typing import Dict, List

import numpy as np
import pandas as pd

from tahmin_motoru import TuketimTahminModeli


def olcutler(gercek: List[float], tahmin: List[float]) -> Dict[str, float]:
    g, t = np.asarray(gercek, float), np.asarray(tahmin, float)
    e = g - t
    return {
        "n": int(len(g)),
        "MAPE": float(np.mean(np.abs(e) / g) * 100),
        "NMBE": float(e.sum() / g.sum() * 100),
        "CVRMSE": float(np.sqrt(np.mean(e ** 2)) / g.mean() * 100),
        "en_kotu": float(np.max(np.abs(e) / g) * 100),
        "ashrae_g14": bool(abs(e.sum() / g.sum() * 100) <= 5 and np.sqrt(np.mean(e ** 2)) / g.mean() * 100 <= 15),
    }


def ileriye_donuk_sinama(gunluk: pd.DataFrame, son_ay: int = 15, kolonlar=None) -> Dict:
    m0 = TuketimTahminModeli(kolonlar=kolonlar)
    k = m0.k
    gunluk = gunluk.copy()
    gunluk[k["tarih"]] = pd.to_datetime(gunluk[k["tarih"]])
    gunluk = gunluk.sort_values(k["tarih"]).drop_duplicates(k["tarih"])
    aylik = m0.aylik_ozet(gunluk)
    tam = aylik[aylik.apply(lambda r: r.gun_sayisi >= calendar.monthrange(int(r.yil), int(r.ay))[1] - 3, axis=1)]
    hedefler = tam.sort_values(["yil", "ay"]).tail(son_ay)

    satirlar = []
    for h in hedefler.itertuples(index=False):
        y, a = int(h.yil), int(h.ay)
        gecmis = gunluk[gunluk[k["tarih"]] < pd.Timestamp(y, a, 1)]
        m = TuketimTahminModeli(kolonlar=kolonlar)
        if not m.egit(gecmis).get("basarili"):
            continue
        ml = m.tahmin_gecmisten(gecmis, y, a)["toplam_kwh"]
        gy = aylik[(aylik.yil == y - 1) & (aylik.ay == a)]
        if gy.empty:
            continue
        ay_gun = calendar.monthrange(y, a)[1]
        gecen_yil = float(gy.toplam.iloc[0]) / int(gy.gun_sayisi.iloc[0]) * ay_gun
        # Son 3 ayın, geçen yılın aynı aylarına göre günlük ortalama değişimi
        oran = []
        for s in aylik[(aylik.yil * 12 + aylik.ay < y * 12 + a) &
                       (aylik.yil * 12 + aylik.ay >= y * 12 + a - 3)].itertuples(index=False):
            q = aylik[(aylik.yil == s.yil - 1) & (aylik.ay == s.ay)]
            if not q.empty and q.toplam.iloc[0] > 0:
                oran.append((s.toplam / s.gun_sayisi) / (q.toplam.iloc[0] / q.gun_sayisi.iloc[0]))
        satirlar.append({"yil": y, "ay": a, "gercek": float(h.toplam), "ml": ml,
                         "gecen_yil": gecen_yil, "gecen_yil_trend": gecen_yil * (np.mean(oran) if oran else 1.0)})

    t = pd.DataFrame(satirlar)
    return {
        "aylar": t,
        "ml": olcutler(t.gercek, t.ml),
        "gecen_yil": olcutler(t.gercek, t.gecen_yil),
        "gecen_yil_trend": olcutler(t.gercek, t.gecen_yil_trend),
    }


def _yaz(ad: str, o: Dict) -> None:
    print("  %-34s n=%2d  MAPE %5.1f%%  NMBE %+5.1f%%  CV(RMSE) %5.1f%%  en kötü %5.1f%%  ASHRAE G14: %s"
          % (ad, o["n"], o["MAPE"], o["NMBE"], o["CVRMSE"], o["en_kotu"], "GEÇER" if o["ashrae_g14"] else "KALIR"))


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("csv")
    p.add_argument("--ay", type=int, default=15)
    a = p.parse_args()
    s = ileriye_donuk_sinama(pd.read_csv(a.csv), a.ay)
    print("İleriye dönük sınama (her ay yalnız ÖNCEKİ veriyle eğitildi):")
    _yaz("ML (GradientBoosting)", s["ml"])
    _yaz("Basit: geçen yılın aynı ayı", s["gecen_yil"])
    _yaz("Basit: geçen yıl × son 3 ay değişimi", s["gecen_yil_trend"])
    print()
    for r in s["aylar"].itertuples(index=False):
        print("  %d-%02d  gerçek %10.0f   ML %10.0f (%+5.1f%%)   geçen yıl %10.0f (%+5.1f%%)"
              % (r.yil, r.ay, r.gercek, r.ml, (r.gercek - r.ml) / r.ml * 100,
                 r.gecen_yil, (r.gercek - r.gecen_yil) / r.gecen_yil * 100))
