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


def start_portals():
    procs = []

    p1 = subprocess.Popen(
        ["streamlit", "run", "app_portal.py",
         "--server.port", "8501",
         "--server.headless", "true"],
        cwd=BASE_DIR
    )
    logger.info(f"✅ Enerji Portal başlatıldı (PID: {p1.pid}, Port: 8501)")
    procs.append(p1)

    p2 = subprocess.Popen(
        ["uvicorn", "main_portal:app",
         "--host", "127.0.0.1",
         "--port", "8005"],
        cwd=BASE_DIR
    )
    logger.info(f"✅ HVAC Portal başlatıldı (PID: {p2.pid}, Port: 8005)")
    procs.append(p2)

    p3 = subprocess.Popen(
        ["python", "cloud_sync.py"],
        cwd=BASE_DIR
    )
    logger.info(f"✅ Cloud Sync başlatıldı (PID: {p3.pid})")
    procs.append(p3)

    return procs


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
    logger.info("=" * 50)
    logger.info("  HVAC Watchdog başlatılıyor...")
    logger.info("=" * 50)

    procs = start_portals()
    logger.info("Portallar çalışıyor. Güncelleme sinyali bekleniyor...")

    while True:
        time.sleep(10)

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
