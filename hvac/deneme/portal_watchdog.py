# watchdog.py
# Portalları başlatır, güncelleme sonrası otomatik yeniden başlatır.
# PORTAL_BASLAT.bat bu scripti çalıştırır.

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import os
import sys
import time
import socket
import threading
import webbrowser
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


def start_portals():
    procs = []

    p1 = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", "app_portal.py",
         "--server.port", "8501",
         "--server.headless", "true"],
        cwd=BASE_DIR, env=_COCUK_ENV
    )
    logger.info(f"✅ Enerji Portal başlatıldı (PID: {p1.pid}, Port: 8501)")
    procs.append(p1)

    p2 = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "main_portal:app",
         "--host", "127.0.0.1",
         "--port", "8005"],
        cwd=BASE_DIR, env=_COCUK_ENV
    )
    logger.info(f"✅ HVAC Portal başlatıldı (PID: {p2.pid}, Port: 8005)")
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


# ── Enerji Portal Agent'ı ─────────────────────────────────────────────────
# Portallardan AYRI izlenir: agent ölürse yalnızca agent yeniden başlatılır,
# portallar ve veri toplama etkilenmez (yukarıdaki procs listesine BİLEREK
# eklenmez — o listedeki bir süreç durunca hepsi yeniden başlatılıyor).
_agent = {"surec": None, "son_baslatma": 0.0}
_AGENT_BEKLEME_SN = 60          # art arda çökerse en sık bu aralıkla yeniden dener


def _agent_baslat():
    """Enerji agent'ı çalışmıyorsa başlatır (enerji_agent.py yoksa sessizce geçer)."""
    p = _agent["surec"]
    if p is not None and p.poll() is None:
        return
    if not os.path.exists(os.path.join(BASE_DIR, "enerji_agent.py")):
        return
    if time.time() - _agent["son_baslatma"] < _AGENT_BEKLEME_SN:
        return
    try:
        _agent["son_baslatma"] = time.time()
        _agent["surec"] = subprocess.Popen([sys.executable, "enerji_agent.py"],
                                           cwd=BASE_DIR, env=_COCUK_ENV)
        logger.info(f"🤖 Enerji Portal Agent'ı başlatıldı (PID: {_agent['surec'].pid})")
    except Exception as e:
        logger.warning(f"Enerji agent'ı başlatılamadı: {e}")   # portallar çalışmaya devam eder


def _agent_durdur():
    p = _agent["surec"]
    if p is None:
        return
    try:
        p.terminate()
        p.wait(timeout=5)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass
    _agent["surec"], _agent["son_baslatma"] = None, 0.0
# ── Tarayıcı: portallar GERÇEKTEN hazır olunca açılır ───────────────────
# 11.11.2026 — "portal çok geç açılıyor" şikayetinin sebebi buydu:
# PORTAL_BASLAT.bat 5 saniye bekleyip tarayıcıyı açıyordu, AMA watchdog
# bat'ın en sonunda çalışıyor; yani tarayıcı sunucular daha BAŞLAMADAN
# açılıyordu. Kullanıcı ölü bir sayfa görüp elle yenilemek zorunda
# kalıyordu. Sahadaki ölçüm: watchdog 10:50:59'da başladı, Streamlit
# 10:52:22'de hazır oldu — tarayıcı 10:51:04'te, yani 78 saniye erken
# açılmıştı.
#
# Artık port DİNLEMEYE BAŞLAYINCA açılır. Bekleme süreleri de loglanır:
# yavaşlığın hangi tarafta olduğu bir daha tahmin edilmesin.
TARAYICI_URL   = "http://127.0.0.1:8005"
HVAC_PORT      = 8005
ENERJI_PORT    = 8501
HAZIR_BEKLE_SN = 300          # bu kadar beklenir; dolarsa tarayıcı yine açılır


def _port_dinliyor_mu(port, ip="127.0.0.1", zaman_asimi=1.0) -> bool:
    """Porta TCP bağlantısı kuruluyor mu — sunucu ayağa kalktı mı."""
    s = socket.socket()
    s.settimeout(zaman_asimi)
    try:
        s.connect((ip, int(port)))
        return True
    except OSError:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def _hazir_bekle(port, ad, t0, bitis):
    """Port açılana kadar bekler. (hazir_mi, baslangictan_bu_yana_sn) döner."""
    while time.time() < bitis:
        if _port_dinliyor_mu(port):
            gecen = time.time() - t0
            logger.info("⏱️ %s hazır (%.1f sn)", ad, gecen)
            return True, gecen
        time.sleep(0.5)
    gecen = time.time() - t0
    logger.warning("⚠️ %s %.0f sn içinde yanıt vermedi — tarayıcı yine de açılıyor", ad, gecen)
    return False, gecen


def tarayici_hazir_olunca(url=TARAYICI_URL, bekle_sn=HAZIR_BEKLE_SN):
    """Arka planda bekler, HVAC portalı cevap verince tarayıcıyı açar.

    YALNIZ İLK AÇILIŞTA çağrılır (main). Güncelleme sonrası yeniden
    başlatmalarda tarayıcı tekrar açılmaz — kullanıcının açık sekmesi var.
    """
    t0 = time.time()
    bitis = t0 + bekle_sn

    def _is():
        _hazir_bekle(HVAC_PORT, "HVAC Portal", t0, bitis)
        try:
            webbrowser.open(url)
            logger.info("🌐 Tarayıcı açıldı: %s", url)
        except Exception as e:
            logger.warning("Tarayıcı açılamadı: %s", e)
        # Enerji portalı (Streamlit) geç kalkıyor; süresi ayrıca ölçülür.
        _hazir_bekle(ENERJI_PORT, "Enerji Portal", t0, bitis)

    t = threading.Thread(target=_is, daemon=True)
    t.start()
    return t


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


def main():
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

    procs = start_portals()
    _agent_baslat()
    tarayici_hazir_olunca()          # hazır olunca açar, erken değil
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
