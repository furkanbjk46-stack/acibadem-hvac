# -*- coding: utf-8 -*-
"""Veri toplama alarmları — ağ bağlantısı YOK.

Korunan davranış: alarm YALNIZCA gerçek bir eksiklikte çıkmalı. Yanlış
alarm, bir süre sonra bildirim çubuğunun hiç okunmamasına yol açar; eksik
alarm ise trafo/chiller verisi sessizce boş kalır (27.09'daki çift sayım
tam da fark edilmeyen eksik veriden doğmuştu).
"""
import json
import os
import sys
import tempfile

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)

import veri_alarm as VA

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", ek)


ANALIZORLER = [{"name": n} for n in
               ("TRDP-1", "TRDP-2", "MCC-1", "MCC-5", "CHILLER-1", "KULE-2")]
TAM_OK = {n["name"]: "1234.5 kWh" for n in ANALIZORLER}
TAM_GUNLUK = {n["name"]: 100.0 for n in ANALIZORLER}


def turler(alarmlar):
    return {(a["tur"], a["grup"]) for a in alarmlar}


# ── Her şey yolundaysa alarm YOK ─────────────────────────────────────────
c("tum analizorler okundu -> alarm yok",
  VA.alarm_uret(ANALIZORLER, TAM_OK, TAM_GUNLUK) == [])
c("alarm yoksa ozet toplam 0", VA.ozet([])["toplam"] == 0)
c("alarm yoksa heartbeat ozeti BOS (heartbeat sismesin)",
  VA.ozet([])["toplam"] == 0 and not {k: v for k, v in VA.ozet([]).items() if k == "mesajlar" and v})

# ── Bağlantı hatası ──────────────────────────────────────────────────────
_csv = dict(TAM_OK, **{"TRDP-2": "[Baglanti Hatasi]"})
_al = VA.alarm_uret(ANALIZORLER, _csv, TAM_GUNLUK)
c("baglanti hatasi alarm uretir", ("baglanti", "trafo") in turler(_al), turler(_al))
c("trafo baglanti hatasi KRITIK", all(a["onem"] == "kritik" for a in _al), _al)
c("alarm mesajinda cihaz adi gecer", "TRDP-2" in _al[0]["mesaj"], _al[0]["mesaj"])
c("saglam cihazlar alarma girmez", "MCC-1" not in _al[0]["mesaj"])

_csv = dict(TAM_OK, **{"MCC-1": "[Baglanti Hatasi]", "MCC-5": "[Baglanti Hatasi]"})
_al = VA.alarm_uret(ANALIZORLER, _csv, TAM_GUNLUK)
c("MCC baglanti hatasi UYARI (toplam hesabi ayakta)",
  all(a["onem"] == "uyari" for a in _al), _al)
c("ayni gruptaki cihazlar TEK alarmda toplanir", len(_al) == 1, _al)
c("iki cihaz da listelenir", _al[0]["cihazlar"] == ["MCC-1", "MCC-5"], _al[0]["cihazlar"])

# ── CSV'de hiç görünmeyen cihaz da bağlantı hatası sayılır ──────────────
_al = VA.alarm_uret(ANALIZORLER, {k: v for k, v in TAM_OK.items() if k != "CHILLER-1"},
                    TAM_GUNLUK)
c("CSV'de olmayan cihaz baglanti hatasi sayilir",
  any("CHILLER-1" in a["cihazlar"] for a in _al), _al)
c("chiller eksikligi KRITIK", all(a["onem"] == "kritik" for a in _al))

# ── Okundu ama günlük veri üretilemedi ──────────────────────────────────
_gunluk = {k: v for k, v in TAM_GUNLUK.items() if k != "TRDP-1"}
_al = VA.alarm_uret(ANALIZORLER, TAM_OK, _gunluk)
c("okundu ama gunluk veri yoksa ayri tur", ("veri_yok", "trafo") in turler(_al), turler(_al))
c("veri_yok mesaji baglanti mesajindan farkli", "boş" in _al[0]["mesaj"], _al[0]["mesaj"])
_gunluk2 = dict(TAM_GUNLUK, **{"MCC-1": ""})
c("bos string de veri_yok sayilir",
  any("MCC-1" in a["cihazlar"] for a in VA.alarm_uret(ANALIZORLER, TAM_OK, _gunluk2)))
c("SIFIR tuketim alarm DEGIL (pano bos calisiyor olabilir)",
  VA.alarm_uret(ANALIZORLER, TAM_OK, dict(TAM_GUNLUK, **{"MCC-1": 0})) == [])

# ── İlk gün: referans yok, daily_kwh None ────────────────────────────────
_al = VA.alarm_uret(ANALIZORLER, TAM_OK, None)
c("ilk gun (referans yok) hepsi veri_yok",
  _al and all(a["tur"] == "veri_yok" for a in _al), turler(_al))
c("ilk gunde baglanti hatasi UYDURULMAZ",
  not any(a["tur"] == "baglanti" for a in _al))

# ── Sıralama ve özet ────────────────────────────────────────────────────
_karisik = VA.alarm_uret(
    ANALIZORLER,
    dict(TAM_OK, **{"MCC-1": "[Baglanti Hatasi]", "CHILLER-1": "[Baglanti Hatasi]"}),
    TAM_GUNLUK)
c("kritikler listenin basinda", _karisik[0]["onem"] == "kritik", [a["onem"] for a in _karisik])
_oz = VA.ozet(_karisik)
c("ozet toplam dogru", _oz["toplam"] == len(_karisik))
c("ozet kritik sayar", _oz["kritik"] == 1, _oz)
c("ozette cihaz listesi var", "CHILLER-1" in _oz["baglanti"], _oz["baglanti"])
c("ozet kucuk kalir (heartbeat JSONB)", len(json.dumps(_oz, ensure_ascii=False)) < 700,
  len(json.dumps(_oz, ensure_ascii=False)))

# ── CSV okuma ────────────────────────────────────────────────────────────
_gec = os.path.join(tempfile.gettempdir(), "_va_test.csv")
with open(_gec, "w", encoding="utf-8", newline="") as f:
    f.write("Okuma_Zamani,Cihaz_Adi,IP,Enerji_kWh,Durum\n")
    f.write("2026-10-07,TRDP-1,10.0.0.1,500,500 kWh\n")
    f.write("2026-10-07,TRDP-2,10.0.0.2,,[Baglanti Hatasi]\n")
_d = VA.csv_durumlari(_gec)
c("CSV durumlari okunur", _d.get("TRDP-1") == "500 kWh" and "Hatasi" in _d.get("TRDP-2", ""))
c("CSV yoksa bos sozluk (cokmez)", VA.csv_durumlari(_gec + ".yok") == {})
os.remove(_gec)

# ── Kaydet / oku çevrimi ─────────────────────────────────────────────────
_asil = VA.DURUM_DOSYA
VA.DURUM_DOSYA = os.path.join(tempfile.gettempdir(), "_va_durum.json")
try:
    _oz2 = VA.kaydet(_karisik)
    c("kaydet ozet dondurur", _oz2["toplam"] == len(_karisik))
    _geri = VA.oku()
    c("okunan alarm sayisi ayni", len(_geri["alarmlar"]) == len(_karisik))
    c("son_ozet alarm varken dolu", VA.son_ozet().get("toplam") == len(_karisik))
    VA.kaydet([])
    c("alarm temizlenince son_ozet BOS (uyari dusmeli)", VA.son_ozet() == {})
    os.remove(VA.DURUM_DOSYA)
    c("dosya yokken oku() cokmez", VA.oku()["alarmlar"] == [])
finally:
    VA.DURUM_DOSYA = _asil

# ── Bildirim tekrarı: aynı durum iki kez bildirilmemeli ─────────────────
_imza_dosya = os.path.join(tempfile.gettempdir(), "_va_imza.txt")
if os.path.exists(_imza_dosya):
    os.remove(_imza_dosya)
c("imza ayni alarm icin ayni", VA._imza(_karisik) == VA._imza(list(reversed(_karisik))))
c("imza farkli alarm icin farkli", VA._imza(_karisik) != VA._imza(_karisik[:1]))
c("alarm yoksa bildirim gonderilmez",
  VA.bildirim_gonder("https://sahte", "anahtar", "maslak", [], _imza_dosya) is False)
c("baglanti bilgisi yoksa bildirim gonderilmez",
  VA.bildirim_gonder("", "", "maslak", _karisik, _imza_dosya) is False)

# ── Bağlantı noktaları (kaynak kodu kontrolü) ───────────────────────────
_db = open(os.path.join(BURASI, "data_bridge.py"), encoding="utf-8").read()
_cs = open(os.path.join(BURASI, "cloud_sync.py"), encoding="utf-8").read()
_ap = open(os.path.join(BURASI, "app_portal.py"), encoding="utf-8").read()
c("gunluk snapshot alarm kontrolu yapar", "veri_alarm.kontrol_et" in _db)
c("heartbeat ozeti gonderir", "_veri_alarm_ozet" in _cs and '"veri_alarm"' in _cs)
c("portal bildirim cubugu alarmlari okur", "import veri_alarm" in _ap)
c("alarm kontrolu snapshot'i cokertmez (try/except)",
  "Veri alarm kontrolu yapilamadi" in _db)

_mrk = open(os.path.join(os.path.dirname(BURASI), "..", "merkez", "app_merkez.py"),
            encoding="utf-8").read()
c("Synapse canli uyarilar veri_alarm okur", 'ozet.get("veri_alarm")' in _mrk)

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
raise SystemExit(1 if basarisiz else 0)
