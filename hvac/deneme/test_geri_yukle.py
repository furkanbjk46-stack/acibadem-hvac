# -*- coding: utf-8 -*-
"""PC geri yükleme (F3): K1'in merkeze gönderdiği ayarlar + enerji + kartlar boş klasöre birebir döner. Ağ yok."""
import base64
import csv
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
import ayar_kaydi  # noqa: E402
import geri_yukle as GY  # noqa: E402

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", str(ek)[:300])


class Sorgu:
    def __init__(self, satirlar):
        self.s, self.f = satirlar, []

    def select(self, *a):
        return self

    def eq(self, a, b):
        self.f.append((a, b))
        return self

    def order(self, *a, **k):
        return self

    def range(self, a, b):
        self.r = (a, b)
        return self

    def execute(self):
        d = [x for x in self.s if all(x.get(k) == v for k, v in self.f)]
        return type("C", (), {"data": d[self.r[0]:self.r[1] + 1]})()


class Merkez:
    def __init__(self):
        self.t = {"lokasyon_ayarlari": [], "energy_data": [], "bakim_kartlari": []}

    def table(self, ad):
        return Sorgu(self.t[ad])


# Eski PC: Maslak şablon ayarları + bağlantı dosyası + xlsx
eski = tempfile.mkdtemp(prefix="eski_pc_")
yeni = tempfile.mkdtemp(prefix="yeni_pc_")
sablon = os.path.join(BURASI, "ornek_ayar", "maslak")
shutil.copytree(sablon, os.path.join(eski, "ayar"))
with open(os.path.join(eski, "ayar", "supabase_config.json"), "w") as f:
    json.dump({"supabase_key": "GIZLI"}, f)
XLSX = bytes(range(256)) * 10
with open(os.path.join(eski, "ayar", "bacnet_okuma_sablonu.xlsx"), "wb") as f:
    f.write(XLSX)
anlik = ayar_kaydi.tara(eski)["anlik"]
M = Merkez()
M.t["lokasyon_ayarlari"] = [{"lokasyon_id": "maslak", "dosya": a["dosya"], "icerik": a["icerik"], "boyut": a["boyut"],
                             "guncelleme": "2026-11-12T10:00"} for a in anlik]
M.t["lokasyon_ayarlari"].append({"lokasyon_id": "atasehir", "dosya": "sayaclar.json", "icerik": {"x": 1}})
M.t["energy_data"] = [{"id": i, "lokasyon_id": "maslak", "Tarih": "2026-10-%02d" % (31 - i), "TRDP1_kWh": 1000.5 + i,
                       "Kar_Eritme_Aktif": None, "created_at": "x"} for i in range(30)]
M.t["energy_data"].append({"id": 99, "lokasyon_id": "atasehir", "Tarih": "2026-10-01", "TRDP1_kWh": 1})
M.t["bakim_kartlari"] = [{"lokasyon_id": "maslak", "cihaz": "MAS-1 AHU-6", "kart": {"durum": "arizali"},
                          "updated_at": "2026-11-01T10:00:00+00:00"}]

c("bağlantı dosyası merkeze hiç gitmedi", all(a["dosya"] != "supabase_config.json" for a in anlik))

adim = GY.plan(M, "maslak", yeni)
c("gösterimde hiçbir şey yazılmaz", not os.path.exists(os.path.join(yeni, "ayar")))
yaz = [a for a in adim if a["islem"] == "yaz"]
c("boş PC: bütün ayarlar + enerji + kartlar yazılacak", {a["tur"] for a in yaz} == {"ayar", "enerji", "kart"}
  and len([a for a in yaz if a["tur"] == "ayar"]) == len(anlik), [(a["tur"], a["hedef"]) for a in adim])
GY.uygula(adim, yeni)

ayni = []
for ad in sorted(os.listdir(os.path.join(eski, "ayar"))):
    if ad in GY.GIZLI:
        continue
    a, b = os.path.join(eski, "ayar", ad), os.path.join(yeni, "ayar", ad)
    if ad.endswith(".json"):
        ayni.append(json.load(open(a, encoding="utf-8-sig")) == json.load(open(b, encoding="utf-8")))
    else:
        ayni.append(open(a, "rb").read() == open(b, "rb").read())
c("ayarlar birebir döner (JSON içerik, xlsx bayt bayt)", ayni and all(ayni), ayni)
c("bağlantı dosyası geri yüklenmez (elle konur)", not os.path.exists(os.path.join(yeni, "ayar", "supabase_config.json")))
c("başka lokasyonun ayarı karışmaz",
  json.load(open(os.path.join(yeni, "ayar", "sayaclar.json"), encoding="utf-8")) != {"x": 1})

ep = GY.yollar.yol("energy_data.csv", yeni)
rows = list(csv.DictReader(open(ep, encoding="utf-8")))
c("enerji: yalnız bu lokasyon, tarih sırasıyla, iç sütunlar yok",
  len(rows) == 30 and rows[0]["Tarih"] == "2026-10-02" and rows[-1]["Tarih"] == "2026-10-31"
  and list(rows[0])[0] == "Tarih" and "id" not in rows[0] and "lokasyon_id" not in rows[0] and "created_at" not in rows[0],
  (len(rows), list(rows[0])))
c("enerji: boş değer boş hücre, sayı aynı", rows[0]["Kar_Eritme_Aktif"] == "" and float(rows[-1]["TRDP1_kWh"]) == 1000.5)
kp = GY.yollar.yol("configs/maintenance_cards.json", yeni)
k = json.load(open(kp, encoding="utf-8"))["cards"]
c("kartlar: gövde + merkezdeki zaman (eşitleme yeniden göndermez)",
  k == {"MAS-1 AHU-6": {"durum": "arizali", "_updated_at": "2026-11-01T10:00:00+00:00"}}, k)

# İkinci çalıştırma: var olan hiçbir şeye dokunmaz
adim2 = GY.plan(M, "maslak", yeni)
c("var olan dosyalar korunur", all(a["islem"] == "atla" for a in adim2), [(a["tur"], a["islem"]) for a in adim2])
# Sahada değişmiş ayar + --uzerine-yaz: eskisi yedeklenir
with open(os.path.join(yeni, "ayar", "hvac_settings.json"), "w", encoding="utf-8") as f:
    f.write('{"degisti": true}')
adim3 = [a for a in GY.plan(M, "maslak", yeni, uzerine_yaz=True) if a["hedef"].endswith("hvac_settings.json")]
GY.uygula(adim3, yeni)
c("--uzerine-yaz: eskisi yedeklenir, merkezdeki yazılır",
  os.path.exists(adim3[0].get("yedek", "")) and "degisti" in open(adim3[0]["yedek"], encoding="utf-8").read()
  and "degisti" not in open(os.path.join(yeni, "ayar", "hvac_settings.json"), encoding="utf-8").read())
c("yerelde daha az gün varsa bile --uzerine-yaz olmadan enerji korunur",
  [a["islem"] for a in GY.plan(M, "maslak", yeni) if a["tur"] == "enerji"] == ["atla"])

shutil.rmtree(eski, ignore_errors=True)
shutil.rmtree(yeni, ignore_errors=True)
print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
