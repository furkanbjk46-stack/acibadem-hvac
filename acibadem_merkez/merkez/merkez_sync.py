# merkez_sync.py
# Supabase'den tüm lokasyon verilerini çeker

import json
import os
import logging
import pandas as pd
from datetime import datetime

logger = logging.getLogger(__name__)
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "configs", "merkez_config.json")


def load_config():
    if not os.path.exists(CONFIG_FILE):
        return None
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_client(config):
    try:
        from supabase import create_client
        url = config["supabase_url"]
        key = config["supabase_key"]
        if "BURAYA" in url or "BURAYA" in key:
            return None
        return create_client(url, key)
    except Exception as e:
        logger.error(f"Supabase bağlantı hatası: {e}")
        return None


def fetch_energy_data(client, lokasyon_id: str = None) -> pd.DataFrame:
    """Supabase'den enerji verilerini çek"""
    try:
        query = client.table("energy_data").select("*")
        if lokasyon_id:
            query = query.eq("lokasyon_id", lokasyon_id)
        result = query.order("Tarih", desc=False).execute()
        
        if result.data:
            df = pd.DataFrame(result.data)
            if "Tarih" in df.columns:
                df["Tarih"] = pd.to_datetime(df["Tarih"], errors="coerce")
            return df
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"Enerji verisi çekme hatası: {e}")
        return pd.DataFrame()


def fetch_lokasyon_bilgileri(client) -> list:
    """Tüm lokasyon bilgilerini çek"""
    try:
        result = client.table("lokasyonlar").select("*").execute()
        return result.data if result.data else []
    except Exception as e:
        logger.error(f"Lokasyon bilgisi çekme hatası: {e}")
        return []


def fetch_hvac_summary(client, lokasyon_id: str = None) -> pd.DataFrame:
    """HVAC özet verilerini çek"""
    try:
        query = client.table("hvac_summary").select("*")
        if lokasyon_id:
            query = query.eq("lokasyon_id", lokasyon_id)
        result = query.execute()
        
        if result.data:
            return pd.DataFrame(result.data)
        return pd.DataFrame()
    except Exception as e:
        logger.error(f"HVAC verisi çekme hatası: {e}")
        return pd.DataFrame()
