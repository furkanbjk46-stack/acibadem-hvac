# lisans.py
# Makine ID tabanlı lisans dogrulama sistemi
# Supabase'deki 'lisanslar' tablosunu kontrol eder

from __future__ import annotations
import subprocess, json, os, sys
from pathlib import Path

# ── Makine ID ────────────────────────────────────────
def get_makine_id() -> str:
    """Windows motherboard UUID'sini dondurur."""
    try:
        result = subprocess.check_output(
            "wmic csproduct get uuid",
            shell=True, stderr=subprocess.DEVNULL
        ).decode().strip().split("\n")
        for line in result:
            uid = line.strip()
            if uid and uid.upper() != "UUID":
                return uid
    except Exception:
        pass
    # Fallback: MAC adresi
    import uuid
    return str(uuid.getnode())


# ── Supabase config ───────────────────────────────────
def _load_config() -> dict:
    cfg_path = Path(__file__).parent / "supabase_config.json"
    with open(cfg_path, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Lisans kontrolu ───────────────────────────────────
def lisans_kontrol() -> dict:
    """
    Donus: {
        "gecerli": True/False,
        "makine_id": "...",
        "lokasyon_id": "...",
        "hata": None / "hata mesaji"
    }
    """
    makine_id = get_makine_id()
    try:
        cfg = _load_config()
        url = cfg["supabase_url"]
        key = cfg["supabase_key"]
        lok_id = cfg.get("lokasyon_id", "")

        from supabase import create_client
        sb = create_client(url, key)

        sonuc = (
            sb.table("lisanslar")
            .select("aktif, lokasyon_id, makine_adi")
            .eq("makine_id", makine_id)
            .eq("lokasyon_id", lok_id)
            .single()
            .execute()
        )

        if sonuc.data and sonuc.data.get("aktif"):
            return {
                "gecerli": True,
                "makine_id": makine_id,
                "lokasyon_id": lok_id,
                "makine_adi": sonuc.data.get("makine_adi", ""),
                "hata": None,
            }
        else:
            return {
                "gecerli": False,
                "makine_id": makine_id,
                "lokasyon_id": lok_id,
                "hata": "Bu cihaz icin lisans tanimli degil veya pasif.",
            }

    except Exception as e:
        err = str(e)
        # Tablo bulunamazsa (ilk kurulum) gec
        if "no rows" in err.lower() or "pgrst116" in err.lower():
            return {
                "gecerli": False,
                "makine_id": makine_id,
                "lokasyon_id": cfg.get("lokasyon_id", "") if "cfg" in dir() else "",
                "hata": "Lisans bulunamadi. Lutfen yetkili ile iletisime gecin.",
            }
        return {
            "gecerli": False,
            "makine_id": makine_id,
            "lokasyon_id": "",
            "hata": f"Lisans sunucusuna baglanılamadi: {err}",
        }
