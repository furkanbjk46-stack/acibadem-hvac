# -*- coding: utf-8 -*-
"""Günlük snapshot referans sırası — H-02 (26.10.2026 denetimi).

Modbus referansı (modbus_daily_ref.json) ancak dünün satırı energy_data.csv'ye
YAZILDIKTAN sonra bugüne ilerlemeli; yazma başarısızsa telafi çalışması aynı
farkla tekrar deneyebilmeli. Geçici klasörde çalışır, gerçek dosyalara dokunmaz.

    python test_gunluk_referans.py
"""
import json
import os
import shutil
import sys
import tempfile
import types
from datetime import date, timedelta

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(errors="replace")
except Exception:
    pass
import logging  # noqa: E402
logging.disable(logging.CRITICAL)

sys.modules["veri_alarm"] = types.SimpleNamespace(kontrol_et=lambda *a, **k: {})  # ağ yok
import data_bridge as DB  # noqa: E402

tmp = tempfile.mkdtemp(prefix="referans_")
DB.ENERGY_CSV = os.path.join(tmp, "energy_data.csv")
DB.REF_FILE = os.path.join(tmp, "modbus_daily_ref.json")
DB.hava_durumu = None
DB.read_bacnet_csv = lambda: {}
BUGUN, DUN, ONCEKI = date.today().isoformat(), (date.today() - timedelta(days=1)).isoformat(), \
    (date.today() - timedelta(days=2)).isoformat()
ilk_sayac = {n: 1000.0 for n in ("MCC", "Chiller-1")}
DB.read_modbus_csv = lambda: {n: v + 500.0 for n, v in ilk_sayac.items()}
_asil_yaz = DB.write_to_energy_csv

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


def ref_tarihi():
    if not os.path.exists(DB.REF_FILE):
        return None
    return json.load(open(DB.REF_FILE, encoding="utf-8")).get("date")


def sifirla(ref_tarih=DUN):
    for f in (DB.ENERGY_CSV, DB.REF_FILE):
        if os.path.exists(f):
            os.remove(f)
    if ref_tarih:
        DB.save_ref(ref_tarih, dict(ilk_sayac))
    DB.write_to_energy_csv = _asil_yaz


# 1) Yazma başarısız → referans dünde kalır, CSV'de satır yok
sifirla()
DB.write_to_energy_csv = lambda row: False
DB.run_daily_snapshot()
c("yazma başarısızsa referans İLERLEMEZ", ref_tarihi() == DUN, ref_tarihi())

# 2) Telafi (tekrar çalıştırma) aynı farkla yazar, sonra referans bugüne geçer
DB.write_to_energy_csv = _asil_yaz
DB.run_daily_snapshot()
c("telafi dünün satırını yazar", DB.date_exists_in_csv(DUN))
c("başarılı yazmadan sonra referans bugüne geçer", ref_tarihi() == BUGUN, ref_tarihi())
import csv  # noqa: E402
satir = next(csv.DictReader(open(DB.ENERGY_CSV, encoding="utf-8")))
_dolu = [k for k, v in satir.items() if k.endswith("_kWh") and v not in ("", None)]
c("telafide Modbus farkı boş DEĞİL (gün kaybolmadı)", bool(_dolu), satir)

# 3) Satır oluşturulurken hata → referans korunur
sifirla()
_asil_build = DB.build_daily_row
DB.build_daily_row = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("test"))
try:
    DB.run_daily_snapshot()
except RuntimeError:
    pass
DB.build_daily_row = _asil_build
c("satır oluşturma hatasında referans İLERLEMEZ", ref_tarihi() == DUN, ref_tarihi())

# 4) İlk çalıştırma: referans yok → bugünün referansı kaydedilir
sifirla(ref_tarih=None)
DB.run_daily_snapshot()
c("ilk çalıştırmada referans kaydedilir", ref_tarihi() == BUGUN, ref_tarihi())

# 5) Tarih zaten CSV'de → referans yine bugüne geçer (ertesi gün doğru fark)
sifirla()
DB.write_to_energy_csv({"Tarih": DUN})
DB.run_daily_snapshot()
c("satır zaten varsa referans bugüne geçer", ref_tarihi() == BUGUN, ref_tarihi())

# 6) write_to_energy_csv dönüşü
sifirla()
c("yazma True döner", _asil_yaz({"Tarih": ONCEKI}) is True)
os.remove(DB.ENERGY_CSV)
os.makedirs(DB.ENERGY_CSV)  # klasör → dosya açılamaz
c("yazılamazsa False döner", _asil_yaz({"Tarih": ONCEKI}) is False)

shutil.rmtree(tmp, ignore_errors=True)
for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)[:300]))
gecen = sum(1 for _, ok, _ in T if ok)
print("\n%d/%d PASS" % (gecen, len(T)))
sys.exit(0 if gecen == len(T) else 1)
