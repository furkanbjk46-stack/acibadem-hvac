# -*- coding: utf-8 -*-
"""
AYLIK ENERJİ TÜKETİM TAHMİNİ — bağımsız paket
=============================================

Kaynak: hvac/deneme/monthly_report/forecast_engine.py (MLPredictor). Algoritma
BİREBİR aynıdır; yalnızca dosya yolları, lokasyon yöneticisi ve pickle yolu
koddan çıkarıldı, sütun adları dışarıdan verilebilir hale getirildi. Başka bir
programda kullanmak için bu dosya + sinama.py yeterlidir.

Bağımlılık: pandas, numpy, scikit-learn

ALGORİTMA (özet — ayrıntı BENIOKU.md'de)
  1. Günlük veri → AYLIK satıra toplanır (tüketim/gaz/kojen = toplam,
     sıcaklık/set/adet = ortalama, gün sayısı = kayıt sayısı).
     15 günden az verisi olan ay eğitime alınmaz; en az 12 ay gerekir.
  2. Her ay için 11 özellik: ay, sin/cos(ay) (mevsim döngüsü), gün sayısı,
     dış hava ort., chiller set ort., chiller/absorption/kazan adet ort.,
     kojen üretimi toplamı, kazan doğalgazı toplamı.
  3. İki ayrı GradientBoostingRegressor (150 ağaç, derinlik 5, öğrenme 0.1):
     biri toplam tüketim, biri şebeke tüketimi için.
  4. Tahmin edilecek ayın girdileri bilinmediği için GEÇMİŞTE AYNI AYIN
     ortalama koşulları kullanılır (ör. Kasım tahmini = geçmiş Kasımların
     ortalama dış havası, ortalama chiller adedi...). Kojen ve gaz için
     geçmiş aynı ayların yıllık ortalaması.
"""
from __future__ import annotations

import calendar
import math
import pickle
from typing import Dict, Optional

import numpy as np
import pandas as pd

OZELLIKLER = [
    "ay", "ay_sin", "ay_cos", "gun_sayisi", "dis_hava", "chiller_set",
    "chiller_adet", "absorption_adet", "kazan_adet", "kojen_uretim", "kazan_dogalgaz",
]

# Girdi tablosundaki sütun adları. Başka programda adlar farklıysa
# TuketimTahminModeli(kolonlar={...}) ile değiştirilir.
VARSAYILAN_KOLONLAR = {
    "tarih": "Tarih",
    "toplam": "Toplam_Hastane_Tuketim_kWh",
    "sebeke": "Sebeke_Tuketim_kWh",
    "dis_hava": "Dis_Hava_Sicakligi_C",
    "chiller_set": "Chiller_Set_Temp_C",
    "chiller_adet": "Chiller_Adet",
    "absorption_adet": "Absorption_Chiller_Adet",
    "kazan_adet": "Kazan_Adet",
    "kojen_uretim": "Kojen_Uretim_kWh",
    "kazan_dogalgaz": "Kazan_Dogalgaz_m3",
}

# Eksik sütunun varsayılan değeri (orijinal koddaki fillna değerleri)
_VARSAYILAN_DEGER = {"chiller_set": 7.0}


class TuketimTahminModeli:
    """Aylık toplam ve şebeke tüketimi için iki GradientBoosting modeli."""

    EN_AZ_AY = 12
    EN_AZ_GUN = 15

    def __init__(self, kolonlar: Optional[Dict[str, str]] = None,
                 n_estimators: int = 150, max_depth: int = 5,
                 min_samples_split: int = 3, learning_rate: float = 0.1,
                 random_state: int = 42):
        self.k = dict(VARSAYILAN_KOLONLAR, **(kolonlar or {}))
        self.parametre = dict(n_estimators=n_estimators, max_depth=max_depth,
                              min_samples_split=min_samples_split,
                              learning_rate=learning_rate, random_state=random_state)
        self.model_toplam = None
        self.model_sebeke = None
        self.r2_toplam = None
        self.r2_sebeke = None
        self.ozellik_onemi: Dict[str, float] = {}
        self.egitim_ay = 0

    # ── Veri hazırlama ────────────────────────────────────────────────────
    def _hazirla(self, gunluk: pd.DataFrame) -> pd.DataFrame:
        k = self.k
        d = gunluk.copy()
        d[k["tarih"]] = pd.to_datetime(d[k["tarih"]])
        for ad in k:
            if ad != "tarih":
                if k[ad] in d.columns:
                    d[k[ad]] = pd.to_numeric(d[k[ad]], errors="coerce")
                else:
                    d[k[ad]] = np.nan
        d["_yil"] = d[k["tarih"]].dt.year
        d["_ay"] = d[k["tarih"]].dt.month
        return d

    def aylik_ozet(self, gunluk: pd.DataFrame) -> pd.DataFrame:
        """Günlük → aylık. Toplamlar 'sum', koşullar 'mean'."""
        k, d = self.k, self._hazirla(gunluk)
        a = d.groupby(["_yil", "_ay"]).agg(
            toplam=(k["toplam"], "sum"), sebeke=(k["sebeke"], "sum"),
            dis_hava=(k["dis_hava"], "mean"), chiller_set=(k["chiller_set"], "mean"),
            chiller_adet=(k["chiller_adet"], "mean"), absorption_adet=(k["absorption_adet"], "mean"),
            kazan_adet=(k["kazan_adet"], "mean"), kojen_uretim=(k["kojen_uretim"], "sum"),
            kazan_dogalgaz=(k["kazan_dogalgaz"], "sum"), gun_sayisi=(k["tarih"], "count"),
        ).reset_index().rename(columns={"_yil": "yil", "_ay": "ay"})
        return a

    @staticmethod
    def ozellik_satiri(ay: int, gun_sayisi: float, kosul: Dict[str, float]) -> Dict[str, float]:
        satir = {"ay": float(ay), "ay_sin": math.sin(2 * math.pi * ay / 12),
                 "ay_cos": math.cos(2 * math.pi * ay / 12), "gun_sayisi": float(gun_sayisi)}
        for ad in OZELLIKLER[4:]:
            v = kosul.get(ad)
            satir[ad] = float(_VARSAYILAN_DEGER.get(ad, 0.0) if v is None or v != v else v)
        return satir

    def _X(self, aylik: pd.DataFrame) -> pd.DataFrame:
        return pd.DataFrame([self.ozellik_satiri(int(r.ay), r.gun_sayisi, r._asdict())
                             for r in aylik.itertuples(index=False)])[OZELLIKLER]

    # ── Eğitim ────────────────────────────────────────────────────────────
    def egit(self, gunluk: pd.DataFrame, cv_kat: int = 5) -> Dict:
        from sklearn.ensemble import GradientBoostingRegressor
        from sklearn.model_selection import cross_val_score

        aylik = self.aylik_ozet(gunluk)
        aylik = aylik[aylik.gun_sayisi >= self.EN_AZ_GUN]
        if len(aylik) < self.EN_AZ_AY:
            return {"basarili": False, "neden": "yetersiz ay (%d/%d)" % (len(aylik), self.EN_AZ_AY)}

        X = self._X(aylik)
        y_t, y_s = aylik["toplam"].fillna(0), aylik["sebeke"].fillna(0)
        self.model_toplam = GradientBoostingRegressor(**self.parametre).fit(X, y_t)
        self.model_sebeke = GradientBoostingRegressor(**self.parametre).fit(X, y_s)
        # NOT: orijinaldeki gibi karıştırmasız k-katlı CV (zaman sırasına bakmaz).
        # Gerçek başarıyı sinama.ileriye_donuk_sinama ölçer.
        kat = min(cv_kat, len(X))
        self.r2_toplam = float(np.mean(cross_val_score(
            GradientBoostingRegressor(**self.parametre), X, y_t, cv=kat, scoring="r2")))
        self.r2_sebeke = float(np.mean(cross_val_score(
            GradientBoostingRegressor(**self.parametre), X, y_s, cv=kat, scoring="r2")))
        self.ozellik_onemi = dict(zip(OZELLIKLER, map(float, self.model_toplam.feature_importances_)))
        self.egitim_ay = len(aylik)
        return {"basarili": True, "ay": self.egitim_ay, "r2_toplam": self.r2_toplam,
                "r2_sebeke": self.r2_sebeke, "ozellik_onemi": self.ozellik_onemi}

    # ── Tahmin ────────────────────────────────────────────────────────────
    def gecmis_kosullar(self, gunluk: pd.DataFrame, ay: int) -> Dict[str, float]:
        """Geçmişte aynı ayın ortalama koşulları (ekrandaki tahminin girdisi)."""
        d = self._hazirla(gunluk)
        g = d[d["_ay"] == ay]
        if g.empty:
            return {}
        k, yil_sayisi = self.k, max(g["_yil"].nunique(), 1)
        return {
            "dis_hava": g[k["dis_hava"]].fillna(0).mean(),
            "chiller_set": g[k["chiller_set"]].fillna(7).mean(),
            "chiller_adet": g[k["chiller_adet"]].fillna(0).mean(),
            "absorption_adet": g[k["absorption_adet"]].fillna(0).mean(),
            "kazan_adet": g[k["kazan_adet"]].fillna(0).mean(),
            "kojen_uretim": g[k["kojen_uretim"]].fillna(0).sum() / yil_sayisi,
            "kazan_dogalgaz": g[k["kazan_dogalgaz"]].fillna(0).sum() / yil_sayisi,
        }

    def tahmin(self, yil: int, ay: int, kosul: Dict[str, float],
               gun_sayisi: Optional[int] = None) -> Dict[str, float]:
        """Verilen koşullarla bir ayın tahmini (senaryo da bu)."""
        if self.model_toplam is None:
            raise RuntimeError("Model eğitilmedi")
        gun = gun_sayisi or calendar.monthrange(yil, ay)[1]
        X = pd.DataFrame([self.ozellik_satiri(ay, gun, kosul)])[OZELLIKLER]
        t = max(float(self.model_toplam.predict(X)[0]), 0.0)
        s = max(float(self.model_sebeke.predict(X)[0]), 0.0)
        return {"toplam_kwh": t, "sebeke_kwh": s, "kojen_kwh": max(t - s, 0.0),
                "gunluk_toplam_kwh": t / gun, "gun_sayisi": gun}

    def tahmin_gecmisten(self, gunluk: pd.DataFrame, yil: int, ay: int) -> Dict[str, float]:
        """Ekrandaki 'Tahmin (kWh)' sütunu: geçmiş aynı ayın koşullarıyla."""
        kosul = self.gecmis_kosullar(gunluk, ay)
        if not kosul:
            return {}
        sonuc = self.tahmin(yil, ay, kosul)
        sonuc["kosullar"] = {a: round(float(v), 1) for a, v in kosul.items()}
        return sonuc

    # ── Kalıcılık ────────────────────────────────────────────────────────
    def kaydet(self, yol: str) -> None:
        with open(yol, "wb") as f:
            pickle.dump({"surum": 1, "ozellikler": OZELLIKLER, "kolonlar": self.k,
                         "parametre": self.parametre, "model_toplam": self.model_toplam,
                         "model_sebeke": self.model_sebeke, "r2_toplam": self.r2_toplam,
                         "r2_sebeke": self.r2_sebeke, "ozellik_onemi": self.ozellik_onemi,
                         "egitim_ay": self.egitim_ay}, f)

    @classmethod
    def yukle(cls, yol: str) -> "TuketimTahminModeli":
        with open(yol, "rb") as f:
            v = pickle.load(f)
        if v.get("ozellikler") != OZELLIKLER:
            raise ValueError("Kayıtlı modelin özellik listesi farklı — yeniden eğitin")
        m = cls(kolonlar=v["kolonlar"], **v["parametre"])
        for a in ("model_toplam", "model_sebeke", "r2_toplam", "r2_sebeke", "ozellik_onemi", "egitim_ay"):
            setattr(m, a, v[a])
        return m
