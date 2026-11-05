# -*- coding: utf-8 -*-
"""Müdür tespitleri (05.11.2026) — iki düzeltmenin testi.

  1) Parola veya izleme anahtarı değişince AÇIK oturum düşmeli.
  2) Canlı toplama yalnız KENDİ ölçümü taze sayaçlar girmeli; tabloda kalmış
     24 saatlik bir değer (ör. 9.000 kW) toplamı şişirmemeli.

    python merkez/test_oturum_tazelik.py
"""
import ast
import os
import sys
import time
import types
from datetime import datetime, timedelta

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)

SONUC = []


def c(ad, kosul, ayrinti=""):
    SONUC.append(bool(kosul))
    print(("PASS " if kosul else "FAIL ") + ad + ("" if kosul else "   " + str(ayrinti)))


# ── Sahte streamlit: session_state, secrets, query_params ──
class _Dur(Exception):
    pass


class _Sorgu(dict):
    pass


_st = types.ModuleType("streamlit")
_st.session_state = {}
_st.secrets = {}
_st.query_params = _Sorgu()
_st.stop = lambda: (_ for _ in ()).throw(_Dur())
sys.modules["streamlit"] = _st

import giris  # noqa: E402

H1 = giris.parola_hash_uret("EskiParola123")
H2 = giris.parola_hash_uret("YeniParola456")
_ayar = {"hash": H1}
_yazilan_cerez = []
giris._ayarlar = lambda: ("acibadem", _ayar["hash"])
giris._cerez_oku = lambda ad: ""                       # sunucu çerez göremiyor (en kötü durum)
giris._cerez_yaz = lambda jeton, sn: _yazilan_cerez.append(jeton)
giris._cerez_sil = lambda: None
giris._cm = lambda: None


def _form(*a, **k):
    raise _Dur()


giris._giris_formu = _form


def kapi():
    """giris_kapisi() → True: içeri alındı, False: giriş formuna düştü."""
    try:
        giris.giris_kapisi()
        return True
    except _Dur:
        return False


ss = _st.session_state

# ═════ 1) Tam yetkili oturum ═════
ss.clear()
ss.update(giris_ok=True, giris_son_hareket=time.time(),
          giris_jeton=giris._jeton_uret(H1, giris.OTURUM_SAAT * 3600))
c("geçerli oturum içeri alınır", kapi())

_ayar["hash"] = H2                                     # parola değiştirildi
_yazilan_cerez.clear()
c("parola değişince AÇIK oturum düşer", not kapi() and not ss.get("giris_ok"), dict(ss))
c("düşen oturuma YENİ parolayla çerez yazılmaz", not _yazilan_cerez, _yazilan_cerez)

# Eskiden: çerez okunamayınca geçersiz jeton yerine yeni parolayla jeton üretilirdi
_ayar["hash"] = H1
ss.clear()
ss.update(giris_ok=True, giris_son_hareket=time.time(), giris_jeton="uydurma.jeton.imza")
_yazilan_cerez.clear()
c("geçersiz jetonlu oturum içeri alınmaz", not kapi())
c("geçersiz jeton yenisiyle DEĞİŞTİRİLMEZ (çerez yazılmaz)", not _yazilan_cerez, _yazilan_cerez)

ss.clear()
ss.update(giris_ok=True, giris_son_hareket=time.time())
c("jetonsuz oturum içeri alınmaz", not kapi())

# Kullanım sürdükçe oturum düşmesin: süresinin yarısı geçen jeton yenilenir
ss.clear()
_az = giris._jeton_uret(H1, 600)                       # 10 dk kalmış
ss.update(giris_ok=True, giris_son_hareket=time.time(), giris_jeton=_az)
_yazilan_cerez.clear()
c("süresi azalan geçerli jeton içeri alınır", kapi())
c("...ve GÜNCEL parolayla yenilenip çereze yazılır",
  ss["giris_jeton"] != _az and giris._jeton_gecerli(ss["giris_jeton"], H1)
  and _yazilan_cerez == [ss["giris_jeton"]], _yazilan_cerez)

ss.clear()
_tam = giris._jeton_uret(H1, giris.OTURUM_SAAT * 3600)
ss.update(giris_ok=True, giris_son_hareket=time.time(), giris_jeton=_tam)
kapi()
c("taze jeton gereksiz yere yenilenmez", ss["giris_jeton"] == _tam)

c("süresi dolmuş jetonlu oturum düşer",
  (ss.clear(), ss.update(giris_ok=True, giris_son_hareket=time.time(),
                          giris_jeton=giris._jeton_uret(H1, -5)), not kapi())[-1])

# ═════ 2) İzleyici linki ═════
K1, K2 = "izleme-anahtari-1-uzun-rastgele", "izleme-anahtari-2-uzun-rastgele"
_st.secrets = {"izleme": {"anahtar": K1}}
ss.clear()
_st.query_params.clear()
_st.query_params["izle"] = giris.izleme_jetonu_uret(K1)
c("geçerli izleyici linki içeri alır", kapi() and giris.izleyici_mi())
c("link jetonu adres çubuğundan silinir", "izle" not in _st.query_params)
c("sonraki turda (link yok) izleyici devam eder", kapi() and giris.izleyici_mi())

_st.secrets = {"izleme": {"anahtar": K2}}              # anahtar değiştirildi
c("izleme anahtarı değişince AÇIK izleyici oturumu düşer",
  not kapi() and not giris.izleyici_mi() and not ss.get("giris_ok"), dict(ss))

_st.secrets = {"izleme": {"anahtar": K1}}
ss.clear()
_st.query_params["izle"] = giris.izleme_jetonu_uret(K1)
kapi()
_st.secrets = {}                                       # anahtar tamamen kaldırıldı
c("izleme anahtarı kaldırılınca AÇIK izleyici oturumu düşer",
  not kapi() and not giris.izleyici_mi(), dict(ss))

_st.secrets = {"izleme": {"anahtar": K1}}
ss.clear()
_st.query_params["izle"] = "uydurma"
c("uydurma izleyici linki içeri almaz", not kapi() and not giris.izleyici_mi())
_st.query_params.clear()

ss.clear()
ss.update(giris_ok=True, izleyici=True, izleyici_jeton="x", giris_son_hareket=time.time())
giris.cikis_yap()
c("çıkış izleyici jetonunu da siler", "izleyici_jeton" not in ss and ss.get("giris_cikis"))

# ═════ 3) Canlı toplam: satır bazında tazelik ═════
import canli_izleme as CI  # noqa: E402

c("canli_izleme sürüm damgası sayfayla aynı",
  "_CI_GEREKEN_SURUM = %d" % CI.SURUM in open(os.path.join(BURASI, "pages", "lokasyon_detay.py"),
                                             encoding="utf-8").read())
T = datetime(2026, 11, 5, 12, 0, 0)
olc = [{"cihaz": "TRDP-1", "kw": 900.0, "olcum_zamani": (T - timedelta(seconds=10)).isoformat()},
       {"cihaz": "TRDP-9", "kw": 9000.0, "olcum_zamani": (T - timedelta(hours=24)).isoformat()},
       {"cihaz": "MCC-1", "kw": 50.0, "olcum_zamani": "bozuk"}]
taze, eski = CI.taze_ayir(olc, simdi=T)
c("taze_ayir: yalnız kendi ölçümü taze satır geçer", [o["cihaz"] for o in taze] == ["TRDP-1"], taze)
c("taze_ayir: 24 saatlik satır ve zamanı okunamayan satır eski",
  sorted(a for a, _ in eski) == ["MCC-1", "TRDP-9"], eski)
c("taze_ayir: sınırdaki satır (tam 120 sn) taze",
  len(CI.taze_ayir([{"cihaz": "A", "olcum_zamani": (T - timedelta(seconds=120)).isoformat()}],
                   simdi=T)[0]) == 1)
_h = CI.eski_sayac_html(eski)
c("eski sayaç notu: sayı, ad ve yaş", "2 sayacın ölçümü eski" in _h and "TRDP-9" in _h
  and "önce" in _h and "zamanı okunamadı" in _h, _h)
c("eski sayaç yoksa not yok", CI.eski_sayac_html([]) == "")
s = CI.seri_guncelle(None, taze, 300, simdi=T)
c("detay sayfası serisi eski değeri toplamaz",
  CI.toplam(CI.son_degerler(s)) == 900.0, CI.son_degerler(s))

_MRK = open(os.path.join(BURASI, "app_merkez.py"), encoding="utf-8").read()
_fn = next(n for n in ast.parse(_MRK).body if isinstance(n, ast.FunctionDef) and n.name == "canli_ozet_hesapla")
_ns = {"datetime": datetime, "CANLI_BAYAT_SN": 120}
exec(ast.get_source_segment(_MRK, _fn), _ns)
_simdi = datetime.now()
_taze_t = (_simdi - timedelta(seconds=10)).isoformat()
_eski_t = (_simdi - timedelta(hours=24)).isoformat()
oz = _ns["canli_ozet_hesapla"]([
    {"lokasyon_id": "maslak", "cihaz": "TRDP-1", "kw": 900.0, "olcum_zamani": _taze_t},
    {"lokasyon_id": "maslak", "cihaz": "TRDP-9", "kw": 9000.0, "olcum_zamani": _eski_t},
    {"lokasyon_id": "maslak", "cihaz": "CHILLER-1", "kw": 200.0, "olcum_zamani": "bozuk"},
    {"lokasyon_id": "kopuk", "cihaz": "TRDP-1", "kw": 700.0, "olcum_zamani": _eski_t}])
c("ana ekran: 24 saatlik 9.000 kW toplama GİRMEZ", oz["maslak"]["trafo"] == 900.0
  and oz["maslak"]["enerji"] == 900.0, oz.get("maslak"))
c("ana ekran: zamanı okunamayan satır toplama girmez", oz["maslak"]["sogutma"] is None, oz.get("maslak"))
c("ana ekran: atlanan eski satır sayısı tutulur", oz["maslak"]["eski_sayac"] == 2, oz.get("maslak"))
c("ana ekran: bütün satırları eski lokasyon canlı sayılmaz", "kopuk" not in oz, oz)
c("ana ekran: lokasyon yaşı taze satırdan", oz["maslak"]["yas"] < 60, oz.get("maslak"))

hata = SONUC.count(False)
print("\n%d/%d PASS" % (len(SONUC) - hata, len(SONUC)))
sys.exit(1 if hata else 0)
