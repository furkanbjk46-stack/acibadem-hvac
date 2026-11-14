# -*- coding: utf-8 -*-
"""
SAYAÇLAR — lokasyonun Modbus enerji analizörlerinin TEK KAYNAĞI (Faz 1 / C1, 12.11.2026)
=====================================================================================

Kaynak: ayar/sayaclar.json (lokasyona ait; teknik ekip düzenler, yama dokunmaz). Dosya
yoksa ornek_ayar/<lokasyon>/sayaclar.json'dan bir kez kopyalanır (yollar.yol tohumlama).

Eskiden liste üç yerde ayrı ayrı tutuluyordu: data_collector.ANALYZERS (IP, marka),
data_bridge (hangi sayaç hangi sütuna, chiller/MCC grupları), enerji_agent (izlenen sütunlar).
Kod Maslak'a ait olduğundan her lokasyona ayrı kod gerekecekti.

Satır: {"ad", "ip", "marka", "tur", "sutun", "kritik"}
  tur: trafo | sebeke | uretim | chiller | alt_sayac
"""
import json
import logging
import os

import yollar

BURASI = os.path.dirname(os.path.abspath(__file__))
TURLER = ("trafo", "sebeke", "uretim", "chiller", "alt_sayac")
logger = logging.getLogger("sayaclar")
_ONBELLEK = {}


def yukle(base_dir: str = None) -> list:
    """Sayaç listesi (sıra korunur). Dosya yok / bozuksa [] (okuma yapılmaz, uyarı loglanır)."""
    p = yollar.yol("ayar/sayaclar.json", base_dir or BURASI)
    try:
        _st = os.stat(p)                     # aynı saniyede yapılan düzenleme de görülsün
        anahtar = (p, _st.st_mtime_ns, _st.st_size)
    except OSError:
        logger.warning("Sayaç listesi yok: %s — Modbus sayaçları okunmayacak", p)
        return []
    if _ONBELLEK.get("anahtar") != anahtar:
        try:
            with open(p, encoding="utf-8-sig") as f:
                veri = json.load(f)
            liste = [dict(s) for s in (veri.get("sayaclar") if isinstance(veri, dict) else veri) or []]
            hatali = [s.get("ad") for s in liste if not s.get("ad") or s.get("tur") not in TURLER]
            if hatali:
                logger.error("Sayaç listesinde geçersiz satır (ad/tur): %s", hatali)
                liste = [s for s in liste if s.get("ad") and s.get("tur") in TURLER]
        except Exception as e:
            logger.error("Sayaç listesi okunamadı (%s): %s", p, e)
            liste = []
        _ONBELLEK.update(anahtar=anahtar, liste=liste)
    return [dict(s) for s in _ONBELLEK["liste"]]


def analizorler(base_dir: str = None) -> list:
    """data_collector biçimi: {"ip", "name", "brand"[, "uretim": True][, "sebeke": True]}."""
    cikti = []
    for s in yukle(base_dir):
        a = {"ip": s.get("ip", ""), "name": s["ad"], "brand": s.get("marka", "")}
        if s["tur"] == "uretim":
            a["uretim"] = True
        if s["tur"] == "sebeke":
            a["sebeke"] = True
        cikti.append(a)
    return cikti


def adlar(tur, base_dir: str = None) -> list:
    """Bu türdeki sayaçların adları (liste sırasıyla). tur: str ya da demet."""
    turler = (tur,) if isinstance(tur, str) else tuple(tur)
    return [s["ad"] for s in yukle(base_dir) if s["tur"] in turler]


def sutun(ad: str, base_dir: str = None) -> str:
    for s in yukle(base_dir):
        if s["ad"] == ad:
            return s.get("sutun", "")
    return ""


def sutunlar(tur=None, base_dir: str = None) -> list:
    turler = TURLER if tur is None else ((tur,) if isinstance(tur, str) else tuple(tur))
    return [s["sutun"] for s in yukle(base_dir) if s["tur"] in turler and s.get("sutun")]


def kritik_adlar(base_dir: str = None) -> set:
    return {s["ad"] for s in yukle(base_dir) if s.get("kritik")}
