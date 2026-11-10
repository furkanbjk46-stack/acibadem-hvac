#!/usr/bin/env python3
"""ust_agent.py (rapor kuralları) ve agent_gorunum.py (canlı ekran) testi. Ağ gerekmez."""
import json
import os
import re
import sys
from datetime import datetime, timedelta, timezone

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import agent_gorunum as G  # noqa: E402
import ust_agent as U  # noqa: E402

gecti = kaldi = 0


def c(ad, kosul, ek=""):
    global gecti, kaldi
    if kosul:
        gecti += 1
        print("  ✓ " + ad)
    else:
        kaldi += 1
        print("  ✗ %s   %s" % (ad, ek))


AN = datetime(2026, 11, 10, 12, 0, tzinfo=timezone.utc)


def iso(dk):
    return (AN - timedelta(minutes=dk)).isoformat()


def bulgu(i=1, durum="acik", acilma=1, onem="kritik", son=5, **ek):
    b = {"id": i, "lokasyon_id": "maslak", "agent": "enerji", "anahtar": "diyagram_toplami:kural:2026-11-09",
         "kontrol": "diyagram_toplami", "bolum": "Enerji Diyagramı", "onem": onem,
         "baslik": "Enerji diyagramında Hastane Genel toplamı tutmuyor (09.11.2026)",
         "beklenen": "61.240 kWh", "bulunan": "58.904 kWh · fark −2.336 kWh",
         "denenen": "günü yeniden hesaplattı → fark sürüyor", "tekrar_adimi": "Diyagramı aç",
         "olasi_yer": "enerji_hesap.py", "durum": durum, "ilk_gorulme": iso(60), "son_gorulme": iso(son),
         "gorulme_sayisi": 4, "acilma_sayisi": acilma}
    b.update(ek)
    return b


def rapor(i=10, bulgu_id=1, durum="acik", acilma=1, **ic):
    icerik = {"acilma": acilma, "bulunan": "58.904 kWh · fark −2.336 kWh", "son_gorulme": iso(5),
              "gorulme_sayisi": 4}
    icerik.update(ic)
    return {"id": i, "rapor_no": "RPR-2026-1110-001", "bulgu_id": bulgu_id, "lokasyon_id": "maslak",
            "agent": "enerji", "tur": "ariza", "onem": "yuksek", "durum": durum, "baslik": "x",
            "icerik": icerik, "olaylar": [{"zaman": iso(60), "olay": "acildi", "metin": "açıldı"}]}


def tur_satiri(lok="maslak", dk=5, agent="enerji"):
    return {"lokasyon_id": lok, "agent": agent, "tur_zamani": iso(dk)}


print("kararlar: rapor açma")
k = U.kararlar([bulgu()], [], [tur_satiri()], AN)
c("açık bulgu için rapor açılır", len(k["yeni"]) == 1 and k["guncelle"] == [], k)
r = k["yeni"][0]
c("rapor bulgunun bütün alanlarını taşır",
  all(r["icerik"][a] for a in ("beklenen", "bulunan", "denenen", "tekrar_adimi", "olasi_yer", "bolum")))
c("önem eşlemesi kritik → yüksek", r["onem"] == "yuksek" and r["durum"] == "acik" and r["tur"] == "ariza")
c("açılış olayı yazılır", r["olaylar"][0]["olay"] == "acildi")
k = U.kararlar([bulgu()], [rapor()], [tur_satiri()], AN)
c("aynı açılış için ikinci rapor açılmaz", k["yeni"] == [], k["yeni"])
k = U.kararlar([bulgu(acilma=3, onem="uyari")], [], [], AN)
c("3. kez açılan bulgu tekrarlayan sayılır, önem yükselir",
  k["yeni"][0]["icerik"].get("tekrarlayan") and k["yeni"][0]["onem"] == "yuksek"
  and any(o["olay"] == "tekrarlayan" for o in k["yeni"][0]["olaylar"]))
c("kapanmış bulgu için rapor açılmaz", U.kararlar([bulgu(durum="kapandi")], [], [], AN)["yeni"] == [])
_elle = dict(rapor(durum="kapandi"), icerik={"acilma": 1})
c("elle kapatılan iş emri, sorun sürse de yeniden açılmaz",
  U.kararlar([bulgu()], [], [], AN, gecmis=[_elle])["yeni"] == [])
c("aynı sorun kapanıp YENİDEN çıkarsa (açılma 2) yeni iş emri açılır",
  len(U.kararlar([bulgu(acilma=2)], [], [], AN, gecmis=[_elle])["yeni"]) == 1)
c("'bilgi' önemindeki bulgu iş emri açmaz", U.kararlar([bulgu(onem="bilgi")], [], [], AN)["yeni"] == [])

print("kararlar: takip ve kapanış")
k = U.kararlar([bulgu(durum="kapandi")], [rapor()], [], AN)
c("kimse dokunmadan bulgu kapandı → rapor 'kendiliğinden' kapanır",
  k["guncelle"][0][1]["durum"] == "kapandi" and "kendiliğinden" in k["guncelle"][0][1]["cozum"])
k = U.kararlar([bulgu(durum="kapandi")], [rapor(durum="dogrulaniyor", dogrulama_zamani=iso(30))], [], AN)
c("yama sonrası bulgu kapandı → 'agent tekrar kontrolü geçti'",
  k["guncelle"][0][1]["durum"] == "kapandi" and "doğrulandı" in k["guncelle"][0][1]["cozum"]
  and k["guncelle"][0][1]["olaylar"][-1]["olay"] == "dogrulandi")
k = U.kararlar([bulgu(son=2)], [rapor(durum="dogrulaniyor", dogrulama_zamani=iso(20))], [], AN)
c("yamadan hemen sonra (pay içinde) sorun görülse de rapor açılmaz", not any(
    a.get("durum") == "acik" for _, a in k["guncelle"]), k["guncelle"])
k = U.kararlar([bulgu(son=2)], [rapor(durum="dogrulaniyor", dogrulama_zamani=iso(120))], [], AN)
g = k["guncelle"][0][1]
c("pay geçtikten sonra sorun sürüyor → 'düzeltme tutmadı', yeniden açılır",
  g["durum"] == "acik" and g["icerik"]["deneme"] == 1 and "dogrulama_zamani" not in g["icerik"]
  and g["olaylar"][-1]["olay"] == "tutmadi")
k = U.kararlar([bulgu(acilma=2)], [rapor(acilma=1)], [], AN)
c("bulgu kapanıp yeniden açıldıysa eski rapor kapanır, yeni açılış için yeni rapor açılır",
  k["guncelle"][0][1]["durum"] == "kapandi" and len(k["yeni"]) == 1 and k["yeni"][0]["icerik"]["acilma"] == 2)
k = U.kararlar([bulgu(gorulme_sayisi=9)], [rapor()], [], AN)
c("açık raporun kanıtı tazelenir (görülme sayısı)", k["guncelle"] and k["guncelle"][0][1]["icerik"]["gorulme_sayisi"] == 9)
k = U.kararlar([bulgu()], [rapor()], [], AN)
c("değişiklik yoksa yazma yapılmaz", k == {"yeni": [], "guncelle": []}, k)

print("kararlar: çapraz (susan agent)")
k = U.kararlar([], [], [tur_satiri("bodrum", 130), tur_satiri("maslak", 5), tur_satiri("merkez", 1, "ust")], AN)
c("45 dk'dır tur atmayan agent için çapraz rapor açılır",
  len(k["yeni"]) == 1 and k["yeni"][0]["tur"] == "capraz" and "bodrum" in k["yeni"][0]["baslik"])
cr = dict(rapor(i=11, bulgu_id=None), tur="capraz", icerik={"capraz": "susan:bodrum:enerji"})
k = U.kararlar([], [cr], [tur_satiri("bodrum", 130)], AN)
c("açık çapraz rapor varken ikincisi açılmaz", k["yeni"] == [])
k = U.kararlar([], [cr], [tur_satiri("bodrum", 3)], AN)
c("agent yeniden tur atınca çapraz rapor kapanır", k["guncelle"][0][1]["durum"] == "kapandi")
c("üst agent'ın kendi tur satırı susan agent sayılmaz",
  U.kararlar([], [], [tur_satiri("merkez", 500, "ust")], AN)["yeni"] == [])

print("tur (sahte veritabanı)")


class SahteDb(U.Db):
    def __init__(self, tablolar):
        self.t = tablolar
        self.yazilan = []

    def oku(self, yol):
        tablo, _, sorgu = yol.partition("?")
        satirlar = list(self.t.get(tablo, []))
        for parca in sorgu.split("&"):
            alan, _, ifade = parca.partition("=")
            if alan in ("select", "order", "limit") or not ifade:
                continue
            op, _, deger = ifade.partition(".")
            if op == "eq":
                satirlar = [r for r in satirlar if str(r.get(alan)) == deger]
            elif op == "in":
                liste = deger.strip("()").split(",")
                satirlar = [r for r in satirlar if str(r.get(alan)) in liste]
            elif op == "like":
                satirlar = [r for r in satirlar if str(r.get(alan)).startswith(deger.rstrip("*").replace("%2D", "-"))]
        return satirlar

    def ekle(self, tablo, satir):
        satir = dict(satir, id=100 + len(self.yazilan))
        self.t.setdefault(tablo, []).append(satir)
        self.yazilan.append(("ekle", tablo, satir))

    def degistir(self, tablo, filtre, alanlar):
        rid = int(filtre.split(".")[1])
        for r in self.t.get(tablo, []):
            if r["id"] == rid:
                r.update(alanlar)
        self.yazilan.append(("degistir", tablo, rid, alanlar))

    def ust_tur_yaz(self, ozet, an):
        self.yazilan.append(("tur", ozet))


db = SahteDb({"agent_bulgular": [bulgu()], "agent_raporlar": [
    {"id": 5, "rapor_no": "RPR-2026-1110-004", "durum": "kapandi", "bulgu_id": None, "icerik": {}}],
    "agent_turlar": [tur_satiri()]})
s = U.tur(db, AN)
c("ilk tur raporu açar, numara günün sıradaki numarası", s["acilan"] == ["RPR-2026-1110-005"], s)
c("üst agent kendi tur satırını yazar", db.yazilan[-1][0] == "tur" and db.yazilan[-1][1]["acilan"] == 1)
s = U.tur(db, AN)
c("ikinci tur aynı raporu tekrar açmaz", s["acilan"] == [], s)
db.t["agent_bulgular"][0]["durum"] = "kapandi"
s = U.tur(db, AN)
r = [x for x in db.t["agent_raporlar"] if x.get("rapor_no") == "RPR-2026-1110-005"][0]
c("bulgu kapanınca (açık bulgu sorgusunda yok) bağlı rapor yine bulunur ve kapanır", r["durum"] == "kapandi", r)
db2 = SahteDb({"agent_bulgular": [bulgu(i=7)], "agent_turlar": [], "agent_raporlar": [
    {"id": 70, "rapor_no": "RPR-2026-1110-009", "durum": "kapandi", "bulgu_id": 7, "icerik": {"acilma": 1}}]})
c("tur: elle kapatılmış iş emrinin bulgusu için yeni rapor açılmaz", U.tur(db2, AN)["acilan"] == [])
c("üst agent bulgulara ve diğer tablolara YAZMAZ",
  {y[1] for y in db.yazilan if y[0] in ("ekle", "degistir")} == {"agent_raporlar"})
c("gece yarısı İstanbul gününe göre numara",
  U.rapor_no(SahteDb({"agent_raporlar": []}), datetime(2026, 11, 10, 22, 30, tzinfo=timezone.utc))
  == "RPR-2026-1111-001")

print("servis / merkez devri")
c("tur satırına kaynak yazılır", U.tur(SahteDb({"agent_bulgular": [], "agent_raporlar": [], "agent_turlar": []}), AN,
                                       kaynak="servis")["ozet"]["kaynak"] == "servis")
_sv = lambda dk, kaynak: SahteDb({"agent_turlar": [{"lokasyon_id": "merkez", "agent": "ust", "tur_zamani": iso(dk),
                                                    "ozet": {"kaynak": kaynak}}]})
c("servis 2 dk önce tur attıysa merkezdeki yedek çalışmaz", U.servis_aktif(_sv(2, "servis"), AN))
c("servis 10 dk'dır susuyorsa merkez yedeği devreye girer", not U.servis_aktif(_sv(10, "servis"), AN))
c("son turu merkez yedeği attıysa servis yok sayılır", not U.servis_aktif(_sv(1, "merkez"), AN))
c("tur satırı yoksa servis yok", not U.servis_aktif(SahteDb({"agent_turlar": []}), AN))

print("eylemler (Synapse düğmeleri)")
r0 = rapor()
a = U.eylem_alanlari(r0, "baslat", "furkan", an=AN)
c("düzeltmeye başladım → duzeltiliyor, olay ve düzelten", a["durum"] == "duzeltiliyor" and a["duzelten"] == "furkan"
  and a["olaylar"][-1]["olay"] == "baslat" and len(r0["olaylar"]) == 1)
a = U.eylem_alanlari(r0, "yama", "furkan", "enerji_hesap düzeltildi, 3a2b1c", AN)
c("yama gönderildi → dogrulaniyor + doğrulama zamanı + not", a["durum"] == "dogrulaniyor"
  and a["icerik"]["dogrulama_zamani"] == AN.isoformat() and "3a2b1c" in a["cozum"])
a = U.eylem_alanlari(r0, "kapat", "furkan", "sahada kojen bakımdaydı", AN)
c("elle kapat → kapandi + kapanma + gerekçe", a["durum"] == "kapandi" and a["kapanma"] and "bakımdaydı" in a["cozum"])
k = U.kararlar([bulgu(durum="kapandi")], [dict(r0, durum="dogrulaniyor",
                                                icerik=U.eylem_alanlari(r0, "yama", "f", an=AN - timedelta(hours=1))["icerik"])], [], AN)
c("yama → bulgu kapandı zinciri raporu 'doğrulandı' diye kapatır", k["guncelle"][0][1]["olaylar"][-1]["olay"] == "dogrulandi")

print("gorunum")
turlar = [dict(tur_satiri(), kontroller=[{"kod": "diyagram_toplami", "durum": "sorun", "mesaj": "<b>x</b>"},
                                          {"kod": "gunluk_dongu", "durum": "gecti", "mesaj": ""}]),
          dict(tur_satiri("merkez", 1, "ust"))]
kotu = dict(rapor(), baslik="<script>alert(1)</script>", rapor_no="RPR-1",
            icerik={"bulunan": "<img src=x onerror=alert(1)>", "olasi_yer": "a & b", "acilma": 1},
            olusturma=iso(30), guncelleme=iso(10))
v = G.gorunum(turlar, [bulgu()], [kotu, dict(rapor(i=2), durum="kapandi", kapanma=iso(100))], AN)
c("açık sorunlu agent 'hata' ve kırmızı rozet", v["agentlar"]["e"]["durum"] == "hata" and "1 açık sorun" in v["agentlar"]["e"]["rozet"])
c("kurulmamış agent'lar boş durumda", v["agentlar"]["m"]["durum"] is None and v["agentlar"]["s"]["durum"] is None)
c("üst agent 1 dk önce tur attı → çalışıyor, çipler yanık", v["ust"]["durum"] == "ok" and v["ust"]["cip"])
c("kontrol durumları sayfaya gider", v["kontroller"]["diyagram_toplami"]["durum"] == "sorun")
c("açık rapor önce, kapanan sonra", [r["durum"] for r in v["raporlar"]] == ["acik", "kapandi"])
dok = json.dumps(v, ensure_ascii=False)
c("DB'den gelen HTML kaçırılır (script/img/&)", "<script>" not in dok and "<img" not in dok and "<b>x" not in dok
  and "&lt;script&gt;" in dok and "a &amp; b" in dok)
c("şu an: açık iş emri sayısı", v["su_an"]["baslik"] == "1 açık iş emri" and v["acik_sayisi"] == 1)
v2 = G.gorunum([dict(tur_satiri(dk=90))], [], [], AN)
c("90 dk tur yok → agent 'susuyor'", v2["agentlar"]["e"]["durum"] == "bekle" and "susuyor" in v2["agentlar"]["e"]["rozet"])
c("üst agent hiç çalışmadıysa 'hata'", v2["ust"]["durum"] == "hata")
v3 = G.gorunum([], [], [], AN)
import html as _html  # noqa: E402
c("hiç veri yokken 'henüz çalışmıyor' (metin HTML olarak kaçırılmış gelir)",
  _html.unescape(v3["su_an"]["baslik"]).startswith("Agent'lar henüz") and v3["anlik"] is None)

print("sayfa")
sablon = open(os.path.join(BURASI, "sunum", "agent_katmanlari.html"), encoding="utf-8").read()
sy = G.sayfa(sablon, v)
c("veri sayfaya enjekte edilir, açık tema", "window.SYNAPSE_CANLI = " in sy and 'data-tema="acik"' in sy)
c("enjekte edilen JSON </script> içeremez", "</script" not in sy.split("window.SYNAPSE_CANLI = ")[1].split(";</script>")[0])
c("sayfada canlı mod var, simülasyon canlıda otomatik oynamaz",
  "function canliCiz" in sablon and re.search(r"if \(window\.SYNAPSE_CANLI\) \{ canliCiz", sablon)
  and "else { sifirla(); if (!azHareket)" in sablon)
c("sayfadaki kontrol eşlemesi enerji_agent kontrol kodlarıyla aynı",
  all(k in sablon for k in ("diyagram_toplami", "gunluk_dongu", "sayac_erisimi", "donmus_veri", "veri_kalitesi",
                            "hava_durumu", "yerel_bulut", "portal_sagligi")))
_ea = os.path.join(BURASI, "..", "hvac", "deneme", "enerji_agent.py")
if os.path.exists(_ea):
    _kodlar = set(re.findall(r'\("([a-z_]+)", "[^"]+", k_', open(_ea, encoding="utf-8").read()))
    c("enerji_agent'ın 8 kontrolünün hepsi ekranda adlandırılmış", _kodlar == set(G.KONTROL_AD), _kodlar ^ set(G.KONTROL_AD))

print("\n%d geçti, %d kaldı" % (gecti, kaldi))
sys.exit(1 if kaldi else 0)
