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

# Sekmeler: 1) canlı sunucu / veri durumu  2) canlı SQL durumu  3) agent katmanları simülasyonu
_sekme_sunucu, _sekme_sql, _sekme_agent = st.tabs(
    ["🖥️ Sunucu ve veritabanı", "🗄️ SQL (canlı)", "🤖 Agent katmanları"])

with _sekme_sunucu:
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
                f"border:1px solid {_T.CERCEVE};border-radius:14px;padding:11px 13px;"
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
            "Veritabanı ölçümü (`synapse_kullanim`) okunamadı. Ölçüm fonksiyonu yalnızca "
            "service_role anahtarına açıktır; sunucudaki `merkez/.streamlit/secrets.toml` "
            "dosyasında `[supabase] service_key` tanımlı olmalı."
            + ("" if _servis_mi else "  ·  Şu an **anon** anahtar kullanılıyor."))
    else:
        _top, _kota, _oran = _IZ.disk_orani(_k, _lim)
        _s = _k.get("saglik") or {}
        # Eşik kararı izleme.py'de; burada yalnızca seviyeye renk verilir.
        _bar_renk = {"kritik": _T.KRITIK, "dikkat": _T.UYARI,
                     "iyi": _T.IYI}[_IZ.disk_seviye(_oran, _lim)]
        _serit([
            _kutu("Veritabanı", _IZ.boyut(_top),
                  "%d GB sınırın %%%.1f'i" % (_lim["plan_disk_gb"], _oran), _bar_renk),
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

    # komutlar.created_at UTC tutulur; sınır da UTC verilir. (Eskiden var olmayan
    # 'olusturma' sütunu sorgulanıyordu: istek 400 dönüyor, kutular hep 0 kalıyordu.)
    _sinir = (_dt.now(_tz.utc) - _td(hours=24)).strftime("%Y-%m-%dT%H:%M:%SZ")
    _komut = _rest(url, _anahtar,
                   "komutlar?select=durum,created_at&created_at=gte.%s&limit=1000" % _sinir)
    _kom_hata = [k for k in _komut if str(k.get("durum", "")).lower()
                 in ("hata", "dogrulanamadi", "suresi_doldu")] if _komut else []

    _serit([
        _kutu("Bekleyen yama", str(len(_bekleyen)),
              "lokasyona henüz uygulanmadı",
              _T.UYARI if _bekleyen else _T.IYI),
        _kutu("24 saatte komut", str(len(_komut) if isinstance(_komut, list) else 0),
              "oto-set + elle gönderilen"),
        _kutu("Başarısız komut", str(len(_kom_hata)),
              "hata / doğrulanamadı / süresi doldu", _T.KRITIK if _kom_hata else _T.IYI),
    ])

    if _yamalar:
        import pandas as _pd3
        import sql_durumu as _SQ0

        def _ist_saat(m):
            z = _SQ0.zaman(m)
            return z.strftime("%d.%m.%Y %H:%M") if z else "—"
        st.dataframe(_pd3.DataFrame([
            {"Versiyon": y.get("versiyon"), "Hedef": y.get("hedef"),
             "Durum": y.get("durum"), "Zaman": _ist_saat(y.get("created_at"))}
            for y in _yamalar]), hide_index=True, use_container_width=True)

    st.caption("Eşikler: merkez/configs/izleme_limitleri.json · Ölçüm fonksiyonu: "
               "synapse_kullanim() · Saatler İstanbul saatidir.")

with _sekme_sql:
    import sql_durumu as _SQ

    def _sql_kutu(baslik, deger, alt, renk=None):
        return (f"<div style='flex:1;min-width:150px;background:{_T.YUZEY};"
                f"border:1px solid {_T.CERCEVE};border-radius:14px;padding:11px 13px;"
                f"box-shadow:{_T.GOLGE};'>"
                f"<div style='font-size:9px;letter-spacing:1.4px;text-transform:uppercase;"
                f"color:{_T.SOLUK};'>{baslik}</div>"
                f"<div style='font-size:19px;font-weight:650;margin-top:3px;"
                f"color:{renk or _T.MUREKKEP};'>{deger}</div>"
                f"<div style='font-size:10.5px;color:{_T.SOLUK};'>{alt}</div></div>")

    def _sql_alarm(sev, baslik, aciklama):
        renk = {"kritik": (_T.KRITIK_YAZI, "rgba(208,59,59,.07)", "rgba(208,59,59,.45)", "⛔"),
                "dikkat": (_T.UYARI_YAZI, "rgba(250,178,25,.10)", "rgba(250,178,25,.5)", "⚠️"),
                "iyi": (_T.IYI_YAZI, "rgba(12,163,12,.07)", "rgba(12,163,12,.4)", "✓")}[sev]
        return (f"<div style='background:{renk[1]};border:1px solid {renk[2]};border-radius:9px;"
                f"padding:10px 13px;margin-bottom:8px;'>"
                f"<div style='font-size:12.5px;font-weight:600;color:{renk[0]};'>"
                f"{renk[3]} {baslik}</div>"
                f"<div style='font-size:11.5px;color:{_T.MUREKKEP_2};margin-top:2px;'>"
                f"{aciklama}</div></div>")

    _sql_anahtar = _anahtar          # Sunucu sekmesinde seçilen anahtar (service_role varsa o)

    # Yalnız bu bölüm 30 sn'de bir kendini yeniler; sayfanın geri kalanı yeniden çizilmez.
    @st.fragment(run_every="30s")
    def _sql_canli():
        import pandas as _pds
        _v, _ms, _hata = _SQ.oku(url, _sql_anahtar)
        _simdi = _dt.now(_IST)
        st.markdown(
            f"<div style='font-size:11px;color:{_T.SOLUK};margin:4px 0 2px;'>"
            f"<span style='display:inline-block;width:8px;height:8px;border-radius:50%;"
            f"background:{_T.IYI if _v else _T.KRITIK};margin-right:6px;'></span>"
            f"Canlı · 30 sn'de bir yenilenir · son ölçüm {_simdi.strftime('%H:%M:%S')}</div>",
            unsafe_allow_html=True)
        if _v is None:
            if _hata == "fonksiyon_yok":
                st.info("SQL durum ölçümü henüz kurulmamış. "
                        "`veritabani/degisiklikler/001_sql_durumu_olcumu.sql` uygulanınca görünür.")
            elif _hata == "yetki_yok":
                st.warning("Ölçüm fonksiyonu yalnızca service_role anahtarına açık; "
                           "portal şu an başka bir anahtarla bağlı.")
            else:
                st.error("Veritabanına ulaşılamadı (%s)." % _hata)
            return

        _yed = _SQ.yedekler()
        _dsk = _SQ.disk()
        _top_b, _b_parca = _SQ.baglanti_ozeti(_v)
        _ist = _v.get("istatistik") or {}
        _son_yedek = _yed[0] if _yed else None
        _kutular = [
            _sql_kutu("PostgreSQL", str(_v.get("surum", "—")).split(" ")[0],
                      "açık: " + _SQ.calisma_suresi(_v.get("baslangic"), _simdi)),
            _sql_kutu("API yanıtı", "%d ms" % _ms if _ms is not None else "—",
                      "PostgREST, bu ölçümün süresi",
                      _T.IYI if (_ms or 0) < 1000 else _T.UYARI),
            _sql_kutu("Bağlantı", str(_top_b), _b_parca or "—"),
            _sql_kutu("Bekleyen kilit", str(_v.get("bekleyen_kilit", 0)),
                      "%s deadlock · %s rollback" % (_ist.get("kilitlenme", 0),
                                                     _IZ.sayi(_ist.get("rollback"))),
                      _T.UYARI if _v.get("bekleyen_kilit") else _T.IYI),
            _sql_kutu("Gece yedeği",
                      _son_yedek["zaman"].strftime("%d.%m %H:%M") if _son_yedek else "—",
                      ("%s · %d dosya" % (_IZ.boyut(_son_yedek["bayt"]), len(_yed)))
                      if _son_yedek else "/opt/Backup okunamadı"),
            _sql_kutu("Sunucu diski",
                      ("%%%.0f" % (_dsk[0] / _dsk[1] * 100)) if _dsk else "—",
                      ("%s boş / %s" % (_IZ.boyut(_dsk[2]), _IZ.boyut(_dsk[1]))) if _dsk else "—"),
        ]
        st.markdown("<div style='display:flex;gap:10px;flex-wrap:wrap;margin:10px 0 14px;'>"
                    + "".join(_kutular) + "</div>", unsafe_allow_html=True)

        st.markdown("".join(_sql_alarm(*a) for a in
                            _SQ.uyarilar(_v, _yed if _os.path.isdir(_SQ.YEDEK_KLASORU) else None,
                                         _dsk, _simdi)),
                    unsafe_allow_html=True)

        st.markdown(f"<div style='font-size:12px;font-weight:650;color:{_T.LACIVERT};"
                    f"margin:14px 0 6px;'>Tablolar · son kayda göre</div>", unsafe_allow_html=True)
        st.dataframe(_pds.DataFrame(_SQ.tablo_satirlari(_v, _simdi)), hide_index=True,
                     use_container_width=True)
        st.caption("Eklenen / Güncellenen / Silinen: istatistik sıfırlandığından beri toplam. "
                   "Ölü satır: güncelleme/silme sonrası temizlenmeyi bekleyen satırlar; "
                   "veritabanı kendiliğinden temizler (Son bakım).")

        _sut = _v.get("energy_data_sutunlari") or []
        with st.expander("energy_data sütunları (%d) — yeni sayaç sütunu buraya eklenir" % len(_sut)):
            st.dataframe(_pds.DataFrame([{"#": i + 1, "Sütun": s.get("ad"), "Tür": s.get("tur")}
                                         for i, s in enumerate(_sut)]),
                         hide_index=True, use_container_width=True, height=320)
            st.caption("Sahadaki energy_data.csv sütun adları bunlarla birebir aynı olmalı. "
                       "Yeni sütun önce veritabanına eklenir (veritabani/degisiklikler/), "
                       "sonra sahaya yama gider.")

        _gec = _v.get("sema_gecmisi") or []
        with st.expander("Şema değişiklik geçmişi (%d)" % len(_gec)):
            if _gec:
                st.dataframe(_pds.DataFrame([
                    {"Dosya": g.get("dosya"), "Açıklama": g.get("ozet"),
                     "Uygulayan": g.get("uygulayan"),
                     "Zaman": (_SQ.zaman(g.get("uygulandi")) or _simdi).strftime("%d.%m.%Y %H:%M")}
                    for g in _gec]), hide_index=True, use_container_width=True)
            else:
                st.caption("Henüz kayıtlı değişiklik yok.")
            st.caption("Değişiklikler repodaki veritabani/degisiklikler/NNN_*.sql dosyalarıdır; "
                       "veritabani/sema_degistir.py ile yedek alınarak uygulanır.")

    _sql_canli()

with _sekme_agent:
    # CANLI: tasarım sayfası (merkez/sunum/agent_katmanlari.html) agent tablolarından gelen
    # veriyle canlı modda çizilir. Altta iş emri düğmeleri, en altta tasarım simülasyonu.
    import streamlit.components.v1 as _bilesen
    import agent_gorunum as _AG
    import ust_agent as _UA

    def _agent_oku(yol):
        """Agent tabloları; tablo yoksa / yetki yoksa None (önbelleksiz: canlı)."""
        try:
            _r = _ureq.Request(url.rstrip("/") + "/rest/v1/" + yol,
                               headers={"apikey": _anahtar, "Authorization": "Bearer " + _anahtar})
            with _ureq.urlopen(_r, timeout=20) as _c:
                return _json.load(_c)
        except Exception:
            return None

    _burasi = _os.path.dirname(_os.path.abspath(__file__))
    _sablon = None
    for _aday in (_burasi, _os.path.dirname(_burasi)):
        try:
            with open(_os.path.join(_aday, "sunum", "agent_katmanlari.html"), encoding="utf-8") as _f:
                _sablon = _f.read()
            break
        except OSError:
            continue

    @st.fragment(run_every="60s")
    def _agent_canli():
        _turlar = _agent_oku("agent_turlar?select=*")
        _bulgular = _agent_oku("agent_bulgular?select=*&durum=eq.acik")
        _sinir_k = (_dt.now(_tz.utc) - _td(days=14)).strftime("%Y-%m-%dT%H:%M:%SZ")
        _acik = _agent_oku("agent_raporlar?select=*&durum=neq.kapandi&order=olusturma.desc")
        _kapali = _agent_oku("agent_raporlar?select=*&durum=eq.kapandi&kapanma=gte.%s"
                             "&order=kapanma.desc&limit=20" % _sinir_k)
        if None in (_turlar, _bulgular, _acik, _kapali):
            st.warning("Agent tabloları okunamadı. `veritabani/degisiklikler/002_agent_tablolari.sql` "
                       "uygulanmış olmalı ve portal service_role anahtarıyla bağlı olmalı.")
            return
        _v = _AG.gorunum(_turlar, _bulgular, _acik + _kapali, ust_durum=_UA.arka_plan_durumu())
        _ay1, _ay2 = st.columns([1, 6])
        with _ay1:
            # Tıklama yalnızca bu bölümü (şema + iş emirleri) yeniden okur; sayfa yenilenmez.
            if st.button("🔄 Yenile", key="ag_yenile", use_container_width=True):
                st.rerun(scope="fragment")
        with _ay2:
            st.caption("Canlı · dakikada bir kendiliğinden yenilenir · son okuma %s" % _v["zaman"])
        if _sablon:
            # Yükseklik sayfanın içindeki betikle içeriğe göre ayarlanır (iç kaydırma yok);
            # buradaki değer yalnızca ilk çizim içindir.
            _bilesen.html(_AG.sayfa(_sablon, _v), height=1700, scrolling=False)
        else:
            st.info("Agent katmanları sayfası bulunamadı (merkez/sunum/agent_katmanlari.html).")

        # ── İş emri düğmeleri (sürüm 1: düzelten sensin) ──
        st.markdown(f"<div style='font-size:12px;font-weight:650;color:{_T.LACIVERT};margin:10px 0 4px;'>"
                    f"İş emri işlemleri</div>", unsafe_allow_html=True)
        if not _acik:
            st.caption("Açık iş emri yok.")
            return
        _secenek = {"%s · %s · %s" % (r.get("rapor_no"), _AG.DURUM_METIN.get(r.get("durum"), r.get("durum")),
                                      r.get("baslik")): r for r in _acik}
        _sec = st.selectbox("İş emri", list(_secenek), key="ag_rapor_sec")
        _not = st.text_input("Not (isteğe bağlı: ne yapıldı, hangi commit/yama)", key="ag_rapor_not")
        _testler = st.text_input("Yama öncesi koşan testler (isteğe bağlı, ör. test_enerji_agent 57/57)",
                                 key="ag_rapor_testler")
        _b1, _b2, _b3 = st.columns(3)
        _eylem = None
        with _b1:
            if st.button("🔧 Düzeltmeye başladım", use_container_width=True, key="ag_baslat"):
                _eylem = "baslat"
        with _b2:
            if st.button("📦 Düzeltildi, yama gönderildi", use_container_width=True, key="ag_yama"):
                _eylem = "yama"
        with _b3:
            if st.button("✖ Gereksiz, kapat", use_container_width=True, key="ag_kapat"):
                _eylem = "kapat"
        st.caption("Yama gönderildi dendikten sonra sunucuda test koşmaz: Maslak'taki agent aynı kontrolü "
                   "tekrar çalıştırır, sorun görülmezse iş emri kendiliğinden kapanır. Sorun doğrulama sınırından "
                   "sonra hâlâ görülürse 'düzeltme tutmadı' diye yeniden açılır. Sınır kontrole göre: anlık "
                   "kontroller %d dk, sayaçlar ertesi gece 00:30 (23:59 okuması), günlük veri kontrolleri "
                   "ertesi 09:00." % _UA.DOGRULAMA_PAYI_DK)
        if _eylem:
            _r = _secenek[_sec]
            try:                                     # tek kullanıcılı giriş: ayardaki kullanıcı adı
                import giris as _gr
                _kim = _gr._ayarlar()[0] or "kullanıcı"
            except Exception:
                _kim = "kullanıcı"
            try:
                _UA.Db(url, _anahtar).degistir("agent_raporlar", "id=eq.%d" % int(_r["id"]),
                                               _UA.eylem_alanlari(_r, _eylem, _kim, _not, testler=_testler))
                st.success("%s güncellendi." % _r.get("rapor_no"))
                st.rerun(scope="fragment")
            except Exception as _ee:
                st.error("Güncellenemedi: %s" % _ee)

    _agent_canli()

    with st.expander("Tasarım simülasyonu (örnek senaryolar)"):
        if _sablon:
            st.caption("Tasarım simülasyonu · örnek senaryolar ve örnek raporlar · "
                       "gerçek arıza ya da canlı veri değildir.")
            _bilesen.html(_sablon.replace('<html lang="tr">', '<html lang="tr" data-tema="acik">', 1),
                          height=1900, scrolling=True)
