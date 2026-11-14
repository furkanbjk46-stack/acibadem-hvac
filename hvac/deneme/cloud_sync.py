# cloud_sync.py
# Lokasyondan Supabase'e enerji verisi senkronizasyonu
# Bu dosya her lokasyonun acıbadem/ klasörüne kopyalanır

import yollar  # dosya yolları (ayar/ durum/ veri/; Faz 1)
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
import re
from datetime import datetime, date, timezone

logging.basicConfig(level=logging.INFO, format='%(asctime)s [SYNC] %(message)s')
logger = logging.getLogger(__name__)

# ── LOG DOSYASI ───────────────────────────────────────────────────────────
# cloud_sync watchdog tarafından arka planda başlatılıyor; konsolu kimse
# görmüyordu. Bir arıza olduğunda (örn. oto-set'in sessizce durması) sahada
# bakılacak hiçbir iz kalmıyordu. Log artık dosyaya da yazılır ve döner:
# 2 MB'ta yenilenir, 3 yedek tutulur — disk şişmez.
try:
    from logging.handlers import RotatingFileHandler as _RFH
    _LOG_DOSYA = yollar.yol("cloud_sync.log", os.path.dirname(__file__))
    _fh = _RFH(_LOG_DOSYA, maxBytes=2_000_000, backupCount=3, encoding="utf-8")
    _fh.setFormatter(logging.Formatter('%(asctime)s [SYNC] %(levelname)s %(message)s'))
    logging.getLogger().addHandler(_fh)
except Exception as _le:      # log kurulamazsa program yine de çalışmalı
    logger.warning(f"Log dosyasi kurulamadi: {_le}")
# Uyarı / hata özeti: log 3 gün tutuyor; gün gün özet 30 gün durur ve merkeze gider (N5)
try:
    import hata_ozeti
    hata_ozeti.kur("sync")
except Exception:
    hata_ozeti = None

CONFIG_FILE = yollar.yol("supabase_config.json", os.path.dirname(__file__))
DATA_FILE = yollar.yol("energy_data.csv", os.path.dirname(__file__))
HVAC_FILE = yollar.yol("hvac_analysis_history.csv", os.path.dirname(__file__))
HVAC_SON_CALISMA_FILE = yollar.yol("hvac_son_calisma.txt", os.path.dirname(__file__))
ALARM_RAPORU_SON_AY_FILE = yollar.yol("alarm_raporu_son_ay.txt", os.path.dirname(__file__))


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
        # Lokasyon anahtarı (configs/lokasyon_anahtari.json) varsa istekler onunla imzalanır:
        # veritabanı bu PC'ye yalnız kendi lokasyonunun satırlarında izin verir (yol haritası B1).
        # Dosya yoksa ya da sb_kimlik yüklenemezse bugünkü gibi ortak anahtar.
        try:
            import sb_kimlik
            return sb_kimlik.istemci(url, key)
        except ImportError:
            return create_client(url, key)
    except ImportError:
        logger.error("supabase kütüphanesi yüklü değil! pip install supabase")
        return None
    except Exception as e:
        logger.error(f"Supabase bağlantı hatası: {e}")
        return None


_EKSIK_SUTUN = re.compile(r"Could not find the '([^']+)' column")


def _ekle_bilinmeyen_sutunsuz(client, tablo, batch, dusen, deneme=20):
    """Toplu insert; merkezde OLMAYAN sütun hatasında (PGRST204) o sütunu çıkarıp yeniden dener.

    Eskiden energy_data.csv'deki tek bir yeni sütun (yeni sayaç) lokasyonun BÜTÜN gönderimini
    düşürüyordu. Artık o sütun energy_data'ya gitmez ama satırlar gider; sayacın değeri
    sayac_gunluk'a (D1) zaten satır olarak yazılır. dusen: bu turda çıkarılan sütunlar (paylaşılır).
    """
    for _ in range(deneme):
        gidecek = [{k: v for k, v in r.items() if k not in dusen} for r in batch] if dusen else batch
        try:
            client.table(tablo).insert(gidecek).execute()
            return
        except Exception as e:
            m = _EKSIK_SUTUN.search(str(e))
            if not m or m.group(1) in dusen:
                raise
            dusen.add(m.group(1))
            logger.warning("⚠️ %s'da '%s' sütunu yok — bu sütun gönderilmeden devam ediliyor "
                           "(sayaç ise değeri sayac_gunluk'a gider; sütun gerekiyorsa merkezde açılmalı)",
                           tablo, m.group(1))
    raise RuntimeError("%s: çok fazla eksik sütun (%s)" % (tablo, ", ".join(sorted(dusen))))


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

        # Türetilmiş sütunları GÖNDERMEDEN ÖNCE yeniden hesapla.
        # Eskiden bu yalnızca Enerji portalı açıldığında oluyordu; portal
        # açılmazsa eski (yanlış) değerler buluta gidiyordu. Kural
        # enerji_hesap.py'de, app_portal.recalc() ile aynı yerde.
        try:
            import enerji_hesap
            df = enerji_hesap.yeniden_hesapla(df)
            logger.info("🧮 Türetilmiş enerji sütunları gönderim öncesi yeniden hesaplandı")
        except Exception as _he:
            # Hesap başarısızsa ham CSV gönderilir — sync hiç yapılmamasından iyidir.
            logger.error("Enerji hesabı uygulanamadı, ham değerler gönderiliyor: %s", _he)

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

        # Sayaç başına ince tablo (D1): energy_data'dan bağımsız; hata olursa enerji gönderimi sürer
        try:
            import sayac_gunluk
            sayac_gunluk.gonder(client, records, lokasyon_id)
        except Exception as _sge:
            logger.warning(f"sayac_gunluk gönderilemedi: {_sge}")

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
                # Tam sayı olan ondalık → tamsayı (2.0 → 2). Boş hücresi olan sütunu
                # pandas float okur; Supabase'deki INTEGER sütunlar (Chiller_Adet,
                # Kazan_Adet, Kojen_Adet...) "2.0"ı reddeder ve toplu insert TAMAMEN
                # düşer. 24.10.2026: donmuş BACnet günleri boşaltılınca adetler ilk kez
                # boş hücre içerdi. real sütunlar tamsayıyı zaten kabul eder.
                if isinstance(clean[k], float) and clean[k].is_integer():
                    clean[k] = int(clean[k])
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
        dusen = set()
        for i in range(0, len(clean_records), batch_size):
            batch = clean_records[i:i + batch_size]
            _ekle_bilinmeyen_sutunsuz(client, "energy_data", batch, dusen)
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


SON_YAMA_FILE = yollar.yol("son_yama.json", os.path.dirname(__file__))
YAMA_SURUMU_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "yama_surumu.json")  # yamayla gelir


def son_yama_surumu():
    """Bu PC'de uygulanan son yamanın sürümü (heartbeat ile merkeze gider). Yoksa None.

    Önce durum/son_yama.json (bu programın uyguladığı son yama); yoksa yamanın kendi getirdiği
    yama_surumu.json — ilk büyük yamayı sahadaki eski program uygular ve son_yama.json'u yazmaz.
    """
    for p in (SON_YAMA_FILE, YAMA_SURUMU_FILE):
        try:
            with open(p, "r", encoding="utf-8") as f:
                v = (json.load(f) or {}).get("versiyon")
            if v:
                return v
        except Exception:
            continue
    return None


def _guvenli_yol(base_dir: str, dosya_yolu: str):
    """Yamadaki dosya yolu program klasörünün İÇİNDE mi? Değilse None (../, mutlak yol, sürücü)."""
    if not dosya_yolu or os.path.isabs(dosya_yolu) or ":" in dosya_yolu:
        return None
    kok = os.path.realpath(base_dir)
    tam = os.path.realpath(os.path.join(kok, dosya_yolu))
    return tam if tam.startswith(kok + os.sep) else None


YAMA_YEDEK_SAKLA = 10      # son kaç yamanın yedeği tutulur


def _yama_yedekle(base_dir, versiyon, dosya_yolu, tam_yol):
    """Yamanın değiştireceği dosyanın ESKİ hâlini durum/yama_yedek/<sürüm>/<yol> altına kopyalar
    (yol haritası A4: bozuk bir yamada eski koda dönülebilsin). Son YAMA_YEDEK_SAKLA sürüm tutulur.
    Yedek alınamazsa yama yine uygulanır (yedek kolaylıktır; asıl geri alma git'ten yapılır)."""
    try:
        if not os.path.isfile(tam_yol):
            return
        import re as _re_y
        import shutil as _sh
        kok = yollar.klasor("durum/yama_yedek", base_dir)
        surum_dizini = os.path.join(kok, _re_y.sub(r"[^\w.\-]", "_", str(versiyon)) or "bilinmeyen")
        hedef = os.path.join(surum_dizini, *dosya_yolu.replace("\\", "/").split("/"))
        if os.path.exists(hedef):
            return                      # aynı yamada ilk (gerçek eski) hâl korunur
        os.makedirs(os.path.dirname(hedef), exist_ok=True)
        _sh.copy2(tam_yol, hedef)
        surumler = sorted((os.path.join(kok, d) for d in os.listdir(kok) if os.path.isdir(os.path.join(kok, d))),
                          key=os.path.getmtime)
        for eski in surumler[:-YAMA_YEDEK_SAKLA]:
            _sh.rmtree(eski, ignore_errors=True)
    except Exception as e:
        logger.warning(f"Yama yedeği alınamadı ({dosya_yolu}): {e}")


def check_and_apply_update(client, lokasyon_id: str, base_dir: str = None):
    """Bekleyen güncellemeleri KRONOLOJİK sırayla TÜMÜNÜ uygula.

    Eski davranış (limit(1) + en yeni kayıt) birden fazla bekleyen kayıt
    biriktiğinde yalnız sonuncusunu uygulayıp diğerlerini sonsuza dek
    'bekliyor' bırakıyordu — aradaki yamaların içeriği kayboluyordu.
    Artık tüm bekleyenler eskiden yeniye uygulanır (aynı dosya birden fazla
    kayıtta varsa son yazılan — en yeni — kazanır), restart bayrağı en sonda
    bir kez yazılır.

    ÇOK LOKASYON (12.11.2026, yol haritası A1): her uygulama yama_uygulamalari
    tablosuna (yama_id, lokasyon_id) olarak yazılır.
      * hedef=<bu lokasyon> → eskisi gibi satırın durumu da güncellenir.
      * hedef='all' → satırın durumuna DOKUNULMAZ (yoksa ilk lokasyon kapatır, diğerleri
        hiç almaz). Bu lokasyonun uygulama kaydı varsa yama atlanır. Bütün lokasyonlar
        uygulayınca veritabanı tetiği (yama_all_kapat) satırı kapatır.
      * Uygulama kayıtları okunamazsa 'all' yamaları bu turda uygulanmaz (aynı yamanın
        her turda yeniden uygulanmasındansa beklemek güvenli); lokasyona özel yamalar sürer.
    GÜVENLİK: yamadaki dosya yolu program klasörünün dışını gösteriyorsa yazılmaz.
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

        all_idler = [k["id"] for k in r.data if k.get("hedef") == "all"]
        uygulanmis, kayit_okunur = set(), True
        if all_idler:
            try:
                u = client.table("yama_uygulamalari").select("yama_id") \
                    .eq("lokasyon_id", lokasyon_id).in_("yama_id", all_idler).execute()
                uygulanmis = {x["yama_id"] for x in (u.data or [])}
            except Exception as e:
                kayit_okunur = False
                logger.error(f"Yama uygulama kayıtları okunamadı — 'all' yamaları bu turda atlandı: {e}")

        bekleyen = [k for k in r.data if k.get("hedef") != "all"
                    or (kayit_okunur and k["id"] not in uygulanmis)]
        if not bekleyen:
            return

        base_dir = base_dir or os.path.dirname(__file__)
        tum_dosyalar = set()   # restart kararı için (tüm kayıtların birleşimi)
        son_versiyon = "?"

        logger.info(f"🔄 {len(bekleyen)} bekleyen güncelleme bulundu — kronolojik sırayla uygulanıyor...")

        for kayit in bekleyen:
            kayit_id = kayit["id"]
            versiyon = kayit.get("versiyon", "?")
            dosyalar = kayit.get("dosyalar", {})
            son_versiyon = versiyon

            logger.info(f"🔄 v{versiyon} uygulanıyor ({len(dosyalar)} dosya, hedef {kayit.get('hedef')})...")

            uygulanan = 0
            hatalar = []

            for dosya_yolu, icerik in dosyalar.items():
                try:
                    tam_yol = _guvenli_yol(base_dir, dosya_yolu)
                    if tam_yol is None:
                        hatalar.append(dosya_yolu)
                        logger.error(f"  ⛔ {dosya_yolu}: program klasörünün dışı — yazılmadı")
                        continue
                    if not yollar.yama_yazabilir_mi(dosya_yolu):
                        # Faz 1: yama yalnız KODU günceller; lokasyon ayarı, durum ve veri
                        # (ayar/ durum/ veri/ ve eski adları) yamayla ezilmez.
                        hatalar.append(dosya_yolu)
                        logger.error(f"  ⛔ {dosya_yolu}: lokasyon ayarı/verisi — yama yazmaz")
                        continue
                    # Geri alma (yol haritası A4): değişecek dosyanın ESKİ hâli yedeklenir
                    _yama_yedekle(base_dir, versiyon, dosya_yolu, tam_yol)
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

            yeni_durum = "tamamlandi" if not hatalar else "hata"
            try:
                client.table("yama_uygulamalari").insert({
                    "yama_id": kayit_id, "lokasyon_id": lokasyon_id, "durum": yeni_durum,
                    "versiyon": versiyon, "hatali_dosyalar": hatalar,
                }).execute()
            except Exception as e:
                logger.warning(f"Yama uygulama kaydı yazılamadı (v{versiyon}): {e}")
            if kayit.get("hedef") != "all":
                # Lokasyona özel satırın durumu (sadece mevcut kolon)
                client.table("guncellemeler").update({
                    "durum": yeni_durum,
                }).eq("id", kayit_id).execute()

            logger.info(f"✅ v{versiyon} tamamlandı — {uygulanan} dosya uygulandı")

        try:
            with open(yollar.yol("son_yama.json", base_dir), "w", encoding="utf-8") as f:
                json.dump({"versiyon": son_versiyon, "zaman": datetime.now().isoformat(timespec="seconds")}, f)
        except Exception as e:
            logger.warning(f"son_yama.json yazılamadı: {e}")

        # Kritik dosya değiştiyse tam yeniden başlatma gerekir (tek sefer, en sonda)
        KRITIK_DOSYALAR = {"cloud_sync.py", "portal_watchdog.py"}
        tam_restart = bool(tum_dosyalar & KRITIK_DOSYALAR)

        if tam_restart:
            flag_path = os.path.join(base_dir, "_full_restart.flag")
            logger.info("🔄 Kritik dosya güncellendi — TAM yeniden başlatma sinyali gönderildi (_full_restart.flag)")
        else:
            flag_path = os.path.join(base_dir, "_restart.flag")
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
        "pressure_sensor":      "Basınç Sensörü",
    }
    try:
        mc_file = yollar.yol("configs/maintenance_cards.json", os.path.dirname(__file__))
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
        # Aylık bakım işareti durumu (Synapse canlı uyarıları bunu okur)
        try:
            from bakim_durum import heartbeat_alani
            aylik_bakim = heartbeat_alani()
        except Exception:
            aylik_bakim = {}
        return {
            "toplam_ariza": toplam_ariza,
            "toplam_bakim": toplam_bakim,
            "toplam_sorun": toplam_ariza + toplam_bakim,
            "cihaz_sayisi": len(cards),
            "arizali_cihazlar": arizali_cihazlar,
            "bakimda_cihazlar": bakimda_cihazlar,
            "son_guncelleme": data.get("last_updated", ""),
            "aylik_bakim": aylik_bakim,
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

    EGRESS OPTİMİZASYONU (delta senkron): Eskiden her turda TÜM kartların `kart`
    JSONB gövdesi indiriliyordu (46 kart × ~2 KB × günde 720 tur ≈ 60 MB/gün →
    Supabase egress kotasını tüketiyordu). Artık önce yalnızca `cihaz,updated_at`
    çekilir (~60 byte/kart); `kart` gövdesi SADECE buluttaki sürümü yerelden yeni
    olan cihazlar için indirilir. Tipik turda 0 gövde iner.
    """
    mc_file = yollar.yol("configs/maintenance_cards.json", os.path.dirname(__file__))
    try:
        data = {"last_updated": None, "updated_by": None, "cards": {}}
        if os.path.exists(mc_file):
            with open(mc_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        cards = data.get("cards", {}) or {}

        # 0) HAFİF TARAMA — sadece zaman damgaları (kart gövdesi YOK)
        r = client.table("bakim_kartlari") \
            .select("cihaz,updated_at") \
            .eq("lokasyon_id", lokasyon_id) \
            .range(0, 999).execute()
        bulut = {x["cihaz"]: x for x in (r.data or [])}

        # 0b) Buluttaki sürümü yerelden YENİ olan cihazları belirle — gövde yalnız onlar için inecek
        _indirilecek = []
        for cihaz, satir in bulut.items():
            if cihaz not in cards:
                continue  # yerelde yok → aşağıda silinecek, gövdesine gerek yok
            _yerel_ts = _ts_parse(cards[cihaz].get("_updated_at") if isinstance(cards[cihaz], dict) else None)
            if _ts_parse(satir.get("updated_at")) > _yerel_ts:
                _indirilecek.append(cihaz)

        if _indirilecek:
            r2 = client.table("bakim_kartlari") \
                .select("cihaz,kart,updated_at") \
                .eq("lokasyon_id", lokasyon_id) \
                .in_("cihaz", _indirilecek).execute()
            for x in (r2.data or []):
                bulut[x["cihaz"]] = x  # gövdeli satırla değiştir
            logger.info(f"🔧 {len(_indirilecek)} kartın gövdesi indirildi (delta senkron)")

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
                # GÜVENLİK: delta senkronda gövde inmediyse (ağ hatası vb.) yerel kartı
                # boş dict ile EZME — bu turu atla, sonraki turda tekrar denenir.
                _govde = satir.get("kart")
                if not _govde:
                    logger.warning(f"Bakım kartı gövdesi inmedi, atlandı: {cihaz}")
                    continue
                yeni = dict(_govde)
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


# Heartbeat upsert'i 'returning=minimal' destekliyor mu (postgrest sürümüne göre);
# ilk hatada False'a düşer ve bir daha denenmez.
_HB_MINIMAL_OK = True


def _oto_durum_topla() -> dict:
    """Oto-set'in son turda ne yaptığı — heartbeat bunu Supabase'e taşır.

    ASLA İSTİSNA ATMAZ. İlk sürümde bu blok doğrudan send_heartbeat içindeydi
    ve `_oto_set_ok` bayrağına bakıyordu; oysa o bayrak start_background_sync
    fonksiyonunun YEREL değişkeni. Heartbeat'ten erişilince NameError oluştu,
    dıştaki try bunu yuttu ve HEARTBEAT HİÇ GÖNDERİLMEDİ — lokasyon çevrimdışı
    görünmeye başladı. Bu yüzden burası kendi başına, dışarıya hata sızdırmayan
    bir fonksiyon.

    Modül yüklenemiyorsa bu da bir CEVAPTIR; sessiz kalmak yanıltır.
    """
    try:
        from oto_set import durum_ozet
        return durum_ozet()
    except Exception as e:
        return {"zaman": datetime.now().isoformat(timespec="seconds"),
                "sonuc": "modul_yok",
                "metin": "oto_set modülü yüklenemedi",
                "aciklama": str(e)[:200]}


def _geri_bildirim_ozet() -> dict:
    """Tasarruf önerisi geri bildirim sayacı (ml_training_data.json).

    NEDEN VAR: Öneri geri bildirimleri bugüne kadar yalnızca lokasyon PC'sinde
    birikiyordu; merkezden kaç kayıt olduğu GÖRÜLEMİYORDU. Öğrenme döngüsünü
    (reddedilen öneriyi aşağı al / bastır) kurmadan önce sahada ne kadar veri
    olduğunu bilmek gerekir: kural başına yeterli geri bildirim yoksa öğrenme
    motoru aylarca hiçbir şey yapmaz.

    Heartbeat 2 dakikada bir gittiği için özet KÜÇÜK tutulur (sayılar + en çok
    reddedilen 2 kural).
    """
    try:
        try:
            from location_manager import get_manager
            yol = get_manager().get_data_path("ml_training_data.json")
        except Exception:
            yol = yollar.yol("ml_training_data.json", os.path.dirname(os.path.abspath(__file__)))
        if not os.path.exists(yol):
            return {"kayit": 0, "geri_bildirim": 0}
        with open(yol, "r", encoding="utf-8") as f:
            kayitlar = json.load(f)
        if not isinstance(kayitlar, list):
            return {"kayit": 0, "geri_bildirim": 0}

        durum_sayac = {}
        kural_red = {}
        kural_geri_bildirim = {}
        geri_bildirimli = 0
        for k in kayitlar:
            fb = k.get("feedback") or {}
            durum = fb.get("status")
            if not durum or durum == "pending":
                continue
            geri_bildirimli += 1
            durum_sayac[durum] = durum_sayac.get(durum, 0) + 1
            kural = (k.get("recommendation") or {}).get("rule_id") or "BILINMIYOR"
            kural_geri_bildirim[kural] = kural_geri_bildirim.get(kural, 0) + 1
            if durum == "not_applied":
                kural_red[kural] = kural_red.get(kural, 0) + 1

        # Öğrenme için eşik: bir kural hakkında karar vermek en az 5 geri bildirim ister
        hazir = sorted(k for k, n in kural_geri_bildirim.items() if n >= 5)
        en_cok_red = sorted(kural_red.items(), key=lambda x: -x[1])[:2]

        return {
            "kayit": len(kayitlar),
            "geri_bildirim": geri_bildirimli,
            "uygulandi": durum_sayac.get("applied", 0),
            "uygulanmadi": durum_sayac.get("not_applied", 0),
            "kismi": durum_sayac.get("partially_applied", 0),
            "ogrenmeye_hazir_kural": hazir,
            "en_cok_red": [{"kural": k, "adet": n} for k, n in en_cok_red],
        }
    except Exception as e:
        logger.debug(f"Geri bildirim özeti okunamadı: {e}")
        return {}


def _oz_test_ozet() -> dict:
    """Mekanik Zeka öz testinin son sonucu (oz_test.py). Yoksa boş sözlük.

    KENDİ İÇİNDE KAPALI: oz_test modülü bulunamazsa/okunamazsa heartbeat
    bozulmaz — v7.1'de benzer bir içe aktarma hatası heartbeat'i kesmişti.
    """
    try:
        import oz_test
        return oz_test.son_sonuc() or {}
    except Exception as e:
        logger.debug(f"Öz test özeti okunamadı: {e}")
        return {}


def _veri_alarm_ozet() -> dict:
    """Veri toplama alarmlarinin KUCUK ozeti (veri_alarm.py).

    Synapse'teki CANLI UYARILAR bu ozeti okur; alarm yoksa bos sozluk doner
    ve heartbeat'i bosuna sismez. Kendi icinde kapali: modul okunamazsa
    heartbeat kesilmez.
    """
    try:
        import veri_alarm
        return veri_alarm.son_ozet()
    except Exception as e:
        logger.debug(f"Veri alarm ozeti okunamadi: {e}")
        return {}


def send_heartbeat(client, lokasyon_id: str):
    """Supabase'e kısa heartbeat gönder (her 2 dakikada bir çağrılır)"""
    try:
        _ozet = get_bakim_ozet() or {}
        _ozet["oto"] = _oto_durum_topla()
        _ozet["oz_test"] = _oz_test_ozet()
        _ozet["geri_bildirim"] = _geri_bildirim_ozet()
        _ozet["veri_alarm"] = _veri_alarm_ozet()

        payload = {
            "lokasyon_id": lokasyon_id,
            "ping_zamani": datetime.now().isoformat(),
            "durum": "online",
            "bakim_ozet": _ozet,
        }
        _surum = son_yama_surumu()
        if _surum:
            payload["versiyon"] = _surum      # uygulanan son yama (yol haritası A2)
        # returning="minimal": yazılan satır geri DÖNMESİN — bakim_ozet JSONB'si
        # (arızalı/bakımda cihaz listeleri) her 2 dakikada boşuna indiriliyordu (egress).
        # GÜVENLİK: heartbeat kritik (kesilirse lokasyon 'çevrimdışı' görünür ve Synapse
        # alarm verir). Bu yüzden minimal HER hatada normal upsert'e düşer ve bir daha
        # denenmez — sürüm uyumsuzluğunda çift istek atmayalım.
        global _HB_MINIMAL_OK
        if _HB_MINIMAL_OK:
            try:
                client.table("lokasyonlar").upsert(
                    payload, on_conflict="lokasyon_id", returning="minimal").execute()
            except Exception as _me:
                _HB_MINIMAL_OK = False
                logger.info(f"Heartbeat 'minimal' desteklenmiyor, standart moda geçildi: {_me}")
                client.table("lokasyonlar").upsert(payload, on_conflict="lokasyon_id").execute()
        else:
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
            "versiyon": son_yama_surumu() or "2.0",
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

    import location_manager as _lm_k   # kimlik: lokasyon profili (Faz 1)
    lokasyon_id = _lm_k.lokasyon_id(None, config.get("lokasyon_id")) or "bilinmeyen"
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


_ARKA_PLAN = {"basladi": False}
_ARKA_PLAN_KILIDI = threading.Lock()


def start_background_sync():
    """Arka planda periyodik senkronizasyon ve heartbeat başlat.

    Dönüş: True  — bu süreç döngüleri başlattı (ya da zaten çalıştırıyor)
           False — döngüler BAŞKA bir süreçte çalışıyor, burada başlatılmadı
           None  — yapılandırma yok / otomatik sync kapalı

    TEK KOPYA GARANTİSİ: Önceden app_portal.py her Streamlit çalışmasında bu
    fonksiyonu çağırıyor ve her seferinde YENİ döngüler başlıyordu; watchdog'un
    ayrı cloud_sync.py süreci de çalıştığı için oto-set aynı geçişi 2-3 kez
    uyguluyor, komutlar ve heartbeat tekrarlanıyordu. Artık:
      * aynı süreçte ikinci çağrı hiçbir şey başlatmaz,
      * makinede döngüleri yalnızca kilidi alan TEK süreç çalıştırır.
    """
    with _ARKA_PLAN_KILIDI:
        if _ARKA_PLAN["basladi"]:
            return True
        try:
            from kilit import surec_kilidi_al
            sahip = surec_kilidi_al("cloud_sync")
        except Exception as _ke:
            # Kilit modülü yoksa (yarım güncelleme) eski davranış: başlat.
            # Başlatmamak heartbeat'i keser ve lokasyon çevrimdışı görünür.
            logger.warning(f"Tek kopya kilidi kullanılamadı, döngüler yine de başlatılıyor: {_ke}")
            sahip = True
        if not sahip:
            logger.info("Arka plan döngüleri başka bir süreçte çalışıyor — bu süreçte başlatılmadı.")
            return False
        _ARKA_PLAN["basladi"] = True

    config = load_config()
    if not config:
        return

    auto_sync = config.get("auto_sync", True)

    if not auto_sync:
        logger.info("Otomatik senkronizasyon kapalı (supabase_config.json)")
        return

    import location_manager as _lm_k   # kimlik: lokasyon profili (Faz 1)
    lokasyon_id = _lm_k.lokasyon_id(None, config.get("lokasyon_id")) or "bilinmeyen"
    client = get_supabase_client(config)

    # Günlük sync saati: 08:00
    _SYNC_SAAT   = 8
    _SYNC_DAKIKA = 0
    _SYNC_SON_FILE = yollar.yol("sync_son_calisma.txt", os.path.dirname(__file__))

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

    # Oto-set karar motoru (yoksa sessizce atla)
    try:
        from oto_set import kontrol as _oto_set_kontrol
        _oto_set_ok = True
    except Exception:
        _oto_set_ok = False

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
                    # OTO-SET KARARI — her turda (≈1 dk), yalnızca dönem
                    # geçişinde komut üretir.
                    #
                    # Karar bilerek BURADA veriliyor: merkez portal (Streamlit
                    # Cloud) kimse kullanmayınca uyuduğu için setler saatinde
                    # değil, biri portalı açtığında gidiyordu (ör. 23:00 yerine
                    # 00:32). Lokasyon PC'si 7/24 açık olduğundan zamanlama
                    # burada güvenilir.
                    if _oto_set_ok and _sb_url and _sb_key:
                        _oto_set_kontrol(_sb_url, _sb_key, lokasyon_id)
                    # Her turda: BACnet komut polling (≈1 dk aralık)
                    # Oto-set'in ürettiği komutlar da bu akıştan geçer; böylece
                    # değer doğrulama kapısı (5-40 °C) ve denetim izi korunur.
                    if _bacnet_writer_ok and _sb_url and _sb_key:
                        _komutlari_isle(_sb_url, _sb_key, lokasyon_id)
                    # Her 2 turda bir (≈2 dk): heartbeat + güncelleme kontrolü
                    if _tick % 2 == 0:
                        send_heartbeat(client, lokasyon_id)
                        check_and_apply_update(client, lokasyon_id)
                        # Ayar değişiklikleri (ayar/ klasörü) merkeze — Faz 1 / K1. Hata olursa
                        # heartbeat ve yama akışı etkilenmez; gönderilemeyen sonraki turda gider.
                        try:
                            import ayar_kaydi
                            ayar_kaydi.tara_ve_gonder(client, lokasyon_id)
                        except Exception as _ake:
                            logger.warning(f"Ayar kaydı turu tamamlanamadı: {_ake}")
                    # Bakım kartı senkronu: her 10 turda bir (≈10 dk) — EGRESS optimizasyonu.
                    # Sahadan QR ile yapılan kart değişikliğinin lokasyona inmesi için
                    # 2 dk gereksiz hassastı; 10 dk saha akışı için fazlasıyla yeterli.
                    if _tick % 10 == 0:
                        sync_bakim_kartlari(client, lokasyon_id)
                        # Uyarı / hata özeti merkeze (N5): yalnız değişen gün + şablon satırları
                        if hata_ozeti is not None:
                            try:
                                hata_ozeti.gonder(client, lokasyon_id)
                            except Exception as _hoe:
                                logger.warning(f"Hata özeti gönderilemedi: {_hoe}")
                    # AHU geçmişi: 90 günden eskiler günlük özete, ham dosyalar silinir
                    # (yol haritası N3; günde bir kez, kendi işaretiyle).
                    if _tick % 30 == 0:
                        try:
                            import gecmis_bakim
                            gecmis_bakim.gunluk_calistir()
                        except Exception as _gbe:
                            logger.warning(f"AHU geçmiş bakımı yapılamadı: {_gbe}")
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

    def _canli_guc_loop():
        """Canlı TRDP gücünü buluta taşır (≈15 sn).

        Heartbeat döngüsüne EKLENMEDİ: o 1 dakikada bir dönüyor ve canlı panel
        için fazla yavaş. Ölçümü data_collector yapar, burası yalnızca dosyayı
        okuyup yazar — Modbus'a bu süreçten gidilmez.

        Kendi içinde kapalıdır: modül yoksa, dosya yoksa ya da tablo henüz
        açılmamışsa sessizce döner; senkron ve heartbeat etkilenmez.
        """
        try:
            import canli_guc
        except Exception as e:
            logger.info(f"Canlı güç taşıma kapalı (modül yok): {e}")
            return
        _periyot = max(5, int(canli_guc.ayar_oku().get("periyot_sn", 15)))
        _son_yazilan = None
        _uyarildi = False
        while True:
            try:
                veri = canli_guc.son_olcum()
                # Aynı ölçüm iki kez yazılmasın (okuma durduysa boşuna istek gitmesin)
                if client and veri and veri.get("zaman") != _son_yazilan:
                    satirlar = [{
                        "lokasyon_id": lokasyon_id,
                        "cihaz": o.get("cihaz"),
                        "kw": o.get("kw"),
                        "yontem": o.get("yontem"),
                        "aciklama": o.get("not"),
                        "olcum_zamani": veri["zaman"],
                    } for o in veri.get("olcumler", []) if o.get("cihaz")]
                    if satirlar:
                        # Tabloda GEÇMİŞ TUTULMAZ: lokasyon×cihaz başına tek
                        # satır, üzerine yazılır. Grafiğin ihtiyacı olan son
                        # birkaç dakika merkezin oturumunda birikir; böylece
                        # Supabase'de satır sayısı sabit kalır (4 satır).
                        client.table("canli_guc").upsert(
                            satirlar, on_conflict="lokasyon_id,cihaz",
                            returning="minimal").execute()
                        _son_yazilan = veri["zaman"]
                        _uyarildi = False
            except Exception as e:
                if not _uyarildi:      # her 15 sn log basmasın
                    logger.warning(f"Canlı güç taşınamadı: {e}")
                    _uyarildi = True
            time.sleep(_periyot)

    t_sync = threading.Thread(target=_sync_loop, daemon=True, name="cloud-sync")
    t_sync.start()

    t_hb = threading.Thread(target=_heartbeat_loop, daemon=True, name="heartbeat")
    t_hb.start()

    t_cg = threading.Thread(target=_canli_guc_loop, daemon=True, name="canli-guc-sync")
    t_cg.start()

    logger.info(f"🔄 Arka plan senkronizasyonu başlatıldı (günlük {_SYNC_SAAT:02d}:{_SYNC_DAKIKA:02d}, heartbeat: 2 dk)")
    return True


# ============ Manuel / Subprocess çalıştırma ============
if __name__ == "__main__":
    print("=" * 50)
    print("  HVAC Enerji Sistemi — Bulut Senkronizasyonu")
    print("=" * 50)

    # NOT: Startup'ta run_sync() ÇAĞIRILMAZ.
    # Sync zamanlaması _sync_loop tarafından (sync_son_calisma.txt ile) yönetilir.
    # Bu sayede restart/güncelleme sonrasında çift sync olmaz.
    _basladi = start_background_sync()

    # Ana thread canlı kalsın (daemon thread'ler ölmesin).
    # Döngüler başka bir süreçteyse (False) dakikada bir yeniden denenir:
    # o süreç kapanırsa işletim sistemi kilidi bırakır ve görev burada devralınır.
    try:
        while True:
            time.sleep(60)
            if _basladi is False:
                _basladi = start_background_sync()
    except KeyboardInterrupt:
        print("\nCloud Sync durduruldu.")
