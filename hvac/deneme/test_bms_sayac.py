# -*- coding: utf-8 -*-
"""BMS sayaçları (26.11.2026): panelde Nokta Türü = sayaç → sayaclar.json (kaynak=bms) → 23:59 okuma
(birim kontrolü) → günlük fark → ortak sütunlar (su / gaz) ve elektrik toplamları. Ağ bağlantısı YOK."""
import json
import os
import shutil
import sys
import tempfile

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import logging  # noqa: E402
logging.disable(logging.CRITICAL)
import pandas as pd  # noqa: E402
import donanim as D  # noqa: E402
import sayaclar  # noqa: E402

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", str(ek)[:400])


def kurulum():
    d = tempfile.mkdtemp(prefix="bms_sayac_")
    os.makedirs(os.path.join(d, "ayar"))
    for f in ("sayaclar.json", "bacnet_noktalari.json", "bacnet_okuma_sablonu.xlsx", "bacnet_esleme.json",
              "lokasyon_profili.json"):
        shutil.copy(os.path.join(BURASI, "ornek_ayar", "maslak", f), os.path.join(d, "ayar", f))
    return d


def nokta(ad, inst, tur=None, nt=None, carpan=None, durum="okunan değer"):
    return {"Gateway IP": "10.20.30.2", "Network (DNET)": 2, "MAC (DADR)": "0x011C", "Device Instance ID": 2098211,
            "Object Type": 0, "Object Instance": inst, "Point Name": ad, "Durum": durum,
            "Nokta Türü": nt, "Sayaç Türü": tur, "Çarpan": carpan}


d = kurulum()
m = D.mevcut(d)
an_once = json.dumps(m["analizorler"], sort_keys=True, default=str)

# ── 1) Nokta türü: standart addan tahmin ──
es = D._esleme(d)
c("nokta türü tahmini: durum / set / ölçüm / diğer",
  [D.nokta_turu_tahmin(n, es) for n in ("CH-1 DURUM BILGISI", "CH-1 IC SET", "DIS HAVA", "MAS-1 KAZAN SICAKLIK",
                                         "BILINMEYEN NOKTA")] == ["durum", "set", "ölçüm", "ölçüm", "diğer"])
c("mevcut BMS satırlarında Nokta Türü dolu (sayaç yok)",
  all(s.get("Nokta Türü") in D.NOKTA_TURLERI for s in m["bms"]) and not any(s["Nokta Türü"] == "sayaç" for s in m["bms"]))
c("değişiklik yokken fark yok (yeni sütunlar eski listeyi bozmaz)", not D.fark_var(D.fark(m, D.normalize(m))))

# ── 2) Doğrulama ──
bms = list(m["bms"])
h, _ = D.dogrula(D.normalize({"bms": bms + [nokta("SU ANA", 120, nt="sayaç")]}), d)
c("sayaç: Sayaç Türü zorunlu", any("Sayaç Türü seçilmeli" in x for x in h), h)
h, _ = D.dogrula(D.normalize({"bms": bms + [nokta("SU ANA", 120, "su_ana", "sayaç", "-1")]}), d)
c("sayaç: çarpan > 0", any("Çarpan" in x for x in h), h)
h, _ = D.dogrula(D.normalize({"bms": bms + [nokta("TRDP-1", 120, "trafo", "sayaç")]}), d)
c("sayaç adı analizör adıyla çakışırsa hata", any("aynı adda bir analizör" in x for x in h), h)
h, u = D.dogrula(D.normalize({"bms": bms + [nokta("CH-9 KWH", 121, "chiller", "sayaç")]}), d)
c("BMS'ten elektrik sayacı: çift sayım uyarısı", not h and any("çift sayım" in x for x in u), (h, u))
h, u = D.dogrula(D.normalize({"bms": [dict(s) for s in bms] + [nokta("DIS HAVA X", 122, nt="durum")]}), d)
c("seçilen tür adla uyuşmazsa uyarı (hata değil)", not h and any("DIS HAVA X" in x for x in u), (h, u))
_b = [dict(s) for s in bms]
_b[0] = dict(_b[0], **{"Nokta Türü": "sayaç", "Sayaç Türü": "su_ana"})
h, u = D.dogrula(D.normalize({"bms": _b}), d)
c("standart nokta adı sayaç yapılırsa uyarı", any("standart bir nokta adı" in x for x in u), u)
h, _ = D.dogrula(D.normalize({"bms": bms + [nokta("SU ANA", 120, "su_ana", "sayaç", "0,001")]}), d)
c("geçerli su sayacı (Türkçe ondalık çarpan) hatasız", not h, h)
c("Türkçe ondalık okunur", D.normalize({"bms": [nokta("X", 1, carpan="1.000,5")]})["bms"][0]["Çarpan"] == 1000.5)

# ── 3) Kayıt: sayaclar.json'a kaynak=bms, analizörler korunur ──
yeni_bms = bms + [nokta("SU ANA", 120, "su_ana", "sayaç"), nokta("SU MUTFAK", 121, "su_alt", "sayaç", 0.001),
                  nokta("GAZ KAZAN", 122, "gaz_kazan", "sayaç"), nokta("CH-9 KWH", 123, "chiller", "sayaç"),
                  nokta("SU YENI", 124, "su_ana", "sayaç", durum="okunacak")]
r = D.kaydet({"bms": yeni_bms}, d, yeniden_baslat=False)
sj = json.load(open(os.path.join(d, "ayar", "sayaclar.json"), encoding="utf-8"))
bms_k = {s["ad"]: s for s in sj["sayaclar"] if s.get("kaynak") == "bms"}
c("sayaclar.json yazıldı", any("sayaclar.json" in p for p in r["yazilan"]), r["yazilan"])
c("okunan 4 BMS sayacı kaynak=bms (okunacak olan girmez)", sorted(bms_k) == ["CH-9 KWH", "GAZ KAZAN", "SU ANA", "SU MUTFAK"],
  sorted(bms_k))
c("su sayacı: m³, kendi sütunu, çarpan", bms_k["SU ANA"]["birim"] == "m³" and bms_k["SU ANA"]["sutun"] == "S_SU_ANA_m3"
  and bms_k["SU MUTFAK"]["carpan"] == 0.001, bms_k.get("SU ANA"))
c("elektrik BMS sayacı: kWh sütunu", bms_k["CH-9 KWH"]["birim"] == "kWh" and bms_k["CH-9 KWH"]["sutun"] == "S_CH_9_KWH_kWh",
  bms_k.get("CH-9 KWH"))
c("Modbus analizör listesi bozulmadı (32)", len([s for s in sj["sayaclar"] if s.get("kaynak") != "bms"]) == 32)
sayaclar._ONBELLEK.clear()
c("data_collector analizör listesine BMS sayacı girmez", all(a["name"] not in bms_k for a in sayaclar.analizorler(d)))
c("türden ad: su_ana / chiller", sayaclar.adlar("su_ana", d) == ["SU ANA"] and "CH-9 KWH" in sayaclar.adlar("chiller", d))
import openpyxl  # noqa: E402
ws = openpyxl.load_workbook(os.path.join(d, "ayar", "bacnet_okuma_sablonu.xlsx")).worksheets[0]
satir = list(ws.iter_rows(values_only=True))
c("okuma şablonunda sayaç noktaları adresiyle (7 sütun)", list(satir[0]) == D.BMS_ADRES
  and {"SU ANA", "GAZ KAZAN"} <= {x[6] for x in satir[1:]} and "SU YENI" not in {x[6] for x in satir[1:]})
m2 = D.mevcut(d)
c("mevcut(): analizörler aynı (BMS sayacı analizör tablosunda görünmez)",
  json.dumps(m2["analizorler"], sort_keys=True, default=str) == an_once)
su = [s for s in m2["bms"] if s["Point Name"] == "SU MUTFAK"][0]
c("mevcut(): BMS satırı sayaç bilgisiyle geri gelir", su["Nokta Türü"] == "sayaç" and su["Sayaç Türü"] == "su_alt"
  and su["Çarpan"] == 0.001, su)
c("mevcut(): okunacak sayaç bekleyen listede türüyle", [s for s in m2["bms"] if s["Point Name"] == "SU YENI"][0]["Sayaç Türü"]
  == "su_ana")
c("kayıt sonrası fark yok", not D.fark_var(D.fark(m2, D.normalize(m2))))
k = D.sistem_karsiligi(d)
c("sistem karşılığı: su_ana → kendi sütunu + Su_Tuketimi_m3", "Su_Tuketimi_m3" in k.get("SU ANA", "")
  and "S_SU_ANA_m3" in k.get("SU ANA", ""), k.get("SU ANA"))
_, u = D.dogrula(D.normalize(m2), d)
c("sayaç noktası 'hesap karşılığı yok' uyarısına girmez", not any("SU ANA" in x for x in u if "karşılığı yok" in x), u)

# Analizör tablosu kaydı BMS sayaçlarını silmez
an = [dict(s) for s in m2["analizorler"]]
an[0] = dict(an[0], NOT="test notu")
D.kaydet({"analizorler": an}, d, yeniden_baslat=False)
sj2 = json.load(open(os.path.join(d, "ayar", "sayaclar.json"), encoding="utf-8"))
c("analizör kaydı BMS sayaçlarını korur", sorted(s["ad"] for s in sj2["sayaclar"] if s.get("kaynak") == "bms")
  == sorted(bms_k), [s["ad"] for s in sj2["sayaclar"] if s.get("kaynak") == "bms"])

# Tür değişince birim değişir → yeni sütun (eski sütunun geçmişi karışmaz); aynı birimde sütun korunur
m3 = D.mevcut(d)
for s in m3["bms"]:
    if s["Point Name"] == "SU MUTFAK":
        s["Sayaç Türü"] = "isi"
    if s["Point Name"] == "SU ANA":
        s["Çarpan"] = 2.0
D.kaydet({"bms": m3["bms"]}, d, yeniden_baslat=False)
sj3 = {s["ad"]: s for s in json.load(open(os.path.join(d, "ayar", "sayaclar.json"), encoding="utf-8"))["sayaclar"]}
c("birim değişince yeni sütun", sj3["SU MUTFAK"]["sutun"] == "S_SU_MUTFAK_kWh" and sj3["SU MUTFAK"]["birim"] == "kWh",
  sj3["SU MUTFAK"])
c("aynı birimde sütun korunur", sj3["SU ANA"]["sutun"] == "S_SU_ANA_m3" and sj3["SU ANA"]["carpan"] == 2.0)

# Excel gidiş-dönüş; eski biçim Excel (yeni sütunlar yok) sayaç bilgisini kaybetmez
m4 = D.mevcut(d)
g = D.excel_oku(D.excel_yaz(m4, "Maslak", d))
c("Excel gidiş-dönüş: fark yok", not D.fark_var(D.fark(m4, {k: g[k] for k in D.SUTUNLAR})),
  D.fark(m4, {k: g[k] for k in D.SUTUNLAR}).get("bms"))
eski = {"bms": [{a: s.get(a) for a in D.BMS_ADRES + ["Durum"]} for s in m4["bms"]]}
notlar = D.tamamla(eski, m4)
e_su = [s for s in eski["bms"] if s["Point Name"] == "SU ANA"][0]
c("eski biçim Excel: sayaç türü programdaki kayıttan tamamlanır",
  e_su.get("Nokta Türü") == "sayaç" and e_su.get("Sayaç Türü") == "su_ana" and any("BMS" in n for n in notlar),
  (e_su, notlar))
c("tür uyarısı: yeni BMS sayacı endeks notuyla",
  any("ENDEKS" in x and "SU X" in x for x in D.tur_uyarilari(m4, {"bms": m4["bms"] + [nokta("SU X", 130, "su_ana",
                                                                                              "sayaç")]})))

# ── 4) Okuma: birim kontrolü (data_collector) ──
import data_collector as dc  # noqa: E402
sablon = pd.DataFrame([nokta("SU ANA", 120), nokta("SU MUTFAK", 121), nokta("GAZ KAZAN", 122),
                       nokta("CH-9 KWH", 123), nokta("ISI", 124)])
BIRIMLER = {120: 80, 121: 82, 122: 135, 123: 146}       # m³, litre, m³/h (anlık), MWh


def okuyucu(ip, dnet, mac, ot, oi, prop):
    if prop == dc.PROP_UNITS:
        return float(BIRIMLER[oi]) if oi in BIRIMLER else "[Zaman Asimi]"
    return {120: 1500.0, 121: 25000.0, 122: 40.0, 123: 12.5, 124: 300.0}[oi]


liste = [{"ad": "SU ANA", "nokta": "SU ANA", "tur": "su_ana", "birim": "m³", "carpan": 1.0},
         {"ad": "SU MUTFAK", "nokta": "SU MUTFAK", "tur": "su_alt", "birim": "m³", "carpan": 1.0},
         {"ad": "GAZ KAZAN", "nokta": "GAZ KAZAN", "tur": "gaz_kazan", "birim": "m³", "carpan": 1.0},
         {"ad": "CH-9 KWH", "nokta": "CH-9 KWH", "tur": "chiller", "birim": "kWh", "carpan": 1.0},
         {"ad": "ISI", "nokta": "ISI", "tur": "isi", "birim": "kWh", "carpan": 2.0},
         {"ad": "YOK", "nokta": "YOK", "tur": "su_alt", "birim": "m³"}]
o = {a: (v, durum) for a, _ip, v, durum in dc.bms_sayaclari_oku(liste, sablon, okuyucu)}
c("m³ endeksi aynen", o["SU ANA"][0] == 1500.0 and "hata" not in o["SU ANA"][1].lower(), o["SU ANA"])
c("litre → m³ kendiliğinden", o["SU MUTFAK"][0] == 25.0 and "litre" in o["SU MUTFAK"][1], o["SU MUTFAK"])
c("anlık debi (m³/h) reddedilir — değer yazılmaz, durum 'hata'",
  o["GAZ KAZAN"][0] is None and "hata" in o["GAZ KAZAN"][1].lower() and "anlık" in o["GAZ KAZAN"][1], o["GAZ KAZAN"])
c("MWh → kWh kendiliğinden", o["CH-9 KWH"][0] == 12500.0, o["CH-9 KWH"])
c("birim okunamazsa yalnız çarpan", o["ISI"][0] == 600.0 and "okunamadı" in o["ISI"][1], o["ISI"])
c("şablonda olmayan nokta: hata", o["YOK"][0] is None and "hata" in o["YOK"][1].lower(), o["YOK"])
c("yanlış boyut (kWh türüne m³ birimi) reddedilir", dc.bms_birim_cevir(80, "kWh")[2] is not None
  and dc.bms_birim_cevir(19, "m³")[2] is not None)

# ── 5) Günlük satır: fark, ortak sütunlar, toplamlar (data_bridge) ──
import data_bridge as DB  # noqa: E402
sayaclar._ONBELLEK.clear()
_eski = (DB.BASE_DIR, DB.CHILLER_ANALYZERS, DB.ALL_ANALYZERS, DB.MCC_ONLY_ANALYZERS, DB.BMS_SAYAC_ADLARI, DB.MODBUS_CSV)
try:
    DB.BASE_DIR = d
    DB.CHILLER_ANALYZERS = set(sayaclar.adlar("chiller", d))
    DB.ALL_ANALYZERS = set(sayaclar.adlar(("chiller", "alt_sayac"), d))
    DB.MCC_ONLY_ANALYZERS = DB.ALL_ANALYZERS - DB.CHILLER_ANALYZERS
    DB.BMS_SAYAC_ADLARI = {s["ad"] for s in sayaclar.bms_sayaclar(d)}
    c("BMS chiller sayacı soğutma grubunda", "CH-9 KWH" in DB.CHILLER_ANALYZERS)
    csvp = os.path.join(d, "analizor.csv")
    with open(csvp, "w", encoding="utf-8", newline="") as f:
        f.write("Okuma_Zamani,Cihaz_Adi,IP,Enerji_kWh,Durum\n")
        f.write("2026-11-25 23:59:00,SU ANA,10.20.30.2,1500.75,1500.75 m³\n")
        f.write("2026-11-25 23:59:00,TRDP-1,1.1.1.1,123456.9,ok\n")
    DB.MODBUS_CSV = csvp
    ok = DB.read_modbus_csv()
    c("okuma dosyası: BMS endeksi ondalıklı, analizör tam sayı", ok == {"SU ANA": 1500.75, "TRDP-1": 123456}, ok)
    from datetime import date, timedelta  # noqa: E402
    dun = (date.today() - timedelta(days=1)).isoformat()
    gunluk = DB.calc_daily_kwh({"SU ANA": 1500.75, "GAZ KAZAN": 880.0, "CH-9 KWH": 5000, "SU MUTFAK": 10.0},
                               {"date": dun, "readings": {"SU ANA": 1180.25, "GAZ KAZAN": 800.0, "CH-9 KWH": 3000,
                                                          "SU MUTFAK": 9.5}})
    c("günlük fark (m³)", gunluk["SU ANA"] == 320.5 and gunluk["GAZ KAZAN"] == 80.0, gunluk)
    c("ortak sütunlar: su ve kazan gazı (kojen gazı sayacı yok → yazılmaz)",
      DB.toplam_sutunlari(gunluk, d) == {"Su_Tuketimi_m3": 320.5, "Kazan_Dogalgaz_m3": 80.0}, DB.toplam_sutunlari(gunluk, d))
    c("sayaçlardan biri okunamazsa toplam boş", DB.toplam_sutunlari({"GAZ KAZAN": 80.0}, d)["Su_Tuketimi_m3"] == "")
    row = DB.build_daily_row(dun, {}, gunluk)
    c("günlük satır: Su_Tuketimi_m3 + kendi sütunu", row.get("Su_Tuketimi_m3") == 320.5 and row.get("S_SU_ANA_m3") == 320.5,
      {k: row.get(k) for k in ("Su_Tuketimi_m3", "S_SU_ANA_m3", "Kazan_Dogalgaz_m3")})
    c("günlük satır: BMS chiller soğutma toplamında", row.get("Chiller_Tuketim_kWh") == 2000.0, row.get("Chiller_Tuketim_kWh"))
    c("alt su sayacı su toplamına girmez", row.get("Su_Tuketimi_m3") == 320.5 and row.get("S_SU_MUTFAK_kWh") == 0.5)
finally:
    (DB.BASE_DIR, DB.CHILLER_ANALYZERS, DB.ALL_ANALYZERS, DB.MCC_ONLY_ANALYZERS, DB.BMS_SAYAC_ADLARI,
     DB.MODBUS_CSV) = _eski
    sayaclar._ONBELLEK.clear()

# ── 6) Veri alarmı: BMS sayacı okunamazsa alarm ──
import veri_alarm as VA  # noqa: E402
_eb = VA.BASE_DIR
try:
    VA.BASE_DIR = d
    al = VA.alarm_uret(["SU ANA"], {"SU ANA": "[BMS Hatasi: Zaman Asimi]"}, {}, "2026-11-25")
    c("BMS sayacı bağlantı alarmı (BMS sayacı grubu)", al and al[0]["grup"] == "bms_sayac" and "SU ANA" in al[0]["cihazlar"], al)
finally:
    VA.BASE_DIR = _eb

shutil.rmtree(d, ignore_errors=True)
print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
