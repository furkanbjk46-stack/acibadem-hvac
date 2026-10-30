# -*- coding: utf-8 -*-
"""data_collector: BACnet şablonu her günlük okumadan önce YENİDEN okunur mu?

27.10.2026 hatası: şablona DIS HAVA NEM + KOJEN-1..4 eklendi, program açılışta
okuduğu eski 48 noktalık listeyle devam etti → energy_data'da Kojen_Adet ve
Dis_Hava_Nem_Yuzde boş. Bu test program yeniden başlatılmadan yeni noktaların
ertesi sabah okunduğunu doğrular.

    python test_bacnet_sablon_yenileme.py
"""
import csv
import os
import sys
import tempfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pandas as pd  # noqa: E402
import data_collector as DC  # noqa: E402

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


gecici = tempfile.mkdtemp()
os.makedirs(os.path.join(gecici, "configs"))
sablon = os.path.join(gecici, "configs", "hedefli_okuma_sablonu_2.xlsx")
csv_yol = os.path.join(gecici, "hedefli_enerji_verileri.csv")


def sablon_yaz(adlar):
    pd.DataFrame([{"Gateway IP": "192.168.0.2", "Network (DNET)": 2, "MAC (DADR)": "0x0103",
                   "Device Instance ID": 2098215, "Object Type": 3, "Object Instance": i,
                   "Point Name": ad} for i, ad in enumerate(adlar)]).to_excel(sablon, index=False)


ESKI = ["DIS HAVA", "CH SET", "SEBEKE KESIK BILGISI"]
YENI = ["DIS HAVA", "DIS HAVA NEM", "CH SET"] + ["KOJEN-%d DURUM BILGISI" % i for i in range(1, 5)]
sablon_yaz(ESKI)

DC._EXCEL_FILE_CONFIGS = sablon
DC._EXCEL_FILE_ROOT = os.path.join(gecici, "yok.xlsx")
DC.BACNET_CSV = csv_yol
DC.bacnet_nokta_oku = lambda *a, **k: 1.0

# Sahte saat: gün 1 okuma penceresi → (okuma) → gün 2 aynı pencere → (okuma) → dur
# (pencere DC.BACNET_SAAT/DAKIKA'dan — 30.10.2026'da 07:05'ten 23:54'e alındı)
_DK = DC.BACNET_DAKIKA + 1 if DC.BACNET_DAKIKA < 59 else DC.BACNET_DAKIKA
ANLAR = [datetime(2026, 10, 27, DC.BACNET_SAAT, _DK), datetime(2026, 10, 28, DC.BACNET_SAAT, _DK)]
okunan = []


class _Dur(Exception):
    pass


class _Saat:
    i = -1

    @classmethod
    def now(cls):
        cls.i += 1
        if cls.i >= len(ANLAR):
            raise _Dur()
        return ANLAR[cls.i]


def _uyu(_sn):
    # Her günlük okumadan sonra o günün CSV'sini sakla; ilk günden sonra şablonu güncelle
    if os.path.exists(csv_yol):
        okunan.append([r["Point_Name"] for r in csv.DictReader(open(csv_yol, encoding="utf-8"))])
        os.remove(csv_yol)
        if len(okunan) == 1:
            sablon_yaz(YENI)            # program ÇALIŞIRKEN şablon güncellendi


DC.datetime = _Saat
DC.time.sleep = _uyu
try:
    DC.bacnet_thread()
except _Dur:
    pass

c("gun 1: acilistaki (eski) sablonla okundu", okunan and okunan[0] == ESKI, okunan)
c("gun 2: yeniden baslatmadan YENI sablonla okundu", len(okunan) > 1 and okunan[1] == YENI, okunan)
c("gun 2: kaldirilan nokta artik okunmuyor", len(okunan) > 1 and "SEBEKE KESIK BILGISI" not in okunan[1])

# Şablon okunamazsa son başarılı şablonla devam
DC.datetime = datetime
c("okunamayan sablon None doner (thread cokmez)",
  (lambda: (open(sablon, "w").write("bozuk"), DC.bacnet_sablonu_oku())[1])() is None)
c("sablon yolu her cagrida yeniden belirlenir", DC.bacnet_sablon_yolu() == sablon)

for ad, ok, detay in T:
    print(("PASS " if ok else "FAIL ") + ad + ("" if ok else "   " + str(detay)[:300]))
print("%d/%d PASS" % (sum(1 for x in T if x[1]), len(T)))
sys.exit(0 if all(x[1] for x in T) else 1)
