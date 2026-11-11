# -*- coding: utf-8 -*-
"""mekanik_zeka_agent.py testi — sahte klasör, sahte saat, sahte ağ. Gerçek veriye ve ağa dokunmaz."""
import csv
import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
import enerji_agent as C  # noqa: E402
import mekanik_zeka_agent as M  # noqa: E402

gecti = kaldi = 0


def c(ad, kosul, ek=""):
    global gecti, kaldi
    if kosul:
        gecti += 1
        print("PASS " + ad)
    else:
        kaldi += 1
        print("FAIL %s   %s" % (ad, ek))


SIMDI = datetime(2026, 11, 11, 12, 0)


def satir(lok, status="OK", severity="OPTIMAL", rule="", sat="OK", action="Optimal"):
    return {"Location": lok, "Status": status, "Severity": severity, "Rule": rule, "SAT Status": sat, "Action": action}


class Kur:
    def __init__(self, analiz_dk=5, oat=11.4, satirlar=None, oz="GECTI", oto_yazim="2026-11-11T08:00:20",
                 donmus=False, grafik_dk=5, kural=(True, 8, 23)):
        self.tmp = tempfile.TemporaryDirectory()
        self.d = self.tmp.name
        os.makedirs(os.path.join(self.d, "configs"))
        os.makedirs(os.path.join(self.d, "ahu_okuma_gecmis"))
        satirlar = satirlar if satirlar is not None else [satir("AHU-%d" % i) for i in range(20)]
        self.json("hvac_ahu_analiz_sonuclari.json", {
            "timestamp": (SIMDI - timedelta(minutes=analiz_dk)).isoformat(), "ahu_sayisi": len(satirlar),
            "oat": oat, "sonuc": {"recs_table": {"rows": satirlar}}})
        self.json(os.path.join("configs", "uretim_tuketim_gecmis.json"), [
            {"timestamp": (SIMDI - timedelta(minutes=grafik_dk)).strftime("%Y-%m-%d %H:%M:%S"),
             "uretilen_kw": 1330, "talep_kw": 1811}])
        self.json(os.path.join("configs", "oz_test_sonuc.json"),
                  {"durum": oz, "gecen": 197 if oz == "GECTI" else 190, "toplam": 197,
                   "kalan_dosyalar": [] if oz == "GECTI" else ["test_kural_onceligi.py"]})
        self.json(os.path.join("configs", "oto_set_durum.json"), {"donem": "gunduz", "zaman": oto_yazim})
        for i in range(4):
            z = (SIMDI - timedelta(minutes=10 * (4 - i))).strftime("%Y%m%d_%H%M")
            with open(os.path.join(self.d, "ahu_okuma_gecmis", "ahu_bacnet_%s.csv" % z), "w", newline="", encoding="utf-8") as f:
                w = csv.writer(f)
                w.writerow(["Timestamp", "AHU_Adi", "Lokasyon", "Nokta_Tipi", "Deger", "Durum"])
                for a in range(10):
                    for n in ("SAT", "RAT", "VANA"):
                        w.writerow([z, "AHU-%d" % a, "MAS-1", n, 20.0 + a + (0 if donmus else i * 0.1), "OK"])
        self.kural = kural
        self.api = {"/api/health": 200, "/api/last_auto_analysis": 200, "/api/instruction-guide": 200,
                    "/api/uretim_tuketim_gecmis": 200}
        self.internet = 200
        self.istekler = []
        self.bekleme = []
        self.o = M.ortam(dizin=self.d, simdi=SIMDI, http=self.http, bekle=self.bekleme.append,
                         bulut={"url": "http://db", "key": "k", "lokasyon_id": "maslak"})

    def json(self, ad, veri):
        with open(os.path.join(self.d, ad), "w", encoding="utf-8") as f:
            json.dump(veri, f)

    def http(self, url, yontem="GET", basliklar=None, govde=None, zaman_asimi=15):
        self.istekler.append((yontem, url, govde))
        for uc, kod in self.api.items():
            if url.endswith(uc):
                return kod, "x"
        if "open-meteo" in url:
            return (self.internet, "{}") if self.internet == 200 else (None, "getaddrinfo failed")
        if "/ayarlar?" in url:
            if self.kural is None:
                return 503, "hata"
            a, g, ge = self.kural
            return 200, json.dumps([{"key": "oto_set_aktif", "value": "true" if a else "false"},
                                    {"key": "oto_gunduz_saat", "value": str(g)}, {"key": "oto_gece_saat", "value": str(ge)}])
        return 201, ""

    def tur(self):
        return C.tur(self.o, M.KONTROLLER)


def anahtarlar(s):
    return sorted(b["anahtar"] for b in s["bulgular"])


def durumlar(s):
    return {k["kod"]: k["durum"] for k in s["kontroller"]}


# 1) Sağlıklı
k = Kur()
s = k.tur()
c("sağlıklı Mekanik Zeka'da bulgu yok", s["bulgular"] == [], anahtarlar(s))
c("on kontrolün hepsi geçti", set(durumlar(s).values()) == {"gecti"} and len(s["kontroller"]) == 10, durumlar(s))
post = [g for y, u, g in k.istekler if y == "POST" and "agent_turlar" in u]
c("tur 'mekanik_zeka' agent'ı olarak yazılır", post and post[0]["agent"] == "mekanik_zeka", post[:1])
c("durum dosyası Enerji agent'ınkinden ayrı", os.path.exists(os.path.join(k.d, "configs", "mekanik_zeka_agent_durum.json"))
  and not os.path.exists(os.path.join(k.d, "configs", "enerji_agent_durum.json")))

# 2) Portal / API
k = Kur()
k.api["/api/health"] = None
s = k.tur()
b = [x for x in s["bulgular"] if x["kontrol"] == "portal_api"]
c("8005 yanıt vermiyorsa kritik (bir kez yeniden dener)", b and b[0]["onem"] == "kritik" and 20 in k.bekleme)
k = Kur()
k.api["/api/instruction-guide"] = 500
s = k.tur()
c("tek uç bozuksa uyarı", any(x["anahtar"] == "portal_api:uclar" and x["onem"] == "uyari" for x in s["bulgular"]))
k = Kur()
k.api["/api/last_auto_analysis"] = 404
c("henüz analiz yoksa (404) uç hatası sayılmaz", not any(x["kontrol"] == "portal_api" for x in k.tur()["bulgular"]))

# 3) Otomatik analiz
c("analiz 60 dk gecikti → uyarı", any(x["anahtar"] == "otomatik_analiz:gecikti" and x["onem"] == "uyari"
                                      for x in Kur(analiz_dk=60).tur()["bulgular"]))
c("analiz 4 saat gecikti → kritik", any(x["anahtar"] == "otomatik_analiz:gecikti" and x["onem"] == "kritik"
                                        for x in Kur(analiz_dk=240).tur()["bulgular"]))
c("santralsiz analiz → kritik", any(x["anahtar"] == "otomatik_analiz:bos" for x in Kur(satirlar=[]).tur()["bulgular"]))

# 4) Dış hava
s = Kur(oat=20.0).tur()
c("analiz varsayılan 20 °C ile yapıldıysa yakalanır", "dis_hava:varsayilan" in anahtarlar(s), anahtarlar(s))
c("gerçek dış hava (20,3) yakalanmaz", "dis_hava:varsayilan" not in anahtarlar(Kur(oat=20.3).tur()))

# 5) AHU verisi ve sensör mantığı
sat = [satir("AHU-%d" % i) for i in range(14)] + [satir("AHU-V%d" % i, "ANALIZ_DISI", "CRITICAL", "SKIP_VERI_YOK", "NO DATA") for i in range(6)]
s = Kur(satirlar=sat).tur()
b = [x for x in s["bulgular"] if x["kontrol"] == "ahu_veri"]
c("santrallerin %30'undan veri yoksa yakalanır, santraller listelenir", b and "6 / 20" in b[0]["baslik"] and "AHU-V0" in b[0]["bulunan"])
sat = [satir("AHU-%d" % i) for i in range(19)] + [satir("AHU-V", "ANALIZ_DISI", "CRITICAL", "SKIP_VERI_YOK")]
c("tek santralde veri yoksa bulgu açılmaz", "ahu_veri:veri_yok" not in anahtarlar(Kur(satirlar=sat).tur()))
sat = [satir("AHU-%d" % i) for i in range(18)] + [satir("AHU-S", "ANALIZ_DISI", "WARNING", "SENSOR", "SENSOR_FAULT", "ANALİZ DIŞI — Sensör Arızası"),
                                                 satir("AHU-X", "OK", "OPTIMAL", "", "SENSOR_FAULT")]
s = Kur(satirlar=sat).tur()
b = [x for x in s["bulgular"] if x["kontrol"] == "sensor_mantigi"]
c("sensör arızalı satır OPTİMAL sayılıyorsa kritik (doğru ayrılan sayılmaz)",
  b and b[0]["onem"] == "kritik" and "AHU-X" in b[0]["bulunan"] and "AHU-S" not in b[0]["bulunan"])
c("STOP santralleri (SKIP_STOP, OPTIMAL) normaldir", Kur(satirlar=[satir("A", "ANALIZ_DISI", "OPTIMAL", "SKIP_STOP", "STANDBY")] * 20).tur()["bulgular"] == [])

# 6) Donmuş okuma, grafik, öz test
s = Kur(donmus=True).tur()
c("son 4 okuma birebir aynıysa donmuş AHU kritik", any(x["anahtar"] == "donmus_ahu:son_okumalar" and x["onem"] == "kritik" for x in s["bulgular"]))
c("grafik 60 dk güncellenmediyse uyarı", "talep_uretim:bayat" in anahtarlar(Kur(grafik_dk=60).tur()))
s = Kur(oz="KALDI").tur()
b = [x for x in s["bulgular"] if x["kontrol"] == "oz_test"]
c("öz test kaldıysa kritik, kalan dosya yazılır", b and b[0]["onem"] == "kritik" and "test_kural_onceligi.py" in b[0]["bulunan"])

# 7) Oto-set (yalnız izler)
s = Kur(oto_yazim="2026-11-05T08:00:20").tur()
b = [x for x in s["bulgular"] if x["kontrol"] == "oto_set"]
c("son geçiş (bugün 08:00) uygulanmadıysa kritik", b and b[0]["onem"] == "kritik" and "11.11 08:00" in b[0]["baslik"]
  and "05.11.2026 08:00" in b[0]["bulunan"], b[0]["baslik"] if b else "")
c("oto-set için agent'ın denediği: yalnızca izler", b and "dokunmaz" in b[0]["denenen"])
k = Kur(oto_yazim="2026-11-10T23:00:10")
k.o._simdi = datetime(2026, 11, 11, 8, 20)             # 08:00 geçişinin üzerinden 30 dk geçmedi
c("geçiş saatinden sonra 30 dk pay tanınır", not any(x["kontrol"] == "oto_set" for x in k.tur()["bulgular"]))
c("oto-set kapalıysa (merkez ayarı) kontrol atlanır", durumlar(Kur(oto_yazim="2026-11-01T08:00:00", kural=(False, 8, 23)).tur())["oto_set"] == "atlandi")
c("kural okunamazsa atlanır, sorun sayılmaz", durumlar(Kur(kural=None).tur())["oto_set"] == "atlandi")
s = Kur(oto_yazim="2026-11-10T23:00:30").tur()
c("dünkü 23:00 yazıldı ama bugünkü 08:00 yazılmadıysa yine yakalanır", any(x["kontrol"] == "oto_set" for x in s["bulgular"]))
_kod = open(os.path.join(BURASI, "mekanik_zeka_agent.py"), encoding="utf-8").read()
_govde = _kod.split('"""', 2)[2]
c("agent oto_set / bacnet_writer'ı içe aktarmaz ve yazmaz",
  "import oto_set" not in _govde and "from oto_set" not in _govde and "bacnet_writer" not in _govde)
c("agent süreç başlatmaz / durdurmaz, dosyaya yazmaz", "subprocess" not in _govde and "to_csv" not in _govde
  and "open(" not in _govde.replace("with open(p, encoding", "").replace("with open(os.path.join(klasor, f), newline", ""))

# 8) İnternet: bilgi (iş emri açmaz)
k = Kur()
k.internet = None
s = k.tur()
b = [x for x in s["bulgular"] if x["kontrol"] == "internet"]
c("internet yoksa 'bilgi' bulgusu (iş emri açmaz), sebep yazılır", b and b[0]["onem"] == "bilgi" and "getaddrinfo" in b[0]["bulunan"])

# 9) Watchdog iki agent'ı da izler
_wd = open(os.path.join(BURASI, "portal_watchdog.py"), encoding="utf-8").read()
c("watchdog Enerji ve Mekanik Zeka agent'larını ayrı ayrı başlatır",
  '"enerji_agent.py"' in _wd and '"mekanik_zeka_agent.py"' in _wd and "procs.append(_agent" not in _wd)

print("\n%d/%d PASS" % (gecti, gecti + kaldi))
sys.exit(1 if kaldi else 0)
