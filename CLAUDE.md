# Proje Kuralları — HVAC & Enerji Portalı

## ⚠️ KURAL 1 — Lokasyon Güncelleme Mekanizması (ASLA UNUTMA)

Lokasyonlara (altunizade, maslak vb.) yapılan kod değişiklikleri **Supabase `guncellemeler` tablosu** üzerinden yayınlanır.

### Nasıl çalışır:
- Lokasyon PC'leri internete bağlandığında `guncellemeler` tablosunu kontrol eder
- `durum = 'bekliyor'` olan kayıtları bulur ve ilgili dosyaları otomatik günceller
- `GUNCELLE.bat` USB ile manuel güncelleme için kullanılır (internet yokken)

### Bir dosya değiştirdiğinde yapılacaklar:
1. **Geliştirme dosyasını düzenle** (`hvac/deneme/app_portal.py` vb.)
2. **GitHub'a push et** (main branch)
3. **Supabase `guncellemeler` tablosuna insert et** — her lokasyon için ayrı kayıt:

```python
import zipfile, json, urllib.request

url = 'https://qayjwkqnnjjsnnxovhei.supabase.co'
key = '<service_role_key>'  # supabase_secret.json'dan al

# Her lokasyon için ayrı insert
for hedef in ['altunizade', 'maslak']:
    payload = json.dumps({
        'versiyon': '2.X',          # bir önceki versiyondan +0.1 artır
        'hedef': hedef,             # 'altunizade' veya 'maslak'
        'dosyalar': {
            'app_portal.py': <degisen_dosya_icerigi>
            # Sadece değişen dosyaları ekle — tam paket değil!
        },
        'durum': 'bekliyor'
    }).encode('utf-8')

    req = urllib.request.Request(
        url + '/rest/v1/guncellemeler',
        data=payload,
        headers={
            'apikey': key,
            'Authorization': 'Bearer ' + key,
            'Content-Type': 'application/json',
            'Prefer': 'return=representation'
        },
        method='POST'
    )
    urllib.request.urlopen(req)
```

### Supabase `guncellemeler` tablo yapısı:
| Sütun | Tip | Açıklama |
|-------|-----|----------|
| id | uuid | Otomatik |
| versiyon | text | Ör: "2.6" |
| hedef | text | "altunizade", "maslak" veya "all" |
| dosyalar | jsonb | `{"app_portal.py": "<içerik>", ...}` |
| durum | text | "bekliyor" → lokasyon uygulayınca "tamamlandi" |
| created_at | timestamptz | Otomatik |

### Önemli notlar:
- `dosyalar` alanına **sadece değişen dosyaları** koy (yama mantığı)
- Her lokasyon için **ayrı ayrı** kayıt oluştur (hedef=altunizade, hedef=maslak)
- Versiyon numarası mevcut en yüksek versiyondan **+0.1** artırılır
- `supabase_secret.json` → service_role_key kullan (config'deki publishable key değil)
- Lokasyon zip paketleri: `lokasyonlar/acibadem_altunizade_vX.zip`, `lokasyonlar/acibadem_maslak_vX.zip`

---

## KURAL 2 — GitHub Repo Yapısı

- **main branch** → Streamlit Cloud (GM merkez portal) otomatik deploy eder
- `hvac/deneme/` → Lokasyon programı (Synergy) — dosya rolleri için KURAL 4'e bak
- `lokasyonlar/` → Lokasyon zip paketleri
- `merkez/` → GM merkez portal dosyaları
- `requirements.txt` → Repo kökünde (merkez/ içinde değil)

## ⚠️ KURAL 4 — Hangi İş Hangi Portalda (değişiklikten ÖNCE kontrol et)

Lokasyon PC'sinde **iki ayrı uygulama** çalışır; `portal_watchdog.py` ikisini de başlatır.
Dosya adları yanıltıcıdır: `main_portal` "ana program" değildir.

| Dosya | Uygulama | Port | Buraya yapılan işler |
|---|---|---|---|
| `main_portal.py` | **Mekanik Zeka** (FastAPI) | 8005 | Kural motoru (`determine_effective_mode`, `analyze_ahu_performance`, `check_special_conditions`, `tutarlilik_kontrol`), ΔT/hedef/skor/önem, CONFIG eşikleri, `INSTRUCTION_GUIDE`, `/api/*` uçları, bakım kartı, QR bağlantı, portal giriş ekranı (`/`, `/hvac`, `/enerji`) |
| `static/index.html` | Mekanik Zeka arayüzü | — | Analiz ekranı, talimat penceresi, PDF üretimi |
| `app_portal.py` | **Enerji ve Verimlilik** (Streamlit) | 8501 | Enerji verisi girişi/düzenleme, tarih silme, bildirim banner'ı, tüketim takibi, doğalgaz/elektrik/kojen kalemleri, raporlama ekranları |

**Enerji tarafının yardımcıları:** `data_bridge.py`, `data_collector.py`, `monthly_report/`, `daily_report.py`, `monthly_summary_report.py`

**Ortak altyapı:** `cloud_sync.py`, `oto_set.py`, `bacnet_writer.py`, `ahu_collector.py` (AHU okur → Mekanik Zeka'ya besler), `kilit.py`, `portal_watchdog.py`, `on_kosul.py`, `bakim_durum.py`

**Kural:** Bir geliştirme/değişiklik istendiğinde ÖNCE işin hangi tarafa ait olduğu tespit edilir, doğru dosya düzeltilir, yama KURAL 1'e göre o dosyayla yayınlanır. Enerji işi `main_portal`'a, mekanik kuralı `app_portal`'a yazılmaz.

---

## KURAL 3 — Bağımlılıklar

- `kaleido` **kullanma** — Streamlit Cloud'da çalışmıyor
- Grafikler için `matplotlib` kullan (PDF içinde)
- PDF için `fpdf2` kullan (DejaVu font ile Türkçe karakter desteği)
