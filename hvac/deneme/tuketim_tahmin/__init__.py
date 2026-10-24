# -*- coding: utf-8 -*-
"""Günlük tüketim tahmin modeli — Enerji portalı (Tahmin & Trend) için.

Bu klasördeki model dosyaları (gunluk_model, tahmin_motoru, takvim,
veri_kalite, sinama) disa_aktarim/tuketim_tahmin/ paketinin BİREBİR
kopyasıdır: o paket başka programlarda tek başına çalışsın diye düz
(`import takvim`) içe aktarım kullanıyor. Aynı dosyaları değiştirmeden
burada da çalıştırmak için klasör sys.path'e eklenir. İki kopyanın aynı
kaldığını test_tuketim_tahmin.py denetler.

Portal yalnız portal_ozet.py'yi kullanır.
"""
import os
import sys

_BURASI = os.path.dirname(os.path.abspath(__file__))
if _BURASI not in sys.path:
    sys.path.insert(0, _BURASI)
