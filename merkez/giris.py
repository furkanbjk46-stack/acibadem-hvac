# -*- coding: utf-8 -*-
"""
SYNAPSE — Giriş kapısı (kimlik doğrulama)
==========================================

app_merkez.py'nin QR bakım bloğundan SONRA çağrılır:

    import giris
    giris.giris_kapisi()          # giriş yapılmamışsa ekranı basar ve durdurur

NEDEN GEREKLİ:
Merkez portal Supabase'e service_role anahtarıyla bağlanır (RLS'i bypass eder).
Yani portala erişebilen, veritabanına tam yetkili demektir. Bu yüzden portalın
önünde kimlik doğrulaması olmak zorundadır.

PAROLA SAKLAMA:
Parola düz metin olarak DEĞİL, PBKDF2-SHA256 (200.000 tur) karması olarak
Streamlit secrets içinde tutulur. Karma üretmek için:

    python giris.py "yeni-parola"

çıktısını Streamlit Cloud → Settings → Secrets içine yapıştır:

    [giris]
    kullanici = "acibadem"
    parola_hash = "pbkdf2_sha256$200000$....$...."

GÜVENLİK NOTU — fail-closed:
[giris] bölümü tanımlı değilse portal AÇILMAZ; kurulum talimatı gösterilir.
Aksi hâlde secrets'ı eklemeyi unutmak portalı herkese açık bırakırdı.
"""

import base64
import hashlib
import hmac
import os
import secrets as _secrets
import sys
import threading
import time

# ── Ayarlar ────────────────────────────────────────────────────────────────
PBKDF2_TUR       = 200_000   # iterasyon sayısı
OTURUM_SAAT      = 12        # bu kadar hareketsizlikten sonra oturum düşer
KILIT_ESIGI      = 8         # bu kadar hatalı denemeden sonra geçici kilit
KILIT_SURE_SN    = 300       # kilit süresi (5 dk)
MAKS_GECIKME_SN  = 8         # hatalı denemede uygulanan azami bekleme
CEREZ_AD         = "synapse_oturum"   # oturum çerezinin adı

_BASE = os.path.dirname(os.path.abspath(__file__))
_ARKAPLAN = os.path.join(_BASE, "assets", "login_bg.jpg")

# Hatalı deneme sayacı — süreç genelinde (tek ortak hesap olduğu için tek sayaç).
# session_state kullanılmaz: saldırgan yeni oturum açarak sayacı sıfırlayabilirdi.
_kilit = threading.Lock()
_durum = {"hata": 0, "son_hata": 0.0}


# ═══════════════════════════════════════════════════════════════════════════
# PAROLA KARMA
# ═══════════════════════════════════════════════════════════════════════════

def parola_hash_uret(parola: str, tuz: bytes = None) -> str:
    """Parolayı PBKDF2-SHA256 ile karmalar. Saklanabilir tek satır döner."""
    tuz = tuz or _secrets.token_bytes(16)
    ozet = hashlib.pbkdf2_hmac("sha256", parola.encode("utf-8"), tuz, PBKDF2_TUR)
    return "pbkdf2_sha256$%d$%s$%s" % (PBKDF2_TUR, tuz.hex(), ozet.hex())


def parola_dogrula(parola: str, kayit: str) -> bool:
    """Girilen parolayı saklanan karma ile karşılaştırır (zamanlama-güvenli)."""
    try:
        yontem, tur, tuz_hex, ozet_hex = kayit.split("$")
        if yontem != "pbkdf2_sha256":
            return False
        ozet = hashlib.pbkdf2_hmac(
            "sha256", parola.encode("utf-8"), bytes.fromhex(tuz_hex), int(tur))
        return hmac.compare_digest(ozet.hex(), ozet_hex)
    except Exception:
        return False


# ═══════════════════════════════════════════════════════════════════════════
# KABA KUVVET KORUMASI
# ═══════════════════════════════════════════════════════════════════════════

def _kilitli_mi():
    """(kilitli: bool, kalan_saniye: int)"""
    with _kilit:
        if _durum["hata"] < KILIT_ESIGI:
            return False, 0
        kalan = KILIT_SURE_SN - (time.time() - _durum["son_hata"])
        if kalan <= 0:
            _durum["hata"] = 0
            return False, 0
        return True, int(kalan)


def _hata_kaydet():
    with _kilit:
        _durum["hata"] += 1
        _durum["son_hata"] = time.time()
        sayi = _durum["hata"]
    # Artan gecikme: her hatada bekleme katlanır (deneme hızını düşürür)
    time.sleep(min(2 ** min(sayi, 5) * 0.25, MAKS_GECIKME_SN))


def _basari_kaydet():
    with _kilit:
        _durum["hata"] = 0


# ═══════════════════════════════════════════════════════════════════════════
# OTURUM ÇEREZİ — sayfa yenilemesinde oturumun düşmemesi için
# ═══════════════════════════════════════════════════════════════════════════
#
# NEDEN: Streamlit'in session_state'i tarayıcı oturumuna bağlıdır; F5'te sıfırlanır.
# Kalıcılık için imzalı bir jeton çerezde tutulur.
#
# GÜVENLİK TASARIMI:
#   * Çerezde parola YOKTUR — yalnızca "son kullanma zamanı + rastgele değer +
#     HMAC imzası" bulunur.
#   * İmza anahtarı parola karmasından türetilir; karma yalnızca sunucudadır.
#     Bu sayede saldırgan geçerli jeton UYDURAMAZ.
#   * Yan fayda: parola değiştirilince imza anahtarı da değişir → eski tüm
#     oturumlar kendiliğinden geçersiz olur.
#   * Süre sunucu tarafında doğrulanır; çerezdeki tarihe güvenilmez.
#
# Çerez yazma tarayıcı tarafında yapılır (Streamlit çerez yazamaz), ancak
# DOĞRULAMA tamamen sunucuda (st.context.cookies) yapılır — kritik olan budur.

def _imza_anahtari(parola_hash: str) -> bytes:
    """İmza anahtarını parola karmasından türetir (karma sunucuda kalır)."""
    return hashlib.sha256(("synapse-oturum-v1|" + parola_hash).encode()).digest()


def _jeton_uret(parola_hash: str, saniye: int) -> str:
    son = int(time.time()) + saniye
    rastgele = _secrets.token_hex(8)
    govde = "%d.%s" % (son, rastgele)
    imza = hmac.new(_imza_anahtari(parola_hash), govde.encode(), hashlib.sha256).hexdigest()
    return govde + "." + imza


def _jeton_gecerli(jeton: str, parola_hash: str) -> bool:
    """Jetonun imzasını ve süresini SUNUCUDA doğrular."""
    try:
        son_s, rastgele, imza = jeton.split(".")
        govde = "%s.%s" % (son_s, rastgele)
        beklenen = hmac.new(_imza_anahtari(parola_hash), govde.encode(),
                            hashlib.sha256).hexdigest()
        if not hmac.compare_digest(imza, beklenen):
            return False                      # imza tutmuyor → uydurma
        return int(son_s) > time.time()       # süresi dolmuş mu
    except Exception:
        return False


# ── Çerez okuma köprüsü ────────────────────────────────────────────────────
#
# NEDEN AYRI BİR KÜTÜPHANE:
# Streamlit Cloud'da yapılan ölçüm (?tani=1) şunu gösterdi:
#   * çerez tarayıcıya YAZILIYOR (synapse_oturum hem bileşende hem üst belgede var)
#   * ancak SUNUCU hiçbir çerez görmüyor: st.context.cookies TAMAMEN BOŞ,
#     tarayıcıda 9 çerez varken bile.
# Yani Cloud ortamında çerezler sunucu tarafına geçmiyor ve st.context.cookies
# kullanılamıyor. Değerin tarayıcıdan Python'a geri dönmesi için çift yönlü bir
# bileşen gerekiyor; extra-streamlit-components/CookieManager tam olarak bunu yapar.
#
# SAVUNMALI KURULUM: kütüphane yoksa veya hata verirse uygulama ÇÖKMEZ;
# st.context.cookies'e geri düşer (yerelde çalışır, Cloud'da oturum kalıcı olmaz).

def _cm():
    """CookieManager örneğini döner; kullanılamıyorsa None."""
    import streamlit as st
    if st.session_state.get("_cm_kullanilamaz"):
        return None
    cm = st.session_state.get("_cm")
    if cm is not None:
        return cm
    try:
        import extra_streamlit_components as stx
        cm = stx.CookieManager(key="synapse_cerez_yoneticisi")
        st.session_state["_cm"] = cm
        st.session_state.pop("_cm_hata", None)
        return cm
    except Exception as e:
        # Hata mesajı saklanır: ?tani=1 ekranında gösterilir. Kütüphane
        # yayın ortamında yüklenemezse sorunu buradan görebilmek gerekir.
        st.session_state["_cm_hata"] = "%s: %s" % (type(e).__name__, e)
        st.session_state["_cm_kullanilamaz"] = True
        return None


def _cerez_oku(ad: str) -> str:
    import streamlit as st
    cm = _cm()
    if cm is not None:
        try:
            # get_all() KULLANILIR, get() DEĞİL.
            #
            # Kütüphanede get(), yalnızca CookieManager NESNESİ OLUŞTURULURKEN
            # doldurulan bir önbelleği okur. Nesneyi session_state'te sakladığımız
            # için (ki saklamak zorundayız, yoksa her turda yeni bileşen oluşur)
            # o önbellek ilk çalıştırmadaki BOŞ haliyle donup kalıyordu ve
            # get() hep None dönüyordu.
            #
            # Belirtisi tam olarak şuydu: ?tani=1 ekranı (get_all çağırdığı için)
            # çerezi geçerli görüyor, ama giriş kapısı (get çağırdığı için)
            # göremeyip kullanıcıyı giriş ekranına atıyordu.
            #
            # get_all() bileşeni yeniden çalıştırır ve güncel çerezleri getirir.
            tum = cm.get_all(key="synapse_cerez_okuma") or {}
            deger = tum.get(ad)
            if deger:
                return str(deger)
        except Exception:
            pass
    try:
        return str(st.context.cookies.get(ad, "") or "")
    except Exception:
        return ""


_CEREZ_JS = """
// Cerezi olabildigince cok yoldan yazmayi dener ve isini garantiye alir.
//
// NEDEN BU KADAR YOL:
// Streamlit Cloud'da uygulama bir sarmalayici IFRAME icinde calisabiliyor.
// O durumda:
//   * window.parent.document erisimi capraz-kaynak olur ve HATA firlatir
//     -> tek basina window.parent kullanan yazim sessizce basarisiz olur
//   * cerez ucuncu-taraf baglamda kalir; SameSite=Lax ile TARAYICI GONDERMEZ
//     -> SameSite=None; Secure gerekir (yalnizca https'te gecerlidir)
// Bu yuzden once bilesenin KENDI belgesine (ki uygulamanin alan adina aittir)
// yazilir, sonra parent denenir; her birinde once None+Secure, tutmazsa Lax.
function _syn_yaz(ad, deger, saniye){
  var temel = ad + "=" + deger + "; path=/; max-age=" + saniye;
  var denemeler = [temel + "; SameSite=None; Secure", temel + "; SameSite=Lax"];
  var yazildi = false;

  for (var i = 0; i < denemeler.length && !yazildi; i++){
    try{
      document.cookie = denemeler[i];
      yazildi = document.cookie.indexOf(ad + "=") > -1;
    }catch(e){}
  }
  // Ust belgeye de dene (ayni kaynaksa calisir, degilse hata yutulur)
  for (var j = 0; j < denemeler.length; j++){
    try{ window.parent.document.cookie = denemeler[j]; }catch(e){}
  }
  return yazildi;
}
"""


def _cerez_yaz(jeton: str, saniye: int):
    """Çerezi tarayıcıya yazar (bkz. _CEREZ_JS içindeki gerekçe).

    Önce CookieManager denenir — çünkü okuma da onun üzerinden yapılıyor ve
    yazdığını kendi önbelleğinde de tutar. Kullanılamıyorsa doğrudan JS'e düşülür.
    """
    import streamlit as st
    import streamlit.components.v1 as components

    cm = _cm()
    if cm is not None:
        try:
            from datetime import datetime as _dt, timedelta as _td, timezone as _tz
            cm.set(CEREZ_AD, jeton,
                   expires_at=_dt.now(_tz.utc) + _td(seconds=saniye),
                   key="synapse_cerez_yaz")
            return
        except Exception:
            pass

    components.html(
        "<script>%s _syn_yaz(%r, %r, %d);</script>"
        % (_CEREZ_JS, CEREZ_AD, jeton, saniye), height=0)


def _cerez_sil():
    import streamlit.components.v1 as components

    import streamlit as st
    cm = _cm()
    # cm.delete yalnızca BİR KEZ çağrılır: her turda çağrılması hem yinelenen
    # bileşen anahtarı hatasına yol açar hem de her seferinde yeni bir rerun
    # tetikler.
    if cm is not None and not st.session_state.get("_cm_silindi"):
        st.session_state["_cm_silindi"] = True
        try:
            cm.delete(CEREZ_AD, key="synapse_cerez_sil")
        except Exception:
            pass

    components.html(
        """<script>
        var _a = %r;
        var _v = ["; SameSite=None; Secure", "; SameSite=Lax", ""];
        for (var i = 0; i < _v.length; i++){
          try{ document.cookie = _a + "=; path=/; max-age=0" + _v[i]; }catch(e){}
          try{ window.parent.document.cookie = _a + "=; path=/; max-age=0" + _v[i]; }catch(e){}
        }
        </script>""" % CEREZ_AD, height=0)


# ═══════════════════════════════════════════════════════════════════════════
# GÖRSEL
# ═══════════════════════════════════════════════════════════════════════════

def _arkaplan_uri():
    """Arka plan görselini data URI olarak döner (CSS'e gömmek için)."""
    import streamlit as st

    @st.cache_data(show_spinner=False)
    def _oku():
        try:
            with open(_ARKAPLAN, "rb") as f:
                return "data:image/jpeg;base64," + base64.b64encode(f.read()).decode()
        except FileNotFoundError:
            return ""
    return _oku()


def _stil():
    import streamlit as st
    uri = _arkaplan_uri()
    arka = ("background-image:url('%s') !important;" % uri) if uri else ""
    st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');

/* Arka plan görseli — koyulaştırma + vinyet ile metin okunurluğu korunur.
   (Görsel cyan baskın olduğu için doygunluğa dokunulmaz.) */
[data-testid="stAppViewContainer"]{
  %s
  background-size:cover !important;
  background-position:center !important;
  background-attachment:fixed !important;
}
[data-testid="stAppViewContainer"]::before{
  content:"";position:fixed;inset:0;z-index:0;pointer-events:none;
  background:
    radial-gradient(ellipse at 50%% 50%%, rgba(2,6,23,0.34) 0%%, rgba(2,6,23,0.76) 100%%),
    linear-gradient(180deg, rgba(2,6,23,0.45) 0%%, transparent 30%%, rgba(2,6,23,0.58) 100%%);
}
[data-testid="stHeader"], [data-testid="stToolbar"]{background:transparent !important;}
[data-testid="stDecoration"]{display:none !important;}   /* ustteki renkli serit */
[data-testid="stToolbar"]{display:none !important;}      /* Deploy / menu */
[data-testid="stSidebarCollapsedControl"]{display:none !important;}  /* kenar cubugu oku */
footer, #MainMenu{visibility:hidden;}
/* Panel dikeyde ortalanir (giris ekraninda baska icerik yok) */
.block-container{padding-top:14vh !important; padding-bottom:6vh !important;
                 position:relative; z-index:1;}

/* ── Buzlu cam panel ──
   Genislik CSS ile sinirlanir: layout="wide" oldugu icin panel aksi halde
   ekrani boydan boya kaplar ve tasarimin oranlari bozulur. */
.st-key-giris_panel{
  max-width:780px !important;
  margin:0 auto !important;
  background:rgba(15,23,42,0.40) !important;
  backdrop-filter:blur(22px) saturate(140%%) !important;
  -webkit-backdrop-filter:blur(22px) saturate(140%%) !important;
  border:1px solid rgba(56,189,248,0.22) !important;
  border-radius:18px !important;
  padding:40px 38px !important;
  box-shadow:0 30px 80px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.08) !important;
}
.st-key-giris_panel [data-testid="stVerticalBlock"]{gap:0.35rem;}

/* Iki yariyi ayiran dikey cizgi (tasarimdaki bolunmus ekran gorunumu) */
.st-key-giris_panel [data-testid="stHorizontalBlock"]{align-items:stretch;}
.st-key-giris_panel [data-testid="stColumn"]:first-of-type{
  border-right:1px solid rgba(56,189,248,0.16);
  padding-right:34px !important;
}
.st-key-giris_panel [data-testid="stColumn"]:last-of-type{
  padding-left:34px !important;
  display:flex;flex-direction:column;justify-content:center;
}
/* Sol yari: marka ustte, istatistikler altta */
.g-sol{display:flex;flex-direction:column;justify-content:space-between;min-height:236px;}

.g-ust{font-family:'Plus Jakarta Sans',sans-serif;font-size:8.5px;letter-spacing:3.4px;
       color:#94a3b8;text-transform:uppercase;}
.g-mrk{font-family:'Playfair Display',serif;font-size:31px;color:#f8fafc;font-weight:600;
       letter-spacing:1px;line-height:1.15;margin-top:5px;text-shadow:0 2px 22px rgba(0,0,0,0.55);}
.g-alt{font-family:'Plus Jakarta Sans',sans-serif;font-size:9.5px;letter-spacing:2.6px;
       color:#38bdf8;text-transform:uppercase;margin-top:7px;}
.g-istat{display:flex;justify-content:space-between;align-items:baseline;padding:9px 0;
         border-bottom:1px solid rgba(56,189,248,0.14);font-size:10.5px;color:#cbd5e1;
         font-family:'Plus Jakarta Sans',sans-serif;}
.g-istat:last-child{border:none;}
.g-istat b{font-family:'Playfair Display',serif;font-size:15px;color:#38bdf8;font-weight:700;
           text-shadow:0 0 15px rgba(56,189,248,0.45);}
.g-nokta{display:inline-block;width:6px;height:6px;border-radius:50%%;background:#10b981;
         margin-right:7px;box-shadow:0 0 9px #10b981;}
.g-kucuk{font-size:9.5px;color:#64748b;text-align:center;margin-top:12px;
         font-family:'Plus Jakarta Sans',sans-serif;}

/* ── Streamlit girdilerini tasarıma uydur ── */
.st-key-giris_panel [data-testid="stTextInput"] input{
  background:rgba(2,6,23,0.42) !important;
  border:1px solid rgba(56,189,248,0.22) !important;
  border-radius:9px !important;color:#e2e8f0 !important;
  font-family:'Plus Jakarta Sans',sans-serif !important;font-size:13px !important;
  padding:11px 13px !important;
}
.st-key-giris_panel [data-testid="stTextInput"] input:focus{
  border-color:rgba(56,189,248,0.65) !important;
  box-shadow:0 0 0 3px rgba(56,189,248,0.13) !important;
}
.st-key-giris_panel [data-testid="stTextInput"] label p{
  font-size:9px !important;letter-spacing:1.8px !important;text-transform:uppercase !important;
  color:#94a3b8 !important;font-family:'Plus Jakarta Sans',sans-serif !important;
}
/* Buton — form icindeki gonder butonu .stButton DEGIL,
   [data-testid="stFormSubmitButton"] altindadir; ikisi de hedeflenir. */
.st-key-giris_panel .stButton button,
.st-key-giris_panel [data-testid="stFormSubmitButton"] button{
  width:100%% !important;border-radius:9px !important;padding:11px !important;
  border:1px solid rgba(56,189,248,0.45) !important;
  background:linear-gradient(180deg, rgba(14,165,233,0.30), rgba(14,165,233,0.16)) !important;
  color:#e0f2fe !important;font-size:11.5px !important;letter-spacing:2.4px !important;
  text-transform:uppercase !important;font-weight:600 !important;
  font-family:'Plus Jakarta Sans',sans-serif !important;
  box-shadow:0 6px 22px rgba(14,165,233,0.18) !important;
  transition:background .18s ease, border-color .18s ease !important;
}
.st-key-giris_panel .stButton button:hover,
.st-key-giris_panel [data-testid="stFormSubmitButton"] button:hover{
  background:linear-gradient(180deg, rgba(14,165,233,0.42), rgba(14,165,233,0.24)) !important;
  border-color:rgba(56,189,248,0.75) !important;
}
/* Form kabini gorunmez olsun — panel zaten cam kutuyu cizer */
.st-key-giris_panel [data-testid="stForm"]{
  border:none !important;padding:0 !important;background:transparent !important;
}
.st-key-giris_panel .g-kucuk{margin-top:16px;}
</style>
""" % arka, unsafe_allow_html=True)


# ═══════════════════════════════════════════════════════════════════════════
# GİRİŞ KAPISI
# ═══════════════════════════════════════════════════════════════════════════

def _ayarlar():
    """secrets'tan [giris] bilgilerini okur. (kullanici, parola_hash)"""
    import streamlit as st
    try:
        g = st.secrets.get("giris", {})
        return str(g.get("kullanici", "") or ""), str(g.get("parola_hash", "") or "")
    except Exception:
        return "", ""


def oturum_gecerli() -> bool:
    """Oturum açık ve süresi dolmamış mı?"""
    import streamlit as st
    if not st.session_state.get("giris_ok"):
        return False
    son = st.session_state.get("giris_son_hareket", 0)
    if time.time() - son > OTURUM_SAAT * 3600:
        st.session_state["giris_ok"] = False
        return False
    st.session_state["giris_son_hareket"] = time.time()
    return True


def _kurulum_ekrani():
    import streamlit as st
    _stil()
    _, orta, _ = st.columns([1, 2.4, 1])
    with orta:
        with st.container(key="giris_panel"):
            st.markdown("<div class='g-ust'>Acıbadem Sağlık Grubu</div>"
                        "<div class='g-mrk'>SYNAPSE</div>"
                        "<div class='g-alt'>Kurulum Gerekli</div>", unsafe_allow_html=True)
            st.markdown("---")
            st.warning("Giriş bilgileri tanımlı değil — portal güvenlik gereği kapalı.")
            st.markdown(
                "**Streamlit Cloud → Settings → Secrets** içine şunu ekleyin:\n\n"
                "```toml\n[giris]\nkullanici = \"acibadem\"\n"
                "parola_hash = \"<asagidaki komutun ciktisi>\"\n```\n\n"
                "Karma üretmek için bilgisayarınızda:\n\n"
                "```bash\npython merkez/giris.py \"secmek-istediginiz-parola\"\n```")
    st.stop()


def giris_kapisi():
    """Giriş yapılmamışsa giriş ekranını basar ve uygulamayı durdurur."""
    import streamlit as st

    kullanici_ad, parola_hash = _ayarlar()
    if not kullanici_ad or not parola_hash:
        _kurulum_ekrani()
        return

    # Teşhis ekranı — giriş yapılmış olsun olmasın çalışır, gizli değer göstermez
    try:
        _tani = str(st.query_params.get("tani", "") or "")
    except Exception:
        _tani = ""
    if _tani == "1":
        _tani_ekrani(parola_hash)
        st.stop()

    if oturum_gecerli():
        # KENDİNİ ONARAN ÇEREZ YAZIMI:
        # Çerez yalnızca "giriş sonrası ilk çalıştırmada" yazılsaydı, o tek
        # denemenin kaçırıldığı durumda (bileşen render edilmeden yeni bir
        # rerun olması gibi) oturum kalıcı olmaz ve kullanıcı her sayfa
        # yenilemesinde düşerdi. Bu yüzden çerez, sunucu onu göremediği her
        # çalıştırmada yeniden yazılır. İşlem fiyatı birkaç yüz bayt HTML'dir.
        if not _cerez_oku(CEREZ_AD):
            jeton = st.session_state.get("giris_jeton")
            if not jeton or not _jeton_gecerli(jeton, parola_hash):
                jeton = _jeton_uret(parola_hash, OTURUM_SAAT * 3600)
                st.session_state["giris_jeton"] = jeton
            _cerez_yaz(jeton, OTURUM_SAAT * 3600)
        return

    # ── Çıkış yapıldıysa ──
    # Silme cikis_yap() içinde yapılamaz: orada st.rerun() hemen çağrıldığı için
    # bileşenin JS'i çalışmaz. Bu yüzden silme buraya ertelenir.
    #
    # Bayrak, çerez GERÇEKTEN silinene kadar korunur. Tek seferde tüketilseydi
    # şu olurdu (ve oldu): CookieManager.delete() kendi rerun'unu tetikleyip
    # bu çalıştırmayı yarıda keser, bayrak tükenmiş olur, sonraki turda önbellekte
    # duran eski jeton okunup oturum GERİ AÇILIRDI — yani "Çıkış" çalışmazdı.
    if st.session_state.get("giris_cikis"):
        _cerez_sil()
        if not _cerez_oku(CEREZ_AD):
            st.session_state.pop("giris_cikis", None)
            st.session_state.pop("_cm_silindi", None)
        _giris_formu(kullanici_ad, parola_hash)
        st.stop()

    # ── Sayfa yenilendiyse: çerezdeki jetonla oturumu geri getir ──
    # NOT: Bu çağrı aynı zamanda CookieManager bileşenini render eder.
    jeton = _cerez_oku(CEREZ_AD)
    if jeton and _jeton_gecerli(jeton, parola_hash):
        st.session_state["giris_ok"] = True
        st.session_state["giris_jeton"] = jeton
        st.session_state["giris_son_hareket"] = time.time()
        return

    # CookieManager değeri İLK çalıştırmada döndürmez; bir tur sonra gelir.
    # Bu turda giriş formu basılırsa kullanıcı yazmaya başlar ve bileşen
    # cevap verince form sıfırlanır. Bu yüzden bir kez kısa bekleme yapılır.
    # Bileşen hiç cevap vermezse diye elle geçiş butonu bırakıldı — kimse
    # bekleme ekranında takılı kalmasın.
    if _cm() is not None and not st.session_state.get("_cerez_beklendi"):
        st.session_state["_cerez_beklendi"] = True
        _stil()
        with st.container(key="giris_panel"):
            st.markdown(
                "<div class='g-ust'>Acıbadem Sağlık Grubu</div>"
                "<div class='g-mrk'>SYNAPSE</div>"
                "<div class='g-alt'>Oturum denetleniyor…</div>",
                unsafe_allow_html=True)
            st.button("Giriş ekranına geç", key="_bekleme_atla")
        st.stop()

    _giris_formu(kullanici_ad, parola_hash)
    st.stop()


def _tani_ekrani(parola_hash: str):
    """?tani=1 ile açılan teşhis ekranı.

    Oturumun sayfa yenilemesinde neden düştüğünü yayın ortamında tespit etmek
    için. GİZLİ DEĞER GÖSTERMEZ — yalnızca 'var/yok' ve 'geçerli/geçersiz'
    bilgisi ile çerez ADLARI listelenir; jeton içeriği ve parola karması asla
    yazdırılmaz.
    """
    import streamlit as st
    st.markdown("### SYNAPSE — Oturum Teşhisi")

    try:
        surum = st.__version__
    except Exception:
        surum = "bilinmiyor"
    cookies_var = hasattr(st.context, "cookies")

    try:
        adlar = sorted(dict(st.context.cookies).keys())
    except Exception as e:
        adlar = []
        st.error("st.context.cookies okunamadi: %s" % e)

    # ── CookieManager durumu (asıl okuma yolu) ──
    try:
        import extra_streamlit_components as _stx
        stx_yuklendi = True
        stx_surum = getattr(_stx, "__version__", "surum bilgisi yok")
    except Exception as e:
        stx_yuklendi = False
        stx_surum = "%s: %s" % (type(e).__name__, e)

    cm = _cm()
    cm_cerezleri = "-"
    if cm is not None:
        try:
            cm_cerezleri = sorted((cm.get_all() or {}).keys())
        except Exception as e:
            cm_cerezleri = "get_all hatasi: %s" % e

    jeton = _cerez_oku(CEREZ_AD)

    st.write({
        "streamlit_surumu": surum,
        "extra_streamlit_components_yuklendi": stx_yuklendi,
        "extra_streamlit_components_surum": stx_surum,
        "CookieManager_olusturuldu": cm is not None,
        "CookieManager_hatasi": st.session_state.get("_cm_hata", "-"),
        "CookieManager_gordugu_cerezler": cm_cerezleri,
        "st.context.cookies_destekleniyor": cookies_var,
        "sunucunun_gordugu_cerez_adlari": adlar,
        "oturum_cerezi_geldi_mi": bool(jeton),
        "oturum_cerezi_gecerli_mi": bool(jeton) and _jeton_gecerli(jeton, parola_hash),
        "session_state_giris_ok": bool(st.session_state.get("giris_ok")),
    })

    st.caption(
        "Beklenen: streamlit 1.42+, destekleniyor=True ve giriş yaptıktan sonra "
        "sayfayı yenileyince listede 'synapse_oturum' görünmeli. Görünmüyorsa "
        "çerez tarayıcıya yazılamıyor demektir."
    )

    # ── TARAYICI TARAFI ÖLÇÜM ──
    # Sunucu çerezleri boş görüyorsa sorun ya yazmada ya da çerezin sunucuya
    # gönderilmemesinde. Bunu ayırmak için ölçüm bileşenin İÇİNDEN yapılır.
    st.markdown("---")
    st.markdown("**Tarayıcı tarafı** (bileşen iframe'inin gördüğü)")
    import streamlit.components.v1 as components
    components.html("""
    <div style="font-family:ui-monospace,Consolas,monospace;font-size:12px;
                color:#cbd5e1;background:#0b1220;border:1px solid #1e3a5f;
                border-radius:8px;padding:12px;line-height:1.75">
    <script>
      function yaz(k, v){
        document.write('<div><b style="color:#38bdf8">' + k + ':</b> ' + v + '</div>');
      }
      var adlar = document.cookie.split(';').map(function(c){
        return c.trim().split('=')[0];
      }).filter(function(x){ return x; });
      yaz('bilesen belgesinin cerez adlari', adlar.length ? adlar.join(', ') : '(bos)');
      yaz('synapse_oturum bilesende', document.cookie.indexOf('synapse_oturum=') > -1);

      var ustErisim = false, ustCerez = '(erisilemedi)';
      try{
        var d = window.parent.document;
        ustErisim = true;
        var ua = d.cookie.split(';').map(function(c){ return c.trim().split('=')[0]; })
                  .filter(function(x){ return x; });
        ustCerez = ua.length ? ua.join(', ') : '(bos)';
      }catch(e){ ustCerez = 'HATA: ' + e.name; }
      yaz('ust belgeye erisim', ustErisim);
      yaz('ust belgenin cerez adlari', ustCerez);

      var iframeIcinde = '(bilinmiyor)';
      try{ iframeIcinde = (window.parent.self !== window.parent.top); }catch(e){ iframeIcinde = 'ERISILEMEDI (capraz kaynak)'; }
      yaz('uygulama iframe icinde mi', iframeIcinde);

      try{ yaz('ust adres kaynagi', window.parent.location.origin); }
      catch(e){ yaz('ust adres kaynagi', 'ERISILEMEDI'); }

      try{ yaz('ancestorOrigins', JSON.stringify(Array.from(window.location.ancestorOrigins || []))); }
      catch(e){ yaz('ancestorOrigins', '-'); }
    </script>
    </div>
    """, height=220)
    st.info("Bu sayfa yalnızca teşhis içindir; adres satırından ?tani=1 "
            "kaldırılınca normal giriş ekranı gelir.")


def _giris_formu(kullanici_ad: str, parola_hash: str):
    """Giriş ekranını basar. (st.stop() çağırmaz — çağıran karar verir.)"""
    import streamlit as st
    _stil()
    # Dış sütun kullanılmaz; panel genişliğini CSS'teki max-width belirler
    # (dar ekranda sütun panelden ince kalıp tasarımı bozuyordu).
    with st.container(key="giris_panel"):
        sol, sag = st.columns([1.05, 1], gap="large")

        with sol:
            # Yalnızca sistemin çevrimiçi olduğu belirtilir.
            # Lokasyon/santral sayıları BİLİNÇLİ OLARAK gösterilmez:
            #   1) Giriş yapmamış ziyaretçiye kaç hastane izlendiği bilgisi sızar
            #   2) Giriş sayfasının her açılışında Supabase sorgusu (egress) oluşur
            st.markdown(
                "<div class='g-sol'>"
                "<div>"
                "<div class='g-ust'>Acıbadem Sağlık Grubu</div>"
                "<div class='g-mrk'>SYNAPSE</div>"
                "<div class='g-alt'>Operasyonel Zeka</div>"
                "</div>"
                "<div class='g-istat'><span><span class='g-nokta'></span>Sistem</span>"
                "<b>ÇEVRİMİÇİ</b></div>"
                "</div>",
                unsafe_allow_html=True)

        with sag:
            kilitli, kalan = _kilitli_mi()
            if kilitli:
                st.error("Çok fazla hatalı deneme. %d saniye sonra tekrar deneyin."
                         % kalan)
            else:
                with st.form("giris_formu", clear_on_submit=False):
                    ad = st.text_input("Kullanıcı Adı", key="giris_ad",
                                       placeholder="kullanici.adi")
                    pr = st.text_input("Parola", type="password", key="giris_pr",
                                       placeholder="••••••••••")
                    gonder = st.form_submit_button("Giriş Yap",
                                                   use_container_width=True)
                if gonder:
                    # Kullanıcı adı da zamanlama-güvenli karşılaştırılır
                    ad_ok = hmac.compare_digest(ad.strip(), kullanici_ad)
                    if ad_ok and parola_dogrula(pr, parola_hash):
                        _basari_kaydet()
                        st.session_state["giris_ok"] = True
                        st.session_state["giris_son_hareket"] = time.time()
                        # Jeton burada üretilir ama çerez BİR SONRAKİ
                        # çalıştırmada yazılır: st.rerun() hemen çağrıldığı
                        # için bileşenin JS'i çalışmaya fırsat bulamaz.
                        st.session_state["giris_jeton"] = _jeton_uret(
                            parola_hash, OTURUM_SAAT * 3600)
                        st.rerun()
                    else:
                        _hata_kaydet()
                        st.error("Kullanıcı adı veya parola hatalı.")
                st.markdown("<div class='g-kucuk'>Yetkisiz erişim girişimleri "
                            "kayıt altına alınır</div>", unsafe_allow_html=True)


def cikis_yap():
    """Oturumu kapatır.

    Çerez BURADA silinmez — çağıran taraf hemen st.rerun() yaptığı için
    silme bileşeninin JS'i çalışmaz ve çerez kalırdı (kullanıcı anında geri
    giriş yapmış olurdu). Bunun yerine bayrak bırakılır; çerez, giriş ekranının
    basıldığı bir sonraki çalıştırmada giris_kapisi() içinde silinir.
    """
    import streamlit as st
    # _cerez_beklendi BİLEREK sıfırlanmaz: sıfırlanırsa çıkıştan sonra
    # "Oturum denetleniyor…" ekranı bir kez daha görünür. O bekleme yalnızca
    # yeni bir sayfa açılışında (session_state zaten boşken) gereklidir.
    for k in ("giris_ok", "giris_son_hareket", "giris_jeton"):
        st.session_state.pop(k, None)
    st.session_state["giris_cikis"] = True


# ═══════════════════════════════════════════════════════════════════════════
# KOMUT SATIRI — parola karması üretici
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    # Parola argüman olarak da verilebilir, ama TERCİH EDİLEN yol gizli sorudur:
    # argüman verilirse parola terminal geçmişinde (PowerShell history, bash
    # .bash_history) düz metin olarak kalır.
    if len(sys.argv) >= 2:
        parola = sys.argv[1]
        print("\n[uyari] Parola komut satirinda verildi; terminal gecmisinde "
              "kalabilir.\n        Daha guvenlisi: argumansiz calistirmak.\n")
    else:
        import getpass
        parola = getpass.getpass("Belirlemek istediginiz parola (yazarken gorunmez): ")
        tekrar = getpass.getpass("Parolayi tekrar girin: ")
        if parola != tekrar:
            print("\nHATA: Parolalar ayni degil. Tekrar deneyin.")
            sys.exit(1)
        if len(parola) < 8:
            print("\nHATA: Parola en az 8 karakter olmali.")
            sys.exit(1)

    kullanici = input("Kullanici adi [acibadem]: ").strip() or "acibadem"

    print()
    print("=" * 62)
    print("Streamlit Cloud -> Settings -> Secrets icine ASAGIDAKI 3 SATIRI")
    print("EKLEYIN. Mevcut [supabase] ve [anthropic] bolumlerini SILMEYIN.")
    print("=" * 62)
    print()
    print("[giris]")
    print('kullanici = "%s"' % kullanici)
    print('parola_hash = "%s"' % parola_hash_uret(parola))
    print()
