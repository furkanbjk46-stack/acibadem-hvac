# -*- coding: utf-8 -*-
"""
LOKASYON DONANIMI PANELİ — Enerji portalı sekmesi (Streamlit). Çekirdek: donanim.py.

İki yol, aynı akış:
  • Excel: boş şablonu / mevcut listeyi indir → doldur → yükle
  • Panel: tabloda satır ekle / düzenle / sil
  → Kontrol (hata varsa kayıt yok) → önizleme (eklenen / silinen / değişen) → onay → yedek + kayıt
  → program yeniden başlar (analizör listesi açılışta okunur).

Şifre: ilk açılışta belirlenir; yalnız bu bilgisayarda özet olarak durur (ayar/panel_sifresi.json,
merkeze gitmez). Unutulursa o dosya silinip yeniden belirlenir.
"""
import os
import time
from datetime import datetime

import pandas as pd
import streamlit as st

import donanim as D

BURASI = os.path.dirname(os.path.abspath(__file__))
_ON = "don_"          # session_state anahtar öneki


def _ss():
    return st.session_state


def _df(tur, satirlar, karsilik=None):
    sutunlar = D.SUTUNLAR[tur]
    df = pd.DataFrame([{a: s.get(a) for a in sutunlar} for s in satirlar], columns=sutunlar)
    for a in sutunlar:
        if a in D.TAMSAYI:
            df[a] = pd.to_numeric(df[a], errors="coerce").astype("Int64")
        else:
            df[a] = df[a].astype(object).where(df[a].notna(), "")     # boş hücre "None" yazmasın
    if tur == "bms" and karsilik is not None:
        df["Sistem karşılığı"] = [karsilik.get(s.get("Point Name"))
                                  or ("oto-set yazar" if s.get("Durum") == D.YAZILABILIR else None)
                                  for s in satirlar]
    return df


def _sutun_ayari(tur):
    cc = st.column_config
    if tur == "analizorler":
        return {
            "AD": cc.TextColumn("AD", required=True, help="Tekil ve kalıcı: geçmiş veri bu adla tutulur"),
            "IP ADRESI": cc.TextColumn("IP ADRESI", help="Boşsa sayaç bekleyen listede durur, okunmaz"),
            "BİNA": cc.TextColumn("BİNA"),
            "MARKA": cc.SelectboxColumn("MARKA", options=list(D.MARKALAR)),
            "TÜR": cc.SelectboxColumn("TÜR", options=list(D.TURLER),
                                      help="trafo · sebeke · uretim (kojen) · chiller · alt_sayac (MCC, kule…) · "
                                           "kontrol (okunur, hiçbir toplama girmez)"),
            "KRİTİK": cc.SelectboxColumn("KRİTİK", options=list(D.EVET_HAYIR),
                                         help="Evet: okunamazsa agent kritik sorun sayar"),
            "NOT": cc.TextColumn("NOT", width="large"),
        }
    tam = {a: cc.NumberColumn(a, step=1, format="%d", min_value=0) for a in D.TAMSAYI}
    if tur == "bms":
        return dict(tam, **{
            "Gateway IP": cc.TextColumn("Gateway IP"),
            "MAC (DADR)": cc.TextColumn("MAC (DADR)", help="0x ile onaltılı, ör. 0x011C"),
            "Point Name": cc.TextColumn("Point Name", width="medium", required=True),
            "Durum": cc.SelectboxColumn("Durum", options=list(D.DURUMLAR), required=True,
                                        help="okunan değer = program okur · yazılabilir değer = oto-set yazar "
                                             "(bu panel değiştirmez) · okunacak = henüz okunmuyor"),
            "Sistem karşılığı": cc.TextColumn("Sistem karşılığı", disabled=True, width="medium"),
        })
    return dict(tam, **{
        "Bina": cc.TextColumn("Bina", required=True),
        "Santral": cc.TextColumn("Santral", required=True),
        "Nokta Tipi": cc.SelectboxColumn("Nokta Tipi", options=list(D.NOKTA_TIPLERI), required=True),
        "Gateway IP": cc.TextColumn("Gateway IP"),
        "MAC (DADR)": cc.TextColumn("MAC (DADR)", help="0x ile onaltılı, ör. 0x0101"),
    })


def _kayitlar(df, tur):
    return [{a: r.get(a) for a in D.SUTUNLAR[tur]} for r in df.to_dict("records")]


def _sifre_kapisi(base) -> bool:
    ss = _ss()
    if ss.get(_ON + "acik"):
        return True
    if not D.sifre_var(base):
        st.info("Panel bu bilgisayarda ilk kez açılıyor — bir **panel şifresi** belirleyin. Şifre yalnız bu "
                "bilgisayarda (özet olarak) durur, merkeze gönderilmez. Unutulursa `ayar/panel_sifresi.json` "
                "silinip yeniden belirlenir.")
        with st.form(_ON + "sifre_belirle"):
            s1 = st.text_input("Yeni şifre (en az 6 karakter)", type="password")
            s2 = st.text_input("Şifre tekrar", type="password")
            if st.form_submit_button("Şifreyi belirle ve paneli aç"):
                if s1 != s2:
                    st.error("İki şifre aynı değil.")
                else:
                    try:
                        D.sifre_belirle(s1, base)
                        ss[_ON + "acik"] = True
                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))
        return False
    st.caption("Analizör ve BMS (BACnet) listeleri bu panelden değiştirilir. Değişiklik programın okuduğu "
               "ayar dosyalarına yazılır; panel şifrelidir.")
    with st.form(_ON + "giris"):
        s = st.text_input("Panel şifresi", type="password")
        if st.form_submit_button("Paneli aç"):
            if D.sifre_dogru(s, base):
                ss[_ON + "acik"] = True
                st.rerun()
            else:
                time.sleep(1.5)
                st.error("Şifre yanlış.")
    return False


def _excel_yukle(yuklenen, base, mevcut):
    ss = _ss()
    kimlik = getattr(yuklenen, "file_id", None) or (yuklenen.name, yuklenen.size)
    if ss.get(_ON + "son_dosya") == kimlik:
        return
    ss[_ON + "son_dosya"] = kimlik
    try:
        okunan = D.excel_oku(yuklenen.getvalue())
    except Exception as e:
        ss[_ON + "notlar"] = ["Excel okunamadı: %s" % e]
        return
    tablolar = {k: okunan[k] for k in D.SUTUNLAR if k in okunan}
    notlar = list(okunan.get("_uyari") or []) + D.tamamla(tablolar, mevcut)
    taslak = ss.get(_ON + "taslak") or {k: list(v) for k, v in mevcut.items()}
    taslak.update(tablolar)
    ss[_ON + "taslak"] = taslak
    ss[_ON + "surum"] = ss.get(_ON + "surum", 0) + 1
    ss[_ON + "notlar"] = notlar + (["Yüklenen tablolar aşağıda taslak olarak açıldı; kontrol edip kaydedin. "
                                    "Dosyada olmayan tablolar değişmez."] if tablolar else [])


def _onizleme(f):
    for tur, d in f.items():
        if not (d["eklenen"] or d["silinen"] or d["degisen"]):
            continue
        st.markdown("**%s** — %d eklenen · %d silinen · %d değişen" % (
            D.TABLO_ADI[tur], len(d["eklenen"]), len(d["silinen"]), len(d["degisen"])))
        if d["eklenen"]:
            st.markdown("➕ " + " · ".join(d["eklenen"][:40]) + (" …" if len(d["eklenen"]) > 40 else ""))
        if d["silinen"]:
            st.markdown("➖ " + " · ".join(d["silinen"][:40]) + (" …" if len(d["silinen"]) > 40 else ""))
        for etiket, alanlar in d["degisen"][:40]:
            st.markdown("✏️ %s: %s" % (etiket, "; ".join("%s %s → %s" % (a, e if e is not None else "—",
                                                                         y if y is not None else "—")
                                                        for a, e, y in alanlar)))
        if len(d["degisen"]) > 40:
            st.caption("… ve %d değişiklik daha" % (len(d["degisen"]) - 40))


def ciz(base: str = None):
    base = base or BURASI
    ss = _ss()
    st.subheader("Lokasyon Donanımı")
    if not _sifre_kapisi(base):
        return

    mevcut = D.mevcut(base)
    taslak = ss.get(_ON + "taslak") or mevcut
    surum = ss.get(_ON + "surum", 0)
    try:
        import json
        import yollar
        with open(yollar.yol("ayar/lokasyon_profili.json", base), encoding="utf-8-sig") as fh:
            _p = json.load(fh)
        lok_adi = _p.get("ad") or _p.get("isim") or _p.get("lokasyon_id") or ""
    except Exception:
        lok_adi = ""

    ust = st.columns([1.2, 1.2, 2.6, 0.8])
    with ust[0]:
        st.download_button("⬇ Mevcut listeyi Excel indir", D.excel_yaz(mevcut, lok_adi, base),
                           file_name="Lokasyon_Donanimi_%s.xlsx" % datetime.now().strftime("%Y%m%d"),
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)
    with ust[1]:
        st.download_button("⬇ Boş şablon", D.excel_yaz(None), file_name="Lokasyon_Donanimi_Sablon.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                           use_container_width=True)
    with ust[2]:
        yuklenen = st.file_uploader("Doldurulmuş Excel'i yükle", type=["xlsx"], key=_ON + "yukle",
                                    label_visibility="collapsed")
        if yuklenen is not None:
            _excel_yukle(yuklenen, base, mevcut)
            taslak = ss.get(_ON + "taslak") or mevcut
            surum = ss.get(_ON + "surum", 0)
    with ust[3]:
        if st.button("🔒 Kilitle", use_container_width=True):
            for k in [k for k in ss.keys() if str(k).startswith(_ON)]:
                del ss[k]
            st.rerun()
    for n in ss.get(_ON + "notlar") or []:
        (st.warning if n.startswith("DİKKAT") or "okunamadı" in n else st.info)(n)

    karsilik = D.sistem_karsiligi(base)
    duzen = {}
    sekmeler = st.tabs(["Analizörler", "BMS okuma noktaları", "AHU noktaları"])
    aciklama = {
        "analizorler": "Enerji analizörleri (Modbus). IP'si olmayan satır bekleyen listede durur, okunmaz. "
                       "Satır eklemek için tablonun altındaki + satırını kullanın; silmek için satırı seçip çöp "
                       "kutusuna basın.",
        "bms": "Enerji / tesis BACnet noktaları. Yalnız 'okunan değer' satırları okunur. 'yazılabilir değer' "
               "noktaları oto-set'in kendi ayarındadır; bu panel onları yalnız listeler.",
        "ahu": "Mekanik Zeka'nın okuduğu santral noktaları. Bina + Santral + Nokta Tipi tekil olmalı.",
    }
    for sekme, tur in zip(sekmeler, ("analizorler", "bms", "ahu")):
        with sekme:
            st.caption(aciklama[tur])
            df = _df(tur, taslak.get(tur) or [], karsilik if tur == "bms" else None)
            yeni_df = st.data_editor(df, key="%sed_%s_%d" % (_ON, tur, surum), num_rows="dynamic",
                                     hide_index=True, use_container_width=True, column_config=_sutun_ayari(tur),
                                     height=min(38 + 35 * (len(df) + 1), 560))
            duzen[tur] = _kayitlar(yeni_df, tur)
            okunan = [s for s in D.normalize({tur: duzen[tur]})[tur]]
            if tur == "analizorler":
                ip = sum(1 for s in okunan if s.get("IP ADRESI"))
                st.caption("%d analizör okunuyor · %d bekleyen (IP yok)" % (ip, len(okunan) - ip))
            elif tur == "bms":
                say = {d: sum(1 for s in okunan if s.get("Durum") == d) for d in D.DURUMLAR}
                st.caption("%d okunan · %d yazılabilir (oto-set) · %d okunacak" % (
                    say[D.OKUNAN], say[D.YAZILABILIR], say[D.OKUNACAK]))
            else:
                st.caption("%d nokta · %d santral" % (len(okunan), len({(s.get("Bina"), s.get("Santral"))
                                                                        for s in okunan})))

    yeni = D.normalize(duzen)
    f = D.fark(mevcut, yeni)
    st.markdown("---")
    if not D.fark_var(f):
        st.caption("Kaydedilmemiş değişiklik yok.")
    else:
        yeni = {t: v for t, v in yeni.items() if D.fark_var({t: f[t]})}     # yalnız değişen tablolar
        hatalar, uyarilar = D.dogrula(yeni, base)
        st.markdown("#### Önizleme")
        _onizleme(f)
        for u in D.tur_uyarilari(mevcut, yeni):
            st.warning("Tür etkisi — " + u)
        for u in uyarilar:
            st.warning(u)
        if hatalar:
            st.error("Kaydetmeden önce düzeltin (%d):\n\n" % len(hatalar)
                     + "\n".join("- " + h for h in hatalar[:30]) + ("\n- …" if len(hatalar) > 30 else ""))
        silinen = sum(len(d["silinen"]) for d in f.values())
        onay = True
        if silinen and not hatalar:
            onay = st.checkbox("%d kaydın silinmesini onaylıyorum" % silinen, key=_ON + "sil_onay_%d" % surum)
        k = st.columns([1.4, 1, 3])
        with k[0]:
            if st.button("💾 Kaydet ve programı yeniden başlat", type="primary",
                         disabled=bool(hatalar) or not onay, use_container_width=True):
                try:
                    r = D.kaydet(yeni, base, kullanici="ayar paneli")
                except Exception as e:
                    st.error("Kaydedilemedi: %s" % e)
                else:
                    for kk in [kk for kk in ss.keys() if str(kk).startswith(_ON) and kk != _ON + "acik"]:
                        del ss[kk]
                    ss[_ON + "sonuc"] = r
                    st.rerun()
        with k[1]:
            if st.button("↩ Değişiklikleri at", use_container_width=True):
                for kk in [kk for kk in ss.keys() if str(kk).startswith(_ON) and kk != _ON + "acik"]:
                    del ss[kk]
                st.rerun()

    r = ss.get(_ON + "sonuc")
    if r:
        if r.get("yazilan"):
            st.success("Kaydedildi: %s. Yedek: %s. Program birkaç saniye içinde yeniden başlayacak; sayfa "
                       "kendiliğinden yenilenir." % (", ".join(r["yazilan"]), os.path.relpath(r["yedek"], base)))
        else:
            st.info("Değişiklik yoktu, bir şey yazılmadı.")
    gecmis = D.son_kayitlar(base)
    if gecmis:
        with st.expander("Son kayıtlar"):
            for g in gecmis:
                oz = "; ".join("%s: +%d −%d ~%d" % (D.TABLO_ADI.get(t, t), o.get("eklenen", 0), o.get("silinen", 0),
                                                    o.get("degisen", 0)) for t, o in (g.get("ozet") or {}).items())
                st.markdown("- %s — %s (yedek: `%s`)" % (g.get("zaman", "").replace("T", " "), oz or "—",
                                                          g.get("yedek", "")))
