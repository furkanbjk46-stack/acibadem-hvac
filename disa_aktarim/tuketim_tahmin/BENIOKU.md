# Enerji Tüketim Tahmini — bağımsız paket

Başka bir programa taşınmak üzere hazırlandı. Şu an Maslak verisiyle geliştiriliyor.
Lokasyon yamasına girmez; lokasyon verisi bu klasöre konmaz.

| Dosya | İş |
|---|---|
| `gunluk_model.py` | **Önerilen model.** Günlük tüketim, GES/kojen/şebeke ayrımı, aylık birleşik tahmin |
| `veri_kalite.py` | Eğitimden önce bozuk günleri bayraklar (donmuş sensör, sıfır/çift gün, kojen kaybı, elle hariç) |
| `tahmin_motoru.py` | Portaldaki mevcut algoritmanın birebir kopyası (aylık GBM). Kıyas için duruyor |
| `sinama.py` | İleriye dönük sınama: bütün yöntemler + ASHRAE G14 |
| `test_paket.py` | Doğrusu bilinen yapay veriyle 20 kontrol |
| `lokasyonlar/maslak.json` | Lokasyona özel ayar: koordinat, hariç tutulan dönemler |
| `sablonlar/*.csv` | Ek veri dosyalarının sütun şablonları |

Bağımlılık: `pandas`, `numpy`, `scikit-learn`.

## Kullanım

```python
import pandas as pd
from gunluk_model import GunlukTahminModeli, birlestir
import veri_kalite

ayar = veri_kalite.lokasyon_ayari("maslak")
g, kalite = birlestir(pd.read_csv("enerji.csv"),
                      hava=pd.read_csv("hava.csv"),            # isteğe bağlı
                      operasyon=pd.read_csv("operasyon.csv"),  # isteğe bağlı
                      haric=ayar["haric"])
print(kalite.ozet())

m = GunlukTahminModeli()
m.egit(g)
m.ay_tahmini(2026, 11)                           # kojen planı yok → varsayım
m.ay_tahmini(2026, 11, kojen_calisma_gun=26)     # ya da kojen_plan_kwh=1_150_000
m.gunluk_tahmin("2026-11-01", "2026-11-07", hava=hava_tahmini_df)
```

`ay_tahmini` çıktısı şu alanları verir: `tuketim`, `ges`, `kojen`, `sebeke`, `kojen_kaynak`
(`plan_kwh` | `plan_gun` | `varsayim`). Ayrıca iki bileşen ayrı ayrı döner:
`tuketim_gunluk_model` ve `tuketim_gecen_yil_duzeltmeli`.

## Model nasıl çalışıyor

1. **Veri kalitesi.** Bozuk günler silinmez, bayraklanır.
   - Tüketim bozuksa gün eğitime girmez.
   - Yalnız sensör bozuksa o değer boşaltılır. Dışarıdan hava verisi gelirse onunla doldurulur.
2. **Tüketim (yük).** Günlük doğrusal model (Ridge). Girdiler:
   - soğutma derece-günü (18 °C üstü), ısıtma derece-günü (15 °C altı),
   - hafta sonu, tatil, mevsim,
   - **isteğe bağlı:** hasta sayısı, ameliyat sayısı, yağış, bulut, güneş radyasyonu, hava durumu
     (yağmurlu/karlı).

   İsteğe bağlı bir sütun eğitim döneminin %80'inde dolu değilse model onu kendiliğinden
   kullanmaz. Veri boş kalsa da çalışır; veri gelince yeniden eğitmek yeter.
3. **Seviye düzeltmesi.** Son 90 günün gerçek/tahmin oranı uygulanır (±%15 ile sınırlı). Yeni
   bölüm açılması gibi kalıcı değişimleri yakalar.
4. **GES.** Radyasyon, bulut ve yağıştan öğrenilir. Yağmurlu günde GES düşer, açık şebekeye
   yazılır. GES verisi yoksa GES = 0.
5. **Kojen = plan (girdi).** Kojen hava ya da takvimle değil, işletme kararıyla çalışıyor.
   Maslak'ta 2026 Nisan–Haziran neredeyse hiç çalışmadı, Aralık 2025'te 11 gün çalıştı. Plan
   verilmezse son 90 günün çalışma düzeni varsayılır.
6. **Şebeke = tüketim − GES − kojen** (enerji dengesi).
7. **Aylık birleşik tahmin** = (günlük modelin ay toplamı + hava/seviye düzeltmeli geçen yılın
   aynı ayı) / 2.

## Gerçek Maslak verisiyle sonuç

Sınama ileriye dönük: her ay yalnız kendinden önceki veriyle eğitildi. 15 temiz ay ölçüldü.
Eylül 2026 kullanıcı kararıyla hariç tutuldu.

| Yöntem | MAPE | NMBE | CV(RMSE) | En kötü | ASHRAE G14 |
|---|---|---|---|---|---|
| Portaldaki ML (aylık GBM) | %4,0 | −%2,3 | %4,7 | %8,5 | Geçer |
| Geçen yılın aynı ayı | %3,6 | −%1,7 | %4,8 | %11,1 | Geçer |
| Günlük model | %3,5 | −%1,0 | %4,4 | %9,1 | Geçer |
| **Birleşik (önerilen)** | **%2,8** | −%1,1 | %4,0 | %8,0 | Geçer |
| Şebeke — kojen planı yokken | %35,2 | | | | Kalır |
| Şebeke — kojen çalışma günü verilince | %16,3 | | | | Kalır |
| **Şebeke — kojen kWh planı verilince** | **%5,3** | −%2,0 | %7,0 | %18,6 | Geçer |

ASHRAE Guideline 14 aylık ölçütü: NMBE ±%5, CV(RMSE) ≤%15.

**Yorum:**
- **Toplam tüketim.** Birleşik yöntem portaldaki modelden ortalama 1,2 puan iyi. 15 ay küçük bir
  örnek; fark yön olarak tutarlı ama kesin kanıt değil.
- **Şebeke.** Tahminin kalitesi tamamen **kojen planına** bağlı. Kojen kWh planı verilirse
  şebeke de ölçütü geçiyor.
- **Hava.** Maslak verisinde 2025 sonuna kadar dış hava aylık ortalama olarak girilmiş;
  20.09.2026'dan beri de donmuş. Yani modelin henüz **gerçek günlük havası yok**. Günlük hava
  geçmişi geldiğinde derece-gün etkisi doğru öğrenilecek. Bu dosyanın sonuçlarını hava verisi
  gelince yeniden ölçün.

### Günlük hava verisi eklenince (24.10.2026)

Hava `hava_indir.py` ile Open-Meteo arşivinden indirildi: `lokasyonlar/maslak_hava.csv`,
1241 gün. 2026'da bina sensörüyle korelasyon 0,88. Bina sensörü ortalama ~2 °C yüksek okuyor,
çünkü 07:05'teki anlık okuma; günlük ortalama değil.

| Yöntem (15 temiz ay) | Havasız | Günlük hava ile | Ayın **gerçek** havası bilinseydi |
|---|---|---|---|
| Günlük model | %3,5 | %3,2 | %3,3 |
| Birleşik | %2,8 | %3,0 | %2,8 |

**Sonuç:** Aylık TOPLAM tüketimde hava neredeyse fark yaratmıyor. Kusursuz hava tahmini bile
sonucu iyileştirmiyor. Maslak'ın yükünü baz yük (hastane işletmesi) ve mevsim belirliyor;
mevsim etkisini model zaten takvimden öğreniyor. Hava verisinin asıl değeri şu üç yerde olacak:
- **GES üretimi** (radyasyon ve bulut doğrudan belirler),
- **günlük / haftalık** tahmin,
- **soğutma ve ısıtma kırılımı.**

### Soğutma ve ısıtma ayrı tahmin (24.10.2026)

Kullanım: `GunlukTahminModeli(hedef="sogutma")` (chiller kWh) ya da `hedef="isitma_gaz"`
(kazan m³). Sınama ileriye dönük, son 24 ay. Hata, aylık ortalamaya oranla verildi; yazın
gaz ~0 olduğu için yüzde hata anlamsız.

| Kalem | Geçen yılın aynı ayı | Model | Model + ayın gerçek havası | Model + kojen planı |
|---|---|---|---|---|
| Soğutma | %36 | %22,6 | %18 | %22,6 (katkısı yok) |
| Isıtma gazı | %68 | %53 | %42 | **%30** |

- **Soğutma:** Hava burada gerçekten belirleyici. Kalan hata işletmeden geliyor: 2024–25
  kışında chiller tüketimi bir önceki yılın üçte birine düştü.
- **Isıtma gazı:** Asıl belirleyen **kojen**. Kojen çalışınca atık ısısı kazanın yerini
  tutuyor. 04–06.2026'da kojen durunca kazan gazı 3–4 katına çıktı. Bu yüzden ısıtmada kojen
  planı girdi olarak kullanılıyor. Lokasyon 24.10.2026'dan itibaren günlük `Kojen_Adet`
  (BACnet KOJEN-1..4 DURUM) yazacak; geçmiş biriktikçe plan "kaç kojen çalışacak" olarak
  verilebilecek.
- **Geçen yılla ortalama alınmaz:** Bu ortalama yalnız toplam tüketimde kullanılıyor. Soğutma
  ve ısıtmada geçen yılın aynı ayı tek başına çok kötü; işletme düzeni yıldan yıla değişiyor.

## Gemini v2 paketinin incelemesi (24.10.2026)

Gemini'nin önerdiği paketin rapordaki sonucu: ham veride %3,36, "temizlenmiş" veride %1,87.

**Adil karşılaştırma:**
- **Düzenek:** Aynı temiz aylar kullanıldı ve kimsenin değiştirmediği kayıtlı gerçek
  değerle kıyaslandı. İki dönem ölçüldü: Gemini'nin raporlamadığı 07.2024–06.2025 ve
  raporladığı 07.2025–08.2026.

| 25 temiz ay | MAPE | NMBE (sistematik sapma) |
|---|---|---|
| Gemini v2 | %3,29 | −%1,50 |
| Bu paket (birleşik) | %3,35 | **−%0,59** |
| Geçen yılın aynı ayı | %4,16 | −%2,17 |

- **%1,87 gerçek değil:** O sınamada gerçekleşen değerin kendisi, Gemini'nin temizlik
  kuralıyla değiştirilmiş. Ağustos 2026: 2.094.350 → 2.204.689, tahmine yaklaştırılmış.
- **Gerçek seviye eşit:** İki model başa baş. Gemini raporladığı dönemde biraz önde, öncekinde
  geride; sabitlerinin o döneme göre ayarlandığına işaret ediyor.
- **Alınanlar** (veriyle doğrulandı):
  - Türkiye bayram/resmi tatil takvimi (`takvim.py`).
  - Cumartesi/Pazar ayrımı. Aynı ayın hafta içine göre Cmt %94, Pzr %90, tatil %90.
  - Üç veri hatası türü: şebeke 0 yazılmış gün, ani düşük toplam, tek günlük sensör sıçraması.
    Doğru tespitlerdi ve geçmişte 6 gün daha bu yüzden bozuk çıktı.
- **Alınmayanlar:**
  - Maslak'a özel sabitler (44.500–91.500 kWh "bozuk" sınırı, 1600 kWh/derece-gün, 58.500
    baz yük). Başka binada çalışmaz.
  - Sabit aylık nem tablosu. Gerçek günlük nem artık internetten geliyor.
  - sklearn'süz yedek GradientBoosting kodu. Gereksiz.

## Ek veri dosyaları

Şablonlar `sablonlar/` klasöründe. Hepsinin ortak sütunu `Tarih` (YYYY-AA-GG), günlük satır.

| Dosya | Sütunlar | Not |
|---|---|---|
| hava | `sicaklik_ort, sicaklik_max, sicaklik_min, yagis_mm, bulut_yuzde, gunes_radyasyon, hava_durumu` | Geçmiş + gelecek (hava tahmini). Radyasyon kWh/m²/gün. Durum metni: güneşli / bulutlu / yağmurlu / karlı |
| operasyon | `hasta_sayisi, ameliyat_sayisi, tatil` | `tatil` 0/1. Boş hücre olabilir |
| GES | `GES_Uretim_kWh` | Ana enerji tablosuna sütun olarak eklenir |

## Sınamayı tekrarlamak

```bash
python test_paket.py
python sinama.py enerji.csv --lokasyon maslak
python sinama.py enerji.csv --lokasyon maslak --hava hava.csv --operasyon operasyon.csv --ay 18
```

Yeni bir lokasyon için `lokasyonlar/<ad>.json` açılır: koordinat ve hariç tutulacak dönemler.
Her model değişikliği `sinama.py` ile **portaldaki ML'e ve "geçen yılın aynı ayı" kuralına
karşı** ölçülür. Bu ikisini yenemeyen değişiklik alınmaz.
