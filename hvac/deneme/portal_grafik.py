# -*- coding: utf-8 -*-
"""
ENERJİ PORTALI — GRAFİK & TREND (29.10.2026)
============================================

Synapse lokasyon Dashboard'undaki GRAFİK bölümünün (merkez/pages/lokasyon_detay.py)
Enerji portalındaki karşılığı: kategorili AÇILIR LİSTEDEN tüm metrikler,
her metriğin kendi simgesi/birimi ve karşılaştırılan aya göre rozet.
Grafikler DÜZ (29.10.2026, kullanıcı kararı): akan desen / animasyon yok, düz renk.

Dönem, Dashboard'un üstündeki Yıl/Ay ↔ Karşılaştırılacak Yıl/Ay seçimidir.
Değerler veriden olduğu gibi çizilir; hiçbir değer üretilmez.
"""
import pandas as pd
import plotly.graph_objects as go

try:
    import synapse_ikonlar as IK
except Exception:
    IK = None

KAP = "grafik_secim"          # açılır listenin st.container anahtarı
ALAN = "grafik_alani"         # grafiğin st.container anahtarı

# (kategori, [(ad, tip, birim, simge)])
GRUPLAR = [
    ("ENERJİ & KAYNAK", [
        ("Tüketim", "tuketim", "kWh", "enerji"),
        ("Şebeke Tüketimi", "sebeke", "kWh", "sebeke"),
        ("Trafolar (TRDP)", "trafo", "kWh", "trdp"),
        ("Kojen Üretim", "kojen", "kWh", "kojen"),
        ("Kojenler (1-4)", "kojenler", "kWh", "kojen"),
    ]),
    ("GAZ & SU", [
        ("Kazan Doğalgaz", "kazan", "m³", "kazan"),
        ("Kojen Doğalgaz", "kojen_gaz", "m³", "dogalgaz"),
        ("Su Tüketimi", "su", "m³", "su"),
    ]),
    ("SOĞUTMA & MEKANİK", [
        ("Soğutma Tüketimi", "sogutma", "kWh", "sogutma"),
        ("Chiller'lar (1-5)", "chillerler", "kWh", "sogutma"),
        ("MCC Tüketimi", "mcc", "kWh", "mcc"),
        ("Chiller Set & Dış Hava", "chiller_set", "°C", "termometre"),
    ]),
    ("ÖZET & KARŞILAŞTIRMA", [
        ("kWh/m² Trendi", "verim", "kWh/m²", "verim"),
        ("Seçilen Ay ↔ Karşılaştırılan Ay", "karsilastir", "kWh", "takvim"),
        ("Enerji Kırılımı", "kirilim", "kWh", "grafik"),
    ]),
]
SECENEKLER = {ad: tip for _, ogeler in GRUPLAR for ad, tip, _, _ in ogeler}
BIRIM = {tip: b for _, ogeler in GRUPLAR for _, tip, b, _ in ogeler}
SIMGE = {tip: s for _, ogeler in GRUPLAR for _, tip, _, s in ogeler}

# Tek sütunlu metrikler: (kolon, —, renk)
TEK = {
    "tuketim":   ("Toplam_Hastane_Tuketim_kWh", "akim", "#2a78d6"),
    "sebeke":    ("Sebeke_Tuketim_kWh", "elektrik", "#4a3aa7"),
    "kojen":     ("Kojen_Uretim_kWh", "uretim", "#0ca30c"),
    "kazan":     ("Kazan_Dogalgaz_m3", "alev", "#d03b3b"),
    "kojen_gaz": ("Kojen_Dogalgaz_m3", "alev", "#eb6834"),
    "su":        ("Su_Tuketimi_m3", "dalga", "#0ea5e9"),
    "sogutma":   ("Toplam_Sogutma_Tuketim_kWh", "buz", "#2a78d6"),
    "mcc":       ("MCC_Tuketim_kWh", "led", "#eb6834"),
}
# Çok sütunlu metrikler: [(etiket, kolon, renk)]
_COK_RENK = ["#4a3aa7", "#256abf", "#c98500", "#0ca30c", "#d03b3b", "#6da7ec"]
COK = {
    "trafo":      [("TRDP-%d" % i, "TRDP%d_kWh" % i, _COK_RENK[i - 1]) for i in range(1, 5)],
    "kojenler":   [("Kojen-%d" % i, "Kojen%d_kWh" % i, _COK_RENK[i - 1]) for i in range(1, 5)],
    "chillerler": [("CH-%d" % i, "Chiller%d_kWh" % i, _COK_RENK[i - 1]) for i in range(1, 6)],
}
# Rozet için toplanan kolon(lar)
ROZET_KOLON = dict({t: [k] for t, (k, _, _) in TEK.items()},
                   trafo=[k for _, k, _ in COK["trafo"]], kojenler=[k for _, k, _ in COK["kojenler"]],
                   chillerler=[k for _, k, _ in COK["chillerler"]], verim=["Toplam_Hastane_Tuketim_kWh"],
                   karsilastir=["Toplam_Hastane_Tuketim_kWh"], kirilim=["Toplam_Hastane_Tuketim_kWh"])

_YAZI = "Inter,system-ui,-apple-system,Segoe UI,sans-serif"


# ── Kategorili seçici (Synapse görünümü: KATEGORİ başlığı / simge · ad · birim) ──
# 31.10.2026: st.selectbox'ın açılır listesi sürüme göre farklı çiziliyor (1.42 sabit
# yükseklikli sanal liste, 1.5x data-key'li) ve yalnız görünen satırlar DOM'da —
# kategori başlığı / simge CSS'i sahada tutmuyordu (liste düz görünüyordu). Yerine
# açılır panel (st.popover) içinde gerçek başlıklar ve satır düğmeleri: her sürümde aynı.
SECIM = "dash_grafik_tip"      # seçili metriğin tipi (session_state)
_AD = {tip: ad for ad, tip in SECENEKLER.items()}


def _sec(st_, tip):
    st_.session_state[SECIM] = tip
    # Streamlit paneli seçimden sonra açık bırakıyor (31.10.2026 tarayıcı denemesi):
    # bir sonraki çizimde kapatma betiği çalışsın.
    st_.session_state[SECIM + "_kapat"] = True


# Paneli kapatır: Escape + panel dışına tıklama (baseweb Popover ikisini de dinler).
_KAPAT_JS = ("<script>const d=window.parent.document;"
             "d.dispatchEvent(new KeyboardEvent('keydown',{key:'Escape',code:'Escape',keyCode:27,bubbles:true}));"
             "['mousedown','mouseup','click'].forEach(t=>d.body.dispatchEvent(new MouseEvent(t,{bubbles:true})));"
             "</script>")


def secili(st_, varsayilan: str = "tuketim") -> str:
    tip = st_.session_state.get(SECIM, varsayilan)
    return tip if tip in _AD else varsayilan


def secici_css(secili_tip: str) -> str:
    # Görünüm Synapse lokasyon Dashboard'undaki listeyle aynı: beyaz panel, gri büyük
    # harf kategori başlığı, satırlarda arka plan YOK (portalın genel düğme rengi —
    # açık mavi — ezilir), üzerine gelince çok açık gri, seçili satır açık mavi + sol çizgi.
    # Streamlit markdown bloklarına eksi alt boşluk verir; başlık satırla çakışmasın
    # diye başlığın kabındaki boşluklar sıfırlanır.
    css = (
        '.st-key-%s button{justify-content:flex-start;background:#fff !important;'
        'border:1px solid rgba(24,26,30,.12) !important;border-radius:12px;min-height:40px;'
        'box-shadow:0 6px 16px -12px rgba(20,22,26,.3) !important;}'
        '.st-key-%s button p{font-size:13px !important;font-weight:600 !important;color:#133273 !important;}'
        '[data-testid="stPopoverBody"]:has(.gsec-baslik){background:#fff !important;}'
        # Yükseklik sınırı + kaydırma: panel tüm listeyi (≈1100 px) sığdıramayınca Streamlit
        # onu düğmenin üstüne/ortaya taşıyordu. Ay seçimindeki gibi AŞAĞI açılsın (31.10.2026).
        '[data-testid="stPopoverBody"]:has(.gsec-baslik){max-height:min(440px,55vh) !important;'
        'overflow-y:auto !important;}'
        # DİKKAT: panel kapalıyken içeriği SAYFADA gizli durur. :has() kuralları panelin
        # dışına taşarsa tüm Dashboard bloğuna uygulanır (31.10.2026: bölüm araları
        # sıfırlanıp sayfa sıkıştı, panel açılınca kural düşüp sayfa kaydı). Hepsi
        # stPopoverBody İÇİNE sınırlı.
        '[data-testid="stPopoverBody"] [data-testid="stElementContainer"]:has(.gsec-baslik),'
        '[data-testid="stPopoverBody"] [data-testid="stMarkdown"]:has(.gsec-baslik),'
        '[data-testid="stPopoverBody"] [data-testid="stMarkdownContainer"]:has(.gsec-baslik)'
        '{margin:0 !important;padding:0 !important;}'
        'p.gsec-baslik{display:block;margin:0 !important;padding:14px 10px 6px !important;line-height:1.2;'
        'font-size:10.5px !important;font-weight:800 !important;letter-spacing:1.1px;color:#8b97ab !important;}'
        'p.gsec-baslik.ilk{padding-top:4px !important;}'
        '[data-testid="stPopoverBody"] [data-testid="stVerticalBlock"]:has(> div [class*="st-key-gsec_"]),'
        '[data-testid="stPopoverBody"] [data-testid="stVerticalBlock"]:has(> [class*="st-key-gsec_"])'
        '{gap:0 !important;}'
        '[class*="st-key-gsec_"] button,[class*="st-key-gsec_"] button:focus,'
        '[class*="st-key-gsec_"] button:active{justify-content:flex-start;border:none !important;'
        'background:transparent !important;min-height:40px;padding:0 12px;border-radius:8px;'
        'box-shadow:none !important;}'
        '[class*="st-key-gsec_"] button:hover{background:#f3f6fb !important;}'
        '[class*="st-key-gsec_"] button p{font-size:14px !important;font-weight:600 !important;color:#24324d !important;}'
        '[class*="st-key-gsec_"] button::after{margin-left:auto;padding-left:16px;font-size:10.5px;'
        'font-weight:600;color:#8b97ab;font-family:ui-monospace,SFMono-Regular,Menlo,monospace;}'
        '.st-key-gsec_%s button,.st-key-gsec_%s button:focus,.st-key-gsec_%s button:hover'
        '{background:#eef3fb !important;box-shadow:inset 3px 0 0 #2a78d6 !important;}'
        '.st-key-gsec_%s button p{color:#133273 !important;}'
    ) % (KAP, KAP, secili_tip, secili_tip, secili_tip, secili_tip)
    for _, tip in SECENEKLER.items():
        css += '.st-key-gsec_%s button::after{content:"%s";}' % (tip, BIRIM.get(tip, ""))
        if IK:
            css += IK.etiket_css('.st-key-gsec_%s button p' % tip, SIMGE.get(tip, "grafik"), 16)
    if IK:
        css += IK.etiket_css('.st-key-%s button p' % KAP, SIMGE.get(secili_tip, "grafik"), 17)
    return "<style>" + css + "</style>"


def secici(st_, varsayilan: str = "tuketim") -> str:
    """Kategorili grafik seçici; seçilen metriğin tipini döner.
    Panel başlığı seçili metrik olduğu için seçim değişince panel yeniden çizilir ve kapanır."""
    tip = secili(st_, varsayilan)
    st_.markdown(secici_css(tip), unsafe_allow_html=True)
    with st_.container(key=KAP):
        with st_.popover("%s  ·  %s" % (_AD[tip], BIRIM[tip]), use_container_width=True):
            for i, (baslik, ogeler) in enumerate(GRUPLAR):
                st_.markdown("<p class='gsec-baslik%s'>%s</p>" % (" ilk" if i == 0 else "", baslik),
                             unsafe_allow_html=True)
                for ad, t, _, _ in ogeler:
                    st_.button(ad, key="gsec_" + t, use_container_width=True, on_click=_sec, args=(st_, t))
    if st_.session_state.pop(SECIM + "_kapat", False):
        import time
        import streamlit.components.v1 as components
        # Zaman damgası: içerik her seferinde farklı olsun, betik yeniden çalışsın
        components.html("<!-- %s -->" % time.time() + _KAPAT_JS, height=0)
    return tip


# ── Rozet: seçilen ay ↔ karşılaştırılan ay ────────────────────────────────
def _topla(dfx, kolonlar):
    t = 0.0
    for k in kolonlar:
        if k in dfx.columns:
            t += float(pd.to_numeric(dfx[k], errors="coerce").fillna(0).sum())
    return t


def rozet(tip: str, df_donem, df_kiyas, kiyas_adi: str) -> str:
    """Tüketim kalemi: artış kırmızı ▲, azalış yeşil ▼. Karşılaştırma yoksa boş."""
    kol = ROZET_KOLON.get(tip)
    if not kol or df_kiyas is None or df_kiyas.empty or df_donem.empty:
        return ""
    simdi, once = _topla(df_donem, kol), _topla(df_kiyas, kol)
    # İki ayın da verisi olmalı: bu ay girilmemiş kalem "▼ %100 azaldı" diye görünmesin
    if once <= 0 or simdi <= 0:
        return ""
    fark = (simdi - once) / once * 100
    renk, rgb, yon = ("#d03b3b", "239,68,68", "▲") if fark > 0 else ("#0ca30c", "16,185,129", "▼")
    return ("<span style='background:rgba(%s,0.15);border:1px solid %s;border-radius:6px;padding:2px 10px;"
            "font-size:11px;font-weight:700;color:%s;margin-left:8px;'>%s %s%%%s · %s</span>"
            % (rgb, renk, renk, yon, "+" if fark > 0 else "-", f"{abs(fark):.1f}".replace(".", ","), kiyas_adi))


# ── Grafikler ─────────────────────────────────────────────────────────────
def _duzen(fig, birim, yukseklik=370, sag_eksen=None, lejant=False):
    fig.update_layout(
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#24324d", family=_YAZI),
        margin=dict(t=30 if lejant else 6, b=20, l=55, r=55 if sag_eksen else 10), height=yukseklik,
        xaxis=dict(gridcolor="rgba(19,50,115,0.07)", showgrid=True),
        yaxis=dict(gridcolor="rgba(19,50,115,0.07)", showgrid=True, title=dict(text=birim, font=dict(size=10))),
        showlegend=lejant, legend=dict(orientation="h", y=1.1, font=dict(size=10)),
        hoverlabel=dict(font=dict(family=_YAZI)),
    )
    if sag_eksen:
        fig.update_layout(yaxis2=dict(title=dict(text=sag_eksen, font=dict(size=10)), overlaying="y", side="right",
                                      showgrid=False))
    return fig


def _gunluk(dfx, kolon):
    d = dfx[["Tarih", kolon]].copy() if kolon in dfx.columns else pd.DataFrame(columns=["Tarih", kolon])
    d["Tarih"] = pd.to_datetime(d["Tarih"], errors="coerce")
    d[kolon] = pd.to_numeric(d[kolon], errors="coerce")
    return d.dropna(subset=["Tarih"]).groupby(d["Tarih"].dt.date)[kolon].sum(min_count=1)


def _tarih_ekseni(fig):
    fig.update_xaxes(tickformat="%d.%m", hoverformat="%d.%m.%Y")
    return fig


def tahmin_grafigi(gunler, birim: str):
    """Günlük çubuklar: gerçekleşen (yeşil), hava tahminiyle (koyu mavi), geçmiş
    ortalama havayla (açık mavi) + sağ eksende sıcaklık. Animasyon yok."""
    d = pd.DataFrame(gunler)
    if d.empty:
        return None
    d["tarih"] = pd.to_datetime(d["tarih"])
    fig = go.Figure()
    for tur, ad, renk in (("gercek", "Gerçekleşen", "#0ca30c"), ("tahmin", "Tahmin (hava tahminiyle)", "#2a78d6"),
                          ("ortalama", "Tahmin (geçmiş ortalama havayla)", "#9db8e0")):
        s = d[d["kaynak"] == tur]
        if len(s):
            fig.add_bar(x=s["tarih"], y=s["deger"], name=ad, marker_color=renk,
                        hovertemplate="%{x|%d.%m.%Y}<br>%{y:,.0f} " + birim + "<extra></extra>")
    fig.add_scatter(x=d["tarih"], y=d["sicaklik"], name="Ort. sıcaklık (°C)", yaxis="y2", mode="lines+markers",
                    line=dict(color="#e0773a", width=2), marker=dict(size=4),
                    hovertemplate="%{y:.1f} °C<extra></extra>")
    return _tarih_ekseni(_duzen(fig, birim, yukseklik=340, sag_eksen="°C", lejant=True))


def ciz(tip: str, df_donem, df_kiyas, ay_adi: str, kiyas_adi: str, m2: float = 0):
    """(fig | None, bilgi metni). bilgi: veri yoksa kullanıcıya gösterilecek açıklama."""
    if df_donem is None or df_donem.empty:
        return None, "Seçilen ayda veri yok."
    birim = BIRIM.get(tip, "")

    if tip in TEK:
        kolon, _, renk = TEK[tip]
        s = _gunluk(df_donem, kolon).dropna()
        if s.empty or not (s.abs().sum() > 0):
            return None, "Bu metrik için seçilen ayda veri yok."
        fig = go.Figure(go.Bar(x=list(s.index), y=s.values, marker=dict(color=renk),
                               hovertemplate="<b>%{x|%d.%m.%Y}</b><br>%{y:,.1f} " + birim + "<extra></extra>"))
        return _tarih_ekseni(_duzen(fig, birim)), ""

    if tip in COK:
        fig, var = go.Figure(), False
        for etiket, kolon, renk in COK[tip]:
            s = _gunluk(df_donem, kolon).dropna()
            if s.empty or not (s.abs().sum() > 0):
                continue      # sayacı olmayan seri çizilmez (uydurma 0 yok)
            var = True
            fig.add_trace(go.Bar(x=list(s.index), y=s.values, name=etiket, marker=dict(color=renk),
                                 hovertemplate=etiket + " · %{x|%d.%m.%Y}<br>%{y:,.0f} kWh<extra></extra>"))
        if not var:
            return None, "Bu metrik için seçilen ayda veri yok."
        fig.update_layout(barmode="stack")
        return _tarih_ekseni(_duzen(fig, birim, lejant=True)), ""

    if tip == "chiller_set":
        fig = go.Figure()
        dh = _gunluk(df_donem, "Dis_Hava_Sicakligi_C").dropna()
        cs = df_donem.copy()
        cs["Tarih"] = pd.to_datetime(cs["Tarih"], errors="coerce")
        cs = cs.groupby(cs["Tarih"].dt.date)["Chiller_Set_Temp_C"].mean() \
            if "Chiller_Set_Temp_C" in cs.columns else pd.Series(dtype=float)
        cs = pd.to_numeric(cs, errors="coerce").dropna()
        if cs.empty and dh.empty:
            return None, "Chiller set / dış hava verisi yok."
        if not dh.empty:
            fig.add_trace(go.Scatter(x=list(dh.index), y=dh.values, name="Dış Hava", yaxis="y2",
                                     line=dict(color="#c98500", width=1.5, dash="dot")))
        if not cs.empty:
            fig.add_trace(go.Scatter(x=list(cs.index), y=cs.values, name="Chiller Set",
                                     line=dict(color="#2a78d6", width=2), fill="tozeroy",
                                     fillcolor="rgba(42,120,214,0.07)"))
        return _tarih_ekseni(_duzen(fig, "Set °C", sag_eksen="Dış Hava °C", lejant=True)), ""

    if tip == "verim":
        if not m2:
            return None, "Bina alanı (m²) ayarlarda girilmemiş."
        s = _gunluk(df_donem, "Toplam_Hastane_Tuketim_kWh").dropna()
        if s.empty:
            return None, "Tüketim verisi yok."
        fig = go.Figure(go.Scatter(x=list(s.index), y=(s / m2).values, line=dict(color="#c98500", width=2),
                                   fill="tozeroy", fillcolor="rgba(201,133,0,0.08)",
                                   hovertemplate="<b>%{x|%d.%m.%Y}</b><br>%{y:.3f} kWh/m²<extra></extra>"))
        return _tarih_ekseni(_duzen(fig, "kWh/m²")), ""

    if tip == "karsilastir":
        def gunler(dfx):
            d = dfx.copy()
            d["Tarih"] = pd.to_datetime(d["Tarih"], errors="coerce")
            return d.groupby(d["Tarih"].dt.day)["Toplam_Hastane_Tuketim_kWh"].sum() \
                if "Toplam_Hastane_Tuketim_kWh" in d.columns else pd.Series(dtype=float)
        bu = gunler(df_donem)
        once = gunler(df_kiyas) if df_kiyas is not None and not df_kiyas.empty else pd.Series(dtype=float)
        if bu.empty:
            return None, "Tüketim verisi yok."
        fig = go.Figure()
        if not once.empty:
            fig.add_trace(go.Bar(x=list(once.index), y=once.values, name=kiyas_adi, marker=dict(color="#9cc3f2"),
                                 hovertemplate="Gün %{x}: %{y:,.0f} kWh<extra></extra>"))
        fig.add_trace(go.Bar(x=list(bu.index), y=bu.values, name=ay_adi, marker=dict(color="#2a78d6"),
                             hovertemplate="Gün %{x}: %{y:,.0f} kWh<extra></extra>"))
        fig.update_layout(barmode="group")
        fig = _duzen(fig, "kWh", lejant=True)
        fig.update_xaxes(title=dict(text="Gün", font=dict(size=10)), dtick=1)
        return fig, ""

    if tip == "kirilim":
        d = df_donem.copy()
        d["Tarih"] = pd.to_datetime(d["Tarih"], errors="coerce")
        g = d.groupby(d["Tarih"].dt.date)
        def s(k):
            return pd.to_numeric(g[k].sum(), errors="coerce").fillna(0) if k in d.columns else None
        top, sog, mcc = s("Toplam_Hastane_Tuketim_kWh"), s("Toplam_Sogutma_Tuketim_kWh"), s("MCC_Tuketim_kWh")
        if top is None or not (top.sum() > 0):
            return None, "Tüketim verisi yok."
        sog = sog if sog is not None else top * 0
        mcc = mcc if mcc is not None else top * 0
        diger = (top - sog - mcc).clip(lower=0)
        fig = go.Figure()
        for ad, ser, renk in (("Soğutma", sog, "#2a78d6"), ("MCC", mcc, "#eb6834"), ("Aydınlatma / Diğer", diger, "#c98500")):
            fig.add_trace(go.Bar(x=list(ser.index), y=ser.values, name=ad, marker=dict(color=renk),
                                 hovertemplate=ad + " · %{x|%d.%m.%Y}<br>%{y:,.0f} kWh<extra></extra>"))
        fig.update_layout(barmode="stack")
        return _tarih_ekseni(_duzen(fig, "kWh", lejant=True)), ""

    return None, ""
