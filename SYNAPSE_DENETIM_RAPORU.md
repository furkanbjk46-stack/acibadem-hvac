# SYNAPSE (Merkez Portal) — Hesaplama Denetim Raporu
**Tarih:** 05.07.2026 · **Kapsam:** merkez/app_merkez.py (2236), pages/lokasyon_detay.py (1415), pages/rapor_olustur.py (900), merkez_sync.py (76)
**Yöntem:** Satır satır statik inceleme + izole fonksiyonlarda çalıştırmalı sentetik testler
**Not:** Önceki denetimde bulunan SY-1 (kojen verim) hariç tutuldu — bu tur *yeni* alanlara odaklandı.

---

## 1. Çalıştırmalı Test Sonuçları

| Test paketi | Sonuç |
|---|---|
| Oto Set histerezis (Chiller 4-bölge + Kollektör/FCU ikili mod) — 15 senaryo | **15/15 ✓** |
| sparkline_svg güvenlik (tek değer, sabit seri) | **2/2 ✓** |
| tr() Türkçe sayı formatı (binlik nokta, ondalık virgül) | ✓ |
| Global Özet kısmi-ay kıyası (sentetik) | ❌ **SYN-1 doğrulandı: %-83,3 sahte düşüş** |

## 2. Bulgular

### ❌ SYN-1 (ORTA-YÜKSEK, testle kanıtlandı) — Global Özet: kısmi ay vs tam ay
`app_merkez.py` ~satır 995-1043: sol kolondaki "GLOBAL ÖZET" kartlarında bu ayın
(1'inden bugüne, kısmi) toplamı **geçen ayın tamamı** ile yüzdeleniyor.
**Kanıt:** Günlük tüketim birebir aynıyken, ayın 5'inde kart **"▼ %83,3 düşüş"** (yeşil) gösteriyor.
Ay sonuna kadar her gün yanıltıcı bir "tasarruf" izlenimi verir; GM'nin ana ekranıdır.
**Düzeltme:** Geçen ayın *aynı gün aralığı* ile kıyasla (`_gec_ay_bas` → `_gec_ay_bas + (bugün.gün-1)`)
veya gün-ortalaması üzerinden yüzdele. (MR-1'in aylık versiyonu — aynı hata sınıfı.)

### ❌ SYN-5 (ORTA) — lokasyon_detay "Bu Ay vs Geçen Ay" fark özeti aynı hatada
`lokasyon_detay.py` ~satır 836-847: grafikteki günlük çubuklar doğru, ancak alttaki
"Bu ay şimdiye kadar geçen aya göre %X az/fazla" özeti `bu_top` (kısmi) / `gec_top` (tam ay)
oranı → ayın başında her zaman "az tüketim" der.
**Düzeltme:** `gec_gun`'u bu ayın gün sayısına kırp: `gec_gun[gec_gun.index <= son_gun_no]`.

### ⚠️ SYN-2 (DÜŞÜK) — Kojen Üretim metriğinde renk yönü ters
`app_merkez.py` `_pct_html`: artış = kırmızı ▲, düşüş = yeşil ▼ — tüketim için doğru,
ancak aynı fonksiyon **"⚙️ Kojen Üretim"** satırında da kullanılıyor. Kojen üretiminin artması
İYİ bir şeydir; kırmızı gösterilmesi yanıltıcı.
**Düzeltme:** Metrik başına `iyi_yon` parametresi (tüketim=düşüş iyi, üretim=artış iyi).

### ⚠️ SYN-3 (DÜŞÜK) — Lokasyon kartı % değişimi yanlış gün çiftini kıyaslayabiliyor
`dun_kwh()` dün verisi yoksa **en son mevcut güne** düşer (fallback), ama `onceki_gun_kwh()`
sabit olarak **bugün-2**'ye bakar. Dün verisi yoksa (örn. sync gecikti): kart "son gün"
değerini gösterir ama % değişim ya boş kalır ya da alakasız iki günü oranlar.
Ayrıca karttaki **"kWh/m²"** rozeti günlük değerdir — etiket "kWh/m²/gün" olmalı.
**Düzeltme:** `onceki_gun_kwh`'ı da dun_kwh'ın seçtiği günün bir öncesine bağla.

### ⚠️ SYN-4 (DÜŞÜK) — "Kazan verimi" kavramsal olarak yanlış + ölü grafik dalı
`lokasyon_detay.py` ~satır 869-877: "Doğalgaz Verimliliği" grafiğinde
**"Kazan (kWh/m³)" = Toplam ELEKTRİK tüketimi / Kazan gazı** — kazan gazı elektrik üretmez;
bu bir "genel yoğunluk" metriğidir, "Kazan verimi" etiketi yanlış.
**Ek tespit:** Bu grafik dalı (`dogalgaz_verim`) `grafik_secenekler` sözlüğünde YOK —
kullanıcı hiç seçemez, **ölü kod**. Ya seçeneğe ekleyip etiketi düzelt ya da dalı sil.

### ⚠️ SYN-6 (DÜŞÜK) — merkez_sync.py ölü + sayfalamasız (tuzak)
`merkez_sync.fetch_energy_data` hiçbir sayfa tarafından kullanılmıyor (aktif sayfalar kendi
sayfalamalı fetch'lerini içeriyor). Fonksiyonda **sayfalama yok** ve `order("Tarih", asc)` ile
Supabase varsayılan 1000 satır limiti → veri 1000 günü aşınca **en yeni kayıtlar hiç gelmez**
(en eski 1000 satır döner). Şu an zararsız ama ileride biri kullanırsa sessiz veri kaybı.
**Düzeltme:** Dosyayı sil veya sayfalama ekle.

### 📄 SYN-7 (KOZMETİK) — küçük etiket/metin uyumsuzlukları
- "🚨 CANLI UYARILAR" içinde "⚠️ {isim}: **Bugün** veri yok" mesajı aslında **dünü** kontrol ediyor (`== dun`).
- "AYLIK kWh/m² VERİMLİLİK" grafiğinde devam eden ay kısmi olduğu için son bar yapay düşük — "(devam ediyor)" notu eklenebilir.
- `_dig_modu_hesapla` docstring "±2°C histerezis" diyor, gerçek `_DIG_H = 3.0`.

## 3. Temiz Çıkanlar (denetlendi, sorun yok)

- **fetch_energy:** 1000'lik sayfalama + `drop_duplicates(lokasyon_id, Tarih, keep=last)` ✓
- **Oto Set kontrolü:** 4-bölge chiller histerezisi, ikili kollektör/FCU modu, dönem geçişi
  (06:00/19:00), tek-thread kilidi, komut üretimi — 15/15 senaryo testi geçti ✓
- **YoY badge (`_yoy_badge`):** `DateOffset(years=1)` (29 Şubat güvenli), aynı dönem uzunluğu,
  sıfır-bölme koruması ✓ — tüketim grafiklerinde renk yönü doğru
- **Kojen karşılama oranı:** `kojen/toplam*100`, `min(...,100)` sınırı ✓
- **Enerji kırılım donutları:** Kaynak (Kojen+Şebeke+Diğer) ve Tüketim (Soğutma+MCC+Diğer),
  Diğer `max(...,0)` ile negatif korumalı ✓ — v5.8 sonrası Toplam=Şebeke+Kojen ile tutarlı
- **KPI Özet / Rapor PDF metrikleri:** dönem toplamları, kWh/m², chiller set ortalaması ✓
- **TRDP kartları (Maslak):** TRDP-1/3=Bina, TRDP-2/4=Mekanik — Synergy portalıyla tutarlı ✓
- **Türkçe sayı formatı (`tr`)**: 1.234.567 / 1.234,56 ✓
- **online_bilgi:** 10 dk ping eşiği, tz-naive dönüşüm ✓
- **Harita, sparkline, uyarı sıralaması:** hesap hatası yok ✓

## 4. Öncelik Özeti

| # | Bulgu | Önem | Kanıt |
|---|---|---|---|
| SYN-1 | Global Özet kısmi ay vs tam ay → sahte %83 "düşüş" | **ORTA-YÜKSEK** | ✅ test |
| SYN-5 | Ay karşılaştırma fark özeti aynı hata (lokasyon_detay) | **ORTA** | statik |
| SYN-2 | Kojen Üretim % renk yönü ters | DÜŞÜK | statik |
| SYN-3 | Kart % değişimi yanlış gün çifti + kWh/m² etiketi | DÜŞÜK | statik |
| SYN-4 | "Kazan verimi" yanlış payda + ölü grafik dalı | DÜŞÜK | statik |
| SYN-6 | merkez_sync ölü + sayfalamasız (gelecek tuzağı) | DÜŞÜK | statik |
| SYN-7 | Etiket/docstring uyumsuzlukları (3 adet) | KOZMETİK | statik |

**Öneri:** SYN-1 + SYN-5 tek yamada düzeltilmeli (ikisi de "kısmi dönem vs tam dönem" sınıfı,
GM'nin gördüğü ana metrikler). SYN-2/3/4/6/7 ikinci pakette toplanabilir. app_merkez yalnızca
Streamlit Cloud'da çalıştığı için dağıtım = GitHub push (lokasyon yaması gerekmez).
