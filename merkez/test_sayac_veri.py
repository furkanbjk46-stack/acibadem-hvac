# -*- coding: utf-8 -*-
"""sayac_gunluk okuma (D1) ve Synapse enerji sorgusunun tarih penceresi (D2). Ağ bağlantısı YOK."""
import ast
import os
import sys
from datetime import date

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import sayac_veri as SV  # noqa: E402

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", str(ek)[:300])


SATIRLAR = ([{"lokasyon_id": "maslak", "tarih": "2026-11-%02d" % g, "sayac": s, "tur": t, "birim": "kWh",
              "deger": d * g} for g in range(1, 4)
             for s, t, d in (("MCC-10", "alt_sayac", 10), ("MCC-2", "alt_sayac", 2), ("TRDP-1", "trafo", 1000),
                             ("Sebeke", "sebeke", 5000))]
            + [{"lokasyon_id": "maslak", "tarih": "2026-11-02", "sayac": "Bos", "tur": "alt_sayac", "deger": None}]
            + [{"lokasyon_id": "atasehir", "tarih": "2026-11-01", "sayac": "X", "tur": "trafo", "deger": 1}])


class Sorgu:
    def __init__(self, ist):
        self.i, self.f = ist, []

    def select(self, s):
        self.i.select.append(s)
        return self

    def eq(self, a, b):
        self.f.append(lambda r: r.get(a) == b)
        return self

    def gte(self, a, b):
        self.f.append(lambda r: str(r.get(a)) >= b)
        return self

    def lte(self, a, b):
        self.f.append(lambda r: str(r.get(a)) <= b)
        return self

    def in_(self, a, b):
        self.f.append(lambda r: r.get(a) in b)
        return self

    def order(self, *a, **k):
        return self

    def range(self, a, b):
        self.r = (a, b)
        return self

    def execute(self):
        if self.i.hata:
            raise Exception("relation \"public.sayac_gunluk\" does not exist")
        d = [r for r in SATIRLAR if all(f(r) for f in self.f)]
        return type("C", (), {"data": d[self.r[0]:self.r[1] + 1]})()


class Ist:
    def __init__(self, hata=False):
        self.hata, self.select = hata, []

    def table(self, ad):
        assert ad == "sayac_gunluk"
        return Sorgu(self)


ist = Ist()
L = SV.sayac_listesi(ist, "maslak", date(2026, 11, 5))
c("liste: yalnız bu lokasyon, tür sırası (şebeke, trafo, …), doğal sıra (MCC-2 < MCC-10)",
  [x["sayac"] for x in L] == ["Sebeke", "TRDP-1", "Bos", "MCC-2", "MCC-10"], [x["sayac"] for x in L])
c("liste sorgusu yalnız gerekli sütunlar (select=* yok)", ist.select == ["sayac,tur,birim"], ist.select)
c("tablo yoksa liste boş (grafik seçeneği çıkmaz)", SV.sayac_listesi(Ist(hata=True), "maslak") == [])
c("varsayılan seçim: ilk türün sayaçları", SV.varsayilan_secim(L) == ["Sebeke"])
c("varsayılan seçim üst sınırı", len(SV.varsayilan_secim([{"sayac": str(i), "tur": "trafo"} for i in range(9)])) == 6)

ist = Ist()
D = SV.gunluk_degerler(ist, "maslak", ["MCC-2", "TRDP-1", "Bos"], "2026-11-02", "2026-11-03")
c("değerler: seçilen sayaçlar ve tarih aralığı", D == {"MCC-2": {"2026-11-02": 4.0, "2026-11-03": 6.0},
                                                    "TRDP-1": {"2026-11-02": 2000.0, "2026-11-03": 3000.0},
                                                    "Bos": {}}, D)
c("değer sorgusu yalnız gerekli sütunlar", ist.select == ["tarih,sayac,deger"], ist.select)
c("sayaç seçilmezse sorgu yok", SV.gunluk_degerler(Ist(hata=True), "maslak", [], "a", "b") == {})
c("özet: toplam ve gün sayısı", SV.ozet(D)[0] == ("MCC-2", 10.0, 2))

# Sayfa bağlantısı: grafik seçeneği yalnız sayaç verisi varsa listelenir
sayfa = open(os.path.join(BURASI, "pages", "lokasyon_detay.py"), encoding="utf-8").read()
ast.parse(sayfa)
c("lokasyon detayı: Sayaçlar seçeneği sayaç listesine bağlı",
  '("Sayaçlar (tek tek)", "sayaclar", "kWh")] if _sayac_liste else []' in sayfa
  and 'elif grafik_tip == "sayaclar":' in sayfa)

# D2: ana sayfa bütün geçmişi değil, pencereyi çeker
ana = open(os.path.join(BURASI, "app_merkez.py"), encoding="utf-8").read()
govde = ana[ana.index("def fetch_energy("):ana.index("def fetch_lokasyonlar(")]
c("fetch_energy tarih penceresiyle sorgular", '.gte("Tarih"' in govde and "ENERJI_PENCERE_GUN" in govde)
import re  # noqa: E402
m = re.search(r"^ENERJI_PENCERE_GUN\s*=\s*(\d+)", ana, re.M)
c("pencere en az 2 yıl + pay (geçen yıl kıyası, 'Son 12 ay' önceki dönemi)", m and int(m.group(1)) >= 760,
  m and m.group(1))

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
