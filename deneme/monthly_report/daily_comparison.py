# daily_comparison.py
# Günlük değer karşılaştırma ve uyarı sistemi
# Değer girildikten sonra dünkü ve geçen yıl aynı gün ile karşılaştırma yapar

from __future__ import annotations
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
import os
import json


# Eşik değerleri
THRESHOLD_WARNING = 5.0  # %5 artışta uyarı
THRESHOLD_CRITICAL = 15.0  # %15 artışta kritik uyarı


class DailyComparisonEngine:
    """
    Günlük değer karşılaştırma motoru.
    
    Özellikler:
    - Dünkü değerle karşılaştırma
    - Geçen yıl aynı günle karşılaştırma  
    - %5+ artışta uyarı üretme
    """
    
    # Karşılaştırılacak alanlar ve Türkçe isimleri
    COMPARISON_FIELDS = {
        "total_grid_consumption": "Şebeke Elektrik Tüketimi",
        "total_cooling_consumption": "Soğutma (Chiller) Tüketimi",
        "total_heating_consumption": "Isıtma Tüketimi",
        "total_gas": "Doğalgaz Tüketimi",
        "total_mcc_consumption": "MCC Tüketimi",
        "total_hospital_consumption": "Toplam Hastane Tüketimi",
    }
    
    def __init__(self, history_file: str = "daily_energy_history.json"):
        self.history_file = history_file
        self.history = self._load_history()
    
    def _load_history(self) -> Dict:
        """Tarihsel veriyi yükle"""
        if os.path.exists(self.history_file):
            try:
                with open(self.history_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                print(f"History yükleme hatası: {e}")
                return {}
        return {}
    
    def _save_history(self):
        """Tarihsel veriyi kaydet"""
        try:
            with open(self.history_file, "w", encoding="utf-8") as f:
                json.dump(self.history, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            print(f"History kaydetme hatası: {e}")
    
    def save_daily_entry(self, entry_date: date, field: str, value: float):
        """Günlük değeri kaydet"""
        date_key = entry_date.strftime("%Y-%m-%d")
        
        if date_key not in self.history:
            self.history[date_key] = {}
        
        self.history[date_key][field] = value
        self.history[date_key]["_last_updated"] = datetime.now().isoformat()
        
        self._save_history()
    
    def save_daily_data(self, entry_date: date, data: Dict[str, float]):
        """Birden fazla değeri tek seferde kaydet"""
        date_key = entry_date.strftime("%Y-%m-%d")
        
        if date_key not in self.history:
            self.history[date_key] = {}
        
        for field, value in data.items():
            if value is not None:
                self.history[date_key][field] = value
        
        self.history[date_key]["_last_updated"] = datetime.now().isoformat()
        self._save_history()
    
    def get_previous_day(self, entry_date: date, field: str) -> Optional[float]:
        """Bir önceki günün değerini getir"""
        prev_date = entry_date - timedelta(days=1)
        date_key = prev_date.strftime("%Y-%m-%d")
        
        if date_key in self.history:
            return self.history[date_key].get(field)
        return None
    
    def get_same_day_last_year(self, entry_date: date, field: str) -> Optional[float]:
        """Geçen yıl aynı günün değerini getir"""
        # Geçen yıl aynı gün (366 gün öncesi için 365, artık yıl için 366)
        try:
            last_year_date = entry_date.replace(year=entry_date.year - 1)
        except ValueError:
            # 29 Şubat durumu için
            last_year_date = entry_date - timedelta(days=365)
        
        date_key = last_year_date.strftime("%Y-%m-%d")
        
        if date_key in self.history:
            return self.history[date_key].get(field)
        return None
    
    def calculate_change_percent(self, current: float, previous: float) -> float:
        """Yüzdelik değişimi hesapla"""
        if previous is None or previous == 0:
            return 0.0
        return ((current - previous) / previous) * 100
    
    def compare_and_warn(self, entry_date: date, data: Dict[str, float]) -> List[Dict]:
        """
        Girilen değerleri karşılaştır ve uyarı üret.
        
        Returns:
            List[Dict]: Uyarı listesi
            Her uyarı: {
                "field": alan adı,
                "field_tr": Türkçe alan adı,
                "current": güncel değer,
                "previous_day": dünkü değer,
                "last_year": geçen yıl değeri,
                "change_vs_yesterday": dünkü değere göre değişim %,
                "change_vs_last_year": geçen yıla göre değişim %,
                "severity": "WARNING" veya "CRITICAL",
                "message": Türkçe uyarı mesajı
            }
        """
        warnings = []
        
        for field, current_value in data.items():
            if current_value is None or field.startswith("_"):
                continue
            
            if field not in self.COMPARISON_FIELDS:
                continue
            
            field_tr = self.COMPARISON_FIELDS[field]
            
            # Dünkü değeri al
            prev_day_value = self.get_previous_day(entry_date, field)
            # Geçen yıl aynı günü al
            last_year_value = self.get_same_day_last_year(entry_date, field)
            
            # Değişimleri hesapla
            change_vs_yesterday = None
            change_vs_last_year = None
            
            if prev_day_value is not None:
                change_vs_yesterday = self.calculate_change_percent(current_value, prev_day_value)
            
            if last_year_value is not None:
                change_vs_last_year = self.calculate_change_percent(current_value, last_year_value)
            
            # Uyarı üret
            warning = None
            severity = None
            message = None
            
            # Dünkü değere göre kontrol
            if change_vs_yesterday is not None and change_vs_yesterday >= THRESHOLD_WARNING:
                if change_vs_yesterday >= THRESHOLD_CRITICAL:
                    severity = "CRITICAL"
                    message = (
                        f"⚠️ KRİTİK: {field_tr} dünkü değere göre %{change_vs_yesterday:.1f} artış gösterdi!\n"
                        f"Dün: {prev_day_value:,.0f} → Bugün: {current_value:,.0f}\n"
                        f"Olası nedenler:\n"
                        f"  • Değer yanlış girilmiş olabilir\n"
                        f"  • Sahada unutulmuş/açık kalan cihaz olabilir\n"
                        f"  • Anormal operasyon durumu olabilir"
                    )
                else:
                    severity = "WARNING"
                    message = (
                        f"⚡ UYARI: {field_tr} dünkü değere göre %{change_vs_yesterday:.1f} artış gösterdi.\n"
                        f"Dün: {prev_day_value:,.0f} → Bugün: {current_value:,.0f}\n"
                        f"Lütfen değeri kontrol edin."
                    )
                
                warning = {
                    "field": field,
                    "field_tr": field_tr,
                    "current": current_value,
                    "previous_day": prev_day_value,
                    "last_year": last_year_value,
                    "change_vs_yesterday": change_vs_yesterday,
                    "change_vs_last_year": change_vs_last_year,
                    "severity": severity,
                    "message": message,
                    "comparison_type": "yesterday"
                }
                warnings.append(warning)
            
            # Geçen yıla göre kontrol (dünkü değer yoksa)
            elif change_vs_last_year is not None and change_vs_last_year >= THRESHOLD_WARNING:
                if change_vs_last_year >= THRESHOLD_CRITICAL:
                    severity = "CRITICAL"
                    message = (
                        f"📊 KRİTİK: {field_tr} geçen yıl aynı güne göre %{change_vs_last_year:.1f} artış gösterdi!\n"
                        f"Geçen yıl: {last_year_value:,.0f} → Bu yıl: {current_value:,.0f}\n"
                        f"Dikkatli incelenmeli."
                    )
                else:
                    severity = "WARNING"
                    message = (
                        f"📈 UYARI: {field_tr} geçen yıl aynı güne göre %{change_vs_last_year:.1f} artış gösterdi.\n"
                        f"Geçen yıl: {last_year_value:,.0f} → Bu yıl: {current_value:,.0f}"
                    )
                
                warning = {
                    "field": field,
                    "field_tr": field_tr,
                    "current": current_value,
                    "previous_day": prev_day_value,
                    "last_year": last_year_value,
                    "change_vs_yesterday": change_vs_yesterday,
                    "change_vs_last_year": change_vs_last_year,
                    "severity": severity,
                    "message": message,
                    "comparison_type": "last_year"
                }
                warnings.append(warning)
        
        # Severity'ye göre sırala (CRITICAL önce)
        warnings.sort(key=lambda x: 0 if x["severity"] == "CRITICAL" else 1)
        
        return warnings
    
    def get_comparison_summary(self, entry_date: date, data: Dict[str, float]) -> Dict:
        """
        Tüm karşılaştırmaların özetini döndür.
        """
        summary = {
            "date": entry_date.strftime("%Y-%m-%d"),
            "comparisons": [],
            "warnings_count": 0,
            "critical_count": 0
        }
        
        for field, current_value in data.items():
            if current_value is None or field.startswith("_"):
                continue
            
            if field not in self.COMPARISON_FIELDS:
                continue
            
            field_tr = self.COMPARISON_FIELDS[field]
            prev_day = self.get_previous_day(entry_date, field)
            last_year = self.get_same_day_last_year(entry_date, field)
            
            comparison = {
                "field": field,
                "field_tr": field_tr,
                "current": current_value,
                "previous_day": prev_day,
                "last_year": last_year,
                "change_vs_yesterday": self.calculate_change_percent(current_value, prev_day) if prev_day else None,
                "change_vs_last_year": self.calculate_change_percent(current_value, last_year) if last_year else None
            }
            summary["comparisons"].append(comparison)
        
        # Uyarıları say
        warnings = self.compare_and_warn(entry_date, data)
        summary["warnings_count"] = len(warnings)
        summary["critical_count"] = sum(1 for w in warnings if w["severity"] == "CRITICAL")
        summary["warnings"] = warnings
        
        return summary


# Kullanım örneği için fonksiyon
def check_daily_values(entry_date: date, energy_data: Dict[str, float], 
                       history_file: str = "daily_energy_history.json") -> Dict:
    """
    Günlük değerleri karşılaştır ve uyarı üret.
    
    Args:
        entry_date: Değerlerin girildiği tarih
        energy_data: Enerji değerleri dict'i
        history_file: Tarihsel veri dosya yolu
    
    Returns:
        Dict: Karşılaştırma özeti ve uyarılar
    """
    engine = DailyComparisonEngine(history_file)
    
    # Önce karşılaştırma yap
    summary = engine.get_comparison_summary(entry_date, energy_data)
    
    # Sonra değerleri kaydet (bir sonraki karşılaştırma için)
    engine.save_daily_data(entry_date, energy_data)
    
    return summary
