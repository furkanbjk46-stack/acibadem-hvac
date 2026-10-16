# OTO-SET — Algoritma ve Eşik Değerleri

Bu belge **koddan çıkarılmıştır**; her sayının yanında kaynağı yazılıdır.
Tek kaynak `hvac/deneme/oto_set.py`'dir — merkez (Synapse) kural kopyası
tutmaz, yalnızca sahanın bildirdiğini gösterir.

Çıkarım tarihi: 16.10.2026 · Kod sürümü: v9.9 (maslak)

> **16.10.2026 düzeltmesi:** Kollektör/FCU/AHU tarafında **iki eşik** vardır
> (23 °C ve 15 °C). 01.10.2026'da 15 °C eşiği eklenirken 23 °C eşiği
> yanlışlıkla kaldırılmış, mod ikiliye düşmüştü; dış hava 23'ün üstüne
> çıktığında kollektör gündüz 10 °C'de kalıyordu (tabloda 8 °C). İki eşik
> birlikte geri kondu — ayrıntı §6.

---

## 1. Görev dağılımı

| Taraf | Ne yapar |
|---|---|
| **Merkez (Synapse)** | Kuralı yayınlar: `oto_set_aktif`, `oto_gunduz_saat`, `oto_gece_saat` (Supabase `ayarlar` tablosu) |
| **Lokasyon PC'si** | Kuralı uygular, dış havaya göre modu seçer, setpoint'i **doğrudan BACnet'e** yazar, cihazdan geri okuyup doğrular |

Karar neden sahada veriliyor: merkez Streamlit Cloud'da uyuduğunda arka plan
döngüsü de duruyordu; setler saatinde değil, biri portalı açtığında gidiyordu
(31.08'de 23:00 yerine 00:32). Lokasyon PC'si 7/24 açık.

Setpoint `komutlar` tablosundan **geçmez**: anon anahtarın o tabloya yazma
yetkisi güvenlik gereği kapatıldı. Denetim izi `oto_mod_log` + `komutlar`
log satırlarına düşer (`OTO-SET` öneki).

---

## 2. Çalışma döngüsü

```
cloud_sync döngüsü (her 1 dakika)
        │
        ▼
  kontrol()  ── kilit alınamazsa: "mesgul", tur atlanır
        │
        ▼
  1. Merkezden kuralı oku        → okunamazsa HİÇBİR ŞEY YAPMA
  2. Aktif mi?                   → değilse "kapali"
  3. Saatten dönemi bul          → dönem değişmediyse yalnızca doğrulamayı ilerlet
  4. Hava tahminini al           → yoksa geçişi ERTELE
  5. Referans sıcaklığı seç
  6. Chiller modu + kollektör modu (histerezisli)
  7. 11 noktaya BACnet yaz
  8. 3 dk sonra cihazdan geri oku, 15 dk'ya kadar takip et
```

**Komut YALNIZCA dönem geçişinde üretilir.** Gün ortasında hava tahmini
değişse bile set gitmez; bir sonraki geçişte uygulanır.

---

## 3. Dönem (gündüz / gece)

`donem_hesapla(saat, gunduz_saat, gece_saat)` — `oto_set.py:454`

- `gunduz_saat < gece_saat` → `gunduz_saat ≤ saat < gece_saat` ise **gündüz**, değilse gece
- `gunduz_saat > gece_saat` (gece yarısını aşan ayar) → `saat ≥ gunduz_saat` **veya** `saat < gece_saat` ise gündüz
- İkisi eşitse sürekli gündüz

**Yürürlükteki değerler (16.10.2026, Supabase `ayarlar`):**

| Ayar | Değer |
|---|---|
| `oto_set_aktif` | `true` |
| `oto_gunduz_saat` | **8** (08:00) |
| `oto_gece_saat` | **23** (23:00) |

Lokasyona özel saat tanımlı değil. Tanımlanırsa anahtar
`oto_gunduz_saat_<lokasyon>` biçimindedir ve genel anahtarı ezer.

> **Varsayılan geçiş saati bilerek YOKTUR.** Önceden ayar okunamazsa
> 05:00/22:00 kullanılıyordu; 12.09'da anlık bir ağ hatasında gece geçişi
> 22:41'de yapıldı ve sahaya 3 set turu gitti. Artık kural okunamazsa o tur
> hiçbir şey yapılmaz. (`oto_set.py:76`)

---

## 4. Referans sıcaklık

| Dönem | Referans | Neden |
|---|---|---|
| **Gündüz** geçişi | **bugünün max** sıcaklığı | Sabah başlayan gündüz, bugünün gündüzüdür |
| **Gece** geçişi | **yarının min** sıcaklığı | Akşam başlayan gece takvimde yarına sarkar; en düşük sıcaklık yarın sabaha doğru oluşur |

- Kaynak: `api.open-meteo.com` → `temperature_2m_max` / `temperature_2m_min`
- Koordinat: `configs/lokasyon_profili.json` → `supabase_config.json` → İstanbul (41.0082 / 28.9784)
- Önbellek: **30 dakika**, koordinata bağlı (`_TAHMIN_OMRU_DK`, `oto_set.py:102`)
- Tahmin alınamazsa geçiş **ertelenir** — eski referansla set gönderilmez

---

## 5. Chiller modu — 4 bölge, ±2 °C histerezis

`CH_SINIRLAR = [7.0, 23.0, 26.0]` · `CH_H = 2.0` · `oto_set.py:57-60`

### Bölgeler ve set değerleri

| Mod | Dış hava referansı | Chiller seti |
|---|---|---|
| `koc_soguk` | ref < 7 °C | **8,0 °C** |
| `serin` | 7 ≤ ref < 23 °C | **7,5 °C** |
| `ilimli` | 23 ≤ ref < 26 °C | **7,0 °C** |
| `sicak` | ref ≥ 26 °C | **6,5 °C** |

Mantık: dışarısı soğudukça set **yükselir** (daha az soğutma), ısındıkça
**düşer**.

### Histerezis — moddan çıkış eşikleri

Mevcut moddan çıkmak için sınırın **2 °C ötesine** geçmek gerekir:

| Mevcut mod | Çıkış koşulu |
|---|---|
| `koc_soguk` | ref > **9** |
| `serin` | ref > **25** veya ref < **5** |
| `ilimli` | ref > **28** veya ref < **21** |
| `sicak` | ref < **24** |

Çıkış koşulu sağlanmazsa mod **aynı kalır**. Sağlanırsa doğrudan hedef
bölgeye geçilir — **kademesiz**: `serin`den `sicak`a tek adımda atlanabilir.

**Örnek:** mod `serin` iken ref 24 °C → 24 > 25 değil, çıkmaz, `serin` kalır
(set 7,5). Ertesi gün ref 27 °C → 27 > 25, çıkar; hedef bölge 26 ≤ 27 olduğu
için `sicak` (set 6,5) — `ilimli` atlanır.

---

## 6. Kollektör / FCU / AHU modu — 3 bölge, 2 eşik, ±3 °C histerezis

`DIG_SINIRLAR = [15.0, 23.0]` · `DIG_H = 3.0` · `oto_set.py:79-92`

**İki eşik iki ayrı işi yapar; biri diğerinin yerine geçmez:**

- **23 °C** → yaz bölgesini açar: kollektör 8/10, FCU 12, AHU 8
- **15 °C** → kış bölgesini açar: kollektör 12/14. Bu eşik, sıcaklık 23'ün
  altına indiğinde kollektörün gündüz 10 °C'de takılıp **chiller'ı sürekli
  çalıştırması** sorunu için eklenmiştir.

### Bölgeler ve set değerleri

| Mod | Dış hava | Gündüz kollektör | Gece kollektör | FCU (A/B blok) | AHU (Zon-1/2) |
|---|---|---|---|---|---|
| `yogun_sogutma` | ref > 23 °C | **8,0** | **10,0** | **12,0** | **8,0** |
| `sogutma` | 15 ≤ ref ≤ 23 °C | **10,0** | **12,0** | **14,0** | **10,0** |
| `isitma` | ref < 15 °C | **12,0** | **14,0** | **14,0** | **10,0** |

### Histerezis — moddan çıkış eşikleri

| Mevcut mod | Çıkış koşulu |
|---|---|
| `yogun_sogutma` | ref < **20** → `sogutma` |
| `sogutma` | ref > **26** → `yogun_sogutma` · ref < **12** → `isitma` |
| `isitma` | ref > **18** → `sogutma` |
| (bilinmiyor) | doğrudan bölgesine düşer: <15 ısıtma, 15–23 soğutma, ≥23 yoğun soğutma |

Chiller'da olduğu gibi **kademesiz**: yaz ortasından kışa tek adımda
`yogun_sogutma` → `isitma` geçilebilir, araya sahte bir `sogutma` turu
konmaz.

Her geçişte **altı noktanın tamamı** yazılır — gündüz ve gece kollektör
setleri, dönem hangisi olursa olsun birlikte güncellenir.

> **Tarihçe.** 01.10.2026'da işletme tablosuna göre eşik 23 → 15 °C
> değiştirildi, kollektör setleri +2 °C yapıldı ve FCU/AHU "moddan bağımsız
> sabit" kabul edildi. Bu sırada 23 °C bölgesi tablodan düştü; 16.10.2026'da
> sahadan bildirilen hata üzerine iki eşik birlikte geri kondu. FCU/AHU
> yalnızca 15–23 ve 15 altı bölgelerde sabittir, yaz bölgesinde 12/8'e iner.

---

## 7. Yazılan noktalar (Maslak — 11 nokta)

| Grup | Noktalar |
|---|---|
| Chiller | `CH1_REM_SET` … `CH5_REM_SET` (hepsine aynı değer) |
| Kollektör | `GUNDUZ_KOLLEKTOR_SET`, `GECE_KOLLEKTOR_SET` |
| FCU | `A_BLOK_FCU_SET`, `B_BLOK_FCU_SET` |
| AHU | `ZON1_KLIMA_SANTRALI_SET`, `ZON2_KLIMA_SANTRALI_SET` |

Adresler Supabase `lokasyon_noktalar` tablosundan okunur. Bir nokta o
lokasyonda tanımlı değilse atlanır; hiç nokta yoksa sonuç `nokta_yok`.

---

## 8. Değer kapısı ve komut ömrü

`hvac/deneme/bacnet_writer.py:33-41`

| Eşik | Değer | Ne yapar |
|---|---|---|
| `KOMUT_DEGER_MIN` | **5,0 °C** | Altındaki değer BACnet'e yazılmaz |
| `KOMUT_DEGER_MAX` | **40,0 °C** | Üstündeki değer BACnet'e yazılmaz |
| `KOMUT_OMUR_DK` | **30 dk** | Elle gönderilen komut bu süreden eskiyse uygulanmaz |

NaN / sonsuz / sayı olmayan değerler de reddedilir. Oto-set ile elle gönderilen
komutlar **aynı kapıdan** geçer.

---

## 9. Doğrulama — gönderildi ≠ uygulandı

`oto_set.py:242-244`

| Eşik | Değer | Anlamı |
|---|---|---|
| `ILK_DOGRULAMA_DK` | **3 dk** | Yazmadan sonra ilk geri okumaya kadar beklenen süre |
| `IC_IZLEME_DK` | **15 dk** | Tutmayan nokta bu süre boyunca her dakika yeniden okunur |
| `DOGRULAMA_TOLERANS` | **0,05 °C** | Okunan ile hedef arasındaki kabul edilebilir fark |

Chiller'larda **gerçekleşen** nokta okunur (`CH1_REM_SET` → `CH-1 IC SET`,
`configs/geri_okuma.json`); karşılığı olmayan noktalarda yazılan noktanın
kendisi tekrar okunur.

> Neden gecikmeli: komutu gönderdiğimiz an cihaz yeni değeri henüz almamış
> olur ve **eski** değeri döndürür. Sahada görüldü: CH5'e 6,5 gitti, anında
> IC SET 7,5 okundu. (`oto_set.py:216`)

Sonuç kodları: `dogrulandi` · `uygulanmadi` (okundu ama tutmadı) ·
`okunamadi` (cihaza erişilemedi).

---

## 10. Durma kuralları (sessiz hata üretmemek için)

| Durum | Davranış | Sonuç kodu |
|---|---|---|
| Merkezden kural okunamıyor | Hiçbir şey yapma | `kural_okunamadi` |
| Üç ayardan biri eksik/bozuk | Kuralın tamamı yok sayılır | `kural_okunamadi` |
| Lokasyona özel anahtar var ama bozuk | **Genel değere düşülmez**, beklenir | `kural_okunamadi` |
| Oto-set kapalı | Hiçbir şey yapma | `kapali` |
| Dönem değişmedi | Yalnızca doğrulamayı ilerlet | `gecis_yok` |
| Hava tahmini yok | Geçişi ertele | `tahmin_yok` |
| Başka tur çalışıyor | Turu atla | `mesgul` |

Her tur bir sonuç bırakır; heartbeat bunu Supabase'e taşır ve Synapse kartta
gösterir. (İlk sürümde dört çıkış yolu da sessizce `return` ediyordu; sistem
sahada 10 gün durdu ve kimse fark etmedi.)

---

## 11. Bütün eşikler — tek tablo

| Eşik | Değer | Nerede |
|---|---|---|
| Chiller bölge sınırları | 7 / 23 / 26 °C | `oto_set.py:57` |
| Chiller histerezisi | ±2 °C | `oto_set.py:60` |
| Chiller setleri | 8,0 / 7,5 / 7,0 / 6,5 °C | `oto_set.py:59` |
| Kollektör mod eşikleri | **23 ve 15 °C** | `oto_set.py:79` |
| Kollektör histerezisi | ±3 °C | `oto_set.py:81` |
| Kollektör setleri (gündüz/gece) | >23: 8/10 · 15–23: 10/12 · <15: 12/14 °C | `oto_set.py:82-92` |
| FCU seti | >23: 12 °C · diğer: 14 °C | `oto_set.py:82-92` |
| AHU seti | >23: 8 °C · diğer: 10 °C | `oto_set.py:82-92` |
| Geçiş saatleri | 08:00 / 23:00 | Supabase `ayarlar` |
| Tahmin önbelleği | 30 dk | `oto_set.py:102` |
| İlk doğrulama | 3 dk | `oto_set.py:242` |
| Doğrulama takibi | 15 dk | `oto_set.py:243` |
| Doğrulama toleransı | 0,05 °C | `oto_set.py:244` |
| Yazma alt/üst sınırı | 5 / 40 °C | `bacnet_writer.py:33-34` |
| Komut ömrü | 30 dk | `bacnet_writer.py:41` |

---

## 12. Kuralın tek yerde durması

`hvac/deneme/test_oto_set.py` (159 test) bu kuralların **ikinci bir
kopyasının** oluşmadığını denetler — açıkça `merkez/app_merkez.py` dosyasına
bakıp `CH_SET` / `DIG_SET` / `DIG_ESIK` tanımı ve gömülü set değeri
bulunmadığını doğrular. 01.10.2026'ya kadar merkez aynı eşik tablosunun
kopyasını taşıyordu. Synapse bu değerleri artık sahanın heartbeat'inden
(`durum_ozet()` → `setler.esikler`) okur; tablo değişince portal eski değeri
göstermeye devam etmesin diye.

Bir eşiği değiştirmek için: `oto_set.py`'deki sabiti düzelt → testleri
çalıştır → KURAL 1'e göre lokasyonlara yayınla.
