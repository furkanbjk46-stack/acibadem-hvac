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
  tur: trafo | sebeke | uretim | chiller | alt_sayac | kontrol
  kontrol (14.11.2026): okunur ve günlük değeri kaydedilir, HİÇBİR toplama girmez — başka sayaçların
  toplamını ölçen karşılaştırma sayacı (ör. Maslak STEP-UP/3 = KOJEN-3 + KOJEN-4). Enerji, üretim
  sayaçları gibi yönden bağımsız okunur (giren + verilen; tüketim sayacında verilen ≈ 0).

BMS SAYAÇLARI (26.11.2026): sayaç Modbus analizörü değil, BMS'teki (Desigo) bir BACnet noktası da olabilir —
su, doğalgaz, ısı ya da elektrik (ör. chiller kWh'i analizör yerine BMS'ten). Panelde BMS noktasının
"Nokta Türü" = sayaç seçilir; satır bu listeye şu alanlarla girer:
  {"ad", "kaynak": "bms", "nokta": <Point Name>, "tur", "birim", "carpan", "sutun", "kritik"}
  Adres BACnet okuma şablonundadır (Point Name ile bulunur). Değer ENDEKS olmalı (sürekli artan toplam);
  günlük tüketim = bugünkü endeks − dünkü endeks (analizörlerle aynı hesap, aynı 23:59 okuması).
  Elektrik türleri (trafo … kontrol) BMS'ten de gelebilir ve aynı toplamlara girer. Ek türler:
    su_ana    → Su_Tuketimi_m3 (birden çoksa toplamı)      su_alt    → yalnız kendi sütunu
    gaz_kazan → Kazan_Dogalgaz_m3                          gaz_kojen → Kojen_Dogalgaz_m3
    gaz_alt   → yalnız kendi sütunu                        isi       → ısı sayacı (kWh), hiçbir toplama girmez
"""
import json
import logging
import os

import yollar

BURASI = os.path.dirname(os.path.abspath(__file__))
ELEKTRIK_TURLERI = ("trafo", "sebeke", "uretim", "chiller", "alt_sayac", "kontrol")
DIGER_TURLER = ("su_ana", "su_alt", "gaz_kazan", "gaz_kojen", "gaz_alt", "isi")
TURLER = ELEKTRIK_TURLERI + DIGER_TURLER
# Türün birimi (BMS sayacının değeri bu birime çevrilir) ve günlük satırdaki ortak sütunu
BIRIM = {t: "kWh" for t in ELEKTRIK_TURLERI + ("isi",)}
BIRIM.update({t: "m³" for t in ("su_ana", "su_alt", "gaz_kazan", "gaz_kojen", "gaz_alt")})
TOPLAM_SUTUN = {"su_ana": "Su_Tuketimi_m3", "gaz_kazan": "Kazan_Dogalgaz_m3", "gaz_kojen": "Kojen_Dogalgaz_m3"}
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


def bms_mi(s: dict) -> bool:
    return (s.get("kaynak") or "modbus") == "bms"


def bms_sayaclar(base_dir: str = None) -> list:
    """BMS (BACnet) noktasından okunan sayaçlar."""
    return [s for s in yukle(base_dir) if bms_mi(s)]


def birim(s: dict) -> str:
    return s.get("birim") or BIRIM.get(s.get("tur"), "kWh")


def analizorler(base_dir: str = None) -> list:
    """data_collector biçimi (yalnız Modbus): {"ip", "name", "brand"[, "uretim": True][, "sebeke": True]}."""
    cikti = []
    for s in yukle(base_dir):
        if bms_mi(s):
            continue
        a = {"ip": s.get("ip", ""), "name": s["ad"], "brand": s.get("marka", "")}
        if s["tur"] in ("uretim", "kontrol"):      # yön bağımsız okuma (toplama girmek ayrı: tur)
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
