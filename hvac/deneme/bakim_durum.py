# -*- coding: utf-8 -*-
# bakim_durum.py
# Aylık bakım işareti için ORTAK okuma katmanı (tek kaynak: configs/bakim_takvimi.json).
# main_portal (API), app_portal (banner + PDF notu), daily_report, monthly_summary_report,
# bakim_raporu ve cloud_sync (heartbeat) bu modülü kullanır.

import os
import json
import datetime

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
TAKVIM_FILE = os.path.join(BASE_DIR, "configs", "bakim_takvimi.json")
BAKIM_UYARI_GUNU = 25  # ayın bu gününden itibaren işaret yoksa uyarı


def _oku() -> dict:
    try:
        with open(TAKVIM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def ay_durumu(ay: str = None) -> dict:
    """Verilen ay ('YYYY-MM', varsayılan: bu ay) için işaret durumu."""
    if ay is None:
        ay = datetime.datetime.now().strftime("%Y-%m")
    kayit = _oku().get(ay) or {}
    return {
        "ay": ay,
        "yapildi": bool(kayit.get("yapildi")),
        "tarih": kayit.get("tarih", ""),
        "isaretleyen": kayit.get("isaretleyen", ""),
    }


def uyari_gerekli() -> bool:
    """Ayın BAKIM_UYARI_GUNU'nden itibaren bu ayın işareti yoksa True."""
    now = datetime.datetime.now()
    return now.day >= BAKIM_UYARI_GUNU and not ay_durumu()["yapildi"]


def rapor_notu(ay: str = None) -> str:
    """Rapor açıklama bölümlerine eklenecek not; sorun yoksa boş string.
    ay verilirse o ay kesin kontrol edilir (aylık raporlar için);
    verilmezse 'bu ay + gün eşiği' kuralı uygulanır (günlük/anlık raporlar)."""
    if ay is not None:
        if not ay_durumu(ay)["yapildi"]:
            return f"UYARI: {ay} ayında santral bakımları yapılmamıştır (aylık bakım işareti girilmedi)."
        return ""
    if uyari_gerekli():
        return "UYARI: Bu ay santral bakımları yapılmamıştır (aylık bakım işareti girilmedi)."
    return ""


def heartbeat_alani() -> dict:
    """cloud_sync heartbeat'inin bakim_ozet'ine eklenecek alan (Synapse uyarısı için)."""
    d = ay_durumu()
    return {
        "ay": d["ay"],
        "yapildi": d["yapildi"],
        "tarih": d["tarih"],
        "uyari": uyari_gerekli(),
    }
