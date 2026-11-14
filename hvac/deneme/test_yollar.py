# -*- coding: utf-8 -*-
"""Klasör düzeni (Faz 1 / N1): yollar.yol çözümü ve tasi() — Maslak'ın bugünkü düzeni taklit edilir."""
import json
import os
import sys
import tempfile
import time

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import yollar as Y  # noqa: E402

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", ek)


def yaz(base, goreli, icerik="x", yas=0):
    p = os.path.join(base, *goreli.split("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(icerik)
    t = time.time() - yas
    os.utime(p, (t, t))
    return p


def var(base, goreli):
    return os.path.exists(os.path.join(base, *goreli.split("/")))


# Maslak'ın bugünkü düzeni (06.11.2026 paketi)
d = tempfile.mkdtemp(prefix="yollar_")
yaz(d, "energy_data.csv", "Tarih,A\n2026-11-05,1\n")
yaz(d, "supabase_config.json", '{"lokasyon_id": "maslak"}')
yaz(d, "configs/hvac_settings.json", '{"a": 1}')
yaz(d, "configs/oto_set_durum.json", '{"donem": "gunduz"}')
yaz(d, "configs/maintenance_cards.json", "{}")
yaz(d, "configs/ahu_nokta_konfig.json", "[eski 14.07]", yas=1000)
yaz(d, "ahu_nokta_konfig.json", "[yeni 31.10]", yas=10)
yaz(d, "ahu_okuma_gecmis/ahu_bacnet_20261106_1630.csv", "a")
yaz(d, "static/outputs/hvac_analysis_1.csv", "a")
yaz(d, "static/index.html", "<html>")
yaz(d, "cloud_sync.log", "log")
yaz(d, "cloud_sync.log.1", "eski log")
yaz(d, "configs/energy_data_yedek_bacnet_donma_20261024.csv", "y")
yaz(d, "_restart.flag", "v13")
yaz(d, "main_portal.py", "# kod")

# 1) Taşımadan önce: eski yerler kullanılır
c("taşımadan önce energy_data.csv kökte bulunur", Y.yol("energy_data.csv", d) == os.path.join(d, "energy_data.csv"))
c("taşımadan önce iki nokta kopyasından en son düzenlenen (kök) geçerli",
  Y.yol("configs/ahu_nokta_konfig.json", d) == os.path.join(d, "ahu_nokta_konfig.json"))
c("kayıtta olmayan yol kökte kalır (kod)", Y.yol("main_portal.py", d) == os.path.join(d, "main_portal.py"))

# 2) Taşıma
r = Y.tasi(d)
c("ana veri veri/ altına taşındı", var(d, "veri/energy_data.csv") and not var(d, "energy_data.csv"))
c("bağlantı dosyası ayar/ altına taşındı", var(d, "ayar/supabase_config.json") and not var(d, "supabase_config.json"))
c("ayar → ayar/, durum → durum/, bakım kartları → veri/",
  var(d, "ayar/hvac_settings.json") and var(d, "durum/oto_set_durum.json") and var(d, "veri/maintenance_cards.json"))
c("ayrışmış nokta kopyalarından en son düzenlenen ayar/bacnet_noktalari.json oldu",
  open(os.path.join(d, "ayar", "bacnet_noktalari.json"), encoding="utf-8").read() == "[yeni 31.10]")
c("eski kopya silinmedi, durum/tasima_yedek/ altında",
  open(os.path.join(d, "durum", "tasima_yedek", "configs", "ahu_nokta_konfig.json"), encoding="utf-8").read() == "[eski 14.07]")
c("klasörler taşındı (AHU geçmişi, çıktılar)",
  var(d, "veri/ahu_okuma_gecmis/ahu_bacnet_20261106_1630.csv") and var(d, "veri/ciktilar/hvac_analysis_1.csv")
  and not var(d, "ahu_okuma_gecmis"))
c("arayüz dosyaları yerinde (static/index.html kod)", var(d, "static/index.html"))
c("log ve dönen yedeği veri/log/ altında", var(d, "veri/log/cloud_sync.log") and var(d, "veri/log/cloud_sync.log.1"))
c("tarihli eski yedekler veri/eski_yedekler/ altında", var(d, "veri/eski_yedekler/energy_data_yedek_bacnet_donma_20261024.csv"))
c("yeniden başlatma işareti ve kod yerinde", var(d, "_restart.flag") and var(d, "main_portal.py"))
c("taşıma raporu durum/tasima.json'da", var(d, "durum/tasima.json") and len(r["tasinan"]) >= 10 and not r["hata"], r["hata"])

# 3) Taşımadan sonra: yeni yerler
c("taşımadan sonra eski adla sorulan yol yeni yeri verir",
  Y.yol("energy_data.csv", d) == os.path.join(d, "veri", "energy_data.csv")
  and Y.yol("configs/ahu_nokta_konfig.json", d) == os.path.join(d, "ayar", "bacnet_noktalari.json"))

# 4) Tekrar çalıştırmak zararsız
once = sorted(os.listdir(os.path.join(d, "veri")))
r2 = Y.tasi(d)
c("ikinci taşıma hiçbir şey yapmaz", not r2["tasinan"] and not r2["yedeklenen"] and sorted(os.listdir(os.path.join(d, "veri"))) == once)

# 5) Eski kod taşımadan sonra eski yere yazarsa: yeni yer korunur, eski kopya yedeğe
yaz(d, "energy_data.csv", "eski kodun yazdığı")
r3 = Y.tasi(d)
c("yeni yer varken eski yerde çıkan dosya yeni yeri ezmez, yedeğe gider",
  open(os.path.join(d, "veri", "energy_data.csv"), encoding="utf-8").read().startswith("Tarih")
  and "energy_data.csv" in r3["yedeklenen"])

# 6) Sıfırdan kurulum: hiçbir şey yokken yeni yerlere yazılır
d2 = tempfile.mkdtemp(prefix="yollar_yeni_")
p = Y.yol("configs/oto_set_durum.json", d2)
c("yeni kurulumda durum dosyası durum/ altına ve klasörü hazır",
  p == os.path.join(d2, "durum", "oto_set_durum.json") and os.path.isdir(os.path.dirname(p)))
with open(p, "w", encoding="utf-8") as f:
    json.dump({}, f)
c("yeni yere ilk yazım hata vermez", os.path.exists(p))

# 7) Katmanlar ve yama koruması
c("katmanlar doğru", Y.katman("energy_data.csv") == "veri" and Y.katman("configs/hvac_settings.json") == "ayar"
  and Y.katman("configs/oto_set_durum.json") == "durum" and Y.katman("main_portal.py") == "kod")
c("yama kod yazar", Y.yama_yazabilir_mi("main_portal.py") and Y.yama_yazabilir_mi("static/vendor/chart.umd.min.js"))
c("yama lokasyon ayarı / verisi / durumu yazamaz (eski ve yeni adlarıyla)",
  not any(Y.yama_yazabilir_mi(x) for x in ("configs/hvac_settings.json", "ayar/hvac_settings.json",
                                           "energy_data.csv", "veri/energy_data.csv", "durum/x.json",
                                           "supabase_config.json", "configs/yeni_bir_ayar.json")))

# 7b) Kod klasörleri asla taşınmaz (12.11.2026: tuketim_tahmin/ kod paketiydi, veri sanılıp taşınmıştı)
import subprocess  # noqa: E402
_izlenen = subprocess.run(["git", "ls-files"], cwd=BURASI, capture_output=True, text=True).stdout.split()
_kayit_eski = [e for _, es in Y.KAYIT for e in es if e.endswith("/")]
_cakisan = [e for e in _kayit_eski if any(p.startswith(e) and p.endswith(".py") for p in _izlenen)]
c("kayıttaki taşınacak klasörlerin hiçbiri repoda kod içermiyor", _izlenen and not _cakisan, _cakisan)
d3 = tempfile.mkdtemp(prefix="yollar_kod_")
yaz(d3, "ahu_okuma_gecmis/yanlislikla.py", "# kod")
r4 = Y.tasi(d3)
c("içinde .py olan klasör taşınmaz, hata olarak raporlanır",
  var(d3, "ahu_okuma_gecmis/yanlislikla.py") and any("kod içeren" in h for h in r4["hata"]), r4)

# 8) Kodda eski yerler elle yazılmıyor (yeni bir dosya yolu bu modül dışında kurulmasın)
import re  # noqa: E402
eskiler = sorted({e.rstrip("/") for _, es in Y.KAYIT for e in es}, key=len, reverse=True)
desen = re.compile(r'os\.path\.join\([^)]*["\'](' + "|".join(re.escape(e.split("/")[0]) for e in eskiler) + r')["\']')
ihlal = []
for ad in sorted(os.listdir(BURASI)) + ["monthly_report/" + x for x in os.listdir(os.path.join(BURASI, "monthly_report"))]:
    if ad.endswith(".py") and not os.path.basename(ad).startswith("test_") and ad not in (
            "yollar.py", "simulasyon_sunucu.py", "ornek_veri_uret.py", "guncelleme_yayinla.py", "_test_ping.py"):
        for i, satir in enumerate(open(os.path.join(BURASI, ad), encoding="utf-8"), 1):
            m = desen.search(satir)
            if m and "yollar." not in satir and m.group(1) not in ("static",):
                ihlal.append("%s:%d" % (ad, i))
c("kodda kayıtlı dosyalar için elle os.path.join kalmadı (yollar.yol kullanılır)", not ihlal, ihlal[:10])

# 8b) Geniş tarama: alt paketler dahil, kayıttaki eski adı tırnak içinde geçirip dosya yolu kuran her satır
# (12.11.2026: monthly_report/hvac_history.py iç içe dirname ile kuruyordu, ilk tarama görmedi)
_adlar = sorted({e.rstrip("/").split("/")[-1] for _, es in Y.KAYIT for e in es}, key=len, reverse=True)
_desen2 = re.compile(r'["\'](?:[^"\']*/)?(' + "|".join(re.escape(a) for a in _adlar) + r')["\']')
_izinli = ("yollar.", "get_data_path(", ".yol(", "_yol(", "SABLON_ADI =", "NOKTA_DOSYA =", "_ANAHTAR =",
           'os.path.join(yedek_dizin, "bacnet_donma_temizlik.json")')
ihlal2 = []
for _kok, _dz, _ds in os.walk(BURASI):
    _dz[:] = [x for x in _dz if x not in ("__pycache__", "ayar", "durum", "veri", "static")]
    for ad in _ds:
        if not ad.endswith(".py") or ad.startswith("test_") or ad in (
                "yollar.py", "simulasyon_sunucu.py", "ornek_veri_uret.py", "guncelleme_yayinla.py", "_test_ping.py"):
            continue
        for i, satir in enumerate(open(os.path.join(_kok, ad), encoding="utf-8", errors="replace"), 1):
            s = satir.strip()
            if (not s.startswith("#") and _desen2.search(s) and not any(z in s for z in _izinli)
                    and any(k in s for k in ("os.path.join", "open(", "Path(", "_FILE =", "_DIR =", "_PATH ="))):
                ihlal2.append("%s:%d" % (os.path.relpath(os.path.join(_kok, ad), BURASI), i))
c("alt paketler dahil hiçbir modül kayıtlı dosyanın yolunu kendisi kurmuyor", not ihlal2, ihlal2[:10])

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
