# -*- coding: utf-8 -*-
"""
HASTANELER — Synapse'teki hastane listesinin TEK KAYNAĞI (Faz 1 / D3, 12.11.2026)
================================================================================

Kaynak: merkez/configs/hastaneler.json — {lokasyon_id: {isim, kisa, lat, lon, m2, renk}}

Eskiden liste dört yerde ayrı ayrı duruyordu: app_merkez.py, pages/lokasyon_detay.py,
pages/rapor_olustur.py (Türkçe karaktersiz kopya) ve configs/lokasyon_koordinat.json (hava
besleyici). Yeni bir hastane = hastaneler.json'a bir satır.
"""
import json
import os

BURASI = os.path.dirname(os.path.abspath(__file__))
DOSYA = os.path.join(BURASI, "configs", "hastaneler.json")
_TR = str.maketrans("ıİşŞğĞüÜöÖçÇ", "iIsSgGuUoOcC")


def yukle(dosya: str = None) -> dict:
    """{lokasyon_id: {isim, kisa, lat, lon, m2, renk}} — dosyadaki sırayla; her çağrıda yeni kopya."""
    with open(dosya or DOSYA, encoding="utf-8") as f:
        veri = json.load(f)
    return {k: dict(v) for k, v in veri["hastaneler"].items()}


def koordinatlar(dosya: str = None) -> dict:
    """{lokasyon_id: (enlem, boylam)} — hava besleyici (agent_servisi.py) için."""
    return {k: (float(v["lat"]), float(v["lon"])) for k, v in yukle(dosya).items()}


def ascii_ad(metin: str) -> str:
    """Türkçe karaktersiz ad (rapor PDF'i Unicode yazı tipi bulamazsa Helvetica'ya düşer)."""
    return str(metin).translate(_TR)


def yukle_ascii(dosya: str = None) -> dict:
    """Rapor sayfasının kullandığı karaktersiz kopya (isim ve kısa ad)."""
    return {k: dict(v, isim=ascii_ad(v["isim"]), kisa=ascii_ad(v["kisa"])) for k, v in yukle(dosya).items()}
