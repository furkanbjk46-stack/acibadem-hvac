
import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
import csv, io, os, datetime, uuid, logging, json, shutil
import pandas as pd
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass, asdict
from enum import Enum

# Saha tecrübesi kuralları
from rules.temperature_cascade import check_field_experience_rules
from rules.location_config import get_location_config


# ================ KONFİGÜRASYON ================
class EngineVersion(Enum):
    V1 = "v1"
    V2 = "v2"

class EquipmentType(Enum):
    AHU = "AHU"
    CHILLER = "CHILLER"
    FCU = "FCU"
    COLLECTOR = "COLLECTOR"
    HEAT_EXCHANGER = "HEAT_EXCHANGER"
    OTHER = "OTHER"

class StatusSeverity(Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    OPTIMAL = "OPTIMAL"
    MISSING_DATA = "MISSING_DATA"

# Konfigürasyon değerleri
CONFIG = {
    "APP_TITLE": "HVAC ΔT Öneri Motoru — Engine v2",
    
    # Hedef ΔT değerleri
    "TARGET_DT_AHU": 5.0,
    "TARGET_DT_CHILLER": 3.0,
    "TARGET_DT_FCU": 4.0,
    "TARGET_DT_COLLECTOR": 3.0,
    "TARGET_DT_HEAT_EXCHANGER": 8.0,
    "TARGET_DT_DEFAULT": 5.0,
    "TARGET_DT_HEAT": 25.0,
    
    # Toleranslar
    "TOLERANCE_CRITICAL": 1.0,
    "TOLERANCE_NORMAL": 3.0,
    
    # SAT analiz eşikleri
    "SAT_COOLING_THRESHOLD": 1.0,
    "SAT_HEATING_THRESHOLD": 1.0,
    "SAT_COOLING_MIN": 15.0,  # Soğutma için minimum SAT
    "SAT_COOLING_MAX": 18.0,  # Soğutma için maksimum SAT
    "SAT_HEATING_MIN": 28.0,  # Isıtma için minimum SAT
    "SAT_HEATING_MAX": 31.0,  # Isıtma için maksimum SAT
    "COMFORT_DEPARTURE": 3.0,
    
    # Skorlama parametreleri
    "SCORE_DEPARTURE_WEIGHT": 1.5,
    "SCORE_LOW_DT_BONUS": 4.0,
    "SCORE_COMFORT_PENALTY": 2.0,
    "SCORE_CRITICAL_THRESHOLD": 7.0,
    
    # Approach analizi
    "APPROACH_WARNING_THRESHOLD": 2.5,
    "APPROACH_MAX": 10.0,  # 7.0'dan 10.0'a yükseltildi - false positive azaltmak için
    
    # Low ΔT sendromu eşikleri
    "LOW_DT_THRESHOLD": 3.0,
    "HIGH_VALVE_THRESHOLD": 90,
    "VALVE_SIMUL_THRESHOLD": 5,
    
    # Chiller teşhis eşikleri
    "CHILLER_BYPASS_DT": 1.0,
    "CHILLER_LOW_DT_THRESHOLD": 3.0,
    
    # Isıtma teşhis eşikleri
    "HEAT_EFF_LOW_THRESHOLD": 20.0,
    "HEAT_SAT_LOW_THRESHOLD": 28.0,
    
    # OAT bias
    "OAT_BIAS_MAX": 0.5,
    
    # Plant collector patterns
    "PLANT_COLLECTOR_PATTERNS": ["ana", "main", "header", "kollekt", "collector", "primary", "primer"],
    
    # Bina bilgileri
    "BUILDING_AREA_M2": 0,  # Hastane toplam alan (m²) - 0 ise m² bazlı metrikler gösterilmez
    
    # Birim fiyatlar (0 ise maliyet gösterilmez)
    "UNIT_PRICE_ELECTRICITY": 0,  # TL/kWh
    "UNIT_PRICE_GAS": 0,          # TL/m³
    "UNIT_PRICE_WATER": 0,        # TL/m³
    
    # Rapor zamanlayıcı ayarları
    "DAILY_REPORT_HOUR": 17,      # Günlük rapor saati (0-23)
    "DAILY_REPORT_MINUTE": 0,     # Günlük rapor dakikası (0-59)
    "MONTHLY_REPORT_DAY": 5,      # Aylık rapor günü (1-28)
    "MONTHLY_REPORT_HOUR": 17,    # Aylık rapor saati (0-23)
}

# ================ AYAR YÖNETİMİ ================
# Eski hardcoded yollar — geriye uyumluluk için tutuluyor
# Yeni kod _get_settings_file() / _get_maintenance_file() kullanmalı
SETTINGS_FILE = os.path.join(os.path.dirname(__file__), "configs", "hvac_settings.json")
MAINTENANCE_FILE = os.path.join(os.path.dirname(__file__), "configs", "maintenance_cards.json")
DEFAULT_CONFIG = CONFIG.copy()  # Varsayılan ayarları sakla

def _get_settings_file(location_id: str = None) -> str:
    """Ayar dosyası yolunu döndür."""
    return os.path.join(os.path.dirname(__file__), "configs", "hvac_settings.json")

def _get_maintenance_file(location_id: str = None) -> str:
    """Bakım kartı dosyası yolunu döndür."""
    return os.path.join(os.path.dirname(__file__), "configs", "maintenance_cards.json")

def _get_daily_reports_dir(location_id: str = None) -> str:
    """Günlük rapor klasörü yolunu döndür."""
    path = os.path.join(os.path.dirname(__file__), "daily_reports")
    os.makedirs(path, exist_ok=True)
    return path

def _get_monthly_reports_dir(location_id: str = None) -> str:
    """Aylık rapor klasörü yolunu döndür."""
    path = os.path.join(os.path.dirname(__file__), "monthly_reports_summary")
    os.makedirs(path, exist_ok=True)
    return path

# ================ BAKIM KARTI YÖNETİMİ ================
MAINTENANCE_COMPONENTS = [
    "heating_valve_body", "heating_valve_signal",
    "cooling_valve_body", "cooling_valve_signal",
    "supply_sensor", "return_sensor"
]
MAINTENANCE_STATUSES = ["OK", "FAULTY", "MAINTENANCE", "N/A"]
MAINTENANCE_LABELS = {
    "heating_valve_body": "Isıtma Vanası Gövde",
    "heating_valve_signal": "Isıtma Vanası 0-10V",
    "cooling_valve_body": "Soğutma Vanası Gövde",
    "cooling_valve_signal": "Soğutma Vanası 0-10V",
    "supply_sensor": "Üfleme Sensör",
    "return_sensor": "Emiş Sensör"
}

def load_maintenance_cards() -> dict:
    """Bakım kartlarını JSON dosyasından yükle."""
    try:
        if os.path.exists(MAINTENANCE_FILE):
            with open(MAINTENANCE_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        print(f"Bakım kartı yükleme hatası: {e}")
    return {"last_updated": None, "updated_by": None, "cards": {}}

def save_maintenance_cards(data: dict) -> bool:
    """Bakım kartlarını JSON dosyasına kaydet."""
    try:
        os.makedirs(os.path.dirname(MAINTENANCE_FILE), exist_ok=True)
        with open(MAINTENANCE_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Bakım kartı kaydetme hatası: {e}")
        return False

def get_maintenance_card(equipment_name: str) -> dict:
    """Tek bir cihazın bakım kartını getir. Yoksa tüm bileşenler OK döner."""
    data = load_maintenance_cards()
    card = data.get("cards", {}).get(equipment_name, None)
    if card is None:
        return {comp: "OK" for comp in MAINTENANCE_COMPONENTS}
    return card

def get_maintenance_notes(equipment_name: str) -> list:
    """Arızalı/bakımdaki bileşenler için analiz notları üret."""
    card = get_maintenance_card(equipment_name)
    notes = []
    for comp in MAINTENANCE_COMPONENTS:
        status = card.get(comp, "OK")
        label = MAINTENANCE_LABELS.get(comp, comp)
        if status == "FAULTY":
            notes.append(f"🔴 {label}: ARIZALI - Bu bileşenle ilgili veriler güvenilmez")
        elif status == "MAINTENANCE":
            notes.append(f"🟡 {label}: BAKIMDA")
    return notes

def load_settings_from_file():
    """JSON dosyasından ayarları yükle."""
    global CONFIG
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
                saved_settings = json.load(f)
                # Sadece mevcut CONFIG anahtarlarını güncelle
                for key in saved_settings:
                    if key in CONFIG:
                        CONFIG[key] = saved_settings[key]
            logging.debug(f"Ayarlar yüklendi: {SETTINGS_FILE}")
    except Exception as e:
        logging.warning(f"Ayarlar yüklenirken hata: {e}")

def save_settings_to_file(new_settings: dict):
    """Ayarları JSON dosyasına kaydet."""
    global CONFIG
    try:
        # Zamanlayıcı anahtarları değişti mi kontrol et
        timer_keys = {"DAILY_REPORT_HOUR", "DAILY_REPORT_MINUTE", "MONTHLY_REPORT_DAY", "MONTHLY_REPORT_HOUR"}
        timer_changed = any(
            key in new_settings and float(new_settings[key]) != float(CONFIG.get(key, 0))
            for key in timer_keys
            if key in new_settings
        )
        
        # CONFIG'i güncelle
        for key, value in new_settings.items():
            if key in CONFIG:
                CONFIG[key] = value
        
        # Dosyaya kaydet
        os.makedirs(os.path.dirname(SETTINGS_FILE), exist_ok=True)
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump({k: v for k, v in CONFIG.items() if not isinstance(v, list)}, f, indent=2, ensure_ascii=False)
        logging.info(f"Ayarlar kaydedildi: {SETTINGS_FILE}")
        
        # Zamanlayıcı ayarları değiştiyse yeniden zamanla
        if timer_changed:
            logging.info(f"Zamanlayıcı ayarları değişti, yeniden zamanlama yapılacak...")
            _resched_fn = globals().get("_reschedule_all_timers")
            if _resched_fn and callable(_resched_fn):
                try:
                    _resched_fn()
                    logging.info("Zamanlayıcılar başarıyla yeniden zamanlandı.")
                except Exception as e:
                    logging.error(f"Zamanlayıcı yeniden başlatma hatası: {e}")
            else:
                logging.warning("_reschedule_all_timers henüz tanımlı değil")
        
        return True
    except Exception as e:
        logging.error(f"Ayarlar kaydedilirken hata: {e}")
        return False

def reset_settings_to_default():
    """Ayarları varsayılana döndür."""
    global CONFIG
    CONFIG = DEFAULT_CONFIG.copy()
    save_settings_to_file(CONFIG)
    return True

# Başlangıçta ayarları yükle
load_settings_from_file()

# ================ OPERATÖR TALİMAT REHBERİ ================
INSTRUCTION_GUIDE = {
    "NOT_COOLING": {
        "severity": "CRITICAL",
        "score": 8.0,
        "title": "Üfleme Soğutmuyor",
        "description": "Üfleme sıcaklığı (SAT) oda sıcaklığından yüksek. Sistem soğutma yapamıyor.",
        "steps": [
            "Üfleme sıcaklığını kontrol edin - oda sıcaklığından düşük olmalı",
            "Soğutma vanası açık mı kontrol edin",
            "Su sıcaklığını kontrol edin - yeterince soğuk mu?",
            "Chiller çalışıyor mu kontrol edin",
            "Coil temiz mi kontrol edin",
            "Fan çalışıyor mu ve yeterli devirde mi?",
            "Setpoint'leri kontrol edin - çok yüksek olabilir"
        ],
        "causes": [
            "Soğutma vanası kapalı",
            "Chiller çalışmıyor",
            "Su sıcaklığı çok yüksek",
            "Coil kirli",
            "Fan arızası",
            "Setpoint çok yüksek"
        ]
    },
    "NOT_HEATING": {
        "severity": "CRITICAL",
        "score": 8.0,
        "title": "Üfleme Isıtmıyor",
        "description": "Üfleme sıcaklığı (SAT) oda sıcaklığından düşük. Sistem ısıtma yapamıyor.",
        "steps": [
            "Üfleme sıcaklığını kontrol edin - oda sıcaklığından yüksek olmalı",
            "Isıtma vanası açık mı kontrol edin",
            "Su sıcaklığını kontrol edin - yeterince sıcak mı?",
            "Kazan/ısıtıcı çalışıyor mu kontrol edin",
            "Coil temiz mi kontrol edin",
            "Fan çalışıyor mu ve yeterli devirde mi?",
            "Setpoint'leri kontrol edin - çok düşük olabilir"
        ],
        "causes": [
            "Isıtma vanası kapalı",
            "Kazan çalışmıyor",
            "Su sıcaklığı çok düşük",
            "Coil kirli veya havası var",
            "Fan arızası",
            "Setpoint çok düşük"
        ]
    },
    "SIMUL_HEAT_COOL": {
        "severity": "CRITICAL",
        "score": 10.0,
        "title": "Eşzamanlı Isıtma + Soğutma",
        "description": "Soğutma ve ısıtma vanaları aynı anda açık (her ikisi de ≥5%). Bu enerji israfı ve kontrol sistemi arızasıdır.",
        "steps": [
            "BMS kontrol panelinde ekipmanın modunu kontrol edin",
            "Soğutma veya ısıtma modlarından birini devre dışı bırakın",
            "Otomasyon programını kontrol edin - mod geçişi hatası olabilir",
            "Vana aktüatörlerini manuel test edin - sıkışma olabilir",
            "Sensör kalibrasyonunu kontrol edin"
        ],
        "causes": [
            "BMS programlama hatası",
            "Mod geçiş arızası (yaz/kış)",
            "Vana aktüatörü arızası",
            "Oda termostatı arızası"
        ]
    },
    "CHILLER_BYPASS": {
        "severity": "CRITICAL",
        "score": 9.0,
        "title": "Chiller Bypass / Arıza",
        "description": "Chiller ΔT < 1.0°C. Chiller çalışıyor gibi görünüyor ama su soğutmuyor.",
        "steps": [
            "Chiller bypass vanasını kontrol edin - kapalı olmalı",
            "Kompresör çalışıyor mu? Akım değerlerini okuyun",
            "Evaporatör giriş/çıkış sıcaklıklarını manuel termometre ile doğrulayın",
            "Chiller alarm panelini kontrol edin",
            "Soğutucu gaz basınçlarını kontrol edin",
            "Gerekirse chilleri durdurun ve yedek chillera geçin"
        ],
        "causes": [
            "Bypass vanası açık kalmış",
            "Kompresör arızası",
            "Soğutucu gaz kaçağı",
            "Evaporatör tıkanıklığı",
            "Sensör arızası"
        ]
    },
    "LOW_FLOW_DETECTED": {
        "severity": "CRITICAL",
        "score": 8.0,
        "title": "Düşük Debi / Pompa Basıncı",
        "description": "Su tarafı ΔT yüksek (≥25°C) ama üfleme sıcaklığı düşük (<28°C). Su yeterince akmıyor.",
        "steps": [
            "Pompa çalışıyor mu? Akım değerini kontrol edin",
            "Pompa basınç göstergelerini okuyun (giriş/çıkış)",
            "Filtre diferansiyel basıncını kontrol edin - tıkanık olabilir",
            "Balans vanalarını kontrol edin - kapalı olabilir",
            "Hava tutma olabilir - havalandırma vanalarını açın",
            "Debi ölçer varsa okumayı kontrol edin"
        ],
        "causes": [
            "Pompa arızası veya düşük devir",
            "Filtre tıkanıklığı",
            "Balans vanası kapalı",
            "Sistemde hava",
            "Boru tıkanıklığı"
        ]
    },
    "HEAT_EFF_LOW": {
        "severity": "CRITICAL",
        "score": 7.0,
        "title": "Isıtma Etkisi Düşük",
        "description": "Isıtma vanası çok açık (≥90%) ama üfleme havası soğuk (<28°C).",
        "steps": [
            "AHU SAT setpoint'i yükseltin (örn. 30-35°C)",
            "Kolektör/Transfer gidiş setpoint'i yükseltin",
            "Kazan setpoint'i yükseltin",
            "Kazan çalışıyor mu ve hedef sıcaklıkta mı kontrol edin",
            "Isıtma suyu sıcaklığını manuel termometre ile doğrulayın",
            "Isıtma vanası gerçekten açık mı? Manuel kontrol edin",
            "Coil'de hava olabilir - havalandırın",
            "Pompa debisini kontrol edin"
        ],
        "causes": [
            "Setpoint'ler çok düşük ayarlanmış",
            "Kazan arızası veya düşük sıcaklık",
            "Isıtma vanası arızası",
            "Coil'de hava",
            "Düşük debi"
        ],
        "setpoint_chain": "Kazan (70-80°C) → Kolektör (50-60°C) → AHU SAT (30-35°C) → Oda (20-22°C)"
    },
    "COOL_EFF_LOW": {
        "severity": "CRITICAL",
        "score": 7.0,
        "title": "Soğutma Etkisi Düşük",
        "description": "Soğutma vanası çok açık (≥90%) ama üfleme havası sıcak (approach >7°C).",
        "steps": [
            "AHU SAT setpoint'i düşürün (örn. 12-14°C)",
            "Kolektör/Transfer gidiş setpoint'i düşürün",
            "Chiller setpoint'i düşürün (örn. 6-7°C)",
            "Chiller çalışıyor mu ve hedef sıcaklıkta mı kontrol edin",
            "Soğutma suyu sıcaklığını manuel termometre ile doğrulayın",
            "Soğutma vanası gerçekten açık mı? Manuel kontrol edin",
            "Coil kirli olabilir - temizlik planlayın",
            "Pompa debisini kontrol edin"
        ],
        "causes": [
            "Setpoint'ler çok yüksek ayarlanmış",
            "Chiller yetersiz kapasitede",
            "Soğutma vanası arızası",
            "Coil kirliliği",
            "Düşük debi"
        ],
        "setpoint_chain": "Chiller (6-7°C) → Kolektör (8-10°C) → AHU SAT (12-14°C) → Oda (22-24°C)"
    },
    "CHILLER_LOW_DT": {
        "severity": "WARNING",
        "score": 6.0,
        "title": "Düşük ΔT Sendromu (Chiller)",
        "description": "Chiller ΔT < 3.0°C. Chiller çalışıyor ama verimli değil.",
        "steps": [
            "Chiller yükünü kontrol edin - çok düşük yükte çalışıyor olabilir",
            "Primer pompa debisini azaltın (VFD varsa)",
            "Bypass vanası kısmen açık olabilir - kontrol edin",
            "Chiller setpoint'i kontrol edin",
            "Evaporatör temizliği gerekebilir",
            "Birden fazla chiller varsa, bir tanesini kapatın"
        ],
        "causes": [
            "Aşırı debi (over-pumping)",
            "Kısmi bypass",
            "Düşük yük",
            "Evaporatör kirliliği"
        ]
    },
    "LOW_DT_SYNDROME": {
        "severity": "WARNING",
        "score": 5.0,
        "title": "Düşük ΔT Sendromu",
        "description": "Vana çok açık (≥90%) ama ΔT düşük (≤3.0°C). Coil'den geçen su ısınmıyor/soğumuyor.",
        "steps": [
            "Coil kirliliğini kontrol edin - temizlik gerekebilir",
            "Bypass vanası kısmen açık olabilir",
            "Sensörleri kontrol edin - yanlış okuma olabilir",
            "Debiyi azaltmayı deneyin (balans vanası veya VFD)",
            "Hava filtreleri tıkalı olabilir - değiştirin",
            "Fan devri düşük olabilir - kontrol edin"
        ],
        "causes": [
            "Coil kirliliği",
            "Bypass vanası açık",
            "Sensör hatası",
            "Aşırı debi",
            "Hava tarafı problemi"
        ]
    },
    "COMFORT_OVERRIDE": {
        "severity": "WARNING",
        "score": 4.0,
        "title": "Konfor Öncelikli",
        "description": "Oda sıcaklığı setpoint'ten çok uzak (>3°C). Konfor öncelikli, enerji optimizasyonu bekleyebilir.",
        "steps": [
            "Önce konforu sağlayın - ΔT optimizasyonu şimdilik bekleyebilir",
            "Oda setpoint'i gerçekçi mi kontrol edin",
            "Oda sensörü doğru mu? Manuel termometre ile karşılaştırın",
            "Sistem kapasitesi yeterli mi?",
            "Dış hava sıcaklığı aşırı mı?",
            "Konfor sağlandıktan sonra ΔT optimizasyonuna dönün"
        ],
        "causes": [
            "Yetersiz kapasite",
            "Aşırı yük (çok sıcak/soğuk hava)",
            "Setpoint çok agresif",
            "Sensör hatası"
        ]
    },
    "AIR_DT_LOW_COOL": {
        "severity": "WARNING",
        "score": 4.0,
        "title": "Hava ΔT Düşük (Soğutma)",
        "description": "Soğutma vanası yüksek ama hava ΔT <3.0°C. Hava yeterince soğumuyor.",
        "steps": [
            "AHU SAT setpoint'i ve sensörlerini kontrol edin",
            "Return ve supply hava sensörlerini kalibre edin",
            "Su tarafı setpoint zincirini kontrol edin",
            "Hava filtreleri tıkalı olabilir",
            "Fan devri düşük olabilir",
            "Coil kirliliğini kontrol edin"
        ],
        "causes": [
            "Sensör hatası",
            "Setpoint problemleri",
            "Hava tarafı tıkanıklık",
            "Coil kirliliği"
        ]
    },
    "BAND_LOW": {
        "severity": "WARNING",
        "score": 3.0,
        "title": "ΔT Hedef Altında",
        "description": "ΔT hedefin altında. Çok fazla su akıyor, verimlilik düşük.",
        "steps": [
            "Pompa VFD'si varsa devri azaltın",
            "Balans vanasını kısmen kapatın",
            "Bypass vanasını kısmen açın (varsa)",
            "Setpoint'leri kontrol edin - çok düşük olabilir",
            "Birden fazla pompa varsa birini kapatın"
        ],
        "causes": [
            "Aşırı debi",
            "Setpoint'ler çok düşük",
            "Düşük yük"
        ]
    },
    "BAND_HIGH": {
        "severity": "WARNING",
        "score": 3.0,
        "title": "ΔT Hedef Üstünde",
        "description": "ΔT hedefin üstünde. Yeterince su akmıyor.",
        "steps": [
            "Pompa VFD'si varsa devri artırın",
            "Balans vanasını daha fazla açın",
            "Bypass vanasını kapatın (varsa)",
            "Filtre tıkanıklığını kontrol edin",
            "Pompa kapasitesi yeterli mi kontrol edin",
            "Ek pompa devreye alın (varsa)"
        ],
        "causes": [
            "Yetersiz debi",
            "Filtre tıkanıklığı",
            "Pompa kapasitesi yetersiz",
            "Balans vanası çok kapalı"
        ]
    },
    "IN_BAND": {
        "severity": "OPTIMAL",
        "score": 0.0,
        "title": "Normal Çalışma",
        "description": "Ekipman hedef band içinde çalışıyor. Müdahale gerekmez.",
        "steps": [
            "Sistem normal çalışıyor",
            "Rutin bakım planına devam edin",
            "Trend verilerini izlemeye devam edin"
        ],
        "causes": []
    },
    "MISSING_DATA": {
        "severity": "CRITICAL",
        "score": 0.0,
        "title": "Veri Eksik",
        "description": "ΔT hesaplanamadı. Gerekli sensör verileri eksik veya hatalı.",
        "steps": [
            "Gidiş ve dönüş sıcaklık sensörlerini kontrol edin",
            "BMS'de sensör bağlantılarını doğrulayın",
            "Sensör kalibrasyonunu kontrol edin",
            "Veri toplama sistemini kontrol edin",
            "Sensör arızası varsa değiştirin"
        ],
        "causes": [
            "Sensör arızası",
            "Bağlantı kopukluğu",
            "BMS iletişim hatası",
            "Veri toplama sistemi arızası"
        ]
    },
    "NORMAL": {
        "severity": "OPTIMAL",
        "score": 0.0,
        "title": "Normal Çalışma",
        "description": "Sistem normal parametreler içinde çalışıyor.",
        "steps": [
            "Sistem normal çalışıyor, müdahale gerekmiyor",
            "Rutin bakım planına devam edin",
            "Trend verilerini izlemeye devam edin"
        ],
        "causes": []
    },
    "HIGH_DT": {
        "severity": "WARNING",
        "score": 5.0,
        "title": "Yüksek ΔT",
        "description": "Su tarafı ΔT hedefin üstünde. Debi artırılmalı.",
        "steps": [
            "Pompa VFD'si varsa devri artırın",
            "Balans vanasını daha fazla açın",
            "Filtre tıkanıklığını kontrol edin",
            "Sistemde hava olup olmadığını kontrol edin",
            "Bypass vanası kapalı mı kontrol edin"
        ],
        "causes": [
            "Yetersiz debi",
            "Filtre tıkanıklığı",
            "Pompa kapasitesi yetersiz",
            "Sistemde hava var"
        ]
    },
    "LOW_DT": {
        "severity": "WARNING",
        "score": 4.0,
        "title": "Düşük ΔT",
        "description": "Su tarafı ΔT hedefin altında. Debi azaltılmalı veya yük yetersiz.",
        "steps": [
            "Pompa VFD'si varsa devri azaltın",
            "Balans vanasını kısmen kapatın",
            "Bypass vanası açık mı kontrol edin",
            "Sistemde yeterli yük var mı kontrol edin",
            "Birden fazla pompa varsa birini kapatın"
        ],
        "causes": [
            "Aşırı debi",
            "Bypass vanası açık",
            "Düşük yük/talep",
            "Balans vanası çok açık"
        ]
    },
    "SAT_WARNING": {
        "severity": "WARNING",
        "score": 5.0,
        "title": "SAT Uyarısı",
        "description": "Üfleme sıcaklığı ideal aralığın dışında.",
        "steps": [
            "SAT setpoint'ini kontrol edin",
            "Vana açıklığını kontrol edin",
            "Su sıcaklığını kontrol edin",
            "Hava debisini kontrol edin"
        ],
        "causes": [
            "Setpoint yanlış ayarlanmış",
            "Vana sorunu",
            "Su sıcaklığı problemi"
        ]
    },
    "SAT_HIGH": {
        "severity": "WARNING",
        "score": 5.0,
        "title": "SAT Yüksek",
        "description": "Üfleme sıcaklığı hedefin üstünde. Aşırı ısıtma yapıyor.",
        "steps": [
            "Isıtma vanasını kısın veya kapatın",
            "SAT setpoint'ini düşürün",
            "Su sıcaklığını kontrol edin - çok yüksek olabilir",
            "Kazan/ısıtıcı sıcaklığını düşürün"
        ],
        "causes": [
            "Vana çok açık",
            "Setpoint çok yüksek",
            "Kazan sıcaklığı çok yüksek"
        ]
    },
    "SAT_LOW": {
        "severity": "WARNING",
        "score": 5.0,
        "title": "SAT Düşük",
        "description": "Üfleme sıcaklığı hedefin altında. Aşırı soğutma veya donma riski.",
        "steps": [
            "Soğutma vanasını kısın veya kapatın",
            "SAT setpoint'ini artırın",
            "Chiller sıcaklığını yükseltin",
            "Coil donma korumasını kontrol edin"
        ],
        "causes": [
            "Vana çok açık",
            "Setpoint çok düşük",
            "Chiller sıcaklığı çok düşük",
            "Donma riski"
        ]
    },
    "INSUFFICIENT_CAPACITY": {
        "severity": "WARNING",
        "score": 7.0,
        "title": "Yetersiz Kapasite",
        "description": "Vana tam açık ama konfor sağlanamıyor. Kapasite yetersiz.",
        "steps": [
            "Eşanjör/coil kapasitesini kontrol edin",
            "Su debisini artırın",
            "Su sıcaklığını kontrol edin (soğutmada daha soğuk, ısıtmada daha sıcak)",
            "Ek kapasite gerekebilir",
            "Coil temizliğini kontrol edin"
        ],
        "causes": [
            "Coil kapasitesi yetersiz",
            "Su debisi düşük",
            "Su sıcaklığı yetersiz",
            "Coil kirli",
            "Yük çok yüksek"
        ]
    },
    "SEASONAL_CHILLER_TRANSITION": {
        "severity": "WARNING",
        "score": 8.0,
        "title": "Mevsimsel Chiller Geçiş Uyarısı",
        "description": "Dış hava 10°C altında iken Chiller yüksek kapasitede ve düşük verimle zorlanarak çalışıyor. Free-Cooling fırsatı değerlendirilemiyor.",
        "steps": [
            "AHU'larda %100 taze hava moduna geçerek Free-Cooling yapın",
            "Taze hava damperlerini tam açın — soğuk dış hava doğal soğutma sağlar",
            "Chiller yükü düşmüyorsa ana kollektör setpoint'ini düşürün",
            "Eğer tek Chiller hala %90 üzerinde zorlanıyorsa 2. Chiller'i devreye alın",
            "Free-Cooling sonrası Chiller yükünü tekrar izleyin",
            "Chiller COP değerini takip edin — düşük COP enerji israfına işaret eder"
        ],
        "causes": [
            "Free-Cooling damperlerinin kapalı veya kısmi açık olması",
            "AHU'ların taze hava modunda çalışmaması",
            "Ana kollektör setpoint'inin çok yüksek ayarlanmış olması",
            "Tek Chiller ile karşılanamayan aşırı soğutma talebi",
            "Mevsimsel geçiş programının devreye girmemesi"
        ],
        "setpoint_chain": "Dış Hava (<10°C) → AHU %100 Taze Hava (Free-Cooling) → Kollektör Setpoint Düşür → 2. Chiller Devreye Al"
    }
}


# ================ DATA MODELLERİ ================
@dataclass
class TemperatureData:
    supply: Optional[float] = None
    return_: Optional[float] = None
    inlet: Optional[float] = None
    outlet: Optional[float] = None
    room: Optional[float] = None
    setpoint: Optional[float] = None
    sat: Optional[float] = None
    plant_supply: Optional[float] = None
    plant_return: Optional[float] = None
    oat: Optional[float] = None

@dataclass
class ValveData:
    cooling: Optional[float] = None
    heating: Optional[float] = None

@dataclass
class EquipmentProfile:
    type: str
    name: str
    location: str = ""
    mode: str = ""
    priority: str = "Normal"
    temperatures: TemperatureData = None
    valves: ValveData = None
    humidity: Optional[float] = None
    
    def __post_init__(self):
        if self.temperatures is None:
            self.temperatures = TemperatureData()
        if self.valves is None:
            self.valves = ValveData()

@dataclass
class AnalysisResult:
    delta_t: Optional[float] = None
    air_delta_t: Optional[float] = None  # Air ΔT from Supply/Return
    target_delta_t: Optional[float] = None
    departure: Optional[float] = None
    sat_status: str = "NO DATA"
    approach_supply: Optional[float] = None
    approach_return: Optional[float] = None
    score: float = 0.0
    action: str = "Normal"
    reason: str = ""
    rule: str = ""

    status: str = "IN_BAND"
    severity: str = "OPTIMAL"
    band: str = ""
    dt_source: str = ""
    recommended_sat: Optional[float] = None  # SAT recommendation
    field_experience_issues: List[Dict[str, Any]] = None  # Saha tecrübesi kural ihlalleri
    maintenance_notes: List[str] = None  # Bakım kartı notları
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "Su ΔT (°C)": f"{self.delta_t:.2f}" if self.delta_t is not None else "",
            "Hava ΔT (°C)": f"{self.air_delta_t:.2f}" if self.air_delta_t is not None else "",
            "Target ΔT (°C)": f"{self.target_delta_t:.2f}" if self.target_delta_t is not None else "",
            "ΔT Dev (°C)": f"{self.departure:+.2f}" if self.departure is not None else "",
            "SAT Status": self.sat_status,
            "Recommended SAT (°C)": f"{self.recommended_sat:.1f}" if self.recommended_sat is not None else "",
            "Approach_Supply (°C)": f"{self.approach_supply:+.2f}" if self.approach_supply is not None else "",
            "Approach_Return (°C)": f"{self.approach_return:+.2f}" if self.approach_return is not None else "",
            "Score": f"{self.score:.1f}",
            "Action": self.action,
            "Reason": self.reason,
            "Rule": self.rule,

            "Status": self.status,
            "Severity": self.severity,
            "Band": self.band,
            "DT Source": self.dt_source,
            "Maintenance Notes": " | ".join(self.maintenance_notes) if self.maintenance_notes else "",
        }

# ================ UTILITY FONKSİYONLARI ================
class HVACUtils:
    @staticmethod
    def to_float(value: Any) -> Optional[float]:
        """Convert any value to float safely. Handles %, empty strings, and localized formats."""
        if value is None:
            return None
        
        try:
            if isinstance(value, (int, float)):
                return float(value)
            
            # String cleaning
            s = str(value).strip()
            # Remove % symbol
            s = s.replace('%', '')
            # Replace comma with dot
            s = s.replace(",", ".")
            
            if not s or s.lower() in ("none", "null", "nan", "na", ""):
                return None
            
            return float(s)
        except (ValueError, TypeError):
            return None
    
    @staticmethod
    def canonical_key(key: str) -> str:
        """Standardize column names - FIXED MAPPING for UI compatibility."""
        if not key:
            return ""
        
        key_lower = key.strip().lower()
        
        # Exact mapping from UI to backend expected keys
        mapping = {
            # UI sends these -> backend expects these
            "location": "Location",
            "mahal": "Location",
            "asset": "Name",
            "name": "Name",
            "type": "Type",
            "mode": "Mode",
            "priority": "Priority",
            
            # Temperature readings - tüm varyasyonlar
            "supply_temp": "Supply (°C)",
            "supply": "Supply (°C)",
            "supply (°c)": "Supply (°C)",
            "return_temp": "Return (°C)",
            "return": "Return (°C)",
            "return (°c)": "Return (°C)",
            "inlet_temp": "Inlet (°C)",
            "inlet": "Inlet (°C)",
            "inlet (°c)": "Inlet (°C)",
            "outlet_temp": "Outlet (°C)",
            "outlet": "Outlet (°C)",
            "outlet (°c)": "Outlet (°C)",
            "room_temp": "Room (°C)",
            "room": "Room (°C)",
            "room (°c)": "Room (°C)",
            "oda": "Room (°C)",
            "setpoint": "Set (°C)",
            "set": "Set (°C)",
            "set (°c)": "Set (°C)",
            "sat": "SAT (°C)",
            "sat (°c)": "SAT (°C)",
            "supply_air_temp": "SAT (°C)",
            "ufleme": "SAT (°C)",
            
            # Valves
            "cool_valve": "Cool Valve (%)",
            "cooling_valve": "Cool Valve (%)",
            "cool valve (%)": "Cool Valve (%)",
            "sogutma_vana": "Cool Valve (%)",
            "sogutma_vanasi": "Cool Valve (%)",
            "heat_valve": "Heat Valve (%)",
            "heating_valve": "Heat Valve (%)",
            "heat valve (%)": "Heat Valve (%)",
            "isitma_vana": "Heat Valve (%)",
            "isitma_vanasi": "Heat Valve (%)",
            
            # Plant references
            "plant_supply": "Plant Supply (°C)",
            "plant supply (°c)": "Plant Supply (°C)",
            "plant_return": "Plant Return (°C)",
            "plant return (°c)": "Plant Return (°C)",
            
            # Other
            "humidity": "Humidity (%)",
            "humidity %": "Humidity (%)",
            "humidity (%)": "Humidity (%)",
            "nem": "Humidity (%)",
            "oat": "OAT (°C)",
            "oat (°c)": "OAT (°C)",
            "dis_sicaklik": "OAT (°C)",
        }
        
        # Try exact match first
        if key_lower in mapping:
            return mapping[key_lower]
        
        # Try partial matches
        for pattern, canonical in mapping.items():
            if pattern in key_lower:
                return canonical
        
        return key
    
    @staticmethod
    def is_heating_mode(mode_str: str) -> bool:
        """Check if equipment is in heating mode."""
        if not mode_str:
            return False
        
        mode = str(mode_str).strip().lower()
        heating_indicators = ["heat", "heating", "ısıt", "isit", "kalorifer", "winter", "heater"]
        return any(indicator in mode for indicator in heating_indicators)

# ================ HVAC ANALİZ MOTORU ================
class HVACAnalyzer:
    def __init__(self, config: Dict[str, Any] = None):
        self.config = config or CONFIG
        self.utils = HVACUtils()
    
    def classify_equipment_type(self, type_str: str) -> EquipmentType:
        """Classify equipment based on type string."""
        if not type_str:
            return EquipmentType.OTHER
        
        type_lower = str(type_str).strip().lower()
        
        if any(k in type_lower for k in ["ahu", "air handling", "klima santral", "santral", "ks", "hvac unit"]):
            return EquipmentType.AHU
        elif any(k in type_lower for k in ["chiller", "soğutma grubu", "sogutma grubu", "chiler"]):
            return EquipmentType.CHILLER
        elif any(k in type_lower for k in ["fcu", "fan coil", "fancoil", "fan-coil", "fc"]):
            return EquipmentType.FCU
        elif any(k in type_lower for k in ["kollekt", "collector", "header", "manifold", "primary", "primer", "ana hat"]):
            return EquipmentType.COLLECTOR
        elif any(k in type_lower for k in ["heat exchanger", "ısı eşanjörü", "ısı eşanjör", "eşanjör", "esanjor"]):
            return EquipmentType.HEAT_EXCHANGER
        else:
            return EquipmentType.OTHER
    
    def normalize_row(self, row: Dict[str, Any]) -> Dict[str, Any]:
        """Normalize row keys to canonical names."""
        normalized = {}
        for key, value in row.items():
            canonical_key = self.utils.canonical_key(key)
            normalized[canonical_key] = value
        return normalized
    
    def extract_equipment_profile(self, row: Dict[str, Any]) -> EquipmentProfile:
        """Extract equipment profile from normalized row."""
        normalized = self.normalize_row(row)
        
        # Get basic info
        equipment_type = normalized.get("Type", "")
        name = normalized.get("Name", "")
        location = normalized.get("Location", "")
        mode = normalized.get("Mode", "")
        priority = normalized.get("Priority", "Normal")
        
        # Create temperature data
        temps = TemperatureData(
            supply=self.utils.to_float(normalized.get("Supply (°C)")),
            return_=self.utils.to_float(normalized.get("Return (°C)")),
            inlet=self.utils.to_float(normalized.get("Inlet (°C)")),
            outlet=self.utils.to_float(normalized.get("Outlet (°C)")),
            room=self.utils.to_float(normalized.get("Room (°C)")),
            setpoint=self.utils.to_float(normalized.get("Set (°C)")),
            sat=self.utils.to_float(normalized.get("SAT (°C)")),
            plant_supply=self.utils.to_float(normalized.get("Plant Supply (°C)")),
            plant_return=self.utils.to_float(normalized.get("Plant Return (°C)")),
            oat=self.utils.to_float(normalized.get("OAT (°C)"))
        )
        
        # Backward-compat: if Supply is missing but SAT exists, treat SAT as Supply Air
        if temps.supply is None and temps.sat is not None:
            temps.supply = temps.sat
        
        # Fallback: if Return is missing but Room exists, use Room as Return Air
        if temps.return_ is None and temps.room is not None:
            temps.return_ = temps.room

        # Create valve data
        valves = ValveData(
            cooling=self.utils.to_float(normalized.get("Cool Valve (%)")),
            heating=self.utils.to_float(normalized.get("Heat Valve (%)"))
        )
        
        # Otomatik mod algılama ve kolektör seçimi
        # NOT: Kolektör sıcaklıkları analyze_data fonksiyonunda profiles'dan bulunup atanacak
        # Burada sadece mode'u AUTO olarak işaretle
        cooling_valve = valves.cooling if valves.cooling is not None else 0
        heating_valve = valves.heating if valves.heating is not None else 0
        
        if mode.upper() == "AUTO" or (cooling_valve == 0 and heating_valve == 0):
            # Mode AUTO olarak ayarla
            mode = "AUTO"
        
        # DEBUG: SAT, Room, Set değerlerini logla
        logger.debug(f"EXTRACT {name}: SAT={temps.sat}, Room={temps.room}, Set={temps.setpoint}, normalized keys={list(normalized.keys())[:10]}")
        
        # Create profile
        return EquipmentProfile(
            type=equipment_type,
            name=name,
            location=location,
            mode=mode,
            priority=priority,
            temperatures=temps,
            valves=valves,
            humidity=self.utils.to_float(normalized.get("Humidity (%)"))
        )
    
    def calculate_delta_t(self, profile: EquipmentProfile) -> Tuple[Optional[float], str]:
        """Calculate **WATER** ΔT (coil/plant). 

        IMPORTANT:
        - Supply/Return = AIR temperatures (AHU discharge/return air) -> NOT used as ΔT source.
        - Inlet/Outlet   = WATER temperatures (coil water entering/leaving) -> primary ΔT source.
        """
        dt_source = ""
        delta_t = None

        inlet = profile.temperatures.inlet
        outlet = profile.temperatures.outlet

        # Priority 1: Coil water (Inlet/Outlet)
        if inlet is not None and outlet is not None:
            # Cooling coil: water warms across coil -> outlet > inlet
            # Heating coil: water cools across coil -> inlet > outlet
            if self.utils.is_heating_mode(profile.mode):
                delta_t = inlet - outlet
            else:
                delta_t = outlet - inlet

            dt_source = "Inlet/Outlet (Water)"
            if delta_t is not None and delta_t < 0:
                delta_t = abs(delta_t)

        # Priority 2: Plant water (Plant Supply/Return) fallback
        if delta_t is None and profile.temperatures.plant_supply is not None and profile.temperatures.plant_return is not None:
            delta_t = profile.temperatures.plant_return - profile.temperatures.plant_supply
            dt_source = "Plant Supply/Return (Water)"
            if delta_t is not None and delta_t < 0:
                delta_t = abs(delta_t)

        return delta_t, dt_source

    def calculate_air_delta_t(self, profile: EquipmentProfile) -> Optional[float]:
        """Calculate AIR ΔT from Supply/Return (AHU discharge vs return air)."""
        supply_air = profile.temperatures.supply
        return_air = profile.temperatures.return_
        if supply_air is None or return_air is None:
            return None

        if self.utils.is_heating_mode(profile.mode):
            air_dt = supply_air - return_air
        else:
            air_dt = return_air - supply_air

        if air_dt is not None and air_dt < 0:
            air_dt = abs(air_dt)

        return air_dt

    
    def get_target_delta_t(self, profile: EquipmentProfile, oat: Optional[float] = None) -> float:
        """Get target ΔT based on equipment type and mode."""
        eq_type = self.classify_equipment_type(profile.type)
        is_heating = self.utils.is_heating_mode(profile.mode)
        
        # Heating mode target (type-specific)
        if is_heating and eq_type != EquipmentType.CHILLER:
            # AHU/FCU ısıtma coil'leri için düşük ΔT (10°C)
            if eq_type in [EquipmentType.AHU, EquipmentType.FCU]:
                return 10.0
            # Heat exchanger için
            elif eq_type == EquipmentType.HEAT_EXCHANGER:
                return 8.0
            # Kazan vb. için yüksek ΔT
            else:
                return self.config["TARGET_DT_HEAT"]
        
        # OAT bias for AHUs (cooling mode)
        oat_bias = 0.0  # Default 0 when OAT is None
        if eq_type == EquipmentType.AHU and oat is not None:
            oat_temp = oat
            max_bias = self.config["OAT_BIAS_MAX"]
            if oat_temp <= 15.0:
                oat_bias = -max_bias
            elif oat_temp >= 25.0:
                oat_bias = max_bias
            else:
                oat_bias = (oat_temp - 20.0) / 5.0 * max_bias
        
        # Equipment specific targets (cooling mode)
        if eq_type == EquipmentType.AHU:
            return self.config["TARGET_DT_AHU"] + oat_bias
        elif eq_type == EquipmentType.CHILLER:
            return self.config["TARGET_DT_CHILLER"]
        elif eq_type == EquipmentType.FCU:
            return self.config.get("TARGET_DT_FCU") or self.config.get("TARGET_DT_DEFAULT", 5.0)
        elif eq_type == EquipmentType.COLLECTOR:
            return self.config["TARGET_DT_COLLECTOR"]
        elif eq_type == EquipmentType.HEAT_EXCHANGER:
            return self.config["TARGET_DT_HEAT_EXCHANGER"]
        else:
            return self.config["TARGET_DT_DEFAULT"]
    
    def analyze_sat_status(self, profile: EquipmentProfile) -> str:
        """Analyze SAT (Supply Air Temperature) status.
        
        IMPORTANT: Vana açıklığı düşükken (<%40) SAT beklenen değerlerin altında olması normaldir.
        Bu durumda uyarı vermemeli ve mod ataması yapmamalı, çünkü vana düşükken doğru üfleme değeri alınamaz.
        """
        sat = profile.temperatures.sat
        
        # Room yoksa Return'ü kullan (özellikle AHU'lar için)
        rat = profile.temperatures.room
        if rat is None:
            rat = profile.temperatures.return_
        
        setpoint = profile.temperatures.setpoint
        
        # SAT veya Setpoint eksikse analiz yapılamaz
        if sat is None or setpoint is None:
            return "NO DATA"
        
        # =================== VANA EŞİK KONTROLÜ ===================
        # Vana açıklığı <%40 ise SAT analizi yapılamaz
        # Çünkü vana düşükken doğru üfleme değeri alınamaz
        VALVE_THRESHOLD = 40.0  # %40 eşik değeri
        
        # Vana değerlerini al
        heating_valve = profile.valves.heating if profile.valves.heating is not None else 0.0
        cooling_valve = profile.valves.cooling if profile.valves.cooling is not None else 0.0
        
        # Her iki vana da <%40 ise analiz yapılamaz
        if heating_valve < VALVE_THRESHOLD and cooling_valve < VALVE_THRESHOLD:
            return "VALVE LOW"
        
        # Mod tespiti - AUTO modda vana pozisyonuna göre belirle
        is_heating = self.utils.is_heating_mode(profile.mode)
        
        # AUTO modda hangi vana daha açık ise o modu kullan
        if profile.mode and profile.mode.upper() == "AUTO":
            if heating_valve > cooling_valve and heating_valve >= VALVE_THRESHOLD:
                is_heating = True
            elif cooling_valve > heating_valve and cooling_valve >= VALVE_THRESHOLD:
                is_heating = False
        
        # İlgili vana kontrolü
        valve_pct = heating_valve if is_heating else cooling_valve
        
        # İlgili vana düşükse analiz yapılamaz
        if valve_pct < VALVE_THRESHOLD:
            return "VALVE LOW"
        # =============================================================
        
        # Room/Return yoksa sadece SAT vs Setpoint karşılaştır
        if rat is None:
            # Basit kontrol: SAT, Setpoint'e yakın mı?
            diff = abs(sat - setpoint)
            if diff <= 3.0:
                return "OPTIMAL"
            else:
                return "CHECK REQUIRED"
        
        if is_heating:
            if sat < rat:
                return "NOT HEATING"
            elif sat < (setpoint - self.config["SAT_HEATING_THRESHOLD"]):
                return "INSUFFICIENT HEATING"
            else:
                return "OPTIMAL"
        else:  # Cooling mode
            if sat > rat:
                return "NOT COOLING"
            elif sat > (setpoint + self.config["SAT_COOLING_THRESHOLD"]):
                return "INSUFFICIENT COOLING"
            else:
                return "OPTIMAL"
    
    def calculate_recommended_sat(self, profile: EquipmentProfile, 
                                  sat_status: str,
                                  approach_supply: Optional[float],
                                  rule: str,
                                  effective_mode: str = None) -> Optional[float]:
        """
        Calculate recommended SAT based on current conditions.
        
        Logic:
        - If SAT is too high (cooling mode): Recommend lowering to 15-18°C range
        - If SAT is too low (heating mode): Recommend raising to 28-35°C range
        - If approach is poor: Recommend adjusting SAT
        - If NORMAL/OPTIMAL: No recommendation (return None)
        - If AMBIGUOUS: No recommendation (return None)
        """
        # Only recommend for AHU/FCU (equipment with SAT control)
        eq_type = self.classify_equipment_type(profile.type)
        if eq_type not in [EquipmentType.AHU, EquipmentType.FCU]:
            return None
        
        current_sat = profile.temperatures.sat
        if current_sat is None:
            return None
        
        # AMBIGUOUS veya UNKNOWN modda öneri üretme
        if effective_mode and effective_mode.upper() in ["AMBIGUOUS", "UNKNOWN"]:
            return None
        
        # Don't recommend if system is working well
        if rule in ["NORMAL", "IN_BAND"] and sat_status == "OPTIMAL":
            return None
        
        # effective_mode varsa onu kullan; yoksa profile.mode'dan tahmin et
        if effective_mode:
            is_heating = "HEAT" in effective_mode.upper()
        else:
            is_heating = self.utils.is_heating_mode(profile.mode)
        
        # Get target SAT ranges from config
        sat_cool_min = self.config.get("SAT_COOLING_MIN", 15.0)
        sat_cool_max = self.config.get("SAT_COOLING_MAX", 18.0)
        sat_heat_min = self.config.get("SAT_HEATING_MIN", 28.0)
        sat_heat_max = self.config.get("SAT_HEATING_MAX", 31.0)

        # Cooling mode recommendations
        if not is_heating:
            # SAT too high - recommend target of 16°C (middle of 15-18)
            if rule == "NOT_COOLING" or sat_status == "NOT_COOLING":
                return (sat_cool_min + sat_cool_max) / 2  # 16.5°C
            elif rule == "SAT_LOW" or "SAT Düşük" in str(sat_status):
                # SAT too low - recommend 16°C
                return (sat_cool_min + sat_cool_max) / 2
            elif rule == "COOL_EFF_LOW":
                return current_sat - 2.0 if current_sat > sat_cool_max else None
            elif approach_supply and approach_supply > 7.0:
                return max(current_sat - 2.0, sat_cool_min)

        # Heating mode recommendations
        else:
            # SAT too low - recommend target (middle of sat_heat_min - sat_heat_max)
            if rule == "NOT_HEATING" or sat_status == "NOT_HEATING":
                return (sat_heat_min + sat_heat_max) / 2
            elif rule == "SAT_HIGH" or "SAT Yüksek" in str(sat_status):
                # SAT too high - recommend middle of heating range
                return (sat_heat_min + sat_heat_max) / 2
            elif rule == "HEAT_EFF_LOW":
                return current_sat + 3.0 if current_sat < sat_heat_min else None
            elif approach_supply and approach_supply < -5.0:
                return min(current_sat + 3.0, sat_heat_max)
        
        return None
    
    def calculate_approach(self, profile: EquipmentProfile, plant_supply: Optional[float], plant_return: Optional[float]) -> Tuple[Optional[float], Optional[float]]:
        """Calculate coil *approach* using AIR vs WATER.

        - Supply/Return = AIR (AHU discharge/return air)
        - Inlet/Outlet = WATER (coil water entering/leaving)

        Cooling (default): 
          Approach_Supply = SupplyAir - WaterIn
          Approach_Return = ReturnAir - WaterOut
        Heating:
          Approach_Supply = WaterIn - SupplyAir
          Approach_Return = WaterOut - ReturnAir
        """
        supply_air = profile.temperatures.supply
        return_air = profile.temperatures.return_
        
        # Water temperatures - SADECE gerçek değerleri kullan, 0 fallback YOK
        water_in = profile.temperatures.inlet if profile.temperatures.inlet is not None else plant_supply
        water_out = profile.temperatures.outlet if profile.temperatures.outlet is not None else plant_return

        approach_supply = None
        approach_return = None

        # Heating mode detection - AUTO modda vana pozisyonuna göre belirle
        is_heating = self.utils.is_heating_mode(profile.mode)
        
        # ========== VANA EŞİK KONTROLÜ ==========
        # Vana <%40 ise mod ataması yapılmaz - doğru üfleme değeri alınamaz
        VALVE_THRESHOLD = 40.0
        heating_valve = profile.valves.heating if profile.valves.heating is not None else 0
        cooling_valve = profile.valves.cooling if profile.valves.cooling is not None else 0
        
        # Her iki vana da <%40 ise mod belirsiz
        valves_too_low = (heating_valve < VALVE_THRESHOLD and cooling_valve < VALVE_THRESHOLD)
        # ===========================================
        
        # AUTO modda vana pozisyonuna bak (sadece vanalar yeterliyse)
        if profile.mode and profile.mode.upper() == "AUTO" and not valves_too_low:
            # Hangi vana daha açık?
            if heating_valve > cooling_valve and heating_valve >= VALVE_THRESHOLD:
                is_heating = True
            elif cooling_valve > heating_valve and cooling_valve >= VALVE_THRESHOLD:
                is_heating = False
            # Eşitse mevcut is_heating değeri kalır

        # Approach hesapla - SADECE her iki değer de varsa
        if supply_air is not None and water_in is not None:
            approach_supply = (water_in - supply_air) if is_heating else (supply_air - water_in)
        # Eğer water_in None ise approach None kalır (0 kullanma!)

        if return_air is not None and water_out is not None:
            approach_return = (water_out - return_air) if is_heating else (return_air - water_out)
        # Eğer water_out None ise approach None kalır (0 kullanma!)

        return approach_supply, approach_return

    
    def calculate_departure(self, profile: EquipmentProfile) -> Optional[float]:
        """Calculate room-setpoint departure for comfort analysis."""
        if profile.temperatures.room is None or profile.temperatures.setpoint is None:
            return None
        return abs(profile.temperatures.room - profile.temperatures.setpoint)
    
    def find_plant_reference(self, profiles: List[EquipmentProfile]) -> Tuple[Optional[float], Optional[float]]:
        """Find plant supply/return reference from collector rows."""
        plant_supply = None
        plant_return = None
        
        for profile in profiles:
            if self.classify_equipment_type(profile.type) == EquipmentType.COLLECTOR:
                name_lower = profile.name.lower()
                # Check if this is a main/primary collector
                is_main_collector = any(
                    pattern in name_lower 
                    for pattern in self.config["PLANT_COLLECTOR_PATTERNS"]
                )
                
                if is_main_collector:
                    # Try different temperature sources in order
                    if profile.temperatures.supply is not None:
                        plant_supply = profile.temperatures.supply
                    elif profile.temperatures.inlet is not None:
                        plant_supply = profile.temperatures.inlet
                    
                    if profile.temperatures.return_ is not None:
                        plant_return = profile.temperatures.return_
                    elif profile.temperatures.outlet is not None:
                        plant_return = profile.temperatures.outlet
                    
                    if plant_supply is not None or plant_return is not None:
                        break
        
        return plant_supply, plant_return
    
    def check_special_conditions(self, profile: EquipmentProfile, delta_t: Optional[float], effective_mode: str = None) -> Dict[str, Any]:
        """Check for special HVAC conditions.
        
        Args:
            effective_mode: Hesaplanmış gerçek mod (HEATING/COOLING/AMBIGUOUS).
                           None ise profile.mode'dan çıkarılır.
        """
        result = {
            "action": "",
            "reason": "",
            "rule": "",
        }
        
        eq_type = self.classify_equipment_type(profile.type)
        # effective_mode varsa onu kullan, yoksa profile.mode'dan çıkar
        _mode = effective_mode if effective_mode else profile.mode
        is_heating = self.utils.is_heating_mode(_mode)
        
        # 1. Simultaneous heating/cooling
        # Vana değerlerini güvenli al (None -> 0)
        cool_v = profile.valves.cooling if profile.valves.cooling is not None else 0.0
        heat_v = profile.valves.heating if profile.valves.heating is not None else 0.0
        
        if (cool_v >= 5.0 and heat_v >= 5.0):
            result.update({
                "action": "Investigate Simultaneous HEAT+COOL",
                "reason": f"Soğutma ({cool_v:.0f}%) ve ısıtma ({heat_v:.0f}%) vanaları aynı anda açık (Eşik: %5)",
                "rule": "SIMUL_HEAT_COOL"
            })
            return result
        
        # 2. Comfort override
        departure = self.calculate_departure(profile)
        if departure is not None and departure > self.config["COMFORT_DEPARTURE"]:
            result.update({
                "action": "Prioritize Comfort",
                "reason": f"Oda-Setpoint sapması yüksek ({departure:.1f}°C). ΔT optimizasyonu ertelendi.",
                "rule": "COMFORT_OVERRIDE"
            })
            return result


        # 3. AHU coil effectiveness (AIR vs WATER)
        if eq_type == EquipmentType.AHU:
            supply_air = profile.temperatures.supply
            return_air = profile.temperatures.return_
            water_in = profile.temperatures.inlet if profile.temperatures.inlet is not None else profile.temperatures.plant_supply
            water_out = profile.temperatures.outlet if profile.temperatures.outlet is not None else profile.temperatures.plant_return
            air_dt = self.calculate_air_delta_t(profile)

            # COOLING: valve high but supply air still warm relative to entering water
            if (not is_heating and profile.valves.cooling is not None and 
                profile.valves.cooling >= self.config.get("HIGH_VALVE_THRESHOLD", 90)):
                if supply_air is not None and water_in is not None:
                    approach = supply_air - water_in
                    max_app = self.config.get("APPROACH_MAX", 7.0)
                    if approach > max_app:
                        result.update({
                            "action": "KRİTİK: Soğutma Etkisi Düşük (Üfleme Sıcak)",
                            "reason": (
                                f"Cool valve yüksek (%{profile.valves.cooling:.0f}) ama üfleme {supply_air:.1f}°C. "
                                f"Giren su {water_in:.1f}°C → Approach {approach:.1f}°C (limit ~{max_app:.1f}°C). "
                                "Setpoint zinciri: AHU SAT setpoint ↓ → Kolektör/Transfer gidiş seti ↓ → Chiller seti ↓."
                            ),
                            "rule": "COOL_EFF_LOW"
                        })
                        return result

                # If we have air delta, also sanity-check (return should be warmer than supply in cooling)
                if air_dt is not None and air_dt < 3.0 and supply_air is not None and return_air is not None:
                    result.update({
                        "action": "UYARI: Soğutma Etkisi Zayıf (Hava ΔT düşük)",
                        "reason": (
                            f"Cool valve yüksek (%{profile.valves.cooling:.0f}) ama hava ΔT düşük ({air_dt:.1f}°C). "
                            f"Return {return_air:.1f}°C → Supply {supply_air:.1f}°C. "
                            "Önce AHU SAT setpoint ve sensörleri doğrula; sonra su tarafı setpoint zincirini kontrol et."
                        ),
                        "rule": "AIR_DT_LOW_COOL"
                    })
                    return result

            # HEATING: valve high but supply air still cold
            if (is_heating and profile.valves.heating is not None and 
                profile.valves.heating >= self.config.get("HIGH_VALVE_THRESHOLD", 90)):
                heat_min = 28.0
                if supply_air is not None and supply_air < heat_min:
                    result.update({
                        "action": "KRİTİK: Isıtma Etkisi Düşük (Üfleme Soğuk)",
                        "reason": (
                            f"Heat valve yüksek (%{profile.valves.heating:.0f}) ama üfleme {supply_air:.1f}°C (<{heat_min:.0f}°C). "
                            "Setpoint zinciri: AHU SAT setpoint ↑ → Kolektör/Transfer gidiş seti ↑ → Kazan seti ↑."
                        ),
                        "rule": "HEAT_EFF_LOW"
                    })
                    return result

        # 3. Chiller diagnostics
        if eq_type == EquipmentType.CHILLER and delta_t is not None:
            if delta_t < self.config["CHILLER_BYPASS_DT"]:
                result.update({
                    "action": "KRİTİK: Chiller Bypass / Arıza",
                    "reason": f"ΔT çok düşük ({delta_t:.1f}°C). Bypass açık veya kompresör yük almıyor.",
                    "rule": "CHILLER_BYPASS"
                })
                return result
            elif delta_t < self.config["CHILLER_LOW_DT_THRESHOLD"]:
                result.update({
                    "action": "Düşük ΔT Sendromu (Chiller)",
                    "reason": f"Chiller ΔT düşük ({delta_t:.1f}°C). Hedef ~{self.config['TARGET_DT_CHILLER']:.1f}°C.",
                    "rule": "CHILLER_LOW_DT"
                })
                return result
        
        # 4. Heating diagnostics - SAT kontrolü
        if is_heating and eq_type != EquipmentType.CHILLER and delta_t is not None:
            # Check SAT for heating - ΔT iyi ama SAT düşükse debi sorunu
            if (delta_t >= self.config["TARGET_DT_HEAT"] and 
                profile.temperatures.sat is not None and
                profile.temperatures.sat < self.config["HEAT_SAT_LOW_THRESHOLD"]):
                result.update({
                    "action": "Düşük Debi / Pompa Basıncı Kontrolü",
                    "reason": f"Su tarafı ΔT ({delta_t:.1f}°C) iyi ancak üfleme ({profile.temperatures.sat:.1f}°C) düşük.",
                    "rule": "LOW_FLOW_DETECTED"
                })
                return result
        
        # 5. Low ΔT syndrome
        if (profile.valves.cooling is not None and 
            profile.valves.cooling >= self.config["HIGH_VALVE_THRESHOLD"] and
            delta_t is not None and 
            delta_t <= self.config["LOW_DT_THRESHOLD"]):
            result.update({
                "action": "Investigate Low-ΔT Syndrome",
                "reason": "Vana yüksek ama ΔT düşük: coil kirliliği / bypass / sensör kontrol.",
                "rule": "LOW_DT_SYNDROME"
            })
            return result
        
        return result
    


    def calculate_score(self, profile: EquipmentProfile, delta_t: Optional[float], 
                       target_dt: float, departure: Optional[float],
                       sat_status: str, special_rule: str) -> float:
        """Calculate 0-10 priority score."""
        score = 0.0
        
        # Base score from ΔT departure
        if departure is not None:
            score += min(abs(departure) * 2.0, 6.0)
        
        # Priority weight
        priority = profile.priority.lower()
        if "kritik" in priority or "critical" in priority or priority == "1":
            score *= 1.5
        
        # Valve position impact
        max_valve = max(
            profile.valves.cooling or 0,
            profile.valves.heating or 0
        )
        if max_valve > 80:
            score *= 1.2
        
        # SAT issues (VALVE_LOW hariç - vana düşükken SAT sorunu normal)
        if sat_status not in ["OPTIMAL", "NO DATA", "VALVE_LOW", "VALVE LOW"]:
            score += 2.0
        
        # Special rules bonus
        rule_boosts = {
            "SIMUL_HEAT_COOL": 10.0,
            "CHILLER_BYPASS": 9.0,
            "NOT_COOLING": 9.0,
            "NOT_HEATING": 9.0,
            "LOW_FLOW_DETECTED": 8.0,
            "HEAT_EFF_LOW": 7.0,
            "COOL_EFF_LOW": 7.0,
            "CHILLER_LOW_DT": 6.0,
            "LOW_DT_SYNDROME": 5.0,
            "SAT_HIGH": 5.0,
            "SAT_LOW": 5.0,
            "BAND_HIGH": 4.0,
            "BAND_LOW": 4.0,
            "COMFORT_OVERRIDE": 4.0,
            "HIGH_DT": 3.0,
            "LOW_DT": 3.0,
        }
        if special_rule in rule_boosts:
            score = max(score, rule_boosts[special_rule])
        
        return min(score, 10.0)
    
    def map_severity(self, status: str, score: float) -> str:
        """Map backend status to UI severity. Score takes priority."""
        # CRITICAL: Score >= 7.0 always means CRITICAL, regardless of status
        if score >= 7.0:
            return "CRITICAL"
        
        # CRITICAL: Missing data is always critical
        if status == "MISSING_DATA":
            return "CRITICAL"
        
        # WARNING: Score between 5.0 and 7.0, or status is LOW/HIGH
        if 5.0 <= score < 7.0:
            return "WARNING"
        if status in ["LOW", "HIGH"]:
            return "WARNING"
        
        # OPTIMAL: Everything else (low score and IN_BAND status)
        return "OPTIMAL"
    
    def determine_effective_mode(self, profile: EquipmentProfile) -> str:
        """Determine effective operation mode, especially for AUTO."""
        raw_mode = str(profile.mode).strip().upper()
        
        # If explicitly HEAT or COOL, return it
        if "HEAT" in raw_mode or "ISIT" in raw_mode or "WINTER" in raw_mode:
            return "HEATING"
        if "COOL" in raw_mode or "SOGUT" in raw_mode or "SUMMER" in raw_mode:
            return "COOLING"
            
        # If AUTO, try to guess based on sensors or valve
        if raw_mode == "AUTO" or not raw_mode:
            # 1. Valve position check
            heat_v = profile.valves.heating or 0
            cool_v = profile.valves.cooling or 0
            
            # AMBIGUOUS: İki vana birden yüksekse kontrol çakışması
            if heat_v >= 15 and cool_v >= 15:
                return "AMBIGUOUS"
            
            if heat_v > cool_v and heat_v >= 15:
                return "HEATING (Auto)"
            if cool_v > heat_v and cool_v >= 15:
                return "COOLING (Auto)"
                
            # 2. Temperature check (SAT vs Return)
            sat = profile.temperatures.sat or profile.temperatures.supply
            ret = profile.temperatures.return_ or profile.temperatures.room
            
            if sat is not None and ret is not None:
                if sat > ret + 2.0:
                    return "HEATING (Auto-Detected)"
                if sat < ret - 2.0:
                    return "COOLING (Auto-Detected)"
                    
        return "UNKNOWN"

    def analyze_equipment(self, profile: EquipmentProfile, 
                         plant_supply: Optional[float], 
                         plant_return: Optional[float],
                         oat: Optional[float],
                         tol_crit: float,
                         tol_norm: float) -> AnalysisResult:
        """Main dispatcher for equipment analysis."""
        eq_type = self.classify_equipment_type(profile.type)
        
        # Determine effective mode (crucial for AHU)
        effective_mode = self.determine_effective_mode(profile)
        
        # Dispatch based on type
        if eq_type == EquipmentType.AHU:
            # Bakım kartını al (varsa)
            maint_card = get_maintenance_card(profile.name) if profile.name else {}
            return self.analyze_ahu_performance(profile, effective_mode, plant_supply, plant_return, oat, tol_crit, tol_norm, maintenance_card=maint_card)
        else:
            # FCU, Chiller, and others use the standard logic
            return self.analyze_fcu_performance(profile, effective_mode, plant_supply, plant_return, oat, tol_crit, tol_norm)

    def _analyze_base(self, profile: EquipmentProfile, result: AnalysisResult, oat) -> Optional[AnalysisResult]:
        """Ortak delta_t hesaplaması ve STANDBY kontrolü. STANDBY ise doldurulmuş result döner, değilse None."""
        # Delta T hesaplamaları (tüm path'ler için ortak)
        delta_t, dt_source = self.calculate_delta_t(profile)
        result.delta_t = delta_t
        result.dt_source = dt_source
        result.air_delta_t = self.calculate_air_delta_t(profile)
        target_dt = self.get_target_delta_t(profile, oat)
        result.target_delta_t = target_dt
        if delta_t is not None:
            result.departure = delta_t - target_dt

        # Chiller, Kazan ve Kolektörler vana ile kontrol edilmez (veya farklı mantık), bu yüzden STANDBY'a düşmemeli
        SKIP_STANDBY_TYPES = ["CHILLER", "KAZAN", "KOLLEKTOR", "COLLECTOR", "POMPA", "PUMP"]
        eq_type_upper = profile.type.upper() if profile.type else ""

        cooling_valve = profile.valves.cooling if profile.valves.cooling is not None else 0
        heating_valve = profile.valves.heating if profile.valves.heating is not None else 0
        mode_upper = profile.mode.upper() if profile.mode else ""

        # Eğer özel tip değilse VE Auto+Vana0 ise Standby
        if (not any(t in eq_type_upper for t in SKIP_STANDBY_TYPES)) and \
           mode_upper == "AUTO" and cooling_valve == 0 and heating_valve == 0:
            # Ekipman bekleme modunda - veri eksik değil!
            result.status = "STANDBY"
            result.action = "Bekleme Modu"
            result.reason = "Sistem AUTO modda, vanalar kapalı. Ekipman talep bekliyor."
            result.rule = "STANDBY"
            result.severity = "OPTIMAL"
            result.sat_status = "STANDBY"
            result.score = 0.0
            return result

        return None

    def analyze_ahu_performance(self, profile: EquipmentProfile, effective_mode: str,
                              plant_supply, plant_return, oat, tol_crit, tol_norm,
                              maintenance_card: dict = None) -> AnalysisResult:
        """Specific logic for Air Handling Units (Santraller)."""
        result = AnalysisResult()
        
        # --- BAKIM KARTI KONTROLÜ ---
        maint = maintenance_card or {}
        maintenance_notes = []
        skip_sat = False
        skip_return = False
        
        if maint.get("supply_sensor") == "FAULTY":
            skip_sat = True
            maintenance_notes.append("Üfleme sensörü arızalı - SAT verisi güvenilmez")
        if maint.get("return_sensor") == "FAULTY":
            skip_return = True
            maintenance_notes.append("Emiş sensörü arızalı - Emiş verisi güvenilmez")
        if maint.get("heating_valve_body") == "FAULTY":
            maintenance_notes.append("Isıtma vanası gövdesi arızalı - Bilinen arıza")
        if maint.get("cooling_valve_body") == "FAULTY":
            maintenance_notes.append("Soğutma vanası gövdesi arızalı - Bilinen arıza")
        if maint.get("heating_valve_signal") == "FAULTY":
            maintenance_notes.append("Isıtma vanası 0-10V arızalı - Vana pozisyonu güvenilmez")
        if maint.get("cooling_valve_signal") == "FAULTY":
            maintenance_notes.append("Soğutma vanası 0-10V arızalı - Vana pozisyonu güvenilmez")
        
        result.maintenance_notes = maintenance_notes
        
        # --- 0. STANDBY CHECK ---
        standby = self._analyze_base(profile, result, oat)
        if standby is not None:
            return standby

        # AHU Logic: Focus on SAT (Supply Air Temp) vs Setpoint vs Return
        sat = profile.temperatures.sat or profile.temperatures.supply
        ret = profile.temperatures.return_ or profile.temperatures.room
        set_temp = profile.temperatures.setpoint

        delta_t = result.delta_t
        target_dt = result.target_delta_t

        # P2 Fix: AHU departure — delta_t yoksa SAT vs setpoint mutlak farkını kullan
        if result.departure is None and sat is not None and set_temp is not None:
            result.departure = abs(sat - set_temp)

        # Calculate approach
        app_sup, app_ret = self.calculate_approach(profile, plant_supply, plant_return)
        result.approach_supply = app_sup
        result.approach_return = app_ret

        # --- 1. PERFORMANCE CHECK ---
        is_heating = "HEAT" in effective_mode
        
        # Default Logic (similar to base but customized)
        if delta_t is None:
            result.status = "MISSING_DATA"
            result.band = "N/A"
            result.action = "Veri Eksik"
            result.rule = "MISSING_DATA"
            result.score = 5.0  # Sıralamada dibe düşmemesi için minimum skor
        else:
            check_tolerance = tol_crit if "kritik" in profile.priority.lower() else tol_norm
            if delta_t < (target_dt - check_tolerance):
                result.status = "LOW"
                result.action = "Düşük ΔT"
                result.reason = f"ΔT ({delta_t:.1f}) < Hedef ({target_dt:.1f})"
                result.rule = "LOW_DT"
            elif delta_t > (target_dt + check_tolerance):
                result.status = "HIGH"
                result.action = "Yüksek ΔT"
                result.reason = f"ΔT ({delta_t:.1f}) > Hedef ({target_dt:.1f})"
                result.rule = "HIGH_DT"
            else:
                result.status = "IN_BAND"
                result.band = f"±{check_tolerance}"
                result.action = "Normal"
                result.rule = "NORMAL"
        
        # --- 2. FUNCTIONAL CHECK (SAT vs Setpoint) ---
        # NOT: Bu inline SAT kontrolü, genel analyze_sat_status() fonksiyonunun
        # AHU-özel versiyonudur ve öncelikli olarak çalışır. İki mantığı
        # birleştirirken dikkat edin; inline AHU kontrolleri daha hassastır.
        # VANA EŞİK KONTROLÜ: Vana <%40 ise SAT kontrolü yapılmaz
        VALVE_THRESHOLD = 40.0
        heating_valve = profile.valves.heating if profile.valves.heating is not None else 0
        cooling_valve = profile.valves.cooling if profile.valves.cooling is not None else 0
        
        # İlgili vana değerini al
        relevant_valve = heating_valve if is_heating else cooling_valve
        
        # Vana yeterince açık değilse SAT kontrolü ATLA
        if relevant_valve < VALVE_THRESHOLD:
            result.sat_status = "VALVE_LOW"
            # SAT kontrolü yapılmadan devam et
        elif sat is not None:
            if is_heating:
                # Isıtma: SAT 28-35°C aralığında olmalı
                sat_min = self.config.get("SAT_HEATING_MIN", 28.0)
                sat_max = self.config.get("SAT_HEATING_MAX", 35.0)
                
                if sat < sat_min:
                    result.sat_status = "NOT_HEATING"
                    result.action = "KRİTİK: Isıtmıyor"
                    result.reason = f"Üfleme ({sat:.1f}°C) < {sat_min}°C. Vana veya kazan kontrolü gerekli."
                    result.severity = "CRITICAL"
                    result.score = 9.0
                    result.rule = "NOT_HEATING"
                elif sat > sat_max:
                    result.sat_status = "WARNING"
                    result.action = "UYARI: SAT Yüksek"
                    result.reason = f"Üfleme ({sat:.1f}°C) > {sat_max}°C. Aşırı ısıtma."
                    result.severity = "WARNING"
                    result.rule = "SAT_HIGH"
                else:
                    result.sat_status = "OPTIMAL"
            else:
                # Soğutma: SAT 15-18°C aralığında olmalı
                sat_min = self.config.get("SAT_COOLING_MIN", 15.0)
                sat_max = self.config.get("SAT_COOLING_MAX", 18.0)
                
                if sat > sat_max:
                    result.sat_status = "NOT_COOLING"
                    result.action = "KRİTİK: Soğutmuyor"
                    result.reason = f"Üfleme ({sat:.1f}°C) > {sat_max}°C. Vana veya chiller kontrolü gerekli."
                    result.severity = "CRITICAL"
                    result.score = 9.0
                    result.rule = "NOT_COOLING"
                elif sat < sat_min:
                    result.sat_status = "WARNING"
                    result.action = "UYARI: SAT Düşük"
                    result.reason = f"Üfleme ({sat:.1f}°C) < {sat_min}°C. Aşırı soğutma/donma riski."
                    result.severity = "WARNING"
                    result.rule = "SAT_LOW"
                else:
                    result.sat_status = "OPTIMAL"

        # --- 3. SPECIAL CONDITIONS ---
        special = self.check_special_conditions(profile, delta_t, effective_mode=effective_mode)
        if special["rule"]:
            result.action = special["action"]
            result.reason = special["reason"]
            result.rule = special["rule"]
            result.severity = "CRITICAL" if "KRİTİK" in special["action"] else "WARNING"
            result.score = max(result.score, 8.0)
        
        # Calculate final score — mevcut skorla max al; özel kural veya SAT skoru korunur (P1-1)
        result.score = max(result.score, self.calculate_score(
            profile, delta_t, target_dt, result.departure,
            result.sat_status, result.rule
        ))
        
        # Calculate recommended SAT (effective_mode geçiriliyor)
        result.recommended_sat = self.calculate_recommended_sat(
            profile, result.sat_status, result.approach_supply, result.rule,
            effective_mode=effective_mode
        )
            
        return result

    def analyze_fcu_performance(self, profile: EquipmentProfile, effective_mode: str,
                              plant_supply, plant_return, oat, tol_crit, tol_norm) -> AnalysisResult:
        """Standard logic for FCU and others (Room vs Set focus)."""
        result = AnalysisResult()
        
        # --- 0. STANDBY CHECK ---
        standby = self._analyze_base(profile, result, oat)
        if standby is not None:
            return standby

        delta_t = result.delta_t
        target_dt = result.target_delta_t

        # Determine Status
        if delta_t is None:
            result.status = "MISSING_DATA"
            result.band = "N/A"
            result.score = 5.0  # Sıralamada dibe düşmemesi için minimum skor
        else:
            tolerance = tol_crit if "kritik" in profile.priority.lower() else tol_norm
            lower = target_dt - tolerance
            upper = target_dt + tolerance
            
            if delta_t < lower:
                result.status = "LOW"
                result.band = f"±{tolerance:.1f}"
            elif delta_t > upper:
                result.status = "HIGH"
                result.band = f"±{tolerance:.1f}"
            else:
                result.status = "IN_BAND"
                result.band = f"±{tolerance:.1f}"
                
        # Analyze SAT Status (Generic)
        result.sat_status = self.analyze_sat_status(profile)
        
        # Calculate approach
        app_sup, app_ret = self.calculate_approach(profile, plant_supply, plant_return)
        result.approach_supply = app_sup
        result.approach_return = app_ret

        # --- COMFORT CHECK (FCU Specific) ---
        departure = self.calculate_departure(profile) # abs(room - set)
        if departure is not None and departure > 2.0:
             # Vana açık mı diye bak
            v_cool = profile.valves.cooling or 0
            v_heat = profile.valves.heating or 0
            is_valve_open = v_cool > 80 or v_heat > 80
            
            if is_valve_open:
                result.action = "Yetersiz Kapasite / Verimsiz"
                result.reason = f"Oda ({profile.temperatures.room}°C) Set'ten ({profile.temperatures.setpoint}°C) uzak ama vana açık."
                result.severity = "WARNING"
                result.score = 7.5
        
        # Check special conditions
        special_conditions = self.check_special_conditions(profile, delta_t, effective_mode=effective_mode)
        if special_conditions["rule"]:
            result.action = special_conditions["action"]
            result.reason = special_conditions["reason"]
            result.rule = special_conditions["rule"]

        else:
             # Standard Recommendations
            if result.status == "LOW":
                result.action = "ΔT Hedef Altında - Akış Azalt"
                result.reason = f"ΔT ({delta_t:.1f}°C) < Hedef ({target_dt:.1f}°C)"
                result.rule = "BAND_LOW"
            elif result.status == "HIGH":
                result.action = "ΔT Hedef Üstünde - Akış Artır"
                result.reason = f"ΔT ({delta_t:.1f}°C) > Hedef ({target_dt:.1f}°C)"
                result.rule = "BAND_HIGH"
            elif result.status == "IN_BAND":
                result.action = "Normal"
                result.reason = "Hedef band içinde"
                result.rule = "IN_BAND"
            elif result.status == "MISSING_DATA":
                result.action = "Veri Eksik"
                result.reason = "ΔT hesaplanamadı - sensör verisi eksik"
                result.rule = "MISSING_DATA"
                
        # Recommend SAT logic
        result.recommended_sat = self.calculate_recommended_sat(
            profile, result.sat_status, result.approach_supply, result.rule
        )
        
        # Calculate score — comfort check score'u koruyarak max al (P1-1)
        result.score = max(result.score, self.calculate_score(
            profile, delta_t, target_dt, result.departure,
            result.sat_status, result.rule
        ))
        
        # Map severity for UI (considering rule type)
        result.severity = self.map_severity(result.status, result.score)
        
        # Override severity for specific rules
        if result.rule in ["BAND_LOW", "BAND_HIGH"]:
            result.severity = "WARNING"
        elif result.rule in ["IN_BAND", "NORMAL"]:
            result.severity = "OPTIMAL"
        
        return result

# ================ FASTAPI UYGULAMASI ================
app = FastAPI(title=CONFIG["APP_TITLE"])

# Logging setup — UTF-8 stream handler (Windows charmap uyumluluğu)
_log_handler = logging.StreamHandler(stream=open(sys.stderr.fileno(), 'w', encoding='utf-8', closefd=False))
_log_handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logging.basicConfig(
    level=logging.INFO,
    handlers=[_log_handler]
)
logger = logging.getLogger(__name__)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:8005", "http://localhost:8501"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

# Hata yönetimi
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    return JSONResponse(
        {"success": False, "detail": exc.detail},
        status_code=exc.status_code
    )

@app.exception_handler(Exception)
async def unhandled_exception_handler(request: Request, exc: Exception):
    logger.exception("Unhandled exception")
    return JSONResponse(
        {"success": False, "detail": f"Internal Server Error: {type(exc).__name__}"},
        status_code=500
    )

# Statik dosyalar
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(STATIC_DIR, exist_ok=True)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

# Çıktı dizini
OUTPUT_DIR = os.path.join(STATIC_DIR, "outputs")
os.makedirs(OUTPUT_DIR, exist_ok=True)

# ================ INPUT VALIDATION ================

def validate_equipment_data(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Validate equipment data for correct ranges and required fields.
    
    Returns:
        dict: {"valid": bool, "errors": List[str], "warnings": List[str]}
    """
    errors = []
    warnings = []
    
    # Temperature field names (all possible variations)
    temp_fields = [
        "Supply (°C)", "Return (°C)", "Inlet (°C)", "Outlet (°C)",
        "Room (°C)", "Set (°C)", "SAT (°C)", 
        "Plant Supply (°C)", "Plant Return (°C)"
    ]
    
    # Valve field names
    valve_fields = ["Cool Valve (%)", "Heat Valve (%)"]
    
    # Required fields
    required_fields = ["Type", "Name"]
    
    for idx, row in enumerate(rows, start=1):
        row_id = f"Satır {idx}"
        equipment_name = row.get("Name", row_id)
        
        # Check required fields
        for field in required_fields:
            value = row.get(field)
            if not value or (isinstance(value, str) and value.strip() == ""):
                errors.append(f"{equipment_name}: '{field}' alanı zorunludur")
        
        # Validate temperature ranges (-10°C to +100°C)
        for field in temp_fields:
            value = row.get(field)
            if value is not None and value != "":
                try:
                    temp = float(value)
                    if temp < -10 or temp > 100:
                        errors.append(
                            f"{equipment_name}: '{field}' değeri geçersiz ({temp}°C). "
                            f"Geçerli aralık: -10°C ile +100°C arası"
                        )
                except (ValueError, TypeError):
                    # Skip non-numeric values (they might be intentionally empty)
                    pass
        
        # Validate valve percentages (0-100%)
        for field in valve_fields:
            value = row.get(field)
            if value is not None and value != "":
                try:
                    valve = float(value)
                    if valve < 0 or valve > 100:
                        errors.append(
                            f"{equipment_name}: '{field}' değeri geçersiz ({valve}%). "
                            f"Geçerli aralık: 0% ile 100% arası"
                        )
                except (ValueError, TypeError):
                    pass
        
        # Logical validation: Supply vs Return (cooling mode)
        mode = str(row.get("Mode", "")).upper()
        supply = row.get("Supply (°C)")
        return_temp = row.get("Return (°C)")
        
        if supply is not None and return_temp is not None:
            try:
                supply_val = float(supply)
                return_val = float(return_temp)
                
                if "COOL" in mode:
                    if supply_val > return_val:
                        warnings.append(
                            f"{equipment_name}: Soğutma modunda Supply ({supply_val}°C) "
                            f"Return'den ({return_val}°C) yüksek. Kontrol edin."
                        )
                elif "HEAT" in mode:
                    if supply_val < return_val:
                        warnings.append(
                            f"{equipment_name}: Isıtma modunda Supply ({supply_val}°C) "
                            f"Return'den ({return_val}°C) düşük. Kontrol edin."
                        )
            except (ValueError, TypeError):
                pass
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings
    }

# ================ API ENDPOINTS ================

@app.get("/", include_in_schema=False)
async def portal_home():
    """Ana giriş ekranı (HVAC / Enerji)."""
    return HTMLResponse(_load_or_create_portal_html())

@app.get("/home", include_in_schema=False)
async def home_redirect():
    return RedirectResponse(url="/", status_code=302)

@app.get("/hvac", include_in_schema=False)
async def hvac_entry():
    """HVAC arayüzünü portal çerçevesinde aç."""
    _bootstrap_static_assets()
    hvac_ui = "/static/index.html"
    title = "HVAC ΔT Öneri Motoru"
    return HTMLResponse(_iframe_wrapper_html(title=title, iframe_src=hvac_ui))

@app.get("/enerji", include_in_schema=False)
async def enerji_entry():
    """Enerji (Streamlit) uygulamasını portal çerçevesinde aç."""
    streamlit_url = os.environ.get("STREAMLIT_URL", "http://localhost:8501").rstrip("/")
    iframe_src = f"{streamlit_url}/?embed=true"
    title = "Enerji Yönetimi & Raporlama"
    return HTMLResponse(_iframe_wrapper_html(title=title, iframe_src=iframe_src))

# --- Portal yardımcıları (Acıbadem temalı ana sayfa) ---
ACIBADEM_PRIMARY = os.environ.get("ACIBADEM_PRIMARY", "#012D75")  # koyu mavi

def _bootstrap_static_assets():
    """static/index.html yoksa kök dizindeki index.html'i kopyala (HVAC UI için)."""
    try:
        os.makedirs(STATIC_DIR, exist_ok=True)
        # HVAC UI
        hvac_static = os.path.join(STATIC_DIR, "index.html")
        hvac_root = os.path.join(os.path.dirname(__file__), "index.html")
        if (not os.path.exists(hvac_static)) and os.path.exists(hvac_root):
            shutil.copyfile(hvac_root, hvac_static)
    except Exception:
        # sessiz geç: portal yine de çalışır
        pass

def _load_or_create_portal_html() -> str:
    """Portal HTML'ini static/portal.html olarak tut; yoksa üret."""
    _bootstrap_static_assets()
    portal_path = os.path.join(STATIC_DIR, "portal.html")
    if not os.path.exists(portal_path):
        html = _portal_html()
        try:
            with open(portal_path, "w", encoding="utf-8") as f:
                f.write(html)
        except Exception:
            return html
    try:
        with open(portal_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return _portal_html()

def _portal_html() -> str:
    # Modern, premium ve dinamik görsel düzen
    return f"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>Acıbadem Sağlık Grubu — Sistem Girişi</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
  <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.5.1/css/all.min.css" rel="stylesheet">
  <style>
    :root {{
      --acibadem: {ACIBADEM_PRIMARY};
      --acibadem-light: #1a4a9e;
      --bg: #0a0e1a;
      --card: #ffffff;
      --text: #0f172a;
      --text-light: #ffffff;
      --muted: #64748b;
      --border: #e2e8f0;
      --shadow: 0 20px 60px rgba(1, 45, 117, 0.25);
      --glow: 0 0 40px rgba(1, 45, 117, 0.3);
    }}
    
    * {{ 
      box-sizing: border-box;
      margin: 0;
      padding: 0;
    }}
    
    @keyframes gradient {{
      0% {{ background-position: 0% 50%; }}
      50% {{ background-position: 100% 50%; }}
      100% {{ background-position: 0% 50%; }}
    }}
    
    @keyframes float {{
      0%, 100% {{ transform: translateY(0px); }}
      50% {{ transform: translateY(-20px); }}
    }}
    
    @keyframes glow {{
      0%, 100% {{ opacity: 0.5; }}
      50% {{ opacity: 1; }}
    }}
    
    body {{
      margin: 0;
      font-family: 'Inter', system-ui, -apple-system, sans-serif;
      color: var(--text-light);
      background: linear-gradient(-45deg, #0a0e1a, var(--acibadem), #1a2332, var(--acibadem-light));
      background-size: 400% 400%;
      animation: gradient 15s ease infinite;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;
      overflow-x: hidden;
    }}
    
    body::before {{
      content: '';
      position: absolute;
      top: -50%;
      left: -50%;
      width: 200%;
      height: 200%;
      background: radial-gradient(circle, rgba(1,45,117,0.1) 0%, transparent 70%);
      animation: float 20s ease-in-out infinite;
    }}
    
    .wrap {{
      max-width: 1200px;
      width: 100%;
      margin: 0 auto;
      padding: 60px 24px;
      position: relative;
      z-index: 1;
    }}
    
    .brand {{
      text-align: center;
      margin-bottom: 60px;
      animation: float 6s ease-in-out infinite;
    }}
    
    .logo-container {{
      width: 120px;
      height: 120px;
      margin: 0 auto 24px;
      background: rgba(255, 255, 255, 0.1);
      backdrop-filter: blur(10px);
      border-radius: 30px;
      display: flex;
      align-items: center;
      justify-content: center;
      border: 2px solid rgba(255, 255, 255, 0.2);
      box-shadow: var(--glow);
      animation: glow 3s ease-in-out infinite;
    }}
    
    .logo-container i {{
      font-size: 56px;
      color: white;
    }}
    
    .title {{
      font-weight: 900;
      letter-spacing: 2px;
      color: white;
      font-size: 42px;
      line-height: 1.1;
      text-transform: uppercase;
      margin-bottom: 12px;
      text-shadow: 0 4px 20px rgba(0, 0, 0, 0.3);
    }}
    
    .subtitle {{
      color: rgba(255, 255, 255, 0.9);
      font-weight: 500;
      font-size: 18px;
      letter-spacing: 0.5px;
    }}
    
    .cards {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(400px, 1fr));
      gap: 32px;
      margin-top: 48px;
    }}
    
    @media (max-width: 900px) {{
      .cards {{ 
        grid-template-columns: 1fr;
        gap: 24px;
      }}
    }}
    
    .card {{
      background: rgba(255, 255, 255, 0.95);
      backdrop-filter: blur(20px);
      border: 1px solid rgba(255, 255, 255, 0.3);
      border-radius: 24px;
      box-shadow: var(--shadow);
      padding: 40px 32px;
      position: relative;
      overflow: hidden;
      transition: all 0.4s cubic-bezier(0.175, 0.885, 0.32, 1.275);
      cursor: pointer;
    }}
    
    .card::before {{
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 6px;
      background: linear-gradient(90deg, var(--acibadem), var(--acibadem-light));
      transform: scaleX(0);
      transform-origin: left;
      transition: transform 0.4s ease;
    }}
    
    .card:hover::before {{
      transform: scaleX(1);
    }}
    
    .card::after {{
      content: '';
      position: absolute;
      inset: 0;
      background: linear-gradient(135deg, rgba(1,45,117,0.05), transparent 60%);
      opacity: 0;
      transition: opacity 0.4s ease;
    }}
    
    .card:hover {{
      transform: translateY(-12px) scale(1.02);
      box-shadow: 0 30px 80px rgba(1, 45, 117, 0.35);
    }}
    
    .card:hover::after {{
      opacity: 1;
    }}
    
    .icon {{
      width: 80px;
      height: 80px;
      border-radius: 20px;
      display: flex;
      align-items: center;
      justify-content: center;
      background: linear-gradient(135deg, var(--acibadem), var(--acibadem-light));
      color: white;
      font-size: 36px;
      margin-bottom: 24px;
      position: relative;
      box-shadow: 0 10px 30px rgba(1, 45, 117, 0.3);
      transition: all 0.4s ease;
    }}
    
    .card:hover .icon {{
      transform: rotate(5deg) scale(1.1);
      box-shadow: 0 15px 40px rgba(1, 45, 117, 0.5);
    }}
    
    .card h2 {{
      margin: 0 0 12px 0;
      font-size: 28px;
      font-weight: 800;
      color: var(--text);
      position: relative;
    }}
    
    .card p {{
      margin: 0 0 24px 0;
      color: var(--muted);
      line-height: 1.6;
      font-size: 15px;
      position: relative;
    }}
    
    .btn {{
      display: inline-flex;
      align-items: center;
      gap: 12px;
      padding: 16px 28px;
      border-radius: 14px;
      background: linear-gradient(135deg, var(--acibadem), var(--acibadem-light));
      color: white;
      font-weight: 700;
      font-size: 15px;
      text-decoration: none;
      position: relative;
      overflow: hidden;
      transition: all 0.3s ease;
      box-shadow: 0 4px 15px rgba(1, 45, 117, 0.3);
    }}
    
    .btn::before {{
      content: '';
      position: absolute;
      inset: 0;
      background: linear-gradient(135deg, var(--acibadem-light), var(--acibadem));
      opacity: 0;
      transition: opacity 0.3s ease;
    }}
    
    .btn:hover::before {{
      opacity: 1;
    }}
    
    .btn:hover {{
      transform: translateX(4px);
      box-shadow: 0 6px 25px rgba(1, 45, 117, 0.5);
    }}
    
    .btn i, .btn span {{
      position: relative;
      z-index: 1;
    }}
    
    .foot {{
      margin-top: 60px;
      text-align: center;
      display: flex;
      justify-content: center;
      gap: 16px;
      flex-wrap: wrap;
    }}
    
    .pill {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 12px 20px;
      border-radius: 999px;
      background: rgba(255, 255, 255, 0.15);
      backdrop-filter: blur(10px);
      border: 1px solid rgba(255, 255, 255, 0.2);
      color: white;
      font-size: 14px;
      font-weight: 600;
      transition: all 0.3s ease;
    }}
    
    .pill:hover {{
      background: rgba(255, 255, 255, 0.25);
      transform: translateY(-2px);
    }}
    
    .pill i {{
      font-size: 16px;
    }}
    
    @media (max-width: 600px) {{
      .title {{
        font-size: 32px;
      }}
      
      .subtitle {{
        font-size: 16px;
      }}
      
      .card {{
        padding: 28px 24px;
      }}
      
      .cards {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <div class="wrap">
    <div class="brand">
      <div class="logo-container">
        <i class="fa-solid fa-hospital"></i>
      </div>
      <div class="title">ACIBADEM SAĞLIK GRUBU</div>
      <div class="subtitle">Enerji & HVAC Yönetim Sistemi</div>
    </div>

    <div class="cards">
      <div class="card" onclick="window.location.href='/hvac'">
        <div class="icon"><i class="fa-solid fa-wind"></i></div>
        <h2>HVAC Optimizasyon</h2>
        <p>Delta-T analizi, ekipman performans takibi ve akıllı öneri sistemi ile HVAC sistemlerinizi optimize edin.</p>
        <a class="btn" href="/hvac">
          <span>HVAC'ı Aç</span>
          <i class="fa-solid fa-arrow-right"></i>
        </a>
      </div>

      <div class="card" onclick="window.location.href='/enerji'">
        <div class="icon"><i class="fa-solid fa-bolt"></i></div>
        <h2>Enerji Yönetimi</h2>
        <p>Günlük enerji tüketimi takibi, detaylı raporlama ve trend analizi ile enerji verimliliğinizi artırın.</p>
        <a class="btn" href="/enerji">
          <span>Enerji'yi Aç</span>
          <i class="fa-solid fa-arrow-right"></i>
        </a>
      </div>
    </div>

    <div class="foot">
      <div class="pill">
        <i class="fa-solid fa-shield-heart"></i>
        <span>Güvenli Portal</span>
      </div>
      <div class="pill">
        <i class="fa-solid fa-chart-line"></i>
        <span>Gerçek Zamanlı Analiz</span>
      </div>
      <div class="pill">
        <i class="fa-solid fa-link"></i>
        <span>API: /docs</span>
      </div>
    </div>
  </div>
</body>
</html>"""

def _iframe_wrapper_html(title: str, iframe_src: str) -> str:
    return f"""<!doctype html>
<html lang="tr">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width,initial-scale=1" />
  <title>{title}</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap" rel="stylesheet">
  <style>
    :root {{
      --acibadem: {ACIBADEM_PRIMARY};
      --bg: #0b1220;
      --panel: #ffffff;
      --muted: #475569;
      --border: #e2e8f0;
      --shadow: 0 12px 35px rgba(15, 23, 42, 0.12);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: Inter, system-ui, -apple-system, Segoe UI, Roboto, Arial, sans-serif;
      background: #f6f8fb;
    }}
    .topbar {{
      position: sticky;
      top: 0;
      z-index: 10;
      background: rgba(255,255,255,0.92);
      backdrop-filter: blur(8px);
      border-bottom: 1px solid var(--border);
    }}
    .topbar-inner {{
      max-width: 1400px;
      margin: 0 auto;
      padding: 12px 14px;
      display:flex;
      align-items:center;
      justify-content:space-between;
      gap: 10px;
    }}
    .left {{
      display:flex; align-items:center; gap: 10px;
    }}
    .brand {{
      font-weight: 800;
      color: var(--acibadem);
      letter-spacing: 0.4px;
      text-transform: uppercase;
      font-size: 14px;
    }}
    .title {{
      font-weight: 700;
      color: #0f172a;
      font-size: 14px;
      opacity: 0.85;
    }}
    a.home {{
      display:inline-flex;
      align-items:center;
      gap: 10px;
      padding: 10px 12px;
      border-radius: 12px;
      border: 1px solid rgba(1,45,117,0.25);
      background: rgba(1,45,117,0.06);
      color: var(--acibadem);
      font-weight: 800;
      text-decoration:none;
      white-space: nowrap;
    }}
    a.home:hover {{
      background: rgba(1,45,117,0.12);
      border-color: rgba(1,45,117,0.35);
    }}
    .frame {{
      width: 100%;
      height: calc(100vh - 58px);
      border: 0;
      display:block;
      background: #fff;
    }}
  </style>
</head>
<body>
  <div class="topbar">
    <div class="topbar-inner">
      <div class="left">
        <div class="brand">ACIBADEM SAĞLIK GRUBU</div>
        <div class="title">— {title}</div>
      </div>
      <div style="display:flex; align-items:center; gap:10px;"><a class="home" href="/" target="_top">⬅ Ana Sayfa</a><a class="home" href="{iframe_src}" target="_blank" style="background:rgba(1,45,117,0.03); font-weight:700;">↗ Ayrı Sekmede Aç</a></div>
    </div>
  </div>
  <iframe class="frame" src="{iframe_src}" loading="lazy"></iframe>
</body>
</html>"""

# ================ AYARLAR API'LERİ ================

@app.get("/api/settings")
async def get_settings():
    """Mevcut ayarları getir."""
    # List'leri hariç tut (UI'da gösterilmeyecek)
    settings = {k: v for k, v in CONFIG.items() if not isinstance(v, list) and k != "APP_TITLE"}
    return {
        "success": True,
        "settings": settings,
        "defaults": {k: v for k, v in DEFAULT_CONFIG.items() if not isinstance(v, list) and k != "APP_TITLE"}
    }

@app.post("/api/settings")
async def save_settings(request: Request):
    """Ayarları kaydet."""
    try:
        body = await request.json()
        new_settings = body.get("settings", {})
        
        if not new_settings:
            raise HTTPException(status_code=400, detail="Ayarlar boş olamaz")
        
        success = save_settings_to_file(new_settings)
        
        if success:
            return {"success": True, "message": "Ayarlar kaydedildi"}
        else:
            raise HTTPException(status_code=500, detail="Ayarlar kaydedilemedi")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Geçersiz JSON formatı")

@app.post("/api/settings/reset")
async def reset_settings():
    """Ayarları varsayılana döndür."""
    success = reset_settings_to_default()
    if success:
        return {"success": True, "message": "Ayarlar varsayılana döndürüldü"}
    else:
        raise HTTPException(status_code=500, detail="Ayarlar sıfırlanamadı")

# ================ BAKIM KARTLARI API ================

@app.get("/api/maintenance")
async def get_all_maintenance():
    """Tüm bakım kartlarını getir."""
    data = load_maintenance_cards()
    return {
        "success": True,
        "data": data,
        "components": MAINTENANCE_COMPONENTS,
        "statuses": MAINTENANCE_STATUSES,
        "labels": MAINTENANCE_LABELS
    }

@app.post("/api/maintenance")
async def save_maintenance(request: Request):
    """Bakım kartlarını kaydet."""
    try:
        body = await request.json()
        cards = body.get("cards", {})
        
        if not cards:
            raise HTTPException(status_code=400, detail="Bakım kartı verisi boş")
        
        # Validate statuses
        for eq_name, card in cards.items():
            for comp in MAINTENANCE_COMPONENTS:
                if comp in card and card[comp] not in MAINTENANCE_STATUSES:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Geçersiz durum: {card[comp]} (İzin verilenler: {MAINTENANCE_STATUSES})"
                    )
        
        data = {
            "last_updated": datetime.datetime.now().isoformat(),
            "updated_by": body.get("updated_by", "Operatör"),
            "cards": cards
        }
        
        success = save_maintenance_cards(data)
        if success:
            return {"success": True, "message": f"{len(cards)} cihazın bakım kartı kaydedildi"}
        else:
            raise HTTPException(status_code=500, detail="Bakım kartları kaydedilemedi")
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Geçersiz JSON formatı")

@app.get("/api/maintenance/{equipment_name}")
async def get_equipment_maintenance(equipment_name: str):
    """Tek bir cihazın bakım kartını getir."""
    card = get_maintenance_card(equipment_name)
    notes = get_maintenance_notes(equipment_name)
    return {
        "success": True,
        "equipment": equipment_name,
        "card": card,
        "notes": notes,
        "has_issues": any(card.get(c) in ["FAULTY", "MAINTENANCE"] for c in MAINTENANCE_COMPONENTS)
    }

# ================ GÜNLÜK RAPOR ================

import threading
from fastapi.responses import FileResponse

def _generate_daily_report():
    """Otomatik günlük rapor PDF'i oluştur."""
    try:
        from daily_report import DailyReportGenerator
        gen = DailyReportGenerator()
        filepath = gen.generate()
        logging.info(f"Günlük rapor oluşturuldu: {filepath}")
        # Bildirim dosyası yaz
        _write_report_notification("daily", filepath)
    except Exception as e:
        logging.error(f"Günlük rapor hatası: {e}")

# Global timer referansları (ayar değişince iptal + yeniden zamanlama için)
_daily_timer = None
_monthly_timer = None
_daily_stop_event = threading.Event()
_monthly_stop_event = threading.Event()

def _write_report_notification(report_type: str, filepath: str):
    """Otomatik rapor oluşturulduğunda bildirim dosyası yaz."""
    try:
        notif_dir = os.path.join(os.path.dirname(__file__), "configs")
        os.makedirs(notif_dir, exist_ok=True)
        notif_file = os.path.join(notif_dir, "report_notifications.json")
        
        # Mevcut bildirimleri oku
        notifications = {}
        if os.path.exists(notif_file):
            with open(notif_file, "r", encoding="utf-8") as f:
                notifications = json.load(f)
        
        # Yeni bildirimi ekle
        notifications[report_type] = {
            "filepath": filepath,
            "filename": os.path.basename(filepath),
            "timestamp": datetime.datetime.now().strftime("%d.%m.%Y %H:%M"),
            "seen": False
        }
        
        with open(notif_file, "w", encoding="utf-8") as f:
            json.dump(notifications, f, indent=2, ensure_ascii=False)
        
        logging.debug(f"Rapor bildirimi kaydedildi: {report_type} → {filepath}")
    except Exception as e:
        logging.error(f"Bildirim yazma hatası: {e}")

def _schedule_daily_report(from_settings_change=False):
    """Config'ten okunan saatte günlük rapor üretimi zamanlayıcısı.
    Polling tabanlı: her 30 saniyede saati kontrol eder."""
    global _daily_timer, _daily_stop_event
    # Eski thread varsa stop flag ile durdur
    if _daily_timer is not None and _daily_timer.is_alive():
        _daily_stop_event.set()
        _daily_timer.join(timeout=5)
    _daily_stop_event = threading.Event()
    
    hour = int(CONFIG.get("DAILY_REPORT_HOUR", 17))
    minute = int(CONFIG.get("DAILY_REPORT_MINUTE", 0))
    
    # Ayar değişikliğinden geliyorsa ve saat geçmişse → hemen üret
    if from_settings_change:
        now = datetime.datetime.now()
        target_today = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        if now >= target_today:
            logging.info(f"Günlük rapor saati geçmiş ({hour:02d}:{minute:02d}), 30 saniye içinde üretilecek...")
            def run_immediate():
                import time
                time.sleep(30)
                _generate_daily_report()
            t = threading.Thread(target=run_immediate, daemon=True)
            t.start()
    
    # Polling thread: her 30 sn kontrol et
    _daily_generated_today = {"date": None}
    
    # Sunucu açılışında bugünün raporu zaten varsa işaretle (tekrar üretme)
    _today_check = datetime.datetime.now().strftime("%Y%m%d")
    _yesterday_check = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")
    _daily_report_dir = os.path.join(os.path.dirname(__file__), "daily_reports")
    for _check_date in [_today_check, _yesterday_check]:
        _check_file = os.path.join(_daily_report_dir, f"gunluk_rapor_{_check_date}.pdf")
        if os.path.exists(_check_file):
            _mod = datetime.datetime.fromtimestamp(os.path.getmtime(_check_file))
            if _mod.strftime("%Y-%m-%d") == datetime.datetime.now().strftime("%Y-%m-%d"):
                _daily_generated_today["date"] = datetime.datetime.now().strftime("%Y-%m-%d")
                logging.debug(f"Bugünün günlük raporu zaten mevcut, tekrar üretilmeyecek.")
                break
    
    stop_event = _daily_stop_event  # closure için yerel referans
    
    def daily_polling_loop():
        import time
        while not stop_event.is_set():
            try:
                now = datetime.datetime.now()
                target_h = int(CONFIG.get("DAILY_REPORT_HOUR", 17))
                target_m = int(CONFIG.get("DAILY_REPORT_MINUTE", 0))
                today_str = now.strftime("%Y-%m-%d")
                
                target_time = now.replace(hour=target_h, minute=target_m, second=0, microsecond=0)
                
                if now >= target_time and _daily_generated_today["date"] != today_str:
                    logging.info(f"Günlük rapor üretim zamanı geldi: {target_h:02d}:{target_m:02d}")
                    _daily_generated_today["date"] = today_str
                    _generate_daily_report()
                    logging.info("Günlük rapor başarıyla üretildi.")
            except Exception as e:
                logging.error(f"Günlük rapor polling hatası: {e}")
            
            stop_event.wait(30)  # Event ile bekleme — stop anında hemen çıkar
    
    _daily_timer = threading.Thread(target=daily_polling_loop, daemon=True, name="daily_report_poller")
    _daily_timer.start()
    logging.info(f"Günlük rapor zamanlayıcı başlatıldı → Hedef: {hour:02d}:{minute:02d} (polling)")

# ─── Sunucu başlangıcında mevcut raporları kontrol et ───
def _check_existing_reports_on_startup():
    """Sunucu başladığında mevcut günlük/aylık raporları kontrol edip
    bildirim dosyası yoksa otomatik oluşturur."""
    try:
        notif_file = os.path.join(os.path.dirname(__file__), "configs", "report_notifications.json")
        notifications = {}
        if os.path.exists(notif_file):
            with open(notif_file, "r", encoding="utf-8") as f:
                notifications = json.load(f)
        
        changed = False
        
        # Günlük rapor kontrolü — dünün raporunu ara
        if "daily" not in notifications or not notifications.get("daily", {}).get("filepath"):
            yesterday = (datetime.datetime.now() - datetime.timedelta(days=1)).strftime("%Y%m%d")
            daily_dir = os.path.join(os.path.dirname(__file__), "daily_reports")
            if os.path.isdir(daily_dir):
                # En son üretilen raporu bul
                daily_files = sorted(
                    [f for f in os.listdir(daily_dir) if f.startswith("gunluk_rapor_") and f.endswith(".pdf")],
                    reverse=True
                )
                if daily_files:
                    latest = daily_files[0]
                    filepath = os.path.join(daily_dir, latest)
                    mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(filepath))
                    # Son 24 saat içinde oluşturulmuşsa bildirim yaz
                    if (datetime.datetime.now() - mod_time).total_seconds() < 86400:
                        notifications["daily"] = {
                            "filepath": filepath,
                            "filename": latest,
                            "timestamp": mod_time.strftime("%d.%m.%Y %H:%M"),
                            "seen": False
                        }
                        changed = True
                        logging.debug(f"Başlangıç: Mevcut günlük rapor bulundu → {latest}")
        
        # Aylık rapor kontrolü
        if "monthly" not in notifications or not notifications.get("monthly", {}).get("filepath"):
            monthly_dir = os.path.join(os.path.dirname(__file__), "monthly_reports_summary")
            if os.path.isdir(monthly_dir):
                monthly_files = sorted(
                    [f for f in os.listdir(monthly_dir) if f.endswith(".pdf")],
                    reverse=True
                )
                if monthly_files:
                    latest = monthly_files[0]
                    filepath = os.path.join(monthly_dir, latest)
                    mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(filepath))
                    # Son 31 gün içinde oluşturulmuşsa bildirim yaz
                    if (datetime.datetime.now() - mod_time).total_seconds() < 31 * 86400:
                        notifications["monthly"] = {
                            "filepath": filepath,
                            "filename": latest,
                            "timestamp": mod_time.strftime("%d.%m.%Y %H:%M"),
                            "seen": False
                        }
                        changed = True
                        logging.debug(f"Başlangıç: Mevcut aylık rapor bulundu → {latest}")
        
        if changed:
            os.makedirs(os.path.join(os.path.dirname(__file__), "configs"), exist_ok=True)
            with open(notif_file, "w", encoding="utf-8") as f:
                json.dump(notifications, f, indent=2, ensure_ascii=False)
            logging.debug("Başlangıç: Rapor bildirimleri güncellendi.")
    except Exception as e:
        logging.error(f"Başlangıç rapor kontrolü hatası: {e}")

_check_existing_reports_on_startup()


# Zamanlayıcıyı başlat
_schedule_daily_report()

# ─── Aylık Rapor Zamanlayıcı ───
def _generate_monthly_report():
    """Aylık rapor PDF'i oluştur (önceki ay verileri)."""
    try:
        from monthly_summary_report import MonthlyReportGenerator
        gen = MonthlyReportGenerator()
        filepath = gen.generate()
        logging.info(f"Aylık rapor oluşturuldu: {filepath}")
        _write_report_notification("monthly", filepath)
    except Exception as e:
        logging.error(f"Aylık rapor hatası: {e}")

def _schedule_monthly_report(from_settings_change=False):
    """Config'ten okunan gün ve saatte aylık rapor üretimi zamanlayıcısı.
    Polling tabanlı: her 60 saniyede saati kontrol eder."""
    global _monthly_timer, _monthly_stop_event
    # Eski thread varsa stop flag ile durdur
    if _monthly_timer is not None and _monthly_timer.is_alive():
        _monthly_stop_event.set()
        _monthly_timer.join(timeout=5)
    _monthly_stop_event = threading.Event()
    
    day = int(CONFIG.get("MONTHLY_REPORT_DAY", 5))
    hour = int(CONFIG.get("MONTHLY_REPORT_HOUR", 17))
    
    # Ayar değişikliğinden geliyorsa ve saat geçmişse → hemen üret
    if from_settings_change:
        now = datetime.datetime.now()
        if now.day >= day:
            target_today = now.replace(day=day, hour=hour, minute=0, second=0, microsecond=0)
            if now >= target_today:
                logging.info(f"Aylık rapor saati geçmiş ({day}/{hour:02d}:00), 30 saniye içinde üretilecek...")
                def run_immediate():
                    import time
                    time.sleep(30)
                    _generate_monthly_report()
                t = threading.Thread(target=run_immediate, daemon=True)
                t.start()
    
    # Polling thread: her 60 sn kontrol et
    _monthly_generated_this_month = {"month": None}
    
    # Sunucu açılışında bu ayın raporu zaten varsa tekrar üretme
    _monthly_report_dir = os.path.join(os.path.dirname(__file__), "monthly_reports_summary")
    if os.path.isdir(_monthly_report_dir):
        _existing_monthly = sorted(
            [f for f in os.listdir(_monthly_report_dir) if f.endswith(".pdf")],
            reverse=True
        )
        if _existing_monthly:
            _em_path = os.path.join(_monthly_report_dir, _existing_monthly[0])
            _em_mod = datetime.datetime.fromtimestamp(os.path.getmtime(_em_path))
            _em_month = _em_mod.strftime("%Y-%m")
            _cur_month = datetime.datetime.now().strftime("%Y-%m")
            if _em_month == _cur_month:
                _monthly_generated_this_month["month"] = _cur_month
                logging.debug(f"Bu ayın aylık raporu zaten mevcut ({_existing_monthly[0]}), tekrar üretilmeyecek.")
    
    stop_event = _monthly_stop_event  # closure için yerel referans
    
    def monthly_polling_loop():
        import time
        while not stop_event.is_set():
            try:
                now = datetime.datetime.now()
                target_d = int(CONFIG.get("MONTHLY_REPORT_DAY", 5))
                target_h = int(CONFIG.get("MONTHLY_REPORT_HOUR", 17))
                month_str = now.strftime("%Y-%m")
                
                if now.day >= target_d:  # Kaçırma koruması: gün geçmişse de üret
                    target_time = now.replace(day=target_d, hour=target_h, minute=0, second=0, microsecond=0)
                    if now >= target_time and _monthly_generated_this_month["month"] != month_str:
                        logging.info(f"Aylık rapor üretim zamanı geldi: gün {now.day} >= hedef {target_d}, saat {target_h:02d}:00")
                        _monthly_generated_this_month["month"] = month_str
                        _generate_monthly_report()
                        logging.info("Aylık rapor başarıyla üretildi.")
            except Exception as e:
                logging.error(f"Aylık rapor polling hatası: {e}")
            
            stop_event.wait(60)  # Event ile bekleme — stop anında hemen çıkar
    
    _monthly_timer = threading.Thread(target=monthly_polling_loop, daemon=True, name="monthly_report_poller")
    _monthly_timer.start()
    logging.info(f"Aylık rapor zamanlayıcı başlatıldı → Hedef: Her ayın {day}. günü {hour:02d}:00 (polling)")

def _reschedule_all_timers():
    """Tüm zamanlayıcıları yeniden başlat (ayar değişikliği sonrası)."""
    logging.info("Zamanlayıcılar yeniden başlatılıyor (ayar değişikliği)...")
    _schedule_daily_report(from_settings_change=True)
    _schedule_monthly_report(from_settings_change=True)

_schedule_monthly_report()

# ─── Zamanlayıcı Durumu API ───
@app.get("/api/scheduler/status")
async def scheduler_status():
    """Sistem saatini ve zamanlayıcı durumunu göster."""
    now = datetime.datetime.now()
    
    # Günlük rapor bilgisi
    daily_hour = int(CONFIG.get("DAILY_REPORT_HOUR", 17))
    daily_minute = int(CONFIG.get("DAILY_REPORT_MINUTE", 0))
    daily_target_today = now.replace(hour=daily_hour, minute=daily_minute, second=0, microsecond=0)
    
    if now < daily_target_today:
        next_daily = daily_target_today
    else:
        next_daily = daily_target_today + datetime.timedelta(days=1)
    
    daily_remaining = (next_daily - now).total_seconds()
    daily_h = int(daily_remaining // 3600)
    daily_m = int((daily_remaining % 3600) // 60)
    
    # Bugünün günlük raporu var mı?
    daily_dir = os.path.join(os.path.dirname(__file__), "daily_reports")
    today_daily_file = os.path.join(daily_dir, f"gunluk_rapor_{now.strftime('%Y%m%d')}.pdf")
    daily_generated_today = os.path.exists(today_daily_file)
    
    # Aylık rapor bilgisi
    monthly_day = int(CONFIG.get("MONTHLY_REPORT_DAY", 5))
    monthly_hour = int(CONFIG.get("MONTHLY_REPORT_HOUR", 17))
    
    # Bu ayın aylık raporu var mı?
    monthly_dir = os.path.join(os.path.dirname(__file__), "monthly_reports_summary")
    monthly_generated_this_month = False
    monthly_last_file = None
    if os.path.isdir(monthly_dir):
        monthly_pdfs = sorted([f for f in os.listdir(monthly_dir) if f.endswith(".pdf")], reverse=True)
        if monthly_pdfs:
            monthly_last_file = monthly_pdfs[0]
            mp = os.path.join(monthly_dir, monthly_pdfs[0])
            mt = datetime.datetime.fromtimestamp(os.path.getmtime(mp))
            if mt.strftime("%Y-%m") == now.strftime("%Y-%m"):
                monthly_generated_this_month = True
    
    # Sonraki aylık rapor zamanı
    try:
        next_monthly = now.replace(day=monthly_day, hour=monthly_hour, minute=0, second=0, microsecond=0)
        if now >= next_monthly:
            # Sonraki ay
            if now.month == 12:
                next_monthly = next_monthly.replace(year=now.year + 1, month=1)
            else:
                next_monthly = next_monthly.replace(month=now.month + 1)
        monthly_remaining = (next_monthly - now).total_seconds()
        monthly_days = int(monthly_remaining // 86400)
        monthly_h = int((monthly_remaining % 86400) // 3600)
    except ValueError:
        next_monthly = None
        monthly_days = 0
        monthly_h = 0
    
    return {
        "success": True,
        "system_time": now.strftime("%d.%m.%Y %H:%M:%S"),
        "timezone": "Yerel Saat",
        "daily": {
            "target_time": f"{daily_hour:02d}:{daily_minute:02d}",
            "next_run": next_daily.strftime("%d.%m.%Y %H:%M"),
            "remaining": f"{daily_h} saat {daily_m} dakika",
            "generated_today": daily_generated_today,
            "status": "✅ Bugün üretildi" if daily_generated_today else f"⏳ {daily_h}s {daily_m}dk sonra"
        },
        "monthly": {
            "target_day": monthly_day,
            "target_hour": f"{monthly_hour:02d}:00",
            "next_run": next_monthly.strftime("%d.%m.%Y %H:%M") if next_monthly else "—",
            "remaining": f"{monthly_days} gün {monthly_h} saat",
            "generated_this_month": monthly_generated_this_month,
            "last_report": monthly_last_file,
            "status": "✅ Bu ay üretildi" if monthly_generated_this_month else f"⏳ {monthly_days}g {monthly_h}s sonra"
        }
    }

@app.post("/api/daily-report/generate")
async def generate_daily_report():
    """Manuel günlük rapor tetikleme."""
    try:
        from daily_report import DailyReportGenerator
        gen = DailyReportGenerator()
        filepath = gen.generate()
        filename = os.path.basename(filepath)
        return {"success": True, "filename": filename, "message": "Günlük rapor başarıyla oluşturuldu."}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/daily-report/status")
async def daily_report_status():
    """En son günlük raporun durumunu kontrol et."""
    reports_dir = os.path.join(os.path.dirname(__file__), "daily_reports")
    if not os.path.exists(reports_dir):
        return {"success": True, "ready": False, "message": "Henüz rapor oluşturulmamış."}
    
    # En son PDF'i bul
    pdfs = sorted([f for f in os.listdir(reports_dir) if f.endswith('.pdf')], reverse=True)
    if not pdfs:
        return {"success": True, "ready": False, "message": "Henüz rapor oluşturulmamış."}
    
    latest = pdfs[0]
    filepath = os.path.join(reports_dir, latest)
    mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(filepath))
    
    # Bugün oluşturulmuş mu?
    is_today = mod_time.date() == datetime.date.today()
    
    return {
        "success": True,
        "ready": True,
        "is_today": is_today,
        "filename": latest,
        "created_at": mod_time.strftime("%d.%m.%Y %H:%M"),
        "size_kb": round(os.path.getsize(filepath) / 1024, 1)
    }

@app.get("/api/daily-report/download")
async def download_daily_report(filename: str = None):
    """Günlük rapor PDF indirme."""
    reports_dir = os.path.join(os.path.dirname(__file__), "daily_reports")
    
    if filename:
        filepath = os.path.join(reports_dir, filename)
    else:
        # En son raporu indir
        if not os.path.exists(reports_dir):
            raise HTTPException(status_code=404, detail="Rapor dizini bulunamadı")
        pdfs = sorted([f for f in os.listdir(reports_dir) if f.endswith('.pdf')], reverse=True)
        if not pdfs:
            raise HTTPException(status_code=404, detail="Henüz rapor oluşturulmamış")
        filepath = os.path.join(reports_dir, pdfs[0])
    
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Rapor dosyası bulunamadı")
    
    return FileResponse(
        filepath,
        media_type="application/pdf",
        filename=os.path.basename(filepath)
    )

@app.get("/api/daily-report/list")
async def list_daily_reports():
    """Mevcut tüm günlük raporları listele."""
    reports_dir = os.path.join(os.path.dirname(__file__), "daily_reports")
    if not os.path.exists(reports_dir):
        return {"success": True, "reports": []}
    
    pdfs = sorted([f for f in os.listdir(reports_dir) if f.endswith('.pdf')], reverse=True)
    reports = []
    for pdf in pdfs[:30]:  # Son 30 rapor
        fp = os.path.join(reports_dir, pdf)
        mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(fp))
        reports.append({
            "filename": pdf,
            "created_at": mod_time.strftime("%d.%m.%Y %H:%M"),
            "size_kb": round(os.path.getsize(fp) / 1024, 1)
        })
    return {"success": True, "reports": reports}

# ================ AYLIK RAPOR ================

@app.post("/api/monthly-report/generate")
async def generate_monthly_report(year: int = None, month: int = None):
    """Manuel aylık rapor tetikleme."""
    try:
        from monthly_summary_report import MonthlyReportGenerator
        gen = MonthlyReportGenerator()
        filepath = gen.generate(year, month)
        filename = os.path.basename(filepath)
        return {"success": True, "filename": filename, "message": "Aylık rapor başarıyla oluşturuldu."}
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.get("/api/monthly-report/status")
async def monthly_report_status():
    """En son aylık raporun durumunu kontrol et."""
    reports_dir = os.path.join(os.path.dirname(__file__), "monthly_reports_summary")
    if not os.path.exists(reports_dir):
        return {"success": True, "ready": False}
    pdfs = sorted([f for f in os.listdir(reports_dir) if f.endswith('.pdf')], reverse=True)
    if not pdfs:
        return {"success": True, "ready": False}
    latest = pdfs[0]
    filepath = os.path.join(reports_dir, latest)
    mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(filepath))
    return {
        "success": True, "ready": True,
        "filename": latest,
        "created_at": mod_time.strftime("%d.%m.%Y %H:%M"),
        "size_kb": round(os.path.getsize(filepath) / 1024, 1)
    }

@app.get("/api/monthly-report/download")
async def download_monthly_report(filename: str = None):
    """Aylık rapor PDF indirme."""
    reports_dir = os.path.join(os.path.dirname(__file__), "monthly_reports_summary")
    if filename:
        filepath = os.path.join(reports_dir, filename)
    else:
        if not os.path.exists(reports_dir):
            raise HTTPException(status_code=404, detail="Rapor dizini bulunamadı")
        pdfs = sorted([f for f in os.listdir(reports_dir) if f.endswith('.pdf')], reverse=True)
        if not pdfs:
            raise HTTPException(status_code=404, detail="Henüz rapor oluşturulmamış")
        filepath = os.path.join(reports_dir, pdfs[0])
    if not os.path.exists(filepath):
        raise HTTPException(status_code=404, detail="Rapor dosyası bulunamadı")
    return FileResponse(filepath, media_type="application/pdf", filename=os.path.basename(filepath))

@app.get("/api/monthly-report/list")
async def list_monthly_reports():
    """Mevcut tüm aylık raporları listele."""
    reports_dir = os.path.join(os.path.dirname(__file__), "monthly_reports_summary")
    if not os.path.exists(reports_dir):
        return {"success": True, "reports": []}
    pdfs = sorted([f for f in os.listdir(reports_dir) if f.endswith('.pdf')], reverse=True)
    reports = []
    for pdf in pdfs[:24]:
        fp = os.path.join(reports_dir, pdf)
        mod_time = datetime.datetime.fromtimestamp(os.path.getmtime(fp))
        reports.append({
            "filename": pdf,
            "created_at": mod_time.strftime("%d.%m.%Y %H:%M"),
            "size_kb": round(os.path.getsize(fp) / 1024, 1)
        })
    return {"success": True, "reports": reports}

# ================ HEALTH CHECK ================

@app.get("/api/health")
async def health_check():
    """Sağlık kontrol endpoint'i."""
    return {
        "success": True,
        "status": "healthy",
        "service": "HVAC ΔT Öneri Motoru",
        "version": "2.0",
        "timestamp": datetime.datetime.utcnow().isoformat() + "Z"
    }

@app.post("/api/recommend")
async def recommend(
    csv_file: UploadFile = File(...),
    oat: str = Form("20"),
    engine: str = Form("v2"),
    tol_ahu_critical: str = Form("1.0"),
    tol_ahu_normal: str = Form("3.0"),
    chiller_load_percent: str = Form(None),
    chiller_cop: str = Form(None)
):
    """CSV veya Excel dosyasını analiz eder."""
    try:
        # Read file content
        content = await csv_file.read()
        filename = csv_file.filename.lower()
        
        # Determine file type and parse accordingly
        rows = []
        
        if filename.endswith('.xlsx') or filename.endswith('.xls'):
            # Excel file - use pandas
            try:
                df = pd.read_excel(io.BytesIO(content))
                # Convert DataFrame to list of dictionaries
                rows = df.to_dict('records')
                # Convert NaN to None for consistency
                for row in rows:
                    for key, value in row.items():
                        if pd.isna(value):
                            row[key] = None
            except Exception as e:
                logger.error(f"Excel parsing error: {e}")
                raise HTTPException(
                    status_code=400, 
                    detail=f"Excel dosyası okunamadı: {str(e)}"
                )
        else:
            # CSV file - use csv.DictReader
            # Try different encodings
            text = None
            for encoding in ['utf-8-sig', 'utf-8', 'cp1254', 'iso-8859-9']:
                try:
                    text = content.decode(encoding)
                    break
                except UnicodeDecodeError:
                    continue
            
            if text is None:
                text = content.decode('utf-8-sig', errors='ignore')
            
            # Parse CSV with automatic delimiter detection
            try:
                # Detect delimiter (tab, semicolon, or comma)
                sample = text[:1000]  # First 1000 chars
                delimiter = ','
                
                # Check for tab first (Excel paste often uses tab)
                if sample.count('\t') > sample.count(',') and sample.count('\t') > sample.count(';'):
                    delimiter = '\t'
                elif sample.count(';') > sample.count(','):
                    delimiter = ';'
                
                logger.info(f"Detected CSV delimiter: '{delimiter}' (repr: {repr(delimiter)})")
                
                reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
                for row in reader:
                    rows.append(row)
            except Exception as e:
                logger.error(f"CSV parsing error: {e}")
                raise HTTPException(
                    status_code=400,
                    detail=f"CSV dosyası okunamadı: {str(e)}"
                )
        
        if not rows:
            raise HTTPException(status_code=400, detail="Dosya boş veya geçersiz format")
        
        # Normalize column names BEFORE validation
        # This handles Turkish/English variations and different formats
        normalized_rows = []
        for row in rows:
            normalized_row = {}
            for key, value in row.items():
                # Use canonical_key to normalize column names
                canonical = HVACUtils.canonical_key(key)
                normalized_row[canonical] = value
            normalized_rows.append(normalized_row)
        
        # Use normalized rows for validation and analysis
        rows = normalized_rows
        
        # Validate input data
        validation_result = validate_equipment_data(rows)
        if not validation_result["valid"]:
            error_msg = "Veri doğrulama hataları:\n" + "\n".join(validation_result["errors"])
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Log warnings if any
        if validation_result["warnings"]:
            for warning in validation_result["warnings"]:
                logger.warning(f"Validation warning: {warning}")
        
        # Analyze
        result = await analyze_data(
            rows=rows,
            oat=oat,
            engine=engine,
            tol_crit=tol_ahu_critical,
            tol_norm=tol_ahu_normal,
            chiller_load_percent=chiller_load_percent,
            chiller_cop=chiller_cop
        )

        return JSONResponse(result)

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Recommend error: {e}")
        raise HTTPException(status_code=500, detail=f"Analiz hatası: {str(e)}")

@app.post("/api/recommend_json")
async def recommend_json(payload: Dict[str, Any]):
    """JSON payload ile analiz."""
    try:
        rows = payload.get("rows", [])
        
        if not rows:
            raise HTTPException(status_code=400, detail="Veri listesi boş")
        
        # Normalize column names BEFORE validation
        normalized_rows = []
        for row in rows:
            normalized_row = {}
            for key, value in row.items():
                canonical = HVACUtils.canonical_key(key)
                normalized_row[canonical] = value
            normalized_rows.append(normalized_row)
        
        rows = normalized_rows
        
        # Validate input data
        validation_result = validate_equipment_data(rows)
        if not validation_result["valid"]:
            error_msg = "Veri doğrulama hataları:\n" + "\n".join(validation_result["errors"])
            raise HTTPException(status_code=400, detail=error_msg)
        
        # Log warnings if any
        if validation_result["warnings"]:
            for warning in validation_result["warnings"]:
                logger.warning(f"Validation warning: {warning}")
        
        result = await analyze_data(
            rows=rows,
            oat=payload.get("oat", "20"),
            engine=payload.get("engine", "v2"),
            tol_crit=payload.get("tol_ahu_critical", "1.0"),
            tol_norm=payload.get("tol_ahu_normal", "3.0"),
            chiller_load_percent=payload.get("chiller_load_percent"),
            chiller_cop=payload.get("chiller_cop")
        )

        return JSONResponse(result)

    except Exception as e:
        logger.error(f"Recommend JSON error: {e}")
        raise HTTPException(status_code=500, detail=f"Analiz hatası: {str(e)}")

def calculate_chiller_cop(load_percent: float) -> float:
    """2000 KW Chiller Performans Eğrisine göre COP hesapla (doğrusal interpolasyon)."""
    import bisect
    _curve = [
        (10.0, 2.52), (20.0, 4.59), (25.0, 5.37), (30.0, 6.04),
        (40.0, 7.25), (50.0, 7.98), (60.0, 7.52), (70.0, 6.98),
        (75.0, 6.68), (80.0, 6.38), (90.0, 5.72), (100.0, 5.05),
    ]
    loads = [x[0] for x in _curve]
    cops  = [x[1] for x in _curve]
    p = max(0.0, min(100.0, float(load_percent)))
    if p <= loads[0]:
        return cops[0]
    if p >= loads[-1]:
        return cops[-1]
    i = bisect.bisect_right(loads, p)
    x0, y0 = loads[i - 1], cops[i - 1]
    x1, y1 = loads[i],     cops[i]
    return round(y0 + (y1 - y0) * (p - x0) / (x1 - x0), 4)


async def analyze_data(rows: List[Dict[str, Any]],
                      oat: str,
                      engine: str,
                      tol_crit: str,
                      tol_norm: str,
                      chiller_load_percent: str = None,
                      chiller_cop: str = None) -> Dict[str, Any]:
    """Ana analiz fonksiyonu."""
    # Initialize analyzer
    analyzer = HVACAnalyzer()
    utils = HVACUtils()

    # Convert parameters
    oat_float = utils.to_float(oat)
    tol_crit_float = utils.to_float(tol_crit) or CONFIG["TOLERANCE_CRITICAL"]
    tol_norm_float = utils.to_float(tol_norm) or CONFIG["TOLERANCE_NORMAL"]
    chiller_load_float = utils.to_float(chiller_load_percent)
    # COP otomatik hesaplanır; chiller_cop parametresi geriye dönük uyumluluk için tutulur
    if chiller_load_float is not None:
        chiller_cop_float = calculate_chiller_cop(chiller_load_float)
    else:
        chiller_cop_float = utils.to_float(chiller_cop)
    
    # Extract profiles
    profiles = []
    for row in rows:
        try:
            profile = analyzer.extract_equipment_profile(row)
            profiles.append(profile)
        except Exception as e:
            logger.warning(f"Row processing error: {e}")
            continue
    
    # Find plant reference
    plant_supply, plant_return = analyzer.find_plant_reference(profiles)
    
    # Kolektörleri bul (soğutma ve ısıtma)
    cooling_collector = None
    heating_collector = None
    
    logger.debug("=== KOLEKTÖR ARAMA BAŞLADI ===")
    for profile in profiles:
        eq_type = analyzer.classify_equipment_type(profile.type)
        logger.debug(f"Profile: {profile.name}, Type: {profile.type}, Classified: {eq_type}, Mode: {profile.mode}")

        if eq_type == EquipmentType.COLLECTOR:
            mode_upper = profile.mode.upper() if profile.mode else ""
            name_lower = profile.name.lower() if profile.name else ""

            logger.debug(f"  → KOLEKTÖR BULUNDU: {profile.name}, Mode: {mode_upper}")
            logger.debug(f"     Inlet: {profile.temperatures.inlet}, Outlet: {profile.temperatures.outlet}")

            # Mode'a göre veya isme göre algıla
            is_cooling = "COOL" in mode_upper or any(k in name_lower for k in ["soğutma", "sogutma", "cooling", "chilled"])
            is_heating = "HEAT" in mode_upper or any(k in name_lower for k in ["ısıtma", "isitma", "heating", "hot"])

            if is_cooling:
                cooling_collector = profile
                logger.debug(f"  ✅ SOĞUTMA KOLEKTÖRÜ ATANDI: {profile.name}")
            elif is_heating:
                heating_collector = profile
                logger.debug(f"  ✅ ISITMA KOLEKTÖRÜ ATANDI: {profile.name}")

    logger.debug(f"Soğutma Kolektörü: {cooling_collector.name if cooling_collector else 'YOK'}")
    logger.debug(f"Isıtma Kolektörü: {heating_collector.name if heating_collector else 'YOK'}")

    # Kolektör sıcaklıklarını AUTO mode ekipmanlara ata
    logger.debug("=== KOLEKTÖR ATAMA BAŞLADI ===")
    for profile in profiles:
        # Sadece AHU ve FCU için
        eq_type = analyzer.classify_equipment_type(profile.type)
        if eq_type not in [EquipmentType.AHU, EquipmentType.FCU]:
            continue

        logger.debug(f"Ekipman: {profile.name} ({eq_type})")
        logger.debug(f"  Inlet ÖNCE: {profile.temperatures.inlet}, Outlet ÖNCE: {profile.temperatures.outlet}")

        # Inlet/Outlet yoksa ve mode AUTO ise veya vana pozisyonuna göre
        if profile.temperatures.inlet is None or profile.temperatures.outlet is None:
            cooling_valve = profile.valves.cooling if profile.valves.cooling is not None else 0
            heating_valve = profile.valves.heating if profile.valves.heating is not None else 0

            logger.debug(f"  Cool Valve: {cooling_valve}%, Heat Valve: {heating_valve}%")

            # Hangi vana açık?
            if cooling_valve > 0 and cooling_collector:
                # Soğutma vanası açık - soğutma kolektörünü kullan
                logger.debug(f"  → SOĞUTMA VANASI AÇIK, kolektör atanıyor...")
                profile.temperatures.inlet = cooling_collector.temperatures.inlet
                profile.temperatures.outlet = cooling_collector.temperatures.outlet
                logger.debug(f"  ✅ ATANDI: Inlet={profile.temperatures.inlet}, Outlet={profile.temperatures.outlet}")
            elif heating_valve > 0 and heating_collector:
                # Isıtma vanası açık - ısıtma kolektörünü kullan
                logger.debug(f"  → ISITMA VANASI AÇIK, kolektör atanıyor...")
                profile.temperatures.inlet = heating_collector.temperatures.inlet
                profile.temperatures.outlet = heating_collector.temperatures.outlet
                logger.debug(f"  ✅ ATANDI: Inlet={profile.temperatures.inlet}, Outlet={profile.temperatures.outlet}")
            elif cooling_valve == 0 and heating_valve == 0:
                # Her iki vana kapalı - mode'a göre veya varsayılan
                logger.debug(f"  → HER İKİ VANA KAPALI, mode'a göre atanıyor...")
                mode_upper = profile.mode.upper() if profile.mode else ""
                if "COOL" in mode_upper and cooling_collector:
                    profile.temperatures.inlet = cooling_collector.temperatures.inlet
                    profile.temperatures.outlet = cooling_collector.temperatures.outlet
                    logger.debug(f"  ✅ SOĞUTMA MOD: Inlet={profile.temperatures.inlet}, Outlet={profile.temperatures.outlet}")
                elif "HEAT" in mode_upper and heating_collector:
                    profile.temperatures.inlet = heating_collector.temperatures.inlet
                    profile.temperatures.outlet = heating_collector.temperatures.outlet
                    logger.debug(f"  ✅ ISITMA MOD: Inlet={profile.temperatures.inlet}, Outlet={profile.temperatures.outlet}")
        else:
            logger.debug(f"  ℹ️ Inlet/Outlet zaten var, atlanıyor")

    logger.debug("=== KOLEKTÖR ATAMA BİTTİ ===")
    
    # Analyze each equipment
    results = []
    for profile in profiles:
        try:
            analysis = analyzer.analyze_equipment(
                profile=profile,
                plant_supply=plant_supply,
                plant_return=plant_return,
                oat=oat_float,
                tol_crit=tol_crit_float,
                tol_norm=tol_norm_float
            )
            
            # Create result row
            result_row = {
                "Location": profile.location,
                "Asset": f"{profile.type}:{profile.name}",
                "Type": profile.type,
                "Name": profile.name,
                "Mode": profile.mode,
                "Priority": profile.priority,
                "Supply (°C)": profile.temperatures.supply,
                "Return (°C)": profile.temperatures.return_,
                "Inlet (°C)": profile.temperatures.inlet,
                "Outlet (°C)": profile.temperatures.outlet,
                "Room (°C)": profile.temperatures.room,
                "Set (°C)": profile.temperatures.setpoint,
                "SAT (°C)": profile.temperatures.sat,
                "Cool Valve (%)": profile.valves.cooling,
                "Heat Valve (%)": profile.valves.heating,
                "Humidity (%)": profile.humidity,
                "Plant Supply (°C)": plant_supply,
                "Plant Return (°C)": plant_return,
                "OAT (°C)": oat_float,
            }
            
            # Add analysis results
            result_row.update(analysis.to_dict())
            
            # Frontend tablo uyumluluğu için "ΔT (°C)" key'i ekle
            if "Su ΔT (°C)" in result_row:
                result_row["ΔT (°C)"] = result_row["Su ΔT (°C)"]
            
            # Frontend tablo uyumluluğu için "Recommended SAT (°C)" key'i ekle
            for key in result_row.keys():
                if "recommended" in key.lower() and "sat" in key.lower():
                    result_row["Recommended SAT (°C)"] = result_row[key]
                    break
            
            # Saha tecrübesi kural kontrolü
            field_issues = check_field_experience_rules(result_row)
            if field_issues:
                result_row["Field Experience Issues"] = field_issues
                result_row["Field Experience Count"] = len(field_issues)
            else:
                result_row["Field Experience Issues"] = []
                result_row["Field Experience Count"] = 0
            
            results.append(result_row)
            
        except Exception as e:
            logger.error(f"Analysis error for {profile.name}: {e}")
            results.append({
                "Location": profile.location,
                "Asset": f"{profile.type}:{profile.name}",
                "Type": profile.type,
                "Name": profile.name,
                "Action": "Hata",
                "Reason": f"Analiz hatası: {str(e)}",
                "Status": "MISSING_DATA",
                "Severity": "CRITICAL",
                "Score": 0
            })
    
    # ========== KURAL 8: SEASONAL_CHILLER_TRANSITION ==========
    # Dış hava <10°C iken Chiller yüksek kapasitede zorlanıyorsa uyar
    if (oat_float is not None and oat_float < 10 and
            chiller_load_float is not None and chiller_load_float > 80):
        cop_str = f"{chiller_cop_float:.2f}" if chiller_cop_float is not None else "bilinmiyor"
        chiller_warning_row = {
            "Location": "SİSTEM",
            "Asset": "SISTEM:Chiller-Yuk-Analizi",
            "Type": "CHILLER",
            "Name": "Chiller Yük/COP Analizi",
            "Mode": "COOLING",
            "Priority": "Critical",
            "OAT (°C)": oat_float,
            "Chiller Yük (%)": chiller_load_float,
            "Chiller COP": chiller_cop_float,
            "Status": "SEASONAL_CHILLER_TRANSITION",
            "Severity": "WARNING",
            "Score": 8.0,
            "Rule": "SEASONAL_CHILLER_TRANSITION",
            "Action": "Free-Cooling Potansiyelini Artırın",
            "Reason": (
                f"Dış hava ({oat_float}°C) serbest soğutma için çok uygun ancak "
                f"Chiller {chiller_load_float}% kapasite ve {cop_str} COP ile zorlanarak çalışıyor! "
                f"Free-Cooling potansiyelini artırın. Eğer sistem hala bu yüksek yükte çalışmaya "
                f"devam ederse, 2. Chiller'i devreye almak için ana kollektör setini düşürmeniz gerekebilir."
            ),
            "Field Experience Issues": [],
            "Field Experience Count": 0,
            "Maintenance Notes": "",
        }
        # Kural bilgilerini INSTRUCTION_GUIDE'dan ekle
        rule_info = INSTRUCTION_GUIDE.get("SEASONAL_CHILLER_TRANSITION", {})
        chiller_warning_row["Band"] = rule_info.get("title", "Mevsimsel Chiller Geçiş Uyarısı")
        results.append(chiller_warning_row)
        logger.info(
            f"KURAL 8 TETİKLENDİ: OAT={oat_float}°C, "
            f"Chiller Yük={chiller_load_float}%, COP={cop_str}"
        )

    # Sort by score (descending)
    results.sort(key=lambda x: float(x.get("Score", 0)), reverse=True)

    # Calculate KPIs
    critical_count = sum(1 for r in results if r.get("Severity") == "CRITICAL")
    warning_count = sum(1 for r in results if r.get("Severity") == "WARNING")
    optimal_count = sum(1 for r in results if r.get("Severity") == "OPTIMAL")
    
    # Generate output columns
    output_columns = [
        "Asset", "Type", "Name", "Status", "Severity", "Su ΔT (°C)", "Hava ΔT (°C)", "Target ΔT (°C)", 
        "ΔT Dev (°C)", "Band", "SAT Status", "Recommended SAT (°C)", "Score", 
        "Action", "Reason", "Rule", "DT Source",
        "Approach_Supply (°C)", "Approach_Return (°C)",
        "Plant Supply (°C)", "Plant Return (°C)", "OAT (°C)"
    ]
    
    # Save to CSV
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    unique_id = uuid.uuid4().hex[:8]
    filename = f"hvac_analysis_{timestamp}_{unique_id}.csv"
    filepath = os.path.join(OUTPUT_DIR, filename)
    
    with open(filepath, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=output_columns)
        writer.writeheader()
        for row in results:
            writer.writerow({col: row.get(col, "") for col in output_columns})

    # 7 günden eski output dosyalarını temizle
    try:
        cutoff = datetime.datetime.now() - datetime.timedelta(days=7)
        for old_file in os.listdir(OUTPUT_DIR):
            old_path = os.path.join(OUTPUT_DIR, old_file)
            if os.path.isfile(old_path):
                file_mtime = datetime.datetime.fromtimestamp(os.path.getmtime(old_path))
                if file_mtime < cutoff:
                    os.remove(old_path)
                    logger.debug(f"Eski output dosyası silindi: {old_file}")
    except Exception as e:
        logger.warning(f"Output temizleme hatası: {e}")

    # Calculate average score
    avg_score = sum(float(r.get("Score", 0)) for r in results) / len(results) if results else 0.0
    
    # ========== OTOMATİK HVAC HİSTORY KAYDETME ==========
    # Analiz sonuçlarını aylık rapor için otomatik kaydet
    try:
        from monthly_report.hvac_history import HVACHistoryManager
        from datetime import date as dt_date
        
        hvac_history = HVACHistoryManager()
        analysis_date = dt_date.today()  # Bugünün tarihi
        
        # CSV dosya adından tarih çıkarmaya çalış (opsiyonel)
        # Örnek: "2026-01-17_santral_analizi.csv" -> 2026-01-17
        if filename:
            import re
            date_match = re.search(r'(\d{4}-\d{2}-\d{2})', filename)
            if date_match:
                try:
                    from datetime import datetime as dt
                    analysis_date = dt.strptime(date_match.group(1), "%Y-%m-%d").date()
                except:
                    pass
        
        # Sonuçları kaydet
        hvac_history.save_analysis_summary(
            analysis_date=analysis_date,
            results=results,
            csv_filename=filename
        )
        logger.info(f"HVAC analiz sonuçları otomatik kaydedildi: {analysis_date}")
        
    except ImportError:
        logger.warning("monthly_report modülü bulunamadı, HVAC history kaydedilmedi")
    except Exception as e:
        logger.warning(f"HVAC history kaydetme hatası: {e}")
    
    return {
        "success": True,
        "recs_table": {
            "cols": output_columns,
            "rows": results,
            "meta": {
                "engine": engine,
                "oat": oat_float,
                "plant_supply": plant_supply,
                "plant_return": plant_return,
                "total_count": len(results),
                "critical_count": critical_count,
                "warning_count": warning_count,
                "optimal_count": optimal_count
            }
        },
        "kpi": {
            "total": len(results),
            "crit": critical_count,
            "warn": warning_count,
            "optimal": optimal_count,
            "avg_score": round(avg_score, 1)
        },
        "outputs": {
            "csv_bundle": f"/static/outputs/{filename}"
        }
    }

# Uygulamayı başlat
if __name__ == "__main__":
    import uvicorn
    
    print("=" * 60)
    print("HVAC Delta-T Oneri Motoru - Engine v2")
    print(f"Baslatiliyor...")
    print(f"API URL: http://localhost:8005")
    print(f"API Docs: http://localhost:8005/docs")
    print("=" * 60)
    
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8005,
        log_level="info"
    )