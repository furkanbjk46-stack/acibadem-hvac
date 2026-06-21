# app_merkez.py
# Acıbadem Genel Merkez — Tek Sayfa Komuta Merkezi
# Harita ortada, widget'lar etrafında — Koyu Mavi / Neon
# v: 2026-05-27

from __future__ import annotations
import os, json
import numpy as np
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(
    page_title="ACIBADEM-SYNAPSE",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

from streamlit_autorefresh import st_autorefresh
st_autorefresh(interval=10000, key="autorefresh")  # 10 saniye

# ============ CSS ============
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Playfair+Display:wght@400;600&family=Plus+Jakarta+Sans:wght@300;400;500;600;700&display=swap');

html, body {
    margin: 0 !important;
    padding: 0 !important;
    height: 100% !important;
}
html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"], [data-testid="stMain"] {
    background-color: #060b14 !important;
    background-image: radial-gradient(circle at 50% 0%, #0f172a 0%, #020617 100%) !important;
    min-height: 100vh !important;
}
[data-testid="stAppViewContainer"] {
    background-color: #060b14 !important;
    background-image: radial-gradient(circle at 50% 0%, #0f172a 0%, #020617 100%) !important;
}
[data-testid="stMain"] { padding: 0 !important; margin: 0 !important; height: 100vh !important; overflow: hidden !important; }
[data-testid="stHeader"]                  { display: none !important; height: 0 !important; }
[data-testid="collapsedControl"]          { display: none !important; visibility: hidden !important; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; visibility: hidden !important; }
section[data-testid="stSidebarCollapsedControl"] { display: none !important; }
.stSidebarCollapsedControl               { display: none !important; }
button[kind="header"]                    { display: none !important; }
#MainMenu                                { display: none !important; }
header[data-testid="stHeader"] button    { display: none !important; }
[data-testid="stSidebar"]      { display: none !important; }
[data-testid="stToolbar"]      { display: none !important; }

/* Sayfa: header + footer kendi boylarını alır, kolon satırı kalan TÜM boşluğu doldurur (taşma/boşluk yok) */
.block-container {
    display: flex !important;
    flex-direction: column !important;
    height: 100vh !important;
    max-height: 100vh !important;
    overflow: hidden !important;
    padding: 0.4rem 0.75rem 0.3rem 0.75rem !important;
    max-width: 100% !important;
    box-sizing: border-box !important;
}
[data-testid="stHorizontalBlock"] {
    flex: 1 1 auto !important;
    min-height: 0 !important;
    overflow: hidden !important;
}
[data-testid="stHorizontalBlock"] [data-testid="column"] {
    height: 100% !important;
}

/* Harita iframe — kolonun tamamını doldursun */
[data-testid="column"]:nth-child(3) [data-testid="stIFrame"],
[data-testid="column"]:nth-child(3) iframe {
    width: 100% !important;
    height: 100% !important;
    border: none !important;
}
[data-testid="column"]:nth-child(3) [data-testid="element-container"] {
    height: 100% !important;
}
[data-testid="column"]:nth-child(3) [data-testid="stVerticalBlock"] {
    height: 100% !important;
}

/* Tüm yazılar */
h1,h2,h3,h4,h5,h6 { color: #f8fafc !important; font-family: 'Playfair Display', 'Plus Jakarta Sans', serif !important; font-weight: 400 !important; }
p, span, div, label { color: #cbd5e1 !important; font-family: 'Plus Jakarta Sans', sans-serif !important; }

/* Streamlit Material ikon istisnası — _arrow_right gibi ikonların bozulmaması için */
span[data-testid="stIconMaterial"],
[data-testid="stExpanderToggleIcon"] span,
button span[data-testid="stIconMaterial"] {
    font-family: 'Material Symbols Rounded' !important;
    color: inherit !important;
}

/* Metrik */
[data-testid="stMetricValue"]  { color: #38bdf8 !important; font-size: 22px !important; font-weight: 800 !important; font-family: 'Playfair Display', 'Plus Jakarta Sans', serif !important; text-shadow: 0 0 15px rgba(56, 189, 248,0.5) !important; }
[data-testid="stMetricLabel"]  { color: rgba(150,210,255,0.7) !important; font-size: 10px !important; letter-spacing: 1px !important; text-transform: uppercase !important; }
[data-testid="stMetricDelta"]  { color: #10b981 !important; }
[data-testid="metric-container"] {
    background: rgba(15, 23, 42, 0.4) !important;
    backdrop-filter: blur(12px) !important;
    border: 1px solid rgba(255, 255, 255, 0.05) !important;
    border-radius: 8px !important;
    padding: 12px !important;
    box-shadow: none !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 3px; }
::-webkit-scrollbar-track { background: #0f172a; }
::-webkit-scrollbar-thumb { background: rgba(56,189,248,0.3); border-radius: 3px; }

/* Neon kart */
.nk {
    background: rgba(15, 23, 42, 0.4);
    backdrop-filter: blur(12px);
    border: 1px solid rgba(255, 255, 255, 0.05);
    border-radius: 8px;
    padding: 14px;
    margin-bottom: 10px;
    box-shadow: none;
}
.nk-green { border-color: rgba(16,185,129,0.45) !important; box-shadow: 0 0 15px rgba(16,185,129,0.08) !important; }
.nk-red   { border-color: rgba(239,68,68,0.45) !important;  box-shadow: 0 0 15px rgba(239,68,68,0.08) !important;  }
.nk-gray  { border-color: rgba(100,120,150,0.3) !important; opacity: 0.6; }
.nk {
    display: block !important;
    text-decoration: none !important;
    cursor: pointer;
    transition: border-color 0.2s, transform 0.15s;
}
.nk:hover { transform: translateY(-2px); border-color: rgba(56, 189, 248,0.5) !important; }

.lok-scroll {
    max-height: 492px;
    overflow-y: auto;
    overflow-x: hidden;
    padding-right: 3px;
    scrollbar-width: thin;
    scrollbar-color: rgba(56, 189, 248,0.35) rgba(15,23,42,0.6);
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 10px;
    align-content: start;
}
.lok-scroll .nk { margin-bottom: 0 !important; }

.ozet-grid {
    display: grid;
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
}
.lok-scroll::-webkit-scrollbar { width: 4px; }
.lok-scroll::-webkit-scrollbar-track { background: rgba(15,23,42,0.6); border-radius: 2px; }
.lok-scroll::-webkit-scrollbar-thumb { background: rgba(56, 189, 248,0.28); border-radius: 2px; }
.lok-scroll::-webkit-scrollbar-thumb:hover { background: rgba(56, 189, 248,0.55); }

.sec { font-family:'Playfair Display','Plus Jakarta Sans',serif; font-size:10px; color:rgba(56, 189, 248,0.7);
       letter-spacing:2px; text-transform:uppercase; border-bottom:1px solid rgba(56, 189, 248,0.15);
       padding-bottom:5px; margin-bottom:10px; }

/* Sol kolon (Lokasyon Durumu + Global Özet) tek bir cam kart içinde */
[data-testid="stVerticalBlock"]:has(> [data-testid="stVerticalBlockBorderWrapper"] #syn-sol-panel),
[data-testid="stVerticalBlock"]:has(#syn-sol-panel) {
    background: rgba(15, 23, 42, 0.45) !important;
    backdrop-filter: blur(14px) !important;
    -webkit-backdrop-filter: blur(14px) !important;
    border: 1px solid rgba(255, 255, 255, 0.06) !important;
    border-radius: 14px !important;
    padding: 14px !important;
    box-shadow: 0 8px 28px 0 rgba(0,0,0,0.35) !important;
    height: 100% !important;
    max-height: 100% !important;
    overflow-y: auto !important;
    box-sizing: border-box !important;
}
/* Tek kart içinde tekrar eden iç kutu görünümünü hafiflet */
[data-testid="stVerticalBlock"]:has(#syn-sol-panel) .nk {
    background: rgba(255,255,255,0.02) !important;
    box-shadow: none !important;
}

/* Sağ kolon (Canlı Uyarılar + Oto Set + Dış Hava + Enerji Zekası + Otomatik Analiz) tek cam kart */
[data-testid="stVerticalBlock"]:has(> [data-testid="stVerticalBlockBorderWrapper"] #syn-sag-panel),
[data-testid="stVerticalBlock"]:has(#syn-sag-panel) {
    background: rgba(15, 23, 42, 0.45) !important;
    backdrop-filter: blur(14px) !important;
    -webkit-backdrop-filter: blur(14px) !important;
    border: 1px solid rgba(255, 255, 255, 0.06) !important;
    border-radius: 14px !important;
    padding: 14px !important;
    box-shadow: 0 8px 28px 0 rgba(0,0,0,0.35) !important;
    height: 100% !important;
    max-height: 100% !important;
    overflow-y: auto !important;
    box-sizing: border-box !important;
}

.alrt-r { background:rgba(239,68,68,0.12); border:1px solid rgba(239,68,68,0.35);
           border-radius:8px; padding:7px 10px; margin:3px 0; font-size:11px; color:#fca5a5 !important; }
.alrt-y { background:rgba(245,158,11,0.12); border:1px solid rgba(245,158,11,0.35);
           border-radius:8px; padding:7px 10px; margin:3px 0; font-size:11px; color:#fcd34d !important; }
.alrt-g { background:rgba(16,185,129,0.12); border:1px solid rgba(16,185,129,0.35);
           border-radius:8px; padding:7px 10px; margin:3px 0; font-size:11px; color:#6ee7b7 !important; }

@keyframes pulse {
  0%   { opacity: 0.6; transform: scale(0.95); }
  50%  { opacity: 1;   transform: scale(1.05); }
  100% { opacity: 0.6; transform: scale(0.95); }
}
@keyframes breathe {
  0%, 100% { box-shadow: 0 0 4px currentColor, 0 0 8px currentColor;  transform: scale(1);    opacity: 0.85; }
  50%       { box-shadow: 0 0 10px currentColor, 0 0 22px currentColor, 0 0 36px currentColor; transform: scale(1.25); opacity: 1; }
}
@keyframes breathe-ring {
  0%, 100% { transform: scale(0.88); opacity: 0.25; }
  50%       { transform: scale(1.12); opacity: 0.55; }
}
@keyframes neon-breathe {
  0%, 100% {
    text-shadow:
      0 0 10px rgba(56, 189, 248,0.4),
      0 0 25px rgba(56, 189, 248,0.2),
      0 0 50px rgba(56, 189, 248,0.08);
    opacity: 0.82;
  }
  50% {
    text-shadow:
      0 0 20px rgba(56, 189, 248,1),
      0 0 45px rgba(56, 189, 248,0.7),
      0 0 90px rgba(56, 189, 248,0.35),
      0 0 140px rgba(56, 189, 248,0.15);
    opacity: 1;
  }
}
@keyframes neon-breathe-sub {
  0%, 100% { opacity: 0.35; letter-spacing: 4px; }
  50%       { opacity: 0.65; letter-spacing: 5px; }
}

.btn-refresh button {
    background: rgba(14, 165, 233, 0.15) !important;
    color: #38bdf8 !important; border: 1px solid rgba(14, 165, 233, 0.3) !important;
    border-radius: 6px !important; font-size: 11px !important;
    padding: 4px 12px !important; font-family:'Plus Jakarta Sans',sans-serif !important;
}
.btn-refresh button:hover {
    background: rgba(14, 165, 233, 0.25) !important;
    color: #ffffff !important;
}

/* Alarm expander */
[data-testid="stExpander"] {
    background: rgba(15, 23, 42, 0.4) !important;
    border: 1px solid rgba(255, 255, 255, 0.05) !important;
    border-radius: 8px !important;
    margin-bottom: 5px !important;
}
[data-testid="stExpander"]:has(.alrt-exp-r) {
    border-color: rgba(239,68,68,0.45) !important;
    background: rgba(239,68,68,0.05) !important;
}
[data-testid="stExpander"]:has(.alrt-exp-y) {
    border-color: rgba(245,158,11,0.35) !important;
    background: rgba(245,158,11,0.04) !important;
}
[data-testid="stExpanderToggleIcon"] { color: rgba(56, 189, 248,0.6) !important; }
.alrt-detay-r {
    background: rgba(239,68,68,0.10); border-left: 3px solid #ef4444;
    border-radius: 6px; padding: 8px 12px; margin: 4px 0;
    font-size: 12px; color: #fca5a5 !important;
}
.alrt-detay-y {
    background: rgba(245,158,11,0.10); border-left: 3px solid #f59e0b;
    border-radius: 6px; padding: 8px 12px; margin: 4px 0;
    font-size: 12px; color: #fcd34d !important;
}
.alarm-detay-kart {
    background: rgba(0,0,0,0.25);
    border: 1px solid rgba(255,255,255,0.05);
    border-radius: 8px; padding: 10px 14px; margin-top: 8px;
}
.btn-goto button {
    background: rgba(14, 165, 233, 0.15) !important;
    color: #38bdf8 !important;
    border: 1px solid rgba(14, 165, 233, 0.3) !important;
    border-radius: 6px !important;
    font-size: 11px !important;
    padding: 4px 14px !important;
    width: 100% !important;
}
.btn-goto button:hover { background: rgba(14, 165, 233, 0.25) !important; color: #ffffff !important; }
</style>
""", unsafe_allow_html=True)


# ============ SABİT VERİ ============
HASTANELER = {
    # ── İstanbul ──
    "maslak":       {"isim": "Acıbadem Maslak",        "kisa": "MASLAK",        "lat": 41.1273, "lon": 29.0246, "m2": 15000, "renk": "#38bdf8"},
    "altunizade":   {"isim": "Acıbadem Altunizade",    "kisa": "ALTUNİZADE",    "lat": 41.0189, "lon": 29.0458, "m2": 10000, "renk": "#f59e0b"},
    "kozyatagi":    {"isim": "Acıbadem Kozyatağı",     "kisa": "KOZYATAĞİ",    "lat": 40.9766, "lon": 29.0928, "m2": 12000, "renk": "#10b981"},
    "taksim":       {"isim": "Acıbadem Taksim",        "kisa": "TAKSİM",        "lat": 41.0417, "lon": 28.9827, "m2":  8000, "renk": "#a855f7"},
    "atakent":      {"isim": "Acıbadem Atakent",       "kisa": "ATAKENT",       "lat": 41.0349, "lon": 28.7789, "m2": 20000, "renk": "#f97316"},
    "atasehir":     {"isim": "Acıbadem Ataşehir",      "kisa": "ATAŞEHİR",      "lat": 40.9934, "lon": 29.1213, "m2": 14000, "renk": "#06b6d4"},
    "bakirkoy":     {"isim": "Acıbadem Bakırköy",      "kisa": "BAKIRKÖY",      "lat": 40.9776, "lon": 28.8731, "m2": 12000, "renk": "#84cc16"},
    "fulya":        {"isim": "Acıbadem Fulya",         "kisa": "FULYA",         "lat": 41.0557, "lon": 28.9994, "m2":  9000, "renk": "#e879f9"},
    "international":{"isim": "Acıbadem International", "kisa": "INTERNAT.",     "lat": 40.9590, "lon": 28.8354, "m2": 18000, "renk": "#14b8a6"},
    "kadikoy":      {"isim": "Acıbadem Kadıköy",       "kisa": "KADİKÖY",       "lat": 41.0072, "lon": 29.0429, "m2":  8000, "renk": "#ec4899"},
    "kartal":       {"isim": "Acıbadem Kartal",        "kisa": "KARTAL",        "lat": 40.8860, "lon": 29.2041, "m2": 11000, "renk": "#ef4444"},
    # ── Ankara ──
    "ankara":         {"isim": "Acıbadem Ankara",          "kisa": "ANKARA",       "lat": 39.9179, "lon": 32.8626, "m2": 16000, "renk": "#fb7185"},
    "bayindir":       {"isim": "Acıbadem Bayındır Söğütözü","kisa": "BAYINDIR",    "lat": 39.8980, "lon": 32.8240, "m2": 12000, "renk": "#f43f5e"},
    # ── Bursa ──
    "bursa":          {"isim": "Acıbadem Bursa",            "kisa": "BURSA",        "lat": 40.2090, "lon": 28.9790, "m2": 13000, "renk": "#fbbf24"},
    # ── Kocaeli ──
    "kocaeli":        {"isim": "Acıbadem Kocaeli",          "kisa": "KOCAELİ",      "lat": 40.7654, "lon": 29.9408, "m2": 10000, "renk": "#34d399"},
    # ── Eskişehir ──
    "eskisehir":      {"isim": "Acıbadem Eskişehir",        "kisa": "ESKİŞEHİR",    "lat": 39.7767, "lon": 30.5206, "m2":  9000, "renk": "#818cf8"},
    # ── İzmir ──
    "izmir":          {"isim": "Acıbadem İzmir Kent",       "kisa": "İZMİR",        "lat": 38.4192, "lon": 27.1287, "m2": 15000, "renk": "#38bdf8"},
    # ── Kayseri ──
    "kayseri":        {"isim": "Acıbadem Kayseri",          "kisa": "KAYSERİ",      "lat": 38.7225, "lon": 35.4875, "m2": 11000, "renk": "#a78bfa"},
    # ── Adana ──
    "adana":          {"isim": "Acıbadem Adana",            "kisa": "ADANA",        "lat": 37.0000, "lon": 35.3213, "m2": 12000, "renk": "#f472b6"},
    "adana_ortopedia":{"isim": "Acıbadem Adana Ortopedia",  "kisa": "ADANA ORT.",   "lat": 37.0100, "lon": 35.3350, "m2":  5000, "renk": "#e879f9"},
    # ── Muğla / Bodrum ──
    "bodrum":         {"isim": "Acıbadem Bodrum",           "kisa": "BODRUM",       "lat": 37.0344, "lon": 27.4305, "m2":  7000, "renk": "#2dd4bf"},
}

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "configs", "merkez_config.json")

def load_config():
    # Streamlit Cloud: önce st.secrets'a bak
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
    # Yerel PC: dosyadan oku
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def hex_rgba(h, a=0.1):
    h = h.lstrip("#")
    r,g,b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    return f"rgba({r},{g},{b},{a})"

@st.cache_data(ttl=300, show_spinner=False)
def fetch_dis_hava() -> float | None:
    """İstanbul anlık sıcaklık. Önce Open-Meteo, olmadı wttr.in."""
    # 1) Open-Meteo API
    import urllib.request as _ur2, json as _json
    try:
        _om_url = "https://api.open-meteo.com/v1/forecast?latitude=41.0082&longitude=28.9784&current=temperature_2m&timezone=Europe%2FIstanbul"
        with _ur2.urlopen(_om_url, timeout=8) as r:
            return float(_json.loads(r.read())["current"]["temperature_2m"])
    except Exception:
        pass

    # 3) Fallback: wttr.in (Cloudflare CDN üzerinde, çok güvenilir)
    try:
        with _ur2.urlopen("https://wttr.in/Istanbul?format=j1", timeout=8) as r:
            return float(_json.loads(r.read())["current_condition"][0]["temp_C"])
    except Exception:
        pass

    return None


def _dis_hava_log_yaz(sb_url: str, sb_key: str, derece: float, kaynak: str = "api"):
    """Dış hava değerini dis_hava_log tablosuna yaz. Saatte 1'den fazla yazmaz."""
    try:
        from supabase import create_client as _cc
        _c = _cc(sb_url, sb_key)
        # Son kayıt 55 dakikadan yeniyse tekrar yazma
        _son = _c.table("dis_hava_log") \
                  .select("timestamp") \
                  .order("timestamp", desc=True) \
                  .limit(1).execute()
        if _son.data:
            _son_zaman = pd.Timestamp(_son.data[0]["timestamp"])
            if (pd.Timestamp.now(tz="UTC") - _son_zaman.tz_convert("UTC")).total_seconds() < 3300:
                return  # 55 dakika geçmemiş, yazma
        _c.table("dis_hava_log").insert({
            "derece": round(derece, 2),
            "kaynak": kaynak,
        }).execute()
    except Exception:
        pass  # Log yazma hatası ana akışı etkilemesin

@st.cache_data(ttl=120, show_spinner=False)
def fetch_energy(url, key):
    try:
        from supabase import create_client
        c = create_client(url, key)
        all_data = []
        offset = 0
        batch = 1000
        while True:
            r = c.table("energy_data").select("*").order("Tarih", desc=False).range(offset, offset + batch - 1).execute()
            if not r.data:
                break
            all_data.extend(r.data)
            if len(r.data) < batch:
                break
            offset += batch
        if all_data:
            df = pd.DataFrame(all_data)
            if "Tarih" in df.columns:
                df["Tarih"] = pd.to_datetime(df["Tarih"], errors="coerce")
            for col in df.columns:
                if col not in ["id","lokasyon_id","Tarih","Kar_Eritme_Aktif"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            # Mükerrer tarihleri temizle (aynı lokasyon + tarih kombinasyonu)
            if "lokasyon_id" in df.columns:
                df = df.drop_duplicates(subset=["lokasyon_id", "Tarih"], keep="last")
            return df, None
        return pd.DataFrame(), None
    except Exception as e:
        return pd.DataFrame(), str(e)

@st.cache_data(ttl=30, show_spinner=False)
def fetch_lokasyonlar(url, key):
    try:
        from supabase import create_client
        c = create_client(url, key)
        r = c.table("lokasyonlar").select("*").execute()
        return r.data or []
    except:
        return []

@st.cache_data(ttl=60, show_spinner=False)
def fetch_m2_supabase(url, key):
    """Supabase ayarlar tablosundan m² değerlerini çek."""
    try:
        from supabase import create_client
        import json as _json
        c = create_client(url, key)
        r = c.table("ayarlar").select("value").eq("key", "m2_degerler").execute()
        if r.data:
            return _json.loads(r.data[0]["value"])
    except Exception:
        pass
    return {}

def save_m2_supabase(url, key, m2_dict):
    """m² değerlerini Supabase ayarlar tablosuna kaydet."""
    from supabase import create_client
    import json as _json
    c = create_client(url, key)
    c.table("ayarlar").upsert({
        "key": "m2_degerler",
        "value": _json.dumps({k: int(v) for k, v in m2_dict.items()})
    }).execute()

# ═══════════════════════════════════════════════════════════════
# OTOMATİK SET KONTROLÜ — 3 günlük tahmin + histerezis
# ═══════════════════════════════════════════════════════════════

# Chiller: 4 bölge, ±2°C histerezis
_CH_SINIRLAR = [7.0, 23.0, 26.0]
_CH_MODLAR   = ["koc_soguk", "serin", "ilimli", "sicak"]
_CH_SET      = {"koc_soguk": 8.0, "serin": 7.5, "ilimli": 7.0, "sicak": 6.5}
_CH_H        = 2.0

# Kollektor / FCU / AHU: tek eşik 20°C, ±2°C histerezis
_DIG_ESIK = 20.0
_DIG_H    = 2.0
_DIG_SET  = {
    "sogutma": {
        "GUNDUZ_KOLLEKTOR_SET":    13.0,
        "GECE_KOLLEKTOR_SET":      15.0,
        "A_BLOK_FCU_SET":          12.0,
        "B_BLOK_FCU_SET":          12.0,
        "ZON1_KLIMA_SANTRALI_SET":  8.0,
        "ZON2_KLIMA_SANTRALI_SET":  8.0,
    },
    "isitma": {
        "GUNDUZ_KOLLEKTOR_SET":    14.0,
        "GECE_KOLLEKTOR_SET":      16.0,
        "A_BLOK_FCU_SET":          14.0,
        "B_BLOK_FCU_SET":          14.0,
        "ZON1_KLIMA_SANTRALI_SET": 10.0,
        "ZON2_KLIMA_SANTRALI_SET": 10.0,
    },
}
_CH_NOKTALAR = ["CH1_REM_SET","CH2_REM_SET","CH3_REM_SET","CH4_REM_SET","CH5_REM_SET"]


def _fetch_yarin_tahmin() -> dict | None:
    """Open-Meteo'dan yarının gündüz max ve gece min sıcaklığını döner."""
    try:
        import urllib.request as _ur, json as _jj
        _api = (
            "https://api.open-meteo.com/v1/forecast"
            "?latitude=41.0082&longitude=28.9784"
            "&daily=temperature_2m_max,temperature_2m_min"
            "&timezone=Europe%2FIstanbul&forecast_days=3"
        )
        with _ur.urlopen(_api, timeout=8) as _r:
            _d = _jj.loads(_r.read())
        return {
            "max": round(_d["daily"]["temperature_2m_max"][1], 1),  # yarın max (gündüz)
            "min": round(_d["daily"]["temperature_2m_min"][1], 1),  # yarın min (gece)
        }
    except Exception:
        return None


def _ch_modu_hesapla(ort: float, mevcut: str) -> str:
    """4 bölgeli chiller modu — ±2°C histerezis."""
    if mevcut not in _CH_MODLAR:
        # Bilinmiyor: doğrudan hesapla
        for i, sinir in enumerate(_CH_SINIRLAR):
            if ort < sinir:
                return _CH_MODLAR[i]
        return _CH_MODLAR[-1]
    idx = _CH_MODLAR.index(mevcut)
    if idx < len(_CH_SINIRLAR) and ort > _CH_SINIRLAR[idx] + _CH_H:
        return _CH_MODLAR[idx + 1]
    if idx > 0 and ort < _CH_SINIRLAR[idx - 1] - _CH_H:
        return _CH_MODLAR[idx - 1]
    return mevcut


def _dig_modu_hesapla(ort: float, mevcut: str) -> str:
    """Kollektor/FCU/AHU ikili mod — ±2°C histerezis."""
    if mevcut == "sogutma":
        return "isitma" if ort < _DIG_ESIK - _DIG_H else "sogutma"
    if mevcut == "isitma":
        return "sogutma" if ort > _DIG_ESIK + _DIG_H else "isitma"
    return "sogutma" if ort >= _DIG_ESIK else "isitma"


def _oto_set_kontrol(sb_url: str, sb_key: str):
    """
    Yarınki gündüz/gece tahminlerine göre dönem bazlı set kontrolü.
    06:00–19:00 → yarın max (gündüz seti) / 19:00–06:00 → yarın min (gece seti)
    Dönem geçişinde (06:00 / 19:00) her zaman komut gönderilir.
    """
    import urllib.request as _ur2, json as _jj2
    from datetime import datetime as _dtt, timezone as _tz, timedelta as _td

    _IST = _tz(_td(hours=3))  # Türkiye UTC+3 (sabit, DST yok)

    try:
        # ── OTO SET aktif mi kontrol et ──
        _aktif_req = _ur2.Request(
            sb_url + "/rest/v1/ayarlar?key=eq.oto_set_aktif&select=value",
            headers={"apikey": sb_key, "Authorization": "Bearer " + sb_key}
        )
        with _ur2.urlopen(_aktif_req, timeout=4) as _ar:
            _aktif_data = _jj2.loads(_ar.read())
        _oto_aktif = (_aktif_data[0]["value"] == "true") if _aktif_data else True
        if not _oto_aktif:
            logging.getLogger(__name__).info("oto_set_kontrol: devre disi, atlanıyor.")
            return

        tahmin = _fetch_yarin_tahmin()
        if tahmin is None:
            return

        # Dönem belirle: gündüz 06:00–19:00, gece 19:00–06:00 (İstanbul UTC+3)
        _saat = _dtt.now(_IST).hour
        _gunduz = 6 <= _saat < 19
        _donem  = "gunduz" if _gunduz else "gece"
        _ref    = tahmin["max"] if _gunduz else tahmin["min"]

        def _sb_ayar_oku(k):
            _q = _ur2.Request(
                sb_url + f"/rest/v1/ayarlar?key=eq.{k}&select=value",
                headers={"apikey": sb_key, "Authorization": "Bearer " + sb_key}
            )
            with _ur2.urlopen(_q, timeout=6) as _r:
                _d = _jj2.loads(_r.read())
            return _d[0]["value"] if _d else ""

        def _sb_ayar_yaz(k, v):
            _p = _jj2.dumps({"key": k, "value": v}).encode()
            _q = _ur2.Request(
                sb_url + "/rest/v1/ayarlar",
                data=_p,
                headers={
                    "apikey": sb_key, "Authorization": "Bearer " + sb_key,
                    "Content-Type": "application/json",
                    "Prefer": "resolution=merge-duplicates,return=minimal",
                },
                method="POST"
            )
            _ur2.urlopen(_q, timeout=6)

        mevcut_ch    = _sb_ayar_oku("oto_mod_chiller")
        mevcut_dig   = _sb_ayar_oku("oto_mod_diger")
        mevcut_donem = _sb_ayar_oku("oto_donem")  # son uygulanan dönem

        yeni_ch  = _ch_modu_hesapla(_ref, mevcut_ch)
        yeni_dig = _dig_modu_hesapla(_ref, mevcut_dig)

        ch_degisti    = yeni_ch  != mevcut_ch
        dig_degisti   = yeni_dig != mevcut_dig
        donem_degisti = _donem   != mevcut_donem  # 06:00 veya 19:00 geçişi

        # Dönem değişmedi ve mod değişmedi → sadece kontrol zamanını güncelle
        if not ch_degisti and not dig_degisti and not donem_degisti:
            _sb_ayar_yaz("oto_set_son_kontrol", _jj2.dumps({
                "zaman": _dtt.now(_IST).isoformat(),
                "donem": _donem, "ref_sicaklik": _ref,
                "yarin_max": tahmin["max"], "yarin_min": tahmin["min"],
                "chiller_mod": yeni_ch, "diger_mod": yeni_dig, "komut_sayisi": 0
            }))
            return

        # Aktif lokasyonları lokasyon_noktalar'dan çek
        _lq = _ur2.Request(
            sb_url + "/rest/v1/lokasyon_noktalar?select=lokasyon",
            headers={"apikey": sb_key, "Authorization": "Bearer " + sb_key}
        )
        with _ur2.urlopen(_lq, timeout=6) as _r:
            _loks = list({x["lokasyon"] for x in _jj2.loads(_r.read())})

        komutlar = []
        # Dönem geçişinde her iki grubu da gönder; sadece mod değişmişse ilgiliyi gönder
        _ch_gonder  = ch_degisti  or donem_degisti
        _dig_gonder = dig_degisti or donem_degisti

        for lok in _loks:
            if _ch_gonder:
                for nokta in _CH_NOKTALAR:
                    komutlar.append({
                        "lokasyon": lok, "nokta_adi": nokta,
                        "hedef_deger": _CH_SET[yeni_ch], "durum": "bekliyor"
                    })
            if _dig_gonder:
                for nokta, deger in _DIG_SET[yeni_dig].items():
                    komutlar.append({
                        "lokasyon": lok, "nokta_adi": nokta,
                        "hedef_deger": deger, "durum": "bekliyor"
                    })

        if komutlar:
            _ins = _jj2.dumps(komutlar).encode()
            _ir = _ur2.Request(
                sb_url + "/rest/v1/komutlar",
                data=_ins,
                headers={
                    "apikey": sb_key, "Authorization": "Bearer " + sb_key,
                    "Content-Type": "application/json", "Prefer": "return=minimal"
                },
                method="POST"
            )
            _ur2.urlopen(_ir, timeout=10)

        if _ch_gonder:
            _sb_ayar_yaz("oto_mod_chiller", yeni_ch)
        if _dig_gonder:
            _sb_ayar_yaz("oto_mod_diger", yeni_dig)
        _sb_ayar_yaz("oto_donem", _donem)
        _sb_ayar_yaz("oto_set_son_kontrol", _jj2.dumps({
            "zaman": _dtt.now(_IST).isoformat(),
            "donem": _donem, "ref_sicaklik": _ref,
            "yarin_max": tahmin["max"], "yarin_min": tahmin["min"],
            "chiller_mod": yeni_ch, "diger_mod": yeni_dig,
            "komut_sayisi": len(komutlar), "lokasyonlar": _loks,
        }))

        # Log
        _lok_str = ", ".join(_loks)
        _log_kayitlar = []
        if _ch_gonder:
            _log_kayitlar.append({
                "tip": "chiller", "eski_mod": mevcut_ch, "yeni_mod": yeni_ch,
                "tahmin_ort": _ref,
                "komut_sayisi": sum(1 for k in komutlar if k["nokta_adi"] in _CH_NOKTALAR),
                "lokasyonlar": _lok_str,
            })
        if _dig_gonder:
            _log_kayitlar.append({
                "tip": "diger", "eski_mod": mevcut_dig, "yeni_mod": yeni_dig,
                "tahmin_ort": _ref,
                "komut_sayisi": sum(1 for k in komutlar if k["nokta_adi"] not in _CH_NOKTALAR),
                "lokasyonlar": _lok_str,
            })
        if _log_kayitlar:
            _lr = _ur2.Request(
                sb_url + "/rest/v1/oto_mod_log",
                data=_jj2.dumps(_log_kayitlar).encode(),
                headers={
                    "apikey": sb_key, "Authorization": "Bearer " + sb_key,
                    "Content-Type": "application/json", "Prefer": "return=minimal"
                },
                method="POST"
            )
            _ur2.urlopen(_lr, timeout=6)

    except Exception as _oe:
        import logging
        logging.getLogger(__name__).warning(f"oto_set_kontrol hata: {_oe}")


# ─── Arka plan thread: her 5 dakikada bir otomatik set kontrolü ───────────────
import threading as _threading

# Process-level flag — kaç tarayıcı sekmesi açılırsa açılsın tek thread çalışır
_OTO_THREAD_STARTED = False
_OTO_THREAD_LOCK    = _threading.Lock()

def _oto_set_loop(sb_url: str, sb_key: str):
    import time as _time
    while True:
        _time.sleep(300)   # 5 dakika
        _oto_set_kontrol(sb_url, sb_key)

# ═══════════════════════════════════════════════════════════════

@st.cache_data(ttl=30, show_spinner=False)
def fetch_guncellemeler(url, key):
    try:
        from supabase import create_client
        c = create_client(url, key)
        r = c.table("guncellemeler").select("versiyon,hedef,durum,created_at").order("created_at", desc=True).limit(8).execute()
        return r.data or []
    except:
        return []

config = load_config()
url  = config.get("supabase_url","")
key  = config.get("supabase_key","")
bagli = bool(url and "BURAYA" not in url)

# Otomatik set arka plan thread'ini başlat (process genelinde 1 kez)
if bagli:
    with _OTO_THREAD_LOCK:
        if not _OTO_THREAD_STARTED:
            _OTO_THREAD_STARTED = True
            _threading.Thread(
                target=_oto_set_loop, args=(url, key), daemon=True, name="oto-set"
            ).start()
            # İlk kontrolü hemen yap (thread 5 dk bekler)
            _threading.Thread(
                target=_oto_set_kontrol, args=(url, key), daemon=True
            ).start()

# m² değerlerini Supabase'den yükle (yoksa config/default kullan)
m2_config = {}
if bagli:
    m2_config = fetch_m2_supabase(url, key)
if not m2_config:
    m2_config = config.get("m2_degerler", {})
for lok_id in HASTANELER:
    if lok_id in m2_config:
        HASTANELER[lok_id]["m2"] = int(m2_config[lok_id])

now = datetime.now()  # timezone-naive — pandas karsilastirmalari icin
try:
    import pytz as _pytz
    now_display = datetime.now(_pytz.timezone("Europe/Istanbul"))
except ImportError:
    from datetime import timezone as _tz
    now_display = datetime.now(_tz(timedelta(hours=3)))
dun  = (now - timedelta(days=1)).strftime("%Y-%m-%d")

# ============ HEADER ============
st.markdown("""
<div style="text-align:center; padding:12px 0 8px;">
  <div style="font-family:'Plus Jakarta Sans',sans-serif; font-size:11px; color:#94a3b8;
              letter-spacing:3px; text-transform:uppercase;">
    ACIBADEM SAĞLIK GRUBU
  </div>
  <div style="font-family:'Playfair Display','Plus Jakarta Sans',serif; font-size:34px; font-weight:600; color:#f8fafc;
              letter-spacing:1px; line-height:1.3;">
    SYNAPSE // Merkezi Veri Bağlantısı
  </div>
  <div style="font-family:'Plus Jakarta Sans',sans-serif; font-size:11px; color:#38bdf8;
              letter-spacing:2px; margin-top:6px; text-transform:uppercase;">
    Operasyonel Zeka
  </div>
</div>
""", unsafe_allow_html=True)

# ── Lokasyon detay yönlendirmesi (kart ikonu tıklanınca) ──
if "detay" in st.query_params:
    _lok = st.query_params["detay"]
    if _lok in HASTANELER:
        st.session_state["detay_lokasyon"] = _lok
        st.query_params.clear()
        st.switch_page("pages/lokasyon_detay.py")

# ── Rapor yönlendirmesi ──
if "rapor" in st.query_params:
    _lok = st.query_params["rapor"]
    if _lok in HASTANELER:
        st.session_state["rapor_lokasyon"] = _lok
        st.query_params.clear()
        st.switch_page("pages/rapor_olustur.py")

if not bagli:
    st.error("⚠️ Supabase bağlantısı yok. merkez_config.json dosyasını kontrol edin.")
    st.stop()

df_all, _fetch_err = fetch_energy(url, key)
lokasyonlar  = fetch_lokasyonlar(url, key)
lok_dict     = {l["lokasyon_id"]: l for l in lokasyonlar}

# Sadece bilinen lokasyonları al (deneme/test verileri filtrelenir)
if not df_all.empty and "lokasyon_id" in df_all.columns:
    df_all = df_all[df_all["lokasyon_id"].isin(HASTANELER.keys())]

aktif_loklar = df_all["lokasyon_id"].unique().tolist() if not df_all.empty else []

# Bağlantı hatası varsa üstte küçük uyarı göster (sayfayı durdurma)
if _fetch_err:
    st.warning(f"⚠️ Enerji verisi alınamadı — Supabase erişilemiyor. Proje duraklatılmış olabilir. Hata: `{_fetch_err[:80]}`")

# ── Online durumu hesapla ──
def online_bilgi(lok_id):
    ld = lok_dict.get(lok_id, {})
    ping = str(ld.get("ping_zamani") or "").strip()
    if ping and ping not in ("None",""):
        try:
            dt = pd.to_datetime(ping).tz_localize(None)
            fark = (now - dt).total_seconds() / 60
            return fark < 10, fark
        except:
            pass
    return False, None

def dun_kwh(lok_id):
    if df_all.empty or lok_id not in aktif_loklar:
        return 0
    lok_df = df_all[df_all["lokasyon_id"] == lok_id]
    if lok_df.empty:
        return 0
    # Önce dünü dene, yoksa en son mevcut günü kullan
    d = lok_df[lok_df["Tarih"].dt.strftime("%Y-%m-%d") == dun]
    if d.empty:
        son = lok_df["Tarih"].dropna().max()
        d = lok_df[lok_df["Tarih"].dt.strftime("%Y-%m-%d") == son.strftime("%Y-%m-%d")]
    if not d.empty and "Toplam_Hastane_Tuketim_kWh" in d.columns:
        return d["Toplam_Hastane_Tuketim_kWh"].sum()
    return 0

def onceki_gun_kwh(lok_id):
    """Dünden bir önceki günün kWh değeri (% değişim için)."""
    if df_all.empty or lok_id not in aktif_loklar:
        return 0
    lok_df = df_all[df_all["lokasyon_id"] == lok_id]
    if lok_df.empty:
        return 0
    onceki = (now - timedelta(days=2)).strftime("%Y-%m-%d")
    d = lok_df[lok_df["Tarih"].dt.strftime("%Y-%m-%d") == onceki]
    if not d.empty and "Toplam_Hastane_Tuketim_kWh" in d.columns:
        return d["Toplam_Hastane_Tuketim_kWh"].sum()
    return 0

def sparkline_svg(values, renk, w=75, h=28):
    """Verilen değerlerden mini SVG sparkline üret."""
    if not values or len(values) < 2:
        return f'<svg width="{w}" height="{h}"></svg>'
    mn, mx = min(values), max(values)
    span = mx - mn if mx != mn else 1
    pts = []
    for i, v in enumerate(values):
        x = i / (len(values) - 1) * w
        y = h - ((v - mn) / span) * (h - 4) - 2
        pts.append(f"{x:.1f},{y:.1f}")
    path = " ".join(pts)
    # Alan dolgusu için kapat
    fill_path = f"M{pts[0]} " + " ".join(f"L{p}" for p in pts[1:]) + f" L{w},{ h} L0,{h} Z"
    return f'''<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}">
      <defs>
        <linearGradient id="sg_{renk[1:]}" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="{renk}" stop-opacity="0.3"/>
          <stop offset="100%" stop-color="{renk}" stop-opacity="0"/>
        </linearGradient>
      </defs>
      <path d="{fill_path}" fill="url(#sg_{renk[1:]})" />
      <polyline points="{path}" fill="none" stroke="{renk}" stroke-width="1.5"
                stroke-linejoin="round" stroke-linecap="round"/>
    </svg>'''

def son7_kwh(lok_id):
    """Son 7 günün günlük kWh listesini döndür."""
    if df_all.empty or "Toplam_Hastane_Tuketim_kWh" not in df_all.columns:
        return []
    son7_bas = (now - timedelta(days=7)).strftime("%Y-%m-%d")
    d = df_all[(df_all["lokasyon_id"] == lok_id) & (df_all["Tarih"].dt.strftime("%Y-%m-%d") >= son7_bas)]
    if d.empty:
        return []
    return d.groupby(d["Tarih"].dt.strftime("%Y-%m-%d"))["Toplam_Hastane_Tuketim_kWh"].sum().tolist()

def hvac_yuzdesi(lok_id):
    """Dünkü ortalama Chiller Load %"""
    if df_all.empty or "Chiller_Load_Percent" not in df_all.columns:
        return None
    d = df_all[(df_all["lokasyon_id"] == lok_id) & (df_all["Tarih"].dt.strftime("%Y-%m-%d") == dun)]
    if d.empty:
        return None
    val = d["Chiller_Load_Percent"].mean()
    return round(val, 1) if pd.notna(val) else None

# ============================================================
# ANA LAYOUT: sol (lokasyon) | sağ (dashboard) | harita (en sağ)
# ============================================================
sol, sag, merkez = st.columns([1.3, 1.3, 1.4], gap="small")

# ════════════════════════════════
# SOL KOLON
# ════════════════════════════════
with sol:
    st.markdown('<div id="syn-sol-panel"></div>', unsafe_allow_html=True)
    # ── Lokasyon Durumu ──
    st.markdown('<div class="sec">📍 LOKASYON DURUMU</div>', unsafe_allow_html=True)

    # Tümünü tüketime göre sırala (veri olanlar önce, olmayanlar sona)
    lok_sira = sorted(
        HASTANELER.items(),
        key=lambda x: (dun_kwh(x[0]) or 0),
        reverse=True
    )

    # Tüm kartları tek HTML bloğu olarak oluştur → scrollable div içine sar
    tum_kartlar = '<div class="lok-scroll">'

    for i, (lok_id, lok_info) in enumerate(lok_sira):
        online, fark_dk = online_bilgi(lok_id)
        kwh      = dun_kwh(lok_id)
        renk     = lok_info["renk"]
        if fark_dk is None:
            card_cls   = "nk nk-gray"
            durum_renk = "#6b7280"
            durum_lbl  = "KURULMADI"
        elif online:
            card_cls   = "nk nk-green"
            durum_renk = "#10b981"
            durum_lbl  = "ÇEVRİMİÇİ"
        else:
            card_cls   = "nk nk-red"
            durum_renk = "#ef4444"
            durum_lbl  = "ÇEVRİMDIŞI"

        kwh_str   = f"{kwh:,.0f}".replace(",", ".") if kwh else "—"
        m2_lok    = lok_info.get("m2", 10000)
        verim_str = f"{kwh/m2_lok:.2f}".replace(".", ",") if kwh else "—"
        sira_badge = f'<span style="position:absolute;top:8px;left:10px;font-family:Playfair Display,Plus Jakarta Sans,serif;font-size:8px;color:rgba(150,210,255,0.35);font-weight:700;">#{i+1}</span>' if i < 4 else ""

        # % değişim hesapla (dün vs önceki gün)
        onceki_kwh = onceki_gun_kwh(lok_id)
        if kwh and onceki_kwh and onceki_kwh > 0:
            degisim_pct = (kwh - onceki_kwh) / onceki_kwh * 100
            if degisim_pct > 2:
                degisim_html = f'<span style="font-size:9px;color:#ef4444;font-weight:700;">▲ {degisim_pct:.1f}%</span>'
            elif degisim_pct < -2:
                degisim_html = f'<span style="font-size:9px;color:#10b981;font-weight:700;">▼ {abs(degisim_pct):.1f}%</span>'
            else:
                degisim_html = f'<span style="font-size:9px;color:#6b7280;">≈ {degisim_pct:+.1f}%</span>'
        else:
            degisim_html = ""


        rr = int(renk[1:3],16); rg = int(renk[3:5],16); rb = int(renk[5:7],16)
        dr = int(durum_renk[1:3],16); dg = int(durum_renk[3:5],16); db = int(durum_renk[5:7],16)

        tum_kartlar += (
            f'<a class="{card_cls}" href="?detay={lok_id}" title="{lok_info["kisa"]} detayına git" '
            f'style="padding:14px;position:relative;">'
            + sira_badge +
            f'<span style="position:absolute;top:8px;right:10px;font-size:14px;'
            f'color:rgba({rr},{rg},{rb},0.55);">⟶</span>'
            f'<div style="display:flex;align-items:center;gap:14px;">'
            f'<div style="position:relative;width:58px;height:58px;flex-shrink:0;display:flex;align-items:center;justify-content:center;">'
            f'<div style="position:absolute;top:-5px;left:-5px;right:-5px;bottom:-5px;border-radius:50%;'
            f'background:radial-gradient(circle,rgba({rr},{rg},{rb},0.22) 0%,rgba({rr},{rg},{rb},0.05) 55%,transparent 75%);'
            f'animation:breathe-ring 3s ease-in-out infinite;"></div>'
            f'<div style="font-size:36px;line-height:1;position:relative;z-index:1;'
            f'filter:drop-shadow(0 0 8px rgba({rr},{rg},{rb},0.8));">🏥</div>'
            f'<div style="position:absolute;top:2px;right:2px;z-index:2;width:11px;height:11px;'
            f'border-radius:50%;background:rgba({dr},{dg},{db},1);border:2px solid #020617;'
            f'box-shadow:0 0 5px rgba({dr},{dg},{db},0.9);"></div>'
            f'</div>'
            f'<div style="flex:1;min-width:0;">'
            f'<div style="font-family:Playfair Display,Plus Jakarta Sans,serif;font-size:10px;font-weight:700;'
            f'color:{renk};letter-spacing:1.5px;text-shadow:0 0 7px rgba({rr},{rg},{rb},0.6);'
            f'margin-bottom:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{lok_info["kisa"]}</div>'
            f'<div style="font-size:8px;color:{durum_renk};font-weight:600;margin-bottom:5px;">{durum_lbl}</div>'
            f'<div style="display:flex;align-items:baseline;gap:4px;margin-bottom:3px;">'
            f'<span style="font-family:Playfair Display,Plus Jakarta Sans,serif;font-size:16px;font-weight:900;'
            f'color:{renk};text-shadow:0 0 10px rgba({rr},{rg},{rb},0.65);line-height:1;">{kwh_str}</span>'
            f'<span style="font-size:8px;color:rgba(150,210,255,0.5);">kWh</span>'
            f'<span style="margin-left:4px;">{degisim_html}</span>'
            f'</div>'
            f'<div style="display:inline-flex;align-items:center;gap:5px;'
            f'background:rgba(56, 189, 248,0.05);border-radius:5px;padding:3px 8px;'
            f'border:1px solid rgba(56, 189, 248,0.10);">'
            f'<span style="font-size:7px;color:rgba(150,210,255,0.4);text-transform:uppercase;letter-spacing:1px;">kWh/m²</span>'
            f'<span style="font-family:Playfair Display,Plus Jakarta Sans,serif;font-size:11px;color:#38bdf8;font-weight:700;">{verim_str}</span>'
            f'</div>'
            f'</div></div></a>'
        )

    tum_kartlar += '</div>'
    st.markdown(tum_kartlar, unsafe_allow_html=True)
    st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)

    # ── Global Özet (Aylık + Trend) ──
    _ay_tr = ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran",
              "Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"]
    _bu_yil = now.year
    _bu_ay  = now.month
    st.markdown(f'<div class="sec">⚡ GLOBAL ÖZET — {_ay_tr[_bu_ay-1].upper()} {_bu_yil}</div>', unsafe_allow_html=True)
    if not df_all.empty:
        # Dönem filtreleri
        _bu_ay_bas   = pd.Timestamp(year=_bu_yil,   month=_bu_ay, day=1)
        _gec_ay_yil  = _bu_yil - 1 if _bu_ay == 1 else _bu_yil
        _gec_ay_no   = 12 if _bu_ay == 1 else _bu_ay - 1
        _gec_ay_bas  = pd.Timestamp(year=_gec_ay_yil, month=_gec_ay_no, day=1)
        _gec_ay_son  = _bu_ay_bas - pd.Timedelta(days=1)
        _bu_yil_bas  = pd.Timestamp(year=_bu_yil,   month=1, day=1)
        _gec_yil_bas = pd.Timestamp(year=_bu_yil-1, month=1, day=1)
        _gec_yil_son = _bu_yil_bas - pd.Timedelta(days=1)

        _df_bu_ay   = df_all[df_all["Tarih"] >= _bu_ay_bas]
        _df_gec_ay  = df_all[(df_all["Tarih"] >= _gec_ay_bas) & (df_all["Tarih"] <= _gec_ay_son)]
        _df_bu_yil  = df_all[df_all["Tarih"] >= _bu_yil_bas]
        _df_gec_yil = df_all[(df_all["Tarih"] >= _gec_yil_bas) & (df_all["Tarih"] <= _gec_yil_son)]

        def tr(sayi, ondalik=0):
            fmt = f"{sayi:,.{ondalik}f}"
            if ondalik > 0:
                parts = fmt.split(".")
                return parts[0].replace(",", ".") + "," + parts[1]
            return fmt.replace(",", ".")

        def _cs(df, col):
            return df[col].sum() if col in df.columns else 0

        def _pct_html(bu, gec):
            if not gec or gec == 0: return ""
            p = (bu - gec) / gec * 100
            renk = "#10b981" if p <= 0 else "#ef4444"
            yon  = "▼" if p <= 0 else "▲"
            return f'<b style="color:{renk};font-size:10px;"> {yon}{abs(p):.1f}%</b>'

        _gec_ay_label = _ay_tr[_gec_ay_no - 1]

        _metrikler = [
            ("⚡ Toplam Enerji", "Toplam_Hastane_Tuketim_kWh", "kWh"),
            ("🔥 Doğalgaz",      None,                         "m³"),
            ("❄️ Soğutma",       "Toplam_Sogutma_Tuketim_kWh","kWh"),
            ("💧 Su",             "Su_Tuketimi_m3",             "m³"),
            ("⚙️ Kojen Üretim",  "Kojen_Uretim_kWh",           "kWh"),
        ]

        _ozet_kartlar = '<div class="ozet-grid">'
        for _lbl, _col, _birim in _metrikler:
            if _col is None:  # Doğalgaz: kazan + kojen toplamı
                _bu   = _cs(_df_bu_ay,   "Kazan_Dogalgaz_m3") + _cs(_df_bu_ay,   "Kojen_Dogalgaz_m3")
                _ga   = _cs(_df_gec_ay,  "Kazan_Dogalgaz_m3") + _cs(_df_gec_ay,  "Kojen_Dogalgaz_m3")
                _by   = _cs(_df_bu_yil,  "Kazan_Dogalgaz_m3") + _cs(_df_bu_yil,  "Kojen_Dogalgaz_m3")
                _gy   = _cs(_df_gec_yil, "Kazan_Dogalgaz_m3") + _cs(_df_gec_yil, "Kojen_Dogalgaz_m3")
            else:
                _bu = _cs(_df_bu_ay,   _col)
                _ga = _cs(_df_gec_ay,  _col)
                _by = _cs(_df_bu_yil,  _col)
                _gy = _cs(_df_gec_yil, _col)

            _trend_parts = []
            if _ga > 0: _trend_parts.append(f"{_gec_ay_label}: {tr(_ga)} {_birim}")
            if _by > 0: _trend_parts.append(f"{_bu_yil} YTD: {tr(_by)} {_birim}")
            if _gy > 0: _trend_parts.append(f"{_bu_yil-1}: {tr(_gy)} {_birim}")
            _trend_html = (
                f'<div style="font-size:9px;color:rgba(120,170,220,0.5);margin-top:2px;">'
                + " &nbsp;|&nbsp; ".join(_trend_parts) + "</div>"
            ) if _trend_parts else ""

            _ozet_kartlar += (
                f'<div style="padding:7px 10px;background:rgba(0,20,50,0.6);'
                f'border-radius:8px;border:1px solid rgba(56, 189, 248,0.1);">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;">'
                f'<span style="font-size:11px;color:rgba(150,210,255,0.7);">{_lbl}</span>'
                f'<span style="font-size:12px;font-weight:700;color:#38bdf8;'
                f'font-family:\'Playfair Display\',\'Plus Jakarta Sans\',serif;">{tr(_bu)} {_birim}{_pct_html(_bu, _ga)}</span>'
                f'</div>'
                f'{_trend_html}'
                f'</div>'
            )
        _ozet_kartlar += '</div>'
        st.markdown(_ozet_kartlar, unsafe_allow_html=True)

# ════════════════════════════════
# MERKEZ KOLON — TÜRKİYE HARİTASI
# ════════════════════════════════
with merkez:
    # ── Leaflet harita verisi ─────────────────────────────
    harita_js = []
    for lok_id, lok_info in HASTANELER.items():
        online, fark_dk = online_bilgi(lok_id)
        kwh = dun_kwh(lok_id)
        durum  = "Çevrimiçi" if online else ("Kurulmadı" if fark_dk is None else "Çevrimdışı")
        d_renk = "#10b981" if online else ("#6b7280" if fark_dk is None else "#ef4444")
        boyut  = max(10, min(22, kwh / 1400)) if kwh > 0 else 9
        harita_js.append({
            "isim":  lok_info["isim"],
            "kisa":  lok_info["kisa"],
            "lat":   lok_info["lat"],
            "lon":   lok_info["lon"],
            "durum": durum,
            "kwh":   f"{int(kwh):,}" if kwh else "—",
            "m2":    f"{lok_info['m2']:,}",
            "renk":  d_renk,
            "boyut": boyut,
            "online": bool(online),
        })

    hjs = json.dumps(harita_js, ensure_ascii=False)

    harita_html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#020617; }}
#map {{ width:100%; height:100vh; background:#020617; }}
.leaflet-container {{ background:#020617 !important; font-family:'Plus Jakarta Sans',sans-serif; }}
.leaflet-popup-content-wrapper {{
    background:rgba(15, 23, 42, 0.85) !important;
    backdrop-filter: blur(12px) !important;
    border:1px solid rgba(255, 255, 255, 0.08) !important;
    border-radius:8px !important;
    box-shadow:0 4px 20px rgba(0,0,0,0.6) !important;
    padding:0 !important;
}}
.leaflet-popup-content {{ margin:0 !important; color:white !important; }}
.leaflet-popup-tip-container {{ display:none; }}
.leaflet-popup-close-button {{ color:rgba(56, 189, 248,0.5) !important; font-size:16px !important; top:8px !important; right:10px !important; }}
.leaflet-control-zoom a {{
    background:rgba(15, 23, 42, 0.7) !important;
    color:#38bdf8 !important;
    border-color:rgba(255, 255, 255, 0.08) !important;
}}
.leaflet-control-zoom a:hover {{ background:rgba(15, 23, 42, 0.9) !important; }}
.leaflet-control-attribution {{ display:none !important; }}
@keyframes breathe-outer {{
    0%,100% {{ opacity:0.10; transform:scale(0.92); }}
    50%      {{ opacity:0.28; transform:scale(1.20); }}
}}
@keyframes breathe-inner {{
    0%,100% {{ opacity:0.22; transform:scale(0.96); }}
    50%     {{ opacity:0.50; transform:scale(1.10); }}
}}
</style>
</head><body>
<div id="map"></div>
<script>
var map = L.map('map', {{
    center: [39.0, 35.0],
    zoom: 5,
    zoomControl: true,
    attributionControl: false,
    preferCanvas: true
}});

// CartoDB Dark Matter — ücretsiz, API key yok
L.tileLayer('https://{{s}}.basemaps.cartocdn.com/dark_all/{{z}}/{{x}}/{{y}}{{r}}.png', {{
    maxZoom: 19, subdomains: 'abcd', noWrap: true
}}).addTo(map);

window.addEventListener('resize', function() {{ map.invalidateSize(true); }});
setTimeout(function() {{ map.invalidateSize(true); }}, 300);

var hospitals = {hjs};

hospitals.forEach(function(h) {{
    var s  = h.boyut;
    var c  = h.renk;
    var hs = s / 2;

    // ── Dış glow halkası ──
    L.marker([h.lat, h.lon], {{
        icon: L.divIcon({{
            className:'',
            html:'<div style="width:'+(s*3.8)+'px;height:'+(s*3.8)+'px;background:'+c+';border-radius:50%;animation:breathe-outer 3s ease-in-out infinite;"></div>',
            iconSize:[s*3.8, s*3.8], iconAnchor:[s*1.9, s*1.9]
        }}),
        interactive:false, zIndexOffset:-200
    }}).addTo(map);

    // ── İç glow halkası ──
    L.marker([h.lat, h.lon], {{
        icon: L.divIcon({{
            className:'',
            html:'<div style="width:'+(s*2)+'px;height:'+(s*2)+'px;background:'+c+';border-radius:50%;animation:breathe-inner 3s ease-in-out infinite;"></div>',
            iconSize:[s*2, s*2], iconAnchor:[s, s]
        }}),
        interactive:false, zIndexOffset:-100
    }}).addTo(map);

    // ── Ana nokta ──
    var dot = L.marker([h.lat, h.lon], {{
        icon: L.divIcon({{
            className:'',
            html:'<div style="width:'+s+'px;height:'+s+'px;background:'+c+';border-radius:50%;border:2px solid rgba(255,255,255,0.28);box-shadow:0 0 10px '+c+',0 0 3px rgba(0,0,0,0.8);"></div>',
            iconSize:[s, s], iconAnchor:[hs, hs]
        }}),
        zIndexOffset:100
    }}).addTo(map);

    // ── Etiket ──
    L.marker([h.lat, h.lon], {{
        icon: L.divIcon({{
            className:'',
            html:'<div style="color:rgba(180,220,255,0.80);font-size:8px;font-family:Orbitron,monospace;font-weight:700;white-space:nowrap;letter-spacing:1.5px;text-shadow:0 1px 4px rgba(0,0,0,0.95),0 0 8px rgba(0,0,0,0.9);padding-left:4px;padding-top:2px;">'+h.kisa+'</div>',
            iconSize:[100,16], iconAnchor:[-hs-2, hs-2]
        }}),
        interactive:false, zIndexOffset:300
    }}).addTo(map);

    // ── Popup ──
    var kwh_bar = h.kwh !== '—'
        ? '<div style="margin-top:8px;height:3px;background:rgba(56, 189, 248,0.15);border-radius:2px;"><div style="height:3px;background:'+c+';border-radius:2px;width:80%;"></div></div>'
        : '';
    dot.bindPopup(
        '<div style="padding:14px 16px;min-width:170px;">' +
        '<div style="font-family:Orbitron,monospace;font-size:9px;color:'+c+';font-weight:700;letter-spacing:2px;margin-bottom:6px;">'+h.isim.toUpperCase()+'</div>' +
        '<div style="display:flex;align-items:center;gap:5px;margin-bottom:10px;">' +
        '<div style="width:7px;height:7px;border-radius:50%;background:'+c+';box-shadow:0 0 6px '+c+';"></div>' +
        '<span style="font-size:9px;color:'+c+';font-weight:600;">'+h.durum+'</span></div>' +
        '<div style="font-size:12px;color:#a0c8ff;margin-bottom:4px;">⚡ <b style="color:white;font-size:14px;">'+h.kwh+'</b> kWh</div>' +
        '<div style="font-size:10px;color:rgba(150,200,255,0.55);">📐 '+h.m2+' m²</div>' +
        kwh_bar + '</div>',
        {{ maxWidth:220, className:'' }}
    );
}});
</script>
</body></html>"""

    st.markdown('<div class="sec">🗺️ HASTANE ENERJİ AĞI</div>', unsafe_allow_html=True)
    import base64, streamlit.components.v1 as _cv1
    _b64 = base64.b64encode(harita_html.encode("utf-8")).decode()
    _cv1.iframe(f"data:text/html;base64,{_b64}", height=1150, scrolling=False)

    # ── Veri hazırlığı: Chiller Set & Dış Hava (sağ kolonda gösterilecek) ──
    chiller_vals = {}
    dis_hava_val = fetch_dis_hava()
    _dis_hava_kaynak = "🌐 Canlı" if dis_hava_val is not None else "📊 DB"
    if dis_hava_val is not None:
        _dis_hava_log_yaz(url, key, dis_hava_val, "lokasyon_pc")
    min_val = max_val = min_isim = max_isim = min_renk = max_renk = None
    if not df_all.empty and "Chiller_Set_Temp_C" in df_all.columns:
        son_veri = df_all.sort_values("Tarih").groupby("lokasyon_id").last().reset_index()
        for _, row in son_veri.iterrows():
            lok_id = row["lokasyon_id"]
            if pd.notna(row.get("Chiller_Set_Temp_C", float("nan"))):
                chiller_vals[lok_id] = float(row["Chiller_Set_Temp_C"])
            if dis_hava_val is None and pd.notna(row.get("Dis_Hava_Sicakligi_C", float("nan"))):
                dis_hava_val = float(row["Dis_Hava_Sicakligi_C"])
                _dis_hava_kaynak = "📊 DB"
        if chiller_vals:
            min_lok = min(chiller_vals, key=chiller_vals.get)
            max_lok = max(chiller_vals, key=chiller_vals.get)
            min_val = chiller_vals[min_lok]
            max_val = chiller_vals[max_lok]
            min_renk = HASTANELER.get(min_lok, {}).get("renk", "#38bdf8")
            max_renk = HASTANELER.get(max_lok, {}).get("renk", "#f59e0b")
            min_isim = HASTANELER.get(min_lok, {}).get("kisa", min_lok)
            max_isim = HASTANELER.get(max_lok, {}).get("kisa", max_lok)


# ════════════════════════════════
# SAĞ KOLON
# ════════════════════════════════
with sag:
    st.markdown('<div id="syn-sag-panel"></div>', unsafe_allow_html=True)
    # ── Canlı Uyarılar ──
    st.markdown('<div class="sec">🚨 CANLI UYARILAR</div>', unsafe_allow_html=True)

    # Her lokasyon için uyarı listesi: {lok_id: [(severity, msg), ...]}
    lok_uyari_map = {lok_id: [] for lok_id in HASTANELER}

    # 1) Bakım kartı arızaları (Supabase lokasyonlar.bakim_ozet)
    for lok_id, lok_info in HASTANELER.items():
        ld = lok_dict.get(lok_id, {})
        ozet = ld.get("bakim_ozet") or {}
        if isinstance(ozet, str):
            try: ozet = json.loads(ozet)
            except: ozet = {}
        ariza  = ozet.get("toplam_ariza", 0)
        bakim  = ozet.get("toplam_bakim", 0)
        isim   = lok_info["kisa"]
        if ariza > 0:
            arizali = ", ".join(
                c.get("ad", str(c)) if isinstance(c, dict) else str(c)
                for c in ozet.get("arizali_cihazlar", [])[:2]
            )
            lok_uyari_map[lok_id].append(("r", f"🔴 {isim}: {ariza} ARIZALI bileşen — {arizali}"))
        if bakim > 0:
            lok_uyari_map[lok_id].append(("y", f"🟡 {isim}: {bakim} bileşen bakımda"))

    # 2) Enerji verisi uyarıları
    if not df_all.empty:
        son_gun = df_all[df_all["Tarih"].dt.strftime("%Y-%m-%d") == dun]
        for lok_id in aktif_loklar:
            isim = HASTANELER.get(lok_id, {}).get("kisa", lok_id)
            lok_son = son_gun[son_gun["lokasyon_id"] == lok_id]
            if lok_son.empty:
                lok_uyari_map.setdefault(lok_id, []).append(("r", f"⚠️ {isim}: Bugün veri yok"))
                continue
            if "Chiller_Set_Temp_C" in lok_son.columns:
                cs = lok_son["Chiller_Set_Temp_C"].mean()
                if pd.notna(cs) and cs > 9:
                    lok_uyari_map[lok_id].append(("y", f"🌡️ {isim}: Chiller set yüksek ({cs:.1f}°C)"))
                elif pd.notna(cs) and cs < 6:
                    lok_uyari_map[lok_id].append(("y", f"❄️ {isim}: Chiller set düşük ({cs:.1f}°C)"))
            if "Chiller_Load_Percent" in lok_son.columns:
                cl = lok_son["Chiller_Load_Percent"].mean()
                if pd.notna(cl) and cl > 90:
                    lok_uyari_map[lok_id].append(("r", f"🔥 {isim}: Chiller kritik yük (%{cl:.0f})"))

    # 3) Çevrimdışı uyarıları — sol kolonda kart olarak gösterildiği için burada yok

    # Lokasyonları arıza sayısına göre sırala (en fazla arıza önce)
    def lok_ariza_skoru(lok_id):
        ld = lok_dict.get(lok_id, {})
        ozet = ld.get("bakim_ozet") or {}
        if isinstance(ozet, str):
            try: ozet = json.loads(ozet)
            except: ozet = {}
        return ozet.get("toplam_sorun", 0) * 10 + len(lok_uyari_map.get(lok_id, []))

    sirali_loklar = sorted(HASTANELER.keys(), key=lok_ariza_skoru, reverse=True)

    # ── Uyarıları lokasyon bazında grupla ve göster ──────
    lok_ile_uyari = [(lid, lok_uyari_map.get(lid, []))
                     for lid in sirali_loklar
                     if lok_uyari_map.get(lid)]

    if not lok_ile_uyari:
        st.markdown(
            "<div style='background:rgba(16,185,129,0.07);border:1px solid rgba(16,185,129,0.2);"
            "border-radius:8px;padding:8px 12px;font-size:11px;color:#6ee7b7;'>✅ Tüm sistemler normal</div>",
            unsafe_allow_html=True
        )
    else:
        uyari_html = "<div style='max-height:195px;overflow-y:auto;padding-right:4px;scrollbar-width:thin;scrollbar-color:rgba(56, 189, 248,0.3) transparent;'>"
        for lid, uyarilar in lok_ile_uyari:
            lok_inf  = HASTANELER.get(lid, {})
            isim     = lok_inf.get("kisa", lid)
            has_crit = any(s == "r" for s, _ in uyarilar)
            kart_bg  = "rgba(239,68,68,0.06)" if has_crit else "rgba(245,158,11,0.06)"
            kart_br  = "rgba(239,68,68,0.30)" if has_crit else "rgba(245,158,11,0.25)"
            dot_renk = "#ef4444" if has_crit else "#f59e0b"
            satirlar = ""
            for sev, msg in uyarilar:
                s_renk = "#fca5a5" if sev == "r" else "#fcd34d"
                s_bg   = "rgba(239,68,68,0.08)" if sev == "r" else "rgba(245,158,11,0.08)"
                satirlar += (
                    f"<div style='background:{s_bg};border-radius:5px;padding:4px 8px;"
                    f"margin-top:4px;font-size:10px;color:{s_renk};'>{msg}</div>"
                )
            uyari_html += (
                f"<details style='background:{kart_bg};border:1px solid {kart_br};"
                f"border-radius:8px;padding:6px 10px;margin-bottom:5px;cursor:pointer;'>"
                f"<summary style='list-style:none;display:flex;align-items:center;gap:6px;"
                f"font-size:11px;font-weight:600;color:rgba(200,230,255,0.85);'>"
                f"<span style='width:7px;height:7px;border-radius:50%;background:{dot_renk};"
                f"box-shadow:0 0 5px {dot_renk};flex-shrink:0;display:inline-block;'></span>"
                f"{isim} — {len(uyarilar)} uyarı"
                f"</summary>"
                f"<div style='margin-top:4px;'>{satirlar}</div>"
                f"</details>"
            )
        uyari_html += "</div>"
        st.markdown(uyari_html, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)

    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)

    # ── OTO SET — Birleşik Kart (toggle + durum + geçmiş) ──
    st.markdown("""<style>
    .switch{position:relative;display:inline-block;width:46px;height:26px;flex-shrink:0;}
    .switch input{opacity:0;width:0;height:0;}
    .slider{position:absolute;cursor:pointer;top:0;left:0;right:0;bottom:0;border-radius:26px;
        transition:.35s;background:rgba(100,120,160,0.35);border:1px solid rgba(100,140,200,0.2);}
    .slider.on{background:#10b981;box-shadow:0 0 10px rgba(16,185,129,0.5);border-color:rgba(16,185,129,0.4);}
    .slider.off{background:#374151;box-shadow:none;}
    .slider:before{content:"";position:absolute;height:20px;width:20px;left:3px;bottom:2px;
        background:white;border-radius:50%;transition:.35s;box-shadow:0 2px 6px rgba(0,0,0,0.4);}
    .slider.on:before{transform:translateX(20px);}
    .slider.off:before{transform:translateX(0);}
    div[data-testid="stCheckbox"]{position:absolute;opacity:0;pointer-events:none;height:0;}
    </style>""", unsafe_allow_html=True)

    import json as _oajson, urllib.request as _oaur

    # Verileri çek
    _oto_aktif_su = True
    _os = {}
    _ml_data = []
    try:
        with _oaur.urlopen(_oaur.Request(
            url + "/rest/v1/ayarlar?key=eq.oto_set_aktif&select=value",
            headers={"apikey":key,"Authorization":"Bearer "+key}), timeout=4) as r:
            d = _oajson.loads(r.read())
            _oto_aktif_su = (d[0]["value"] == "true") if d else True
    except Exception: pass
    try:
        with _oaur.urlopen(_oaur.Request(
            url + "/rest/v1/ayarlar?key=eq.oto_set_son_kontrol&select=value",
            headers={"apikey":key,"Authorization":"Bearer "+key}), timeout=4) as r:
            d = _oajson.loads(r.read())
            _os = _oajson.loads(d[0]["value"]) if d else {}
    except Exception: pass
    try:
        with _oaur.urlopen(_oaur.Request(
            url + "/rest/v1/oto_mod_log?order=created_at.desc&limit=60"
                 "&select=tip,eski_mod,yeni_mod,tahmin_ort,komut_sayisi,created_at",
            headers={"apikey":key,"Authorization":"Bearer "+key}), timeout=4) as r:
            _ml_data = _oajson.loads(r.read())
    except Exception: pass

    # Toggle değerleri
    _sw_cls  = "on" if _oto_aktif_su else "off"
    _st_renk = "#10b981" if _oto_aktif_su else "#ef4444"
    _st_txt  = "AKTİF" if _oto_aktif_su else "DEVRE DIŞI"
    _alt_txt = "Senaryo çalışıyor" if _oto_aktif_su else "BACnet komut gönderilmiyor"

    # OTO SET durum değerleri
    _os_zaman   = _os.get("zaman","")[:16].replace("T"," ")
    _os_ref     = _os.get("ref_sicaklik", _os.get("tahmin_ort", "—"))
    _os_max     = _os.get("yarin_max","—")
    _os_min     = _os.get("yarin_min","—")
    _os_ch      = _os.get("chiller_mod","—")
    _os_dig     = _os.get("diger_mod","—")
    _os_cnt     = _os.get("komut_sayisi", 0)
    _os_donem   = _os.get("donem","")
    _donem_ikon = "🌞" if _os_donem=="gunduz" else ("🌙" if _os_donem=="gece" else "")
    _ch_label   = {"koc_soguk":"❄️ 8.0°C","serin":"🌤️ 7.5°C",
                   "ilimli":"☀️ 7.0°C","sicak":"🔥 6.5°C"}.get(_os_ch, _os_ch)
    _dig_label  = {"sogutma":"☀️ Soğutma","isitma":"❄️ Isıtma"}.get(_os_dig, _os_dig)
    _cnt_html   = (f"<span style='color:#f59e0b;font-weight:700;'>⚡ {_os_cnt} komut gönderildi</span>"
                   ) if _os_cnt > 0 else "<span style='color:rgba(180,220,255,0.3);'>Mod değişmedi</span>"

    # Mod geçiş değerleri
    _ml_ch  = [x for x in _ml_data if x["tip"]=="chiller"]
    _ml_dig = [x for x in _ml_data if x["tip"]=="diger"]
    _ml_top = len(_ml_data)
    _eski_yeni_ikon = lambda e,y: "⬆️" if (
        ["koc_soguk","serin","ilimli","sicak","isitma","sogutma"].index(y)
        > ["koc_soguk","serin","ilimli","sicak","isitma","sogutma"].index(e)) else "⬇️"
    _son_gecis_html = ""
    if _ml_data:
        _ml_son = _ml_data[0]
        _son_tip = "🧊 Chiller" if _ml_son["tip"]=="chiller" else "🌀 Kol/FCU/AHU"
        try: _son_ok = _eski_yeni_ikon(_ml_son["eski_mod"], _ml_son["yeni_mod"])
        except: _son_ok = "↔️"
        _son_gecis_html = (
            f"<div style='font-size:9px;border-top:1px solid rgba(56, 189, 248,0.08);"
            f"padding-top:6px;margin-top:6px;color:rgba(180,220,255,0.5);'>"
            f"Son geçiş: {_son_tip} &nbsp;{_son_ok}&nbsp; "
            f"<b style='color:rgba(200,230,255,0.75);'>{_ml_son['eski_mod']}</b> → "
            f"<b style='color:#38bdf8;'>{_ml_son['yeni_mod']}</b> &nbsp;·&nbsp; "
            f"<span style='color:#f59e0b;'>{_ml_son['tahmin_ort']}°C</span></div>"
        )

    # ── OTO SET Kartı (toggle hariç — toggle aşağıda st.toggle ile) ──
    st.markdown(
        f"<div style='background:rgba(15, 23, 42, 0.4);backdrop-filter:blur(12px);"
        f"border:1px solid rgba(255,255,255,0.05);border-radius:8px;padding:14px 16px;'>"
        # ── Satır 1: Başlık ──
        f"<div style='display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;'>"
        f"<div>"
        f"<div style='font-family:Playfair Display,Plus Jakarta Sans,serif;font-size:9px;font-weight:700;"
        f"color:rgba(56, 189, 248,0.7);letter-spacing:2px;margin-bottom:2px;'>🤖 OTO SET</div>"
        f"<div style='font-size:11px;font-weight:700;color:{_st_renk};'>{_st_txt}"
        f"<span style='font-size:9px;font-weight:400;color:rgba(180,220,255,0.4);margin-left:6px;'>{_alt_txt}</span></div>"
        f"</div>"
        f"</div>"
        # ── Ayırıcı ──
        f"<div style='border-top:1px solid rgba(56, 189, 248,0.08);margin-bottom:10px;'></div>"
        # ── Satır 2: Sıcaklık + zaman ──
        f"<div style='display:flex;align-items:baseline;justify-content:space-between;margin-bottom:8px;'>"
        f"<div style='display:flex;align-items:baseline;gap:6px;'>"
        f"<span style='font-family:Playfair Display,Plus Jakarta Sans,serif;font-size:18px;font-weight:900;"
        f"color:#38bdf8;text-shadow:0 0 12px rgba(56, 189, 248,0.5);'>{_donem_ikon} {_os_ref}°C</span>"
        f"<span style='font-size:9px;color:rgba(150,210,255,0.4);'>yarın max:{_os_max} / min:{_os_min}</span>"
        f"</div>"
        f"<span style='font-size:8px;color:rgba(150,210,255,0.3);'>{_os_zaman}</span>"
        f"</div>"
        # ── Satır 3: Rozetler ──
        f"<div style='display:flex;gap:5px;flex-wrap:wrap;margin-bottom:8px;'>"
        f"<div style='background:rgba(56, 189, 248,0.08);border:1px solid rgba(56, 189, 248,0.2);"
        f"border-radius:6px;padding:3px 8px;font-size:9px;color:rgba(200,230,255,0.8);'>"
        f"❄️ Chiller &nbsp;<b style='color:#38bdf8;'>{_ch_label}</b></div>"
        f"<div style='background:rgba(56, 189, 248,0.08);border:1px solid rgba(56, 189, 248,0.2);"
        f"border-radius:6px;padding:3px 8px;font-size:9px;color:rgba(200,230,255,0.8);'>"
        f"🌀 KOL/FCU &nbsp;<b style='color:#38bdf8;'>{_dig_label}</b></div>"
        f"<div style='background:rgba(56, 189, 248,0.08);border:1px solid rgba(56, 189, 248,0.2);"
        f"border-radius:6px;padding:3px 8px;font-size:9px;color:rgba(200,230,255,0.8);'>"
        f"🧊 {len(_ml_ch)} &nbsp;·&nbsp; 🌀 {len(_ml_dig)} &nbsp;·&nbsp; "
        f"<span style='color:#f59e0b;'>Σ {_ml_top}</span></div>"
        f"</div>"
        # ── Satır 4: Komut + son geçiş ──
        f"<div style='font-size:9px;border-top:1px solid rgba(56, 189, 248,0.08);padding-top:6px;'>"
        f"{_cnt_html}</div>"
        f"{_son_gecis_html}"
        f"</div>",
        unsafe_allow_html=True
    )

    # Senaryo açma/kapama butonu (st.toggle/checkbox CSS tarafından gizleniyordu)
    _btn_lbl = "🟢 Senaryo AKTİF — Kapat" if _oto_aktif_su else "🔴 Senaryo KAPALI — Aç"
    _btn_type = "secondary" if _oto_aktif_su else "primary"
    if st.button(_btn_lbl, key="oto_set_toggle_btn", use_container_width=True, type=_btn_type):
        _yeni_deger = "false" if _oto_aktif_su else "true"
        _pay = _oajson.dumps({"key":"oto_set_aktif","value":_yeni_deger}).encode()
        _oaur.urlopen(_oaur.Request(url+"/rest/v1/ayarlar", data=_pay, method="POST",
            headers={"apikey":key,"Authorization":"Bearer "+key,
                     "Content-Type":"application/json","Prefer":"resolution=merge-duplicates"}), timeout=4)
        st.rerun()

    # Detay listesi — session_state toggle (autorefresh'e karşı dayanıklı)
    if _ml_data:
        if "gecis_listesi_acik" not in st.session_state:
            st.session_state["gecis_listesi_acik"] = False

        _btn_label = "🔼 Geçişleri gizle" if st.session_state["gecis_listesi_acik"] else "📋 Tüm geçişleri göster"
        if st.button(_btn_label, key="gecis_toggle_btn", use_container_width=True):
            st.session_state["gecis_listesi_acik"] = not st.session_state["gecis_listesi_acik"]
            st.rerun()

        if st.session_state["gecis_listesi_acik"]:
            _gecis_satirlari = ""
            for _mk in _ml_data[:20]:
                _mk_z  = _mk["created_at"][:16].replace("T", " ")
                _mk_ti = "🧊" if _mk["tip"] == "chiller" else "🌀"
                try:
                    _mk_ok = _eski_yeni_ikon(_mk["eski_mod"], _mk["yeni_mod"])
                except Exception:
                    _mk_ok = "↔️"
                _gecis_satirlari += (
                    f"<div style='font-size:10px;padding:4px 0;"
                    f"border-bottom:1px solid rgba(56, 189, 248,0.06);'>"
                    f"<span style='color:rgba(150,210,255,0.35);'>{_mk_z}</span>"
                    f" &nbsp;{_mk_ti} {_mk_ok}&nbsp; "
                    f"<b style='color:rgba(200,230,255,0.7);'>{_mk['eski_mod']}</b>"
                    f" → <b style='color:#38bdf8;'>{_mk['yeni_mod']}</b>"
                    f" &nbsp;<span style='color:#f59e0b;'>{_mk['tahmin_ort']}°C</span>"
                    f" &nbsp;<span style='color:rgba(16,185,129,0.7);'>{_mk['komut_sayisi']} komut</span>"
                    f"</div>"
                )
            st.markdown(
                f"<div style='background:rgba(0,0,0,0.25);border:1px solid rgba(255,255,255,0.05);"
                f"border-radius:10px;padding:8px 12px;margin-bottom:5px;'>"
                f"{_gecis_satirlari}</div>",
                unsafe_allow_html=True
            )

    # ── Chiller Set & Dış Hava Kartı ──
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    # ── Chiller Set & Dış Hava — Birleşik Kart ──
    _ch_ic = ""
    if dis_hava_val is not None:
        _ch_ic += (
            f"<div style='display:flex;align-items:baseline;gap:6px;margin-bottom:8px;'>"
            f"<span style='font-family:Playfair Display,Plus Jakarta Sans,serif;font-size:18px;font-weight:900;"
            f"color:#f59e0b;text-shadow:0 0 12px rgba(245,158,11,0.5);'>"
            f"🌡️ {dis_hava_val:.1f}°C</span>"
            f"<span style='font-size:9px;color:rgba(150,210,255,0.4);'>Dış Hava İstanbul"
            f" &nbsp;·&nbsp; {_dis_hava_kaynak}</span>"
            f"</div>"
        )
    _rozet_ic = ""
    if min_val is not None:
        _rozet_ic += (
            f"<div style='background:rgba(56, 189, 248,0.08);border:1px solid rgba(56, 189, 248,0.2);"
            f"border-radius:6px;padding:3px 10px;font-size:9px;color:rgba(200,230,255,0.8);'>"
            f"❄️ Min &nbsp;<b style='color:#38bdf8;font-family:Playfair Display,Plus Jakarta Sans,serif;'>{min_val:.1f}°C</b>"
            f"&nbsp;<span style='color:{min_renk};'>{min_isim}</span></div>"
        )
    if max_val is not None and max_isim != min_isim:
        _rozet_ic += (
            f"<div style='background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.2);"
            f"border-radius:6px;padding:3px 10px;font-size:9px;color:rgba(200,230,255,0.8);'>"
            f"🔥 Max &nbsp;<b style='color:#ef4444;font-family:Playfair Display,Plus Jakarta Sans,serif;'>{max_val:.1f}°C</b>"
            f"&nbsp;<span style='color:{max_renk};'>{max_isim}</span></div>"
        )
    if dis_hava_val is not None or min_val is not None:
        st.markdown(
            f"<div style='background:rgba(15, 23, 42, 0.4);backdrop-filter:blur(12px);"
            f"border:1px solid rgba(255,255,255,0.05);border-radius:8px;padding:14px 16px;'>"
            f"<div style='font-family:Playfair Display,Plus Jakarta Sans,serif;font-size:8px;font-weight:700;"
            f"color:rgba(56, 189, 248,0.6);letter-spacing:2px;margin-bottom:10px;'>🌡️ DIŞ HAVA & CHİLLER SET</div>"
            f"{_ch_ic}"
            f"<div style='display:flex;gap:5px;flex-wrap:wrap;'>{_rozet_ic}</div>"
            f"</div>",
            unsafe_allow_html=True
        )
    else:
        st.markdown("<div class='alrt-y'>⚠️ Chiller set verisi bulunamadı</div>", unsafe_allow_html=True)

    st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)

    # ════════════════════════════════
    # 🤖 ENERJİ ZEKASI — AI Modülü
    # ════════════════════════════════

    # ── Son 30 günlük metrikleri hesapla ──
    _ai_metriks = {}
    _toplam_kwh_genel = 0

    def _col_sum(df, col):
        return float(df[col].sum()) if col in df.columns else 0.0
    def _col_mean(df, col):
        return df[col].dropna().mean() if col in df.columns else float("nan")

    if not df_all.empty:
        _son30 = df_all[df_all["Tarih"] >= (pd.Timestamp.now() - pd.Timedelta(days=30))]
        for _lok_id, _info in HASTANELER.items():
            _lok_df = _son30[_son30["lokasyon_id"] == _lok_id]
            if _lok_df.empty:
                continue
            _m2_val  = _info.get("m2", 10000)
            _gun_say = max(1, _lok_df["Tarih"].dt.date.nunique())

            # ── Elektrik ──
            _kwh      = _col_sum(_lok_df, "Toplam_Hastane_Tuketim_kWh")
            _chkwh    = _col_sum(_lok_df, "Chiller_Tuketim_kWh")
            _mcc_kwh  = _col_sum(_lok_df, "MCC_Tuketim_kWh")
            _kojen    = _col_sum(_lok_df, "Kojen_Uretim_kWh")
            _sebeke   = _col_sum(_lok_df, "Sebeke_Tuketim_kWh")

            # ── Doğalgaz & Su ──
            _gaz_m3   = _col_sum(_lok_df, "Dogalgaz_Tuketim_m3")
            _su_m3    = _col_sum(_lok_df, "Su_Tuketim_m3")

            # ── Chiller anlık ──
            _cs_raw   = _col_mean(_lok_df, "Chiller_Set_Temp_C")
            _cl_raw   = _col_mean(_lok_df, "Chiller_Load_Percent")

            if _kwh <= 0:
                continue

            # ── Türetilmiş verimlilik metrikleri ──
            _kwh_m2_gun  = round(_kwh / _gun_say / _m2_val, 2)       # kWh/m²/gün
            _kojen_verim = round(_kojen / _gaz_m3, 2) if _gaz_m3 > 0 else None   # kWh/m³
            _gaz_verim   = round(_kwh   / _gaz_m3, 2) if _gaz_m3 > 0 else None   # kWh/m³ toplam
            _sebeke_bag  = round(_sebeke / (_sebeke + _kojen) * 100, 1) if (_sebeke + _kojen) > 0 else None  # %
            _chiller_pay = round(_chkwh / _kwh * 100, 1) if _kwh > 0 else None   # % soğutma payı

            _ai_metriks[_lok_id] = {
                "isim":        _info["kisa"],
                "kwh_m2":      _kwh_m2_gun,
                "toplam_kwh":  round(_kwh),
                "chiller_set": round(_cs_raw, 1) if not np.isnan(_cs_raw) else None,
                "chiller_yuk": round(_cl_raw, 1) if not np.isnan(_cl_raw) else None,
                "chiller_pay": _chiller_pay,
                "kojen_kwh":   round(_kojen) if _kojen > 0 else None,
                "kojen_verim": _kojen_verim,
                "sebeke_bag":  _sebeke_bag,
                "gaz_m3":      round(_gaz_m3) if _gaz_m3 > 0 else None,
                "gaz_verim":   _gaz_verim,
                "su_m3":       round(_su_m3) if _su_m3 > 0 else None,
                "gun_say":     _gun_say,
                "anormal":     False,
                "ort_kwh_m2":  0.0,
            }
        _toplam_kwh_genel = sum(v["toplam_kwh"] for v in _ai_metriks.values())

    # ── Aykırı değer tespiti (1.5 std) ──
    if len(_ai_metriks) >= 3:
        _yogunluklar = [v["kwh_m2"] for v in _ai_metriks.values()]
        _ort_y = float(np.mean(_yogunluklar))
        _std_y = float(np.std(_yogunluklar))
        for _m in _ai_metriks.values():
            _m["anormal"]    = bool(abs(_m["kwh_m2"] - _ort_y) > 1.5 * _std_y)
            _m["ort_kwh_m2"] = round(_ort_y, 1)

    # ── Sıralama & özet metrikler ──
    if _ai_metriks:
        _sirali     = sorted(_ai_metriks.items(), key=lambda x: x[1]["kwh_m2"])
        _en_iyi     = _sirali[0]
        _en_kotu    = _sirali[-1]
        _anormal_n  = sum(1 for v in _ai_metriks.values() if v["anormal"])

        # ── Enerji Zekası Kartı ──
        _ez_satirlar = ""
        for _lid, _mv in _sirali:
            _ez_renk = "#ef4444" if _mv["anormal"] else "#38bdf8"
            _flag    = " ⚠️" if _mv["anormal"] else ""
            _ez_satirlar += (
                f"<div style='display:flex;justify-content:space-between;align-items:center;"
                f"padding:5px 0;border-bottom:1px solid rgba(56, 189, 248,0.06);'>"
                f"<span style='font-size:10px;font-weight:600;color:rgba(200,230,255,0.8);'>"
                f"{_mv['isim']}{_flag}</span>"
                f"<span style='font-family:Playfair Display,Plus Jakarta Sans,serif;font-size:10px;color:{_ez_renk};'>"
                f"{_mv['kwh_m2']} kWh/m²/gün</span>"
                f"</div>"
            )

        _anormal_html = ""
        if _anormal_n > 0:
            _anormal_isimler = ", ".join(v["isim"] for v in _ai_metriks.values() if v["anormal"])
            _anormal_html = (
                f"<div style='font-size:9px;color:#f59e0b;margin-top:6px;'>"
                f"⚡ {_anormal_n} lokasyon normal dışı: {_anormal_isimler}</div>"
            )

        st.markdown(
            f"<div style='background:rgba(15, 23, 42, 0.4);backdrop-filter:blur(12px);"
            f"border:1px solid rgba(255,255,255,0.05);border-radius:8px;padding:14px 16px;'>"
            f"<div style='font-family:Playfair Display,Plus Jakarta Sans,serif;font-size:8px;font-weight:700;"
            f"color:rgba(56, 189, 248,0.6);letter-spacing:2px;margin-bottom:10px;'>🤖 ENERJİ ZEKASI</div>"
            f"{_ez_satirlar}"
            f"{_anormal_html}"
            f"</div>",
            unsafe_allow_html=True
        )

        # ── AI yetki kontrolü ──
        _api_key = ""
        try:
            _api_key = st.secrets.get("anthropic", {}).get("api_key", "")
        except Exception:
            pass

        if not _api_key:
            st.markdown(
                "<div class='alrt-y' style='margin-top:6px;font-size:10px;'>"
                "🔑 AI aktif değil.<br>Streamlit Secrets'a "
                "<code>anthropic.api_key</code> ekleyin.</div>",
                unsafe_allow_html=True)
        else:
            _su_an  = datetime.now()
            _bugun  = _su_an.date()

            # ── Supabase'den bugünün analizini oku ──
            def _sb_analiz_oku(tarih):
                """Supabase ai_analizler tablosundan ilgili günün analizini çek."""
                try:
                    from supabase import create_client as _cc
                    _c = _cc(url, key)
                    _r = _c.table("ai_analizler").select("metin,created_at") \
                           .eq("tarih", str(tarih)).limit(1).execute()
                    if _r.data:
                        return _r.data[0]["metin"], _r.data[0]["created_at"]
                except Exception:
                    pass
                return None, None

            def _sb_analiz_yaz(tarih, metin, lok_n):
                """Analiz metnini Supabase ai_analizler tablosuna kaydet (upsert)."""
                try:
                    from supabase import create_client as _cc
                    _c = _cc(url, key)
                    _c.table("ai_analizler").upsert({
                        "tarih":      str(tarih),
                        "metin":      metin,
                        "lok_sayisi": lok_n,
                    }, on_conflict="tarih").execute()
                except Exception:
                    pass

            # Saat 09:00'dan önce dünün analizini göster, sonra bugününkü
            _analiz_tarihi = _bugun if _su_an.hour >= 9 else (_bugun - pd.Timedelta(days=1).to_pytimedelta().__class__(days=1))
            _analiz_tarihi = _bugun if _su_an.hour >= 9 else (_su_an - pd.Timedelta(days=1)).date()

            _sb_metin, _sb_zaman = _sb_analiz_oku(_analiz_tarihi)

            _yenile_btn = False  # varsayılan

            # Çalıştırma koşulu: DB'de bugün yoksa VEYA yenile butonuna basıldıysa
            _calistir = (_sb_metin is None) or _yenile_btn

            if not _calistir:
                _ai_metin  = _sb_metin
                _ai_zaman_str = pd.Timestamp(_sb_zaman).strftime("%d.%m %H:%M") if _sb_zaman else ""
            else:
                _dun_dt  = pd.Timestamp(_bugun) - pd.Timedelta(days=1)
                _dun_str = _dun_dt.strftime("%d.%m.%Y")
                _lok_n   = len(_ai_metriks)   # aktif lokasyon sayısı

                # ════════════════════════════════════════════════════
                # Lokasyon sayısına göre adaptif blok + prompt yapısı
                #
                #  KATMANlar:
                #  TIER 1 — 1-3 lok  : Her lokasyon tam detay
                #  TIER 2 — 4-7 lok  : Özet tablo + top-3 anormal detay
                #  TIER 3 — 8+  lok  : Grup istatistik + sadece kritikler
                # ════════════════════════════════════════════════════

                def _dun_verisi(lid):
                    """Bir lokasyon için dünün ham satırını döndür."""
                    return df_all[
                        (df_all["lokasyon_id"] == lid) &
                        (df_all["Tarih"].dt.date == _dun_dt.date())
                    ]

                def _dun_blok_tam(lid, mv):
                    """TIER 1 — tam detay bloğu."""
                    _ddf = _dun_verisi(lid)
                    _m2v = HASTANELER.get(lid, {}).get("m2", 10000)
                    b = f"【{mv['isim']}】{' ⚠️ANORMAL' if mv['anormal'] else ''}\n"
                    if not _ddf.empty:
                        dkwh = _col_sum(_ddf, "Toplam_Hastane_Tuketim_kWh")
                        dgaz = _col_sum(_ddf, "Dogalgaz_Tuketim_m3")
                        dkoj = _col_sum(_ddf, "Kojen_Uretim_kWh")
                        dseb = _col_sum(_ddf, "Sebeke_Tuketim_kWh")
                        dsu  = _col_sum(_ddf, "Su_Tuketim_m3")
                        dcs  = _col_mean(_ddf, "Chiller_Set_Temp_C")
                        dcl  = _col_mean(_ddf, "Chiller_Load_Percent")
                        b += f"  ▶ Dün ({_dun_str}):\n"
                        if dkwh > 0:
                            b += f"    Elektrik : {dkwh:,.0f} kWh  ({round(dkwh/_m2v,2)} kWh/m²/gün)\n"
                        if dkoj > 0:
                            b += f"    Kojen    : {dkoj:,.0f} kWh"
                            if dgaz > 0: b += f"  |  Verim: {round(dkoj/dgaz,2)} kWh/m³ (≥3.5)"
                            b += "\n"
                        if (dseb + dkoj) > 0:
                            b += f"    Şebeke bağ.: %{round(dseb/(dseb+dkoj)*100,1)}  (<%30 ideal)\n"
                        if dgaz > 0:
                            b += f"    Doğalgaz : {dgaz:,.0f} m³"
                            if dkwh > 0: b += f"  |  Genel verim: {round(dkwh/dgaz,2)} kWh/m³"
                            b += "\n"
                        if dsu  > 0: b += f"    Su       : {dsu:,.0f} m³\n"
                        if not np.isnan(dcs):
                            b += f"    Chiller  : {round(dcs,1)}°C"
                            if not np.isnan(dcl): b += f"  |  Yük %{round(dcl,0):.0f}"
                            b += "\n"
                    else:
                        b += f"  ▶ Dün: veri yok\n"
                    b += f"  ▷ 30g ort: {mv['kwh_m2']} kWh/m²/gün"
                    if mv["kojen_verim"]: b += f"  |  Kojen: {mv['kojen_verim']} kWh/m³"
                    if mv["sebeke_bag"]:  b += f"  |  Şebeke: %{mv['sebeke_bag']}"
                    return b + "\n"

                def _dun_blok_ozet(lid, mv):
                    """TIER 2 — tek satır özet."""
                    _ddf = _dun_verisi(lid)
                    _m2v = HASTANELER.get(lid, {}).get("m2", 10000)
                    flag = " ⚠️" if mv["anormal"] else ""
                    if not _ddf.empty:
                        dkwh = _col_sum(_ddf, "Toplam_Hastane_Tuketim_kWh")
                        dgaz = _col_sum(_ddf, "Dogalgaz_Tuketim_m3")
                        dkoj = _col_sum(_ddf, "Kojen_Uretim_kWh")
                        dseb = _col_sum(_ddf, "Sebeke_Tuketim_kWh")
                        kv   = round(dkoj/dgaz,2) if dgaz>0 and dkoj>0 else "-"
                        sb   = f"%{round(dseb/(dseb+dkoj)*100,1)}" if (dseb+dkoj)>0 else "-"
                        yo   = round(dkwh/_m2v,2) if dkwh>0 else "-"
                        return (f"  {mv['isim']}{flag}: {yo} kWh/m²/gün  |  "
                                f"Kojen verim {kv}  |  Şebeke {sb}  |  30g ort {mv['kwh_m2']}\n")
                    else:
                        return f"  {mv['isim']}{flag}: veri yok  |  30g ort {mv['kwh_m2']} kWh/m²/gün\n"

                def _dun_blok_mini(lid, mv):
                    """TIER 3 — minimal, sadece anahtar değerler."""
                    _ddf = _dun_verisi(lid)
                    _m2v = HASTANELER.get(lid, {}).get("m2", 10000)
                    flag = "⚠️" if mv["anormal"] else "✓"
                    if not _ddf.empty:
                        dkwh = _col_sum(_ddf, "Toplam_Hastane_Tuketim_kWh")
                        dgaz = _col_sum(_ddf, "Dogalgaz_Tuketim_m3")
                        dkoj = _col_sum(_ddf, "Kojen_Uretim_kWh")
                        dseb = _col_sum(_ddf, "Sebeke_Tuketim_kWh")
                        kv   = round(dkoj/dgaz,2) if dgaz>0 and dkoj>0 else "-"
                        sb   = f"%{round(dseb/(dseb+dkoj)*100,1)}" if (dseb+dkoj)>0 else "-"
                        yo   = round(dkwh/_m2v,2) if dkwh>0 else "-"
                        return f"  [{flag}] {mv['isim']}: {yo} kWh/m²  Koj:{kv}  Şeb:{sb}\n"
                    else:
                        return f"  [?] {mv['isim']}: veri yok\n"

                # ── Referans satırı (tüm tier'larda ortak) ──
                _ref = (
                    "Referans: Yoğunluk 0.5–1.5 kWh/m²/gün | "
                    "Kojen ≥3.5 kWh/m³ | Şebeke <%30 | Gaz verimi ≥5.0 kWh/m³\n\n"
                )

                # ════════════════ TIER 1: 1-3 lokasyon ════════════════
                if _lok_n <= 3:
                    _lok_bloklari = [_dun_blok_tam(lid, mv) for lid, mv in _sirali]
                    _max_tok = 500
                    _yonerge = (
                        "Türkçe, mühendis dilinde:\n"
                        "1. Dünün enerji dengesi — kojen/şebeke/gaz üçgeni\n"
                        "2. En kritik anomali ve kök nedeni\n"
                        "3. Bugün yapılacak 1 somut aksiyon\n"
                        "Maksimum 180 kelime."
                    )

                # ════════════════ TIER 2: 4-7 lokasyon ════════════════
                elif _lok_n <= 7:
                    # Tüm lokasyonlar özet tablo
                    _ozet_satirlar = [_dun_blok_ozet(lid, mv) for lid, mv in _sirali]
                    # Anormal olanlar için tam detay (max 3)
                    _anormal_lids  = [(lid, mv) for lid, mv in _sirali if mv["anormal"]][:3]
                    _detay_satirlar= [_dun_blok_tam(lid, mv) for lid, mv in _anormal_lids]
                    _lok_bloklari  = (
                        ["ÖZET TABLO (tüm lokasyonlar):\n"] + _ozet_satirlar +
                        (["\nANORMAL LOKASYONLAR — detay:\n"] + _detay_satirlar if _detay_satirlar else [])
                    )
                    _max_tok = 650
                    _yonerge = (
                        "Türkçe, mühendis dilinde:\n"
                        "1. Grup geneli enerji dengesi (1-2 cümle)\n"
                        "2. Anormal lokasyonların kök nedeni (her biri 1-2 cümle)\n"
                        "3. Bugün öncelikli yapılacak 2 aksiyon (lokasyon adıyla)\n"
                        "Maksimum 220 kelime."
                    )

                # ════════════════ TIER 3: 8+ lokasyon ════════════════
                else:
                    # Grup istatistikleri
                    _tum_yo    = [mv["kwh_m2"] for _, mv in _sirali]
                    _grp_ort   = round(float(np.mean(_tum_yo)), 2)
                    _grp_std   = round(float(np.std(_tum_yo)), 2)
                    _grp_min   = _sirali[0][1]["isim"]
                    _grp_max   = _sirali[-1][1]["isim"]
                    _anormal_n2= sum(1 for _, mv in _sirali if mv["anormal"])
                    _kojen_vrs = [mv["kojen_verim"] for _, mv in _sirali if mv["kojen_verim"]]
                    _seb_vrs   = [mv["sebeke_bag"]  for _, mv in _sirali if mv["sebeke_bag"]]
                    _grp_blok  = (
                        f"GRUP İSTATİSTİKLERİ ({_lok_n} lokasyon):\n"
                        f"  Yoğunluk: ort {_grp_ort}  std {_grp_std}  "
                        f"  en iyi {_grp_min}  en yüksek {_grp_max}\n"
                        f"  Anormal lokasyon: {_anormal_n2}/{_lok_n}\n"
                    )
                    if _kojen_vrs:
                        _grp_blok += f"  Kojen verim ort: {round(float(np.mean(_kojen_vrs)),2)} kWh/m³\n"
                    if _seb_vrs:
                        _grp_blok += f"  Şebeke bağ. ort: %{round(float(np.mean(_seb_vrs)),1)}\n"

                    # Tüm lokasyonlar mini satır
                    _mini_satirlar = [_dun_blok_mini(lid, mv) for lid, mv in _sirali]
                    # Sadece top-3 kritik (en yüksek yoğunluk + anormal) tam detay
                    _kritik = [(lid, mv) for lid, mv in _sirali if mv["anormal"]]
                    _kritik += [(lid, mv) for lid, mv in reversed(_sirali)
                                if not mv["anormal"] and (lid, mv) not in _kritik]
                    _kritik = _kritik[:3]
                    _detay_satirlar = [_dun_blok_tam(lid, mv) for lid, mv in _kritik]
                    _lok_bloklari = (
                        [_grp_blok, "\nTÜM LOKASYONLAR (mini):\n"] + _mini_satirlar +
                        ["\nKRİTİK LOKASYONLAR — detay:\n"] + _detay_satirlar
                    )
                    _max_tok = 800
                    _yonerge = (
                        "Türkçe, mühendis dilinde, yönetici özeti formatında:\n"
                        "1. Grup geneli durum: kaç lokasyon normal/anormal, genel trend\n"
                        "2. En kritik 3 lokasyon: kısa kök neden (1 cümle/lokasyon)\n"
                        "3. Sistem geneli 1 stratejik aksiyon + 2 acil lokasyon aksiyonu\n"
                        "Maksimum 250 kelime."
                    )

                _ort_str = f"{list(_ai_metriks.values())[0].get('ort_kwh_m2','?')}"
                _prompt = (
                    f"Sen Acıbadem Sağlık Grubu enerji yönetimi uzmanısın. "
                    f"Her sabah dünün verilerini analiz edip günlük rapor hazırlıyorsun.\n"
                    f"Analiz: {_dun_str}  |  Aktif lokasyon: {_lok_n}  |  "
                    f"30g toplam elektrik: {_toplam_kwh_genel:,} kWh\n"
                    + _ref
                    + "".join(_lok_bloklari)
                    + "\n" + _yonerge
                    + "\n\nÖNEMLİ FORMAT KURALLARI:\n"
                    "- Kesinlikle başlık, rapor adı veya hastane adı yazma\n"
                    "- ## veya # gibi markdown başlık kullanma\n"
                    "- ** kalın ** kullanma, düz metin yaz\n"
                    "- Doğrudan madde madde analize başla (1. ... 2. ... 3. ...)\n"
                    "- --- ayraç kullanma"
                )

                with st.spinner(f"🤖 {_lok_n} lokasyon analiz ediliyor…"):
                    try:
                        import anthropic as _anthro
                        _cli = _anthro.Anthropic(api_key=_api_key)
                        _resp = _cli.messages.create(
                            model="claude-haiku-4-5",
                            max_tokens=_max_tok,
                            messages=[{"role": "user", "content": _prompt}]
                        )
                        _ai_metin = _resp.content[0].text.strip()
                        # Supabase'e kaydet — günde 1 kez garantisi
                        _sb_analiz_yaz(_analiz_tarihi, _ai_metin, _lok_n)
                        _ai_zaman_str = _su_an.strftime("%d.%m %H:%M")
                    except Exception as _ae:
                        _ai_metin = f"⚠️ Hata: {str(_ae)[:120]}"
                        _ai_zaman_str = ""

            # ── AI çıktısını göster ──
            if _ai_metin:
                import re as _re
                _ai_temiz = _ai_metin
                _ai_temiz = _re.sub(r"#{1,3}\s*", "", _ai_temiz)
                _ai_temiz = _re.sub(r"\*\*(.+?)\*\*", r"\1", _ai_temiz)
                _ai_temiz = _re.sub(r"\*(.+?)\*",   r"\1", _ai_temiz)
                _ai_temiz = _re.sub(r"^---+$", "", _ai_temiz, flags=_re.MULTILINE)
                _ai_temiz = _ai_temiz.strip()

                # Kart başlığı — sol başlık sağ buton
                st.markdown("""<style>
                div[data-testid="stButton"] > button[kind="secondary"] {
                    background: rgba(56, 189, 248,0.06) !important;
                    border: 1px solid rgba(56, 189, 248,0.2) !important;
                    color: rgba(56, 189, 248,0.7) !important;
                    font-size: 9px !important;
                    padding: 2px 10px !important;
                    border-radius: 6px !important;
                    font-family: 'Inter', sans-serif !important;
                    letter-spacing: 0.5px !important;
                    height: 26px !important;
                    line-height: 1 !important;
                }
                div[data-testid="stButton"] > button[kind="secondary"]:hover {
                    background: rgba(56, 189, 248,0.12) !important;
                    border-color: rgba(56, 189, 248,0.4) !important;
                    color: #38bdf8 !important;
                }
                </style>""", unsafe_allow_html=True)

                # Kart dış çerçevesi — üst kısım
                st.markdown(
                    f"<div style='background:rgba(15, 23, 42, 0.4);backdrop-filter:blur(12px);"
                    f"border:1px solid rgba(255,255,255,0.05);border-radius:8px;margin-top:6px;overflow:hidden;'>"
                    f"<div style='display:flex;justify-content:space-between;align-items:center;"
                    f"padding:10px 14px;border-bottom:1px solid rgba(56, 189, 248,0.08);'>"
                    f"<span style='font-family:Playfair Display,Plus Jakarta Sans,serif;font-size:8px;font-weight:700;"
                    f"color:rgba(56, 189, 248,0.6);letter-spacing:2px;'>🤖 OTOMATİK SABAH ANALİZİ</span>"
                    f"<span style='font-size:8px;color:rgba(150,210,255,0.3);'>🕐 {_ai_zaman_str}</span>"
                    f"</div>"
                    f"<div style='padding:12px 14px;font-size:11px;color:rgba(200,230,255,0.85);"
                    f"line-height:1.7;max-height:220px;overflow-y:auto;"
                    f"scrollbar-width:thin;scrollbar-color:rgba(56, 189, 248,0.3) transparent;'>"
                    + _ai_temiz.replace("\n", "<br>") +
                    f"</div>"
                    f"<div style='padding:6px 14px 10px;border-top:1px solid rgba(56, 189, 248,0.08);'></div>"
                    f"</div>",
                    unsafe_allow_html=True)

                # Buton kartın altındaki boşluğa yerleşiyor — negatif margin ile karta yapışır
                st.markdown("<div style='margin-top:-32px;padding:0 14px 10px;'>", unsafe_allow_html=True)
                if st.button("🔄 Yeniden Analiz Et", key="btn_ai_yenile", use_container_width=True):
                    _sb_metin = None
                    st.rerun()
                st.markdown("</div>", unsafe_allow_html=True)

    else:
        st.markdown(
            "<div class='alrt-y'>📊 Henüz yeterli veri yok.</div>",
            unsafe_allow_html=True)

    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)


# ============ FOOTER ============
st.markdown(f"""
<div style="text-align:center; padding:10px 0 4px; border-top:1px solid rgba(56, 189, 248,0.08); margin-top:10px;">
  <span style="font-family:'Playfair Display','Plus Jakarta Sans',serif; font-size:9px; color:rgba(56, 189, 248,0.25); letter-spacing:2px;">
    ACIBADEM ENERJİ YÖNETİM SİSTEMİ &nbsp;·&nbsp; {now_display.strftime('%d.%m.%Y %H:%M')}
  </span>
</div>
""", unsafe_allow_html=True)

# ============ AYARLAR ============
with st.expander("⚙️  Ayarlar", expanded=False):
    st.markdown('<div class="sec">⚙️ SİSTEM AYARLARI</div>', unsafe_allow_html=True)

    ayar_tab1, ayar_tab2, ayar_tab3, ayar_tab4, ayar_tab5, ayar_tab6 = st.tabs(["🔗 Bağlantı", "📦 Güncellemeler", "🏥 Hastaneler", "📐 Alan (m²)", "📢 Mesaj Gönder", "🎛️ Uzaktan Kontrol"])

    # ── Bağlantı ──
    with ayar_tab1:
        st.markdown("**Supabase Bağlantısı**")
        mevcut_url = config.get("supabase_url", "")
        mevcut_key = config.get("supabase_key", "")
        yeni_url = st.text_input("Supabase URL", value=mevcut_url, key="ayar_url")
        yeni_key = st.text_input("Supabase Anon Key", value=mevcut_key, key="ayar_key", type="password")
        if st.button("💾 Bağlantıyı Kaydet", key="btn_baglanti"):
            import json as _json
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            cfg_yeni = config.copy()
            cfg_yeni["supabase_url"] = yeni_url.strip()
            cfg_yeni["supabase_key"] = yeni_key.strip()
            with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                _json.dump(cfg_yeni, f, indent=2, ensure_ascii=False)
            st.success("✅ Bağlantı bilgileri kaydedildi. Sayfayı yenileyin.")

    # ── Güncellemeler ──
    with ayar_tab2:
        st.markdown("**Son Güncellemeler**")
        gunc = fetch_guncellemeler(url, key)
        durum_renk_map = {"tamamlandi": "#10b981", "bekliyor": "#f59e0b", "iptal": "#6b7280", "hata": "#ef4444"}
        durum_icon_map = {"tamamlandi": "✅", "bekliyor": "⏳", "iptal": "❌", "hata": "🚨"}
        if not gunc:
            st.info("Henüz güncelleme kaydı yok.")
        for r in gunc:
            dr = durum_renk_map.get(r["durum"], "#aaa")
            di = durum_icon_map.get(r["durum"], "?")
            tarih = r["created_at"][:16].replace("T", " ")
            st.markdown(f"""
            <div style="padding:7px 10px; margin:3px 0; background:rgba(0,20,50,0.6);
                        border-radius:8px; border-left:3px solid {dr};">
              <div style="font-size:12px; color:#e0f2fe; font-weight:600;">{di} {r['versiyon']}
                <span style="color:rgba(150,210,255,0.5); font-size:11px;">→ {r['hedef']}</span>
              </div>
              <div style="font-size:10px; color:{dr};">{r['durum'].upper()} &nbsp;·&nbsp;
                <span style="color:rgba(150,210,255,0.35);">{tarih}</span>
              </div>
            </div>
            """, unsafe_allow_html=True)

    # ── Hastaneler ──
    with ayar_tab3:
        st.markdown("**Kayıtlı Lokasyonlar**")
        if not lokasyonlar:
            st.info("Lokasyon verisi bulunamadı.")
        else:
            for lok in lokasyonlar:
                ping = str(lok.get("ping_zamani") or "—")[:16].replace("T", " ")
                isim = lok.get("isim") or lok.get("lokasyon_id", "?")
                st.markdown(f"""
                <div style="padding:8px 12px; margin:4px 0; background:rgba(0,20,50,0.6);
                            border-radius:8px; border:1px solid rgba(56, 189, 248,0.1);
                            display:flex; justify-content:space-between; align-items:center;">
                  <span style="font-size:12px; color:#e0f2fe; font-weight:600;">🏥 {isim}</span>
                  <span style="font-size:10px; color:rgba(150,210,255,0.45);">Son ping: {ping}</span>
                </div>
                """, unsafe_allow_html=True)

    # ── Alan (m²) ──
    with ayar_tab4:
        st.markdown("**Lokasyon Alan Bilgileri (m²)**")
        st.caption("Yıllık güncellemeler için buradan değiştirebilirsiniz. Kaydetmek için butona basın.")
        yeni_m2 = {}
        for lok_id, lok_info in HASTANELER.items():
            mevcut_m2 = lok_info.get("m2", 10000)
            yeni_m2[lok_id] = st.number_input(
                f"🏥 {lok_info['isim']}",
                min_value=100,
                max_value=500000,
                value=mevcut_m2,
                step=100,
                key=f"m2_{lok_id}",
                help=f"Mevcut: {mevcut_m2:,} m²"
            )
        if st.button("💾 m² Değerlerini Kaydet", key="btn_m2"):
            try:
                save_m2_supabase(url, key, yeni_m2)
                fetch_m2_supabase.clear()
                st.success("✅ m² değerleri kaydedildi. Sayfayı yenileyin.")
            except Exception as ex:
                cfg_yeni = config.copy()
                cfg_yeni["m2_degerler"] = {k: int(v) for k, v in yeni_m2.items()}
                os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(cfg_yeni, f, indent=2, ensure_ascii=False)
                st.warning(f"⚠️ Supabase'e yazılamadı, local kaydedildi: {ex}")

    # ── Mesaj Gönder ──
    with ayar_tab5:
        st.markdown("**Lokasyona Mesaj Gönder**")
        st.caption("Seçilen lokasyonun ekranında bildirim olarak görünür. Personel okundu diyene kadar kalır.")

        _lok_secenekler = {"Tüm Lokasyonlar": "all"}
        for _lid, _linf in HASTANELER.items():
            _lok_secenekler[_linf["isim"]] = _lid

        _msg_hedef   = st.selectbox("Lokasyon", list(_lok_secenekler.keys()), key="msg_hedef")
        _msg_oncelik = st.radio("Öncelik", ["bilgi", "uyari", "acil"],
                                format_func=lambda x: {"bilgi": "🔵 Bilgi", "uyari": "🟡 Uyarı", "acil": "🔴 Acil"}[x],
                                horizontal=True, key="msg_oncelik")
        _msg_metin   = st.text_area("Mesaj", placeholder="Merhaba, bugün saat 14:00'de bakım yapılacaktır...",
                                    height=100, key="msg_metin")

        if st.button("📤 Gönder", key="btn_msg_gonder", use_container_width=True):
            if not _msg_metin.strip():
                st.warning("⚠️ Mesaj boş olamaz.")
            else:
                try:
                    from supabase import create_client as _cc
                    _c = _cc(url, key)
                    _c.table("bildirimler").insert({
                        "lokasyon":  _lok_secenekler[_msg_hedef],
                        "mesaj":     _msg_metin.strip(),
                        "gonderen":  "GM Merkez",
                        "oncelik":   _msg_oncelik,
                        "okundu":    False,
                    }).execute()
                    st.success(f"✅ Mesaj gönderildi → {_msg_hedef}")
                except Exception as _me:
                    st.error(f"❌ Gönderilemedi: {_me}")

    # ── Uzaktan Kontrol ──
    with ayar_tab6:
        st.markdown("**🎛️ Uzaktan BACnet Set Kontrolü**")
        st.caption("Lokasyon BACnet noktasına değer gönder. Lokasyon PC 1 dakika içinde uygular.")

        _uc_col1, _uc_col2 = st.columns(2)

        with _uc_col1:
            # Lokasyon seçimi (sadece aktif lokasyonlar)
            _uc_lok_sec = {_linf["isim"]: _lid for _lid, _linf in HASTANELER.items()}
            _uc_lok_isim = st.selectbox("Lokasyon", list(_uc_lok_sec.keys()), key="uc_lok")
            _uc_lok_id   = _uc_lok_sec[_uc_lok_isim]

        with _uc_col2:
            # Bu lokasyonun nokta listesini Supabase'den çek
            try:
                from supabase import create_client as _ucc
                _ucc_client = _ucc(url, key)
                _uc_noktalar_raw = (
                    _ucc_client.table("lokasyon_noktalar")
                    .select("nokta_adi,aciklama")
                    .eq("lokasyon", _uc_lok_id)
                    .execute()
                    .data
                )
                _uc_nokta_map = {
                    (n.get("aciklama") or n["nokta_adi"]): n["nokta_adi"]
                    for n in _uc_noktalar_raw
                }
            except Exception:
                _uc_nokta_map = {}

            if _uc_nokta_map:
                _uc_nokta_label = st.selectbox("Nokta", list(_uc_nokta_map.keys()), key="uc_nokta")
                _uc_nokta_adi   = _uc_nokta_map[_uc_nokta_label]
            else:
                st.warning(f"⚠️ {_uc_lok_isim} için tanımlı nokta yok.")
                _uc_nokta_adi = None

        _uc_deger = st.number_input(
            "Hedef Değer (°C)",
            min_value=0.0, max_value=99.0, value=7.0, step=0.5,
            key="uc_deger"
        )

        # Son komutlar tablosu
        try:
            _uc_son_komutlar = (
                _ucc_client.table("komutlar")
                .select("nokta_adi,hedef_deger,durum,hata_mesaji,created_at,executed_at")
                .eq("lokasyon", _uc_lok_id)
                .order("created_at", desc=True)
                .limit(30)
                .execute()
                .data
            )
        except Exception:
            _uc_son_komutlar = []

        _uc_g_col1, _uc_g_col2 = st.columns([1, 2])
        with _uc_g_col1:
            if st.button("📡 Komutu Gönder", key="btn_uc_gonder",
                         use_container_width=True,
                         disabled=(not _uc_nokta_adi)):
                try:
                    from supabase import create_client as _ucc2
                    _ucc2(url, key).table("komutlar").insert({
                        "lokasyon":    _uc_lok_id,
                        "nokta_adi":   _uc_nokta_adi,
                        "hedef_deger": float(_uc_deger),
                        "durum":       "bekliyor",
                    }).execute()
                    st.success(f"✅ Komut gönderildi → {_uc_nokta_label} = {_uc_deger}°C")
                    st.rerun()
                except Exception as _uce:
                    st.error(f"❌ Gönderilemedi: {_uce}")

        with _uc_g_col2:
            st.caption("Son komutlar:")
            if _uc_son_komutlar:
                _durum_renk = {
                    "bekliyor":    "🟡",
                    "tamamlandi":  "✅",
                    "hata":        "❌",
                }
                for _k in _uc_son_komutlar:
                    _zaman = (_k.get("created_at", "")[:16].replace("T", " "))
                    _icon  = _durum_renk.get(_k["durum"], "⏳")
                    _hata  = f" — {_k['hata_mesaji']}" if _k.get("hata_mesaji") else ""
                    st.markdown(
                        f"{_icon} `{_k['nokta_adi']}` → **{_k['hedef_deger']}°C** "
                        f"<span style='color:rgba(255,255,255,0.5);font-size:11px;'>{_zaman}{_hata}</span>",
                        unsafe_allow_html=True
                    )
            else:
                st.caption("Henüz komut gönderilmedi.")
