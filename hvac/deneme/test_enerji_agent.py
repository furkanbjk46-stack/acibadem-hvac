# -*- coding: utf-8 -*-
"""enerji_agent.py testi — sahte klasör, sahte saat, sahte ağ. Gerçek veriye ve ağa dokunmaz."""
import csv
import json
import os
import sys
import tempfile
from datetime import date, datetime, timedelta

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import enerji_agent as A  # noqa: E402

gecti = kaldi = 0


def c(ad, kosul, ek=""):
    global gecti, kaldi
    if kosul:
        gecti += 1
        print("PASS " + ad)
    else:
        kaldi += 1
        print("FAIL %s   %s" % (ad, ek))


SIMDI = datetime(2026, 11, 10, 9, 0)          # 08:30 sonrası: bütün günlük işler bitmiş olmalı
DUN = date(2026, 11, 9)
SUTUNLAR = ["Tarih", "Sebeke_Tuketim_kWh", "Kojen1_kWh", "Kojen2_kWh", "Kojen_Uretim_kWh",
            "Chiller_Tuketim_kWh", "MCC_Tuketim_kWh", "VRF_Split_Tuketim_kWh",
            "Toplam_Hastane_Tuketim_kWh", "Toplam_Sogutma_Tuketim_kWh", "Diger_Yuk_kWh",
            "Chiller1_kWh", "Dis_Hava_Sicakligi_C", "Hava_Sicaklik_Ort_C", "Hava_Sicaklik_Max_C",
            "Hava_Sicaklik_Min_C", "Hava_Nem_Ort_Yuzde"]


def gun(t, i=0, **ek):
    """Kuralla tutarlı bir gün satırı (toplam = şebeke + kojen)."""
    seb, k1, k2, ch, mcc = 33000 + 37 * i, 14000 + 11 * i, 14060 + 7 * i, 9000 + 13 * i, 12000 + 5 * i
    r = {"Tarih": t.isoformat(), "Sebeke_Tuketim_kWh": seb, "Kojen1_kWh": k1, "Kojen2_kWh": k2,
         "Kojen_Uretim_kWh": k1 + k2, "Chiller_Tuketim_kWh": ch, "MCC_Tuketim_kWh": mcc,
         "VRF_Split_Tuketim_kWh": 0, "Toplam_Hastane_Tuketim_kWh": seb + k1 + k2,
         "Toplam_Sogutma_Tuketim_kWh": ch, "Diger_Yuk_kWh": seb + k1 + k2 - mcc - ch,
         "Chiller1_kWh": 2000 + 3 * i, "Dis_Hava_Sicakligi_C": 12.5 + 0.1 * i,
         "Hava_Sicaklik_Ort_C": 13 + 0.1 * i, "Hava_Sicaklik_Max_C": 17, "Hava_Sicaklik_Min_C": 9,
         "Hava_Nem_Ort_Yuzde": 70}
    r.update(ek)
    return r


def saglikli_gunler(n=40):
    return [gun(DUN - timedelta(days=n - 1 - i), i) for i in range(n)]


class Kur:
    """Sağlıklı bir lokasyon klasörü kurar; testler tek tek bozar."""

    def __init__(self, gunler=None, bulut=True):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        os.makedirs(os.path.join(self.d, "configs"))
        self.gunler = gunler if gunler is not None else saglikli_gunler()
        self.enerji_yaz()
        self.modbus_yaz()
        self.bacnet_yaz("2026-11-10 07:05:12")
        with open(self.yol("sync_son_calisma.txt"), "w") as f:
            f.write("2026-11-10")
        self.istekler = []
        self.bulut_satirlari = None      # None → yereldekiyle aynı
        self.portal_kodu = 200
        self.internet_kodu = 200
        self.yedek_gunleri = None        # None → hava_gunluk isteği başarısız
        self.bulut_kodu = 200
        self.yazma_kodu = 201
        self.bekleme = []
        self.o = A.Ortam(dizin=self.d, simdi=SIMDI, http=self.http, bekle=self.bekleme.append,
                         bulut={"url": "http://db", "key": "k", "lokasyon_id": "maslak"} if bulut else None)

    def yol(self, *p):
        return os.path.join(self.d, *p)

    def enerji_yaz(self):
        with open(self.yol("energy_data.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=SUTUNLAR)
            w.writeheader()
            w.writerows(self.gunler)

    def modbus_yaz(self, zaman="2026-11-09 23:59:03", hatali=()):
        with open(self.yol("analizor_guncel_veriler.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Okuma_Zamani", "Cihaz_Adi", "IP", "Enerji_kWh", "Durum"])
            for ad in ("SEBEKE", "KOJEN-1", "KOJEN-2", "CHILLER-1", "MCC-1", "KULE-1"):
                w.writerow([zaman, ad, "192.168.1.15", "" if ad in hatali else 1000,
                            "[Baglanti Hatasi]" if ad in hatali else "1000 kWh"])

    def bacnet_yaz(self, zaman):
        with open(self.yol("hedefli_enerji_verileri.csv"), "w", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            w.writerow(["Timestamp", "Nokta", "Deger"])
            w.writerow([zaman, "DIS_HAVA", 12.5])

    def http(self, url, yontem="GET", basliklar=None, govde=None, zaman_asimi=15):
        self.istekler.append((yontem, url, govde))
        if "_stcore/health" in url:
            return self.portal_kodu, "ok"
        if "open-meteo" in url:
            return (200, "{}") if self.internet_kodu == 200 else (None, "getaddrinfo failed")
        if "hava_gunluk" in url:
            return (200, json.dumps([{"tarih": t} for t in self.yedek_gunleri]))                 if self.yedek_gunleri is not None else (503, "hata")
        if yontem == "GET" and "energy_data" in url:
            if self.bulut_kodu != 200:
                return self.bulut_kodu, "hata"
            satirlar = self.bulut_satirlari if self.bulut_satirlari is not None else self.gunler
            return 200, json.dumps(satirlar)
        return self.yazma_kodu, ""

    def tur(self):
        return A.tur(self.o)


def anahtarlar(s):
    return sorted(b["anahtar"] for b in s["bulgular"])


def durumlar(s):
    return {k["kod"]: k["durum"] for k in s["kontroller"]}


# ── 1) Sağlıklı lokasyon ─────────────────────────────────────────────────
k = Kur()
s = k.tur()
c("sağlıklı lokasyonda bulgu yok", s["bulgular"] == [], anahtarlar(s))
c("on kontrolün hepsi geçti", set(durumlar(s).values()) == {"gecti"} and len(s["kontroller"]) == 10, durumlar(s))
c("energy_data.csv DEĞİŞMEDİ (agent salt okur)",
  open(k.yol("energy_data.csv"), encoding="utf-8").read().count("\n") == 41)

# ── 2) Diyagram toplamı ──────────────────────────────────────────────────
g = saglikli_gunler()
g[-3]["Toplam_Hastane_Tuketim_kWh"] -= 2336          # dosyada eski/yanlış toplam
k = Kur(g)
k.bulut_satirlari = saglikli_gunler()                 # cloud_sync buluta KURALLA hesaplanmış değeri gönderir
s = k.tur()
b = [x for x in s["bulgular"] if x["kontrol"] == "diyagram_toplami"]
c("kayıtlı toplam kuralla tutmuyorsa yakalanır", len(b) == 1 and b[0]["anahtar"].startswith("diyagram_toplami:kayit:"), anahtarlar(s))
c("yalnız yerel dosya eskiyse önem 'bilgi' (iş emri açılmaz)", bool(b) and b[0]["onem"] == "bilgi")
c("bulguda beklenen / bulunan / denenen / tekrar / olası yer dolu",
  bool(b) and all(b[0][a] for a in ("beklenen", "bulunan", "denenen", "tekrar_adimi", "olasi_yer")))
c("buluta giden değer kuralla hesaplandığı için yerel↔bulut bundan etkilenmez",
  not any(x["kontrol"] == "yerel_bulut" for x in s["bulgular"]), anahtarlar(s))

import enerji_hesap  # noqa: E402
_asil = enerji_hesap.yeniden_hesapla


def _bozuk_kural(df):
    df = _asil(df)
    df.loc[df.index[-1], "Toplam_Hastane_Tuketim_kWh"] -= 2336     # koddaki hata taklidi
    return df


enerji_hesap.yeniden_hesapla = _bozuk_kural
k = Kur()
s = k.tur()
enerji_hesap.yeniden_hesapla = _asil
b = [x for x in s["bulgular"] if x["anahtar"].startswith("diyagram_toplami:kural:")]
c("hesap KODU bozuksa kritik 'toplam tutmuyor' bulgusu", len(b) == 1 and b[0]["onem"] == "kritik", anahtarlar(s))
c("rapordaki fark doğru (−2.336 kWh)", bool(b) and "−2.336" in b[0]["bulunan"], b[0]["bulunan"] if b else "")
c("olası yer enerji_hesap.py", bool(b) and "enerji_hesap.py" in b[0]["olasi_yer"])

# ── 3) Günlük döngü ──────────────────────────────────────────────────────
k = Kur(saglikli_gunler()[:-1])                       # dünün satırı yok
s = k.tur()
c("dünün satırı yazılmamışsa kritik bulgu", "gunluk_dongu:kopru:2026-11-09" in anahtarlar(s), anahtarlar(s))
c("dünün eksikliği 'eksik gün' olarak ikinci kez sayılmaz", "veri_kalitesi:eksik_gun" not in anahtarlar(s))
k = Kur()
k.modbus_yaz("2026-11-08 23:59:03")
k.bacnet_yaz("2026-11-09 07:05:00")
os.remove(k.yol("sync_son_calisma.txt"))
s = k.tur()
c("Modbus 23:59 okuması eskiyse yakalanır", "gunluk_dongu:modbus" in anahtarlar(s))
c("BACnet 07:05 bugün okunmadıysa yakalanır", "gunluk_dongu:bacnet" in anahtarlar(s))
c("08:00 eşitlemesi çalışmadıysa yakalanır", "gunluk_dongu:bulut" in anahtarlar(s))
k = Kur(saglikli_gunler()[:-1])
k.bacnet_yaz("2026-11-09 07:05:00")
os.remove(k.yol("sync_son_calisma.txt"))
k.o._simdi = datetime(2026, 11, 10, 0, 10)            # saatleri henüz gelmedi
s = k.tur()
c("saati gelmeyen iş için bulgu açılmaz (00:10)", not any(a.startswith("gunluk_dongu") for a in anahtarlar(s)), anahtarlar(s))

# ── 4) Sayaç erişimi ─────────────────────────────────────────────────────
k = Kur()
k.modbus_yaz(hatali=("SEBEKE", "KULE-1"))
s = k.tur()
b = {x["anahtar"]: x for x in s["bulgular"]}
c("okunamayan sayaçlar ayrı ayrı bulgu", {"sayac_erisimi:SEBEKE", "sayac_erisimi:KULE-1"} <= set(b))
c("şebeke kritik, kule uyarı", b["sayac_erisimi:SEBEKE"]["onem"] == "kritik" and b["sayac_erisimi:KULE-1"]["onem"] == "uyari")

# ── 5) Donmuş veri ───────────────────────────────────────────────────────
g = saglikli_gunler()
for r in g[-5:]:
    r["Chiller1_kWh"] = 2100
k = Kur(g)
s = k.tur()
b = [x for x in s["bulgular"] if x["anahtar"] == "donmus_veri:Chiller1_kWh"]
c("5 gün aynı değer veren sayaç yakalanır", len(b) == 1 and "5 gündür" in b[0]["baslik"], anahtarlar(s))
g = saglikli_gunler()
for r in g[-4:]:
    r.update(Kojen1_kWh=0, Kojen2_kWh=0, Kojen_Uretim_kWh=0,
             Toplam_Hastane_Tuketim_kWh=r["Sebeke_Tuketim_kWh"],
             Diger_Yuk_kWh=r["Sebeke_Tuketim_kWh"] - r["MCC_Tuketim_kWh"] - r["Chiller_Tuketim_kWh"])
k = Kur(g)
s = k.tur()
c("kojen üretimi günlerce 0 ise yakalanır", "donmus_veri:kojen_sifir" in anahtarlar(s), anahtarlar(s))
c("sıfır değerler 'donmuş sayaç' sayılmaz", "donmus_veri:Kojen1_kWh" not in anahtarlar(s))

# ── 6) Veri kalitesi ─────────────────────────────────────────────────────
g = saglikli_gunler()
del g[-10]                                            # arada eksik gün
g.append(dict(g[-5]))                                 # mükerrer tarih
g[-3]["Chiller_Tuketim_kWh"] = -50                    # eksi değer
k = Kur(g)
s = k.tur()
a = anahtarlar(s)
c("eksik gün yakalanır", "veri_kalitesi:eksik_gun" in a, a)
c("mükerrer tarih yakalanır", any(x.startswith("veri_kalitesi:mukerrer:") for x in a), a)
c("eksi tüketim yakalanır", any(x.startswith("veri_kalitesi:eksi:Chiller_Tuketim_kWh") for x in a), a)
g = saglikli_gunler()
g[-1]["Sebeke_Tuketim_kWh"] = -1200                   # şebekeye verilen gün (yeni kural)
g[-1]["Toplam_Hastane_Tuketim_kWh"] = -1200 + g[-1]["Kojen_Uretim_kWh"]
g[-1]["Diger_Yuk_kWh"] = max(0, g[-1]["Toplam_Hastane_Tuketim_kWh"] - g[-1]["MCC_Tuketim_kWh"] - g[-1]["Chiller_Tuketim_kWh"])
k = Kur(g)
s = k.tur()
c("eksi ŞEBEKE kurala uygundur, bulgu açılmaz", not any("eksi:Sebeke" in x for x in anahtarlar(s)), anahtarlar(s))
g = saglikli_gunler()
g[-2].update(Sebeke_Tuketim_kWh=160000, Toplam_Hastane_Tuketim_kWh=160000 + g[-2]["Kojen_Uretim_kWh"],
             Diger_Yuk_kWh=160000 + g[-2]["Kojen_Uretim_kWh"] - g[-2]["MCC_Tuketim_kWh"] - g[-2]["Chiller_Tuketim_kWh"])
k = Kur(g)
s = k.tur()
c("olağan dışı toplam (medyanın ~3 katı) yakalanır", any(x.startswith("veri_kalitesi:aykiri:") for x in anahtarlar(s)), anahtarlar(s))

# ── 7) Yerel ↔ bulut ─────────────────────────────────────────────────────
k = Kur()
k.bulut_satirlari = [dict(r) for r in k.gunler]
k.bulut_satirlari[-2]["Toplam_Hastane_Tuketim_kWh"] += 477
del k.bulut_satirlari[-4]
s = k.tur()
a = anahtarlar(s)
c("bulutta farklı değer yakalanır", "yerel_bulut:fark:2026-11-08" in a, a)
c("bulutta olmayan gün yakalanır", "yerel_bulut:yok:2026-11-06" in a, a)
k = Kur()
k.o._simdi = datetime(2026, 11, 10, 7, 0)             # 08:00 eşitlemesinden önce
k.bulut_satirlari = [dict(r) for r in k.gunler[:-1]]  # dün henüz bulutta yok
s = k.tur()
c("08:30'dan önce dünün bulutta olmaması sorun sayılmaz", not any(x.startswith("yerel_bulut") for x in anahtarlar(s)), anahtarlar(s))
k = Kur()
k.bulut_kodu = 503
s = k.tur()
c("veritabanına ulaşılamazsa bir kez yeniden dener, sonra bildirir",
  "yerel_bulut:erisim" in anahtarlar(s) and 20 in k.bekleme)
k = Kur(bulut=False)
s = k.tur()
c("bulut ayarı olmayan PC'de yerel↔bulut atlanır", durumlar(s)["yerel_bulut"] == "atlandi")
c("bulut ayarı olmayan PC hiçbir şey GÖNDERMEZ",
  not any(y != "GET" for y, _, _ in k.istekler) and "bulut ayarı yok" in s["gonderim"], k.istekler)

# ── 8) Hava durumu ve portal sağlığı ─────────────────────────────────────
g = saglikli_gunler()
g[-1].update(Hava_Sicaklik_Ort_C="", Hava_Nem_Ort_Yuzde="")
k = Kur(g)
s = k.tur()
b = [x for x in s["bulgular"] if x["kontrol"] == "hava_durumu"]
c("dünün hava verisi boşsa yakalanır ve servis yoklanır",
  len(b) == 1 and "yanıt veriyor" in b[0]["denenen"] and any("open-meteo" in u for _, u, _ in k.istekler))
g = saglikli_gunler()
for r in g[-2:]:
    r.update(Hava_Sicaklik_Ort_C="")
g[-12]["Hava_Sicaklik_Ort_C"] = ""                    # 7 günlük pencerenin dışında
k = Kur(g)
k.internet_kodu = None
k.yedek_gunleri = ["2026-11-08", "2026-11-09"]
s = k.tur()
b = [x for x in s["bulgular"] if x["kontrol"] == "hava_durumu"]
c("son 7 gündeki bütün boş günler tek bulguda; anahtar en eski boş gün",
  len(b) == 1 and b[0]["anahtar"] == "hava_durumu:2026-11-08" and b[0]["kanit"]["bos_gunler"] == ["2026-11-08", "2026-11-09"],
  b[0]["anahtar"] if b else "")
c("internete ulaşılamadığı sebebiyle yazılır", bool(b) and "ulaşılamıyor (getaddrinfo failed)" in b[0]["bulunan"], b[0]["bulunan"] if b else "")
c("Synapse yedek yolunda kaç günün hazır olduğu yazılır", bool(b) and "2/2 gün hazır" in b[0]["bulunan"]
  and "hava_doldur" in b[0]["olasi_yer"])
k.yedek_gunleri = None
s = k.tur()
b = [x for x in s["bulgular"] if x["kontrol"] == "hava_durumu"]
c("iki kaynak da yoksa erişim kontrolü önerilir", bool(b) and "internet erişimi" in b[0]["olasi_yer"]
  and b[0]["gorulme_sayisi"] == 2)
g = saglikli_gunler()
g[-1]["Hava_Sicaklik_Ort_C"] = ""
k = Kur(g)
k.o._simdi = datetime(2026, 11, 10, 0, 10)             # köprü henüz yazmadı: dün pencere dışında
s = k.tur()
c("00:30'dan önce dünün boş havası sayılmaz", not any(x["kontrol"] == "hava_durumu" for x in s["bulgular"]))
k = Kur()
k.portal_kodu = None
s = k.tur()
b = [x for x in s["bulgular"] if x["anahtar"] == "portal_sagligi:8501"]
c("portal yanıt vermiyorsa kritik bulgu (yeniden başlatmaz)", len(b) == 1 and b[0]["onem"] == "kritik" and "başlatmadı" in b[0]["denenen"])
k = Kur()
with open(k.yol("cloud_sync.log"), "w", encoding="utf-8") as f:
    f.write("2026-11-10 08:50:01,123 [SYNC] ERROR Enerji senkronizasyon hatası: PGRST204\n"
            "2026-11-09 08:00:01,123 [SYNC] ERROR eski hata\n"
            "2026-11-10 08:55:01,123 [SYNC] INFO tamam\n")
s = k.tur()
b = [x for x in s["bulgular"] if x["anahtar"] == "portal_sagligi:esitleme_hatasi"]
c("eşitleme kaydındaki YENİ hata yakalanır, eskisi sayılmaz", len(b) == 1 and "1 hata" in b[0]["baslik"] and "PGRST204" in b[0]["bulunan"])

# ── 8b) Portallar arası tutarlılık ve kapsam ───────────────────────────
k = Kur()
k.bulut_satirlari = [dict(r) for r in k.gunler] + [dict(k.gunler[-3])]      # 07.11 iki kez yazılmış
a = anahtarlar(k.tur())
c("Synapse'te mükerrer gün yakalanır (detay toplamı şişer)", "portal_tutarliligi:mukerrer:2026-11" in a, a)
c("mükerrer gün aylık toplamı da bozar", "portal_tutarliligi:toplam:2026-11" in a, a)
c("günlük karşılaştırma mükerreri görmez (bu yüzden ayrı kontrol)", not any(x.startswith("yerel_bulut") for x in a), a)

k = Kur()
k.bulut_satirlari = [dict(r) for r in k.gunler]
eski = [r for r in k.bulut_satirlari if r["Tarih"] == "2026-10-15"][0]
eski["Toplam_Hastane_Tuketim_kWh"] += 500                                   # 7 günlük pencerenin dışında
a = anahtarlar(k.tur())
c("7 günden eski farklı gün aylık toplamda yakalanır (geçen ay)", "portal_tutarliligi:toplam:2026-10" in a
  and "portal_tutarliligi:toplam:2026-11" not in a, a)

k = Kur()
k.bulut_kodu = 503
s = k.tur()
c("Synapse okunamazsa tutarlılık atlanır (yerel ↔ bulut zaten bildirir)",
  durumlar(s)["portal_tutarliligi"] == "atlandi", durumlar(s))

k = Kur()
alanlar = SUTUNLAR + ["Kule1_kWh", "Kule2_kWh", "Hava_Gunes_Radyasyon_kWh_m2"]
with open(k.yol("energy_data.csv"), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=alanlar)
    w.writeheader()
    w.writerows([dict(r, Kule1_kWh=150, Kule2_kWh=0, Hava_Gunes_Radyasyon_kWh_m2=3.1) for r in k.gunler])
s = k.tur()
b = [x for x in s["bulgular"] if x["kontrol"] == "kapsam"]
c("veri gelen ama izlenmeyen sayaç kapsam bulgusu (bilgi)", len(b) == 1 and b[0]["onem"] == "bilgi"
  and b[0]["kanit"]["sutunlar"] == ["Kule1_kWh"], b)
c("hep sıfır sayaç ve kWh_m2 hava alanı sayılmaz", b and "Kule2_kWh" not in b[0]["bulunan"]
  and "Radyasyon" not in b[0]["bulunan"])

# ── 9) Bulgu ömrü: açılma → tekrar → kapanma → yeniden açılma ────────────
k = Kur()
k.modbus_yaz(hatali=("KOJEN-1",))
s1 = k.tur()
s2 = k.tur()
b2 = s2["bulgular"][0]
c("ikinci turda aynı bulgu: yeni satır değil, sayaç artar",
  len(s2["bulgular"]) == 1 and b2["gorulme_sayisi"] == 2 and b2["ilk_gorulme"] == s1["bulgular"][0]["ilk_gorulme"])
k.modbus_yaz()
s3 = k.tur()
c("sorun geçince bulgu kapanır", s3["bulgular"] == [] and [x["anahtar"] for x in s3["kapananlar"]] == ["sayac_erisimi:KOJEN-1"])
yama = [(y, u, g) for y, u, g in k.istekler if y == "PATCH"]
c("kapanış veritabanına bildirilir", len(yama) == 1 and yama[0][2]["durum"] == "kapandi" and "sayac_erisimi%3AKOJEN-1" in yama[0][1], yama)
k.modbus_yaz(hatali=("KOJEN-1",))
s4 = k.tur()
c("aynı sorun yeniden çıkarsa açılma sayısı 2 (tekrarlayan sorun)", s4["bulgular"][0]["acilma_sayisi"] == 2 and s4["bulgular"][0]["gorulme_sayisi"] == 1)

k = Kur()
k.modbus_yaz(hatali=("KOJEN-1",))
k.tur()
os.remove(k.yol("analizor_guncel_veriler.csv"))       # kontrol artık ÇALIŞAMIYOR
s = k.tur()
c("kontrol atlandıysa açık bulgu kapanmış SAYILMAZ",
  s["kapananlar"] == [] and s["ozet"]["acik_bulgu"] == 1 and durumlar(s)["sayac_erisimi"] == "atlandi")

# ── 10) Gönderim ─────────────────────────────────────────────────────────
k = Kur()
k.modbus_yaz(hatali=("KOJEN-1",))
s = k.tur()
post = {u.split("/rest/v1/")[1].split("?")[0]: g for y, u, g in k.istekler if y == "POST"}
c("tur ve bulgu doğru tablolara yazılır", set(post) == {"agent_turlar", "agent_bulgular"}, list(post))
c("tur satırı: lokasyon, agent, özet, kontroller",
  post["agent_turlar"]["lokasyon_id"] == "maslak" and post["agent_turlar"]["agent"] == "enerji"
  and post["agent_turlar"]["ozet"]["sorun"] == 1 and len(post["agent_turlar"]["kontroller"]) == 10)
c("bulgu satırı tablo sütunlarıyla uyumlu",
  set(post["agent_bulgular"][0]) == {"lokasyon_id", "agent", "anahtar", "kontrol", "bolum", "onem", "baslik",
                                     "beklenen", "bulunan", "denenen", "tekrar_adimi", "olasi_yer", "kanit",
                                     "durum", "ilk_gorulme", "son_gorulme", "gorulme_sayisi", "acilma_sayisi",
                                     "kapanma"}, sorted(post["agent_bulgular"][0]))
_sql = open(os.path.join(BURASI, "..", "..", "veritabani", "degisiklikler", "002_agent_tablolari.sql"),
            encoding="utf-8").read() if os.path.exists(os.path.join(BURASI, "..", "..", "veritabani")) else None
if _sql is not None:                                   # yalnız geliştirme deposunda
    _tablo = _sql.split("CREATE TABLE IF NOT EXISTS public.agent_bulgular")[1].split(");")[0]
    c("gönderilen her alan 002_agent_tablolari.sql'de var",
      all((" %s " % a) in _tablo.replace("\n", " ") for a in post["agent_bulgular"][0]),
      [a for a in post["agent_bulgular"][0] if (" %s " % a) not in _tablo.replace("\n", " ")])
k = Kur()
k.modbus_yaz(hatali=("KOJEN-1",))
k.tur()
k.modbus_yaz()
k.yazma_kodu = 500                                    # veritabanı yazmayı reddediyor
s = k.tur()
d = json.load(open(k.yol("configs", "enerji_agent_durum.json"), encoding="utf-8"))
c("gönderilemeyen kapanış saklanır", "gönderim hatası" in s["gonderim"] and len(d["bekleyen_kapanis"]) == 1)
k.yazma_kodu = 204
k.tur()
d = json.load(open(k.yol("configs", "enerji_agent_durum.json"), encoding="utf-8"))
c("sonraki turda yeniden gönderilir", d["bekleyen_kapanis"] == [])

# ── 11) Dayanıklılık ve sınırlar ─────────────────────────────────────────
def _patlar(o):
    raise RuntimeError("beklenmeyen")


s = A.tur(Kur().o, kontroller=[("x", "Bozuk kontrol", _patlar), ("sayac_erisimi", "Sayaç", A.k_sayac_erisimi)])
c("bir kontrol çökerse tur sürer, 'hata' olarak görünür", durumlar(s) == {"x": "hata", "sayac_erisimi": "gecti"})
_kod = open(os.path.join(BURASI, "enerji_agent.py"), encoding="utf-8").read()
_govde = _kod.split('"""', 2)[2]
c("agent oto_set / bacnet_writer kullanmaz", "import oto_set" not in _govde and "bacnet_writer" not in _govde)
c("agent süreç başlatmaz / durdurmaz", "subprocess" not in _govde and "os.kill" not in _govde)
c("agent energy_data.csv'ye yazmaz", "to_csv" not in _govde)
c("açılışta ilk turdan önce bekler (portal ayağa kalksın)", A.BASLANGIC_BEKLEME_SN >= 60
  and "time.sleep(BASLANGIC_BEKLEME_SN)" in _kod)
_wd = open(os.path.join(BURASI, "portal_watchdog.py"), encoding="utf-8").read()
c("watchdog agent'ı portallardan AYRI izler (ölürse portallar yeniden başlamaz)",
  "enerji_agent.py" in _wd and "_agent_baslat" in _wd and "procs.append(_agent" not in _wd)

print("\n%d/%d PASS" % (gecti, gecti + kaldi))
sys.exit(1 if kaldi else 0)
