# savings_engine.py
# Otomatik tasarruf önerileri motoru - kural bazlı, kendi öğrenen sistem

from __future__ import annotations
from datetime import datetime
from typing import Dict, List, Optional, Callable
import json
import os


class SavingsRule:
    """Tek bir tasarruf kuralı"""
    
    def __init__(self, rule_id: str, name: str, severity: str,
                 condition: Callable, message_template: str,
                 savings_potential: str, category: str):
        self.rule_id = rule_id
        self.name = name
        self.severity = severity  # CRITICAL, WARNING, INFO
        self.condition = condition
        self.message_template = message_template
        self.savings_potential = savings_potential
        self.category = category  # ENERGY, HVAC, CHILLER, MCC


class SavingsRecommendationEngine:
    """
    Otomatik tasarruf önerileri motoru.
    Kural bazlı analiz yaparak tasarruf fırsatlarını tespit eder.
    Feedback loop ile kendi öğrenir.
    """
    
    def __init__(self, training_data_path: str = "savings_training_data.json"):
        self.training_data_path = training_data_path
        self.training_data = self._load_training_data()
        self.rules = self._initialize_rules()
    
    def _load_training_data(self) -> List[Dict]:
        """Eğitim verilerini yükle"""
        if os.path.exists(self.training_data_path):
            try:
                with open(self.training_data_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return []
        return []
    
    def _save_training_data(self):
        """Eğitim verilerini kaydet"""
        try:
            with open(self.training_data_path, "w", encoding="utf-8") as f:
                json.dump(self.training_data, f, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            print(f"Training data kaydetme hatası: {e}")
    
    def _initialize_rules(self) -> List[SavingsRule]:
        """Tasarruf kurallarını tanımla"""
        rules = [
            # 1. Chiller Set Sıcaklığı
            SavingsRule(
                rule_id="CHILLER_SET_LOW",
                name="Chiller Set Sıcaklığı Düşük",
                severity="WARNING",
                condition=self._check_chiller_set_low,
                message_template="""Chiller set sıcaklığı geçen yıla göre düşürülmüş.
Geçen yıl: {prev_chiller_set:.1f}°C → Bu yıl: {cur_chiller_set:.1f}°C
Her 1°C düşüş yaklaşık %3-5 enerji artışına neden olur.
ÖNERİ: Konfor koşulları izin veriyorsa set sıcaklığını {prev_chiller_set:.1f}°C'ye yükseltin.""",
                savings_potential="3-5%",
                category="CHILLER"
            ),
            
            # 2. MCC Tüketim Anomalisi
            SavingsRule(
                rule_id="MCC_SPIKE",
                name="MCC Tüketim Anomalisi",
                severity="CRITICAL",
                condition=self._check_mcc_spike,
                message_template="""MCC tüketiminde anormal artış tespit edildi!
Geçen yıl: {prev_mcc:,.0f} kWh → Bu yıl: {cur_mcc:,.0f} kWh ({change_pct:+.1f}%)
ÖNERİ: Sahada unutulmuş cihaz kontrolü yapın.
Olası sebepler: Klima, ısıtıcı, makine vb. unutulmuş olabilir.""",
                savings_potential="10-20%",
                category="MCC"
            ),
            
            # 3. Eş Zamanlı Isıtma-Soğutma
            SavingsRule(
                rule_id="SIMUL_HEAT_COOL",
                name="Eş Zamanlı Isıtma-Soğutma",
                severity="WARNING",
                condition=self._check_simultaneous_heat_cool,
                message_template="""Aynı dönemde hem ısıtma hem soğutma tespit edildi!
Soğutma modu: %{cooling_pct:.0f} | Isıtma modu: %{heating_pct:.0f}
Bu durum enerji israfına yol açar.
ÖNERİ: Dead-band ayarlarını kontrol edin (min 2-3°C aralık bırakın).
Oda termostatlarını gözden geçirin.""",
                savings_potential="5-15%",
                category="HVAC"
            ),
            
            # 4. Düşük Su ΔT
            SavingsRule(
                rule_id="LOW_DELTA_T",
                name="Düşük Su ΔT Değeri",
                severity="INFO",
                condition=self._check_low_delta_t,
                message_template="""Ortalama Su ΔT değeri düşük: {avg_delta_t:.1f}°C
Hedef Su ΔT: 5-8°C (Soğutma) veya 8-12°C (Isıtma)
Düşük Su ΔT, pompanın verimsiz çalıştığını veya vana sorununu gösterir.
ÖNERİ: Pompa hızlarını ve vana açıklıklarını kontrol edin.""",
                savings_potential="2-5%",
                category="HVAC"
            ),
            
            # 5. Yüksek Kritik Sorun Sayısı
            SavingsRule(
                rule_id="HIGH_CRITICAL_COUNT",
                name="Yüksek Kritik Sorun Sayısı",
                severity="CRITICAL",
                condition=self._check_high_critical_count,
                message_template="""Bu ay toplam {critical_count} kritik HVAC sorunu tespit edildi.
Geçen yıla göre {change_text}.
ÖNERİ: Bakım planını gözden geçirin, arızalı ekipmanları tespit edin.""",
                savings_potential="5-10%",
                category="HVAC"
            ),
            
            # 6. Toplam Tüketim Artışı
            SavingsRule(
                rule_id="TOTAL_CONSUMPTION_INCREASE",
                name="Toplam Tüketim Artışı",
                severity="WARNING",
                condition=self._check_total_consumption_increase,
                message_template="""Toplam hastane tüketimi geçen yıla göre arttı.
Geçen yıl: {prev_total:,.0f} kWh → Bu yıl: {cur_total:,.0f} kWh ({change_pct:+.1f}%)
ÖNERİ: Tüketim artışının nedenini araştırın.
- Yeni ekipman mı eklendi?
- Çalışma saatleri mi uzadı?
- Verimlilik kaybı mı var?""",
                savings_potential="5-15%",
                category="ENERGY"
            ),
            
            # ========== AKILLI HARMANLAMA KURALLARI (HVAC + ENERJİ) ==========
            
            # 7. Chiller Tüketimi Yüksek + Su ΔT Düşük = Pompa/Vana Sorunu
            SavingsRule(
                rule_id="CHILLER_HIGH_DELTA_LOW",
                name="Chiller Tüketimi ↑ + Su ΔT ↓ = Pompa/Vana Sorunu",
                severity="CRITICAL",
                condition=self._check_chiller_high_delta_low,
                message_template="""Kritik Harmanlama Analizi: Chiller tüketimi yüksek ama Su ΔT düşük!
🔹 Chiller Tüketimi: {chiller_consumption:,.0f} kWh (Geçen yıla göre +{chiller_change:.1f}%)
🔹 Ortalama Su ΔT: {avg_delta_t:.1f}°C (Hedef: 5-8°C)

Bu durum pompanın verimsiz çalıştığını veya vana sorununu gösterir.
Chiller soğuk su üretiyor ama sistem bu kapasiteyi kullanamıyor!

ÖNERİ:
1. Pompa hızlarını kontrol edin (VFD ayarları)
2. Vana açıklıklarını ve aktüatörleri kontrol edin
3. Borularda tıkanıklık/kirlenme kontrolü yapın
4. Basınç farkını ölçün""",
                savings_potential="10-20%",
                category="COMBINED"
            ),
            
            # 8. Chiller Set Düşük + Soğutma Tüketimi Yüksek
            SavingsRule(
                rule_id="CHILLER_SET_VS_CONSUMPTION",
                name="Chiller Set ↓ + Tüketim ↑ = Set Sıcaklığı Optimizasyonu",
                severity="WARNING",
                condition=self._check_chiller_set_vs_consumption,
                message_template="""Harmanlama Analizi: Chiller set sıcaklığı düşük, tüketim artmış!
🔹 Chiller Set: {cur_chiller_set:.1f}°C (Geçen yıl: {prev_chiller_set:.1f}°C)
🔹 Soğutma Tüketimi Değişimi: {consumption_change:+.1f}%

Her 1°C düşüş yaklaşık %3-5 enerji artışına neden olur.
Tahminî tasarruf: Set sıcaklığını {prev_chiller_set:.1f}°C'ye yükseltirseniz yıllık {estimated_savings:,.0f} kWh tasarruf!

ÖNERİ:
1. Konfor şikayetleri var mı kontrol edin
2. Yoksa set sıcaklığını kademeli olarak yükseltin
3. İç ortam sıcaklıklarını monitör edin""",
                savings_potential="5-10%",
                category="COMBINED"
            ),
            
            # 9. Isıtma-Soğutma Eşzamanlı + Yüksek Tüketim
            SavingsRule(
                rule_id="SIMUL_HEAT_COOL_HIGH_CONSUMPTION",
                name="Isıtma-Soğutma Eşzamanlı + Yüksek Tüketim = Dead-band Ayarı",
                severity="CRITICAL",
                condition=self._check_simul_with_high_consumption,
                message_template="""Kritik Harmanlama Analizi: Eşzamanlı ısıtma-soğutma + yüksek tüketim!
🔹 Soğutma Modu: %{cooling_pct:.0f} | Isıtma Modu: %{heating_pct:.0f}
🔹 Toplam Tüketim Değişimi: {consumption_change:+.1f}%
🔹 Eşzamanlı gün sayısı: {simul_days} gün

Aynı anda hem ısıtma hem soğutma yapılıyor ve tüketim artmış!
Bu çok ciddi enerji israfı demektir.

ÖNERİ:
1. Dead-band ayarlarını kontrol edin (min 3°C aralık olmalı)
2. Oda termostatlarını kalibre edin
3. BMS set değerlerini gözden geçirin
4. Mevsim geçişlerinde kontrol stratejisi uygulayın""",
                savings_potential="15-25%",
                category="COMBINED"
            ),
            
            # 10. SAT Optimizasyonu Fırsatı
            SavingsRule(
                rule_id="SAT_OPTIMIZATION",
                name="Üfleme Sıcaklığı (SAT) Optimizasyonu",
                severity="WARNING",
                condition=self._check_sat_optimization,
                message_template="""SAT Optimizasyon Fırsatı Tespit Edildi!
Toplam {sat_issues} adet santralde SAT iyileştirmesi yapılabilir.
Bu santrallerde üfleme sıcaklığı set değerleri optimize edilerek:
1. Isıtmada/Soğutmada aşırı tüketim önlenebilir
2. Konfor artırılabilir
3. Enerji tasarrufu sağlanabilir

ÖNERİ: HVAC Analiz sayfasındaki "Recommended SAT" değerlerini uygulayın.
Potansiyel tasarruf: %5-15 (sistem verimliliğine bağlı)""",
                savings_potential="5-15%",
                category="HVAC"
            ),
            
            # ========== YENİ GELİŞMİŞ KURALLAR (11-16) ==========
            
            # 11. Dış Hava vs Chiller Set Korelasyonu (Dinamik Tablo)
            SavingsRule(
                rule_id="CHILLER_SET_DYNAMIC",
                name="Dinamik Chiller Set Optimizasyonu",
                severity="INFO",
                condition=self._check_chiller_set_dynamic,
                message_template="""{dynamic_message}""",
                savings_potential="3-5%",
                category="CHILLER"
            ),
            
            # 12. VRF/Split Bypass Tespiti
            SavingsRule(
                rule_id="VRF_BYPASS_DETECTED",
                name="VRF/Split Merkezi Sistemi Bypass Ediyor",
                severity="CRITICAL",
                condition=self._check_vrf_bypass,
                message_template="""Kritik Enerji Kaçağı Tespit Edildi!
📊 VRF/Split Tüketimi: {vrf_consumption:,.0f} kWh (Geçen yıla göre {vrf_change:+.1f}%)
🏭 Chiller Tüketimi: {chiller_consumption:,.0f} kWh

VRF/Split sistemler merkezi soğutmayı bypass ediyor olabilir!
Bu durum hem enerji israfına hem de konfor dengesizliğine yol açar.

ÖNERİ:
1. Sahada açık kalan split klimaları tespit edin
2. VRF/Split kullanım politikası belirleyin
3. Merkezi sistem yeterliliğini kontrol edin
4. İzinsiz split klima montajını engelleyin""",
                savings_potential="10-20%",
                category="ENERGY"
            ),
            
            # 13. Free Cooling Potansiyeli
            SavingsRule(
                rule_id="FREE_COOLING_POTENTIAL",
                name="Free Cooling Fırsatı",
                severity="WARNING",
                condition=self._check_free_cooling_potential,
                message_template="""Ücretsiz Soğutma Fırsatı Kaçırılıyor!
🌡️ Ortalama Dış Hava: {outdoor_temp:.1f}°C
❄️ Soğutma Modunda Santral: %{cooling_pct:.0f}

Dış hava yeterince serin ama mekanik soğutma kullanılıyor!
Free cooling ile Chiller'lar kapatılıp dış hava ile soğutma yapılabilir.

ÖNERİ:
1. Ekonomizer damperlerini kontrol edin
2. Free cooling set noktalarını gözden geçirin
3. Dış hava <15°C'de mekanik soğutmayı kapatın
4. Geçiş mevsimi kontrol stratejisi uygulayın""",
                savings_potential="15-30%",
                category="COMBINED"
            ),
            
            # 14. Enerji Verimlilik İndeksi Düşüşü
            SavingsRule(
                rule_id="EFFICIENCY_INDEX_DROP",
                name="Enerji Verimlilik İndeksi Düşmüş",
                severity="WARNING",
                condition=self._check_efficiency_index,
                message_template="""⚠️ Verimlilik Kaybı Tespit Edildi!

📊 Karşılaştırma: Aynı dış hava koşullarında enerji tüketimi geçen yıla göre %{index_change:.0f} daha fazla!
(Bu yıl: {current_index:,.0f} kWh/°C | Geçen yıl: {previous_index:,.0f} kWh/°C)

🔍 OLASI SEBEPLER VE ÖNERİLER:
{dynamic_advice}""",
                savings_potential="5-10%",
                category="ENERGY"
            ),
            
            # 15. MAS Santral Sıcaklık Dengesizliği
            SavingsRule(
                rule_id="MAS_IMBALANCE",
                name="Merkez Santral Sıcaklık Dengesizliği",
                severity="INFO",
                condition=self._check_mas_imbalance,
                message_template="""Santral Sıcaklık Dengesizliği Tespit Edildi!
🏭 MAS1 Ortalama: {mas1_temp:.1f}°C
🏭 MAS2 Ortalama: {mas2_temp:.1f}°C
📏 Fark: {temp_diff:.1f}°C

Santraller arasında dengesiz yük dağılımı var.
Bu, bir santralin fazla çalışmasına ve enerji israfına neden olur.

ÖNERİ:
1. Yük dağılım ayarlarını kontrol edin
2. Boru hattı balansını gözden geçirin
3. Santral kapasitelerini eşitleyin""",
                savings_potential="3-5%",
                category="HVAC"
            ),
            
            # 16. Su Tüketim Anomalisi
            SavingsRule(
                rule_id="WATER_CONSUMPTION_ANOMALY",
                name="Su Tüketim Anomalisi",
                severity="CRITICAL",
                condition=self._check_water_anomaly,
                message_template="""Su Tüketiminde Anormal Artış!
💧 Su Tüketimi: {water_consumption:,.0f} m³ (Geçen yıla göre {water_change:+.1f}%)
❄️ Soğutma Tüketimi Değişimi: {cooling_change:+.1f}%

Su tüketimi artmış ama soğutma tüketimi aynı/azalmış!
Bu cooling tower verimsizliği veya su kaçağı olabilir.

ÖNERİ:
1. Cooling tower blowdown oranını kontrol edin
2. Su kaçağı tespiti yapın
3. Makeup water hattını inceleyin
4. Su kalitesini kontrol edin (scaling/fouling)""",
                savings_potential="5-10%",
                category="ENERGY"
            ),
        ]
        
        return rules
    
    # ========== KURAL KOŞULLARI ==========
    
    def _check_chiller_set_low(self, unified_data: Dict, yoy_data: Dict) -> Optional[Dict]:
        """Chiller set sıcaklığı düşük mü?"""
        comparisons = yoy_data.get("comparisons", {})
        chiller_cmp = comparisons.get("avg_chiller_set_temp", {})
        
        cur = chiller_cmp.get("current")
        prev = chiller_cmp.get("previous")
        
        if cur is None or prev is None:
            return None
        
        # Geçen yıldan düşükse
        if cur < prev - 0.3:  # En az 0.3°C düşük
            return {
                "cur_chiller_set": cur,
                "prev_chiller_set": prev,
                "difference": prev - cur
            }
        
        return None
    
    def _check_mcc_spike(self, unified_data: Dict, yoy_data: Dict) -> Optional[Dict]:
        """MCC tüketiminde spike var mı?"""
        comparisons = yoy_data.get("comparisons", {})
        mcc_cmp = comparisons.get("total_mcc_consumption", {})
        
        cur = mcc_cmp.get("current")
        prev = mcc_cmp.get("previous")
        change_pct = mcc_cmp.get("change_percent")
        
        if cur is None or prev is None or change_pct is None:
            return None
        
        # %50'den fazla artış
        if change_pct > 50:
            return {
                "cur_mcc": cur,
                "prev_mcc": prev,
                "change_pct": change_pct
            }
        
        return None
    
    def _check_simultaneous_heat_cool(self, unified_data: Dict, yoy_data: Dict) -> Optional[Dict]:
        """Eş zamanlı ısıtma-soğutma var mı?"""
        summary = unified_data.get("summary", {})
        
        cooling_pct = summary.get("cooling_mode_percentage", 0)
        heating_pct = summary.get("heating_mode_percentage", 0)
        
        # İkisi de %30'dan fazlaysa
        if cooling_pct > 30 and heating_pct > 30:
            return {
                "cooling_pct": cooling_pct,
                "heating_pct": heating_pct
            }
        
        return None
    
    def _check_low_delta_t(self, unified_data: Dict, yoy_data: Dict) -> Optional[Dict]:
        """Su ΔT (gidiş-dönüş su sıcaklığı farkı) düşük mü?"""
        summary = unified_data.get("summary", {})
        avg_delta_t = summary.get("avg_delta_t")
        
        if avg_delta_t is None:
            return None
        
        # 3°C'den düşükse
        if avg_delta_t < 3.0:
            return {
                "avg_delta_t": avg_delta_t
            }
        
        return None
    
    def _check_high_critical_count(self, unified_data: Dict, yoy_data: Dict) -> Optional[Dict]:
        """Kritik sorun sayısı yüksek mi?"""
        current_summary = yoy_data.get("current_summary", {})
        previous_summary = yoy_data.get("previous_summary", {})
        
        cur_critical = current_summary.get("total_critical_issues", 0)
        prev_critical = previous_summary.get("total_critical_issues", 0)
        
        # 10'dan fazla kritik sorun varsa
        if cur_critical > 10:
            if cur_critical > prev_critical:
                change_text = f"{cur_critical - prev_critical} adet artış var"
            elif cur_critical < prev_critical:
                change_text = f"{prev_critical - cur_critical} adet azalma var"
            else:
                change_text = "değişiklik yok"
            
            return {
                "critical_count": cur_critical,
                "change_text": change_text
            }
        
        return None
    
    def _check_total_consumption_increase(self, unified_data: Dict, yoy_data: Dict) -> Optional[Dict]:
        """Toplam tüketim arttı mı?"""
        comparisons = yoy_data.get("comparisons", {})
        total_cmp = comparisons.get("total_hospital_consumption", {})
        
        cur = total_cmp.get("current")
        prev = total_cmp.get("previous")
        change_pct = total_cmp.get("change_percent")
        
        if cur is None or prev is None or change_pct is None:
            return None
        
        # %10'dan fazla artış
        if change_pct > 10:
            return {
                "cur_total": cur,
                "prev_total": prev,
                "change_pct": change_pct
            }
        
        return None
    
    # ========== AKILLI HARMANLAMA KOŞULLARI (HVAC + ENERJİ) ==========
    
    def _check_chiller_high_delta_low(self, unified_data: Dict, yoy_data: Dict) -> Optional[Dict]:
        """Chiller tüketimi yüksek + Su ΔT düşük = Pompa/Vana sorunu"""
        summary = unified_data.get("summary", {})
        comparisons = yoy_data.get("comparisons", {})
        
        # HVAC ΔT verisi
        avg_delta_t = summary.get("hvac_avg_delta_t") or summary.get("avg_delta_t")
        
        # Chiller tüketim karşılaştırması
        chiller_cmp = comparisons.get("total_cooling_consumption", {})
        chiller_change = chiller_cmp.get("change_percent")
        chiller_consumption = chiller_cmp.get("current")
        
        if avg_delta_t is None or chiller_change is None or chiller_consumption is None:
            return None
        
        # ΔT düşük VE Chiller tüketimi artmış
        if avg_delta_t < 4.0 and chiller_change > 10:
            return {
                "avg_delta_t": avg_delta_t,
                "chiller_consumption": chiller_consumption,
                "chiller_change": chiller_change
            }
        
        return None
    
    def _check_chiller_set_vs_consumption(self, unified_data: Dict, yoy_data: Dict) -> Optional[Dict]:
        """Chiller set düşük + soğutma tüketimi yüksek"""
        comparisons = yoy_data.get("comparisons", {})
        
        # Chiller set karşılaştırması
        chiller_set_cmp = comparisons.get("avg_chiller_set_temp", {})
        cur_set = chiller_set_cmp.get("current")
        prev_set = chiller_set_cmp.get("previous")
        
        # Soğutma tüketimi karşılaştırması
        consumption_cmp = comparisons.get("total_cooling_consumption", {})
        consumption_change = consumption_cmp.get("change_percent")
        cur_consumption = consumption_cmp.get("current")
        
        if cur_set is None or prev_set is None or consumption_change is None:
            return None
        
        # Set düşük VE tüketim artmış
        if cur_set < prev_set - 0.3 and consumption_change > 5:
            # Tahminî tasarruf hesapla (1°C = %4 kabul edilir)
            set_difference = prev_set - cur_set
            estimated_savings = (cur_consumption or 0) * (set_difference * 0.04)
            
            return {
                "cur_chiller_set": cur_set,
                "prev_chiller_set": prev_set,
                "consumption_change": consumption_change,
                "estimated_savings": estimated_savings
            }
        
        return None
    
    def _check_simul_with_high_consumption(self, unified_data: Dict, yoy_data: Dict) -> Optional[Dict]:
        """Eşzamanlı ısıtma-soğutma + yüksek tüketim"""
        summary = unified_data.get("summary", {})
        comparisons = yoy_data.get("comparisons", {})
        
        # HVAC modları (history veya standart)
        cooling_pct = summary.get("hvac_avg_cooling_pct") or summary.get("cooling_mode_percentage", 0)
        heating_pct = summary.get("hvac_avg_heating_pct") or summary.get("heating_mode_percentage", 0)
        simul_days = summary.get("hvac_simul_heat_cool_days", 0)
        
        # Tüketim değişimi
        consumption_cmp = comparisons.get("total_hospital_consumption", {})
        consumption_change = consumption_cmp.get("change_percent", 0)
        
        # Hem ısıtma hem soğutma yüksek VE tüketim artmış
        if cooling_pct > 30 and heating_pct > 30 and consumption_change > 5:
            return {
                "cooling_pct": cooling_pct,
                "heating_pct": heating_pct,
                "consumption_change": consumption_change,
                "simul_days": simul_days
            }
        
        return None
    
    def _check_sat_optimization(self, unified_data: Dict, yoy_data: Dict) -> Optional[Dict]:
        """SAT sorunları var mı?"""
        summary = unified_data.get("summary", {})
        # hvac_history.py'den gelen sat_issues_total veya SAT_Sorun_Adet
        sat_issues = summary.get("sat_issues_total", 0) or summary.get("SAT_Sorun_Adet", 0)
        
        if sat_issues > 0:
            return {
                "sat_issues": sat_issues
            }
        
        return None
    
    # ========== YENİ GELİŞMİŞ KURAL FONKSİYONLARI (11-16) ==========
    
    def _check_chiller_set_dynamic(self, unified_data: Dict, yoy_data: Dict) -> Optional[Dict]:
        """
        Dış hava bazlı dinamik Chiller set optimizasyonu.
        
        Dinamik Tablo:
        | Dış Hava      | Önerilen Set | Not                                    |
        |--------------|--------------|----------------------------------------|
        | <5°C         | 8°C          | Kapasite %40 altına düşürme             |
        | 5-15°C       | 7.5°C        | -                                      |
        | 16-25°C      | 7°C          | -                                      |
        | >25°C        | 6.5°C        | Kapasite %85 üzerine çıkarma            |
        """
        summary = unified_data.get("summary", {})
        
        outdoor_temp = summary.get("avg_outdoor_temp")
        chiller_set = summary.get("avg_chiller_set_temp")
        
        if outdoor_temp is None or chiller_set is None:
            return None
        
        # Dinamik tablo: Dış hava aralığına göre önerilen set sıcaklığı
        if outdoor_temp < 5:
            recommended_set = 8.0
            capacity_note = " (NOT: Chiller kapasitesini %40 altına düşürmeyin!)"
        elif 5 <= outdoor_temp <= 15:
            recommended_set = 7.5
            capacity_note = ""
        elif 16 <= outdoor_temp <= 25:
            recommended_set = 7.0
            capacity_note = ""
        else:  # >25°C
            recommended_set = 6.5
            capacity_note = " (NOT: Chiller kapasitesini %85 üzerine çıkarmayın!)"
        
        # Mevcut set önerilen set'e yakın mı kontrol et (±0.5°C tolerans)
        if abs(chiller_set - recommended_set) <= 0.5:
            return None  # Zaten optimal
        
        # Öneri mesajı oluştur
        if chiller_set < recommended_set:
            action = "yükseltebilirsiniz"
            benefit = "enerji tasarrufu"
        else:
            action = "düşürebilirsiniz"
            benefit = "soğutma kapasitesi artışı"
        
        dynamic_message = f"""Dış Hava Bazlı Chiller Set Optimizasyonu!
🌡️ Ortalama Dış Hava: {outdoor_temp:.1f}°C
❄️ Mevcut Chiller Set: {chiller_set:.1f}°C
✅ Önerilen Chiller Set: {recommended_set:.1f}°C{capacity_note}

Dış hava sıcaklığına göre set sıcaklığını {recommended_set:.1f}°C'ye {action}.
Her 1°C değişim yaklaşık %3-5 {benefit} sağlar.

📊 Dış Hava - Set Sıcaklığı Tablosu:
• <5°C → 8°C (Kapasite: min %40)
• 5-15°C → 7.5°C
• 16-25°C → 7°C  
• >25°C → 6.5°C (Kapasite: max %85)

ÖNERİ: Konfor şikayetlerini izleyerek kademeli geçiş yapın."""
        
        return {
            "dynamic_message": dynamic_message,
            "outdoor_temp": outdoor_temp,
            "chiller_set": chiller_set,
            "recommended_set": recommended_set
        }
    
    def _check_vrf_bypass(self, unified_data: Dict, yoy_data: Dict) -> Optional[Dict]:
        """VRF/Split merkezi sistemi bypass ediyor mu?"""
        summary = unified_data.get("summary", {})
        comparisons = yoy_data.get("comparisons", {})
        
        # VRF tüketimi
        vrf_consumption = summary.get("total_vrf_consumption", 0)
        chiller_consumption = summary.get("total_chiller_consumption", 0)
        
        # VRF değişimi (YoY)
        vrf_cmp = comparisons.get("total_vrf_consumption", {})
        vrf_change = vrf_cmp.get("change_percent")
        
        if vrf_consumption is None or vrf_consumption == 0:
            return None
        
        # VRF %15+ artmış VE Chiller hala çalışıyor
        if vrf_change is not None and vrf_change > 15 and chiller_consumption > 0:
            return {
                "vrf_consumption": vrf_consumption,
                "vrf_change": vrf_change,
                "chiller_consumption": chiller_consumption
            }
        
        return None
    
    def _check_free_cooling_potential(self, unified_data: Dict, yoy_data: Dict) -> Optional[Dict]:
        """Free cooling potansiyeli var mı?"""
        summary = unified_data.get("summary", {})
        
        outdoor_temp = summary.get("avg_outdoor_temp")
        cooling_pct = summary.get("hvac_avg_cooling_pct") or summary.get("cooling_mode_percentage", 0)
        
        if outdoor_temp is None:
            return None
        
        # Dış hava düşük (<15°C) ama soğutma hala aktif (>%30)
        if outdoor_temp < 15 and cooling_pct > 30:
            return {
                "outdoor_temp": outdoor_temp,
                "cooling_pct": cooling_pct
            }
        
        return None
    
    def _check_efficiency_index(self, unified_data: Dict, yoy_data: Dict) -> Optional[Dict]:
        """Enerji verimlilik indeksi düşmüş mü? Dinamik öneriler üretir."""
        current_summary = unified_data.get("summary", {})
        previous_summary = yoy_data.get("previous_summary", {})
        
        current_index = current_summary.get("efficiency_index")
        previous_index = previous_summary.get("efficiency_index")
        
        if current_index is None or previous_index is None or previous_index == 0:
            return None
        
        # Verimlilik indeksi %10+ artmış (daha fazla kWh/°C = daha verimsiz)
        index_change = ((current_index - previous_index) / previous_index) * 100
        
        if index_change > 10:
            # Dinamik öneri oluşturma
            advice_list = []
            
            # Kritik sorun sayısına bak
            critical_count = current_summary.get("total_critical_issues", 0) or 0
            if critical_count > 5:
                advice_list.append(f"🔴 HVAC analizinde {critical_count} kritik sorun var. Öncelikle bunları giderin (vana/sensör arızaları).")
            
            # Chiller set değişimine bak
            cur_chiller = current_summary.get("avg_chiller_set_temp")
            prev_chiller = previous_summary.get("avg_chiller_set_temp")
            if cur_chiller and prev_chiller and (cur_chiller < prev_chiller - 0.5):
                diff = prev_chiller - cur_chiller
                advice_list.append(f"❄️ Chiller set değeri geçen yıla göre {diff:.1f}°C düşük ({cur_chiller:.1f}°C vs {prev_chiller:.1f}°C). Yükseltmeyi deneyin.")
            
            # Hastane tüketim artışına bak
            cur_hosp = current_summary.get("total_hospital_consumption", 0) or 0
            prev_hosp = previous_summary.get("total_hospital_consumption", 0) or 0
            if prev_hosp > 0:
                hosp_change = ((cur_hosp - prev_hosp) / prev_hosp) * 100
                if hosp_change > 15:
                    advice_list.append(f"📈 Hastane genel tüketimi %{hosp_change:.0f} artmış. Binadaki cihaz yükü veya doluluk artmış olabilir.")
            
            # Eğer hiçbir özel sebep bulunamadıysa genel öneri
            if not advice_list:
                advice_list.append("🔧 Sistemde genel verimlilik kaybı var.")
                advice_list.append("⚙️ Pompa basınç farkı set değerlerini ve sürücü frekanslarını kontrol edin.")
                advice_list.append("🌡️ Sistem gidiş suyu set değerlerini optimize edin.")
            
            dynamic_advice = "\n".join(advice_list)
            
            return {
                "current_index": current_index,
                "previous_index": previous_index,
                "index_change": index_change,
                "dynamic_advice": dynamic_advice
            }
        
        return None
    
    def _check_mas_imbalance(self, unified_data: Dict, yoy_data: Dict) -> Optional[Dict]:
        """MAS santral sıcaklık dengesizliği var mı?"""
        summary = unified_data.get("summary", {})
        
        # Önce soğutma modunu kontrol et
        mas1_cooling = summary.get("avg_mas1_cooling_temp")
        mas2_cooling = summary.get("avg_mas2_cooling_temp")
        
        # Sonra ısıtma modunu kontrol et
        mas1_heating = summary.get("avg_mas1_heating_temp")
        mas2_heating = summary.get("avg_mas2_heating_temp")
        
        # Soğutma modunda dengesizlik
        if mas1_cooling is not None and mas2_cooling is not None:
            temp_diff = abs(mas1_cooling - mas2_cooling)
            if temp_diff > 5:  # 5°C'den fazla fark
                return {
                    "mas1_temp": mas1_cooling,
                    "mas2_temp": mas2_cooling,
                    "temp_diff": temp_diff
                }
        
        # Isıtma modunda dengesizlik
        if mas1_heating is not None and mas2_heating is not None:
            temp_diff = abs(mas1_heating - mas2_heating)
            if temp_diff > 5:  # 5°C'den fazla fark
                return {
                    "mas1_temp": mas1_heating,
                    "mas2_temp": mas2_heating,
                    "temp_diff": temp_diff
                }
        
        return None
    
    def _check_water_anomaly(self, unified_data: Dict, yoy_data: Dict) -> Optional[Dict]:
        """Su tüketim anomalisi var mı?"""
        summary = unified_data.get("summary", {})
        comparisons = yoy_data.get("comparisons", {})
        
        # Su tüketimi
        water_consumption = summary.get("total_water_consumption", 0)
        
        # Su ve soğutma değişimi (YoY)
        water_cmp = comparisons.get("total_water_consumption", {})
        cooling_cmp = comparisons.get("total_cooling_consumption", {})
        
        water_change = water_cmp.get("change_percent")
        cooling_change = cooling_cmp.get("change_percent", 0) or 0
        
        if water_consumption is None or water_consumption == 0 or water_change is None:
            return None
        
        # Su %20+ artmış AMA soğutma %5'ten az değişmiş
        if water_change > 20 and abs(cooling_change) < 5:
            return {
                "water_consumption": water_consumption,
                "water_change": water_change,
                "cooling_change": cooling_change
            }
        
        return None

    # ========== ANA FONKSİYONLAR ==========
    
    def generate_recommendations(self, unified_data: Dict, yoy_data: Dict) -> List[Dict]:
        """
        Tüm kuralları uygulayarak tasarruf önerileri üret.
        """
        recommendations = []
        
        for rule in self.rules:
            try:
                result = rule.condition(unified_data, yoy_data)
                
                if result is not None:
                    # Kural tetiklendi
                    message = rule.message_template.format(**result)
                    
                    recommendations.append({
                        "rule_id": rule.rule_id,
                        "name": rule.name,
                        "severity": rule.severity,
                        "category": rule.category,
                        "message": message,
                        "savings_potential": rule.savings_potential,
                        "data": result,
                        "timestamp": datetime.now().isoformat()
                    })
            except Exception as e:
                print(f"Kural {rule.rule_id} hatası: {e}")
                continue
        
        # Severity'ye göre sırala (CRITICAL > WARNING > INFO)
        severity_order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
        recommendations.sort(key=lambda x: severity_order.get(x["severity"], 3))
        
        # ========== ML TRAINING DATA KAYDETME ==========
        # Her öneri için bağlam verilerini kaydet (Faz 2 hazırlığı)
        if recommendations:
            try:
                from .training_data import TrainingDataCollector
                collector = TrainingDataCollector()
                
                summary = unified_data.get("summary", {})
                
                # Enerji ve HVAC verilerini ayrıştır
                energy_keys = {"total_hospital_consumption", "total_grid_consumption", 
                              "total_cooling_consumption", "total_vrf_consumption",
                              "total_water_consumption", "total_gas_m3",
                              "avg_outdoor_temp", "avg_chiller_set_temp", "efficiency_index"}
                hvac_keys = {"hvac_avg_delta_t", "hvac_avg_cooling_pct", "hvac_avg_heating_pct",
                            "total_critical_issues", "sat_issues_total",
                            "hvac_simul_heat_cool_days", "cooling_mode_percentage", "heating_mode_percentage"}
                
                energy_summary = {k: v for k, v in summary.items() if k in energy_keys}
                hvac_summary = {k: v for k, v in summary.items() if k in hvac_keys}
                
                for rec in recommendations:
                    collector.save_recommendation_context(
                        recommendation=rec,
                        energy_summary=energy_summary,
                        hvac_summary=hvac_summary,
                        yoy_data=yoy_data
                    )
                
                print(f"ML Training: {len(recommendations)} oneri kaydedildi")
            except Exception as e:
                print(f"Training data kaydetme hatasi: {e}")
        
        return recommendations
    
    def learn_from_outcome(self, recommendation_id: str, outcome: str, 
                           actual_savings: Optional[float] = None):
        """
        Öneri sonuçlarından öğren (feedback loop).
        
        Args:
            recommendation_id: Öneri ID'si
            outcome: "applied", "ignored", "partially_applied"
            actual_savings: Gerçekleşen tasarruf yüzdesi
        """
        self.training_data.append({
            "recommendation_id": recommendation_id,
            "outcome": outcome,
            "actual_savings": actual_savings,
            "timestamp": datetime.now().isoformat()
        })
        
        self._save_training_data()
    
    def get_recommendation_summary(self, recommendations: List[Dict]) -> Dict:
        """Önerilerin özet istatistikleri"""
        if not recommendations:
            return {
                "total_count": 0,
                "critical_count": 0,
                "warning_count": 0,
                "info_count": 0,
                "total_potential_savings": "0%"
            }
        
        critical = sum(1 for r in recommendations if r["severity"] == "CRITICAL")
        warning = sum(1 for r in recommendations if r["severity"] == "WARNING")
        info = sum(1 for r in recommendations if r["severity"] == "INFO")
        
        # Potansiyel tasarruf hesaplama (tahmini)
        # Gerçek hesaplama için daha detaylı analiz gerekir
        total_potential = 0
        for r in recommendations:
            potential = r.get("savings_potential", "0%")
            # "5-10%" formatını parse et
            if "-" in potential:
                low, high = potential.replace("%", "").split("-")
                total_potential += (float(low) + float(high)) / 2
            elif potential.endswith("%"):
                total_potential += float(potential.replace("%", ""))
        
        return {
            "total_count": len(recommendations),
            "critical_count": critical,
            "warning_count": warning,
            "info_count": info,
            "total_potential_savings": f"{total_potential:.0f}%"
        }
