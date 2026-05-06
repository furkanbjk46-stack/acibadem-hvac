# 🧠 Proje Notları & Açık Konular
_Son güncelleme: 05.05.2026_

---

## ✅ Tamamlanan Özellikler

### Enerji Zekası AI Modülü (app_merkez.py — sağ kolon)
- Her sabah sayfa açılınca **otomatik** çalışır (gün değişimini algılar)
- Dünün gerçek verilerini analiz eder: elektrik, kojen, şebeke, doğalgaz, su, chiller
- **3 katmanlı adaptif format** — lokasyon sayısına göre otomatik değişir:
  - **TIER 1 (1–3 lok):** Her lokasyon tam detay, 180 kelime
  - **TIER 2 (4–7 lok):** Özet tablo + anormal lokasyonlar detay, 220 kelime
  - **TIER 3 (8+ lok):** Grup istatistik + mini tablo + top-3 kritik, 250 kelime
- max_tokens da tier'a göre otomatik: 500 / 650 / 800
- 30 dakika session_state cache — gün boyunca tekrar API çağrısı yapmaz
- Manuel "🔄 Yeniden Analiz Et" butonu zorla yeniler
- Model: `claude-haiku-4-5` (çok ucuz, günlük ~$0.008 maliyet)

### AI'ye gönderilen metrikler (her lokasyon için):
- Elektrik tüketimi (kWh) + kWh/m²/gün
- Kojen üretimi + verim (kWh/m³) — norm ≥3.5
- Şebeke bağımlılığı % — ideal <%30
- Doğalgaz tüketimi m³ + genel verim (kWh/m³) — norm ≥5.0
- Su tüketimi m³
- Chiller set °C + yük %
- 30 günlük ortalama trend

---

## 📌 Hatırlanması Gereken Kurallar

### Enerji üçgeni ilişkisi
```
Doğalgaz m³
    ↓
Kojen (elektrik üret)  ←→  Şebeke (dışarıdan çek)
    ↓
Toplam tüketim
```
- `kojen_verim` = Kojen_kWh / Dogalgaz_m3
- `sebeke_bag`  = Şebeke / (Şebeke + Kojen) × 100
- `gaz_verim`   = Toplam_kWh / Dogalgaz_m3

### Analizör grupları (data_bridge.py)
- `CHILLER_ANALYZERS`   = CH-1 … CH-5
- `MCC_ONLY_ANALYZERS`  = ALL_ANALYZERS − CHILLER_ANALYZERS
- Soğutma = Chiller only | MCC = Chiller hariç tümü | Toplam = hepsi

### Supabase güncelleme mekanizması
- Lokasyon PC'leri → `guncellemeler` tablosu → `durum='bekliyor'`
- Her lokasyon için **ayrı** kayıt: hedef='altunizade', hedef='maslak'
- Sadece değişen dosyaları `dosyalar` alanına koy (yama mantığı)

---

## 🔜 Yapılacaklar / Açık Konular

- [ ] Lokasyon sayısı 4+ olduğunda TIER 2 formatını gerçek veriyle test et
- [ ] Lokasyon sayısı 8+ olduğunda TIER 3 formatını gerçek veriyle test et
- [ ] AI analizinde trend karşılaştırması ekle (bu hafta vs geçen hafta)
- [ ] Kojen verimi normun altına düşünce otomatik uyarı ekle (Canlı Uyarılar'a)
- [ ] m² değerleri Ayarlar'dan güncelleniyor ama Supabase'e yazılıyor mu kontrol et

---

## 💰 Anthropic API Durumu
- Plan: Evaluation access
- Kredi: $5.00 yüklendi (harcanan: ~$0.01)
- Monthly limit: $100 (güvenlik tavanı — kredin bitince durur)
- Günlük maliyet tahmini (10 lokasyon): ~$0.008 → $5 ile **~1.7 yıl**

---

## 🔑 Servis Anahtarları
- Supabase: `supabase_secret.json` → service_role_key kullan
- Anthropic: Streamlit Secrets → `[anthropic] api_key = "sk-ant-..."`
- Supabase URL: `https://qayjwkqnnjjsnnxovhei.supabase.co`
