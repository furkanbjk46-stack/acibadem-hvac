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
