# -*- coding: utf-8 -*-
"""
VERİ KALİTE KONTROLÜ — eğitimden ÖNCE bozuk günleri ayıkla
=========================================================

NEDEN: Model bozuk veriyle eğitilirse bozukluğu "öğrenir" ve sınamada da
yanlış ölçülür. Maslak'ta (23.10.2026 incelemesi) görülenler:
  · BACnet noktaları 20.09.2026'dan beri DONMUŞ: dış hava her gün 19,88 °C,
    chiller yükü, kazan sıcaklıkları da aynı — veri dosyası güncellenmiyor.
  · 30.09.2026'dan beri kojen üretimi boş → toplam tüketim yalnız şebeke,
    gerçeğin altında.
  · 18.10 = 0 kWh, 19.10 = 106.818 kWh → iki gün tek güne yazılmış.
  · Eylül 2026'da hesap yöntemi değişti (kojen/şebeke) → kullanıcı kararıyla
    hariç (lokasyonlar/maslak.json).
  · 2025 sonuna kadar dış hava AYLIK ortalama olarak her güne yazılmış
    (her ay tek değer) — günlük hava etkisi bu dönemden öğrenilemez.

Kontrol bozuk günü SİLMEZ; neden'li bir bayrak koyar. Tüketim hedefi bozuksa
gün eğitimden çıkar; yalnız sensör bozuksa o sensör değeri boşaltılır
(hava verisi dışarıdan gelirse onunla doldurulur).
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from typing import Dict, List, Optional

import numpy as np
import pandas as pd

BURASI = os.path.dirname(os.path.abspath(__file__))


@dataclass
class KaliteRaporu:
    bulgular: List[Dict] = field(default_factory=list)

    def ekle(self, tur: str, bas, son, gun: int, aciklama: str) -> None:
        self.bulgular.append({"tur": tur, "bas": str(pd.Timestamp(bas).date()),
                              "son": str(pd.Timestamp(son).date()), "gun": int(gun),
                              "aciklama": aciklama})

    def ozet(self) -> str:
        if not self.bulgular:
            return "Veri kalite sorunu bulunmadı."
        return "\n".join("  [%s] %s → %s (%d gün): %s" % (b["tur"], b["bas"], b["son"], b["gun"], b["aciklama"])
                         for b in self.bulgular)


def lokasyon_ayari(lokasyon: str) -> Dict:
    """lokasyonlar/<ad>.json — elle hariç tutulan dönemler vb."""
    yol = os.path.join(BURASI, "lokasyonlar", lokasyon + ".json")
    if not os.path.exists(yol):
        return {}
    with open(yol, encoding="utf-8") as f:
        return json.load(f)


def _kosular(seri: pd.Series):
    """Aynı değerin art arda tekrarlandığı bloklar: (bas_idx, son_idx, uzunluk, deger)."""
    s = seri.round(3)
    grup = (s != s.shift()).cumsum()
    for _, blok in s.groupby(grup):
        if blok.notna().all():
            yield blok.index[0], blok.index[-1], len(blok), blok.iloc[0]


def kontrol(gunluk: pd.DataFrame, kolonlar: Dict[str, str], haric: Optional[List[Dict]] = None,
            donma_gun: int = 5) -> (pd.DataFrame, KaliteRaporu):
    """Döner: (bayraklı tablo, rapor). Tabloya eklenen sütunlar:
       _hedef_gecerli (bool) — toplam tüketim eğitimde kullanılabilir mi
       _hava_cozunurluk — 'gunluk' | 'aylik' | 'yok'
    """
    k = kolonlar
    d = gunluk.copy()
    d[k["tarih"]] = pd.to_datetime(d[k["tarih"]])
    d = d.sort_values(k["tarih"]).drop_duplicates(k["tarih"]).reset_index(drop=True)
    for c in (k["toplam"], k["sebeke"], k["kojen_uretim"], k["dis_hava"]):
        if c in d.columns:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    t = d[k["tarih"]]
    r = KaliteRaporu()
    d["_hedef_gecerli"] = True
    d["_hava_cozunurluk"] = "gunluk"

    # 1) Elle hariç tutulan dönemler
    for h in haric or []:
        m = (t >= pd.Timestamp(h["bas"])) & (t <= pd.Timestamp(h["son"]))
        if m.any():
            d.loc[m, "_hedef_gecerli"] = False
            r.ekle("HARİÇ", h["bas"], h["son"], m.sum(), h.get("neden", "elle hariç tutuldu"))

    # 2) Sıfır / eksi / boş toplam
    y = d[k["toplam"]]
    m = y.isna() | (y <= 0)
    if m.any():
        d.loc[m, "_hedef_gecerli"] = False
        for i in d.index[m]:
            r.ekle("SIFIR", t[i], t[i], 1, "toplam tüketim boş veya 0")

    # 3) İki gün tek güne yazılmış: sıfır günün komşusu ~2 kat
    med = y.where(y > 0).rolling(15, center=True, min_periods=5).median()
    for i in d.index[m]:
        for j in (i - 1, i + 1):
            if 0 <= j < len(d) and y[j] > 1.6 * (med[j] or np.inf):
                d.loc[j, "_hedef_gecerli"] = False
                r.ekle("ÇİFT GÜN", t[j], t[j], 1,
                       "%.0f kWh ≈ normalin %.1f katı; yanındaki gün 0 — iki gün birleşmiş" % (y[j], y[j] / med[j]))

    # 4) Kojen kaybı: kojen normalde var, sonra boş/0 kalmış → toplam eksik sayılır
    if k["kojen_uretim"] in d.columns:
        kj = d[k["kojen_uretim"]]
        calisiyor = kj.rolling(60, min_periods=20).apply(lambda s: (s > 0).mean(), raw=True).shift(1)
        kayip = kj.isna() & (calisiyor > 0.5)
        for bas, son, n, _ in _kosular(kayip.astype(float).where(kayip)):
            if n >= 3:
                aralik = (t >= t[bas]) & (t <= t[son])
                d.loc[aralik, "_hedef_gecerli"] = False
                r.ekle("KOJEN YOK", t[bas], t[son], n,
                       "kojen üretimi okunmuyor; toplam = yalnız şebeke, gerçeğin altında")

    # 5) Dış hava: aylık ortalama mı girilmiş, sensör mü donmuş?
    if k["dis_hava"] in d.columns:
        hv = d[k["dis_hava"]]
        for bas, son, n, deger in _kosular(hv):
            if n < donma_gun:
                continue
            ayni_ay = t[bas].to_period("M") == t[son].to_period("M")
            tam_ay = ayni_ay and t[bas].day == 1 and t[son].day >= t[son].days_in_month - 1
            aralik = (t >= t[bas]) & (t <= t[son])
            if tam_ay or (ayni_ay and n >= 20):
                d.loc[aralik, "_hava_cozunurluk"] = "aylik"
            else:
                d.loc[aralik, k["dis_hava"]] = np.nan
                d.loc[aralik, "_hava_cozunurluk"] = "yok"
                r.ekle("DONMUŞ SENSÖR", t[bas], t[son], n,
                       "dış hava %d gün boyunca %.2f °C — BACnet verisi güncellenmiyor" % (n, deger))
        aylik = d["_hava_cozunurluk"] == "aylik"
        if aylik.any():
            r.ekle("AYLIK HAVA", t[aylik].min(), t[aylik].max(), aylik.sum(),
                   "dış hava her güne aylık ortalama olarak yazılmış; günlük hava etkisi bu dönemden öğrenilemez")
    return d, r
