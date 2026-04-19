# data_merger.py
# HVAC + Enerji verilerini birleştiren modül

from __future__ import annotations
import os
import pandas as pd
from datetime import date, datetime
from typing import Dict, List, Optional
import statistics
import math
from pathlib import Path


def _safe_mean(values):
    """Güvenli ortalama — float'a çevirir, NaN/None temizler."""
    clean = []
    for v in values:
        try:
            f = float(v)
            if not math.isnan(f):
                clean.append(f)
        except (TypeError, ValueError):
            continue
    return statistics.mean(clean) if clean else None

# Enerji veri dosyası (app_portal.py ile aynı)
DATA_FILE = "energy_data.csv"

class UnifiedDataMerger:
    """
    HVAC ve Enerji portal verilerini birleştiren sınıf.
    Aylık rapor için günlük birleşik veri sağlar.
    HVAC history modülü ile entegre çalışır.
    """
    
    def __init__(self, energy_csv_path: str = None, hvac_data_callback = None):
        """
        Args:
            energy_csv_path: Enerji CSV dosyasının yolu
            hvac_data_callback: HVAC verilerini getiren fonksiyon (opsiyonel)
        """
        self.energy_csv_path = energy_csv_path or DATA_FILE
        self.hvac_data_callback = hvac_data_callback
        
        # HVAC History Manager'ı yükle
        self.hvac_history = None
        try:
            from .hvac_history import HVACHistoryManager
            self.hvac_history = HVACHistoryManager()
        except ImportError:
            pass
        
    def load_energy_data(self) -> pd.DataFrame:
        """Enerji portal verilerini yükle"""
        if not os.path.exists(self.energy_csv_path):
            return pd.DataFrame()
        
        try:
            df = pd.read_csv(self.energy_csv_path)
            if "Tarih" in df.columns:
                df["Tarih"] = pd.to_datetime(df["Tarih"], format="%Y-%m-%d", errors="coerce").dt.date
            return df
        except Exception as e:
            print(f"Enerji verisi yükleme hatası: {e}")
            return pd.DataFrame()
    
    def get_energy_data_for_date(self, target_date: date) -> Dict:
        """Belirli bir gün için enerji verileri"""
        df = self.load_energy_data()
        if df.empty:
            return {}
        
        day_data = df[df["Tarih"] == target_date]
        if day_data.empty:
            return {}
        
        row = day_data.iloc[0]
        return {
            "date": target_date,
            "chiller_set_temp": row.get("Chiller_Set_Temp_C"),
            "chiller_count": row.get("Chiller_Adet"),
            "absorption_chiller_count": row.get("Absorption_Chiller_Adet"),
            "boiler_count": row.get("Kazan_Adet"),
            "grid_consumption": row.get("Sebeke_Tuketim_kWh"),
            "cogen_production": row.get("Kojen_Uretim_kWh"),
            "boiler_gas": row.get("Kazan_Dogalgaz_m3"),
            "cogen_gas": row.get("Kojen_Dogalgaz_m3"),
            "water_consumption": row.get("Su_Tuketimi_m3"),
            "chiller_consumption": row.get("Chiller_Tuketim_kWh"),
            "mcc_consumption": row.get("MCC_Tuketim_kWh"),
            "vrf_consumption": row.get("VRF_Split_Tuketim_kWh"),
            "outdoor_temp": row.get("Dis_Hava_Sicakligi_C"),
            "total_hospital": row.get("Toplam_Hastane_Tuketim_kWh"),
            "total_cooling": row.get("Toplam_Sogutma_Tuketim_kWh"),
            "other_load": row.get("Diger_Yuk_kWh"),
            # Sıcaklık verileri
            "mas1_heating_temp": row.get("Mas1_Isitma_Temp"),
            "mas1_boiler_temp": row.get("Mas1_Kazan_Temp"),
            "mas1_cooling_temp": row.get("Mas1_Sogutma_Temp"),
            "mas2_heating_temp": row.get("Mas2_Isitma_Temp"),
            "mas2_boiler_temp": row.get("Mas2_Kazan_Temp"),
            "mas2_cooling_temp": row.get("Mas2_Sogutma_Temp"),
        }
    
    def get_energy_data_for_month(self, year: int, month: int) -> pd.DataFrame:
        """Belirli bir ay için tüm enerji verileri"""
        df = self.load_energy_data()
        if df.empty:
            return df
        
        # Ay filtresi
        df_month = df[
            (pd.to_datetime(df["Tarih"], format="%Y-%m-%d", errors="coerce").dt.year == year) &
            (pd.to_datetime(df["Tarih"], format="%Y-%m-%d", errors="coerce").dt.month == month)
        ]
        return df_month
    
    def get_hvac_data_for_date(self, target_date: date) -> List[Dict]:
        """
        Belirli bir gün için HVAC santral verileri.
        NOT: Bu fonksiyon HVAC portalından veri çekecek şekilde genişletilebilir.
        Şimdilik placeholder olarak boş liste döner.
        """
        if self.hvac_data_callback:
            return self.hvac_data_callback(target_date)
        
        # Placeholder - gerçek implementasyonda HVAC portalından veri çekilecek
        return []
    
    def merge_daily_data(self, target_date: date) -> Dict:
        """
        Belirli bir gün için HVAC + Enerji birleşik veri.
        """
        energy = self.get_energy_data_for_date(target_date)
        hvac_list = self.get_hvac_data_for_date(target_date)
        
        # HVAC özet istatistikleri
        hvac_summary = {
            "total_ahu_count": len(hvac_list),
            "cooling_mode_count": 0,
            "heating_mode_count": 0,
            "avg_delta_t": None,
            "critical_count": 0,
            "warning_count": 0,
            "optimal_count": 0,
        }
        
        if hvac_list:
            delta_t_values = []
            for ahu in hvac_list:
                mode = ahu.get("mode", "").upper()
                if "COOL" in mode:
                    hvac_summary["cooling_mode_count"] += 1
                elif "HEAT" in mode:
                    hvac_summary["heating_mode_count"] += 1
                
                severity = ahu.get("severity", "").upper()
                if severity == "CRITICAL":
                    hvac_summary["critical_count"] += 1
                elif severity == "WARNING":
                    hvac_summary["warning_count"] += 1
                else:
                    hvac_summary["optimal_count"] += 1
                
                dt = ahu.get("delta_t")
                if dt is not None:
                    delta_t_values.append(float(dt))
            
            if delta_t_values:
                hvac_summary["avg_delta_t"] = _safe_mean(delta_t_values)
        
        return {
            "date": target_date,
            "energy": energy,
            "hvac": hvac_summary,
            "hvac_details": hvac_list
        }
    
    def merge_monthly_data(self, year: int, month: int) -> Dict:
        """
        Bir ay için tüm günlerin birleşik verileri ve özet istatistikler.
        HVAC history modülünden de veri alır.
        """
        import calendar
        
        # Ayın gün sayısı
        _, days_in_month = calendar.monthrange(year, month)
        
        daily_data = []
        for day in range(1, days_in_month + 1):
            try:
                d = date(year, month, day)
                daily = self.merge_daily_data(d)
                if daily["energy"]:  # Veri varsa ekle
                    daily_data.append(daily)
            except ValueError:
                continue
        
        # Aylık özet hesapla (önce enerji verileri)
        summary = self._calculate_monthly_summary(daily_data)
        
        # HVAC history'den aylık özet al ve birleştir
        hvac_monthly = self._get_hvac_history_summary(year, month)
        if hvac_monthly:
            summary.update({
                "hvac_history_available": True,
                "hvac_days_with_data": hvac_monthly.get("days_with_data", 0),
                "hvac_avg_delta_t": hvac_monthly.get("avg_delta_t"),
                "hvac_total_critical": hvac_monthly.get("total_critical", 0),
                "hvac_total_warning": hvac_monthly.get("total_warning", 0),
                "hvac_avg_cooling_pct": hvac_monthly.get("avg_cooling_pct", 0),
                "hvac_avg_heating_pct": hvac_monthly.get("avg_heating_pct", 0),
                "hvac_simul_heat_cool_days": hvac_monthly.get("simul_heat_cool_days", 0),
                "hvac_low_delta_t_total": hvac_monthly.get("low_delta_t_total", 0),
                "hvac_sat_issues_total": hvac_monthly.get("sat_issues_total", 0),
                # AHU Kapasite Analizi
                "ahu_avg_cooling_valve": hvac_monthly.get("ahu_avg_cooling_valve"),
                "ahu_avg_heating_valve": hvac_monthly.get("ahu_avg_heating_valve"),
                "ahu_cooling_capacity": hvac_monthly.get("ahu_cooling_capacity", "VERİ YOK"),
                "ahu_heating_capacity": hvac_monthly.get("ahu_heating_capacity", "VERİ YOK"),
            })
        else:
            summary["hvac_history_available"] = False
        
        return {
            "year": year,
            "month": month,
            "days_with_data": len(daily_data),
            "daily_data": daily_data,
            "summary": summary,
            "hvac_monthly_summary": hvac_monthly
        }
    
    def _get_hvac_history_summary(self, year: int, month: int) -> Optional[Dict]:
        """HVAC history'den aylık özet al"""
        if self.hvac_history is None:
            return None
        
        try:
            return self.hvac_history.get_monthly_summary(year, month)
        except Exception as e:
            print(f"HVAC history özet hatası: {e}")
            return None
    
    def _calculate_monthly_summary(self, daily_data: List[Dict]) -> Dict:
        """Aylık özet istatistikler"""
        if not daily_data:
            return {}
        
        # Enerji toplamları - NaN güvenli toplama
        def safe_sum(key):
            """Bir anahtar için tüm günleri topla, NaN/None'ı 0 say"""
            total = 0.0
            for d in daily_data:
                val = d["energy"].get(key)
                if val is not None:
                    try:
                        f_val = float(val)
                        if not math.isnan(f_val):
                            total += f_val
                    except (ValueError, TypeError):
                        pass
            return total

        total_grid = safe_sum("grid_consumption")
        total_cooling = safe_sum("total_cooling")
        total_hospital = safe_sum("total_hospital")
        total_boiler_gas = safe_sum("boiler_gas")
        total_cogen_gas = safe_sum("cogen_gas")
        total_mcc = safe_sum("mcc_consumption")
        
        # Yeni: VRF/Split ve Su tüketimi toplamları
        total_vrf = safe_sum("vrf_consumption")
        total_water = safe_sum("water_consumption")
        total_chiller = safe_sum("chiller_consumption")
        
        # Ortalamalar
        chiller_sets = [d["energy"].get("chiller_set_temp") for d in daily_data if d["energy"].get("chiller_set_temp")]
        outdoor_temps = [d["energy"].get("outdoor_temp") for d in daily_data if d["energy"].get("outdoor_temp")]
        
        avg_chiller_set = _safe_mean(chiller_sets) if chiller_sets else None
        avg_outdoor_temp = _safe_mean(outdoor_temps) if outdoor_temps else None
        
        # Yeni: MAS santral sıcaklıkları ortalaması
        mas1_cooling_temps = [d["energy"].get("mas1_cooling_temp") for d in daily_data if d["energy"].get("mas1_cooling_temp")]
        mas2_cooling_temps = [d["energy"].get("mas2_cooling_temp") for d in daily_data if d["energy"].get("mas2_cooling_temp")]
        mas1_heating_temps = [d["energy"].get("mas1_heating_temp") for d in daily_data if d["energy"].get("mas1_heating_temp")]
        mas2_heating_temps = [d["energy"].get("mas2_heating_temp") for d in daily_data if d["energy"].get("mas2_heating_temp")]
        
        avg_mas1_cooling = _safe_mean(mas1_cooling_temps) if mas1_cooling_temps else None
        avg_mas2_cooling = _safe_mean(mas2_cooling_temps) if mas2_cooling_temps else None
        avg_mas1_heating = _safe_mean(mas1_heating_temps) if mas1_heating_temps else None
        avg_mas2_heating = _safe_mean(mas2_heating_temps) if mas2_heating_temps else None
        
        # Yeni: Dönüş sıcaklıkları ortalaması (iç ortam göstergesi olarak)
        all_return_temps = mas1_cooling_temps + mas2_cooling_temps + mas1_heating_temps + mas2_heating_temps
        # Düzeltme: NumPy tiplerini (int64/float64) standart float'a çevir
        all_return_temps = [float(x) for x in all_return_temps if x is not None]
        avg_return_temp = _safe_mean(all_return_temps) if all_return_temps else None
        
        # Yeni: Enerji Verimlilik İndeksi = Toplam Tüketim / |Dış Hava - Dönüş Sıcaklığı|
        efficiency_index = None
        if avg_outdoor_temp is not None and avg_return_temp is not None:
            temp_diff = abs(avg_outdoor_temp - avg_return_temp)
            if temp_diff > 1:  # En az 1°C fark olmalı
                efficiency_index = total_hospital / temp_diff if total_hospital > 0 else None
        
        # HVAC özet
        total_ahu = sum(d["hvac"]["total_ahu_count"] for d in daily_data)
        total_cooling_mode = sum(d["hvac"]["cooling_mode_count"] for d in daily_data)
        total_heating_mode = sum(d["hvac"]["heating_mode_count"] for d in daily_data)
        total_critical = sum(d["hvac"]["critical_count"] for d in daily_data)
        
        delta_t_values = [d["hvac"]["avg_delta_t"] for d in daily_data if d["hvac"]["avg_delta_t"]]
        avg_delta_t = _safe_mean(delta_t_values) if delta_t_values else None
        
        return {
            # Enerji toplamları
            "total_grid_consumption": total_grid,
            "total_cooling_consumption": total_cooling,
            "total_hospital_consumption": total_hospital,
            "total_gas": total_boiler_gas + total_cogen_gas,
            "total_boiler_gas": total_boiler_gas,
            "total_cogen_gas": total_cogen_gas,
            "total_mcc_consumption": total_mcc,
            
            # Yeni: VRF, Su, Chiller toplamları
            "total_vrf_consumption": total_vrf,
            "total_water_consumption": total_water,
            "total_chiller_consumption": total_chiller,
            
            # Ortalamalar
            "avg_chiller_set_temp": avg_chiller_set,
            "avg_outdoor_temp": avg_outdoor_temp,
            
            # Yeni: MAS santral sıcaklıkları
            "avg_mas1_cooling_temp": avg_mas1_cooling,
            "avg_mas2_cooling_temp": avg_mas2_cooling,
            "avg_mas1_heating_temp": avg_mas1_heating,
            "avg_mas2_heating_temp": avg_mas2_heating,
            "avg_return_temp": avg_return_temp,
            
            # Yeni: Enerji Verimlilik İndeksi (kWh/°C)
            "efficiency_index": efficiency_index,
            
            # HVAC özet
            "total_ahu_analyzed": total_ahu,
            "cooling_mode_percentage": (total_cooling_mode / total_ahu * 100) if total_ahu > 0 else 0,
            "heating_mode_percentage": (total_heating_mode / total_ahu * 100) if total_ahu > 0 else 0,
            "total_critical_issues": total_critical,
            "avg_delta_t": avg_delta_t,
        }
