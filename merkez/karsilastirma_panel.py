# -*- coding: utf-8 -*-
"""
LOKASYON DETAY PENCERESİ — ORTAK ARAYÜZ
=======================================

Karşılaştırma sayfasındaki "Lokasyon detayı" penceresinin GÖVDESİ burada
durur. Hem canlı sayfa (pages/ozet_karsilastirma.py) hem sunum sürümü
(sunum/ozet_karsilastirma_demo.py) bu modülü kullanır — böylece ikisi
birbirinden ayrışamaz (kural_denetim.py ile aynı mantık).

Hesaplar karsilastirma_hesap.py'de; burada YALNIZCA sunum vardır.
HTML üreten fonksiyonlar streamlit'e dokunmaz, doğrudan test edilebilir.
"""


# ── Biçim yardımcıları (saf) ──────────────────────────────────────────────
def tr(sayi, ondalik=0):
    """1234.5 → '1.234,5' (Türkçe binlik/ondalık)."""
    fmt = f"{sayi:,.{ondalik}f}"
    if ondalik > 0:
        tam, _, kusur = fmt.partition(".")
        return tam.replace(",", ".") + "," + kusur
    return fmt.replace(",", ".")


def kutu(ikon, baslik, deger, alt, renk="#38bdf8"):
    return (
        f"<div style='flex:1;min-width:120px;background:rgba(0,20,50,0.6);"
        f"border:1px solid rgba(56,189,248,0.12);border-radius:10px;padding:10px 12px;'>"
        f"<div style='font-size:9px;color:rgba(150,210,255,0.55);letter-spacing:1px;'>"
        f"{ikon} {baslik}</div>"
        f"<div style='font-family:Playfair Display,serif;font-size:20px;font-weight:700;"
        f"color:{renk};margin-top:2px;'>{deger}</div>"
        f"<div style='font-size:9px;color:rgba(120,170,220,0.5);'>{alt}</div></div>"
    )


def ilerleme(ad, kwh, yuzde, renk):
    return (
        f"<div style='margin:6px 0;'>"
        f"<div style='display:flex;justify-content:space-between;font-size:11px;"
        f"color:rgba(200,230,255,0.8);'><span>{ad}</span>"
        f"<span style='color:{renk};font-family:monospace;'>%{yuzde:.1f} · {tr(kwh)} kWh</span></div>"
        f"<div style='background:rgba(30,41,59,0.9);height:7px;border-radius:4px;overflow:hidden;'>"
        f"<div style='width:{min(100, yuzde):.1f}%;height:100%;background:{renk};'></div></div></div>"
    )


def mini_liste(baslik, kalemler, renk):
    if not kalemler:
        return ""
    en_buyuk = max(k for _, k in kalemler) or 1
    satirlar = "".join(
        f"<div style='display:grid;grid-template-columns:90px 1fr 90px;gap:8px;align-items:center;"
        f"font-size:10px;margin:3px 0;'><span style='color:rgba(200,230,255,0.75);'>{ad}</span>"
        f"<div style='background:rgba(30,41,59,0.9);height:6px;border-radius:3px;overflow:hidden;'>"
        f"<div style='width:{k / en_buyuk * 100:.0f}%;height:100%;background:{renk};'></div></div>"
        f"<span style='text-align:right;font-family:monospace;color:rgba(200,230,255,0.6);'>"
        f"{tr(k)} kWh</span></div>" for ad, k in kalemler)
    return (f"<div style='margin-top:10px;'><div style='font-size:9px;letter-spacing:1px;"
            f"color:rgba(56,189,248,0.6);margin-bottom:2px;'>{baslik}</div>{satirlar}</div>")


def durum_stil(v):
    """Tablodaki 'Durum' hücresinin rengi."""
    if v in ("Eşik üstü", "Hedef altı"):
        return "color:#f59e0b;font-weight:600"
    if v == "Normal":
        return "color:#10b981"
    return "color:rgba(150,210,255,0.4)"


# ── Tıklama çözümleme (saf) ───────────────────────────────────────────────
def grafik_secimi(olay, ad2id):
    """Plotly seçim olayından lokasyon_id; yoksa None."""
    try:
        noktalar = olay["selection"]["points"]
    except Exception:
        return None
    for p in noktalar or []:
        lid = ad2id.get(p.get("y")) or ad2id.get(p.get("label"))
        if lid:
            return lid
    return None


def tablo_secimi(olay, satirlar):
    """st.dataframe seçim olayından lokasyon_id; yoksa None."""
    try:
        idx = (olay["selection"]["rows"] or [None])[0]
    except Exception:
        return None
    if idx is None or idx >= len(satirlar):
        return None
    return satirlar[idx]["id"]


def yeni_secim(st, kaynak, lid):
    """Aynı seçim her rerun'da pencereyi yeniden açmasın; yalnızca YENİ tıklama açar."""
    anahtar = "_ozet_son_secim_" + kaynak
    if not lid:
        st.session_state.pop(anahtar, None)
        return None
    if st.session_state.get(anahtar) == lid:
        return None
    st.session_state[anahtar] = lid
    return lid


# ── Pencere gövdesi ───────────────────────────────────────────────────────
def panel_govde(st, r, dag, ld, ctx):
    """Detay penceresinin içeriğini çizer.

    r   : satır sözlüğü (id/isim/deger/ikinci/kotu/durum/m2/gun/ort_chiller_yuk)
    dag : karsilastirma_hesap.sistem_dagilimi(...) çıktısı
    ld  : karsilastirma_hesap.lokasyon_durumu(...) çıktısı
    ctx : {M, secim, bas, bit, ik_metin, ik_birim, esik, oran, ik_ond,
           beklenen_gun, grup, teshis, anahtar}
    """
    M, ik_metin = ctx["M"], ctx["ik_metin"]
    ik_birim, esik = ctx["ik_birim"], ctx["esik"]
    on = ctx.get("anahtar", "ozet_panel")

    st.markdown(
        f"<div style='font-family:Playfair Display,serif;font-size:22px;color:#f8fafc;'>"
        f"{r.get('isim', r['ad'])}</div>"
        f"<div style='font-size:10px;color:rgba(120,170,220,0.55);'>{M['ad']} · {ctx['secim']} · "
        f"{ctx['bas'].strftime('%d.%m.%Y')} → {ctx['bit'].strftime('%d.%m.%Y')}</div>",
        unsafe_allow_html=True)

    k = (kutu("Σ", "DÖNEM " + M["ad"], f"{tr(r['deger'])} {M['birim']}",
              f"{r['gun']} günlük veri")
         + kutu("📐", "GÖSTERGE", ik_metin(r["ikinci"]), ik_birim,
                "#f59e0b" if r["kotu"] else "#10b981" if r["kotu"] is False else "#38bdf8")
         + kutu("🏢", "ALAN", f"{tr(r['m2'])} m²", r["durum"]))
    st.markdown(f"<div style='display:flex;gap:8px;flex-wrap:wrap;margin:10px 0;'>{k}</div>",
                unsafe_allow_html=True)

    # Teşhis (veriye dayalı maddeler)
    sev, baslik, maddeler = ctx["teshis"](
        r, ctx["grup"], dag, esik, M["artis_iyi"], ik_birim,
        ondalik=1 if ctx["oran"] else ctx["ik_ond"], beklenen_gun=ctx["beklenen_gun"])
    renk = {"uyari": ("#f59e0b", "rgba(245,158,11,0.08)", "⚠️"),
            "normal": ("#10b981", "rgba(16,185,129,0.08)", "✓"),
            "bilgi": ("#38bdf8", "rgba(56,189,248,0.06)", "ℹ️")}[sev]
    st.markdown(
        f"<div style='border:1px solid {renk[0]}55;background:{renk[1]};border-radius:10px;"
        f"padding:10px 14px;margin:6px 0 12px;'>"
        f"<div style='color:{renk[0]};font-weight:700;font-size:12px;'>{renk[2]} {baslik}</div>"
        + "".join(f"<div style='font-size:11px;color:rgba(200,230,255,0.8);margin-top:4px;'>• {m}</div>"
                  for m in maddeler)
        + "</div>", unsafe_allow_html=True)

    # Sistem bazlı dağılım
    s1, s2 = st.columns([3, 2])
    with s1:
        h = ("<div style='font-size:10px;letter-spacing:1px;color:rgba(56,189,248,0.7);'>"
             "SİSTEM BAZLI ELEKTRİK DAĞILIMI</div>"
             "<div style='font-size:9px;color:rgba(120,170,220,0.45);margin-bottom:4px;'>"
             "Sayaç verisi · ölçülmeyen yükler ayrı gösterilir</div>")
        if dag["kalemler"]:
            h += "".join(ilerleme(a, kw, y, rn) for a, kw, y, rn in dag["kalemler"])
        else:
            h += ("<div style='font-size:11px;color:rgba(150,210,255,0.5);'>"
                  "Bu dönem için sistem kırılımı yok.</div>")
        h += mini_liste("CHILLER BAZINDA", dag["chiller"], "#06b6d4")
        h += mini_liste("SOĞUTMA KULELERİ", dag["kule"], "#38bdf8")
        h += mini_liste("MCC PANOLARI", dag["mcc"], "#3b82f6")
        st.markdown(h, unsafe_allow_html=True)
    with s2:
        kay = dag["sebeke"] + dag["kojen"]
        h2 = ("<div style='font-size:10px;letter-spacing:1px;color:rgba(56,189,248,0.7);"
              "margin-bottom:4px;'>ENERJİ KAYNAĞI</div>")
        if kay:
            h2 += ilerleme("Şebeke", dag["sebeke"], dag["sebeke"] / kay * 100, "#a855f7")
            if dag["kojen"] > 0:        # kojen tesisi olmayan hastanede satır gösterilmez
                h2 += ilerleme("Kojen", dag["kojen"], dag["kojen"] / kay * 100, "#10b981")
        h2 += ("<div style='font-size:10px;letter-spacing:1px;color:rgba(56,189,248,0.7);"
               "margin:14px 0 4px;'>SİSTEM DURUMU</div>")
        for et, dg in (("Bağlantı", ld["baglanti"]), ("Oto-set", ld["oto_metin"]),
                       ("Chiller doğrulama", ld["dogrulama"] or "—"),
                       ("Arızalı cihaz", str(ld["ariza"])), ("Bakımdaki cihaz", str(ld["bakim"])),
                       ("Ort. chiller yükü", "—" if r.get("ort_chiller_yuk") is None
                        else f"%{r['ort_chiller_yuk']:.0f}")):
            h2 += (f"<div style='display:flex;justify-content:space-between;gap:8px;font-size:10px;"
                   f"padding:4px 0;border-bottom:1px solid rgba(56,189,248,0.07);'>"
                   f"<span style='color:rgba(150,210,255,0.55);'>{et}</span>"
                   f"<span style='color:rgba(220,240,255,0.85);text-align:right;'>{dg}</span></div>")
        st.markdown(h2, unsafe_allow_html=True)

    b1, b2, b3 = st.columns(3)
    with b1:
        if st.button("📍 Lokasyon detayına git", use_container_width=True, key=on + "_detay"):
            st.session_state.pop("detay_ozet", None)
            st.session_state["detay_lokasyon"] = r["id"]
            st.rerun()
    with b2:
        if st.button("📄 Rapor oluştur", use_container_width=True, key=on + "_rapor"):
            st.session_state["rapor_lokasyon"] = r["id"]
            st.switch_page("pages/rapor_olustur.py")
    with b3:
        if st.button("Kapat", use_container_width=True, key=on + "_kapat"):
            st.rerun()
