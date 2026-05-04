# pages/lokasyon_detay.py
# Lokasyon Detay Sayfası — Sadece Okuma & Grafik

from __future__ import annotations
import os, sys, json
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

# ── CSS ──────────────────────────────────────────────
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
* { font-family: 'Inter', sans-serif; }
/* Streamlit Material ikon istisnası */
span[data-testid="stIconMaterial"],
[data-testid="stExpanderToggleIcon"] span,
button span[data-testid="stIconMaterial"] {
    font-family: 'Material Symbols Rounded' !important;
}
.sec {
    font-family: 'Orbitron', sans-serif;
    font-size: 9px; font-weight: 700;
    color: rgba(0,212,255,0.5);
    letter-spacing: 3px; text-transform: uppercase;
    padding: 4px 0 8px; margin-top: 16px;
    border-bottom: 1px solid rgba(0,212,255,0.12);
}
.metric-card {
    background: rgba(0,20,50,0.7);
    border: 1px solid rgba(0,212,255,0.15);
    border-radius: 12px;
    padding: 16px;
    text-align: center;
}
[data-testid="stTabs"] [data-baseweb="tab-list"] {
    background: rgba(0,20,50,0.5);
    border-radius: 10px; padding: 4px; gap: 4px;
}
[data-testid="stTabs"] [data-baseweb="tab"] {
    color: rgba(160,200,255,0.6);
    border-radius: 8px; font-weight: 600;
}
[data-testid="stTabs"] [aria-selected="true"] {
    background: rgba(0,212,255,0.15) !important;
    color: #00d4ff !important;
}
[data-testid="stTabs"] [data-baseweb="tab-panel"] {
    background: rgba(0,10,30,0.4);
    border-radius: 12px; padding: 20px;
    border: 1px solid rgba(0,212,255,0.08);
}
.stDataFrame thead tr th {
    background: rgba(1,45,117,0.9) !important;
    color: #fff !important; font-weight:700 !important;
}
.stDataFrame tbody tr td {
    background: rgba(10,25,60,0.7) !important;
    color: #d8eeff !important;
    border-bottom: 1px solid rgba(80,130,220,0.15) !important;
}
.stButton > button {
    background: rgba(0,212,255,0.1) !important;
    color: #00d4ff !important;
    border: 1px solid rgba(0,212,255,0.3) !important;
    border-radius: 10px !important;
    font-weight: 600 !important;
}
.stButton > button:hover {
    background: rgba(0,212,255,0.2) !important;
}
</style>
""", unsafe_allow_html=True)

# ── Lokasyon bilgileri (app_merkez.py ile senkron) ───────
HASTANELER = {
    # ── İstanbul ──
    "maslak":        {"isim": "Acıbadem Maslak",         "kisa": "MASLAK",       "m2": 15000, "renk": "#00d4ff"},
    "altunizade":    {"isim": "Acıbadem Altunizade",     "kisa": "ALTUNİZADE",   "m2": 10000, "renk": "#f59e0b"},
    "kozyatagi":     {"isim": "Acıbadem Kozyatağı",      "kisa": "KOZYATAĞİ",   "m2": 12000, "renk": "#10b981"},
    "taksim":        {"isim": "Acıbadem Taksim",         "kisa": "TAKSİM",       "m2":  8000, "renk": "#a855f7"},
    "atakent":       {"isim": "Acıbadem Atakent",        "kisa": "ATAKENT",      "m2": 20000, "renk": "#f97316"},
    "atasehir":      {"isim": "Acıbadem Ataşehir",       "kisa": "ATAŞEHİR",     "m2": 14000, "renk": "#06b6d4"},
    "bakirkoy":      {"isim": "Acıbadem Bakırköy",       "kisa": "BAKIRKÖY",     "m2": 12000, "renk": "#84cc16"},
    "fulya":         {"isim": "Acıbadem Fulya",          "kisa": "FULYA",        "m2":  9000, "renk": "#e879f9"},
    "international": {"isim": "Acıbadem International",  "kisa": "INTERNAT.",    "m2": 18000, "renk": "#14b8a6"},
    "kadikoy":       {"isim": "Acıbadem Kadıköy",        "kisa": "KADİKÖY",      "m2":  8000, "renk": "#ec4899"},
    "kartal":        {"isim": "Acıbadem Kartal",         "kisa": "KARTAL",       "m2": 11000, "renk": "#ef4444"},
    # ── Ankara ──
    "ankara":          {"isim": "Acıbadem Ankara",           "kisa": "ANKARA",      "m2": 16000, "renk": "#fb7185"},
    "bayindir":        {"isim": "Acıbadem Bayındır",          "kisa": "BAYINDIR",    "m2": 12000, "renk": "#f43f5e"},
    # ── Bursa ──
    "bursa":           {"isim": "Acıbadem Bursa",             "kisa": "BURSA",       "m2": 13000, "renk": "#fbbf24"},
    # ── Kocaeli ──
    "kocaeli":         {"isim": "Acıbadem Kocaeli",           "kisa": "KOCAELİ",     "m2": 10000, "renk": "#34d399"},
    # ── Eskişehir ──
    "eskisehir":       {"isim": "Acıbadem Eskişehir",         "kisa": "ESKİŞEHİR",   "m2":  9000, "renk": "#818cf8"},
    # ── İzmir ──
    "izmir":           {"isim": "Acıbadem İzmir Kent",        "kisa": "İZMİR",       "m2": 15000, "renk": "#38bdf8"},
    # ── Kayseri ──
    "kayseri":         {"isim": "Acıbadem Kayseri",           "kisa": "KAYSERİ",     "m2": 11000, "renk": "#a78bfa"},
    # ── Adana ──
    "adana":           {"isim": "Acıbadem Adana",             "kisa": "ADANA",       "m2": 12000, "renk": "#f472b6"},
    "adana_ortopedia": {"isim": "Acıbadem Adana Ortopedia",   "kisa": "ADANA ORT.",  "m2":  5000, "renk": "#e879f9"},
    # ── Bodrum ──
    "bodrum":          {"isim": "Acıbadem Bodrum",            "kisa": "BODRUM",      "m2":  7000, "renk": "#2dd4bf"},
}

# ── Config & Lokasyon seç ────────────────────────────
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

lok_id = st.session_state.get("detay_lokasyon", None)
if not lok_id or lok_id not in HASTANELER:
    st.error("Lokasyon seçilmedi. Ana sayfaya dönün.")
    if st.button("⬅ Ana Sayfaya Dön"):
        st.switch_page("app_merkez.py")
    st.stop()

lok_info = HASTANELER[lok_id]
renk     = lok_info["renk"]
m2       = lok_info.get("m2", 10000)
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

# ── DEBUG: Supabase'deki tüm lokasyon_id'leri göster ──
with st.expander("🔍 Supabase Debug — Tüm Lokasyon ID'leri", expanded=False):
    debug_df = fetch_tum_lokasyonlar_debug(url, key)
    if not debug_df.empty:
        st.dataframe(debug_df, use_container_width=True, hide_index=True)
        st.caption(f"Bu sayfada aranan lok_id: **`{lok_id}`**")
    else:
        st.warning("Veri alınamadı.")
now = datetime.now()
dun = (now - timedelta(days=1)).strftime("%Y-%m-%d")

# En son mevcut tarihi bul (dün yoksa geriye doğru en yakın tarih)
if not df.empty:
    son_tarih = df["Tarih"].dropna().max()
    son_tarih_str = son_tarih.strftime("%Y-%m-%d")
else:
    son_tarih_str = dun

# ── Header ───────────────────────────────────────────
col_geri, col_baslik = st.columns([1, 9])
with col_geri:
    if st.button("⬅ Geri"):
        st.switch_page("app_merkez.py")
with col_baslik:
    st.markdown(
        f"""<div style='padding:8px 0;'>
        <div style='font-family:Orbitron,sans-serif;font-size:8px;color:rgba(0,212,255,0.45);
                    letter-spacing:5px;text-transform:uppercase;'>ACIBADEM SAĞLIK GRUBU — LOKASYON DETAY</div>
        <div style='font-family:Orbitron,sans-serif;font-size:22px;font-weight:900;
                    color:{renk};text-shadow:0 0 25px rgba({rr},{rg},{rb},0.8);
                    letter-spacing:3px;'>{lok_info["isim"].upper()}</div>
        </div>""",
        unsafe_allow_html=True
    )

st.markdown("---")

if df.empty:
    st.warning("Bu lokasyon için veri bulunamadı.")
    st.stop()

# ── SEKMELER ─────────────────────────────────────────
tab1, tab2, tab3, tab4 = st.tabs(["📊 Dashboard", "📈 Trend & Tahmin", "📋 Veri Tablosu", "📄 Rapor Oluştur"])

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

    # ── 3 SÜTUN LAYOUT ────────────────────────────────
    col_left, col_mid, col_right = st.columns([2, 4, 2])

    # ──────────── SÜTUN 1: Stacked metrik kartlar ────────────
    with col_left:
        st.markdown('<div class="sec">⚡ ÖZET</div>', unsafe_allow_html=True)

        def metric_card_v(ikon, baslik, deger, birim, renk_hex, alt_bilgi=""):
            r2=int(renk_hex[1:3],16); g2=int(renk_hex[3:5],16); b2=int(renk_hex[5:7],16)
            alt_html = (
                f"<div style='font-size:8px;color:rgba(150,210,255,0.4);margin-top:5px;"
                f"letter-spacing:0.5px;'>{alt_bilgi}</div>"
            ) if alt_bilgi else ""
            st.markdown(
                f"""<div class="metric-card" style="margin-bottom:10px;">
                <div style='font-size:18px;margin-bottom:2px;'>{ikon}</div>
                <div style='font-size:8px;color:rgba(150,210,255,0.5);letter-spacing:1px;
                            text-transform:uppercase;margin-bottom:4px;'>{baslik}</div>
                <div style='font-family:Orbitron,sans-serif;font-size:17px;font-weight:900;
                            color:{renk_hex};text-shadow:0 0 12px rgba({r2},{g2},{b2},0.7);'>
                    {deger}<span style='font-size:8px;color:rgba(150,210,255,0.5);margin-left:3px;'>{birim}</span>
                </div>{alt_html}</div>""",
                unsafe_allow_html=True
            )

        metric_card_v("⚡", f"Tüketim ({son_tarih_str})", f"{kwh_dun:,.0f}", "kWh", "#00d4ff")
        metric_card_v("📐", "kWh/m²",     f"{verim_dun:.2f}", "kWh/m²", "#f59e0b")
        metric_card_v(
            "📅", f"{ay_adi} Toplam",
            f"{kwh_bu_ay:,.0f}", "kWh", "#10b981",
            alt_bilgi=f"{ay_bas_str} → {ay_bit_str}  ({ay_gun_sayi} gün)"
        )
        metric_card_v("❄️", "Chiller Set", f"{ch_set:.1f}" if ch_set else "—", "°C", "#a855f7")

        # Kojen öz tüketim oranı
        if kojen_urt and kwh_dun and kwh_dun > 0:
            kojen_oran = min(kojen_urt / kwh_dun * 100, 100)
            metric_card_v("⚙️", "Kojen Karşılama", f"{kojen_oran:.1f}", "%", "#10b981")


    # ──────────── SÜTUN 2: Grafik seçici + dinamik grafik ────────────
    with col_mid:
        st.markdown('<div class="sec">📊 GRAFİK</div>', unsafe_allow_html=True)

        grafik_secenekler = {
            "📊 Tüketim":               "tuketim",
            "❄️ Chiller Set Trendi":    "chiller",
            "📐 kWh/m² Trendi":         "verimlilik",
            "💧 Su Tüketimi":            "su",
            "⚙️ Kojen Üretim":          "kojen",
            "🔌 Şebeke Tüketimi":       "sebeke",
            "🏭 MCC Tüketimi":          "mcc",
            "🔥 Kazan Doğalgaz":        "kazan",
            "📆 Bu Ay vs Geçen Ay":     "ay_karsilastir",
            "🔥 Doğalgaz Verimliliği":  "dogalgaz_verim",
            "📋 KPI Özet":              "kpi_ozet",
        }

        # ── Grafik seçici + Tarih aralığı (yan yana) ──
        _gc1, _gc2, _gc3 = st.columns([3, 1.5, 1.5])
        with _gc1:
            secim = st.selectbox(
                "Grafik Seçin", list(grafik_secenekler.keys()),
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
                font=dict(color="#a0c8ff", family="Inter"),
                margin=dict(t=4, b=20, l=50, r=10), height=355,
                xaxis=dict(gridcolor="rgba(0,212,255,0.07)", showgrid=True),
                yaxis=dict(gridcolor="rgba(0,212,255,0.07)", showgrid=True,
                           title=dict(text="kWh", font=dict(size=10))),
            )
            st.plotly_chart(fig, use_container_width=True, config={"displayModeBar": False})

        # ── Tüketim ──
        if grafik_tip == "tuketim":
            _bar_chart(secili_df, tarih_aralik_str)

        # ── Chiller Set Trendi ──
        elif grafik_tip == "chiller":
            if "Chiller_Set_Temp_C" in secili_df.columns and not secili_df.empty:
                st.caption(tarih_aralik_str)
                fig_ch = go.Figure()
                if "Dis_Hava_Sicakligi_C" in secili_df.columns:
                    fig_ch.add_trace(go.Scatter(
                        x=secili_df["Tarih"], y=secili_df["Dis_Hava_Sicakligi_C"],
                        name="Dış Hava", line=dict(color="#f59e0b", width=1.5, dash="dot"),
                        yaxis="y2",
                    ))
                fig_ch.add_trace(go.Scatter(
                    x=secili_df["Tarih"], y=secili_df["Chiller_Set_Temp_C"],
                    name="Chiller Set", line=dict(color=renk, width=2),
                    fill="tozeroy", fillcolor=f"rgba({rr},{rg},{rb},0.07)",
                ))
                fig_ch.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#a0c8ff", family="Inter"),
                    margin=dict(t=10,b=20,l=50,r=50), height=370,
                    xaxis=dict(gridcolor="rgba(0,212,255,0.07)"),
                    yaxis=dict(title=dict(text="Set °C", font=dict(size=10)),
                               gridcolor="rgba(0,212,255,0.07)"),
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
                    font=dict(color="#a0c8ff", family="Inter"),
                    margin=dict(t=10,b=20,l=50,r=10), height=370,
                    xaxis=dict(gridcolor="rgba(0,212,255,0.07)"),
                    yaxis=dict(gridcolor="rgba(0,212,255,0.07)",
                               title=dict(text="kWh/m²", font=dict(size=10))),
                )
                st.plotly_chart(fig_v, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Verimlilik verisi bulunamadı.")

        # ── Su Tüketimi ──
        elif grafik_tip == "su":
            if "Su_Tuketimi_m3" in secili_df.columns and not secili_df.empty:
                st.caption(tarih_aralik_str)
                su_df = secili_df.groupby(secili_df["Tarih"].dt.date)["Su_Tuketimi_m3"].sum().reset_index()
                su_df.columns = ["Tarih", "m3"]
                fig_su = go.Figure(go.Bar(
                    x=su_df["Tarih"], y=su_df["m3"],
                    marker=dict(color="rgba(56,189,248,0.75)"),
                    hovertemplate="<b>%{x}</b><br>%{y:,.1f} m³<extra></extra>",
                ))
                fig_su.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#a0c8ff", family="Inter"),
                    margin=dict(t=10,b=20,l=50,r=10), height=370,
                    xaxis=dict(gridcolor="rgba(0,212,255,0.07)"),
                    yaxis=dict(gridcolor="rgba(0,212,255,0.07)",
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
                    marker=dict(color="rgba(168,85,247,0.75)"),
                    hovertemplate="<b>%{x}</b><br>%{y:,.0f} kWh<extra></extra>",
                ))
                fig_sb.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#a0c8ff", family="Inter"),
                    margin=dict(t=10,b=20,l=50,r=10), height=370,
                    xaxis=dict(gridcolor="rgba(0,212,255,0.07)"),
                    yaxis=dict(gridcolor="rgba(0,212,255,0.07)",
                               title=dict(text="kWh", font=dict(size=10))),
                )
                st.plotly_chart(fig_sb, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Şebeke tüketim verisi bulunamadı.")

        # ── MCC Tüketimi ──
        elif grafik_tip == "mcc":
            if "MCC_Tuketim_kWh" in secili_df.columns and not secili_df.empty:
                st.caption(tarih_aralik_str)
                mcc_df = secili_df.groupby(secili_df["Tarih"].dt.date)["MCC_Tuketim_kWh"].sum().reset_index()
                mcc_df.columns = ["Tarih", "kWh"]
                fig_mcc = go.Figure(go.Bar(
                    x=mcc_df["Tarih"], y=mcc_df["kWh"],
                    marker=dict(color="rgba(249,115,22,0.75)"),
                    hovertemplate="<b>%{x}</b><br>%{y:,.0f} kWh<extra></extra>",
                ))
                fig_mcc.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#a0c8ff", family="Inter"),
                    margin=dict(t=10,b=20,l=50,r=10), height=370,
                    xaxis=dict(gridcolor="rgba(0,212,255,0.07)"),
                    yaxis=dict(gridcolor="rgba(0,212,255,0.07)",
                               title=dict(text="kWh", font=dict(size=10))),
                )
                st.plotly_chart(fig_mcc, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("MCC tüketim verisi bulunamadı.")

        # ── Kazan Doğalgaz ──
        elif grafik_tip == "kazan":
            if "Kazan_Dogalgaz_m3" in secili_df.columns and not secili_df.empty:
                st.caption(tarih_aralik_str)
                kaz_df = secili_df.groupby(secili_df["Tarih"].dt.date)["Kazan_Dogalgaz_m3"].sum().reset_index()
                kaz_df.columns = ["Tarih", "m3"]
                fig_kaz = go.Figure(go.Bar(
                    x=kaz_df["Tarih"], y=kaz_df["m3"],
                    marker=dict(color="rgba(239,68,68,0.75)"),
                    hovertemplate="<b>%{x}</b><br>%{y:,.1f} m³<extra></extra>",
                ))
                fig_kaz.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#a0c8ff", family="Inter"),
                    margin=dict(t=10,b=20,l=50,r=10), height=370,
                    xaxis=dict(gridcolor="rgba(0,212,255,0.07)"),
                    yaxis=dict(gridcolor="rgba(0,212,255,0.07)",
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
                    font=dict(color="#a0c8ff", family="Inter"),
                    margin=dict(t=30,b=20,l=50,r=10), height=370,
                    xaxis=dict(gridcolor="rgba(0,212,255,0.07)", title="Gün"),
                    yaxis=dict(gridcolor="rgba(0,212,255,0.07)", title=dict(text="kWh", font=dict(size=10))),
                    barmode="group",
                    legend=dict(orientation="h", y=1.1, font=dict(size=10)),
                )
                # Toplam fark özeti
                bu_top  = bu_gun.sum()
                gec_top = gec_gun.sum()
                if gec_top > 0:
                    fark_pct = (bu_top - gec_top) / gec_top * 100
                    fark_renk = "#ef4444" if fark_pct > 0 else "#10b981"
                    fark_yon  = "▲" if fark_pct > 0 else "▼"
                    st.markdown(
                        f"<div style='text-align:center;font-size:11px;color:{fark_renk};margin-bottom:4px;'>"
                        f"{fark_yon} Bu ay şimdiye kadar geçen aya göre <b>{abs(fark_pct):.1f}%</b> "
                        f"{'fazla' if fark_pct>0 else 'az'} tüketim</div>",
                        unsafe_allow_html=True
                    )
                st.plotly_chart(fig_ay, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Ay karşılaştırma verisi bulunamadı.")

        # ── Doğalgaz Verimliliği ──
        elif grafik_tip == "dogalgaz_verim":
            has_kojen = "Kojen_Uretim_kWh" in secili_df.columns and "Kojen_Dogalgaz_m3" in secili_df.columns
            has_kazan = "Kazan_Dogalgaz_m3" in secili_df.columns and "Toplam_Hastane_Tuketim_kWh" in secili_df.columns
            if (has_kojen or has_kazan) and not secili_df.empty:
                st.caption(tarih_aralik_str)
                fig_dv = go.Figure()
                if has_kojen:
                    kj_g = secili_df.groupby(secili_df["Tarih"].dt.date)[["Kojen_Uretim_kWh","Kojen_Dogalgaz_m3"]].sum().reset_index()
                    kj_g["verim"] = kj_g.apply(
                        lambda r: r["Kojen_Uretim_kWh"]/r["Kojen_Dogalgaz_m3"] if r["Kojen_Dogalgaz_m3"]>0 else None, axis=1
                    )
                    fig_dv.add_trace(go.Scatter(
                        x=kj_g["Tarih"], y=kj_g["verim"],
                        name="Kojen (kWh/m³)", line=dict(color="#10b981", width=2),
                        hovertemplate="<b>%{x}</b><br>%{y:.2f} kWh/m³<extra></extra>",
                    ))
                if has_kazan:
                    kz_g = secili_df.groupby(secili_df["Tarih"].dt.date)[["Toplam_Hastane_Tuketim_kWh","Kazan_Dogalgaz_m3"]].sum().reset_index()
                    kz_g["verim"] = kz_g.apply(
                        lambda r: r["Toplam_Hastane_Tuketim_kWh"]/r["Kazan_Dogalgaz_m3"] if r["Kazan_Dogalgaz_m3"]>0 else None, axis=1
                    )
                    fig_dv.add_trace(go.Scatter(
                        x=kz_g["Tarih"], y=kz_g["verim"],
                        name="Kazan (kWh/m³)", line=dict(color="#ef4444", width=2, dash="dot"),
                        hovertemplate="<b>%{x}</b><br>%{y:.2f} kWh/m³<extra></extra>",
                    ))
                fig_dv.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#a0c8ff", family="Inter"),
                    margin=dict(t=10,b=20,l=50,r=10), height=370,
                    xaxis=dict(gridcolor="rgba(0,212,255,0.07)"),
                    yaxis=dict(gridcolor="rgba(0,212,255,0.07)",
                               title=dict(text="kWh / m³ gaz", font=dict(size=10))),
                    legend=dict(orientation="h", y=1.1, font=dict(size=10)),
                )
                st.plotly_chart(fig_dv, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Doğalgaz verimlilik verisi bulunamadı.")

        # ── KPI Özet Scorecard (seçilen tarih aralığı) ──
        elif grafik_tip == "kpi_ozet":
            kpi_rows = []
            _kd = secili_df  # KPI için seçilen tarih aralığı
            _etiket = tarih_aralik_str
            if "Toplam_Hastane_Tuketim_kWh" in _kd.columns:
                kpi_rows.append((f"⚡ Elektrik Tüketimi ({_etiket})", f"{_kd['Toplam_Hastane_Tuketim_kWh'].sum():,.0f} kWh", "#00d4ff"))
            if "Kojen_Uretim_kWh" in _kd.columns:
                kpi_rows.append((f"⚙️ Kojen Üretimi ({_etiket})", f"{_kd['Kojen_Uretim_kWh'].sum():,.0f} kWh", "#10b981"))
            if "Kojen_Uretim_kWh" in _kd.columns and "Toplam_Hastane_Tuketim_kWh" in _kd.columns:
                top = _kd["Toplam_Hastane_Tuketim_kWh"].sum()
                ko  = _kd["Kojen_Uretim_kWh"].sum()
                if top > 0:
                    kpi_rows.append(("⚙️ Kojen Karşılama Oranı", f"%{ko/top*100:.1f}", "#10b981"))
            if "Kojen_Dogalgaz_m3" in _kd.columns:
                kpi_rows.append((f"🔥 Kojen Doğalgaz ({_etiket})", f"{_kd['Kojen_Dogalgaz_m3'].sum():,.1f} m³", "#f97316"))
            if "Kazan_Dogalgaz_m3" in _kd.columns:
                kpi_rows.append((f"🏭 Kazan Doğalgaz ({_etiket})", f"{_kd['Kazan_Dogalgaz_m3'].sum():,.1f} m³", "#ef4444"))
            if "Su_Tuketimi_m3" in _kd.columns:
                kpi_rows.append((f"💧 Su Tüketimi ({_etiket})", f"{_kd['Su_Tuketimi_m3'].sum():,.1f} m³", "#38bdf8"))
            if "Sebeke_Tuketim_kWh" in _kd.columns:
                kpi_rows.append((f"🔌 Şebeke Tüketimi ({_etiket})", f"{_kd['Sebeke_Tuketim_kWh'].sum():,.0f} kWh", "#a855f7"))
            if "MCC_Tuketim_kWh" in _kd.columns:
                kpi_rows.append((f"🏗️ MCC Tüketimi ({_etiket})", f"{_kd['MCC_Tuketim_kWh'].sum():,.0f} kWh", "#f59e0b"))
            if m2 and "Toplam_Hastane_Tuketim_kWh" in _kd.columns and _kd["Toplam_Hastane_Tuketim_kWh"].sum() > 0:
                kpi_rows.append((f"📐 kWh/m² ({_etiket})", f"{_kd['Toplam_Hastane_Tuketim_kWh'].sum()/m2:.2f}", "#f59e0b"))

            if kpi_rows:
                rows_html = ""
                for baslik, deger, renk_hex in kpi_rows:
                    r2=int(renk_hex[1:3],16); g2=int(renk_hex[3:5],16); b2=int(renk_hex[5:7],16)
                    rows_html += (
                        f"<div style='display:flex;justify-content:space-between;align-items:center;"
                        f"padding:10px 14px;border-bottom:1px solid rgba(0,212,255,0.07);'>"
                        f"<span style='font-size:12px;color:rgba(180,220,255,0.8);'>{baslik}</span>"
                        f"<span style='font-family:Orbitron,sans-serif;font-size:13px;font-weight:700;"
                        f"color:{renk_hex};text-shadow:0 0 8px rgba({r2},{g2},{b2},0.5);'>{deger}</span>"
                        f"</div>"
                    )
                st.markdown(
                    f"<div style='background:rgba(0,15,40,0.7);border:1px solid rgba(0,212,255,0.12);"
                    f"border-radius:12px;overflow:hidden;'>{rows_html}</div>",
                    unsafe_allow_html=True
                )
            else:
                st.info("KPI verisi bulunamadı.")

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
                        name="Kojen Üretim", marker=dict(color="rgba(16,185,129,0.75)"),
                        hovertemplate="<b>%{x}</b><br>%{y:,.0f} kWh<extra></extra>",
                    ))
                if "Kojen_Dogalgaz_m3" in secili_df.columns:
                    kg_df = secili_df.groupby(secili_df["Tarih"].dt.date)["Kojen_Dogalgaz_m3"].sum().reset_index()
                    kg_df.columns = ["Tarih", "m3"]
                    fig_kj.add_trace(go.Scatter(
                        x=kg_df["Tarih"], y=kg_df["m3"],
                        name="Doğalgaz (m³)", line=dict(color="#f59e0b", width=2),
                        yaxis="y2",
                        hovertemplate="<b>%{x}</b><br>%{y:,.1f} m³<extra></extra>",
                    ))
                fig_kj.update_layout(
                    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
                    font=dict(color="#a0c8ff", family="Inter"),
                    margin=dict(t=10,b=20,l=50,r=50), height=370,
                    xaxis=dict(gridcolor="rgba(0,212,255,0.07)"),
                    yaxis=dict(gridcolor="rgba(0,212,255,0.07)",
                               title=dict(text="kWh", font=dict(size=10))),
                    yaxis2=dict(title=dict(text="m³", font=dict(size=10)),
                                overlaying="y", side="right"),
                    legend=dict(orientation="h", y=1.12, font=dict(size=10)),
                    barmode="group",
                )
                st.plotly_chart(fig_kj, use_container_width=True, config={"displayModeBar": False})
            else:
                st.info("Kojen verisi bulunamadı.")

    # ──────────── SÜTUN 3: Kojen Doğalgaz & Kaynak Verileri ────────────
    with col_right:
        st.markdown('<div class="sec">⚙️ KOJEN & KAYNAK</div>', unsafe_allow_html=True)

        def info_card(ikon, baslik, deger, birim, renk_hex):
            r2=int(renk_hex[1:3],16); g2=int(renk_hex[3:5],16); b2=int(renk_hex[5:7],16)
            st.markdown(
                f"""<div class="metric-card" style="margin-bottom:10px;">
                <div style='font-size:16px;margin-bottom:2px;'>{ikon}</div>
                <div style='font-size:8px;color:rgba(150,210,255,0.5);letter-spacing:1px;
                            text-transform:uppercase;margin-bottom:4px;'>{baslik}</div>
                <div style='font-family:Orbitron,sans-serif;font-size:15px;font-weight:900;
                            color:{renk_hex};text-shadow:0 0 10px rgba({r2},{g2},{b2},0.6);'>
                    {deger}<span style='font-size:8px;color:rgba(150,210,255,0.5);margin-left:3px;'>{birim}</span>
                </div></div>""",
                unsafe_allow_html=True
            )

        kgaz_str   = f"{kojen_gaz:,.1f}"  if kojen_gaz  is not None else "—"
        kurt_str   = f"{kojen_urt:,.0f}"  if kojen_urt  is not None else "—"
        kzan_str   = f"{kazan_gaz:,.1f}"  if kazan_gaz  is not None else "—"
        su_str     = f"{su_tuk:,.1f}"     if su_tuk     is not None else "—"
        sebeke_str = f"{sebeke_tuk:,.0f}" if sebeke_tuk is not None else "—"
        mcc_str    = f"{mcc_tuk:,.0f}"    if mcc_tuk   is not None else "—"

        info_card("🔥", "Kojen Doğalgaz", kgaz_str,   "m³",  "#f97316")
        info_card("⚙️", "Kojen Üretim",  kurt_str,   "kWh", "#10b981")
        info_card("🏭", "Kazan Doğalgaz", kzan_str,   "m³",  "#ef4444")
        info_card("💧", "Su Tüketimi",    su_str,     "m³",  "#38bdf8")
        info_card("🔌", "Şebeke Tüketim", sebeke_str, "kWh", "#a855f7")
        info_card("🏗️", "MCC Tüketim",   mcc_str,    "kWh", "#f59e0b")

    # ══════════════════════════════════════════════════════
    # HVAC & BAKIM DURUMU
    # ══════════════════════════════════════════════════════
    st.markdown("<div style='margin-top:18px'></div>", unsafe_allow_html=True)
    st.markdown('<div class="sec">🔧 HVAC & BAKIM DURUMU</div>', unsafe_allow_html=True)

    arizali_list = bakim_ozet.get("arizali_cihazlar", [])
    bakim_list   = bakim_ozet.get("bakim_cihazlari", [])
    toplam_ariza = bakim_ozet.get("toplam_ariza", 0)
    toplam_bakim = bakim_ozet.get("toplam_bakim", 0)
    hvac_kritik  = hvac_ozet.get("kritik", [])
    hvac_uyari   = hvac_ozet.get("uyari",  [])
    hvac_normal  = hvac_ozet.get("normal", [])

    KART  = "background:rgba(0,15,40,0.6);border-radius:12px;padding:14px;"
    LBL   = ("font-size:8px;color:rgba(150,210,255,0.5);letter-spacing:1.5px;"
             "text-transform:uppercase;margin-bottom:8px;font-weight:700;")

    def cihaz_html(cihaz, bg, border, text_renk):
        if isinstance(cihaz, dict):
            ad  = cihaz.get("ad", cihaz.get("name", str(cihaz)))
            det = cihaz.get("detay", cihaz.get("ariza", cihaz.get("bakim_turu", "")))
        else:
            ad, det = str(cihaz), ""
        det_part = (
            "<div style='font-size:10px;color:rgba(255,255,255,0.45);"
            "margin-top:2px;padding-left:14px;'>" + det + "</div>"
        ) if det else ""
        return (
            "<div style='background:" + bg + ";border-left:3px solid " + border + ";"
            "border-radius:6px;padding:8px 12px;margin-bottom:6px;'>"
            "<span style='font-size:12px;color:" + text_renk + ";font-weight:600;'>"
            + chr(9679) + " " + ad + "</span>"
            + det_part +
            "</div>"
        )

    def hvac_satir_html(cihaz, bg, border, badge_renk, badge_text, text_renk):
        if isinstance(cihaz, dict):
            ad  = cihaz.get("ad", str(cihaz))
            det = cihaz.get("sorun", "")
        else:
            ad, det = str(cihaz), ""
        det_part = (
            "<div style='font-size:10px;color:rgba(255,255,255,0.4);"
            "margin-top:3px;'>" + det + "</div>"
        ) if det else ""
        return (
            "<div style='background:" + bg + ";border:1px solid " + border + ";"
            "border-radius:7px;padding:8px 12px;margin-bottom:6px;'>"
            "<div style='display:flex;align-items:center;gap:10px;'>"
            "<span style='font-size:9px;font-weight:700;letter-spacing:1px;"
            "color:" + badge_renk + ";min-width:52px;'>" + badge_text + "</span>"
            "<span style='font-size:12px;color:" + text_renk + ";font-weight:600;'>"
            + ad + "</span></div>" + det_part + "</div>"
        )

    col_ar, col_bk, col_hv = st.columns([1, 1, 2])

    # ── Sütun 1: Arızalı ──────────────────────────
    with col_ar:
        ar_renk = "#ef4444" if toplam_ariza > 0 else "#10b981"
        rows = "".join(
            cihaz_html(c, "rgba(239,68,68,0.10)", "#ef4444", "#fca5a5")
            for c in arizali_list
        ) if arizali_list else (
            "<div style='font-size:11px;color:#6ee7b7;padding:4px 0;'>Ariza yok</div>"
        )
        st.markdown(
            "<details style='" + KART + "border:1px solid rgba(239,68,68,0.25);cursor:pointer;'>"
            "<summary style='list-style:none;outline:none;'>"
            "<div style='" + LBL + "'>ARIZALI CIHAZLAR</div>"
            "<div style='font-family:Orbitron,sans-serif;font-size:28px;font-weight:900;"
            "color:" + ar_renk + ";margin-bottom:4px;'>" + str(toplam_ariza) + "</div>"
            "<div style='font-size:9px;color:rgba(150,210,255,0.4);margin-bottom:4px;'>▼ detay için tıkla</div>"
            "</summary>"
            "<div style='margin-top:8px;'>" + rows + "</div>"
            "</details>",
            unsafe_allow_html=True
        )

    # ── Sütun 2: Bakımda ──────────────────────────
    with col_bk:
        bk_renk = "#f59e0b" if toplam_bakim > 0 else "#10b981"
        rows = "".join(
            cihaz_html(c, "rgba(245,158,11,0.10)", "#f59e0b", "#fcd34d")
            for c in bakim_list
        ) if bakim_list else (
            "<div style='font-size:11px;color:rgba(150,210,255,0.5);padding:4px 0;'>Cihaz listesi girilmemiş</div>"
        )
        st.markdown(
            "<details style='" + KART + "border:1px solid rgba(245,158,11,0.25);cursor:pointer;'>"
            "<summary style='list-style:none;outline:none;'>"
            "<div style='" + LBL + "'>BAKIMDAKI CIHAZLAR</div>"
            "<div style='font-family:Orbitron,sans-serif;font-size:28px;font-weight:900;"
            "color:" + bk_renk + ";margin-bottom:4px;'>" + str(toplam_bakim) + "</div>"
            "<div style='font-size:9px;color:rgba(150,210,255,0.4);margin-bottom:4px;'>▼ detay için tıkla</div>"
            "</summary>"
            "<div style='margin-top:8px;'>" + rows + "</div>"
            "</details>",
            unsafe_allow_html=True
        )

    # ── Sütun 3: HVAC Analiz ──────────────────────
    with col_hv:
        if hvac_kritik or hvac_uyari:
            hv_rows = "".join(
                hvac_satir_html(c, "rgba(239,68,68,0.08)", "rgba(239,68,68,0.35)",
                                "#ef4444", "KRITIK", "#fca5a5")
                for c in hvac_kritik
            ) + "".join(
                hvac_satir_html(c, "rgba(245,158,11,0.08)", "rgba(245,158,11,0.30)",
                                "#f59e0b", "UYARI", "#fcd34d")
                for c in hvac_uyari
            )
            if hvac_normal:
                hv_rows += (
                    "<div style='font-size:11px;color:#6ee7b7;padding:4px 0;'>"
                    + str(len(hvac_normal)) + " cihaz normal</div>"
                )
        elif arizali_list:
            hv_rows = "".join(
                hvac_satir_html(c, "rgba(239,68,68,0.08)", "rgba(239,68,68,0.35)",
                                "#ef4444", "KRITIK", "#fca5a5")
                for c in arizali_list
            )
        else:
            hv_rows = (
                "<div style='background:rgba(16,185,129,0.08);"
                "border:1px solid rgba(16,185,129,0.2);"
                "border-radius:8px;padding:14px;text-align:center;'>"
                "<div style='font-size:18px;margin-bottom:4px;'>&#10003;</div>"
                "<div style='font-size:12px;color:#6ee7b7;'>Tum HVAC sistemleri normal</div>"
                "</div>"
            )
        st.markdown(
            "<div style='" + KART + "border:1px solid rgba(0,212,255,0.12);'>"
            "<div style='" + LBL + "'>HVAC ANALIZ DURUMU</div>"
            + hv_rows + "</div>",
            unsafe_allow_html=True
        )


# ════════ TAB 2: TREND & TAHMİN ════════
with tab2:
    st.markdown('<div class="sec">📈 YILLIK TÜKETİM TRENDİ</div>', unsafe_allow_html=True)
    if "Toplam_Hastane_Tuketim_kWh" in df.columns and not df.empty:
        df["yil"] = df["Tarih"].dt.year
        df["ay"]  = df["Tarih"].dt.month
        yillik = df.groupby(["yil","ay"])["Toplam_Hastane_Tuketim_kWh"].sum().reset_index()
        fig_tr = go.Figure()
        for yil in sorted(yillik["yil"].unique()):
            yd = yillik[yillik["yil"]==yil]
            opasite = 0.5 if yil < now.year else 1.0
            fig_tr.add_trace(go.Scatter(
                x=yd["ay"], y=yd["Toplam_Hastane_Tuketim_kWh"],
                name=str(yil),
                line=dict(width=2 if yil==now.year else 1.5),
                opacity=opasite,
                mode="lines+markers",
                hovertemplate=f"{yil} Ay %{{x}}: %{{y:,.0f}} kWh<extra></extra>",
            ))
        fig_tr.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#a0c8ff", family="Inter"),
            margin=dict(t=10,b=30,l=60,r=10), height=300,
            xaxis=dict(gridcolor="rgba(0,212,255,0.07)", tickvals=list(range(1,13)),
                       ticktext=["Oca","Şub","Mar","Nis","May","Haz","Tem","Ağu","Eyl","Eki","Kas","Ara"]),
            yaxis=dict(gridcolor="rgba(0,212,255,0.07)",
                       title=dict(text="kWh", font=dict(size=10))),
            legend=dict(orientation="h", y=1.1, font=dict(size=11)),
        )
        st.plotly_chart(fig_tr, use_container_width=True, config={"displayModeBar": False})
    else:
        st.info("Trend verisi bulunamadı.")

    # kWh/m² aylık verimlilik
    st.markdown('<div class="sec">📐 AYLIK kWh/m² VERİMLİLİK</div>', unsafe_allow_html=True)
    if "Toplam_Hastane_Tuketim_kWh" in df.columns:
        verim_df = df.groupby(df["Tarih"].dt.to_period("M"))["Toplam_Hastane_Tuketim_kWh"].sum().reset_index()
        verim_df.columns = ["Donem","kWh"]
        verim_df["Donem"] = verim_df["Donem"].astype(str)
        verim_df["kWhm2"] = verim_df["kWh"] / m2
        fig_v = go.Figure(go.Bar(
            x=verim_df["Donem"], y=verim_df["kWhm2"],
            marker=dict(color=f"rgba({rr},{rg},{rb},0.7)"),
            hovertemplate="<b>%{x}</b><br>%{y:.2f} kWh/m²<extra></extra>",
        ))
        fig_v.update_layout(
            paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
            font=dict(color="#a0c8ff", family="Inter"),
            margin=dict(t=10,b=30,l=50,r=10), height=220,
            xaxis=dict(gridcolor="rgba(0,212,255,0.07)"),
            yaxis=dict(gridcolor="rgba(0,212,255,0.07)",
                       title=dict(text="kWh/m²", font=dict(size=10))),
        )
        st.plotly_chart(fig_v, use_container_width=True, config={"displayModeBar": False})

# ════════ TAB 3: VERİ TABLOSU ════════
with tab3:
    st.markdown('<div class="sec">📋 VERİ TABLOSU</div>', unsafe_allow_html=True)
    col_f1, col_f2 = st.columns([1,1])
    with col_f1:
        bas = st.date_input("Başlangıç", value=(now - timedelta(days=30)).date(), key="dt_bas")
    with col_f2:
        bit = st.date_input("Bitiş", value=now.date(), key="dt_bit")

    filtre = df[(df["Tarih"].dt.date >= bas) & (df["Tarih"].dt.date <= bit)].copy()
    filtre["Tarih"] = filtre["Tarih"].dt.strftime("%Y-%m-%d")

    goster_cols = [c for c in [
        "Tarih","Chiller_Set_Temp_C","Chiller_Adet","Dis_Hava_Sicakligi_C",
        "Toplam_Hastane_Tuketim_kWh","Toplam_Sogutma_Tuketim_kWh",
        "Sebeke_Tuketim_kWh","MCC_Tuketim_kWh","Kojen_Uretim_kWh",
        "Kazan_Dogalgaz_m3","Su_Tuketimi_m3",
    ] if c in filtre.columns]

    st.markdown(f"<div style='font-size:11px;color:rgba(150,210,255,0.5);margin-bottom:8px;'>{len(filtre)} kayıt</div>", unsafe_allow_html=True)
    st.dataframe(filtre[goster_cols].sort_values("Tarih", ascending=False),
                 use_container_width=True, hide_index=True, height=450)

# ════════ TAB 4: RAPOR OLUŞTUR ════════
with tab4:
    st.markdown("<div style='height:40px'></div>", unsafe_allow_html=True)
    st.markdown(
        f"""<div style='text-align:center;padding:40px;
            background:rgba(0,20,50,0.6);border:1px solid rgba(0,212,255,0.15);
            border-radius:16px;max-width:500px;margin:0 auto;'>
            <div style='font-size:48px;margin-bottom:16px;'>📄</div>
            <div style='font-family:Orbitron,sans-serif;font-size:14px;font-weight:700;
                color:{renk};letter-spacing:2px;margin-bottom:8px;'>RAPOR OLUŞTUR</div>
            <div style='font-size:12px;color:rgba(150,210,255,0.6);margin-bottom:24px;'>
                {lok_info["isim"]} için aylık enerji raporu oluşturun
            </div>
        </div>""",
        unsafe_allow_html=True
    )
    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
    col_c1, col_c2, col_c3 = st.columns([2, 2, 2])
    with col_c2:
        if st.button("📄 Rapor Oluştur", use_container_width=True, key="rapor_btn"):
            st.session_state["rapor_lokasyon"] = lok_id
            st.switch_page("pages/rapor_olustur.py")
