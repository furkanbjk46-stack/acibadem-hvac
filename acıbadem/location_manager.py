# location_manager.py
# Çoklu Lokasyon Yönetim Modülü
# Her lokasyonun kendi veri dosyaları, ayarları, raporları ve ML modeli vardır.

from __future__ import annotations
import os
import json
import shutil
import logging
from typing import Dict, List, Optional

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
LOCATIONS_DIR = os.path.join(BASE_DIR, "locations")
ACTIVE_LOCATION_FILE = os.path.join(BASE_DIR, "configs", "active_location.json")

# Lokasyon klasöründe olması gereken alt yapı
_LOCATION_SUBDIRS = ["configs", "daily_reports", "monthly_reports_summary"]
_LOCATION_FILES = {
    "configs/hvac_settings.json": {},
    "configs/maintenance_cards.json": {"cards": []},
    "configs/report_notifications.json": {},
}

# Eski (tek lokasyon) yapıdaki dosyalar → migration için
_LEGACY_FILES = {
    "energy_data.csv": "energy_data.csv",
    "hvac_analysis_history.csv": "hvac_analysis_history.csv",
    "ml_training_data.json": "ml_training_data.json",
    "savings_training_data.json": "savings_training_data.json",
    "configs/hvac_settings.json": "configs/hvac_settings.json",
    "configs/maintenance_cards.json": "configs/maintenance_cards.json",
    "configs/ml_forecast_model.pkl": "configs/ml_forecast_model.pkl",
    "configs/report_notifications.json": "configs/report_notifications.json",
    "configs/hastane_merkez.json": "configs/hastane_merkez.json",
    "configs/ai_features.json": "configs/ai_features.json",
}
_LEGACY_DIRS = {
    "daily_reports": "daily_reports",
    "monthly_reports_summary": "monthly_reports_summary",
}


class LocationManager:
    """Çoklu lokasyon yönetimi."""

    def __init__(self):
        os.makedirs(LOCATIONS_DIR, exist_ok=True)
        os.makedirs(os.path.dirname(ACTIVE_LOCATION_FILE), exist_ok=True)

    # ─── Aktif Lokasyon ───────────────────────────────────

    def get_active_location_id(self) -> str:
        """Aktif lokasyon ID'sini döndür. Varsayılan: maslak."""
        try:
            if os.path.exists(ACTIVE_LOCATION_FILE):
                with open(ACTIVE_LOCATION_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("active", "maslak")
        except Exception:
            pass
        return "maslak"

    def set_active_location(self, location_id: str) -> bool:
        """Aktif lokasyonu değiştir."""
        if location_id not in self.list_location_ids():
            logging.warning(f"Bilinmeyen lokasyon: {location_id}")
            return False
        try:
            with open(ACTIVE_LOCATION_FILE, "w", encoding="utf-8") as f:
                json.dump({"active": location_id}, f, indent=2)
            logging.info(f"Aktif lokasyon değiştirildi: {location_id}")
            return True
        except Exception as e:
            logging.error(f"Lokasyon kaydetme hatası: {e}")
            return False

    # ─── Lokasyon Bilgileri ───────────────────────────────

    def list_location_ids(self) -> List[str]:
        """Mevcut lokasyon ID'lerini döndür."""
        if not os.path.isdir(LOCATIONS_DIR):
            return []
        return sorted([
            d for d in os.listdir(LOCATIONS_DIR)
            if os.path.isdir(os.path.join(LOCATIONS_DIR, d))
            and os.path.exists(os.path.join(LOCATIONS_DIR, d, "location.json"))
        ])

    def list_locations(self) -> List[Dict]:
        """Tüm lokasyonları profil bilgileriyle listele."""
        result = []
        for loc_id in self.list_location_ids():
            config = self.get_location_config(loc_id)
            if config:
                result.append({
                    "id": loc_id,
                    "name": config.get("name", loc_id),
                    "short_name": config.get("short_name", loc_id),
                    "is_master": config.get("is_master", False),
                })
        return result

    def get_location_config(self, location_id: str = None) -> Dict:
        """Lokasyon profil dosyasını (location.json) yükle."""
        loc_id = location_id or self.get_active_location_id()
        config_path = os.path.join(LOCATIONS_DIR, loc_id, "location.json")
        try:
            if os.path.exists(config_path):
                with open(config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
        except Exception as e:
            logging.warning(f"Lokasyon config yükleme hatası ({loc_id}): {e}")
        return {}

    # ─── Dosya Yolları ─────────────────────────────────────

    def get_location_dir(self, location_id: str = None) -> str:
        """Lokasyonun kök klasörünü döndür."""
        loc_id = location_id or self.get_active_location_id()
        return os.path.join(LOCATIONS_DIR, loc_id)

    def get_data_path(self, filename: str, location_id: str = None) -> str:
        """Lokasyon bazlı dosya yolu döndür.
        
        Örnekler:
            get_data_path("energy_data.csv") → locations/maslak/energy_data.csv
            get_data_path("configs/hvac_settings.json") → locations/maslak/configs/hvac_settings.json
        """
        loc_dir = self.get_location_dir(location_id)
        return os.path.join(loc_dir, filename)

    # ─── Lokasyon Oluşturma ────────────────────────────────

    def create_location(self, location_id: str, config: Dict) -> bool:
        """Yeni lokasyon oluştur (klasör yapısı + profil dosyası)."""
        loc_dir = os.path.join(LOCATIONS_DIR, location_id)
        if os.path.exists(loc_dir):
            logging.warning(f"Lokasyon zaten mevcut: {location_id}")
            return False

        try:
            os.makedirs(loc_dir, exist_ok=True)

            # Alt klasörleri oluştur
            for subdir in _LOCATION_SUBDIRS:
                os.makedirs(os.path.join(loc_dir, subdir), exist_ok=True)

            # Varsayılan config dosyalarını oluştur
            for filepath, default_content in _LOCATION_FILES.items():
                full_path = os.path.join(loc_dir, filepath)
                if not os.path.exists(full_path):
                    with open(full_path, "w", encoding="utf-8") as f:
                        json.dump(default_content, f, indent=2, ensure_ascii=False)

            # location.json yaz
            config["id"] = location_id
            with open(os.path.join(loc_dir, "location.json"), "w", encoding="utf-8") as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            logging.info(f"Lokasyon oluşturuldu: {location_id} ({config.get('name', '')})")
            return True
        except Exception as e:
            logging.error(f"Lokasyon oluşturma hatası: {e}")
            return False

    # ─── Legacy Migration ──────────────────────────────────

    def migrate_legacy_data(self) -> bool:
        """Eski tek-lokasyon yapısındaki verileri locations/maslak/ altına taşı.
        
        İlk çalıştırmada çağrılır. Eğer locations/maslak/ zaten varsa
        ve dolu ise tekrar migration yapmaz.
        """
        maslak_dir = os.path.join(LOCATIONS_DIR, "maslak")

        # location.json var VE energy_data.csv var → zaten tamamen taşınmış
        if (os.path.exists(os.path.join(maslak_dir, "location.json"))
            and os.path.exists(os.path.join(maslak_dir, "energy_data.csv"))):
            logging.debug("Migration zaten yapılmış, atlanıyor.")
            return True

        logging.info("Legacy migration başlıyor — mevcut veriler locations/maslak/ altına taşınıyor...")

        # Maslak klasörünü oluştur
        os.makedirs(maslak_dir, exist_ok=True)
        for subdir in _LOCATION_SUBDIRS:
            os.makedirs(os.path.join(maslak_dir, subdir), exist_ok=True)

        migrated_count = 0

        # Dosyaları taşı (kopyala, silme — güvenlik)
        for legacy_rel, target_rel in _LEGACY_FILES.items():
            src = os.path.join(BASE_DIR, legacy_rel)
            dst = os.path.join(maslak_dir, target_rel)
            if os.path.exists(src):
                os.makedirs(os.path.dirname(dst), exist_ok=True)
                if not os.path.exists(dst):
                    shutil.copy2(src, dst)
                    migrated_count += 1
                    logging.info(f"  Migration: {legacy_rel} → locations/maslak/{target_rel}")

        # Klasörleri kopyala
        for legacy_dir, target_dir in _LEGACY_DIRS.items():
            src_dir = os.path.join(BASE_DIR, legacy_dir)
            dst_dir = os.path.join(maslak_dir, target_dir)
            if os.path.isdir(src_dir) and not os.path.exists(dst_dir):
                shutil.copytree(src_dir, dst_dir)
                migrated_count += 1
                logging.info(f"  Migration: {legacy_dir}/ → locations/maslak/{target_dir}/")

        # Maslak location.json oluştur
        maslak_config = {
            "id": "maslak",
            "name": "Acıbadem Maslak Hastanesi",
            "short_name": "Maslak",
            "is_master": True,
            "energy_schema": {
                "heating_lines": ["MAS-1", "MAS-2"],
                "fields_per_line": ["heating_temp", "boiler_temp", "cooling_temp"],
                "labels": {
                    "MAS-1": "Mas-1",
                    "MAS-2": "Mas-2"
                }
            },
            "csv_columns": {
                "heating_temp_cols": [
                    "Mas1_Isitma_Temp_C", "Mas1_Kazan_Temp_C", "Mas1_Sogutma_Temp_C",
                    "Mas2_Isitma_Temp_C", "Mas2_Kazan_Temp_C", "Mas2_Sogutma_Temp_C"
                ]
            }
        }
        config_path = os.path.join(maslak_dir, "location.json")
        if not os.path.exists(config_path):
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(maslak_config, f, indent=2, ensure_ascii=False)

        logging.info(f"Legacy migration tamamlandı: {migrated_count} öğe taşındı.")
        return True

    def ensure_locations_ready(self):
        """Sunucu başlangıcında çağrılır: migration + altunizade profili oluştur."""
        # 1. Maslak migration
        self.migrate_legacy_data()

        # 2. Altunizade profili yoksa oluştur
        if "altunizade" not in self.list_location_ids():
            altunizade_config = {
                "name": "Acıbadem Altunizade Hastanesi",
                "short_name": "Altunizade",
                "is_master": False,
                "energy_schema": {
                    "heating_lines": [],
                    "fields_per_line": [],
                    "labels": {},
                    "single_fields": ["heating_temp", "boiler_temp", "cooling_temp"],
                    "single_labels": {
                        "heating_temp": "Isıtma Temp",
                        "boiler_temp": "Kazan Temp",
                        "cooling_temp": "Soğutma Temp"
                    }
                },
                "csv_columns": {
                    "heating_temp_cols": [
                        "Isitma_Temp_C", "Kazan_Temp_C", "Sogutma_Temp_C"
                    ]
                }
            }
            self.create_location("altunizade", altunizade_config)

        # Aktif lokasyon dosyası yoksa varsayılan yaz
        if not os.path.exists(ACTIVE_LOCATION_FILE):
            self.set_active_location("maslak")


# Modül seviyesi singleton
_manager = None

def get_manager() -> LocationManager:
    """Tekil LocationManager instance."""
    global _manager
    if _manager is None:
        _manager = LocationManager()
    return _manager
