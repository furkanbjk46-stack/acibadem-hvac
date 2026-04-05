# app_merkez.py
# Acıbadem Genel Merkez — Enerji & HVAC Komuta Merkezi
# Koyu Mavi / Neon Tasarım

from __future__ import annotations
import os, sys, json
import streamlit as st
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Acıbadem GM — Enerji Komuta Merkezi",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# ============ TEMA / CSS ============
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Orbitron:wght@400;700;900&family=Inter:wght@300;400;600;700&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    background: #020b18 !important;
}
[data-testid="stAppViewContainer"] {
    background: radial-gradient(ellipse at 20% 50%, #0a1628 0%, #020b18 60%, #050d1f 100%) !important;
}
[data-testid="stHeader"] { background: transparent !important; }
[data-testid="stSidebar"] { background: #020b18 !important; }

/* Genel metin */
h1,h2,h3,h4,h5,h6 { color: #e0f2fe !important; font-family: 'Orbitron', sans-serif !important; }
p, span, div, label { color: rgba(200,230,255,0.85) !important; font-family: 'Inter', sans-serif !important; }

/* Metrik kartlar */
[data-testid="stMetricValue"] { color: #00d4ff !important; font-size: 26px !important; font-weight: 800 !important; font-family: 'Orbitron', sans-serif !important; text-shadow: 0 0 20px rgba(0,212,255,0.6) !important; }
[data-testid="stMetricLabel"] { color: rgba(150,210,255,0.8) !important; font-size: 11px !important; letter-spacing: 1px !important; text-transform: uppercase !important; }
[data-testid="stMetricDelta"] { color: #10b981 !important; }
[data-testid="metric-container"] {
    background: linear-gradient(135deg, rgba(0,30,60,0.8), rgba(0,15,40,0.9)) !important;
    border: 1px solid rgba(0,212,255,0.25) !important;
    border-radius: 14px !important;
    padding: 16px !important;
    box-shadow: 0 0 20px rgba(0,212,255,0.08), inset 0 1px 0 rgba(255,255,255,0.05) !important;
}

/* Tab stili */
[data-baseweb="tab-list"] {
    background: rgba(0,20,50,0.6) !important;
    border-radius: 12px !important;
    padding: 6px !important;
    border: 1px solid rgba(0,212,255,0.15) !important;
    gap: 4px !important;
}
[data-baseweb="tab"] {
    background: transparent !important;
    color: rgba(150,210,255,0.7) !important;
    border-radius: 8px !important;
    font-family: 'Inter', sans-serif !important;
    font-weight: 600 !important;
    font-size: 13px !important;
}
[aria-selected="true"] {
    background: linear-gradient(135deg, rgba(0,100,200,0.4), rgba(0,212,255,0.2)) !important;
    color: #00d4ff !important;
    box-shadow: 0 0 12px rgba(0,212,255,0.3) !important;
}
[data-baseweb="tab-panel"] {
    background: rgba(0,15,40,0.4) !important;
    border-radius: 16px !important;
    border: 1px solid rgba(0,212,255,0.1) !important;
    padding: 20px !important;
}

/* Buton */
.stButton > button {
    background: linear-gradient(135deg, #0066cc, #00d4ff) !important;
    color: #000 !important; font-weight: 700 !important;
    border: none !important; border-radius: 10px !important;
    box-shadow: 0 0 15px rgba(0,212,255,0.4) !important;
}
.stButton > button:hover { transform: translateY(-2px) !important; box-shadow: 0 0 25px rgba(0,212,255,0.6) !important; }

/* Select / input */
[data-baseweb="select"] { background: rgba(0,20,50,0.8) !important; border: 1px solid rgba(0,212,255,0.3) !important; border-radius: 8px !important; }

/* Scrollbar */
::-webkit-scrollbar { width: 4px; }
::-webkit-scrollbar-track { background: #020b18; }
::-webkit-scrollbar-thumb { background: rgba(0,212,255,0.3); border-radius: 4px; }

.neon-card {
    background: linear-gradient(135deg, rgba(0,30,70,0.85), rgba(0,15,45,0.95));
    border: 1px solid rgba(0,212,255,0.25);
    border-radius: 16px;
    padding: 20px;
    margin-bottom: 12px;
    box-shadow: 0 0 25px rgba(0,212,255,0.08), inset 0 1px 0 rgba(255,255,255,0.04);
}
.neon-card-online {
    border-color: rgba(16,185,129,0.5) !important;
    box-shadow: 0 0 20px rgba(16,185,129,0.1) !important;
}
.neon-card-offline {
    border-color: rgba(239,68,68,0.5) !important;
    box-shadow: 0 0 20px rgba(239,68,68,0.1) !important;
}
.header-title {
    font-family: 'Orbitron', sans-serif;
    font-size: 22px;
    font-weight: 900;
    color: #00d4ff;
    text-shadow: 0 0 30px rgba(0,212,255,0.7);
    letter-spacing: 3px;
    text-transform: uppercase;
}
.header-sub {
    font-family: 'Inter', sans-serif;
    font-size: 12px;
    color: rgba(150,210,255,0.6);
    letter-spacing: 2px;
    text-transform: uppercase;
}
.alert-red {
    background: linear-gradient(135deg, rgba(239,68,68,0.15), rgba(220,38,38,0.08));
    border: 1px solid rgba(239,68,68,0.4);
    border-radius: 10px; padding: 10px 14px; margin: 4px 0;
    color: #fca5a5 !important;
    font-size: 13px;
}
.alert-yellow {
    background: linear-gradient(135deg, rgba(245,158,11,0.15), rgba(217,119,6,0.08));
    border: 1px solid rgba(245,158,11,0.4);
    border-radius: 10px; padding: 10px 14px; margin: 4px 0;
    color: #fcd34d !important;
    font-size: 13px;
}
.alert-green {
    background: linear-gradient(135deg, rgba(16,185,129,0.15), rgba(5,150,105,0.08));
    border: 1px solid rgba(16,185,129,0.4);
    border-radius: 10px; padding: 10px 14px; margin: 4px 0;
    color: #6ee7b7 !important;
    font-size: 13px;
}
.section-title {
    font-family: 'Orbitron', sans-serif;
    font-size: 13px;
    color: rgba(0,212,255,0.8);
    letter-spacing: 2px;
    text-transform: uppercase;
    border-bottom: 1px solid rgba(0,212,255,0.2);
    padding-bottom: 6px;
    margin-bottom: 14px;
}
</style>
""", unsafe_allow_html=True)

# ============ CONFIG ============
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "configs", "merkez_config.json")

HASTANELER = {
    "maslak":      {"isim": "Acıbadem Maslak",      "lat": 41.1073, "lon": 29.0228, "m2": 15000, "renk": "#00d4ff"},
    "altunizade":  {"isim": "Acıbadem Altunizade",  "lat": 41.0215, "lon": 29.0663, "m2": 10000, "renk": "#f59e0b"},
    "kozyatagi":   {"isim": "Acıbadem Kozyatağı",   "lat": 40.9872, "lon": 29.1035, "m2": 12000, "renk": "#10b981"},
    "taksim":      {"isim": "Acıbadem Taksim",       "lat": 41.0370, "lon": 28.9850, "m2": 8000,  "renk": "#a855f7"},
}

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

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
            num_cols = [col for col in df.columns if col not in ["id","lokasyon_id","Tarih","Kar_Eritme_Aktif"]]
            for col in num_cols:
                df[col] = pd.to_numeric(df[col], errors="coerce")
            return df
    except Exception as e:
        st.error(f"Veri hatası: {e}")
    return pd.DataFrame()

@st.cache_data(ttl=30, show_spinner=False)
def fetch_lokasyonlar(url, key):
    try:
        from supabase import create_client
        c = create_client(url, key)
        r = c.table("lokasyonlar").select("*").execute()
        return r.data or []
    except:
        return []

def plotly_cfg():
    return dict(paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color="#a0c8ff", family="Inter"), margin=dict(t=30,b=30,l=40,r=20))

# ============ BAĞLANTI ============
config = load_config()
url = config.get("supabase_url","")
key = config.get("supabase_key","")
bagli = bool(url and "BURAYA" not in url)

# ============ HEADER ============
st.markdown("""
<div style="text-align:center; padding: 20px 0 10px 0;">
    <div style="font-family:'Orbitron',sans-serif; font-size:11px; color:rgba(0,212,255,0.5); letter-spacing:4px; text-transform:uppercase; margin-bottom:6px;">
        ACIBADEM SAĞLIK GRUBU
    </div>
    <div style="font-family:'Orbitron',sans-serif; font-size:24px; font-weight:900; color:#00d4ff;
                text-shadow: 0 0 40px rgba(0,212,255,0.8); letter-spacing:4px; text-transform:uppercase;">
        ENERJİ & HVAC KOMUTA MERKEZİ
    </div>
    <div style="font-family:'Inter',sans-serif; font-size:11px; color:rgba(150,210,255,0.5); letter-spacing:2px; margin-top:4px;">
        GENEL MERKEZ — CANLI İZLEME PANELİ
    </div>
</div>
""", unsafe_allow_html=True)

if not bagli:
    st.error("⚠️ Supabase bağlantısı yok. merkez_config.json dosyasını kontrol edin.")
    st.stop()

df_all = fetch_energy(url, key)
lokasyonlar = fetch_lokasyonlar(url, key)
lok_dict = {l["lokasyon_id"]: l for l in lokasyonlar}

# Aktif lokasyon listesi (veri olanlar)
aktif_loklar = df_all["lokasyon_id"].unique().tolist() if not df_all.empty else []

# ============ TABS ============
tabs = st.tabs([
    "🏠 Genel Bakış",
    "⚡ Enerji Analizi",
    "🌡️ HVAC & Chiller",
    "📊 Benchmark",
    "🗺️ Türkiye Haritası",
    "📦 Güncellemeler",
])

# ============================================================
# TAB 1 — GENEL BAKIŞ
# ============================================================
with tabs[0]:

    now = datetime.now()

    # Dünün verisi
    dun = (now - timedelta(days=1)).strftime("%Y-%m-%d")
    bugun = now.strftime("%Y-%m-%d")

    # ── DURUM SATIRI ──
    st.markdown('<div class="section-title">🟢 LOKASYON DURUMU</div>', unsafe_allow_html=True)

    lok_cols = st.columns(len(HASTANELER))
    for i, (lok_id, lok_info) in enumerate(HASTANELER.items()):
        with lok_cols[i]:
            lok_data = lok_dict.get(lok_id, {})
            ping_str = str(lok_data.get("ping_zamani") or "").strip()
            online = False
            ping_ago = "—"
            if ping_str and ping_str not in ("None",""):
                try:
                    ping_dt = pd.to_datetime(ping_str).tz_localize(None)
                    fark = (now - ping_dt).total_seconds() / 60
                    online = fark < 10
                    ping_ago = f"{int(fark)}dk önce" if fark < 60 else f"{int(fark/60)}sa önce"
                except:
                    pass

            # Dünkü tüketim
            dun_kwh = "—"
            if not df_all.empty and lok_id in aktif_loklar:
                dun_df = df_all[(df_all["lokasyon_id"]==lok_id) & (df_all["Tarih"].dt.strftime("%Y-%m-%d")==dun)]
                if not dun_df.empty and "Toplam_Hastane_Tuketim_kWh" in dun_df.columns:
                    val = dun_df["Toplam_Hastane_Tuketim_kWh"].sum()
                    dun_kwh = f"{val:,.0f}"

            renk = lok_info["renk"]
            durum_icon = "🟢" if online else "🔴"
            durum_text = "ÇEVRİMİÇİ" if online else "ÇEVRİMDIŞI"
            card_class = "neon-card neon-card-online" if online else "neon-card neon-card-offline"

            st.markdown(f"""
            <div class="{card_class}">
                <div style="font-family:'Orbitron',sans-serif; font-size:11px; color:{renk}; letter-spacing:1px; margin-bottom:8px;">{lok_info['isim'].upper()}</div>
                <div style="font-size:22px; font-weight:900; color:{renk}; text-shadow:0 0 15px {renk}88; font-family:'Orbitron',sans-serif;">{dun_kwh} <span style="font-size:11px; color:rgba(150,210,255,0.6);">kWh</span></div>
                <div style="font-size:10px; color:rgba(150,210,255,0.5); margin-top:2px;">Dünkü Tüketim</div>
                <div style="margin-top:10px; font-size:11px;">{durum_icon} <span style="color:{'#10b981' if online else '#ef4444'}; font-weight:700;">{durum_text}</span></div>
                <div style="font-size:10px; color:rgba(150,210,255,0.4);">Son sinyal: {ping_ago}</div>
            </div>
            """, unsafe_allow_html=True)

    st.markdown("---")

    # ── GLOBAL ÖZET METRİKLER ──
    st.markdown('<div class="section-title">⚡ GLOBAL TÜKETİM ÖZETİ</div>', unsafe_allow_html=True)

    if not df_all.empty:
        son30 = df_all[df_all["Tarih"] >= (now - timedelta(days=30))]
        m1, m2, m3, m4, m5 = st.columns(5)

        toplam_kwh = son30["Toplam_Hastane_Tuketim_kWh"].sum() if "Toplam_Hastane_Tuketim_kWh" in son30 else 0
        toplam_gaz = son30["Kazan_Dogalgaz_m3"].sum() + son30["Kojen_Dogalgaz_m3"].sum() if "Kazan_Dogalgaz_m3" in son30 else 0
        toplam_su = son30["Su_Tuketimi_m3"].sum() if "Su_Tuketimi_m3" in son30 else 0
        toplam_sogutma = son30["Toplam_Sogutma_Tuketim_kWh"].sum() if "Toplam_Sogutma_Tuketim_kWh" in son30 else 0
        kojen_uretim = son30["Kojen_Uretim_kWh"].sum() if "Kojen_Uretim_kWh" in son30 else 0

        with m1: st.metric("⚡ Toplam Enerji (30g)", f"{toplam_kwh/1000:,.0f} MWh")
        with m2: st.metric("🔥 Doğalgaz (30g)", f"{toplam_gaz:,.0f} m³")
        with m3: st.metric("❄️ Soğutma (30g)", f"{toplam_sogutma/1000:,.0f} MWh")
        with m4: st.metric("💧 Su (30g)", f"{toplam_su:,.0f} m³")
        with m5: st.metric("⚙️ Kojen Üretim (30g)", f"{kojen_uretim/1000:,.0f} MWh")

    st.markdown("---")

    # ── GÜNLÜK TREND GRAFİĞİ + UYARILAR ──
    col_grafik, col_uyari = st.columns([3, 1])

    with col_grafik:
        st.markdown('<div class="section-title">📈 30 GÜNLÜK ENERJİ TRENDİ</div>', unsafe_allow_html=True)
        if not df_all.empty and "Toplam_Hastane_Tuketim_kWh" in df_all.columns:
            trend_df = df_all[df_all["Tarih"] >= (now - timedelta(days=30))].copy()
            trend_df["Lokasyon"] = trend_df["lokasyon_id"].map(
                lambda x: HASTANELER.get(x, {}).get("isim", x))

            fig_trend = go.Figure()
            renkler = ["#00d4ff", "#f59e0b", "#10b981", "#a855f7"]
            for idx, lok_id in enumerate(trend_df["lokasyon_id"].unique()):
                lok_data_t = trend_df[trend_df["lokasyon_id"]==lok_id]
                renk = HASTANELER.get(lok_id, {}).get("renk", renkler[idx % len(renkler)])
                fig_trend.add_trace(go.Scatter(
                    x=lok_data_t["Tarih"], y=lok_data_t["Toplam_Hastane_Tuketim_kWh"],
                    name=HASTANELER.get(lok_id, {}).get("isim", lok_id),
                    line=dict(color=renk, width=2),
                    fill="tozeroy", fillcolor=f"{renk}15",
                    mode="lines",
                ))
            fig_trend.update_layout(**plotly_cfg(), height=280,
                xaxis=dict(gridcolor="rgba(0,212,255,0.08)", showgrid=True),
                yaxis=dict(gridcolor="rgba(0,212,255,0.08)", showgrid=True, title="kWh"),
                legend=dict(orientation="h", y=1.1, font=dict(color="#a0c8ff")),
            )
            st.plotly_chart(fig_trend, use_container_width=True)

    with col_uyari:
        st.markdown('<div class="section-title">🚨 CANLI UYARILAR</div>', unsafe_allow_html=True)
        uyarilar = []

        if not df_all.empty:
            son_gun = df_all[df_all["Tarih"].dt.strftime("%Y-%m-%d") == dun]
            for lok_id in aktif_loklar:
                lok_son = son_gun[son_gun["lokasyon_id"]==lok_id]
                isim = HASTANELER.get(lok_id, {}).get("isim", lok_id)
                if lok_son.empty:
                    uyarilar.append(("red", f"⚠️ {isim}: Bugün veri yok"))
                    continue
                if "Chiller_Set_Temp_C" in lok_son.columns:
                    cs = lok_son["Chiller_Set_Temp_C"].mean()
                    if pd.notna(cs) and cs > 9:
                        uyarilar.append(("yellow", f"🌡️ {isim}: Chiller set yüksek ({cs:.1f}°C)"))
                    elif pd.notna(cs) and cs < 6:
                        uyarilar.append(("yellow", f"❄️ {isim}: Chiller set düşük ({cs:.1f}°C)"))
                if "Chiller_Load_Percent" in lok_son.columns:
                    cl = lok_son["Chiller_Load_Percent"].mean()
                    if pd.notna(cl) and cl > 90:
                        uyarilar.append(("red", f"🔥 {isim}: Chiller yük kritik (%{cl:.0f})"))

            # Offline uyarı
            for lok_id, lok_info in HASTANELER.items():
                if lok_id in lok_dict:
                    ping_str = str(lok_dict[lok_id].get("ping_zamani") or "").strip()
                    if ping_str and ping_str not in ("None",""):
                        try:
                            ping_dt = pd.to_datetime(ping_str).tz_localize(None)
                            fark = (now - ping_dt).total_seconds() / 60
                            if fark > 10:
                                uyarilar.append(("red", f"🔴 {lok_info['isim']}: Çevrimdışı ({int(fark)}dk)"))
                        except:
                            pass

        if not uyarilar:
            st.markdown('<div class="alert-green">✅ Tüm sistemler normal</div>', unsafe_allow_html=True)
        else:
            for seviye, mesaj in uyarilar[:8]:
                css = f"alert-{seviye}"
                st.markdown(f'<div class="{css}">{mesaj}</div>', unsafe_allow_html=True)

# ============================================================
# TAB 2 — ENERJİ ANALİZİ
# ============================================================
with tabs[1]:
    if df_all.empty:
        st.info("Veri yok.")
    else:
        # Filtreler
        fc1, fc2, fc3 = st.columns([2, 2, 1])
        with fc1:
            lok_secim = st.multiselect("Lokasyon",
                options=aktif_loklar,
                default=aktif_loklar,
                format_func=lambda x: HASTANELER.get(x, {}).get("isim", x))
        with fc2:
            metrik = st.selectbox("Metrik", [
                "Toplam_Hastane_Tuketim_kWh", "Sebeke_Tuketim_kWh",
                "Kojen_Uretim_kWh", "Chiller_Tuketim_kWh",
                "Kazan_Dogalgaz_m3", "Su_Tuketimi_m3",
            ], format_func=lambda x: {
                "Toplam_Hastane_Tuketim_kWh": "Toplam Tüketim (kWh)",
                "Sebeke_Tuketim_kWh": "Şebeke Tüketimi (kWh)",
                "Kojen_Uretim_kWh": "Kojenerasyon Üretimi (kWh)",
                "Chiller_Tuketim_kWh": "Chiller Tüketimi (kWh)",
                "Kazan_Dogalgaz_m3": "Doğalgaz (m³)",
                "Su_Tuketimi_m3": "Su Tüketimi (m³)",
            }.get(x, x))
        with fc3:
            periyot = st.selectbox("Periyot", ["Günlük","Haftalık","Aylık"])

        df_fil = df_all[df_all["lokasyon_id"].isin(lok_secim)].copy()

        if periyot == "Haftalık":
            df_fil["Periyot"] = df_fil["Tarih"].dt.to_period("W").astype(str)
        elif periyot == "Aylık":
            df_fil["Periyot"] = df_fil["Tarih"].dt.to_period("M").astype(str)
        else:
            df_fil["Periyot"] = df_fil["Tarih"].dt.strftime("%Y-%m-%d")

        df_fil["Lokasyon"] = df_fil["lokasyon_id"].map(lambda x: HASTANELER.get(x, {}).get("isim", x))

        if metrik in df_fil.columns:
            agg = df_fil.groupby(["Periyot","Lokasyon"])[metrik].sum().reset_index()

            fig_enerji = px.bar(agg, x="Periyot", y=metrik, color="Lokasyon",
                barmode="group",
                color_discrete_map={HASTANELER[k]["isim"]: HASTANELER[k]["renk"] for k in HASTANELER},
                template="plotly_dark",
            )
            fig_enerji.update_layout(**plotly_cfg(), height=350,
                xaxis=dict(gridcolor="rgba(0,212,255,0.06)"),
                yaxis=dict(gridcolor="rgba(0,212,255,0.06)"),
                bargap=0.25, legend=dict(orientation="h", y=1.1),
            )
            st.plotly_chart(fig_enerji, use_container_width=True)

            # Özet tablo — Plotly
            ozet = agg.pivot(index="Periyot", columns="Lokasyon", values=metrik).fillna(0).reset_index()
            lok_isimleri = [c for c in ozet.columns if c != "Periyot"]
            fig_tablo = go.Figure(data=[go.Table(
                header=dict(
                    values=["<b>Periyot</b>"] + [f"<b>{c}</b>" for c in lok_isimleri],
                    fill_color="rgba(0,100,200,0.5)", font=dict(color="white", size=12),
                    align="center", height=34,
                ),
                cells=dict(
                    values=[ozet["Periyot"]] + [ozet[c].apply(lambda x: f"{x:,.0f}") for c in lok_isimleri],
                    fill_color=[["rgba(0,20,50,0.6)","rgba(0,30,70,0.4)"] * len(ozet)],
                    font=dict(color="white", size=11), align="center", height=28,
                )
            )])
            fig_tablo.update_layout(paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=5,b=5,l=0,r=0), height=300)
            st.plotly_chart(fig_tablo, use_container_width=True)

# ============================================================
# TAB 3 — HVAC & CHİLLER
# ============================================================
with tabs[2]:
    if df_all.empty:
        st.info("Veri yok.")
    else:
        son60 = df_all[df_all["Tarih"] >= (datetime.now() - timedelta(days=60))].copy()
        son60["Lokasyon"] = son60["lokasyon_id"].map(lambda x: HASTANELER.get(x, {}).get("isim", x))

        g1, g2 = st.columns(2)

        with g1:
            st.markdown('<div class="section-title">🌡️ CHİLLER SET vs DIŞ HAVA</div>', unsafe_allow_html=True)
            if "Chiller_Set_Temp_C" in son60.columns and "Dis_Hava_Sicakligi_C" in son60.columns:
                fig_ch = go.Figure()
                fig_ch.add_trace(go.Scatter(
                    x=son60["Tarih"], y=son60["Dis_Hava_Sicakligi_C"],
                    name="Dış Hava (°C)", line=dict(color="#f59e0b", width=1.5, dash="dot"),
                    yaxis="y2"
                ))
                for lok_id in son60["lokasyon_id"].unique():
                    ld = son60[son60["lokasyon_id"]==lok_id]
                    renk = HASTANELER.get(lok_id, {}).get("renk", "#00d4ff")
                    fig_ch.add_trace(go.Scatter(
                        x=ld["Tarih"], y=ld["Chiller_Set_Temp_C"],
                        name=f"Chiller Set - {HASTANELER.get(lok_id,{}).get('isim',lok_id)}",
                        line=dict(color=renk, width=2), mode="lines"
                    ))
                fig_ch.update_layout(**plotly_cfg(), height=300,
                    yaxis=dict(title="Chiller Set (°C)", gridcolor="rgba(0,212,255,0.08)"),
                    yaxis2=dict(title="Dış Hava (°C)", overlaying="y", side="right", gridcolor="rgba(0,212,255,0.04)"),
                    legend=dict(orientation="h", y=1.15, font=dict(size=10)),
                )
                st.plotly_chart(fig_ch, use_container_width=True)

        with g2:
            st.markdown('<div class="section-title">❄️ CHİLLER YÜK DAĞILIMI</div>', unsafe_allow_html=True)
            if "Chiller_Load_Percent" in son60.columns:
                fig_load = go.Figure()
                for lok_id in son60["lokasyon_id"].unique():
                    ld = son60[son60["lokasyon_id"]==lok_id]
                    renk = HASTANELER.get(lok_id, {}).get("renk", "#00d4ff")
                    fig_load.add_trace(go.Box(
                        y=ld["Chiller_Load_Percent"].dropna(),
                        name=HASTANELER.get(lok_id,{}).get("isim",lok_id),
                        marker_color=renk, line_color=renk,
                        fillcolor=f"{renk}22",
                    ))
                fig_load.update_layout(**plotly_cfg(), height=300,
                    yaxis=dict(title="Yük (%)", gridcolor="rgba(0,212,255,0.08)"),
                )
                st.plotly_chart(fig_load, use_container_width=True)

        # Chiller aylık ortalama tablo
        st.markdown('<div class="section-title">📋 HVAC AYLIK ÖZET</div>', unsafe_allow_html=True)
        son60["Ay"] = son60["Tarih"].dt.to_period("M").astype(str)
        hvac_cols = ["Chiller_Set_Temp_C","Chiller_Load_Percent","Chiller_Adet","Kazan_Adet"]
        mevcut_hvac = [c for c in hvac_cols if c in son60.columns]
        if mevcut_hvac:
            hvac_ozet = son60.groupby(["Ay","Lokasyon"])[mevcut_hvac].mean().round(1).reset_index()
            fig_hvac_t = go.Figure(data=[go.Table(
                header=dict(
                    values=["<b>Ay</b>","<b>Lokasyon</b>"] + [f"<b>{c.replace('_',' ')}</b>" for c in mevcut_hvac],
                    fill_color="rgba(0,100,200,0.5)", font=dict(color="white",size=12),
                    align="center", height=34,
                ),
                cells=dict(
                    values=[hvac_ozet["Ay"], hvac_ozet["Lokasyon"]] + [hvac_ozet[c].apply(lambda x: f"{x:.1f}") for c in mevcut_hvac],
                    fill_color=[["rgba(0,20,50,0.6)","rgba(0,30,70,0.4)"] * len(hvac_ozet)],
                    font=dict(color="white",size=11), align="center", height=28,
                )
            )])
            fig_hvac_t.update_layout(paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=5,b=5,l=0,r=0), height=320)
            st.plotly_chart(fig_hvac_t, use_container_width=True)

# ============================================================
# TAB 4 — BENCHMARK
# ============================================================
with tabs[3]:
    if df_all.empty:
        st.info("Veri yok.")
    else:
        st.markdown('<div class="section-title">🏆 LOKASYON KARŞILAŞTIRMA</div>', unsafe_allow_html=True)

        df_bench = df_all.copy()
        df_bench["Ay"] = df_bench["Tarih"].dt.to_period("M").astype(str)
        df_bench["Lokasyon"] = df_bench["lokasyon_id"].map(lambda x: HASTANELER.get(x, {}).get("isim", x))

        if "Toplam_Hastane_Tuketim_kWh" in df_bench.columns:
            monthly = df_bench.groupby(["Ay","Lokasyon","lokasyon_id"])["Toplam_Hastane_Tuketim_kWh"].sum().reset_index()
            monthly["m2"] = monthly["lokasyon_id"].map(lambda x: HASTANELER.get(x,{}).get("m2", 10000))
            monthly["kWh/m²"] = (monthly["Toplam_Hastane_Tuketim_kWh"] / monthly["m2"]).round(1)

            b1, b2 = st.columns(2)
            with b1:
                fig_b1 = px.bar(monthly, x="Ay", y="Toplam_Hastane_Tuketim_kWh", color="Lokasyon",
                    barmode="group", template="plotly_dark",
                    color_discrete_map={HASTANELER[k]["isim"]: HASTANELER[k]["renk"] for k in HASTANELER},
                    labels={"Toplam_Hastane_Tuketim_kWh": "Toplam kWh"},
                    title="Aylık Toplam Tüketim",
                )
                fig_b1.update_layout(**plotly_cfg(), height=320, title_font=dict(color="#00d4ff", size=13))
                st.plotly_chart(fig_b1, use_container_width=True)

            with b2:
                fig_b2 = px.bar(monthly, x="Ay", y="kWh/m²", color="Lokasyon",
                    barmode="group", template="plotly_dark",
                    color_discrete_map={HASTANELER[k]["isim"]: HASTANELER[k]["renk"] for k in HASTANELER},
                    title="Aylık Enerji Yoğunluğu (kWh/m²)",
                )
                fig_b2.update_layout(**plotly_cfg(), height=320, title_font=dict(color="#00d4ff", size=13))
                st.plotly_chart(fig_b2, use_container_width=True)

            # Verimlilik sıralaması — Plotly tablo
            pivot = monthly.pivot(index="Ay", columns="Lokasyon", values="kWh/m²").fillna(0).reset_index()
            lok_isimleri = [c for c in pivot.columns if c != "Ay"]
            if len(lok_isimleri) >= 2:
                pivot["En Verimli"] = pivot[lok_isimleri].idxmin(axis=1)
                fig_rank = go.Figure(data=[go.Table(
                    header=dict(
                        values=["<b>Ay</b>"] + [f"<b>{c}<br>kWh/m²</b>" for c in lok_isimleri] + ["<b>🏆 En Verimli</b>"],
                        fill_color="rgba(0,100,200,0.5)", font=dict(color="white",size=12),
                        align="center", height=36,
                    ),
                    cells=dict(
                        values=[pivot["Ay"]] + [pivot[c].apply(lambda x: f"{x:.1f}") for c in lok_isimleri] + [pivot["En Verimli"]],
                        fill_color=[["rgba(0,20,50,0.6)","rgba(0,30,70,0.4)"] * len(pivot)],
                        font=dict(color="white",size=12), align="center", height=30,
                    )
                )])
                fig_rank.update_layout(paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=5,b=5,l=0,r=0), height=350)
                st.markdown('<div class="section-title">📋 AYLIK VERİMLİLİK SIRALAMASI</div>', unsafe_allow_html=True)
                st.plotly_chart(fig_rank, use_container_width=True)

# ============================================================
# TAB 5 — TÜRKİYE HARİTASI
# ============================================================
with tabs[4]:
    st.markdown('<div class="section-title">🗺️ HASTANE AĞI — TÜRKİYE</div>', unsafe_allow_html=True)

    now = datetime.now()
    dun = (now - timedelta(days=1)).strftime("%Y-%m-%d")

    harita_data = []
    for lok_id, lok_info in HASTANELER.items():
        lok_veri = lok_dict.get(lok_id, {})
        ping_str = str(lok_veri.get("ping_zamani") or "").strip()
        online = False
        if ping_str and ping_str not in ("None",""):
            try:
                ping_dt = pd.to_datetime(ping_str).tz_localize(None)
                online = (now - ping_dt).total_seconds() / 60 < 10
            except:
                pass

        dun_kwh = 0
        if not df_all.empty and lok_id in aktif_loklar:
            dun_df = df_all[(df_all["lokasyon_id"]==lok_id) & (df_all["Tarih"].dt.strftime("%Y-%m-%d")==dun)]
            if not dun_df.empty and "Toplam_Hastane_Tuketim_kWh" in dun_df.columns:
                dun_kwh = dun_df["Toplam_Hastane_Tuketim_kWh"].sum()

        harita_data.append({
            "Hastane": lok_info["isim"],
            "lat": lok_info["lat"],
            "lon": lok_info["lon"],
            "Durum": "Çevrimiçi" if online else "Çevrimdışı",
            "Tüketim (kWh)": int(dun_kwh),
            "m2": lok_info["m2"],
            "renk": "#10b981" if online else "#ef4444",
            "boyut": max(15, min(40, dun_kwh / 1000)) if dun_kwh > 0 else 15,
        })

    harita_df = pd.DataFrame(harita_data)

    fig_harita = go.Figure()

    # Türkiye sınır çizgisi (arka plan için basit scatter)
    fig_harita.add_trace(go.Scattermapbox(
        lat=harita_df["lat"], lon=harita_df["lon"],
        mode="markers+text",
        marker=dict(
            size=harita_df["boyut"],
            color=harita_df["renk"],
            opacity=0.9,
        ),
        text=harita_df["Hastane"],
        textposition="top center",
        textfont=dict(color="white", size=12, family="Orbitron"),
        customdata=harita_df[["Durum","Tüketim (kWh)","m2"]].values,
        hovertemplate="<b>%{text}</b><br>Durum: %{customdata[0]}<br>Dünkü Tüketim: %{customdata[1]:,} kWh<br>Alan: %{customdata[2]:,} m²<extra></extra>",
        name=""
    ))

    fig_harita.update_layout(
        mapbox=dict(
            style="carto-darkmatter",
            center=dict(lat=41.02, lon=29.02),
            zoom=10.5,
        ),
        paper_bgcolor="rgba(0,0,0,0)",
        margin=dict(t=0,b=0,l=0,r=0),
        height=500,
        showlegend=False,
    )
    st.plotly_chart(fig_harita, use_container_width=True)

    # Haritanın altında kart listesi
    st.markdown('<div class="section-title" style="margin-top:16px;">📍 LOKASYON DETAYLARI</div>', unsafe_allow_html=True)
    kart_cols = st.columns(len(harita_data))
    for i, row in enumerate(harita_data):
        with kart_cols[i]:
            online = row["Durum"] == "Çevrimiçi"
            renk = "#10b981" if online else "#ef4444"
            st.markdown(f"""
            <div class="neon-card {'neon-card-online' if online else 'neon-card-offline'}">
                <div style="font-family:'Orbitron',sans-serif; font-size:10px; color:{HASTANELER.get(list(HASTANELER.keys())[i],{}).get('renk','#00d4ff')}; letter-spacing:1px;">{row['Hastane'].upper()}</div>
                <div style="font-size:20px; font-weight:800; color:#00d4ff; font-family:'Orbitron',sans-serif; margin-top:6px;">{row['Tüketim (kWh)']:,} <span style="font-size:10px;">kWh</span></div>
                <div style="font-size:10px; color:rgba(150,210,255,0.5);">Dünkü Tüketim</div>
                <div style="margin-top:8px; font-size:11px; color:{renk};">{'🟢 Çevrimiçi' if online else '🔴 Çevrimdışı'}</div>
            </div>
            """, unsafe_allow_html=True)

# ============================================================
# TAB 6 — GÜNCELLEMELER
# ============================================================
with tabs[5]:
    st.markdown('<div class="section-title">📦 GÜNCELLEME DURUMU</div>', unsafe_allow_html=True)

    @st.cache_data(ttl=30, show_spinner=False)
    def fetch_guncellemeler(url, key):
        try:
            from supabase import create_client
            c = create_client(url, key)
            r = c.table("guncellemeler").select("id,versiyon,hedef,durum,created_at").order("created_at", desc=True).limit(20).execute()
            return r.data or []
        except:
            return []

    gunc_data = fetch_guncellemeler(url, key)

    if st.button("🔄 Yenile"):
        st.cache_data.clear()
        st.rerun()

    if gunc_data:
        durum_renk = {"tamamlandi":"#10b981","bekliyor":"#f59e0b","iptal":"#6b7280","hata":"#ef4444"}
        durum_icon = {"tamamlandi":"✅","bekliyor":"⏳","iptal":"❌","hata":"🚨"}

        fig_g = go.Figure(data=[go.Table(
            header=dict(
                values=["<b>Versiyon</b>","<b>Hedef</b>","<b>Durum</b>","<b>Tarih</b>"],
                fill_color="rgba(0,100,200,0.5)", font=dict(color="white",size=12),
                align="center", height=34,
            ),
            cells=dict(
                values=[
                    [r["versiyon"] for r in gunc_data],
                    [r["hedef"] for r in gunc_data],
                    [f"{durum_icon.get(r['durum'],'')} {r['durum']}" for r in gunc_data],
                    [r["created_at"][:16].replace("T"," ") for r in gunc_data],
                ],
                fill_color=[["rgba(0,20,50,0.6)","rgba(0,30,70,0.4)"] * len(gunc_data)],
                font=dict(color="white",size=12), align="center", height=30,
            )
        )])
        fig_g.update_layout(paper_bgcolor="rgba(0,0,0,0)", margin=dict(t=5,b=5,l=0,r=0), height=500)
        st.plotly_chart(fig_g, use_container_width=True)
    else:
        st.info("Güncelleme kaydı yok.")

# ============ FOOTER ============
st.markdown(f"""
<div style="text-align:center; padding:20px 0 10px; border-top:1px solid rgba(0,212,255,0.1); margin-top:20px;">
    <div style="font-family:'Orbitron',sans-serif; font-size:10px; color:rgba(0,212,255,0.3); letter-spacing:2px;">
        ACIBADEM SAĞLIK GRUBU — ENERJİ YÖNETİM SİSTEMİ
    </div>
    <div style="font-size:10px; color:rgba(150,210,255,0.3); margin-top:4px;">
        Son güncelleme: {datetime.now().strftime('%d.%m.%Y %H:%M')}
    </div>
</div>
""", unsafe_allow_html=True)
