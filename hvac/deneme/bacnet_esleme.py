# -*- coding: utf-8 -*-
"""
BACNET EŞLEMESİ — BACnet noktaları → energy_data sütunları ve ısıtma hatları (Faz 1 / C2, 12.11.2026)
==================================================================================================

Kaynak: ayar/bacnet_esleme.json (lokasyona ait; teknik ekip düzenler, yama dokunmaz). Yoksa
ornek_ayar/<lokasyon>/bacnet_esleme.json'dan bir kez kopyalanır.

Eskiden data_bridge.BACNET_MAP ve MAS-1 / MAS-2 ısıtma hatları (Mas1_*/Mas2_* sütunları) 7 modülde
koda gömülüydü: köprü, Mekanik Zeka kolektör ortalamaları, tanılama, alarm, Enerji portalı girişi.

{"noktalar": {"<Point Name>": "<sütun ya da _ara_deger>"},
 "isitma_hatlari": [{"ad", "etiket", "isitma", "kazan", "sogutma"}]}
"""
import json
import logging
import os

import yollar

BURASI = os.path.dirname(os.path.abspath(__file__))
logger = logging.getLogger("bacnet_esleme")
_ONBELLEK = {}


def yukle(base_dir: str = None) -> dict:
    p = yollar.yol("ayar/bacnet_esleme.json", base_dir or BURASI)
    try:
        _st = os.stat(p)
        anahtar = (p, _st.st_mtime_ns, _st.st_size)
    except OSError:
        logger.warning("BACnet eşlemesi yok: %s — BACnet değerleri tabloya yazılmayacak", p)
        return {"noktalar": {}, "isitma_hatlari": []}
    if _ONBELLEK.get("anahtar") != anahtar:
        try:
            with open(p, encoding="utf-8-sig") as f:
                veri = json.load(f)
            if not isinstance(veri, dict):
                raise ValueError("JSON nesnesi değil")
        except Exception as e:
            logger.error("BACnet eşlemesi okunamadı (%s): %s", p, e)
            veri = {}
        _ONBELLEK.update(anahtar=anahtar, veri={
            "noktalar": dict(veri.get("noktalar") or {}),
            "isitma_hatlari": [dict(h) for h in (veri.get("isitma_hatlari") or []) if h.get("ad")]})
    v = _ONBELLEK["veri"]
    return {"noktalar": dict(v["noktalar"]), "isitma_hatlari": [dict(h) for h in v["isitma_hatlari"]]}


def noktalar(base_dir: str = None) -> dict:
    """{Point Name: sütun} — data_bridge.BACNET_MAP'in yerine."""
    return yukle(base_dir)["noktalar"]


def hatlar(base_dir: str = None) -> list:
    return yukle(base_dir)["isitma_hatlari"]


def hat_sutunlari(base_dir: str = None, alanlar=("isitma", "kazan", "sogutma")) -> list:
    """Hatların sıcaklık sütunları, hat sırasıyla: [H1 ısıtma, H1 kazan, H1 soğutma, H2 ...]."""
    return [h[a] for h in hatlar(base_dir) for a in alanlar if h.get(a)]


def nokta_adlari(alan: str, base_dir: str = None) -> list:
    """Hatların bu alanı (isitma / kazan / sogutma) için BACnet nokta adları (hat sırasıyla)."""
    ters = {v: k for k, v in noktalar(base_dir).items()}
    return [ters[h[alan]] for h in hatlar(base_dir) if h.get(alan) in ters]
