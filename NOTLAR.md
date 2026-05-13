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
- [ ] B-BLOK FCU SET, ZON-1, ZON-2 obj_inst değerlerini sahada doğrula (14,15,16 tahmini)
- [ ] Chiller REM Set otomatik tetik: dış hava eşiği aşılınca tüm chillerlere otomatik komut gönder (sezon geçiş algoritması)

---

## 🎯 Uzaktan Kontrol & Bildirim Sistemi (✅ A+B+C+D Kodlandı)

### A) Chiller REM Set — Uzaktan Yazma ✅ KODLANDI
- Dış hava eşiği aşılınca (sezon geçişi) Chiller REM set noktasına BACnet WriteProperty ile otomatik yaz
- Histerezis toleransı: ±1°C (sürekli dalgalanmayı önler)
- Tüm lokasyonlara aynı anda gönderilir, her lokasyon kendi BACnet noktasına yazar

**Gerekli Supabase tabloları:**
```
komutlar        → id, lokasyon, nokta_adi, hedef_deger, durum(bekliyor/tamamlandi), created_at
lokasyon_noktalar → lokasyon, nokta_adi, gateway_ip, dnet, mac_hex, obj_type, obj_inst
```

**Mimari akış:**
```
Open-Meteo dış hava → eşik kontrolü (±1°C histerezis)
    → Supabase komutlar tablosu (tüm lokasyonlar için ayrı kayıt)
    → Lokasyon PC polling (her 1 dk)
    → BACnet WriteProperty → Chiller REM Set noktası
    → durum = 'tamamlandi'
```

**Not:** Her lokasyonun BACnet adresi farklı → `lokasyon_noktalar` tablosundan okur, kod değişmez, sınırsız ölçeklenir.

---

### C) GM → Lokasyon Manuel Mesajlaşma ✅ KODLANDI
- GM portaldan lokasyon ekranına serbest metin mesajı gönderilebilir ("Merhaba..." gibi)
- Aynı `bildirimler` tablosu kullanılır, `gonderen = "GM Merkez"` alanıyla ayırt edilir
- Öncelik seçimi: Bilgi (mavi) / Uyarı (sarı) / Acil (kırmızı)
- Hedef: tek lokasyon veya tümü (hedef = 'all')
- Lokasyon ekranında banner olarak çıkar, personel "Okundu" butonuyla kapatır
- Birden fazla mesaj varsa üst üste sıralanır, her biri ayrı kapatılır

**GM Portal UI:**
- Lokasyon seçici dropdown
- Serbest metin alanı
- Öncelik radio butonu
- Gönder butonu → Supabase bildirimler tablosuna yazar

**Supabase bildirimler tablosu:**
```
id, lokasyon, mesaj, gonderen, oncelik(bilgi/uyari/acil), okundu(bool), created_at
```

---

### D) Dış Hava 7 Günlük Log + Akıllı Eşik Sistemi ✅ KODLANDI

**Fikir:** Anlık dış hava verisi zaten çekiliyor. Bunu 7 günlük log olarak tutarak
tüm sistem için (chiller, kazan, enerji) dinamik analiz ve proaktif uyarı üret.

**Supabase dis_hava_log tablosu:**
```
id, timestamp, derece, kaynak(api/db)
→ 7 günden eski kayıtlar otomatik silinir
→ Saatte 1 kayıt yeterli (her sayfa açılışında yazar)
```

**Kullanım alanları:**
- **Chiller:** 3 gündür yükseliş trendi → eşik geçmeden proaktif uyarı
- **Kazan:** Gece minimumlarına bakarak sabah ısıtma başlangıcını optimize et
- **Enerji analizi:** Tüketim farkının ne kadarı hava kaynaklı, ne kadarı operasyonel
- **Dinamik eşikler:** Sabit 7/23°C yerine lokasyon ve sezona göre öğrenilmiş eşikler
- **AI entegrasyonu:** Enerji Zekası'na haftalık dış hava trendi de beslenir

**Analiz çıktıları:**
```
"3 gündür sıcaklık artıyor, yarın 25°C bekleniyor → Chiller hazırlığı önerilir"
"Bu hafta ort. 19°C, geçen hafta 12°C → tüketim farkının %60'ı hava kaynaklı"
"Gece min. 8°C'nin altına düştü → sabah kazan devreye alma saatini öne al"
```

**Maliyet:** Sıfır — zaten yapılan API çağrısına sadece Supabase write eklenir.
- **AI entegrasyonu:** Enerji Zekası'na haftalık dış hava trendi beslenerek "tüketim artışı hava kaynaklı mı, operasyonel mi" tespiti yapılabilir.

---

### B) Kollektör / Zon / Ortak Alan Setleri — Bildirim Sistemi ✅ KODLANDI (bildirimler tablosu)
- Mevsimsel geçişlerde (sezon değişimi algılandığında) lokasyon ekranına bildirim gönder
- İçerik: "Geçiş dönemi — Kollektör seti kontrol edilmeli / sahadan güncellenmeli"
- Chiller REM gibi otomatik yazmaz, personele hatırlatma yapar

**Gerekli: Lokasyon programına Bildirim Merkezi kurulması**
- app_portal.py içinde bir bildirim paneli/kutusu
- Supabase `bildirimler` tablosunu polling ile okur
- Okundu/okunmadı takibi
- GM portaldan veya otomatik tetikleyiciden yazılır

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
