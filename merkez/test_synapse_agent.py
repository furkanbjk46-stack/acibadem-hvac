#!/usr/bin/env python3
"""synapse_agent.py testi — ağ ve sunucu yok; veritabanı (PostgREST) ve sunucu bilgileri taklit edilir."""
import os
import re
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import synapse_agent as S  # noqa: E402

gecti = kaldi = 0


def c(ad, kosul, ek=""):
    global gecti, kaldi
    if kosul:
        gecti += 1
        print("  ✓ " + ad)
    else:
        kaldi += 1
        print("  ✗ %s   %s" % (ad, ek))


IST = S.IST
SIMDI = datetime(2026, 11, 11, 14, 0, tzinfo=IST)          # 11:00 UTC


def iso(dk_once, saat_dilimsiz=False):
    z = SIMDI - timedelta(minutes=dk_once)
    return z.replace(tzinfo=None).isoformat() if saat_dilimsiz else z.astimezone(timezone.utc).isoformat()


class SahteSunucu:
    def __init__(self, disk=(50, 100, 50), bellek=(4000, 16000), servis=None, yedek="var"):
        self._disk, self._bellek, self._servis, self._yedek = disk, bellek, servis or {}, yedek

    def disk(self):
        return self._disk

    def bellek(self):
        return self._bellek

    def servis(self, ad):
        return self._servis.get(ad, "active")

    def yedekler(self):
        if self._yedek == "var":
            return [{"ad": "synapse_db_20261111_013000.dump", "bayt": 1, "zaman": SIMDI.replace(hour=1, minute=30)}]
        return self._yedek


def saglikli_veri():
    return {
        "lokasyonlar": [{"lokasyon_id": "maslak", "isim": "Maslak", "ping_zamani": iso(2, True), "versiyon": "13.6"},
                        {"lokasyon_id": "altunizade", "isim": "Altunizade", "ping_zamani": iso(1, True),
                         "versiyon": "13.6"}],
        "energy_data": [{"lokasyon_id": "maslak", "Tarih": "2026-11-10"},
                        {"lokasyon_id": "altunizade", "Tarih": "2026-11-10T00:00:00"}],
        "canli_guc": [{"lokasyon_id": "maslak", "cihaz": "S%d" % i, "olcum_zamani": iso(1)} for i in range(10)],
        "guncellemeler": [],
        "komutlar": [{"id": 1, "lokasyon": "maslak", "nokta_adi": "AHU1", "durum": "tamamlandi",
                      "created_at": iso(30), "executed_at": iso(29)}],
        "agent_bulgular": [],
    }


class SahteDb:
    """PostgREST taklidi: GET tabloyu döner, POST/PATCH çağrıları kaydedilir."""

    def __init__(self, veri, anahtarsiz=401, portal=200):
        self.veri, self.anahtarsiz, self.portal = veri, anahtarsiz, portal
        self.yazilan, self.okunan = [], []

    def __call__(self, url, yontem="GET", govde=None, ek=None, anahtarsiz=False, zaman_asimi=20):
        if url == S.PORTAL_SAGLIK:
            return self.portal, "ok"
        yol = url.split("/rest/v1/")[1]
        tablo = yol.split("?")[0]
        if anahtarsiz:
            return self.anahtarsiz, "[]"
        if yontem != "GET":
            self.yazilan.append((yontem, yol, govde))
            return 201 if yontem == "POST" else 204, None
        self.okunan.append(yol)
        satir = list(self.veri.get(tablo, []))
        m = re.search(r"durum=in\.\(([^)]*)\)", yol)
        if m:
            satir = [r for r in satir if r.get("durum") in m.group(1).split(",")]
        return 200, satir


def ortam(veri=None, **ek):
    db = SahteDb(veri or saglikli_veri(), **{k: ek.pop(k) for k in ("anahtarsiz", "portal") if k in ek})
    return S.Ortam("https://x/synapse-db", "anahtar", simdi=SIMDI, http=db, sunucu=SahteSunucu(**ek)), db


def kodlar(liste):
    return sorted(b["anahtar"] for b in liste)


print("Sağlıklı sistem")
o, db = ortam()
s = S.tur(o)
c("bütün kontroller geçti", s["ozet"]["gecti"] == s["ozet"]["toplam"] == len(S.KONTROLLER), s["kontroller"])
c("bulgu yok, bulgu yazılmadı", not s["bulgular"] and not any("agent_bulgular" in y[1] for y in db.yazilan))
tur_yaz = [y for y in db.yazilan if y[1].startswith("agent_turlar")]
c("tur satırı (merkez, synapse) yazıldı", len(tur_yaz) == 1 and tur_yaz[0][2]["lokasyon_id"] == "merkez"
  and tur_yaz[0][2]["agent"] == "synapse" and tur_yaz[0][2]["surum"] == S.SURUM)
c("gönderim başarılı", s["gonderim"] == "gönderildi", s["gonderim"])

print("\nYetki sınırı: hiçbir okuma select=* kullanmaz, yalnız izinli sütunlar")
IZINLI = {"lokasyonlar": {"lokasyon_id", "isim", "son_sync", "versiyon", "durum", "ping_zamani", "bakim_ozet"},
          "energy_data": {"lokasyon_id", "Tarih"}, "canli_guc": {"lokasyon_id", "cihaz", "olcum_zamani"},
          "guncellemeler": {"id", "versiyon", "hedef", "durum", "created_at"},
          "komutlar": {"id", "lokasyon", "nokta_adi", "durum", "created_at", "executed_at"}}
for yol in db.okunan:
    tablo, sorgu = yol.split("?")[0], yol.split("?")[1]
    sec = set(re.search(r"select=([^&]*)", sorgu).group(1).split(","))
    if tablo in IZINLI:
        c("%s yalnız izinli sütunlar (%s)" % (tablo, ",".join(sorted(sec))), sec <= IZINLI[tablo], sec - IZINLI[tablo])
    else:
        c("%s okuması select=* değil" % tablo, "*" not in sec)
c("yazılan tablolar yalnız agent_turlar / agent_bulgular",
  all(y[1].split("?")[0] in ("agent_turlar", "agent_bulgular") for y in db.yazilan))

print("\nSorunlu sistem")
v = saglikli_veri()
v["lokasyonlar"][1]["ping_zamani"] = iso(25, True)                      # altunizade 25 dk sessiz
v["lokasyonlar"][1]["versiyon"] = "13.5"
v["energy_data"] = [{"lokasyon_id": "maslak", "Tarih": "2026-11-10"}, {"lokasyon_id": "altunizade", "Tarih": "2026-11-08"}]
v["canli_guc"] = ([{"lokasyon_id": "maslak", "cihaz": "S%d" % i, "olcum_zamani": iso(1)} for i in range(6)]
                  + [{"lokasyon_id": "maslak", "cihaz": "B%d" % i, "olcum_zamani": iso(40)} for i in range(4)]
                  + [{"lokasyon_id": "altunizade", "cihaz": "A1", "olcum_zamani": iso(90)}])
v["guncellemeler"] = [{"id": "y1", "versiyon": "13.7", "hedef": "maslak", "durum": "bekliyor", "created_at": iso(45)},
                      {"id": "y2", "versiyon": "13.7", "hedef": "altunizade", "durum": "bekliyor", "created_at": iso(5)},
                      {"id": "y3", "versiyon": "13.4", "hedef": "maslak", "durum": "hata", "created_at": iso(600)},
                      {"id": "y4", "versiyon": "13.6", "hedef": "maslak", "durum": "tamamlandi", "created_at": iso(60)}]
v["komutlar"] = [{"id": 1, "lokasyon": "maslak", "nokta_adi": "AHU1", "durum": "bekliyor", "created_at": iso(20)},
                 {"id": 2, "lokasyon": "maslak", "nokta_adi": "AHU2", "durum": "bekliyor", "created_at": iso(3)},
                 {"id": 3, "lokasyon": "maslak", "nokta_adi": "AHU3", "durum": "dogrulanamadi", "created_at": iso(100)}]
o, db = ortam(v, anahtarsiz=200, portal=502, disk=(93, 100, 7), bellek=(500, 16000),
              servis={"nginx": "failed"}, yedek=[{"ad": "synapse_db_20261109_013000.dump", "bayt": 1,
                                                  "zaman": SIMDI - timedelta(hours=40)}])
s = S.tur(o)
b = {x["anahtar"]: x for x in s["bulgular"]}
beklenen = {"lokasyon_baglanti:altunizade", "gunluk_esitleme:altunizade", "canli_sayac:maslak:bayat",
            "canli_sayac:altunizade:akis", "yama_kuyrugu:bekliyor:y1", "yama_kuyrugu:hata:y3", "komutlar:bekleyen",
            "komutlar:basarisiz", "surum:fark", "anahtarsiz_erisim:energy_data", "synapse_portal:saglik",
            "sunucu:disk", "sunucu:bellek", "sunucu:servis:nginx", "sunucu:yedek"}
c("beklenen bulguların hepsi, fazlası yok", set(b) == beklenen, set(b) ^ beklenen)
c("çevrimdışı 25 dk → uyarı (60 dk altı)", b["lokasyon_baglanti:altunizade"]["onem"] == "uyari")
c("5 dk'lık yama bekleme sayılmaz", "yama_kuyrugu:bekliyor:y2" not in b)
c("hata ile biten yama kritik", b["yama_kuyrugu:hata:y3"]["onem"] == "kritik")
c("3 dk'lık komut bekleme sayılmaz, 20 dk'lık sayılır", "AHU1" in b["komutlar:bekleyen"]["bulunan"]
  and "AHU2" not in b["komutlar:bekleyen"]["bulunan"])
c("bayat sayaç listesi kanıtta", b["canli_sayac:maslak:bayat"]["kanit"]["sayaclar"] == ["B0", "B1", "B2", "B3"])
c("sürüm farkı yalnız bilgi", b["surum:fark"]["onem"] == "bilgi")
c("anahtarsız erişim açık → kritik", b["anahtarsiz_erisim:energy_data"]["onem"] == "kritik")
c("disk %93 kritik, servis kritik, 40 saatlik yedek uyarı",
  b["sunucu:disk"]["onem"] == "kritik" and b["sunucu:servis:nginx"]["onem"] == "kritik"
  and b["sunucu:yedek"]["onem"] == "uyari")
c("her bulguda başlık, beklenen, bulunan dolu",
  all(x["baslik"] and x["beklenen"] and x["bulunan"] for x in s["bulgular"]))
yaz = [y for y in db.yazilan if y[1].startswith("agent_bulgular?on_conflict")]
c("bulgular tek upsert ile yazıldı", len(yaz) == 1 and len(yaz[0][2]) == len(beklenen))
c("yazılan bulgular merkez/synapse, açık, ilk görülme 1",
  all(r["lokasyon_id"] == "merkez" and r["agent"] == "synapse" and r["durum"] == "acik"
      and r["gorulme_sayisi"] == 1 and r["acilma_sayisi"] == 1 for r in yaz[0][2]))
c("özet: 9 kontrol sorunlu", s["ozet"]["sorun"] == 9 and s["ozet"]["acik_bulgu"] == len(beklenen), s["ozet"])

print("\nBulgu ömrü veritabanından (diske yazılmaz)")
v = saglikli_veri()
v["lokasyonlar"][1]["ping_zamani"] = iso(25, True)
ilk = iso(300)
v["agent_bulgular"] = [
    {"anahtar": "lokasyon_baglanti:altunizade", "kontrol": "lokasyon_baglanti", "durum": "acik", "ilk_gorulme": ilk,
     "gorulme_sayisi": 4, "acilma_sayisi": 2},
    {"anahtar": "sunucu:disk", "kontrol": "sunucu", "durum": "acik", "ilk_gorulme": ilk, "gorulme_sayisi": 1,
     "acilma_sayisi": 1},
    {"anahtar": "gunluk_esitleme:maslak", "kontrol": "gunluk_esitleme", "durum": "acik", "ilk_gorulme": ilk,
     "gorulme_sayisi": 1, "acilma_sayisi": 1},
]
o, db = ortam(v)
kapat_once = datetime(2026, 11, 11, 8, 0, tzinfo=IST)                  # 09:00'dan önce: eşitleme atlanır
o._simdi = kapat_once
for r in v["lokasyonlar"]:
    r["ping_zamani"] = (kapat_once - timedelta(minutes=2)).replace(tzinfo=None).isoformat()
v["lokasyonlar"][1]["ping_zamani"] = (kapat_once - timedelta(minutes=25)).replace(tzinfo=None).isoformat()
for r in v["canli_guc"]:
    r["olcum_zamani"] = (kapat_once - timedelta(minutes=1)).isoformat()
s = S.tur(o)
yaz = [y for y in db.yazilan if y[1].startswith("agent_bulgular?on_conflict")][0][2]
r = [x for x in yaz if x["anahtar"] == "lokasyon_baglanti:altunizade"][0]
c("açık bulgu tekrar görülünce sayaç artar, ilk görülme korunur",
  r["gorulme_sayisi"] == 5 and r["acilma_sayisi"] == 2 and r["ilk_gorulme"] == ilk)
yamalar = [y for y in db.yazilan if y[0] == "PATCH"]
c("artık görülmeyen bulgu kapanır (sunucu:disk)",
  len(yamalar) == 1 and "sunucu%3Adisk" in yamalar[0][1] and yamalar[0][2]["durum"] == "kapandi")
c("atlanan kontrolün açık bulgusu kapanmaz (eşitleme 09:00 öncesi)",
  not any("gunluk_esitleme" in y[1] for y in yamalar) and s["kontroller"][1]["durum"] == "atlandi")

v["agent_bulgular"] = [{"anahtar": "lokasyon_baglanti:altunizade", "kontrol": "lokasyon_baglanti",
                        "durum": "kapandi", "ilk_gorulme": ilk, "gorulme_sayisi": 9, "acilma_sayisi": 2}]
o, db = ortam(v)
o._simdi = kapat_once
S.tur(o)
r = [y for y in db.yazilan if y[1].startswith("agent_bulgular?on_conflict")][0][2][0]
c("kapanmış bulgu yeniden açılınca açılma +1, görülme 1, ilk görülme yenilenir",
  r["acilma_sayisi"] == 3 and r["gorulme_sayisi"] == 1 and r["ilk_gorulme"] != ilk and r["kapanma"] is None)

print("\nHata dayanıklılığı")
v = saglikli_veri()
o, db = ortam(v)
gercek = db.__call__


def yetkisiz(url, yontem="GET", *a, **k):
    if "canli_guc" in url:
        return 401, "permission denied"
    return gercek(url, yontem, *a, **k)


o.http = yetkisiz
s = S.tur(o)
d = {k["kod"]: k["durum"] for k in s["kontroller"]}
c("okunamayan tablo kontrolü 'atlandi', diğerleri çalışır", d["canli_sayac"] == "atlandi" and d["sunucu"] == "gecti", d)


def patlak(o):
    raise ValueError("beklenmedik")


s = S.tur(ortam()[0], [("x", "X", patlak)] + S.KONTROLLER)
c("çöken kontrol 'hata' olur, tur sürer", s["kontroller"][0]["durum"] == "hata"
  and s["ozet"]["gecti"] == len(S.KONTROLLER))

print("\nSaat")
c("saat dilimsiz ping İstanbul saati kabul edilir", S.zaman("2026-11-11T14:00:00") == SIMDI)
c("UTC zaman doğru çevrilir", S.zaman("2026-11-11T11:00:00+00:00") == SIMDI)
c("bozuk zaman None", S.zaman("dün") is None and S.zaman(None) is None)

print("\n%d geçti, %d kaldı" % (gecti, kaldi))
sys.exit(1 if kaldi else 0)
