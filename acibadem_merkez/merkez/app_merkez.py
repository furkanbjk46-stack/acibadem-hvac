# app_merkez.py
# Acıbadem Genel Merkez — Enerji & HVAC Merkezi Dashboard
# Supabase üzerinden tüm lokasyonların verilerini gösterir

from __future__ import annotations
import os
import sys
import json
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(
    page_title="Acıbadem Genel Merkez — Enerji Komuta Merkezi",
    page_icon="🏢",
    layout="wide"
)

# ============ CSS ============
st.markdown("""
<style>
    .stApp {
        background: linear-gradient(-45deg, #0a0e1a, #1a0a2e, #0a1628, #2a1a3e);
        background-size: 400% 400%;
        animation: gradient 20s ease infinite;
    }
    @keyframes gradient {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    h1, h2, h3, h4, h5, h6 { color: #ffffff !important; }
    p, span, div, label { color: rgba(255,255,255,0.9) !important; }
    
    .stTabs [data-baseweb="tab-panel"] {
        background: rgba(255,255,255,0.08);
        backdrop-filter: blur(20px);
        border-radius: 16px;
        padding: 24px;
        border: 1px solid rgba(255,255,255,0.15);
    }
    .stTabs [data-baseweb="tab-list"] {
        background: rgba(255,255,255,0.08);
        border-radius: 12px;
        padding: 8px;
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        color: rgba(255,255,255,0.7);
        border-radius: 8px;
        font-weight: 600;
    }
    .stTabs [aria-selected="true"] {
        background: rgba(255,255,255,0.2) !important;
        color: #ffffff !important;
    }
    [data-testid="stMetricValue"] { color: #ffffff !important; font-size: 28px !important; font-weight: 800 !important; }
    [data-testid="stMetricLabel"] { color: rgba(255,255,255,0.7) !important; }
    [data-testid="stMetricDelta"] { color: rgba(255,255,255,0.9) !important; }
    
    .stButton > button {
        background: linear-gradient(135deg, #6b21a8, #9333ea);
        color: white; border: none; border-radius: 10px; font-weight: 700;
    }
    .stButton > button:hover { transform: translateY(-2px); box-shadow: 0 4px 12px rgba(147,51,234,0.4); }
    .stButton > button p, .stButton > button span { color: #ffffff !important; }
    
    .lokasyon-card {
        background: rgba(255,255,255,0.08);
        backdrop-filter: blur(20px);
        border-radius: 16px;
        padding: 20px;
        border: 1px solid rgba(255,255,255,0.15);
        margin-bottom: 16px;
    }
    .status-online { color: #10b981; font-weight: 800; }
    .status-offline { color: #ef4444; font-weight: 800; }
</style>
""", unsafe_allow_html=True)

# ============ CONFIG & DATA ============
CONFIG_FILE = os.path.join(os.path.dirname(__file__), "configs", "merkez_config.json")

def load_config():
    if os.path.exists(CONFIG_FILE):
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def get_client():
    config = load_config()
    try:
        from supabase import create_client
        url = config.get("supabase_url", "")
        key = config.get("supabase_key", "")
        if "BURAYA" in url or not url:
            return None, config
        return create_client(url, key), config
    except Exception:
        return None, config

@st.cache_data(ttl=300, show_spinner=False)
def fetch_all_energy(url, key):
    """Tüm lokasyonların enerji verisini çek (5dk cache)"""
    try:
        from supabase import create_client
        client = create_client(url, key)
        result = client.table("energy_data").select("*").order("Tarih", desc=False).execute()
        if result.data:
            df = pd.DataFrame(result.data)
            if "Tarih" in df.columns:
                df["Tarih"] = pd.to_datetime(df["Tarih"], errors="coerce")
            return df
    except Exception as e:
        st.error(f"Veri çekme hatası: {e}")
    return pd.DataFrame()

@st.cache_data(ttl=300, show_spinner=False)
def fetch_lokasyonlar(url, key):
    try:
        from supabase import create_client
        client = create_client(url, key)
        result = client.table("lokasyonlar").select("*").execute()
        return result.data if result.data else []
    except Exception:
        return []

# ============ HEADER ============
st.markdown("""
<div style='text-align:center; margin-bottom:20px;'>
    <h1 style='font-size:28px; letter-spacing:1px;'>🏢 ACIBADEM GENEL MERKEZ</h1>
    <p style='font-size:16px; opacity:0.7;'>Enerji & HVAC Komuta Merkezi</p>
</div>
""", unsafe_allow_html=True)

# ============ BAĞLANTI KONTROLÜ ============
config = load_config()
sb_url = config.get("supabase_url", "")
sb_key = config.get("supabase_key", "")

if "BURAYA" in sb_url or not sb_url:
    st.warning("⚠️ Supabase bağlantısı henüz ayarlanmamış! `merkez/configs/merkez_config.json` dosyasını düzenleyin.")
    st.info("""
    **Kurulum Adımları:**
    1. [supabase.com](https://supabase.com) adresinden ücretsiz hesap açın
    2. Yeni proje oluşturun
    3. Project Settings → API bölümünden URL ve anon key alın
    4. `merkez_config.json` dosyasına yapıştırın
    """)
    st.stop()

# ============ VERİ YÜKLEMELERİ ============
with st.spinner("📡 Lokasyonlardan veri çekiliyor..."):
    df_all = fetch_all_energy(sb_url, sb_key)
    lokasyonlar = fetch_lokasyonlar(sb_url, sb_key)

if df_all.empty:
    st.info("📭 Henüz lokasyonlardan veri gelmemiş. Lokasyonlarda `cloud_sync.py` çalıştırıldığından emin olun.")
    st.stop()

# Lokasyon isimleri
LOK_NAMES = {
    "maslak": "Acıbadem Maslak",
    "altunizade": "Acıbadem Altunizade"
}

aktif_lokasyonlar = df_all["lokasyon_id"].unique().tolist() if "lokasyon_id" in df_all.columns else []

# ============ TABS ============
tabs = st.tabs([
    "📊 Genel Bakış",
    "⚡ Enerji Karşılaştırma",
    "💰 Maliyet Özet",
    "📈 Trend & Benchmark",
    "🔧 HVAC Durumu"
])

# ============ TAB 1: GENEL BAKIŞ ============
with tabs[0]:
    st.markdown("### 📊 Lokasyon Durumları")
    
    # Lokasyon kartları
    cols = st.columns(max(len(aktif_lokasyonlar), 2))
    
    for i, lok_id in enumerate(aktif_lokasyonlar):
        lok_name = LOK_NAMES.get(lok_id, lok_id.title())
        lok_df = df_all[df_all["lokasyon_id"] == lok_id].copy()
        
        # Son sync bilgisi
        lok_info = next((l for l in lokasyonlar if l.get("lokasyon_id") == lok_id), {})
        son_sync = lok_info.get("son_sync", "Bilinmiyor")
        durum = lok_info.get("durum", "offline")
        
        with cols[i]:
            status_class = "status-online" if durum == "online" else "status-offline"
            status_icon = "🟢" if durum == "online" else "🔴"
            
            st.markdown(f"""
            <div class='lokasyon-card'>
                <h3>{lok_name} {status_icon}</h3>
                <p>Toplam Kayıt: <strong>{len(lok_df)}</strong></p>
                <p>Son Senkronizasyon: <strong>{son_sync[:16] if len(str(son_sync)) > 16 else son_sync}</strong></p>
            </div>
            """, unsafe_allow_html=True)
            
            # Son günün verileri
            if not lok_df.empty and "Tarih" in lok_df.columns:
                son_gun = lok_df.sort_values("Tarih").iloc[-1]
                tarih_str = str(son_gun.get("Tarih", ""))[:10]
                
                st.caption(f"📅 Son Veri: {tarih_str}")
                
                m1, m2 = st.columns(2)
                toplam = son_gun.get("Toplam_Hastane_Tuketim_kWh", 0) or 0
                sogutma = son_gun.get("Toplam_Sogutma_Tuketim_kWh", 0) or 0
                m1.metric("Toplam Tüketim", f"{toplam:,.0f} kWh")
                m2.metric("Soğutma", f"{sogutma:,.0f} kWh")
                
                m3, m4 = st.columns(2)
                chiller = son_gun.get("Chiller_Tuketim_kWh", 0) or 0
                mcc = son_gun.get("MCC_Tuketim_kWh", 0) or 0
                m3.metric("Chiller", f"{chiller:,.0f} kWh")
                m4.metric("MCC", f"{mcc:,.0f} kWh")
    
    # Grup toplam
    st.markdown("---")
    st.markdown("### 🏢 Grup Toplam (Tüm Lokasyonlar)")
    
    # Son 30 gün toplamları
    if "Tarih" in df_all.columns:
        son_30 = df_all[df_all["Tarih"] >= (datetime.now() - timedelta(days=30))]
        
        gc1, gc2, gc3, gc4 = st.columns(4)
        
        total_hosp = son_30.get("Toplam_Hastane_Tuketim_kWh", pd.Series([0])).sum()
        total_cool = son_30.get("Toplam_Sogutma_Tuketim_kWh", pd.Series([0])).sum()
        total_chiller = son_30.get("Chiller_Tuketim_kWh", pd.Series([0])).sum()
        total_mcc = son_30.get("MCC_Tuketim_kWh", pd.Series([0])).sum()
        
        gc1.metric("📊 Son 30 Gün Toplam", f"{total_hosp:,.0f} kWh")
        gc2.metric("❄️ Toplam Soğutma", f"{total_cool:,.0f} kWh")
        gc3.metric("🧊 Toplam Chiller", f"{total_chiller:,.0f} kWh")
        gc4.metric("⚡ Toplam MCC", f"{total_mcc:,.0f} kWh")

# ============ TAB 2: ENERJİ KARŞILAŞTIRMA ============
with tabs[1]:
    st.markdown("### ⚡ Lokasyon Bazlı Enerji Karşılaştırması")
    
    if "Tarih" in df_all.columns and "lokasyon_id" in df_all.columns:
        # Zaman aralığı seçimi
        period = st.radio("Dönem", ["Son 30 Gün", "Son 90 Gün", "Son 1 Yıl", "Tümü"], horizontal=True)
        
        df_plot = df_all.copy()
        if period == "Son 30 Gün":
            df_plot = df_plot[df_plot["Tarih"] >= (datetime.now() - timedelta(days=30))]
        elif period == "Son 90 Gün":
            df_plot = df_plot[df_plot["Tarih"] >= (datetime.now() - timedelta(days=90))]
        elif period == "Son 1 Yıl":
            df_plot = df_plot[df_plot["Tarih"] >= (datetime.now() - timedelta(days=365))]
        
        # Lokasyon isimlerini güncelle
        df_plot["Lokasyon"] = df_plot["lokasyon_id"].map(lambda x: LOK_NAMES.get(x, x))
        
        # Günlük toplam tüketim karşılaştırması
        numeric_cols = ["Toplam_Hastane_Tuketim_kWh", "Chiller_Tuketim_kWh", "MCC_Tuketim_kWh",
                       "Sebeke_Tuketim_kWh", "Kazan_Dogalgaz_m3"]
        
        for col in numeric_cols:
            if col in df_plot.columns:
                df_plot[col] = pd.to_numeric(df_plot[col], errors="coerce")
        
        # Toplam tüketim çizgi grafiği
        if "Toplam_Hastane_Tuketim_kWh" in df_plot.columns:
            fig = px.line(
                df_plot, x="Tarih", y="Toplam_Hastane_Tuketim_kWh",
                color="Lokasyon",
                title="Günlük Toplam Hastane Tüketimi (kWh)",
                color_discrete_map={
                    "Acıbadem Maslak": "#3b82f6",
                    "Acıbadem Altunizade": "#f59e0b"
                }
            )
            fig.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="white"
            )
            st.plotly_chart(fig, use_container_width=True)
        
        # Chiller tüketim karşılaştırması
        if "Chiller_Tuketim_kWh" in df_plot.columns:
            fig2 = px.line(
                df_plot, x="Tarih", y="Chiller_Tuketim_kWh",
                color="Lokasyon",
                title="Günlük Chiller Tüketimi (kWh)",
                color_discrete_map={
                    "Acıbadem Maslak": "#3b82f6",
                    "Acıbadem Altunizade": "#f59e0b"
                }
            )
            fig2.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="white"
            )
            st.plotly_chart(fig2, use_container_width=True)
        
        # Aylık karşılaştırma bar chart
        st.markdown("#### 📊 Aylık Toplam Karşılaştırma")
        df_monthly = df_plot.copy()
        df_monthly["Ay"] = df_monthly["Tarih"].dt.to_period("M").astype(str)
        
        if "Toplam_Hastane_Tuketim_kWh" in df_monthly.columns:
            monthly_agg = df_monthly.groupby(["Ay", "Lokasyon"])["Toplam_Hastane_Tuketim_kWh"].sum().reset_index()
            
            fig3 = px.bar(
                monthly_agg, x="Ay", y="Toplam_Hastane_Tuketim_kWh",
                color="Lokasyon", barmode="group",
                title="Aylık Toplam Tüketim Karşılaştırması",
                color_discrete_map={
                    "Acıbadem Maslak": "#3b82f6",
                    "Acıbadem Altunizade": "#f59e0b"
                }
            )
            fig3.update_layout(
                template="plotly_dark",
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font_color="white"
            )
            st.plotly_chart(fig3, use_container_width=True)

# ============ TAB 3: MALİYET ÖZET ============
with tabs[2]:
    st.markdown("### 💰 Grup Maliyet Özeti")
    
    # Birim fiyatlar
    st.markdown("#### ⚙️ Birim Fiyatlar")
    pc1, pc2, pc3 = st.columns(3)
    elektrik_fiyat = pc1.number_input("Elektrik (TL/kWh)", value=4.20, step=0.10, format="%.2f")
    gaz_fiyat = pc2.number_input("Doğalgaz (TL/m³)", value=8.50, step=0.10, format="%.2f")
    su_fiyat = pc3.number_input("Su (TL/m³)", value=35.0, step=1.0, format="%.1f")
    
    st.markdown("---")
    
    if "Tarih" in df_all.columns:
        # Son ay verileri
        son_ay = df_all[df_all["Tarih"] >= (datetime.now() - timedelta(days=30))]
        
        for lok_id in aktif_lokasyonlar:
            lok_name = LOK_NAMES.get(lok_id, lok_id)
            lok_df = son_ay[son_ay["lokasyon_id"] == lok_id]
            
            if lok_df.empty:
                continue
            
            st.markdown(f"#### 🏥 {lok_name}")
            
            # Tüketim toplam hesapla
            sebeke = pd.to_numeric(lok_df.get("Sebeke_Tuketim_kWh", 0), errors="coerce").sum()
            kojen = pd.to_numeric(lok_df.get("Kojen_Uretim_kWh", 0), errors="coerce").sum()
            kazan_gaz = pd.to_numeric(lok_df.get("Kazan_Dogalgaz_m3", 0), errors="coerce").sum()
            kojen_gaz = pd.to_numeric(lok_df.get("Kojen_Dogalgaz_m3", 0), errors="coerce").sum()
            su = pd.to_numeric(lok_df.get("Su_Tuketimi_m3", 0), errors="coerce").sum()
            
            elek_maliyet = sebeke * elektrik_fiyat
            gaz_maliyet = (kazan_gaz + kojen_gaz) * gaz_fiyat
            su_maliyet = su * su_fiyat
            toplam_maliyet = elek_maliyet + gaz_maliyet + su_maliyet
            
            mc1, mc2, mc3, mc4 = st.columns(4)
            mc1.metric("⚡ Elektrik", f"₺{elek_maliyet:,.0f}")
            mc2.metric("🔥 Doğalgaz", f"₺{gaz_maliyet:,.0f}")
            mc3.metric("💧 Su", f"₺{su_maliyet:,.0f}")
            mc4.metric("💰 TOPLAM", f"₺{toplam_maliyet:,.0f}")
            
            st.markdown("---")
        
        # Grup toplam
        st.markdown("#### 🏢 GRUP TOPLAM MALİYET (Son 30 Gün)")
        g_sebeke = pd.to_numeric(son_ay.get("Sebeke_Tuketim_kWh", 0), errors="coerce").sum()
        g_kazan = pd.to_numeric(son_ay.get("Kazan_Dogalgaz_m3", 0), errors="coerce").sum()
        g_kojen = pd.to_numeric(son_ay.get("Kojen_Dogalgaz_m3", 0), errors="coerce").sum()
        g_su = pd.to_numeric(son_ay.get("Su_Tuketimi_m3", 0), errors="coerce").sum()
        
        g_total = g_sebeke * elektrik_fiyat + (g_kazan + g_kojen) * gaz_fiyat + g_su * su_fiyat
        
        st.metric("🏢 GRUP TOPLAM MALİYET", f"₺{g_total:,.0f}")

# ============ TAB 4: TREND & BENCHMARK ============
with tabs[3]:
    st.markdown("### 📈 Verimlilik Karşılaştırması (Benchmark)")
    
    if len(aktif_lokasyonlar) >= 2 and "Tarih" in df_all.columns:
        # Aylık kWh toplamları
        df_bench = df_all.copy()
        df_bench["Ay"] = df_bench["Tarih"].dt.to_period("M").astype(str)
        df_bench["Lokasyon"] = df_bench["lokasyon_id"].map(lambda x: LOK_NAMES.get(x, x))
        
        for col in ["Toplam_Hastane_Tuketim_kWh", "Chiller_Tuketim_kWh"]:
            if col in df_bench.columns:
                df_bench[col] = pd.to_numeric(df_bench[col], errors="coerce")
        
        if "Toplam_Hastane_Tuketim_kWh" in df_bench.columns:
            monthly = df_bench.groupby(["Ay", "Lokasyon"])["Toplam_Hastane_Tuketim_kWh"].sum().reset_index()
            
            # Pivot tablo
            pivot = monthly.pivot(index="Ay", columns="Lokasyon", values="Toplam_Hastane_Tuketim_kWh").fillna(0)
            
            if len(pivot.columns) >= 2:
                st.dataframe(pivot.style.format("{:,.0f}"), use_container_width=True)
                
                # Fark hesapla
                lok_cols = list(pivot.columns)
                pivot["Fark (kWh)"] = pivot[lok_cols[0]] - pivot[lok_cols[1]]
                pivot["Verimli Olan"] = pivot["Fark (kWh)"].apply(
                    lambda x: lok_cols[1] if x > 0 else lok_cols[0]
                )
                
                st.markdown("#### 🏆 Aylık Verimlilik Sıralaması")
                st.dataframe(pivot[["Fark (kWh)", "Verimli Olan"]], use_container_width=True)
    else:
        st.info("Benchmark için en az 2 lokasyondan veri gerekiyor.")

# ============ TAB 5: HVAC DURUMU ============
with tabs[4]:
    st.markdown("### 🔧 Lokasyon HVAC Durumları")
    st.info("HVAC analiz özeti, lokasyonlardan senkronize edildiğinde burada görünecektir.")
    
    # Senkron bilgileri göster
    if lokasyonlar:
        for lok in lokasyonlar:
            lok_id = lok.get("lokasyon_id", "?")
            lok_name = LOK_NAMES.get(lok_id, lok_id)
            son_sync = lok.get("son_sync", "Bilinmiyor")
            durum = lok.get("durum", "offline")
            
            icon = "🟢" if durum == "online" else "🔴"
            st.markdown(f"""
            **{icon} {lok_name}**  
            Son Senkronizasyon: `{son_sync}`  
            Durum: `{durum}`
            """)
    else:
        st.warning("Henüz lokasyon bilgisi yok.")

# ============ FOOTER ============
st.markdown("---")
fc1, fc2 = st.columns(2)
fc1.caption(f"Son güncelleme: {datetime.now().strftime('%d.%m.%Y %H:%M')}")
if fc2.button("🔄 Veriyi Yenile"):
    st.cache_data.clear()
    st.rerun()
