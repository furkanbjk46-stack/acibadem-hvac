# -*- coding: utf-8 -*-
"""
GÜNLÜK TAHMİN MODELİ — hava durumu, operasyon ve kaynak ayrımı (GES / kojen / şebeke)
===================================================================================

tahmin_motoru.TuketimTahminModeli (aylık, 11 özellik) yerine önerilen model.
Gerçek Maslak verisinde ileriye dönük sınamada aylık modelden iyi çıktı;
sonuçlar ve gerekçe BENIOKU.md'de.

YAPI
  1) TÜKETİM (yük) = f(derece-gün, hafta sonu/tatil, mevsim,
                       [hasta sayısı], [ameliyat sayısı], [yağış, bulut, radyasyon])
     Doğrusal model (Ridge). Günlük satır sayısı ~1000; aylık modelde 40 vardı.
     Son 90 günün gerçek/tahmin oranı ile seviye düzeltmesi: binaya yeni bölüm
     eklenmesi gibi kalıcı değişimleri yakalar.
  2) GES üretimi = f(radyasyon / bulut / yağış, mevsim)      — veri varsa
  3) KOJEN üretimi = PLAN (girdi): "bu ay kaç gün çalışacak" ya da kWh.
     Kojen hava/takvimle değil işletme kararıyla çalışıyor — Maslak'ta 2026
     Nisan–Haziran neredeyse hiç çalışmadı, Aralık 2025'te 11 gün. Gerçek
     veride kojeni hava/takvimden tahmin etmek %112 hata verdi; bu yüzden
     plan verilmezse son 90 günün çalışma düzeni varsayılır ve sonuçta
     "kojen_kaynak" = "varsayim" yazılır.
     (Yağmurlu günde GES düşer → açığı şebeke ya da kojen kapatır; kojen
      plandaysa açık şebekeye yazılır — denge bunu kendiliğinden yapar.)
  4) ŞEBEKE = TÜKETİM − GES − KOJEN   (enerji dengesi; negatifse 0)
  5) AYLIK BİRLEŞİK TAHMİN = (günlük model + hava düzeltmeli geçen yılın aynı ayı) / 2

[köşeli] özellikler İSTEĞE BAĞLIDIR: sütun yoksa ya da eğitim döneminin %80'inde
dolu değilse model onu kendiliğinden kullanmaz. Hasta/ameliyat verisi boş kalsa da
model çalışır; veri gelince yeniden eğitmek yeter.

EK VERİ DOSYALARI (hepsi isteğe bağlı, ortak sütun "Tarih"; şablonlar sablonlar/ içinde)
  hava       : sicaklik_ort, sicaklik_max, sicaklik_min, yagis_mm, bulut_yuzde,
               gunes_radyasyon (kWh/m²/gün), hava_durumu (metin: güneşli/bulutlu/yağmurlu/karlı)
  operasyon  : hasta_sayisi, ameliyat_sayisi, tatil (0/1)
  enerji     : ana günlük tabloda GES_Uretim_kWh sütunu (adı kolonlar ile değişir)
"""
from __future__ import annotations

import calendar
from typing import Dict, List, Optional

import numpy as np
import pandas as pd
from sklearn.linear_model import Ridge
from sklearn.pipeline import make_pipeline
from sklearn.preprocessing import StandardScaler

from tahmin_motoru import VARSAYILAN_KOLONLAR
import takvim
import veri_kalite

KOLONLAR = dict(VARSAYILAN_KOLONLAR, ges_uretim="GES_Uretim_kWh",
                sogutma="Chiller_Tuketim_kWh",        # soğutma elektriği (chiller analizörleri)
                isitma_gaz="Kazan_Dogalgaz_m3")       # ısıtma: kazan doğalgazı
# GunlukTahminModeli(hedef=...) ile tahmin edilebilecek kalemler
HEDEFLER = ("toplam", "sogutma", "isitma_gaz")
SOGUTMA_TABAN = 18.0   # °C üstü soğutma derece-günü
ISITMA_TABAN = 15.0    # °C altı ısıtma derece-günü (hastane iç yükü yüksek)
ISTEGE_BAGLI = ["hasta_sayisi", "ameliyat_sayisi", "yagis_mm", "bulut_yuzde", "gunes_radyasyon",
                "durum_yagmurlu", "durum_karli"]
DOLULUK_ESIGI = 0.8
TAKVIM_OZELLIK = ["cumartesi", "pazar", "tatil", "ay_sin", "ay_cos"]   # GES/kojen modelleri
# energy_data içindeki hava sütunları (lokasyon portalı hava_durumu.py) → iç adlar
ENERJI_HAVA_SUTUNLARI = {
    "sicaklik_ort": "Hava_Sicaklik_Ort_C", "sicaklik_max": "Hava_Sicaklik_Max_C",
    "sicaklik_min": "Hava_Sicaklik_Min_C", "yagis_mm": "Hava_Yagis_mm",
    "bulut_yuzde": "Hava_Bulut_Yuzde", "gunes_radyasyon": "Hava_Gunes_Radyasyon_kWh_m2",
    "hava_durumu": "Hava_Durumu",
}
SEVIYE_GUN = 90
EGITIM_GUN = 730


def _durum_kodla(metin: pd.Series) -> pd.DataFrame:
    m = metin.fillna("").astype(str).str.lower()
    return pd.DataFrame({
        "durum_yagmurlu": m.str.contains("yağmur|yagmur|sağanak|saganak|rain|shower").astype(float),
        "durum_karli": m.str.contains("kar|snow").astype(float),
    }).where(metin.notna())


def birlestir(gunluk: pd.DataFrame, hava: Optional[pd.DataFrame] = None,
              operasyon: Optional[pd.DataFrame] = None, kolonlar: Optional[Dict] = None,
              haric: Optional[List[Dict]] = None):
    """Ana tablo + ek veriler → modelin iç tablosu. Döner (tablo, kalite_raporu)."""
    k = dict(KOLONLAR, **(kolonlar or {}))
    # Lokasyon portalı (24.10.2026'dan beri) günlük havayı energy_data'nın içine
    # yazıyor (Hava_* sütunları, hava_durumu.py). Ayrı hava dosyası verilmediyse
    # oradan alınır — başka programda da aynı sütun adlarıyla çalışır.
    if hava is None and ENERJI_HAVA_SUTUNLARI["sicaklik_ort"] in gunluk.columns:
        hava = pd.DataFrame({"Tarih": gunluk[k["tarih"]]})
        for ic, dis in ENERJI_HAVA_SUTUNLARI.items():
            if dis in gunluk.columns:
                hava[ic] = gunluk[dis].values
        if "Dis_Hava_Nem_Yuzde" in gunluk.columns and "nem_yuzde" not in hava.columns:
            hava["nem_yuzde"] = gunluk["Dis_Hava_Nem_Yuzde"].values
    d, rapor = veri_kalite.kontrol(gunluk, k, haric=haric)
    g = pd.DataFrame({"tarih": d[k["tarih"]]})
    for ic, dis in (("toplam", "toplam"), ("sebeke", "sebeke"), ("kojen", "kojen_uretim"), ("ges", "ges_uretim"),
                    ("sogutma", "sogutma"), ("isitma_gaz", "isitma_gaz")):
        g[ic] = pd.to_numeric(d[k[dis]], errors="coerce") if k[dis] in d.columns else np.nan
    g["hedef_gecerli"] = d["_hedef_gecerli"].values
    # Bina sensörü: yalnız GÜNLÜK çözünürlükte güvenilir
    sensor = (pd.to_numeric(d[k["dis_hava"]], errors="coerce") if k["dis_hava"] in d.columns
              else pd.Series(np.nan, index=d.index))
    g["T"] = np.where(d["_hava_cozunurluk"] == "gunluk", sensor, np.nan)
    g["T_aylik"] = np.where(d["_hava_cozunurluk"] == "aylik", sensor, np.nan)
    if hava is not None and len(hava):
        h = hava.copy()
        h["tarih"] = pd.to_datetime(h["Tarih"])
        if "hava_durumu" in h.columns:
            h = pd.concat([h, _durum_kodla(h["hava_durumu"])], axis=1)
        g = g.merge(h.drop(columns=["Tarih"]), on="tarih", how="left")
        # Dışarıdan gelen hava, donmuş/aylık bina sensörünün yerine geçer
        if "sicaklik_ort" in g.columns:
            g["T"] = g["sicaklik_ort"].combine_first(g["T"])
    if operasyon is not None and len(operasyon):
        o = operasyon.copy()
        o["tarih"] = pd.to_datetime(o["Tarih"])
        g = g.merge(o.drop(columns=["Tarih"]), on="tarih", how="left")
    for c in ISTEGE_BAGLI + ["tatil"]:
        if c not in g.columns:
            g[c] = np.nan
    g["T"] = g["T"].combine_first(pd.Series(g["T_aylik"]))
    return g.sort_values("tarih").reset_index(drop=True), rapor


class GunlukTahminModeli:
    def __init__(self, alpha: float = 1.0, hedef: str = "toplam"):
        """hedef: 'toplam' (hastane tüketimi), 'sogutma' (chiller kWh), 'isitma_gaz' (kazan m³).
        Kaynak ayrımı (GES/kojen/şebeke) yalnız 'toplam' için anlamlıdır."""
        if hedef not in HEDEFLER:
            raise ValueError("hedef %s olmalı" % (HEDEFLER,))
        self.alpha = alpha
        self.hedef = hedef
        self.secilen: List[str] = []
        self.model = self.model_ges = self.model_kojen = None
        self.seviye = 1.0
        self.klima: Optional[pd.Series] = None      # takvim günü → ortalama sıcaklık
        self.ek_ort: Dict[str, pd.Series] = {}      # isteğe bağlı özelliklerin ay/hafta günü ortalaması
        self.gecmis: Optional[pd.DataFrame] = None

    # ── Özellikler ──────────────────────────────────────────────────────
    @staticmethod
    def _temel(t: pd.Series, T: pd.Series, tatil: pd.Series) -> pd.DataFrame:
        ay = t.dt.month
        return pd.DataFrame({
            "CDD": (T - SOGUTMA_TABAN).clip(lower=0).values,
            "HDD": (ISITMA_TABAN - T).clip(lower=0).values,
            # Cumartesi ve Pazar AYRI: Maslak'ta aynı ayın hafta içine göre Cmt %94, Pzr %90
            "cumartesi": (t.dt.dayofweek == 5).astype(float).values,
            "pazar": (t.dt.dayofweek == 6).astype(float).values,
            "tatil": tatil.fillna(0).astype(float).values,
            "ay_sin": np.sin(2 * np.pi * ay / 12).values,
            "ay_cos": np.cos(2 * np.pi * ay / 12).values,
        })

    def _X(self, g: pd.DataFrame, ozellik: List[str]) -> pd.DataFrame:
        X = self._temel(g["tarih"], g["T"], g["tatil"])
        for c in ozellik:
            X[c] = g[c].astype(float).values
        return X

    def _doldur(self, g: pd.DataFrame) -> pd.DataFrame:
        """Gelecekte/boşlukta bilinmeyen girdiler: sıcaklık → klimatoloji,
        isteğe bağlılar → geçmişin ay × hafta günü ortalaması."""
        g = g.copy()
        doy = g["tarih"].dt.dayofyear
        g["T"] = g["T"].fillna(doy.map(self.klima))
        # Tatil: operasyon dosyası vermediyse Türkiye takvimi (resmi + dini bayram)
        g["tatil"] = g["tatil"].fillna(takvim.tatil_serisi(g["tarih"]))
        for c, tablo in self.ek_ort.items():
            anahtar = list(zip(g["tarih"].dt.month, g["tarih"].dt.dayofweek))
            g[c] = g[c].fillna(pd.Series([tablo.get(a, np.nan) for a in anahtar], index=g.index))
            g[c] = g[c].fillna(tablo.mean())
        return g

    # ── Eğitim ──────────────────────────────────────────────────────────
    def egit(self, g: pd.DataFrame, bitis: Optional[pd.Timestamp] = None) -> Dict:
        bitis = bitis or g["tarih"].max() + pd.Timedelta(days=1)
        gecmis = g[g["tarih"] < bitis].copy()
        self.gecmis = gecmis
        pencere = gecmis[gecmis["tarih"] >= bitis - pd.Timedelta(days=EGITIM_GUN)]
        gecerli = pencere[pencere["hedef_gecerli"] & pencere[self.hedef].notna()]

        # Klimatoloji (takvim günü ort. sıcaklık)
        kl = gecmis.groupby(gecmis["tarih"].dt.dayofyear)["T"].mean().reindex(range(1, 367))
        self.klima = kl.interpolate(limit_direction="both")

        # İsteğe bağlı özellik seçimi: eğitim penceresinin en az %80'i dolu olmalı
        self.secilen = [c for c in ISTEGE_BAGLI if gecerli[c].notna().mean() >= DOLULUK_ESIGI]
        # Isıtma gazında KOJEN PLANI girdidir: kojen çalışınca atık ısısı kazanın yerini
        # tutar (Maslak 04–06.2026 kojen durunca kazan gazı 3–4 katına çıktı). Gerçek
        # veride ısıtma gazı hatası %42 → %22 (ileriye dönük, 24 ay).
        # Soğutmada denendi, katkısı yok — eklenmez.
        if self.hedef == "isitma_gaz" and gecerli["kojen"].notna().mean() >= DOLULUK_ESIGI:
            self.secilen.append("kojen")
        self.ek_ort = {c: gecmis.groupby([gecmis["tarih"].dt.month, gecmis["tarih"].dt.dayofweek])[c].mean()
                       for c in self.secilen}
        egt = self._doldur(gecerli)
        self.model = make_pipeline(StandardScaler(), Ridge(alpha=self.alpha)).fit(
            self._X(egt, self.secilen), egt[self.hedef])

        # Seviye düzeltmesi: son 90 geçerli gün
        son = egt[egt["tarih"] >= bitis - pd.Timedelta(days=SEVIYE_GUN)]
        if len(son) >= 30:
            self.seviye = float(np.clip(son[self.hedef].sum() / max(self.model.predict(self._X(son, self.secilen)).sum(), 1e-9),
                                        0.85, 1.15))

        # Kaynak modelleri (veri varsa)
        hava_ek = [c for c in ("yagis_mm", "bulut_yuzde", "gunes_radyasyon", "durum_yagmurlu", "durum_karli")
                   if c in self.secilen]
        self.model_ges = self._kaynak_modeli(egt, "ges", hava_ek)
        self.model_kojen = self._kaynak_modeli(egt, "kojen", hava_ek)
        return {"basarili": True, "gun": int(len(egt)), "ozellikler": ["CDD", "HDD", "cumartesi", "pazar", "tatil",
                "ay_sin", "ay_cos"] + self.secilen, "seviye": self.seviye,
                "ges_modeli": self.model_ges is not None, "kojen_modeli": self.model_kojen is not None}

    def _kaynak_modeli(self, egt: pd.DataFrame, hedef: str, hava_ek: List[str]):
        v = egt[egt[hedef].notna()]
        if len(v) < 60 or v[hedef].sum() <= 0:
            return None
        X = self._temel(v["tarih"], v["T"], v["tatil"])[TAKVIM_OZELLIK]
        for c in hava_ek:
            X[c] = v[c].astype(float).values
        # Son 90 günün düzeyi: kojen bakım/çalışma rejimi değişince eski yıllar yanıltmasın
        agirlik = np.where(v["tarih"] >= v["tarih"].max() - pd.Timedelta(days=SEVIYE_GUN), 3.0, 1.0)
        m = make_pipeline(StandardScaler(), Ridge(alpha=self.alpha))
        m.fit(X, v[hedef], ridge__sample_weight=agirlik)
        return (m, hava_ek)

    # ── Tahmin ──────────────────────────────────────────────────────────
    def gunluk_tahmin(self, bas, son, hava: Optional[pd.DataFrame] = None,
                      operasyon: Optional[pd.DataFrame] = None) -> pd.DataFrame:
        """Gelecek günler. hava/operasyon verilirse (ör. hava tahmini, ameliyat planı) kullanılır."""
        g = pd.DataFrame({"tarih": pd.date_range(bas, son)})
        g["T"] = np.nan
        for c in ISTEGE_BAGLI + ["tatil", "kojen"]:
            g[c] = np.nan
        for ek in (hava, operasyon):
            if ek is not None and len(ek):
                e = ek.copy(); e["tarih"] = pd.to_datetime(e["Tarih"])
                if "hava_durumu" in e.columns:
                    e = pd.concat([e, _durum_kodla(e["hava_durumu"])], axis=1)
                if "sicaklik_ort" in e.columns:
                    e["T"] = e["sicaklik_ort"]
                g = g.set_index("tarih"); e = e.set_index("tarih")
                for c in e.columns:
                    if c in g.columns:
                        g[c] = g[c].combine_first(e[c].reindex(g.index))
                g = g.reset_index()
        g = self._doldur(g)
        sonuc = pd.DataFrame({"tarih": g["tarih"]})
        sonuc["tuketim"] = np.clip(self.model.predict(self._X(g, self.secilen)) * self.seviye, 0, None)
        for ad, mdl in (("ges", self.model_ges), ("kojen", self.model_kojen)):
            if mdl is None:
                sonuc[ad] = 0.0
            else:
                m, ek = mdl
                X = self._temel(g["tarih"], g["T"], g["tatil"])[TAKVIM_OZELLIK]
                for c in ek:
                    X[c] = g[c].astype(float).values
                sonuc[ad] = np.clip(m.predict(X), 0, None)
        sonuc["sebeke"] = np.clip(sonuc["tuketim"] - sonuc["ges"] - sonuc["kojen"], 0, None)
        sonuc["T"] = g["T"].values
        return sonuc

    def kojen_gunluk_ort(self) -> float:
        """Son 90 günde kojenin ÇALIŞTIĞI günlerin ortalama üretimi (kWh/gün)."""
        h = self.gecmis
        if h is None or h["kojen"].notna().sum() == 0:
            return 0.0
        son = h[(h["tarih"] >= h["tarih"].max() - pd.Timedelta(days=SEVIYE_GUN)) & (h["kojen"] > 1000)]
        if son.empty:
            son = h[h["kojen"] > 1000]
        return float(son["kojen"].mean()) if len(son) else 0.0

    def ay_tahmini(self, yil: int, ay: int, hava=None, operasyon=None,
                   kojen_plan_kwh: Optional[float] = None,
                   kojen_calisma_gun: Optional[float] = None) -> Dict:
        """Aylık tahmin: günlük model, hava düzeltmeli geçen yıl ve ikisinin ortalaması.
        Kojen planı: kojen_plan_kwh ya da kojen_calisma_gun verilirse şebeke ona göre çıkar."""
        ay_gun = calendar.monthrange(yil, ay)[1]
        bas = pd.Timestamp(yil, ay, 1)

        # Kojen planı (toplamda şebeke dengesi, ısıtma gazında doğrudan girdi)
        if kojen_plan_kwh is not None:
            kojen, kojen_kaynak = float(kojen_plan_kwh), "plan_kwh"
        elif kojen_calisma_gun is not None:
            kojen, kojen_kaynak = float(kojen_calisma_gun) * self.kojen_gunluk_ort(), "plan_gun"
        else:
            # Varsayım: son 90 günün çalışma oranı sürer
            son = self.gecmis[self.gecmis["tarih"] >= bas - pd.Timedelta(days=SEVIYE_GUN)]
            oran_calisma = float((son["kojen"] > 1000).mean()) if son["kojen"].notna().any() else 0.0
            kojen, kojen_kaynak = oran_calisma * ay_gun * self.kojen_gunluk_ort(), "varsayim"
        if "kojen" in self.secilen and kojen_kaynak != "varsayim":
            gunler = pd.date_range(bas, periods=ay_gun)
            plan = pd.DataFrame({"Tarih": gunler.strftime("%Y-%m-%d"), "kojen": kojen / ay_gun})
            if operasyon is not None and len(operasyon):
                plan = operasyon.drop(columns=["kojen"], errors="ignore").merge(plan, on="Tarih", how="outer")
            operasyon = plan

        gt = self.gunluk_tahmin(bas, bas + pd.Timedelta(days=ay_gun - 1), hava, operasyon)
        gunluk = float(gt["tuketim"].sum())

        # Hava düzeltmeli geçen yıl: geçen yılın aynı ayı + (bu yılın hava etkisi − o yılın hava etkisi),
        # × son 90 günün bir yıl öncesine göre değişimi
        h = self.gecmis
        gy = h[(h["tarih"].dt.year == yil - 1) & (h["tarih"].dt.month == ay) & h["hedef_gecerli"]
               & h[self.hedef].notna()]
        gecen_yil = None
        if len(gy) >= ay_gun - 3:
            gy_dolu = self._doldur(gy)
            model_gy = self.model.predict(self._X(gy_dolu, self.secilen)).sum() / len(gy) * ay_gun
            model_bu = gunluk / self.seviye
            gercek_gy = gy[self.hedef].sum() / len(gy) * ay_gun
            # hedef boş günler (ör. bilinmeyen toplam) ortalamayı NaN yapmasın
            gecerli_h = h["hedef_gecerli"] & h[self.hedef].notna()
            son90 = h[(h["tarih"] >= bas - pd.Timedelta(days=SEVIYE_GUN)) & gecerli_h]
            once90 = h[(h["tarih"] >= bas - pd.Timedelta(days=SEVIYE_GUN + 365)) &
                       (h["tarih"] < bas - pd.Timedelta(days=365)) & gecerli_h]
            degisim = (son90[self.hedef].mean() / once90[self.hedef].mean()
                       if len(son90) > 30 and len(once90) > 30 and once90[self.hedef].mean() > 0 else 1.0)
            gecen_yil = (gercek_gy + (model_bu - model_gy)) * float(np.clip(degisim, 0.85, 1.15))
        # Geçen yılla ORTALAMA yalnız toplamda: soğutma/ısıtmada geçen yılın aynı ayı
        # tek başına %36 / %68 hata veriyor (işletme düzeni yıldan yıla değişiyor —
        # kojen bakımı, chiller rejimi); karıştırmak sonucu bozuyor (gaz %27 → %30).
        if self.hedef == "toplam" and gecen_yil:
            birlesik = (gunluk + gecen_yil) / 2
        else:
            birlesik = gunluk
        oran = birlesik / gunluk if gunluk > 0 else 1.0
        ges = float(gt["ges"].sum())
        return {"yil": yil, "ay": ay, "gun": ay_gun,
                "tuketim_gunluk_model": gunluk, "tuketim_gecen_yil_duzeltmeli": gecen_yil,
                "tuketim": birlesik, "ges": ges, "kojen": kojen, "kojen_kaynak": kojen_kaynak,
                "sebeke": max(birlesik - ges - kojen, 0.0),
                "ort_sicaklik": float(gt["T"].mean()), "seviye_duzeltmesi": self.seviye,
                "olcek": oran}
