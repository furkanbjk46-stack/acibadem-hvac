# -*- coding: utf-8 -*-
"""Lokasyon donanımı paneli çekirdeği (donanim.py): Excel ↔ tablo, doğrulama, önizleme, yedekli kayıt, şifre."""
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
        print("FAIL", ad, " ", str(ek)[:300])


def kurulum():
    d = tempfile.mkdtemp(prefix="donanim_")
    os.makedirs(os.path.join(d, "ayar"))
    for f in ("sayaclar.json", "bacnet_noktalari.json", "bacnet_okuma_sablonu.xlsx", "bacnet_esleme.json",
              "lokasyon_profili.json"):
        shutil.copy(os.path.join(BURASI, "ornek_ayar", "maslak", f), os.path.join(d, "ayar", f))
    return d


d = kurulum()
m = D.mevcut(d)
c("mevcut liste okunur (Maslak: 32 analizör, 51 BMS, 386 AHU)",
  [len(m[k]) for k in ("analizorler", "bms", "ahu")] == [32, 51, 386], {k: len(v) for k, v in m.items()})
h, _ = D.dogrula(m, d)
c("mevcut liste hatasız doğrulanır", not h, h[:3])

# ── Excel gidiş-dönüş ──
x = D.excel_yaz(m, "Maslak", d)
g = D.excel_oku(x)
t = {k: g[k] for k in D.SUTUNLAR}
c("Excel'e yazılıp okunan liste birebir aynı", not D.fark_var(D.fark(m, t)), D.fark(m, t))
r = D.kaydet(t, d, yeniden_baslat=False)
c("değişiklik yoksa hiçbir dosya yazılmaz", r["yazilan"] == [] and r["yedek"] is None, r)
c("değişiklik yoksa yeniden başlatma işareti yok", not os.path.exists(os.path.join(d, "_restart.flag")))
bos = D.excel_oku(D.excel_yaz(None))
c("boş şablon okunur: her tabloda bir örnek satır", all(len(bos[k]) == 1 for k in D.SUTUNLAR))
c("boş şablonun örnek satırları geçerli", not D.dogrula({k: bos[k] for k in D.SUTUNLAR})[0])

# ── STEP-UP/3 ekleme (panel yolu) ──
yeni = {"analizorler": [dict(s) for s in m["analizorler"]] + [
    {"AD": "STEP-UP/3", "IP ADRESI": "172.17.91.124", "BİNA": "MAS-1", "MARKA": "janitza", "TÜR": "TRAFO",
     "KRİTİK": "evet", "NOT": None},
    {"AD": "SU", "IP ADRESI": None, "BİNA": "MAS-1", "MARKA": None, "TÜR": None, "KRİTİK": None,
     "NOT": "sayaç gelmedi"},
    {"AD": None, "IP ADRESI": None, "BİNA": None, "MARKA": None, "TÜR": None, "KRİTİK": None, "NOT": None}]}
yeni = D.normalize(yeni)
c("panelde boş bırakılan satır atılır", len(yeni["analizorler"]) == 34)
c("serbest yazım seçeneğe oturur (janitza→Janitza, TRAFO→trafo, evet→Evet)",
  yeni["analizorler"][32]["MARKA"] == "Janitza" and yeni["analizorler"][32]["TÜR"] == "trafo"
  and yeni["analizorler"][32]["KRİTİK"] == "Evet", yeni["analizorler"][32])
k = D.normalize({"analizorler": [dict(s) for s in m["analizorler"]] + [
    {"AD": "STEP-UP/3", "IP ADRESI": "172.17.91.124", "MARKA": "Janitza", "TÜR": "kontrol", "KRİTİK": "Hayır"}]})
dk = tempfile.mkdtemp(prefix="donanim_k_")
shutil.copytree(os.path.join(d, "ayar"), os.path.join(dk, "ayar"))
D.kaydet(k, dk, yeniden_baslat=False)
c("kontrol sayacı hiçbir toplama girmez", all("STEP-UP/3" not in sayaclar.adlar(t, dk)
                                               for t in ("trafo", "sebeke", "uretim", "chiller", "alt_sayac")))
c("kontrol sayacı yön bağımsız okunur ve günlük değeri kaydedilir",
  any(a["name"] == "STEP-UP/3" and a.get("uretim") for a in sayaclar.analizorler(dk))
  and "S_STEP_UP_3_kWh" in sayaclar.sutunlar(base_dir=dk))
c("kontrol türü için 'toplama girmez' notu", "toplama girmez" in D.tur_uyarilari(m, k)[0])
shutil.rmtree(dk, ignore_errors=True)
tu = D.tur_uyarilari(m, yeni)
c("yeni trafo için Şebeke toplamı uyarısı", len(tu) == 1 and "STEP-UP/3" in tu[0] and "step-up" in tu[0], tu)
f = D.fark(m, yeni)
c("önizleme: 2 eklenen, silinen/değişen yok",
  len(f["analizorler"]["eklenen"]) == 2 and not f["analizorler"]["silinen"] and not f["analizorler"]["degisen"], f)
r = D.kaydet(yeni, d, kullanici="test")
sj = json.load(open(os.path.join(d, "ayar", "sayaclar.json"), encoding="utf-8"))
c("STEP-UP/3 sayaclar.json'a girdi (marka küçük harf, yeni sütun, kritik)",
  {"ad": "STEP-UP/3", "ip": "172.17.91.124", "marka": "janitza", "tur": "trafo", "sutun": "S_STEP_UP_3_kWh",
   "kritik": True, "bina": "MAS-1"} in sj["sayaclar"], sj["sayaclar"][-1])
c("yeni sayacın günlük değeri sayac_gunluk satırına gider",
  any(x["sayac"] == "STEP-UP/3" and x["deger"] == 12.5 for x in
      __import__("sayac_gunluk").satirlar([{"Tarih": "2026-11-14", "S_STEP_UP_3_kWh": 12.5}], "maslak", d)
      .get("2026-11-14", [])))
c("sütun adı çakışmaz", D.sutun_uret("STEP-UP/3", {"S_STEP_UP_3_kWh"}) == "S_STEP_UP_3_2_kWh"
  and D.sutun_uret("Şebeke ölçü") == "S_SEBEKE_OLCU_kWh")
c("IP'si olmayan SU okunan listeye girmez", all(s["ad"] != "SU" for s in sj["sayaclar"]))
bek = json.load(open(os.path.join(d, "ayar", "donanim_bekleyen.json"), encoding="utf-8"))
c("SU bekleyen listede saklanır", [s["AD"] for s in bek["analizorler"]] == ["SU"], bek)
c("açıklama ve mevcut sütunlar korunur", sj.get("_aciklama") and
  next(s for s in sj["sayaclar"] if s["ad"] == "TRDP-1")["sutun"] == "TRDP1_kWh")
c("program yeni listeyi okur (sayaclar.analizorler)",
  any(a["name"] == "STEP-UP/3" and a["brand"] == "janitza" for a in sayaclar.analizorler(d)))
c("yalnız değişen tablo dosyaları yazılır", sorted(r["yazilan"]) ==
  sorted([os.path.join("ayar", "sayaclar.json"), os.path.join("ayar", "donanim_bekleyen.json")]), r["yazilan"])
c("önce yedek alınır (eski sayaclar.json)", os.path.exists(os.path.join(r["yedek"], "sayaclar.json")) and
  "STEP-UP/3" not in open(os.path.join(r["yedek"], "sayaclar.json"), encoding="utf-8").read())
c("kayıt sonrası yeniden başlatma işareti", os.path.exists(os.path.join(d, "_restart.flag")))
c("günlüğe yazılır", D.son_kayitlar(d)[0]["ozet"]["analizorler"]["eklenen"] == 2, D.son_kayitlar(d))
m2 = D.mevcut(d)
c("bekleyen satır panelde yine görünür", any(s["AD"] == "SU" for s in m2["analizorler"]))

# ── Doğrulama ──
def hata(tablo, satir):
    return D.dogrula(D.normalize({tablo: [satir]}))[0]


c("IP'li analizörde marka/tür zorunlu", len(hata("analizorler", {"AD": "X", "IP ADRESI": "10.0.0.1"})) == 2)
c("geçersiz IP yakalanır", hata("analizorler", {"AD": "X", "IP ADRESI": "10.0.0.300", "MARKA": "Siemens",
                                                 "TÜR": "trafo"}))
iki = D.normalize({"analizorler": [
    {"AD": "MCC-1", "IP ADRESI": "10.0.0.1", "MARKA": "Siemens", "TÜR": "alt_sayac"},
    {"AD": "mcc-1", "IP ADRESI": "10.0.0.1", "MARKA": "Siemens", "TÜR": "alt_sayac"}]})
c("aynı ad ve aynı IP yakalanır", len(D.dogrula(iki)[0]) == 2, D.dogrula(iki)[0])
c("BMS: MAC biçimi ve tamsayı alanlar", len(hata("bms", {"Gateway IP": "10.0.0.2", "Network (DNET)": "iki",
                                                          "MAC (DADR)": "11C", "Device Instance ID": 5,
                                                          "Object Type": 0, "Object Instance": 1,
                                                          "Point Name": "X", "Durum": "okunan değer"})) == 2)
c("BMS: 'okunacak' satırda adres zorunlu değil",
  not hata("bms", {"Point Name": "SEBEKE KESIK BILGISI", "Durum": "okunacak"}))
c("BMS: sayı olarak girilen MAC onaltılıya çevrilir",
  D.normalize({"bms": [{"MAC (DADR)": 284, "Point Name": "X"}]})["bms"][0]["MAC (DADR)"] == "0x011C")
c("AHU: listede olmayan nokta tipi yakalanır",
  hata("ahu", {"Bina": "A", "Santral": "Ahu-1", "Nokta Tipi": "Nem", "Gateway IP": "10.0.0.8",
               "Network (DNET)": 1, "MAC (DADR)": "0x01", "Object Type": 0, "Object Instance": 1}))
try:
    D.kaydet({"analizorler": [{"AD": "X", "IP ADRESI": "1.2.3.4"}]}, d, yeniden_baslat=False)
    c("hatalı veri kaydedilmez", False)
except ValueError:
    c("hatalı veri kaydedilmez", "STEP-UP/3" in open(os.path.join(d, "ayar", "sayaclar.json"), encoding="utf-8").read())

# ── BMS: okunan / yazılabilir / okunacak ──
bms = [dict(s) for s in m["bms"]]
bms[0] = dict(bms[0], **{"MAC (DADR)": "0x0999"})
bms.append({"Gateway IP": "192.168.0.2", "Network (DNET)": 2, "MAC (DADR)": "0x011C", "Device Instance ID": 1,
            "Object Type": 2, "Object Instance": 5, "Point Name": "GUNDUZ KOLLEKTOR SET", "Durum": "Yazıla bılır değer"})
bms.append({"Point Name": "SEBEKE KESIK BILGISI", "Durum": "okunacak"})
yb = D.normalize({"bms": bms})
f = D.fark(m, yb)
c("adres değişikliği 'değişen' olarak görünür (silinip eklenmez)",
  len(f["bms"]["degisen"]) == 1 and len(f["bms"]["eklenen"]) == 2 and not f["bms"]["silinen"], f["bms"])
D.kaydet(yb, d, yeniden_baslat=False)
import openpyxl  # noqa: E402
ws = openpyxl.load_workbook(os.path.join(d, "ayar", "bacnet_okuma_sablonu.xlsx")).worksheets[0]
satir = list(ws.iter_rows(values_only=True))
c("okuma şablonu: yalnız okunan noktalar, 7 sütun, aynı başlık",
  len(satir) == 52 and list(satir[0]) == D.BMS_SUTUN[:-1], (len(satir), satir[0]))
c("okuma şablonunda yeni MAC", satir[1][2] == "0x0999")
bek = json.load(open(os.path.join(d, "ayar", "donanim_bekleyen.json"), encoding="utf-8"))
c("yazılabilir + okunacak bekleyende; analizör bekleyeni korunur",
  [s["Durum"] for s in bek["bms"]] == ["yazılabilir değer", "okunacak"] and bek["analizorler"][0]["AD"] == "SU")

# ── Eski biçimli Excel (MARKA / TÜR yok) ──
eski_bicim = {"analizorler": D.normalize({"analizorler": [
    {"AD": "TRDP-1", "IP ADRESI": "172.17.91.121"}, {"AD": "CH-4", "IP ADRESI": "172.17.91.117"}]})["analizorler"]}
notlar = D.tamamla(eski_bicim, m)
c("eski biçimde marka / tür IP'den tamamlanır",
  eski_bicim["analizorler"][0]["MARKA"] == "Janitza" and eski_bicim["analizorler"][1]["TÜR"] == "chiller", eski_bicim)
c("aynı IP'de farklı ad uyarılır", any("CHILLER-4 → CH-4" in n for n in notlar), notlar)

# ── Şifre ──
c("şifre yokken panel şifre belirletir", not D.sifre_var(d))
try:
    D.sifre_belirle("12345", d)
    c("6 karakterden kısa şifre reddedilir", False)
except ValueError:
    c("6 karakterden kısa şifre reddedilir", True)
D.sifre_belirle("maslak-panel", d)
icerik = open(os.path.join(d, "ayar", "panel_sifresi.json"), encoding="utf-8").read()
c("şifre dosyada açık yazılmaz", "maslak-panel" not in icerik)
c("doğru / yanlış şifre", D.sifre_dogru("maslak-panel", d) and not D.sifre_dogru("maslak", d))
import ayar_kaydi  # noqa: E402
import geri_yukle  # noqa: E402
c("şifre dosyası merkeze gitmez ve geri yüklenmez",
  "panel_sifresi.json" in ayar_kaydi.GIZLI and "panel_sifresi.json" in geri_yukle.GIZLI)

# ── Enerji portalı yeni sayaç sütununu CSV'den silmez (app_portal.ensure_schema) ──
import ast  # noqa: E402
import re  # noqa: E402
import pandas as pd  # noqa: E402
_kaynak = open(os.path.join(BURASI, "app_portal.py"), encoding="utf-8").read()
_fn = next(n for n in ast.parse(_kaynak).body if isinstance(n, ast.FunctionDef) and n.name == "ensure_schema")
c("portal şemasına sayaclar.json sütunları eklenir",
  'SCHEMA = SCHEMA + [s["sutun"] for s in _SAYAC_LISTESI' in _kaynak)
_ns = {"pd": pd, "SCHEMA": ["Tarih", "S_STEP_UP_3_kWh"], "_PANEL_SUTUN": re.compile(r"^S_[A-Z0-9_]+_kWh$")}
exec(compile(ast.Module(body=[_fn], type_ignores=[]), "ensure_schema", "exec"), _ns)
_cik = _ns["ensure_schema"](pd.DataFrame({"Tarih": ["2026-11-14"], "S_STEP_UP_3_kWh": [1.0],
                                          "S_ESKI_SAYAC_kWh": [2.0], "Cop": [3]}))
c("ensure_schema: yeni ve panelden silinmiş sayaç sütunu korunur, ilgisiz sütun atılır",
  list(_cik.columns) == ["Tarih", "S_STEP_UP_3_kWh", "S_ESKI_SAYAC_kWh"], list(_cik.columns))

shutil.rmtree(d, ignore_errors=True)
print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
