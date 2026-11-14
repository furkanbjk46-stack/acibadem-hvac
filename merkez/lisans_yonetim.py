# -*- coding: utf-8 -*-
"""
LİSANS YÖNETİMİ — Synapse → Yönetim → Lisanslar (14.11.2026, veritabani 008_lisans_talepleri)
==========================================================================================

Lisansı olmayan lokasyon PC'si (yeni kurulum) merkeze kendisi talep bırakır: makine kimliği,
lokasyon, bilgisayar adı. Burada "Onayla" denince lisans satırı aktif açılır; PC dakikada bir
yeniden sorduğu için program kendiliğinden başlar. Lisans pasife alınabilir / yeniden açılabilir.

Onay, ret ve pasife alma LİSANS ONAY ŞİFRESİ ister: Synapse ile lokasyonlar aynı ortak anahtarı
kullandığından, şifre olmasa bir lokasyon kendi lisansını onaylayabilirdi. Şifre veritabanında yalnız
bcrypt özeti olarak durur (araclar/lisans_onay_sifresi.py belirler); doğrulamayı veritabanı yapar.
"""
import html
import json
import urllib.error
import urllib.request

KARAR_MESAJ = {
    "onaylandi": ("ok", "Lisans onaylandı — PC en geç 1-2 dk içinde kendiliğinden açılır."),
    "reddedildi": ("ok", "Talep reddedildi."),
    "aktif": ("ok", "Lisans etkinleştirildi."),
    "pasif": ("ok", "Lisans pasife alındı — program o PC'de bir sonraki açılışta başlamaz."),
    "sifre_yanlis": ("hata", "Lisans onay şifresi yanlış."),
    "sifre_yok": ("hata", "Lisans onay şifresi henüz belirlenmemiş (araclar/lisans_onay_sifresi.py)."),
    "cok_deneme": ("hata", "Çok sayıda hatalı şifre denemesi — 15 dakika sonra tekrar deneyin."),
    "talep_yok": ("hata", "Talep bulunamadı (silinmiş olabilir); sayfayı yenileyin."),
    "lisans_yok": ("hata", "Lisans bulunamadı; sayfayı yenileyin."),
}
DURUM_ADI = {"bekliyor": "Onay bekliyor", "onaylandi": "Onaylandı", "reddedildi": "Reddedildi"}


def _istek(url, key, yol, veri=None, zaman=20):
    istek = urllib.request.Request(
        url.rstrip("/") + "/rest/v1/" + yol,
        data=None if veri is None else json.dumps(veri).encode("utf-8"),
        headers={"apikey": key, "Authorization": "Bearer " + key, "Content-Type": "application/json"},
        method="GET" if veri is None else "POST")
    with urllib.request.urlopen(istek, timeout=zaman) as c:
        return json.load(c)


def talepleri_oku(url, key):
    """Lisans talepleri (yeniden eskiye); tablo yoksa (008 uygulanmamış) / hata → None."""
    try:
        return _istek(url, key, "lisans_talepleri?select=*&order=son_talep.desc")
    except (urllib.error.URLError, ValueError, OSError):
        return None


def lisanslari_oku(url, key):
    try:
        return _istek(url, key, "lisanslar?select=id,lokasyon_id,makine_id,makine_adi,aktif,olusturma"
                                "&order=lokasyon_id.asc,olusturma.asc")
    except (urllib.error.URLError, ValueError, OSError):
        return None


def _rpc(url, key, ad, veri):
    try:
        sonuc = _istek(url, key, "rpc/" + ad, veri, zaman=30)
    except urllib.error.HTTPError as e:
        return "hata: HTTP %s" % e.code
    except (urllib.error.URLError, ValueError, OSError) as e:
        return "hata: %s" % e
    return sonuc if isinstance(sonuc, str) else "hata: beklenmeyen cevap"


def karar_ver(url, key, talep_id, karar, sifre, notu=None):
    """karar: 'onayla' | 'reddet'. Dönüş: KARAR_MESAJ anahtarı ya da 'hata: ...'."""
    return _rpc(url, key, "lisans_karar", {"p_talep": talep_id, "p_karar": karar, "p_sifre": sifre or "",
                                           "p_not": notu or None})


def aktiflik(url, key, lisans_id, aktif, sifre):
    return _rpc(url, key, "lisans_aktiflik", {"p_lisans": lisans_id, "p_aktif": bool(aktif), "p_sifre": sifre or ""})


def mesaj(kod):
    """(tür, metin) — tür: ok | hata."""
    return KARAR_MESAJ.get(kod, ("hata", "İşlem yapılamadı: %s" % kod))


def bekleyenler(talepler):
    return [t for t in talepler or [] if t.get("durum") == "bekliyor"]


def canli_uyarilar(talepler, hastaneler):
    """{lokasyon_id: [("y", metin)]} — ana sayfadaki Canlı Uyarılar için bekleyen talepler."""
    cikti = {}
    for t in bekleyenler(talepler):
        lok = t.get("lokasyon_id") or "?"
        isim = (hastaneler.get(lok) or {}).get("kisa") or lok
        cikti.setdefault(lok, []).append(       # metin ana sayfada HTML içine basılır: PC'den gelen ad kaçışlanır
            ("y", html.escape("🔑 %s: yeni PC lisans onayı bekliyor (%s) — Yönetim → Lisanslar"
                              % (isim, t.get("makine_adi") or (t.get("makine_id") or "")[:8]))))
    return cikti


def _zaman(s):
    s = str(s or "")
    return (s[8:10] + "." + s[5:7] + "." + s[:4] + " " + s[11:16]) if len(s) >= 16 else s


def ciz(st, url, key, hastaneler):
    """Yönetim → Lisanslar sekmesi."""
    talepler = talepleri_oku(url, key)
    lisanslar = lisanslari_oku(url, key) or []
    if talepler is None:
        st.info("Lisans talepleri tablosu bu sunucuda henüz yok (veritabanı değişikliği 008 uygulanmamış).")
        talepler = []

    sonuc = st.session_state.pop("lisans_sonuc", None)
    if sonuc:
        (st.success if sonuc[0] == "ok" else st.error)(sonuc[1])

    st.caption("Yeni kurulan lokasyon PC'si lisansı yoksa buraya kendisi talep bırakır (makine kimliği, "
               "lokasyon, bilgisayar adı). Onaylanınca PC 1-2 dk içinde kendiliğinden açılır. Onay, ret ve "
               "pasife alma **lisans onay şifresi** ister.")
    sifre = st.text_input("Lisans onay şifresi", type="password", key="lisans_onay_sifresi",
                          help="Veritabanında yalnız özeti durur; araclar/lisans_onay_sifresi.py ile belirlenir.")

    def _isle(kod):
        st.session_state["lisans_sonuc"] = mesaj(kod)
        st.rerun()

    bek = bekleyenler(talepler)
    st.markdown("#### Bekleyen talepler (%d)" % len(bek))
    if not bek:
        st.caption("Onay bekleyen talep yok.")
    for t in bek:
        lok = t.get("lokasyon_id")
        isim = (hastaneler.get(lok) or {}).get("isim")
        with st.container(border=True):
            st.markdown("**%s** — %s · `%s`" % (isim or lok, t.get("makine_adi") or "adsız PC", t.get("makine_id")))
            ek = []
            if not isim:
                ek.append("⚠️ '%s' Synapse'in hastane listesinde yok — lokasyon kimliği yanlış yazılmış olabilir"
                          % lok)
            st.caption("İlk talep %s · son %s · %s kez soruldu%s%s" % (
                _zaman(t.get("ilk_talep")), _zaman(t.get("son_talep")), t.get("talep_sayisi") or 1,
                (" · sürüm " + t["surum"]) if t.get("surum") else "", (" · " + " · ".join(ek)) if ek else ""))
            k1, k2, _ = st.columns([1, 1, 4])
            if k1.button("✅ Onayla", key="lis_onay_%s" % t["id"], type="primary", use_container_width=True):
                _isle(karar_ver(url, key, t["id"], "onayla", sifre))
            if k2.button("✖ Reddet", key="lis_ret_%s" % t["id"], use_container_width=True):
                _isle(karar_ver(url, key, t["id"], "reddet", sifre))

    st.markdown("#### Lisanslar (%d)" % len(lisanslar))
    if not lisanslar:
        st.caption("Lisans kaydı yok ya da okunamadı.")
    for l in lisanslar:
        lok = l.get("lokasyon_id")
        isim = (hastaneler.get(lok) or {}).get("isim") or lok
        c1, c2 = st.columns([5, 1])
        c1.markdown("%s **%s** — %s · `%s` · %s" % (
            "🟢" if l.get("aktif") else "⚪", isim, l.get("makine_adi") or "adsız PC",
            str(l.get("makine_id") or "")[:13] + "…", "aktif" if l.get("aktif") else "pasif"))
        if l.get("aktif"):
            if c2.button("Pasife al", key="lis_pasif_%s" % l["id"], use_container_width=True):
                _isle(aktiflik(url, key, l["id"], False, sifre))
        elif c2.button("Etkinleştir", key="lis_aktif_%s" % l["id"], use_container_width=True):
            _isle(aktiflik(url, key, l["id"], True, sifre))

    gecmis = [t for t in talepler if t.get("durum") != "bekliyor"]
    if gecmis:
        with st.expander("Karara bağlanmış talepler (%d)" % len(gecmis)):
            for t in gecmis:
                st.markdown("- %s · %s · %s — **%s** (%s)" % (
                    t.get("lokasyon_id"), t.get("makine_adi") or "adsız PC", str(t.get("makine_id"))[:13] + "…",
                    DURUM_ADI.get(t.get("durum"), t.get("durum")), _zaman(t.get("karar_zamani"))))
                if t.get("durum") == "reddedildi":
                    if st.button("Yine de onayla", key="lis_geri_%s" % t["id"]):
                        _isle(karar_ver(url, key, t["id"], "onayla", sifre))
