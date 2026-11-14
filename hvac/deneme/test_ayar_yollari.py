# -*- coding: utf-8 -*-
"""Tek BACnet nokta dosyası (yol haritası N2) — okuma (ahu_collector) ve ekran (main_portal) aynı dosyaya bakar."""
import json
import os
import sys
import tempfile
import time

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import ayar_yollari as Y  # noqa: E402

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", ek)


def yaz(p, veri, zaman):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(veri, f)
    os.utime(p, (zaman, zaman))


d = tempfile.mkdtemp()
kok, cfg = os.path.join(d, Y.NOKTA_DOSYA), os.path.join(d, "configs", Y.NOKTA_DOSYA)
c("hiç dosya yoksa yeni kurulumun yeri ayar/bacnet_noktalari.json (Faz 1)",
  Y.nokta_konfig_yolu(d) == os.path.join(d, "ayar", "bacnet_noktalari.json"))
yaz(kok, [{"gateway_ip": "192.168.0.6"}], time.time() - 100)
c("yalnız kökte varsa kökteki", Y.nokta_konfig_yolu(d) == kok)
yaz(cfg, [{"gateway_ip": "192.168.0.5"}], time.time() - 1000)
c("iki kopyadan en son düzenlenen geçerli (Maslak: kök 31.10, configs 14.07)", Y.nokta_konfig_yolu(d) == kok)
c("ayrışma tespit edilir", Y.nokta_konfig_ayrisik(d))
yaz(cfg, [{"gateway_ip": "192.168.0.7"}], time.time())
c("teknik ekip configs/ kopyasını düzenlerse o geçerli olur", Y.nokta_konfig_yolu(d) == cfg)
yaz(kok, [{"gateway_ip": "192.168.0.7"}], time.time())
c("içerik aynıysa ayrışma yok", not Y.nokta_konfig_ayrisik(d))

# Okuyan iki program da yardımcıyı kullanıyor
_ac = open(os.path.join(BURASI, "ahu_collector.py"), encoding="utf-8").read()
_mp = open(os.path.join(BURASI, "main_portal.py"), encoding="utf-8").read()
c("ahu_collector nokta dosyasını yardımcıdan okur ve yazar",
  "ayar_yollari.nokta_konfig_yolu(BASE_DIR)" in _ac and "with open(AHU_CONFIG_FILE" not in _ac)
c("main_portal aynı yardımcıyı kullanır", "ayar_yollari.nokta_konfig_yolu()" in _mp)

import ahu_collector as A  # noqa: E402
eski = (A.BASE_DIR,)
A_BASE = A.BASE_DIR
try:
    A.BASE_DIR = d
    c("ahu_collector.load_ahu_config geçerli dosyayı okur", A.load_ahu_config() == [{"gateway_ip": "192.168.0.7"}])
    A.AHU_CONFIG_FILE = os.path.join(d, "sim.json")
    yaz(A.AHU_CONFIG_FILE, [{"sim": 1}], time.time())
    c("simülasyon AHU_CONFIG_FILE'ı değiştirirse o kullanılır", A.load_ahu_config() == [{"sim": 1}])
finally:
    A.BASE_DIR = A_BASE
    A.AHU_CONFIG_FILE = A._AHU_CONFIG_OTOMATIK

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
