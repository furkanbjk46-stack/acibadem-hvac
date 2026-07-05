# SYNAPSE / SYNERGY — Kapsamlı Sistem Denetim Raporu
**Tarih:** 05.07.2026 · **Kapsam:** 39 Python dosyası, ~25.100 satır (tüm repo)
**Yöntem:** Statik denetim (satır satır) + **çalıştırmalı sentetik senaryo testleri** (D: geri bağlandıktan sonra koşuldu)

---

## 0. Test Yöntemi ve Çalıştırmalı Sonuçlar

1. **Syntax taraması:** 39/39 dosya temiz ✓ (Python 3.13.6)
2. **Mekanik Zeka kural motoru:** 33 sentetik senaryo koşuldu → 26 PASS.
   FAIL'lerin tamamı ya statik bulguları **doğruladı** (MZ-1, MZ-2) ya da **yeni hata** ortaya
   çıkardı (MZ-6) ya da doküman-config uyumsuzluğuydu (MZ-8). Doğru çalışanlar:
   ΔT yönleri, hava ΔT, OAT bias, STANDBY (OFF + AUTO/kapalı vana), SIMUL_HEAT_COOL,
   NOT_COOLING/NOT_HEATING (%70 eşiği), SAT_WARNING (%40-69), AIR_DT_LOW_COOL,
   CHILLER_BYPASS/LOW_DT, LOW_FLOW (FCU'da tetikleniyor / AHU'da tetiklenmiyor ✓),
   LOW_DT_SYNDROME (soğutma), COMFORT_OVERRIDE, FCU IN_BAND, AUTO mod çözümleme,
   map_severity eşikleri.
3. **Enerji recalc:** 5 senaryo → 4 PASS; S4 FAIL'i **E-1 bulgusunu doğruladı** (aşağıda).
4. **data_bridge:** 10/10 PASS (günlük fark, sayaç sıfırlama→0, aşırı fark→0, ilk çalıştırma,
   stale referans, safe_sum, şebeke fallback, MCC/Chiller ayrımı).
5. **forecast_engine.calculate_savings:** sentetik 2 tam yıl + yarım yıl → **MR-1 doğrulandı**:
   günlük tüketim hiç değişmediği hâlde "%50,8 tasarruf" raporladı ve önceki yıl olarak
   2025 yerine **2024**'ü seçti (aşağıda).

> ⚠️ **Operasyonel risk (denetimde bizzat yaşandı):** Python kurulumu `D:\Program Files (x86)\`
> yolunda; D: koptuğunda collector/portal/bridge dahil her şey durur. C:'ye taşınmalı (Ö-1).

---

## 1. Mekanik Zeka (main_portal.py) — Kural Motoru Denetimi

Denetlenen fonksiyonlar: `calculate_delta_t`, `calculate_air_delta_t`, `get_target_delta_t`,
`analyze_sat_status`, `calculate_recommended_sat`, `calculate_approach`, `calculate_departure`,
`check_special_conditions`, `calculate_score`, `map_severity`, `determine_effective_mode`,
`analyze_equipment`, `_analyze_base`, `analyze_ahu_performance`, `analyze_fcu_performance`.

### ✅ Doğru bulunanlar
- Su ΔT yönü: soğutmada `outlet-inlet`, ısıtmada `inlet-outlet`, negatifse mutlak değer ✓
- AHU'da ana metrik hava ΔT'si (SAT-Return); su ΔT sadece merkezi ekipmanda ✓
- OAT bias: ≤15°C → -2, ≥25°C → +2, arada lineer `(oat-20)/5*2` ✓
- STANDBY mantığı (OFF modları + AUTO/vanalar<0.5) ve SKIP tipleri ✓
- AUTO mod çözümleme öncelik zinciri (vana → SAT/Return → OAT → UNKNOWN) ✓
- İki aşamalı vana eşiği (%40 giriş / %70 kritik) NOT_COOLING/NOT_HEATING için ✓
- LOW_FLOW_DETECTED'in AHU'dan çıkarılması ✓ (önceki düzeltme yerinde)
- rule_boosts tablosu INSTRUCTION_GUIDE ile hizalı ✓ (M1–M6 düzeltmeleri yerinde)
- FCU yolunda severity → `map_severity` + BAND/IN_BAND override ✓

### ❌ BULGU MZ-1 (ORTA-YÜKSEK, **testle doğrulandı**) — AHU yolunda severity ataması eksik
**Test kanıtı:** AHU LOW_DT senaryosu → `rule=LOW_DT, score=6.0, severity=OPTIMAL` (WARNING olmalı);
AHU MISSING_DATA → `score=5.0, severity=OPTIMAL` (CRITICAL olmalı).
`analyze_ahu_performance` fonksiyonunun **sonunda `map_severity` çağrılmıyor**
(FCU yolunda satır ~2086'da var). Sonuç: SAT ve özel-kural dallarına girmeyen AHU satırlarında
`severity` varsayılan **"OPTIMAL"** kalıyor:
- AHU + `LOW_DT` / `HIGH_DT` (bant ihlali, skor 4–5) → **OPTIMAL görünüyor** (doküman: WARNING)
- AHU + `MISSING_DATA` (skor 5) → **OPTIMAL görünüyor** (map_severity'e göre CRITICAL olmalı)

**Düzeltme:** AHU yolunun sonunda, severity hâlâ varsayılandaysa
`result.severity = map_severity(result.status, result.score)` uygula
(SAT/özel kural atamalarını ezmeden).

### ❌ BULGU MZ-2 (ORTA, **testle doğrulandı**) — LOW_DT_SYNDROME sadece soğutma vanasına bakıyor
`check_special_conditions` (~satır 1527): kural yalnızca `valves.cooling >= %90` kontrol ediyor.
**Test kanıtı:** FCU ısıtma, heat valve %95, su ΔT 2.0 → `LOW_DT_SYNDROME` yerine `BAND_LOW` döndü.
Doküman "İlgili Valve ≥ %90" diyor.
**Düzeltme:** `max(cool_v, heat_v) >= HIGH_VALVE_THRESHOLD` veya moda göre ilgili vana.

### ❌ BULGU MZ-6 (ORTA, **YENİ — testte keşfedildi**) — INSUFFICIENT_CAPACITY eziliyor
`analyze_fcu_performance`: comfort kontrolü `INSUFFICIENT_CAPACITY` kuralını atadıktan sonra,
özel kural YOKSA çalışan "Standard Recommendations" `else` bloğu kuralı **`IN_BAND`/`BAND_*` ile
eziyor**. Test kanıtı: FCU oda 24.5/set 22 (sapma 2.5), vana %90, ΔT bantta →
`rule=IN_BAND, score=6.0` (INSUFFICIENT_CAPACITY olmalıydı) ve IN_BAND override'ı severity'yi
OPTIMAL'e çekiyor. **Düzeltme:** Standard Recommendations bloğu yalnızca `result.rule` boşken çalışmalı.

### 📄 BULGU MZ-8 (DOKÜMAN/CONFIG UYUMSUZLUĞU — testte keşfedildi)
Çalışan config değerleri dokümandan farklı:
| Parametre | Doküman | Çalışan config |
|---|---|---|
| TARGET_DT_HEAT | 15.0°C | **25** |
| HEAT_SAT_LOW_THRESHOLD | 27.0°C | **28.0** |
| AHU hava ΔT hedefi (cool/heat) | (dokümanda su ΔT 5.0 anlatılıyor) | **10.0 / 10.0** |
Davranış tutarlı çalışıyor; ancak LOW_FLOW_DETECTED artık ΔT≥25 gerektiriyor → ΔT 15-24 arası
düşük-debi durumları yakalanmaz. Eşik bilinçli yükseltildiyse doküman güncellenmeli;
değilse config gözden geçirilmeli.

### ⚠️ BULGU MZ-3 (DÜŞÜK) — Kural öncelik sırası skor sırasıyla çelişiyor
`check_special_conditions` içinde **COMFORT_OVERRIDE (skor 4)** ikinci sırada kontrol edilip
erken `return` yapıyor; sonrasında gelecek **LOW_FLOW_DETECTED (8)**, **CHILLER_BYPASS (9)**,
**HEAT/COOL_EFF_LOW (7)** maskelenebiliyor. Örnek: FCU'da oda-set sapması 3.5°C iken aynı anda
su ΔT + SAT düşük-debi tablosu varsa rapora yalnız COMFORT_OVERRIDE düşer.
**Öneri:** Özel kuralları skor sırasına göre değerlendir (en ağır kural kazanır).

### ⚠️ BULGU MZ-4 (KOZMETİK) — 0.0 değeri falsy tuzağı
`sat = temperatures.sat or temperatures.supply` kalıbı: SAT tam **0.0°C** ise (donma koşulu)
supply'a düşer. `is not None` kullanılması daha güvenli. (Aynı kalıp determine_effective_mode'da da var.)

### 📄 BULGU MZ-5 (DOKÜMAN) — Skor ağırlığı uyumsuzluğu
Kod: `score += min(abs(departure) * 2.0, 6.0)` — doküman (kural_parametreleri, df6):
`SCORE_DEPARTURE_WEIGHT = 1.5`. Kod 2.0 kullanıyor. Ayrıca dokümandaki
`SCORE_LOW_DT_BONUS +4.0` / `SCORE_COMFORT_PENALTY +2.0` kodda rule_boosts tablanıyla
uygulanıyor (davranış eşdeğer ama doküman güncel değil).

---

## 2. Enerji ve Verimlilik (Synergy — app_portal.py, data_bridge.py, cloud_sync.py)

### ✅ Doğru bulunanlar
- `recalc`: Toplam Soğutma = Chiller + VRF ✓ · Şebeke = TRDP1-4 (2/4 doluysa) yoksa
  TRDP1+3+MCC+Soğutma fallback ✓ · Toplam Hastane = Şebeke + Kojen ✓ · Diğer Yük clip(≥0) ✓
- Enerji Diyagramı toplama mantığı `recalc` ile **tutarlı** (aynı 2/4-dolu kuralı) ✓
- Diyagram %'leri Hastane Genel Toplam üzerinden ✓ (canlı doğrulandı)
- `data_bridge`: günlük fark = bugün-dün, negatif fark→0 (sayaç sıfırlama), >50.000 kWh→0
  (format hatası), stale referans→Modbus alanları boş ✓
- TRDP-1/3 data_collector cihaz listesinde mevcut ✓; MCC = tüm analizörler − Chiller
  (Kule + Siemens MCC dahil) ✓
- Atomik CSV yazımı (tempfile + os.replace) hem portal hem bridge'de ✓
- `cloud_sync`: yerel satır sayısı bulut kayıtlarının yarısından azsa sync iptal (veri
  kaybı koruması) ✓
- `safe_pct_change`, YoY ay karşılaştırma, pay hesapları (%) sıfır-bölme korumalı ✓

### ⚠️ BULGU E-1 (DÜŞÜK, **testle doğrulandı**) — Şebeke bilinmiyorken Kojen toplam dışı kalıyor
`recalc` satır ~1476: şebeke verisi hiç yoksa **Kojen üretimi toplam hastaneye eklenmiyor**.
**Test kanıtı:** Kojen 10.000 + MCC 7.000 + Chiller 5.000 (şebeke boş) → Toplam Hastane
**12.000** çıktı (22.000 olmalı). Nadir senaryo ama toplam eksik görünür.

### ⚠️ BULGU E-2 (KOZMETİK) — data_bridge yorum/saat uyumsuzluğu
Dosya başındaki yorum ve log "08:30" diyor; gerçek `SNAPSHOT_HOUR=7, MINUTE=10` (07:10).

### ⚠️ BULGU E-3 (ÖNERİ) — Kaçırılan gün telafisi yok
`bridge_loop` sadece tam 07:10'da tetikler; PC o dakika kapalıysa **o günün satırı hiç yazılmaz**.
Başlangıçta "dün CSV'de yok + saat > 07:10 ise snapshot çalıştır" telafisi eklenmeli.

### 📄 BULGU E-4 (KOZMETİK) — Yanıltıcı kaleido mesajları
PDF hata mesajları hâlâ "pip install -U kaleido" öneriyor (satır ~2685, 2750, 4112) ama render
matplotlib ile yapılıyor (kaleido kuralı gereği doğru). Mesajlar kafa karıştırıcı, güncellenmeli.

---

## 3. Synapse (merkez/) — GM Merkez Portal

### ✅ Doğru bulunanlar
- Verimlilik metrikleri sıfır-bölme korumalı; şebeke bağımlılığı `sebeke/(sebeke+kojen)` ✓
- kWh/m²/gün = toplam / gün sayısı / m² ✓ · aykırı değer tespiti (≥3 lokasyon, 1.5 std) ✓
- rapor_olustur: grafikler matplotlib (kaleido yok) ✓
- YoY değişim formülleri ✓

### ❌ BULGU SY-1 (ORTA) — Kojen verimi yanlış payda ile hesaplanıyor
`app_merkez.py` satır ~1599 ve ~1769: `kojen_verim = Kojen_kWh / (Kazan_gaz + Kojen_gaz)`.
Kojen verimi tanım gereği **sadece kojenin yaktığı gazla** hesaplanmalı:
`Kojen_kWh / Kojen_Dogalgaz_m3`. Mevcut hâliyle kazan gazı arttıkça (kış) kojen verimi
yapay olarak düşük görünür ve "≥3.5 kWh/m³" hedefiyle karşılaştırma yanıltıcı olur.
Bu değer AI değerlendirme metnine de giriyor → yanlış yorum üretebilir.
**Düzeltme:** paydayı `Kojen_Dogalgaz_m3`'e çevir (iki yerde). "Genel verim" (toplam kWh / toplam gaz)
ayrı metrik olarak kalabilir, o doğru.

---

## 4. Aylık Rapor Motorları (monthly_report/)

### ✅ Doğru bulunanlar
- `yoy_analyzer`: değişim % formülü, previous=0 koruması, anlamlı-değişim sıralaması ✓
- `daily_comparison.calculate_change_percent` ✓ · `data_merger` NaN-güvenli toplamlar ✓
- `ahu_alarm_takip`: Skor/Score sütun uyumluluğu ve >7 filtresi ✓

### ❌ BULGU MR-1 (ORTA-YÜKSEK, **testle doğrulandı**) — Kısmi yıl "tasarruf" hesabı şişiyor
`forecast_engine.calculate_savings`: `full_years` = ≥300 günlük yıllar, ama **karşılaştırılan
`year`'ın full olması şart koşulmuyor**.
**Test kanıtı (sentetik):** 2024 + 2025 tam yıl, 2026 yarım yıl, günlük tüketim üç yılda da
birebir aynı → sonuç: **"%50,8 tasarruf (18.600 kWh)"**. Üstelik `idx=-1 → full_years[-2]`
mantığı yüzünden önceki yıl olarak 2025 değil **2024** seçildi (çifte hata).
**Düzeltme:** `if year not in full_years: return {}` (veya kısmi yılı gün-normalize et) +
prev_year seçimini `full_years`'ta year'dan küçük en büyük yıl olarak düzelt.

### ⚠️ BULGU MR-2 (DÜŞÜK) — 0.0°C dış hava ortalamadan düşüyor
`data_merger._calculate_monthly_summary`: `if d["energy"].get("outdoor_temp")` filtresi
**0.0°C değerini de eliyor** (falsy). Donma günlerinde dış hava ortalaması hafif sapar.
`is not None` kullanılmalı (aynı kalıp MAS sıcaklıkları için de geçerli).

---

## 5. Synergy Ekosistemi — Destek Bileşenleri

| Bileşen | Durum |
|---|---|
| `lisans.py` | ✓ Dev-ortam istisnası (config yoksa geç), makine ID + lokasyon eşleşme, hata mesajları doğru |
| `data_collector.py` | ✓ TRDP-1/3 dahil analizör listesi tam |
| `cloud_sync.py` | ✓ Yarım-CSV koruması, upsert mantığı |
| `location_manager` / güncelleme mekanizması | ✓ Supabase `guncellemeler` akışı (v5.6'ya kadar sorunsuz yayın) |
| `ahu_alarm_takip` | ✓ Skor>7 filtresi ve sayaç dosyaları |
| Bağımlılık kuralları | ✓ kaleido import edilmiyor (yalnız mesaj metinlerinde geçiyor), grafikler matplotlib, PDF fpdf2+DejaVu |

---

## 6. Bulgu Özeti (öncelik sırasıyla)

| # | Bileşen | Bulgu | Önem | Test |
|---|---|---|---|---|
| MZ-1 | Mekanik Zeka | AHU yolunda map_severity çağrılmıyor → LOW_DT/HIGH_DT/MISSING_DATA AHU'lar "OPTIMAL" görünüyor | **ORTA-YÜKSEK** | ✅ doğrulandı |
| MR-1 | Aylık rapor | Kısmi yıl vs tam yıl → "%50,8 sahte tasarruf" + yanlış önceki yıl seçimi | **ORTA-YÜKSEK** | ✅ doğrulandı |
| MZ-6 | Mekanik Zeka | **YENİ:** INSUFFICIENT_CAPACITY, IN_BAND/BAND_* tarafından eziliyor | **ORTA** | ✅ testte keşfedildi |
| SY-1 | Synapse | Kojen verimi toplam gazla bölünüyor (sadece kojen gazı olmalı) — 2 yer | **ORTA** | statik |
| MZ-2 | Mekanik Zeka | LOW_DT_SYNDROME ısıtma vanasını görmüyor | **ORTA** | ✅ doğrulandı |
| MZ-8 | Config/Doküman | TARGET_DT_HEAT çalışan 25 / doküman 15; LOW_FLOW eşiği daralmış | ORTA | ✅ testte keşfedildi |
| MZ-3 | Mekanik Zeka | COMFORT_OVERRIDE (4) daha ağır kuralları (8-9) maskeleyebiliyor | DÜŞÜK | statik |
| E-1 | Enerji | Şebeke boşken Kojen toplam hastane dışı kalıyor (12.000 vs 22.000) | DÜŞÜK | ✅ doğrulandı |
| MR-2 | Aylık rapor | 0.0°C dış hava ortalamadan eleniyor (falsy filtre) | DÜŞÜK | statik |
| MZ-4 | Mekanik Zeka | `sat or supply` 0.0 tuzağı | KOZMETİK | statik |
| MZ-5 | Doküman | Skor ağırlığı kod 2.0 / doküman 1.5 | KOZMETİK | statik |
| E-2 | data_bridge | Yorum "08:30", gerçek 07:10 | KOZMETİK | statik |
| E-4 | PDF | Yanıltıcı "kaleido yükleyin" mesajları | KOZMETİK | statik |

### ✅ Testle temiz çıkanlar
data_bridge (10/10), recalc ana senaryolar (4/5), tüm kritik kurallar (SIMUL, NOT_COOLING/HEATING,
CHILLER_BYPASS/LOW_DT, LOW_FLOW FCU/AHU ayrımı, SAT_WARNING iki aşamalı vana eşiği, STANDBY,
AUTO mod çözümleme, map_severity eşikleri), Enerji Diyagramı toplam/yüzdeleri (canlı doğrulama).

## 7. Öneriler

1. **Ö-1 (KRİTİK-OPERASYONEL):** Python kurulumunu D:'den C:'ye taşı. D: sürücüsü koptuğu an
   collector + bridge + portal + watchdog hepsi durur (bu denetim sırasında bizzat yaşandı).
   Lokasyon PC'lerinde de Python'un sistem diskinde olduğunu doğrula.
2. **Ö-2:** MZ-1 + MZ-2 + MZ-6 + SY-1 + MR-1 düzeltmelerini tek yama olarak uygula (v5.7)
   — beşi de "yanlış hesap/yanlış etiket" sınıfında ve testle kanıtlandı.
3. **Ö-3:** data_bridge'e kaçırılan gün telafisi ekle (E-3) — lokasyon PC yeniden başlarsa
   o günün verisi kaybolmasın.
4. **Ö-4:** ✅ YAPILDI — çalıştırmalı test paketi koşuldu (33 kural senaryosu + 5 recalc +
   10 data_bridge + tasarruf senaryosu). Test scripti scratchpad'de; kalıcı `tests/` klasörüne
   taşınması önerilir (yamalar sonrası regresyon için).
5. **Ö-5:** kural_parametreleri dokümanını çalışan config ile eşitle (MZ-5 skor ağırlığı,
   MZ-8 TARGET_DT_HEAT/HEAT_SAT_LOW/AHU hava hedefleri).
6. **Ö-6:** Enerji Diyagramı topolojisini Altunizade için de tanımla (şu an sadece Maslak;
   diğer lokasyonda sekme bilgi mesajı gösteriyor — tasarım gereği ama kullanıcı beklentisi olabilir).

---
*Denetim: Claude (statik kod denetimi). Çalıştırmalı doğrulama D: sürücüsü döndüğünde önerilir.*
