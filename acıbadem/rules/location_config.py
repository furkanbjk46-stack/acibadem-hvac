"""
Location Configuration Module
Lokasyon bazlı konfigürasyon yönetimi
"""

import json
from pathlib import Path
from typing import Dict, Optional, Any

class LocationConfig:
    """
    Lokasyon bazlı konfigürasyon yöneticisi
    Her lokasyon için farklı set değerleri ve kurallar
    """
    
    def __init__(self, config_dir: str = "configs"):
        self.config_dir = Path(config_dir)
        self.configs: Dict[str, Dict] = {}
        self.current_location = "hastane_merkez"
        self._load_all_configs()
    
    def _load_all_configs(self):
        """Tüm konfigürasyon dosyalarını yükle"""
        if not self.config_dir.exists():
            print(f"[UYARI] Konfigurasyon dizini bulunamadi: {self.config_dir}")
            return

        for config_file in self.config_dir.glob("*.json"):
            location_id = config_file.stem
            try:
                with open(config_file, 'r', encoding='utf-8') as f:
                    self.configs[location_id] = json.load(f)
                print(f"[OK] Konfigurasyon yuklendi: {location_id}")
            except Exception as e:
                print(f"[HATA] Konfigurasyon yuklenemedi ({location_id}): {e}")

        if not self.configs:
            print("[UYARI] Hic konfigurasyon dosyasi bulunamadi!")
    
    def set_location(self, location_id: str):
        """Aktif lokasyonu değiştir"""
        if location_id not in self.configs:
            print(f"[UYARI] Lokasyon '{location_id}' bulunamadi, varsayilan kullaniliyor")
            if self.configs:
                location_id = list(self.configs.keys())[0]
            else:
                return
        
        self.current_location = location_id
        config = self.configs[location_id]
        print(f"[LOKASYON] Aktif lokasyon: {config.get('location_name', location_id)}")
    
    def get(self, key_path: str, default: Any = None) -> Any:
        """
        Konfigürasyon değeri al
        Örnek: get("rules.fcu.set_min") → 21.0
        """
        if not self.current_location or self.current_location not in self.configs:
            return default
        
        config = self.configs[self.current_location]
        
        # Nokta ile ayrılmış yolu takip et
        keys = key_path.split(".")
        value = config
        
        for key in keys:
            if isinstance(value, dict) and key in value:
                value = value[key]
            else:
                return default
        
        return value
    
    def get_location_name(self) -> str:
        """Aktif lokasyon adını al"""
        if self.current_location and self.current_location in self.configs:
            return self.configs[self.current_location].get("location_name", self.current_location)
        return "Bilinmeyen"


# Global instance
_location_config = None

def get_location_config() -> LocationConfig:
    """Global konfigürasyon instance'ını al"""
    global _location_config
    if _location_config is None:
        _location_config = LocationConfig()
    return _location_config
