# -*- coding: utf-8 -*-
"""Ayarlar → Veri: tabloları JSON / CSV indirme testleri (örnek veri sunucusuyla).

    python merkez/test_veri_disa_aktar.py
"""
import csv
import io
import json
import os
import sys
import zipfile
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import _sim_sunucu  # noqa: E402
import veri_disa_aktar as V  # noqa: E402

SONUC = []


def c(ad, kosul, ayrinti=""):
    SONUC.append(bool(kosul))
    print(("PASS " if kosul else "FAIL ") + ad + ("" if kosul else "   " + str(ayrinti)))


U = _sim_sunucu.sunucu_baslat(8097)
K = "simulasyon"

liste = V.tablolari_bul(U, K)
c("bilinen tablolar listede", all(t in liste for t in V.TABLOLAR), liste)

ed = V.tablo_oku(U, K, "energy_data")
c("energy_data 1000'den fazla satir sayfalanarak tam okunur", len(ed) > 1000, len(ed))
c("sayfalarda tekrar yok", len({(r.get("lokasyon_id"), r.get("Tarih")) for r in ed}) == len(ed))
kucuk = V.tablo_oku(U, K, "energy_data", sayfa=250)
c("sayfa boyu sonucu degistirmez", len(kucuk) == len(ed))

# Gerçek PostgREST olmayan tabloya 404 döner (örnek sunucu boş liste döner) → taklit et
import urllib.error  # noqa: E402
_asil_get = V._get
def _get_404(u, k):
    if "/boyle_tablo_yok" in u:
        raise urllib.error.HTTPError(u, 404, "Not Found", {}, None)
    return _asil_get(u, k)
V._get = _get_404
veri, hata = V.hepsini_oku(U, K, ["energy_data", "lokasyonlar", "boyle_tablo_yok"])
V._get = _asil_get
c("404 'tablo yok' diye yazilir", hata.get("boyle_tablo_yok") == "HTTP 404 (tablo yok)", hata)
c("olmayan tablo hata olarak raporlanir, digerleri okunur",
  "boyle_tablo_yok" in hata and len(veri["energy_data"]) == len(ed) and "lokasyonlar" in veri, hata)

z = datetime(2026, 10, 26, 15, 40)
ad, bayt, mime = V.paket(veri, hata, "json", kaynak="ornek", zaman=z)
j = json.loads(bayt.decode("utf-8"))
c("JSON tek dosya, adinda tarih", ad == "synapse_yedek_20261026_1540.json" and mime == "application/json")
c("JSON tum tablolari ve sayilari tasir", len(j["tablolar"]["energy_data"]) == len(ed)
  and j["satir_sayilari"]["lokasyonlar"] == len(veri["lokasyonlar"]) and "boyle_tablo_yok" in j["okunamayan"])

ad, bayt, mime = V.paket(veri, hata, "csv", kaynak="ornek", zaman=z)
zf = zipfile.ZipFile(io.BytesIO(bayt))
c("CSV ZIP: tablo basina dosya + ozet", sorted(zf.namelist()) == ["energy_data.csv", "lokasyonlar.csv", "ozet.txt"]
  and ad.endswith("_csv.zip"), zf.namelist())
ham = zf.read("energy_data.csv")
c("CSV Excel icin BOM'lu UTF-8", ham.startswith(b"\xef\xbb\xbf"))
satirlar = list(csv.reader(io.StringIO(ham.decode("utf-8-sig")), delimiter=";"))
c("CSV satir sayisi = tablo + baslik", len(satirlar) == len(ed) + 1)
c("ozet okunamayani yazar", "boyle_tablo_yok" in zf.read("ozet.txt").decode("utf-8"))
c("ic ice deger CSV'de JSON metni", V.tablo_csv([{"a": {"x": 1}, "b": None}]).decode("utf-8-sig").splitlines()[1] == '"{""x"": 1}";')
c("farkli sutunlu satirlar birlesir", V.tablo_csv([{"a": 1}, {"b": 2}]).decode("utf-8-sig").splitlines()[0] == "a;b")
c("Turkce karakter korunur", "Ataşehir" in V.tablo_csv([{"ad": "Ataşehir"}]).decode("utf-8"))

# Modül yalnız OKUR
_kaynak = open(V.__file__, encoding="utf-8").read()
c("modul yazma istegi yapmaz", 'method="GET"' in _kaynak and not any(m in _kaynak for m in ('"POST"', '"PATCH"', '"DELETE"', '"PUT"')))
_m = open(os.path.join(os.path.dirname(V.__file__), "app_merkez.py"), encoding="utf-8").read()
c("Ayarlar'da Veri sekmesi", '"💾 Veri"' in _m and "with ayar_tab7:" in _m)
c("tek tik indirme: ertelenmis veri, sayfa yenilenmez", 'lambda: _vda_uret("json")' in _m and 'lambda: _vda_uret("csv")' in _m
  and _m.count('on_click="ignore"') >= 2)
c("Veri sekmesi izleyicide yok (st.stop sonrasi)",
  _m.index("if _IZLEYICI:\n    st.stop()") < _m.index("with ayar_tab7:"))

print("\n%d/%d PASS" % (sum(SONUC), len(SONUC)))
sys.exit(0 if all(SONUC) else 1)
