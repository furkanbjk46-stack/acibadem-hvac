# -*- coding: utf-8 -*-
"""Saha teşhisi + BACnet alarmları — Maslak'ın 20.09.2026 donmasını birebir canlandırır.

Gerçek dosyalara dokunmaz: her senaryo geçici klasörde kurulur.
"""
import csv
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass
import saha_teshis as ST  # noqa: E402
import veri_alarm as VA  # noqa: E402

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


def bacnet_csv(yol, zaman, ok=True):
    with open(yol, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Timestamp", "Device_ID", "Point_Name", "Value", "Status"])
        w.writeheader()
        for ad, v in (("DIS HAVA", 19.88), ("CH SET", 7.5), ("MAS-1 ISITMA SICAKLIK", 91.12)):
            w.writerow({"Timestamp": zaman, "Device_ID": 1, "Point_Name": ad,
                        "Value": v if ok else "", "Status": "OK" if ok else "[Zaman Asimi]"})


def energy_csv(yol, gun_sayisi, donmus_gun):
    bas = datetime(2026, 9, 1)
    with open(yol, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["Tarih", "Dis_Hava_Sicakligi_C", "Chiller_Set_Temp_C",
                                           "Kazan_Adet", "Chiller_Load_Percent", "Mas1_Isitma_Temp"])
        w.writeheader()
        for i in range(gun_sayisi):
            donuk = i >= gun_sayisi - donmus_gun
            w.writerow({"Tarih": (bas + timedelta(days=i)).strftime("%Y-%m-%d"),
                        "Dis_Hava_Sicakligi_C": "19.88" if donuk else "%.2f" % (21 - i * 0.13),
                        "Chiller_Set_Temp_C": "7.5", "Kazan_Adet": "0",       # sabit kalması NORMAL
                        "Chiller_Load_Percent": "66.5" if donuk else "%.1f" % (70 + i % 5),
                        "Mas1_Isitma_Temp": "91.12" if donuk else "%.2f" % (80 + i % 7)})


tmp = tempfile.mkdtemp()
simdi = datetime(2026, 10, 23, 23, 45)
bc, ec = os.path.join(tmp, "b.csv"), os.path.join(tmp, "e.csv")

# ── Maslak senaryosu: okuma 20.09 07:05'te kalmış, 34 gün donuk ──
bacnet_csv(bc, "2026-09-20 07:05:12")
energy_csv(ec, 53, 34)
al = VA.bacnet_alarmlari(simdi=simdi, bacnet_csv=bc, energy_csv=ec)
turler = {a["tur"]: a for a in al}
c("bayat BACnet dosyası KRİTİK alarm", turler.get("bacnet_bayat", {}).get("onem") == "kritik", al)
c("alarm mesajı son okuma tarihini söylüyor", "20.09.2026" in turler.get("bacnet_bayat", {}).get("mesaj", ""))
c("donmuş değer alarmı", "donmus_deger" in turler, al)
c("dış hava donmuş listede", "Dis_Hava_Sicakligi_C" in turler.get("donmus_deger", {}).get("cihazlar", []))
c("chiller set (normalde sabit) donmuş SAYILMIYOR",
  "Chiller_Set_Temp_C" not in turler.get("donmus_deger", {}).get("cihazlar", []))

# ── Sağlıklı: bugün okunmuş, değerler değişiyor ──
bacnet_csv(bc, "2026-10-23 07:05:40")
energy_csv(ec, 53, 0)
c("sağlıklı zincirde BACnet alarmı YOK", VA.bacnet_alarmlari(simdi=simdi, bacnet_csv=bc, energy_csv=ec) == [])
c("dosya hiç yoksa KRİTİK", VA.bacnet_alarmlari(simdi=simdi, bacnet_csv=os.path.join(tmp, "yok.csv"),
                                                energy_csv=ec)[0]["onem"] == "kritik")

# ── Teşhis cümleleri: "nerede koptu" ──
def r(**k):
    v = {"bacnet_csv": {"var": True, "nokta": 40, "ok": 40, "bayat": False},
         "sablon": {"var": True, "okunuyor": True}, "surec": {"data_collector": 1},
         "canli": {"denendi": 5, "ok": 5}, "donma": {}}
    v.update(k)
    return v

bayat = {"var": True, "nokta": 40, "ok": 40, "bayat": True, "saat_once": 808, "son_okuma": "2026-09-20 07:05:12"}
t = ST.teshis_koy(r(bacnet_csv=bayat))
c("bayat + gateway cevap veriyor → iş parçacığı sorunu", any("ağda değil" in x for x in t), t)
t = ST.teshis_koy(r(bacnet_csv=bayat, canli={"denendi": 5, "ok": 0}))
c("bayat + gateway cevapsız → ağ/gateway", any("gateway/ağ" in x for x in t), t)
c("şablon yok → KRİTİK", ST.teshis_koy(r(sablon={"var": False}))[0].startswith("KRİTİK"))
c("şablon açılamıyor → KRİTİK", any("açılamıyor" in x for x in ST.teshis_koy(
    r(sablon={"var": True, "okunuyor": False, "hata": "PermissionError"}))))
t = ST.teshis_koy(r(sablon={"var": True, "okunuyor": True, "configs_var": True, "kok_var": False,
                            "collector_yolu": "hedefli_okuma_sablonu_2.xlsx", "collector_buluyor": False}))
c("şablon configs'te, collector kökte arıyor → KRİTİK ve açıklıyor",
  t[0].startswith("KRİTİK") and "BULAMIYOR" in t[0] and "configs/ altında" in t[0], t)
c("collector çalışmıyor → KRİTİK", any("çalışmıyor" in x for x in ST.teshis_koy(r(surec={"data_collector": 0}))))
c("collector 2 kopya → UYARI", any("2 kopya" in x for x in ST.teshis_koy(r(surec={"data_collector": 2}))))
c("sağlıklı → TAMAM", ST.teshis_koy(r()) == ["TAMAM: BACnet zinciri sağlıklı."])

# ── Donma taraması dosyadan ──
energy_csv(ec, 53, 34)
eski = ST.ENERGY_CSV
ST.ENERGY_CSV = ec
d = ST.donma_taramasi()
ST.ENERGY_CSV = eski
c("tarama dış havayı 34 gün buluyor", d.get("Dis_Hava_Sicakligi_C", {}).get("gun") == 34, d)
c("tarama chiller set'i işaretlemiyor", "Chiller_Set_Temp_C" not in d, d)

# ── Heartbeat'e giden özet küçük ve öz test özetinde ──
eski_d = ST.SONUC_DOSYASI
ST.SONUC_DOSYASI = os.path.join(tmp, "sonuc.json")
with open(ST.SONUC_DOSYASI, "w", encoding="utf-8") as f:
    json.dump(r(bacnet_csv=bayat, donma=d) | {"zaman": "x", "durum": "KRITIK",
              "teshis": ST.teshis_koy(r(bacnet_csv=bayat, donma=d))}, f, ensure_ascii=False)
oz = ST.son_ozet()
ST.SONUC_DOSYASI = eski_d
c("özet küçük (<1500 karakter)", len(json.dumps(oz, ensure_ascii=False)) < 1500, len(json.dumps(oz)))
c("özette durum ve teşhis var", oz.get("durum") == "KRITIK" and oz.get("teshis"), oz)
import oz_test  # noqa: E402
c("öz test özeti teşhisi taşıyor (heartbeat alanı)", "teshis" in oz_test.son_sonuc() or oz_test.son_sonuc() == {})
c("teşhis modülü salt okuma: dosyaya yazdığı TEK yer kendi sonuç dosyası",
  open(os.path.join(BURASI, "saha_teshis.py"), encoding="utf-8").read().count('open(gecici, "w"') == 1)

# ── Kök sebep düzeltmesi: data_collector şablonu configs/'te de bulmalı ──
import data_collector as DC  # noqa: E402
c("data_collector önce configs/ yolunu dener",
  DC._EXCEL_FILE_CONFIGS.endswith(os.path.join("configs", "hedefli_okuma_sablonu_2.xlsx")))
c("data_collector ve ahu_collector aynı sırayla arar",
  "configs" in open(os.path.join(BURASI, "ahu_collector.py"), encoding="utf-8").read().split("_ENERGY_EXCEL_CONFIGS")[1][:80])
c("geliştirme PC'sinde şablon artık bulunuyor (configs/)", os.path.exists(DC.EXCEL_FILE), DC.EXCEL_FILE)

hata = [x for x in T if not x[1]]
for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)[:300]))
print("%d/%d PASS" % (len(T) - len(hata), len(T)))
sys.exit(1 if hata else 0)
