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


# ── Açılır liste görünümü (kategori başlığı · simge · ad · birim) ──────────
def secici_css(secili_tip: str) -> str:
    """Streamlit 1.42 (baseweb menü) ve 1.5x+ (sanal liste) seçicileri birlikte."""
    if not IK:
        return ""
    ilk, sira = {}, 0
    for baslik, ogeler in GRUPLAR:
        ilk[sira] = baslik
        sira += len(ogeler)
    n = len(SECENEKLER)
    listeler = ['[data-baseweb="popover"] ul[role="listbox"]:has(> li:nth-child(%d)):not(:has(> li:nth-child(%d)))'
                % (n, n + 1),
                '[data-testid="stSelectboxVirtualDropdown"]:has([data-key="%d"])' % (n - 1)]
    css = ""
    for L in listeler:
        css += (L + '{max-height:480px !important;padding:4px 8px 8px !important;}'
                + L + ' [role="option"]{display:flex !important;flex-wrap:wrap;align-items:center;'
                'min-height:36px;font-size:12.5px !important;font-weight:600 !important;color:#24324d !important;'
                'border-radius:8px;}'
                + L + ' [role="option"][aria-selected="true"]{background:#eef3fb !important;color:#133273 !important;'
                'box-shadow:inset 3px 0 0 #2a78d6;}')
    for i, (ad, tip) in enumerate(SECENEKLER.items()):
        for j, L in enumerate(listeler):
            sec = (L + ' > li[role="option"]:nth-child(%d)' % (i + 1)) if j == 0 else \
                  (L + ' [role="option"][data-key="%d"]' % i)
            css += IK.etiket_css(sec, SIMGE.get(tip, "grafik"), 16)
            css += sec + '::after{content:"%s";margin-left:auto;padding-left:12px;font-size:10.5px;' \
                         'font-weight:600;color:#8b97ab;}' % BIRIM.get(tip, "")
            if i in ilk and i > 0:          # kategori sınırı: araya boşluk + ince çizgi
                css += sec + '{margin-top:10px;border-top:1px solid rgba(24,26,30,.08);}'
    # Seçili değerin önüne simge
    css += IK.etiket_css('.st-key-%s [data-baseweb="select"] > div' % KAP, SIMGE.get(secili_tip, "grafik"), 17)
    css += ('.st-key-%s [data-baseweb="select"] > div{display:flex;align-items:center;padding-left:12px;'
            'background:#fff !important;border:1px solid rgba(24,26,30,.12) !important;border-radius:12px !important;'
            'box-shadow:0 6px 16px -12px rgba(20,22,26,.3);}'
            '.st-key-%s [data-baseweb="select"] *{font-size:13px !important;font-weight:600 !important;'
            'color:#133273 !important;}' % (KAP, KAP))
    return "<style>" + css + "</style>"


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
