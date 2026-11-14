# -*- coding: utf-8 -*-
"""Aylık rapor: ısıtma / santral hatları ayar dosyasından (yol haritası R1). Maslak (2 hat) çıktısı eskisiyle aynı,
1 ve 3 hatlı lokasyon da çalışır."""
import csv
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
from monthly_report import data_merger as DM  # noqa: E402
from monthly_report import savings_engine as SE  # noqa: E402

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", str(ek)[:400])


d = tempfile.mkdtemp(prefix="rapor_hat_")
MASLAK = [{"ad": "MAS-1", "etiket": "Mas-1", "isitma": "Mas1_Isitma_Temp", "kazan": "Mas1_Kazan_Temp",
           "sogutma": "Mas1_Sogutma_Temp"},
          {"ad": "MAS-2", "etiket": "Mas-2", "isitma": "Mas2_Isitma_Temp", "kazan": "Mas2_Kazan_Temp",
           "sogutma": "Mas2_Sogutma_Temp"}]
UC = [{"ad": "ATA-A", "isitma": "A_Isi", "sogutma": "A_Sog"}, {"ad": "ATA-B", "isitma": "B_Isi", "sogutma": "B_Sog"},
      {"ad": "ATA-C", "isitma": "C_Isi", "sogutma": "C_Sog"}]


def csv_yaz(ad, sutunlar, satirlar):
    p = os.path.join(d, ad)
    with open(p, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["Tarih", "Toplam_Hastane_Tuketim_kWh", "Dis_Hava_Sicakligi_C"] + sutunlar)
        for g, deg in enumerate(satirlar, 1):
            w.writerow(["2026-10-%02d" % g, 50000, 15] + deg)
    return p


def ay(p, hatlar):
    DM._isitma_hatlari = lambda: hatlar
    m = DM.UnifiedDataMerger(energy_csv_path=p)
    return m.merge_monthly_data(2026, 10)


motor = SE.SavingsRecommendationEngine(training_data_path=os.path.join(d, "egitim.json"))
kural = next(r for r in motor.rules if r.rule_id == "MAS_IMBALANCE")


def mesaj(ozet):
    r = kural.condition({"summary": ozet}, {})
    return kural.message_template.format(**r) if r else None


_eski = DM._isitma_hatlari
try:
    # Maslak: iki hat, eski sütunlar
    p = csv_yaz("maslak.csv", ["Mas1_Isitma_Temp", "Mas1_Kazan_Temp", "Mas1_Sogutma_Temp", "Mas2_Isitma_Temp",
                               "Mas2_Kazan_Temp", "Mas2_Sogutma_Temp"],
                [[60, 70, 8, 52, 71, 14], [62, 70, "", 54, 71, 15], [58, 69, 9, 50, 70, 16]])
    r = ay(p, MASLAK)
    g1 = r["daily_data"][0]["energy"]
    c("günlük: eski anahtarlar (mas1_* / mas2_*) aynı sütunlardan",
      (g1["mas1_heating_temp"], g1["mas2_cooling_temp"], g1["mas1_boiler_temp"]) == (60, 14, 70), g1)
    c("günlük: hat başına değerler", g1["hatlar"]["MAS-2"]["heating_temp"] == 52 and g1["hatlar"]["MAS-1"]["etiket"] == "MAS1")
    s = r["summary"]
    c("özet: eski ortalamalar", (s["avg_mas1_heating_temp"], s["avg_mas2_heating_temp"], s["avg_mas1_cooling_temp"],
                                 s["avg_mas2_cooling_temp"]) == (60, 52, 8.5, 15), s)
    c("özet: dönüş sıcaklığı bütün hatların ortalaması",
      abs(s["avg_return_temp"] - (8 + 9 + 14 + 15 + 16 + 60 + 62 + 58 + 52 + 54 + 50) / 11) < 1e-9, s["avg_return_temp"])
    c("özet: hat_ortalamalari hat sırasıyla", [h["ad"] for h in s["hat_ortalamalari"]] == ["MAS-1", "MAS-2"])
    eski_ozet = {k: s[k] for k in ("avg_mas1_cooling_temp", "avg_mas2_cooling_temp", "avg_mas1_heating_temp",
                                   "avg_mas2_heating_temp")}
    c("Maslak: kural mesajı hat listesiyle de eski özetle de aynı",
      mesaj(s) is not None and mesaj(s) == mesaj(eski_ozet) and "🏭 MAS1 Ortalama: 8.5°C\n🏭 MAS2 Ortalama: 15.0°C" in mesaj(s),
      mesaj(s))

    # Üç hatlı lokasyon: ilk iki hat yakın, üçüncüsü uzak → dengesizlik yine bulunur
    p = csv_yaz("uc.csv", ["A_Isi", "A_Sog", "B_Isi", "B_Sog", "C_Isi", "C_Sog"],
                [[60, 10, 61, 11, 70, 12], [60, 10, 61, 11, 70, 12]])
    s = ay(p, UC)["summary"]
    c("3 hat: üç hat ortalaması", [(h["ad"], h["isitma"]) for h in s["hat_ortalamalari"]]
      == [("ATA-A", 60), ("ATA-B", 61), ("ATA-C", 70)], s["hat_ortalamalari"])
    m3 = mesaj(s)
    c("3 hat: en sıcak / en soğuk farkı (ilk ikisi yakın olsa da)", m3 and "Fark: 10.0°C" in m3 and "ATAC Ortalama: 70.0°C" in m3, m3)

    # Tek hat: dengesizlik kuralı çalışmaz, rapor hata vermez
    p = csv_yaz("tek.csv", ["A_Isi", "A_Sog"], [[60, 10], [80, 30]])
    s = ay(p, UC[:1])["summary"]
    c("1 hat: ikinci hat boş, kural sessiz", s["avg_mas2_heating_temp"] is None and s["avg_mas1_heating_temp"] == 70
      and mesaj(s) is None, s)

    # Hat tanımı yok (bacnet_esleme.json yok)
    s = ay(p, [])["summary"]
    c("hat tanımı yok: sıcaklıklar boş, hata yok", s["hat_ortalamalari"] == [] and s["avg_return_temp"] is None
      and mesaj(s) is None)
finally:
    DM._isitma_hatlari = _eski
    shutil.rmtree(d, ignore_errors=True)

c("gerçek ayar: Maslak şablonundaki hatlar okunur",
  [h["ad"] for h in DM._isitma_hatlari()] in (["MAS-1", "MAS-2"], []), DM._isitma_hatlari())
print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
