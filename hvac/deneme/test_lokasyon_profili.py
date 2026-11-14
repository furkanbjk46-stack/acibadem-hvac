# -*- coding: utf-8 -*-
"""Lokasyon profili (Faz 1): kimlik tek kaynaktan — ayar/lokasyon_profili.json."""
import json
import os
import re
import sys
import tempfile

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import location_manager as L  # noqa: E402

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", ek)


def yaz(base, goreli, veri):
    p = os.path.join(base, *goreli.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        json.dump(veri, f)


# Kimlik
d = tempfile.mkdtemp(prefix="profil_")
c("hiçbir dosya yoksa kimlik boş", L.lokasyon_id(d) == "")
yaz(d, "supabase_config.json", {"lokasyon_id": "maslak", "supabase_url": "x"})
c("profil yoksa bağlantı dosyasındaki kimlik (eski kurulum)", L.lokasyon_id(d) == "maslak")
yaz(d, "configs/lokasyon_profili.json", {"lokasyon_id": "atasehir", "ad": "Acıbadem Ataşehir"})
c("profil varsa kimlik profilden (bağlantı dosyası farklı olsa da)", L.lokasyon_id(d) == "atasehir")
c("verilen yedek değer profil varken kullanılmaz", L.lokasyon_id(d, "baska") == "atasehir")
d2 = tempfile.mkdtemp(prefix="profil_yeni_")
yaz(d2, "ayar/lokasyon_profili.json", {"lokasyon_id": "atasehir"})
c("yeni düzende ayar/lokasyon_profili.json okunur", L.lokasyon_id(d2) == "atasehir" and L.profil(d2)["lokasyon_id"] == "atasehir")
d3 = tempfile.mkdtemp(prefix="profil_bos_")
yaz(d3, "configs/lokasyon_profili.json", {"lokasyon_id": ""})
c("profilde kimlik boşsa yedek kullanılır", L.lokasyon_id(d3, "maslak") == "maslak")

# Isıtma hatları ve BACnet eşlemesi (Faz 1 / C2): ayar/bacnet_esleme.json
import bacnet_esleme as BE  # noqa: E402
c("Maslak eşlemesi şablondan: iki hat, 31 nokta",
  [h["ad"] for h in BE.hatlar()] == ["MAS-1", "MAS-2"] and len(BE.noktalar()) == 31)
c("hat sütunları hat sırasıyla", BE.hat_sutunlari()[:3] == ["Mas1_Isitma_Temp", "Mas1_Kazan_Temp", "Mas1_Sogutma_Temp"])
c("hatların nokta adları eşlemeden bulunur",
  BE.nokta_adlari("sogutma") == ["MAS-1 SOGUTMA SICAKLIK", "MAS-2 SOGUTMA SICAKLIK"])
d4 = tempfile.mkdtemp(prefix="esleme_")
yaz(d4, "ayar/lokasyon_profili.json", {"lokasyon_id": "atasehir", "ad": "Acıbadem Ataşehir"})
yaz(d4, "ayar/bacnet_esleme.json", {"noktalar": {"ATS ISITMA": "Isitma_Temp_C", "DIS HAVA": "Dis_Hava_Sicakligi_C"},
                                    "isitma_hatlari": [{"ad": "ATS", "etiket": "Ana hat", "isitma": "Isitma_Temp_C"}]})
k = L.lokasyon_konfig(d4)
c("tek hatlı lokasyon: yapılandırma dosyalardan (Maslak sabiti yok)",
  k["id"] == "atasehir" and k["energy_schema"]["heating_lines"] == ["ATS"]
  and k["csv_columns"]["heating_temp_cols"] == ["Isitma_Temp_C"] and k["name"] == "Acıbadem Ataşehir Hastanesi")
c("eksik alanlı hat sorun çıkarmaz (yalnız ısıtma)", BE.hat_sutunlari(d4) == ["Isitma_Temp_C"]
  and BE.nokta_adlari("sogutma", d4) == [])
d5 = tempfile.mkdtemp(prefix="esleme_yok_")
c("eşleme dosyası yoksa boş (BACnet yazılmaz, hata yok)", BE.noktalar(d5) == {} and BE.hatlar(d5) == [])

# Kodda kimlik bağlantı dosyasından doğrudan okunmuyor
desen = re.compile(r'\b(cfg|_cfg|config|c)\.get\(\s*["\']lokasyon_id["\']')
ihlal = []
for ad in sorted(os.listdir(BURASI)):
    if ad.endswith(".py") and not ad.startswith("test_") and ad not in (
            "location_manager.py", "simulasyon_sunucu.py", "ornek_veri_uret.py", "guncelleme_yayinla.py", "_test_ping.py"):
        satirlar = open(os.path.join(BURASI, ad), encoding="utf-8").read().splitlines()
        for i, satir in enumerate(satirlar):
            if desen.search(satir):
                # değer yardımcıya 'yedek' olarak veriliyorsa yardımcı çağrısı yakındadır (±5 satır)
                cevre = "\n".join(satirlar[max(0, i - 5):i + 6]).replace('get("lokasyon_id"', "")
                if "lokasyon_id(" not in cevre:
                    ihlal.append("%s:%d" % (ad, i + 1))
c("kodda lokasyon kimliği bağlantı dosyasından doğrudan okunmuyor (location_manager.lokasyon_id)", not ihlal, ihlal)

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
