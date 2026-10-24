# -*- coding: utf-8 -*-
"""
SAHA TEŞHİSİ — veri toplama zincirini uçtan uca kontrol eder (SALT OKUMA)
========================================================================

NEDEN: Maslak'ta 20.09.2026'dan itibaren enerji tablosundaki BACnet değerleri
(dış hava, chiller yükü/adedi, kazan ve ısıtma sıcaklıkları) her gün AYNI
değerle yazıldı; bir ay boyunca kimse fark etmedi. Sebep zinciri:

  data_collector.py  BACnet'i günde BİR kez (07:05–07:10) okur
                     → hedefli_enerji_verileri.csv'yi yeniden yazar
  data_bridge.py     23:45'te o dosyayı okur → energy_data satırı
                     (dosyanın tarihine BAKMAZ: dosya güncellenmezse dünkü
                      değerleri her gün yeniden yazar)
  Mekanik Zeka       BACnet'i KENDİ okumasıyla (ahu_collector) yapar —
                     analizler çalıştığı için sorun görünmedi.

Bu modül zincirin her halkasını ölçer ve sonucu heartbeat'e verir:
  1. hedefli_enerji_verileri.csv  — son okuma ne zaman, kaç nokta OK, hata türleri
  2. BACnet okuma şablonu (Excel)  — var mı, okunuyor mu, kaç nokta / gateway
  3. data_collector süreci          — çalışıyor mu, kaç kopya
  4. CANLI BACnet deneme okuması    — şu an gateway cevap veriyor mu (ReadProperty, salt okuma)
  5. energy_data.csv                — hangi sütun kaç gündür aynı değerde
  6. Log dosyaları                  — BACnet satırları (varsa)
  → TEŞHİS: kural tabanlı sonuç cümlesi ("nerede koptu")

Hiçbir dosyayı değiştirmez, süreç başlatmaz/durdurmaz, BACnet'e YAZMAZ.
Sonuç: configs/saha_teshis_sonuc.json   (oz_test.py çağırır → heartbeat → Synapse)

    python saha_teshis.py          → çalıştır ve yazdır
    python saha_teshis.py --oku    → son sonucu yazdır
"""
import csv
import glob
import json
import os
import subprocess
import sys
from datetime import datetime

BURASI = os.path.dirname(os.path.abspath(__file__))
SONUC_DOSYASI = os.path.join(BURASI, "configs", "saha_teshis_sonuc.json")
BACNET_CSV = os.path.join(BURASI, "hedefli_enerji_verileri.csv")
MODBUS_CSV = os.path.join(BURASI, "analizor_guncel_veriler.csv")
ENERGY_CSV = os.path.join(BURASI, "energy_data.csv")
BAYAT_SAAT = 26          # günlük okuma + tolerans
DONMA_GUN = 4            # bu kadar gün aynı değer = donmuş say
CANLI_ZAMAN_ASIMI = 6.0  # canlı deneme okumasında nokta başına saniye
CANLI_NOKTA = 5

# energy_data'da BACnet'ten gelen ÖLÇÜM sütunları (data_bridge.BACNET_MAP hedefleri).
# Chiller set ve cihaz adetleri bilerek YOK: haftalarca aynı kalmaları normaldir,
# donma taramasına girerse sahte alarm üretir. Ondalıklı ölçümün günlerce birebir
# aynı kalması ise fiziksel olarak olanaksızdır.
BACNET_SUTUNLARI = ["Dis_Hava_Sicakligi_C", "Chiller_Load_Percent", "Mas1_Isitma_Temp",
                    "Mas1_Kazan_Temp", "Mas2_Isitma_Temp", "Mas2_Kazan_Temp",
                    "Mas1_Sogutma_Temp", "Mas2_Sogutma_Temp"]


def _saat_once(ts: datetime) -> float:
    return round((datetime.now() - ts).total_seconds() / 3600, 1)


def bacnet_csv_durumu() -> dict:
    if not os.path.exists(BACNET_CSV):
        return {"var": False}
    satirlar = []
    with open(BACNET_CSV, newline="", encoding="utf-8") as f:
        satirlar = list(csv.DictReader(f))
    mtime = datetime.fromtimestamp(os.path.getmtime(BACNET_CSV))
    zamanlar = [s.get("Timestamp", "") for s in satirlar if s.get("Timestamp")]
    son = max(zamanlar) if zamanlar else None
    hatalar = {}
    for s in satirlar:
        if s.get("Status") != "OK":
            k = (s.get("Status") or "?")[:40]
            hatalar[k] = hatalar.get(k, 0) + 1
    son_dt = datetime.strptime(son, "%Y-%m-%d %H:%M:%S") if son else mtime
    dis = next((s for s in satirlar if s.get("Point_Name", "").strip() == "DIS HAVA"), None)
    return {
        "var": True, "nokta": len(satirlar),
        "ok": sum(1 for s in satirlar if s.get("Status") == "OK"),
        "son_okuma": son, "dosya_degisti": mtime.isoformat(timespec="seconds"),
        "saat_once": _saat_once(son_dt), "bayat": _saat_once(son_dt) > BAYAT_SAAT,
        "hatalar": dict(sorted(hatalar.items(), key=lambda x: -x[1])[:5]),
        "dis_hava": dis.get("Value") if dis else None,
    }


SABLON_ADI = "hedefli_okuma_sablonu_2.xlsx"


def _sablon_yolu():
    yollar = [os.path.join(BURASI, "configs", SABLON_ADI), os.path.join(BURASI, SABLON_ADI)]
    return next((y for y in yollar if os.path.exists(y)), None)


def sablon_durumu() -> dict:
    """Şablon NEREDE ve data_collector onu BULABİLİYOR mu — ikisi ayrı sorudur.
    ahu_collector (Mekanik Zeka) önce configs/, sonra kökte arar; data_collector'ın
    kendi yolu ayrıca okunur. İkisi ayrışırsa Mekanik Zeka çalışır, enerji
    tablosunun BACnet okuması başlamaz."""
    configs_var = os.path.exists(os.path.join(BURASI, "configs", SABLON_ADI))
    kok_var = os.path.exists(os.path.join(BURASI, SABLON_ADI))
    try:
        import data_collector as dc
        collector_yolu = os.path.relpath(dc.EXCEL_FILE, BURASI)
        collector_buluyor = os.path.exists(dc.EXCEL_FILE)
    except Exception as e:
        collector_yolu, collector_buluyor = "okunamadı: %s" % type(e).__name__, None
    r = {"var": configs_var or kok_var, "configs_var": configs_var, "kok_var": kok_var,
         "collector_yolu": collector_yolu, "collector_buluyor": collector_buluyor}
    yol = _sablon_yolu()
    if not yol:
        return r
    try:
        import pandas as pd
        df = pd.read_excel(yol)
        df["Gateway IP"] = df["Gateway IP"].ffill()
        r.update(okunuyor=True, nokta=int(len(df)),
                 gateway=sorted({str(g).strip() for g in df["Gateway IP"].dropna()})[:5])
    except Exception as e:
        r.update(okunuyor=False, hata=f"{type(e).__name__}: {e}"[:200])
    return r


def surec_durumu() -> dict:
    """Çalışan python süreçlerinin komut satırları (Windows: CIM, diğer: ps)."""
    try:
        if os.name == "nt":
            komut = ["powershell", "-NoProfile", "-Command",
                     "Get-CimInstance Win32_Process -Filter \"Name like 'python%'\" | "
                     "Select-Object -ExpandProperty CommandLine"]
        else:
            komut = ["ps", "-eo", "args"]
        cikti = subprocess.run(komut, capture_output=True, text=True, timeout=20,
                               errors="replace").stdout or ""
    except Exception as e:
        return {"olculemedi": f"{type(e).__name__}: {e}"[:120]}
    satir = [s for s in cikti.splitlines() if s.strip()]
    say = lambda ad: sum(1 for s in satir if ad in s)
    return {"data_collector": say("data_collector.py"), "data_bridge": say("data_bridge.py"),
            "cloud_sync": say("cloud_sync.py"), "watchdog": say("portal_watchdog.py")}


def canli_bacnet_denemesi() -> dict:
    """Şablondaki ilk birkaç noktayı ŞİMDİ okur (ReadProperty — salt okuma)."""
    try:
        import pandas as pd
        import data_collector as dc
        yol = _sablon_yolu()
        if not yol:
            return {"denendi": 0, "ok": 0, "hata": "şablon bulunamadı"}
        df = pd.read_excel(yol)
        df["Gateway IP"] = df["Gateway IP"].ffill()
        df["Network (DNET)"] = df["Network (DNET)"].ffill()
        oncelik = df[df["Point Name"].astype(str).str.strip() == "DIS HAVA"]
        secim = pd.concat([oncelik, df.drop(oncelik.index).head(CANLI_NOKTA - len(oncelik))])
        eski = dc.BACNET_TIMEOUT
        dc.BACNET_TIMEOUT = CANLI_ZAMAN_ASIMI
        sonuclar = []
        try:
            for _, r in secim.iterrows():
                v = dc.bacnet_nokta_oku(str(r["Gateway IP"]).strip(), int(float(r["Network (DNET)"])),
                                        str(r["MAC (DADR)"]), int(float(r["Object Type"])),
                                        int(float(r["Object Instance"])), dc.PROP_PRESENT_VALUE)
                sonuclar.append({"nokta": str(r["Point Name"]), "deger": v if isinstance(v, (int, float)) else None,
                                 "durum": "OK" if isinstance(v, (int, float)) else str(v)[:40]})
        finally:
            dc.BACNET_TIMEOUT = eski
        return {"denendi": len(sonuclar), "ok": sum(1 for s in sonuclar if s["durum"] == "OK"),
                "sonuclar": sonuclar}
    except Exception as e:
        return {"denendi": 0, "ok": 0, "hata": f"{type(e).__name__}: {e}"[:200]}


def donma_taramasi() -> dict:
    """energy_data.csv: her BACnet sütunu son kaç gündür aynı değerde."""
    if not os.path.exists(ENERGY_CSV):
        return {}
    with open(ENERGY_CSV, newline="", encoding="utf-8") as f:
        satirlar = list(csv.DictReader(f))[-90:]
    sonuc = {}
    for c in BACNET_SUTUNLARI:
        degerler = [s.get(c, "") for s in satirlar if s.get(c, "") not in ("", None)]
        if len(degerler) < DONMA_GUN:
            continue
        son, n = degerler[-1], 0
        for v in reversed(degerler):
            if v != son:
                break
            n += 1
        if n >= DONMA_GUN:
            ilk = satirlar[len(satirlar) - n]["Tarih"] if n <= len(satirlar) else "?"
            sonuc[c] = {"gun": n, "deger": son, "baslangic": ilk}
    return sonuc


def log_taramasi() -> list:
    bulunan = []
    for yol in glob.glob(os.path.join(BURASI, "*.log")) + glob.glob(os.path.join(BURASI, "logs", "*.log")):
        try:
            with open(yol, encoding="utf-8", errors="replace") as f:
                satirlar = [s.rstrip() for s in f if "BACnet" in s or "bacnet" in s]
            if satirlar:
                bulunan.append({"dosya": os.path.basename(yol), "son": satirlar[-3:]})
        except Exception:
            pass
    return bulunan[:3]


def teshis_koy(r: dict) -> list:
    """Ölçümlerden 'nerede koptu' cümleleri. En önemlisi başta."""
    t = []
    csvd, sab, sur, can, don = r["bacnet_csv"], r["sablon"], r["surec"], r["canli"], r["donma"]
    if not sab.get("var"):
        t.append("KRİTİK: BACnet okuma şablonu (hedefli_okuma_sablonu_2.xlsx) yok — BACnet okuması hiç başlamaz.")
    elif sab.get("collector_buluyor") is False:
        t.append("KRİTİK: şablon %s ama data_collector '%s' yolunda arıyor ve BULAMIYOR — "
                 "enerji tablosunun BACnet okuması başlamıyor (Mekanik Zeka configs/'u da aradığı "
                 "için o çalışmaya devam ediyor)." % ("configs/ altında" if sab.get("configs_var") else "kökte",
                                                       sab.get("collector_yolu")))
    elif not sab.get("okunuyor"):
        t.append("KRİTİK: BACnet şablonu açılamıyor (%s) — okuma iş parçacığı başlamadan kapanıyor." % sab.get("hata"))
    if sur.get("data_collector") == 0:
        t.append("KRİTİK: data_collector.py çalışmıyor — Modbus ve BACnet günlük okuması yapılmıyor.")
    elif (sur.get("data_collector") or 0) > 1:
        t.append("UYARI: data_collector.py %d kopya çalışıyor — dosyaya aynı anda yazma çakışması olabilir."
                 % sur["data_collector"])
    if csvd.get("bayat"):
        neden = "BACnet okuması %.0f saattir yapılmıyor (son: %s)." % (csvd["saat_once"], csvd["son_okuma"])
        if can.get("ok"):
            t.append("KRİTİK: " + neden + " Gateway ŞU AN cevap veriyor → sorun ağda değil, "
                     "günlük okuma iş parçacığında (durmuş ya da 07:05 penceresi kaçıyor).")
        elif can.get("denendi"):
            t.append("KRİTİK: " + neden + " Canlı denemede de cevap yok → gateway/ağ/BACnet cihazı tarafı.")
        else:
            t.append("KRİTİK: " + neden)
    elif csvd.get("var") and csvd.get("nokta") and csvd["ok"] < csvd["nokta"] * 0.5:
        t.append("UYARI: son BACnet okumasında %d/%d nokta OK; hatalar: %s" % (csvd["ok"], csvd["nokta"], csvd["hatalar"]))
    if don:
        en = max(don.values(), key=lambda v: v["gun"])
        t.append("UYARI: energy_data'da %d BACnet sütunu donmuş (en uzun %d gün, %s'ten beri) — "
                 "data_bridge eski dosyayı her gün yeniden yazıyor." % (len(don), en["gun"], en["baslangic"]))
    if not t:
        t.append("TAMAM: BACnet zinciri sağlıklı.")
    return t


def calistir() -> dict:
    bas = datetime.now()
    r = {"zaman": bas.isoformat(timespec="seconds")}
    for ad, fn in (("bacnet_csv", bacnet_csv_durumu), ("sablon", sablon_durumu), ("surec", surec_durumu),
                   ("canli", canli_bacnet_denemesi), ("donma", donma_taramasi), ("loglar", log_taramasi)):
        try:
            r[ad] = fn()
        except Exception as e:
            r[ad] = {"hata": f"{type(e).__name__}: {e}"[:200]}
    r["teshis"] = teshis_koy(r)
    r["durum"] = "KRITIK" if any(x.startswith("KRİTİK") for x in r["teshis"]) else \
                 ("UYARI" if any(x.startswith("UYARI") for x in r["teshis"]) else "TAMAM")
    r["sure_sn"] = round((datetime.now() - bas).total_seconds(), 1)
    try:
        os.makedirs(os.path.dirname(SONUC_DOSYASI), exist_ok=True)
        gecici = SONUC_DOSYASI + ".tmp"
        with open(gecici, "w", encoding="utf-8") as f:
            json.dump(r, f, ensure_ascii=False, indent=1)
        os.replace(gecici, SONUC_DOSYASI)
    except Exception:
        pass
    return r


def son_ozet() -> dict:
    """Heartbeat için KÜÇÜK özet (bakim_ozet şişmesin)."""
    try:
        with open(SONUC_DOSYASI, encoding="utf-8") as f:
            r = json.load(f)
    except Exception:
        return {}
    csvd, can, sur = r.get("bacnet_csv") or {}, r.get("canli") or {}, r.get("surec") or {}
    sab = r.get("sablon") or {}
    return {
        "zaman": r.get("zaman"), "durum": r.get("durum"),
        "teshis": (r.get("teshis") or [])[:4],
        "bacnet_son_okuma": csvd.get("son_okuma"), "bacnet_ok": [csvd.get("ok"), csvd.get("nokta")],
        "canli_ok": [can.get("ok"), can.get("denendi")], "collector": sur.get("data_collector"),
        "sablon": {"configs": sab.get("configs_var"), "kok": sab.get("kok_var"),
                   "collector_buluyor": sab.get("collector_buluyor")},
        "donmus_sutun": sorted((r.get("donma") or {}).keys()),
    }


if __name__ == "__main__":
    if "--oku" in sys.argv:
        print(json.dumps(son_ozet(), ensure_ascii=False, indent=1))
        sys.exit(0)
    s = calistir()
    print(json.dumps({k: v for k, v in s.items() if k != "teshis"}, ensure_ascii=False, indent=1)[:4000])
    print("\nTEŞHİS (%s):" % s["durum"])
    for x in s["teshis"]:
        print("  • " + x)
