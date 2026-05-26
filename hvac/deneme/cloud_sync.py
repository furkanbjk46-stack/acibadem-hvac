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
from datetime import datetime, date

logging.basicConfig(level=logging.INFO, format='%(asctime)s [SYNC] %(message)s')
logger = logging.getLogger(__name__)

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "supabase_config.json")
DATA_FILE = os.path.join(os.path.dirname(__file__), "energy_data.csv")
HVAC_FILE = os.path.join(os.path.dirname(__file__), "hvac_analysis_history.csv")
HVAC_SON_CALISMA_FILE = os.path.join(os.path.dirname(__file__), "hvac_son_calisma.txt")


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

        # Güvenli sync: önce mevcut ID'leri al, sonra yeni veriyi insert et,
        # insert başarılıysa eski ID'leri sil — insert fail olursa eski veri korunur
        mevcut = client.table("energy_data").select("id").eq("lokasyon_id", lokasyon_id).execute()
        eski_idler = [r["id"] for r in (mevcut.data or [])]

        batch_size = 500
        total = 0
        for i in range(0, len(clean_records), batch_size):
            batch = clean_records[i:i + batch_size]
            client.table("energy_data").insert(batch).execute()
            total += len(batch)

        # Insert tamamen başarılıysa eski kayıtları temizle
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
    """Supabase'de bekleyen güncelleme varsa uygula"""
    try:
        r = client.table("guncellemeler") \
            .select("*") \
            .eq("durum", "bekliyor") \
            .in_("hedef", [lokasyon_id, "all"]) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()

        if not r.data:
            return

        kayit = r.data[0]
        kayit_id = kayit["id"]
        versiyon = kayit.get("versiyon", "?")
        dosyalar = kayit.get("dosyalar", {})

        logger.info(f"🔄 Güncelleme bulundu: v{versiyon} ({len(dosyalar)} dosya) — uygulanıyor...")

        base_dir = os.path.dirname(__file__)
        uygulanan = 0
        hatalar = []

        for dosya_yolu, icerik in dosyalar.items():
            try:
                tam_yol = os.path.join(base_dir, dosya_yolu)
                os.makedirs(os.path.dirname(tam_yol), exist_ok=True)
                with open(tam_yol, "w", encoding="utf-8") as f:
                    f.write(icerik)
                uygulanan += 1
                logger.info(f"  ✅ {dosya_yolu}")
            except Exception as e:
                hatalar.append(dosya_yolu)
                logger.error(f"  ❌ {dosya_yolu}: {e}")

        # Durumu güncelle (sadece mevcut kolon, ek kolon gerekmez)
        yeni_durum = "tamamlandi" if not hatalar else "hata"
        client.table("guncellemeler").update({
            "durum": yeni_durum,
        }).eq("id", kayit_id).execute()

        logger.info(f"✅ Güncelleme tamamlandı: v{versiyon} — {uygulanan} dosya uygulandı")

        # Kritik dosya değiştiyse tam yeniden başlatma gerekir
        KRITIK_DOSYALAR = {"cloud_sync.py", "portal_watchdog.py"}
        tam_restart = bool(set(dosyalar.keys()) & KRITIK_DOSYALAR)

        if tam_restart:
            flag_path = os.path.join(os.path.dirname(__file__), "_full_restart.flag")
            logger.info("🔄 Kritik dosya güncellendi — TAM yeniden başlatma sinyali gönderildi (_full_restart.flag)")
        else:
            flag_path = os.path.join(os.path.dirname(__file__), "_restart.flag")
            logger.info("🔄 Yeniden başlatma sinyali gönderildi (_restart.flag)")

        with open(flag_path, "w") as f:
            f.write(f"v{versiyon} - {datetime.now().isoformat()}")

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

    interval = config.get("sync_interval_minutes", 240) * 60  # dakika → saniye (varsayılan 4 saat)
    auto_sync = config.get("auto_sync", True)

    if not auto_sync:
        logger.info("Otomatik senkronizasyon kapalı (supabase_config.json)")
        return

    lokasyon_id = config.get("lokasyon_id", "bilinmeyen")
    client = get_supabase_client(config)

    def _sync_loop():
        while True:
            try:
                run_sync()
            except Exception as e:
                logger.error(f"Senkronizasyon döngüsü hatası: {e}")
            time.sleep(interval)

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

    # HVAC günlük analiz saati (08:30)
    _HVAC_SAAT   = 8
    _HVAC_DAKIKA = 30

    def _hvac_son_gun_oku():
        """Disk'ten son HVAC çalışma tarihini oku — program restart'ına karşı kalıcı."""
        try:
            if os.path.exists(HVAC_SON_CALISMA_FILE):
                with open(HVAC_SON_CALISMA_FILE, "r") as f:
                    return datetime.strptime(f.read().strip(), "%Y-%m-%d").date()
        except Exception:
            pass
        return None

    def _hvac_son_gun_yaz(tarih):
        """Son HVAC çalışma tarihini disk'e yaz."""
        try:
            with open(HVAC_SON_CALISMA_FILE, "w") as f:
                f.write(tarih.strftime("%Y-%m-%d"))
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
                    # Her 2 turda bir: heartbeat + güncelleme kontrolü
                    if _tick % 2 == 0:
                        send_heartbeat(client, lokasyon_id)
                        check_and_apply_update(client, lokasyon_id)
                    # Günlük HVAC analizi: saat 08:30'da, günde 1 kez
                    # _hvac_son_gun DOSYAYA yazılır — program restart'ta tekrar çalışmaz
                    if _ahu_ok:
                        _now = datetime.now()
                        _bugun = _now.date()
                        _saat_tamam = (
                            _now.hour == _HVAC_SAAT and
                            _HVAC_DAKIKA <= _now.minute < _HVAC_DAKIKA + 5
                        )
                        if _saat_tamam and _hvac_son_gun_oku() != _bugun:
                            _hvac_son_gun_yaz(_bugun)  # önce yaz — tekrar tetiklenmesin
                            try:
                                logger.info("⏰ 08:30 HVAC AHU analizi başlatılıyor...")
                                _hvac_analiz()
                            except Exception as _ae:
                                logger.error("HVAC analiz hatası: %s", _ae)
                    _tick += 1
            except Exception as e:
                logger.warning(f"Heartbeat döngüsü hatası: {e}")
            time.sleep(60)  # 1 dakika

    t_sync = threading.Thread(target=_sync_loop, daemon=True, name="cloud-sync")
    t_sync.start()

    t_hb = threading.Thread(target=_heartbeat_loop, daemon=True, name="heartbeat")
    t_hb.start()

    logger.info(f"🔄 Arka plan senkronizasyonu başlatıldı (her {interval // 60} dakika, heartbeat: 2 dk)")


# ============ Manuel / Subprocess çalıştırma ============
if __name__ == "__main__":
    print("=" * 50)
    print("  HVAC Enerji Sistemi — Bulut Senkronizasyonu")
    print("=" * 50)

    # Önce bir kerelik tam sync yap
    run_sync()

    # Sonra arka plan döngüsünü başlat (heartbeat + güncelleme kontrolü)
    start_background_sync()

    # Ana thread canlı kalsın (daemon thread'ler ölmesin)
    try:
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\nCloud Sync durduruldu.")
