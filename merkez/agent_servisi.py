# -*- coding: utf-8 -*-
"""
AGENT SERVİSİ — üst agent + hava besleyici, Synapse'ten BAĞIMSIZ süreç (thapps)
==============================================================================

Yönetici systemd servisi olarak kurar (veritabani/UST_AGENT_SERVIS_TALEBI.md):

    WorkingDirectory=/opt/canliizleme_app/merkez
    EnvironmentFile=/etc/canliizleme/ust_agent.env     # SYNAPSE_URL, SYNAPSE_AGENT_KEY
    ExecStart=/opt/canliizleme_app/venv/bin/python agent_servisi.py

İki iş parçacığı çalıştırır:
  * üst agent (ust_agent.py)        her 120 sn: bulgu → iş emri, takip, kapatma
  * hava besleyici (hava_besleyici.py) her 3 saat: lokasyonların günlük havası

Bu servis çalışırken merkez portalının içindeki yedek kopyalar kendiliğinden
devre dışı kalır (tur satırındaki "kaynak": "servis" işaretine bakarlar);
servis durursa ~5 dk içinde merkez yedeği devreye girer.

Disk: hiçbir şey yazmaz. Log: stdout (journald). Bağımlılık: yalnızca stdlib.

    python agent_servisi.py          → sürekli
    python agent_servisi.py --tek    → bir üst agent turu + bir hava turu, sonucu yazdır, çık
"""
import json
import logging
import os
import sys
import threading
import time

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import hava_besleyici  # noqa: E402
import ust_agent  # noqa: E402

KOORDINAT_DOSYA = os.path.join(BURASI, "configs", "lokasyon_koordinat.json")
logger = logging.getLogger("agent_servisi")


def koordinatlar():
    """{lokasyon_id: (enlem, boylam)} — configs/lokasyon_koordinat.json (app_merkez HASTANELER ile aynı)."""
    with open(KOORDINAT_DOSYA, encoding="utf-8") as f:
        d = json.load(f)
    return {k: (float(v[0]), float(v[1])) for k, v in d.items() if not k.startswith("_")}


def ayarlar():
    url = os.environ.get("SYNAPSE_URL", "").strip()
    key = os.environ.get("SYNAPSE_AGENT_KEY", "").strip()
    if not url or not key:
        sys.exit("SYNAPSE_URL ve SYNAPSE_AGENT_KEY ortam değişkenleri gerekli (EnvironmentFile).")
    return url, key


def hava_dongu(url, key, koor):
    while True:
        try:
            logger.info("Hava besleyici: %s", hava_besleyici.tur(url, key, koor))
        except Exception as e:
            logger.warning("Hava besleyici turu tamamlanamadı: %s: %s", type(e).__name__, e)
        time.sleep(hava_besleyici.ARALIK_SN)


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s %(message)s",
                        stream=sys.stdout)
    url, key = ayarlar()
    koor = koordinatlar()
    db = ust_agent.Db(url, key)
    if "--tek" in sys.argv:
        print(json.dumps({"ust_agent": ust_agent.tur(db, kaynak="servis"),
                          "hava": hava_besleyici.tur(url, key, koor)}, ensure_ascii=False, indent=1))
        return
    logger.info("Agent servisi başladı (üst agent her %d sn, hava her %d sn)",
                ust_agent.TUR_SN, hava_besleyici.ARALIK_SN)
    threading.Thread(target=hava_dongu, args=(url, key, koor), name="hava", daemon=True).start()
    while True:                                   # üst agent ana iş parçacığında
        try:
            s = ust_agent.tur(db, kaynak="servis")
            if s["acilan"] or s["guncellenen"]:
                logger.info("Üst agent turu: %d iş emri açıldı, %d güncellendi", len(s["acilan"]), s["guncellenen"])
        except Exception as e:
            logger.warning("Üst agent turu tamamlanamadı: %s: %s", type(e).__name__, e)
        time.sleep(ust_agent.TUR_SN)


if __name__ == "__main__":
    main()
