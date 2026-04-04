# location_manager.py
# Tek lokasyon yönetimi — Maslak

from __future__ import annotations
import os
import json
import logging
from typing import Dict

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

LOCATION_CONFIG = {
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


class LocationManager:
    """Tek lokasyon yönetimi."""

    def get_active_location_id(self) -> str:
        return "maslak"

    def list_locations(self) -> list:
        return [LOCATION_CONFIG]

    def get_location_config(self, location_id: str = None) -> Dict:
        return LOCATION_CONFIG

    def get_location_dir(self, location_id: str = None) -> str:
        return BASE_DIR

    def get_data_path(self, filename: str, location_id: str = None) -> str:
        return os.path.join(BASE_DIR, filename)

    def ensure_locations_ready(self):
        pass


_manager = None

def get_manager() -> LocationManager:
    global _manager
    if _manager is None:
        _manager = LocationManager()
    return _manager
