# training_data.py
# ML için veri toplama modülü - Faz 2 hazırlığı

from __future__ import annotations
import os
import json
from datetime import datetime
from typing import Dict, List, Optional


class TrainingDataCollector:
    """
    ML eğitimi için veri toplayan modül.
    Kural motoru çalışırken arka planda veri toplar.
    Faz 2'de ML motoru bu verileri kullanacak.
    """
    
    try:
        from location_manager import get_manager as _get_loc_mgr
        DATA_FILE = _get_loc_mgr().get_data_path("ml_training_data.json")
    except Exception:
        DATA_FILE = "ml_training_data.json"
    
    def __init__(self, data_file: str = None):
        self.data_file = data_file or self.DATA_FILE
        self.data = self._load_data()
    
    def _load_data(self) -> List[Dict]:
        """Mevcut eğitim verilerini yükle"""
        if os.path.exists(self.data_file):
            try:
                with open(self.data_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception as e:
                import logging
                logging.warning(f"Training data yükleme hatası ({self.data_file}): {e}")
                return []
        return []
    
    def _save_data(self):
        """Eğitim verilerini kaydet"""
        try:
            with open(self.data_file, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            print(f"Training data kaydetme hatasi: {e}")
    
    def save_recommendation_context(self, 
                                     recommendation: Dict,
                                     energy_summary: Dict = None,
                                     hvac_summary: Dict = None,
                                     yoy_data: Dict = None):
        """
        Öneri + bağlam verilerini kaydet.
        
        Args:
            recommendation: Üretilen öneri
            energy_summary: Enerji özet verileri
            hvac_summary: HVAC özet verileri
            yoy_data: YoY karşılaştırma verileri
        """
        record = {
            "id": f"REC_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.data)}",
            "timestamp": datetime.now().isoformat(),
            "recommendation": {
                "rule_id": recommendation.get("rule_id"),
                "name": recommendation.get("name"),
                "severity": recommendation.get("severity"),
                "category": recommendation.get("category"),
                "savings_potential": recommendation.get("savings_potential"),
            },
            "context": {
                "energy": self._extract_key_metrics(energy_summary) if energy_summary else {},
                "hvac": self._extract_key_metrics(hvac_summary) if hvac_summary else {},
            },
            "yoy_changes": self._extract_yoy_changes(yoy_data) if yoy_data else {},
            "feedback": None,  # Kullanıcı sonradan dolduracak
            "outcome": None,   # Gerçek sonuç (uygulandı mı, tasarruf sağlandı mı)
        }
        
        self.data.append(record)
        self._save_data()
        
        return record["id"]
    
    def _extract_key_metrics(self, summary: Dict) -> Dict:
        """Özet verilerden önemli metrikleri çıkar"""
        if not summary:
            return {}
        
        key_fields = [
            "total_grid_consumption",
            "total_cooling_consumption",
            "total_gas",
            "avg_chiller_set_temp",
            "avg_outdoor_temp",
            "hvac_avg_delta_t",
            "hvac_total_critical",
            "hvac_avg_cooling_pct",
            "hvac_avg_heating_pct",
        ]
        
        return {k: summary.get(k) for k in key_fields if summary.get(k) is not None}
    
    def _extract_yoy_changes(self, yoy_data: Dict) -> Dict:
        """YoY değişikliklerini çıkar"""
        if not yoy_data:
            return {}
        
        comparisons = yoy_data.get("comparisons", {})
        changes = {}
        
        for metric, data in comparisons.items():
            if data.get("change_percent") is not None:
                changes[metric] = {
                    "current": data.get("current"),
                    "previous": data.get("previous"),
                    "change_pct": data.get("change_percent"),
                    "trend": data.get("trend"),
                    "status": data.get("status"),
                }
        
        return changes
    
    def update_feedback(self, record_id: str, feedback: str, notes: str = None):
        """
        Kullanıcı feedback'i güncelle.
        
        Args:
            record_id: Kayıt ID'si
            feedback: "applied", "not_applied", "partially_applied", "pending"
            notes: Ek notlar
        """
        for record in self.data:
            if record["id"] == record_id:
                record["feedback"] = {
                    "status": feedback,
                    "notes": notes,
                    "updated_at": datetime.now().isoformat()
                }
                self._save_data()
                return True
        
        return False
    
    def update_outcome(self, record_id: str, 
                       actual_savings: float = None,
                       success: bool = None,
                       notes: str = None):
        """
        Gerçek sonucu güncelle (ML eğitimi için kritik).
        
        Args:
            record_id: Kayıt ID'si
            actual_savings: Gerçek tasarruf yüzdesi
            success: Başarılı mı?
            notes: Ek notlar
        """
        for record in self.data:
            if record["id"] == record_id:
                record["outcome"] = {
                    "actual_savings": actual_savings,
                    "success": success,
                    "notes": notes,
                    "updated_at": datetime.now().isoformat()
                }
                self._save_data()
                return True
        
        return False
    
    def get_pending_feedback(self) -> List[Dict]:
        """Feedback beklenen kayıtlar"""
        return [r for r in self.data if r.get("feedback") is None]
    
    def get_statistics(self) -> Dict:
        """Eğitim verisi istatistikleri"""
        total = len(self.data)
        with_feedback = sum(1 for r in self.data if r.get("feedback"))
        with_outcome = sum(1 for r in self.data if r.get("outcome"))
        
        # Kural bazlı dağılım
        rule_counts = {}
        for r in self.data:
            rule_id = r.get("recommendation", {}).get("rule_id", "UNKNOWN")
            rule_counts[rule_id] = rule_counts.get(rule_id, 0) + 1
        
        return {
            "total_records": total,
            "with_feedback": with_feedback,
            "with_outcome": with_outcome,
            "feedback_rate": (with_feedback / total * 100) if total > 0 else 0,
            "outcome_rate": (with_outcome / total * 100) if total > 0 else 0,
            "rule_distribution": rule_counts,
            "ready_for_ml": total >= 100,  # En az 100 kayıt
        }
