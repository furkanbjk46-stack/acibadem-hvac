# yoy_analyzer.py
# Geçen yıl aynı aya göre karşılaştırma modülü

from __future__ import annotations
from datetime import date
from typing import Dict, List, Optional
from .data_merger import UnifiedDataMerger


class YearOverYearAnalyzer:
    """
    Geçen yıl aynı aya göre karşılaştırma yapan sınıf.
    YoY (Year over Year) analizi sağlar.
    """
    
    # Karşılaştırılacak metrikler
    COMPARISON_METRICS = [
        # Enerji metrikleri
        ("total_grid_consumption", "Şebeke Tüketimi", "kWh", "lower_better"),
        ("total_cooling_consumption", "Soğutma Tüketimi", "kWh", "lower_better"),
        ("total_hospital_consumption", "Toplam Hastane", "kWh", "lower_better"),
        ("total_gas", "Toplam Doğalgaz", "m³", "lower_better"),
        ("total_mcc_consumption", "MCC Tüketimi", "kWh", "lower_better"),
        
        # Yeni: VRF ve Su metrikleri
        ("total_vrf_consumption", "VRF/Split Tüketimi", "kWh", "lower_better"),
        ("total_water_consumption", "Su Tüketimi", "m³", "lower_better"),
        ("total_chiller_consumption", "Chiller Tüketimi", "kWh", "lower_better"),
        
        # Ayar metrikleri
        ("avg_chiller_set_temp", "Ortalama Chiller Set", "°C", "higher_better"),
        ("avg_outdoor_temp", "Ortalama Dış Hava", "°C", "neutral"),
        
        # Yeni: Enerji Verimlilik İndeksi
        ("efficiency_index", "Enerji Verimlilik İndeksi", "kWh/°C", "lower_better"),
        
        # HVAC metrikleri
        ("total_critical_issues", "Kritik Sorun Sayısı", "adet", "lower_better"),
        ("avg_delta_t", "Ortalama Su ΔT", "°C", "target_range"),
    ]
    
    def __init__(self, data_merger: UnifiedDataMerger = None):
        self.merger = data_merger or UnifiedDataMerger()
    
    def compare_month(self, year: int, month: int) -> Dict:
        """
        Belirtilen ay ile geçen yıl aynı ayı karşılaştırır.
        
        Returns:
            Dict: Karşılaştırma sonuçları
        """
        # Bu yılın verileri
        current_data = self.merger.merge_monthly_data(year, month)
        current_summary = current_data.get("summary", {})
        
        # Geçen yılın verileri
        last_year = year - 1
        previous_data = self.merger.merge_monthly_data(last_year, month)
        previous_summary = previous_data.get("summary", {})
        
        # Karşılaştırma
        comparisons = {}
        for metric_key, label, unit, direction in self.COMPARISON_METRICS:
            cur_val = current_summary.get(metric_key)
            prev_val = previous_summary.get(metric_key)
            
            comparison = self._compare_values(cur_val, prev_val, direction)
            comparison["label"] = label
            comparison["unit"] = unit
            comparison["direction"] = direction
            
            comparisons[metric_key] = comparison
        
        return {
            "current_year": year,
            "current_month": month,
            "previous_year": last_year,
            "current_days_with_data": current_data.get("days_with_data", 0),
            "previous_days_with_data": previous_data.get("days_with_data", 0),
            "comparisons": comparisons,
            "current_summary": current_summary,
            "previous_summary": previous_summary,
        }
    
    def _compare_values(self, current: Optional[float], previous: Optional[float], 
                        direction: str) -> Dict:
        """İki değeri karşılaştır ve trend belirle"""
        result = {
            "current": current,
            "previous": previous,
            "change_absolute": None,
            "change_percent": None,
            "trend": "→",  # Nötr
            "status": "neutral",
        }
        
        if current is None or previous is None:
            result["status"] = "no_data"
            return result
        
        if previous == 0:
            result["change_percent"] = None
        else:
            result["change_percent"] = ((current - previous) / previous) * 100
        
        result["change_absolute"] = current - previous
        
        # Trend belirleme
        if current > previous:
            result["trend"] = "↑"
            if direction == "lower_better":
                result["status"] = "negative"  # Artış kötü
            elif direction == "higher_better":
                result["status"] = "positive"  # Artış iyi
            else:
                result["status"] = "neutral"
        elif current < previous:
            result["trend"] = "↓"
            if direction == "lower_better":
                result["status"] = "positive"  # Azalış iyi
            elif direction == "higher_better":
                result["status"] = "negative"  # Azalış kötü
            else:
                result["status"] = "neutral"
        
        return result
    
    def get_significant_changes(self, comparison_result: Dict, 
                                 threshold_percent: float = 10.0) -> List[Dict]:
        """
        Önemli değişiklikleri (eşik üstü) listele.
        
        Args:
            comparison_result: compare_month() sonucu
            threshold_percent: Değişiklik eşiği (%)
        """
        significant = []
        
        for metric_key, data in comparison_result.get("comparisons", {}).items():
            change_pct = data.get("change_percent")
            if change_pct is not None and abs(change_pct) >= threshold_percent:
                significant.append({
                    "metric": metric_key,
                    "label": data["label"],
                    "unit": data["unit"],
                    "current": data["current"],
                    "previous": data["previous"],
                    "change_percent": change_pct,
                    "trend": data["trend"],
                    "status": data["status"],
                    "direction": data["direction"],
                })
        
        # Değişiklik büyüklüğüne göre sırala
        significant.sort(key=lambda x: abs(x["change_percent"]), reverse=True)
        
        return significant
    
    def format_comparison_text(self, comparison: Dict) -> str:
        """Karşılaştırmayı okunabilir metin olarak formatla"""
        label = comparison["label"]
        current = comparison["current"]
        previous = comparison["previous"]
        unit = comparison["unit"]
        change_pct = comparison.get("change_percent", 0)
        trend = comparison["trend"]
        
        if change_pct is None:
            return f"{label}: {current:,.1f} {unit} (geçen yıl veri yok)"
        
        return f"{label}: {current:,.1f} {unit} {trend} %{change_pct:+.1f} (geçen yıl: {previous:,.1f} {unit})"
