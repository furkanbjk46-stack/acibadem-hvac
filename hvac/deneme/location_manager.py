# location_manager.py
# Lokasyon yönetimi — bu PC'nin lokasyonu (kimlik, ad, ısıtma hatları ayar/ dosyalarından; Faz 1)

from __future__ import annotations
import yollar  # dosya yolları (ayar/ durum/ veri/; Faz 1)
import os
import json
import logging
from typing import Dict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

def lokasyon_konfig(base_dir: str = None) -> Dict:
    """Lokasyon yapılandırması — KODDA DEĞİL (Faz 1, 12.11.2026): kimlik ve ad ayar/lokasyon_profili.json'dan,
    ısıtma hatları ayar/bacnet_esleme.json'dan. Eskiden burada Maslak sabitti (MAS-1 / MAS-2)."""
    import bacnet_esleme
    p = profil(base_dir)
    hatlar = bacnet_esleme.hatlar(base_dir or BASE_DIR)
    lok = lokasyon_id(base_dir)
    ad = p.get("ad") or lok
    # Ekran adı: profilde tam_ad varsa o; yoksa "Acibadem Maslak" → "Acıbadem Maslak Hastanesi"
    # (Maslak'ın profili yama ile değiştirilemez; başlık eskisiyle aynı kalsın).
    tam_ad = p.get("tam_ad") or ad.replace("Acibadem", "Acıbadem")
    if not p.get("tam_ad") and tam_ad and "Hastane" not in tam_ad:
        tam_ad += " Hastanesi"
    return {
        "id": lok,
        "name": tam_ad,
        "short_name": p.get("kisa_ad") or ad.replace("Acibadem ", "").replace("Acıbadem ", ""),
        "is_master": True,
        "energy_schema": {
            "heating_lines": [h["ad"] for h in hatlar],
            "fields_per_line": ["heating_temp", "boiler_temp", "cooling_temp"],
            "labels": {h["ad"]: h.get("etiket") or h["ad"] for h in hatlar},
            "lines": hatlar,
        },
        "csv_columns": {"heating_temp_cols": bacnet_esleme.hat_sutunlari(base_dir or BASE_DIR)},
    }


class LocationManager:
    """Tek lokasyon yönetimi."""

    def get_active_location_id(self) -> str:
        return lokasyon_id()

    def list_locations(self) -> list:
        return [lokasyon_konfig()]

    def get_location_config(self, location_id: str = None) -> Dict:
        return lokasyon_konfig()

    def get_location_dir(self, location_id: str = None) -> str:
        return BASE_DIR

    def get_data_path(self, filename: str, location_id: str = None) -> str:
        # Dosyanın geçerli yeri: ayar/ durum/ veri/ katmanları (yollar.py, Faz 1)
        return yollar.yol(filename, BASE_DIR)

    def ensure_locations_ready(self):
        pass


# ── Lokasyon kimliği: TEK KAYNAK ayar/lokasyon_profili.json (Faz 1, 12.11.2026) ──────────────
# Kimlik eskiden 9 ayrı yerde bağlantı dosyasından (supabase_config.json) okunuyordu. Bağlantı
# dosyası yalnızca sunucu adresi ve anahtar içindir; lokasyon kimliği lokasyon profilindedir.
# Profil yoksa ya da kimlik boşsa (eski kurulum) bağlantı dosyasındaki değer kullanılır.
_PROFIL_ONBELLEK = {}


def profil(base_dir: str = None) -> dict:
    """ayar/lokasyon_profili.json içeriği (yoksa {}). Dosya değişince yeniden okunur."""
    p = yollar.yol("configs/lokasyon_profili.json", base_dir or BASE_DIR)
    try:
        _st = os.stat(p)                     # aynı saniyede yapılan düzenleme de görülsün
        anahtar = (p, _st.st_mtime_ns, _st.st_size)
    except OSError:
        return {}
    if _PROFIL_ONBELLEK.get("anahtar") != anahtar:
        try:
            with open(p, encoding="utf-8-sig") as f:
                veri = json.load(f)
        except Exception:
            veri = {}
        _PROFIL_ONBELLEK.update(anahtar=anahtar, veri=veri if isinstance(veri, dict) else {})
    return dict(_PROFIL_ONBELLEK["veri"])


def lokasyon_id(base_dir: str = None, yedek: str = None) -> str:
    """Bu PC'nin lokasyon kimliği: profil → (verildiyse) yedek → bağlantı dosyası → ''."""
    lok = str(profil(base_dir).get("lokasyon_id") or "").strip()
    if lok:
        return lok
    if yedek:
        return str(yedek).strip()
    try:
        with open(yollar.yol("supabase_config.json", base_dir or BASE_DIR), encoding="utf-8-sig") as f:
            return str(json.load(f).get("lokasyon_id") or "").strip()
    except Exception:
        return ""


_manager = None

def get_manager() -> LocationManager:
    global _manager
    if _manager is None:
        _manager = LocationManager()
    return _manager
