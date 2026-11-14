# watchdog.py
# Portalları başlatır, güncelleme sonrası otomatik yeniden başlatır.
# PORTAL_BASLAT.bat bu scripti çalıştırır.

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import os
import sys
import time
import subprocess
import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [WATCHDOG] %(message)s',
    datefmt='%H:%M:%S'
)
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FLAG_FILE = os.path.join(BASE_DIR, "_restart.flag")
FULL_RESTART_FLAG = os.path.join(BASE_DIR, "_full_restart.flag")

# Alt süreçler watchdog altında çalıştıklarını bilsin. app_portal.py bunu
# görünce kendi içinde senkronizasyon döngüsü BAŞLATMAZ; döngüler yalnızca
# aşağıda başlatılan cloud_sync.py sürecinde çalışır (tek kopya).
_COCUK_ENV = dict(os.environ, HVAC_WATCHDOG="1")


PORT_BEKLEME_SN = 30


def _portlari_hazirla(bekleme_sn=PORT_BEKLEME_SN, _bekle=time.sleep):
    """Portlar (ayar/portlar.json; yoksa 8501 / 8005) ve çocuk süreçlerin birbirini bulduğu adresler.

    Port KAYDIRILMAZ (QR etiketleri portu taşır). Yeniden başlatmada eski süreç portu birkaç saniye
    tutabildiği için önce beklenir; hâlâ doluysa açıkça uyarılır (log → merkezde hata özeti,
    durum/portlar_durum.json → kurulum kontrolü) ve portal yine başlatılır.
    """
    try:
        import portlar as _pt
    except Exception:                       # modül yoksa bugünkü sabit portlar
        return {"enerji": 8501, "mekanik_zeka": 8005}
    p = _pt.yukle(BASE_DIR)
    sinir = time.monotonic() + bekleme_sn
    while True:
        dolu = _pt.durum_yaz(BASE_DIR)
        if not dolu or time.monotonic() >= sinir:
            break
        _bekle(2)
    for ad, port in dolu:
        logger.error("⛔ %s portu %d başka bir program tarafından kullanılıyor — portal açılamayabilir. "
                     "Portu tutan programı kapatın; port değiştirilmez (QR etiketleri bu portu taşır).",
                     "Enerji" if ad == "enerji" else "Mekanik Zeka", port)
    # Portallar birbirine ve agent'lar portallara bu adreslerden ulaşır (açıkça verilmişse dokunulmaz)
    _COCUK_ENV.setdefault("STREAMLIT_URL", "http://localhost:%d" % p["enerji"])
    _COCUK_ENV.setdefault("PORTAL_URL", "http://localhost:%d/" % p["mekanik_zeka"])
    return p


def start_portals():
    procs = []
    port = _portlari_hazirla()

    p1 = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app_portal.py",
         "--server.port", str(port["enerji"]),
         "--server.headless", "true"],
        cwd=BASE_DIR, env=_COCUK_ENV
    )
    logger.info(f"✅ Enerji Portal başlatıldı (PID: {p1.pid}, Port: {port['enerji']})")
    procs.append(p1)

    p2 = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main_portal:app",
         "--host", "127.0.0.1",
         "--port", str(port["mekanik_zeka"])],
        cwd=BASE_DIR, env=_COCUK_ENV
    )
    logger.info(f"✅ HVAC Portal başlatıldı (PID: {p2.pid}, Port: {port['mekanik_zeka']})")
    procs.append(p2)

    p3 = subprocess.Popen(
        [sys.executable, "cloud_sync.py"],
        cwd=BASE_DIR, env=_COCUK_ENV
    )
    logger.info(f"✅ Cloud Sync başlatıldı (PID: {p3.pid})")
    procs.append(p3)

    p4 = subprocess.Popen(
        [sys.executable, "data_collector.py"],
        cwd=BASE_DIR, env=_COCUK_ENV
    )
    logger.info(f"✅ Veri Toplayici başlatıldı (PID: {p4.pid}) — Modbus + BACnet")
    procs.append(p4)

    p5 = subprocess.Popen(
        [sys.executable, "data_bridge.py"],
        cwd=BASE_DIR, env=_COCUK_ENV
    )
    logger.info(f"✅ Data Bridge başlatıldı (PID: {p5.pid}) — her gece 00:05'te dünün (23:59 okuması) satırını energy_data.csv'ye yazar (data_bridge.SNAPSHOT_HOUR/MINUTE)")
    procs.append(p5)

    _oz_test_baslat()
    return procs


def _oz_test_baslat():
    """Mekanik Zeka öz testini ARKA PLANDA çalıştırır (portalı geciktirmez).

    Testler lokasyonun KENDİ ayarlarıyla koşar: aynı kod farklı ayarla farklı
    karar verir, bu yüzden 'bende yeşildi' yetmez. Sonuç configs/oz_test_sonuc.json
    dosyasına yazılır ve heartbeat ile Synapse'e gider.
    """
    try:
        subprocess.Popen([sys.executable, "oz_test.py"], cwd=BASE_DIR, env=_COCUK_ENV,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        logger.info("🧪 Mekanik Zeka öz testi arka planda başlatıldı")
    except Exception as e:
        logger.warning(f"Öz test başlatılamadı: {e}")   # portal çalışmaya devam eder


# ── Portal agent'ları (Enerji, Mekanik Zeka) ───────────────────────────────
# Portallardan AYRI izlenir: bir agent ölürse yalnızca o agent yeniden başlatılır,
# portallar ve veri toplama etkilenmez (yukarıdaki procs listesine BİLEREK
# eklenmez — o listedeki bir süreç durunca hepsi yeniden başlatılıyor).
_AGENTLAR = {
    "enerji_agent.py": "Enerji Portal Agent'ı",
    "mekanik_zeka_agent.py": "Mekanik Zeka Agent'ı",
}
_agent = {d: {"surec": None, "son_baslatma": 0.0} for d in _AGENTLAR}
_AGENT_BEKLEME_SN = 60          # art arda çökerse en sık bu aralıkla yeniden dener


def _agent_baslat():
    """Çalışmayan agent'ları başlatır (dosyası olmayan agent sessizce geçilir)."""
    for dosya, ad in _AGENTLAR.items():
        a = _agent[dosya]
        p = a["surec"]
        if p is not None and p.poll() is None:
            continue
        if not os.path.exists(os.path.join(BASE_DIR, dosya)):
            continue
        if time.time() - a["son_baslatma"] < _AGENT_BEKLEME_SN:
            continue
        try:
            a["son_baslatma"] = time.time()
            a["surec"] = subprocess.Popen([sys.executable, dosya], cwd=BASE_DIR, env=_COCUK_ENV)
            logger.info(f"🤖 {ad} başlatıldı (PID: {a['surec'].pid})")
        except Exception as e:
            logger.warning(f"{ad} başlatılamadı: {e}")   # portallar çalışmaya devam eder


def _agent_durdur():
    for a in _agent.values():
        p = a["surec"]
        if p is None:
            continue
        try:
            p.terminate()
            p.wait(timeout=5)
        except Exception:
            try:
                p.kill()
            except Exception:
                pass
        a["surec"], a["son_baslatma"] = None, 0.0


def stop_portals(procs):
    for p in procs:
        try:
            p.terminate()
            p.wait(timeout=5)
            logger.info(f"🛑 Süreç durduruldu (PID: {p.pid})")
        except Exception:
            try:
                p.kill()
            except Exception:
                pass


TEK_KOPYA_BEKLEME_SN = 60


def tek_kopya(bekleme_sn=TEK_KOPYA_BEKLEME_SN, _bekle=time.sleep, _al=None):
    """Bu PC'de tek watchdog çalışsın (kurulum programı otomatik başlatma ekler, 12.11.2026).

    Başka bir başlatma yolu da varsa (Başlangıç klasörü + görev zamanlayıcı gibi) ikinci watchdog
    portalları ve veri toplamayı ikinci kez başlatırdı. Kilit süreç ömrü boyunca tutulur.
    BEKLEME: tam yeniden başlatmada eski watchdog yenisini başlatıp ANCAK SONRA kapanır; yeni
    watchdog kilidi hemen alamaz. Bu yüzden vazgeçmeden önce bekleme_sn boyunca yeniden denenir.
    """
    if _al is None:
        from kilit import surec_kilidi_al as _al
    sinir = time.monotonic() + bekleme_sn
    while True:
        if _al("watchdog"):
            return True
        if time.monotonic() >= sinir:
            return False
        _bekle(2)


def main():
    if not tek_kopya():
        logger.warning("Başka bir watchdog zaten çalışıyor — bu kopya kapanıyor (portallar o kopyada).")
        sys.exit(0)

    # ── LİSANS KONTROLÜ ──────────────────────────────
    try:
        from lisans import lisans_kontrol
        _lis = lisans_kontrol()
        if not _lis["gecerli"]:
            print("=" * 55)
            print("  LISANSSIZ ERISIM — PROGRAM BASLATILMIYOR")
            print("=" * 55)
            print(f"  Makine ID : {_lis['makine_id']}")
            print(f"  Hata      : {_lis['hata']}")
            print("  Yetkili   : Acibadem Genel Merkez Enerji Yonetimi")
            print("=" * 55)
            sys.exit(1)
        else:
            logger.info(f"[LISANS] Gecerli — {_lis.get('makine_adi', _lis['makine_id'])}")
    except ImportError:
        pass  # lisans.py yoksa devam et

    logger.info("=" * 50)
    logger.info("  HVAC Watchdog başlatılıyor...")
    logger.info("=" * 50)

    # Klasör düzeni (Faz 1): eski yerlerdeki ayar/durum/veri dosyaları bir kez ayar/ durum/ veri/
    # altına taşınır. Burada, HİÇBİR çocuk süreç çalışmazken yapılır; hata olursa programlar
    # eski yerleri kullanmaya devam eder (yollar.yol geri düşer).
    try:
        import yollar
        _r = yollar.tasi()
        if _r["tasinan"] or _r["hata"]:
            logger.info(f"📁 Klasör düzeni: {len(_r['tasinan'])} taşındı, {len(_r['hata'])} hata")
    except Exception as _te:
        logger.warning(f"Klasör düzeni taşıması yapılamadı (eski yerler kullanılır): {_te}")
    procs = start_portals()
    _agent_baslat()
    logger.info("Portallar çalışıyor. Güncelleme sinyali bekleniyor...")

    while True:
        time.sleep(10)
        _agent_baslat()          # agent durduysa yalnızca agent yeniden başlar

        # Süreç ölmüş mü kontrol et
        for i, p in enumerate(procs):
            if p.poll() is not None:
                logger.warning(f"⚠️ Süreç beklenmedik şekilde durdu (PID: {p.pid}), yeniden başlatılıyor...")
                stop_portals(procs)
                time.sleep(2)
                procs = start_portals()
                break

        # TAM yeniden başlatma (cloud_sync.py / portal_watchdog.py değiştiyse)
        if os.path.exists(FULL_RESTART_FLAG):
            logger.info("🔄 TAM yeniden başlatma sinyali alındı — sistem sıfırlanıyor...")
            _agent_durdur()      # yeni watchdog yeni kodla kendi agent'ını başlatır
            stop_portals(procs)
            try:
                os.remove(FULL_RESTART_FLAG)
            except Exception:
                pass
            time.sleep(2)
            # Watchdog'u yeni kodla yeniden başlat, bu process'i sonlandır
            subprocess.Popen([sys.executable, os.path.abspath(__file__)], cwd=BASE_DIR)
            logger.info("✅ Yeni watchdog başlatıldı, mevcut process sonlanıyor.")
            sys.exit(0)

        # Normal yeniden başlatma (sadece portallar)
        if os.path.exists(FLAG_FILE):
            logger.info("🔄 Güncelleme sinyali alındı — portallar yeniden başlatılıyor...")
            _agent_durdur()      # yama agent kodunu da değiştirmiş olabilir
            stop_portals(procs)
            try:
                os.remove(FLAG_FILE)
            except Exception:
                pass
            time.sleep(3)
            procs = start_portals()
            logger.info("✅ Portallar güncelleme sonrası yeniden başlatıldı.")


if __name__ == "__main__":
    main()
