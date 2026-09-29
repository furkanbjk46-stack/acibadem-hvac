# -*- coding: utf-8 -*-
"""
YÖNETİM — canlı sunucu ve veri durumu
=====================================

app_merkez.py bu dosyayı KENDİ globals()'ı içinde exec eder (lokasyon_detay
ile aynı desen); st, url, key, HASTANELER buradan doğrudan kullanılır.

Her açılışta CANLI okur, dosya üretmeye gerek yoktur. Giriş zaten
Synapse oturumuyla korunur (giris.py); bu sayfa ayrıca ölçüm ve alarm
mantığını izleme.py'den alır — statik şema sayfasıyla aynı eşikler.

Veritabanı ölçümleri synapse_kullanim() RPC'sinden gelir. RPC yalnızca
service_role'a açıksa ve portal anon anahtar kullanıyorsa o bölüm
"yetki yok" notuyla görünür; işletim durumu bölümleri yine çalışır.
"""

import json as _json
import os as _os
import sys as _sys
import urllib.error as _uhata
import urllib.request as _ureq
from datetime import datetime as _dt, timedelta as _td, timezone as _tz

_sys.path.insert(0, _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))))
import izleme as _IZ  # ölçüm + alarm mantığı (statik sayfayla ORTAK)
import tema as _T

_IST = _tz(_td(hours=3))


# ── Geri ──────────────────────────────────────────────────────────────────
if st.button("⬅ Geri", key="yonetim_geri"):
    st.session_state.pop("yonetim", None)
    st.rerun()

st.markdown(
    f"<div style='margin:2px 0 14px;'>"
    f"<div style='font-size:9px;color:{_T.SOLUK};letter-spacing:3.2px;"
    f"text-transform:uppercase;'>ACIBADEM SAĞLIK GRUBU — SYNAPSE</div>"
    f"<div style='font-size:26px;font-weight:650;letter-spacing:-0.02em;"
    f"color:{_T.MUREKKEP};margin-top:2px;'>Yönetim · Sunucu ve Veri Durumu</div>"
    f"<div style='font-size:11px;color:{_T.SOLUK};margin-top:2px;'>"
    f"Veriler her açılışta canlı okunur · {_dt.now(_IST).strftime('%d.%m.%Y %H:%M')}</div></div>",
    unsafe_allow_html=True)

_y1, _y2 = st.columns([1, 6])
with _y1:
    if st.button("🔄 Yenile", key="yonetim_yenile", use_container_width=True):
        st.cache_data.clear()
        st.rerun()


# ── Yardımcılar ───────────────────────────────────────────────────────────
def _servis_anahtari():
    """Varsa service_role anahtarı (ortam/secrets); yoksa portalın anon anahtarı."""
    cev = _os.environ.get("SUPABASE_SERVICE_KEY", "").strip()
    if cev:
        return cev, True
    # st.secrets'e dosya YOKKEN dokunmak ekrana "No secrets found" hatası
    # bastırıyor; bu yüzden önce dosyanın varlığına bakılır.
    for _yol in (_os.path.join(_os.path.expanduser("~"), ".streamlit", "secrets.toml"),
                 _os.path.join(_os.getcwd(), ".streamlit", "secrets.toml")):
        if _os.path.exists(_yol):
            try:
                _s = st.secrets.get("supabase", {})
                if _s.get("service_key"):
                    return str(_s["service_key"]), True
            except Exception:
                pass
            break
    return key, False


@st.cache_data(ttl=60, show_spinner=False)
def _rest(_url, _key, yol):
    """Tek seferlik REST okuması (60 sn önbellek — Yenile bunu temizler)."""
    try:
        istek = _ureq.Request(_url.rstrip("/") + "/rest/v1/" + yol,
                              headers={"apikey": _key, "Authorization": "Bearer " + _key})
        with _ureq.urlopen(istek, timeout=25) as c:
            return _json.load(c)
    except (_uhata.HTTPError, _uhata.URLError, ValueError):
        return []


@st.cache_data(ttl=60, show_spinner=False)
def _kullanim(_url, _key):
    return _IZ.kullanim_oku(_url, _key)


def _kutu(baslik, deger, alt, renk=None):
    return (f"<div style='flex:1;min-width:150px;background:{_T.YUZEY};"
            f"border:1px solid {_T.CERCEVE};border-radius:10px;padding:11px 13px;"
            f"box-shadow:{_T.GOLGE};'>"
            f"<div style='font-size:9px;letter-spacing:1.4px;text-transform:uppercase;"
            f"color:{_T.SOLUK};'>{baslik}</div>"
            f"<div style='font-size:19px;font-weight:650;margin-top:3px;"
            f"color:{renk or _T.MUREKKEP};'>{deger}</div>"
            f"<div style='font-size:10.5px;color:{_T.SOLUK};'>{alt}</div></div>")


def _serit(kutular):
    st.markdown("<div style='display:flex;gap:10px;flex-wrap:wrap;margin:10px 0 14px;'>"
                + "".join(kutular) + "</div>", unsafe_allow_html=True)


def _alarm_kutusu(sev, baslik, aciklama):
    renk = {"kritik": (_T.KRITIK_YAZI, "rgba(208,59,59,.07)", "rgba(208,59,59,.45)", "⛔"),
            "dikkat": (_T.UYARI_YAZI, "rgba(250,178,25,.10)", "rgba(250,178,25,.5)", "⚠️"),
            "iyi": (_T.IYI_YAZI, "rgba(12,163,12,.07)", "rgba(12,163,12,.4)", "✓")}[sev]
    return (f"<div style='background:{renk[1]};border:1px solid {renk[2]};border-radius:9px;"
            f"padding:10px 13px;margin-bottom:8px;'>"
            f"<div style='font-size:12.5px;font-weight:600;color:{renk[0]};'>"
            f"{renk[3]} {baslik}</div>"
            f"<div style='font-size:11.5px;color:{_T.MUREKKEP_2};margin-top:2px;'>"
            f"{aciklama}</div></div>")


def _yas(zaman_metni):
    """ISO zamandan 'kaç dakika/saat/gün önce' — (dakika, metin)."""
    if not zaman_metni:
        return None, "—"
    try:
        z = _dt.fromisoformat(str(zaman_metni).replace("Z", "+00:00"))
        if z.tzinfo is not None:
            z = z.astimezone(_IST).replace(tzinfo=None)
        dk = (_dt.now(_IST).replace(tzinfo=None) - z).total_seconds() / 60
    except (ValueError, TypeError):
        return None, "—"
    if dk < 60:
        return dk, "%.0f dk önce" % dk
    if dk < 1440:
        return dk, "%.1f saat önce" % (dk / 60)
    return dk, "%.0f gün önce" % (dk / 1440)


_anahtar, _servis_mi = _servis_anahtari()
_lim = _IZ.limitler()

# ══════════════════════════════════════════════════════════════════════════
# 1) SUNUCU / VERİTABANI
# ══════════════════════════════════════════════════════════════════════════
st.markdown(f"<div style='font-size:11px;font-weight:700;letter-spacing:2.2px;"
            f"text-transform:uppercase;color:{_T.LACIVERT};padding-bottom:8px;"
            f"border-bottom:2px solid {_T.LACIVERT};margin:18px 0 12px;'>"
            f"🖥️ Sunucu ve veritabanı</div>", unsafe_allow_html=True)

_k = _kullanim(url, _anahtar)
if not isinstance(_k, dict) or "veritabani_bayt" not in _k:
    st.warning(
        "Veritabanı ölçümü okunamadı. İki sebebi olabilir: (1) `merkez/izleme_kurulum.sql` "
        "henüz çalıştırılmadı, (2) fonksiyon yalnızca service_role'a açık ve portal anon "
        "anahtar kullanıyor. Çözüm: SQL dosyasındaki isteğe bağlı GRANT satırını çalıştırın "
        "ya da Streamlit secrets içine `[supabase] service_key` ekleyin."
        + ("" if _servis_mi else "  ·  Şu an **anon** anahtar kullanılıyor."))
else:
    _top, _kota, _oran = _IZ.disk_orani(_k, _lim)
    _s = _k.get("saglik") or {}
    # Eşik kararı izleme.py'de; burada yalnızca seviyeye renk verilir.
    _bar_renk = {"kritik": _T.KRITIK, "dikkat": _T.UYARI,
                 "iyi": _T.IYI}[_IZ.disk_seviye(_oran, _lim)]
    _serit([
        _kutu("Veritabanı", _IZ.boyut(_top),
              "%d GB kotanın %%%.1f'i" % (_lim["plan_disk_gb"], _oran), _bar_renk),
        _kutu("Önbellek isabeti", "%%%s" % (_s.get("onbellek_isabet_yuzde") or "—"),
              "yüksek olan iyi"),
        _kutu("Aktif bağlantı", "%s / %s" % (_s.get("aktif_baglanti", "—"),
                                             _s.get("azami_baglanti", "—")), "anlık"),
        _kutu("İşlem", _IZ.sayi(_s.get("islem_commit")),
              "commit · %s rollback" % _IZ.sayi(_s.get("islem_rollback"))),
    ])
    st.markdown(
        f"<div style='height:9px;border-radius:5px;background:{_T.YUZEY_2};overflow:hidden;"
        f"border:1px solid {_T.CERCEVE};margin-bottom:14px;'>"
        f"<div style='width:{min(100.0, _oran):.1f}%;height:100%;background:{_bar_renk};'></div>"
        f"</div>", unsafe_allow_html=True)

    _al = _IZ.alarmlar(_k, _lim)
    st.markdown("".join(_alarm_kutusu(*a) for a in _al), unsafe_allow_html=True)

    with st.expander("Tablo boyutları", expanded=False):
        import pandas as _pd
        _satir = [{"Tablo": t.get("tablo"),
                   "Toplam": _IZ.boyut(t.get("toplam_bayt")),
                   "Veri": _IZ.boyut(t.get("veri_bayt")),
                   "İndeks": _IZ.boyut(t.get("indeks_bayt")),
                   "Satır (tahmin)": _IZ.sayi(t.get("satir_tahmin")),
                   "Pay": "%%%.1f" % ((t.get("toplam_bayt") or 0) / _top * 100 if _top else 0)}
                  for t in _k.get("tablolar", [])]
        st.dataframe(_pd.DataFrame(_satir), hide_index=True, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════
# 2) LOKASYON BAĞLANTI VE VERİ AKIŞI
# ══════════════════════════════════════════════════════════════════════════
st.markdown(f"<div style='font-size:11px;font-weight:700;letter-spacing:2.2px;"
            f"text-transform:uppercase;color:{_T.LACIVERT};padding-bottom:8px;"
            f"border-bottom:2px solid {_T.LACIVERT};margin:22px 0 12px;'>"
            f"📡 Lokasyon bağlantısı ve veri akışı</div>", unsafe_allow_html=True)

_loklar = _rest(url, _anahtar, "lokasyonlar?select=lokasyon_id,isim,durum,versiyon,"
                               "ping_zamani,son_sync&order=lokasyon_id")
_son_veri = _rest(url, _anahtar,
                  "energy_data?select=lokasyon_id,Tarih&order=Tarih.desc&limit=400")
_son_tarih = {}
for _r in _son_veri if isinstance(_son_veri, list) else []:
    _son_tarih.setdefault(_r.get("lokasyon_id"), _r.get("Tarih"))

if not _loklar:
    st.info("Lokasyon kaydı okunamadı.")
else:
    _cevrimici = _cevrimdisi = 0
    _satirlar = []
    for _l in _loklar:
        _dk, _metin = _yas(_l.get("ping_zamani"))
        _online = _dk is not None and _dk < 10
        _cevrimici += 1 if _online else 0
        _cevrimdisi += 0 if _online else 1
        _t = _son_tarih.get(_l.get("lokasyon_id"))
        _gun = "—"
        if _t:
            try:
                _gun = (_dt.now(_IST).date() - _dt.fromisoformat(str(_t)[:10]).date()).days
                _gun = "bugün" if _gun == 0 else ("dün" if _gun == 1 else "%d gün önce" % _gun)
            except ValueError:
                _gun = str(_t)
        _satirlar.append({
            "Lokasyon": _l.get("isim") or _l.get("lokasyon_id"),
            "Bağlantı": "🟢 Çevrimiçi" if _online else "🔴 Çevrimdışı",
            "Son ping": _metin,
            "Sürüm": _l.get("versiyon") or "—",
            "Son veri": _t or "—",
            "Tazelik": _gun,
        })
    _serit([
        _kutu("Çevrimiçi", str(_cevrimici), "son 10 dk içinde ping",
              _T.IYI if _cevrimici else _T.SOLUK),
        _kutu("Çevrimdışı", str(_cevrimdisi), "ping gecikmiş",
              _T.KRITIK if _cevrimdisi else _T.SOLUK),
        _kutu("Kayıtlı lokasyon", str(len(_loklar)), "lokasyonlar tablosu"),
    ])
    import pandas as _pd2
    st.dataframe(_pd2.DataFrame(_satirlar), hide_index=True, use_container_width=True)

# ══════════════════════════════════════════════════════════════════════════
# 3) YAMA KUYRUĞU VE KOMUT TRAFİĞİ
# ══════════════════════════════════════════════════════════════════════════
st.markdown(f"<div style='font-size:11px;font-weight:700;letter-spacing:2.2px;"
            f"text-transform:uppercase;color:{_T.LACIVERT};padding-bottom:8px;"
            f"border-bottom:2px solid {_T.LACIVERT};margin:22px 0 12px;'>"
            f"📦 Yama kuyruğu ve komut trafiği</div>", unsafe_allow_html=True)

_yamalar = _rest(url, _anahtar,
                 "guncellemeler?select=versiyon,hedef,durum,created_at"
                 "&order=created_at.desc&limit=10")
_bekleyen = [y for y in _yamalar if y.get("durum") == "bekliyor"] if _yamalar else []

_sinir = (_dt.now(_IST) - _td(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
_komut = _rest(url, _anahtar,
               "komutlar?select=durum,olusturma&olusturma=gte.%s&limit=500" % _sinir)
_kom_hata = [k for k in _komut if str(k.get("durum", "")).lower() in ("hata", "dogrulanamadi")] \
    if _komut else []

_serit([
    _kutu("Bekleyen yama", str(len(_bekleyen)),
          "lokasyona henüz uygulanmadı",
          _T.UYARI if _bekleyen else _T.IYI),
    _kutu("24 saatte komut", str(len(_komut) if isinstance(_komut, list) else 0),
          "oto-set + elle gönderilen"),
    _kutu("Başarısız komut", str(len(_kom_hata)),
          "hata / doğrulanamadı", _T.KRITIK if _kom_hata else _T.IYI),
])

if _yamalar:
    import pandas as _pd3
    st.dataframe(_pd3.DataFrame([
        {"Versiyon": y.get("versiyon"), "Hedef": y.get("hedef"),
         "Durum": y.get("durum"), "Zaman": str(y.get("created_at", ""))[:16].replace("T", " ")}
        for y in _yamalar]), hide_index=True, use_container_width=True)

st.caption("Eşikler: merkez/configs/izleme_limitleri.json · Ölçüm fonksiyonu: "
           "merkez/izleme_kurulum.sql · Aynı mantık statik şema sayfasında da kullanılır.")
