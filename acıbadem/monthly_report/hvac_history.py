# hvac_history.py
# HVAC analiz sonuçlarını tarih bazlı kaydetme modülü

from __future__ import annotations
import os
import pandas as pd
from datetime import date, datetime
from typing import Dict, List, Optional
import json


# HVAC analiz geçmişi dosyası
HVAC_HISTORY_FILE = "hvac_analysis_history.csv"


class HVACHistoryManager:
    """
    HVAC analiz sonuçlarını tarih bazlı kaydeden ve sorgulayan sınıf.
    Her analiz çalıştırıldığında özet veriler bu dosyaya kaydedilir.
    """
    
    # Kaydedilecek özet alanları
    HISTORY_COLUMNS = [
        "Tarih",
        "Analiz_Zamani",
        "Toplam_AHU",
        "Toplam_FCU", 
        "Sogutma_Modu_Adet",
        "Isitma_Modu_Adet",
        "Ort_Delta_T",
        "Min_Delta_T",
        "Max_Delta_T",
        "Ort_Vana_Acikligi",
        "Kritik_Sorun_Adet",
        "Uyari_Adet",
        "Optimal_Adet",
        "Sogutma_Modu_Yuzde",
        "Isitma_Modu_Yuzde",
        "Esit_Zamanli_Isitma_Sogutma",  # True/False
        "Dusuk_DeltaT_Adet",  # ΔT < 3°C olanlar
        "SAT_Sorun_Adet",  # NOT_COOLING veya NOT_HEATING
        "Analiz_CSV_Dosyasi",  # Hangi CSV analiz edildi
        # ========== AHU KAPASİTE ANALİZİ ==========
        "AHU_Ort_Sogutma_Vana",   # Sadece AHU'ların ort. soğutma vana %
        "AHU_Ort_Isitma_Vana",    # Sadece AHU'ların ort. ısıtma vana %
        "AHU_Sogutma_Kapasite",   # YETERLI / DIKKAT / YETERSIZ
        "AHU_Isitma_Kapasite",    # YETERLI / DIKKAT / YETERSIZ
    ]
    
    def __init__(self, history_file: str = None):
        self.history_file = history_file or HVAC_HISTORY_FILE
        self._ensure_file_exists()
    
    def _ensure_file_exists(self):
        """Dosya yoksa oluştur"""
        if not os.path.exists(self.history_file):
            df = pd.DataFrame(columns=self.HISTORY_COLUMNS)
            df.to_csv(self.history_file, index=False)
    
    def load_history(self) -> pd.DataFrame:
        """Tüm geçmişi yükle"""
        try:
            df = pd.read_csv(self.history_file)
            if "Tarih" in df.columns:
                # Düzeltme: ISO standart format kullan (locale bağımsız)
                df["Tarih"] = pd.to_datetime(df["Tarih"], format="%Y-%m-%d", errors="coerce").dt.date
            return df
        except Exception as e:
            print(f"HVAC history yükleme hatası: {e}")
            return pd.DataFrame(columns=self.HISTORY_COLUMNS)
    
    def save_analysis_summary(self, analysis_date: date, results: List[Dict], 
                               csv_filename: str = None) -> bool:
        """
        Analiz sonuçlarını özet olarak kaydet.
        
        Args:
            analysis_date: Analiz yapılan tarih
            results: Analiz sonuçları listesi (her santral için dict)
            csv_filename: Analiz edilen CSV dosyası
        """
        try:
            # Özet hesapla
            summary = self._calculate_summary(analysis_date, results, csv_filename)
            
            # Mevcut geçmişi yükle
            df = self.load_history()
            
            # Aynı tarih varsa güncelle, yoksa ekle
            if not df.empty and analysis_date in df["Tarih"].values:
                df = df[df["Tarih"] != analysis_date]
            
            # Yeni satır ekle
            new_row = pd.DataFrame([summary])
            df = pd.concat([df, new_row], ignore_index=True)
            
            # Tarihe göre sırala
            df = df.sort_values("Tarih")
            
            # Kaydet
            df.to_csv(self.history_file, index=False)
            
            return True
            
        except Exception as e:
            print(f"HVAC history kaydetme hatası: {e}")
            return False
    
    def _calculate_summary(self, analysis_date: date, results: List[Dict], 
                           csv_filename: str) -> Dict:
        """Analiz sonuçlarından özet hesapla"""
        
        if not results:
            return {col: None for col in self.HISTORY_COLUMNS}
        
        # Temel sayımlar - Type sütununu kontrol et (hem "Type" hem "Tip" destekle)
        def get_type(r):
            return (r.get("Type") or r.get("Tip") or "").upper()
        
        total_ahu = sum(1 for r in results if get_type(r) == "AHU")
        total_fcu = sum(1 for r in results if get_type(r) == "FCU")
        
        # Mod sayımları — effective_mode varsa onu kullan, yoksa Mode'a bak
        def get_eff_mode(r):
            return str(r.get("Effective_Mode") or r.get("effective_mode") or r.get("Mode") or "").upper()
        cooling_count = sum(1 for r in results if "COOL" in get_eff_mode(r))
        heating_count = sum(1 for r in results if "HEAT" in get_eff_mode(r))
        
        total_units = len(results)
        cooling_pct = (cooling_count / total_units * 100) if total_units > 0 else 0
        heating_pct = (heating_count / total_units * 100) if total_units > 0 else 0
        
        # Eş zamanlı ısıtma-soğutma kontrolü - HER İKİ VANA DA AÇIK MI?
        simul_heat_cool_count = 0
        for r in results:
            cool_v = r.get("Cool Valve (%)") or r.get("cool_valve") or 0
            heat_v = r.get("Heat Valve (%)") or r.get("heat_valve") or 0
            try:
                cool_v = float(str(cool_v).replace('%', '').replace(',', '.'))
                heat_v = float(str(heat_v).replace('%', '').replace(',', '.'))
            except:
                cool_v, heat_v = 0, 0
            
            # Eşik: Her iki vana da %5'ten fazla açık
            if cool_v >= 5 and heat_v >= 5:
                simul_heat_cool_count += 1
        
        simul_heat_cool = simul_heat_cool_count > 0
        
        # ΔT istatistikleri
        delta_t_values = []
        for r in results:
            dt = r.get("Su ΔT (°C)") or r.get("ΔT (°C)") or r.get("delta_t")
            if dt is not None:
                try:
                    delta_t_values.append(float(dt))
                except:
                    pass
        
        avg_dt = sum(delta_t_values) / len(delta_t_values) if delta_t_values else None
        min_dt = min(delta_t_values) if delta_t_values else None
        max_dt = max(delta_t_values) if delta_t_values else None
        low_dt_count = sum(1 for dt in delta_t_values if dt < 3.0)
        
        # Vana açıklığı ortalaması - tüm olası sütun isimlerini destekle
        valve_values = []
        for r in results:
            # Cool ve Heat vana değerlerini al
            cool_v = r.get("Cool Valve (%)") or r.get("Soğutma Vana (%)") or r.get("cool_valve")
            heat_v = r.get("Heat Valve (%)") or r.get("Isıtma Vana (%)") or r.get("heat_valve")
            valve = r.get("Vana Açıklığı (%)") or r.get("valve_opening")
            
            # Hangisi doluysa onu kullan (max değeri al)
            values_to_check = [cool_v, heat_v, valve]
            for v in values_to_check:
                if v is not None:
                    try:
                        valve_values.append(float(str(v).replace('%', '').replace(',', '.')))
                        break  # İlk geçerli değeri bulduk
                    except:
                        pass
        avg_valve = sum(valve_values) / len(valve_values) if valve_values else None
        
        # Severity sayımları
        critical_count = sum(1 for r in results if str(r.get("Severity", "")).upper() == "CRITICAL")
        warning_count = sum(1 for r in results if str(r.get("Severity", "")).upper() == "WARNING")
        optimal_count = sum(1 for r in results if str(r.get("Severity", "")).upper() == "OPTIMAL")
        
        # SAT sorun sayısı (Critical + Warning)
        sat_issues = sum(1 for r in results 
                         if r.get("Rule") in ["NOT_COOLING", "NOT_HEATING", "SAT_HIGH", "SAT_LOW"]
                         or "NOT_COOLING" in str(r.get("SAT Status", "")).upper() 
                         or "NOT_HEATING" in str(r.get("SAT Status", "")).upper())
        
        # ========== AHU KAPASİTE ANALİZİ ==========
        # Sadece AHU'lar için soğutma ve ısıtma vana ortalamalarını hesapla
        ahu_cooling_valves = []
        ahu_heating_valves = []
        
        for r in results:
            eq_type = get_type(r)
            if eq_type != "AHU":
                continue
            
            # Soğutma vanası
            cool_v = r.get("Cool Valve (%)") or r.get("Soğutma Vana (%)") or r.get("cool_valve")
            if cool_v is not None:
                try:
                    val = float(str(cool_v).replace('%', '').replace(',', '.'))
                    if val > 0:  # Sadece açık olan vanaları hesaba kat
                        ahu_cooling_valves.append(val)
                except:
                    pass
            
            # Isıtma vanası
            heat_v = r.get("Heat Valve (%)") or r.get("Isıtma Vana (%)") or r.get("heat_valve")
            if heat_v is not None:
                try:
                    val = float(str(heat_v).replace('%', '').replace(',', '.'))
                    if val > 0:  # Sadece açık olan vanaları hesaba kat
                        ahu_heating_valves.append(val)
                except:
                    pass
        
        # Ortalama hesapla
        ahu_avg_cooling = sum(ahu_cooling_valves) / len(ahu_cooling_valves) if ahu_cooling_valves else None
        ahu_avg_heating = sum(ahu_heating_valves) / len(ahu_heating_valves) if ahu_heating_valves else None
        
        # Kapasite değerlendirmesi fonksiyonu
        def evaluate_capacity(avg_valve):
            """
            Kapasite değerlendirmesi:
            - <50% : YETERLI (rezerv var)
            - 50-70%: NORMAL
            - 70-85%: DIKKAT (sınıra yakın)
            - >85% : YETERSIZ (sistem zorlanıyor)
            """
            if avg_valve is None:
                return "VERİ YOK"
            if avg_valve < 50:
                return "YETERLI"
            elif avg_valve < 70:
                return "NORMAL"
            elif avg_valve < 85:
                return "DIKKAT"
            else:
                return "YETERSIZ"
        
        ahu_cooling_capacity = evaluate_capacity(ahu_avg_cooling)
        ahu_heating_capacity = evaluate_capacity(ahu_avg_heating)
        
        return {
            "Tarih": analysis_date,
            "Analiz_Zamani": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "Toplam_AHU": total_ahu,
            "Toplam_FCU": total_fcu,
            "Sogutma_Modu_Adet": cooling_count,
            "Isitma_Modu_Adet": heating_count,
            "Ort_Delta_T": round(avg_dt, 2) if avg_dt is not None else None,
            "Min_Delta_T": round(min_dt, 2) if min_dt is not None else None,
            "Max_Delta_T": round(max_dt, 2) if max_dt is not None else None,
            "Ort_Vana_Acikligi": round(avg_valve, 1) if avg_valve is not None else None,
            "Kritik_Sorun_Adet": critical_count,
            "Uyari_Adet": warning_count,
            "Optimal_Adet": optimal_count,
            "Sogutma_Modu_Yuzde": round(cooling_pct, 1),
            "Isitma_Modu_Yuzde": round(heating_pct, 1),
            "Esit_Zamanli_Isitma_Sogutma": simul_heat_cool,
            "Dusuk_DeltaT_Adet": low_dt_count,
            "SAT_Sorun_Adet": sat_issues,
            "Analiz_CSV_Dosyasi": csv_filename or "",
            # AHU Kapasite Analizi
            "AHU_Ort_Sogutma_Vana": round(ahu_avg_cooling, 1) if ahu_avg_cooling is not None else None,
            "AHU_Ort_Isitma_Vana": round(ahu_avg_heating, 1) if ahu_avg_heating is not None else None,
            "AHU_Sogutma_Kapasite": ahu_cooling_capacity,
            "AHU_Isitma_Kapasite": ahu_heating_capacity,
        }
    
    def get_history_for_month(self, year: int, month: int) -> pd.DataFrame:
        """Belirli bir ay için geçmişi getir"""
        df = self.load_history()
        if df.empty:
            return df
        
        df_month = df[
            (pd.to_datetime(df["Tarih"], format="%Y-%m-%d", errors="coerce").dt.year == year) &
            (pd.to_datetime(df["Tarih"], format="%Y-%m-%d", errors="coerce").dt.month == month)
        ]
        return df_month
    
    def get_monthly_summary(self, year: int, month: int) -> Dict:
        """Aylık özet istatistikler"""
        df = self.get_history_for_month(year, month)
        
        if df.empty:
            return {
                "days_with_data": 0,
                "total_analyses": 0,
            }
        
        return {
            "days_with_data": len(df),
            "total_analyses": len(df),
            "avg_ahu_count": df["Toplam_AHU"].mean() if "Toplam_AHU" in df else 0,
            "avg_fcu_count": df["Toplam_FCU"].mean() if "Toplam_FCU" in df else 0,
            "avg_delta_t": df["Ort_Delta_T"].mean() if "Ort_Delta_T" in df else None,
            "total_critical": df["Kritik_Sorun_Adet"].sum() if "Kritik_Sorun_Adet" in df else 0,
            "total_warning": df["Uyari_Adet"].sum() if "Uyari_Adet" in df else 0,
            "avg_cooling_pct": df["Sogutma_Modu_Yuzde"].mean() if "Sogutma_Modu_Yuzde" in df else 0,
            "avg_heating_pct": df["Isitma_Modu_Yuzde"].mean() if "Isitma_Modu_Yuzde" in df else 0,
            "simul_heat_cool_days": df["Esit_Zamanli_Isitma_Sogutma"].sum() if "Esit_Zamanli_Isitma_Sogutma" in df else 0,
            "low_delta_t_total": df["Dusuk_DeltaT_Adet"].sum() if "Dusuk_DeltaT_Adet" in df else 0,
            "sat_issues_total": df["SAT_Sorun_Adet"].sum() if "SAT_Sorun_Adet" in df else 0,
            # AHU Kapasite Analizi
            "ahu_avg_cooling_valve": df["AHU_Ort_Sogutma_Vana"].mean() if "AHU_Ort_Sogutma_Vana" in df else None,
            "ahu_avg_heating_valve": df["AHU_Ort_Isitma_Vana"].mean() if "AHU_Ort_Isitma_Vana" in df else None,
            "ahu_cooling_capacity": df["AHU_Sogutma_Kapasite"].mode().iloc[0] if "AHU_Sogutma_Kapasite" in df and not df["AHU_Sogutma_Kapasite"].empty else "VERİ YOK",
            "ahu_heating_capacity": df["AHU_Isitma_Kapasite"].mode().iloc[0] if "AHU_Isitma_Kapasite" in df and not df["AHU_Isitma_Kapasite"].empty else "VERİ YOK",
        }
