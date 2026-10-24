# Aylık Tüketim Tahmini — algoritma, gerçek başarı, geliştirme yolu

Kaynak: `hvac/deneme/monthly_report/forecast_engine.py` (Enerji ve Verimlilik → Tahmin & Trend).
Bu klasördeki kod aynı algoritmanın bağımsız hâlidir. Orijinalle aynı veride 12 ayın tahmini
birebir aynı çıktı (fark 0 kWh).

| Dosya | İş |
|---|---|
| `tahmin_motoru.py` | Model: eğitim, tahmin, senaryo, kaydet/yükle |
| `sinama.py` | İleriye dönük sınama + basit yöntemlerle kıyas + ASHRAE G14 |

Bağımlılık: `pandas`, `numpy`, `scikit-learn`.

```python
from tahmin_motoru import TuketimTahminModeli
m = TuketimTahminModeli()                      # sütun adları farklıysa kolonlar={...}
m.egit(gunluk_df)                              # günlük tablo
m.tahmin_gecmisten(gunluk_df, 2026, 11)        # ekrandaki "Tahmin (kWh)"
m.tahmin(2026, 11, {"dis_hava": 12, "chiller_adet": 1, ...})   # senaryo
```

## 1. Nasıl çalışıyor

1. **Günlük → aylık.** Tüketim, kojen ve gaz ay içinde toplanır. Dış hava, chiller set ve
   cihaz adetlerinin ortalaması alınır. 15 günden az verisi olan ay atılır. Eğitim için en az
   12 ay gerekir.
2. **11 özellik.** Ay, sin/cos(ay) (Aralık ile Ocak'ın komşu olduğunu modele anlatır), gün
   sayısı, dış hava, chiller set, chiller / absorption / kazan adedi, kojen üretimi, kazan gazı.
3. **İki GradientBoosting modeli.** Biri toplam, biri şebeke tüketimi için. Ayarlar: 150 ağaç,
   derinlik 5, öğrenme hızı 0,1. Her ağaç bir öncekinin hatasını düzeltir.
4. **Tahmin anı.** Gelecek ayın dış havası ve chiller adedi henüz bilinmediği için **geçmişte
   aynı ayın ortalama koşulları** girilir. Örneğin Kasım tahmini, geçmiş Kasımların
   ortalamasıyla yapılır.

## 2. Ekrandaki "Sapma %1–9" ne demek — ve ne demek değil

- **Ekran görüntüleri sentetik veriden.** Paylaşılan ekranlar (987 gün, R² 0,380, Ocak
  gerçekleşen 1.995.872) geliştirme PC'sindeki **örnek (sentetik) veriden**. Bu veri
  `ornek_veri_uret.py` ile üretildi. Gerçek Maslak Ocak 2026 değeri 1.792.966 kWh.
- **"Sapma" sütunu başarı ölçüsü değil.** O sütun, modelin **eğitimde gördüğü** aylarla
  kıyaslanır. Gerçek başarı, modelin hiç görmediği ayı tahmin edip etmediğidir.
- **Yerel model bayat.** Yerel model 02.05.2026'da 987 günle eğitilmiş. Yeniden eğitim koşulu
  `kayıt sayısı > eğitim + 20`. Mevcut dosya 730 satır olduğu için model hiç yenilenmiyor.

## 3. Gerçek Maslak verisiyle dürüst sınama

Veri: 1220 gün (22.06.2023 → 23.10.2026). Her hedef ay için model yalnızca o aydan **önceki**
veriyle eğitildi. Değerlendirme son 15 tam ay üzerinde (07.2025 – 09.2026).

| Yöntem | MAPE | NMBE | CV(RMSE) | En kötü ay | ASHRAE G14 |
|---|---|---|---|---|---|
| **ML (bu algoritma)** | **%4,4** | −%0,6 | %6,2 | %14,8 | Geçer |
| Basit: geçen yılın aynı ayı | %4,0 | %0,0 | %6,1 | %14,1 | Geçer |
| Basit: geçen yıl × son 3 ay değişimi | %4,5 | +%1,0 | %6,9 | %17,3 | Geçer |
| ML, ayın **gerçek** koşullarıyla (üst sınır) | %6,7 | −%2,3 | %8,2 | %17,6 | Geçer |

Modelin kendi çapraz doğrulama R² değeri gerçek veride: toplam 0,17, şebeke −0,03.

**Sonuç:**
- **Doğruluk gerçek.** İleriye dönük %4,4 ortalama hata, ASHRAE Guideline 14 aylık ölçütünü
  geçiyor (NMBE ±%5, CV(RMSE) ≤%15). "%20 kabul edilir" sınırının çok altında.
- **Ama başarı algoritmadan gelmiyor.** "Geçen yılın aynı ayı" gibi bir satırlık bir kural
  aynı (hatta biraz daha iyi) sonucu veriyor. Hastanenin yükü yıldan yıla çok kararlı; düşük
  hata tesisin özelliği.
- **Model havayı öğrenmemiş.** Ayın gerçek dış havası verilince tahmin **kötüleşiyor**
  (%4,4 → %6,7). Model aslında "bu ay genelde ne kadar" sorusunu ezberliyor. Ekranda dış
  havanın %73 etkili görünmesinin sebebi, sıcaklığın ayın yerine geçmesi.
- **Büyük değişimleri ikisi de kaçırıyor.** 09.2026'da ML +%17, basit kural +%21 kaçırdı.
  Tüketim bir önceki Eylül'e göre +%16 arttı.

Bu yüzden başka bir programa "%1–9 tutturan ML" diye taşımak doğru olmaz. Doğru ifade şu:
"aylık tahmin %4–5 hatayla çalışıyor, bu seviyeyi basit bir kural da veriyor."

## 4. Geliştirme yolu (öneri — öncelik sırasıyla)

1. **Kıyas çizgisini zorunlu yap.** Her ölçümde `sinama.py` ile "geçen yılın aynı ayı"
   kuralını yen. Yenemeyen model değer katmıyor.
2. **Sızıntılı özellikleri çıkar.** Kojen üretimi, kazan gazı ve chiller adedi ay bitmeden
   bilinmez; üstelik tüketimin sonucudur, sebebi değil. Önceden bilinebilecek özellikler:
   takvim, tatil/bayram günü, dış hava, derece-gün.
3. **Havayı doğru öğret.** Ortalama sıcaklık yerine soğutma/ısıtma **derece-gün** kullan
   (ör. 18 °C tabanlı). Fizik yasası gibi doğrusal davranır, az veriyle öğrenilir.
   Hava tahmini servisiyle birleşince gelecek ay için anlamlı girdi olur.
4. **Günlük modele geç.** Aylık modelde 40 satır var; GradientBoosting için çok az. Günlük
   modelde 1200+ satır olur, aylık tahmin günlerin toplamı olarak çıkar.
5. **Değişimi yakala.** Son 3 ayın yıllık değişim oranını özellik olarak ekle. 09.2026 gibi
   kalıcı yük artışlarını ancak bu yakalar.
6. **Doğru doğrulama.** Karıştırmasız k-katlı CV yerine zaman sıralı doğrulama kullan
   (`TimeSeriesSplit` ya da `sinama.py`'deki ileriye dönük yöntem).
7. **Belirsizlik ver.** Tek sayı yerine aralık ver (ör. %80 güven bandı). Quantile
   GradientBoosting ya da geçmiş hata dağılımı kullanılabilir.
8. **Portaldaki iki hata** (bu pakette değil, `forecast_engine.py`'de):
   - Yeniden eğitim koşulu veri azalınca hiç tetiklenmiyor.
   - "Sapma" sütunu eğitimde görülmüş aylarla kıyaslıyor; ileriye dönük sapma gösterilmeli.

## 5. Sınamayı tekrarlamak

```bash
python sinama.py gunluk_veri.csv --ay 15
```

CSV sütunları `VARSAYILAN_KOLONLAR` adlarıyla olmalı, ya da `TuketimTahminModeli(kolonlar=...)`
ile eşlenmeli. Lokasyon verisi bu klasöre konmaz.
