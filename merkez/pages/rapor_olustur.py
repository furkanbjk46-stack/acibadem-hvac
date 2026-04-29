# pages/rapor_olustur.py
# Lokasyon Rapor Oluşturma — Enerji Portalı Standart Formatı

from __future__ import annotations
import os, sys, json, io, tempfile
import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

st.set_page_config(
    page_title="Rapor Oluştur",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── CSS ──────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Inter:wght@300;400;600;700&display=swap');
html, body, [data-testid="stAppViewContainer"] { background: #020b18 !important; }
[data-testid="stAppViewContainer"] { background: radial-gradient(ellipse at 50% 40%, #071830 0%, #020b18 70%) !important; }
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="collapsedControl"] { display: none !important; visibility: hidden !important; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; visibility: hidden !important; }
#MainMenu { display: none !important; }
* { font-family: 'Inter', sans-serif; }
.sec {
    font-family: 'Orbitron', sans-serif;
    font-size: 9px; font-weight: 700;
    color: rgba(0,212,255,0.5);
    letter-spacing: 3px; text-transform: uppercase;
    padding: 4px 0 10px; margin-top: 20px;
    border-bottom: 1px solid rgba(0,212,255,0.12);
}
[data-testid="stRadio"] label {
    background: rgba(0,20,50,0.6) !important;
    border: 1px solid rgba(0,212,255,0.2) !important;
    border-radius: 12px !important;
    padding: 14px 28px !important;
    color: #a0c8ff !important;
    font-weight: 600 !important;
    font-size: 14px !important;
    min-width: 150px;
    text-align: center;
}
.stButton > button {
    background: rgba(0,212,255,0.1) !important;
    color: #00d4ff !important;
    border: 1px solid rgba(0,212,255,0.35) !important;
    border-radius: 12px !important;
    font-weight: 700 !important;
    font-size: 15px !important;
    padding: 12px 32px !important;
}
.stButton > button:hover { background: rgba(0,212,255,0.22) !important; }
.stDownloadButton > button {
    background: linear-gradient(135deg, rgba(16,185,129,0.2), rgba(0,212,255,0.15)) !important;
    color: #10b981 !important;
    border: 1px solid rgba(16,185,129,0.45) !important;
    border-radius: 12px !important;
    font-weight: 700 !important;
    font-size: 16px !important;
    padding: 14px 40px !important;
    width: 100% !important;
}
</style>
""", unsafe_allow_html=True)

# ── Lokasyon tanımları ────────────────────────────────────
HASTANELER = {
    "maslak":        {"isim": "Acibadem Maslak",        "kisa": "MASLAK",      "m2": 15000, "renk": "#00d4ff"},
    "altunizade":    {"isim": "Acibadem Altunizade",    "kisa": "ALTUNIZADE",  "m2": 10000, "renk": "#f59e0b"},
    "kozyatagi":     {"isim": "Acibadem Kozyatagi",     "kisa": "KOZYATAGI",   "m2": 12000, "renk": "#10b981"},
    "taksim":        {"isim": "Acibadem Taksim",        "kisa": "TAKSIM",      "m2":  8000, "renk": "#a855f7"},
    "atakent":       {"isim": "Acibadem Atakent",       "kisa": "ATAKENT",     "m2": 20000, "renk": "#f97316"},
    "atasehir":      {"isim": "Acibadem Atasehir",      "kisa": "ATASEHIR",    "m2": 14000, "renk": "#06b6d4"},
    "bakirkoy":      {"isim": "Acibadem Bakirkoy",      "kisa": "BAKIRKOY",    "m2": 12000, "renk": "#84cc16"},
    "fulya":         {"isim": "Acibadem Fulya",         "kisa": "FULYA",       "m2":  9000, "renk": "#e879f9"},
    "international": {"isim": "Acibadem International", "kisa": "INTERNAT.",   "m2": 18000, "renk": "#14b8a6"},
    "kadikoy":       {"isim": "Acibadem Kadikoy",       "kisa": "KADIKOY",     "m2":  8000, "renk": "#ec4899"},
    "kartal":        {"isim": "Acibadem Kartal",        "kisa": "KARTAL",      "m2": 11000, "renk": "#ef4444"},
}

# ── Config ────────────────────────────────────────────────
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "configs", "merkez_config.json")

def load_config():
    try:
        if "supabase" in st.secrets:
            cfg = {
                "supabase_url": st.secrets["supabase"]["url"],
                "supabase_key": st.secrets["supabase"]["key"],
            }
            if "m2_degerler" in st.secrets:
                cfg["m2_degerler"] = dict(st.secrets["m2_degerler"])
            return cfg
    except Exception:
        pass
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

config = load_config()
url = config.get("supabase_url", "")
key = config.get("supabase_key", "")

lok_id = st.session_state.get("rapor_lokasyon", None)
if not lok_id or lok_id not in HASTANELER:
    st.error("Lokasyon secilmedi. Ana sayfaya donun.")
    if st.button("Ana Sayfaya Don"):
        st.switch_page("app_merkez.py")
    st.stop()

lok_info = HASTANELER[lok_id]
renk     = lok_info["renk"]
m2       = lok_info.get("m2", 10000)
rr = int(renk[1:3],16); rg = int(renk[3:5],16); rb = int(renk[5:7],16)

# ── Veri çek ─────────────────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def fetch_lok_data(url, key, lok_id):
    try:
        from supabase import create_client
        c = create_client(url, key)
        all_data, offset, batch = [], 0, 1000
        while True:
            r = (c.table("energy_data").select("*")
                  .eq("lokasyon_id", lok_id)
                  .order("Tarih", desc=False)
                  .range(offset, offset + batch - 1)
                  .execute())
            if not r.data:
                break
            all_data.extend(r.data)
            if len(r.data) < batch:
                break
            offset += batch
        if all_data:
            df = pd.DataFrame(all_data)
            df["Tarih"] = pd.to_datetime(df["Tarih"], errors="coerce")
            for col in df.columns:
                if col not in ["id", "lokasyon_id", "Tarih", "Kar_Eritme_Aktif"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df
    except Exception:
        pass
    return pd.DataFrame()

df = fetch_lok_data(url, key, lok_id)

# ── Header ───────────────────────────────────────────────
col_geri, col_baslik = st.columns([1, 8])
with col_geri:
    if st.button("Geri"):
        st.switch_page("pages/lokasyon_detay.py")
with col_baslik:
    st.markdown(
        f"""<div style='padding:8px 0;'>
        <div style='font-family:Orbitron,sans-serif;font-size:8px;color:rgba(0,212,255,0.45);
                    letter-spacing:5px;text-transform:uppercase;'>ACIBADEM SAGLIK GRUBU - RAPOR SISTEMI</div>
        <div style='font-family:Orbitron,sans-serif;font-size:22px;font-weight:900;
                    color:{renk};text-shadow:0 0 25px rgba({rr},{rg},{rb},0.8);
                    letter-spacing:3px;'>{lok_info["isim"].upper()}</div>
        </div>""",
        unsafe_allow_html=True
    )

st.markdown("---")

if df.empty:
    st.warning("Bu lokasyon icin veri bulunamadi.")
    st.stop()

son_tarih = df["Tarih"].dropna().max()

# ── Dönem seçimi ─────────────────────────────────────────
st.markdown('<div class="sec">RAPOR DONEMI SECIN</div>', unsafe_allow_html=True)
st.markdown("")
period = st.radio(
    "Donem",
    ["Gunluk", "Haftalik", "Aylik"],
    horizontal=True,
    label_visibility="collapsed",
    key="rapor_period"
)

if period == "Gunluk":
    bas         = son_tarih
    period_type = "GUNLUK"
    period_str  = son_tarih.strftime("%d.%m.%Y")
elif period == "Haftalik":
    bas         = son_tarih - timedelta(days=6)
    period_type = "HAFTALIK"
    period_str  = f"{bas.strftime('%d.%m')} - {son_tarih.strftime('%d.%m.%Y')}"
else:
    bas         = son_tarih - timedelta(days=29)
    period_type = "AYLIK"
    period_str  = f"{bas.strftime('%d.%m')} - {son_tarih.strftime('%d.%m.%Y')}"

period_df = df[(df["Tarih"] >= bas) & (df["Tarih"] <= son_tarih)].copy()

st.markdown(
    f"""<div style='background:rgba(0,20,50,0.5);border:1px solid rgba(0,212,255,0.12);
                   border-radius:10px;padding:12px 18px;margin:14px 0;
                   font-size:12px;color:rgba(150,210,255,0.7);'>
        <span style='color:rgba(0,212,255,0.8);font-weight:700;'>{period_type}</span>
        &nbsp;·&nbsp; {period_str}
        &nbsp;·&nbsp; {len(period_df)} gunluk veri
    </div>""",
    unsafe_allow_html=True
)


# ══════════════════════════════════════════════════════════
# PDF URETICI — Enerji Portali Standart Formati
# ══════════════════════════════════════════════════════════

def _sanitize(text: str) -> str:
    """Emoji/sembol/Unicode özel karakter → ASCII, metin temizleme."""
    if text is None:
        return ""
    for char, rep in {
        # Tire/cizgi varyantlari
        "\u2014": " - ",   # em dash —
        "\u2013": " - ",   # en dash –
        "\u2012": "-",     # figure dash
        "\u2015": "-",     # horizontal bar
        # Tirnak
        "\u2018": "'", "\u2019": "'",   # sol/sag tek tirnak
        "\u201c": '"', "\u201d": '"',   # sol/sag cift tirnak
        # Diger semboller
        "•": "-", "·": ".", "→": "->", "←": "<-", "↑": "^", "↓": "v",
        "…": "...",
        # Emoji
        "📊": "", "✅": "[OK]", "❌": "[X]", "⚠️": "[!]",
        "📈": "", "📉": "", "🔹": "*", "❄️": "", "🔥": "",
        "🟢": "[+]", "🟡": "[-]", "🔴": "[!]",
        "📄": "", "📐": "", "⚡": "", "🏥": "",
    }.items():
        text = text.replace(char, rep)
    return text


def _download_dejavu(fonts_dir):
    """DejaVu fontlarini internetten indir (ilk kurulumda bir kez)."""
    import urllib.request
    BASE_URL = "https://github.com/dejavu-fonts/dejavu-fonts/raw/master/ttf/"
    files = {
        "DejaVuSans.ttf":        BASE_URL + "DejaVuSans.ttf",
        "DejaVuSans-Bold.ttf":   BASE_URL + "DejaVuSans-Bold.ttf",
        "DejaVuSans-Oblique.ttf":BASE_URL + "DejaVuSans-Oblique.ttf",
    }
    os.makedirs(fonts_dir, exist_ok=True)
    for fname, furl in files.items():
        dest = os.path.join(fonts_dir, fname)
        if not os.path.exists(dest):
            try:
                urllib.request.urlretrieve(furl, dest)
            except Exception:
                pass


def _setup_unicode_font(pdf):
    """DejaVu Unicode font ekle — Turkce karakter destegi.
    Font yoksa uygulama klasorune indirir."""
    from pathlib import Path
    BASE       = Path(__file__).parent.parent
    fonts_dir  = BASE / "fonts"

    def cands(name):
        return [
            fonts_dir / name,
            Path("C:/Windows/Fonts") / name,
            Path("/usr/share/fonts/truetype/dejavu") / name,
        ]

    reg  = next((p for p in cands("DejaVuSans.ttf") if p.exists()), None)

    # Font bulunamazsa indir, tekrar dene
    if reg is None:
        _download_dejavu(str(fonts_dir))
        reg  = next((p for p in cands("DejaVuSans.ttf") if p.exists()), None)

    bold = next((p for p in cands("DejaVuSans-Bold.ttf") if p.exists()), None)
    ital = next((p for p in cands("DejaVuSans-Oblique.ttf") if p.exists()), None)

    if reg:
        pdf.add_font("DejaVu", "",  str(reg),  uni=True)
        if bold: pdf.add_font("DejaVu", "B", str(bold), uni=True)
        pdf.add_font("DejaVu", "I", str(ital) if ital else str(reg), uni=True)
        return "DejaVu"
    return "Helvetica"


def _plotly_bar(period_df, lok_renk) -> Optional[bytes]:
    """Gunluk tuketim bar grafigi."""
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
    except ImportError:
        return None

    if "Toplam_Hastane_Tuketim_kWh" not in period_df.columns or period_df.empty:
        return None

    gun = (period_df.groupby(period_df["Tarih"].dt.date)["Toplam_Hastane_Tuketim_kWh"]
           .sum().reset_index())
    gun.columns = ["Tarih", "kWh"]

    colors = [lok_renk] * len(gun)
    if colors:
        colors[-1] = "#00d4ff"

    fig = go.Figure(go.Bar(
        x=[str(d) for d in gun["Tarih"]],
        y=gun["kWh"],
        marker_color=colors,
        hovertemplate="<b>%{x}</b><br>%{y:,.0f} kWh<extra></extra>",
    ))
    fig.update_layout(
        paper_bgcolor="#1a2332", plot_bgcolor="#0f172a",
        font=dict(color="white", size=11),
        xaxis=dict(gridcolor="rgba(255,255,255,0.08)", tickangle=-35,
                   tickfont=dict(size=9)),
        yaxis=dict(gridcolor="rgba(255,255,255,0.08)", title="kWh",
                   tickfont=dict(size=9)),
        margin=dict(l=50, r=20, t=30, b=60),
        width=560, height=280,
        title=dict(text="Gunluk Tuketim (kWh)", font=dict(size=13, color="white")),
    )
    return pio.to_image(fig, format="png", scale=2)


def _plotly_chiller(period_df) -> Optional[bytes]:
    """Chiller Set + Dis Hava trend grafigi."""
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
    except ImportError:
        return None

    if "Chiller_Set_Temp_C" not in period_df.columns:
        return None
    ch = period_df.dropna(subset=["Chiller_Set_Temp_C"]).copy()
    if ch.empty:
        return None

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=ch["Tarih"], y=ch["Chiller_Set_Temp_C"],
        name="Chiller Set", line=dict(color="#a855f7", width=2.5),
        fill="tozeroy", fillcolor="rgba(168,85,247,0.07)",
    ))
    if "Dis_Hava_Sicakligi_C" in ch.columns and ch["Dis_Hava_Sicakligi_C"].notna().any():
        fig.add_trace(go.Scatter(
            x=ch["Tarih"], y=ch["Dis_Hava_Sicakligi_C"],
            name="Dis Hava", line=dict(color="#f59e0b", width=1.8, dash="dot"),
            yaxis="y2",
        ))
    fig.update_layout(
        paper_bgcolor="#1a2332", plot_bgcolor="#0f172a",
        font=dict(color="white", size=11),
        xaxis=dict(gridcolor="rgba(255,255,255,0.08)"),
        yaxis=dict(title="Set degeri (C)", gridcolor="rgba(255,255,255,0.08)",
                   tickfont=dict(size=9)),
        yaxis2=dict(title="Dis Hava (C)", overlaying="y", side="right",
                    tickfont=dict(size=9)),
        legend=dict(orientation="h", y=1.12, font=dict(size=10)),
        margin=dict(l=50, r=50, t=40, b=30),
        width=560, height=260,
        title=dict(text="Chiller Set Trendi", font=dict(size=13, color="white")),
    )
    return pio.to_image(fig, format="png", scale=2)


def _plotly_pie(sebeke, kojen) -> Optional[bytes]:
    """Enerji kaynagi pasta grafigi."""
    try:
        import plotly.graph_objects as go
        import plotly.io as pio
    except ImportError:
        return None

    if sebeke <= 0 and kojen <= 0:
        return None

    labels = ["Sebeke", "Kojen Uretim"]
    values = [sebeke, kojen]
    colors = ["#3b82f6", "#10b981"]

    fig = go.Figure(go.Pie(
        labels=labels, values=values, hole=0.45,
        marker=dict(colors=colors, line=dict(color="#1a2332", width=2)),
        textinfo="label+percent",
        textfont=dict(size=12, color="white"),
    ))
    fig.update_layout(
        paper_bgcolor="#1a2332",
        font=dict(color="white", size=11),
        showlegend=True,
        legend=dict(orientation="h", y=-0.15, x=0.5, xanchor="center",
                    font=dict(size=10, color="white")),
        margin=dict(l=10, r=10, t=30, b=40),
        width=300, height=280,
        title=dict(text="Enerji Kaynagi", font=dict(size=13, color="white")),
    )
    return pio.to_image(fig, format="png", scale=2)


# ── PDF Sınıfı ───────────────────────────────────────────
class HastaneRaporPDF:
    """
    Enerji Portali standart formatiyla PDF rapor olusturucu.
    fpdf2 kullanir — DejaVu font ile Turkce karakter destegi.
    """

    ACCENT    = (59, 130, 246)    # Mavi
    HEADER_BG = (15, 23, 42)     # Koyu lacivert header
    DARK_BG   = (26, 35, 50)     # Koyu arka plan
    CARD_BG   = (245, 247, 250)  # Kart arka plani (acik)
    SUCCESS   = (16, 185, 129)   # Yesil
    WARNING_C = (245, 158, 11)   # Turuncu
    DANGER    = (239, 68, 68)    # Kirmizi
    WHITE     = (255, 255, 255)
    GRAY      = (120, 130, 150)
    DARK_TEXT = (30, 30, 40)

    def __init__(self, lok_info: dict, period_type: str, period_str: str):
        from fpdf import FPDF
        self.pdf = FPDF()
        self.pdf.set_auto_page_break(auto=True, margin=20)
        self.font = _setup_unicode_font(self.pdf)
        self.lok_info = lok_info
        self.period_type = period_type
        self.period_str  = period_str

        # Lokasyon rengi (0-255)
        hx = lok_info["renk"].lstrip("#")
        self.LOK_COLOR = (int(hx[0:2],16), int(hx[2:4],16), int(hx[4:6],16))

    # ── İç yardımcılar ──────────────────────────────────

    def _set_fill(self, rgb):
        self.pdf.set_fill_color(*rgb)

    def _set_text(self, rgb):
        self.pdf.set_text_color(*rgb)

    def _set_font(self, style="", size=10):
        self.pdf.set_font(self.font, style, size)

    # ── Header / Footer ─────────────────────────────────

    def _draw_header(self):
        p = self.pdf
        # Arka plan
        self._set_fill(self.HEADER_BG)
        p.rect(0, 0, 210, 44, "F")
        # Accent alt cizgi
        self._set_fill(self.ACCENT)
        p.rect(0, 44, 210, 1.5, "F")
        # Sol lokasyon renk seridi
        self._set_fill(self.LOK_COLOR)
        p.rect(0, 0, 4, 44, "F")

        # Ust yazi: Kurum
        self._set_font("", 7.5)
        self._set_text(self.GRAY)
        p.set_xy(8, 6)
        p.cell(0, 5, "ACIBADEM SAGLIK GRUBU  |  ENERJI & HVAC YONETIM SISTEMI")

        # Hastane adi
        self._set_font("B", 18)
        self._set_text(self.WHITE)
        p.set_xy(8, 13)
        p.cell(0, 10, _sanitize(self.lok_info["isim"].upper()))

        # Olusturulma
        self._set_font("", 7)
        self._set_text(self.GRAY)
        p.set_xy(8, 35)
        p.cell(0, 5, f"Olusturuldu: {datetime.now().strftime('%d.%m.%Y  %H:%M')}")

        # Sag: Donem rozeti
        self._set_fill(self.LOK_COLOR)
        p.rect(130, 8, 72, 18, "F")
        self._set_font("B", 9)
        self._set_text(self.HEADER_BG)
        p.set_xy(130, 10)
        p.cell(72, 6, f"{self.period_type} RAPOR", align="C")
        self._set_font("", 7.5)
        self._set_text(self.WHITE)
        p.set_xy(130, 18)
        p.cell(72, 6, _sanitize(self.period_str), align="C")

        p.set_y(50)

    def _draw_footer(self):
        p = self.pdf
        p.set_y(-14)
        self._set_fill(self.HEADER_BG)
        p.rect(0, p.get_y(), 210, 14, "F")
        self._set_fill(self.ACCENT)
        p.rect(0, p.get_y(), 210, 0.8, "F")
        self._set_font("I", 7.5)
        self._set_text(self.GRAY)
        p.set_x(10)
        p.cell(0, 12,
               _sanitize(f"Acibadem Saglik Grubu - {self.lok_info['isim']}  /  "
                          f"{self.period_type}  /  {self.period_str}  /  "
                          f"Sayfa {p.page_no()}"))

    # ── Yardımcı çizim ──────────────────────────────────

    def section_title(self, title: str, color=None):
        if color is None:
            color = self.ACCENT
        p = self.pdf
        p.ln(5)
        self._set_fill(color)
        p.rect(10, p.get_y(), 3, 8, "F")
        self._set_font("B", 12)
        self._set_text(self.DARK_TEXT)
        p.set_x(16)
        p.cell(0, 8, _sanitize(title))
        p.ln(10)

    def kpi_row(self, metrics: list):
        """
        metrics: [(etiket, deger, birim, renk_rgb), ...]
        Yatay KPI kart satiri cizer.
        """
        p    = self.pdf
        n    = len(metrics)
        gap  = 4
        w    = (190 - gap * (n - 1)) / n
        h    = 26
        x0   = 10
        y0   = p.get_y()

        for i, (lbl, val, unit, col) in enumerate(metrics):
            x = x0 + i * (w + gap)
            # Kart arka plan
            self._set_fill(self.CARD_BG)
            p.rect(x, y0, w, h, "F")
            # Sol renk seridi
            self._set_fill(col)
            p.rect(x, y0, 2.5, h, "F")
            # Etiket
            self._set_font("", 6.5)
            self._set_text(self.GRAY)
            p.set_xy(x + 5, y0 + 3)
            p.cell(w - 7, 4, _sanitize(lbl))
            # Deger
            self._set_font("B", 13)
            self._set_text(col)
            p.set_xy(x + 5, y0 + 9)
            p.cell(w - 7, 8, _sanitize(str(val)))
            # Birim
            self._set_font("", 6.5)
            self._set_text(self.GRAY)
            p.set_xy(x + 5, y0 + 19)
            p.cell(w - 7, 4, _sanitize(unit))

        p.set_y(y0 + h + 5)

    def add_chart(self, img_bytes: bytes, w: float = 190, h: float = 0):
        if img_bytes is None:
            return
        p = self.pdf
        tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
        try:
            tmp.write(img_bytes)
            tmp.close()
            p.image(tmp.name, x=10, y=p.get_y(), w=w, h=h)
            if h > 0:
                p.set_y(p.get_y() + h + 4)
            else:
                p.ln(6)
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass

    def add_chart_pair(self, left_bytes: bytes, right_bytes: bytes,
                       left_w_ratio=0.62, h=60):
        """Iki grafigi yan yana koy."""
        if left_bytes is None and right_bytes is None:
            return
        p   = self.pdf
        lw  = 190 * left_w_ratio
        rw  = 190 * (1 - left_w_ratio) - 4
        y0  = p.get_y()

        for img, x, iw in [
            (left_bytes,  10,      lw),
            (right_bytes, 10+lw+4, rw),
        ]:
            if img is None:
                continue
            tmp = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
            try:
                tmp.write(img)
                tmp.close()
                p.image(tmp.name, x=x, y=y0, w=iw, h=h)
            finally:
                try:
                    os.unlink(tmp.name)
                except Exception:
                    pass

        p.set_y(y0 + h + 5)

    # ── Ana üretici ─────────────────────────────────────

    def build(self, period_df: pd.DataFrame, m2: int,
              bar_img, chiller_img, pie_img) -> bytes:
        p = self.pdf
        p.add_page()
        self._draw_header()

        # ── 1. Ozet Metrikler ──────────────────────────
        def cs(col): return period_df[col].sum() if col in period_df.columns else 0
        def cm(col):
            v = period_df[col].mean() if col in period_df.columns else None
            return None if (v is None or pd.isna(v)) else v

        kwh_total  = cs("Toplam_Hastane_Tuketim_kWh")
        kwh_m2     = kwh_total / m2 if kwh_total and m2 else 0
        ch_set     = cm("Chiller_Set_Temp_C")
        sebeke     = cs("Sebeke_Tuketim_kWh")
        kojen      = cs("Kojen_Uretim_kWh")
        kazan_gaz  = cs("Kazan_Dogalgaz_m3")
        kojen_gaz  = cs("Kojen_Dogalgaz_m3")
        toplam_gaz = kazan_gaz + kojen_gaz
        su         = cs("Su_Tuketimi_m3")

        CYAN   = self.ACCENT
        AMBER  = (245, 158, 11)
        GREEN  = (16, 185, 129)
        PURPLE = (168, 85, 247)
        ORANGE = (249, 115, 22)
        BLUE2  = (6, 182, 212)

        self.section_title("OZET METRIKLER", CYAN)

        self.kpi_row([
            ("TOPLAM TUKETIM",   f"{kwh_total/1000:,.2f}", "MWh",    CYAN),
            ("kWh / m2",         f"{kwh_m2:.3f}",           "kWh/m2", AMBER),
            ("CHILLER SET ORT.", f"{ch_set:.1f}" if ch_set else "--", "C",  PURPLE),
            ("TOPLAM DOGALGAZ",  f"{toplam_gaz:,.0f}",       "m3",    ORANGE),
        ])

        self.kpi_row([
            ("SEBEKE TUKETIMI", f"{sebeke:,.0f}",  "kWh", CYAN),
            ("KOJEN URETIMI",   f"{kojen:,.0f}",   "kWh", GREEN),
            ("KAZAN DOGALGAZ",  f"{kazan_gaz:,.0f}", "m3", ORANGE),
            ("SU TUKETIMI",     f"{su:,.1f}",       "m3",  BLUE2),
        ])

        # ── 2. Tuketim Bar Grafigi ─────────────────────
        self.section_title("GUNLUK TUKETIM (kWh)", CYAN)
        self.add_chart(bar_img, w=190, h=68)

        # ── 3. Chiller + Pasta yan yana ───────────────
        if chiller_img or pie_img:
            self.section_title("CHILLER SET TRENDI  &  ENERJI KAYNAGI", PURPLE)
            self.add_chart_pair(chiller_img, pie_img, left_w_ratio=0.63, h=68)

        # ── Footer ────────────────────────────────────
        self._draw_footer()

        buf = io.BytesIO()
        p.output(buf)
        return buf.getvalue()


# ── Rapor Oluştur ─────────────────────────────────────────
def generate_pdf(df, period_df, lok_info, lok_id, period_type, period_str, m2):
    try:
        from fpdf import FPDF  # noqa — sadece import testi
    except ImportError:
        import subprocess
        try:
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "fpdf2", "--quiet"],
                timeout=60
            )
            from fpdf import FPDF  # noqa
        except Exception as e:
            return None, None, f"fpdf2 yuklenemedi: {e}. Terminal: pip install fpdf2"

    try:
        import plotly.io  # noqa
    except ImportError:
        return None, None, "plotly yuklu degil. Terminal: pip install plotly kaleido"

    son_tarih = df["Tarih"].dropna().max()

    lok_renk = lok_info["renk"]

    with st.spinner("Grafikler olusturuluyor..."):
        bar_img     = _plotly_bar(period_df, lok_renk)
        chiller_img = _plotly_chiller(period_df)
        sebeke_val  = period_df["Sebeke_Tuketim_kWh"].sum() if "Sebeke_Tuketim_kWh" in period_df.columns else 0
        kojen_val   = period_df["Kojen_Uretim_kWh"].sum()   if "Kojen_Uretim_kWh"   in period_df.columns else 0
        pie_img     = _plotly_pie(sebeke_val, kojen_val)

    rapor = HastaneRaporPDF(lok_info, period_type, period_str)
    pdf_bytes = rapor.build(period_df, m2, bar_img, chiller_img, pie_img)

    dosya = f"rapor_{lok_id}_{period_type.lower()}_{son_tarih.strftime('%Y%m%d')}.pdf"
    return pdf_bytes, dosya, None


# ── UI ───────────────────────────────────────────────────
st.markdown("")
col_btn, _, col_dl = st.columns([2, 1, 2])

with col_btn:
    if st.button("Rapor Olustur", use_container_width=True):
        pdf_bytes, dosya_adi, hata = generate_pdf(
            df, period_df, lok_info, lok_id, period_type, period_str, m2
        )
        if hata:
            st.error(hata)
        elif pdf_bytes:
            st.session_state["_pdf_bytes"] = pdf_bytes
            st.session_state["_pdf_dosya"] = dosya_adi
            st.success(f"Rapor hazir: **{dosya_adi}**")
        else:
            st.error("PDF olusturulamadi.")

with col_dl:
    if st.session_state.get("_pdf_bytes"):
        st.download_button(
            "PDF Indir",
            data=st.session_state["_pdf_bytes"],
            file_name=st.session_state.get("_pdf_dosya", "rapor.pdf"),
            mime="application/pdf",
            use_container_width=True,
        )
