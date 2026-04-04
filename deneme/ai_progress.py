# ai_progress.py
# Yapay Zeka / Makine Öğrenmesi İlerleme Hesaplayıcı
# Dashboard'da gösterilecek AI olgunluk seviyesini hesaplar.

import os
import json
import logging
from datetime import datetime

# Dosya yolları (lokasyon bazlı + fallback)
_BASE = os.path.dirname(__file__)
try:
    from location_manager import get_manager as _get_loc_mgr
    _lm = _get_loc_mgr()
    _ENERGY_CSV = _lm.get_data_path("energy_data.csv")
    _SETTINGS_FILE = _lm.get_data_path("configs/hvac_settings.json")
    _TRAINING_FILE = _lm.get_data_path("savings_training_data.json")
    _ML_TRAINING_FILE = _lm.get_data_path("ml_training_data.json")
    _AI_FEATURES_FILE = _lm.get_data_path("configs/ai_features.json")
except Exception:
    _ENERGY_CSV = os.path.join(_BASE, "energy_data.csv")
    _SETTINGS_FILE = os.path.join(_BASE, "configs", "hvac_settings.json")
    _TRAINING_FILE = os.path.join(_BASE, "savings_training_data.json")
    _ML_TRAINING_FILE = os.path.join(_BASE, "ml_training_data.json")
    _AI_FEATURES_FILE = os.path.join(_BASE, "configs", "ai_features.json")

# ─── Varsayılan AI Özellik Durumları ───
_DEFAULT_FEATURES = {
    "rule_engine":          {"name": "Kural Bazlı Öneri Motoru",    "active": True,  "points": 8},
    "yoy_comparison":       {"name": "YoY Karşılaştırma",           "active": True,  "points": 4},
    "anomaly_detection":    {"name": "Anomali Tespiti",             "active": True,  "points": 4},
    "ahu_capacity":         {"name": "AHU Kapasite Analizi",        "active": True,  "points": 4},
    "cost_analysis":        {"name": "Maliyet Hesaplama",           "active": True,  "points": 3},
    "hvac_sat_analysis":    {"name": "HVAC SAT/Mode Analizi",       "active": True,  "points": 4},
    "maintenance_cards":    {"name": "Bakım Kartı Entegrasyonu",    "active": True,  "points": 3},
    # İleri AI (henüz aktif değil)
    "statistical_anomaly":  {"name": "İstatistiksel Anomali",       "active": False, "points": 5},
    "weather_api":          {"name": "Hava Durumu API",             "active": False, "points": 5},
    "prediction_model":     {"name": "Tüketim Tahmin Modeli",       "active": False, "points": 5},
    "feedback_filtering":   {"name": "Geri Bildirim Filtresi",      "active": False, "points": 5},
}


def _count_energy_data_days() -> int:
    """energy_data.csv'deki benzersiz gün sayısını döner."""
    try:
        if not os.path.exists(_ENERGY_CSV):
            return 0
        import pandas as pd
        df = pd.read_csv(_ENERGY_CSV)
        if "Tarih" in df.columns:
            return df["Tarih"].nunique()
        return len(df)
    except Exception:
        return 0


def _count_feedback() -> int:
    """Toplam geri bildirim (kabul + red) sayısını döner."""
    total = 0
    for fpath in [_TRAINING_FILE, _ML_TRAINING_FILE]:
        try:
            if os.path.exists(fpath):
                with open(fpath, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    total += len(data)
                elif isinstance(data, dict):
                    total += sum(len(v) if isinstance(v, list) else 1 for v in data.values())
        except Exception:
            pass
    return total


def _get_features() -> dict:
    """Aktif AI özelliklerini döner. ai_features.json varsa onu kullanır."""
    features = dict(_DEFAULT_FEATURES)
    try:
        if os.path.exists(_AI_FEATURES_FILE):
            with open(_AI_FEATURES_FILE, "r", encoding="utf-8") as f:
                overrides = json.load(f)
            for key, val in overrides.items():
                if key in features:
                    features[key]["active"] = val.get("active", features[key]["active"])
    except Exception:
        pass
    return features


def calculate_ai_progress() -> dict:
    """
    AI ilerleme skorunu hesaplar.
    
    Returns:
        dict: {
            "total_score": int (0-100),
            "level": str,
            "level_emoji": str,
            "categories": {
                "data_maturity": {"score": int, "max": 25, "detail": str},
                "feedback": {"score": int, "max": 25, "detail": str},
                "feature_maturity": {"score": int, "max": 30, "detail": str},
                "advanced_ai": {"score": int, "max": 20, "detail": str},
            },
            "features": dict,
            "next_milestone": str
        }
    """
    
    # ─── 1. Veri Olgunluğu (max %25) ───
    days = _count_energy_data_days()
    if days >= 365:
        data_score = 25
    elif days >= 180:
        data_score = 20
    elif days >= 90:
        data_score = 15
    elif days >= 30:
        data_score = 10
    elif days > 0:
        data_score = 5
    else:
        data_score = 0
    
    if days < 30:
        data_detail = f"{days} gün veri → 30 güne ulaşınca +5%"
    elif days < 90:
        data_detail = f"{days} gün veri → 90 güne ulaşınca +5%"
    elif days < 180:
        data_detail = f"{days} gün veri → 180 güne ulaşınca +5%"
    elif days < 365:
        data_detail = f"{days} gün veri → 365 güne ulaşınca +5%"
    else:
        data_detail = f"{days} gün veri ✓ Maksimum seviye"
    
    # ─── 2. Geri Bildirim (max %25) ───
    fb_count = _count_feedback()
    if fb_count >= 100:
        fb_score = 25
    elif fb_count >= 50:
        fb_score = 20
    elif fb_count >= 30:
        fb_score = 15
    elif fb_count >= 10:
        fb_score = 10
    elif fb_count >= 1:
        fb_score = 5
    else:
        fb_score = 0
    
    if fb_count == 0:
        fb_detail = "Henüz geri bildirim yok → İlk öneriyi değerlendirin"
    elif fb_count < 10:
        fb_detail = f"{fb_count} geri bildirim → 10'a ulaşınca +5%"
    elif fb_count < 30:
        fb_detail = f"{fb_count} geri bildirim → 30'a ulaşınca +5%"
    elif fb_count < 50:
        fb_detail = f"{fb_count} geri bildirim → 50'ye ulaşınca +5%"
    elif fb_count < 100:
        fb_detail = f"{fb_count} geri bildirim → 100'e ulaşınca +5%"
    else:
        fb_detail = f"{fb_count} geri bildirim ✓ Maksimum seviye"
    
    # ─── 3. Özellik Olgunluğu (max %30) ───
    features = _get_features()
    # Temel özellikler (ilk 7, max 30 puan)
    basic_features = {k: v for k, v in features.items() 
                      if k not in ("statistical_anomaly", "weather_api", "prediction_model", "feedback_filtering")}
    feat_score = sum(f["points"] for f in basic_features.values() if f["active"])
    feat_total = sum(f["points"] for f in basic_features.values())
    active_count = sum(1 for f in basic_features.values() if f["active"])
    total_count = len(basic_features)
    feat_detail = f"{active_count}/{total_count} özellik aktif"
    
    # ─── 4. İleri AI (max %20) ───
    adv_features = {k: v for k, v in features.items() 
                    if k in ("statistical_anomaly", "weather_api", "prediction_model", "feedback_filtering")}
    adv_score = sum(f["points"] for f in adv_features.values() if f["active"])
    adv_active = sum(1 for f in adv_features.values() if f["active"])
    adv_total = len(adv_features)
    adv_detail = f"{adv_active}/{adv_total} ileri özellik aktif" if adv_active > 0 else "Henüz ileri AI özelliği aktif değil"
    
    # ─── Toplam Skor ───
    total = data_score + fb_score + feat_score + adv_score
    
    # ─── Seviye Belirleme ───
    if total >= 80:
        level, emoji = "Otonom", "🤖"
    elif total >= 60:
        level, emoji = "İleri", "🚀"
    elif total >= 40:
        level, emoji = "Olgun", "🧠"
    elif total >= 20:
        level, emoji = "Gelişen", "📈"
    else:
        level, emoji = "Başlangıç", "🌱"
    
    # ─── Sonraki Hedef ───
    milestones = [
        (20, "Gelişen seviyeye ulaş"),
        (40, "Olgun seviyeye ulaş"),
        (60, "İleri seviyeye ulaş"),
        (80, "Otonom seviyeye ulaş"),
        (100, "Maksimum AI olgunluğu"),
    ]
    next_milestone = "Sistem tam olgunluğa ulaştı! 🏆"
    for threshold, desc in milestones:
        if total < threshold:
            next_milestone = f"%{threshold} → {desc} (kalan: %{threshold - total})"
            break
    
    return {
        "total_score": total,
        "level": level,
        "level_emoji": emoji,
        "categories": {
            "data_maturity": {"score": data_score, "max": 25, "detail": data_detail, "icon": "📊"},
            "feedback": {"score": fb_score, "max": 25, "detail": fb_detail, "icon": "💬"},
            "feature_maturity": {"score": feat_score, "max": 30, "detail": feat_detail, "icon": "⚙️"},
            "advanced_ai": {"score": adv_score, "max": 20, "detail": adv_detail, "icon": "🚀"},
        },
        "features": features,
        "data_days": days,
        "feedback_count": fb_count,
        "next_milestone": next_milestone,
    }
