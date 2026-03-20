---
description: Tolerans değerlerini güncelle (kural ekleme/çıkarma/değiştirme)
---

# Tolerans Değerleri Güncelleme Workflow

Bu workflow "tolerans güncelle", "eşik değiştir", "kural ekle/çıkar" veya benzeri bir istek geldiğinde çalıştırılır.

## Referans Dosyaları

1. **Tolerans Değerleri Belgesi:**
   - `C:\Users\furka\.gemini\antigravity\brain\f0a17b7e-f8f2-4d9c-af71-957a740dbb8a\tolerans_degerleri.md`
   
2. **Config JSON Dosyası:**
   - `c:\Users\furka\Downloads\acibadem_hvac_patch_air_water_split\acıbadem\configs\hvac_settings.json`

3. **Ana Portal Kodu:**
   - `c:\Users\furka\Downloads\acibadem_hvac_patch_air_water_split\acıbadem\main_portal.py`
   - CONFIG dictionary (satır ~37-90)

## Adımlar

### 1. Değişiklik Türünü Belirle
- **Tolerans değişikliği:** JSON config + belge güncelle
- **Kural ekleme:** main_portal.py + INSTRUCTION_GUIDE + index.html INSTRUCTION_DATA
- **Kural çıkarma:** Yukarıdakileri tersine çevir

### 2. Config Dosyasını Güncelle
Dosya: `configs/hvac_settings.json`
```json
{
  "TARGET_DT_AHU": 5.0,
  "SAT_COOLING_MIN": 15.0,
  // ... diğer değerler
}
```

### 3. Tolerans Belgesini Güncelle
Dosya: `tolerans_degerleri.md`
- İlgili tabloyu güncelle
- Tarih damgasını güncelle

### 4. Kod Değişikliği Gerekiyorsa
- `main_portal.py` → CONFIG dictionary
- `main_portal.py` → INSTRUCTION_GUIDE (kural açıklamaları)
- `static/index.html` → INSTRUCTION_DATA (frontend talimatları)

### 5. UI Ayarlar Panelini Kontrol Et
Yeni bir ayar eklendiyse:
- `index.html` → Settings Modal'a input ekle
- JavaScript → `populateSettingsForm` fonksiyonuna key ekle

## Mevcut Tolerans Değerleri Özeti

| Kategori | Parametre | Varsayılan |
|----------|-----------|------------|
| **Hedef ΔT** | AHU | 5.0°C |
| **Hedef ΔT** | FCU | 4.0°C |
| **Hedef ΔT** | Chiller | 3.0°C |
| **Hedef ΔT** | Kolektör | 3.0°C |
| **Hedef ΔT** | Eşanjör | 8.0°C |
| **Hedef ΔT** | Isıtma | 25.0°C |
| **SAT Soğutma** | Min | 15.0°C |
| **SAT Soğutma** | Max | 18.0°C |
| **SAT Isıtma** | Min | 28.0°C |
| **SAT Isıtma** | Max | 31.0°C |
| **Vana** | Min Analiz | %40 |
| **Vana** | Yüksek | %90 |
| **Vana** | Simul | %5 |
| **Tolerans** | Kritik | 1.0°C |
| **Tolerans** | Normal | 3.0°C |
| **Approach** | Max | 10.0°C |
| **Skor** | Kritik Eşik | 7.0 |

## Notlar

- Bu dosyalar sistemin temel ayarlarını içerir
- Değişikliklerden sonra sunucu yeniden başlatılmalı
- Değişiklikler `tolerans_degerleri.md` belgesine yansıtılmalı
