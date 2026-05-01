# app_merkez.py
# Acıbadem Genel Merkez — Tek Sayfa Komuta Merkezi
# Harita ortada, widget'lar etrafında — Koyu Mavi / Neon

from __future__ import annotations
import os, json
import numpy as np
import streamlit as st
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Acıbadem GM — Komuta Merkezi",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============ CSS ============
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Inter:wght@300;400;600;700&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    background: #020b18 !important;
}
[data-testid="stAppViewContainer"] {
    background: radial-gradient(ellipse at 50% 40%, #071830 0%, #020b18 70%) !important;
}
[data-testid="stHeader"]                  { background: transparent !important; }
[data-testid="collapsedControl"]          { display: none !important; visibility: hidden !important; }
[data-testid="stSidebarCollapsedControl"] { display: none !important; visibility: hidden !important; }
section[data-testid="stSidebarCollapsedControl"] { display: none !important; }
.stSidebarCollapsedControl               { display: none !important; }
button[kind="header"]                    { display: none !important; }
#MainMenu                                { display: none !important; }
header[data-testid="stHeader"] button    { display: none !important; }
[data-testid="stSidebar"]      { display: none !important; }
[data-testid="stToolbar"]      { display: none !important; }
.block-container { padding: 0.5rem 1.5rem 1rem 1.5rem !important; max-width: 100% !important; }

/* Tüm yazılar */
h1,h2,h3,h4,h5,h6 { color: #e0f2fe !important; font-family: 'Orbitron', sans-serif !important; }
p, span, div, label { color: rgba(200,230,255,0.85) !important; font-family: 'Inter', sans-serif !important; }

/* Streamlit Material ikon istisnası — _arrow_right gibi ikonların bozulmaması için */
span[data-testid="stIconMaterial"],
[data-testid="stExpanderToggleIcon"] span,
button span[data-testid="stIconMaterial"] {
    font-family: 'Material Symbols Rounded' !important;
    color: inherit !important;
}

/* Metrik */
[data-testid="stMetricValue"]  { color: #00d4ff !important; font-size: 22px !important; font-weight: 800 !important; font-family: 'Orbitron', sans-serif !important; text-shadow: 0 0 15px rgba(0,212,255,0.5) !important; }
[data-testid="stMetricLabel"]  { color: rgba(150,210,255,0.7) !important; font-size: 10px !important; letter-spacing: 1px !important; text-transform: uppercase !important; }
[data-testid="stMetricDelta"]  { color: #10b981 !important; }
[data-testid="metric-container"] {
    background: linear-gradient(135deg, rgba(0,30,60,0.85), rgba(0,15,40,0.95)) !important;
    border: 1px solid rgba(0,212,255,0.2) !important;
    border-radius: 12px !important;
    padding: 12px !important;
    box-shadow: 0 0 15px rgba(0,212,255,0.06) !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 3px; }
::-webkit-scrollbar-track { background: #020b18; }
::-webkit-scrollbar-thumb { background: rgba(0,212,255,0.3); border-radius: 3px; }

/* Neon kart */
.nk {
    background: linear-gradient(135deg, rgba(0,25,60,0.9), rgba(0,12,35,0.95));
    border: 1px solid rgba(0,212,255,0.2);
    border-radius: 14px;
    padding: 14px;
    margin-bottom: 10px;
    box-shadow: 0 0 18px rgba(0,212,255,0.06);
}
.nk-green { border-color: rgba(16,185,129,0.45) !important; box-shadow: 0 0 15px rgba(16,185,129,0.08) !important; }
.nk-red   { border-color: rgba(239,68,68,0.45) !important;  box-shadow: 0 0 15px rgba(239,68,68,0.08) !important;  }
.nk-gray  { border-color: rgba(100,120,150,0.3) !important; opacity: 0.6; }

.lok-scroll {
    max-height: 492px;
    overflow-y: auto;
    overflow-x: hidden;
    padding-right: 3px;
    scrollbar-width: thin;
    scrollbar-color: rgba(0,212,255,0.25) rgba(0,15,40,0.4);
}
.lok-scroll::-webkit-scrollbar { width: 4px; }
.lok-scroll::-webkit-scrollbar-track { background: rgba(0,15,40,0.4); border-radius: 2px; }
.lok-scroll::-webkit-scrollbar-thumb { background: rgba(0,212,255,0.28); border-radius: 2px; }
.lok-scroll::-webkit-scrollbar-thumb:hover { background: rgba(0,212,255,0.55); }

.sec { font-family:'Orbitron',sans-serif; font-size:10px; color:rgba(0,212,255,0.7);
       letter-spacing:2px; text-transform:uppercase; border-bottom:1px solid rgba(0,212,255,0.15);
       padding-bottom:5px; margin-bottom:10px; }

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
      0 0 10px rgba(0,212,255,0.4),
      0 0 25px rgba(0,212,255,0.2),
      0 0 50px rgba(0,212,255,0.08);
    opacity: 0.82;
  }
  50% {
    text-shadow:
      0 0 20px rgba(0,212,255,1),
      0 0 45px rgba(0,212,255,0.7),
      0 0 90px rgba(0,212,255,0.35),
      0 0 140px rgba(0,212,255,0.15);
    opacity: 1;
  }
}
@keyframes neon-breathe-sub {
  0%, 100% { opacity: 0.35; letter-spacing: 4px; }
  50%       { opacity: 0.65; letter-spacing: 5px; }
}

.btn-refresh button {
    background: linear-gradient(135deg,#003d80,#0066cc) !important;
    color: #fff !important; border: 1px solid rgba(0,212,255,0.4) !important;
    border-radius: 8px !important; font-size: 11px !important;
    padding: 4px 12px !important; font-family:'Inter',sans-serif !important;
}

/* Alarm expander */
[data-testid="stExpander"] {
    background: rgba(0,15,40,0.7) !important;
    border: 1px solid rgba(0,212,255,0.15) !important;
    border-radius: 10px !important;
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
[data-testid="stExpanderToggleIcon"] { color: rgba(0,212,255,0.6) !important; }
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
    background: rgba(0,20,55,0.6);
    border: 1px solid rgba(0,212,255,0.12);
    border-radius: 8px; padding: 10px 14px; margin-top: 8px;
}
.btn-goto button {
    background: rgba(0,212,255,0.08) !important;
    color: #00d4ff !important;
    border: 1px solid rgba(0,212,255,0.3) !important;
    border-radius: 8px !important;
    font-size: 11px !important;
    padding: 4px 14px !important;
    width: 100% !important;
}
.btn-goto button:hover { background: rgba(0,212,255,0.18) !important; }
</style>
""", unsafe_allow_html=True)

# ============ SABİT VERİ ============
HASTANELER = {
    # ── İstanbul ──
    "maslak":       {"isim": "Acıbadem Maslak",        "kisa": "MASLAK",        "lat": 41.1273, "lon": 29.0246, "m2": 15000, "renk": "#00d4ff"},
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
    """Open-Meteo API'den İstanbul anlık sıcaklığını çek (ücretsiz, API key yok)."""
    try:
        import urllib.request, json as _json
        url = "https://api.open-meteo.com/v1/forecast?latitude=41.0082&longitude=28.9784&current=temperature_2m&timezone=Europe%2FIstanbul"
        with urllib.request.urlopen(url, timeout=5) as r:
            data = _json.loads(r.read())
        return float(data["current"]["temperature_2m"])
    except Exception:
        return None

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

# m² değerlerini Supabase'den yükle (yoksa config/default kullan)
m2_config = {}
if bagli:
    m2_config = fetch_m2_supabase(url, key)
if not m2_config:
    m2_config = config.get("m2_degerler", {})
for lok_id in HASTANELER:
    if lok_id in m2_config:
        HASTANELER[lok_id]["m2"] = int(m2_config[lok_id])

now  = datetime.now()
dun  = (now - timedelta(days=1)).strftime("%Y-%m-%d")

# ============ HEADER ============
st.markdown("""
<div style="text-align:center; padding:12px 0 8px;">
  <div style="font-family:'Orbitron',sans-serif; font-size:9px; color:rgba(0,212,255,0.45);
              letter-spacing:5px; text-transform:uppercase;
              animation:neon-breathe-sub 3.5s ease-in-out infinite;">
    ACIBADEM SAĞLIK GRUBU
  </div>
  <div style="font-family:'Orbitron',sans-serif; font-size:20px; font-weight:900; color:#00d4ff;
              letter-spacing:4px; text-transform:uppercase; line-height:1.3;
              animation:neon-breathe 3s ease-in-out infinite;">
    ENERJİ &amp; HVAC KOMUTA MERKEZİ
  </div>
  <div style="font-family:'Inter',sans-serif; font-size:10px; color:rgba(150,210,255,0.4);
              letter-spacing:2px; margin-top:2px;
              animation:neon-breathe-sub 3.5s ease-in-out infinite; animation-delay:0.8s;">
    GENEL MERKEZ — CANLI İZLEME
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
# ANA LAYOUT: sol | harita | sağ
# ============================================================
sol, merkez, sag = st.columns([1, 2.8, 1], gap="small")

# ════════════════════════════════
# SOL KOLON
# ════════════════════════════════
with sol:
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
        sira_badge = f'<span style="position:absolute;top:8px;left:10px;font-family:Orbitron,sans-serif;font-size:8px;color:rgba(150,210,255,0.35);font-weight:700;">#{i+1}</span>' if i < 4 else ""

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
            f'<div class="{card_cls}" style="padding:14px;position:relative;">'
            + sira_badge +
            f'<a href="?detay={lok_id}" title="Detaya Git" style="position:absolute;top:8px;right:10px;'
            f'font-size:14px;color:rgba({rr},{rg},{rb},0.55);text-decoration:none;'
            f'transition:color 0.2s;" onmouseover="this.style.color=\'rgba({rr},{rg},{rb},1)\'" '
            f'onmouseout="this.style.color=\'rgba({rr},{rg},{rb},0.55)\'">⟶</a>'
            f'<div style="display:flex;align-items:center;gap:14px;">'
            f'<div style="position:relative;width:58px;height:58px;flex-shrink:0;display:flex;align-items:center;justify-content:center;">'
            f'<div style="position:absolute;top:-5px;left:-5px;right:-5px;bottom:-5px;border-radius:50%;'
            f'background:radial-gradient(circle,rgba({rr},{rg},{rb},0.22) 0%,rgba({rr},{rg},{rb},0.05) 55%,transparent 75%);'
            f'animation:breathe-ring 3s ease-in-out infinite;"></div>'
            f'<div style="font-size:36px;line-height:1;position:relative;z-index:1;'
            f'filter:drop-shadow(0 0 8px rgba({rr},{rg},{rb},0.8));">🏥</div>'
            f'<div style="position:absolute;top:2px;right:2px;z-index:2;width:11px;height:11px;'
            f'border-radius:50%;background:rgba({dr},{dg},{db},1);border:2px solid #020b18;'
            f'box-shadow:0 0 5px rgba({dr},{dg},{db},0.9);"></div>'
            f'</div>'
            f'<div style="flex:1;min-width:0;">'
            f'<div style="font-family:Orbitron,sans-serif;font-size:10px;font-weight:700;'
            f'color:{renk};letter-spacing:1.5px;text-shadow:0 0 7px rgba({rr},{rg},{rb},0.6);'
            f'margin-bottom:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{lok_info["kisa"]}</div>'
            f'<div style="font-size:8px;color:{durum_renk};font-weight:600;margin-bottom:5px;">{durum_lbl}</div>'
            f'<div style="display:flex;align-items:baseline;gap:4px;margin-bottom:3px;">'
            f'<span style="font-family:Orbitron,sans-serif;font-size:16px;font-weight:900;'
            f'color:{renk};text-shadow:0 0 10px rgba({rr},{rg},{rb},0.65);line-height:1;">{kwh_str}</span>'
            f'<span style="font-size:8px;color:rgba(150,210,255,0.5);">kWh</span>'
            f'<span style="margin-left:4px;">{degisim_html}</span>'
            f'</div>'
            f'<div style="display:inline-flex;align-items:center;gap:5px;'
            f'background:rgba(0,212,255,0.05);border-radius:5px;padding:3px 8px;'
            f'border:1px solid rgba(0,212,255,0.10);">'
            f'<span style="font-size:7px;color:rgba(150,210,255,0.4);text-transform:uppercase;letter-spacing:1px;">kWh/m²</span>'
            f'<span style="font-family:Orbitron,sans-serif;font-size:11px;color:#00d4ff;font-weight:700;">{verim_str}</span>'
            f'</div>'
            f'</div></div></div>'
        )

    tum_kartlar += '</div>'
    st.markdown(tum_kartlar, unsafe_allow_html=True)
    st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)

    # ── Global Özet ──
    st.markdown('<div class="sec">⚡ GLOBAL ÖZET (30G)</div>', unsafe_allow_html=True)
    if not df_all.empty:
        son30 = df_all[df_all["Tarih"] >= (now - timedelta(days=30))]
        def tr(sayi, ondalik=0):
            """Türkçe sayı formatı: binlik=nokta, ondalık=virgül."""
            fmt = f"{sayi:,.{ondalik}f}"
            if ondalik > 0:
                parts = fmt.split(".")
                return parts[0].replace(",", ".") + "," + parts[1]
            return fmt.replace(",", ".")

        ozet = {
            "⚡ Toplam Enerji": f"{tr(son30['Toplam_Hastane_Tuketim_kWh'].sum()/1000)} MWh" if "Toplam_Hastane_Tuketim_kWh" in son30 else "—",
            "🔥 Doğalgaz": f"{tr(son30.get('Kazan_Dogalgaz_m3', pd.Series([0])).sum() + son30.get('Kojen_Dogalgaz_m3', pd.Series([0])).sum())} m³",
            "❄️ Soğutma": f"{tr(son30['Toplam_Sogutma_Tuketim_kWh'].sum()/1000)} MWh" if "Toplam_Sogutma_Tuketim_kWh" in son30 else "—",
            "💧 Su": f"{tr(son30['Su_Tuketimi_m3'].sum())} m³" if "Su_Tuketimi_m3" in son30 else "—",
            "⚙️ Kojen Üretim": f"{tr(son30['Kojen_Uretim_kWh'].sum()/1000)} MWh" if "Kojen_Uretim_kWh" in son30 else "—",
        }
        for label, val in ozet.items():
            st.markdown(f"""
            <div style="display:flex; justify-content:space-between; align-items:center;
                        padding:7px 10px; margin:3px 0; background:rgba(0,20,50,0.6);
                        border-radius:8px; border:1px solid rgba(0,212,255,0.1);">
              <span style="font-size:11px; color:rgba(150,210,255,0.7);">{label}</span>
              <span style="font-size:12px; font-weight:700; color:#00d4ff; font-family:'Orbitron',sans-serif;">{val}</span>
            </div>
            """, unsafe_allow_html=True)

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
body {{ background:#020b18; }}
#map {{ width:100%; height:608px; background:#020b18; }}
.leaflet-container {{ background:#020b18 !important; font-family:Inter,sans-serif; }}
.leaflet-popup-content-wrapper {{
    background:rgba(2,11,30,0.96) !important;
    border:1px solid rgba(0,212,255,0.35) !important;
    border-radius:12px !important;
    box-shadow:0 0 24px rgba(0,212,255,0.18), 0 4px 20px rgba(0,0,0,0.6) !important;
    padding:0 !important;
}}
.leaflet-popup-content {{ margin:0 !important; color:white !important; }}
.leaflet-popup-tip-container {{ display:none; }}
.leaflet-popup-close-button {{ color:rgba(0,212,255,0.5) !important; font-size:16px !important; top:8px !important; right:10px !important; }}
.leaflet-control-zoom a {{
    background:rgba(0,15,40,0.9) !important;
    color:#00d4ff !important;
    border-color:rgba(0,212,255,0.25) !important;
}}
.leaflet-control-zoom a:hover {{ background:rgba(0,30,70,0.95) !important; }}
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
    maxZoom: 19, subdomains: 'abcd'
}}).addTo(map);

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
        ? '<div style="margin-top:8px;height:3px;background:rgba(0,212,255,0.15);border-radius:2px;"><div style="height:3px;background:'+c+';border-radius:2px;width:80%;"></div></div>'
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
    import streamlit.components.v1 as components
    components.html(harita_html, height=612, scrolling=False)

    # ── Harita altı: Chiller Set vs Dış Hava (Gauge Kartları) ──
    st.markdown('<div class="sec">🌡️ CHİLLER SET vs DIŞ HAVA</div>', unsafe_allow_html=True)
    if not df_all.empty and "Chiller_Set_Temp_C" in df_all.columns:
        # En son veri noktasını al (her lokasyon için)
        son_veri = df_all.sort_values("Tarih").groupby("lokasyon_id").last().reset_index()

        chiller_vals = {}
        # Canlı dış hava → Open-Meteo, yoksa DB'den fallback
        dis_hava_val = fetch_dis_hava()
        _dis_hava_kaynak = "🌐 Canlı" if dis_hava_val is not None else "📊 DB"
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
            min_renk = HASTANELER.get(min_lok, {}).get("renk", "#00d4ff")
            max_renk = HASTANELER.get(max_lok, {}).get("renk", "#f59e0b")
            min_isim = HASTANELER.get(min_lok, {}).get("kisa", min_lok)
            max_isim = HASTANELER.get(max_lok, {}).get("kisa", max_lok)

            g_steps = [
                {"range": [4,  7],  "color": "rgba(0,212,255,0.08)"},
                {"range": [7,  10], "color": "rgba(245,158,11,0.07)"},
                {"range": [10, 16], "color": "rgba(239,68,68,0.07)"},
            ]

            def gauge_fig(val, renk, isim, ikon, etiket):
                rr = int(renk[1:3],16); rg = int(renk[3:5],16); rb = int(renk[5:7],16)
                fig = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=val,
                    number={"suffix": " °C", "font": {"size": 26, "color": renk, "family": "Orbitron, sans-serif"},
                            "valueformat": ".1f"},
                    title={"text": f"{ikon} {isim}<br><span style='font-size:9px;color:#6b8fa8;letter-spacing:1px;'>{etiket}</span>",
                           "font": {"size": 11, "color": "#a0c8ff", "family": "Orbitron, sans-serif"}},
                    gauge={
                        "axis": {"range": [4, 16],
                                 "tickcolor": "rgba(160,200,255,0.25)",
                                 "tickfont": {"size": 8, "color": "rgba(160,200,255,0.4)"},
                                 "dtick": 3},
                        "bar": {"color": f"rgba({rr},{rg},{rb},0.9)", "thickness": 0.25},
                        "bgcolor": "rgba(0,0,0,0)",
                        "borderwidth": 1,
                        "bordercolor": f"rgba({rr},{rg},{rb},0.2)",
                        "steps": g_steps,
                        "threshold": {
                            "line": {"color": renk, "width": 2},
                            "thickness": 0.8,
                            "value": val,
                        },
                    }
                ))
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(t=55, b=10, l=15, r=15),
                    height=185,
                    font=dict(family="Inter, sans-serif", color="#a0c8ff"),
                )
                return fig

            def gauge_fig_dh(val, kaynak=""):
                renk = "#f59e0b"
                rr,rg,rb = 245,158,11
                fig = go.Figure(go.Indicator(
                    mode="gauge+number",
                    value=val,
                    number={"suffix": " °C", "font": {"size": 26, "color": renk, "family": "Orbitron, sans-serif"},
                            "valueformat": ".1f"},
                    title={"text": f"🌡️ DIŞ HAVA<br><span style='font-size:9px;color:#6b8fa8;letter-spacing:1px;'>İSTANBUL — {kaynak}</span>",
                           "font": {"size": 11, "color": "#a0c8ff", "family": "Orbitron, sans-serif"}},
                    gauge={
                        "axis": {"range": [-10, 45],
                                 "tickcolor": "rgba(160,200,255,0.25)",
                                 "tickfont": {"size": 8, "color": "rgba(160,200,255,0.4)"},
                                 "dtick": 10},
                        "bar": {"color": f"rgba({rr},{rg},{rb},0.9)", "thickness": 0.25},
                        "bgcolor": "rgba(0,0,0,0)",
                        "borderwidth": 1,
                        "bordercolor": f"rgba({rr},{rg},{rb},0.2)",
                        "steps": [
                            {"range": [-10, 5],  "color": "rgba(0,212,255,0.08)"},
                            {"range": [5,  25],  "color": "rgba(16,185,129,0.06)"},
                            {"range": [25, 45],  "color": "rgba(239,68,68,0.07)"},
                        ],
                        "threshold": {
                            "line": {"color": renk, "width": 2},
                            "thickness": 0.8,
                            "value": val,
                        },
                    }
                ))
                fig.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)",
                    margin=dict(t=55, b=10, l=15, r=15),
                    height=185,
                    font=dict(family="Inter, sans-serif", color="#a0c8ff"),
                )
                return fig

            gc1, gc2, gc3 = st.columns(3)
            with gc1:
                st.plotly_chart(
                    gauge_fig(min_val, min_renk, min_isim, "🏥", "EN DÜŞÜK SET"),
                    use_container_width=True, config={"displayModeBar": False}
                )
            with gc2:
                st.plotly_chart(
                    gauge_fig(max_val, max_renk, max_isim, "🏥", "EN YÜKSEK SET"),
                    use_container_width=True, config={"displayModeBar": False}
                )
            with gc3:
                if dis_hava_val is not None:
                    st.plotly_chart(
                        gauge_fig_dh(dis_hava_val, _dis_hava_kaynak),
                        use_container_width=True, config={"displayModeBar": False}
                    )
        else:
            st.info("Chiller set verisi bulunamadı.")

# ════════════════════════════════
# SAĞ KOLON
# ════════════════════════════════
with sag:
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
            arizali = ", ".join(ozet.get("arizali_cihazlar", [])[:2])
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
        uyari_html = "<div style='max-height:260px;overflow-y:auto;padding-right:2px;'>"
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

    # ── Sezon Göstergesi ──
    st.markdown('<div class="sec">🌡️ SEZON DURUMU</div>', unsafe_allow_html=True)
    if dis_hava_val is not None:
        if dis_hava_val >= 23:
            sezon_ikon, sezon_ad, sezon_renk = "☀️", "SOĞUTMA SEZONU", "#f59e0b"
            sezon_acik = f"Dış hava {dis_hava_val:.1f}°C — Chiller'lar aktif (set ≤7.0°C)"
        elif dis_hava_val <= 7:
            sezon_ikon, sezon_ad, sezon_renk = "❄️", "ISITMA SEZONU", "#38bdf8"
            sezon_acik = f"Dış hava {dis_hava_val:.1f}°C — Kazan sistemleri aktif (set 8.0°C)"
        else:
            sezon_ikon, sezon_ad, sezon_renk = "🌤️", "GEÇİŞ DÖNEMİ", "#10b981"
            sezon_acik = f"Dış hava {dis_hava_val:.1f}°C — Yük dengeli (set 7.5°C)"
        sr=int(sezon_renk[1:3],16); sg=int(sezon_renk[3:5],16); sb=int(sezon_renk[5:7],16)
        st.markdown(
            f"<div style='background:rgba({sr},{sg},{sb},0.08);border:1px solid rgba({sr},{sg},{sb},0.3);"
            f"border-radius:10px;padding:10px 12px;text-align:center;'>"
            f"<div style='font-size:24px;margin-bottom:4px;'>{sezon_ikon}</div>"
            f"<div style='font-family:Orbitron,sans-serif;font-size:9px;font-weight:700;"
            f"color:{sezon_renk};letter-spacing:2px;margin-bottom:4px;'>{sezon_ad}</div>"
            f"<div style='font-size:10px;color:rgba(180,220,255,0.6);'>{sezon_acik}</div>"
            f"</div>",
            unsafe_allow_html=True
        )
    else:
        st.markdown('<div class="alrt-y">🌡️ Dış hava verisi alınamadı</div>', unsafe_allow_html=True)

    # ── En Verimli / En Verimsiz + Günlük Özet ──
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    st.markdown('<div class="sec">📊 GÜNLÜK ÖZET</div>', unsafe_allow_html=True)
    if not df_all.empty and "Toplam_Hastane_Tuketim_kWh" in df_all.columns:
        gun_rows = []
        for lid in aktif_loklar:
            kwh_g = dun_kwh(lid)
            if kwh_g and kwh_g > 0:
                m2_g = HASTANELER.get(lid, {}).get("m2", 10000)
                gun_rows.append({
                    "isim":   HASTANELER.get(lid, {}).get("kisa", lid),
                    "kwh":    kwh_g,
                    "kwh_m2": kwh_g / m2_g,
                    "renk":   HASTANELER.get(lid, {}).get("renk", "#00d4ff"),
                })
        if gun_rows:
            gun_rows.sort(key=lambda x: x["kwh_m2"])
            en_verimli  = gun_rows[0]
            en_verimsiz = gun_rows[-1]
            toplam_aktif   = len(gun_rows)
            toplam_kwh_gun = sum(r["kwh"] for r in gun_rows)
            st.markdown(
                f"<div style='background:rgba(16,185,129,0.08);border:1px solid rgba(16,185,129,0.25);"
                f"border-radius:8px;padding:8px 12px;margin-bottom:6px;'>"
                f"<div style='font-size:8px;color:rgba(16,185,129,0.7);letter-spacing:1px;"
                f"text-transform:uppercase;margin-bottom:2px;'>🥇 En Verimli</div>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                f"<span style='font-size:12px;color:{en_verimli['renk']};font-weight:700;'>{en_verimli['isim']}</span>"
                f"<span style='font-family:Orbitron,sans-serif;font-size:11px;color:#10b981;'>{en_verimli['kwh_m2']:.2f} kWh/m²</span>"
                f"</div></div>",
                unsafe_allow_html=True
            )
            st.markdown(
                f"<div style='background:rgba(239,68,68,0.08);border:1px solid rgba(239,68,68,0.25);"
                f"border-radius:8px;padding:8px 12px;margin-bottom:6px;'>"
                f"<div style='font-size:8px;color:rgba(239,68,68,0.7);letter-spacing:1px;"
                f"text-transform:uppercase;margin-bottom:2px;'>⚠️ En Yüksek Tüketim</div>"
                f"<div style='display:flex;justify-content:space-between;align-items:center;'>"
                f"<span style='font-size:12px;color:{en_verimsiz['renk']};font-weight:700;'>{en_verimsiz['isim']}</span>"
                f"<span style='font-family:Orbitron,sans-serif;font-size:11px;color:#ef4444;'>{en_verimsiz['kwh_m2']:.2f} kWh/m²</span>"
                f"</div></div>",
                unsafe_allow_html=True
            )
            st.markdown(
                f"<div style='background:rgba(0,212,255,0.05);border:1px solid rgba(0,212,255,0.12);"
                f"border-radius:8px;padding:8px 12px;'>"
                f"<div style='display:flex;justify-content:space-between;'>"
                f"<span style='font-size:10px;color:rgba(150,210,255,0.6);'>Aktif Lokasyon</span>"
                f"<span style='font-family:Orbitron,sans-serif;font-size:11px;color:#00d4ff;'>{toplam_aktif}</span>"
                f"</div>"
                f"<div style='display:flex;justify-content:space-between;margin-top:4px;'>"
                f"<span style='font-size:10px;color:rgba(150,210,255,0.6);'>Toplam (dün)</span>"
                f"<span style='font-family:Orbitron,sans-serif;font-size:11px;color:#00d4ff;'>{toplam_kwh_gun/1000:.1f} MWh</span>"
                f"</div></div>",
                unsafe_allow_html=True
            )

    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)


# ============ FOOTER ============
st.markdown(f"""
<div style="text-align:center; padding:10px 0 4px; border-top:1px solid rgba(0,212,255,0.08); margin-top:10px;">
  <span style="font-family:'Orbitron',sans-serif; font-size:9px; color:rgba(0,212,255,0.25); letter-spacing:2px;">
    ACIBADEM ENERJİ YÖNETİM SİSTEMİ &nbsp;·&nbsp; {now.strftime('%d.%m.%Y %H:%M')}
  </span>
</div>
""", unsafe_allow_html=True)

# ============ AYARLAR ============
with st.expander("⚙️  Ayarlar", expanded=False):
    st.markdown('<div class="sec">⚙️ SİSTEM AYARLARI</div>', unsafe_allow_html=True)

    ayar_tab1, ayar_tab2, ayar_tab3, ayar_tab4 = st.tabs(["🔗 Bağlantı", "📦 Güncellemeler", "🏥 Hastaneler", "📐 Alan (m²)"])

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
                            border-radius:8px; border:1px solid rgba(0,212,255,0.1);
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
                # Supabase başarısız olursa local dosyaya yaz
                cfg_yeni = config.copy()
                cfg_yeni["m2_degerler"] = {k: int(v) for k, v in yeni_m2.items()}
                os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
                with open(CONFIG_FILE, "w", encoding="utf-8") as f:
                    json.dump(cfg_yeni, f, indent=2, ensure_ascii=False)
                st.warning(f"⚠️ Supabase'e yazılamadı, local kaydedildi: {ex}")
