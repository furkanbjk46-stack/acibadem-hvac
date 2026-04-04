"""
Temperature Cascade Rules
Sıcaklık kademesi kontrol kuralları - 3 yıllık saha tecrübesi
"""

from typing import Dict, Any, Optional
from .location_config import get_location_config


class TemperatureCascadeRules:
    """
    Sıcaklık kademesi kuralları
    Uçtan merkeze: FCU → Transfer → Chiller
    """
    
    def __init__(self):
        self.config = get_location_config()
    
    def validate_fcu_set(self, set_temp: Optional[float]) -> Dict[str, Any]:
        """FCU setpoint kontrolü (21-26°C band)"""
        if set_temp is None:
            return {"valid": True}
        
        min_set = self.config.get("rules.fcu.set_min", 21.0)
        max_set = self.config.get("rules.fcu.set_max", 26.0)
        
        if set_temp < min_set:
            return {
                "valid": False,
                "issue": "FCU Set Çok Düşük",
                "current": set_temp,
                "recommended": min_set,
                "reason": "Oda fazla soğur, enerji israfı",
                "saving_potential": "Yüksek"
            }
        elif set_temp > max_set:
            return {
                "valid": False,
                "issue": "FCU Set Çok Yüksek",
                "current": set_temp,
                "recommended": max_set,
                "reason": "Oda fazla ısınır, enerji israfı",
                "saving_potential": "Yüksek"
            }
        
        return {"valid": True}
    
    def validate_ahu_sat(self, sat: Optional[float], mode: str) -> Dict[str, Any]:
        """Santral üfleme sıcaklığı kontrolü"""
        if sat is None:
            return {"valid": True}
        
        is_heating = "HEAT" in mode.upper() if mode else False
        
        if is_heating:
            target = self.config.get("rules.ahu.sat_heating", 28.0)
        else:
            target = self.config.get("rules.ahu.sat_cooling", 18.0)
        
        tolerance = self.config.get("tolerances.temperature", 2.0)
        
        if abs(sat - target) > tolerance:
            return {
                "valid": False,
                "issue": f"Santral Üfleme {'Isıtma' if is_heating else 'Soğutma'} İçin Optimal Değil",
                "current": sat,
                "recommended": target,
                "reason": "FCU'lar fazla enerji tüketir",
                "saving_potential": "Orta"
            }
        
        return {"valid": True}
    
    def validate_transfer_temp(self, transfer_temp: Optional[float], 
                               equipment_type: str, 
                               mode: str) -> Dict[str, Any]:
        """Transfer hattı sıcaklık kontrolü"""
        if transfer_temp is None:
            return {"valid": True}
        
        is_heating = "HEAT" in mode.upper() if mode else False
        is_fcu = "FCU" in equipment_type.upper()
        
        if is_heating:
            if is_fcu:
                target = self.config.get("rules.fcu.transfer_heating", 50.0)
            else:
                target = self.config.get("rules.ahu.transfer_heating", 60.0)
        else:
            if is_fcu:
                target = self.config.get("rules.fcu.transfer_cooling", 15.0)
            else:
                target = self.config.get("rules.ahu.transfer_cooling", 13.0)
        
        tolerance = self.config.get("tolerances.temperature", 2.0)
        
        if abs(transfer_temp - target) > tolerance:
            return {
                "valid": False,
                "issue": f"Transfer Sıcaklığı {equipment_type} İçin Optimal Değil",
                "current": transfer_temp,
                "recommended": target,
                "reason": "Su tarafında tasarruf fırsatı",
                "saving_potential": "Yüksek"
            }
        
        return {"valid": True}


def check_field_experience_rules(equipment_data: Dict[str, Any]) -> list:
    """
    Basit kural kontrolü - main_portal.py'den çağrılacak
    """
    rules = TemperatureCascadeRules()
    issues = []
    
    eq_type = equipment_data.get("Type", "")
    # P1-3: Effective_Mode varsa onu kullan (AUTO modda gerçek yönü bilir)
    mode = equipment_data.get("Effective_Mode") or equipment_data.get("Mode", "COOLING")

    # P3 Fix: AUTO modda ısıtma vanası veya kış sıcaklığına göre effective_mode belirle
    if mode and mode.strip().upper() == "AUTO":
        heat_v = equipment_data.get("Heat Valve (%)", 0) or 0
        cool_v = equipment_data.get("Cool Valve (%)", 0) or 0
        oat = equipment_data.get("OAT (°C)")
        if heat_v > cool_v and heat_v >= 15:
            mode = "HEATING"
        elif oat is not None and oat < 10.0:
            mode = "HEATING"
        else:
            mode = "COOLING"
    
    # FCU set kontrolü
    if "FCU" in eq_type.upper():
        set_temp = equipment_data.get("Set (°C)")
        result = rules.validate_fcu_set(set_temp)
        if not result["valid"]:
            issues.append(result)
    
    # AHU SAT kontrolü
    if "AHU" in eq_type.upper():
        sat = equipment_data.get("SAT (°C)") or equipment_data.get("Supply (°C)")
        result = rules.validate_ahu_sat(sat, mode)
        if not result["valid"]:
            issues.append(result)
    
    # Transfer kontrolü
    if "FCU" in eq_type.upper() or "AHU" in eq_type.upper():
        transfer = equipment_data.get("Inlet (°C)")
        result = rules.validate_transfer_temp(transfer, eq_type, mode)
        if not result["valid"]:
            issues.append(result)
    
    return issues
