# -*- coding: utf-8 -*-
"""Agent ekranı: lokasyon × agent matrisi ve lokasyon seçici (yol haritası F2). Ağ gerekmez."""
import os
import sys
from datetime import datetime, timedelta, timezone

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import agent_gorunum as G  # noqa: E402

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", str(ek)[:300])


AN = datetime(2026, 11, 12, 10, 0, tzinfo=timezone.utc)


def z(dk):
    return (AN - timedelta(minutes=dk)).isoformat()


LOK = [{"lokasyon_id": "maslak", "isim": "Maslak"}, {"lokasyon_id": "atasehir", "isim": "Ataşehir"},
       {"lokasyon_id": "altunizade", "isim": "Altunizade <b>"}]
TUR = [{"lokasyon_id": "maslak", "agent": "enerji", "tur_zamani": z(5)},
       {"lokasyon_id": "maslak", "agent": "mekanik_zeka", "tur_zamani": z(4)},
       {"lokasyon_id": "atasehir", "agent": "enerji", "tur_zamani": z(120)},
       {"lokasyon_id": "merkez", "agent": "synapse", "tur_zamani": z(3)},
       {"lokasyon_id": "merkez", "agent": "ust", "tur_zamani": z(1)}]
BUL = [{"id": 1, "lokasyon_id": "maslak", "agent": "enerji", "anahtar": "donmus_veri:TRDP-1", "durum": "acik"},
       {"id": 2, "lokasyon_id": "merkez", "agent": "synapse", "anahtar": "lokasyon_baglanti:atasehir", "durum": "acik"},
       {"id": 3, "lokasyon_id": "merkez", "agent": "synapse", "anahtar": "sunucu:disk", "durum": "acik"}]
RAP = [{"bulgu_id": 1, "lokasyon_id": "maslak", "agent": "enerji", "durum": "acik", "rapor_no": "R1"},
       {"bulgu_id": 2, "lokasyon_id": "merkez", "agent": "synapse", "durum": "dogrulaniyor", "rapor_no": "R2"},
       {"bulgu_id": 3, "lokasyon_id": "merkez", "agent": "synapse", "durum": "acik", "rapor_no": "R3"},
       {"bulgu_id": 9, "lokasyon_id": "maslak", "agent": "mekanik_zeka", "durum": "kapandi", "rapor_no": "R9"}]

M = G.matris(TUR, BUL, RAP, LOK, AN)
s = {x["lokasyon_id"]: x["hucreler"] for x in M}
c("her kayıtlı lokasyon bir satır", set(s) == {"maslak", "atasehir", "altunizade"})
c("açık iş emri → hata", s["maslak"]["enerji"] == {"durum": "hata", "metin": "1 iş emri"}, s["maslak"])
c("kapanmış iş emri hücreyi kırmızı yapmaz", s["maslak"]["mekanik_zeka"]["durum"] == "ok")
c("eski tur → susuyor", s["atasehir"]["enerji"]["durum"] == "bekle")
c("tur yoksa 'tur yok'", s["atasehir"]["mekanik_zeka"]["durum"] == "yok" and s["altunizade"]["enerji"]["durum"] == "yok")
c("Synapse iş emri anahtardaki lokasyona yazılır", s["atasehir"]["synapse"]["durum"] == "hata"
  and s["maslak"]["synapse"]["durum"] == "ok", (s["atasehir"]["synapse"], s["maslak"]["synapse"]))
c("lokasyona özgü olmayan Synapse iş emri (sunucu) satırlara dağıtılmaz", s["altunizade"]["synapse"]["durum"] == "ok")
c("sorunlu lokasyonlar üstte", [x["lokasyon_id"] for x in M][:2] in (["atasehir", "maslak"], ["maslak", "atasehir"]))
c("merkez satır olmaz", "merkez" not in s and len(G.matris(TUR, BUL, RAP, LOK + [{"lokasyon_id": "merkez"}], AN)) == 3)
h = G.matris_html(M)
c("tablo metni kaçırılır", "Altunizade &lt;b&gt;" in h and "<b>" not in h)

t, b, r = G.suz(TUR, BUL, RAP, "maslak", LOK)
c("süzme: yalnız seçilen lokasyonun portal agent turları", {x["lokasyon_id"] for x in t} == {"maslak", "merkez"})
c("süzme: başka lokasyonun Synapse iş emri gider, genel olan kalır", {x["rapor_no"] for x in r} == {"R1", "R3", "R9"},
  [x["rapor_no"] for x in r])
c("süzme: bulgular", {x["id"] for x in b} == {1, 3})
c("süzme yoksa her şey", G.suz(TUR, BUL, RAP, None) == (TUR, BUL, RAP))
v = G.gorunum(t, [x for x in b if x["durum"] == "acik"], r, an=AN)
c("süzülmüş veriyle şema çizilir", v["acik_sayisi"] == 2 and v["agentlar"]["e"]["durum"] == "hata", v["acik_sayisi"])

HS = [{"gun": "2026-11-10", "anahtar": "a", "seviye": "WARNING", "kaynak": "sync", "sablon": "Modbus <ip> zaman aşımı",
       "adet": 5, "ilk": "2026-11-10T08:00:00+03:00", "son": "2026-11-10T20:00:00+03:00", "ornek": "eski"},
      {"gun": "2026-11-11", "anahtar": "a", "seviye": "WARNING", "kaynak": "sync", "sablon": "Modbus <ip> zaman aşımı",
       "adet": 3, "ilk": "2026-11-11T01:00:00+03:00", "son": "2026-11-11T09:00:00+03:00", "ornek": "yeni"},
      {"gun": "2026-11-12", "anahtar": "b", "seviye": "ERROR", "kaynak": "mz", "sablon": "API hatası",
       "adet": 1, "ilk": "2026-11-12T07:00:00+03:00", "son": "2026-11-12T07:00:00+03:00", "ornek": "x"}]
HO = G.hata_ozeti(HS)
c("hata özeti: şablon başına tek satır, en yeni üstte", [x["mesaj"] for x in HO] == ["API hatası", "Modbus <ip> zaman aşımı"])
c("hata özeti: adetler toplanır, gün sayısı, ilk / son, son örnek",
  (HO[1]["adet"], HO[1]["gun"], HO[1]["ilk"], HO[1]["son"], HO[1]["ornek"]) == (8, 2, "10.11 08:00", "11.11 09:00", "yeni"),
  HO[1])
c("hata özeti: düzey ve kaynak Türkçe", (HO[0]["seviye"], HO[0]["kaynak"]) == ("Hata", "Mekanik Zeka"))

# Canlı Uyarılar (F1, Synapse içi)
CR = [{"rapor_no": "R1", "lokasyon_id": "maslak", "agent": "enerji", "onem": "yuksek", "durum": "acik",
       "baslik": "TRDP-1 <okunamıyor>", "olusturma": "2026-11-12T09:00"},
      {"rapor_no": "R4", "lokasyon_id": "maslak", "agent": "mekanik_zeka", "onem": "orta", "durum": "acik",
       "baslik": "Ahu-7 donmuş", "olusturma": "2026-11-12T08:00"},
      {"rapor_no": "R5", "lokasyon_id": "maslak", "agent": "enerji", "onem": "yuksek", "durum": "dogrulaniyor",
       "baslik": "Diyagram", "olusturma": "2026-11-11T08:00"},
      {"rapor_no": "R2", "lokasyon_id": "merkez", "agent": "synapse", "onem": "yuksek", "durum": "acik", "bulgu_id": 2,
       "baslik": "Ataşehir çevrimdışı"},
      {"rapor_no": "R3", "lokasyon_id": "merkez", "agent": "synapse", "onem": "orta", "durum": "acik", "bulgu_id": 3,
       "baslik": "Disk dolu"},
      {"rapor_no": "R9", "lokasyon_id": "maslak", "agent": "enerji", "onem": "yuksek", "durum": "kapandi", "baslik": "x"}]
CU = G.canli_uyarilar(CR, BUL, ["maslak", "atasehir"])
c("canlı uyarı: lokasyonlara ve merkeze dağılır, kapananlar yok", set(CU) == {"maslak", "atasehir", "merkez"}
  and len(CU["maslak"]) == 3, CU)
c("canlı uyarı: yüksek + açık kırmızı, önce o", CU["maslak"][0][0] == "r" and "R1" in CU["maslak"][0][1])
c("canlı uyarı: doğrulanıyor sarı ve durumu yazılı", any(s == "y" and "R5" in m and "doğrulanıyor" in m
                                                         for s, m in CU["maslak"]), CU["maslak"])
c("canlı uyarı: Synapse iş emri anahtardaki lokasyona", CU["atasehir"][0][0] == "r" and "R2" in CU["atasehir"][0][1])
c("canlı uyarı: sunucu iş emri merkezde, sarı", CU["merkez"] == [("y", CU["merkez"][0][1])] and "Disk dolu" in CU["merkez"][0][1])
c("canlı uyarı: başlık kaçırılır", "&lt;okunamıyor&gt;" in CU["maslak"][0][1] and "<okunamıyor>" not in CU["maslak"][0][1])
c("canlı uyarı: iş emri yoksa boş", G.canli_uyarilar([], [], ["maslak"]) == {})

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
