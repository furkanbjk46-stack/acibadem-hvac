# -*- coding: utf-8 -*-
"""
GÜNLÜK HAVA VERİSİ — Open-Meteo (ücretsiz, anahtar gerekmez)
===========================================================

Geçmiş (arşiv) ve gelecek 16 gün (tahmin) günlük hava verisini lokasyonun
koordinatıyla indirir, sablonlar/hava_sablon.csv biçimine çevirir.

Neden gerekli: Maslak'ta bina sensörünün dış havası 2025 sonuna kadar AYLIK
ortalama olarak girilmiş, 20.09.2026'dan sonra da BACnet okuması durduğu için
donmuştu — modelin hiç gerçek günlük havası yoktu.

Dışarıya giden tek bilgi koordinat ve tarih aralığıdır.

    python hava_indir.py maslak                         # 2023-06-01 → dün (arşiv)
    python hava_indir.py maslak --bas 2024-01-01 --son 2026-10-23
    python hava_indir.py maslak --tahmin                # bugün + 16 gün (hava tahmini)

Sütunlar: Tarih, sicaklik_ort, sicaklik_max, sicaklik_min, yagis_mm,
          bulut_yuzde, gunes_radyasyon (kWh/m²/gün), hava_durumu (metin)
Not: arşiv birkaç gün geriden gelir; son günler boş olabilir.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.request
from datetime import date, timedelta

import pandas as pd

import veri_kalite

ARSIV = "https://archive-api.open-meteo.com/v1/archive"
TAHMIN = "https://api.open-meteo.com/v1/forecast"
GUNLUK = ("temperature_2m_mean,temperature_2m_max,temperature_2m_min,precipitation_sum,"
          "cloud_cover_mean,shortwave_radiation_sum,weather_code")


def durum_metni(kod) -> str:
    """WMO hava kodu → modelin anladığı metin (gunluk_model._durum_kodla)."""
    if kod is None or kod != kod:
        return ""
    k = int(kod)
    if k in (71, 73, 75, 77, 85, 86):
        return "karlı"
    if 51 <= k <= 67 or 80 <= k <= 82 or k >= 95:
        return "yağmurlu"
    if k in (45, 48):
        return "sisli"
    if k in (2, 3):
        return "bulutlu"
    return "güneşli"


def indir(enlem: float, boylam: float, bas: str = None, son: str = None, tahmin: bool = False) -> pd.DataFrame:
    if tahmin:
        url = "%s?latitude=%s&longitude=%s&daily=%s&forecast_days=16&timezone=Europe%%2FIstanbul" % (
            TAHMIN, enlem, boylam, GUNLUK)
    else:
        url = "%s?latitude=%s&longitude=%s&start_date=%s&end_date=%s&daily=%s&timezone=Europe%%2FIstanbul" % (
            ARSIV, enlem, boylam, bas, son, GUNLUK)
    with urllib.request.urlopen(url, timeout=60) as r:
        v = json.load(r)["daily"]
    return cevir(v)


def cevir(gunluk: dict) -> pd.DataFrame:
    d = pd.DataFrame(gunluk)
    durum = d["weather_code"].map(durum_metni)
    # WMO kodu bir saatlik çiselemeyi bile "yağmur" sayar (Maslak'ta 1241 günün
    # 568'i yağmurlu çıktı). 1 mm altı yağışlı gün GES ve yük için bulutlu gündür.
    durum = durum.where(~((durum == "yağmurlu") & (d["precipitation_sum"].fillna(0) < 1.0)), "bulutlu")
    return pd.DataFrame({
        "Tarih": d["time"],
        "sicaklik_ort": d["temperature_2m_mean"],
        "sicaklik_max": d["temperature_2m_max"],
        "sicaklik_min": d["temperature_2m_min"],
        "yagis_mm": d["precipitation_sum"],
        "bulut_yuzde": d["cloud_cover_mean"],
        "gunes_radyasyon": (d["shortwave_radiation_sum"] / 3.6).round(3),   # MJ/m² → kWh/m²
        "hava_durumu": durum,
    }).dropna(subset=["sicaklik_ort"])


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("lokasyon")
    p.add_argument("--bas", default="2023-06-01")
    p.add_argument("--son", default=(date.today() - timedelta(days=1)).isoformat())
    p.add_argument("--tahmin", action="store_true")
    a = p.parse_args()
    ayar = veri_kalite.lokasyon_ayari(a.lokasyon)
    if "enlem" not in ayar:
        raise SystemExit("lokasyonlar/%s.json içinde enlem/boylam yok" % a.lokasyon)
    df = indir(ayar["enlem"], ayar["boylam"], a.bas, a.son, a.tahmin)
    hedef = os.path.join(veri_kalite.BURASI, "lokasyonlar",
                         "%s_hava%s.csv" % (a.lokasyon, "_tahmin" if a.tahmin else ""))
    df.to_csv(hedef, index=False)
    print("%d gün yazıldı → %s  (%s → %s)" % (len(df), hedef, df.Tarih.min(), df.Tarih.max()))
