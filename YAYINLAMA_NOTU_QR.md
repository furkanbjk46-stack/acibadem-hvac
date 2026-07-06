# 📋 YAYINLAMA NOTU — QR Dijital Bakım Kartı Sistemi

> Bu not, `claude/qr-digital-maintenance-cards-3eq56l` branch'indeki QR sistemini
> **evdeki lokal PC'den yayınlamak** için hazırlandı. Sırayla uygula (veya bu
> dosyayı Claude'a ver, adımları o yürütsün). Yayın bitince bu dosya silinebilir.

---

## Bu branch'te ne var? (2 commit)

QR saha etiketi sistemi — sahadaki cihaza yapıştırılan QR okutulunca teknisyenin
telefonunda **merkez portaldaki dijital bakım kartı** açılır (internet yeterli,
hastane ağı gerekmez). Değişiklik lokasyon PC'sine 2 dakikada bir çift yönlü
senkronla iner/çıkar.

Değişen dosyalar:

| Dosya | Ne değişti |
|---|---|
| `merkez/app_merkez.py` | `?bakim=<cihaz>&lok=<lokasyon>` mobil saha sayfası (Supabase `bakim_kartlari` okur/yazar, opsiyonel saha PIN) |
| `merkez/bakim_kartlari_tablo.sql` | Yeni Supabase tablosu — tek seferlik SQL |
| `hvac/deneme/cloud_sync.py` | `sync_bakim_kartlari` — 2 dk'da bir çift yönlü senkron (kart bazında son yazan kazanır) |
| `hvac/deneme/main_portal.py` | Kayıtta kart başına `_updated_at` damgası, `/bakim/{cihaz}` + `/?bakim=` derin bağlantı, `/api/qr-config`, `/api/network-info` |
| `hvac/deneme/static/index.html` | Bakım modalında "QR Etiketleri" paneli → A4 2×4 etiket PDF'i; `?bakim=` ile modal otomatik açılır |
| `hvac/deneme/static/qrcode_generator.js` | **YENİ DOSYA** — QR kütüphanesi (lokal gömülü, internetsiz çalışır) |
| `hvac/deneme/guncelleme_yayinla.py` | İzin listesine `static/qrcode_generator.js` eklendi |

---

## ADIM 1 — main'e merge + push

```bash
git fetch origin
git checkout main
git pull origin main
git merge origin/claude/qr-digital-maintenance-cards-3eq56l
git push origin main
```

Push ile Streamlit Cloud **merkez portalı otomatik deploy eder** (KURAL 2).

## ADIM 2 — Supabase tablosunu oluştur (TEK SEFERLİK)

Supabase Dashboard → **SQL Editor** → `merkez/bakim_kartlari_tablo.sql`
dosyasının içeriğini yapıştır → **Run**.

## ADIM 3 — Yamayı lokasyonlara yayınla (KURAL 1)

Lokal PC'de (supabase_secret.json'un olduğu makine):

```bash
cd hvac/deneme
python guncelleme_yayinla.py
```

- **Versiyon:** `guncellemeler` tablosundaki en yüksek versiyondan **+0.1**
- **Hedef:** her iki lokasyon için ayrı kayıt (önce `2` altunizade, tekrar çalıştır `3` maslak) — ya da `1` (all)
- ⚠️ Merge sonrası working tree temiz olacağı için script "değişen dosya yok —
  tümünü gönder?" diye sorabilir. **Tümünü göndermek yerine** şu 4 dosyayı içeren
  kayıt yeterli (yama mantığı). Script tümünü göndermeyi seçerse de sorun olmaz,
  ama tercihen elle bu 4 dosya gönderilmeli:
  1. `main_portal.py`
  2. `cloud_sync.py` ← **kritik dosya** — lokasyonda TAM restart tetikler (normal)
  3. `static/index.html`
  4. `static/qrcode_generator.js` ← **yeni dosya**, unutma!

## ADIM 4 — (Opsiyonel ama önerilir) Saha PIN'i

Merkez portal internete açık. Streamlit Cloud → App → **Settings → Secrets**:

```toml
[saha]
pin = "1234"   # teknisyenlere verilecek PIN
```

Eklenmezse QR sayfası PIN'siz çalışır.

## ADIM 5 — Etiket adresi (merkez portal URL'si)

QR etiketlerinin içine merkez portalın adresi yazılır. İki seçenek:

- **Kolay yol:** Lokasyon portalında Bakım Kartları → QR Etiketleri panelinde
  adresi bir kez elle gir (`https://<uygulama-adin>.streamlit.app`) — tarayıcı hatırlar.
- **Kalıcı yol:** Her lokasyon PC'sindeki `supabase_config.json` dosyasına ekle:
  `"merkez_url": "https://<uygulama-adin>.streamlit.app"`
  (⚠️ Bu dosya lokasyona özel anahtarlar içerir — `guncellemeler` üzerinden
  toplu ezme, elle/AnyDesk ile ekle.)

## ADIM 6 — Doğrulama kontrol listesi

1. ☐ `guncellemeler` tablosunda kayıtların `durum` alanı ~2-4 dk içinde `tamamlandi` oldu
2. ☐ `bakim_kartlari` tablosunda lokasyonların kartları belirdi (ilk sync sonrası)
3. ☐ Lokasyon portalında Bakım Kartları → **QR Etiketleri → Etiket PDF'i Üret** çalışıyor
4. ☐ Telefonda (mobil veri ile!) QR okutuldu → merkez portalda kart açıldı
5. ☐ Telefondan bir durum değiştirilip kaydedildi → 2-3 dk sonra lokasyon
   portalındaki bakım kartında göründü

---

*Test kapsamı: senkron mantığı 7 senaryoluk sahte-client testinden geçti; rota ve
zaman damgası testleri FastAPI TestClient ile; merkez QR sayfası telefon boyutunda
Playwright ile uçtan uca; QR içeriği jsQR dekoderiyle geri okunarak doğrulandı.*
