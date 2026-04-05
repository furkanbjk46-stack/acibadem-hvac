# app_merkez.py
# Acıbadem Genel Merkez — Tek Sayfa Komuta Merkezi
# Harita ortada, widget'lar etrafında — Koyu Mavi / Neon

from __future__ import annotations
import os, json
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
[data-testid="stHeader"]       { background: transparent !important; }
[data-testid="stSidebar"]      { display: none !important; }
[data-testid="stToolbar"]      { display: none !important; }
.block-container { padding: 0.5rem 1.5rem 1rem 1.5rem !important; max-width: 100% !important; }

/* Tüm yazılar */
h1,h2,h3,h4,h5,h6 { color: #e0f2fe !important; font-family: 'Orbitron', sans-serif !important; }
p, span, div, label { color: rgba(200,230,255,0.85) !important; font-family: 'Inter', sans-serif !important; }

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

.btn-refresh button {
    background: linear-gradient(135deg,#003d80,#0066cc) !important;
    color: #fff !important; border: 1px solid rgba(0,212,255,0.4) !important;
    border-radius: 8px !important; font-size: 11px !important;
    padding: 4px 12px !important; font-family:'Inter',sans-serif !important;
}
</style>
""", unsafe_allow_html=True)

# ============ SABİT VERİ ============
HASTANELER = {
    "maslak":     {"isim": "Acıbadem Maslak",     "kisa": "MASLAK",     "lat": 41.1073, "lon": 29.0228, "m2": 15000, "renk": "#00d4ff"},
    "altunizade": {"isim": "Acıbadem Altunizade", "kisa": "ALTUNİZADE", "lat": 41.0215, "lon": 29.0663, "m2": 10000, "renk": "#f59e0b"},
    "kozyatagi":  {"isim": "Acıbadem Kozyatağı",  "kisa": "KOZYATAĞİ", "lat": 40.9872, "lon": 29.1035, "m2": 12000, "renk": "#10b981"},
    "taksim":     {"isim": "Acıbadem Taksim",      "kisa": "TAKSİM",     "lat": 41.0370, "lon": 28.9850, "m2": 8000,  "renk": "#a855f7"},
}

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "configs", "merkez_config.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def hex_rgba(h, a=0.1):
    h = h.lstrip("#")
    r,g,b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
    return f"rgba({r},{g},{b},{a})"

@st.cache_data(ttl=120, show_spinner=False)
def fetch_energy(url, key):
    try:
        from supabase import create_client
        c = create_client(url, key)
        r = c.table("energy_data").select("*").order("Tarih", desc=False).execute()
        if r.data:
            df = pd.DataFrame(r.data)
            if "Tarih" in df.columns:
                df["Tarih"] = pd.to_datetime(df["Tarih"], errors="coerce")
            for col in df.columns:
                if col not in ["id","lokasyon_id","Tarih","Kar_Eritme_Aktif"]:
                    df[col] = pd.to_numeric(df[col], errors="coerce")
            return df, None
    except Exception as e:
        return pd.DataFrame(), str(e)
    return pd.DataFrame(), None

@st.cache_data(ttl=30, show_spinner=False)
def fetch_lokasyonlar(url, key):
    try:
        from supabase import create_client
        c = create_client(url, key)
        r = c.table("lokasyonlar").select("*").execute()
        return r.data or []
    except:
        return []

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

now  = datetime.now()
dun  = (now - timedelta(days=1)).strftime("%Y-%m-%d")

# ============ HEADER ============
st.markdown("""
<div style="text-align:center; padding:12px 0 8px;">
  <div style="font-family:'Orbitron',sans-serif; font-size:9px; color:rgba(0,212,255,0.45); letter-spacing:5px; text-transform:uppercase;">ACIBADEM SAĞLIK GRUBU</div>
  <div style="font-family:'Orbitron',sans-serif; font-size:20px; font-weight:900; color:#00d4ff;
              text-shadow:0 0 35px rgba(0,212,255,0.8); letter-spacing:4px; text-transform:uppercase; line-height:1.3;">
    ENERJİ &amp; HVAC KOMUTA MERKEZİ
  </div>
  <div style="font-family:'Inter',sans-serif; font-size:10px; color:rgba(150,210,255,0.4); letter-spacing:2px; margin-top:2px;">
    GENEL MERKEZ — CANLI İZLEME
  </div>
</div>
""", unsafe_allow_html=True)

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
    d = df_all[(df_all["lokasyon_id"]==lok_id) & (df_all["Tarih"].dt.strftime("%Y-%m-%d")==dun)]
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
    for lok_id, lok_info in HASTANELER.items():
        online, fark_dk = online_bilgi(lok_id)
        kwh      = dun_kwh(lok_id)
        renk     = lok_info["renk"]
        spark    = son7_kwh(lok_id)
        if fark_dk is None:
            card_cls   = "nk nk-gray"
            durum_renk = "#6b7280"
            durum_lbl  = "KURULMADI"
            dot_shadow = ""
        elif online:
            card_cls   = "nk nk-green"
            durum_renk = "#10b981"
            durum_lbl  = "ÇEVRİMİÇİ"
            dot_shadow = f"box-shadow:0 0 8px {durum_renk},0 0 16px {durum_renk};"
        else:
            card_cls   = "nk nk-red"
            durum_renk = "#ef4444"
            durum_lbl  = "ÇEVRİMDIŞI"
            dot_shadow = f"box-shadow:0 0 8px {durum_renk};"

        kwh_str  = f"{kwh:,.0f}" if kwh else "—"

        # kWh/m² hesapla
        m2 = lok_info.get("m2", 10000)
        verim_str = f"{kwh/m2:.2f}" if kwh else "—"

        rr = int(renk[1:3],16); rg = int(renk[3:5],16); rb = int(renk[5:7],16)
        dr = int(durum_renk[1:3],16); dg = int(durum_renk[3:5],16); db = int(durum_renk[5:7],16)

        kart_html = (
            f'<div class="{card_cls}" style="padding:14px;">'
            f'<div style="display:flex;align-items:center;gap:14px;">'
            f'<div style="position:relative;width:68px;height:68px;flex-shrink:0;display:flex;align-items:center;justify-content:center;">'
            f'<div style="position:absolute;top:-6px;left:-6px;right:-6px;bottom:-6px;border-radius:50%;'
            f'background:radial-gradient(circle,rgba({rr},{rg},{rb},0.25) 0%,rgba({rr},{rg},{rb},0.06) 50%,transparent 75%);'
            f'animation:breathe-ring 3s ease-in-out infinite;"></div>'
            f'<div style="position:absolute;top:-14px;left:-14px;right:-14px;bottom:-14px;border-radius:50%;'
            f'background:radial-gradient(circle,rgba({rr},{rg},{rb},0.10) 0%,transparent 65%);'
            f'animation:breathe-ring 3s ease-in-out infinite;animation-delay:0.5s;"></div>'
            f'<div style="font-size:42px;line-height:1;position:relative;z-index:1;'
            f'filter:drop-shadow(0 0 10px rgba({rr},{rg},{rb},0.8));">🏥</div>'
            f'<div style="position:absolute;top:4px;right:4px;z-index:2;width:13px;height:13px;'
            f'border-radius:50%;background:rgba({dr},{dg},{db},1);border:2px solid #020b18;'
            f'box-shadow:0 0 6px rgba({dr},{dg},{db},0.9),0 0 14px rgba({dr},{dg},{db},0.5);'
            f'animation:breathe-ring 2.4s ease-in-out infinite;"></div>'
            f'</div>'
            f'<div style="flex:1;min-width:0;">'
            f'<div style="font-family:Orbitron,sans-serif;font-size:11px;font-weight:700;'
            f'color:{renk};letter-spacing:2px;text-shadow:0 0 8px rgba({rr},{rg},{rb},0.7);'
            f'margin-bottom:2px;">{lok_info["kisa"]}</div>'
            f'<div style="font-size:9px;color:{durum_renk};font-weight:600;margin-bottom:8px;">{durum_lbl}</div>'
            f'<div style="font-size:8px;color:rgba(150,210,255,0.4);text-transform:uppercase;'
            f'letter-spacing:1px;margin-bottom:2px;">Günlük Tüketim</div>'
            f'<div style="font-family:Orbitron,sans-serif;font-size:18px;font-weight:900;'
            f'color:{renk};text-shadow:0 0 12px rgba({rr},{rg},{rb},0.7);line-height:1;margin-bottom:8px;">'
            f'{kwh_str}<span style="font-size:9px;color:rgba(150,210,255,0.5);margin-left:3px;">kWh</span></div>'
            f'<div style="display:inline-flex;align-items:center;gap:6px;'
            f'background:rgba(0,212,255,0.06);border-radius:6px;padding:4px 10px;'
            f'border:1px solid rgba(0,212,255,0.12);">'
            f'<span style="font-size:8px;color:rgba(150,210,255,0.45);text-transform:uppercase;letter-spacing:1px;">kWh/m²</span>'
            f'<span style="font-family:Orbitron,sans-serif;font-size:12px;color:#00d4ff;font-weight:700;">{verim_str}</span>'
            f'</div>'
            f'</div>'
            f'</div>'
            f'</div>'
        )
        st.markdown(kart_html, unsafe_allow_html=True)

    st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)

    # ── Global Özet ──
    st.markdown('<div class="sec">⚡ GLOBAL ÖZET (30G)</div>', unsafe_allow_html=True)
    if not df_all.empty:
        son30 = df_all[df_all["Tarih"] >= (now - timedelta(days=30))]
        ozet = {
            "⚡ Toplam Enerji": f"{son30['Toplam_Hastane_Tuketim_kWh'].sum()/1000:,.0f} MWh" if "Toplam_Hastane_Tuketim_kWh" in son30 else "—",
            "🔥 Doğalgaz": f"{(son30.get('Kazan_Dogalgaz_m3', pd.Series([0])).sum() + son30.get('Kojen_Dogalgaz_m3', pd.Series([0])).sum()):,.0f} m³",
            "❄️ Soğutma": f"{son30['Toplam_Sogutma_Tuketim_kWh'].sum()/1000:,.0f} MWh" if "Toplam_Sogutma_Tuketim_kWh" in son30 else "—",
            "💧 Su": f"{son30['Su_Tuketimi_m3'].sum():,.0f} m³" if "Su_Tuketimi_m3" in son30 else "—",
            "⚙️ Kojen Üretim": f"{son30['Kojen_Uretim_kWh'].sum()/1000:,.0f} MWh" if "Kojen_Uretim_kWh" in son30 else "—",
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
    # Harita verisi
    harita_data = []
    for lok_id, lok_info in HASTANELER.items():
        online, fark_dk = online_bilgi(lok_id)
        kwh = dun_kwh(lok_id)
        harita_data.append({
            "isim": lok_info["isim"],
            "lat": lok_info["lat"],
            "lon": lok_info["lon"],
            "durum": "Çevrimiçi" if online else ("Kurulmadı" if fark_dk is None else "Çevrimdışı"),
            "kwh": int(kwh),
            "m2": lok_info["m2"],
            "renk": "#10b981" if online else ("#6b7280" if fark_dk is None else "#ef4444"),
            "boyut": max(14, min(38, kwh/900)) if kwh > 0 else 14,
        })
    hdf = pd.DataFrame(harita_data)

    fig_map = go.Figure()
    fig_map.add_trace(go.Scattermapbox(
        lat=hdf["lat"], lon=hdf["lon"],
        mode="markers+text",
        marker=dict(size=hdf["boyut"], color=hdf["renk"], opacity=0.92),
        text=hdf["isim"],
        textposition="top center",
        textfont=dict(color="white", size=11, family="Orbitron"),
        customdata=hdf[["durum","kwh","m2"]].values,
        hovertemplate="<b>%{text}</b><br>Durum: %{customdata[0]}<br>Dün: %{customdata[1]:,} kWh<br>Alan: %{customdata[2]:,} m²<extra></extra>",
        name="",
    ))
    # Glow efekti için büyük şeffaf daire
    fig_map.add_trace(go.Scattermapbox(
        lat=hdf["lat"], lon=hdf["lon"],
        mode="markers",
        marker=dict(size=hdf["boyut"]*2.5, color=hdf["renk"], opacity=0.15),
        hoverinfo="skip", showlegend=False,
    ))

    fig_map.update_layout(
        mapbox=dict(
            style="carto-darkmatter",
            center=dict(lat=41.05, lon=29.02),
            zoom=10.8,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=0, b=0, l=0, r=0),
        height=480,
        showlegend=False,
    )

    st.markdown('<div class="sec">🗺️ HASTANE AĞI — İSTANBUL</div>', unsafe_allow_html=True)
    st.plotly_chart(fig_map, use_container_width=True, config={"displayModeBar": False})

    # ── Harita altı: Chiller Set vs Dış Hava ──
    st.markdown('<div class="sec">🌡️ CHİLLER SET vs DIŞ HAVA (60G)</div>', unsafe_allow_html=True)
    if not df_all.empty and "Chiller_Set_Temp_C" in df_all.columns:
        son60 = df_all[df_all["Tarih"] >= (now - timedelta(days=60))].copy()
        fig_ch = go.Figure()
        fig_ch.add_trace(go.Scatter(
            x=son60["Tarih"], y=son60["Dis_Hava_Sicakligi_C"],
            name="Dış Hava", line=dict(color="#f59e0b", width=1.5, dash="dot"),
            yaxis="y2", mode="lines",
        ))
        for lok_id in son60["lokasyon_id"].unique():
            ld = son60[son60["lokasyon_id"]==lok_id]
            renk = HASTANELER.get(lok_id, {}).get("renk", "#00d4ff")
            fig_ch.add_trace(go.Scatter(
                x=ld["Tarih"], y=ld["Chiller_Set_Temp_C"],
                name=HASTANELER.get(lok_id,{}).get("kisa", lok_id),
                line=dict(color=renk, width=2), mode="lines",
                fill="tozeroy", fillcolor=hex_rgba(renk, 0.07),
            ))
        fig_ch.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#a0c8ff", family="Inter"),
            margin=dict(t=10,b=20,l=40,r=40), height=200,
            xaxis=dict(gridcolor="rgba(0,212,255,0.07)", showgrid=True),
            yaxis=dict(title=dict(text="Set °C", font=dict(size=10)), gridcolor="rgba(0,212,255,0.07)"),
            yaxis2=dict(title=dict(text="Dış Hava °C", font=dict(size=10)), overlaying="y", side="right"),
            legend=dict(orientation="h", y=1.15, font=dict(size=10)),
        )
        st.plotly_chart(fig_ch, use_container_width=True, config={"displayModeBar": False})

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

    # Tüm uyarıları sıralı göster
    tum_uyarilar = []
    for lok_id in sirali_loklar:
        tum_uyarilar.extend(lok_uyari_map.get(lok_id, []))

    if not tum_uyarilar:
        st.markdown('<div class="alrt-g">✅ Tüm sistemler normal</div>', unsafe_allow_html=True)
    else:
        for sev, msg in tum_uyarilar[:10]:
            st.markdown(f'<div class="alrt-{sev}">{msg}</div>', unsafe_allow_html=True)

    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)

    # ── Benchmark (kWh/m²) ──
    st.markdown('<div class="sec">🏆 VERİMLİLİK (kWh/m²)</div>', unsafe_allow_html=True)
    if not df_all.empty and "Toplam_Hastane_Tuketim_kWh" in df_all.columns:
        son30 = df_all[df_all["Tarih"] >= (now - timedelta(days=30))]
        bench_rows = []
        for lok_id in aktif_loklar:
            ld = son30[son30["lokasyon_id"]==lok_id]
            if ld.empty: continue
            toplam = ld["Toplam_Hastane_Tuketim_kWh"].sum()
            m2 = HASTANELER.get(lok_id,{}).get("m2",10000)
            bench_rows.append({
                "isim": HASTANELER.get(lok_id,{}).get("kisa", lok_id),
                "kwh_m2": toplam / m2,
                "renk": HASTANELER.get(lok_id,{}).get("renk","#00d4ff"),
            })
        if bench_rows:
            bench_rows.sort(key=lambda x: x["kwh_m2"])
            max_val = max(r["kwh_m2"] for r in bench_rows)
            for i, row in enumerate(bench_rows):
                pct = row["kwh_m2"] / max_val * 100
                medal = "🥇" if i == 0 else ("🥈" if i == 1 else "🥉")
                st.markdown(f"""
                <div style="margin-bottom:8px;">
                  <div style="display:flex; justify-content:space-between; margin-bottom:3px;">
                    <span style="font-size:11px; color:rgba(200,230,255,0.8);">{medal} {row['isim']}</span>
                    <span style="font-size:11px; font-weight:700; color:{row['renk']}; font-family:'Orbitron',sans-serif;">{row['kwh_m2']:.1f}</span>
                  </div>
                  <div style="height:5px; background:rgba(0,212,255,0.1); border-radius:3px;">
                    <div style="height:5px; width:{pct:.0f}%; background:{row['renk']}; border-radius:3px; box-shadow:0 0 8px {row['renk']};"></div>
                  </div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.markdown('<div class="alrt-y">📡 Veri bekleniyor...</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="alrt-y">📡 Sunucu bağlantısı kurulamadı</div>', unsafe_allow_html=True)

    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)

    # ── 30 Günlük Trend Mini ──
    st.markdown('<div class="sec">📈 30G ENERJİ TRENDİ</div>', unsafe_allow_html=True)
    if df_all.empty or "Toplam_Hastane_Tuketim_kWh" not in df_all.columns:
        st.markdown('<div class="alrt-y">📡 Sunucu bağlantısı kurulamadı</div>', unsafe_allow_html=True)
    elif not df_all.empty and "Toplam_Hastane_Tuketim_kWh" in df_all.columns:
        trend = df_all[df_all["Tarih"] >= (now - timedelta(days=30))].copy()
        fig_mini = go.Figure()
        for lok_id in trend["lokasyon_id"].unique():
            ld = trend[trend["lokasyon_id"]==lok_id]
            renk = HASTANELER.get(lok_id,{}).get("renk","#00d4ff")
            fig_mini.add_trace(go.Scatter(
                x=ld["Tarih"], y=ld["Toplam_Hastane_Tuketim_kWh"],
                name=HASTANELER.get(lok_id,{}).get("kisa", lok_id),
                line=dict(color=renk, width=1.5),
                fill="tozeroy", fillcolor=hex_rgba(renk, 0.07),
                mode="lines",
            ))
        fig_mini.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#a0c8ff", size=9, family="Inter"),
            margin=dict(t=5,b=20,l=30,r=5), height=160,
            xaxis=dict(gridcolor="rgba(0,212,255,0.06)", showticklabels=True, tickfont=dict(size=8)),
            yaxis=dict(gridcolor="rgba(0,212,255,0.06)", tickfont=dict(size=8)),
            legend=dict(orientation="h", y=1.2, font=dict(size=9)),
            showlegend=True,
        )
        st.plotly_chart(fig_mini, use_container_width=True, config={"displayModeBar": False})

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

    ayar_tab1, ayar_tab2, ayar_tab3 = st.tabs(["🔗 Bağlantı", "📦 Güncellemeler", "🏥 Hastaneler"])

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
