# app.py
# Enerji Yönetimi & Raporlama Sistemi (Streamlit + Pandas + Plotly + fpdf2)
# - Excel toplu import: Tarih bazlı UPSERT
# - Esnek sütun eşleştirme (TR/EN, büyük-küçük, boşluk vs.)
# - Veri görüntüleme (binlerce satır)
# - Grafiklerde yıl/ay bazlı slider + Günlük/Aylık/Yıllık
# - PDF Unicode font fix (Türkçe karakterler güvenli)

from __future__ import annotations

import os
import re
import io
import tempfile
from pathlib import Path
from datetime import date

import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.io as pio

from fpdf import FPDF

st.set_page_config(page_title="Enerji Yönetimi & Raporlama", layout="wide")

# Custom Dark Theme CSS
st.markdown("""
<style>
    /* Dark theme for Streamlit */
    .stApp {
        background: linear-gradient(-45deg, #0a0e1a, #012D75, #1a2332, #1a4a9e);
        background-size: 400% 400%;
        animation: gradient 15s ease infinite;
    }
    
    @keyframes gradient {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    
    /* Glassmorphism for containers */
    .stTabs [data-baseweb="tab-panel"] {
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(20px);
        border-radius: 16px;
        padding: 24px;
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
    
    /* Metrics styling */
    [data-testid="stMetricValue"] {
        color: #ffffff !important;
        font-size: 32px !important;
        font-weight: 800 !important;
    }
    
    [data-testid="stMetricLabel"] {
        color: rgba(255, 255, 255, 0.7) !important;
        font-weight: 600 !important;
    }
    
    [data-testid="stMetricDelta"] {
        color: rgba(255, 255, 255, 0.9) !important;
    }
    
    /* Headers */
    h1, h2, h3, h4, h5, h6 {
        color: #ffffff !important;
        font-family: 'Inter', sans-serif !important;
    }
    
    /* Text */
    p, span, div {
        color: rgba(255, 255, 255, 0.9) !important;
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(10px);
        border-radius: 12px;
        padding: 8px;
        gap: 8px;
    }
    
    .stTabs [data-baseweb="tab"] {
        background: transparent;
        color: rgba(255, 255, 255, 0.7);
        border-radius: 8px;
        font-weight: 600;
    }
    
    .stTabs [aria-selected="true"] {
        background: rgba(255, 255, 255, 0.2) !important;
        color: #ffffff !important;
    }
    
    /* Buttons */
    .stButton > button {
        background: linear-gradient(135deg, #012D75, #1a4a9e);
        color: white;
        border: none;
        border-radius: 10px;
        font-weight: 700;
        padding: 12px 24px;
        transition: all 0.3s;
    }
    
    .stButton > button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.4);
    }
    
    /* Input fields - Gri tonları, yumuşak beyaz yazı */
    .stTextInput > div > div > input,
    .stSelectbox > div > div > select,
    .stDateInput > div > div > input,
    .stNumberInput > div > div > input {
        background: rgba(60, 70, 90, 0.8) !important;
        color: #f0f0f0 !important;
        border: 1px solid rgba(255, 255, 255, 0.25) !important;
        border-radius: 10px !important;
    }
    
    /* Selectbox dropdown - Gri tonları */
    div[data-baseweb="select"] > div {
        background: rgba(60, 70, 90, 0.8) !important;
        color: #f0f0f0 !important;
        border: 1px solid rgba(255, 255, 255, 0.25) !important;
        border-radius: 10px !important;
    }
    
    /* Dropdown menu */
    ul[data-baseweb="menu"] {
        background: rgba(40, 50, 70, 0.95) !important;
    }
    
    ul[data-baseweb="menu"] li {
        color: #f0f0f0 !important;
    }
    
    /* Input labels */
    .stTextInput label, .stSelectbox label, .stNumberInput label, .stDateInput label {
        color: #d0d0d0 !important;
    }
    
    /* Placeholder */
    ::placeholder {
        color: rgba(255, 255, 255, 0.5) !important;
    }
    
    /* Dataframe - Enhanced for readability */
    .stDataFrame {
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(20px);
        border-radius: 12px;
        border: 1px solid rgba(255, 255, 255, 0.2);
    }
    
    /* Dataframe table styling - Yumuşak beyaz yazılar */
    .stDataFrame table,
    div[data-testid="stDataFrame"] table,
    .dataframe {
        font-size: 14px !important;
        color: #e8e8e8 !important;
    }
    
    /* Dataframe headers - Koyu mavi arka plan, beyaz yazı */
    .stDataFrame thead tr th,
    div[data-testid="stDataFrame"] thead tr th,
    .dataframe thead tr th {
        background-color: rgba(1, 45, 117, 0.9) !important;
        color: #ffffff !important;
        font-weight: 700 !important;
        font-size: 13px !important;
        padding: 12px 8px !important;
        border-bottom: 2px solid rgba(255, 255, 255, 0.2) !important;
        text-align: left !important;
        min-width: 100px !important;
    }
    
    /* Dataframe cells - BEYAZ arka plan, SİYAH yazı */
    .stDataFrame tbody tr td,
    div[data-testid="stDataFrame"] tbody tr td,
    .dataframe tbody tr td {
        color: #1a1a1a !important;
        background-color: #ffffff !important;
        padding: 10px 8px !important;
        border-bottom: 1px solid rgba(0, 0, 0, 0.1) !important;
        font-size: 13px !important;
        min-width: 100px !important;
    }
    
    /* Override nested elements in cells - SİYAH yazı */
    .stDataFrame tbody tr td *,
    div[data-testid="stDataFrame"] tbody tr td *,
    .dataframe tbody tr td * {
        color: #1a1a1a !important;
    }
    
    /* GÜÇLÜ OVERRIDE - Tüm data elements */
    [data-testid="stDataFrame"] td,
    [data-testid="stDataFrame"] td span,
    [data-testid="stDataFrame"] td div,
    [data-testid="stDataFrame"] .dvn-scroller td,
    .dvn-scroller td,
    .glideDataEditor td,
    [data-testid="glide-data-grid-canvas"] {
        color: #1a1a1a !important;
        background-color: #ffffff !important;
    }
    
    /* Data grid text */
    .dvn-cell,
    .dvn-cell span,
    .gdg-cell {
        color: #1a1a1a !important;
    }
    
    /* Dataframe row hover */
    .stDataFrame tbody tr:hover,
    div[data-testid="stDataFrame"] tbody tr:hover,
    .dataframe tbody tr:hover {
        background-color: rgba(255, 255, 255, 0.1) !important;
    }
    
    /* Dataframe scrollbar */
    .stDataFrame ::-webkit-scrollbar {
        height: 10px;
        width: 10px;
    }
    
    .stDataFrame ::-webkit-scrollbar-track {
        background: rgba(0, 0, 0, 0.05);
        border-radius: 5px;
    }
    
    .stDataFrame ::-webkit-scrollbar-thumb {
        background: rgba(1, 45, 117, 0.6);
        border-radius: 5px;
    }
    
    .stDataFrame ::-webkit-scrollbar-thumb:hover {
        background: rgba(1, 45, 117, 0.8);
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: rgba(10, 14, 26, 0.95);
        backdrop-filter: blur(20px);
        border-right: 1px solid rgba(255, 255, 255, 0.1);
    }
    
    /* File uploader */
    [data-testid="stFileUploader"] {
        background: rgba(255, 255, 255, 0.05);
        border: 2px dashed rgba(255, 255, 255, 0.3);
        border-radius: 12px;
        padding: 20px;
    }
    
    /* Expander */
    .streamlit-expanderHeader {
        background: rgba(255, 255, 255, 0.1);
        backdrop-filter: blur(10px);
        border-radius: 10px;
        color: white !important;
    }
</style>
""", unsafe_allow_html=True)

# ---- Portal navigasyon (HVAC / Enerji ana menü) ----
PORTAL_URL = os.environ.get("PORTAL_URL", "http://localhost:8005/")

# ─── Lokasyon Yönetimi ───
from location_manager import get_manager as get_location_manager
_loc_mgr = get_location_manager()
_loc_mgr.ensure_locations_ready()  # Migration + profil oluşturma
_loc_config = _loc_mgr.get_location_config()

# Sidebar lokasyon seçici
_all_locations = _loc_mgr.list_locations()
_active_loc = _loc_mgr.get_active_location_id()
_loc_names = {loc['id']: loc['short_name'] for loc in _all_locations}
_loc_options = list(_loc_names.keys())
_loc_labels = [f"📍 {_loc_names[lid]}" for lid in _loc_options]

with st.sidebar:
    _selected_idx = _loc_options.index(_active_loc) if _active_loc in _loc_options else 0
    _selected_loc = st.selectbox(
        "🏥 Lokasyon", _loc_options, index=_selected_idx,
        format_func=lambda x: f"📍 {_loc_names.get(x, x)}",
        key="location_selector"
    )
    if _selected_loc != _active_loc:
        _loc_mgr.set_active_location(_selected_loc)
        st.cache_data.clear()  # Lokasyon değiştiğinde veri cache'i temizle
        st.rerun()

st.markdown(
    f"""
    <div style='display:flex; justify-content:space-between; align-items:center; gap:12px; margin: 0 0 10px 0;'>
      <div style='font-weight:800; font-size:14px; letter-spacing:0.4px; color:#ffffff; text-transform:uppercase;'>{_loc_config.get('name', 'ACIBADEM SAĞLIK GRUBU')}</div>
      <a href='{PORTAL_URL}' target='_top' style='text-decoration:none; font-weight:800; color:#ffffff;'>⬅ Ana Sayfa</a>
    </div>
    """,
    unsafe_allow_html=True,
)

# Lokasyon bazlı veri dosyası
DATA_FILE = _loc_mgr.get_data_path("energy_data.csv")

# Lokasyona göre sıcaklık sütunları
_energy_schema = _loc_config.get("energy_schema", {})
_has_dual_lines = bool(_energy_schema.get("heating_lines", []))

# Sıcaklık sütunları: Maslak=Mas1+Mas2, Altunizade=tek hat
if _has_dual_lines:
    _TEMP_COLS_SCHEMA = [
        "Mas1_Isitma_Temp", "Mas1_Kazan_Temp", "Mas1_Sogutma_Temp",
        "Mas2_Isitma_Temp", "Mas2_Kazan_Temp", "Mas2_Sogutma_Temp",
    ]
else:
    _TEMP_COLS_SCHEMA = [
        "Isitma_Temp_C", "Kazan_Temp_C", "Sogutma_Temp_C",
    ]

SCHEMA = [
    "Tarih",
    "Chiller_Set_Temp_C",
    "Chiller_Adet",
    "Absorption_Chiller_Adet",
    "Kazan_Adet",
] + _TEMP_COLS_SCHEMA + [
    "Kar_Eritme_Aktif",
    "Sebeke_Tuketim_kWh",
    "Kojen_Uretim_kWh",
    "Kazan_Dogalgaz_m3",
    "Kojen_Dogalgaz_m3",
    "Su_Tuketimi_m3",
    "Chiller_Tuketim_kWh",
    "MCC_Tuketim_kWh",
    "VRF_Split_Tuketim_kWh",
    "Dis_Hava_Sicakligi_C",
    "Toplam_Hastane_Tuketim_kWh",
    "Toplam_Sogutma_Tuketim_kWh",
    "Diger_Yuk_kWh",
]

NUMERIC_COLS = [
    "Chiller_Set_Temp_C",
    "Chiller_Adet",
    "Absorption_Chiller_Adet",
    "Kazan_Adet",
] + _TEMP_COLS_SCHEMA + [
    "Sebeke_Tuketim_kWh",
    "Kojen_Uretim_kWh",
    "Kazan_Dogalgaz_m3",
    "Kojen_Dogalgaz_m3",
    "Su_Tuketimi_m3",
    "Chiller_Tuketim_kWh",
    "MCC_Tuketim_kWh",
    "VRF_Split_Tuketim_kWh",
    "Dis_Hava_Sicakligi_C",
    "Toplam_Hastane_Tuketim_kWh",
    "Toplam_Sogutma_Tuketim_kWh",
    "Diger_Yuk_kWh",
]

TR_MAP = str.maketrans({
    "ş": "s", "Ş": "s",
    "ı": "i", "İ": "i",
    "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u",
    "ö": "o", "Ö": "o",
    "ç": "c", "Ç": "c",
})


def norm_key(s: str) -> str:
    if s is None:
        return ""
    s = str(s).strip().replace("\u00a0", " ")
    s = s.translate(TR_MAP).lower()
    s = re.sub(r"[\s\-\_\/\(\)\[\]\{\}\.\,\:\;\|]+", " ", s)
    s = re.sub(r"[^a-z0-9 ]+", "", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def infer_canonical_col(col_name: str) -> str | None:
    k = norm_key(col_name)

    if "tarih" in k or k == "date" or "date" in k:
        return "Tarih"

    if ("kar" in k and ("erit" in k or "erime" in k)) or ("snow" in k and "melt" in k):
        return "Kar_Eritme_Aktif"

    if (("dis" in k and "hava" in k) or "outdoor" in k or "ambient" in k) and ("sicak" in k or "temp" in k or "temperature" in k):
        return "Dis_Hava_Sicakligi_C"

    if ("sebeke" in k or "grid" in k) and ("tuket" in k or "consum" in k):
        return "Sebeke_Tuketim_kWh"

    if ("kojen" in k or "cogen" in k or "cogeneration" in k) and ("uret" in k or "produc" in k or "gen" in k):
        return "Kojen_Uretim_kWh"

    if ("kazan" in k or "boiler" in k) and ("dogalgaz" in k or "gaz" in k or "gas" in k):
        return "Kazan_Dogalgaz_m3"
    if ("kojen" in k or "cogen" in k) and ("dogalgaz" in k or "gaz" in k or "gas" in k):
        return "Kojen_Dogalgaz_m3"

    if ("su" in k or "water" in k) and ("tuket" in k or "consum" in k):
        return "Su_Tuketimi_m3"

    if ("chiller" in k) and ("tuket" in k or "consum" in k):
        return "Chiller_Tuketim_kWh"
    if ("mcc" in k) and ("tuket" in k or "consum" in k):
        return "MCC_Tuketim_kWh"
    if ("vrf" in k or "split" in k) and ("tuket" in k or "consum" in k):
        return "VRF_Split_Tuketim_kWh"

    if ("chiller" in k) and ("set" in k or "ayar" in k) and ("temp" in k or "sicak" in k):
        return "Chiller_Set_Temp_C"
    if ("chiller" in k) and ("adet" in k or "count" in k or "sayi" in k) and ("absorp" not in k):
        return "Chiller_Adet"
    if ("absorp" in k or "absorption" in k) and ("chiller" in k) and ("adet" in k or "count" in k or "sayi" in k):
        return "Absorption_Chiller_Adet"
    if ("kazan" in k or "boiler" in k) and ("adet" in k or "count" in k or "sayi" in k):
        return "Kazan_Adet"

    if ("mas 1" in k or "mas1" in k) and ("isit" in k or "heating" in k):
        return "Mas1_Isitma_Temp"
    if ("mas 1" in k or "mas1" in k) and ("kazan" in k or "boiler" in k):
        return "Mas1_Kazan_Temp"
    if ("mas 1" in k or "mas1" in k) and ("sogut" in k or "cool" in k):
        return "Mas1_Sogutma_Temp"

    if ("mas 2" in k or "mas2" in k) and ("isit" in k or "heating" in k):
        return "Mas2_Isitma_Temp"
    if ("mas 2" in k or "mas2" in k) and ("kazan" in k or "boiler" in k):
        return "Mas2_Kazan_Temp"
    if ("mas 2" in k or "mas2" in k) and ("sogut" in k or "cool" in k):
        return "Mas2_Sogutma_Temp"

    return None


def parse_numeric_series(s: pd.Series) -> pd.Series:
    if pd.api.types.is_numeric_dtype(s):
        return s
    x = s.astype(str).str.strip()
    x = x.str.replace("\u00a0", "", regex=False).str.replace(" ", "", regex=False)
    x = x.str.replace(r"(kwh|kw|m3|m\^3|°c|c)$", "", regex=True, case=False)

    def _fix(v: str) -> str:
        if v is None:
            return ""
        v = str(v)
        if v.lower() in ("nan", "none", ""):
            return ""
        has_comma = "," in v
        has_dot = "." in v
        if has_comma and has_dot:
            v = v.replace(".", "").replace(",", ".")
        elif has_comma and not has_dot:
            v = v.replace(",", ".")
        return v

    x = x.map(_fix)
    return pd.to_numeric(x, errors="coerce")


def parse_bool_series(s: pd.Series) -> pd.Series:
    if s.dtype == bool:
        return s
    x = s.astype(str).str.strip().str.lower().map(lambda v: v.translate(TR_MAP))
    true_set = {"1", "true", "yes", "evet", "aktif", "on", "acik", "var"}
    return x.isin(true_set)


def empty_df() -> pd.DataFrame:
    return pd.DataFrame(columns=SCHEMA)


def ensure_schema(df: pd.DataFrame) -> pd.DataFrame:
    for c in SCHEMA:
        if c not in df.columns:
            df[c] = pd.NA
    return df[SCHEMA]


def coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    if "Tarih" in df.columns:
        df["Tarih"] = pd.to_datetime(df["Tarih"], format="%Y-%m-%d", errors="coerce").dt.date
    if "Kar_Eritme_Aktif" in df.columns:
        df["Kar_Eritme_Aktif"] = parse_bool_series(df["Kar_Eritme_Aktif"])
    for c in NUMERIC_COLS:
        if c in df.columns:
            df[c] = parse_numeric_series(df[c])
    return df


def recalc(df: pd.DataFrame) -> pd.DataFrame:
    if df.empty:
        return df
    df["Toplam_Hastane_Tuketim_kWh"] = df["Sebeke_Tuketim_kWh"].fillna(0) + df["Kojen_Uretim_kWh"].fillna(0)
    df["Toplam_Sogutma_Tuketim_kWh"] = df["Chiller_Tuketim_kWh"].fillna(0) + df["VRF_Split_Tuketim_kWh"].fillna(0)
    other = df["Toplam_Hastane_Tuketim_kWh"].fillna(0) - (df["Chiller_Tuketim_kWh"].fillna(0) + df["MCC_Tuketim_kWh"].fillna(0))
    df["Diger_Yuk_kWh"] = other.clip(lower=0)
    return df


@st.cache_data(show_spinner=False)
def load_data() -> pd.DataFrame:
    if not os.path.exists(DATA_FILE):
        return empty_df()
    df = pd.read_csv(DATA_FILE)
    df = ensure_schema(df)
    df = coerce_types(df)
    df = recalc(df)
    df = df.dropna(subset=["Tarih"]).sort_values("Tarih")
    return df


def persist_df(df: pd.DataFrame) -> None:
    out = df.copy()
    out["Tarih"] = out["Tarih"].astype(str)
    out.to_csv(DATA_FILE, index=False)
    load_data.clear()


def upsert_by_date(df_new: pd.DataFrame) -> tuple[int, int]:
    df_new = ensure_schema(df_new.copy())
    df_new = coerce_types(df_new)
    df_new = recalc(df_new)
    df_new = df_new.dropna(subset=["Tarih"]).sort_values("Tarih")
    if df_new.empty:
        return (0, 0)

    df_old = load_data().copy()
    if df_old.empty:
        persist_df(df_new)
        return (0, len(df_new))

    old_dates = set(df_old["Tarih"].tolist())
    new_dates = set(df_new["Tarih"].tolist())
    updated = len(old_dates.intersection(new_dates))
    inserted = len(new_dates - old_dates)

    df_old = df_old[~df_old["Tarih"].isin(new_dates)]
    merged = pd.concat([df_old, df_new], ignore_index=True)
    merged = ensure_schema(merged)
    merged = coerce_types(merged)
    merged = recalc(merged)
    merged = merged.dropna(subset=["Tarih"]).sort_values("Tarih")
    persist_df(merged)
    return (updated, inserted)


def save_single_row(row: dict) -> None:
    df_new = pd.DataFrame([row])
    upsert_by_date(df_new)


def check_daily_anomalies(new_row: dict, df_old: pd.DataFrame, 
                          warning_threshold: float = 0.15,
                          critical_threshold: float = 0.25) -> list:
    """
    Yeni veri ile dünkü değeri ve geçen yıl aynı günü karşılaştır.
    
    Eşik değerleri:
    - warning_threshold: %15+ değişimde UYARI (0.15)
    - critical_threshold: %25+ değişimde KRİTİK (0.25)
    
    Args:
        new_row: Yeni girilen veri (Tarih dahil)
        df_old: Mevcut tüm veri
        warning_threshold: Uyarı eşiği (varsayılan %15)
        critical_threshold: Kritik eşik (varsayılan %25)
    
    Returns:
        list: Uyarı mesajları
    """
    alerts = []
    
    # Kontrol edilecek metrikler ve Türkçe isimleri
    metrics = {
        "Sebeke_Tuketim_kWh": "Şebeke Tüketimi",
        "Chiller_Tuketim_kWh": "Soğutma (Chiller) Tüketimi",
        "MCC_Tuketim_kWh": "MCC Tüketimi",
        "VRF_Split_Tuketim_kWh": "VRF/Split Tüketimi",
        "Kazan_Dogalgaz_m3": "Kazan Doğalgaz",
        "Kojen_Dogalgaz_m3": "Kojenerasyon Doğalgaz",
        "Su_Tuketimi_m3": "Su Tüketimi",
        "Toplam_Hastane_Tuketim_kWh": "Toplam Hastane Tüketimi",
    }
    
    if df_old.empty:
        return alerts
    
    # Yeni girilen tarih
    new_date = new_row.get("Tarih")
    if new_date is None:
        return alerts
    
    # Tarihi date objesine çevir
    if isinstance(new_date, str):
        try:
            from datetime import datetime
            new_date = datetime.strptime(new_date, "%Y-%m-%d").date()
        except:
            try:
                new_date = pd.to_datetime(new_date).date()
            except:
                pass
    
    # Son kaydı al (bir önceki gün)
    last_row = df_old.iloc[-1] if len(df_old) > 0 else None
    
    # Geçen yıl aynı günü bul
    last_year_row = None
    if new_date is not None:
        try:
            from datetime import timedelta
            # Geçen yıl aynı tarih
            try:
                last_year_date = new_date.replace(year=new_date.year - 1)
            except ValueError:
                # 29 Şubat durumu
                last_year_date = new_date - timedelta(days=365)
            
            # Geçen yıl verisini bul
            df_old_copy = df_old.copy()
            df_old_copy["_date"] = pd.to_datetime(df_old_copy["Tarih"], format="%Y-%m-%d", errors="coerce").dt.date
            matches = df_old_copy[df_old_copy["_date"] == last_year_date]
            if not matches.empty:
                last_year_row = matches.iloc[0]
        except Exception as e:
            pass
    
    for col, label in metrics.items():
        try:
            new_val = float(new_row.get(col, 0) or 0)
            
            if new_val == 0:
                continue
            
            # ===== DÜNKÜ DEĞER KARŞILAŞTIRMASI =====
            if last_row is not None:
                old_val = float(last_row.get(col, 0) or 0)
                
                if old_val > 0:
                    change_pct = (new_val - old_val) / old_val
                    
                    if change_pct >= critical_threshold:
                        alerts.append({
                            "type": "KRİTİK",
                            "icon": "🚨",
                            "severity": "CRITICAL",
                            "metric": label,
                            "comparison": "dünkü değere göre",
                            "old": old_val,
                            "new": new_val,
                            "change": change_pct * 100,
                            "message": (
                                f"⚠️ KRİTİK: {label} dünkü değere göre %{change_pct*100:.1f} arttı!\n"
                                f"Dün: {old_val:,.0f} → Bugün: {new_val:,.0f}\n"
                                f"Olası nedenler:\n"
                                f"  • Değer yanlış girilmiş olabilir\n"
                                f"  • Sahada unutulmuş/açık kalan cihaz olabilir\n"
                                f"  • Anormal operasyon durumu olabilir"
                            )
                        })
                    elif change_pct >= warning_threshold:
                        alerts.append({
                            "type": "UYARI",
                            "icon": "📈",
                            "severity": "WARNING",
                            "metric": label,
                            "comparison": "dünkü değere göre",
                            "old": old_val,
                            "new": new_val,
                            "change": change_pct * 100,
                            "message": (
                                f"⚡ UYARI: {label} dünkü değere göre %{change_pct*100:.1f} arttı.\n"
                                f"Dün: {old_val:,.0f} → Bugün: {new_val:,.0f}\n"
                                f"Lütfen değeri kontrol edin."
                            )
                        })
                    elif change_pct <= -critical_threshold:
                        alerts.append({
                            "type": "DÜŞÜŞ",
                            "icon": "📉",
                            "severity": "INFO",
                            "metric": label,
                            "comparison": "dünkü değere göre",
                            "old": old_val,
                            "new": new_val,
                            "change": change_pct * 100,
                            "message": f"📉 {label} dünkü değere göre %{abs(change_pct)*100:.1f} düştü."
                        })
            
            # ===== GEÇEN YIL AYNI GÜN KARŞILAŞTIRMASI =====
            if last_year_row is not None:
                last_year_val = float(last_year_row.get(col, 0) or 0)
                
                if last_year_val > 0:
                    yoy_change_pct = (new_val - last_year_val) / last_year_val
                    
                    # Sadece anlamlı artışları rapor et (geçen yıla göre %20+)
                    if yoy_change_pct >= 0.20:
                        alerts.append({
                            "type": "YOY_ARTIS",
                            "icon": "📊",
                            "severity": "INFO",
                            "metric": label,
                            "comparison": "geçen yıl aynı güne göre",
                            "old": last_year_val,
                            "new": new_val,
                            "change": yoy_change_pct * 100,
                            "message": (
                                f"📊 BİLGİ: {label} geçen yıl aynı güne göre %{yoy_change_pct*100:.1f} arttı.\n"
                                f"Geçen yıl: {last_year_val:,.0f} → Bu yıl: {new_val:,.0f}"
                            )
                        })
        except Exception as e:
            continue
    
    # Severity'ye göre sırala (CRITICAL > WARNING > INFO)
    severity_order = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}
    alerts.sort(key=lambda x: severity_order.get(x.get("severity", "INFO"), 3))
    
    return alerts


def flatten_columns(df: pd.DataFrame) -> pd.DataFrame:
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = [" ".join([str(x) for x in tup if str(x).lower() != "nan"]).strip() for tup in df.columns.values]
    df.columns = [str(c) for c in df.columns]
    return df


def auto_detect_header_row(excel_file, sheet_name: str, max_rows: int = 80) -> int | None:
    try:
        preview = pd.read_excel(excel_file, sheet_name=sheet_name, header=None, nrows=max_rows)
    except Exception:
        return None
    for i in range(len(preview)):
        row_vals = preview.iloc[i].tolist()
        row_norm = [norm_key(v) for v in row_vals]
        if any("tarih" in x for x in row_norm):
            return i
    return None


def guess_date_column_by_values(df: pd.DataFrame) -> tuple[str | None, float]:
    best_col, best_ratio = None, 0.0
    for c in df.columns:
        parsed = pd.to_datetime(df[c], errors="coerce", dayfirst=True)
        ratio = float(parsed.notna().mean())
        if ratio > best_ratio:
            best_ratio, best_col = ratio, c
    return best_col, best_ratio


def normalize_import_df(raw: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    df = flatten_columns(raw.copy())
    info = {"mapped": {}, "unmapped": [], "date_detect": None}

    rename_map = {}
    for c in df.columns:
        canon = infer_canonical_col(c)
        if canon:
            rename_map[c] = canon
            info["mapped"][str(c)] = canon
        else:
            info["unmapped"].append(str(c))

    df = df.rename(columns=rename_map)

    if "Tarih" not in df.columns:
        guessed, ratio = guess_date_column_by_values(df)
        if guessed is not None and ratio >= 0.60:
            df = df.rename(columns={guessed: "Tarih"})
            info["date_detect"] = f"Başlıktan bulunamadı; değerlerden '{guessed}' Tarih kabul edildi (oran={ratio:.0%})."
        else:
            cols_preview = ", ".join([f"'{c}'" for c in list(df.columns)[:30]])
            raise ValueError(
                "Excel'de 'Tarih/TARİH' başlığı bulunamadı ve değerlerden de güvenli tespit edilemedi.\n"
                f"Kolonlar (ilk 30): {cols_preview}\n"
                "Çözüm: Header satırını düzelt veya tarih kolonunun başlığını 'Tarih' yap."
            )

    df = ensure_schema(df)
    df = coerce_types(df)
    df = recalc(df)
    df = df.dropna(subset=["Tarih"]).sort_values("Tarih")
    return df, info


def build_excel_template() -> bytes:
    out = io.BytesIO()
    pd.DataFrame(columns=SCHEMA).to_excel(out, index=False, sheet_name="ENERJI_VERI", engine="openpyxl")
    return out.getvalue()


def month_range(y: int, m: int) -> tuple[date, date]:
    start = date(y, m, 1)
    end = date(y + 1, 1, 1) if m == 12 else date(y, m + 1, 1)
    return start, end


def filter_range(df: pd.DataFrame, start: date, end_excl: date) -> pd.DataFrame:
    if df.empty:
        return df
    mask = (df["Tarih"] >= start) & (df["Tarih"] < end_excl)
    return df.loc[mask].copy()


def safe_pct_change(cur: float, prev: float) -> float | None:
    if prev is None or pd.isna(prev) or prev == 0:
        return None
    return (cur - prev) / prev * 100.0


def yoy_month_compare(df: pd.DataFrame, year: int, month: int) -> dict:
    cur_start, cur_end = month_range(year, month)
    prev_start, prev_end = month_range(year - 1, month)
    cur = filter_range(df, cur_start, cur_end)
    prev = filter_range(df, prev_start, prev_end)

    def sumcol(dfx, col):
        return float(dfx[col].fillna(0).sum()) if not dfx.empty else 0.0

    metrics = {
        "Toplam_Hastane_Tuketim_kWh": (sumcol(cur, "Toplam_Hastane_Tuketim_kWh"), sumcol(prev, "Toplam_Hastane_Tuketim_kWh")),
        "Sebeke_Tuketim_kWh": (sumcol(cur, "Sebeke_Tuketim_kWh"), sumcol(prev, "Sebeke_Tuketim_kWh")),
        "Kojen_Uretim_kWh": (sumcol(cur, "Kojen_Uretim_kWh"), sumcol(prev, "Kojen_Uretim_kWh")),
        "Toplam_Sogutma_Tuketim_kWh": (sumcol(cur, "Toplam_Sogutma_Tuketim_kWh"), sumcol(prev, "Toplam_Sogutma_Tuketim_kWh")),
        "Kazan_Dogalgaz_m3": (sumcol(cur, "Kazan_Dogalgaz_m3"), sumcol(prev, "Kazan_Dogalgaz_m3")),
        "Kojen_Dogalgaz_m3": (sumcol(cur, "Kojen_Dogalgaz_m3"), sumcol(prev, "Kojen_Dogalgaz_m3")),
        "Su_Tuketimi_m3": (sumcol(cur, "Su_Tuketimi_m3"), sumcol(prev, "Su_Tuketimi_m3")),
    }
    return {
        "cur_period": (cur_start, cur_end),
        "prev_period": (prev_start, prev_end),
        "cur_df": cur,
        "prev_df": prev,
        "metrics": metrics,
    }


def aggregate_for_view(df_in: pd.DataFrame, view_mode: str) -> pd.DataFrame:
    if df_in.empty:
        return df_in
    d = df_in.copy()
    dt = pd.to_datetime(d["Tarih"], format="%Y-%m-%d", errors="coerce")
    d["_dt"] = dt

    if view_mode == "Günlük":
        d = d.sort_values("_dt")
        d["Tarih"] = pd.to_datetime(d["Tarih"], format="%Y-%m-%d", errors="coerce")
        return d.drop(columns=["_dt"], errors="ignore")

    if view_mode == "Aylık":
        d["_grp"] = dt.dt.to_period("M").dt.to_timestamp()
    else:
        d["_grp"] = dt.dt.to_period("Y").dt.to_timestamp()

    sum_cols = [
        "Sebeke_Tuketim_kWh", "Kojen_Uretim_kWh", "Toplam_Hastane_Tuketim_kWh",
        "Chiller_Tuketim_kWh", "MCC_Tuketim_kWh", "VRF_Split_Tuketim_kWh",
        "Toplam_Sogutma_Tuketim_kWh", "Kazan_Dogalgaz_m3", "Kojen_Dogalgaz_m3",
        "Su_Tuketimi_m3", "Diger_Yuk_kWh",
    ]
    mean_cols = ["Dis_Hava_Sicakligi_C"]

    grouped = d.groupby("_grp", as_index=False).agg({**{c: "sum" for c in sum_cols}, **{c: "mean" for c in mean_cols}})
    grouped = grouped.rename(columns={"_grp": "Tarih"})
    grouped["Tarih"] = pd.to_datetime(grouped["Tarih"], format="%Y-%m-%d", errors="coerce")
    return grouped


def render_styled_table(df: pd.DataFrame, max_height: int = 400, max_rows: int = 200, table_key: str = "table") -> None:
    """Styled HTML tablo render et - siyah yazı, beyaz arka plan, ondalık 1 basamak
    
    Büyük veri setleri için sayfalama destekler.
    """
    if df.empty:
        st.warning("Gösterilecek veri yok.")
        return
    
    total_rows = len(df)
    
    # Sayfalama - eğer veri çok büyükse
    if total_rows > max_rows:
        total_pages = (total_rows + max_rows - 1) // max_rows
        page_key = f"page_{table_key}"
        
        if page_key not in st.session_state:
            st.session_state[page_key] = 1
        
        # Sayfalama kontrolleri
        col1, col2, col3, col4 = st.columns([1, 2, 2, 1])
        with col1:
            if st.button("◀ Önceki", key=f"prev_{table_key}"):
                if st.session_state[page_key] > 1:
                    st.session_state[page_key] -= 1
                    st.rerun()
        with col2:
            st.markdown(f"**Sayfa {st.session_state[page_key]} / {total_pages}**")
        with col3:
            st.markdown(f"**Toplam: {total_rows} satır**")
        with col4:
            if st.button("Sonraki ▶", key=f"next_{table_key}"):
                if st.session_state[page_key] < total_pages:
                    st.session_state[page_key] += 1
                    st.rerun()
        
        # Sayfa verisi
        start_idx = (st.session_state[page_key] - 1) * max_rows
        end_idx = min(start_idx + max_rows, total_rows)
        df_page = df.iloc[start_idx:end_idx].copy()
    else:
        df_page = df.copy()
    
    # Ondalık basamakları düzelt
    for col in df_page.select_dtypes(include=['float64', 'float32']).columns:
        df_page[col] = df_page[col].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "")
    
    # Styled HTML tablo
    styled_df = df_page.style.set_properties(**{
        'background-color': '#ffffff',
        'color': '#1a1a1a',
        'border': '1px solid #e0e0e0',
        'padding': '4px 6px',
        'font-size': '11px',
        'white-space': 'nowrap'
    }).set_table_styles([
        {'selector': 'th', 'props': [
            ('background-color', '#012D75'),
            ('color', '#ffffff'),
            ('font-weight', 'bold'),
            ('padding', '6px 8px'),
            ('font-size', '11px'),
            ('border', '1px solid #003087'),
            ('white-space', 'nowrap')
        ]},
        {'selector': 'table', 'props': [
            ('width', '100%'),
            ('border-collapse', 'collapse')
        ]}
    ])
    
    # Scrollable container
    st.markdown(f'''
    <div style="max-height: {max_height}px; overflow-y: auto; overflow-x: auto; border: 1px solid #334155; border-radius: 8px;">
        {styled_df.to_html(escape=False)}
    </div>
    ''', unsafe_allow_html=True)


def chart_consumption_vs_temp(df_period: pd.DataFrame):
    if df_period.empty:
        return None
    d = df_period.copy()
    d["Tarih"] = pd.to_datetime(d["Tarih"], format="%Y-%m-%d", errors="coerce")
    
    import plotly.graph_objects as go
    
    fig = go.Figure()
    
    # Ana çizgi - Toplam Tüketim (gradient fill ile)
    fig.add_trace(go.Scatter(
        x=d["Tarih"],
        y=d["Toplam_Hastane_Tuketim_kWh"],
        mode='lines+markers',
        name='Toplam Tüketim',
        line=dict(color='#3b82f6', width=3, shape='spline'),
        marker=dict(size=10, color='#3b82f6', line=dict(color='white', width=2)),
        fill='tozeroy',
        fillcolor='rgba(59, 130, 246, 0.15)',
        hovertemplate='<b>%{x|%d %b}</b><br>Tüketim: %{y:,.0f} kWh<extra></extra>'
    ))
    
    # İkinci eksen - Dış Hava Sıcaklığı
    fig.add_trace(go.Scatter(
        x=d["Tarih"],
        y=d["Dis_Hava_Sicakligi_C"],
        mode='lines+markers',
        name='Dış Hava (°C)',
        yaxis='y2',
        line=dict(color='#f59e0b', width=3, dash='dot', shape='spline'),
        marker=dict(size=8, color='#f59e0b', symbol='diamond', line=dict(color='white', width=2)),
        hovertemplate='<b>%{x|%d %b}</b><br>Sıcaklık: %{y:.1f}°C<extra></extra>'
    ))
    
    # Modern layout - Premium koyu tema
    fig.update_layout(
        title=dict(
            text='<b>📊 Günlük Tüketim & Dış Hava Sıcaklığı</b>',
            font=dict(size=20, color='#ffffff', family="Inter, sans-serif"),
            x=0.02,
            xanchor='left'
        ),
        font=dict(family="Inter, sans-serif", size=13, color='#e2e8f0'),
        plot_bgcolor='rgba(15, 23, 42, 0.98)',
        paper_bgcolor='rgba(15, 23, 42, 0.98)',
        yaxis=dict(
            title=dict(text="Toplam Tüketim (kWh)", font=dict(color='#3b82f6')),
            gridcolor='rgba(59, 130, 246, 0.1)',
            showgrid=True,
            zeroline=False,
            tickformat=',d'
        ),
        yaxis2=dict(
            title=dict(text="Dış Hava (°C)", font=dict(color='#f59e0b')),
            overlaying="y",
            side="right",
            showgrid=False,
            zeroline=False
        ),
        xaxis=dict(
            gridcolor='rgba(255, 255, 255, 0.05)',
            showgrid=True,
            tickformat='%d %b'
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor='rgba(30, 41, 59, 0.9)',
            bordercolor='rgba(255,255,255,0.1)',
            borderwidth=1,
            font=dict(color='white')
        ),
        margin=dict(l=10, r=10, t=80, b=10),
        hovermode='x unified',
        hoverlabel=dict(
            bgcolor="rgba(30, 41, 59, 0.95)",
            font_size=13,
            font_family="Inter, sans-serif",
            font_color="white",
            bordercolor='rgba(255,255,255,0.2)'
        )
    )
    return fig


def chart_stacked_breakdown(df_period: pd.DataFrame):
    if df_period.empty:
        return None
    d = df_period.copy()
    d["Tarih"] = pd.to_datetime(d["Tarih"], format="%Y-%m-%d", errors="coerce")
    plot_df = d[["Tarih", "Chiller_Tuketim_kWh", "MCC_Tuketim_kWh", "Diger_Yuk_kWh"]].fillna(0).copy()
    plot_df = plot_df.rename(columns={
        "Chiller_Tuketim_kWh": "❄️ Chiller",
        "MCC_Tuketim_kWh": "⚡ MCC",
        "Diger_Yuk_kWh": "💡 Aydınlatma/Diğer",
    })
    plot_df = plot_df.melt(id_vars=["Tarih"], var_name="Bileşen", value_name="kWh")
    
    # Premium gradyan renk paleti
    colors = {
        '❄️ Chiller': '#06b6d4',      # Cyan
        '⚡ MCC': '#8b5cf6',            # Violet
        '💡 Aydınlatma/Diğer': '#f59e0b'  # Amber
    }
    
    fig = px.bar(
        plot_df, x="Tarih", y="kWh", color="Bileşen", barmode="stack",
        title="<b>⚡ Enerji Kırılımı</b>",
        labels={"Tarih": "", "kWh": "Tüketim (kWh)"},
        color_discrete_map=colors
    )
    
    # Premium koyu tema layout
    fig.update_layout(
        font=dict(family="Inter, sans-serif", size=13, color='#e2e8f0'),
        plot_bgcolor='rgba(15, 23, 42, 0.98)',
        paper_bgcolor='rgba(15, 23, 42, 0.98)',
        title=dict(
            font=dict(size=20, color='#ffffff', family="Inter, sans-serif"),
            x=0.02,
            xanchor='left'
        ),
        yaxis=dict(
            gridcolor='rgba(255, 255, 255, 0.05)',
            showgrid=True,
            zeroline=False,
            tickformat=',d'
        ),
        xaxis=dict(
            gridcolor='rgba(255, 255, 255, 0.03)',
            showgrid=False,
            tickformat='%d %b'
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor='rgba(30, 41, 59, 0.9)',
            bordercolor='rgba(255,255,255,0.1)',
            borderwidth=1,
            font=dict(color='white'),
            title=None
        ),
        margin=dict(l=10, r=10, t=80, b=10),
        hovermode='x unified',
        hoverlabel=dict(
            bgcolor="rgba(30, 41, 59, 0.95)",
            font_size=13,
            font_family="Inter, sans-serif",
            font_color="white",
            bordercolor='rgba(255,255,255,0.2)'
        ),
        bargap=0.2
    )
    
    # Yuvarlatılmış bar köşeleri ve gölge efekti
    fig.update_traces(
        marker=dict(
            line=dict(color='rgba(255,255,255,0.1)', width=1)
        ),
        hovertemplate='<b>%{x|%d %b}</b><br>%{y:,.0f} kWh<extra></extra>'
    )
    
    return fig


def chart_month_vs_last_year(yoy_info: dict):
    cur_df = yoy_info["cur_df"]
    prev_df = yoy_info["prev_df"]
    cur_start, _ = yoy_info["cur_period"]
    prev_start, _ = yoy_info["prev_period"]

    def tot(dfx, col):
        return float(dfx[col].fillna(0).sum()) if not dfx.empty else 0.0

    rows = []
    for label, dfx in [(cur_start.strftime("%Y-%m"), cur_df), (prev_start.strftime("%Y-%m"), prev_df)]:
        rows.extend([
            {"Dönem": label, "Metrik": "🏥 Toplam Hastane", "Değer": tot(dfx, "Toplam_Hastane_Tuketim_kWh")},
            {"Dönem": label, "Metrik": "⚡ Şebeke", "Değer": tot(dfx, "Sebeke_Tuketim_kWh")},
            {"Dönem": label, "Metrik": "🔋 Kojenerasyon", "Değer": tot(dfx, "Kojen_Uretim_kWh")},
            {"Dönem": label, "Metrik": "❄️ Toplam Soğutma", "Değer": tot(dfx, "Toplam_Sogutma_Tuketim_kWh")},
        ])
    dfp = pd.DataFrame(rows)
    
    # Premium renk paleti - Bu yıl vs Geçen yıl
    colors = {
        cur_start.strftime("%Y-%m"): '#10b981',   # Emerald (Bu yıl)
        prev_start.strftime("%Y-%m"): '#6366f1'   # Indigo (Geçen yıl)
    }
    
    fig = px.bar(
        dfp, x="Metrik", y="Değer", color="Dönem", barmode="group",
        title="<b>📅 Bu Ay vs Geçen Yıl Aynı Ay</b>",
        labels={"Değer": "Toplam (kWh)", "Metrik": ""},
        color_discrete_map=colors
    )
    
    # Premium koyu tema layout
    fig.update_layout(
        font=dict(family="Inter, sans-serif", size=13, color='#e2e8f0'),
        plot_bgcolor='rgba(15, 23, 42, 0.98)',
        paper_bgcolor='rgba(15, 23, 42, 0.98)',
        title=dict(
            font=dict(size=20, color='#ffffff', family="Inter, sans-serif"),
            x=0.02,
            xanchor='left'
        ),
        yaxis=dict(
            gridcolor='rgba(255, 255, 255, 0.05)',
            showgrid=True,
            zeroline=False,
            tickformat=',d'
        ),
        xaxis=dict(
            gridcolor='rgba(255, 255, 255, 0.03)',
            showgrid=False
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor='rgba(30, 41, 59, 0.9)',
            bordercolor='rgba(255,255,255,0.1)',
            borderwidth=1,
            font=dict(color='white'),
            title=None
        ),
        margin=dict(l=10, r=10, t=80, b=10),
        hovermode='x unified',
        hoverlabel=dict(
            bgcolor="rgba(30, 41, 59, 0.95)",
            font_size=13,
            font_family="Inter, sans-serif",
            font_color="white",
            bordercolor='rgba(255,255,255,0.2)'
        ),
        bargap=0.25,
        bargroupgap=0.15
    )
    
    # Premium bar styling
    fig.update_traces(
        marker=dict(
            line=dict(color='rgba(255,255,255,0.15)', width=1)
        ),
        hovertemplate='<b>%{x}</b><br>%{y:,.0f} kWh<extra></extra>'
    )
    
    return fig



# ---------- PDF ----------
def find_unicode_font_pair() -> tuple[str, str, str] | None:
    candidates = []
    # local
    candidates.append(("DejaVu", Path("fonts/DejaVuSans.ttf"), Path("fonts/DejaVuSans-Bold.ttf")))
    # linux
    candidates.append(("DejaVu", Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"), Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")))
    # windows
    win = Path(r"C:\Windows\Fonts")
    candidates.append(("Arial", win / "arial.ttf", win / "arialbd.ttf"))
    candidates.append(("Calibri", win / "calibri.ttf", win / "calibrib.ttf"))
    candidates.append(("SegoeUI", win / "segoeui.ttf", win / "segoeuib.ttf"))
    # mac
    candidates.append(("Arial", Path("/System/Library/Fonts/Supplemental/Arial.ttf"), Path("/System/Library/Fonts/Supplemental/Arial Bold.ttf")))
    candidates.append(("Arial", Path("/Library/Fonts/Arial.ttf"), Path("/Library/Fonts/Arial Bold.ttf")))

    for fam, reg, bold in candidates:
        if reg.exists() and bold.exists():
            return fam, str(reg), str(bold)
    return None


def sanitize_ascii_for_pdf(s: str) -> str:
    if s is None:
        return ""
    s = str(s)
    s = s.replace("İ", "I").replace("İ", "I")
    s = s.replace("ı", "i")
    s = s.replace("ş", "s").replace("Ş", "S")
    s = s.replace("ğ", "g").replace("Ğ", "G")
    s = s.replace("ü", "u").replace("Ü", "U")
    s = s.replace("ö", "o").replace("Ö", "O")
    s = s.replace("ç", "c").replace("Ç", "C")
    return s


def fig_to_png_bytes(fig) -> bytes:
    return pio.to_image(fig, format="png", width=1400, height=700, scale=2)


def generate_pdf_report(start: date, end_exclusive: date, df_period: pd.DataFrame, yoy_info: dict | None, figs: dict[str, object]) -> bytes:
    """Birleşik enerji raporu PDF üret — Günlük/Aylık raporlarla aynı modern stil."""

    # ─── Renk Paleti (günlük/aylık ile aynı) ───
    ACCENT = (59, 130, 246)
    HEADER_BG = (15, 23, 42)
    SUCCESS = (16, 185, 129)
    WARNING_C = (245, 158, 11)
    DANGER = (239, 68, 68)
    WHITE = (255, 255, 255)
    GRAY = (156, 163, 175)

    try:
        pdf = FPDF(orientation="P", unit="mm", format="A4")
        pdf.set_auto_page_break(auto=True, margin=18)

        font_pair = find_unicode_font_pair()
        unicode_ok = False
        if font_pair:
            try:
                fam, reg, bold = font_pair
                pdf.add_font(fam, "", reg, uni=True)
                pdf.add_font(fam, "B", bold, uni=True)
                # Italic: Oblique varsa ekle, yoksa Regular fallback
                import pathlib as _pl
                _italic = _pl.Path(reg).parent / reg.replace("Sans.", "Sans-Oblique.").split("/")[-1].split("\\")[-1]
                if not _italic.exists():
                    _italic = _pl.Path(reg).parent / "DejaVuSans-Oblique.ttf"
                if _italic.exists():
                    pdf.add_font(fam, "I", str(_italic), uni=True)
                else:
                    pdf.add_font(fam, "I", reg, uni=True)  # fallback: regular as italic
                unicode_ok = True
                font = fam
            except Exception:
                font = "Helvetica"
                unicode_ok = False
        else:
            font = "Helvetica"

        def T(txt: str) -> str:
            return txt if unicode_ok else sanitize_ascii_for_pdf(txt)

        # ─── Yardımcı: Bölüm Başlığı ───
        def section_title(icon_title: str, color=None):
            if color is None:
                color = ACCENT
            pdf.ln(4)
            pdf.set_fill_color(*color)
            pdf.rect(10, pdf.get_y(), 3, 8, 'F')
            pdf.set_font(font, 'B', 13)
            pdf.set_text_color(40, 40, 40)
            pdf.set_x(16)
            pdf.cell(0, 8, T(icon_title), 0, 1)
            pdf.ln(2)

        # ─── Yardımcı: KPI Kutusu ───
        def info_box(x, y, w, h, label, value, sub="", color=None):
            if color is None:
                color = ACCENT
            pdf.set_fill_color(245, 247, 250)
            pdf.rect(x, y, w, h, 'F')
            pdf.set_fill_color(*color)
            pdf.rect(x, y + 2, 2, h - 4, 'F')
            pdf.set_font(font, '', 8)
            pdf.set_text_color(120, 120, 120)
            pdf.set_xy(x + 6, y + 3)
            pdf.cell(w - 10, 4, T(label), 0, 0)
            pdf.set_font(font, 'B', 14)
            pdf.set_text_color(30, 30, 30)
            pdf.set_xy(x + 6, y + 9)
            pdf.cell(w - 10, 8, T(value), 0, 0)
            if sub:
                pdf.set_font(font, '', 7)
                if "+" in sub:
                    pdf.set_text_color(*DANGER)
                elif "-" in sub:
                    pdf.set_text_color(*SUCCESS)
                else:
                    pdf.set_text_color(*GRAY)
                pdf.set_xy(x + 6, y + 18)
                pdf.cell(w - 10, 4, T(sub), 0, 0)

        # ─── Yardımcı: Modern Tablo ───
        def modern_table(headers, rows_data, col_widths, header_color=None):
            if header_color is None:
                header_color = HEADER_BG
            rh = 7
            # Header
            pdf.set_fill_color(*header_color)
            pdf.set_text_color(*WHITE)
            pdf.set_font(font, 'B', 9)
            for i, hdr in enumerate(headers):
                pdf.cell(col_widths[i], rh, T(hdr), 0, 0, 'L', fill=True)
            pdf.ln()
            # Rows
            pdf.set_font(font, '', 9)
            for r_idx, row in enumerate(rows_data):
                is_bold = row.get("bold", False) if isinstance(row, dict) else False
                cells = row.get("cells", row) if isinstance(row, dict) else row
                if is_bold:
                    pdf.set_font(font, 'B', 9)
                if r_idx % 2 == 0:
                    pdf.set_fill_color(250, 250, 252)
                else:
                    pdf.set_fill_color(255, 255, 255)
                pdf.set_text_color(40, 40, 40)
                for i, cell_val in enumerate(cells):
                    pdf.cell(col_widths[i], rh, T(str(cell_val)), 0, 0, 'L', fill=True)
                pdf.ln()
                if is_bold:
                    pdf.set_font(font, '', 9)
            # Bottom line
            pdf.set_draw_color(*ACCENT)
            total_w = sum(col_widths)
            pdf.line(pdf.get_x(), pdf.get_y(), pdf.get_x() + total_w, pdf.get_y())
            pdf.set_draw_color(0, 0, 0)

        # ═══════════════════════════════════════════
        #  SAYFA 1 — BAŞLIK
        # ═══════════════════════════════════════════
        pdf.add_page()

        # ─── Header (koyu arka plan) ───
        pdf.set_fill_color(*HEADER_BG)
        pdf.rect(0, 0, 210, 42, 'F')
        pdf.set_fill_color(*ACCENT)
        pdf.rect(0, 42, 210, 1.5, 'F')

        pdf.set_font(font, 'B', 18)
        pdf.set_text_color(*WHITE)
        pdf.set_y(8)
        pdf.cell(0, 10, T("AYLIK BIRLESIK ENERJI RAPORU"), 0, 1, 'C')

        pdf.set_font(font, '', 12)
        pdf.set_text_color(*GRAY)
        end_incl = (pd.to_datetime(end_exclusive) - pd.Timedelta(days=1)).date()
        pdf.cell(0, 7, T(f"Donem: {start.strftime('%d.%m.%Y')} - {end_incl.strftime('%d.%m.%Y')}"), 0, 1, 'C')

        pdf.set_font(font, 'I', 9)
        from datetime import datetime as _dt_now
        pdf.cell(0, 5, T(f"Olusturma: {_dt_now.now().strftime('%d.%m.%Y %H:%M')} | Acibadem Hastanesi"), 0, 1, 'C')
        pdf.ln(8)

        # ─── Veri hesapla ───
        def ssum(col):
            return float(df_period[col].fillna(0).sum()) if not df_period.empty else 0.0

        def savg(col):
            return float(df_period[col].astype(float).mean()) if not df_period.empty else 0.0

        total_h = ssum("Toplam_Hastane_Tuketim_kWh")
        total_grid = ssum("Sebeke_Tuketim_kWh")
        total_cogen = ssum("Kojen_Uretim_kWh")
        total_cool = ssum("Toplam_Sogutma_Tuketim_kWh")
        total_gas_kazan = ssum("Kazan_Dogalgaz_m3")
        total_gas_kojen = ssum("Kojen_Dogalgaz_m3")
        total_water = ssum("Su_Tuketimi_m3") if "Su_Tuketimi_m3" in df_period.columns else 0
        avg_temp = savg("Dis_Hava_Sicakligi_C")
        day_count = len(df_period) if not df_period.empty else 0

        # ═══════════════════════════════════════════
        #  BÖLÜM 1 — ENERJİ ÖZETİ (KPI Kutuları)
        # ═══════════════════════════════════════════
        section_title("ENERJI OZETI", ACCENT)

        box_y = pdf.get_y()
        box_w = 60
        box_h = 25
        gap = 3
        x_start = 10

        info_box(x_start, box_y, box_w, box_h,
                 "Toplam Tuketim", f"{total_h:,.0f} kWh".replace(",", "."),
                 f"{day_count} gun verisi", ACCENT)
        info_box(x_start + box_w + gap, box_y, box_w, box_h,
                 "Sebeke Tuketimi", f"{total_grid:,.0f} kWh".replace(",", "."),
                 "", SUCCESS)
        info_box(x_start + 2*(box_w + gap), box_y, box_w, box_h,
                 "Kojen Uretimi", f"{total_cogen:,.0f} kWh".replace(",", "."),
                 "", WARNING_C)

        pdf.set_y(box_y + box_h + 4)
        box_y2 = pdf.get_y()

        info_box(x_start, box_y2, box_w, box_h,
                 "Sogutma Tuketimi", f"{total_cool:,.0f} kWh".replace(",", "."),
                 f"Oran: %{(total_cool/total_h*100):.1f}" if total_h > 0 else "", (99, 102, 241))
        info_box(x_start + box_w + gap, box_y2, box_w, box_h,
                 "Ort. Dis Hava", f"{avg_temp:.1f} C",
                 "", GRAY)
        info_box(x_start + 2*(box_w + gap), box_y2, box_w, box_h,
                 "Dogalgaz Toplam", f"{(total_gas_kazan + total_gas_kojen):,.0f} m3".replace(",", "."),
                 f"Kazan: {total_gas_kazan:,.0f} + Kojen: {total_gas_kojen:,.0f}".replace(",", "."), DANGER)

        pdf.set_y(box_y2 + box_h + 6)

        # ═══════════════════════════════════════════
        #  BÖLÜM 2 — DETAY TABLOSU
        # ═══════════════════════════════════════════
        section_title("TUKETIM DETAY TABLOSU", ACCENT)

        detail_rows = [
            ["Toplam Hastane Tuketimi", f"{total_h:,.0f} kWh".replace(",", ".")],
            ["Sebeke Tuketimi", f"{total_grid:,.0f} kWh".replace(",", ".")],
            ["Kojenerasyon Uretimi", f"{total_cogen:,.0f} kWh".replace(",", ".")],
            ["Toplam Sogutma Tuketimi", f"{total_cool:,.0f} kWh".replace(",", ".")],
            ["Kazan Dogalgaz", f"{total_gas_kazan:,.0f} m3".replace(",", ".")],
            ["Kojen Dogalgaz", f"{total_gas_kojen:,.0f} m3".replace(",", ".")],
            ["Su Tuketimi", f"{total_water:,.0f} m3".replace(",", ".")],
            ["Ort. Dis Hava Sicakligi", f"{avg_temp:.1f} C"],
        ]
        modern_table(["Gosterge", "Deger"], detail_rows, [125, 55])
        pdf.ln(4)

        # ═══════════════════════════════════════════
        #  BÖLÜM 3 — MALİYET ÖZETİ
        # ═══════════════════════════════════════════
        try:
            import json as _cost_json
            _cost_settings_path = os.path.join(os.path.dirname(__file__), "configs", "hvac_settings.json")
            _cost_prices = {}
            if os.path.exists(_cost_settings_path):
                with open(_cost_settings_path, "r", encoding="utf-8") as _cpf:
                    _cost_prices = _cost_json.load(_cpf)

            _p_elec = float(_cost_prices.get("UNIT_PRICE_ELECTRICITY", 0))
            _p_gas = float(_cost_prices.get("UNIT_PRICE_GAS", 0))
            _p_water = float(_cost_prices.get("UNIT_PRICE_WATER", 0))

            if _p_elec > 0 or _p_gas > 0 or _p_water > 0:
                total_gas_m3 = total_gas_kazan + total_gas_kojen
                cost_elec = total_grid * _p_elec if _p_elec > 0 else 0
                cost_gas = total_gas_m3 * _p_gas if _p_gas > 0 else 0
                cost_water = total_water * _p_water if _p_water > 0 else 0
                cost_total = cost_elec + cost_gas + cost_water

                section_title("MALIYET OZETI (TL)", WARNING_C)

                # Maliyet KPI kutuları
                cost_box_y = pdf.get_y()
                cbox_w = 45
                cgap = 2.5

                if _p_elec > 0:
                    info_box(10, cost_box_y, cbox_w, 25,
                             "Elektrik", f"{cost_elec:,.0f} TL".replace(",", "."),
                             f"{_p_elec:.2f} TL/kWh", ACCENT)
                if _p_gas > 0:
                    info_box(10 + cbox_w + cgap, cost_box_y, cbox_w, 25,
                             "Dogalgaz", f"{cost_gas:,.0f} TL".replace(",", "."),
                             f"{_p_gas:.2f} TL/m3", DANGER)
                if _p_water > 0:
                    info_box(10 + 2*(cbox_w + cgap), cost_box_y, cbox_w, 25,
                             "Su", f"{cost_water:,.0f} TL".replace(",", "."),
                             f"{_p_water:.2f} TL/m3", (59, 130, 200))
                info_box(10 + 3*(cbox_w + cgap), cost_box_y, cbox_w, 25,
                         "TOPLAM", f"{cost_total:,.0f} TL".replace(",", "."),
                         "", SUCCESS)

                pdf.set_y(cost_box_y + 30)
        except Exception:
            pass

        # ═══════════════════════════════════════════
        #  BÖLÜM 4 — İÇGÖRÜLER
        # ═══════════════════════════════════════════
        section_title("ICGORULER VE ANALIZ", SUCCESS)

        insights = []
        if yoy_info and "metrics" in yoy_info:
            cur_total, prev_total = yoy_info["metrics"]["Toplam_Hastane_Tuketim_kWh"]
            pct = safe_pct_change(cur_total, prev_total)
            if pct is None:
                insights.append("Gecen yil ayni ay verisi olmadigi icin YoY kiyas yapilamadi.")
            else:
                direction = "artti" if pct > 0 else "azaldi"
                insights.append(f"Toplam tuketim gecen yilin ayni ayina gore %{abs(pct):.1f} {direction}.")
        else:
            insights.append("Rapor secilen tarih araligina gore olusturuldu.")

        if total_h > 0:
            share = (total_cool / total_h) * 100.0
            insights.append(f"Sogutmanin toplam tuketimine orani yaklasik %{share:.1f}.")

        if total_cogen > 0 and total_h > 0:
            cogen_share = (total_cogen / total_h) * 100.0
            insights.append(f"Kojenerasyon, toplam tuketimin %{cogen_share:.1f}'ini karsilamaktadir.")

        # İçgörü kutusu
        pdf.set_fill_color(240, 249, 245)
        insight_y = pdf.get_y()
        insight_text = "\n".join([f"  {ins}" for ins in insights])
        pdf.set_font(font, '', 10)
        pdf.set_text_color(30, 80, 50)
        pdf.set_x(12)
        pdf.multi_cell(186, 6, T(insight_text))
        insight_end = pdf.get_y()
        # Sol yeşil çizgi
        pdf.set_fill_color(*SUCCESS)
        pdf.rect(10, insight_y, 2, insight_end - insight_y, 'F')
        pdf.ln(4)

        # ═══════════════════════════════════════════
        #  BÖLÜM 5 — GRAFİKLER
        # ═══════════════════════════════════════════
        section_title("GRAFIKLER", (99, 102, 241))
        pdf.set_text_color(40, 40, 40)

        charts_added = 0
        charts_failed = 0

        for title, fig in figs.items():
            if fig is None:
                continue

            # Grafik başlığı
            pdf.set_font(font, 'B', 11)
            pdf.set_text_color(40, 40, 40)
            pdf.set_fill_color(*ACCENT)
            pdf.rect(10, pdf.get_y(), 3, 6, 'F')
            pdf.set_x(16)
            pdf.cell(0, 6, T(title), 0, 1)
            pdf.ln(1)

            try:
                png = fig_to_png_bytes(fig)
                charts_added += 1
            except Exception as e:
                charts_failed += 1
                pdf.set_font(font, '', 9)
                pdf.set_text_color(*DANGER)
                error_msg = str(e)[:180]
                if "kaleido" in error_msg.lower() or "orca" in error_msg.lower():
                    pdf.multi_cell(0, 5, T("Grafik gorsele cevrilemedi. 'kaleido' paketi gerekli: pip install -U kaleido"))
                else:
                    pdf.multi_cell(0, 5, T(f"Grafik gorsele cevrilemedi: {error_msg}"))
                pdf.set_text_color(40, 40, 40)
                continue

            try:
                with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                    tmp.write(png)
                    img_path = tmp.name

                pdf.image(img_path, x=10, w=190)

                try:
                    os.remove(img_path)
                except Exception:
                    pass
            except Exception as img_err:
                charts_failed += 1
                pdf.set_font(font, '', 9)
                pdf.set_text_color(*DANGER)
                pdf.multi_cell(0, 5, T(f"Grafik PDF'e eklenemedi: {str(img_err)[:100]}"))
                pdf.set_text_color(40, 40, 40)

            pdf.ln(4)

        # Grafik uyarı notu
        if charts_failed > 0:
            pdf.ln(2)
            pdf.set_font(font, '', 8)
            pdf.set_text_color(*WARNING_C)
            pdf.multi_cell(0, 5, T(f"Not: {charts_added} grafik eklendi, {charts_failed} grafik eklenemedi."))
            pdf.set_text_color(40, 40, 40)

        # ═══════════════════════════════════════════
        #  FOOTER — Son bilgi satırı
        # ═══════════════════════════════════════════
        pdf.ln(6)
        pdf.set_fill_color(*HEADER_BG)
        footer_y = pdf.get_y()
        pdf.rect(0, footer_y, 210, 12, 'F')
        pdf.set_font(font, 'I', 8)
        pdf.set_text_color(*GRAY)
        pdf.set_y(footer_y + 2)
        pdf.cell(0, 8, T(f"Bu rapor HVAC Enerji Yonetim Sistemi tarafindan {_dt_now.now().strftime('%d.%m.%Y %H:%M')} tarihinde otomatik olusturulmustur."), 0, 0, 'C')

        raw = pdf.output(dest="S")
        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw)
        return raw.encode("latin-1", errors="ignore")

    except Exception as e:
        error_pdf = FPDF(orientation="P", unit="mm", format="A4")
        error_pdf.add_page()
        error_pdf.set_fill_color(*HEADER_BG)
        error_pdf.rect(0, 0, 210, 30, 'F')
        error_pdf.set_font("Helvetica", "B", 16)
        error_pdf.set_text_color(*WHITE)
        error_pdf.set_y(8)
        error_pdf.cell(0, 10, "PDF Olusturma Hatasi", 0, 1, 'C')
        error_pdf.set_text_color(40, 40, 40)
        error_pdf.set_y(35)
        error_pdf.set_font("Helvetica", "", 11)
        error_pdf.multi_cell(0, 6, f"Rapor olusturulurken hata meydana geldi:\n\n{str(e)}")
        error_pdf.ln(5)
        error_pdf.multi_cell(0, 6, "Kontrol edin:\n- Kaleido paketi yuklu mu (pip install -U kaleido)\n- Veri gecerli mi\n- Yeterli disk alani var mi")

        raw = error_pdf.output(dest="S")
        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw)
        return raw.encode("latin-1", errors="ignore")



# =============================
# UI
# =============================
st.title("🏥 Enerji Yönetimi & Raporlama Sistemi")

# Sağ üst: Günlük + Aylık Rapor butonları
# Otomatik rapor bildirimlerini kontrol et
import json as _notif_json
_notif_file = os.path.join(os.path.dirname(__file__), "configs", "report_notifications.json")
_auto_notifs = {}
if os.path.exists(_notif_file):
    try:
        with open(_notif_file, "r", encoding="utf-8") as _nf:
            _auto_notifs = _notif_json.load(_nf)
    except Exception:
        pass

_daily_notif = _auto_notifs.get("daily", {})
_monthly_notif = _auto_notifs.get("monthly", {})
_daily_auto_ready = _daily_notif.get("filepath") and os.path.exists(_daily_notif.get("filepath", "")) and not _daily_notif.get("seen", True)
_monthly_auto_ready = _monthly_notif.get("filepath") and os.path.exists(_monthly_notif.get("filepath", "")) and not _monthly_notif.get("seen", True)

# Yeşil buton CSS (otomatik rapor hazır olduğunda)
if _daily_auto_ready or _monthly_auto_ready:
    st.markdown("""
    <style>
    .auto-report-ready {
        background: linear-gradient(135deg, #059669, #10b981) !important;
        border: 1px solid #34d399 !important;
        border-radius: 8px;
        padding: 10px 14px;
        margin: 4px 0;
        animation: pulse-green 2s ease-in-out infinite;
    }
    @keyframes pulse-green {
        0%, 100% { box-shadow: 0 0 5px rgba(16,185,129,0.3); }
        50% { box-shadow: 0 0 15px rgba(16,185,129,0.6); }
    }
    </style>
    """, unsafe_allow_html=True)

_dr_col1, _dr_col2, _dr_col3 = st.columns([3, 1, 1])
with _dr_col1:
    st.caption("Günlük veri • Excel import • Karşılaştır • PDF rapor")
with _dr_col2:
    if _daily_auto_ready:
        st.markdown('<div class="auto-report-ready">✅ Günlük Rapor Hazır!</div>', unsafe_allow_html=True)
    if st.button("📄 Günlük Rapor Oluştur" if not _daily_auto_ready else "🔄 Yeniden Oluştur", key="daily_report_btn", use_container_width=True):
        try:
            import sys
            sys.path.insert(0, os.path.dirname(__file__))
            from daily_report import DailyReportGenerator
            gen = DailyReportGenerator()
            _dr_path = gen.generate()
            st.session_state["daily_report_path"] = _dr_path
            st.session_state["daily_report_ready"] = True
            st.rerun()
        except Exception as e:
            st.error(f"Rapor oluşturulamadı: {e}")
with _dr_col3:
    if _monthly_auto_ready:
        st.markdown('<div class="auto-report-ready">✅ Aylık Rapor Hazır!</div>', unsafe_allow_html=True)
    if st.button("📊 Aylık Rapor Oluştur" if not _monthly_auto_ready else "🔄 Yeniden Oluştur", key="monthly_report_btn", use_container_width=True):
        try:
            import sys
            sys.path.insert(0, os.path.dirname(__file__))
            from monthly_summary_report import MonthlyReportGenerator
            gen = MonthlyReportGenerator()
            _mr_path = gen.generate()
            st.session_state["monthly_report_path"] = _mr_path
            st.session_state["monthly_report_ready"] = True
            st.rerun()
        except Exception as e:
            st.error(f"Aylık rapor oluşturulamadı: {e}")

# Otomatik günlük rapor bildirim + indirme
if _daily_auto_ready and not st.session_state.get("daily_report_ready"):
    _auto_dr_path = _daily_notif["filepath"]
    _auto_dr_size = round(os.path.getsize(_auto_dr_path) / 1024, 1)
    _auto_dr_name = os.path.basename(_auto_dr_path)
    st.success(f"🟢 Günlük rapor otomatik oluşturuldu! ({_daily_notif.get('timestamp', '')}) — {_auto_dr_size} KB")
    with open(_auto_dr_path, "rb") as _adr_f:
        if st.download_button(
            label="⬇️ Günlük PDF İndir",
            data=_adr_f.read(),
            file_name=_auto_dr_name,
            mime="application/pdf",
            key="auto_daily_download"
        ):
            # Bildirimi okundu olarak işaretle
            _auto_notifs["daily"]["seen"] = True
            with open(_notif_file, "w", encoding="utf-8") as _wnf:
                _notif_json.dump(_auto_notifs, _wnf, indent=2, ensure_ascii=False)

# Otomatik aylık rapor bildirim + indirme
if _monthly_auto_ready and not st.session_state.get("monthly_report_ready"):
    _auto_mr_path = _monthly_notif["filepath"]
    _auto_mr_size = round(os.path.getsize(_auto_mr_path) / 1024, 1)
    _auto_mr_name = os.path.basename(_auto_mr_path)
    st.success(f"🟢 Aylık rapor otomatik oluşturuldu! ({_monthly_notif.get('timestamp', '')}) — {_auto_mr_size} KB")
    with open(_auto_mr_path, "rb") as _amr_f:
        if st.download_button(
            label="⬇️ Aylık PDF İndir",
            data=_amr_f.read(),
            file_name=_auto_mr_name,
            mime="application/pdf",
            key="auto_monthly_download"
        ):
            _auto_notifs["monthly"]["seen"] = True
            with open(_notif_file, "w", encoding="utf-8") as _wnf2:
                _notif_json.dump(_auto_notifs, _wnf2, indent=2, ensure_ascii=False)

# Manuel günlük rapor bildirim
if st.session_state.get("daily_report_ready"):
    _dr_path = st.session_state.get("daily_report_path", "")
    if _dr_path and os.path.exists(_dr_path):
        _dr_size = round(os.path.getsize(_dr_path) / 1024, 1)
        _dr_name = os.path.basename(_dr_path)
        st.success(f"📄 Günlük özel PDF'iniz gönderilmek üzere hazırlanmıştır. ({_dr_size} KB)")
        with open(_dr_path, "rb") as _dr_f:
            st.download_button(
                label="⬇️ Günlük PDF İndir",
                data=_dr_f.read(),
                file_name=_dr_name,
                mime="application/pdf",
                key="daily_report_download"
            )

# Manuel aylık rapor bildirim
if st.session_state.get("monthly_report_ready"):
    _mr_path = st.session_state.get("monthly_report_path", "")
    if _mr_path and os.path.exists(_mr_path):
        _mr_size = round(os.path.getsize(_mr_path) / 1024, 1)
        _mr_name = os.path.basename(_mr_path)
        st.success(f"📊 Aylık özel PDF'iniz gönderilmek üzere hazırlanmıştır. ({_mr_size} KB)")
        with open(_mr_path, "rb") as _mr_f:
            st.download_button(
                label="⬇️ Aylık PDF İndir",
                data=_mr_f.read(),
                file_name=_mr_name,
                mime="application/pdf",
                key="monthly_report_download"
            )

df = load_data()

# Query parameter ile tab seçimi
# URL'de ?page=dashboard veya ?page=karsilastirma varsa Dashboard sekmesi açılır
query_params = st.query_params
default_tab = 0  # Varsayılan: Veri Girişi tab'ı

page_param = query_params.get("page", "")
if page_param in ["dashboard", "karsilastirma", "grafik", "grafikler"]:
    default_tab = 1  # Dashboard & Karşılaştırma tab'ı

# TAB isimleri
TAB_NAMES = [
    "1) Veri Girişi & Excel İçe Aktarım",
    "2) Dashboard & Karşılaştırma",
    "3) PDF Rapor",
    "4) Veri Görüntüleme",
    "5) 📈 Aylık Birleşik Rapor",
    "6) 🔮 Tahmin & Trend",
]

tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(TAB_NAMES)

# ---------------- TAB 1 ----------------
with tab1:
    st.subheader("Günlük Veri Girişi (Tarih bazlı güncelle/ekle)")

    with st.form("daily_entry_form", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)

        with c1:
            tarih = st.date_input("Tarih", value=date.today(), key="entry_tarih")
            dis_hava = st.number_input("Dış Hava Sıcaklığı (°C)", value=0.0, step=0.5, key="entry_dis_hava")
            kar_eritme = st.checkbox("Kar Eritme Aktif (On/Off)", value=False, key="entry_kar")

        with c2:
            st.markdown("**Chiller / Kazan**")
            ch_set = st.number_input("Chiller Set Temp (°C)", value=6.5, step=0.5, key="entry_ch_set")
            ch_count = st.number_input("Chiller Adet (Çalışan)", value=0, step=1, min_value=0, key="entry_ch_count")
            abs_count = st.number_input("Absorption Chiller Adet", value=0, step=1, min_value=0, key="entry_abs_count")
            kazan_count = st.number_input("Kazan Adet", value=0, step=1, min_value=0, key="entry_kazan_count")

        with c3:
            # Lokasyona göre sıcaklık alanları
            if _has_dual_lines:
                # Maslak: çift hat
                st.markdown("**Mas-1 / Mas-2 Sıcaklıkları**")
                mas1_h = st.number_input("Mas-1 Isıtma Temp", value=0.0, step=0.5, key="entry_mas1_h")
                mas1_k = st.number_input("Mas-1 Kazan Temp", value=0.0, step=0.5, key="entry_mas1_k")
                mas1_c = st.number_input("Mas-1 Soğutma Temp", value=0.0, step=0.5, key="entry_mas1_c")
                mas2_h = st.number_input("Mas-2 Isıtma Temp", value=0.0, step=0.5, key="entry_mas2_h")
                mas2_k = st.number_input("Mas-2 Kazan Temp", value=0.0, step=0.5, key="entry_mas2_k")
                mas2_c = st.number_input("Mas-2 Soğutma Temp", value=0.0, step=0.5, key="entry_mas2_c")
            else:
                # Altunizade vb.: tek hat
                _single_labels = _energy_schema.get("single_labels", {})
                st.markdown("**Sıcaklık Değerleri**")
                single_h = st.number_input(_single_labels.get("heating_temp", "Isıtma Temp"), value=0.0, step=0.5, key="entry_single_h")
                single_k = st.number_input(_single_labels.get("boiler_temp", "Kazan Temp"), value=0.0, step=0.5, key="entry_single_k")
                single_c = st.number_input(_single_labels.get("cooling_temp", "Soğutma Temp"), value=0.0, step=0.5, key="entry_single_c")

        st.divider()
        st.subheader("Tüketim / Üretim")

        a1, a2, a3 = st.columns(3)
        with a1:
            sebeke = st.number_input("Şebeke Tüketim (kWh)", value=0.0, step=50.0, min_value=0.0, key="entry_sebeke")
            koj = st.number_input("Kojen Üretim (kWh)", value=0.0, step=50.0, min_value=0.0, key="entry_kojen")
            su = st.number_input("Su Tüketimi (m³)", value=0.0, step=1.0, min_value=0.0, key="entry_su")
        with a2:
            kazan_gaz = st.number_input("Kazan Doğalgaz (m³)", value=0.0, step=10.0, min_value=0.0, key="entry_kazan_gaz")
            koj_gaz = st.number_input("Kojen Doğalgaz (m³)", value=0.0, step=10.0, min_value=0.0, key="entry_kojen_gaz")
        with a3:
            ch_kwh = st.number_input("Chiller Tüketim (kWh)", value=0.0, step=50.0, min_value=0.0, key="entry_ch_kwh")
            mcc_kwh = st.number_input("MCC Tüketim (kWh)", value=0.0, step=50.0, min_value=0.0, key="entry_mcc_kwh")
            vrf_kwh = st.number_input("VRF/Split Tüketim (kWh) (varsa)", value=0.0, step=25.0, min_value=0.0, key="entry_vrf_kwh")

        preview_total_h = sebeke + koj
        preview_total_cool = ch_kwh + vrf_kwh
        preview_other = max(0.0, preview_total_h - (ch_kwh + mcc_kwh))
        st.info(
            f"**Otomatik Hesap Önizleme:** "
            f"Toplam Hastane = **{preview_total_h:,.0f} kWh**, "
            f"Toplam Soğutma = **{preview_total_cool:,.0f} kWh**, "
            f"Diğer Yük = **{preview_other:,.0f} kWh**"
        )

        ok = st.form_submit_button("💾 Kaydet")

    if ok:
        try:
            # Yeni satırı hazırla
            new_row = {
                "Tarih": tarih,
                "Chiller_Set_Temp_C": ch_set,
                "Chiller_Adet": int(ch_count),
                "Absorption_Chiller_Adet": int(abs_count),
                "Kazan_Adet": int(kazan_count),
            }
            # Lokasyona göre sıcaklık sütunları
            if _has_dual_lines:
                new_row.update({
                    "Mas1_Isitma_Temp": mas1_h,
                    "Mas1_Kazan_Temp": mas1_k,
                    "Mas1_Sogutma_Temp": mas1_c,
                    "Mas2_Isitma_Temp": mas2_h,
                    "Mas2_Kazan_Temp": mas2_k,
                    "Mas2_Sogutma_Temp": mas2_c,
                })
            else:
                new_row.update({
                    "Isitma_Temp_C": single_h,
                    "Kazan_Temp_C": single_k,
                    "Sogutma_Temp_C": single_c,
                })
            new_row.update({
                "Kar_Eritme_Aktif": bool(kar_eritme),
                "Sebeke_Tuketim_kWh": sebeke,
                "Kojen_Uretim_kWh": koj,
                "Kazan_Dogalgaz_m3": kazan_gaz,
                "Kojen_Dogalgaz_m3": koj_gaz,
                "Su_Tuketimi_m3": su,
                "Chiller_Tuketim_kWh": ch_kwh,
                "MCC_Tuketim_kWh": mcc_kwh,
                "VRF_Split_Tuketim_kWh": vrf_kwh,
                "Dis_Hava_Sicakligi_C": dis_hava,
            })
            
            # ANOMALİ KONTROLÜ
            existing_data = load_data()
            alerts = check_daily_anomalies(new_row, existing_data)
            
            if alerts:
                # Anomali var -> State'e at ve sayfa yenile (Onay UI'ı tetiklenecek)
                st.session_state.pending_row = new_row
                st.session_state.anomalies = alerts
                st.session_state.confirm_needed = True
                st.rerun()
            else:
                # Sorun yok -> Direkt kaydet
                save_single_row(new_row)
                st.success("✅ Kayıt işlendi: Tarih varsa güncellendi, yoksa eklendi.")
        except Exception as e:
            st.error(f"Kayıt hatası: {e}")

    # ----- FORMDAN BAĞIMSIZ ONAY ALANI (State kontrolü) -----
    if st.session_state.get("confirm_needed"):
        st.warning("⚠️ **Dikkat: Ani değişiklikler tespit edildi!**")
        
        alerts = st.session_state.get("anomalies", [])
        for alert in alerts:
            if alert.get("severity") == "CRITICAL":
                st.error(f"🚨 **{alert.get('metric', '')}**: {alert.get('message', '')}")
            else:
                st.warning(f"📈 **{alert.get('metric', '')}**: {alert.get('message', '')}")
        
        st.info("Kaydetmek istiyor musunuz?")
        
        c_yes, c_no = st.columns(2)
        with c_yes:
            if st.button("✅ Uyarılara Rağmen Kaydet", key="btn_confirm_save"):
                try:
                    row_to_save = st.session_state.get("pending_row")
                    if row_to_save:
                        save_single_row(row_to_save)
                        st.success("✅ Kayıt başarıyla tamamlandı.")
                    
                    # State Temizliği
                    st.session_state.confirm_needed = False
                    st.session_state.pending_row = None
                    st.session_state.anomalies = []
                    st.rerun()
                except Exception as e:
                    st.error(f"Onaylı kayıt hatası: {e}")
        
        with c_no:
            if st.button("❌ İptal Et", key="btn_cancel_save"):
                st.session_state.confirm_needed = False
                st.session_state.pending_row = None
                st.session_state.anomalies = []
                st.info("İşlem iptal edildi.")
                st.rerun()
    # --------------------------------------------------------

    st.divider()
    st.subheader("Toplu Excel Yükleme — Tarih Bazlı UPSERT")

    left, right = st.columns([2, 1])
    with right:
        st.download_button(
            "⬇️ Excel Şablonu İndir",
            data=build_excel_template(),
            file_name="enerji_veri_sablonu.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="btn_template_download",
        )
        st.caption("Header satırı yanlışsa Tarih sütunu var olsa bile 'yok' sanır. Buradan düzelt.")

    with left:
        uploaded = st.file_uploader("Excel dosyası seç (xlsx/xls)", type=["xlsx", "xls"], key="bulk_excel_uploader")
        if uploaded is not None:
            try:
                xls = pd.ExcelFile(uploaded)
                sheet = st.selectbox("Sheet seç", options=xls.sheet_names, index=0, key="bulk_sheet_select")

                colA, colB = st.columns([1, 2])
                with colA:
                    header_row = st.number_input("Başlık satırı (0=ilk satır)", min_value=0, max_value=300, value=0, step=1, key="bulk_header_row")
                with colB:
                    if st.button("🧠 Başlık satırını otomatik bul", key="btn_auto_header"):
                        hdr = auto_detect_header_row(uploaded, sheet_name=sheet, max_rows=80)
                        if hdr is None:
                            st.warning("Başlık satırı otomatik tespit edilemedi. Elle değiştir.")
                        else:
                            st.session_state["bulk_header_row"] = int(hdr)
                            st.success(f"Başlık satırı bulundu: {hdr}")

                raw = pd.read_excel(uploaded, sheet_name=sheet, header=int(st.session_state.get("bulk_header_row", header_row)))
                raw = flatten_columns(raw)

                st.caption("Ham kolonlar:")
                st.code(", ".join(raw.columns.astype(str).tolist()[:60]))

                df_import, info = normalize_import_df(raw)

                if info.get("date_detect"):
                    st.warning(info["date_detect"])

                st.write("🧩 Eşleştirilen sütunlar (Excel → Sistem):")
                st.json(info["mapped"] if info["mapped"] else {"info": "Eşleştirme az; tarih içerikten yakalanmış olabilir."})

                st.write("Önizleme (ilk 30 satır):")
                st.dataframe(df_import.head(30), use_container_width=True)

                existing = load_data()
                existing_dates = set(existing["Tarih"].tolist()) if not existing.empty else set()
                new_dates = set(df_import["Tarih"].tolist())
                upd = len(existing_dates.intersection(new_dates))
                ins = len(new_dates - existing_dates)
                st.warning(f"Bu yükleme sonucu: **{upd}** güncellenecek, **{ins}** yeni satır eklenecek.")

                if st.button("✅ Excel’i İçe Aktar (Güncelle/Ekle)", key="btn_bulk_import"):
                    # Anomali kontrolu
                    existing_data = load_data()
                    alerts_all = []
                    for _, row in df_import.iterrows():
                        alerts = check_daily_anomalies(row.to_dict(), existing_data)
                        alerts_all.extend(alerts)
                    
                    u, i = upsert_by_date(df_import)
                    st.success(f"Tamamlandı. Güncellenen: {u} • Eklenen: {i}")
                    
                    # Uyarilari goster
                    if alerts_all:
                        st.markdown("#### ⚠️ Anlık Değişim Uyarıları")
                        for alert in alerts_all[:8]:
                            if alert["type"] == "YUKSELIS":
                                st.warning(f"{alert['icon']} **{alert['metric']}**: {alert['old']:,.0f} → {alert['new']:,.0f} ({alert['change']:+.0f}%)")
                            else:
                                st.info(f"{alert['icon']} **{alert['metric']}**: {alert['old']:,.0f} → {alert['new']:,.0f} ({alert['change']:.0f}%)")

            except Exception as e:
                st.error(f"Excel içe aktarım hatası: {e}")

    st.divider()
    st.subheader("Mevcut Veri (CSV)")
    df_now = load_data()
    if df_now.empty:
        st.warning("Henüz veri yok.")
    else:
        render_styled_table(df_now, table_key="mevcut_veri")
        exp = df_now.copy()
        exp["Tarih"] = exp["Tarih"].astype(str)
        st.download_button(
            "⬇️ CSV indir",
            data=exp.to_csv(index=False).encode("utf-8"),
            file_name="energy_data_export.csv",
            mime="text/plain",
            key="btn_csv_export",
        )

# ---------------- TAB 2 ----------------
with tab2:
    st.subheader("Dashboard & Karşılaştırma")
    df = load_data()
    if df.empty:
        st.warning("Dashboard için veri gerekli.")
    else:
        # ===== GÜNLÜK ÖZET KARTLARI (Sayfa açılınca ilk görünen bölüm) =====
        from datetime import timedelta
        
        # Kullanıcı talebi: Kartlar "Bugün" yerine "Dün"ü (tamamlanmış günü) göstermeli
        today_date = date.today()
        report_date = today_date - timedelta(days=1)  # Dün (Esas rapor günü)
        compare_date = report_date - timedelta(days=1)   # Dünden önceki gün (Kıyaslama)
        
        # Veri filtreleme
        report_mask = df["Tarih"] == report_date
        compare_mask = df["Tarih"] == compare_date
        
        report_data = df[report_mask]
        compare_data = df[compare_mask]
        
        # Değerleri hesapla (Rapor Günü - Dün)
        if not report_data.empty:
            rep_total = float(report_data["Toplam_Hastane_Tuketim_kWh"].fillna(0).iloc[0])
            rep_chiller = float(report_data["Chiller_Tuketim_kWh"].fillna(0).iloc[0])
            rep_gas = float(report_data["Kazan_Dogalgaz_m3"].fillna(0).iloc[0]) + float(report_data["Kojen_Dogalgaz_m3"].fillna(0).iloc[0])
            rep_grid = float(report_data["Sebeke_Tuketim_kWh"].fillna(0).iloc[0]) if "Sebeke_Tuketim_kWh" in report_data.columns else 0
        else:
            rep_total = 0
            rep_chiller = 0
            rep_gas = 0
            rep_grid = 0
        
        # Kıyaslama (Dünden önceki gün)
        if not compare_data.empty and rep_total > 0:
            compare_total = float(compare_data["Toplam_Hastane_Tuketim_kWh"].fillna(0).iloc[0])
            if compare_total > 0:
                pct_change = ((rep_total - compare_total) / compare_total) * 100
                delta_str = f"{pct_change:+.1f}% (önceki güne göre)"
            else:
                delta_str = None
        else:
            delta_str = None
        
        # HVAC Uyarıları (dünkü analiz verisi - enerji verileriyle tutarlılık için)
        try:
            from monthly_report.hvac_history import HVACHistoryManager
            hvac_hist = HVACHistoryManager()
            hvac_df = hvac_hist.load_history()
            
            if not hvac_df.empty and "Tarih" in hvac_df.columns:
                # Tarih sütununu date'e çevir
                hvac_df["Tarih"] = pd.to_datetime(hvac_df["Tarih"], format="%Y-%m-%d", errors="coerce").dt.date
                
                # Dünkü veriler (enerji kartlarıyla aynı gün: report_date)
                yesterday_hvac = hvac_df[hvac_df["Tarih"] == report_date]
                
                if not yesterday_hvac.empty:
                    # En son kaydı al (aynı gün birden fazla analiz yapılmış olabilir)
                    latest = yesterday_hvac.iloc[-1]
                    critical_count = int(latest.get("Kritik_Sorun_Adet", 0) or 0)
                    warning_count = int(latest.get("Uyari_Adet", 0) or 0)
                else:
                    # Dün için HVAC verisi yok
                    critical_count = None
                    warning_count = None
            else:
                critical_count = None
                warning_count = None
        except Exception:
            critical_count = None
            warning_count = None
        
        # Sistem Sağlık Durumu hesaplama (Kritik ve Uyarı sayılarına göre)
        if critical_count is not None and warning_count is not None:
            # Puan kırma: Her kritik -15, her uyarı -5
            penalty = (critical_count * 15) + (warning_count * 5)
            health_score = max(0, 100 - penalty)
            
            if health_score >= 80:
                health_status = "İyi"
                health_color = "🟢"
            elif health_score >= 50:
                health_status = "Dikkat"
                health_color = "🟡"
            else:
                health_status = "Kritik"
                health_color = "🔴"
        else:
            health_score = None
            health_status = "Veri Yok"
            health_color = "⚪"
        
        # Kartları göster
        # ─── CSS ile bölüm kartları ───
        st.markdown("""
        <style>
        .dash-section {
            background: linear-gradient(135deg, rgba(15,23,42,0.7), rgba(30,41,59,0.5));
            border: 1px solid rgba(59,130,246,0.25);
            border-radius: 12px;
            padding: 16px 20px 12px 20px;
            margin-bottom: 12px;
        }
        .dash-section-title {
            font-size: 17px;
            font-weight: 700;
            color: #e2e8f0;
            margin-bottom: 10px;
            padding-bottom: 6px;
            border-bottom: 2px solid rgba(59,130,246,0.3);
        }
        .dash-section.m2-section {
            border-color: rgba(139,92,246,0.35);
        }
        .dash-section.m2-section .dash-section-title {
            border-bottom-color: rgba(139,92,246,0.4);
        }
        .dash-section.cost-section {
            border-color: rgba(245,158,11,0.35);
        }
        .dash-section.cost-section .dash-section-title {
            border-bottom-color: rgba(245,158,11,0.4);
        }
        </style>
        """, unsafe_allow_html=True)
        
        # ═══ 1. DÜNÜN ÖZETİ ═══
        with st.container(border=True):
            st.markdown(f"**📊 Dünün Özeti — {report_date.strftime('%d.%m.%Y')}**")
            if report_data.empty:
                st.info(f"📅 {report_date.strftime('%d.%m.%Y')} için henüz veri girilmedi.")
            else:
                sc1, sc2, sc3, sc4, sc5 = st.columns(5)
                with sc1:
                    st.metric("⚡ Dünkü Tüketim", f"{rep_total:,.0f} kWh".replace(",", "."), delta=delta_str)
                with sc2:
                    st.metric("❄️ Chiller Tüketimi", f"{rep_chiller:,.0f} kWh".replace(",", "."))
                with sc3:
                    st.metric("🔥 Doğalgaz", f"{rep_gas:,.0f} m³".replace(",", "."))
                with sc4:
                    if critical_count is not None:
                        alert_color = "🔴" if critical_count > 0 else ("🟡" if warning_count > 0 else "🟢")
                        st.metric(f"{alert_color} Aktif Uyarılar", f"{critical_count} Kritik / {warning_count} Uyarı")
                    else:
                        st.metric("⚪ Aktif Uyarılar", "Veri yok", help=f"{report_date.strftime('%d.%m.%Y')} için HVAC analizi bulunamadı")
                with sc5:
                    if health_score is not None:
                        st.metric(f"{health_color} Sistem Sağlığı", f"%{health_score}", delta=health_status, delta_color="off")
                    else:
                        st.metric("⚪ Sistem Sağlığı", "--", delta="Veri yok", delta_color="off")
        
        # Settings'i bir kez oku (m² ve maliyet bölümleri için)
        try:
            import json as _json
            _settings_path = os.path.join(os.path.dirname(__file__), "configs", "hvac_settings.json")
            _all_settings = {}
            if os.path.exists(_settings_path):
                with open(_settings_path, "r", encoding="utf-8") as _f:
                    _all_settings = _json.load(_f)
        except Exception:
            _all_settings = {}
        
        building_area = float(_all_settings.get("BUILDING_AREA_M2", 0))
        price_elec = float(_all_settings.get("UNIT_PRICE_ELECTRICITY", 0))
        price_gas = float(_all_settings.get("UNIT_PRICE_GAS", 0))
        price_water = float(_all_settings.get("UNIT_PRICE_WATER", 0))
        
        # ═══ 2. m² BAŞINA TÜKETİM ═══
        if building_area and building_area > 0 and not report_data.empty:
            with st.container(border=True):
                st.markdown(f"**📐 m² Başına Tüketim — {building_area:,.0f} m²**".replace(",", "."))
                ma1, ma2, ma3 = st.columns(3)
                with ma1:
                    cooling_per_m2 = rep_chiller / building_area
                    st.metric("❄️ Soğutma", f"{cooling_per_m2:.2f} kWh/m²")
                with ma2:
                    heating_kwh = rep_gas * 10.64
                    heating_per_m2 = heating_kwh / building_area
                    st.metric("🔥 Isıtma", f"{heating_per_m2:.2f} kWh/m²")
                with ma3:
                    total_per_m2 = rep_total / building_area
                    st.metric("⚡ Toplam Enerji", f"{total_per_m2:.2f} kWh/m²")
        
        # ═══ 3. DÜNKÜ MALİYET ═══
        has_any_price = price_elec > 0 or price_gas > 0 or price_water > 0
        if has_any_price and not report_data.empty:
            cost_elec = rep_grid * price_elec if price_elec > 0 else 0
            cost_gas = rep_gas * price_gas if price_gas > 0 else 0
            rep_water = 0
            if "Su_Tuketimi_m3" in report_data.columns:
                rep_water = float(report_data.iloc[0].get("Su_Tuketimi_m3", 0) or 0)
            cost_water = rep_water * price_water if price_water > 0 else 0
            cost_total = cost_elec + cost_gas + cost_water
            
            with st.container(border=True):
                st.markdown("**💰 Dünkü Maliyet Tahmini**")
                cost_count = sum([price_elec > 0, price_gas > 0, price_water > 0, True])
                cost_cols = st.columns(cost_count)
                col_idx = 0
                
                if price_elec > 0:
                    with cost_cols[col_idx]:
                        st.metric("⚡ Elektrik", f"₺{cost_elec:,.0f}".replace(",", "."),
                                  delta=f"{price_elec:.2f} TL/kWh", delta_color="off")
                    col_idx += 1
                
                if price_gas > 0:
                    with cost_cols[col_idx]:
                        st.metric("🔥 Doğalgaz", f"₺{cost_gas:,.0f}".replace(",", "."),
                                  delta=f"{price_gas:.2f} TL/m³", delta_color="off")
                    col_idx += 1
                
                if price_water > 0:
                    with cost_cols[col_idx]:
                        st.metric("💧 Su", f"₺{cost_water:,.0f}".replace(",", "."),
                                  delta=f"{price_water:.2f} TL/m³", delta_color="off")
                    col_idx += 1
                
                with cost_cols[col_idx]:
                    st.metric("💰 Toplam Maliyet", f"₺{cost_total:,.0f}".replace(",", "."))
        
        st.divider()
        # ===== /GÜNLÜK ÖZET KARTLARI =====
        
        years = sorted({d.year for d in df["Tarih"].tolist()})
        month_periods = sorted({pd.to_datetime(d).to_period("M") for d in df["Tarih"].tolist()})
        month_labels = [str(p) for p in month_periods]

        st.markdown("### Grafik Aralığı Daraltma (Kaydırıcı)")
        scope = st.radio("Daraltma tipi", ["Yıl Bazlı", "Ay Bazlı"], horizontal=True, key="dash_scope_radio")

        if scope == "Yıl Bazlı":
            y1, y2 = st.select_slider("Yıl aralığı", options=years, value=(years[0], years[-1]), key="dash_year_slider")
            start_scope = date(int(y1), 1, 1)
            end_scope = date(int(y2) + 1, 1, 1)
        else:
            m1, m2 = st.select_slider("Ay aralığı (YYYY-MM)", options=month_labels, value=(month_labels[0], month_labels[-1]), key="dash_month_slider")
            p1 = pd.Period(m1, freq="M")
            p2 = pd.Period(m2, freq="M")
            start_scope = p1.start_time.date()
            end_scope = (p2.end_time + pd.Timedelta(days=1)).date()

        df_scope = filter_range(df, start_scope, end_scope)

        st.divider()
        mode = st.radio("Karşılaştırma modu", ["Ay/Yıl Seç (YoY)", "Özel Tarih Aralığı"], horizontal=True, key="dash_mode_radio")

        if mode == "Ay/Yıl Seç (YoY)":
            c1, c2, c3 = st.columns([1, 1, 2])
            ys = sorted({d.year for d in df_scope["Tarih"].tolist()}) or years
            with c1:
                sel_year = st.selectbox("Yıl", options=ys, index=len(ys) - 1, key="dash_year_select")
            with c2:
                sel_month = st.selectbox("Ay", options=list(range(1, 13)), index=0, key="dash_month_select")
            with c3:
                view_mode = st.radio("Grafik detayı", ["Günlük", "Aylık", "Yıllık"], horizontal=True, key="dash_viewmode_radio")

            start, end = month_range(int(sel_year), int(sel_month))
            df_period = filter_range(df_scope, start, end)
            yoy = yoy_month_compare(df, int(sel_year), int(sel_month))
        else:
            c1, c2, c3 = st.columns([1, 1, 2])
            with c1:
                start = st.date_input("Başlangıç", value=min(df_scope["Tarih"]), key="dash_start_date")
            with c2:
                end_incl = st.date_input("Bitiş", value=max(df_scope["Tarih"]), key="dash_end_date")
            with c3:
                view_mode = st.radio("Grafik detayı", ["Günlük", "Aylık", "Yıllık"], horizontal=True, key="dash_viewmode_radio2")
            end = (pd.to_datetime(end_incl) + pd.Timedelta(days=1)).date()
            df_period = filter_range(df_scope, start, end)
            yoy = None

        def sumcol(dfx, col):
            return float(dfx[col].fillna(0).sum()) if not dfx.empty else 0.0

        total_h = sumcol(df_period, "Toplam_Hastane_Tuketim_kWh")
        total_grid = sumcol(df_period, "Sebeke_Tuketim_kWh")
        total_cool = sumcol(df_period, "Toplam_Sogutma_Tuketim_kWh")
        total_gas = sumcol(df_period, "Kazan_Dogalgaz_m3") + sumcol(df_period, "Kojen_Dogalgaz_m3")
        avg_temp = float(df_period["Dis_Hava_Sicakligi_C"].astype(float).mean()) if not df_period.empty else 0.0

        st.markdown("### Özet Göstergeler")
        k1, k2, k3, k4, k5 = st.columns(5)

        def metric_yoy(col_key, label, val, unit):
            if yoy and col_key in yoy["metrics"]:
                cur_v, prev_v = yoy["metrics"][col_key]
                pct = safe_pct_change(cur_v, prev_v)
                delta = f"{pct:+.1f}%" if pct is not None else "N/A"
                st.metric(label, f"{val:,.0f}".replace(",", ".") + f" {unit}", delta)
            else:
                st.metric(label, f"{val:,.0f}".replace(",", ".") + f" {unit}")

        with k1:
            metric_yoy("Toplam_Hastane_Tuketim_kWh", "Toplam Hastane", total_h, "kWh")
        with k2:
            metric_yoy("Sebeke_Tuketim_kWh", "Şebeke", total_grid, "kWh")
        with k3:
            metric_yoy("Toplam_Sogutma_Tuketim_kWh", "Toplam Soğutma", total_cool, "kWh")
        with k4:
            st.metric("Toplam Doğalgaz", f"{total_gas:,.0f}".replace(",", ".") + " m³")
        with k5:
            st.metric("Ortalama Dış Hava", f"{avg_temp:,.1f}".replace(",", ".") + " °C")

        st.divider()
        st.markdown("### Grafikler")

        df_chart = aggregate_for_view(df_period, view_mode)
        fig_line = chart_consumption_vs_temp(df_chart)
        fig_stack = chart_stacked_breakdown(df_chart)
        fig_bar = chart_month_vs_last_year(yoy) if yoy else None

        left, right = st.columns([2, 1])
        with left:
            if fig_line:
                st.plotly_chart(fig_line, use_container_width=True)
            else:
                st.info("Seçilen aralıkta veri yok.")
        with right:
            if fig_bar:
                st.plotly_chart(fig_bar, use_container_width=True)
            else:
                st.info("YoY bar grafiği için 'Ay/Yıl Seç (YoY)' kullan.")

        if fig_stack:
            st.plotly_chart(fig_stack, use_container_width=True)

        st.divider()
        st.markdown("### Seçilen Dönem Verisi")
        render_styled_table(df_period.sort_values("Tarih"), table_key="dashboard")

# ---------------- TAB 3 ----------------
with tab3:
    st.subheader("PDF Rapor Üretici")
    df = load_data()
    if df.empty:
        st.warning("PDF rapor için veri gerekli.")
    else:
        st.caption("Grafikleri PDF’e gömmek için gerekirse: pip install -U kaleido")
        mode = st.radio("Rapor dönemi", ["Ay/Yıl (YoY dahil)", "Özel Tarih Aralığı"], horizontal=True, key="pdf_mode_radio")

        years = sorted({d.year for d in df["Tarih"].tolist()})
        yoy_info = None

        if mode == "Ay/Yıl (YoY dahil)":
            c1, c2 = st.columns(2)
            with c1:
                ry = st.selectbox("Yıl", options=years, index=len(years) - 1, key="pdf_year_select")
            with c2:
                rm = st.selectbox("Ay", options=list(range(1, 13)), index=0, key="pdf_month_select")

            start, end = month_range(int(ry), int(rm))
            df_period = filter_range(df, start, end)
            yoy_info = yoy_month_compare(df, int(ry), int(rm))
        else:
            c1, c2 = st.columns(2)
            with c1:
                start = st.date_input("Başlangıç", value=min(df["Tarih"]), key="pdf_start_date")
            with c2:
                end_incl = st.date_input("Bitiş", value=max(df["Tarih"]), key="pdf_end_date")
            end = (pd.to_datetime(end_incl) + pd.Timedelta(days=1)).date()
            df_period = filter_range(df, start, end)

        figs = {
            "Toplam Tüketim vs Dış Hava": chart_consumption_vs_temp(df_period),
            "Enerji Kırılımı (Stacked)": chart_stacked_breakdown(df_period),
        }
        if yoy_info:
            figs["Bu Ay vs Geçen Yıl Aynı Ay"] = chart_month_vs_last_year(yoy_info)

        if st.button("🧾 PDF Oluştur", key="pdf_generate_btn"):
            if df_period.empty:
                st.error("Seçilen aralıkta veri yok.")
            else:
                try:
                    pdf_bytes = generate_pdf_report(start, end, df_period, yoy_info, figs)
                    fname = f"enerji_raporu_{start.strftime('%Y%m%d')}_{(pd.to_datetime(end)-pd.Timedelta(days=1)).date().strftime('%Y%m%d')}.pdf"
                    st.download_button("⬇️ PDF’i indir", data=pdf_bytes, file_name=fname, mime="application/pdf", key="pdf_download_btn")
                except Exception as e:
                    st.error(f"PDF üretim hatası: {e}")

        st.divider()
        st.subheader("Rapor Verisi")
        render_styled_table(df_period.sort_values("Tarih"), table_key="pdf_rapor")

# ---------------- TAB 4 ----------------
with tab4:
    st.subheader("Veri Görüntüleme (Tüm geçmiş + filtre)")
    df = load_data()
    if df.empty:
        st.warning("Görüntülenecek veri yok.")
    else:
        f1, f2, f3, f4 = st.columns([1.2, 1.2, 1, 1])
        with f1:
            start = st.date_input("Başlangıç Tarihi", value=min(df["Tarih"]), key="view_start_date")
        with f2:
            end_incl = st.date_input("Bitiş Tarihi", value=max(df["Tarih"]), key="view_end_date")
        with f3:
            kar = st.selectbox("Kar Eritme", ["Hepsi", "Aktif", "Pasif"], index=0, key="view_kar_select")
        with f4:
            q = st.text_input("Hızlı arama (tüm satır)", value="", key="view_search_text")

        end_excl = (pd.to_datetime(end_incl) + pd.Timedelta(days=1)).date()
        dff = filter_range(df, start, end_excl)

        if kar == "Aktif":
            dff = dff[dff["Kar_Eritme_Aktif"] == True]
        elif kar == "Pasif":
            dff = dff[dff["Kar_Eritme_Aktif"] == False]

        if q.strip():
            qn = q.strip().lower().translate(TR_MAP)
            joined = dff.astype(str).apply(lambda r: " ".join(r.values.astype(str)), axis=1)
            joined = joined.str.lower().map(lambda v: v.translate(TR_MAP))
            dff = dff[joined.str.contains(re.escape(qn), na=False)]

        # Sadece DataFrame'de mevcut olan sütunları göster
        available_cols = [c for c in SCHEMA if c in dff.columns]
        cols = st.multiselect("Gösterilecek kolonlar", options=available_cols, default=available_cols, key="view_cols_multiselect")
        show = dff[cols].copy() if cols else dff.copy()

        st.caption(f"Filtrelenmiş satır sayısı: **{len(show)}**")
        render_styled_table(show.sort_values("Tarih"), max_height=520, table_key="veri_goruntuleme")

        exp = show.copy()
        exp["Tarih"] = exp["Tarih"].astype(str)
        st.download_button(
            "⬇️ Filtreli veriyi CSV indir",
            data=exp.to_csv(index=False).encode("utf-8"),
            file_name="energy_data_filtered.csv",
            mime="text/plain",
            key="view_export_filtered_btn",
        )

st.caption("Veriler 'energy_data.csv' dosyasında tutulur. Excel içe aktarım Tarih bazlı UPSERT (güncelle/ekle) yapar.")

# ---------------- TAB 5 ----------------
with tab5:
    st.subheader("📈 Aylık Birleşik Tasarruf Raporu")
    st.markdown("""
    Bu modül, **HVAC + Enerji** verilerini birleştirerek aylık değerlendirme raporu üretir.
    - Geçen yıl aynı aya göre karşılaştırma
    - Otomatik tasarruf önerileri
    - PDF formatında indirilebilir rapor
    """)
    
    try:
        from monthly_report import (
            UnifiedDataMerger, 
            YearOverYearAnalyzer, 
            SavingsRecommendationEngine,
            MonthlyReportPDFGenerator,
            ConsumptionForecastEngine
        )
        
        col1, col2, col3 = st.columns([1, 1, 2])
        with col1:
            report_year = st.selectbox("Yıl", options=list(range(2024, 2027)), index=2, key="monthly_report_year")
        with col2:
            report_month = st.selectbox("Ay", options=list(range(1, 13)), 
                                        format_func=lambda x: ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran",
                                                              "Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"][x-1],
                                        key="monthly_report_month")
        
        if st.button("📊 Rapor Oluştur", key="monthly_report_generate_btn"):
            with st.spinner("Veriler analiz ediliyor..."):
                # Veri birleştirme
                merger = UnifiedDataMerger()
                unified_data = merger.merge_monthly_data(report_year, report_month)
                
                # YoY analiz
                analyzer = YearOverYearAnalyzer(merger)
                yoy_analysis = analyzer.compare_month(report_year, report_month)
                
                # Tasarruf önerileri
                engine = SavingsRecommendationEngine()
                recommendations = engine.generate_recommendations(unified_data, yoy_analysis)
                rec_summary = engine.get_recommendation_summary(recommendations)
                
                st.success(f"Analiz tamamlandı! {unified_data.get('days_with_data', 0)} gün veri işlendi.")
                
                # Özet göstergeler
                st.markdown("### 📊 Özet Göstergeler")
                summary = unified_data.get("summary", {})
                
                m1, m2, m3, m4 = st.columns(4)
                with m1:
                    val = summary.get("total_grid_consumption", 0)
                    yoy_grid = yoy_analysis.get("comparisons", {}).get("total_grid_consumption", {})
                    delta = f"{yoy_grid.get('change_percent', 0):+.1f}%" if yoy_grid.get('change_percent') else None
                    st.metric("Şebeke Tüketimi", f"{val:,.0f} kWh", delta)
                with m2:
                    val = summary.get("total_cooling_consumption", 0)
                    yoy_cool = yoy_analysis.get("comparisons", {}).get("total_cooling_consumption", {})
                    delta = f"{yoy_cool.get('change_percent', 0):+.1f}%" if yoy_cool.get('change_percent') else None
                    st.metric("Soğutma Tüketimi", f"{val:,.0f} kWh", delta)
                with m3:
                    val = summary.get("total_gas", 0)
                    yoy_gas = yoy_analysis.get("comparisons", {}).get("total_gas", {})
                    delta = f"{yoy_gas.get('change_percent', 0):+.1f}%" if yoy_gas.get('change_percent') else None
                    st.metric("Toplam Doğalgaz", f"{val:,.0f} m³", delta)
                with m4:
                    chiller_set = summary.get("avg_chiller_set_temp")
                    if chiller_set:
                        yoy_ch = yoy_analysis.get("comparisons", {}).get("avg_chiller_set_temp", {})
                        delta = f"{yoy_ch.get('change_percent', 0):+.1f}%" if yoy_ch.get('change_percent') else None
                        st.metric("Ort. Chiller Set", f"{chiller_set:.1f}°C", delta)
                    else:
                        st.metric("Ort. Chiller Set", "Veri yok")
                
                st.divider()
                
                # ========== AHU KAPASİTE DURUMU ==========
                st.markdown("### 🏭 AHU Kapasite Durumu")
                st.caption("Klima santrallerinin ortalama vana açıklığına göre sistem kapasitesinin yeterliliği")
                
                ahu_cool_valve = summary.get("ahu_avg_cooling_valve")
                ahu_heat_valve = summary.get("ahu_avg_heating_valve")
                ahu_cool_cap = summary.get("ahu_cooling_capacity", "VERİ YOK")
                ahu_heat_cap = summary.get("ahu_heating_capacity", "VERİ YOK")
                
                cap_col1, cap_col2 = st.columns(2)
                
                with cap_col1:
                    st.markdown("#### ❄️ Soğutma Sistemi")
                    if ahu_cool_valve is not None:
                        # Renkli gösterge
                        if ahu_cool_cap == "YETERLI":
                            st.success(f"**Kapasite:** {ahu_cool_cap} 🟢")
                        elif ahu_cool_cap == "NORMAL":
                            st.info(f"**Kapasite:** {ahu_cool_cap} 🟡")
                        elif ahu_cool_cap == "DIKKAT":
                            st.warning(f"**Kapasite:** {ahu_cool_cap} 🟠")
                        elif ahu_cool_cap == "YETERSIZ":
                            st.error(f"**Kapasite:** {ahu_cool_cap} 🔴")
                        else:
                            st.info(f"**Kapasite:** {ahu_cool_cap}")
                        st.metric("Ort. Soğutma Vanası", f"%{ahu_cool_valve:.1f}")
                    else:
                        st.info("Soğutma verisi yok")
                
                with cap_col2:
                    st.markdown("#### 🔥 Isıtma Sistemi")
                    if ahu_heat_valve is not None:
                        # Renkli gösterge
                        if ahu_heat_cap == "YETERLI":
                            st.success(f"**Kapasite:** {ahu_heat_cap} 🟢")
                        elif ahu_heat_cap == "NORMAL":
                            st.info(f"**Kapasite:** {ahu_heat_cap} 🟡")
                        elif ahu_heat_cap == "DIKKAT":
                            st.warning(f"**Kapasite:** {ahu_heat_cap} 🟠")
                        elif ahu_heat_cap == "YETERSIZ":
                            st.error(f"**Kapasite:** {ahu_heat_cap} 🔴")
                        else:
                            st.info(f"**Kapasite:** {ahu_heat_cap}")
                        st.metric("Ort. Isıtma Vanası", f"%{ahu_heat_valve:.1f}")
                    else:
                        st.info("Isıtma verisi yok")
                
                # Açıklama
                with st.expander("📖 Kapasite Değerlendirme Kriterleri"):
                    st.markdown("""
                    | Ort. Vana | Durum | Açıklama |
                    |-----------|-------|----------|
                    | <%50 | 🟢 YETERLI | Kapasite rahat, rezerv var |
                    | %50-70 | 🟡 NORMAL | Kapasite yeterli |
                    | %70-85 | 🟠 DİKKAT | Kapasite sınırına yakın |
                    | >%85 | 🔴 YETERSİZ | Sistem zorlanıyor, kapasite artırımı düşünülmeli |
                    """)
                
                st.divider()
                
                # ========== MALİYET ÖZETİ ==========
                try:
                    import json as _tab5_json
                    _tab5_settings_path = os.path.join(os.path.dirname(__file__), "configs", "hvac_settings.json")
                    _tab5_prices = {}
                    if os.path.exists(_tab5_settings_path):
                        with open(_tab5_settings_path, "r", encoding="utf-8") as _tf:
                            _tab5_prices = _tab5_json.load(_tf)
                    
                    _p_elec = float(_tab5_prices.get("UNIT_PRICE_ELECTRICITY", 0))
                    _p_gas = float(_tab5_prices.get("UNIT_PRICE_GAS", 0))
                    _p_water = float(_tab5_prices.get("UNIT_PRICE_WATER", 0))
                    
                    if _p_elec > 0 or _p_gas > 0 or _p_water > 0:
                        st.markdown("### 💰 Aylık Maliyet Özeti")
                        
                        _total_grid = summary.get("total_grid_consumption", 0)
                        _total_gas = summary.get("total_gas", 0)
                        _total_water = summary.get("total_water_consumption", 0)
                        _days = unified_data.get("days_with_data", 1) or 1
                        
                        _cost_elec = _total_grid * _p_elec if _p_elec > 0 else 0
                        _cost_gas = _total_gas * _p_gas if _p_gas > 0 else 0
                        _cost_water = _total_water * _p_water if _p_water > 0 else 0
                        _cost_total = _cost_elec + _cost_gas + _cost_water
                        
                        # Metrik kartları
                        _cost_cols = st.columns(4)
                        with _cost_cols[0]:
                            if _p_elec > 0:
                                st.metric("⚡ Elektrik Maliyeti", f"{_cost_elec:,.0f} ₺", f"{_p_elec:.2f} TL/kWh")
                            else:
                                st.metric("⚡ Elektrik Maliyeti", "Fiyat yok")
                        with _cost_cols[1]:
                            if _p_gas > 0:
                                st.metric("🔥 Doğalgaz Maliyeti", f"{_cost_gas:,.0f} ₺", f"{_p_gas:.2f} TL/m³")
                            else:
                                st.metric("🔥 Doğalgaz Maliyeti", "Fiyat yok")
                        with _cost_cols[2]:
                            if _p_water > 0:
                                st.metric("💧 Su Maliyeti", f"{_cost_water:,.0f} ₺", f"{_p_water:.2f} TL/m³")
                            else:
                                st.metric("💧 Su Maliyeti", "Fiyat yok")
                        with _cost_cols[3]:
                            _daily_avg = _cost_total / _days if _days > 0 else 0
                            st.metric("📊 Toplam Maliyet", f"{_cost_total:,.0f} ₺", f"Ort. {_daily_avg:,.0f} ₺/gün")
                        
                        st.divider()
                except Exception:
                    pass
                # ═══ TAHMİN VE TREND ANALİZİ ═══
                try:
                    forecast_engine = ConsumptionForecastEngine()
                    forecast_data = forecast_engine.full_analysis(report_year)
                    
                    yearly = forecast_data.get("yearly_summary", [])
                    monthly_fc = forecast_data.get("monthly_forecast", [])
                    savings = forecast_data.get("savings", {})
                    next_m = forecast_data.get("next_month", {})
                    b_area = forecast_data.get("building_area", 0)
                    
                    # 1. Çok Yıllık Trend
                    if yearly and len(yearly) >= 2:
                        st.markdown("### 📈 Cok Yillik Trend Analizi")
                        
                        yc = st.columns(len(yearly))
                        for idx, ys in enumerate(yearly):
                            with yc[idx]:
                                st.metric(
                                    f"{ys['year']} ({ys['days']} gun)",
                                    f"{ys['total_kwh']:,.0f} kWh".replace(",", "."),
                                    f"{ys['kwh_per_m2']:.1f} kWh/m2" if b_area > 0 else None
                                )
                        
                        # Yıllar arası değişim
                        if len(yearly) >= 2:
                            trend_cols = st.columns(3)
                            last_y = yearly[-1]
                            prev_y = yearly[-2]
                            
                            with trend_cols[0]:
                                chg = (last_y['total_kwh'] - prev_y['total_kwh']) / prev_y['total_kwh'] * 100 if prev_y['total_kwh'] > 0 else 0
                                st.metric("Toplam Degisim", f"{chg:+.1f}%",
                                          f"{prev_y['year']}->{last_y['year']}")
                            with trend_cols[1]:
                                chg_g = (last_y['grid_kwh'] - prev_y['grid_kwh']) / prev_y['grid_kwh'] * 100 if prev_y['grid_kwh'] > 0 else 0
                                st.metric("Sebeke Degisim", f"{chg_g:+.1f}%",
                                          f"{prev_y['year']}->{last_y['year']}")
                            with trend_cols[2]:
                                chg_c = (last_y['chiller_kwh'] - prev_y['chiller_kwh']) / prev_y['chiller_kwh'] * 100 if prev_y['chiller_kwh'] > 0 else 0
                                st.metric("Chiller Degisim", f"{chg_c:+.1f}%",
                                          f"{prev_y['year']}->{last_y['year']}")
                        
                        st.divider()
                    
                    # 2. Aylık Tahmin Tablosu
                    if monthly_fc:
                        st.markdown(f"### 🔮 {report_year} Aylik Tuketim Tahmini")
                        st.caption("Onceki yillar arasi trende gore konservatif projeksiyon")
                        
                        _py5 = str(monthly_fc[0]['prev_year'])
                        _ly5 = str(monthly_fc[0]['last_year'])
                        _md5 = f"| Ay | {_py5} (kWh) | {_ly5} (kWh) | Trend | Tahmin (kWh) | Gerceklesen | Sapma |\n"
                        _md5 += "|:---|---:|---:|:---:|---:|---:|:---:|\n"
                        
                        for fc in monthly_fc:
                            _gc5 = "-"
                            _sp5 = "-"
                            if fc["actual_total"] is not None:
                                _gc5 = f"{fc['actual_total']:,.0f}".replace(",", ".")
                                if fc.get("is_partial"):
                                    _gc5 += f" ({fc['actual_days']}g)"
                                _sp5 = f"{fc['deviation_total_pct']:+.1f}%" if fc.get("deviation_total_pct") is not None else "-"
                            
                            _md5 += f"| {fc['month_name']} | {fc['prev_total']:,.0f} | {fc['last_total']:,.0f} | {fc['trend_total_pct']:+.1f}% | {fc['forecast_total']:,.0f} | {_gc5} | {_sp5} |\n".replace(",", ".")
                        
                        st.markdown(_md5)
                        
                        # Yıllık toplam tahmin
                        total_forecast = sum(fc["forecast_total"] for fc in monthly_fc)
                        total_actual = sum(fc["actual_total"] or 0 for fc in monthly_fc)
                        months_with_data = sum(1 for fc in monthly_fc if fc["actual_total"] is not None)
                        
                        fc_summary = st.columns(3)
                        with fc_summary[0]:
                            st.metric(f"{report_year} Yillik Tahmin",
                                      f"{total_forecast:,.0f} kWh".replace(",", "."))
                        with fc_summary[1]:
                            if months_with_data > 0:
                                st.metric(f"Gerceklesen ({months_with_data} ay)",
                                          f"{total_actual:,.0f} kWh".replace(",", "."))
                            else:
                                st.metric("Gerceklesen", "Veri yok")
                        with fc_summary[2]:
                            if b_area > 0:
                                st.metric("Tahmini kWh/m2",
                                          f"{total_forecast/b_area:.1f} kWh/m2")
                        
                        st.divider()
                    
                    # 3. Tasarruf Özeti
                    if savings and savings.get("savings_total_kwh") is not None:
                        st.markdown("### 💰 Beklenen vs Gerceklesen Tasarruf")
                        st.caption(f"Alan artisina ragmen tuketim degisimi ({savings.get('prev_year', '')}->{savings.get('year', '')})")
                        
                        sv_cols = st.columns(4)
                        with sv_cols[0]:
                            st.metric("Beklenen Tuketim",
                                      f"{savings['expected_total']:,.0f} kWh".replace(",", "."),
                                      f"(alan bazli)")
                        with sv_cols[1]:
                            st.metric("Gerceklesen",
                                      f"{savings['curr_total']:,.0f} kWh".replace(",", "."))
                        with sv_cols[2]:
                            color = "normal" if savings['savings_total_kwh'] >= 0 else "inverse"
                            st.metric("Toplam Tasarruf",
                                      f"{savings['savings_total_kwh']:,.0f} kWh".replace(",", "."),
                                      f"%{savings['savings_total_pct']:.1f}")
                        with sv_cols[3]:
                            st.metric("Sebeke Tasarruf",
                                      f"{savings['savings_grid_kwh']:,.0f} kWh".replace(",", "."),
                                      f"%{savings['savings_grid_pct']:.1f}")
                        
                        st.divider()
                    
                    # 4. Gelecek Ay Tahmini
                    if next_m:
                        st.markdown(f"### 🎯 Gelecek Ay Tahmini: {next_m.get('month_name', '')} {next_m.get('year', '')}")
                        nm_cols = st.columns(3)
                        with nm_cols[0]:
                            st.metric("Beklenen Toplam",
                                      f"{next_m.get('forecast_total', 0):,.0f} kWh".replace(",", "."),
                                      f"Trend: {next_m.get('trend_total_pct', 0):+.1f}%")
                        with nm_cols[1]:
                            st.metric("Beklenen Sebeke",
                                      f"{next_m.get('forecast_grid', 0):,.0f} kWh".replace(",", "."),
                                      f"Trend: {next_m.get('trend_grid_pct', 0):+.1f}%")
                        with nm_cols[2]:
                            if b_area > 0:
                                st.metric("Beklenen kWh/m2",
                                          f"{next_m.get('per_m2', 0):.1f} kWh/m2")
                        
                        st.divider()
                
                except Exception as _fc_err:
                    st.warning(f"Tahmin modülü hatası: {_fc_err}")
                
                # Tasarruf önerileri
                st.markdown(f"### ⚠️ Tasarruf Önerileri ({rec_summary['total_count']} öneri)")
                
                if recommendations:
                    for rec in recommendations:
                        severity = rec.get("severity", "INFO")
                        if severity == "CRITICAL":
                            st.error(f"🚨 **{rec['name']}** (Potansiyel: {rec['savings_potential']})\n\n{rec['message']}")
                        elif severity == "WARNING":
                            st.warning(f"⚠️ **{rec['name']}** (Potansiyel: {rec['savings_potential']})\n\n{rec['message']}")
                        else:
                            st.info(f"ℹ️ **{rec['name']}** (Potansiyel: {rec['savings_potential']})\n\n{rec['message']}")
                else:
                    st.success("✅ Bu dönem için tasarruf önerisi bulunmamaktadır. Sistem verimli çalışıyor!")
                
                st.divider()
                
                # PDF indirme
                st.markdown("### 📥 PDF Rapor İndir")
                try:
                    # PDF Grafiklerini Hazırla
                    pdf_charts = {}
                    
                    # 1. Enerji Dağılımı (Pasta Grafik)
                    try:
                        summ = unified_data.get("summary", {})
                        labels = ["Şebeke", "Doğalgaz", "Soğutma", "Diğer"]
                        values = [
                            summ.get("total_grid_consumption", 0),
                            summ.get("total_gas", 0) * 10.64,  # m3 -> kWh (yaklaşık)
                            summ.get("total_cooling_consumption", 0),
                            summ.get("total_hospital_consumption", 0) - summ.get("total_grid_consumption", 0) # Basit hesap
                        ]
                        # Negatif değerleri temizle
                        values = [max(0, v) for v in values]
                        
                        if sum(values) > 0:
                            fig_pie = px.pie(names=labels, values=values, hole=0.4,
                                           color_discrete_sequence=['#3b82f6', '#f59e0b', '#10b981', '#94a3b8'])
                            fig_pie.update_layout(
                                title="Enerji Tüketim Dağılımı",
                                template="plotly_white",
                                font=dict(family="Arial", size=12),
                                showlegend=True
                            )
                            pdf_charts["Enerji Dağılımı"] = fig_to_png_bytes(fig_pie)
                    except Exception as e:
                        print(f"Chart error (Pie): {e}")

                    # 2. Günlük Tüketim Trendi (Çizgi Grafik)
                    try:
                        daily_df = pd.DataFrame([
                            {
                                "Gün": d["date"], 
                                "Tüketim": d["energy"].get("total_hospital", 0),
                                "Sıcaklık": d["energy"].get("outdoor_temp")
                            } 
                            for d in unified_data.get("daily_data", [])
                        ])
                        
                        if not daily_df.empty:
                            fig_trend = go.Figure()
                            # Tüketim (Bar)
                            fig_trend.add_trace(go.Bar(
                                x=daily_df["Gün"], y=daily_df["Tüketim"],
                                name="Tüketim (kWh)",
                                marker_color='rgba(59, 130, 246, 0.7)'
                            ))
                            # Sıcaklık (Çizgi - 2. Eksen)
                            fig_trend.add_trace(go.Scatter(
                                x=daily_df["Gün"], y=daily_df["Sıcaklık"],
                                name="Dış Hava (°C)",
                                yaxis="y2",
                                line=dict(color='#ef4444', width=3)
                            ))
                            
                            fig_trend.update_layout(
                                title="Günlük Tüketim & Sıcaklık",
                                template="plotly_white",
                                font=dict(family="Arial", size=12),
                                yaxis=dict(title="Tüketim (kWh)"),
                                yaxis2=dict(title="Sıcaklık (°C)", overlaying="y", side="right"),
                                legend=dict(orientation="h", y=1.1)
                            )
                            pdf_charts["Günlük Trend"] = fig_to_png_bytes(fig_trend)
                    except Exception as e:
                        print(f"Chart error (Trend): {e}")

                    # 3. YoY Karşılaştırma (Bar Grafik)
                    try:
                        comps = yoy_analysis.get("comparisons", {})
                        # Ana metrikler
                        metrics = ["total_grid_consumption", "total_cooling_consumption", "total_gas"]
                        display_names = ["Şebeke", "Soğutma", "Doğalgaz"]
                        
                        curr_vals = [comps.get(m, {}).get("current", 0) for m in metrics]
                        prev_vals = [comps.get(m, {}).get("previous", 0) for m in metrics]
                        
                        fig_yoy = go.Figure()
                        fig_yoy.add_trace(go.Bar(
                            name="Bu Yıl", x=display_names, y=curr_vals,
                            marker_color='#10b981'
                        ))
                        fig_yoy.add_trace(go.Bar(
                            name="Geçen Yıl", x=display_names, y=prev_vals,
                            marker_color='#6366f1'
                        ))
                        
                        fig_yoy.update_layout(
                            title="Bu Ay vs Geçen Yıl (YoY)",
                            template="plotly_white",
                            font=dict(family="Arial", size=12),
                            barmode='group',
                            legend=dict(orientation="h", y=1.1)
                        )
                        pdf_charts["Yıllık Karşılaştırma"] = fig_to_png_bytes(fig_yoy)
                    except Exception as e:
                        print(f"Chart error (YoY): {e}")

                    # PDF Oluştur (tahmin verisiyle)
                    pdf_gen = MonthlyReportPDFGenerator()
                    try:
                        _fc_engine = ConsumptionForecastEngine()
                        _fc_data = _fc_engine.full_analysis(report_year)
                    except Exception:
                        _fc_data = None
                    pdf_bytes = pdf_gen.generate(report_year, report_month, unified_data, yoy_analysis, recommendations, charts=pdf_charts, forecast_data=_fc_data)
                    
                    ay_adi = ["Ocak","Şubat","Mart","Nisan","Mayıs","Haziran",
                              "Temmuz","Ağustos","Eylül","Ekim","Kasım","Aralık"][report_month-1]
                    
                    st.download_button(
                        f"📥 {ay_adi} {report_year} Raporunu İndir (PDF)",
                        data=pdf_bytes,
                        file_name=f"aylik_tasarruf_raporu_{report_year}_{report_month:02d}.pdf",
                        mime="application/pdf",
                        key="monthly_pdf_download"
                    )
                except Exception as pdf_err:
                    st.error(f"PDF oluşturma hatası: {pdf_err}")
                
    except ImportError as e:
        st.error(f"Monthly report modülü yüklenemedi: {e}")
        st.info("Lütfen 'monthly_report' klasörünün mevcut olduğundan emin olun.")
    
    # ========== AI İLERLEME + ML EGİTİM VERİSİ ==========
    st.divider()
    st.markdown("### 🧠 Yapay Zeka / Makine Öğrenmesi İlerleme")
    
    # AI İlerleme Göstergesi
    try:
        from ai_progress import calculate_ai_progress
        _ai = calculate_ai_progress()
        _ai_score = _ai["total_score"]
        _ai_level = _ai["level"]
        _ai_emoji = _ai["level_emoji"]
        _cats = _ai["categories"]
        
        with st.container(border=True):
            _ai_col1, _ai_col2 = st.columns([1, 2])
            
            with _ai_col1:
                if _ai_score >= 80:
                    _ring_color = "#10b981"
                elif _ai_score >= 60:
                    _ring_color = "#3b82f6"
                elif _ai_score >= 40:
                    _ring_color = "#f59e0b"
                elif _ai_score >= 20:
                    _ring_color = "#8b5cf6"
                else:
                    _ring_color = "#6b7280"
                
                st.markdown(f"""
                <div style="text-align:center;">
                    <div style="position:relative; width:130px; height:130px; margin:0 auto;">
                        <svg viewBox="0 0 120 120" style="transform:rotate(-90deg)">
                            <circle cx="60" cy="60" r="50" fill="none" stroke="#e5e7eb" stroke-width="10"/>
                            <circle cx="60" cy="60" r="50" fill="none" stroke="{_ring_color}" stroke-width="10"
                                stroke-dasharray="{_ai_score * 3.14} {(100 - _ai_score) * 3.14}"
                                stroke-linecap="round"/>
                        </svg>
                        <div style="position:absolute; top:50%; left:50%; transform:translate(-50%,-50%);
                                    font-size:32px; font-weight:bold; color:{_ring_color};">
                            %{_ai_score}
                        </div>
                    </div>
                    <div style="margin-top:8px; font-size:20px; font-weight:bold;">{_ai_emoji} {_ai_level}</div>
                    <div style="font-size:12px; color:#6b7280; margin-top:4px;">Seviye: Başlangıç → Gelişen → Olgun → İleri → Otonom</div>
                </div>
                """, unsafe_allow_html=True)
            
            with _ai_col2:
                for _cat_key, _cat in _cats.items():
                    _pct = int((_cat["score"] / _cat["max"]) * 100) if _cat["max"] > 0 else 0
                    _cat_names = {
                        "data_maturity": "Veri Olgunluğu",
                        "feedback": "Geri Bildirim / Öğrenme",
                        "feature_maturity": "Özellik Olgunluğu",
                        "advanced_ai": "İleri AI Yetenekleri"
                    }
                    _cat_name = _cat_names.get(_cat_key, _cat_key)
                    
                    st.markdown(f"""
                    <div style="margin-bottom:10px;">
                        <div style="display:flex; justify-content:space-between; font-size:14px; margin-bottom:3px;">
                            <span>{_cat["icon"]} {_cat_name}</span>
                            <span><b>{_cat["score"]}</b>/{_cat["max"]}</span>
                        </div>
                        <div style="background:#e5e7eb; border-radius:6px; height:12px; overflow:hidden;">
                            <div style="background:{_ring_color}; width:{_pct}%; height:100%; border-radius:6px;
                                        transition: width 0.5s ease;"></div>
                        </div>
                        <div style="font-size:11px; color:#6b7280; margin-top:2px;">{_cat["detail"]}</div>
                    </div>
                    """, unsafe_allow_html=True)
                
                st.caption(f"🎯 Sonraki hedef: {_ai['next_milestone']}")
    except Exception:
        st.info("AI ilerleme modülü yüklenemedi.")
    
    st.divider()
    st.markdown("### 🤖 ML Eğitim Verisi Durumu")
    
    try:
        from monthly_report import TrainingDataCollector
        collector = TrainingDataCollector()
        stats = collector.get_statistics()
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            st.metric("Toplam Kayıt", stats.get("total_records", 0))
        with col2:
            st.metric("Feedback Alınan", stats.get("with_feedback", 0))
        with col3:
            feedback_rate = stats.get("feedback_rate", 0)
            st.metric("Feedback Oranı", f"%{feedback_rate:.1f}")
        with col4:
            ready = "✅ HAZIR" if stats.get("ready_for_ml") else "⏳ Veri Toplaniyor"
            st.metric("ML Durumu", ready)
        
        # Kural dağılımı
        rule_dist = stats.get("rule_distribution", {})
        if rule_dist:
            with st.expander("📊 Kural Dağılımı"):
                for rule_id, count in sorted(rule_dist.items(), key=lambda x: -x[1]):
                    st.text(f"  {rule_id}: {count} adet")
        
        # Bekleyen feedback'ler
        pending = collector.get_pending_feedback()
        if pending:
            with st.expander(f"⏳ Feedback Bekleyen Öneriler ({len(pending)} adet)", expanded=True):
                # Session state için seçim listesi
                if "selected_feedbacks" not in st.session_state:
                    st.session_state.selected_feedbacks = set()
                
                # TOPLU İŞLEM BUTONLARI
                col_select_all, col_clear, col_apply_sel, col_reject_sel, col_pending_sel = st.columns(5)
                with col_select_all:
                    if st.button("☑️ Tümünü Seç", key="fb_select_all"):
                        st.session_state.selected_feedbacks = {rec['id'] for rec in pending}
                        st.rerun()
                with col_clear:
                    if st.button("⬜ Temizle", key="fb_clear_all"):
                        st.session_state.selected_feedbacks = set()
                        st.rerun()
                with col_apply_sel:
                    if st.button("✅ Seçilenleri Uygula", key="fb_apply_selected"):
                        for rec_id in st.session_state.selected_feedbacks:
                            collector.update_feedback(rec_id, "applied")
                        st.success(f"{len(st.session_state.selected_feedbacks)} öneri uygulandı olarak işaretlendi!")
                        st.session_state.selected_feedbacks = set()
                        st.rerun()
                with col_reject_sel:
                    if st.button("❌ Seçilenleri Reddet", key="fb_reject_selected"):
                        for rec_id in st.session_state.selected_feedbacks:
                            collector.update_feedback(rec_id, "not_applied")
                        st.warning(f"{len(st.session_state.selected_feedbacks)} öneri reddedildi olarak işaretlendi!")
                        st.session_state.selected_feedbacks = set()
                        st.rerun()
                with col_pending_sel:
                    if st.button("⏸️ Seçilenleri Beklet", key="fb_pending_selected"):
                        for rec_id in st.session_state.selected_feedbacks:
                            collector.update_feedback(rec_id, "pending")
                        st.info(f"{len(st.session_state.selected_feedbacks)} öneri beklemede olarak işaretlendi!")
                        st.session_state.selected_feedbacks = set()
                        st.rerun()
                
                st.divider()
                st.caption(f"📌 Seçili: {len(st.session_state.selected_feedbacks)} adet")
                
                # ÖNERİ LİSTESİ - Checkbox ile
                for rec in pending:
                    rec_data = rec.get("recommendation", {})
                    rec_id = rec['id']
                    
                    col_check, col_info, col_a, col_b, col_c = st.columns([0.5, 3, 1, 1, 1])
                    
                    with col_check:
                        is_selected = rec_id in st.session_state.selected_feedbacks
                        if st.checkbox("", value=is_selected, key=f"fb_check_{rec_id}", label_visibility="collapsed"):
                            st.session_state.selected_feedbacks.add(rec_id)
                        else:
                            st.session_state.selected_feedbacks.discard(rec_id)
                    
                    with col_info:
                        st.markdown(f"**{rec_id}** - {rec_data.get('name', 'N/A')}")
                    
                    with col_a:
                        if st.button("✅", key=f"fb_applied_{rec_id}", help="Uygulandı"):
                            collector.update_feedback(rec_id, "applied")
                            st.success("Kaydedildi!")
                            st.rerun()
                    with col_b:
                        if st.button("❌", key=f"fb_not_{rec_id}", help="Uygulanmadı"):
                            collector.update_feedback(rec_id, "not_applied")
                            st.warning("Kaydedildi!")
                            st.rerun()
                    with col_c:
                        if st.button("⏸️", key=f"fb_pending_{rec_id}", help="Beklemede"):
                            collector.update_feedback(rec_id, "pending")
                            st.info("Kaydedildi!")
                            st.rerun()
                
                if len(pending) > 20:
                    st.info(f"... toplam {len(pending)} öneri bekliyor")
    
    except ImportError:
        st.info("ML eğitim modülü henüz aktif değil.")

# ---------------- TAB 6: TAHMİN & TREND ----------------
with tab6:
    st.subheader("🔮 Tüketim Tahmini ve Trend Analizi")
    st.caption("Geçmiş verilerden geleceğe yönelik projeksiyon ve tasarruf analizi")
    
    try:
        from monthly_report.forecast_engine import ConsumptionForecastEngine as _FCEngine
        from monthly_report.forecast_engine import AYLAR
        
        _fc_col1, _fc_col2 = st.columns([1, 3])
        with _fc_col1:
            _fc_year = st.selectbox("Tahmin Yılı", options=list(range(2024, 2028)), index=2, key="forecast_year_select")
        
        _fc_eng = _FCEngine()
        _fc_result = _fc_eng.full_analysis(_fc_year)
        
        _fc_yearly = _fc_result.get("yearly_summary", [])
        _fc_monthly = _fc_result.get("monthly_forecast", [])
        _fc_savings = _fc_result.get("savings", {})
        _fc_next = _fc_result.get("next_month", {})
        _fc_area = _fc_result.get("building_area", 0)
        
        # ═══ 1. ÇOK YILLIK TREND ═══
        if _fc_yearly and len(_fc_yearly) >= 2:
            st.markdown("### 📈 Çok Yıllık Trend Analizi")
            
            _yc = st.columns(len(_fc_yearly))
            for _yi, _ys in enumerate(_fc_yearly):
                with _yc[_yi]:
                    st.metric(
                        f"{_ys['year']} ({_ys['days']} gün)",
                        f"{_ys['total_kwh']:,.0f} kWh".replace(",", "."),
                        f"{_ys['kwh_per_m2']:.1f} kWh/m²" if _fc_area > 0 else None
                    )
            
            _tc = st.columns(3)
            _ly = _fc_yearly[-1]
            _py = _fc_yearly[-2]
            with _tc[0]:
                _ct = (_ly['total_kwh'] - _py['total_kwh']) / _py['total_kwh'] * 100 if _py['total_kwh'] > 0 else 0
                st.metric("Toplam Değişim", f"{_ct:+.1f}%", f"{_py['year']}→{_ly['year']}")
            with _tc[1]:
                _cg = (_ly['grid_kwh'] - _py['grid_kwh']) / _py['grid_kwh'] * 100 if _py['grid_kwh'] > 0 else 0
                st.metric("Şebeke Değişim", f"{_cg:+.1f}%", f"{_py['year']}→{_ly['year']}")
            with _tc[2]:
                _cc = (_ly['chiller_kwh'] - _py['chiller_kwh']) / _py['chiller_kwh'] * 100 if _py['chiller_kwh'] > 0 else 0
                st.metric("Chiller Değişim", f"{_cc:+.1f}%", f"{_py['year']}→{_ly['year']}")
            
            st.divider()
        
        # ═══ 2. AYLIK TAHMİN TABLOSU ═══
        if _fc_monthly:
            st.markdown(f"### 🔮 {_fc_year} Aylık Tüketim Tahmini")
            st.caption("Önceki yıllar arası trende göre konservatif projeksiyon")
            
            _prev_y = str(_fc_monthly[0]['prev_year'])
            _last_y = str(_fc_monthly[0]['last_year'])
            
            # Markdown tablo başlığı
            _md = f"| Ay | {_prev_y} (kWh) | {_last_y} (kWh) | Trend | Tahmin (kWh) | Gerçekleşen | Sapma |\n"
            _md += "|:---|---:|---:|:---:|---:|---:|:---:|\n"
            
            for _fm in _fc_monthly:
                _ay = _fm["month_name"]
                _p = f"{_fm['prev_total']:,.0f}".replace(",", ".")
                _l = f"{_fm['last_total']:,.0f}".replace(",", ".")
                _tr = f"{_fm['trend_total_pct']:+.1f}%"
                _th = f"{_fm['forecast_total']:,.0f}".replace(",", ".")
                
                if _fm["actual_total"] is not None:
                    _gc = f"{_fm['actual_total']:,.0f}".replace(",", ".")
                    if _fm.get("is_partial"):
                        _gc += f" ({_fm['actual_days']}g)"
                    _sp = f"{_fm['deviation_total_pct']:+.1f}%" if _fm.get("deviation_total_pct") is not None else "-"
                else:
                    _gc = "-"
                    _sp = "-"
                
                _md += f"| {_ay} | {_p} | {_l} | {_tr} | {_th} | {_gc} | {_sp} |\n"
            
            st.markdown(_md)
            
            _tf = sum(f["forecast_total"] for f in _fc_monthly)
            _ta = sum(f["actual_total"] or 0 for f in _fc_monthly)
            _mwd = sum(1 for f in _fc_monthly if f["actual_total"] is not None)
            
            _fs = st.columns(3)
            with _fs[0]:
                st.metric(f"{_fc_year} Yıllık Tahmin", f"{_tf:,.0f} kWh".replace(",", "."))
            with _fs[1]:
                if _mwd > 0:
                    st.metric(f"Gerçekleşen ({_mwd} ay)", f"{_ta:,.0f} kWh".replace(",", "."))
                else:
                    st.metric("Gerçekleşen", "Henüz veri yok")
            with _fs[2]:
                if _fc_area > 0:
                    st.metric("Tahmini kWh/m²", f"{_tf/_fc_area:.1f} kWh/m²")
            
            st.divider()
        
        # ═══ 3. TASARRUF ÖZETİ ═══
        if _fc_savings and _fc_savings.get("savings_total_kwh") is not None:
            st.markdown("### 💰 Beklenen vs Gerçekleşen Tasarruf")
            st.caption(f"Alan artışına rağmen tüketim değişimi ({_fc_savings.get('prev_year', '')}→{_fc_savings.get('year', '')})")
            
            _sv = st.columns(4)
            with _sv[0]:
                st.metric("Beklenen Tüketim", f"{_fc_savings['expected_total']:,.0f} kWh".replace(",", "."), "(alan bazlı)")
            with _sv[1]:
                st.metric("Gerçekleşen", f"{_fc_savings['curr_total']:,.0f} kWh".replace(",", "."))
            with _sv[2]:
                st.metric("Toplam Tasarruf", f"{_fc_savings['savings_total_kwh']:,.0f} kWh".replace(",", "."),
                          f"%{_fc_savings['savings_total_pct']:.1f}")
            with _sv[3]:
                st.metric("Şebeke Tasarruf", f"{_fc_savings['savings_grid_kwh']:,.0f} kWh".replace(",", "."),
                          f"%{_fc_savings['savings_grid_pct']:.1f}")
            
            st.divider()
        
        # ═══ 4. GELECEK AY TAHMİNİ ═══
        if _fc_next:
            st.markdown(f"### 🎯 Gelecek Ay Tahmini: {_fc_next.get('month_name', '')} {_fc_next.get('year', '')}")
            _method = _fc_next.get("method", "trend")
            _method_label = "🤖 ML Model" if _method == "ml" else "📊 Trend"
            st.caption(f"Tahmin yöntemi: {_method_label}")
            _nm = st.columns(3)
            with _nm[0]:
                st.metric("Beklenen Toplam", f"{_fc_next.get('forecast_total', 0):,.0f} kWh".replace(",", "."),
                          f"Trend: {_fc_next.get('trend_total_pct', 0):+.1f}%")
            with _nm[1]:
                st.metric("Beklenen Şebeke", f"{_fc_next.get('forecast_grid', 0):,.0f} kWh".replace(",", "."),
                          f"Trend: {_fc_next.get('trend_grid_pct', 0):+.1f}%")
            with _nm[2]:
                if _fc_area > 0:
                    st.metric("Beklenen kWh/m²", f"{_fc_next.get('per_m2', 0):.1f} kWh/m²")
            
            # Ortalama koşullar (ML tahmini ise)
            if "avg_conditions" in _fc_next:
                _ac = _fc_next["avg_conditions"]
                st.caption(f"Baz koşullar: Dış hava {_ac.get('dis_hava', '-')}°C | Chiller set {_ac.get('chiller_set', '-')}°C | Chiller {_ac.get('chiller_adet', '-')} adet | Kazan {_ac.get('kazan_adet', '-')} adet")
        
        st.divider()
        
        # ═══ 5. ML MODEL BİLGİLERİ ═══
        _model_info = _fc_result.get("model_info", {})
        st.markdown("### 🤖 ML Model Durumu")
        
        if _model_info.get("is_trained"):
            _mi = st.columns(4)
            with _mi[0]:
                _r2t = _model_info.get("r2_total", 0)
                _quality = "Mükemmel" if _r2t > 0.9 else "İyi" if _r2t > 0.7 else "Orta" if _r2t > 0.5 else "Gelişiyor"
                st.metric("Toplam R² Skoru", f"{_r2t:.3f}", _quality)
            with _mi[1]:
                _r2g = _model_info.get("r2_grid", 0)
                st.metric("Şebeke R² Skoru", f"{_r2g:.3f}")
            with _mi[2]:
                st.metric("Eğitim Verisi", f"{_model_info.get('train_samples', 0)} gün")
            with _mi[3]:
                st.metric("Tahmin Yöntemi", "🤖 ML Aktif")
            
            # Feature importance
            _fi = _model_info.get("feature_importance", {})
            if _fi:
                st.markdown("**📊 Parametre Etki Sıralaması:**")
                _fi_labels = {
                    "dis_hava": "Dis Hava Sicakligi", "chiller_adet": "Chiller Adet",
                    "chiller_set": "Chiller Set Temp", "kazan_adet": "Kazan Adet",
                    "ay": "Ay", "ay_sin": "Mevsim (sin)", "ay_cos": "Mevsim (cos)",
                    "gun_sayisi": "Gun Sayisi", "absorption_adet": "Absorption Chiller",
                    "kojen_uretim": "Kojen Uretim", "kazan_dogalgaz": "Kazan Dogalgaz",
                }
                _fi_sorted = sorted(_fi.items(), key=lambda x: x[1], reverse=True)
                _fi_md = "| Parametre | Etki Oranı |\n|:---|---:|\n"
                for _fname, _fval in _fi_sorted:
                    _label = _fi_labels.get(_fname, _fname)
                    _bar = "█" * int(_fval * 50)
                    _fi_md += f"| {_label} | {_bar} {_fval*100:.1f}% |\n"
                st.markdown(_fi_md)
            
            # Yeniden eğit butonu
            if st.button("🔄 Modeli Yeniden Eğit", key="retrain_ml"):
                _rt = _fc_eng.train_model()
                if _rt.get("success"):
                    st.success(f"Model yeniden eğitildi! R²: {_rt.get('r2_total', 0):.3f} | {_rt.get('samples', 0)} veri")
                    st.rerun()
                else:
                    st.error(f"Eğitim hatası: {_rt.get('reason', 'Bilinmeyen')}")
        else:
            st.info("ML model henüz eğitilmedi. İlk eğitim için butona tıklayın.")
            if st.button("🚀 Modeli Eğit", key="first_train_ml"):
                _rt = _fc_eng.train_model()
                if _rt.get("success"):
                    st.success(f"Model eğitildi! R²: {_rt.get('r2_total', 0):.3f} | {_rt.get('samples', 0)} veri")
                    st.rerun()
                else:
                    st.error(f"Eğitim hatası: {_rt.get('reason', 'Bilinmeyen')}")
        
        st.divider()
        
        # ═══ 6. SENARYO TAHMİNİ ═══
        st.markdown("### 🎛️ Senaryo Tahmini")
        st.caption("Parametreleri değiştirerek farklı koşullarda tüketimi tahmin edin")
        
        _sc1, _sc2, _sc3 = st.columns(3)
        with _sc1:
            _s_hava = st.slider("🌡️ Dış Hava (°C)", -10.0, 45.0, 20.0, 0.5, key="sc_hava")
            _s_ay = st.selectbox("📅 Ay", list(range(1, 13)),
                                 format_func=lambda x: AYLAR.get(x, str(x)),
                                 index=2, key="sc_ay")
        with _sc2:
            _s_chiller = st.number_input("❄️ Chiller Adet", 0, 6, 2, key="sc_chiller")
            _s_set = st.slider("🎯 Chiller Set (°C)", 5.0, 12.0, 7.0, 0.5, key="sc_set")
        with _sc3:
            _s_kazan = st.number_input("🔥 Kazan Adet", 0, 4, 1, key="sc_kazan")
            _s_kar = st.checkbox("🌨️ Kar Eritme", key="sc_kar")
        
        if st.button("🔮 Tahmin Et", key="sc_predict"):
            _sc_result = _fc_eng.scenario_predict(
                dis_hava=_s_hava, chiller_set=_s_set,
                chiller_adet=_s_chiller, kazan_adet=_s_kazan,
                ay=_s_ay, kar_eritme=_s_kar,
            )
            if "error" in _sc_result:
                st.warning(_sc_result["error"])
            else:
                _sr = st.columns(3)
                with _sr[0]:
                    st.metric("Günlük Toplam", f"{_sc_result['gunluk_toplam']:,.0f} kWh".replace(",", "."))
                with _sr[1]:
                    st.metric("Günlük Şebeke", f"{_sc_result['gunluk_sebeke']:,.0f} kWh".replace(",", "."))
                with _sr[2]:
                    st.metric(f"Aylık Toplam ({_sc_result['gun_sayisi']} gün)",
                              f"{_sc_result['aylik_toplam']:,.0f} kWh".replace(",", "."))
    
    except Exception as _fc_err:
        st.warning(f"Tahmin modülü hatası: {_fc_err}")