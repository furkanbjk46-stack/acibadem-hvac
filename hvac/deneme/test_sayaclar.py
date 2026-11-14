# -*- coding: utf-8 -*-
"""Sayaç listesi tek kaynaktan (Faz 1 / C1): ayar/sayaclar.json.

ALTIN KAYIT: test_veri_sayac_altin.json, sayaç listesi koddan dosyaya taşınmadan ÖNCE
data_bridge.build_daily_row'un ürettiği satırlardır (12.11.2026). Dosyaya taşındıktan sonra
Maslak için çıktı BİREBİR aynı olmalı: eski kural (4 trafo / eksik trafo / trafo yok / kojen yok),
yeni kural (şebeke var / yok, eksik kojen) ve Modbus yok senaryoları.
"""
import json
import logging
import os
import sys
import tempfile

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
os.chdir(BURASI)
logging.disable(logging.CRITICAL)
import data_bridge as DB  # noqa: E402
import data_collector as DC  # noqa: E402
import sayaclar as S  # noqa: E402

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", str(ek)[:400])


ALTIN = json.load(open(os.path.join(BURASI, "test_veri_sayac_altin.json"), encoding="utf-8"))

# 1) Maslak: dosyadan gelen liste eskisiyle aynı
c("analizör listesi (32 sayaç, sıra, IP, marka, tür işaretleri) eski koddakiyle aynı",
  DC.ANALYZERS == ALTIN["_analizorler"], [a for a in DC.ANALYZERS if a not in ALTIN["_analizorler"]])
c("enerji tablosu sütunları eskisiyle aynı", DB.ENERGY_SCHEMA == ALTIN["_sema"],
  set(DB.ENERGY_SCHEMA) ^ set(ALTIN["_sema"]))
for ad, sen in ALTIN.items():
    if ad.startswith("_"):
        continue
    satir = DB.build_daily_row(sen["tarih"], sen.get("bacnet", {}), sen["girdi"])
    farkli = {k: (sen["satir"].get(k), satir.get(k)) for k in set(satir) | set(sen["satir"])
              if sen["satir"].get(k) != satir.get(k)}
    c("günlük satır altın kayıtla birebir aynı: %s" % ad, not farkli, farkli)

# 2) Kodda sayaç IP'si / sayaç adı kalmadı
for dosya in ("data_collector.py", "data_bridge.py"):
    kod = "\n".join(x for x in open(os.path.join(BURASI, dosya), encoding="utf-8").read().splitlines()
                    if not x.strip().startswith("#"))
    c("%s içinde sayaç IP'si yok" % dosya, "172.17.91." not in kod and "192.168.1.15" not in kod)
c("data_bridge'de sayaç adları sabit değil (TRDP-n / CHILLER-n / MCC-n)",
  not any(x in open(os.path.join(BURASI, "data_bridge.py"), encoding="utf-8").read()
          for x in ('"TRDP-1"', '"CHILLER-1"', '"MCC-1"', '"KULE-1"', 'daily_kwh.get("SEBEKE"')))

# 3) sayaclar modülü
d = tempfile.mkdtemp(prefix="sayac_")
c("dosya yoksa boş liste (okuma yapılmaz)", S.yukle(d) == [])
os.makedirs(os.path.join(d, "ayar"), exist_ok=True)
with open(os.path.join(d, "ayar", "sayaclar.json"), "w", encoding="utf-8") as f:
    json.dump({"sayaclar": [
        {"ad": "TR-A", "ip": "10.0.0.1", "marka": "siemens", "tur": "trafo", "sutun": "TRA_kWh"},
        {"ad": "TR-B", "ip": "10.0.0.2", "marka": "janitza", "tur": "trafo", "sutun": "TRB_kWh"},
        {"ad": "CH-X", "ip": "10.0.0.3", "marka": "siemens", "tur": "chiller", "sutun": "ChX_kWh", "kritik": True},
        {"ad": "BOZUK", "ip": "10.0.0.9", "tur": "bilinmeyen"},
    ]}, f)
c("geçersiz tür ayıklanır, sıra korunur", [s["ad"] for s in S.yukle(d)] == ["TR-A", "TR-B", "CH-X"])
c("data_collector biçimi", S.analizorler(d)[0] == {"ip": "10.0.0.1", "name": "TR-A", "brand": "siemens"})
c("tür ve sütun sorguları", S.adlar("trafo", d) == ["TR-A", "TR-B"] and S.sutunlar("chiller", d) == ["ChX_kWh"]
  and S.kritik_adlar(d) == {"CH-X"})

# 4) Tohumlama: ayar yoksa ornek_ayar/<lokasyon>/'dan bir kez kopyalanır, varsa ezilmez
d2 = tempfile.mkdtemp(prefix="sayac_tohum_")
os.makedirs(os.path.join(d2, "ornek_ayar", "atasehir"))
os.makedirs(os.path.join(d2, "ayar"), exist_ok=True)
with open(os.path.join(d2, "ayar", "lokasyon_profili.json"), "w", encoding="utf-8") as f:
    json.dump({"lokasyon_id": "atasehir"}, f)
with open(os.path.join(d2, "ornek_ayar", "atasehir", "sayaclar.json"), "w", encoding="utf-8") as f:
    json.dump({"sayaclar": [{"ad": "T1", "ip": "1.1.1.1", "marka": "siemens", "tur": "trafo", "sutun": "T1_kWh"}]}, f)
c("eksik ayar lokasyonun şablonundan kopyalanır", [s["ad"] for s in S.yukle(d2)] == ["T1"]
  and os.path.exists(os.path.join(d2, "ayar", "sayaclar.json")))
with open(os.path.join(d2, "ayar", "sayaclar.json"), "w", encoding="utf-8") as f:
    json.dump({"sayaclar": [{"ad": "T9", "ip": "1.1.1.9", "marka": "siemens", "tur": "trafo", "sutun": "T9_kWh",
                            "not": "teknik ekip düzenledi"}]}, f)
import yollar  # noqa: E402
yollar.tohumla(d2)
c("lokasyonda var olan ayar şablonla ezilmez", [s["ad"] for s in S.yukle(d2)] == ["T9"])
c("repoda Maslak şablonu var (ornek_ayar/maslak/sayaclar.json)",
  len(json.load(open(os.path.join(BURASI, "ornek_ayar", "maslak", "sayaclar.json"), encoding="utf-8"))["sayaclar"]) == 32)

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
