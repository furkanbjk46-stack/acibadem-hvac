# cloud_sync.py
# Lokasyondan Supabase'e enerji verisi senkronizasyonu
# Bu dosya her lokasyonun acıbadem/ klasörüne kopyalanır

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

import json
import os
import time
import threading
import logging
from datetime import datetime, date, timezone

logging.basicConfig(level=logging.INFO, format='%(asctime)s [SYNC] %(message)s')
logger = logging.getLogger(__name__)

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "supabase_config.json")
DATA_FILE = os.path.join(os.path.dirname(__file__), "energy_data.csv")
HVAC_FILE = os.path.join(os.path.dirname(__file__), "hvac_analysis_history.csv")
HVAC_SON_CALISMA_FILE = os.path.join(os.path.dirname(__file__), "hvac_son_calisma.txt")
ALARM_RAPORU_SON_AY_FILE = os.path.join(os.path.dirname(__file__), "alarm_raporu_son_ay.txt")


def load_config():
    """Supabase config dosyasını oku"""
    if not os.path.exists(CONFIG_FILE):
        logger.error(f"Config dosyası bulunamadı: {CONFIG_FILE}")
        return None
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def get_supabase_client(config):
    """Supabase client oluştur"""
    try:
        from supabase import create_client
        url = config["supabase_url"]
        key = config["supabase_key"]
        if "BURAYA" in url or "BURAYA" in key:
            logger.error("supabase_config.json içindeki URL ve KEY değerleri henüz ayarlanmamış!")
            return None
        return create_client(url, key)
    except ImportError:
        logger.error("supabase kütüphanesi yüklü değil! pip install supabase")
        return None
    except Exception as e:
        logger.error(f"Supabase bağlantı hatası: {e}")
        return None


def sync_energy_data(client, lokasyon_id: str):
    """energy_data.csv içeriğini Supabase'e gönder"""
    import pandas as pd

    if not os.path.exists(DATA_FILE):
        logger.warning("energy_data.csv bulunamadı, atlanıyor.")
        return 0

    try:
        df = pd.read_csv(DATA_FILE)
        if df.empty:
            logger.info("energy_data.csv boş.")
            return 0

        # Tarih sütununu string'e çevir
        if "Tarih" in df.columns:
            df["Tarih"] = pd.to_datetime(df["Tarih"], errors="coerce").dt.strftime("%Y-%m-%d")
            df = df.dropna(subset=["Tarih"])

        # Tarih bazlı tekilleştir — aynı tarihin birden fazla satırı varsa son olanı tut
        once = len(df)
        if "Tarih" in df.columns:
            df = df.drop_duplicates(subset=["Tarih"], keep="last")
        else:
            df = df.drop_duplicates()
        if len(df) < once:
            logger.info(f"🧹 Tarih bazlı tekilleştirme: {once} → {len(df)} satır ({once - len(df)} kopya temizlendi)")

        # NaN değerleri None yap (JSON uyumlu)
        import math
        df = df.where(df.notna(), None)
        # Float NaN ve Inf temizle
        for col in df.columns:
            if df[col].dtype in ['float64', 'float32']:
                df[col] = df[col].apply(lambda x: None if (x is not None and isinstance(x, float) and (math.isnan(x) or math.isinf(x))) else x)

        # Her satıra lokasyon_id ekle
        df["lokasyon_id"] = lokasyon_id

        records = df.to_dict(orient="records")

        # Float/int dönüşüm (numpy tiplerini standart Python'a çevir + NaN temizle)
        clean_records = []
        for r in records:
            clean = {}
            for k, v in r.items():
                if v is None:
                    clean[k] = None
                elif hasattr(v, 'item'):  # numpy scalar
                    val = v.item()
                    if isinstance(val, float) and (math.isnan(val) or math.isinf(val)):
                        clean[k] = None
                    else:
                        clean[k] = val
                elif isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    clean[k] = None
                else:
                    clean[k] = v
            clean_records.append(clean)

        # Güvenli sync: önce mevcut ID'leri sayfalayarak al (1000 limit yok),
        # insert et, sonra eski ID'leri toplu sil
        eski_idler = []
        offset = 0
        while True:
            r = client.table("energy_data").select("id") \
                .eq("lokasyon_id", lokasyon_id) \
                .range(offset, offset + 999) \
                .execute()
            if not r.data:
                break
            eski_idler.extend([x["id"] for x in r.data])
            if len(r.data) < 1000:
                break
            offset += 1000

        # GÜVENLIK KORUMASI: Yerel CSV bozuk/kısmi (örn. crash sonrası truncate)
        # olduğunda, eldeki satır sayısı buluttaki kayıt sayısının yarısından azsa
        # senkronizasyonu İPTAL et — yoksa eski geçmiş silinip kalıcı veri kaybı olur.
        if eski_idler and len(clean_records) < len(eski_idler) * 0.5:
            logger.error(
                "⛔ SYNC IPTAL (%s): yerel %d satır, bulutta %d kayıt — kısmi/bozuk CSV "
                "şüphesi, veri kaybını önlemek için silme yapılmadı.",
                lokasyon_id, len(clean_records), len(eski_idler)
            )
            return 0

        batch_size = 500
        total = 0
        for i in range(0, len(clean_records), batch_size):
            batch = clean_records[i:i + batch_size]
            client.table("energy_data").insert(batch).execute()
            total += len(batch)

        # Insert başarılıysa eski ID'leri toplu sil
        if eski_idler:
            for i in range(0, len(eski_idler), 500):
                client.table("energy_data").delete().in_("id", eski_idler[i:i+500]).execute()
            logger.info(f"🗑️ Eski {len(eski_idler)} kayıt temizlendi ({lokasyon_id})")

        logger.info(f"✅ Enerji verisi senkronize edildi: {total} satır ({lokasyon_id})")
        return total

    except Exception as e:
        logger.error(f"Enerji senkronizasyon hatası: {e}")
        return 0


def sync_hvac_summary(client, lokasyon_id: str):
    """HVAC analiz gecmisinin son 30 gunluk ozetini JSONB olarak gonder"""
    import pandas as pd

    if not os.path.exists(HVAC_FILE):
        logger.info("hvac_analysis_history.csv bulunamadi, atlaniyor.")
        return 0

    try:
        df = pd.read_csv(HVAC_FILE)
        if df.empty:
            return 0

        # Son 30 gunu al
        if "Tarih" in df.columns:
            df["Tarih"] = pd.to_datetime(df["Tarih"], errors="coerce")
            cutoff = datetime.now() - pd.Timedelta(days=30)
            df = df[df["Tarih"] >= cutoff]
            df["Tarih"] = df["Tarih"].dt.strftime("%Y-%m-%d")

        df = df.where(df.notna(), None)

        import math
        # Her satiri JSONB olarak paketle (tablo yapisi esnek)
        clean_records = []
        for _, row in df.iterrows():
            tarih = row.get("Tarih", None)
            row_dict = {}
            for k, v in row.items():
                if k == "Tarih":
                    continue
                if v is None:
                    continue
                if hasattr(v, 'item'):
                    v = v.item()
                if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                    continue
                row_dict[k] = v
            
            clean_records.append({
                "lokasyon_id": lokasyon_id,
                "Tarih": tarih,
                "veri": json.dumps(row_dict, ensure_ascii=False)
            })

        # Eski veriyi sil, yenisini ekle
        client.table("hvac_summary").delete().eq("lokasyon_id", lokasyon_id).execute()

        batch_size = 500
        total = 0
        for i in range(0, len(clean_records), batch_size):
            batch = clean_records[i:i + batch_size]
            client.table("hvac_summary").insert(batch).execute()
            total += len(batch)

        logger.info(f"HVAC ozeti senkronize edildi: {total} satir ({lokasyon_id})")
        return total

    except Exception as e:
        logger.error(f"HVAC senkronizasyon hatasi: {e}")
        return 0


def check_and_apply_update(client, lokasyon_id: str):
    """Supabase'de bekleyen güncellemeleri KRONOLOJIK sırayla TÜMÜNÜ uygula.

    Eski davranış (limit(1) + en yeni kayıt) birden fazla bekleyen kayıt
    biriktiğinde yalnız sonuncusunu uygulayıp diğerlerini sonsuza dek
    'bekliyor' bırakıyordu — aradaki yamaların içeriği kayboluyordu.
    Artık tüm bekleyenler eskiden yeniye uygulanır (aynı dosya birden fazla
    kayıtta varsa son yazılan — en yeni — kazanır), restart bayrağı en sonda
    bir kez yazılır.
    """
    try:
        r = client.table("guncellemeler") \
            .select("*") \
            .eq("durum", "bekliyor") \
            .in_("hedef", [lokasyon_id, "all"]) \
            .order("created_at", desc=False) \
            .execute()

        if not r.data:
            return

        base_dir = os.path.dirname(__file__)
        tum_dosyalar = set()   # restart kararı için (tüm kayıtların birleşimi)
        son_versiyon = "?"

        logger.info(f"🔄 {len(r.data)} bekleyen güncelleme bulundu — kronolojik sırayla uygulanıyor...")

        for kayit in r.data:
            kayit_id = kayit["id"]
            versiyon = kayit.get("versiyon", "?")
            dosyalar = kayit.get("dosyalar", {})
            son_versiyon = versiyon

            logger.info(f"🔄 v{versiyon} uygulanıyor ({len(dosyalar)} dosya)...")

            uygulanan = 0
            hatalar = []

            for dosya_yolu, icerik in dosyalar.items():
                try:
                    tam_yol = os.path.join(base_dir, dosya_yolu)
                    # Boş içerik = dosyayı sil
                    if icerik == "":
                        if os.path.exists(tam_yol):
                            os.remove(tam_yol)
                            logger.info(f"  🗑️ {dosya_yolu} silindi")
                        uygulanan += 1
                        tum_dosyalar.add(dosya_yolu)
                        continue
                    os.makedirs(os.path.dirname(tam_yol), exist_ok=True)
                    with open(tam_yol, "w", encoding="utf-8") as f:
                        f.write(icerik)
                    uygulanan += 1
                    tum_dosyalar.add(dosya_yolu)
                    logger.info(f"  ✅ {dosya_yolu}")
                except Exception as e:
                    hatalar.append(dosya_yolu)
                    logger.error(f"  ❌ {dosya_yolu}: {e}")

            # Durumu güncelle (sadece mevcut kolon, ek kolon gerekmez)
            yeni_durum = "tamamlandi" if not hatalar else "hata"
            client.table("guncellemeler").update({
                "durum": yeni_durum,
            }).eq("id", kayit_id).execute()

            logger.info(f"✅ v{versiyon} tamamlandı — {uygulanan} dosya uygulandı")

        # Kritik dosya değiştiyse tam yeniden başlatma gerekir (tek sefer, en sonda)
        KRITIK_DOSYALAR = {"cloud_sync.py", "portal_watchdog.py"}
        tam_restart = bool(tum_dosyalar & KRITIK_DOSYALAR)

        if tam_restart:
            flag_path = os.path.join(os.path.dirname(__file__), "_full_restart.flag")
            logger.info("🔄 Kritik dosya güncellendi — TAM yeniden başlatma sinyali gönderildi (_full_restart.flag)")
        else:
            flag_path = os.path.join(os.path.dirname(__file__), "_restart.flag")
            logger.info("🔄 Yeniden başlatma sinyali gönderildi (_restart.flag)")

        with open(flag_path, "w") as f:
            f.write(f"v{son_versiyon} - {datetime.now().isoformat()}")

    except Exception as e:
        logger.error(f"Güncelleme kontrol hatası: {e}")


def get_bakim_ozet() -> dict:
    """configs/maintenance_cards.json dosyasından arıza özetini çıkar."""
    BILESEN_ETIKET = {
        "heating_valve_body":   "Isıtma Vanası Gövde",
        "heating_valve_signal": "Isıtma Vanası 0-10V",
        "cooling_valve_body":   "Soğutma Vanası Gövde",
        "cooling_valve_signal": "Soğutma Vanası 0-10V",
        "supply_sensor":        "Üfleme Sensör",
        "return_sensor":        "Emiş Sensör",
    }
    try:
        mc_file = os.path.join(os.path.dirname(__file__), "configs", "maintenance_cards.json")
        if not os.path.exists(mc_file):
            return {}
        with open(mc_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        cards = data.get("cards", {})
        toplam_ariza = 0
        toplam_bakim = 0
        arizali_cihazlar = []
        bakimda_cihazlar = []
        for cihaz, bilesenler in cards.items():
            ariza_listesi = [
                BILESEN_ETIKET.get(k, k)
                for k, v in bilesenler.items()
                if v == "FAULTY" and k != "note"
            ]
            bakim_listesi = [
                BILESEN_ETIKET.get(k, k)
                for k, v in bilesenler.items()
                if v == "MAINTENANCE" and k != "note"
            ]
            not_metni = bilesenler.get("note", "")
            toplam_ariza += len(ariza_listesi)
            toplam_bakim += len(bakim_listesi)
            if ariza_listesi:
                arizali_cihazlar.append({
                    "ad":        cihaz,
                    "bilesenler": ariza_listesi,
                    "not":       not_metni,
                })
            if bakim_listesi:
                bakimda_cihazlar.append({
                    "ad":        cihaz,
                    "bilesenler": bakim_listesi,
                    "not":       not_metni,
                })
        return {
            "toplam_ariza": toplam_ariza,
            "toplam_bakim": toplam_bakim,
            "toplam_sorun": toplam_ariza + toplam_bakim,
            "cihaz_sayisi": len(cards),
            "arizali_cihazlar": arizali_cihazlar,
            "bakimda_cihazlar": bakimda_cihazlar,
            "son_guncelleme": data.get("last_updated", ""),
        }
    except Exception as e:
        logger.warning(f"Bakım kartı okuma hatası: {e}")
        return {}


def _ts_parse(s) -> datetime:
    """ISO zaman damgasını timezone-aware datetime'a çevir (bozuksa epoch 0)."""
    try:
        dt = datetime.fromisoformat(str(s or "").replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)


def sync_bakim_kartlari(client, lokasyon_id: str):
    """Bakım kartlarını Supabase `bakim_kartlari` tablosuyla ÇİFT YÖNLÜ senkronize et.

    - Kart bazında son-yazan-kazanır (yerel `_updated_at` vs bulut `updated_at`).
    - Cihaz listesinin sahibi YEREL portaldır: yerelde olmayan cihazın bulut
      satırı silinir (sahadan QR ile sadece MEVCUT kartlar düzenlenir).
    - Sahadan (merkez portal QR sayfası) yapılan değişiklikler yerel
      maintenance_cards.json dosyasına indirilir → analiz motoru anında görür.
    """
    mc_file = os.path.join(os.path.dirname(__file__), "configs", "maintenance_cards.json")
    try:
        data = {"last_updated": None, "updated_by": None, "cards": {}}
        if os.path.exists(mc_file):
            with open(mc_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        cards = data.get("cards", {}) or {}

        r = client.table("bakim_kartlari") \
            .select("cihaz,kart,updated_at") \
            .eq("lokasyon_id", lokasyon_id) \
            .range(0, 999).execute()
        bulut = {x["cihaz"]: x for x in (r.data or [])}

        yerel_degisti = False
        simdi = datetime.now(timezone.utc).isoformat()

        # 1) Yerel → Bulut (yeni veya yerelde daha güncel kartlar)
        for cihaz, kart in cards.items():
            if not isinstance(kart, dict):
                continue
            yerel_ts = _ts_parse(kart.get("_updated_at"))
            bulut_satir = bulut.get(cihaz)
            bulut_ts = _ts_parse(bulut_satir["updated_at"]) if bulut_satir else None
            if bulut_satir is None or yerel_ts > bulut_ts:
                gonder_ts = kart.get("_updated_at") or simdi
                if not kart.get("_updated_at"):
                    kart["_updated_at"] = gonder_ts
                    yerel_degisti = True
                client.table("bakim_kartlari").upsert({
                    "lokasyon_id": lokasyon_id,
                    "cihaz": cihaz,
                    "kart": {k: v for k, v in kart.items() if k != "_updated_at"},
                    "updated_at": gonder_ts,
                    "updated_by": "lokasyon",
                }, on_conflict="lokasyon_id,cihaz").execute()
                logger.info(f"🔧 Bakım kartı buluta gönderildi: {cihaz}")

        # 2) Bulut → Yerel (sahadan QR ile güncellenen kartlar)
        for cihaz, satir in bulut.items():
            if cihaz not in cards:
                continue  # aşağıda silinecek
            yerel_ts = _ts_parse(cards[cihaz].get("_updated_at") if isinstance(cards[cihaz], dict) else None)
            bulut_ts = _ts_parse(satir.get("updated_at"))
            if bulut_ts > yerel_ts:
                yeni = dict(satir.get("kart") or {})
                yeni["_updated_at"] = satir.get("updated_at")
                cards[cihaz] = yeni
                yerel_degisti = True
                logger.info(f"🔧 Bakım kartı sahadan indirildi: {cihaz}")

        # 3) Yerelde silinen cihazların bulut satırlarını temizle
        #    (GÜVENLİK: yerel dosya boşsa dokunma — dosya kaybı/yeni kurulum olabilir)
        silinecek = [c for c in bulut if c not in cards]
        if silinecek and cards:
            client.table("bakim_kartlari").delete() \
                .eq("lokasyon_id", lokasyon_id).in_("cihaz", silinecek).execute()
            logger.info(f"🗑️ Bulut bakım kartı silindi (yerelde yok): {', '.join(silinecek)}")

        if yerel_degisti:
            data["cards"] = cards
            data["last_updated"] = datetime.now().isoformat()
            data["updated_by"] = "saha-qr"
            with open(mc_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.warning(f"Bakım kartı senkronizasyon hatası: {e}")


def send_heartbeat(client, lokasyon_id: str):
    """Supabase'e kısa heartbeat gönder (her 2 dakikada bir çağrılır)"""
    try:
        payload = {
            "lokasyon_id": lokasyon_id,
            "ping_zamani": datetime.now().isoformat(),
            "durum": "online",
            "bakim_ozet": get_bakim_ozet(),
        }
        client.table("lokasyonlar").upsert(payload, on_conflict="lokasyon_id").execute()
        logger.debug(f"💓 Heartbeat gönderildi: {lokasyon_id}")
    except Exception as e:
        logger.warning(f"Heartbeat hatası: {e}")


def sync_location_info(client, lokasyon_id: str):
    """Lokasyon durum bilgisini güncelle"""
    try:
        from location_manager import get_manager
        mgr = get_manager()
        loc_config = mgr.get_location_config()

        info = {
            "lokasyon_id": lokasyon_id,
            "isim": loc_config.get("name", lokasyon_id),
            "son_sync": datetime.now().isoformat(),
            "ping_zamani": datetime.now().isoformat(),
            "versiyon": "2.0",
            "durum": "online"
        }

        # Upsert (varsa güncelle, yoksa ekle)
        client.table("lokasyonlar").upsert(info, on_conflict="lokasyon_id").execute()
        logger.info(f"✅ Lokasyon bilgisi güncellendi: {lokasyon_id}")
    except Exception as e:
        logger.error(f"Lokasyon bilgisi güncelleme hatası: {e}")


def run_sync():
    """Tek seferlik tam senkronizasyon"""
    config = load_config()
    if not config:
        return False

    client = get_supabase_client(config)
    if not client:
        return False

    lokasyon_id = config.get("lokasyon_id", "bilinmeyen")
    logger.info(f"🔄 Senkronizasyon başlıyor: {lokasyon_id}")

    # Energy sync devre dışı flag kontrolü
    _sync_flag = os.path.join(os.path.dirname(__file__), "_sync_disabled.flag")
    if os.path.exists(_sync_flag):
        logger.info("⏸️ Energy sync devre dışı (_sync_disabled.flag mevcut) — atlanıyor")
        sync_location_info(client, lokasyon_id)
        return True

    sync_energy_data(client, lokasyon_id)
    sync_hvac_summary(client, lokasyon_id)
    sync_location_info(client, lokasyon_id)

    logger.info(f"✅ Senkronizasyon tamamlandı: {lokasyon_id}")
    return True


def start_background_sync():
    """Arka planda periyodik senkronizasyon ve heartbeat başlat"""
    config = load_config()
    if not config:
        return

    auto_sync = config.get("auto_sync", True)

    if not auto_sync:
        logger.info("Otomatik senkronizasyon kapalı (supabase_config.json)")
        return

    lokasyon_id = config.get("lokasyon_id", "bilinmeyen")
    client = get_supabase_client(config)

    # Günlük sync saati: 08:00
    _SYNC_SAAT   = 8
    _SYNC_DAKIKA = 0
    _SYNC_SON_FILE = os.path.join(os.path.dirname(__file__), "sync_son_calisma.txt")

    def _sync_son_gun_oku():
        try:
            if os.path.exists(_SYNC_SON_FILE):
                with open(_SYNC_SON_FILE, "r") as f:
                    return datetime.strptime(f.read().strip(), "%Y-%m-%d").date()
        except Exception:
            pass
        return None

    def _sync_son_gun_yaz(tarih):
        try:
            with open(_SYNC_SON_FILE, "w") as f:
                f.write(tarih.strftime("%Y-%m-%d"))
        except Exception:
            pass

    def _sync_loop():
        """Her gün saat 08:00'de bir kez çalışır."""
        while True:
            try:
                _now = datetime.now()
                _bugun = _now.date()
                _saat_tamam = (
                    _now.hour == _SYNC_SAAT and
                    _SYNC_DAKIKA <= _now.minute < _SYNC_DAKIKA + 5
                )
                if _saat_tamam and _sync_son_gun_oku() != _bugun:
                    _sync_son_gun_yaz(_bugun)
                    logger.info("⏰ 08:00 Günlük Supabase sync başlatılıyor...")
                    run_sync()
            except Exception as e:
                logger.error(f"Senkronizasyon döngüsü hatası: {e}")
            time.sleep(60)

    # BACnet yazıcıyı import et (yoksa sessizce atla)
    try:
        from bacnet_writer import komutlari_isle as _komutlari_isle
        _bacnet_writer_ok = True
    except Exception:
        _bacnet_writer_ok = False

    # HVAC AHU analiz modülünü import et (yoksa sessizce atla)
    try:
        from ahu_collector import hvac_analiz_calistir as _hvac_analiz
        _ahu_ok = True
    except Exception:
        _ahu_ok = False

    _sb_url = config.get("supabase_url", "")
    _sb_key = config.get("supabase_key", "")

    # HVAC analiz periyodu (dakika) — canlı üretim/talep grafiği için sık çalışır
    _HVAC_PERIYOT_DK = 10

    def _hvac_son_calisma_oku():
        """Disk'ten son HVAC çalışma zamanını oku — program restart'ına karşı kalıcı."""
        try:
            if os.path.exists(HVAC_SON_CALISMA_FILE):
                with open(HVAC_SON_CALISMA_FILE, "r") as f:
                    return datetime.strptime(f.read().strip(), "%Y-%m-%d %H:%M:%S")
        except Exception:
            pass
        return None

    def _hvac_son_calisma_yaz(zaman):
        """Son HVAC çalışma zamanını disk'e yaz."""
        try:
            with open(HVAC_SON_CALISMA_FILE, "w") as f:
                f.write(zaman.strftime("%Y-%m-%d %H:%M:%S"))
        except Exception:
            pass

    def _heartbeat_loop():
        """Her 1 dakikada bir: heartbeat + güncelleme kontrolü + BACnet komut polling + HVAC analiz"""
        _tick = 0
        while True:
            try:
                if client:
                    # Her turda: BACnet komut polling (≈1 dk aralık)
                    if _bacnet_writer_ok and _sb_url and _sb_key:
                        _komutlari_isle(_sb_url, _sb_key, lokasyon_id)
                    # Her 2 turda bir: heartbeat + güncelleme kontrolü + bakım kartı sync
                    if _tick % 2 == 0:
                        send_heartbeat(client, lokasyon_id)
                        check_and_apply_update(client, lokasyon_id)
                        sync_bakim_kartlari(client, lokasyon_id)
                    # HVAC analizi: her _HVAC_PERIYOT_DK dakikada bir
                    # son çalışma zamanı DOSYAYA yazılır — program restart'ta tekrar tetiklenmez
                    if _ahu_ok:
                        _now = datetime.now()
                        _son_calisma = _hvac_son_calisma_oku()
                        _periyot_gecti = (
                            _son_calisma is None or
                            (_now - _son_calisma).total_seconds() >= _HVAC_PERIYOT_DK * 60
                        )
                        if _periyot_gecti:
                            _hvac_son_calisma_yaz(_now)  # önce yaz — tekrar tetiklenmesin
                            try:
                                logger.info("⏰ HVAC AHU analizi başlatılıyor...")
                                _hvac_analiz()
                            except Exception as _ae:
                                logger.error("HVAC analiz hatası: %s", _ae)

                    # Ay sonu AHU alarm tekrar raporu: her ayın 1'inde, günde 1 kez
                    # önceki ayın raporunu otomatik PDF olarak üretir
                    _now2 = datetime.now()
                    if _now2.day == 1:
                        _ay_etiketi = _now2.strftime("%Y-%m")
                        _son_uretilen = ""
                        try:
                            if os.path.exists(ALARM_RAPORU_SON_AY_FILE):
                                with open(ALARM_RAPORU_SON_AY_FILE, "r") as _f:
                                    _son_uretilen = _f.read().strip()
                        except Exception:
                            pass
                        if _son_uretilen != _ay_etiketi:
                            try:
                                from monthly_report.ahu_alarm_pdf import olustur as _alarm_pdf_olustur
                                _onceki_ay = _now2.month - 1 or 12
                                _onceki_yil = _now2.year if _now2.month > 1 else _now2.year - 1
                                _yol = _alarm_pdf_olustur(_onceki_yil, _onceki_ay)
                                logger.info("📄 Ay sonu AHU alarm raporu oluşturuldu: %s", _yol)
                            except Exception as _pe:
                                logger.error("Ay sonu alarm raporu hatası: %s", _pe)
                            try:
                                with open(ALARM_RAPORU_SON_AY_FILE, "w") as _f:
                                    _f.write(_ay_etiketi)
                            except Exception:
                                pass

                    _tick += 1
            except Exception as e:
                logger.warning(f"Heartbeat döngüsü hatası: {e}")
            time.sleep(60)  # 1 dakika

    t_sync = threading.Thread(target=_sync_loop, daemon=True, name="cloud-sync")
    t_sync.start()

    t_hb = threading.Thread(target=_heartbeat_loop, daemon=True, name="heartbeat")
    t_hb.start()

    logger.info(f"🔄 Arka plan senkronizasyonu başlatıldı (günlük {_SYNC_SAAT:02d}:{_SYNC_DAKIKA:02d}, heartbeat: 2 dk)")


# ============ Manuel / Subprocess çalıştırma ============
if __name__ == "__main__":
    print("=" * 50)
    print("  HVAC Enerji Sistemi — Bulut Senkronizasyonu")
    print("=" * 50)

    # NOT: Startup'ta run_sync() ÇAĞIRILMAZ.
    # Sync zamanlaması _sync_loop tarafından (sync_son_calisma.txt ile) yönetilir.
    # Bu sayede restart/güncelleme sonrasında çift sync olmaz.
    start_background_sync()

    # Ana thread canlı kalsın (daemon thread'ler ölmesin)
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nCloud Sync durduruldu.")
