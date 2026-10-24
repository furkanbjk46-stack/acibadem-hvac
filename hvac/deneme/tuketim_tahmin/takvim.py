# -*- coding: utf-8 -*-
"""
TÜRKİYE TATİL TAKVİMİ — resmi tatiller + Ramazan / Kurban bayramları
==================================================================

Maslak'ta (07.2023–08.2026, mevsimden arındırılmış) aynı ayın hafta içi
ortalamasına göre: Cumartesi %94, Pazar %90, bayram/resmi tatil %90.
Dini bayramlar her yıl ~11 gün öne kaydığı için (2025'te Haziran'daki Kurban
2026'da Mayıs sonu) aylık toplamı birkaç yüzde oynatır; model bunu takvimden
ay başlamadan bilir. (Fikir: Gemini v2 paketi; değerler veriyle doğrulandı.)

tatil_degeri(tarih) → 1.0 tam gün tatil, 0.5 arife (öğleden sonra), 0.0 normal.
Yeni yıllar eklenirken Diyanet takvimine bakılmalı (aşağıdaki tarihler bayramın
ilk günü; arife bir önceki gün otomatik).
"""
from __future__ import annotations

from datetime import date, timedelta

import pandas as pd

# (ay, gün) — her yıl aynı
SABIT = {(1, 1), (4, 23), (5, 1), (5, 19), (7, 15), (8, 30), (10, 29)}
SABIT_ARIFE = {(10, 28)}           # Cumhuriyet Bayramı arifesi yarım gün

# Bayramın İLK günü: Ramazan 3 gün, Kurban 4 gün
RAMAZAN = ["2023-04-21", "2024-04-10", "2025-03-30", "2026-03-20", "2027-03-09",
           "2028-02-26", "2029-02-14", "2030-02-04"]
KURBAN = ["2023-06-28", "2024-06-16", "2025-06-06", "2026-05-27", "2027-05-16",
          "2028-05-05", "2029-04-24", "2030-04-13"]


def _gunler():
    tam, arife = set(), set()
    for liste, uzunluk in ((RAMAZAN, 3), (KURBAN, 4)):
        for ilk in liste:
            d = date.fromisoformat(ilk)
            arife.add(d - timedelta(days=1))
            for i in range(uzunluk):
                tam.add(d + timedelta(days=i))
    return tam, arife


_TAM, _ARIFE = _gunler()


def tatil_degeri(t) -> float:
    d = pd.Timestamp(t).date()
    if (d.month, d.day) in SABIT or d in _TAM:
        return 1.0
    if (d.month, d.day) in SABIT_ARIFE or d in _ARIFE:
        return 0.5
    return 0.0


def tatil_serisi(tarihler: pd.Series) -> pd.Series:
    return pd.to_datetime(tarihler).map(tatil_degeri).astype(float)


def kapsiyor_mu(yil: int) -> bool:
    """Bu yılın dini bayram tarihleri listede var mı (yoksa tatil eksik kalır)."""
    return any(x.startswith(str(yil)) for x in RAMAZAN) and any(x.startswith(str(yil)) for x in KURBAN)
