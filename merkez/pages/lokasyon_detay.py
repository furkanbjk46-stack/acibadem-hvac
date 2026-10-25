# pages/lokasyon_detay.py
# Lokasyon Detay Sayfası — Sadece Okuma & Grafik

from __future__ import annotations
import os, sys, json, re
# Ana sayfa: demo app_demo.py ile açılır; "app_merkez.py"ye geçiş orada
# StreamlitAPIException veriyordu (Geri butonu sunumda kırmızı hata basıyordu).
_ANA_SAYFA = "app_demo.py" if os.environ.get("SYNAPSE_DEMO") == "1" else "app_merkez.py"
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

# Üst dizini path'e ekle (app_merkez ile aynı config'i kullan)
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

st.set_page_config(
    page_title="Lokasyon Detay",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ── GİRİŞ KAPISI ──────────────────────────────────────────────────────────
# ZORUNLU: Streamlit çoklu sayfa yapısında bu dosya KENDİ URL'sinden
# (/lokasyon_detay) doğrudan açılabilir; app_merkez.py'deki kapı burayı
# korumaz. Bu yüzden her sayfa kendi kapısını kurar.
import giris
import ikonlar as _ik
if getattr(_ik, "SURUM", 0) < 4:          # yayın sonrası eski modül önbellekte kalmasın
    import importlib as _il_ik
    _ik = _il_ik.reload(_ik)
st.markdown(_ik.CSS, unsafe_allow_html=True)

# ── Dashboard yazı stilleri = Canlı İzleme sekmesi (canli_izleme.STIL) ──
# Kart: beyaz, 16 px köşe · etiket: 10 px / 600 / gri · değer: 26 px / 700 /
# lacivert · alt satır: 10 px gri · bölüm başlığı: 12 px / 700 / lacivert.
# Renk bilgisi değerde değil SİMGEDE taşınır; yalnızca durum bildiren
# değerler (arıza sayısı, geçti/kaldı) durum rengini korur.
st.markdown("""
<style>
.dz-kart{background:#fff;border:1px solid rgba(24,26,30,.10);border-radius:16px;padding:11px 15px;
  box-shadow:0 1px 1px rgba(20,22,26,.05),0 10px 22px -12px rgba(20,22,26,.22);}
.dz-et{font-size:10px;letter-spacing:1.2px;color:#46536b;font-weight:600;text-transform:uppercase;}
.dz-dg{font-size:26px;font-weight:700;color:#133273;line-height:1.15;margin-top:1px;}
.dz-br{font-size:9.5px;font-weight:500;color:#46536b;margin-left:3px;}
.dz-alt{font-size:10px;color:#46536b;margin-top:1px;}
.sec{font-size:12px !important;font-weight:700 !important;letter-spacing:1.4px !important;color:#133273 !important;}
/* Başlıktaki lokasyon adı: rengi üzerinde akan parıltı */
@keyframes dzParilti{0%{background-position:200% 0;}100%{background-position:-200% 0;}}
.dz-baslik{background:linear-gradient(90deg,var(--r) 0%,var(--r) 38%,#ffffff 50%,var(--r) 62%,var(--r) 100%);
  background-size:200% 100%;-webkit-background-clip:text;background-clip:text;color:transparent !important;
  -webkit-text-fill-color:transparent;animation:dzParilti 4.5s linear infinite;
  filter:drop-shadow(0 0 14px color-mix(in srgb, var(--r) 45%, transparent));}
@keyframes dzKay{0%{background-position:0 0;}100%{background-position:-200% 0;}}
.dz-ust{background:linear-gradient(90deg,#2a78d6,#9cc3f2,#2a78d6);background-size:200% 100%;
  -webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;
  animation:dzKay 6s linear infinite;}
.dz-rozet{display:inline-flex;align-items:center;gap:5px;transition:transform .2s ease;}
.dz-rozet:hover{transform:translateY(-1px);}
/* ── HVAC / bakım listesi satırları: okunur renkler, sırayla kayarak gelir ── */
@keyframes dzGir{from{opacity:0;transform:translateX(-8px);}to{opacity:1;transform:none;}}
@keyframes dzSol{0%,100%{box-shadow:inset 3px 0 0 var(--k);}50%{box-shadow:inset 5px 0 0 var(--k), 0 0 0 3px color-mix(in srgb, var(--k) 12%, transparent);}}
.dz-satir{background:color-mix(in srgb, var(--k) 7%, #fff);border:1px solid color-mix(in srgb, var(--k) 28%, transparent);
  border-radius:10px;padding:9px 12px;margin-bottom:7px;box-shadow:inset 3px 0 0 var(--k);
  animation:dzGir .45s ease both, dzSol 2.8s ease-in-out .6s infinite;}
.dz-satir:nth-child(1){animation-delay:0.00s;}.dz-satir:nth-child(2){animation-delay:0.06s;}.dz-satir:nth-child(3){animation-delay:0.12s;}.dz-satir:nth-child(4){animation-delay:0.18s;}.dz-satir:nth-child(5){animation-delay:0.24s;}.dz-satir:nth-child(6){animation-delay:0.30s;}.dz-satir:nth-child(7){animation-delay:0.36s;}.dz-satir:nth-child(8){animation-delay:0.42s;}.dz-satir:nth-child(9){animation-delay:0.48s;}.dz-satir:nth-child(10){animation-delay:0.54s;}.dz-satir:nth-child(11){animation-delay:0.60s;}.dz-satir:nth-child(12){animation-delay:0.66s;}.dz-satir:nth-child(13){animation-delay:0.72s;}.dz-satir:nth-child(14){animation-delay:0.78s;}.dz-satir:nth-child(15){animation-delay:0.84s;}.dz-satir:nth-child(16){animation-delay:0.90s;}.dz-satir:nth-child(17){animation-delay:0.96s;}.dz-satir:nth-child(18){animation-delay:1.02s;}.dz-satir:nth-child(19){animation-delay:1.08s;}.dz-satir:nth-child(20){animation-delay:1.14s;}
.dz-satir-ad{display:flex;align-items:center;gap:8px;font-size:12.5px;font-weight:700;color:#0f1f3d;}
.dz-cip{display:inline-block;background:color-mix(in srgb, var(--k) 13%, #fff);
  border:1px solid color-mix(in srgb, var(--k) 40%, transparent);border-radius:999px;padding:2px 9px;
  margin:5px 5px 0 0;font-size:10px;font-weight:600;color:color-mix(in srgb, var(--k) 70%, #1f2937);}
.dz-not{font-size:10.5px;color:#46536b;margin-top:5px;font-style:italic;}
.dz-etiket{display:inline-flex;align-items:center;gap:5px;min-width:74px;font-size:10px;font-weight:700;
  letter-spacing:1px;color:var(--k);}

/* ── Grafik seçici: Canlı İzleme yazı stili ── */
.st-key-grafik_secim [data-baseweb="select"] > div{background:#fff !important;border:1px solid rgba(24,26,30,.12) !important;
  border-radius:12px !important;box-shadow:0 6px 16px -12px rgba(20,22,26,.3);}
.st-key-grafik_secim [data-baseweb="select"] *{font-size:13px !important;font-weight:600 !important;color:#133273 !important;}
[data-baseweb="popover"] [role="option"]{font-size:12.5px !important;font-weight:600 !important;color:#24324d !important;}
[data-baseweb="popover"] [role="option"]:hover{background:#eef3fb !important;}

/* ── Grafikler: çubuklar alttan büyür, sonra soldan sağa hafif dalga;
      çizgiler soldan sağa çizilir, noktalar atar ── */
@keyframes dzBuyu{from{transform:scaleY(0);}to{transform:scaleY(1);}}
@keyframes dzDalga{0%,100%{opacity:1;}50%{opacity:.78;}}
@keyframes dzCiz{from{stroke-dashoffset:3000;}to{stroke-dashoffset:0;}}
@keyframes dzIsik{0%,100%{filter:drop-shadow(0 0 0 rgba(42,120,214,0));}50%{filter:drop-shadow(0 0 4px rgba(42,120,214,.55));}}
@keyframes dzPop{from{transform:scale(.6);opacity:0;}to{transform:scale(1);opacity:1;}}
.js-plotly-plot .barlayer .point path{transform-box:fill-box;transform-origin:50% 100%;
  animation:dzBuyu .8s cubic-bezier(.2,.8,.2,1) both, dzDalga 3.6s ease-in-out 1s infinite;}
.js-plotly-plot .barlayer .point:nth-child(1) path{animation-delay:0.00s,1.00s;}.js-plotly-plot .barlayer .point:nth-child(2) path{animation-delay:0.03s,1.12s;}.js-plotly-plot .barlayer .point:nth-child(3) path{animation-delay:0.05s,1.24s;}.js-plotly-plot .barlayer .point:nth-child(4) path{animation-delay:0.08s,1.36s;}.js-plotly-plot .barlayer .point:nth-child(5) path{animation-delay:0.10s,1.48s;}.js-plotly-plot .barlayer .point:nth-child(6) path{animation-delay:0.12s,1.60s;}.js-plotly-plot .barlayer .point:nth-child(7) path{animation-delay:0.15s,1.72s;}.js-plotly-plot .barlayer .point:nth-child(8) path{animation-delay:0.18s,1.84s;}.js-plotly-plot .barlayer .point:nth-child(9) path{animation-delay:0.20s,1.96s;}.js-plotly-plot .barlayer .point:nth-child(10) path{animation-delay:0.23s,2.08s;}.js-plotly-plot .barlayer .point:nth-child(11) path{animation-delay:0.25s,2.20s;}.js-plotly-plot .barlayer .point:nth-child(12) path{animation-delay:0.28s,2.32s;}.js-plotly-plot .barlayer .point:nth-child(13) path{animation-delay:0.30s,2.44s;}.js-plotly-plot .barlayer .point:nth-child(14) path{animation-delay:0.33s,2.56s;}.js-plotly-plot .barlayer .point:nth-child(15) path{animation-delay:0.35s,2.68s;}.js-plotly-plot .barlayer .point:nth-child(16) path{animation-delay:0.38s,2.80s;}.js-plotly-plot .barlayer .point:nth-child(17) path{animation-delay:0.40s,2.92s;}.js-plotly-plot .barlayer .point:nth-child(18) path{animation-delay:0.43s,3.04s;}.js-plotly-plot .barlayer .point:nth-child(19) path{animation-delay:0.45s,3.16s;}.js-plotly-plot .barlayer .point:nth-child(20) path{animation-delay:0.48s,3.28s;}.js-plotly-plot .barlayer .point:nth-child(21) path{animation-delay:0.50s,3.40s;}.js-plotly-plot .barlayer .point:nth-child(22) path{animation-delay:0.53s,3.52s;}.js-plotly-plot .barlayer .point:nth-child(23) path{animation-delay:0.55s,3.64s;}.js-plotly-plot .barlayer .point:nth-child(24) path{animation-delay:0.58s,3.76s;}.js-plotly-plot .barlayer .point:nth-child(25) path{animation-delay:0.60s,3.88s;}.js-plotly-plot .barlayer .point:nth-child(26) path{animation-delay:0.62s,4.00s;}.js-plotly-plot .barlayer .point:nth-child(27) path{animation-delay:0.65s,4.12s;}.js-plotly-plot .barlayer .point:nth-child(28) path{animation-delay:0.68s,4.24s;}.js-plotly-plot .barlayer .point:nth-child(29) path{animation-delay:0.70s,4.36s;}.js-plotly-plot .barlayer .point:nth-child(30) path{animation-delay:0.73s,4.48s;}.js-plotly-plot .barlayer .point:nth-child(31) path{animation-delay:0.75s,4.60s;}.js-plotly-plot .barlayer .point:nth-child(32) path{animation-delay:0.78s,4.72s;}.js-plotly-plot .barlayer .point:nth-child(33) path{animation-delay:0.80s,4.84s;}.js-plotly-plot .barlayer .point:nth-child(34) path{animation-delay:0.83s,4.96s;}.js-plotly-plot .barlayer .point:nth-child(35) path{animation-delay:0.85s,5.08s;}.js-plotly-plot .barlayer .point:nth-child(36) path{animation-delay:0.88s,5.20s;}.js-plotly-plot .barlayer .point:nth-child(37) path{animation-delay:0.90s,5.32s;}.js-plotly-plot .barlayer .point:nth-child(38) path{animation-delay:0.93s,5.44s;}.js-plotly-plot .barlayer .point:nth-child(39) path{animation-delay:0.95s,5.56s;}.js-plotly-plot .barlayer .point:nth-child(40) path{animation-delay:0.98s,5.68s;}
.js-plotly-plot .scatterlayer .js-line{stroke-dasharray:3000;animation:dzCiz 1.8s ease-out both, dzIsik 3s ease-in-out 1.8s infinite;}
.js-plotly-plot .scatterlayer .point{transform-box:fill-box;transform-origin:50% 50%;animation:dzPop .5s ease-out 1.2s both;}
.js-plotly-plot .pielayer .slice path.surface{transform-box:view-box;animation:dzPop .7s cubic-bezier(.2,.8,.2,1) both;}
@media (prefers-reduced-motion: reduce){.dz-baslik,.dz-ust,.dz-satir,.js-plotly-plot *{animation:none !important;}}
</style>
""", unsafe_allow_html=True)
giris.giris_kapisi()

# ── CSS ──────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');
* { font-family: Inter,system-ui,-apple-system,Segoe UI,sans-serif; }
body, .stApp { font-feature-settings: "tnum" 1; -webkit-font-smoothing: antialiased; }
/* ── ARKA PLAN — app_merkez ile aynı ── */
html, body, [data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] > div:first-child,
[data-testid="stAppViewContainer"] > div:first-child > div:first-child {
    background-color: #ecebe8 !important;
    background-image: none !important;
}
[data-testid="stHeader"]          { background: transparent !important; }
[data-testid="stToolbar"]         { display: none !important; }
[data-testid="collapsedControl"],
[data-testid="stSidebarCollapsedControl"],
section[data-testid="stSidebarCollapsedControl"],
.stSidebarCollapsedControl,
button[kind="header"],
#MainMenu,
header[data-testid="stHeader"] button { display: none !important; visibility: hidden !important; }

/* ── GENEL YAZI ── */
* { font-family: Inter,system-ui,-apple-system,Segoe UI,sans-serif, 'Inter', sans-serif; }
span[data-testid="stIconMaterial"],
[data-testid="stExpanderToggleIcon"] span,
button span[data-testid="stIconMaterial"] {
    font-family: 'Material Symbols Rounded' !important;
}
p, li, span, div { color: #0f1f3d; }

/* ── SCROLLBAR ── */
::-webkit-scrollbar { width: 4px; height: 4px; }
::-webkit-scrollbar-track { background: #f1f0ed; }
::-webkit-scrollbar-thumb { background: rgba(19,50,115,0.3); border-radius: 3px; }

/* ── BÖLÜM BAŞLIĞI ── */
.sec {
    font-family: Inter,system-ui,-apple-system,Segoe UI,sans-serif;
    font-size: 10px; font-weight: 700;
    color: #133273;
    letter-spacing: 2px; text-transform: uppercase;
    padding: 4px 0 8px; margin-top: 16px;
    border-bottom: 1px solid rgba(24,26,30,0.10);
}

/* ── METRIC KART ── */
.metric-card {
    background: #fafaf8;
    border: 1px solid rgba(24,26,30,0.10);
    border-radius: 12px;
    padding: 16px;
    text-align: center;
    box-shadow: 0 1px 1px rgba(20,22,26,.05),0 10px 22px -12px rgba(20,22,26,.22),inset 0 1px 0 rgba(255,255,255,.95);
}
[data-testid="stMetricValue"]  {
    color: #2a78d6 !important;
    font-size: 22px !important;
    font-weight: 800 !important;
    font-family: Inter,system-ui,-apple-system,Segoe UI,sans-serif !important;
    
}
[data-testid="stMetricLabel"]  {
    color: #46536b !important;
    font-size: 10px !important;
    letter-spacing: 1px !important;
    text-transform: uppercase !important;
}
[data-testid="metric-container"] {
    background: #fafaf8 !important;
    border: 1px solid rgba(24,26,30,0.10) !important;
    border-radius: 12px !important;
    padding: 14px !important;
    !important;
}

/* ── TABS ── */
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: transparent;
    border-bottom: 1px solid rgba(19,50,115,0.05);
    gap: 0;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    background: transparent;
    color:rgb(150,200,255);
    font-weight: 600;
    font-size: 13px;
    border-bottom: 2px solid transparent;
    padding: 10px 20px;
    transition: color 0.2s;
}
[data-testid="stTabs"] [data-baseweb="tab"]:hover {
    color:#133273;
}
[data-testid="stTabs"] [aria-selected="true"] {
    background: transparent !important;
    color: #2a78d6 !important;
    box-shadow: inset 0 -2px 0 #2a78d6, 0 2px 8px rgba(19,50,115,0.3) !important;
}
[data-testid="stTabs"] [data-baseweb="tab-highlight"] {
    background-color: #2a78d6 !important;
    box-shadow: 0 -2px 8px rgba(19,50,115,0.5) !important;
}
[data-testid="stTabs"] [data-baseweb="tab-panel"] {
    background:#fafaf8;
    border-radius: 0 0 12px 12px;
    padding: 20px;
    border: 1px solid rgba(24,26,30,0.10);
    border-top: none;
    }

/* ── BUTONLAR ── */
.stButton > button {
    background: #fafaf8 !important;
    color: #133273 !important;
    border: 1px solid rgba(24,26,30,0.10) !important;
    border-radius: 14px !important;
    font-weight: 600 !important;
    font-family: Inter,system-ui,-apple-system,Segoe UI,sans-serif !important;
    transition: all 0.2s !important;
}
.stButton > button:hover {
    background: #f1f0ed !important;
    border-color: #133273 !important;
}

/* ── DATAFRAME ── */
.stDataFrame thead tr th {
    background: rgba(243,246,251,0.9) !important;
    color: #2a78d6 !important;
    font-weight: 700 !important;
    border-bottom: 2px solid rgba(19,50,115,0.3) !important;
}
.stDataFrame tbody tr td {
    background: #fafaf8 !important;
    color: #0f1f3d !important;
    border-bottom: 1px solid rgba(19,50,115,0.04) !important;
}
.stDataFrame tbody tr:hover td {
    background: rgba(19,50,115,0.06) !important;
}

/* ── SELECT / INPUT ── */
[data-testid="stSelectbox"] > div > div,
[data-testid="stDateInput"] input,
[data-testid="stNumberInput"] input {
    background: #fafaf8 !important;
    color: #0f1f3d !important;
    border: 1px solid rgba(19,50,115,0.2) !important;
    border-radius: 8px !important;
}

/* ── EXPANDER ── */
[data-testid="stExpander"] {
    background: #fafaf8 !important;
    border: 1px solid rgba(24,26,30,0.10) !important;
    border-radius: 14px !important;
}
[data-testid="stExpanderToggleIcon"] { color:#133273 !important; }

/* ── AYIRICI ── */
hr { border-color:#133273 !important; }

/* ── UYARI / INFO KUTUSU ── */
[data-testid="stAlert"] {
    background: rgba(243,246,251,0.5) !important;
    border: 1px solid rgba(19,50,115,0.2) !important;
    border-radius: 14px !important;
    color: #0f1f3d !important;
}
</style>
""", unsafe_allow_html=True)


# ── Lokasyon bilgileri (app_merkez.py ile senkron) ───────
HASTANELER = {
    # ── İstanbul ──
    "maslak":        {"isim": "Acıbadem Maslak",         "kisa": "MASLAK",       "m2": 15000, "renk": "#2a78d6"},
    "altunizade":    {"isim": "Acıbadem Altunizade",     "kisa": "ALTUNİZADE",   "m2": 10000, "renk": "#c98500"},
    "kozyatagi":     {"isim": "Acıbadem Kozyatağı",      "kisa": "KOZYATAĞİ",   "m2": 12000, "renk": "#0ca30c"},
    "taksim":        {"isim": "Acıbadem Taksim",         "kisa": "TAKSİM",       "m2":  8000, "renk": "#4a3aa7"},
    "atakent":       {"isim": "Acıbadem Atakent",        "kisa": "ATAKENT",      "m2": 20000, "renk": "#eb6834"},
    "atasehir":      {"isim": "Acıbadem Ataşehir",       "kisa": "ATAŞEHİR",     "m2": 14000, "renk": "#256abf"},
    "bakirkoy":      {"isim": "Acıbadem Bakırköy",       "kisa": "BAKIRKÖY",     "m2": 12000, "renk": "#84cc16"},
    "fulya":         {"isim": "Acıbadem Fulya",          "kisa": "FULYA",        "m2":  9000, "renk": "#e87ba4"},
    "international": {"isim": "Acıbadem International",  "kisa": "INTERNAT.",    "m2": 18000, "renk": "#14b8a6"},
    "kadikoy":       {"isim": "Acıbadem Kadıköy",        "kisa": "KADİKÖY",      "m2":  8000, "renk": "#ec4899"},
    "kartal":        {"isim": "Acıbadem Kartal",         "kisa": "KARTAL",       "m2": 11000, "renk": "#d03b3b"},
    # ── Ankara ──
    "ankara":          {"isim": "Acıbadem Ankara",           "kisa": "ANKARA",      "m2": 16000, "renk": "#fb7185"},
    "bayindir":        {"isim": "Acıbadem Bayındır Söğütözü", "kisa": "BAYINDIR",    "m2": 12000, "renk": "#f43f5e"},
    # ── Bursa ──
    "bursa":           {"isim": "Acıbadem Bursa",             "kisa": "BURSA",       "m2": 13000, "renk": "#c98500"},
    # ── Kocaeli ──
    "kocaeli":         {"isim": "Acıbadem Kocaeli",           "kisa": "KOCAELİ",     "m2": 10000, "renk": "#0ca30c"},
    # ── Eskişehir ──
    "eskisehir":       {"isim": "Acıbadem Eskişehir",         "kisa": "ESKİŞEHİR",   "m2":  9000, "renk": "#818cf8"},
    # ── İzmir ──
    "izmir":           {"isim": "Acıbadem İzmir Kent",        "kisa": "İZMİR",       "m2": 15000, "renk": "#2a78d6"},
    # ── Kayseri ──
    "kayseri":         {"isim": "Acıbadem Kayseri",           "kisa": "KAYSERİ",     "m2": 11000, "renk": "#a78bfa"},
    # ── Adana ──
    "adana":           {"isim": "Acıbadem Adana",             "kisa": "ADANA",       "m2": 12000, "renk": "#f472b6"},
    "adana_ortopedia": {"isim": "Acıbadem Adana Ortopedia",   "kisa": "ADANA ORT.",  "m2":  5000, "renk": "#e87ba4"},
    # ── Bodrum ──
    "bodrum":          {"isim": "Acıbadem Bodrum",            "kisa": "BODRUM",      "m2":  7000, "renk": "#2dd4bf"},
}

# ── Config & Lokasyon seç ────────────────────────────
CONFIG_FILE = os.path.join(os.path.dirname(os.path.dirname(__file__)), "configs", "merkez_config.json")

def _demo_modu() -> bool:
    """Sunum modu açık mı? app_merkez._demo_modu ile aynı kural."""
    if os.environ.get("SYNAPSE_DEMO", "").strip() == "1":
        return True
    try:
        return str(st.secrets.get("demo", {}).get("aktif", "")).lower() in ("1", "true", "evet")
    except Exception:
        return False


def load_config():
    # ── SUNUM/DEMO MODU ──
    # Bu sayfa ana sayfadan BAĞIMSIZ olarak kendi config'ini okuyordu; demo
    # modunu bilmediği için canlı Supabase adresine bağlanmaya çalışıyor ve
    # "Bu lokasyon için veri bulunamadı" diyordu. Ayrıca st.secrets'a
    # dokunduğu için sunumda "No secrets found" uyarısı görünüyordu.
    # Artık ana sayfayla aynı örnek veri sunucusunu kullanır.
    if _demo_modu():
        import sys as _sys
        _sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        import _sim_sunucu
        return {"supabase_url": _sim_sunucu.sunucu_baslat(8099),
                "supabase_key": "simulasyon"}

    # Harici simülasyon sunucusu (SUNUM_BASLAT.bat ile yerel kullanım)
    _sim = os.environ.get("SYNAPSE_SIM_URL", "").strip()
    if _sim:
        return {"supabase_url": _sim, "supabase_key": "simulasyon"}

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

lok_id = st.session_state.get("detay_lokasyon", None)
if not lok_id or lok_id not in HASTANELER:
    st.error("Lokasyon seçilmedi. Ana sayfaya dönün.")
    if st.button("⬅ Ana Sayfaya Dön"):
        st.session_state.pop("detay_lokasyon", None)
        st.switch_page(_ANA_SAYFA)
    st.stop()

lok_info = HASTANELER[lok_id]
renk     = lok_info["renk"]

# m² — önce Supabase ayarlar tablosundan al, yoksa HASTANELER dict'indeki sabit değer
@st.cache_data(ttl=60, show_spinner=False)
def fetch_m2_detay(url, key):
    try:
        from supabase import create_client
        import json as _j
        c = create_client(url, key)
        r = c.table("ayarlar").select("value").eq("key", "m2_degerler").execute()
        if r.data:
            return _j.loads(r.data[0]["value"])
    except Exception:
        pass
    return {}

_m2_sb = fetch_m2_detay(url, key)
m2 = int(_m2_sb.get(lok_id, lok_info.get("m2", 10000)))

rr = int(renk[1:3],16); rg = int(renk[3:5],16); rb = int(renk[5:7],16)

# ── Veri çek ────────────────────────────────────────
@st.cache_data(ttl=120, show_spinner=False)
def fetch_lok_data(url, key, lok_id):
    try:
        from supabase import create_client
        c = create_client(url, key)
        all_data = []
        offset = 0
        batch = 1000
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
                if col not in ["id","lokasyon_id","Tarih","Kar_Eritme_Aktif"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            # Aynı tarihte birden fazla kayıt varsa en son kaydı tut
            df = df.drop_duplicates(subset=["Tarih"], keep="last")
            df = df.sort_values("Tarih").reset_index(drop=True)
            return df
    except:
        pass
    return pd.DataFrame()

@st.cache_data(ttl=120, show_spinner=False)
def fetch_tum_lokasyonlar_debug(url, key):
    """Supabase'deki tüm lokasyon_id ve kayıt sayılarını döndür (debug, sayfalama ile)."""
    try:
        from supabase import create_client
        c = create_client(url, key)
        all_data = []
        offset = 0
        batch = 1000
        while True:
            r = c.table("energy_data").select("lokasyon_id,Tarih").order("Tarih", desc=False).range(offset, offset + batch - 1).execute()
            if not r.data:
                break
            all_data.extend(r.data)
            if len(r.data) < batch:
                break
            offset += batch
        if all_data:
            import pandas as _pd
            _df = _pd.DataFrame(all_data)
            _df["Tarih"] = _pd.to_datetime(_df["Tarih"], errors="coerce")
            return _df.groupby("lokasyon_id").agg(
                Kayit=("Tarih","count"),
                IlkTarih=("Tarih","min"),
                SonTarih=("Tarih","max")
            ).reset_index()
    except:
        pass
    return pd.DataFrame()

df = fetch_lok_data(url, key, lok_id)

# ── HVAC / Bakım verisi çek ─────────────────────────
@st.cache_data(ttl=60, show_spinner=False)
def fetch_bakim_data(url, key, lok_id):
    """lokasyonlar tablosundan bakim_ozet ve hvac_ozet verisini çek."""
    try:
        from supabase import create_client
        c = create_client(url, key)
        r = c.table("lokasyonlar").select("*").eq("lokasyon_id", lok_id).execute()
        if r.data:
            return r.data[0]
    except Exception:
        pass
    return {}

lok_row   = fetch_bakim_data(url, key, lok_id)
bakim_ozet = lok_row.get("bakim_ozet") or {}
if isinstance(bakim_ozet, str):
    try:    bakim_ozet = json.loads(bakim_ozet)
    except: bakim_ozet = {}

hvac_ozet = lok_row.get("hvac_ozet") or {}
if isinstance(hvac_ozet, str):
    try:    hvac_ozet = json.loads(hvac_ozet)
    except: hvac_ozet = {}

now = datetime.now()
dun = (now - timedelta(days=1)).strftime("%Y-%m-%d")

# En son mevcut tarihi bul (dün yoksa geriye doğru en yakın tarih)
if not df.empty:
    son_tarih = df["Tarih"].dropna().max()
    son_tarih_str = son_tarih.strftime("%Y-%m-%d")
else:
    son_tarih_str = dun

# ── Header ───────────────────────────────────────────
_bagli = not df.empty
_bagli_html = (
    f"<span style='background:rgba(12,163,12,0.15);border:1px solid rgba(12,163,12,0.35);"
    f"border-radius:6px;padding:2px 10px;font-size:10px;color:#0ca30c;font-weight:600;' class='dz-rozet'>"
    + _ik.nokta("#0ca30c", 8) + "Bağlı</span>"
    if _bagli else
    f"<span style='background:rgba(208,59,59,0.15);border:1px solid rgba(208,59,59,0.35);"
    f"border-radius:6px;padding:2px 10px;font-size:10px;color:#d03b3b;font-weight:600;' class='dz-rozet'>"
    + _ik.nokta("#d03b3b", 8) + "Veri Yok</span>"
)
_son_tarih_goster = son_tarih_str if _bagli else "—"
_m2_goster = f"{m2:,.0f}".replace(",", ".")

col_geri, col_baslik = st.columns([1, 9])
with col_geri:
    st.markdown("<style>" + _ik.etiket_css(".st-key-detay_geri button p", "geri", 15)
                + "</style>", unsafe_allow_html=True)
    if st.button("Geri", key="detay_geri"):
        st.session_state.pop("detay_lokasyon", None)
        st.switch_page(_ANA_SAYFA)
with col_baslik:
    st.markdown(
        f"""<div style='display:flex;align-items:center;justify-content:space-between;padding:8px 0;flex-wrap:wrap;gap:8px;'>
          <div>
            <div class='dz-ust' style='font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;font-size:8px;color:#2a78d6;
                        letter-spacing:5px;text-transform:uppercase;'>ACIBADEM SAĞLIK GRUBU — LOKASYON DETAY</div>
            <div class='dz-baslik' style='--r:{renk};font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;font-size:22px;font-weight:900;
                        color:{renk};letter-spacing:3px;'>{lok_info["isim"].upper()}</div>
          </div>
          <div style='display:flex;gap:8px;align-items:center;flex-wrap:wrap;'>
            <span class='dz-rozet' style='background:rgba({rr},{rg},{rb},0.1);border:1px solid rgba({rr},{rg},{rb},0.3);
                         border-radius:6px;padding:2px 10px;font-size:10px;color:{renk};font-weight:600;'>
              {_ik.ikon("verim", 13, renk)} {_m2_goster} m²
            </span>
            <span class='dz-rozet' style='background:rgba(42,120,214,0.08);border:1px solid rgba(42,120,214,0.2);
                         border-radius:6px;padding:2px 10px;font-size:10px;color:#2a78d6;font-weight:600;'>
              {_ik.ikon("takvim", 13, "#2a78d6")} Son: {_son_tarih_goster}
            </span>
            {_bagli_html}
          </div>
        </div>""",
        unsafe_allow_html=True
    )

st.markdown("<div style='height:1px;background:rgba(19,50,115,0.1);margin:8px 0 16px;'></div>", unsafe_allow_html=True)

if df.empty:
    st.warning("Bu lokasyon için veri bulunamadı.")
    st.stop()

# ── SEKMELER ─────────────────────────────────────────
# Trend & Tahmin, Veri Tablosu ve Rapor Oluştur sekmeleri kaldırıldı (22.10.2026).
st.markdown("<style>"
            + _ik.etiket_css('.st-key-detay_sekmeler [role="tab"]:nth-child(1) p', "grafik", 16)
            + _ik.etiket_css('.st-key-detay_sekmeler [role="tab"]:nth-child(2) p', "enerji", 16)
            + "</style>", unsafe_allow_html=True)
with st.container(key="detay_sekmeler"):
    tab1, tab_canli = st.tabs(["Dashboard", "Canlı İzleme"])

# Dış bağlantıyla gelindiyse (?detay=..&sekme=canli) Canlı İzleme sekmesini aç.
# Streamlit sekmeyi koddan seçtirmiyor; sekme düğmesine bir kez tıklatılır.
# Bayrak hemen silinir: 10 sn'lik yenilemelerde kullanıcı başka sekmeye
# geçtiyse geri zorlanmaz (Streamlit seçili sekmeyi yenilemede korur).
if st.session_state.pop("detay_sekme", None) == "canli":
    import streamlit.components.v1 as _sekme_cv1
    _sekme_cv1.html("""
<script>
(function () {
  var deneme = 0;
  function ac() {
    var d;
    try { d = window.parent.document; } catch (e) { return; }
    // Eski Streamlit: [data-baseweb="tab"], yeni (1.5x+): [data-testid="stTab"] / role="tab"
    var sekmeler = d.querySelectorAll(
      '[data-testid="stTabs"] [data-baseweb="tab"], [data-testid="stTab"], [data-testid="stTabs"] [role="tab"]');
    for (var i = 0; i < sekmeler.length; i++) {
      if ((sekmeler[i].innerText || '').indexOf('Canlı İzleme') !== -1) {
        sekmeler[i].click();
        return;
      }
    }
    if (++deneme < 40) { setTimeout(ac, 150); }   // sekmeler henüz çizilmediyse bekle
  }
  ac();
})();
</script>
""", height=0)

# ════════ TAB 1: DASHBOARD ════════
with tab1:
    son_tarih_dt = pd.to_datetime(son_tarih_str)

    # Grafik için kayan pencere (son 30 gün)
    son30_bas = son_tarih_dt - timedelta(days=29)
    son30 = df[(df["Tarih"] >= son30_bas) & (df["Tarih"] <= son_tarih_dt)].copy()
    son7  = df[(df["Tarih"] >= son_tarih_dt - timedelta(days=6)) & (df["Tarih"] <= son_tarih_dt)].copy()
    son_df = df[df["Tarih"].dt.strftime("%Y-%m-%d") == son_tarih_str]  # en son mevcut gün

    # ── AY BAZLI TOPLAM (kart için) ───────────────────
    # Son tarihin ayının 1'inden son veriye kadar — ay kaç günse o kadar alır
    ay_bas_dt  = son_tarih_dt.replace(day=1)
    bu_ay_df   = df[(df["Tarih"] >= ay_bas_dt) & (df["Tarih"] <= son_tarih_dt)].copy()
    kwh_bu_ay  = bu_ay_df["Toplam_Hastane_Tuketim_kWh"].sum() \
                 if "Toplam_Hastane_Tuketim_kWh" in bu_ay_df.columns else 0
    ay_gun_sayi = len(bu_ay_df["Tarih"].dt.date.unique()) if not bu_ay_df.empty else 0
    ay_bas_str  = ay_bas_dt.strftime("%d %b %Y")
    ay_bit_str  = son_tarih_dt.strftime("%d %b %Y")
    ay_adi      = son_tarih_dt.strftime("%B %Y")   # örn: "Nisan 2026"

    # Özet değerler
    kwh_dun    = son_df["Toplam_Hastane_Tuketim_kWh"].sum() if "Toplam_Hastane_Tuketim_kWh" in son_df.columns else 0
    kwh_30     = son30["Toplam_Hastane_Tuketim_kWh"].sum() if "Toplam_Hastane_Tuketim_kWh" in son30.columns else 0
    verim_dun  = kwh_dun / m2 if kwh_dun and m2 else 0
    ch_set     = son_df["Chiller_Set_Temp_C"].mean() if "Chiller_Set_Temp_C" in son_df.columns else None
    kojen_gaz  = son_df["Kojen_Dogalgaz_m3"].sum() if "Kojen_Dogalgaz_m3" in son_df.columns else None
    kojen_urt  = son_df["Kojen_Uretim_kWh"].sum() if "Kojen_Uretim_kWh" in son_df.columns else None
    kazan_gaz  = son_df["Kazan_Dogalgaz_m3"].sum() if "Kazan_Dogalgaz_m3" in son_df.columns else None
    su_tuk     = son_df["Su_Tuketimi_m3"].sum() if "Su_Tuketimi_m3" in son_df.columns else None
    sebeke_tuk = son_df["Sebeke_Tuketim_kWh"].sum() if "Sebeke_Tuketim_kWh" in son_df.columns else None
    mcc_tuk    = son_df["MCC_Tuketim_kWh"].sum() if "MCC_Tuketim_kWh" in son_df.columns else None
    # Soğutma: önce hazır sütunu dene, yoksa Chiller'ı kullan
    _sog_col   = "Toplam_Sogutma_Tuketim_kWh" if "Toplam_Sogutma_Tuketim_kWh" in son_df.columns \
                 else ("Chiller_Tuketim_kWh" if "Chiller_Tuketim_kWh" in son_df.columns else None)
    sog_tuk    = son_df[_sog_col].sum() if _sog_col else None

    # ── 2 SÜTUN LAYOUT — sol KPI + sağ grafik ─────────
    col_left, col_mid = st.columns([1.6, 5.4])

    # ──────────── SÜTUN 1: Stacked metrik kartlar ────────────
    with col_left:
        st.markdown('<div class="sec" style="display:flex;align-items:center;gap:6px;">'
                    + _ik.ikon("enerji", 15) + 'ÖZET</div>', unsafe_allow_html=True)

        def metric_card_v(ikon, baslik, deger, birim, renk_hex, alt_bilgi=""):
            r2=int(renk_hex[1:3],16); g2=int(renk_hex[3:5],16); b2=int(renk_hex[5:7],16)
            alt_html = f"<div class='dz-alt'>{alt_bilgi}</div>" if alt_bilgi else ""
            st.markdown(
                f"""<div class="dz-kart" style="margin-bottom:8px;display:flex;align-items:center;gap:12px;">
                {_ik.ikon(ikon, 28)}
                <div style='min-width:0;'>
                  <div class='dz-et'>{baslik}</div>
                  <div class='dz-dg'>{deger}<span class='dz-br'>{birim}</span></div>{alt_html}
                </div></div>""",
                unsafe_allow_html=True
            )

        metric_card_v("enerji", f"Tüketim ({son_tarih_str})", f"{kwh_dun:,.0f}", "kWh", "#2a78d6")
        metric_card_v("verim", "kWh/m²",     f"{verim_dun:.2f}", "kWh/m²", "#c98500")
        metric_card_v(
            "takvim", f"{ay_adi} Toplam",
            f"{kwh_bu_ay:,.0f}", "kWh", "#0ca30c",
            alt_bilgi=f"{ay_bas_str} → {ay_bit_str}  ({ay_gun_sayi} gün)"
        )
        metric_card_v("chiller", "Chiller Set", f"{ch_set:.1f}" if ch_set else "—", "°C", "#4a3aa7")

        # Soğutma tüketimi
        if sog_tuk is not None and sog_tuk > 0:
            metric_card_v("sogutma", "Soğutma Tüketimi", f"{sog_tuk:,.0f}", "kWh", "#2a78d6")

        # Kojen öz tüketim oranı
        if kojen_urt and kwh_dun and kwh_dun > 0:
            kojen_oran = min(kojen_urt / kwh_dun * 100, 100)
            metric_card_v("kojen", "Kojen Karşılama", f"{kojen_oran:.1f}", "%", "#0ca30c")


    # ──────────── SÜTUN 2: Grafik seçici + dinamik grafik ────────────
    with col_mid:
        st.markdown('<div class="sec">📊 GRAFİK</div>', unsafe_allow_html=True)

        # ── Grafik listesi KATEGORİLERE ayrılmış (başlık · simge · ad · birim) ──
        # Trafolar (TRDP) yalnızca sayacı bağlı lokasyonda listelenir (bugün
        # yalnızca Maslak); boş grafik açacak ölü seçenek gösterilmez.
        _trafo_kolonlar = sorted(
            [c for c in df.columns if re.fullmatch(r"TRDP\d+_kWh", str(c))
             and pd.to_numeric(df[c], errors="coerce").fillna(0).sum() > 0],
            key=lambda c: int(re.findall(r"\d+", c)[0]))
        _GRAFIK_GRUPLARI = [
            ("SU & ENERJİ KAYNAKLARI", [
                ("Su Tüketimi", "su", "m³"),
                ("Tüketim", "tuketim", "kWh"),
                ("Şebeke Tüketimi", "sebeke", "kWh"),
            ] + ([("Trafolar (TRDP)", "trafo", "kWh")] if _trafo_kolonlar else [])),
            ("KOJENERASYON & GAZ SİSTEMLERİ", [
                ("Kojen Üretim", "kojen", "kWh · m³"),
                ("Kazan Doğalgaz", "kazan", "m³"),
            ]),
            ("SOĞUTMA & MEKANİK SİSTEMLER", [
                ("Chiller Set Trendi", "chiller", "°C"),
                ("Soğutma Tüketimi", "sogutma", "kWh"),
                ("MCC Tüketimi", "mcc", "kWh"),
                ("kWh/m² Trendi", "verimlilik", "kWh/m²"),
            ]),
            ("ÖZET & KARŞILAŞTIRMA", [
                ("Bu Ay vs Geçen Ay", "ay_karsilastir", "kWh"),
                ("KPI Özet", "kpi_ozet", "tablo"),
                ("Enerji Kırılımı", "enerji_kirilim", "%"),
            ]),
        ]
        grafik_secenekler = {_ad: _t for _, _ogeler in _GRAFIK_GRUPLARI for _ad, _t, _ in _ogeler}
        _GRAFIK_BIRIM = {_t: _b for _, _ogeler in _GRAFIK_GRUPLARI for _, _t, _b in _ogeler}
        # Her grafiğin simgesi — Dashboard kartlarındakiyle AYNI (ikonlar.py)
        _GRAFIK_IKON = {"tuketim": "enerji", "chiller": "sogutma", "verimlilik": "verim",
                        "sogutma": "sogutma", "su": "su", "kojen": "kojen", "sebeke": "sebeke",
                        "mcc": "mcc", "kazan": "kazan", "ay_karsilastir": "takvim",
                        "kpi_ozet": "kayit", "enerji_kirilim": "grafik", "trafo": "trdp"}

        # Lokasyon değişince önceki seçim bu listede olmayabilir (ör. Maslak'ta
        # trafo grafiği seçiliyken trafosuz lokasyona geçmek); Streamlit böyle
        # bir durumda hata veriyor.
        if st.session_state.get("grafik_sec") not in grafik_secenekler:
            st.session_state.pop("grafik_sec", None)

        # ── Grafik seçici + Tarih aralığı (yan yana) ──
        _gc1, _gc2, _gc3 = st.columns([3, 1.5, 1.5])
        # Streamlit 1.5x+: liste sayfanın dibinde ayrı katmanda açılır
        # (stSelectboxVirtualDropdown), seçenekler data-key ile sıralıdır.
        # Yalnızca bu seçicinin listesi 12+ seçenekli → data-key="11" ile ayırt edilir.
        # Satır düzeni: [kategori başlığı (grubun ilk satırında)] / simge · ad · birim
        _gs_list = list(grafik_secenekler.items())
        _L = '[data-testid="stSelectboxVirtualDropdown"]:has([data-key="11"])'
        _ilk = {}
        _sira = 0
        for _baslik, _ogeler in _GRAFIK_GRUPLARI:
            _ilk[_sira] = _baslik
            _sira += len(_ogeler)
        _gs_css = (
            _L + ' [role="listbox"]{max-height:470px !important;overflow-y:auto !important;padding:4px 8px 8px;}'
            + _L + '{max-height:520px !important;}'
            + _L + ' [role="option"]{display:flex !important;flex-wrap:wrap;align-items:center;height:auto !important;'
              'min-height:38px;padding:1px 0 !important;background:transparent !important;}'
            + _L + ' [role="option"] > div{flex:1 1 auto;display:flex;align-items:center;min-height:36px;'
              'padding:0 10px;border-radius:8px;font-size:12.5px;font-weight:600;color:#24324d;}'
            + _L + ' [role="option"]:hover > div, ' + _L + ' [role="option"][data-focused="true"] > div'
              '{background:#f3f6fb;}'
            + _L + ' [role="option"][aria-selected="true"] > div{background:#eef3fb;color:#133273;'
              'box-shadow:inset 3px 0 0 #2a78d6;}'
            + _L + ' [role="option"] > div::after{margin-left:auto;padding-left:12px;font-family:ui-monospace,'
              'SFMono-Regular,Menlo,monospace;font-size:10.5px;font-weight:600;color:#8b97ab;}'
        )
        for _i, (_ad, _t) in enumerate(_gs_list):
            _sec = _L + ' [role="option"][data-key="%d"]' % _i
            _gs_css += _ik.etiket_css(_sec + " > div", _GRAFIK_IKON.get(_t, "grafik"), 16)
            _gs_css += _sec + ' > div::after{content:"%s";}' % _GRAFIK_BIRIM.get(_t, "")
            if _i in _ilk:
                _gs_css += (_sec + '::before{content:"%s";flex:0 0 100%%;order:-1;padding:%dpx 10px 5px;'
                            'font-size:10.5px;font-weight:800;letter-spacing:1.1px;color:#8b97ab;}'
                            % (_ilk[_i], 6 if _i == 0 else 12))
        _secili_t = grafik_secenekler.get(st.session_state.get("grafik_sec"), "tuketim")
        # Seçili değerin önündeki simge (kutu bir <input> olduğu için grubuna konur)
        _gs_css += _ik.etiket_css('.st-key-grafik_secim [data-testid="stSelectbox"] [role="group"]',
                                  _GRAFIK_IKON.get(_secili_t, "grafik"), 17)
        st.markdown("<style>" + _gs_css
                    + '.st-key-grafik_secim [data-testid="stSelectbox"] [role="group"]'
                      '{display:flex;align-items:center;padding-left:12px;background:#fff;border-radius:12px;}'
                    + '.st-key-grafik_secim [data-testid="stSelectbox"] input{font-size:13px !important;'
                      'font-weight:600 !important;color:#133273 !important;}'
                    + "</style>", unsafe_allow_html=True)
        with _gc1:
          with st.container(key="grafik_secim"):
            secim = st.selectbox(
                "Grafik Seçin", list(grafik_secenekler.keys()),
                index=list(grafik_secenekler.keys()).index("Tüketim"),   # varsayılan: Tüketim
                key="grafik_sec", label_visibility="collapsed"
            )
        with _gc2:
            tarih_bas = st.date_input(
                "Başlangıç", value=ay_bas_dt.date(),
                key="grafik_bas", label_visibility="collapsed"
            )
        with _gc3:
            tarih_bit = st.date_input(
                "Bitiş", value=son_tarih_dt.date(),
                key="grafik_bit", label_visibility="collapsed"
            )
        grafik_tip = grafik_secenekler[secim]

        # ── Sütunların İÇİ hareketli: her kaleme özel akan desen ──────────────
        # Çubuklar alttan büyüyerek gelir (CSS), ardından içleri kalemin kendi
        # efektiyle akar: tüketim → çapraz akım, su → dalga, soğutma → buzlu
        # parıltı, şebeke → şimşek, MCC → pano ışıkları, kazan → alev,
        # kojen → yukarı akan oklar, trafolar → her trafo kendi renginde akım.
        # Desenler sayfaya bir kez gömülen SVG <defs> içindedir (SMIL animasyon);
        # çubuğun dolgusu CSS ile bu desene bağlanır. Saydamlık Plotly'den gelir.
        def _desen_svg(did, efekt, c):
            beyaz = "#ffffff"
            if efekt == "akim":
                return (f"<pattern id='{did}' width='16' height='16' patternUnits='userSpaceOnUse'>"
                        f"<rect width='16' height='16' fill='{c}'/>"
                        f"<path d='M-4 20 L20 -4 M-4 4 L4 -4 M12 20 L20 12' stroke='{beyaz}' stroke-opacity='.26' stroke-width='5'/>"
                        "<animateTransform attributeName='patternTransform' type='translate' from='0 0' to='0 -16' dur='0.9s' repeatCount='indefinite'/></pattern>")
            if efekt == "dalga":
                return (f"<pattern id='{did}' width='40' height='18' patternUnits='userSpaceOnUse'>"
                        f"<rect width='40' height='18' fill='{c}'/>"
                        f"<path d='M0 7 Q10 2 20 7 T40 7' fill='none' stroke='{beyaz}' stroke-opacity='.38' stroke-width='2.2'/>"
                        f"<path d='M0 14 Q10 10 20 14 T40 14' fill='none' stroke='{beyaz}' stroke-opacity='.18' stroke-width='1.6'/>"
                        f"<circle cx='8' cy='11' r='1.2' fill='{beyaz}' fill-opacity='.45'/><circle cx='29' cy='4' r='0.9' fill='{beyaz}' fill-opacity='.4'/>"
                        "<animateTransform attributeName='patternTransform' type='translate' from='0 0' to='-40 -18' dur='3s' repeatCount='indefinite'/></pattern>")
            if efekt == "buz":
                return (f"<linearGradient id='{did}' x1='0' y1='0' x2='0' y2='1' spreadMethod='repeat'>"
                        f"<stop offset='0' stop-color='{c}'/><stop offset='.42' stop-color='{c}'/>"
                        f"<stop offset='.5' stop-color='#d6e9ff'/><stop offset='.58' stop-color='{c}'/><stop offset='1' stop-color='{c}'/>"
                        "<animateTransform attributeName='gradientTransform' type='translate' from='0 -1' to='0 1' dur='2.6s' repeatCount='indefinite'/></linearGradient>")
            if efekt == "elektrik":
                return (f"<pattern id='{did}' width='14' height='18' patternUnits='userSpaceOnUse'>"
                        f"<rect width='14' height='18' fill='{c}'/>"
                        f"<path d='M8 0 L3.5 8 L9.5 9.5 L5 18' fill='none' stroke='{beyaz}' stroke-opacity='.5' stroke-width='1.6'>"
                        "<animate attributeName='stroke-opacity' values='.15;.65;.2;.55;.15' dur='0.8s' repeatCount='indefinite'/></path>"
                        "<animateTransform attributeName='patternTransform' type='translate' from='0 0' to='0 -18' dur='0.7s' repeatCount='indefinite'/></pattern>")
            if efekt == "led":
                return (f"<pattern id='{did}' width='12' height='10' patternUnits='userSpaceOnUse'>"
                        f"<rect width='12' height='10' fill='{c}'/>"
                        f"<rect y='6' width='12' height='2.4' fill='{beyaz}' fill-opacity='.3'>"
                        "<animate attributeName='fill-opacity' values='.08;.4;.08' dur='1.2s' repeatCount='indefinite'/></rect>"
                        "<animateTransform attributeName='patternTransform' type='translate' from='0 0' to='0 -10' dur='1.4s' repeatCount='indefinite'/></pattern>")
            if efekt == "alev":
                return (f"<linearGradient id='{did}' x1='0' y1='0' x2='0' y2='1' spreadMethod='reflect'>"
                        "<stop offset='0' stop-color='#f59e0b'/><stop offset='.35' stop-color='#eb6834'/>"
                        f"<stop offset='.7' stop-color='{c}'/><stop offset='1' stop-color='#9f1d1d'/>"
                        "<animateTransform attributeName='gradientTransform' type='translate' values='0 0;0 -0.18;0 0.05;0 0' dur='1.3s' repeatCount='indefinite'/></linearGradient>")
            if efekt == "uretim":
                return (f"<pattern id='{did}' width='20' height='14' patternUnits='userSpaceOnUse'>"
                        f"<rect width='20' height='14' fill='{c}'/>"
                        f"<path d='M3 11 L10 5 L17 11' fill='none' stroke='{beyaz}' stroke-opacity='.36' stroke-width='2.4' stroke-linecap='round'/>"
                        "<animateTransform attributeName='patternTransform' type='translate' from='0 0' to='0 -14' dur='1.1s' repeatCount='indefinite'/></pattern>")
            return ""

        _TR_RENK = ["#4a3aa7", "#256abf", "#c98500", "#0ca30c", "#d03b3b", "#6da7ec"]
        _EFEKT = {   # grafik → [(efekt, renk) — çubuk serisi sırasıyla]
            "tuketim":        [("akim", renk)],
            "su":             [("dalga", "#0ea5e9")],
            "sogutma":        [("buz", "#2a78d6")],
            "sebeke":         [("elektrik", "#4a3aa7")],
            "mcc":            [("led", "#eb6834")],
            "kazan":          [("alev", "#d03b3b")],
            "kojen":          [("uretim", "#0ca30c")],
            "trafo":          [("akim", _c) for _c in _TR_RENK],
            "ay_karsilastir": [("akim", renk + "66"), ("akim", renk)],
        }.get(grafik_tip, [])
        if _EFEKT:
            _defs = "".join(_desen_svg("dz_%s_%d" % (grafik_tip, _i), _e, _c)
                            for _i, (_e, _c) in enumerate(_EFEKT))
            _kural = "".join(
                '[data-testid="stColumn"]:has(.st-key-grafik_secim) .js-plotly-plot .barlayer '
                '.trace:nth-child(%d) .point path{fill:url(#dz_%s_%d) !important;}' % (_i + 1, grafik_tip, _i)
                for _i in range(len(_EFEKT)))
            st.markdown(
                "<svg width='0' height='0' style='position:absolute;width:0;height:0;overflow:hidden' aria-hidden='true'>"
                "<defs>" + _defs + "</defs></svg><style>" + _kural + "</style>",
                unsafe_allow_html=True)

        # Seçilen tarih aralığına göre filtrele
        secili_df = df[
            (df["Tarih"].dt.date >= tarih_bas) &
            (df["Tarih"].dt.date <= tarih_bit)
        ].copy()
        tarih_aralik_str = (
            f"{pd.Timestamp(tarih_bas).strftime('%d %b')} → "
            f"{pd.Timestamp(tarih_bit).strftime('%d %b %Y')}"
        )

        def _bar_chart(veri_df, baslik=""):
            """Günlük tüketim bar grafiği — verilen df ile çizer."""
            if "Toplam_Hastane_Tuketim_kWh" not in veri_df.columns or veri_df.empty:
                st.info("Tüketim verisi bulunamadı.")
                return
            if baslik:
                st.caption(baslik)
            gun_df = veri_df.groupby(veri_df["Tarih"].dt.date)["Toplam_Hastane_Tuketim_kWh"].sum().reset_index()
            gun_df.columns = ["Tarih", "kWh"]
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=gun_df["Tarih"], y=gun_df["kWh"],
                marker=dict(
                    color=gun_df["kWh"],
                    colorscale=[[0, f"rgba({rr},{rg},{rb},0.4)"], [1, f"rgba({rr},{rg},{rb},0.95)"]],
                    showscale=False,
                ),
                hovertemplate="<b>%{x}</b><br>%{y:,.0f} kWh<extra></extra>",
            ))
            fig.update_layout(
                paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#24324d", family="Inter,system-ui,-apple-system,Segoe UI,sans-serif"),
                margin=dict(t=4, b=20, l=50, r=10), height=355,
                xaxis=dict(gridcolor="rgba(19,50,115,0.07)", showgrid=True),
                yaxis=dict(gridcolor="rgba(19,50,115,0.07)", showgrid=True,
                           title=dict(text="kWh", font=dict(size=10))),
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # ── Geçen Yıl Aynı Dönem Karşılaştırma Badge'i (sadece 5 grafik için) ──
        def _yoy_badge(col, s_df, full_df, t_bas, t_bit):
            """Seçilen dönem ile geçen yıl aynı dönem arasındaki % farkı renkli badge olarak döndür."""
            if col not in full_df.columns or s_df.empty:
                return ""
            bugun_val = s_df[col].sum()
            gec_bas = pd.Timestamp(t_bas) - pd.DateOffset(years=1)
            gec_bit = pd.Timestamp(t_bit) - pd.DateOffset(years=1)
            gec_df = full_df[(full_df["Tarih"] >= gec_bas) & (full_df["Tarih"] <= gec_bit)]
            if gec_df.empty or gec_df[col].sum() == 0:
                return ""
            gec_val = gec_df[col].sum()
            fark = (bugun_val - gec_val) / gec_val * 100
            rgb  = "239,68,68" if fark > 0 else "16,185,129"
            renk_b = "#d03b3b" if fark > 0 else "#0ca30c"
            yon  = "▲" if fark > 0 else "▼"
            etiket = f"+%{abs(fark):.1f}" if fark > 0 else f"-%{abs(fark):.1f}"
            return (
                f"<span style='background:rgba({rgb},0.15);border:1px solid {renk_b};"
                f"border-radius:6px;padding:2px 10px;font-size:11px;font-weight:700;"
                f"color:{renk_b};margin-left:8px;'>{yon} {etiket} geçen yıl</span>"
            )

        # ── Tüketim ──
        if grafik_tip == "tuketim":
            _badge = _yoy_badge("Toplam_Hastane_Tuketim_kWh", secili_df, df, tarih_bas, tarih_bit)
            st.markdown(f"<div style='font-size:11px;color:#46536b;margin-bottom:4px;'>{tarih_aralik_str} {_badge}</div>", unsafe_allow_html=True)
            _bar_chart(secili_df)

        # ── Chiller Set Trendi ──
        elif grafik_tip == "chiller":
            if "Chiller_Set_Temp_C" in secili_df.columns and not secili_df.empty:
                st.caption(tarih_aralik_str)
                fig_ch = go.Figure()
                if "Dis_Hava_Sicakligi_C" in secili_df.columns:
                    fig_ch.add_trace(go.Scatter(
                        x=secili_df["Tarih"], y=secili_df["Dis_Hava_Sicakligi_C"],
                        name="Dış Hava", line=dict(color="#c98500", width=1.5, dash="dot"),
                        yaxis="y2",
                    ))
                fig_ch.add_trace(go.Scatter(
                    x=secili_df["Tarih"], y=secili_df["Chiller_Set_Temp_C"],
                    name="Chiller Set", line=dict(color=renk, width=2),
                    fill="tozeroy", fillcolor=f"rgba({rr},{rg},{rb},0.07)",
                ))
                fig_ch.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#24324d", family="Inter,system-ui,-apple-system,Segoe UI,sans-serif"),
                    margin=dict(t=10,b=20,l=50,r=50), height=370,
                    xaxis=dict(gridcolor="rgba(19,50,115,0.07)"),
                    yaxis=dict(title=dict(text="Set °C", font=dict(size=10)),
                               gridcolor="rgba(19,50,115,0.07)"),
                    yaxis2=dict(title=dict(text="Dış Hava °C", font=dict(size=10)),
                                overlaying="y", side="right"),
                    legend=dict(orientation="h", y=1.12, font=dict(size=10)),
                )
                st.plotly_chart(fig_ch, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Chiller Set verisi bulunamadı.")

        # ── kWh/m² Trendi ──
        elif grafik_tip == "verimlilik":
            if "Toplam_Hastane_Tuketim_kWh" in secili_df.columns and not secili_df.empty:
                st.caption(tarih_aralik_str)
                gun_df2 = secili_df.groupby(secili_df["Tarih"].dt.date)["Toplam_Hastane_Tuketim_kWh"].sum().reset_index()
                gun_df2.columns = ["Tarih", "kWh"]
                gun_df2["kWhm2"] = gun_df2["kWh"] / m2
                fig_v = go.Figure(go.Scatter(
                    x=gun_df2["Tarih"], y=gun_df2["kWhm2"],
                    line=dict(color=renk, width=2),
                    fill="tozeroy", fillcolor=f"rgba({rr},{rg},{rb},0.07)",
                    hovertemplate="<b>%{x}</b><br>%{y:.3f} kWh/m²<extra></extra>",
                ))
                fig_v.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#24324d", family="Inter,system-ui,-apple-system,Segoe UI,sans-serif"),
                    margin=dict(t=10,b=20,l=50,r=10), height=370,
                    xaxis=dict(gridcolor="rgba(19,50,115,0.07)"),
                    yaxis=dict(gridcolor="rgba(19,50,115,0.07)",
                               title=dict(text="kWh/m²", font=dict(size=10))),
                )
                st.plotly_chart(fig_v, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Verimlilik verisi bulunamadı.")

        # ── Su Tüketimi ──
        elif grafik_tip == "su":
            if "Su_Tuketimi_m3" in secili_df.columns and not secili_df.empty:
                _badge = _yoy_badge("Su_Tuketimi_m3", secili_df, df, tarih_bas, tarih_bit)
                st.markdown(f"<div style='font-size:11px;color:#46536b;margin-bottom:4px;'>{tarih_aralik_str} {_badge}</div>", unsafe_allow_html=True)
                su_df = secili_df.groupby(secili_df["Tarih"].dt.date)["Su_Tuketimi_m3"].sum().reset_index()
                su_df.columns = ["Tarih", "m3"]
                fig_su = go.Figure(go.Bar(
                    x=su_df["Tarih"], y=su_df["m3"],
                    marker=dict(color="rgba(19,50,115,0.75)"),
                    hovertemplate="<b>%{x}</b><br>%{y:,.1f} m³<extra></extra>",
                ))
                fig_su.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#24324d", family="Inter,system-ui,-apple-system,Segoe UI,sans-serif"),
                    margin=dict(t=10,b=20,l=50,r=10), height=370,
                    xaxis=dict(gridcolor="rgba(19,50,115,0.07)"),
                    yaxis=dict(gridcolor="rgba(19,50,115,0.07)",
                               title=dict(text="m³", font=dict(size=10))),
                )
                st.plotly_chart(fig_su, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Su tüketimi verisi bulunamadı.")

        # ── Şebeke Tüketimi ──
        elif grafik_tip == "sebeke":
            if "Sebeke_Tuketim_kWh" in secili_df.columns and not secili_df.empty:
                st.caption(tarih_aralik_str)
                sb_df = secili_df.groupby(secili_df["Tarih"].dt.date)["Sebeke_Tuketim_kWh"].sum().reset_index()
                sb_df.columns = ["Tarih", "kWh"]
                fig_sb = go.Figure(go.Bar(
                    x=sb_df["Tarih"], y=sb_df["kWh"],
                    marker=dict(color="rgba(74,58,167,0.75)"),
                    hovertemplate="<b>%{x}</b><br>%{y:,.0f} kWh<extra></extra>",
                ))
                fig_sb.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#24324d", family="Inter,system-ui,-apple-system,Segoe UI,sans-serif"),
                    margin=dict(t=10,b=20,l=50,r=10), height=370,
                    xaxis=dict(gridcolor="rgba(19,50,115,0.07)"),
                    yaxis=dict(gridcolor="rgba(19,50,115,0.07)",
                               title=dict(text="kWh", font=dict(size=10))),
                )
                st.plotly_chart(fig_sb, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Şebeke tüketim verisi bulunamadı.")

        # ── Trafolar (TRDP) — şebekenin trafo bazında kırılımı ──
        elif grafik_tip == "trafo":
            if _trafo_kolonlar and not secili_df.empty:
                st.caption(tarih_aralik_str)
                _tr_renk = ["#4a3aa7", "#256abf", "#c98500", "#0ca30c", "#d03b3b", "#6da7ec"]
                _g = secili_df.groupby(secili_df["Tarih"].dt.date)
                fig_tr = go.Figure()
                for _i, _c in enumerate(_trafo_kolonlar):
                    _s = _g[_c].sum()
                    fig_tr.add_trace(go.Bar(
                        x=list(_s.index), y=list(_s.values),
                        name="TRDP-%s" % re.findall(r"\d+", _c)[0],
                        marker=dict(color=_tr_renk[_i % len(_tr_renk)]),
                        hovertemplate="<b>%{x}</b><br>%{y:,.0f} kWh<extra>%{fullData.name}</extra>",
                    ))
                fig_tr.update_layout(
                    barmode="group", bargap=0.22, bargroupgap=0.06,   # trafolar yan yana
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#24324d", family="Inter,system-ui,-apple-system,Segoe UI,sans-serif"),
                    margin=dict(t=10, b=20, l=50, r=10), height=370,
                    xaxis=dict(gridcolor="rgba(19,50,115,0.07)"),
                    yaxis=dict(gridcolor="rgba(19,50,115,0.07)",
                               title=dict(text="kWh", font=dict(size=10))),
                    legend=dict(orientation="h", y=1.08, x=0, font=dict(size=10),
                                bgcolor="rgba(0,0,0,0)"),
                )
                st.plotly_chart(fig_tr, use_container_width=True, config={"displayModeBar": False})

                # Trafo toplamı şebekeyi karşılıyor mu — eksik sayaç gizlenmesin.
                _tr_top = sum(pd.to_numeric(secili_df[c], errors="coerce").fillna(0).sum()
                              for c in _trafo_kolonlar)
                _sb_top = (pd.to_numeric(secili_df.get("Sebeke_Tuketim_kWh"), errors="coerce")
                           .fillna(0).sum() if "Sebeke_Tuketim_kWh" in secili_df.columns else 0)
                _ozet = "Dönem toplamı: %s kWh · %d trafo" % (f"{_tr_top:,.0f}".replace(",", "."),
                                                              len(_trafo_kolonlar))
                if _sb_top:
                    _kaps = _tr_top / _sb_top * 100
                    _ozet += " · şebekenin %%%.0f'i ölçülü" % _kaps
                    if _kaps < 98:
                        _ozet += " (kalan trafo(lar) henüz bağlı değil)"
                st.caption(_ozet)
            else:
                st.info("Trafo (TRDP) verisi bulunamadı.")

        # ── MCC Tüketimi ──
        elif grafik_tip == "mcc":
            if "MCC_Tuketim_kWh" in secili_df.columns and not secili_df.empty:
                _badge = _yoy_badge("MCC_Tuketim_kWh", secili_df, df, tarih_bas, tarih_bit)
                st.markdown(f"<div style='font-size:11px;color:#46536b;margin-bottom:4px;'>{tarih_aralik_str} {_badge}</div>", unsafe_allow_html=True)
                mcc_df = secili_df.groupby(secili_df["Tarih"].dt.date)["MCC_Tuketim_kWh"].sum().reset_index()
                mcc_df.columns = ["Tarih", "kWh"]
                fig_mcc = go.Figure(go.Bar(
                    x=mcc_df["Tarih"], y=mcc_df["kWh"],
                    marker=dict(color="rgba(235,104,52,0.75)"),
                    hovertemplate="<b>%{x}</b><br>%{y:,.0f} kWh<extra></extra>",
                ))
                fig_mcc.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#24324d", family="Inter,system-ui,-apple-system,Segoe UI,sans-serif"),
                    margin=dict(t=10,b=20,l=50,r=10), height=370,
                    xaxis=dict(gridcolor="rgba(19,50,115,0.07)"),
                    yaxis=dict(gridcolor="rgba(19,50,115,0.07)",
                               title=dict(text="kWh", font=dict(size=10))),
                )
                st.plotly_chart(fig_mcc, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("MCC tüketim verisi bulunamadı.")

        # ── Soğutma Tüketimi (Chiller + VRF) ──
        elif grafik_tip == "sogutma":
            col_s = "Toplam_Sogutma_Tuketim_kWh" if "Toplam_Sogutma_Tuketim_kWh" in secili_df.columns \
                    else ("Chiller_Tuketim_kWh" if "Chiller_Tuketim_kWh" in secili_df.columns else None)
            if col_s and not secili_df.empty:
                _badge = _yoy_badge(col_s, secili_df, df, tarih_bas, tarih_bit)
                st.markdown(f"<div style='font-size:11px;color:#46536b;margin-bottom:4px;'>{tarih_aralik_str} {_badge}</div>", unsafe_allow_html=True)
                sog_df = secili_df.groupby(secili_df["Tarih"].dt.date)[col_s].sum().reset_index()
                sog_df.columns = ["Tarih", "kWh"]
                fig_sog = go.Figure(go.Bar(
                    x=sog_df["Tarih"], y=sog_df["kWh"],
                    marker=dict(color="rgba(19,50,115,0.75)"),
                    hovertemplate="<b>%{x}</b><br>%{y:,.0f} kWh<extra></extra>",
                ))
                fig_sog.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#24324d", family="Inter,system-ui,-apple-system,Segoe UI,sans-serif"),
                    margin=dict(t=10,b=20,l=50,r=10), height=370,
                    xaxis=dict(gridcolor="rgba(19,50,115,0.07)"),
                    yaxis=dict(gridcolor="rgba(19,50,115,0.07)",
                               title=dict(text="kWh", font=dict(size=10))),
                )
                st.plotly_chart(fig_sog, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Soğutma tüketim verisi bulunamadı.")

        # ── Kazan Doğalgaz ──
        elif grafik_tip == "kazan":
            if "Kazan_Dogalgaz_m3" in secili_df.columns and not secili_df.empty:
                _badge = _yoy_badge("Kazan_Dogalgaz_m3", secili_df, df, tarih_bas, tarih_bit)
                st.markdown(f"<div style='font-size:11px;color:#46536b;margin-bottom:4px;'>{tarih_aralik_str} {_badge}</div>", unsafe_allow_html=True)
                kaz_df = secili_df.groupby(secili_df["Tarih"].dt.date)["Kazan_Dogalgaz_m3"].sum().reset_index()
                kaz_df.columns = ["Tarih", "m3"]
                fig_kaz = go.Figure(go.Bar(
                    x=kaz_df["Tarih"], y=kaz_df["m3"],
                    marker=dict(color="rgba(208,59,59,0.75)"),
                    hovertemplate="<b>%{x}</b><br>%{y:,.1f} m³<extra></extra>",
                ))
                fig_kaz.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#24324d", family="Inter,system-ui,-apple-system,Segoe UI,sans-serif"),
                    margin=dict(t=10,b=20,l=50,r=10), height=370,
                    xaxis=dict(gridcolor="rgba(19,50,115,0.07)"),
                    yaxis=dict(gridcolor="rgba(19,50,115,0.07)",
                               title=dict(text="m³", font=dict(size=10))),
                )
                st.plotly_chart(fig_kaz, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Kazan doğalgaz verisi bulunamadı.")

        # ── Bu Ay vs Geçen Ay ──
        elif grafik_tip == "ay_karsilastir":
            if "Toplam_Hastane_Tuketim_kWh" in df.columns and not df.empty:
                bu_ay_bas  = now.replace(day=1)
                gec_ay_bit = bu_ay_bas - timedelta(days=1)
                gec_ay_bas = gec_ay_bit.replace(day=1)
                bu_ay_df  = df[df["Tarih"] >= pd.Timestamp(bu_ay_bas)]
                gec_ay_df = df[(df["Tarih"] >= pd.Timestamp(gec_ay_bas)) & (df["Tarih"] <= pd.Timestamp(gec_ay_bit))]
                bu_gun  = bu_ay_df.groupby(bu_ay_df["Tarih"].dt.day)["Toplam_Hastane_Tuketim_kWh"].sum()
                gec_gun = gec_ay_df.groupby(gec_ay_df["Tarih"].dt.day)["Toplam_Hastane_Tuketim_kWh"].sum()
                fig_ay = go.Figure()
                fig_ay.add_trace(go.Bar(
                    x=gec_gun.index, y=gec_gun.values,
                    name=f"{gec_ay_bas.strftime('%B %Y')}",
                    marker=dict(color=f"rgba({rr},{rg},{rb},0.4)"),
                    hovertemplate="Gün %{x}: %{y:,.0f} kWh<extra></extra>",
                ))
                fig_ay.add_trace(go.Bar(
                    x=bu_gun.index, y=bu_gun.values,
                    name=f"{bu_ay_bas.strftime('%B %Y')}",
                    marker=dict(color=f"rgba({rr},{rg},{rb},0.9)"),
                    hovertemplate="Gün %{x}: %{y:,.0f} kWh<extra></extra>",
                ))
                fig_ay.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#24324d", family="Inter,system-ui,-apple-system,Segoe UI,sans-serif"),
                    margin=dict(t=30,b=20,l=50,r=10), height=370,
                    xaxis=dict(gridcolor="rgba(19,50,115,0.07)", title="Gün"),
                    yaxis=dict(gridcolor="rgba(19,50,115,0.07)", title=dict(text="kWh", font=dict(size=10))),
                    barmode="group",
                    legend=dict(orientation="h", y=1.1, font=dict(size=10)),
                )
                # Toplam fark özeti — SYN-5 fix: geçen ay AYNI GÜN ARALIĞINA kırpılır
                # (kısmi ay tam ayla kıyaslanınca ayın başında sahte "az tüketim" görünüyordu)
                bu_top = bu_gun.sum()
                gec_kiyas = gec_gun[gec_gun.index <= bu_gun.index.max()] if not bu_gun.empty else gec_gun
                gec_top = gec_kiyas.sum()
                if gec_top > 0:
                    fark_pct = (bu_top - gec_top) / gec_top * 100
                    fark_renk = "#d03b3b" if fark_pct > 0 else "#0ca30c"
                    fark_yon  = "▲" if fark_pct > 0 else "▼"
                    st.markdown(
                        f"<div style='text-align:center;font-size:11px;color:{fark_renk};margin-bottom:4px;'>"
                        f"{fark_yon} Bu ay şimdiye kadar, geçen ayın aynı dönemine (ilk {int(bu_gun.index.max())} gün) göre "
                        f"<b>{abs(fark_pct):.1f}%</b> {'fazla' if fark_pct>0 else 'az'} tüketim</div>",
                        unsafe_allow_html=True
                    )
                st.plotly_chart(fig_ay, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Ay karşılaştırma verisi bulunamadı.")

        # (SYN-4: ölü 'dogalgaz_verim' grafik dalı kaldırıldı — grafik_secenekler'de hiç
        #  listelenmiyordu; içindeki "Kazan verimi" hesabı da elektrik/kazan-gazı gibi
        #  kavramsal olarak yanlış bir orandı.)

        # ── KPI Özet Scorecard (seçilen tarih aralığı) ──
        elif grafik_tip == "kpi_ozet":
            kpi_rows = []
            _kd = secili_df  # KPI için seçilen tarih aralığı
            _etiket = tarih_aralik_str   # (yalnızca üstteki başlıkta; satırlarda tarih yok)
            if "Toplam_Hastane_Tuketim_kWh" in _kd.columns:
                kpi_rows.append(("enerji", "Elektrik Tüketimi", f"{_kd['Toplam_Hastane_Tuketim_kWh'].sum():,.0f} kWh", "#2a78d6"))
            if "Kojen_Uretim_kWh" in _kd.columns:
                kpi_rows.append(("kojen", "Kojen Üretimi", f"{_kd['Kojen_Uretim_kWh'].sum():,.0f} kWh", "#0ca30c"))
            if "Kojen_Uretim_kWh" in _kd.columns and "Toplam_Hastane_Tuketim_kWh" in _kd.columns:
                top = _kd["Toplam_Hastane_Tuketim_kWh"].sum()
                ko  = _kd["Kojen_Uretim_kWh"].sum()
                if top > 0:
                    kpi_rows.append(("kojen", "Kojen Karşılama Oranı", f"%{ko/top*100:.1f}", "#0ca30c"))
            if "Kojen_Dogalgaz_m3" in _kd.columns:
                kpi_rows.append(("dogalgaz", "Kojen Doğalgaz", f"{_kd['Kojen_Dogalgaz_m3'].sum():,.1f} m³", "#eb6834"))
            if "Kazan_Dogalgaz_m3" in _kd.columns:
                kpi_rows.append(("kazan", "Kazan Doğalgaz", f"{_kd['Kazan_Dogalgaz_m3'].sum():,.1f} m³", "#d03b3b"))
            if "Su_Tuketimi_m3" in _kd.columns:
                kpi_rows.append(("su", "Su Tüketimi", f"{_kd['Su_Tuketimi_m3'].sum():,.1f} m³", "#2a78d6"))
            if "Sebeke_Tuketim_kWh" in _kd.columns:
                kpi_rows.append(("sebeke", "Şebeke Tüketimi", f"{_kd['Sebeke_Tuketim_kWh'].sum():,.0f} kWh", "#4a3aa7"))
            if "MCC_Tuketim_kWh" in _kd.columns:
                kpi_rows.append(("mcc", "MCC Tüketimi", f"{_kd['MCC_Tuketim_kWh'].sum():,.0f} kWh", "#c98500"))
            _sog_col_kpi = ("Toplam_Sogutma_Tuketim_kWh" if "Toplam_Sogutma_Tuketim_kWh" in _kd.columns
                            else ("Chiller_Tuketim_kWh" if "Chiller_Tuketim_kWh" in _kd.columns else None))
            if _sog_col_kpi:
                kpi_rows.append(("sogutma", "Soğutma Tüketimi", f"{_kd[_sog_col_kpi].sum():,.0f} kWh", "#2a78d6"))
            if m2 and "Toplam_Hastane_Tuketim_kWh" in _kd.columns and _kd["Toplam_Hastane_Tuketim_kWh"].sum() > 0:
                kpi_rows.append(("verim", "kWh/m²", f"{_kd['Toplam_Hastane_Tuketim_kWh'].sum()/m2:.2f}", "#c98500"))

            if kpi_rows:
                st.caption(tarih_aralik_str)
                rows_html = ""
                for ikon_ad, baslik, deger, renk_hex in kpi_rows:
                    rows_html += (
                        f"<div class='dz-satir' style='--k:{renk_hex};display:flex;justify-content:space-between;"
                        f"align-items:center;margin-bottom:6px;'>"
                        f"<span class='dz-et' style='display:inline-flex;align-items:center;gap:10px;'>"
                        f"{_ik.ikon(ikon_ad, 20)}{baslik}</span>"
                        f"<span style='font-size:15px;font-weight:700;color:#133273;white-space:nowrap;'>{deger}</span>"
                        f"</div>"
                    )
                st.markdown(f"<div class='dz-kart'>{rows_html}</div>", unsafe_allow_html=True)
            else:
                st.info("KPI verisi bulunamadı.")

        # ── Enerji Kırılımı (Donut) ──
        elif grafik_tip == "enerji_kirilim":
            st.caption(tarih_aralik_str)
            _ek = secili_df

            # Toplam elektrik tüketimi (merkez değer)
            _toplam = _ek["Toplam_Hastane_Tuketim_kWh"].sum() if "Toplam_Hastane_Tuketim_kWh" in _ek.columns else 0

            # ── Kaynak kırılımı: Kojen + Şebeke + Diğer = Toplam ──
            _kojen  = _ek["Kojen_Uretim_kWh"].sum()  if "Kojen_Uretim_kWh"   in _ek.columns else 0
            _sebeke = _ek["Sebeke_Tuketim_kWh"].sum() if "Sebeke_Tuketim_kWh" in _ek.columns else 0
            _diger_k = max(_toplam - _kojen - _sebeke, 0)  # Fark (negatif olmaması için)

            # ── Tüketim kırılımı: Soğutma + MCC + Diğer = Toplam ──
            _sog_col_k = ("Toplam_Sogutma_Tuketim_kWh" if "Toplam_Sogutma_Tuketim_kWh" in _ek.columns
                          else ("Chiller_Tuketim_kWh" if "Chiller_Tuketim_kWh" in _ek.columns else None))
            _sogutma = _ek[_sog_col_k].sum() if _sog_col_k else 0
            _mcc     = _ek["MCC_Tuketim_kWh"].sum() if "MCC_Tuketim_kWh" in _ek.columns else 0
            _diger_t = max(_toplam - _sogutma - _mcc, 0)

            if _toplam > 0:
                # İki donut yan yana
                _c1, _c2 = st.columns(2)

                def _donut_fig(labels, values, colors, center_val, center_label):
                    fig = go.Figure(go.Pie(
                        labels=labels, values=values,
                        hole=0.58,
                        marker=dict(colors=colors, line=dict(color="#ffffff", width=2)),
                        textinfo="label+percent",
                        textposition="outside",
                        outsidetextfont=dict(size=12, color="#133273"),
                        texttemplate="<b>%{label}</b><br>%{percent}",
                        hovertemplate="<b>%{label}</b><br>%{value:,.0f} kWh<br>%{percent}<extra></extra>",
                        direction="clockwise", sort=True,
                    ))
                    fig.update_layout(
                        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                        font=dict(color="#24324d", family="Inter,system-ui,-apple-system,Segoe UI,sans-serif"),
                        margin=dict(t=52, b=28, l=10, r=10), height=360,
                        showlegend=False,
                        annotations=[dict(
                            text=f"<b>{center_val:,.0f}</b><br><span style='font-size:11px;color:#46536b'>{center_label}</span>",
                            x=0.5, y=0.5, font_size=16, font_color="#133273", showarrow=False,
                        )],
                    )
                    return fig

                with _c1:
                    st.markdown("<div class='dz-et' style='display:flex;align-items:center;justify-content:center;gap:7px;margin-bottom:4px;'>" + _ik.ikon("enerji", 16) + "KAYNAK KIRILIMLARI</div>", unsafe_allow_html=True)
                    _kaynak_labels = []
                    _kaynak_values = []
                    _kaynak_colors = []
                    if _kojen  > 0: _kaynak_labels.append("Kojen");  _kaynak_values.append(_kojen);  _kaynak_colors.append("#0ca30c")
                    if _sebeke > 0: _kaynak_labels.append("Şebeke"); _kaynak_values.append(_sebeke); _kaynak_colors.append("#4a3aa7")
                    if _diger_k > 0: _kaynak_labels.append("Diğer"); _kaynak_values.append(_diger_k); _kaynak_colors.append("#46536b")
                    if _kaynak_labels:
                        st.plotly_chart(_donut_fig(_kaynak_labels, _kaynak_values, _kaynak_colors, _toplam, "kWh toplam"),
                                        use_container_width=True, config={"displayModeBar": False})

                with _c2:
                    st.markdown("<div class='dz-et' style='display:flex;align-items:center;justify-content:center;gap:7px;margin-bottom:4px;'>" + _ik.ikon("mcc", 16) + "TÜKETİM KIRILIMLARI</div>", unsafe_allow_html=True)
                    _tuk_labels = []
                    _tuk_values = []
                    _tuk_colors = []
                    if _sogutma > 0: _tuk_labels.append("Soğutma"); _tuk_values.append(_sogutma); _tuk_colors.append("#2a78d6")
                    if _mcc     > 0: _tuk_labels.append("MCC");     _tuk_values.append(_mcc);     _tuk_colors.append("#c98500")
                    if _diger_t > 0: _tuk_labels.append("Diğer");   _tuk_values.append(_diger_t); _tuk_colors.append("#46536b")
                    if _tuk_labels:
                        st.plotly_chart(_donut_fig(_tuk_labels, _tuk_values, _tuk_colors, _toplam, "kWh toplam"),
                                        use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Enerji kırılımı için yeterli veri bulunamadı.")

        # ── Kojen Üretim ──
        elif grafik_tip == "kojen":
            kojen_cols = [c for c in ["Kojen_Uretim_kWh","Kojen_Dogalgaz_m3"] if c in secili_df.columns]
            if kojen_cols and not secili_df.empty:
                st.caption(tarih_aralik_str)
                fig_kj = go.Figure()
                if "Kojen_Uretim_kWh" in secili_df.columns:
                    kj_df = secili_df.groupby(secili_df["Tarih"].dt.date)["Kojen_Uretim_kWh"].sum().reset_index()
                    kj_df.columns = ["Tarih", "kWh"]
                    fig_kj.add_trace(go.Bar(
                        x=kj_df["Tarih"], y=kj_df["kWh"],
                        name="Kojen Üretim", marker=dict(color="rgba(12,163,12,0.75)"),
                        hovertemplate="<b>%{x}</b><br>%{y:,.0f} kWh<extra></extra>",
                    ))
                if "Kojen_Dogalgaz_m3" in secili_df.columns:
                    kg_df = secili_df.groupby(secili_df["Tarih"].dt.date)["Kojen_Dogalgaz_m3"].sum().reset_index()
                    kg_df.columns = ["Tarih", "m3"]
                    fig_kj.add_trace(go.Scatter(
                        x=kg_df["Tarih"], y=kg_df["m3"],
                        name="Doğalgaz (m³)", line=dict(color="#c98500", width=2),
                        yaxis="y2",
                        hovertemplate="<b>%{x}</b><br>%{y:,.1f} m³<extra></extra>",
                    ))
                fig_kj.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#24324d", family="Inter,system-ui,-apple-system,Segoe UI,sans-serif"),
                    margin=dict(t=10,b=20,l=50,r=50), height=370,
                    xaxis=dict(gridcolor="rgba(19,50,115,0.07)"),
                    yaxis=dict(gridcolor="rgba(19,50,115,0.07)",
                               title=dict(text="kWh", font=dict(size=10))),
                    yaxis2=dict(title=dict(text="m³", font=dict(size=10)),
                                overlaying="y", side="right"),
                    legend=dict(orientation="h", y=1.12, font=dict(size=10)),
                    barmode="group",
                )
                st.plotly_chart(fig_kj, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Kojen verisi bulunamadı.")

    # ──────────── KOJEN & KAYNAK — tam genişlik yatay grid ────────────
    kgaz_str   = f"{kojen_gaz:,.1f}"  if kojen_gaz  is not None else "—"
    kurt_str   = f"{kojen_urt:,.0f}"  if kojen_urt  is not None else "—"
    kzan_str   = f"{kazan_gaz:,.1f}"  if kazan_gaz  is not None else "—"
    su_str     = f"{su_tuk:,.1f}"     if su_tuk     is not None else "—"
    sebeke_str = f"{sebeke_tuk:,.0f}" if sebeke_tuk is not None else "—"
    mcc_str    = f"{mcc_tuk:,.0f}"    if mcc_tuk   is not None else "—"

    def _kaynak_item(ikon, baslik, deger, birim, renk_hex, ikon_renk=None):
        r2=int(renk_hex[1:3],16); g2=int(renk_hex[3:5],16); b2=int(renk_hex[5:7],16)
        return (
            f"<div class='dz-kart' style='display:flex;align-items:center;gap:12px;'>"
            f"{_ik.ikon(ikon, 26, ikon_renk)}"
            f"<div style='min-width:0;'>"
            f"<div class='dz-et'>{baslik}</div>"
            f"<div class='dz-dg'>{deger}<span class='dz-br'>{birim}</span></div>"
            f"</div></div>"
        )

    st.markdown('<div class="sec" style="display:flex;align-items:center;gap:6px;">'
                + _ik.ikon("kojen", 15) + 'KOJEN & KAYNAK</div>', unsafe_allow_html=True)

    # ── TRDP Kırılımı (sadece Maslak) ──
    if lok_id == "maslak":
        trdp1_val = son_df["TRDP1_kWh"].sum() if "TRDP1_kWh" in son_df.columns else None
        trdp2_val = son_df["TRDP2_kWh"].sum() if "TRDP2_kWh" in son_df.columns else None
        trdp3_val = son_df["TRDP3_kWh"].sum() if "TRDP3_kWh" in son_df.columns else None
        trdp4_val = son_df["TRDP4_kWh"].sum() if "TRDP4_kWh" in son_df.columns else None
        _kaynak_items = [
            # Satır 1
            _kaynak_item("dogalgaz", "Kojen Doğalgaz", kgaz_str, "m³",  "#eb6834"),
            _kaynak_item("kojen", "Kojen Üretim",   kurt_str, "kWh", "#0ca30c"),
            _kaynak_item("trdp", "TRDP-1 (Bina)", f"{trdp1_val:,.0f}" if trdp1_val else "—", "kWh", "#256abf", "#256abf"),
            _kaynak_item("trdp", "TRDP-2 (Mek.)", f"{trdp2_val:,.0f}" if trdp2_val else "—", "kWh", "#c98500", "#c98500"),
            # Satır 2
            _kaynak_item("sebeke", "Şebeke Tüketim", sebeke_str, "kWh", "#4a3aa7"),
            _kaynak_item("mcc", "MCC Tüketim",   mcc_str,    "kWh", "#c98500"),
            _kaynak_item("trdp", "TRDP-3 (Bina)", f"{trdp3_val:,.0f}" if trdp3_val else "—", "kWh", "#256abf", "#256abf"),
            _kaynak_item("trdp", "TRDP-4 (Mek.)", f"{trdp4_val:,.0f}" if trdp4_val else "—", "kWh", "#c98500", "#c98500"),
            # Satır 3
            _kaynak_item("kazan", "Kazan Doğalgaz", kzan_str, "m³", "#d03b3b"),
            _kaynak_item("su", "Su Tüketimi",    su_str,   "m³", "#2a78d6"),
        ]
    else:
        # Maslak DIŞI lokasyonlar: trafo kartları yalnızca sayacı dolu olanlar
        # için üretilir. Canlıda bugün hiçbiri dolu değil (liste boş kalır,
        # ekran eskisi gibi görünür); simülasyonda her hastanede dolu olduğu
        # için sunumda diğer kalemlerle birlikte görünür.
        _trdp_kart = []
        for _c in sorted([c for c in df.columns if re.fullmatch(r"TRDP\d+_kWh", str(c))
                          and pd.to_numeric(df[c], errors="coerce").fillna(0).sum() > 0],
                         key=lambda c: int(re.findall(r"\d+", c)[0])):
            _no = re.findall(r"\d+", _c)[0]
            _v = pd.to_numeric(son_df.get(_c), errors="coerce").fillna(0).sum() \
                if _c in son_df.columns else 0
            _trdp_kart.append(_kaynak_item(
                "trdp", f"TRDP-{_no}",
                f"{_v:,.0f}" if _v else "—", "kWh",
                "#256abf" if int(_no) % 2 else "#c98500",
                "#256abf" if int(_no) % 2 else "#c98500"))
        _kaynak_items = [
            _kaynak_item("dogalgaz", "Kojen Doğalgaz", kgaz_str,   "m³",  "#eb6834"),
            _kaynak_item("kojen", "Kojen Üretim",   kurt_str,   "kWh", "#0ca30c"),
            _kaynak_item("sebeke", "Şebeke Tüketim", sebeke_str, "kWh", "#4a3aa7"),
            _kaynak_item("mcc", "MCC Tüketim",   mcc_str,    "kWh", "#c98500"),
            _kaynak_item("kazan", "Kazan Doğalgaz", kzan_str,   "m³",  "#d03b3b"),
            _kaynak_item("su", "Su Tüketimi",    su_str,     "m³",  "#2a78d6"),
        ] + _trdp_kart

    _cols_count = 4 if (lok_id == "maslak" or len(_kaynak_items) > 6) else 3
    _grid_items = "".join(_kaynak_items)
    st.markdown(
        f"<div style='display:grid;grid-template-columns:repeat({_cols_count},1fr);gap:10px;margin-bottom:8px;'>"
        f"{_grid_items}</div>",
        unsafe_allow_html=True
    )

    # ══════════════════════════════════════════════════════
    # HVAC & BAKIM DURUMU
    # ══════════════════════════════════════════════════════
    st.markdown("<div style='margin-top:18px'></div>", unsafe_allow_html=True)
    st.markdown('<div class="sec" style="display:flex;align-items:center;gap:6px;">'
                + _ik.ikon("bakim", 15) + 'HVAC & BAKIM DURUMU</div>', unsafe_allow_html=True)

    arizali_list = bakim_ozet.get("arizali_cihazlar", [])
    bakim_list   = bakim_ozet.get("bakimda_cihazlar", [])
    toplam_ariza = bakim_ozet.get("toplam_ariza", 0)
    toplam_bakim = bakim_ozet.get("toplam_bakim", 0)
    hvac_kritik  = hvac_ozet.get("kritik", [])
    hvac_uyari   = hvac_ozet.get("uyari",  [])
    hvac_normal  = hvac_ozet.get("normal", [])

    # Canlı İzleme kartlarıyla aynı (.dz-kart / .dz-et)
    KART  = ("background:#fff;border:1px solid rgba(24,26,30,0.10);border-radius:16px;"
             "padding:11px 15px;box-shadow:0 1px 1px rgba(20,22,26,.05),0 10px 22px -12px rgba(20,22,26,.22);")
    LBL   = ("font-size:10px;color:#46536b;letter-spacing:1.2px;display:flex;align-items:center;gap:6px;"
             "text-transform:uppercase;margin-bottom:6px;font-weight:600;")

    def cihaz_html(cihaz, bg, border, text_renk):
        if isinstance(cihaz, dict):
            ad         = cihaz.get("ad", cihaz.get("name", str(cihaz)))
            bilesenler = cihaz.get("bilesenler", [])
            not_metni  = cihaz.get("not", cihaz.get("detay", cihaz.get("bakim_turu", "")))
        else:
            ad, bilesenler, not_metni = str(cihaz), [], ""

        # Bileşen badge'leri
        badge_html = ""
        if bilesenler:
            badges = "".join(f"<span class='dz-cip'>{b}</span>" for b in bilesenler)
            badge_html = f"<div style='padding-left:18px;'>{badges}</div>"

        # Not
        not_html = (
            f"<div class='dz-not' style='padding-left:18px;'>{not_metni}</div>"
        ) if not_metni else ""

        return (
            "<div class='dz-satir' style='--k:" + border + ";'>"
            "<div class='dz-satir-ad'>" + _ik.nokta(border, 8) + ad + "</div>"
            + badge_html + not_html +
            "</div>"
        )

    def hvac_satir_html(cihaz, bg, border, badge_renk, badge_text, text_renk):
        if isinstance(cihaz, dict):
            ad  = cihaz.get("ad", str(cihaz))
            det = cihaz.get("sorun", "")
        else:
            ad, det = str(cihaz), ""
        det_part = (
            "<div style='font-size:10px;color:#133273;"
            "margin-top:3px;'>" + det + "</div>"
        ) if det else ""
        return (
            "<div class='dz-satir' style='--k:" + badge_renk + ";'>"
            "<div class='dz-satir-ad'>"
            "<span class='dz-etiket'>" + _ik.ikon("ariza", 14, badge_renk) + badge_text + "</span>"
            + ad + "</div>" + det_part + "</div>"
        )

    col_ar, col_bk, col_hv = st.columns([1, 1, 2])

    # ── Sütun 1: Arızalı ──────────────────────────
    with col_ar:
        ar_renk = "#d03b3b" if toplam_ariza > 0 else "#0ca30c"
        rows = "".join(
            cihaz_html(c, "rgba(208,59,59,0.10)", "#d03b3b", "#b42525")
            for c in arizali_list
        ) if arizali_list else (
            "<div style='font-size:11px;color:#006300;padding:4px 0;'>Ariza yok</div>"
        )
        st.markdown(
            "<details style='" + KART + "border:1px solid rgba(208,59,59,0.25);cursor:pointer;'>"
            "<summary style='list-style:none;outline:none;'>"
            "<div style='" + LBL + "'>ARIZALI CIHAZLAR</div>"
            "<div style='display:flex;align-items:center;gap:12px;margin-bottom:4px;'>"
            + _ik.ikon("ariza", 34, ar_renk, sakin=(toplam_ariza == 0)) +
            "<div style='font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;font-size:26px;font-weight:700;line-height:1.15;"
            "color:" + ar_renk + ";'>" + str(toplam_ariza) + "</div></div>"
            "<div style='font-size:9px;color:#46536b;margin-bottom:4px;'>▼ detay için tıkla</div>"
            "</summary>"
            "<div style='margin-top:8px;'>" + rows + "</div>"
            "</details>",
            unsafe_allow_html=True
        )

    # ── Sütun 2: Bakımda ──────────────────────────
    with col_bk:
        bk_renk = "#c98500" if toplam_bakim > 0 else "#0ca30c"
        rows = "".join(
            cihaz_html(c, "rgba(250,178,25,0.10)", "#c98500", "#8a5a00")
            for c in bakim_list
        ) if bakim_list else (
            "<div style='font-size:11px;color:#46536b;padding:4px 0;'>Cihaz listesi girilmemiş</div>"
        )
        st.markdown(
            "<details style='" + KART + "border:1px solid rgba(250,178,25,0.25);cursor:pointer;'>"
            "<summary style='list-style:none;outline:none;'>"
            "<div style='" + LBL + "'>BAKIMDAKI CIHAZLAR</div>"
            "<div style='display:flex;align-items:center;gap:12px;margin-bottom:4px;'>"
            + _ik.ikon("bakim", 34, bk_renk, sakin=(toplam_bakim == 0)) +
            "<div style='font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;font-size:26px;font-weight:700;line-height:1.15;"
            "color:" + bk_renk + ";'>" + str(toplam_bakim) + "</div></div>"
            "<div style='font-size:9px;color:#46536b;margin-bottom:4px;'>▼ detay için tıkla</div>"
            "</summary>"
            "<div style='margin-top:8px;'>" + rows + "</div>"
            "</details>",
            unsafe_allow_html=True
        )

    # ── Sütun 3: HVAC Analiz ──────────────────────
    with col_hv:
        if hvac_kritik or hvac_uyari:
            hv_rows = "".join(
                hvac_satir_html(c, "rgba(208,59,59,0.08)", "rgba(208,59,59,0.35)",
                                "#d03b3b", "KRİTİK", "#b42525")
                for c in hvac_kritik
            ) + "".join(
                hvac_satir_html(c, "rgba(250,178,25,0.08)", "rgba(250,178,25,0.30)",
                                "#c98500", "UYARI", "#8a5a00")
                for c in hvac_uyari
            )
            if hvac_normal:
                hv_rows += (
                    "<div style='font-size:11px;color:#006300;padding:4px 0;'>"
                    + str(len(hvac_normal)) + " cihaz normal</div>"
                )
        elif arizali_list:
            hv_rows = "".join(
                hvac_satir_html(c, "rgba(208,59,59,0.08)", "rgba(208,59,59,0.35)",
                                "#d03b3b", "KRİTİK", "#b42525")
                for c in arizali_list
            )
        else:
            hv_rows = (
                "<div style='background:rgba(12,163,12,0.08);"
                "border:1px solid rgba(12,163,12,0.2);"
                "border-radius:8px;padding:14px;text-align:center;'>"
                "<div style='font-size:18px;margin-bottom:4px;'>&#10003;</div>"
                "<div style='font-size:12px;color:#006300;'>Tum HVAC sistemleri normal</div>"
                "</div>"
            )
        # Arızalı/Bakımdaki kartlarıyla aynı davranış: kapalı gelir, sayıya
        # tıklayınca liste açılır. Onlarca AHU listelendiğinde sayfa uzuyordu.
        _hv_kritik = len(hvac_kritik) if (hvac_kritik or hvac_uyari) else len(arizali_list)
        _hv_uyari = len(hvac_uyari) if (hvac_kritik or hvac_uyari) else 0
        _hv_sorun = _hv_kritik + _hv_uyari
        _hv_renk = "#d03b3b" if _hv_kritik else ("#c98500" if _hv_uyari else "#0ca30c")
        _hv_ozet = []
        if _hv_kritik:
            _hv_ozet.append("%d kritik" % _hv_kritik)
        if _hv_uyari:
            _hv_ozet.append("%d uyarı" % _hv_uyari)
        if hvac_normal:
            _hv_ozet.append("%d normal" % len(hvac_normal))
        st.markdown(
            "<details style='" + KART + "border:1px solid rgba(" +
            ("239,68,68" if _hv_kritik else "245,158,11" if _hv_uyari else "16,185,129") +
            ",0.25);cursor:pointer;'>"
            "<summary style='list-style:none;outline:none;'>"
            "<div style='" + LBL + "'>HVAC ANALIZ DURUMU</div>"
            "<div style='display:flex;align-items:center;gap:12px;margin-bottom:4px;'>"
            + _ik.ikon("hvac", 34, _hv_renk, sakin=(_hv_sorun == 0)) +
            "<div style='font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;font-size:26px;font-weight:700;line-height:1.15;"
            "color:" + _hv_renk + ";'>" + str(_hv_sorun) + "</div></div>"
            "<div style='font-size:10px;color:#46536b;margin-bottom:2px;'>"
            + (" · ".join(_hv_ozet) if _hv_ozet else "Tüm HVAC sistemleri normal") + "</div>"
            "<div style='font-size:9px;color:#46536b;margin-bottom:4px;'>"
            "▼ detay için tıkla</div>"
            "</summary>"
            "<div style='margin-top:8px;'>" + hv_rows + "</div>"
            "</details>",
            unsafe_allow_html=True
        )

    # ── YÜRÜRLÜKTEKİ SETLER (lokasyona özel) ──────────────────────────
    # Değerler bu lokasyonun heartbeat'inden gelir (bakim_ozet.oto.setler);
    # kural tablosu lokasyonun kendi oto_set.py dosyasındadır, merkezde yok.
    # Ana ekranda tutulmuyor: her hastane kendi dış havasına ve kendi
    # işletme tablosuna göre çalıştığı için özet kartta tek değer göstermek
    # lokasyon sayısı arttıkça yanıltıcı oluyordu.
    _oto = bakim_ozet.get("oto") or {}
    _setler = (_oto or {}).get("setler") or {}
    if _setler:
        st.markdown("<div style='margin-top:14px'></div>", unsafe_allow_html=True)
        st.markdown('<div class="sec">🎛️ YÜRÜRLÜKTEKİ SETLER</div>', unsafe_allow_html=True)

        def _sd(anahtar):
            _v = _setler.get(anahtar)
            return ("%g°C" % _v) if isinstance(_v, (int, float)) else "—"

        _CH_AD = {"koc_soguk": "Koç soğuk", "serin": "Serin",
                  "ilimli": "Ilımlı", "sicak": "Sıcak"}
        _DIG_AD = {"yogun_sogutma": "Yoğun soğutma",
                   "sogutma": "Soğutma", "isitma": "Isıtma"}
        _ch_mod = _CH_AD.get((_oto or {}).get("chiller_mod"), "—")
        _dig_mod = _DIG_AD.get((_oto or {}).get("diger_mod"), "—")
        _donem = {"gunduz": "Gündüz", "gece": "Gece"}.get((_oto or {}).get("donem"), "—")

        _fcu = _setler.get("A_BLOK_FCU_SET", _setler.get("B_BLOK_FCU_SET"))
        _ahu = _setler.get("ZON1_KLIMA_SANTRALI_SET",
                           _setler.get("ZON2_KLIMA_SANTRALI_SET"))
        _esik = _setler.get("esikler") or {}

        def _set_kart(ikon, etiket, deger, alt):
            return ("<div style='" + KART + "'><div style='" + LBL + "'>" + etiket + "</div>"
                    "<div style='display:flex;align-items:center;gap:10px;'>" + _ik.ikon(ikon, 28) +
                    f"<div class='dz-dg'>{deger}</div></div>"
                    f"<div style='font-size:10px;color:#46536b;margin-top:2px;'>{alt}</div></div>")

        _k1, _k2, _k3, _k4 = st.columns(4)
        with _k1:
            st.markdown(_set_kart("chiller", "CHILLER", _sd("chiller"), _ch_mod),
                        unsafe_allow_html=True)
        with _k2:
            st.markdown(_set_kart(
                "kollektor", "KOLLEKTÖR",
                "%s / %s" % (_sd("GUNDUZ_KOLLEKTOR_SET"), _sd("GECE_KOLLEKTOR_SET")),
                "gündüz / gece · %s" % _dig_mod), unsafe_allow_html=True)
        with _k3:
            st.markdown(_set_kart(
                "fcu", "FCU", ("%g°C" % _fcu) if isinstance(_fcu, (int, float)) else "—",
                "A/B blok"), unsafe_allow_html=True)
        with _k4:
            st.markdown(_set_kart(
                "ahu", "AHU", ("%g°C" % _ahu) if isinstance(_ahu, (int, float)) else "—",
                "Zon-1/2 santral"), unsafe_allow_html=True)

        _ck = _esik.get("chiller_sinir") or []
        _alt = []
        if _ck:
            _alt.append("Chiller bölgeleri: %s °C (±%g histerezis)"
                        % (" / ".join("%g" % x for x in _ck), _esik.get("chiller_h", 0)))
        # İki eşik var (15 ve 23 °C) ve saha bunları "dig_sinir" listesiyle
        # bildirir. v9.8 ve öncesi tek eşikli "dig_esik" gönderiyordu; o
        # sürümdeki lokasyonlar güncellenene kadar ikisi de okunur.
        _ds = _esik.get("dig_sinir")
        if not _ds and _esik.get("dig_esik") is not None:
            _ds = [_esik["dig_esik"]]
        if _ds:
            _alt.append("Kollektör/FCU/AHU eşikleri: %s °C (±%g histerezis)"
                        % (" / ".join("%g" % x for x in _ds), _esik.get("dig_h", 0)))
        st.caption("Dönem: %s · %s" % (_donem, " · ".join(_alt) if _alt else
                                       "eşikler bildirilmedi"))

        # ── Kararın dayandığı dış hava (lokasyonun KENDİ koordinatı) ──
        # Setler bu hastanenin kendi hava tahminiyle belirlenir; merkez
        # koordinat göndermez. Profil girilmemişse lokasyon İstanbul
        # varsayılanıyla çalışır — farklı şehirde sessiz bir hatadır,
        # bu yüzden ayrıca uyarı verilir.
        _knm = (_oto or {}).get("konum") or {}
        _thm = (_oto or {}).get("tahmin") or {}
        _hv = []
        if isinstance(_thm.get("ref"), (int, float)):
            _hv.append("Son geçiş referansı: %g °C" % _thm["ref"])
        if isinstance(_thm.get("bugun_max"), (int, float)):
            _hv.append("bugün max %g" % _thm["bugun_max"])
        if isinstance(_thm.get("yarin_min"), (int, float)):
            _hv.append("yarın min %g" % _thm["yarin_min"])
        if _knm.get("kaynak") == "varsayilan":
            st.caption("⚠️ Hava tahmini VARSAYILAN konumla alınıyor (İstanbul "
                       "%g, %g) — lokasyon profili girilmemiş%s"
                       % (_knm.get("enlem", 0), _knm.get("boylam", 0),
                          (" · " + " · ".join(_hv)) if _hv else ""))
        elif _knm:
            st.caption("🌤️ Hava konumu: %s (%g, %g)%s"
                       % (_knm.get("ad") or "—", _knm.get("enlem", 0),
                          _knm.get("boylam", 0),
                          (" · " + " · ".join(_hv)) if _hv else ""))
        elif _hv:
            st.caption("🌤️ " + " · ".join(_hv))

        # ── BU LOKASYONUN GEÇİŞ SAATLERİ ─────────────────────────────
        # 11.10.2026'ya kadar saat anahtarları TEK takımdı; bir hastanenin
        # saatini değiştirmek bütün hastaneleri değiştiriyordu. Artık
        # `oto_gunduz_saat_<lokasyon>` tanımlanabilir; tanımlı değilse genel
        # kural geçerlidir. Değeri BOŞALTMAK genel kurala döndürür (satır
        # silmek RLS'e takılabiliyor, boş değer "tanımsız" sayılır).
        _krl = (_oto or {}).get("kural") or {}
        _ozel_anahtarlar = _krl.get("ozel") or []
        _kg, _kge = _krl.get("gunduz_saat"), _krl.get("gece_saat")
        if isinstance(_kg, int) and isinstance(_kge, int):
            _saat_bas = ("🕐 Geçiş saatleri — gündüz %02d:00 · gece %02d:00  ·  %s"
                         % (_kg, _kge, "bu lokasyona özel" if _ozel_anahtarlar
                            else "genel kural"))
        else:
            _saat_bas = "🕐 Geçiş saatleri — lokasyon henüz bildirmedi"

        with st.expander(_saat_bas):
            # Sunum modunda kontroller GÖRÜNÜR ama pasiftir: paneli göstermek
            # için demo'yu kapatmak gerekmesin, örnek veriye de yazılmasın.
            _demo = _demo_modu()
            try:
                import giris as _gr_iz
                if _gr_iz.izleyici_mi():
                    _demo = True   # izleyici: lokasyon saat ayarı salt okunur
            except Exception:
                pass
            if _demo:
                st.caption("Salt okunur — ayar yazılmaz." if not _demo_modu()
                           else "Sunum modu — ayar yazılmaz.")
            if not isinstance(_kg, int) or not isinstance(_kge, int):
                st.caption("Lokasyon yürürlükteki kuralı henüz bildirmedi "
                           "(güncelleme uygulanınca ilk heartbeat'te gelir).")
            else:
                _s1, _s2 = st.columns(2)
                with _s1:
                    _yg = st.number_input("Gündüz başlangıcı", min_value=0,
                                          max_value=23, value=int(_kg), step=1,
                                          key="lok_gunduz_saat_%s" % lok_id,
                                          disabled=_demo)
                with _s2:
                    _yge = st.number_input("Gece başlangıcı", min_value=0,
                                           max_value=23, value=int(_kge), step=1,
                                           key="lok_gece_saat_%s" % lok_id,
                                           disabled=_demo)

                def _ayar_yaz(anahtar, deger):
                    import urllib.request as _u2, json as _j2
                    _u2.urlopen(_u2.Request(
                        url + "/rest/v1/ayarlar",
                        data=_j2.dumps({"key": anahtar, "value": deger}).encode(),
                        method="POST",
                        headers={"apikey": key, "Authorization": "Bearer " + key,
                                 "Content-Type": "application/json",
                                 "Prefer": "resolution=merge-duplicates"}), timeout=5)

                _b1, _b2 = st.columns(2)
                with _b1:
                    _kayit = st.button("Bu lokasyona özel kaydet",
                                       key="lok_saat_kaydet_%s" % lok_id,
                                       use_container_width=True,
                                       disabled=(_demo or _yg == _yge))
                with _b2:
                    _geri = st.button("Genel kurala dön",
                                      key="lok_saat_sifirla_%s" % lok_id,
                                      use_container_width=True,
                                      disabled=(_demo or not _ozel_anahtarlar))
                if _yg == _yge:
                    st.warning("Gündüz ve gece saati aynı olamaz.")
                if _kayit:
                    try:
                        _ayar_yaz("oto_gunduz_saat_%s" % lok_id, str(int(_yg)))
                        _ayar_yaz("oto_gece_saat_%s" % lok_id, str(int(_yge)))
                        st.success("Kaydedildi — %s için gündüz %02d:00, gece "
                                   "%02d:00. Lokasyon bir sonraki turda uygular."
                                   % (lok_info["kisa"], int(_yg), int(_yge)))
                    except Exception as _e:
                        st.error("Ayar yazılamadı: %s" % _e)
                if _geri:
                    try:
                        _ayar_yaz("oto_gunduz_saat_%s" % lok_id, "")
                        _ayar_yaz("oto_gece_saat_%s" % lok_id, "")
                        st.success("%s genel kurala döndü." % lok_info["kisa"])
                    except Exception as _e:
                        st.error("Ayar yazılamadı: %s" % _e)
            st.caption("Setler yalnızca bu saatlerde gönderilir. Burada "
                       "yapılan değişiklik YALNIZCA bu lokasyonu etkiler; "
                       "genel saat ana ekrandaki OTO SET panelindedir.")

    # ══════════════════════════════════════════════════════
    # SİSTEM SAĞLIĞI (lokasyona özgü)
    # ══════════════════════════════════════════════════════
    # Bu üç gösterge her lokasyon için AYRI anlamlıdır (kendi ayarları, kendi
    # geçmişi, kendi geri bildirimi). Genel özet kartında toplanınca lokasyon
    # sayısı arttıkça okunamaz hale geliyordu — 20.09.2026'da buraya taşındı.
    # _oto yukarıda (YÜRÜRLÜKTEKİ SETLER) tanımlandı — aynı heartbeat sözlüğü
    _oz_test  = bakim_ozet.get("oz_test") or {}
    _geri_bld = bakim_ozet.get("geri_bildirim") or {}

    if _oto or _oz_test or _geri_bld:
        st.markdown("<div style='margin-top:18px'></div>", unsafe_allow_html=True)
        st.markdown('<div class="sec" style="display:flex;align-items:center;gap:6px;">'
                    + _ik.ikon("saglik", 15) + 'SİSTEM SAĞLIĞI</div>', unsafe_allow_html=True)
        sc1, sc2, sc3 = st.columns(3)

        # ── Oto-set: son turda ne yaptı? ──
        with sc1:
            if _oto:
                _sonuc = str(_oto.get("sonuc", ""))
                _iyi = _sonuc in ("yazildi", "gecis_yok", "kapali", "mesgul")
                _renk = "#0ca30c" if _iyi else "#d03b3b"
                _zaman = str(_oto.get("zaman") or "")[11:16]
                _govde = (
                    f"<div style='font-size:15px;color:{_renk};font-weight:700;display:flex;align-items:center;gap:7px;'>"
                    f"{_ik.ikon('tamam' if _iyi else 'hata', 18, _renk)} {_oto.get('metin') or _sonuc or '—'}</div>"
                    + (f"<div style='font-size:10px;color:#46536b;"
                       f"margin-top:4px;'>son tur {_zaman}</div>" if _zaman else "")
                )
                # Son geçişin sahadaki sonucu: gönderilen setler birkaç dakika
                # sonra cihazdan geri okunur (anlık okuma eski değeri gösterir).
                _dgd = _oto.get("dogrulama") or {}
                _dg = _dgd.get("sonuc")
                if _dg == "uygulanmadi":
                    _uy = ", ".join(str(x).replace("_REM_SET", "").replace("_SET", "")
                                    for x in (_dgd.get("uymayan") or [])[:4])
                    _govde += ("<div style='font-size:10px;color:#d03b3b;margin-top:4px;'>"
                               "Set cihazda UYGULANMADI" + (f": {_uy}" if _uy else "") + "</div>")
                elif _dg == "bekliyor":
                    _govde += ("<div style='font-size:10px;color:#c98500;margin-top:4px;'>"
                               "Setler gönderildi — cihazdan doğrulama bekleniyor</div>")
                elif _dg == "uygulandi":
                    _govde += ("<div style='font-size:10px;color:#0ca30c;margin-top:4px;'>"
                               "Son geçişteki tüm setler cihazda doğrulandı</div>")
            else:
                _govde = ("<div style='font-size:12px;color:#46536b;'>"
                          "Bildirim gelmedi</div>")
            st.markdown("<div style='" + KART + "'><div style='" + LBL + "'>" + _ik.ikon("oto", 16) + "OTO-SET</div>"
                        + _govde + "</div>", unsafe_allow_html=True)

        # ── Mekanik Zeka öz testi: lokasyonun KENDİ ayarlarıyla ──
        with sc2:
            if _oz_test:
                _gecti = _oz_test.get("durum") == "GECTI"
                _renk = "#0ca30c" if _gecti else "#d03b3b"
                _kalan = ", ".join(str(d).replace("test_", "").replace(".py", "")
                                   for d in (_oz_test.get("kalan_dosyalar") or [])[:2])
                _govde = (
                    f"<div style='font-size:15px;color:{_renk};font-weight:700;display:flex;align-items:center;gap:7px;'>"
                    f"{_ik.ikon('tamam' if _gecti else 'hata', 18, _renk)} {_oz_test.get('gecen')}/{_oz_test.get('toplam')} "
                    f"{'geçti' if _gecti else 'KALDI'}</div>"
                    + (f"<div style='font-size:10px;color:#d03b3b;margin-top:4px;'>{_kalan}</div>"
                       if _kalan else "")
                    + f"<div style='font-size:10px;color:#46536b;margin-top:4px;'>"
                      f"{str(_oz_test.get('zaman') or '')[:16].replace('T', ' ')}</div>"
                )
            else:
                _govde = ("<div style='font-size:12px;color:#46536b;'>"
                          "Henüz çalışmadı</div>")
            st.markdown("<div style='" + KART + "'><div style='" + LBL + "'>" + _ik.ikon("zeka", 16) + "MEKANİK ZEKA ÖZ TESTİ</div>"
                        + _govde + "</div>", unsafe_allow_html=True)

        # ── Öneri geri bildirimi: öğrenme için yeterli veri var mı? ──
        with sc3:
            if _geri_bld:
                _hazir = _geri_bld.get("ogrenmeye_hazir_kural") or []
                _govde = (
                    f"<div style='font-size:15px;color:#133273;font-weight:700;display:flex;align-items:center;gap:6px;flex-wrap:wrap;'>"
                    f"{_geri_bld.get('geri_bildirim', 0)} geri bildirim "
                    f"<span style='color:#0ca30c;display:inline-flex;align-items:center;gap:3px;'>{_ik.ikon('tamam', 15)}{_geri_bld.get('uygulandi', 0)}</span> "
                    f"<span style='color:#c98500;display:inline-flex;align-items:center;gap:3px;'>{_ik.ikon('hata', 15, '#c98500')}{_geri_bld.get('uygulanmadi', 0)}</span></div>"
                    f"<div style='font-size:10px;color:#46536b;margin-top:4px;'>"
                    f"{_geri_bld.get('kayit', 0)} öneri kaydı</div>"
                )
                if _hazir:
                    _govde += (f"<div style='font-size:10px;color:#0ca30c;margin-top:4px;'>"
                               f"öğrenmeye hazır: {', '.join(_hazir[:2])}</div>")
                else:
                    _govde += ("<div style='font-size:10px;color:#46536b;"
                               "margin-top:4px;'>öğrenme beklemede (kural başına 5 gerekli)</div>")
                _red = _geri_bld.get("en_cok_red") or []
                if _red:
                    _govde += (f"<div style='font-size:10px;color:#c98500;margin-top:4px;'>"
                               f"en çok reddedilen: {_red[0].get('kural')} ({_red[0].get('adet')})</div>")
            else:
                _govde = ("<div style='font-size:12px;color:#46536b;'>"
                          "Bildirim gelmedi</div>")
            st.markdown("<div style='" + KART + "'><div style='" + LBL + "'>" + _ik.ikon("oneri", 16) + "ÖNERİ GERİ BİLDİRİMİ</div>"
                        + _govde + "</div>", unsafe_allow_html=True)



# ════════ TAB: CANLI İZLEME ════════
# Sahadaki sayaçların O ANKİ gücü. Dönem toplamları (kWh) diğer sekmelerde;
# burası "şu anda ne çekiyoruz" sorusunun yeri.
with tab_canli:
    import canli_izleme as _CI

    # Bu SAYFA her çalışmada diskten okunup exec edilir; canli_izleme modülü
    # ise sürece BİR KEZ yüklenir. Yayın sonrası süreç yeniden başlamazsa
    # sayfa yeni, modül eski kalır ve burada olmayan bir işlev çağrılır
    # (21.10.2026: ekranda AttributeError çıktı). Sürüm tutmuyorsa tazele.
    _CI_GEREKEN_SURUM = 7
    if getattr(_CI, "SURUM", 0) < _CI_GEREKEN_SURUM:
        import importlib
        _CI = importlib.reload(_CI)

    _seri_anahtar = "canli_seri_" + str(lok_id)

    # Canlı sayacı olmayan kalemlerden HANGİLERİ bu binada var?
    # Sütun hiç dolmuyorsa o sistem burada yok demektir; kojeni olmayan
    # hastanede "kojen verisi çekilemiyor" yazmak yanlış olurdu.
    _olculmeyen_tum = []
    for _ad, _kolon, _neden in _CI.OLCULMEYEN:
        try:
            if _kolon in df.columns and float(df[_kolon].fillna(0).abs().sum()) > 0:
                _olculmeyen_tum.append((_ad, _neden))
        except Exception:
            pass

    @st.fragment(run_every="3s")
    def _canli_izleme_blok():
        try:
            _canli_izleme_ciz()
        except Exception as _hata:
            # Canlı bölüm 3 saniyede bir yenileniyor; buradaki bir hata
            # sayfayı baştan sona kırmızı traceback'le kaplıyordu. Hata
            # SAKLANMAZ — açılır kutuda durur — ama sekmenin geri kalanı
            # ve diğer sekmeler çalışmaya devam eder.
            st.warning("Canlı izleme şu an çizilemedi. Sayfayı yenilemeyi deneyin.")
            with st.expander("Teknik ayrıntı"):
                st.code("%s: %s" % (type(_hata).__name__, _hata))

    def _canli_izleme_ciz():
        pencere_sn = _CI.PENCERELER.get(
            st.session_state.get("canli_pencere", _CI.VARSAYILAN_PENCERE), 300)

        olcumler, yas = fetch_canli_guc(url, key, lok_id)
        seri = _CI.seri_guncelle(
            st.session_state.get(_seri_anahtar), olcumler, pencere_sn)
        st.session_state[_seri_anahtar] = seri

        degerler = _CI.son_degerler(seri)
        if not degerler and not olcumler:
            st.info("Bu lokasyonda canlı sayaç okuması yok. Sayaçlar bağlı "
                    "değilse ya da lokasyon çevrimdışıysa bu bölüm boş kalır.")
            return

        _yontemler = {o.get("cihaz"): o.get("yontem") for o in (olcumler or [])}
        _gruplar = _CI.gruplara_ayir(list(degerler))
        _aralik = _CI.olcum_araligi_sn(seri)
        _okunan_top = sum(1 for v in degerler.values() if v is not None)
        # Canlı sayacı gelen kalem "ölçülmüyor" diye ayrıca yazılmaz
        _canli_gruplar = {g for g, _, _ in _gruplar}
        _olculmeyen = [(a, n) for a, n in _olculmeyen_tum
                       if _CI.OLCULMEYEN_GRUP.get(a) not in _canli_gruplar]

        # ── Üst şerit ────────────────────────────────────────────────
        _kartlar, _grup_govde = [], []
        for _an, _bas, _cihazlar in _gruplar:
            _tp = _CI.grup_toplami(seri, _cihazlar)
            _ok = sum(1 for _c in _cihazlar if degerler.get(_c) is not None)
            _br = _CI.birim(_an)

            if _an == "enerji":
                _etiket, _alt = "ŞEBEKEDEN ÇEKİLEN", "%d trafo" % len(_cihazlar)
                if yas is not None:
                    _alt += " · son ölçüm %.0f sn önce" % yas
            elif _an == "sogutma":
                _ch = sum(1 for _c in _cihazlar
                          if _CI.kisa_ad(_c).startswith("CH-") and (degerler.get(_c) or 0) >= 1)
                _ku = sum(1 for _c in _cihazlar
                          if _c.upper().startswith("KULE") and (degerler.get(_c) or 0) >= 1)
                _etiket, _alt = _bas, "%d chiller + %d kule çalışıyor" % (_ch, _ku)
            elif _an == "kojen":
                _calisan = sum(1 for _c in _cihazlar if (degerler.get(_c) or 0) >= 1)
                _etiket, _alt = _bas, "%d / %d kojen çalışıyor" % (_calisan, len(_cihazlar))
            elif _an in ("dogalgaz", "su"):
                _etiket, _alt = _bas, "anlık debi · %d sayaç" % len(_cihazlar)
            else:
                _etiket = _bas
                _alt = "%d pano" % len(_cihazlar)
                if _aralik:
                    _alt += " · %d sn'de bir okunuyor" % _aralik
            _kartlar.append(_CI.ozet_kart_html(
                _etiket, "—" if _tp is None else _CI.tr_sayi(_tp) +
                f"<span class='cg-br'>{_br}</span>", _alt, canli=(_an == "enerji")))

            # ── Grup gövdesi ─────────────────────────────────────────
            # Çubukların ölçeği: bu gruptaki sayaçların pencere boyunca
            # gördüğü EN YÜKSEK değer. Toplam satırı ölçeğe katılmaz,
            # yoksa trafoların hepsi toplamın yanında cüce kalırdı.
            _olcek = _CI.olcek_degeri(seri, _cihazlar)
            _satirlar = ""
            if _an == "enerji" and len(_cihazlar) > 1:
                # Trafoların toplamı KENDİ ölçeğinde çizilir
                _ust_olcek = max((v for v in _CI.toplam_seri(seri, _cihazlar)
                                  if v is not None), default=0.0)
                _satirlar += _CI.toplam_satir_html(
                    "ŞEBEKE", _tp, _CI.bar_html(_tp, _ust_olcek))
            for _c in _cihazlar:
                _satirlar += _CI.satir_html(
                    _c, degerler.get(_c),
                    _CI.bar_html(degerler.get(_c), _olcek, birim=_br,
                                 esikli=_an not in _CI.ESIKSIZ_GRUPLAR),
                    _yontemler.get(_c), birim=_br)
            _olcusuz = 0
            if _an == "enerji":
                for _ad, _neden in _olculmeyen:
                    _satirlar += _CI.olculmeyen_satir_html(_ad, _neden)
                _olcusuz = len(_olculmeyen)

            _ack = _CI.GRUP_ACIKLAMA.get(_an, "")
            if _an == "enerji" and _olculmeyen:
                _ack = ("Şebeke trafoları canlı sayaçtan; " +
                        ", ".join(a.lower() for a, _ in _olculmeyen) +
                        " kalemlerinde canlı sayaç yok")
            _grup_govde.append(_CI.grup_html(_bas, _ack, _satirlar, _tp, _ok, _olcusuz, birim=_br))

        _kartlar.append(_CI.ozet_kart_html(
            "OKUNABİLEN SAYAÇ",
            "%d<span class='cg-br'>/ %d</span>" % (_okunan_top, len(degerler) + len(_olculmeyen)),
            "%d kalem canlı ölçülmüyor" % len(_olculmeyen) if _olculmeyen
            else "tüm kalemler ölçülüyor"))

        _yontem_metin, _yontem_renk = _CI.yontem_ozeti(olcumler)
        _ozet_metin = "%d sayaç okunuyor" % _okunan_top
        if _olculmeyen:
            _ozet_metin += ", %d kalemde canlı sayaç yok" % len(_olculmeyen)
        if yas is not None:
            _ozet_metin += " · son ölçüm %.0f sn önce" % yas

        st.markdown(
            _CI.STIL + _CI.ozet_serit_html(_kartlar)
            + "<div class='cg-sarmal'>" + "".join(_grup_govde) + "</div>"
            + _CI.alt_bant_html(_yontem_metin, _yontem_renk, _ozet_metin),
            unsafe_allow_html=True)

    _canli_izleme_blok()

    # Pencere seçimi FRAGMENT DIŞINDA ve altta: kendi kendine yenilenen bir
    # bölümün içindeki widget her turda yeniden kurulur ve seçim elden kayar.
    # Seçim burada yapılır, fragment session_state'ten okur.
    _bos, _sag = st.columns([4, 1])
    with _sag:
        st.selectbox(
            "Pencere", list(_CI.PENCERELER),
            index=list(_CI.PENCERELER).index(_CI.VARSAYILAN_PENCERE),
            key="canli_pencere",
            help="Satır grafiklerinde kaç dakikalık geçmiş görünsün. Seri "
                 "merkezin oturumunda tutulur, veri tabanında yer kaplamaz; "
                 "sekme açıldığında boş başlar ve pencere süresince dolar.")
