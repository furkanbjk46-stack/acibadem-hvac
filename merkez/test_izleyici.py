# -*- coding: utf-8 -*-
"""İzleyici (şifresiz, salt okunur) linki — jeton ve yazma engeli testleri.

    python merkez/test_izleyici.py
"""
import os
import sys
import types
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

SONUC = []


def c(ad, kosul, ayrinti=""):
    SONUC.append(bool(kosul))
    print(("PASS " if kosul else "FAIL ") + ad + ("" if kosul else "   " + str(ayrinti)))


# ── Sahte streamlit: yalnızca session_state ve secrets ──
_ss = {}
_st = types.ModuleType("streamlit")
_st.session_state = _ss
_st.secrets = {}
sys.modules["streamlit"] = _st

# ── Sahte supabase istemcisi: yapılan çağrıları kaydeder ──
_cagrilar = []


class _Sorgu:
    def __init__(self, tablo):
        self.tablo = tablo

    def __getattr__(self, ad):
        def _f(*a, **k):
            _cagrilar.append((self.tablo, ad))
            return self
        return _f


class _Istemci:
    def table(self, ad):
        return _Sorgu(ad)

    def rpc(self, ad, *a, **k):
        _cagrilar.append(("rpc", ad))
        return self


_sb = types.ModuleType("supabase")
_sb.create_client = lambda *a, **k: _Istemci()
sys.modules["supabase"] = _sb

# urlopen gerçek ağa çıkmasın: kaydet ve dön
_acilan = []
urllib.request.urlopen = lambda istek, *a, **k: _acilan.append(istek) or "ok"

import salt_okuma  # noqa: E402
import giris       # noqa: E402

salt_okuma.kur()
salt_okuma.kur()   # ikinci kez kurmak zararsız olmalı
from supabase import create_client  # noqa: E402  (yamalı hali)

U = "https://ornek.supabase.co"


def istek(yol, metod="GET", veri=None):
    return urllib.request.Request(U + yol, data=veri, method=metod)


def engellendi_mi(f):
    try:
        f()
        return False
    except salt_okuma.YazmaEngellendi:
        return True


# ═════ YÖNETİCİ oturumu: hiçbir şey engellenmez ═════
_ss.clear(); _ss["giris_ok"] = True
cl = create_client(U, "k")
c("yonetici: select serbest", not engellendi_mi(lambda: cl.table("ayarlar").select("*").execute()))
c("yonetici: insert serbest", not engellendi_mi(lambda: cl.table("komutlar").insert({}).execute()))
c("yonetici: upsert serbest", not engellendi_mi(lambda: cl.table("ayarlar").upsert({}).execute()))
c("yonetici: REST POST serbest",
  not engellendi_mi(lambda: urllib.request.urlopen(istek("/rest/v1/ayarlar", "POST", b"{}"))))

# ═════ İZLEYİCİ oturumu ═════
_ss.clear(); _ss.update(giris_ok=True, izleyici=True)
cl = create_client(U, "k")
c("izleyici: select serbest", not engellendi_mi(lambda: cl.table("canli_guc").select("*").eq("a", 1).execute()))
for m in ("insert", "upsert", "update", "delete"):
    c("izleyici: %s engelli" % m, engellendi_mi(lambda m=m: getattr(cl.table("ayarlar"), m)({})))
c("izleyici: yazan rpc engelli", engellendi_mi(lambda: cl.rpc("veri_sil")))
c("izleyici: okuma rpc serbest", not engellendi_mi(lambda: cl.rpc("synapse_kullanim")))
c("izleyici: REST GET serbest",
  not engellendi_mi(lambda: urllib.request.urlopen(istek("/rest/v1/ayarlar?key=eq.x"))))
# HIZ (26.10.2026): istemci (url, anahtar) başına bir kez kurulur. Yönetici
# oturumunda kurulan istemci önbellekten gelse de izleyici engeli işlemeli
# (yukarıdaki izleyici kontrolleri zaten önbellekteki istemciyle çalıştı).
c("istemci tekrar kullanilir (her sorguda yeni HTTPS istemcisi kurulmaz)",
  create_client(U, "k")._ic is create_client(U, "k")._ic)
c("farkli anahtar ayri istemci", create_client(U, "k")._ic is not create_client(U, "k2")._ic)
for m in ("POST", "PATCH", "PUT", "DELETE"):
    c("izleyici: REST %s engelli" % m,
      engellendi_mi(lambda m=m: urllib.request.urlopen(istek("/rest/v1/ayarlar", m, b"{}"))))
c("izleyici: urlopen(adres, data) engelli",
  engellendi_mi(lambda: urllib.request.urlopen(U + "/rest/v1/komutlar", b"{}")))
c("izleyici: okuma RPC (POST) serbest",
  not engellendi_mi(lambda: urllib.request.urlopen(istek("/rest/v1/rpc/synapse_kullanim", "POST", b"{}"))))
c("izleyici: baska RPC (POST) engelli",
  engellendi_mi(lambda: urllib.request.urlopen(istek("/rest/v1/rpc/synapse_kullanim_sil", "POST", b"{}"))))
_once = len(_cagrilar)
engellendi_mi(lambda: cl.table("komutlar").insert({"x": 1}).execute())
c("izleyici: engellenen yazma alt istemciye HIC ulasmaz", len(_cagrilar) == _once)

# Oturum değişince engel kalkar (yamalar süreç genelinde, karar oturuma göre)
_ss.pop("izleyici")
c("izleyici bayragi kalkinca yazma serbest",
  not engellendi_mi(lambda: cl.table("ayarlar").upsert({})))

# ═════ Jeton ═════
os.environ["SYNAPSE_IZLEME_ANAHTAR"] = "test-anahtari-0123456789abcdef"
j = giris.izleme_jetonu_uret("test-anahtari-0123456789abcdef")
c("jeton 32 karakter", len(j) == 32)
c("dogru jeton gecerli", giris.izleme_jetonu_gecerli(j))
c("yanlis jeton gecersiz", not giris.izleme_jetonu_gecerli("0" * 32))
c("bos jeton gecersiz", not giris.izleme_jetonu_gecerli(""))
c("anahtar degisince eski jeton gecersiz",
  giris.izleme_jetonu_uret("baska-anahtar-0123456789abcdef") != j)
os.environ["SYNAPSE_IZLEME_ANAHTAR"] = "kisa"
c("kisa anahtarla ozellik kapali (fail-closed)",
  not giris.izleme_jetonu_gecerli(giris.izleme_jetonu_uret("kisa")))
os.environ.pop("SYNAPSE_IZLEME_ANAHTAR")
c("anahtar yoksa ozellik kapali", not giris.izleme_jetonu_gecerli(j))

# ═════ Kaynak denetimi: arayüzde yazma noktaları izleyicide kapalı ═════
_d = os.path.dirname(os.path.abspath(__file__))
_mrk = open(os.path.join(_d, "app_merkez.py"), encoding="utf-8").read()
c("koruma katmani app_merkez basinda kuruluyor",
  _mrk.index("_salt_okuma.kur()") < _mrk.index("giris.giris_kapisi()"))
c("OTO SET anahtari izleyicide kapali", 'help=_sw_ipucu, disabled=_IZLEYICI' in _mrk)
c("gecis saati kaydet izleyicide kapali", "_demo_modu() or _IZLEYICI" in _mrk)
c("AI analizi izleyici tetiklemez", "_yenile_btn) and not _IZLEYICI" in _mrk)
# Ayarlar artık sağ üstteki düğmeyle açılan pencere: izleyicide düğme yok,
# pencere de açılmaz (ve sayfa sonunda izleyici için st.stop korunur)
c("Ayarlar izleyicide gizli",
  "if not _IZLEYICI:\n        # Ayarlar paneli TARAYICIDA" in _mrk
  and _mrk.index("if _IZLEYICI:\n    st.stop()") < _mrk.index('with st.container(key="ayarlar_panel")'))
_gr = open(os.path.join(_d, "giris.py"), encoding="utf-8").read()
c("cikis izleyici bayragini siler", '"giris_jeton", "izleyici")' in _gr)

print("\n%d/%d PASS" % (sum(SONUC), len(SONUC)))
sys.exit(0 if all(SONUC) else 1)
