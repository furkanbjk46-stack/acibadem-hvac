# -*- coding: utf-8 -*-
"""
AYAR YOLLARI — BACnet nokta dosyası için kısa yol (12.11.2026, N2). Asıl kaynak: yollar.py (Faz 1).

NEDEN: BACnet nokta dosyası iki ayrı yerden okunuyordu (kök ve configs/); Maslak'ta iki kopya
ayrışmıştı. Faz 1'de dosyanın yeri ayar/bacnet_noktalari.json oldu; taşınmamış kurulumda
eski kopyalardan EN SON DEĞİŞTİRİLEN geçerlidir (yollar.yol kuralı).
"""
import os

import yollar

BURASI = os.path.dirname(os.path.abspath(__file__))
NOKTA_DOSYA = "ahu_nokta_konfig.json"
_ANAHTAR = "configs/ahu_nokta_konfig.json"


def nokta_konfig_adaylari(base_dir: str = None):
    """Var olabilecek bütün kopyalar: yeni yer + eski yerler."""
    base_dir = base_dir or BURASI
    yeni = yollar.yeni_yer(_ANAHTAR)
    eskiler = [e for y, es in yollar.KAYIT if y == yeni for e in es]
    return [os.path.join(base_dir, *p.split("/")) for p in [yeni] + eskiler]


def nokta_konfig_yolu(base_dir: str = None) -> str:
    """Geçerli BACnet nokta dosyası (yollar.yol kuralı)."""
    return yollar.yol(_ANAHTAR, base_dir or BURASI)


def nokta_konfig_ayrisik(base_dir: str = None) -> bool:
    """Birden çok kopya var ve içerikleri farklı mı (agent'lar ve kurulum kontrolü için)."""
    icerikler = set()
    for p in nokta_konfig_adaylari(base_dir):
        if os.path.exists(p):
            with open(p, "rb") as f:
                icerikler.add(f.read())
    return len(icerikler) > 1
