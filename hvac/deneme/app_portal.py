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
from contextlib import contextmanager
from pathlib import Path
from datetime import date

import streamlit as st
import streamlit.components.v1 as components
import pandas as pd
import enerji_hesap as _enerji_hesap
import plotly.express as px

from fpdf import FPDF

st.set_page_config(page_title="Enerji Yönetimi & Raporlama", layout="wide")

# ── LİSANS KONTROLÜ ──────────────────────────────────
try:
    from lisans import lisans_kontrol
    _lis = lisans_kontrol()
    if not _lis["gecerli"]:
        st.markdown("""
        <div style='display:flex;align-items:center;justify-content:center;height:80vh;'>
        <div style='text-align:center;background:rgba(208,59,59,0.1);border:1px solid rgba(208,59,59,0.4);
                    border-radius:16px;padding:48px 64px;'>
            <div style='font-size:48px;margin-bottom:16px;'>🔒</div>
            <div style='font-size:22px;font-weight:700;color:#d03b3b;margin-bottom:12px;'>
                Lisanssiz Erisim
            </div>
            <div style='font-size:14px;color:#24324d;margin-bottom:24px;'>
                Bu cihaz icin gecerli bir lisans bulunamadi.
            </div>
            <div style='font-size:12px;color:#46536b;'>
                Yetkili: Acibadem Genel Merkez Enerji Yonetimi
            </div>
        </div></div>
        """, unsafe_allow_html=True)
        st.caption(f"Makine ID: `{_lis['makine_id']}`")
        st.stop()
except ImportError:
    pass  # lisans.py yoksa eski davranis (geriye donuk uyumluluk)

# Bulut senkronizasyonu (Supabase) — arka planda otomatik başlat
#
# Watchdog altında (HVAC_WATCHDOG=1) BAŞLATILMAZ: watchdog zaten ayrı bir
# cloud_sync.py süreci çalıştırıyor. Önceden burada da başlatılıyordu ve
# Streamlit bu dosyayı her sayfa açılışında baştan çalıştırdığı için döngüler
# çoğalıyor, oto-set aynı geçişi 2-3 kez uyguluyordu. Watchdog olmadan
# (portalı tek başına çalıştırma: streamlit run app_portal.py) eski davranış sürer; tek kopyayı cloud_sync'teki kilit korur.
if os.environ.get("HVAC_WATCHDOG") != "1":
    try:
        from cloud_sync import start_background_sync
        start_background_sync()
    except Exception:
        pass  # supabase_config.json yoksa veya ayarlanmamışsa sessizce atla


@st.cache_resource(ttl=300)
def _get_forecast_engine():
    """ConsumptionForecastEngine'i (ML modeli dahil) tek seferde yükler ve
    rerun'lar arasında bellekte tutar — her widget etkileşiminde diskten
    pickle yeniden okunmasını engeller."""
    from monthly_report.forecast_engine import ConsumptionForecastEngine
    return ConsumptionForecastEngine()


def _veri_imzasi() -> float:
    """energy_data.csv değişince günlük model önbelleği tazelensin."""
    try:
        return os.path.getmtime(DATA_FILE)
    except OSError:
        return 0.0


@st.cache_data(show_spinner=False, ttl=3600)
def _gunluk_model_ozeti(yil: int, hedef: str, veri_imzasi: float) -> dict:
    """Günlük modelin yıl özeti (tuketim_tahmin/portal_ozet). Geçmiş her ay
    ileriye dönük eğitildiği için ~1-2 sn sürer; veri değişmedikçe önbellekten."""
    from tuketim_tahmin import portal_ozet
    return portal_ozet.yil_ozeti(load_data(), yil, hedef)


def _durust_tahmin_verisi(yil: int) -> dict:
    """Aylık rapor ve PDF için tahmin verisi: eski motorun yapısı korunur, ama
    aylık "Tahmin" ve "Sapma" günlük modelin İLERİYE DÖNÜK sonucuyla değiştirilir.

    NEDEN (H-04, 26.10.2026 denetimi): eski motorun sapması, modelin eğitimde
    GÖRDÜĞÜ aylarla hesaplanıyordu — gerçek başarı değildi, PDF'te de öyle
    basılıyordu. Günlük model her geçmiş ayı yalnız o aydan önceki veriyle
    tahmin eder. Yeni model çalışmazsa eski veri olduğu gibi döner.
    """
    veri = _get_forecast_engine().full_analysis(yil)
    try:
        from tuketim_tahmin import portal_ozet
        oz = portal_ozet.yil_ozeti(load_data(), int(yil), "toplam")
        if oz.get("hata"):
            return veri
        aylar = {a["ay"]: a for a in oz["aylar"]}
        for fc in veri.get("monthly_forecast") or []:
            a = aylar.get(fc.get("month"))
            if not a or a.get("tahmin") is None:
                continue
            fc["forecast_total"] = a["tahmin"]
            fc["deviation_total_pct"] = a["sapma"]
        veri["yontem_notu"] = ("Tahmin ve sapma: günlük model, her ay yalnız o aydan önceki "
                               "veriyle (ileriye dönük). Sapma = (gerçek − tahmin) / tahmin.")
    except Exception:
        pass
    return veri


@st.cache_data(show_spinner=False, ttl=3600)
def _gunluk_model_gelecek_ay(yil: int, ay: int, kojen_gun, veri_imzasi: float) -> dict:
    from tuketim_tahmin import portal_ozet
    return portal_ozet.gelecek_ay(load_data(), yil, ay, kojen_calisma_gun=kojen_gun)

# Custom Dark Theme CSS
st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

    /* Mat plastik beyaz — duz govde, parlama yok */
    .stApp {
        background-color: #ecebe8;
        background-image: none;
        font-family: Inter, system-ui, -apple-system, 'Segoe UI', sans-serif;
    }

    /* Tam genişlik - kenar boşluklarını azalt */
    .block-container {
        max-width: 100% !important;
        padding-left: 2rem !important;
        padding-right: 2rem !important;
    }

    /* Glassmorphism for containers */
    .stTabs [data-baseweb="tab-panel"] {
        background: #fafaf8;
        border-radius: 8px;
        padding: 24px;
        border: 1px solid rgba(24,26,30,0.10);
    }

    /* Metrics styling */
    [data-testid="stMetricValue"] {
        color: #0f1f3d !important;
        font-size: 28px !important;
        font-weight: 300 !important;
    }

    [data-testid="stMetricLabel"] {
        color: #46536b !important;
        font-weight: 600 !important;
        text-transform: uppercase !important;
        letter-spacing: 1px !important;
        font-size: 10px !important;
    }

    /* DELTA RENGİNE DOKUNULMAZ.
       Burada "color: #0f1f3d !important" vardı; Streamlit'in artış/azalış
       rengini eziyor, bütün oklar lacivert çıkıyordu — yani tüketim arttı mı
       azaldı mı renkten anlaşılmıyordu. Renk artık Streamlit'ten gelir:
       tüketim kalemlerinde delta_color="inverse" (artış KIRMIZI, azalış
       YEŞİL), etiket niteliğindeki deltalarda "off" (nötr gri). */

    /* Headers */
    h1, h2, h3 {
        color: #0f1f3d !important;
        font-family: Inter, system-ui, -apple-system, 'Segoe UI', sans-serif !important;
        font-weight: 400 !important;
    }
    h4, h5, h6 {
        color: #0f1f3d !important;
        font-family: Inter, system-ui, -apple-system, 'Segoe UI', sans-serif !important;
    }

    /* Genel metin rengi — metrik deltası HARİÇ: oradaki kırmızı/yeşil
       tüketimin arttığını mı azaldığını mı gösteriyor, ezilmemeli. */
    p, span,
    div:not([data-testid="stMetricDelta"]):not([data-testid="stMetricDelta"] *) {
        color: #24324d !important;
    }

    /* Markdown tabloları (st.markdown tablolar — Tahmin, Özet vb.) */
    .stMarkdown table td,
    .stMarkdown table th,
    [data-testid="stMarkdown"] table td,
    [data-testid="stMarkdown"] table th {
        color: #0f1f3d !important;
        background-color: transparent !important;
    }
    .stMarkdown table th {
        color: #0f1f3d !important;
        font-weight: 700 !important;
        border-bottom: 1px solid rgba(42,120,214, 0.3) !important;
    }
    
    /* Tabs */
    .stTabs [data-baseweb="tab-list"] {
        background: transparent;
        border-bottom: 1px solid rgba(24,26,30,0.10);
        gap: 24px;
        padding: 0;
    }

    .stTabs [data-baseweb="tab"] {
        background: transparent;
        color: #46536b !important;
        border-radius: 0;
        font-weight: 500;
        font-size: 11px;
        text-transform: uppercase;
        letter-spacing: 1px;
        padding: 8px 0 12px 0;
    }

    .stTabs [data-baseweb="tab"] p {
        color: inherit !important;
        font-size: 11px !important;
        font-weight: 500 !important;
        text-transform: uppercase !important;
        letter-spacing: 1px !important;
    }

    .stTabs [data-baseweb="tab"]:hover {
        color: #24324d !important;
    }

    .stTabs [aria-selected="true"] {
        background: transparent !important;
        color: #2a78d6 !important;
        box-shadow: inset 0 -2px 0 #2a78d6, 0 2px 8px rgba(42,120,214, 0.3) !important;
    }

    .stTabs [data-baseweb="tab-highlight"] {
        background-color: #2a78d6 !important;
        box-shadow: 0 -2px 8px rgba(42,120,214, 0.5) !important;
    }
    
    /* Normal butonlar */
    .stButton > button {
        background: rgba(14, 165, 233, 0.15) !important;
        color: #2a78d6 !important;
        border: 1px solid rgba(14, 165, 233, 0.3) !important;
        border-radius: 6px !important;
        font-weight: 500 !important;
        padding: 8px 20px !important;
        transition: all 0.2s;
    }
    .stButton > button:hover {
        background: rgba(14, 165, 233, 0.25) !important;
        border-color: rgba(14, 165, 233, 0.4) !important;
        color: #0f1f3d !important;
        transform: none;
        box-shadow: none !important;
    }

    /* Form submit butonları (Kaydet / Merkeze Gönder) */
    [data-testid="stFormSubmitButton"] button,
    .stFormSubmitButton button {
        background: rgba(14, 165, 233, 0.15) !important;
        color: #2a78d6 !important;
        border: 1px solid rgba(14, 165, 233, 0.3) !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        font-size: 13px !important;
        padding: 10px 20px !important;
        width: 100% !important;
        transition: all 0.2s;
        box-shadow: none !important;
    }
    [data-testid="stFormSubmitButton"] button:hover,
    .stFormSubmitButton button:hover {
        background: rgba(14, 165, 233, 0.25) !important;
        color: #0f1f3d !important;
        box-shadow: none !important;
        transform: none;
    }

    /* Input fields - soft köşeler, yumuşak glow */
    .stTextInput > div > div > input,
    .stDateInput > div > div > input,
    .stNumberInput > div > div > input,
    [data-testid="stNumberInput"] input,
    [data-testid="stTextInput"] input,
    [data-testid="stDateInput"] input,
    [data-testid="stNumberInputField"],
    [data-baseweb="input"] input,
    [data-baseweb="base-input"] input,
    input[type="number"],
    input[type="text"] {
        background: #ffffff !important;
        color: #24324d !important;
        border: 1px solid rgba(24,26,30,0.10) !important;
        border-radius: 10px !important;
        padding: 8px 12px !important;
        transition: border 0.2s, box-shadow 0.2s;
    }
    [data-testid="stNumberInput"] input:focus,
    [data-testid="stTextInput"] input:focus,
    [data-testid="stNumberInputField"]:focus,
    input:focus {
        border: 1px solid rgba(42,120,214, 0.6) !important;
        box-shadow: 0 0 0 3px rgba(42,120,214, 0.2) !important;
        outline: none !important;
    }

    /* Number input container — eski ve yeni BaseUI sürümleri */
    [data-testid="stNumberInput"] > div,
    [data-baseweb="input"],
    [data-baseweb="base-input"] {
        background: #ffffff !important;
        border: 1px solid rgba(24,26,30,0.10) !important;
        border-radius: 10px !important;
        box-shadow: 0 1px 4px rgba(20,22,26,0.2) !important;
    }

    /* Number input içindeki tüm span/div metin elementleri — görünürlük garantisi */
    [data-testid="stNumberInput"] span,
    [data-testid="stNumberInput"] div,
    [data-baseweb="input"] span,
    [data-baseweb="input"] div,
    [data-baseweb="base-input"] span,
    [data-baseweb="base-input"] div {
        color: #24324d !important;
    }

    /* Number input +/- butonları.
       Eskiden KOYU lacivert zemin (rgba(10,25,55,.9)) + mavi ikon vardı;
       portal koyu temadayken kalmış bir artıktı. Açık formda yama gibi
       duruyordu ve mavi ikon koyu zeminde okunmuyordu (kontrast ~3:1).
       Artık kutuyla aynı aileden: açık zemin, lacivert ikon. */
    [data-testid="stNumberInput"] button {
        background: #f6f7f9 !important;
        color: #24324d !important;
        border: 1px solid rgba(24,26,30,0.12) !important;
        border-radius: 8px !important;
    }
    [data-testid="stNumberInput"] button:hover {
        background: #e8edf4 !important;
        color: #133273 !important;
        border-color: rgba(42,120,214,0.45) !important;
    }
    [data-testid="stNumberInput"] button:disabled {
        opacity: 0.45 !important;
    }

    /* Selectbox dropdown */
    div[data-baseweb="select"] > div {
        background: #ffffff !important;
        color: #24324d !important;
        border: 1px solid rgba(24,26,30,0.10) !important;
        border-radius: 10px !important;
        box-shadow: 0 1px 4px rgba(20,22,26,0.2) !important;
    }

    /* Dropdown menu */
    ul[data-baseweb="menu"] {
        background: #ffffff !important;
        border: 1px solid rgba(24,26,30,0.10) !important;
        border-radius: 10px !important;
    }
    ul[data-baseweb="menu"] li {
        color: #24324d !important;
    }
    ul[data-baseweb="menu"] li:hover {
        background: #eef2f9 !important;
    }

    /* Input labels — daha okunabilir */
    .stTextInput label, .stSelectbox label, .stNumberInput label, .stDateInput label,
    [data-testid="stNumberInput"] label,
    [data-testid="stTextInput"] label,
    [data-testid="stDateInput"] label,
    [data-testid="stRadio"] > label,
    [data-testid="stCheckbox"] > label {
        color: #46536b !important;
        font-size: 13px !important;
        font-weight: 600 !important;
        letter-spacing: 0.3px !important;
        text-shadow: 0 1px 3px rgba(20,22,26,0.5) !important;
    }

    /* Placeholder */
    ::placeholder {
        color: rgba(140, 180, 255, 0.35) !important;
    }
    
    /* Dataframe - Enhanced for readability */
    .stDataFrame {
        background: #fafaf8;
        border-radius: 12px;
        border: 1px solid rgba(24,26,30,0.10);
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
        background-color: rgba(250,250,248, 0.9) !important;
        color: #0f1f3d !important;
        font-weight: 700 !important;
        font-size: 13px !important;
        padding: 12px 8px !important;
        border-bottom: 2px solid rgba(24,26,30,0.10) !important;
        text-align: left !important;
        min-width: 100px !important;
    }
    
    /* Dataframe cells - BEYAZ arka plan, SİYAH yazı */
    .stDataFrame tbody tr td,
    div[data-testid="stDataFrame"] tbody tr td,
    .dataframe tbody tr td {
        color: #0f1f3d !important;
        background-color: #fafaf8 !important;
        padding: 10px 8px !important;
        border-bottom: 1px solid rgba(20,22,26, 0.1) !important;
        font-size: 13px !important;
        min-width: 100px !important;
    }
    
    /* Override nested elements in cells - SİYAH yazı */
    .stDataFrame tbody tr td *,
    div[data-testid="stDataFrame"] tbody tr td *,
    .dataframe tbody tr td * {
        color: #0f1f3d !important;
    }
    
    /* GÜÇLÜ OVERRIDE - Tüm data elements */
    [data-testid="stDataFrame"] td,
    [data-testid="stDataFrame"] td span,
    [data-testid="stDataFrame"] td div,
    [data-testid="stDataFrame"] .dvn-scroller td,
    .dvn-scroller td,
    .glideDataEditor td,
    [data-testid="glide-data-grid-canvas"] {
        color: #0f1f3d !important;
        background-color: #fafaf8 !important;
    }
    
    /* Data grid text */
    .dvn-cell,
    .dvn-cell span,
    .gdg-cell {
        color: #0f1f3d !important;
    }
    
    /* Dataframe row hover */
    .stDataFrame tbody tr:hover,
    div[data-testid="stDataFrame"] tbody tr:hover,
    .dataframe tbody tr:hover {
        background-color: #fafaf8 !important;
    }
    
    /* Dataframe scrollbar */
    .stDataFrame ::-webkit-scrollbar {
        height: 10px;
        width: 10px;
    }
    
    .stDataFrame ::-webkit-scrollbar-track {
        background: #ffffff;
        border-radius: 5px;
    }
    
    .stDataFrame ::-webkit-scrollbar-thumb {
        background: rgba(250,250,248, 0.6);
        border-radius: 5px;
    }
    
    .stDataFrame ::-webkit-scrollbar-thumb:hover {
        background: rgba(250,250,248, 0.8);
    }
    
    /* Sidebar */
    [data-testid="stSidebar"] {
        background: #ffffff;
        border-right: 1px solid rgba(24,26,30,0.10);
    }
    
    /* File uploader alan */
    [data-testid="stFileUploader"] {
        background: #ffffff !important;
        border: 2px dashed rgba(24,26,30,0.10) !important;
        border-radius: 12px !important;
        padding: 16px !important;
    }
    [data-testid="stFileUploader"] label,
    [data-testid="stFileUploader"] span,
    [data-testid="stFileUploader"] p,
    [data-testid="stFileUploaderDropzone"] span,
    [data-testid="stFileUploaderDropzone"] p,
    [data-testid="stFileUploaderDropzone"] small {
        color: #46536b !important;
    }
    [data-testid="stFileUploaderDropzone"] {
        background: #ffffff !important;
        border-radius: 10px !important;
    }

    /* Browse files butonu */
    [data-testid="stFileUploaderDropzone"] button,
    [data-testid="stFileUploader"] button,
    [data-testid="stFileUploaderDropzoneInput"] + div button {
        background: rgba(14, 165, 233, 0.15) !important;
        color: #2a78d6 !important;
        border: 1px solid rgba(14, 165, 233, 0.3) !important;
        border-radius: 6px !important;
        font-weight: 500 !important;
        font-size: 13px !important;
        padding: 7px 16px !important;
        transition: all 0.2s;
    }
    [data-testid="stFileUploaderDropzone"] button:hover {
        background: rgba(14, 165, 233, 0.25) !important;
        color: #0f1f3d !important;
        box-shadow: none !important;
    }

    /* Download butonu */
    [data-testid="stDownloadButton"] button,
    .stDownloadButton button {
        background: rgba(14, 165, 233, 0.15) !important;
        color: #2a78d6 !important;
        border: 1px solid rgba(14, 165, 233, 0.3) !important;
        border-radius: 6px !important;
        font-weight: 600 !important;
        font-size: 13px !important;
        padding: 8px 18px !important;
        transition: all 0.2s;
        box-shadow: none !important;
    }
    [data-testid="stDownloadButton"] button:hover,
    .stDownloadButton button:hover {
        background: rgba(14, 165, 233, 0.25) !important;
        color: #0f1f3d !important;
        box-shadow: none !important;
        transform: none;
    }

    /* Divider / çizgiler — daha belirgin */
    hr {
        border: none !important;
        border-top: 2px solid rgba(42,120,214, 0.60) !important;
        margin: 22px 0 !important;
        opacity: 1 !important;
        box-shadow: 0 0 8px rgba(42,120,214, 0.25) !important;
    }
    [data-testid="stDivider"] > div {
        border-top: 2px solid rgba(42,120,214, 0.60) !important;
        box-shadow: 0 0 8px rgba(42,120,214, 0.25) !important;
    }

    /* Dataframe / tablolar - koyu arka plan, görünür çizgilerle */
    .stDataFrame {
        background: #ffffff !important;
        border-radius: 12px !important;
        border: 1px solid rgba(24,26,30,0.10) !important;
        overflow: hidden !important;
    }
    .stDataFrame table,
    div[data-testid="stDataFrame"] table,
    .dataframe {
        font-size: 13px !important;
        color: #24324d !important;
        border-collapse: collapse !important;
        width: 100% !important;
    }
    /* Tablo başlıkları */
    .stDataFrame thead tr th,
    div[data-testid="stDataFrame"] thead tr th,
    .dataframe thead tr th {
        background: rgba(250,250,248, 0.95) !important;
        color: #0f1f3d !important;
        font-weight: 700 !important;
        font-size: 12px !important;
        padding: 10px 10px !important;
        border-bottom: 2px solid rgba(42,120,214, 0.4) !important;
        border-right: 1px solid rgba(42,120,214, 0.15) !important;
        text-align: left !important;
        letter-spacing: 0.3px !important;
    }
    /* Tablo hücreleri - koyu arka plan görünür çizgilerle */
    .stDataFrame tbody tr td,
    div[data-testid="stDataFrame"] tbody tr td,
    .dataframe tbody tr td {
        color: #24324d !important;
        background-color: #ffffff !important;
        padding: 8px 10px !important;
        border-bottom: 1px solid rgba(24,26,30,0.10) !important;
        border-right: 1px solid rgba(24,26,30,0.10) !important;
        font-size: 13px !important;
    }
    .stDataFrame tbody tr td *,
    div[data-testid="stDataFrame"] tbody tr td * {
        color: #24324d !important;
    }
    /* Satır hover */
    .stDataFrame tbody tr:hover td,
    div[data-testid="stDataFrame"] tbody tr:hover td {
        background-color: rgba(42,120,214, 0.3) !important;
    }
    /* Çift satır rengi */
    .stDataFrame tbody tr:nth-child(even) td,
    div[data-testid="stDataFrame"] tbody tr:nth-child(even) td {
        background-color: rgba(15, 35, 75, 0.7) !important;
    }
    /* Glide data grid (yeni Streamlit dataframe) */
    [data-testid="stDataFrame"] td,
    [data-testid="stDataFrame"] td span,
    [data-testid="stDataFrame"] td div,
    .dvn-cell, .dvn-cell span, .gdg-cell {
        color: #24324d !important;
        background-color: #ffffff !important;
    }
    /* render_styled_table (unsafe_allow_html tablo) — satır değerleri her zaman görünür */
    table.dataframe td,
    table[id^="T_"] td,
    table[id^="T_"] tbody td {
        color: #24324d !important;
        background-color: #ffffff !important;
    }
    table.dataframe th,
    table[id^="T_"] th {
        color: #0f1f3d !important;
        background-color: rgba(250,250,248, 0.9) !important;
    }
    /* Scrollbar */
    .stDataFrame ::-webkit-scrollbar { height: 8px; width: 8px; }
    .stDataFrame ::-webkit-scrollbar-track { background: rgba(10,20,50,0.5); border-radius: 4px; }
    .stDataFrame ::-webkit-scrollbar-thumb { background: rgba(26,74,158,0.6); border-radius: 4px; }
    .stDataFrame ::-webkit-scrollbar-thumb:hover { background: rgba(37,99,235,0.8); }

    /* st.table() statik tablolar */
    .stTable table {
        border-collapse: collapse !important;
        width: 100% !important;
        background: #ffffff !important;
        border-radius: 10px !important;
        overflow: hidden !important;
    }
    .stTable th {
        background: rgba(250,250,248, 0.95) !important;
        color: #0f1f3d !important;
        font-weight: 700 !important;
        padding: 10px 12px !important;
        border-bottom: 2px solid rgba(42,120,214, 0.4) !important;
        font-size: 12px !important;
    }
    .stTable td {
        color: #24324d !important;
        background: #ffffff !important;
        padding: 8px 12px !important;
        border-bottom: 1px solid rgba(24,26,30,0.10) !important;
        font-size: 13px !important;
    }

    /* Subheader ve section başlıkları */
    [data-testid="stSubheader"],
    .stSubheader {
        color: #24324d !important;
    }

    /* Info / success / warning / error kutuları */
    [data-testid="stAlert"] {
        border-radius: 10px !important;
        border: 1px solid rgba(24,26,30,0.10) !important;
    }

    /* ════════ EXPANDER — standart koyu tema ════════ */
    [data-testid="stExpander"] {
        border: 1px solid rgba(24,26,30,0.10) !important;
        border-radius: 10px !important;
        overflow: hidden !important;
        background: #ffffff !important;
    }
    .streamlit-expanderHeader,
    [data-testid="stExpander"] summary {
        background: #ffffff !important;
        border-radius: 10px !important;
        color: #24324d !important;
        font-weight: 600 !important;
        padding: 10px 14px !important;
    }
    [data-testid="stExpander"] summary:hover {
        background: rgba(26, 50, 100, 0.9) !important;
    }
    [data-testid="stExpander"] summary p,
    [data-testid="stExpander"] summary span,
    [data-testid="stExpander"] summary div {
        color: #24324d !important;
    }
    /* Expander içeriği */
    [data-testid="stExpander"] > div > div {
        background: rgba(8, 18, 45, 0.55) !important;
        border-top: 1px solid rgba(24,26,30,0.10) !important;
        padding: 12px 14px !important;
    }

    /* Checkbox */
    [data-testid="stCheckbox"] label {
        color: #46536b !important;
    }

    /* Radio butonları */
    [data-testid="stRadio"] label {
        color: #46536b !important;
        font-weight: 600 !important;
    }

    /* ════════ TARİH INPUT — format placeholder fix ════════ */
    /* Tarih alanının tüm içeriği koyu arka plan */
    [data-testid="stDateInput"] > div,
    [data-testid="stDateInput"] [data-baseweb="input"],
    [data-testid="stDateInput"] [data-baseweb="base-input"] {
        background: #ffffff !important;
        border: 1px solid rgba(24,26,30,0.10) !important;
        border-radius: 10px !important;
    }
    /* Tarih alanı giriş metni ve format (YYYY/MM/DD) */
    [data-testid="stDateInputField"],
    [data-testid="stDateInputField"]:focus,
    input[data-testid="stDateInputField"] {
        background: transparent !important;
        color: #24324d !important;
        caret-color: #2a78d6 !important;
    }
    /* Format placeholder rengi — daha belirgin */
    [data-testid="stDateInputField"]::placeholder {
        color: rgba(42,120,214, 0.55) !important;
        font-style: italic !important;
    }
    /* Tarih alanı ikon/ok rengi */
    [data-testid="stDateInput"] svg {
        fill: rgba(42,120,214, 0.7) !important;
    }

    /* ════════ SELECTBOX — kapsamlı koyu tema ════════ */
    /* Container */
    [data-baseweb="select"],
    div[data-baseweb="select"] {
        background: #ffffff !important;
        border-radius: 10px !important;
    }
    div[data-baseweb="select"] > div,
    [data-baseweb="select"] > div {
        background: #ffffff !important;
        color: #24324d !important;
        border: 1px solid rgba(24,26,30,0.10) !important;
        border-radius: 10px !important;
        box-shadow: 0 1px 4px rgba(20,22,26,0.2) !important;
    }
    div[data-baseweb="select"] > div:hover {
        border-color: rgba(42,120,214, 0.55) !important;
    }
    /* Seçili değer metni */
    [data-baseweb="select"] [data-testid="stSelectboxVirtualDropdown"],
    [data-baseweb="select"] span,
    [data-baseweb="select"] input,
    [data-baseweb="select"] input[readonly] {
        color: #24324d !important;
        background: transparent !important;
    }
    /* Ok simgesi */
    [data-baseweb="select"] svg {
        fill: rgba(42,120,214, 0.8) !important;
    }
    /* Dropdown açılır liste */
    [data-baseweb="popover"] ul[data-baseweb="menu"],
    ul[data-baseweb="menu"] {
        background: #ffffff !important;
        border: 1px solid rgba(24,26,30,0.10) !important;
        border-radius: 12px !important;
        box-shadow: 0 1px 1px rgba(20,22,26,.05),0 10px 22px -12px rgba(20,22,26,.26) !important;
    }
    ul[data-baseweb="menu"] li,
    ul[data-baseweb="menu"] [role="option"] {
        color: #24324d !important;
        background: transparent !important;
    }
    ul[data-baseweb="menu"] li:hover,
    ul[data-baseweb="menu"] [aria-selected="true"],
    ul[data-baseweb="menu"] [role="option"]:hover {
        background: #eef2f9 !important;
        color: #133273 !important;
    }

    /* ════════ MULTİSELECT — chip/tag standart stili ════════ */
    [data-baseweb="tag"] {
        background: rgba(26, 60, 130, 0.65) !important;
        border: 1px solid rgba(80, 140, 255, 0.4) !important;
        border-radius: 6px !important;
    }
    [data-baseweb="tag"] span,
    [data-baseweb="tag"] [data-testid="stMultiSelectItem"],
    [data-baseweb="tag"] > span {
        color: #24324d !important;
        font-weight: 600 !important;
    }
    /* Chip silme (X) butonu */
    [data-baseweb="tag"] button,
    [data-baseweb="tag"] [role="button"] {
        color: #46536b !important;
        background: transparent !important;
    }
    [data-baseweb="tag"] button:hover {
        color: #0f1f3d !important;
        background: rgba(200, 80, 80, 0.3) !important;
    }
    /* Multiselect container */
    [data-baseweb="multi-select"] {
        background: #ffffff !important;
        border: 1px solid rgba(24,26,30,0.10) !important;
        border-radius: 10px !important;
    }
    [data-baseweb="multi-select"] input {
        color: #24324d !important;
        background: transparent !important;
    }
    [data-baseweb="multi-select"] input::placeholder {
        color: rgba(42,120,214, 0.45) !important;
    }

    /* ════════ TAKVIM (Date Picker) FİX — Soft Glassmorphism ════════ */

    /* Ana kutu — eski soft hissi korunuyor */
    [data-baseweb="calendar"] {
        background: #ffffff !important;
        border: 1px solid rgba(24,26,30,0.10) !important;
        border-radius: 16px !important;
        box-shadow:
            0 1px 1px rgba(20,22,26,.05),
            0 12px 26px -12px rgba(20,22,26,.26) !important;
        overflow: hidden !important;
    }

    /* Tüm div/span/tablo hücreleri — header + boş köşe hücreler dahil */
    [data-baseweb="calendar"] div,
    [data-baseweb="calendar"] span,
    [data-baseweb="calendar"] table,
    [data-baseweb="calendar"] td,
    [data-baseweb="calendar"] th,
    [data-baseweb="calendar"] [role="grid"],
    [data-baseweb="calendar"] [role="row"],
    [data-baseweb="calendar"] [role="gridcell"],
    [data-baseweb="calendar"] [role="columnheader"] {
        background-color: transparent !important;
        color: #24324d !important;
    }

    /* Butonlar — saydam, soft hover */
    [data-baseweb="calendar"] button {
        background-color: transparent !important;
        color: #24324d !important;
        border: none !important;
        border-radius: 8px !important;
        transition: background 0.15s ease !important;
    }
    [data-baseweb="calendar"] button:hover {
        background-color: rgba(42,120,214, 0.3) !important;
        color: #0f1f3d !important;
    }

    /* Seçili gün — mavi daire */
    [data-baseweb="calendar"] [aria-selected="true"] button,
    [data-baseweb="calendar"] button[aria-selected="true"] {
        background-color: #133273 !important;
        color: #ffffff !important;
        border-radius: 50% !important;
        box-shadow: none !important;
    }

    /* Bugün — ince mavi kenarlık */
    [data-baseweb="calendar"] button[aria-current="date"] {
        border: 1px solid #133273 !important;
        border-radius: 50% !important;
    }

    /* Devre dışı günler */
    [data-baseweb="calendar"] button:disabled {
        color: #a9a8a3 !important;
        background-color: transparent !important;
    }

    /* Haftanın günleri başlık (Mo Tu We...) */
    [data-baseweb="calendar"] [role="columnheader"] {
        color: #46536b !important;
        font-size: 11px !important;
        font-weight: 700 !important;
        letter-spacing: 0.5px !important;
    }

    /* Ay/Yıl selectbox butonları (header'daki April, 2026) */
    [data-baseweb="calendar"] [data-baseweb="select"] > div,
    [data-baseweb="calendar"] [data-baseweb="select"] div,
    [data-baseweb="calendar"] [data-baseweb="select"] span,
    [data-baseweb="calendar"] [data-baseweb="select"] input {
        background-color: rgba(15, 30, 70, 0.7) !important;
        color: #24324d !important;
        border-color: rgba(24,26,30,0.10) !important;
    }
    [data-baseweb="calendar"] [data-baseweb="select"] svg {
        fill: rgba(42,120,214, 0.7) !important;
    }

    /* ════ Ay/Yıl açılır liste (tıklayınca çıkan seçenekler) ════
       Bu liste ayrı bir popover olarak render edilir.
       ul[data-baseweb="menu"] zaten globalde tanımlı ama
       burada daha yüksek özgüllükle tekrar hedefliyoruz. */
    ul[data-baseweb="menu"],
    [data-baseweb="menu"] {
        background: rgba(2, 6, 23, 0.97) !important;
        border: 1px solid rgba(24,26,30,0.10) !important;
        border-radius: 10px !important;
        box-shadow: 0 8px 24px rgba(20,22,26,0.55) !important;
    }
    ul[data-baseweb="menu"] li,
    ul[data-baseweb="menu"] [role="option"],
    [data-baseweb="menu"] li,
    [data-baseweb="menu"] [role="option"],
    [data-baseweb="menu-item"],
    [role="listbox"] [role="option"] {
        color: #24324d !important;
        background-color: transparent !important;
        font-size: 13px !important;
    }
    ul[data-baseweb="menu"] li:hover,
    ul[data-baseweb="menu"] [role="option"]:hover,
    [data-baseweb="menu"] li:hover,
    [role="listbox"] [role="option"]:hover,
    ul[data-baseweb="menu"] [aria-selected="true"],
    [role="listbox"] [aria-selected="true"] {
        background-color: rgba(42,120,214, 0.4) !important;
        color: #0f1f3d !important;
    }
    /* Liste içindeki tüm span/div metinleri */
    ul[data-baseweb="menu"] li span,
    ul[data-baseweb="menu"] li div,
    ul[data-baseweb="menu"] [role="option"] span,
    [data-baseweb="menu-item"] span,
    [data-baseweb="menu-item"] div {
        color: #24324d !important;
        background-color: transparent !important;
    }

    /* Takvim içi ay/yıl listesi — role=option LI elemanları */
    [data-baseweb="calendar"] [role="option"],
    [data-baseweb="calendar"] li[role="option"] {
        color: #24324d !important;
        background-color: transparent !important;
        border-radius: 8px !important;
        padding: 4px 10px !important;
    }
    [data-baseweb="calendar"] [role="option"]:hover {
        background-color: rgba(42,120,214, 0.35) !important;
        color: #0f1f3d !important;
    }
    [data-baseweb="calendar"] [role="option"][aria-selected="true"],
    [data-baseweb="calendar"] li[role="option"][aria-selected="true"] {
        background-color: rgba(42,120,214, 0.55) !important;
        color: #0f1f3d !important;
        font-weight: 600 !important;
    }

    /* ════════ SLIDER — standart ════════ */
    [data-testid="stSlider"] [data-baseweb="slider"] [role="slider"] {
        background: #2a78d6 !important;
        border: 2px solid rgba(42,120,214, 0.7) !important;
    }
    [data-testid="stSlider"] [data-baseweb="slider"] div[class*="Track"] {
        background: #eef2f9 !important;
    }

    /* ════════ GENEL METİN OKUNABİLİRLİK FİX ════════ */
    .stMarkdown h1, .stMarkdown h2, .stMarkdown h3,
    .stMarkdown h4, .stMarkdown h5, .stMarkdown h6 {
        color: #0f1f3d !important;
        font-weight: 700 !important;
        padding-bottom: 6px !important;
        border-bottom: 1px solid rgba(42,120,214, 0.35) !important;
        margin-bottom: 12px !important;
    }
    .stMarkdown p, .stMarkdown li {
        color: #24324d !important;
        line-height: 1.65 !important;
        font-size: 14px !important;
    }
    [data-testid="stSubheader"] h3 {
        color: #e0eeff !important;
        font-size: 18px !important;
        font-weight: 700 !important;
    }
    .stCaption, [data-testid="stCaptionContainer"] p {
        color: #46536b !important;
        font-size: 12px !important;
    }
    strong, b {
        color: #0f1f3d !important;
        font-weight: 700 !important;
    }
</style>
<script>
// ── BasEUI Dropdown Koyu Tema — MutationObserver V2 ──
// Gerçek DOM yapısı: [data-baseweb="popover"] > div > div > ul > div > li[role="option"]
// Yani menu wrapper YOK — role="option" direkt hedeflenir.
(function() {
    var DARK_BG  = '#ffffff';
    var TEXT_CLR = '#24324d';
    var HOVER_BG = '#f1f0ed';
    var SEL_BG   = '#eef2f9';
    var BORDER   = '1px solid rgba(24,26,30,0.10)';
    var RADIUS   = '12px';

    // Tek bir [role="option"] öğesini stillendir
    function styleOption(el) {
        el.style.setProperty('color', TEXT_CLR, 'important');
        el.style.setProperty('background-color', 'transparent', 'important');
        if (el.getAttribute('aria-selected') === 'true') {
            el.style.setProperty('background-color', SEL_BG, 'important');
            el.style.setProperty('color', '#133273', 'important');
        }
        el.querySelectorAll('span, div, p').forEach(function(c) {
            c.style.setProperty('color', TEXT_CLR, 'important');
            c.style.setProperty('background-color', 'transparent', 'important');
        });
        if (!el._hvacHover) {
            el._hvacHover = true;
            el.addEventListener('mouseenter', function() {
                if (el.getAttribute('aria-selected') !== 'true') {
                    el.style.setProperty('background-color', HOVER_BG, 'important');
                    el.style.setProperty('color', '#0f1f3d', 'important');
                    el.querySelectorAll('span, div, p').forEach(function(c) {
                        c.style.setProperty('color', '#0f1f3d', 'important');
                    });
                }
            });
            el.addEventListener('mouseleave', function() {
                if (el.getAttribute('aria-selected') !== 'true') {
                    el.style.setProperty('background-color', 'transparent', 'important');
                    el.style.setProperty('color', TEXT_CLR, 'important');
                    el.querySelectorAll('span, div, p').forEach(function(c) {
                        c.style.setProperty('color', TEXT_CLR, 'important');
                    });
                }
            });
        }
    }

    function applyDark(root) {
        // Popover arka planı (tüm dropdown kapsayıcılar)
        root.querySelectorAll('[data-baseweb="popover"]').forEach(function(el) {
            el.style.setProperty('background-color', DARK_BG, 'important');
            el.style.setProperty('border', BORDER, 'important');
            el.style.setProperty('border-radius', RADIUS, 'important');
            el.style.setProperty('box-shadow', '0 8px 24px rgba(20,22,26,0.55)', 'important');
        });

        // Menu wrapper varsa (eski Streamlit versiyonları)
        root.querySelectorAll('[data-baseweb="menu"]').forEach(function(el) {
            el.style.setProperty('background-color', DARK_BG, 'important');
        });

        // Popover içindeki UL (liste arka planı)
        root.querySelectorAll('[data-baseweb="popover"] ul').forEach(function(el) {
            el.style.setProperty('background-color', DARK_BG, 'important');
        });

        // TÜM role="option" — parent bağımsız, her Streamlit versiyonunda çalışır
        root.querySelectorAll('[role="option"]').forEach(styleOption);

        // Root'un kendisi role="option" ise (MutationObserver'dan geliyorsa)
        if (root.getAttribute && root.getAttribute('role') === 'option') {
            styleOption(root);
        }

        // Selectbox seçili değer
        root.querySelectorAll('[data-baseweb="select"] span, [data-baseweb="select"] input')
            .forEach(function(el) {
                el.style.setProperty('color', TEXT_CLR, 'important');
            });
    }

    // Sayfa açılışında uygula
    applyDark(document);

    // DOM değişikliklerini izle
    var observer = new MutationObserver(function(mutations) {
        mutations.forEach(function(m) {
            m.addedNodes.forEach(function(node) {
                if (node.nodeType !== 1) return;
                var db = node.getAttribute ? node.getAttribute('data-baseweb') : null;
                var role = node.getAttribute ? node.getAttribute('role') : null;

                // Popover eklenirse içini stillendir
                if (db === 'popover') {
                    applyDark(node);
                    return;
                }
                // Herhangi bir role="option" eklendiyse direkt stillendir
                if (role === 'option') {
                    styleOption(node);
                    return;
                }
                // Genel ekleme — içinde option var mı bak
                if (node.querySelector && node.querySelector('[role="option"]')) {
                    applyDark(node);
                }
            });
        });
    });
    observer.observe(document.body, { childList: true, subtree: true });
})();
</script>
""", unsafe_allow_html=True)

# ─── BÖLÜM KARTLARI ───────────────────────────────────────────────────────
# Dashboard, Aylık Birleşik Rapor ve Tahmin & Trend sekmelerindeki bölümler
# düz başlık + ayraçtan ibaretti; hangi sayının hangi bölüme ait olduğu
# anlaşılmıyordu. Artık her bölüm bir kart: anahtarı "kart_" ile başlar,
# biçim aşağıdaki TEK kuraldan gelir. Yeni bölüm eklerken sadece
# _bolum_karti("kart_<ad>", "Başlık") demek yeter.
st.markdown("""
<style>
[class*="st-key-kart_"] {
    background: #fafaf8 !important;
    border: 1px solid rgba(24,26,30,0.16) !important;
    border-left: 5px solid #2a78d6 !important;
    border-radius: 14px !important;
    box-shadow: 0 2px 6px rgba(24,26,30,0.06) !important;
    margin-bottom: 14px !important;
    padding: 14px 18px 16px !important;
}
/* Kart içindeki öğeler kabın genişliğini miras alır; dolgu verilince
   taşmasınlar diye %100'e sabitlenir. */
[class*="st-key-kart_"] > div { width: 100% !important; }
/* Başlık satırı: altında ince ayraç */
[class*="st-key-kart_"] > div:first-child {
    border-bottom: 1px solid rgba(24,26,30,0.12);
    padding-bottom: 8px;
    margin-bottom: 6px;
}
[class*="st-key-kart_"] > div:first-child p {
    font-size: 15px !important;
    color: #24324d !important;
    letter-spacing: 0.2px;
}
[class*="st-key-kart_"] .kart-aciklama {
    display: block;
    font-size: 12px;
    font-weight: 400;
    color: #5b6880 !important;
    margin-top: 2px;
}
/* Bölüm rengi: ölçüm mavi, oran/alan mor, tasarruf amber, tahmin yeşil */
[class*="st-key-kart_m2"], [class*="st-key-kart_ml"],
[class*="st-key-kart_ai"]      { border-left-color: #8b5cf6 !important; }
[class*="st-key-kart_tasarruf"]
                               { border-left-color: #c98500 !important; }
[class*="st-key-kart_tahmin"], [class*="st-key-kart_senaryo"],
[class*="st-key-kart_gelecek"] { border-left-color: #0ca30c !important; }
</style>
""", unsafe_allow_html=True)


@contextmanager
def _bolum_karti(anahtar: str, baslik: str, aciklama: str = ""):
    """Başlıklı bölüm kartı. anahtar "kart_" ile başlamalı (CSS ona bakar)."""
    with st.container(border=False, key=anahtar):
        _ek = f"<span class='kart-aciklama'>{aciklama}</span>" if aciklama else ""
        st.markdown(f"<p><strong>{baslik}</strong>{_ek}</p>", unsafe_allow_html=True)
        yield


def metrik_notlu(etiket: str, deger, not_metni=None, **kw):
    """Altında NÖTR bir açıklama satırı olan metrik.

    NEDEN AYRI: Bu açıklamalar (birim fiyat, "(alan bazlı)", "2025→2026",
    "Gelişiyor" gibi) eskiden st.metric'e delta diye veriliyor, renk de
    delta_color="off" ile kapatılıyordu. İki sorun çıkıyordu:
      1) Streamlit delta'nın yanına HER ZAMAN bir ↑ oku koyar — "2,45 TL/kWh"
         ya da "2025→2026" yanındaki yukarı ok "arttı" demek olur, yanlış bilgi.
      2) "off" rengi rgba(15,31,61,0.6) — soluk gri; kullanıcı 23.10.2026'da
         maliyet kartlarının altındaki yazıların okunmadığını bildirdi.
    Gerçek bir değişim gösterilecekse st.metric'in kendi delta'sı kullanılır
    (ok ve renk orada DOĞRU bilgidir); bu yardımcı sadece etiket/not içindir.
    """
    st.metric(etiket, deger, **kw)
    if not_metni:
        st.markdown(
            "<div class='metrik-not'>%s</div>"
            % str(not_metni).replace("&", "&amp;").replace("<", "&lt;"),
            unsafe_allow_html=True,
        )


st.markdown("""
<style>
.metrik-not {
    margin: -10px 0 2px 2px;
    font-size: 0.80rem;
    line-height: 1.3;
    color: #4a5a78;              /* delta "off" grisinin okunur hali */
    font-variant-numeric: tabular-nums;
}
</style>
""", unsafe_allow_html=True)

# ── Hareket: kartlar süzülerek gelir, sayılar gerçek değere sayarak açılır ──
# (portal_hareket.py — veriye dokunmaz, uydurma/akan değer üretmez)
try:
    import portal_hareket as _portal_hareket
    _portal_hareket.uygula(st, components)
except Exception:
    pass

# ── Tasarım dili: Mekanik Zeka başlığı + Synapse sekme/kart/simge (portal_tasarim.py) ──
try:
    import portal_tasarim as _pt
    st.markdown(_pt.CSS + (_pt.IK.CSS if _pt.IK else "") + _pt.sekme_css(), unsafe_allow_html=True)
except Exception:
    _pt = None

# ── BasEUI Dropdown Koyu Tema — components.html ile gerçek JS enjeksiyonu ──
# st.markdown içindeki <script> tarayıcı tarafından çalıştırılmaz (innerHTML güvenliği).
# components.html bir iframe oluşturur → window.parent.document ile parent DOM'a erişir.
components.html("""
<script>
(function() {
    var DARK_BG  = '#ffffff';
    var TEXT_CLR = '#24324d';
    var HOVER_BG = '#f1f0ed';
    var SEL_BG   = '#eef2f9';
    var BORDER   = '1px solid rgba(24,26,30,0.10)';
    var RADIUS   = '12px';

    function styleOption(el) {
        el.style.setProperty('color', TEXT_CLR, 'important');
        el.style.setProperty('background-color', 'transparent', 'important');
        if (el.getAttribute('aria-selected') === 'true') {
            el.style.setProperty('background-color', SEL_BG, 'important');
            el.style.setProperty('color', '#133273', 'important');
        }
        el.querySelectorAll('span, div, p').forEach(function(c) {
            c.style.setProperty('color', TEXT_CLR, 'important');
            c.style.setProperty('background-color', 'transparent', 'important');
        });
        if (!el._hvacHover) {
            el._hvacHover = true;
            el.addEventListener('mouseenter', function() {
                if (el.getAttribute('aria-selected') !== 'true') {
                    el.style.setProperty('background-color', HOVER_BG, 'important');
                    el.style.setProperty('color', '#0f1f3d', 'important');
                    el.querySelectorAll('span,div,p').forEach(function(c){ c.style.setProperty('color','#0f1f3d','important'); });
                }
            });
            el.addEventListener('mouseleave', function() {
                if (el.getAttribute('aria-selected') !== 'true') {
                    el.style.setProperty('background-color', 'transparent', 'important');
                    el.style.setProperty('color', TEXT_CLR, 'important');
                    el.querySelectorAll('span,div,p').forEach(function(c){ c.style.setProperty('color',TEXT_CLR,'important'); });
                }
            });
        }
    }

    function applyDark(root) {
        root.querySelectorAll('[data-baseweb="popover"]').forEach(function(el) {
            el.style.setProperty('background-color', DARK_BG, 'important');
            el.style.setProperty('border', BORDER, 'important');
            el.style.setProperty('border-radius', RADIUS, 'important');
            el.style.setProperty('box-shadow', '0 8px 24px rgba(20,22,26,0.55)', 'important');
        });
        root.querySelectorAll('[data-baseweb="popover"] ul,[data-baseweb="menu"]').forEach(function(el) {
            el.style.setProperty('background-color', DARK_BG, 'important');
        });
        root.querySelectorAll('[role="option"]').forEach(styleOption);
        if (root.getAttribute && root.getAttribute('role') === 'option') styleOption(root);
        root.querySelectorAll('[data-baseweb="select"] span,[data-baseweb="select"] input').forEach(function(el) {
            el.style.setProperty('color', TEXT_CLR, 'important');
        });
    }

    function setup(doc) {
        applyDark(doc);
        var obs = new MutationObserver(function(mutations) {
            mutations.forEach(function(m) {
                m.addedNodes.forEach(function(node) {
                    if (node.nodeType !== 1) return;
                    var db   = node.getAttribute ? node.getAttribute('data-baseweb') : null;
                    var role = node.getAttribute ? node.getAttribute('role') : null;
                    if (db === 'popover') { applyDark(node); return; }
                    if (role === 'option') { styleOption(node); return; }
                    if (node.querySelector && node.querySelector('[role="option"]')) applyDark(node);
                });
            });
        });
        obs.observe(doc.body, { childList: true, subtree: true });
        doc._hvacObserver = obs;
    }

    try {
        var pDoc = window.parent.document;
        if (pDoc && pDoc.body) {
            setup(pDoc);
        } else {
            window.parent.addEventListener('load', function() { setup(window.parent.document); });
        }
    } catch(e) {
        console.warn('HVAC observer error:', e);
    }
})();
</script>
""", height=0)

# ---- Portal navigasyon (HVAC / Enerji ana menü) ----
PORTAL_URL = os.environ.get("PORTAL_URL", "http://localhost:8005/")

from location_manager import get_manager as get_location_manager
_loc_mgr = get_location_manager()
_loc_mgr.ensure_locations_ready()
_loc_config = _loc_mgr.get_location_config()

# Lokasyon adı ve Ana Sayfa artık başlık kartında (aşağıda, "UI" bölümü)

# --- FAZ 7: MANUEL SYNC (form içine taşındı) ---
DATA_FILE = _loc_mgr.get_data_path("energy_data.csv")

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
    "Kojen_Adet",        # BACnet KOJEN-1..4 DURUM (data_bridge); listede olmazsa portal SİLER
] + _TEMP_COLS_SCHEMA + [
    "Kar_Eritme_Aktif",
    "TRDP1_kWh",
    "TRDP2_kWh",
    "TRDP3_kWh",
    "TRDP4_kWh",
    "Sebeke_Tuketim_kWh",
    "Kojen_Uretim_kWh",
    "Kojen1_kWh",        # 27.10.2026: kojen sayaçları (Kojen_Uretim = toplamı, enerji_hesap)
    "Kojen2_kWh",
    "Kojen3_kWh",
    "Kojen4_kWh",
    "Kazan_Dogalgaz_m3",
    "Kojen_Dogalgaz_m3",
    "Su_Tuketimi_m3",
    "Chiller_Tuketim_kWh",
    "MCC_Tuketim_kWh",
    "VRF_Split_Tuketim_kWh",
    "Dis_Hava_Sicakligi_C",
    "Chiller_Load_Percent",
    "Toplam_Hastane_Tuketim_kWh",
    "Toplam_Sogutma_Tuketim_kWh",
    "Diger_Yuk_kWh",
    "Chiller1_kWh",
    "Chiller2_kWh",
    "Chiller3_kWh",
    "Chiller4_kWh",
    "Chiller5_kWh",
    "MCC1_kWh",
    "MCC2_kWh",
    "MCC3_kWh",
    "MCC4_kWh",
    "MCC5_kWh",
    "MCC6_kWh",
    "MCC7_kWh",
    "Kule1_kWh",
    "Kule2_kWh",
    "Kule3_kWh",
    "MCC_2BK_D01_kWh",
    "MCC_2BK_D02_kWh",
    "MCC_4BK_E01_kWh",
    "MCC_4BK_E02_kWh",
    "MCC_4BK_F01_kWh",
    "MCC_CK_D01_kWh",
    "MCC_CK_E01_kWh",
    "MCC_CK_F01_kWh",
]

# Hava sütunları (bina nem sensörü + lokasyonun internetten aldığı günlük hava).
# Liste TEK YERDE (hava_durumu.py): ensure_schema listede olmayan sütunu her
# açılışta sildiği için burada ayrıca yazılmaz — ayrışırsa veri kaybolur.
try:
    from hava_durumu import HAVA_SUTUNLARI as _HAVA_SUTUNLARI, SAYISAL_SUTUNLAR as _HAVA_SAYISAL
except Exception:
    _HAVA_SUTUNLARI, _HAVA_SAYISAL = [], []
SCHEMA = SCHEMA + _HAVA_SUTUNLARI

# Günlük veri girişi formundaki hava alanları: (session_state anahtarı, sütun)
_HAVA_FORM_ALANLARI = [
    ("entry_hava_ort", "Hava_Sicaklik_Ort_C"), ("entry_hava_max", "Hava_Sicaklik_Max_C"),
    ("entry_hava_min", "Hava_Sicaklik_Min_C"), ("entry_hava_nem", "Hava_Nem_Ort_Yuzde"),
    ("entry_nem_sensor", "Dis_Hava_Nem_Yuzde"), ("entry_hava_yagis", "Hava_Yagis_mm"),
    ("entry_hava_bulut", "Hava_Bulut_Yuzde"), ("entry_hava_rad", "Hava_Gunes_Radyasyon_kWh_m2"),
    ("entry_hava_ruzgar", "Hava_Ruzgar_Ort_kmh"),
]
_HAVA_DURUMLARI = ["", "güneşli", "bulutlu", "yağmurlu", "karlı", "sisli"]   # hava_durumu.durum_metni ile aynı

NUMERIC_COLS = [
    "Chiller_Set_Temp_C",
    "Chiller_Adet",
    "Absorption_Chiller_Adet",
    "Kazan_Adet",
    "Kojen_Adet",
] + _TEMP_COLS_SCHEMA + [
    "TRDP1_kWh",
    "TRDP2_kWh",
    "TRDP3_kWh",
    "TRDP4_kWh",
    "Sebeke_Tuketim_kWh",
    "Kojen_Uretim_kWh",
    "Kojen1_kWh",        # 27.10.2026: kojen sayaçları (Kojen_Uretim = toplamı, enerji_hesap)
    "Kojen2_kWh",
    "Kojen3_kWh",
    "Kojen4_kWh",
    "Kazan_Dogalgaz_m3",
    "Kojen_Dogalgaz_m3",
    "Su_Tuketimi_m3",
    "Chiller_Tuketim_kWh",
    "MCC_Tuketim_kWh",
    "VRF_Split_Tuketim_kWh",
    "Dis_Hava_Sicakligi_C",
    "Chiller_Load_Percent",
    "Toplam_Hastane_Tuketim_kWh",
    "Toplam_Sogutma_Tuketim_kWh",
    "Diger_Yuk_kWh",
    "Chiller1_kWh",
    "Chiller2_kWh",
    "Chiller3_kWh",
    "Chiller4_kWh",
    "Chiller5_kWh",
    "MCC1_kWh",
    "MCC2_kWh",
    "MCC3_kWh",
    "MCC4_kWh",
    "MCC5_kWh",
    "MCC6_kWh",
    "MCC7_kWh",
    "Kule1_kWh",
    "Kule2_kWh",
    "Kule3_kWh",
    "MCC_2BK_D01_kWh",
    "MCC_2BK_D02_kWh",
    "MCC_4BK_E01_kWh",
    "MCC_4BK_E02_kWh",
    "MCC_4BK_F01_kWh",
    "MCC_CK_D01_kWh",
    "MCC_CK_E01_kWh",
    "MCC_CK_F01_kWh",
] + _HAVA_SAYISAL

TR_MAP = str.maketrans({
    "ş": "s", "Ş": "s",
    "ı": "i", "İ": "i",
    "ğ": "g", "Ğ": "g",
    "ü": "u", "Ü": "u",
    "ö": "o", "Ö": "o",
    "ç": "c", "Ç": "c",
})


def sayi(deger, varsayilan: float = 0.0) -> float:
    """Sayıya çevir; boş/bozuk/NaN ise varsayılanı ver.

    NEDEN AYRI BİR YARDIMCI: "float(x) or 0" kalıbı NaN'ı YAKALAMAZ —
    NaN Python'da doğru (truthy) sayılır, dolayısıyla `or 0` devreye
    girmez ve NaN olduğu gibi akar. Ekranda "₺nan" diye göründü
    (23.10.2026: su tüketimi boş olan günde Su ve Toplam Maliyet
    kartları nan yazdı). Pandas'ın boş hücresi de NaN'dır, yani bu
    tuzağa her boş alanda düşülür.
    """
    try:
        d = float(deger)
    except (TypeError, ValueError):
        return varsayilan
    return varsayilan if d != d else d          # d != d → NaN


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

    _kn = re.search(r"kojen ?([1-4])\b", k)
    if _kn and "gaz" not in k and "adet" not in k:
        return "Kojen%s_kWh" % _kn.group(1)          # "Kojen-3 Üretim" → Kojen3_kWh

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
            # Türkçe format: 7.563,010 → 7563.010
            v = v.replace(".", "").replace(",", ".")
        elif has_comma and not has_dot:
            # Virgül ondalık ayraç: 7,563 → 7.563
            v = v.replace(",", ".")
        elif has_dot and not has_comma:
            # Sadece nokta — binlik ayraç mı yoksa ondalık mı?
            # Kural: son noktadan sonra tam 3 rakam varsa → binlik ayraç (Türkçe)
            # Tek nokta:  7.563  → 7563 | 13.9 → 13.9 (ondalık, 1 basamak)
            # Çift nokta: 3.422.900 → son grubu at → 3.422 → 3422
            #             7.563.010 → son grubu at → 7.563 → 7563
            parts = v.split(".")
            if (
                len(parts) >= 2
                and all(len(p) == 3 and p.isdigit() for p in parts[1:])
                and parts[0].lstrip("-").isdigit()
            ):
                if len(parts) > 2:
                    # Çift nokta: son 3 rakamı at, kalanı birleştir (3.422.900 → 3422)
                    v = "".join(parts[:-1])
                else:
                    # Tek nokta 3 basamak: binlik ayraç (7.563 → 7563)
                    v = v.replace(".", "")
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
    """Türetilmiş enerji sütunlarını yeniden hesaplar.

    Kural enerji_hesap.py'de TEK YERDE durur; cloud_sync de buluta
    göndermeden önce aynı modülü kullanır (portal hiç açılmasa bile
    Synapse doğru değeri görsün diye).
    """
    if df.empty:
        return df
    return _enerji_hesap.yeniden_hesapla(df)


@st.cache_data(show_spinner=False, ttl=300)
def load_data() -> pd.DataFrame:
    if not os.path.exists(DATA_FILE):
        return empty_df()
    df = pd.read_csv(DATA_FILE)
    df = ensure_schema(df)
    df = coerce_types(df)
    df = recalc(df)
    df = df.dropna(subset=["Tarih"]).sort_values("Tarih")
    # recalc sonrasi hesaplanan turetime sutunlari CSV'ye geri yaz
    # (cloud_sync dogru degeri Supabase'e gonderebilsin)
    try:
        out = df.copy()
        out["Tarih"] = out["Tarih"].astype(str)
        _atomik_csv_yaz(out, DATA_FILE)
    except Exception:
        pass
    return df


def _atomik_csv_yaz(df: pd.DataFrame, hedef: str) -> None:
    """CSV'yi önce geçici dosyaya yazıp os.replace ile atomik taşır.
    Eşzamanlı erişimde (data_bridge / cloud_sync) yarım/bozuk dosya oluşmasını önler."""
    import os as _os, tempfile as _tf
    _dizin = _os.path.dirname(_os.path.abspath(hedef)) or "."
    _fd, _gecici = _tf.mkstemp(suffix=".tmp", prefix="energy_", dir=_dizin)
    _os.close(_fd)
    try:
        df.to_csv(_gecici, index=False)
        _os.replace(_gecici, hedef)  # atomik (aynı dosya sistemi)
    except Exception:
        if _os.path.exists(_gecici):
            try: _os.remove(_gecici)
            except OSError: pass
        raise


def persist_df(df: pd.DataFrame) -> None:
    out = df.copy()
    out["Tarih"] = out["Tarih"].astype(str)
    _atomik_csv_yaz(out, DATA_FILE)
    load_data.clear()

    # --- FAZ 7: KAYIT ANINDA BULUTA TETIKLE (INSTANT SYNC) ---
    try:
        from cloud_sync import run_sync
        import threading
        t = threading.Thread(target=run_sync, daemon=True, name="cloud-instant-sync")
        t.start()
    except Exception:
        pass


def _eski_degerleri_koru(df_new: pd.DataFrame, df_eski: pd.DataFrame,
                         gelen_sutunlar: list) -> pd.DataFrame:
    """Aynı tarihin ESKİ satırındaki, bu kayıtta GELMEYEN alanları korur.

    Enerji giriş formunda yalnızca elle okunan kalemler var; MCC / Chiller /
    Kule alt sayaçlarını data_bridge günde bir kez yazıyor. Eski davranışta
    kayıt o tarihin satırını TÜMÜYLE yenisiyle değiştiriyordu: geçmiş bir güne
    su veya doğalgaz girilince aynı günün sayaç değerleri siliniyor, enerji
    diyagramında tarih duruyor ama bütün çipler "veri yok" görünüyordu.

    Kural: sütun bu kayıtta HİÇ gelmediyse eski değeri kalır; geldiyse (0 dahil)
    olduğu gibi yazılır — kullanıcı bir kalemi bilerek sıfırlayabilsin diye.
    Yalnızca gelen değer boşsa (NaN) eskisi yedek olarak kullanılır.
    """
    _esk = df_eski.drop_duplicates(subset=["Tarih"], keep="last").set_index("Tarih")
    for _c in df_new.columns:
        if _c == "Tarih" or _c not in _esk.columns:
            continue
        _eski_deger = df_new["Tarih"].map(_esk[_c])
        if _c in gelen_sutunlar:
            df_new[_c] = df_new[_c].where(df_new[_c].notna(), _eski_deger)
        else:
            df_new[_c] = _eski_deger
    return df_new


def upsert_by_date(df_new: pd.DataFrame) -> tuple[int, int]:
    # Gelen tabloda GERÇEKTEN bulunan sütunlar — ensure_schema şemanın geri
    # kalanını NaN ile dolduracağı için ÖNCE saklanır (_eski_degerleri_koru).
    _gelen_sutunlar = [c for c in df_new.columns if c != "Tarih"]
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

    _ayni_tarih = df_old[df_old["Tarih"].isin(new_dates)]
    df_old = df_old[~df_old["Tarih"].isin(new_dates)]
    if not _ayni_tarih.empty:
        df_new = _eski_degerleri_koru(df_new, _ayni_tarih, _gelen_sutunlar)
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
            new_val = sayi(new_row.get(col, 0))
            
            if new_val == 0:
                continue
            
            # ===== DÜNKÜ DEĞER KARŞILAŞTIRMASI =====
            if last_row is not None:
                old_val = sayi(last_row.get(col, 0))
                
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
                last_year_val = sayi(last_year_row.get(col, 0))
                
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


def yoy_month_compare(df: pd.DataFrame, year: int, month: int,
                      prev_year: int = None, prev_month: int = None) -> dict:
    """Seçilen ay ile karşılaştırılan ay. Karşılaştırma verilmezse geçen yılın aynı ayı."""
    cur_start, cur_end = month_range(year, month)
    prev_start, prev_end = month_range(prev_year if prev_year is not None else year - 1,
                                       prev_month if prev_month is not None else month)
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
        col1, col2, col3, col4, col5 = st.columns([1, 2, 2, 2, 1])
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
            _git_sayfa = st.number_input(
                "Sayfaya git", min_value=1, max_value=total_pages,
                value=st.session_state[page_key],
                step=1, key=f"goto_{table_key}", label_visibility="collapsed"
            )
            if _git_sayfa != st.session_state[page_key]:
                st.session_state[page_key] = int(_git_sayfa)
                st.rerun()
        with col5:
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
        'background-color': '#fafaf8',
        'color': '#0f1f3d',
        'border': '1px solid #e0e0e0',
        'padding': '4px 6px',
        'font-size': '11px',
        'white-space': 'nowrap'
    }).set_table_styles([
        {'selector': 'th', 'props': [
            ('background-color', '#012D75'),
            ('color', '#0f1f3d'),
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


def chart_consumption_vs_temp(df_period: pd.DataFrame, view_mode: str = "Günlük"):
    if df_period.empty:
        return None
    d = df_period.copy()
    d["Tarih"] = pd.to_datetime(d["Tarih"], format="%Y-%m-%d", errors="coerce")

    xfmt = {'Günlük': '%d %b', 'Aylık': '%b %Y', 'Yıllık': '%Y'}.get(view_mode, '%d %b')

    import plotly.graph_objects as go

    fig = go.Figure()

    # Ana çizgi - Toplam Tüketim (gradient fill ile)
    fig.add_trace(go.Scatter(
        x=d["Tarih"],
        y=d["Toplam_Hastane_Tuketim_kWh"],
        mode='lines+markers',
        name='Toplam Tüketim',
        line=dict(color='#6da7ec', width=3, shape='spline'),
        marker=dict(size=10, color='#6da7ec', line=dict(color='white', width=2)),
        fill='tozeroy',
        fillcolor='rgba(109,167,236, 0.15)',
        hovertemplate=f'<b>%{{x|{xfmt}}}</b><br>Tüketim: %{{y:,.0f}} kWh<extra></extra>'
    ))

    # İkinci eksen - Dış Hava Sıcaklığı
    fig.add_trace(go.Scatter(
        x=d["Tarih"],
        y=d["Dis_Hava_Sicakligi_C"],
        mode='lines+markers',
        name='Dış Hava (°C)',
        yaxis='y2',
        line=dict(color='#c98500', width=3, dash='dot', shape='spline'),
        marker=dict(size=8, color='#c98500', symbol='diamond', line=dict(color='white', width=2)),
        hovertemplate=f'<b>%{{x|{xfmt}}}</b><br>Sıcaklık: %{{y:.1f}}°C<extra></extra>'
    ))

    # Modern layout - Premium koyu tema
    fig.update_layout(
        title=dict(
            text='<b>📊 Günlük Tüketim & Dış Hava Sıcaklığı</b>',
            font=dict(size=20, color='#0f1f3d', family="Inter, sans-serif"),
            x=0.02,
            xanchor='left'
        ),
        font=dict(family="Inter, sans-serif", size=13, color='#24324d'),
        plot_bgcolor='rgba(250,250,248, 0.98)',
        paper_bgcolor='rgba(250,250,248, 0.98)',
        yaxis=dict(
            # Eksen başlığı çizgi rengiyle aynı tonun KOYUSU: açık zeminde
            # '#6da7ec' okunmuyordu.
            title=dict(text="Toplam Tüketim (kWh)", font=dict(color='#2a78d6')),
            tickfont=dict(color='#3a4660'),
            gridcolor='rgba(109,167,236, 0.1)',
            showgrid=True,
            zeroline=False,
            tickformat=',d'
        ),
        yaxis2=dict(
            title=dict(text="Dış Hava (°C)", font=dict(color='#8a5a00')),
            tickfont=dict(color='#3a4660'),
            overlaying="y",
            side="right",
            showgrid=False,
            zeroline=False
        ),
        xaxis=dict(
            gridcolor='rgba(24,26,30,0.10)',
            showgrid=True,
            tickfont=dict(color='#3a4660'),
            tickformat=xfmt
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor='rgba(241,240,237, 0.9)',
            bordercolor='rgba(24,26,30,0.10)',
            borderwidth=1,
            font=dict(color='#24324d')
        ),
        margin=dict(l=10, r=10, t=80, b=10),
        hovermode='x unified',
        hoverlabel=dict(
            bgcolor="rgba(241,240,237, 0.95)",
            font_size=13,
            font_family="Inter, sans-serif",
            font_color="#24324d",
            bordercolor='rgba(24,26,30,0.10)'
        )
    )
    return fig


def chart_stacked_breakdown(df_period: pd.DataFrame, view_mode: str = "Günlük"):
    if df_period.empty:
        return None
    d = df_period.copy()
    d["Tarih"] = pd.to_datetime(d["Tarih"], format="%Y-%m-%d", errors="coerce")
    xfmt = {'Günlük': '%d %b', 'Aylık': '%b %Y', 'Yıllık': '%Y'}.get(view_mode, '%d %b')
    plot_df = d[["Tarih", "Chiller_Tuketim_kWh", "MCC_Tuketim_kWh", "Diger_Yuk_kWh"]].fillna(0).copy()
    plot_df = plot_df.rename(columns={
        "Chiller_Tuketim_kWh": "❄️ Chiller",
        "MCC_Tuketim_kWh": "⚡ MCC",
        "Diger_Yuk_kWh": "💡 Aydınlatma/Diğer",
    })
    plot_df = plot_df.melt(id_vars=["Tarih"], var_name="Bileşen", value_name="kWh")
    
    # Premium gradyan renk paleti
    colors = {
        '❄️ Chiller': '#256abf',      # Cyan
        '⚡ MCC': '#8b5cf6',            # Violet
        '💡 Aydınlatma/Diğer': '#c98500'  # Amber
    }
    
    fig = px.bar(
        plot_df, x="Tarih", y="kWh", color="Bileşen", barmode="stack",
        title="<b>⚡ Enerji Kırılımı</b>",
        labels={"Tarih": "", "kWh": "Tüketim (kWh)"},
        color_discrete_map=colors
    )
    
    # Premium koyu tema layout
    fig.update_layout(
        font=dict(family="Inter, sans-serif", size=13, color='#24324d'),
        plot_bgcolor='rgba(250,250,248, 0.98)',
        paper_bgcolor='rgba(250,250,248, 0.98)',
        title=dict(
            font=dict(size=20, color='#0f1f3d', family="Inter, sans-serif"),
            x=0.02,
            xanchor='left'
        ),
        yaxis=dict(
            gridcolor='rgba(24,26,30,0.10)',
            showgrid=True,
            zeroline=False,
            tickfont=dict(color='#3a4660'),
            tickformat=',d'
        ),
        xaxis=dict(
            gridcolor='rgba(24,26,30,0.10)',
            showgrid=False,
            tickfont=dict(color='#3a4660'),
            tickformat=xfmt
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor='rgba(241,240,237, 0.9)',
            bordercolor='rgba(24,26,30,0.10)',
            borderwidth=1,
            font=dict(color='#24324d'),
            title=None
        ),
        margin=dict(l=10, r=10, t=80, b=10),
        hovermode='x unified',
        hoverlabel=dict(
            bgcolor="rgba(241,240,237, 0.95)",
            font_size=13,
            font_family="Inter, sans-serif",
            font_color="#24324d",
            bordercolor='rgba(24,26,30,0.10)'
        ),
        bargap=0.2
    )
    
    # Yuvarlatılmış bar köşeleri ve gölge efekti
    fig.update_traces(
        marker=dict(
            line=dict(color='rgba(24,26,30,0.10)', width=1)
        ),
        hovertemplate=f'<b>%{{x|{xfmt}}}</b><br>%{{y:,.0f}} kWh<extra></extra>'
    )

    return fig


def chart_month_vs_last_year(yoy_info: dict, baslik: str = None):
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
        cur_start.strftime("%Y-%m"): '#0ca30c',   # Emerald (Bu yıl)
        prev_start.strftime("%Y-%m"): '#6366f1'   # Indigo (Geçen yıl)
    }
    
    fig = px.bar(
        dfp, x="Metrik", y="Değer", color="Dönem", barmode="group",
        title="<b>📅 %s</b>" % (baslik or "Bu Ay vs Geçen Yıl Aynı Ay"),
        labels={"Değer": "Toplam (kWh)", "Metrik": ""},
        color_discrete_map=colors
    )
    
    # Premium koyu tema layout
    fig.update_layout(
        font=dict(family="Inter, sans-serif", size=13, color='#24324d'),
        plot_bgcolor='rgba(250,250,248, 0.98)',
        paper_bgcolor='rgba(250,250,248, 0.98)',
        title=dict(
            font=dict(size=20, color='#0f1f3d', family="Inter, sans-serif"),
            x=0.02,
            xanchor='left'
        ),
        yaxis=dict(
            gridcolor='rgba(24,26,30,0.10)',
            showgrid=True,
            zeroline=False,
            tickfont=dict(color='#3a4660'),
            tickformat=',d'
        ),
        xaxis=dict(
            gridcolor='rgba(24,26,30,0.10)',
            showgrid=False,
            # Etiketler uzun ("🏥 Toplam Hastane"); yatay yazılınca iç içe
            # giriyordu. Hafif eğik + altta yer bırakılarak okunur kalıyor.
            tickangle=-18,
            tickfont=dict(color='#3a4660', size=12)
        ),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor='rgba(241,240,237, 0.9)',
            bordercolor='rgba(24,26,30,0.10)',
            borderwidth=1,
            font=dict(color='#24324d'),
            title=None
        ),
        margin=dict(l=10, r=10, t=80, b=70),
        hovermode='x unified',
        hoverlabel=dict(
            bgcolor="rgba(241,240,237, 0.95)",
            font_size=13,
            font_family="Inter, sans-serif",
            font_color="#24324d",
            bordercolor='rgba(24,26,30,0.10)'
        ),
        bargap=0.25,
        bargroupgap=0.15
    )
    
    # Premium bar styling
    fig.update_traces(
        marker=dict(
            line=dict(color='rgba(24,26,30,0.10)', width=1)
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
    """Plotly figürü PNG byte'a çevir — matplotlib ile render eder."""
    # ── Matplotlib render (kaleido kullanılmıyor) ────────────────────────
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        import io as _io

        BG = "#0f1729"
        COLORS = ["#6da7ec", "#c98500", "#0ca30c", "#4a3aa7", "#eb6834", "#d03b3b"]

        fig_mpl, ax = plt.subplots(figsize=(14, 7), facecolor=BG)
        ax.set_facecolor(BG)
        ax.tick_params(colors="#46536b")
        for spine in ax.spines.values():
            spine.set_edgecolor("#334155")

        color_idx = 0
        for trace in fig.data:
            ttype = type(trace).__name__.lower()
            color = COLORS[color_idx % len(COLORS)]
            color_idx += 1

            xs = list(trace.x) if getattr(trace, "x", None) is not None else []
            ys = list(trace.y) if getattr(trace, "y", None) is not None else []
            name = getattr(trace, "name", "") or ""

            if ttype in ("scatter", "scattergl") and xs and ys:
                # line rengi varsa kullan
                try:
                    lc = trace.line.color
                    if lc:
                        color = lc
                except Exception:
                    pass
                ax.plot(xs, ys, label=name, color=color, linewidth=2)

            elif ttype == "bar" and xs and ys:
                try:
                    mc = trace.marker.color
                    if mc:
                        color = mc if isinstance(mc, str) else COLORS[color_idx % len(COLORS)]
                except Exception:
                    pass
                ax.bar(xs, ys, label=name, color=color, alpha=0.85)

            elif ttype in ("pie",):
                vals = list(trace.values) if getattr(trace, "values", None) is not None else ys
                labs = list(trace.labels) if getattr(trace, "labels", None) is not None else xs
                if vals:
                    ax.clear()
                    ax.set_facecolor(BG)
                    ax.pie(vals, labels=labs, autopct="%1.0f%%",
                           colors=COLORS[:len(vals)],
                           textprops={"color": "#46536b", "fontsize": 10})

        if ax.get_lines() or ax.patches:
            legend = ax.legend(facecolor="#f1f0ed", labelcolor="#46536b",
                               edgecolor="#334155", fontsize=9)

        buf = _io.BytesIO()
        plt.tight_layout(pad=0.5)
        plt.savefig(buf, format="png", facecolor=BG, dpi=150)
        plt.close(fig_mpl)
        buf.seek(0)
        return buf.read()
    except Exception:
        return None


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
                if "matplotlib" in error_msg.lower():
                    pdf.multi_cell(0, 5, T("Grafik gorsele cevrilemedi. 'matplotlib' paketi gerekli: pip install -U matplotlib"))
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

        # Aylık bakım notu (işaret girilmediyse)
        try:
            from bakim_durum import rapor_notu as _bk_not
            _bn = _bk_not()
            if _bn:
                pdf.set_y(footer_y - 10)
                pdf.set_fill_color(254, 226, 226)
                pdf.set_text_color(220, 38, 38)
                pdf.set_font(font, 'B', 9)
                pdf.multi_cell(0, 7, T("! " + _bn), fill=True)
        except Exception:
            pass

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
        error_pdf.multi_cell(0, 6, "Kontrol edin:\n- Matplotlib paketi yuklu mu (pip install -U matplotlib)\n- Veri gecerli mi\n- Yeterli disk alani var mi")

        raw = error_pdf.output(dest="S")
        if isinstance(raw, (bytes, bytearray)):
            return bytes(raw)
        return raw.encode("latin-1", errors="ignore")



# =============================
# UI
# =============================
# ── Başlık: Mekanik Zeka ile aynı düzen (Ana Sayfa + Ayarlar; Bakım Kartları yok) ──
def _baslik_ciz():
    try:
        _son_t = pd.to_datetime(load_data()["Tarih"], errors="coerce").max()
        _son_txt = _son_t.strftime("%d.%m.%Y") if pd.notna(_son_t) else "—"
    except Exception:
        _son_txt = "—"
    _lok_adi = _loc_config.get("name", "ACIBADEM MASLAK HASTANESİ")
    _ana = PORTAL_URL if PORTAL_URL.endswith("/") else PORTAL_URL + "/"
    if _pt is None:
        st.title("⚡ Enerji ve Verimlilik")
        st.markdown(f"[⬅ Ana Sayfa]({_ana})")
        return
    st.markdown(_pt.baslik_html(
        "Enerji ve Verimlilik", "Enerji Yönetimi & Raporlama", "Sistem Hazır",
        f"{_lok_adi} · Son kayıt: {_son_txt}",
        [("Ana Sayfa", "geri", _ana),
         # Ayarlar Mekanik Zeka'da tek yerde; #ayarlar ayar penceresini açar
         ("Ayarlar", "ayar", _ana + "static/index.html#ayarlar")]), unsafe_allow_html=True)


_baslik_ciz()

# ── Aylık bakım uyarısı (ayın 25'inden itibaren işaret yoksa) ──
try:
    from bakim_durum import uyari_gerekli as _bakim_uyari
    if _bakim_uyari():
        st.error(
            "🔧 **Bu ay santral bakımları yapılmamıştır** — aylık bakım işareti girilmedi. "
            "HVAC portalı → Bakım Kartları → \"Bu Ayın Bakımı Yapıldı\" ile işaretleyin. "
            "İşaretlenmezse tüm raporlara bakım notu düşer ve Synapse'de alarm görünür."
        )
except Exception:
    pass

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

_dr_col1, _dr_col2, _dr_col3 = st.columns([3, 1, 1])
with _dr_col1:
    st.caption("Merkezi Performans İzleme")
with _dr_col2:
    if st.button("📄 Günlük Rapor Oluştur", key="daily_report_btn", use_container_width=True):
        try:
            import sys
            sys.path.insert(0, os.path.dirname(__file__))
            from daily_report import DailyReportGenerator
            gen = DailyReportGenerator()
            _dr_path = gen.generate()
            st.session_state["daily_report_path"] = _dr_path
            st.session_state["daily_report_ready"] = True
            st.session_state["_rapor_toast"] = "📄 Günlük rapor hazır — bildirim çubuğundan indirin."
            st.rerun()
        except Exception as e:
            st.error(f"Rapor oluşturulamadı: {e}")
with _dr_col3:
    if st.button("📊 Aylık Rapor Oluştur", key="monthly_report_btn", use_container_width=True):
        try:
            import sys
            sys.path.insert(0, os.path.dirname(__file__))
            from monthly_summary_report import MonthlyReportGenerator
            gen = MonthlyReportGenerator()
            _mr_path = gen.generate()
            st.session_state["monthly_report_path"] = _mr_path
            st.session_state["monthly_report_ready"] = True
            st.session_state["_rapor_toast"] = "📊 Aylık rapor hazır — bildirim çubuğundan indirin."
            st.rerun()
        except Exception as e:
            st.error(f"Aylık rapor oluşturulamadı: {e}")

def _rapor_kayitlari():
    """Hazır PDF raporları bildirim kaydına çevirir.

    Raporlar eskiden sayfanın üstünde yeşil kutu + indirme düğmesi olarak
    duruyordu; dört rapor birikince ekranın yarısını kaplıyordu. Artık tek
    yerde — bildirim çubuğunda — listelenir, indirme oradan yapılır.
    """
    _kayit = []

    def _ekle(tur, baslik, yol, zaman, notif_anahtar=None):
        if not yol or not os.path.exists(yol):
            return
        _kb = round(os.path.getsize(yol) / 1024, 1)
        _kayit.append({
            "kaynak": "rapor", "sinif": "rapor", "id": None,
            "gonderen": baslik,
            "zaman": zaman or "",
            "mesaj": f"{os.path.basename(yol)} — {_kb} KB",
            "dosya": yol,
            "anahtar": tur,
            "notif_anahtar": notif_anahtar,
        })

    if _daily_auto_ready:
        _ekle("auto_daily", "Günlük rapor (otomatik)", _daily_notif.get("filepath"),
              _daily_notif.get("timestamp", ""), "daily")
    if _monthly_auto_ready:
        _ekle("auto_monthly", "Aylık rapor (otomatik)", _monthly_notif.get("filepath"),
              _monthly_notif.get("timestamp", ""), "monthly")
    if st.session_state.get("daily_report_ready"):
        _ekle("manual_daily", "Günlük rapor (elle)",
              st.session_state.get("daily_report_path", ""), "")
    if st.session_state.get("monthly_report_ready"):
        _ekle("manual_monthly", "Aylık rapor (elle)",
              st.session_state.get("monthly_report_path", ""), "")
    return _kayit


def _rapor_okundu_isaretle(notif_anahtar):
    """İndirilen otomatik rapor bildirimini configs dosyasında kapatır."""
    if not notif_anahtar or notif_anahtar not in _auto_notifs:
        return
    try:
        _auto_notifs[notif_anahtar]["seen"] = True
        with open(_notif_file, "w", encoding="utf-8") as _wnf:
            _notif_json.dump(_auto_notifs, _wnf, indent=2, ensure_ascii=False)
    except Exception:
        pass


# ─── BİLDİRİM ÇUBUĞU ──────────────────────────────────────────────────────
# Tek şerit, üç kaynak:
#   1) Supabase `bildirimler` — GM merkezden gelen mesajlar, HVAC analiz özeti
#   2) veri_alarm.py          — analizör bağlantı hatası / boş günlük veri
#   3) Hazır PDF raporları    — günlük/aylık, otomatik veya elle üretilmiş
# Aynı alarm listesi heartbeat ile Synapse'teki CANLI UYARILAR'a da düşer.
def _bildirim_panel():
    import json as _bj
    import urllib.request
    from datetime import datetime as _dt2

    _ONEM_SIRA = {"acil": 0, "kritik": 0, "uyari": 1, "yuksek": 1, "normal": 2,
                  "bilgi": 2, "rapor": 3}
    _RENK = {"acil": ("#b42525", "rgba(208,59,59,.08)", "rgba(208,59,59,.45)", "🚨", "KRİTİK"),
             "uyari": ("#8a5a00", "rgba(250,178,25,.10)", "rgba(250,178,25,.50)", "⚠️", "UYARI"),
             "bilgi": ("#133273", "rgba(19,50,115,.06)", "rgba(24,26,30,.12)", "ℹ️", "BİLGİ"),
             "rapor": ("#1b7a3e", "rgba(27,122,62,.08)", "rgba(27,122,62,.35)", "📄", "RAPOR")}
    _SINIFLAR = ("acil", "uyari", "bilgi", "rapor")

    def _sinif(onem):
        o = (onem or "bilgi").lower()
        if o in ("acil", "kritik"):
            return "acil"
        if o in ("uyari", "yuksek"):
            return "uyari"
        return "bilgi"

    # ── 1) Veri toplama alarmları (yerel dosya — Supabase'e gerek yok) ──
    _kayitlar = []
    try:
        import veri_alarm
        for _a in (veri_alarm.oku().get("alarmlar") or []):
            _kayitlar.append({
                "kaynak": "veri",
                "sinif": _sinif(_a.get("onem")),
                "mesaj": _a.get("mesaj", ""),
                "gonderen": "Veri Toplama",
                "zaman": _a.get("tarih", ""),
                "id": None,
            })
    except Exception:
        pass

    # ── 2) Supabase bildirimleri ──
    _cfg_path = os.path.join(os.path.dirname(__file__), "supabase_config.json")
    _url = _key = _lok = ""
    if os.path.exists(_cfg_path):
        try:
            with open(_cfg_path, "r", encoding="utf-8") as _f:
                _cfg = _bj.load(_f)
            _url, _key, _lok = (_cfg.get("supabase_url", ""), _cfg.get("supabase_key", ""),
                                _cfg.get("lokasyon_id", ""))
        except Exception:
            pass

    if _url and _key and _lok and "BURAYA" not in _url:
        _now_ts = _dt2.now().timestamp()
        _cached = st.session_state.get("_bildirimler_cache", None)
        if _cached is None or (_now_ts - st.session_state.get("_bildirim_last_check", 0)) > 300:
            try:
                _req = urllib.request.Request(
                    _url + (f"/rest/v1/bildirimler?or=(lokasyon.eq.{_lok},lokasyon.eq.all)"
                            f"&okundu=eq.false&order=created_at.asc"),
                    headers={"apikey": _key, "Authorization": "Bearer " + _key,
                             "Content-Type": "application/json"})
                with urllib.request.urlopen(_req, timeout=5) as _resp:
                    _cached = _bj.loads(_resp.read().decode())
                st.session_state["_bildirimler_cache"] = _cached
                st.session_state["_bildirim_last_check"] = _now_ts
            except Exception:
                _cached = st.session_state.get("_bildirimler_cache", [])
        for _b in (_cached or []):
            _kayitlar.append({
                "kaynak": "mesaj",
                "sinif": _sinif(_b.get("oncelik")),
                "mesaj": _b.get("mesaj", ""),
                "gonderen": _b.get("gonderen", "GM Merkez"),
                "zaman": (_b.get("created_at", "") or "")[:16].replace("T", " "),
                "id": _b.get("id", ""),
            })

    # ── 3) Hazır raporlar (indirme bildirim çubuğunda) ──
    _kayitlar.extend(_rapor_kayitlari())

    if not _kayitlar:
        return

    _kayitlar.sort(key=lambda k: _ONEM_SIRA.get(k["sinif"], 3))
    _say = {s: sum(1 for k in _kayitlar if k["sinif"] == s) for s in _SINIFLAR}
    _en_agir = _kayitlar[0]["sinif"]
    _yazi, _zemin, _kenar, _ikon, _etiket = _RENK[_en_agir]

    # ── Şerit: tek satır özet (rozet + en önemli mesajın ilk satırı) ──
    _rozet = " ".join(
        f"<span style='background:{_RENK[s][1]};border:1px solid {_RENK[s][2]};color:{_RENK[s][0]};"
        f"border-radius:20px;padding:2px 10px;font-size:11px;font-weight:700;margin-right:6px;'>"
        f"{_RENK[s][3]} {_say[s]} {_RENK[s][4]}</span>"
        for s in _SINIFLAR if _say[s])
    _ilk = _kayitlar[0]["mesaj"].splitlines()[0] if _kayitlar[0]["mesaj"] else ""
    st.markdown(
        f"<div style='background:{_zemin};border:1px solid {_kenar};border-left:4px solid {_yazi};"
        f"border-radius:12px;padding:10px 14px;margin:6px 0 2px;'>"
        f"<div style='display:flex;align-items:center;gap:8px;flex-wrap:wrap;'>{_rozet}"
        f"<span style='color:{_yazi};font-size:13px;font-weight:600;'>{_ilk}</span></div></div>",
        unsafe_allow_html=True)

    def _okundu_yap(kayit_id=None):
        """Tek bildirimi ya da (kayit_id yoksa) bu lokasyonun okunmamış
        bildirimlerinin TAMAMINI Supabase'de okundu olarak işaretler."""
        if not (_url and _key and _lok):
            return
        _hedef = (f"/rest/v1/bildirimler?id=eq.{kayit_id}" if kayit_id else
                  f"/rest/v1/bildirimler?or=(lokasyon.eq.{_lok},lokasyon.eq.all)"
                  f"&okundu=eq.false")
        try:
            _pr = urllib.request.Request(
                _url + _hedef,
                data=_bj.dumps({"okundu": True}).encode(),
                headers={"apikey": _key, "Authorization": "Bearer " + _key,
                         "Content-Type": "application/json",
                         "Prefer": "return=minimal"},
                method="PATCH")
            urllib.request.urlopen(_pr, timeout=5)
        except Exception:
            pass
        st.session_state.pop("_bildirimler_cache", None)

    # ── Ayrıntı: tek tek kayıtlar, mesajlar için "okundu" ──
    with st.expander(f"Bildirimler ({len(_kayitlar)})", expanded=(_en_agir == "acil")):
        # Toplu kapatma — çok sayıda mesaj birikince tek tek kapatmak zorunda
        # kalınmasın. Veri alarmları ve raporlar bu düğmeden etkilenmez:
        # alarm sayaç okunmaya başlayınca kendi düşer, rapor indirilince kapanır.
        _mesaj_sayisi = sum(1 for _k in _kayitlar if _k["kaynak"] == "mesaj" and _k["id"])
        if _mesaj_sayisi:
            _t1, _t2 = st.columns([9, 1])
            with _t1:
                st.caption(f"{_mesaj_sayisi} okunmamış mesaj")
            with _t2:
                # Etiket kısa: sağdaki sütun dar, uzun yazı alt alta kırılıyor.
                if st.button("✓✓ Tümü", key="_okundu_tumu",
                             use_container_width=True,
                             help=f"{_mesaj_sayisi} mesajın tamamını okundu olarak işaretle"):
                    _okundu_yap()
                    st.rerun()

        for _i, _k in enumerate(_kayitlar):
            _y, _z, _c, _ik, _et = _RENK[_k["sinif"]]
            _c1, _c2 = st.columns([9, 1])
            with _c1:
                st.markdown(
                    f"<div style='background:{_z};border:1px solid {_c};border-left:4px solid {_y};"
                    f"border-radius:10px;padding:9px 14px;margin-bottom:4px;'>"
                    f"<span style='color:{_y};font-weight:700;font-size:11px;'>"
                    f"{_ik} {_et} · {_k['gonderen']}" + (f" · {_k['zaman']}" if _k["zaman"] else "")
                    + "</span><br>"
                    f"<span style='color:#0f1f3d;font-size:13.5px;white-space:pre-line;'>"
                    f"{_k['mesaj']}</span></div>", unsafe_allow_html=True)
            with _c2:
                if _k["kaynak"] == "rapor":
                    with open(_k["dosya"], "rb") as _rf:
                        if st.download_button(
                                "⬇️ İndir", data=_rf.read(),
                                file_name=os.path.basename(_k["dosya"]),
                                mime="application/pdf",
                                key=f"_rapor_indir_{_k['anahtar']}",
                                use_container_width=True):
                            _rapor_okundu_isaretle(_k.get("notif_anahtar"))
                elif _k["kaynak"] == "mesaj" and _k["id"]:
                    if st.button("✓ Okundu", key=f"_okundu_{_k['id']}", use_container_width=True):
                        _okundu_yap(_k["id"])
                        st.rerun()
                else:
                    # Veri alarmları elle kapatılmaz: sayaç okunmaya başlayınca
                    # bir sonraki günlük turda kendiliğinden düşer.
                    st.caption("otomatik")

_bildirim_panel()
# Elle üretilen rapor: indirme çubukta, kullanıcı nereye bakacağını bilsin.
if st.session_state.pop("_rapor_toast", None):
    st.toast("Rapor hazır — bildirim çubuğundan indirebilirsiniz.", icon="📄")
# ───────────────────────────────────────────────────────────────────────────

df = load_data()

# Query parameter ile tab seçimi
# URL'de ?page=dashboard veya ?page=karsilastirma varsa Dashboard sekmesi açılır
query_params = st.query_params
default_tab = 0  # Varsayılan: Veri Girişi tab'ı

page_param = query_params.get("page", "")
if page_param in ["dashboard", "karsilastirma", "grafik", "grafikler"]:
    default_tab = 1  # Dashboard & Karşılaştırma tab'ı

# TAB isimleri
# TAB isimleri — Synapse sekme dili: düz ad, önünde hareketli simge
# (simgeler portal_tasarim.sekme_css; sıra portal_tasarim.SEKMELER ile aynı)
TAB_NAMES = [
    "Enerji Diyagramı",
    "Veri Girişi & Excel",
    "Dashboard & Karşılaştırma",
    "PDF Rapor",
    "Veri Görüntüleme",
    "Aylık Birleşik Rapor",
    "Tahmin & Trend",
]

with st.container(key="enerji_sekmeler"):
    tab_diyagram, tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs(TAB_NAMES)

# ══════════════════════════════════════════════════════════════════
# ENERJİ DİYAGRAMI — lokasyona özgü enerji topolojisi (şimdilik Maslak)
# Toplam değerler recalc() ile aynı mantık:
#   Toplam Şebeke      = ölçülen TRDP'lerin toplamı (alt sayaç yedeği YOK)
#   Hastane Genel Top. = Şebeke + Kojen Üretim
#   Çip %'leri Hastane Genel Toplam üzerinden hesaplanır.
# ══════════════════════════════════════════════════════════════════
ENERJI_TOPOLOJI = {
    "maslak": {
        "genel":   [("TRDP-1", "TRDP1_kWh"), ("TRDP-3", "TRDP3_kWh")],
        "mekanik": [("TRDP-2", "TRDP2_kWh"), ("TRDP-4", "TRDP4_kWh")],
        "kumeler": [
            ("MCC PANOLARI (SIEMENS)", "mcc", [
                ("2BK-D01", "MCC_2BK_D01_kWh"), ("2BK-D02", "MCC_2BK_D02_kWh"),
                ("4BK-E01", "MCC_4BK_E01_kWh"), ("4BK-E02", "MCC_4BK_E02_kWh"),
                ("4BK-F01", "MCC_4BK_F01_kWh"),
                ("CK-D01", "MCC_CK_D01_kWh"), ("CK-E01", "MCC_CK_E01_kWh"), ("CK-F01", "MCC_CK_F01_kWh"),
            ]),
            ("MCC PANOLARI (JANITZA)", "mcc", [
                ("MCC-1", "MCC1_kWh"), ("MCC-2", "MCC2_kWh"), ("MCC-3", "MCC3_kWh"),
                ("MCC-4", "MCC4_kWh"), ("MCC-5", "MCC5_kWh"), ("MCC-6", "MCC6_kWh"),
                ("MCC-7", "MCC7_kWh"),
            ]),
            ("SOĞUTMA KULELERİ", "sogutma", [
                ("KULE-01", "Kule1_kWh"), ("KULE-02", "Kule2_kWh"), ("KULE-03", "Kule3_kWh"),
            ]),
            ("CHILLER", "sogutma", [
                ("CH-1", "Chiller1_kWh"), ("CH-2", "Chiller2_kWh"), ("CH-3", "Chiller3_kWh"),
                ("CH-4", "Chiller4_kWh"), ("CH-5", "Chiller5_kWh"),
            ]),
        ],
    },
}


def _ed_num(v) -> str:
    """Türkçe binlik ayraç (1.234)."""
    try:
        return f"{float(v):,.0f}".replace(",", ".")
    except (TypeError, ValueError):
        return "—"


def _ed_val(row, col):
    """Satırdan sütun değerini al; yoksa/NaN ise None."""
    if row is None or col not in row.index:
        return None
    v = row.get(col)
    try:
        if v is None or pd.isna(v):
            return None
        return float(v)
    except (TypeError, ValueError):
        return None




def _enerji_diyagrami_render(df_kaynak, lok_id):
    topo = ENERJI_TOPOLOJI.get(lok_id)
    if topo is None:
        st.info("Bu lokasyon için enerji diyagramı henüz tanımlı değil. (Topoloji lokasyona özgüdür.)")
        return
    if df_kaynak is None or df_kaynak.empty:
        st.warning("Enerji verisi bulunamadı.")
        return

    # Tarih sütununu güvenle datetime'a çevir (load_data string bırakabiliyor)
    df_kaynak = df_kaynak.copy()
    df_kaynak["Tarih"] = pd.to_datetime(df_kaynak["Tarih"], errors="coerce")
    df_kaynak = df_kaynak.dropna(subset=["Tarih"])

    # EN YENİ GÜN ÜSTTE: liste en son günden başlayıp geriye iner; açılan
    # listede önce dünün verisi görünsün, en eski gün aşağıda kalsın.
    _tarihler = sorted(df_kaynak["Tarih"].dropna().dt.date.unique(), reverse=True)
    if not _tarihler:
        st.warning("Geçerli tarihli veri yok.")
        return

    # Selectbox — sadece veri olan günler (date_input min==max RangeError'ından kaçınır)
    _sec = st.selectbox(
        "📅 Gün", options=_tarihler, index=0,
        format_func=lambda d: d.strftime("%d.%m.%Y"), key="ed_tarih",
    )
    _gun_df = df_kaynak[df_kaynak["Tarih"].dt.date == _sec]
    if _gun_df.empty:
        st.warning(f"{_sec} için veri yok.")
        return
    row = _gun_df.iloc[-1]

    # ── Toplamlar ──
    bina_genel = sum((_ed_val(row, c) or 0) for _, c in topo["genel"])
    trdp2 = _ed_val(row, "TRDP2_kWh") or 0
    trdp4 = _ed_val(row, "TRDP4_kWh") or 0
    # Mekanik taraf YALNIZCA kendi trafolarından okunur. Alt sayaç (MCC/Chiller)
    # toplamı yedek olarak KULLANILMAZ: o sayaçlar kaynağa bakmadan tüketimi
    # ölçer, kojen çalışırken yükü kojen besler; şebekeye eklenip üstüne kojen
    # de toplanınca aynı enerji iki kez sayılıyordu (recalc() açıklaması).
    bina_mekanik = trdp2 + trdp4
    trafo_toplam = bina_genel + bina_mekanik
    # Kojen = Kojen-1..4 toplamı (recalc / enerji_hesap, 27.10.2026). Kojen OG
    # baradan trafolara karışık beslenir: dört trafo ölçülmüşse trafo toplamı
    # hastane geneli, şebeke = trafo − kojen. Eksik trafoda eski kural.
    kojen = _ed_val(row, "Kojen_Uretim_kWh") or 0
    if all((_ed_val(row, k) or 0) > 0 for k in _enerji_hesap.TRDP_KOLONLARI):
        hastane_genel = trafo_toplam
        sebeke = trafo_toplam - kojen
        _sebeke_lbl = "Şebeke (trafo − kojen)"
    else:
        sebeke = trafo_toplam
        hastane_genel = sebeke + kojen
        _sebeke_lbl = "Şebeke (TRDP 1-4)"
    # Kojen kırılımı: yalnız değeri olan kojenler (okunmayan uydurulmaz)
    _kojen_kirilim = " · ".join(
        f"K{_i} {_ed_num(_ed_val(row, f'Kojen{_i}_kWh'))}"
        for _i in range(1, 5) if (_ed_val(row, f"Kojen{_i}_kWh") or 0) > 0)

    def _pct(x):
        return f"%{(x / hastane_genel * 100):.1f}".replace(".", ",") if hastane_genel > 0 else "—"

    _dis_hava = _ed_val(row, "Dis_Hava_Sicakligi_C")
    _hava_html = (
        f"<span style='background:rgba(250,178,25,0.10);border:1px solid rgba(250,178,25,0.4);"
        f"border-radius:13px;padding:4px 12px;font-size:11px;color:#8a5a00;font-weight:600;'>"
        f"🌡 {_dis_hava:.1f}°C</span>" if _dis_hava is not None else ""
    )

    # ── Stil: Synapse kart dili (portal_tasarim / lokasyon Dashboard'u) ──
    # ID-kapsamlı sınıflar global 'p,span,div{color:!important}' kuralını yener.
    _ik = (lambda ad, b=18: _pt.ikon(ad, b)) if _pt else (lambda ad, b=18: "")
    _style = (
        "<style>"
        "#ed-root{position:relative;padding:2px 0 0;}"
        "#ed-root .layer{position:relative;z-index:1;}"
        "#ed-root .gcard{background:#ffffff;border:1px solid rgba(24,26,30,.10);border-radius:16px;"
        "box-shadow:0 1px 1px rgba(20,22,26,.05),0 10px 22px -12px rgba(20,22,26,.22);padding:16px 18px;}"
        "#ed-root .hbrand{display:flex;align-items:center;gap:8px;color:#133273!important;font-weight:700;"
        "letter-spacing:1.4px;font-size:12px;text-transform:uppercase;padding:4px 0 8px;"
        "border-bottom:1px solid rgba(24,26,30,.10);}"
        "#ed-root .hsub{color:#46536b!important;font-weight:500;letter-spacing:.3px;text-transform:none;font-size:10px;}"
        "#ed-root .hbrand .hsub{margin-left:auto;}"
        "#ed-root .chead{display:flex;align-items:center;justify-content:center;gap:7px;color:#46536b!important;"
        "font-size:10px;font-weight:600;letter-spacing:1.2px;text-transform:uppercase;}"
        "#ed-root .mainv{color:#133273!important;font-weight:800;font-size:40px;line-height:1.1;letter-spacing:-0.02em;}"
        "#ed-root .mainv .u{color:#46536b!important;font-size:13px;font-weight:500;letter-spacing:0;}"
        "#ed-root .bdlbl{display:flex;align-items:center;gap:6px;color:#46536b!important;font-size:10px;"
        "font-weight:600;letter-spacing:1px;text-transform:uppercase;}"
        "#ed-root .vblue{color:#4a3aa7!important;}"
        "#ed-root .vemr{color:#0ca30c!important;}"
        "#ed-root .sectitle{display:flex;align-items:center;gap:8px;color:#133273!important;font-size:12px;"
        "font-weight:700;letter-spacing:1.4px;text-transform:uppercase;}"
        "#ed-root .secval{color:#133273!important;font-size:24px;font-weight:700;letter-spacing:-0.02em;}"
        "#ed-root .secval .u{color:#46536b!important;font-size:10px;font-weight:500;}"
        "#ed-root .pcblue{color:#2a78d6!important;font-weight:700;}"
        "#ed-root .pcamber{color:#c98500!important;font-weight:700;}"
        "#ed-root .trdplbl{display:flex;align-items:center;gap:6px;color:#46536b!important;font-size:10px;"
        "font-weight:600;letter-spacing:1.2px;text-transform:uppercase;}"
        "#ed-root .trdpval{color:#133273!important;font-size:22px;font-weight:700;letter-spacing:-0.02em;}"
        "#ed-root .ptitle{display:flex;align-items:center;gap:7px;color:#133273!important;font-size:11px;"
        "font-weight:700;letter-spacing:1.3px;text-transform:uppercase;}"
        "#ed-root .bar{display:inline-block;width:4px;height:12px;border-radius:2px;vertical-align:middle;}"
        "#ed-root .bblue{background:#2a78d6;}#ed-root .bamber{background:#c98500;}"
        "#ed-root .cel{background:#fafaf8;border:1px solid rgba(24,26,30,.10);border-radius:12px;padding:9px 11px;"
        "transition:transform .2s,box-shadow .2s;}"
        "#ed-root .cel:hover{transform:translateY(-2px);box-shadow:0 10px 20px -14px rgba(19,50,115,.35);}"
        "#ed-root .cid{color:#46536b!important;font-size:10px;font-weight:600;letter-spacing:.8px;text-transform:uppercase;}"
        "#ed-root .cval{color:#133273!important;font-size:16px;font-weight:700;margin-top:1px;}"
        "#ed-root .cval .u{color:#46536b!important;font-size:9px;font-weight:500;}"
        "#ed-root .cpct{color:#c98500!important;font-weight:700;}"
        "#ed-root .cempty{opacity:0.55;}"
        "#ed-root .cempty .cval{color:#46536b!important;font-style:italic;font-size:11px;font-weight:400;}"
        "#ed-root .trdp{flex:1;background:#fafaf8;border:1px solid rgba(24,26,30,.10);border-left:3px solid var(--k);"
        "border-radius:12px;padding:12px 14px;display:flex;justify-content:space-between;align-items:center;"
        "transition:transform .2s,box-shadow .2s;}"
        "#ed-root .trdp:hover{transform:translateY(-2px);box-shadow:0 10px 20px -14px rgba(19,50,115,.35);}"
        "</style>"
    )

    # ── Cam-kart yardımcıları (row / hastane_genel / _pct kapsamından okur) ──
    def _cell(ad, col):
        d = _ed_val(row, col)
        if d is None:
            return (f"<div class='cel cempty'><div class='cid'>{ad}</div>"
                    "<div class='cval'>veri yok</div></div>")
        pct_txt = "%0" if d <= 0 else f"%{(d/hastane_genel*100):.1f}".replace(".", ",") if hastane_genel > 0 else "—"
        return (f"<div class='cel'><div class='cid'>{ad}</div>"
                f"<div class='cval'>{_ed_num(d)} <span class='u'>kWh</span></div>"
                f"<div class='cpct' style='font-size:11px;margin-top:2px;'>{pct_txt}</div></div>")

    def _trdp(ad, col, accent):
        pccls = "pcblue" if accent == "blue" else "pcamber"
        d = _ed_val(row, col)
        if d is None:
            val_txt, pct_txt = "veri yok", ""
        elif d <= 0:
            val_txt, pct_txt = "0", "%0"
        else:
            val_txt = _ed_num(d)
            pct_txt = f"%{(d/hastane_genel*100):.1f}".replace(".", ",") if hastane_genel > 0 else "—"
        _k = "#2a78d6" if accent == "blue" else "#c98500"
        return (f"<div class='trdp' style='--k:{_k};'>"
                f"<div><div class='trdplbl'>{_ik('trdp', 15)}{ad}</div>"
                f"<div class='{pccls}' style='font-size:11px;margin-top:4px;'>{pct_txt}</div></div>"
                f"<div class='trdpval'>{val_txt}</div></div>")

    def _panel(kume, barcls):
        if not kume:
            return ""
        ad, _simge, chips = kume
        grup = sum((_ed_val(row, c) or 0) for _, c in chips)
        cells = "".join(_cell(a, c) for a, c in chips)
        return ("<div class='gcard' style='margin-top:18px;'>"
                f"<div class='ptitle'><span class='bar {barcls}'></span>{_ik(_simge, 16)}{ad} — "
                f"<span class='cpct'>{_pct(grup)}</span></div>"
                "<div style='display:grid;grid-template-columns:repeat(auto-fill,minmax(106px,1fr));"
                f"gap:10px;margin-top:14px;'>{cells}</div></div>")

    def _section(title, total, accent, trdp_list, note="", simge=""):
        pccls = "pcblue" if accent == "blue" else "pcamber"
        cards = "".join(_trdp(a, c, accent) for a, c in trdp_list)
        return ("<div class='gcard'>"
                "<div style='display:flex;justify-content:space-between;align-items:flex-end;margin-bottom:18px;'>"
                f"<div class='sectitle'>{_ik(simge, 18) if simge else ''}{title}{note}</div>"
                "<div style='text-align:right;'>"
                f"<div class='secval'>{_ed_num(total)} <span class='u'>kWh</span></div>"
                f"<div class='{pccls}' style='font-size:12px;'>{_pct(total)}</div></div></div>"
                f"<div style='display:flex;gap:14px;'>{cards}</div></div>")
    # ── Küme eşlemesi (sol sütun: Siemens MCC + Kuleler · sağ sütun: Janitza MCC + Chiller) ──
    _mek_kaynak = "ölçülen TRDP-2/4" if (trdp2 > 0 and trdp4 > 0) else "alt sayaç toplamı"
    _km = {k[0]: k for k in topo["kumeler"]}
    _siemens = _km.get("MCC PANOLARI (SIEMENS)")
    _janitza = _km.get("MCC PANOLARI (JANITZA)")
    _kule = _km.get("SOĞUTMA KULELERİ")
    _chiller = _km.get("CHILLER")
    _date_txt = _sec.strftime("%d.%m.%Y")
    _hava_txt = f" · 🌡 {_dis_hava:.1f}°C" if _dis_hava is not None else ""

    html = _style + (
        "<div id='ed-root'>"
        "<div class='layer'>"
        # ── Üst bar ──
        "<div style='margin-bottom:18px;'>"
        f"<div class='hbrand'>{_ik('trdp', 16)}Enerji Diyagramı"
        f"<span class='hsub'>{_date_txt}{_hava_txt} · kWh/gün</span></div>"
        "</div>"
        # ── 1. Seviye: Hastane Genel Toplam çekirdeği ──
        "<div style='display:flex;justify-content:center;margin-bottom:22px;'>"
        "<div class='gcard' style='width:460px;text-align:center;'>"
        f"<div class='chead'>{_ik('enerji', 18)}Hastane Genel Toplam · Günlük</div>"
        f"<div class='mainv' style='margin:8px 0 14px;'>{_ed_num(hastane_genel)} <span class='u'>kWh</span></div>"
        "<div style='display:flex;justify-content:space-between;border-top:1px solid rgba(24,26,30,0.10);padding-top:16px;'>"
        f"<div style='text-align:left;'><div class='bdlbl'>{_ik('sebeke', 15)}{_sebeke_lbl}</div>"
        f"<div class='vblue' style='font-size:17px;font-weight:600;margin-top:3px;'>{_ed_num(sebeke)} "
        f"<span style='font-size:11px;'>{_pct(sebeke)}</span></div></div>"
        f"<div style='text-align:right;'><div class='bdlbl' style='justify-content:flex-end;'>{_ik('kojen', 15)}Kojen Üretim</div>"
        f"<div class='vemr' style='font-size:17px;font-weight:600;margin-top:3px;'>{_ed_num(kojen)} "
        f"<span style='font-size:11px;'>{_pct(kojen)}</span></div>"
        + (f"<div class='bdlbl' style='margin-top:3px;'>{_kojen_kirilim}</div>" if _kojen_kirilim else "")
        + "</div>"
        "</div></div></div>"
        # ── 2. Seviye: iki sütun ──
        "<div style='display:flex;gap:22px;align-items:flex-start;'>"
        # Sol sütun
        "<div style='flex:1;'>"
        + _section("Bina Genel Tüketim", bina_genel, "blue", topo["genel"], simge="trdp")
        + _panel(_siemens, "bblue")
        + _panel(_kule, "bblue")
        + "</div>"
        # Sağ sütun
        "<div style='flex:1;'>"
        + _section(
            "Bina Mekanik Tüketim", bina_mekanik, "amber", topo["mekanik"],
            note=f" <span class='hsub'>({_mek_kaynak})</span>", simge="mcc",
        )
        + _panel(_janitza, "bamber")
        + _panel(_chiller, "bamber")
        + "</div>"
        "</div>"
        # ── Açıklama ──
        "<div class='hsub' style='font-size:9px;margin-top:18px;letter-spacing:0;'>"
        "Mor = Şebeke · Yeşil = Kojen · Sarı = Hastane Genel Toplam'a oran · "
        "Birim: kWh/gün · TRDP-1/3/4 otomatik (Modbus) · TRDP-2 manuel girilir; "
        "ikisi birden ölçülene kadar mekanik kısım alt sayaç toplamından hesaplanır."
        "</div>"
        "</div></div>"
    )
    st.markdown(html, unsafe_allow_html=True)


with tab_diyagram:
    _ed_lok = _loc_mgr.get_active_location_id() if "_loc_mgr" in dir() else "maslak"
    _enerji_diyagrami_render(df, _ed_lok)

# ---------------- TAB 1 ----------------
with tab1:
    st.subheader("Günlük Veri Girişi (Tarih bazlı güncelle/ekle)")

    # ── Tarih seçici FORM DIŞINDA — değişince mevcut değerleri önyükler ──
    tarih = st.date_input("Tarih", value=date.today(), key="entry_tarih")

    # Tarih değişince: yeni tarihe ait verileri session_state'e açıkça yaz → rerun
    # NOT: Streamlit form widget'ları session_state'deki değeri value= parametresine
    #      tercih eder. Bu yüzden pop+rerun yetmez — açıkça doğru değeri set etmek gerek.
    if st.session_state.get("_prev_entry_tarih") != str(tarih):
        st.session_state["_prev_entry_tarih"] = str(tarih)

        _df_pre = load_data()
        _ex_pre = None
        if not _df_pre.empty:
            _m_pre = _df_pre[_df_pre["Tarih"] == tarih]
            if not _m_pre.empty:
                _ex_pre = _m_pre.iloc[-1]

        def _set_ss(key, col, default):
            if _ex_pre is not None:
                v = _ex_pre.get(col)
                try:
                    if v is not None and not pd.isna(v):
                        st.session_state[key] = type(default)(v)
                        return
                except Exception:
                    pass
            st.session_state[key] = default

        _set_ss("entry_dis_hava",         "Dis_Hava_Sicakligi_C",    0.0)
        _set_ss("entry_chiller_load_pct", "Chiller_Load_Percent",     0.0)
        _set_ss("entry_kar",              "Kar_Eritme_Aktif",         False)
        _set_ss("entry_ch_set",           "Chiller_Set_Temp_C",       6.5)
        _set_ss("entry_ch_count",         "Chiller_Adet",             0)
        _set_ss("entry_abs_count",        "Absorption_Chiller_Adet",  0)
        _set_ss("entry_kazan_count",      "Kazan_Adet",               0)
        _set_ss("entry_kojen_count",      "Kojen_Adet",               0)
        # Hava alanları BOŞ başlar (0 değil): kayıtta boş bırakılan alan yazılmaz,
        # lokasyonun internetten aldığı değer korunur. 0 °C / %0 nem yanlış veri olurdu.
        for _hk, _hc in _HAVA_FORM_ALANLARI:
            _hv = _ex_pre.get(_hc) if _ex_pre is not None else None
            try:
                st.session_state[_hk] = None if _hv is None or pd.isna(_hv) else float(_hv)
            except (TypeError, ValueError):
                st.session_state[_hk] = None
        _hd = _ex_pre.get("Hava_Durumu") if _ex_pre is not None else None
        st.session_state["entry_hava_durumu"] = _hd if isinstance(_hd, str) and _hd in _HAVA_DURUMLARI else ""
        _set_ss("entry_mas1_h",           "Mas1_Isitma_Temp",         0.0)
        _set_ss("entry_mas1_k",           "Mas1_Kazan_Temp",          0.0)
        _set_ss("entry_mas1_c",           "Mas1_Sogutma_Temp",        0.0)
        _set_ss("entry_mas2_h",           "Mas2_Isitma_Temp",         0.0)
        _set_ss("entry_mas2_k",           "Mas2_Kazan_Temp",          0.0)
        _set_ss("entry_mas2_c",           "Mas2_Sogutma_Temp",        0.0)
        _set_ss("entry_single_h",         "Isitma_Temp_C",            0.0)
        _set_ss("entry_single_k",         "Kazan_Temp_C",             0.0)
        _set_ss("entry_single_c",         "Sogutma_Temp_C",           0.0)
        _set_ss("entry_trdp1",            "TRDP1_kWh",                0.0)
        _set_ss("entry_trdp2",            "TRDP2_kWh",                0.0)
        _set_ss("entry_trdp3",            "TRDP3_kWh",                0.0)
        _set_ss("entry_trdp4",            "TRDP4_kWh",                0.0)
        _set_ss("entry_sebeke",           "Sebeke_Tuketim_kWh",       0.0)
        _set_ss("entry_kojen1",           "Kojen1_kWh",               0.0)
        _set_ss("entry_kojen2",           "Kojen2_kWh",               0.0)
        _set_ss("entry_kojen3",           "Kojen3_kWh",               0.0)
        _set_ss("entry_kojen4",           "Kojen4_kWh",               0.0)
        _set_ss("entry_su",               "Su_Tuketimi_m3",           0.0)
        _set_ss("entry_kazan_gaz",        "Kazan_Dogalgaz_m3",        0.0)
        _set_ss("entry_kojen_gaz",        "Kojen_Dogalgaz_m3",        0.0)
        _set_ss("entry_ch_kwh",           "Chiller_Tuketim_kWh",      0.0)
        _set_ss("entry_mcc_kwh",          "MCC_Tuketim_kWh",          0.0)
        _set_ss("entry_vrf_kwh",          "VRF_Split_Tuketim_kWh",    0.0)

        st.rerun()

    # Seçili tarih için mevcut satırı yükle (info mesajı ve _fv fallback için)
    _df_all = load_data()
    _ex = None
    if not _df_all.empty:
        _match = _df_all[_df_all["Tarih"] == tarih]
        if not _match.empty:
            _ex = _match.iloc[-1]
            _info_col, _del_col = st.columns([5, 1])
            with _info_col:
                st.info(
                    f"📋 **{tarih}** için kayıtlı veri bulundu — mevcut değerler önyüklendi. "
                    "Sadece değiştirmek istediğiniz alanları düzenleyip kaydedin."
                )
            with _del_col:
                if not st.session_state.get(f"_sil_onay_{tarih}"):
                    if st.button("🗑️ Sil", key=f"_sil_btn_{tarih}", help=f"{tarih} tarihli veriyi sil", use_container_width=True):
                        st.session_state[f"_sil_onay_{tarih}"] = True
                        st.rerun()
                else:
                    st.warning(f"**{tarih}** silinecek. Emin misin?")
                    _evet_col, _hayir_col = st.columns(2)
                    with _evet_col:
                        if st.button("✅ Evet", key=f"_sil_evet_{tarih}", use_container_width=True):
                            _df_silme = load_data()
                            _df_silme = _df_silme[_df_silme["Tarih"] != tarih]
                            persist_df(_df_silme)
                            st.session_state.pop(f"_sil_onay_{tarih}", None)
                            st.success(f"✅ {tarih} tarihi silindi.")
                            st.rerun()
                    with _hayir_col:
                        if st.button("❌ Hayır", key=f"_sil_hayir_{tarih}", use_container_width=True):
                            st.session_state.pop(f"_sil_onay_{tarih}", None)
                            st.rerun()

    def _fv(col, default):
        if _ex is None:
            return default
        v = _ex.get(col)
        try:
            if v is None or pd.isna(v):
                return default
        except Exception:
            pass
        try:
            return type(default)(v)
        except (ValueError, TypeError):
            return default

    with st.form("daily_entry_form", clear_on_submit=False):
        c1, c2, c3 = st.columns(3)

        with c1:
            dis_hava = st.number_input("Dış Hava Sıcaklığı (°C)", step=0.5, key="entry_dis_hava")
            chiller_load_pct = st.number_input("Chiller Çalışma Kapasitesi Yüzdesi (%)", step=1.0, min_value=0.0, max_value=100.0, key="entry_chiller_load_pct", help="Chiller kapasite yüzdesini girin; COP otomatik hesaplanır.")
            kar_eritme = st.checkbox("Kar Eritme Aktif (On/Off)", key="entry_kar")

        with c2:
            st.markdown("**Chiller / Kazan**")
            ch_set = st.number_input("Chiller Set Temp (°C)", step=0.5, key="entry_ch_set")
            st.caption(
                "💡 **Chiller Set Önerisi:** "
                "0–7°C → **8.0°C** | 7–23°C → **7.5°C** | 23–26°C → **7.0°C** | 26°C+ → **6.5°C**"
            )
            ch_count = st.number_input("Chiller Adet (Çalışan)", step=1, min_value=0, key="entry_ch_count")
            abs_count = st.number_input("Absorption Chiller Adet", step=1, min_value=0, key="entry_abs_count")
            kazan_count = st.number_input("Kazan Adet", step=1, min_value=0, key="entry_kazan_count")
            kojen_count = st.number_input("Kojen Adet (Çalışan)", step=1, min_value=0, max_value=4,
                                          key="entry_kojen_count",
                                          help="BACnet KOJEN-1..4 durumundan her sabah otomatik yazılır.")

        with c3:
            # Lokasyona göre sıcaklık alanları
            if _has_dual_lines:
                # Maslak: çift hat
                st.markdown("**Mas-1 / Mas-2 Sıcaklıkları**")
                mas1_h = st.number_input("Mas-1 Isıtma Temp", step=0.5, key="entry_mas1_h")
                mas1_k = st.number_input("Mas-1 Kazan Temp", step=0.5, key="entry_mas1_k")
                mas1_c = st.number_input("Mas-1 Soğutma Temp", step=0.5, key="entry_mas1_c")
                mas2_h = st.number_input("Mas-2 Isıtma Temp", step=0.5, key="entry_mas2_h")
                mas2_k = st.number_input("Mas-2 Kazan Temp", step=0.5, key="entry_mas2_k")
                mas2_c = st.number_input("Mas-2 Soğutma Temp", step=0.5, key="entry_mas2_c")
            else:
                # Altunizade vb.: tek hat
                _single_labels = _energy_schema.get("single_labels", {})
                st.markdown("**Sıcaklık Değerleri**")
                single_h = st.number_input(_single_labels.get("heating_temp", "Isıtma Temp"), step=0.5, key="entry_single_h")
                single_k = st.number_input(_single_labels.get("boiler_temp", "Kazan Temp"), step=0.5, key="entry_single_k")
                single_c = st.number_input(_single_labels.get("cooling_temp", "Soğutma Temp"), step=0.5, key="entry_single_c")

        st.divider()
        st.subheader("Hava Durumu")
        st.caption("Lokasyon bu alanları her sabah kendi konumunun internetteki günlük hava verisinden "
                   "doldurur; nem sensörü BACnet'ten gelir. Boş bırakılan alan kaydedilmez.")
        h1, h2, h3 = st.columns(3)
        with h1:
            hava_ort = st.number_input("Ortalama Sıcaklık (°C)", step=0.5, value=None, key="entry_hava_ort")
            hava_max = st.number_input("En Yüksek Sıcaklık (°C)", step=0.5, value=None, key="entry_hava_max")
            hava_min = st.number_input("En Düşük Sıcaklık (°C)", step=0.5, value=None, key="entry_hava_min")
        with h2:
            hava_nem = st.number_input("Ortalama Nem (%)", step=1.0, min_value=0.0, max_value=100.0,
                                       value=None, key="entry_hava_nem")
            nem_sensor = st.number_input("Dış Hava Nem Sensörü (%)", step=1.0, min_value=0.0, max_value=100.0,
                                         value=None, key="entry_nem_sensor")
            hava_yagis = st.number_input("Yağış (mm)", step=0.5, min_value=0.0, value=None, key="entry_hava_yagis")
        with h3:
            hava_bulut = st.number_input("Bulutluluk (%)", step=5.0, min_value=0.0, max_value=100.0,
                                         value=None, key="entry_hava_bulut")
            hava_rad = st.number_input("Güneş Radyasyonu (kWh/m²)", step=0.1, min_value=0.0, value=None,
                                       key="entry_hava_rad")
            hava_ruzgar = st.number_input("Ortalama Rüzgâr (km/sa)", step=0.5, min_value=0.0, value=None,
                                          key="entry_hava_ruzgar")
            hava_durumu = st.selectbox("Hava Durumu", _HAVA_DURUMLARI, key="entry_hava_durumu",
                                       format_func=lambda v: v.capitalize() if v else "—")

        st.divider()
        st.subheader("Tüketim / Üretim")

        a1, a2, a3, a4 = st.columns(4)
        with a1:
            st.markdown("**Trafo Tüketimleri (TRDP)**")
            trdp1 = st.number_input("TRDP-1 (kWh)", step=50.0, min_value=0.0, key="entry_trdp1")
            trdp2 = st.number_input("TRDP-2 (kWh)", step=50.0, min_value=0.0, key="entry_trdp2")
            trdp3 = st.number_input("TRDP-3 (kWh)", step=50.0, min_value=0.0, key="entry_trdp3")
            trdp4 = st.number_input("TRDP-4 (kWh)", step=50.0, min_value=0.0, key="entry_trdp4")
        with a2:
            # KOJEN-3/4 her sabah sayaçtan otomatik yazılır (data_bridge);
            # henüz bağlı olmayan kojenler buradan elle girilir.
            st.markdown("**Kojen Üretimleri**")
            koj1 = st.number_input("Kojen-1 Üretim (kWh)", step=50.0, min_value=0.0, key="entry_kojen1")
            koj2 = st.number_input("Kojen-2 Üretim (kWh)", step=50.0, min_value=0.0, key="entry_kojen2")
            koj3 = st.number_input("Kojen-3 Üretim (kWh)", step=50.0, min_value=0.0, key="entry_kojen3",
                                   help="Sayaçtan (PAC3200) her sabah otomatik yazılır.")
            koj4 = st.number_input("Kojen-4 Üretim (kWh)", step=50.0, min_value=0.0, key="entry_kojen4",
                                   help="Sayaçtan (PAC3200) her sabah otomatik yazılır.")
        with a3:
            st.markdown("**Doğalgaz / Su**")
            kazan_gaz = st.number_input("Kazan Doğalgaz (m³)", step=10.0, min_value=0.0, key="entry_kazan_gaz")
            koj_gaz = st.number_input("Kojen Doğalgaz (m³)", step=10.0, min_value=0.0, key="entry_kojen_gaz")
            su = st.number_input("Su Tüketimi (m³)", step=1.0, min_value=0.0, key="entry_su")
        with a4:
            st.markdown("**Alt Sayaçlar**")
            ch_kwh = st.number_input("Chiller Tüketim (kWh)", step=50.0, min_value=0.0, key="entry_ch_kwh")
            mcc_kwh = st.number_input("MCC Tüketim (kWh)", step=50.0, min_value=0.0, key="entry_mcc_kwh")
            vrf_kwh = st.number_input("VRF/Split Tüketim (kWh) (varsa)", step=25.0, min_value=0.0, key="entry_vrf_kwh")

        preview_bina_yuk = trdp1 + trdp3
        preview_mekanik = trdp2 + trdp4
        preview_total_cool = ch_kwh + vrf_kwh
        # Kural enerji_hesap.py'de (27.10.2026): Kojen = Kojen-1..4 toplamı
        # (hiçbiri girilmediyse eski elle girilmiş toplam); dört trafo varsa
        # Toplam = trafo toplamı, Şebeke = trafo − kojen. Önizleme aynı kuralı
        # aynı modülden hesaplar — kaydedilen değerle ayrışmasın.
        _on = _enerji_hesap.yeniden_hesapla(pd.DataFrame([{
            "TRDP1_kWh": trdp1, "TRDP2_kWh": trdp2, "TRDP3_kWh": trdp3, "TRDP4_kWh": trdp4,
            "Kojen1_kWh": koj1, "Kojen2_kWh": koj2, "Kojen3_kWh": koj3, "Kojen4_kWh": koj4,
            # Eski (elle girilmiş) toplam yalnız o gün kojen sayaçları hiç
            # yazılmamışsa korunur; sayaçlı günde hepsi 0'a çekilirse üretim 0'dır.
            "Kojen_Uretim_kWh": (_fv("Kojen_Uretim_kWh", 0.0)
                                 if not any(_fv("Kojen%d_kWh" % _i, 0.0) > 0 for _i in range(1, 5))
                                 else 0.0),
            "Sebeke_Tuketim_kWh": _fv("Sebeke_Tuketim_kWh", 0.0),
            "MCC_Tuketim_kWh": mcc_kwh, "Chiller_Tuketim_kWh": ch_kwh, "VRF_Split_Tuketim_kWh": vrf_kwh,
        }])).iloc[0]
        koj = float(_on["Kojen_Uretim_kWh"])
        sebeke = float(_on["Sebeke_Tuketim_kWh"])
        preview_total_h = float(_on["Toplam_Hastane_Tuketim_kWh"])
        trafo_toplam = trdp1 + trdp2 + trdp3 + trdp4
        _eksik = [a for a, v in (("TRDP-1", trdp1), ("TRDP-2", trdp2),
                                 ("TRDP-3", trdp3), ("TRDP-4", trdp4)) if v <= 0]
        mekanik_not = (" ⚠️ %s girilmedi — şebeke eksik ölçülüyor" % ", ".join(_eksik)) \
            if _eksik else ""
        _ihrac_not = " (eksi: şebekeye verildi)" if sebeke < 0 else ""
        preview_other = max(0.0, preview_mekanik - (ch_kwh + mcc_kwh))
        st.info(
            f"**Otomatik Hesap Önizleme:** "
            f"Trafo Toplamı = **{trafo_toplam:,.0f} kWh**{mekanik_not} | "
            f"Kojen Üretim (1-4) = **{koj:,.0f} kWh** | "
            f"Şebeke (trafo − kojen) = **{sebeke:,.0f} kWh**{_ihrac_not} | "
            f"Toplam Hastane (şebeke + kojen) = **{preview_total_h:,.0f} kWh** | "
            f"Bina Yükü (1+3) = **{preview_bina_yuk:,.0f} kWh** | "
            f"Mekanik (2+4) = **{preview_mekanik:,.0f} kWh** | "
            f"Toplam Soğutma = **{preview_total_cool:,.0f} kWh**"
        )

        _btn_col1, _btn_col2 = st.columns([1, 1])
        with _btn_col1:
            ok = st.form_submit_button("💾 Kaydet", use_container_width=True)
        with _btn_col2:
            gonder_ok = st.form_submit_button("🔄 Merkeze Gönder", use_container_width=True)

    if ok:
        try:
            # Yeni satırı hazırla
            new_row = {
                "Tarih": tarih,
                "Chiller_Set_Temp_C": ch_set,
                "Chiller_Adet": int(ch_count),
                "Absorption_Chiller_Adet": int(abs_count),
                "Kazan_Adet": int(kazan_count),
                "Kojen_Adet": int(kojen_count),
            }
            # Hava: yalnız DOLU alanlar yazılır — boş alan mevcut (internetten gelen) değeri korur
            for _sutun, _deger in (("Hava_Sicaklik_Ort_C", hava_ort), ("Hava_Sicaklik_Max_C", hava_max),
                                   ("Hava_Sicaklik_Min_C", hava_min), ("Hava_Nem_Ort_Yuzde", hava_nem),
                                   ("Dis_Hava_Nem_Yuzde", nem_sensor), ("Hava_Yagis_mm", hava_yagis),
                                   ("Hava_Bulut_Yuzde", hava_bulut), ("Hava_Gunes_Radyasyon_kWh_m2", hava_rad),
                                   ("Hava_Ruzgar_Ort_kmh", hava_ruzgar)):
                if _deger is not None:
                    new_row[_sutun] = float(_deger)
            if hava_durumu:
                new_row["Hava_Durumu"] = hava_durumu
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
                "TRDP1_kWh": trdp1,
                "TRDP2_kWh": trdp2,
                "TRDP3_kWh": trdp3,
                "TRDP4_kWh": trdp4,
                "Sebeke_Tuketim_kWh": sebeke,
                "Kojen_Uretim_kWh": koj,
                "Kojen1_kWh": koj1,
                "Kojen2_kWh": koj2,
                "Kojen3_kWh": koj3,
                "Kojen4_kWh": koj4,
                "Kazan_Dogalgaz_m3": kazan_gaz,
                "Kojen_Dogalgaz_m3": koj_gaz,
                "Su_Tuketimi_m3": su,
                "Chiller_Tuketim_kWh": ch_kwh,
                "MCC_Tuketim_kWh": mcc_kwh,
                "VRF_Split_Tuketim_kWh": vrf_kwh,
                "Dis_Hava_Sicakligi_C": dis_hava,
                "Chiller_Load_Percent": chiller_load_pct if chiller_load_pct > 0 else None,
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

    # ----- MERKEZE GÖNDER -----
    if gonder_ok:
        try:
            from cloud_sync import run_sync
            with st.spinner("📡 Senkronizasyon yapılıyor..."):
                success = run_sync()
            if success:
                st.success("✅ Veriler Merkeze başarıyla gönderildi!")
            else:
                st.warning("⚠️ Senkronizasyon ayarlanmamış (supabase_config.json)")
        except Exception as e:
            st.error(f"❌ Senkronizasyon hatası: {e}")

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
        _dl_col1, _dl_col2 = st.columns(2)
        with _dl_col1:
            st.download_button(
                "⬇️ CSV İndir",
                data=exp.to_csv(index=False).encode("utf-8"),
                file_name="energy_data_export.csv",
                mime="text/plain",
                key="btn_csv_export",
            )
        with _dl_col2:
            try:
                _xlsx_buf = io.BytesIO()
                with pd.ExcelWriter(_xlsx_buf, engine="xlsxwriter") as _writer:
                    exp.to_excel(_writer, index=False, sheet_name="Enerji Verisi")
                st.download_button(
                    "⬇️ Excel İndir (.xlsx)",
                    data=_xlsx_buf.getvalue(),
                    file_name="energy_data_export.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="btn_xlsx_export",
                )
            except Exception as _xe:
                st.warning(f"Excel butonu oluşturulamadı: {_xe}")

# ---------------- TAB 2 ----------------
with tab2:
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
                    critical_count = int(sayi(latest.get("Kritik_Sorun_Adet")))
                    warning_count = int(sayi(latest.get("Uyari_Adet")))
                    # Sağlık yüzdesinin paydası: o gün analiz edilen ünite sayısı.
                    # Eski rapor satırlarında bulgular ünite başına değil BULGU
                    # başına sayılmış (3+52+10=65 iken Toplam_AHU=55), o yüzden
                    # ikisinin büyüğü alınır.
                    unit_count = max(
                        int(sayi(latest.get("Toplam_AHU"))) + int(sayi(latest.get("Toplam_FCU"))),
                        critical_count + warning_count + int(sayi(latest.get("Optimal_Adet"))),
                    )
                else:
                    # Dün için HVAC verisi yok
                    critical_count = None
                    warning_count = None
                    unit_count = 0
            else:
                critical_count = None
                warning_count = None
                unit_count = 0
        except Exception:
            critical_count = None
            warning_count = None
            unit_count = 0

        # Sistem Sağlık Durumu — ÜNİTE SAYISINA ORANLI
        # Eskiden MUTLAK ceza vardı: her kritik -15, her uyarı -5. 55 AHU'luk
        # bir tesiste 20 uyarı puanı sıfıra indiriyordu; 22.10.2026'da kart
        # "%0 / Kritik" yazıyordu (3 kritik + 34 uyarı). Yani gösterge hep dipte
        # kalıp hiçbir şey anlatmıyordu. Artık sorunlu ünitelerin TOPLAMA ORANI
        # bakılıyor: kritik tam, uyarı 0,35 ağırlıkla sayılır.
        if critical_count is not None and warning_count is not None and unit_count > 0:
            _sorunlu = critical_count + warning_count * 0.35
            health_score = int(round(max(0.0, min(1.0, 1 - _sorunlu / unit_count)) * 100))

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
        
        # Kartları göster — Synapse lokasyon Dashboard'u dili (portal_tasarim)
        def _tr_sayi(v, ond=0):
            return f"{v:,.{ond}f}".replace(",", "X").replace(".", ",").replace("X", ".")

        def _gun_deger(col):
            if report_data.empty or col not in report_data.columns:
                return None
            _v = report_data.iloc[0].get(col)
            try:
                return None if _v is None or pd.isna(_v) else float(_v)
            except (TypeError, ValueError):
                return None

        _gun_txt = report_date.strftime('%d.%m.%Y')
        _pct_dun = None
        if not compare_data.empty and rep_total > 0:
            _ct = sayi(compare_data.iloc[0].get("Toplam_Hastane_Tuketim_kWh"))
            _pct_dun = ((rep_total - _ct) / _ct * 100) if _ct > 0 else None

        # ═══ 1. ÖZET (DÜN) ═══
        with st.container(key="kart_dun_ozeti"):
            st.markdown(_pt.bolum(f"Özet — {_gun_txt}", "enerji",
                                  "önceki güne göre" if _pct_dun is not None else ""),
                        unsafe_allow_html=True)
            if report_data.empty:
                st.info(f"📅 {_gun_txt} için henüz veri girilmedi.")
            else:
                _d_txt, _d_cls = _pt.degisim(_pct_dun, ters=True)   # tüketim artışı kötü haber
                if critical_count is not None:
                    _uy_txt, _uy_alt = f"{critical_count} / {warning_count}", "kritik / uyarı"
                else:
                    _uy_txt, _uy_alt = "—", "HVAC analizi yok"
                if health_score is not None:
                    _sg_txt = f"%{health_score}"
                    _sg_alt = (f"{health_status} · {unit_count} ünitenin "
                               f"{critical_count + warning_count}'inde bulgu")
                else:
                    _sg_txt, _sg_alt = "—", "Veri yok"
                st.markdown(_pt.izgara([
                    _pt.kart("enerji", "Dünkü Tüketim", _tr_sayi(rep_total), "kWh", _d_txt, _d_cls),
                    _pt.kart("sogutma", "Chiller Tüketimi", _tr_sayi(rep_chiller), "kWh"),
                    _pt.kart("dogalgaz", "Doğalgaz", _tr_sayi(rep_gas), "m³"),
                    _pt.kart("alarm", "Aktif Uyarılar", _uy_txt, "", _uy_alt),
                    _pt.kart("saglik", "Sistem Sağlığı", _sg_txt, "", _sg_alt),
                ]), unsafe_allow_html=True)

                # ═══ KOJEN & KAYNAK (aynı gün; ölçülmeyen kalem "—") ═══
                def _kk(simge, etiket, col, birim="kWh"):
                    _v = _gun_deger(col)
                    return _pt.kart(simge, etiket, _tr_sayi(_v) if _v is not None else "—",
                                    birim if _v is not None else "")
                st.markdown(_pt.bolum("Kojen & Kaynak", "kojen"), unsafe_allow_html=True)
                st.markdown(_pt.izgara([
                    _kk("sebeke", "Şebeke Tüketim", "Sebeke_Tuketim_kWh"),
                    _kk("kojen", "Kojen Üretim", "Kojen_Uretim_kWh"),
                    _kk("trdp", "TRDP-1 (Bina)", "TRDP1_kWh"),
                    _kk("trdp", "TRDP-2 (Mek.)", "TRDP2_kWh"),
                    _kk("trdp", "TRDP-3 (Bina)", "TRDP3_kWh"),
                    _kk("trdp", "TRDP-4 (Mek.)", "TRDP4_kWh"),
                    _kk("mcc", "MCC Tüketim", "MCC_Tuketim_kWh"),
                    _kk("kazan", "Kazan Doğalgaz", "Kazan_Dogalgaz_m3", "m³"),
                    _kk("dogalgaz", "Kojen Doğalgaz", "Kojen_Dogalgaz_m3", "m³"),
                    _kk("su", "Su Tüketimi", "Su_Tuketimi_m3", "m³"),
                ], 200), unsafe_allow_html=True)

        # Settings'i bir kez oku (m² bölümü için)
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
        
        # ═══ 2. m² BAŞINA TÜKETİM ═══
        if building_area and building_area > 0 and not report_data.empty:
            with st.container(key="kart_m2_tuketim"):
                st.markdown(_pt.bolum("m² Başına Tüketim", "verim",
                                      f"{_tr_sayi(building_area)} m²"), unsafe_allow_html=True)
                cooling_per_m2 = rep_chiller / building_area
                heating_per_m2 = rep_gas * 10.64 / building_area
                total_per_m2 = rep_total / building_area
                st.markdown(_pt.izgara([
                    _pt.kart("sogutma", "Soğutma", _tr_sayi(cooling_per_m2, 2), "kWh/m²"),
                    _pt.kart("kazan", "Isıtma", _tr_sayi(heating_per_m2, 2), "kWh/m²"),
                    _pt.kart("enerji", "Toplam Enerji", _tr_sayi(total_per_m2, 2), "kWh/m²"),
                ]), unsafe_allow_html=True)

        # ===== /GÜNLÜK ÖZET KARTLARI =====
        
        years = sorted({d.year for d in df["Tarih"].tolist()})

        # Dönem seçimi: ay + karşılaştırılacak ikinci ay (29.10.2026 — eski
        # "Grafik Aralığı" kaydırıcısı ve "Karşılaştırma modu" kaldırıldı)
        _AYLAR = ["Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
                  "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
        _son_dt = pd.to_datetime(max(df["Tarih"]))
        st.markdown(_pt.bolum("Dönem ve Karşılaştırma", "takvim", "seçilen ay ↔ karşılaştırılan ay"),
                    unsafe_allow_html=True)
        c1, c2, c3, c4, c5 = st.columns([1, 1, 1, 1, 1.4])
        with c1:
            sel_year = st.selectbox("Yıl", options=years, index=len(years) - 1, key="dash_year_select")
        with c2:
            sel_month = st.selectbox("Ay", options=list(range(1, 13)), index=_son_dt.month - 1,
                                     format_func=lambda m: _AYLAR[m - 1], key="dash_month_select")
        # Varsayılan karşılaştırma: geçen yılın aynı ayı
        _kyil = [y for y in years if y != int(sel_year)] or years
        _kvars = int(sel_year) - 1 if (int(sel_year) - 1) in years else _kyil[-1]
        with c3:
            cmp_year = st.selectbox("Karşılaştırılacak Yıl", options=years, index=years.index(_kvars),
                                    key="dash_cmp_year_select")
        with c4:
            cmp_month = st.selectbox("Karşılaştırılacak Ay", options=list(range(1, 13)), index=int(sel_month) - 1,
                                     format_func=lambda m: _AYLAR[m - 1], key="dash_cmp_month_select")
        with c5:
            view_mode = st.radio("Grafik detayı", ["Günlük", "Aylık", "Yıllık"], horizontal=True,
                                 key="dash_viewmode_radio")

        start, end = month_range(int(sel_year), int(sel_month))
        df_period = filter_range(df, start, end)
        yoy = yoy_month_compare(df, int(sel_year), int(sel_month), int(cmp_year), int(cmp_month))
        _kiyas_txt = (f"{_AYLAR[int(sel_month) - 1]} {sel_year} ↔ "
                      f"{_AYLAR[int(cmp_month) - 1]} {cmp_year}")

        def sumcol(dfx, col):
            return float(dfx[col].fillna(0).sum()) if not dfx.empty else 0.0

        total_h = sumcol(df_period, "Toplam_Hastane_Tuketim_kWh")
        total_grid = sumcol(df_period, "Sebeke_Tuketim_kWh")
        total_cool = sumcol(df_period, "Toplam_Sogutma_Tuketim_kWh")
        total_gas = sumcol(df_period, "Kazan_Dogalgaz_m3") + sumcol(df_period, "Kojen_Dogalgaz_m3")
        avg_temp = float(df_period["Dis_Hava_Sicakligi_C"].astype(float).mean()) if not df_period.empty else 0.0

        st.markdown(_pt.bolum("Dönem Özeti", "takvim", _kiyas_txt), unsafe_allow_html=True)

        def metric_yoy(col_key, simge, label, val, unit):
            # Hepsi tüketim kalemi: artış kırmızı ▲, azalış yeşil ▼ (ters=True)
            _txt, _cls = "", ""
            if yoy and col_key in yoy["metrics"]:
                cur_v, prev_v = yoy["metrics"][col_key]
                _txt, _cls = _pt.degisim(safe_pct_change(cur_v, prev_v), ters=True)
            return _pt.kart(simge, label, _tr_sayi(val), unit, _txt, _cls)

        st.markdown(_pt.izgara([
            metric_yoy("Toplam_Hastane_Tuketim_kWh", "enerji", "Toplam Hastane", total_h, "kWh"),
            metric_yoy("Sebeke_Tuketim_kWh", "sebeke", "Şebeke", total_grid, "kWh"),
            metric_yoy("Toplam_Sogutma_Tuketim_kWh", "sogutma", "Toplam Soğutma", total_cool, "kWh"),
            _pt.kart("dogalgaz", "Toplam Doğalgaz", _tr_sayi(total_gas), "m³"),
            # Dış hava o ay hiç girilmediyse ortalama NaN olur: "nan" yerine "—"
            _pt.kart("termometre", "Ortalama Dış Hava",
                     _tr_sayi(avg_temp, 1) if avg_temp == avg_temp else "—",
                     "°C" if avg_temp == avg_temp else ""),
        ]), unsafe_allow_html=True)

        st.markdown(_pt.bolum("Grafikler", "grafik"), unsafe_allow_html=True)

        df_chart = aggregate_for_view(df_period, view_mode)
        fig_line = chart_consumption_vs_temp(df_chart, view_mode)
        fig_stack = chart_stacked_breakdown(df_chart, view_mode)
        fig_bar = chart_month_vs_last_year(yoy, baslik=_kiyas_txt) if yoy else None

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

        st.markdown(_pt.bolum("Seçilen Dönem Verisi", "kayit"), unsafe_allow_html=True)
        render_styled_table(df_period.sort_values("Tarih"), table_key="dashboard")

# ---------------- TAB 3 ----------------
with tab3:
    st.subheader("PDF Rapor Üretici")
    df = load_data()
    if df.empty:
        st.warning("PDF rapor için veri gerekli.")
    else:
        st.caption("Grafikler PDF içinde matplotlib ile render edilir.")
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
        _fc1, _fc2 = st.columns(2)
        with _fc1:
            st.download_button(
                "⬇️ Filtreli CSV İndir",
                data=exp.to_csv(index=False).encode("utf-8"),
                file_name="energy_data_filtered.csv",
                mime="text/plain",
                key="view_export_filtered_btn",
            )
        with _fc2:
            try:
                _fxlsx_buf = io.BytesIO()
                with pd.ExcelWriter(_fxlsx_buf, engine="xlsxwriter") as _fwriter:
                    exp.to_excel(_fwriter, index=False, sheet_name="Filtreli Veri")
                st.download_button(
                    "⬇️ Filtreli Excel İndir (.xlsx)",
                    data=_fxlsx_buf.getvalue(),
                    file_name="energy_data_filtered.xlsx",
                    mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                    key="view_export_filtered_xlsx_btn",
                )
            except Exception as _fxe:
                st.warning(f"Excel butonu oluşturulamadı: {_fxe}")

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

                # ── Chiller KURAL 8 uyarısını enerji verisi üzerinden ekle ──
                try:
                    _edf = load_data()
                    if not _edf.empty and "Chiller_Load_Percent" in _edf.columns and "Dis_Hava_Sicakligi_C" in _edf.columns:
                        _edf["Tarih"] = pd.to_datetime(_edf["Tarih"], errors="coerce").dt.date
                        _edf_period = _edf[
                            (_edf["Tarih"] >= date(report_year, report_month, 1)) &
                            (_edf["Tarih"] < date(report_year + (report_month // 12), (report_month % 12) + 1, 1))
                        ]
                        _chiller_trigger = _edf_period[
                            (_edf_period["Dis_Hava_Sicakligi_C"].fillna(99) < 10) &
                            (_edf_period["Chiller_Load_Percent"].fillna(0) > 80)
                        ]
                        if not _chiller_trigger.empty:
                            _n = len(_chiller_trigger)
                            recommendations.append({
                                "name": "Mevsimsel Chiller Geçiş Uyarısı (KURAL 8)",
                                "severity": "WARNING",
                                "savings_potential": "Orta",
                                "message": (
                                    f"Bu dönemde {_n} gün; dış hava <10°C iken Chiller >%80 kapasitede çalışmıştır. "
                                    "Free-Cooling potansiyelini artırın ve 2. Chiller devreye alınmasını değerlendirin."
                                ),
                            })
                except Exception:
                    pass

                # ── Chiller Set Sıcaklık Önerisi (Dış Hava Aralığına Göre) ──
                try:
                    def _chiller_set_onerisi(dis_hava_c):
                        if dis_hava_c < 7:
                            return 8.0
                        elif dis_hava_c < 23:
                            return 7.5
                        elif dis_hava_c < 26:
                            return 7.0
                        else:
                            return 6.5

                    _edf2 = load_data()
                    if not _edf2.empty and "Dis_Hava_Sicakligi_C" in _edf2.columns and "Chiller_Set_Temp_C" in _edf2.columns:
                        _edf2["Tarih"] = pd.to_datetime(_edf2["Tarih"], errors="coerce").dt.date
                        _edf2_period = _edf2[
                            (_edf2["Tarih"] >= date(report_year, report_month, 1)) &
                            (_edf2["Tarih"] < date(report_year + (report_month // 12), (report_month % 12) + 1, 1))
                        ].dropna(subset=["Dis_Hava_Sicakligi_C", "Chiller_Set_Temp_C"])

                        if not _edf2_period.empty:
                            _avg_dis = _edf2_period["Dis_Hava_Sicakligi_C"].mean()
                            _avg_set = _edf2_period["Chiller_Set_Temp_C"].mean()
                            _onerilen = _chiller_set_onerisi(_avg_dis)
                            _fark = _avg_set - _onerilen  # pozitif → set fazla düşük, negatif → set fazla yüksek

                            if abs(_fark) >= 0.4:
                                _yon = "düşük" if _fark < 0 else "yüksek"
                                _severity = "CRITICAL" if abs(_fark) >= 1.0 else "WARNING"
                                recommendations.append({
                                    "name": "Chiller Set Sıcaklığı Optimizasyonu",
                                    "severity": _severity,
                                    "savings_potential": "Yüksek" if abs(_fark) >= 1.0 else "Orta",
                                    "message": (
                                        f"Bu dönemde ortalama dış hava sıcaklığı {_avg_dis:.1f}°C iken "
                                        f"ortalama chiller set sıcaklığı {_avg_set:.1f}°C olarak uygulanmış. "
                                        f"Dış hava aralığına göre önerilen set {_onerilen}°C'dir "
                                        f"(uygulanan değer {abs(_fark):.1f}°C {_yon} girişli). "
                                        "Chiller set sıcaklığını önerilen değere ayarlayarak enerji verimliliğini artırabilirsiniz."
                                    ),
                                })
                except Exception:
                    pass

                rec_summary = engine.get_recommendation_summary(recommendations)
                
                st.success(f"Analiz tamamlandı! {unified_data.get('days_with_data', 0)} gün veri işlendi.")
                
                # Özet göstergeler
                with _bolum_karti("kart_birlesik_ozet", "📊 Özet Göstergeler"):
                    summary = unified_data.get("summary", {})
                
                    m1, m2, m3, m4 = st.columns(4)
                    with m1:
                        val = summary.get("total_grid_consumption", 0)
                        yoy_grid = yoy_analysis.get("comparisons", {}).get("total_grid_consumption", {})
                        delta = f"{yoy_grid.get('change_percent', 0):+.1f}%" if yoy_grid.get('change_percent') else None
                        st.metric("Şebeke Tüketimi", f"{val:,.0f} kWh", delta, delta_color="inverse")
                    with m2:
                        val = summary.get("total_cooling_consumption", 0)
                        yoy_cool = yoy_analysis.get("comparisons", {}).get("total_cooling_consumption", {})
                        delta = f"{yoy_cool.get('change_percent', 0):+.1f}%" if yoy_cool.get('change_percent') else None
                        st.metric("Soğutma Tüketimi", f"{val:,.0f} kWh", delta, delta_color="inverse")
                    with m3:
                        val = summary.get("total_gas", 0)
                        yoy_gas = yoy_analysis.get("comparisons", {}).get("total_gas", {})
                        delta = f"{yoy_gas.get('change_percent', 0):+.1f}%" if yoy_gas.get('change_percent') else None
                        st.metric("Toplam Doğalgaz", f"{val:,.0f} m³", delta, delta_color="inverse")
                    with m4:
                        chiller_set = summary.get("avg_chiller_set_temp")
                        if chiller_set:
                            yoy_ch = yoy_analysis.get("comparisons", {}).get("avg_chiller_set_temp", {})
                            delta = f"{yoy_ch.get('change_percent', 0):+.1f}%" if yoy_ch.get('change_percent') else None
                            st.metric("Ort. Chiller Set", f"{chiller_set:.1f}°C", delta, delta_color="off")
                        else:
                            st.metric("Ort. Chiller Set", "Veri yok")
                
                
                # ═══ TAHMİN VE TREND ANALİZİ ═══
                try:
                    # Tahmin/sapma ileriye dönük günlük modelden (H-04)
                    forecast_data = _durust_tahmin_verisi(report_year)
                    
                    yearly = forecast_data.get("yearly_summary", [])
                    monthly_fc = forecast_data.get("monthly_forecast", [])
                    savings = forecast_data.get("savings", {})
                    next_m = forecast_data.get("next_month", {})
                    b_area = forecast_data.get("building_area", 0)
                    
                    # 1. Çok Yıllık Trend
                    if yearly and len(yearly) >= 2:
                        with _bolum_karti("kart_rapor_coklu_yil", "📈 Cok Yillik Trend Analizi"):
                        
                            yc = st.columns(len(yearly))
                            for idx, ys in enumerate(yearly):
                                with yc[idx]:
                                    metrik_notlu(
                                        f"{ys['year']} ({ys['days']} gun)",
                                        f"{ys['total_kwh']:,.0f} kWh".replace(",", "."),
                                        f"{ys['kwh_per_m2']:.1f} kWh/m2" if b_area > 0 else None,
                                    )
                        
                            # Yıllar arası değişim
                            if len(yearly) >= 2:
                                trend_cols = st.columns(3)
                                last_y = yearly[-1]
                                prev_y = yearly[-2]
                            
                                with trend_cols[0]:
                                    chg = (last_y['total_kwh'] - prev_y['total_kwh']) / prev_y['total_kwh'] * 100 if prev_y['total_kwh'] > 0 else 0
                                    metrik_notlu("Toplam Degisim", f"{chg:+.1f}%",
                                                 f"{prev_y['year']}->{last_y['year']}")
                                with trend_cols[1]:
                                    chg_g = (last_y['grid_kwh'] - prev_y['grid_kwh']) / prev_y['grid_kwh'] * 100 if prev_y['grid_kwh'] > 0 else 0
                                    metrik_notlu("Sebeke Degisim", f"{chg_g:+.1f}%",
                                                 f"{prev_y['year']}->{last_y['year']}")
                                with trend_cols[2]:
                                    chg_c = (last_y['chiller_kwh'] - prev_y['chiller_kwh']) / prev_y['chiller_kwh'] * 100 if prev_y['chiller_kwh'] > 0 else 0
                                    metrik_notlu("Chiller Degisim", f"{chg_c:+.1f}%",
                                                 f"{prev_y['year']}->{last_y['year']}")
                        
                    
                    # 2. Aylık Tahmin Tablosu
                    if monthly_fc:
                        with _bolum_karti("kart_rapor_aylik_tahmin", f"🔮 {report_year} Aylik Tuketim Tahmini"):
                            # Kıyas yılı yoksa (motor 0 döndürür) "0 (kWh)" başlıklı
                            # boş sütunlar basılmaz — Tahmin & Trend ile aynı kural.
                            _kiyas5 = bool(monthly_fc[0].get("prev_year")) and bool(monthly_fc[0].get("last_year"))
                            if _kiyas5:
                                st.caption("Onceki yillar arasi trende gore konservatif projeksiyon")
                                _py5 = str(monthly_fc[0]['prev_year'])
                                _ly5 = str(monthly_fc[0]['last_year'])
                                _md5 = f"| Ay | {_py5} (kWh) | {_ly5} (kWh) | Trend | Tahmin (kWh) | Gerceklesen | Sapma |\n"
                                _md5 += "|:---|---:|---:|:---:|---:|---:|:---:|\n"
                            else:
                                st.caption("Kiyas sutunlari yok: trend icin en az iki TAM yil "
                                           "(yilda 300+ gunluk veri) gerekiyor.")
                                _md5 = "| Ay | Tahmin (kWh) | Gerceklesen | Sapma |\n"
                                _md5 += "|:---|---:|---:|:---:|\n"

                            for fc in monthly_fc:
                                _gc5 = "-"
                                _sp5 = "-"
                                if fc["actual_total"] is not None:
                                    _gc5 = f"{fc['actual_total']:,.0f}".replace(",", ".")
                                    if fc.get("is_partial"):
                                        _gc5 += f" ({fc['actual_days']}g)"
                                    _sp5 = f"{fc['deviation_total_pct']:+.1f}%" if fc.get("deviation_total_pct") is not None else "-"

                                if _kiyas5:
                                    _md5 += f"| {fc['month_name']} | {fc['prev_total']:,.0f} | {fc['last_total']:,.0f} | {fc['trend_total_pct']:+.1f}% | {fc['forecast_total']:,.0f} | {_gc5} | {_sp5} |\n".replace(",", ".")
                                else:
                                    _md5 += f"| {fc['month_name']} | {fc['forecast_total']:,.0f} | {_gc5} | {_sp5} |\n".replace(",", ".")
                        
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
                        
                    
                    # 3. Tasarruf Özeti
                    if savings and savings.get("savings_total_kwh") is not None:
                        with _bolum_karti("kart_tasarruf_rapor", "📉 Beklenen vs Gerceklesen Tasarruf"):
                            st.caption(f"Alan artisina ragmen tuketim degisimi ({savings.get('prev_year', '')}->{savings.get('year', '')})")
                        
                            sv_cols = st.columns(4)
                            with sv_cols[0]:
                                metrik_notlu("Beklenen Tuketim",
                                             f"{savings['expected_total']:,.0f} kWh".replace(",", "."),
                                             "(alan bazli)")
                            with sv_cols[1]:
                                st.metric("Gerceklesen",
                                          f"{savings['curr_total']:,.0f} kWh".replace(",", "."))
                            with sv_cols[2]:
                                # TASARRUF tüketimin tersidir: artı tasarruf iyi haber,
                                # yani yukarı ok YEŞİL kalır (Streamlit varsayılanı).
                                st.metric("Toplam Tasarruf",
                                          f"{savings['savings_total_kwh']:,.0f} kWh".replace(",", "."),
                                          f"%{savings['savings_total_pct']:.1f}")
                            with sv_cols[3]:
                                st.metric("Sebeke Tasarruf",
                                          f"{savings['savings_grid_kwh']:,.0f} kWh".replace(",", "."),
                                          f"%{savings['savings_grid_pct']:.1f}")
                        
                    
                    # 4. Gelecek Ay Tahmini
                    if next_m:
                        with _bolum_karti("kart_gelecek_ay_rapor", f"🎯 Gelecek Ay Tahmini: {next_m.get('month_name', '')} {next_m.get('year', '')}"):
                            nm_cols = st.columns(3)
                            with nm_cols[0]:
                                _mtt = next_m.get('trend_total_pct', 0) or 0
                                st.metric("Beklenen Toplam",
                                          f"{next_m.get('forecast_total', 0):,.0f} kWh".replace(",", "."),
                                          f"Trend: {_mtt:+.1f}%",
                                          delta_color="inverse" if abs(_mtt) >= 0.05 else "off")
                            with nm_cols[1]:
                                _mtg = next_m.get('trend_grid_pct', 0) or 0
                                st.metric("Beklenen Sebeke",
                                          f"{next_m.get('forecast_grid', 0):,.0f} kWh".replace(",", "."),
                                          f"Trend: {_mtg:+.1f}%",
                                          delta_color="inverse" if abs(_mtg) >= 0.05 else "off")
                            with nm_cols[2]:
                                if b_area > 0:
                                    st.metric("Beklenen kWh/m2",
                                              f"{next_m.get('per_m2', 0):.1f} kWh/m2")
                        
                
                except Exception as _fc_err:
                    st.warning(f"Tahmin modülü hatası: {_fc_err}")
                
                # Tasarruf önerileri
                with _bolum_karti("kart_oneriler", f"⚠️ Tasarruf Önerileri ({rec_summary['total_count']} öneri)"):
                
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
                
                
                # PDF indirme
                with _bolum_karti("kart_pdf_indir", "📥 PDF Rapor İndir"):
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
                                               color_discrete_sequence=['#6da7ec', '#c98500', '#0ca30c', '#46536b'])
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
                                    marker_color='rgba(109,167,236, 0.7)'
                                ))
                                # Sıcaklık (Çizgi - 2. Eksen)
                                fig_trend.add_trace(go.Scatter(
                                    x=daily_df["Gün"], y=daily_df["Sıcaklık"],
                                    name="Dış Hava (°C)",
                                    yaxis="y2",
                                    line=dict(color='#d03b3b', width=3)
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
                                marker_color='#0ca30c'
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
                            _fc_data = _durust_tahmin_verisi(report_year)
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
    with _bolum_karti("kart_ai_ilerleme", "🧠 Yapay Zeka / Makine Öğrenmesi İlerleme"):
    
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
                        _ring_color = "#0ca30c"
                    elif _ai_score >= 60:
                        _ring_color = "#6da7ec"
                    elif _ai_score >= 40:
                        _ring_color = "#c98500"
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
    
    with _bolum_karti("kart_ml_egitim", "🤖 ML Eğitim Verisi Durumu"):
    
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
        from monthly_report.forecast_engine import AYLAR

        _fc_col1, _fc_col2 = st.columns([1, 3])
        with _fc_col1:
            _fc_year = st.selectbox("Tahmin Yılı", options=list(range(2024, 2028)), index=2, key="forecast_year_select")

        _fc_eng = _get_forecast_engine()
        _fc_result = _fc_eng.full_analysis(_fc_year)
        
        _fc_yearly = _fc_result.get("yearly_summary", [])
        _fc_monthly = _fc_result.get("monthly_forecast", [])
        _fc_savings = _fc_result.get("savings", {})
        _fc_next = _fc_result.get("next_month", {})
        _fc_area = _fc_result.get("building_area", 0)
        
        # ═══ 1. ÇOK YILLIK TREND ═══
        if _fc_yearly and len(_fc_yearly) >= 2:
            with _bolum_karti("kart_tahmin_coklu_yil", "📈 Çok Yıllık Trend Analizi"):
            
                _yc = st.columns(len(_fc_yearly))
                for _yi, _ys in enumerate(_fc_yearly):
                    with _yc[_yi]:
                        metrik_notlu(
                            f"{_ys['year']} ({_ys['days']} gün)",
                            f"{_ys['total_kwh']:,.0f} kWh".replace(",", "."),
                            f"{_ys['kwh_per_m2']:.1f} kWh/m²" if _fc_area > 0 else None,
                        )
            
                _tc = st.columns(3)
                _ly = _fc_yearly[-1]
                _py = _fc_yearly[-2]
                with _tc[0]:
                    _ct = (_ly['total_kwh'] - _py['total_kwh']) / _py['total_kwh'] * 100 if _py['total_kwh'] > 0 else 0
                    metrik_notlu("Toplam Değişim", f"{_ct:+.1f}%", f"{_py['year']}→{_ly['year']}")
                with _tc[1]:
                    _cg = (_ly['grid_kwh'] - _py['grid_kwh']) / _py['grid_kwh'] * 100 if _py['grid_kwh'] > 0 else 0
                    metrik_notlu("Şebeke Değişim", f"{_cg:+.1f}%", f"{_py['year']}→{_ly['year']}")
                with _tc[2]:
                    _cc = (_ly['chiller_kwh'] - _py['chiller_kwh']) / _py['chiller_kwh'] * 100 if _py['chiller_kwh'] > 0 else 0
                    metrik_notlu("Chiller Değişim", f"{_cc:+.1f}%", f"{_py['year']}→{_ly['year']}")
            
        
        # ═══ 2. AYLIK TAHMİN TABLOSU ═══
        if _fc_monthly:
            with _bolum_karti("kart_tahmin_aylik", f"🔮 {_fc_year} Aylık Tüketim Tahmini"):
                # Kıyas yılları YOKSA (en az iki TAM yıl veri gerekir) motor
                # prev_year/last_year'ı 0 döndürüyor; tablo "0 (kWh)" başlıklı
                # sıfır dolu sütunlar gösteriyordu — ne olduğu anlaşılmıyordu.
                # Böyle durumda o sütunlar hiç basılmaz, sebebi yazılır.
                _kiyas_var = bool(_fc_monthly[0].get("prev_year")) and bool(_fc_monthly[0].get("last_year"))
                if _kiyas_var:
                    st.caption("Önceki yıllar arası trende göre konservatif projeksiyon")
                    _prev_y = str(_fc_monthly[0]['prev_year'])
                    _last_y = str(_fc_monthly[0]['last_year'])
                    _md = f"| Ay | {_prev_y} (kWh) | {_last_y} (kWh) | Trend | Tahmin (kWh) | Gerçekleşen | Sapma (eğitim içi) |\n"
                    _md += "|:---|---:|---:|:---:|---:|---:|:---:|\n"
                else:
                    st.caption("Kıyas sütunları yok: trend için en az iki TAM yıl "
                               "(yılda 300+ günlük veri) gerekiyor. Tahmin ML modelinden geliyor.")
                    _md = "| Ay | Tahmin (kWh) | Gerçekleşen | Sapma (eğitim içi) |\n"
                    _md += "|:---|---:|---:|:---:|\n"

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

                    if _kiyas_var:
                        _md += f"| {_ay} | {_p} | {_l} | {_tr} | {_th} | {_gc} | {_sp} |\n"
                    else:
                        _md += f"| {_ay} | {_th} | {_gc} | {_sp} |\n"

                st.markdown(_md)
                st.caption("Bu tablodaki sapma, modelin eğitimde gördüğü aylarla hesaplanır; "
                           "gerçek tahmin başarısını göstermez. Ölçülmüş başarı için aşağıdaki "
                           "Günlük Model kartına bakın.")
            
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

        # ═══ 2b. GÜNLÜK MODEL (YENİ) ═══
        # Eski modelin yanında, kıyaslanabilsin diye. Yukarıdaki "Sapma" modelin
        # eğitimde gördüğü aylarla kıyaslanıyor; burada her geçmiş ay yalnız o
        # aydan ÖNCEKİ veriyle tahmin edilir — sapma gerçek başarıyı gösterir.
        with _bolum_karti("kart_tahmin_gunluk_model", "🧪 Günlük Model Tahmini (yeni)",
                          "Hava + takvim + kojen planı; geçmiş aylar ileriye dönük sınanır"):
            _gm_hedefler = {"toplam": "Toplam tüketim", "sogutma": "Soğutma (chiller kWh)",
                            "isitma_gaz": "Isıtma gazı (kazan m³)"}
            _gm_hedef = st.radio("Tahmin edilen", list(_gm_hedefler), format_func=_gm_hedefler.get,
                                 horizontal=True, key="gm_hedef")
            try:
                with st.spinner("Günlük model hesaplanıyor..."):
                    _gm = _gunluk_model_ozeti(int(_fc_year), _gm_hedef, _veri_imzasi())
            except Exception as _gm_e:
                _gm = {"hata": f"Model çalıştırılamadı: {type(_gm_e).__name__}: {_gm_e}"}
            if _gm.get("hata"):
                st.info(_gm["hata"])
            else:
                _gb = _gm["birim"]
                # Ay NUMARASIYLA eşlenir: eski motor adları ASCII yazıyor ("Subat", "Mayis")
                _eski = {f["month"]: f["forecast_total"] for f in (_fc_monthly or [])} \
                    if _gm_hedef == "toplam" else {}
                _sayi = lambda v: "-" if v is None else f"{v:,.0f}".replace(",", ".")
                if _eski:
                    _gmd = f"| Ay | Mevcut model ({_gb}) | Yeni model ({_gb}) | Gerçekleşen | Yeni model sapması |\n"
                    _gmd += "|:---|---:|---:|---:|:---:|\n"
                else:
                    _gmd = f"| Ay | Yeni model ({_gb}) | Gerçekleşen | Sapma |\n|:---|---:|---:|:---:|\n"
                for _a in _gm["aylar"]:
                    _gc = _sayi(_a["gercek"])
                    if _a["gercek"] is not None and _a["not"]:
                        _gc += f" ({_a['not']})"
                    elif _a["gercek"] is None and _a["not"]:
                        _gc = _a["not"]
                    _sp = f"{_a['sapma']:+.1f}%" if _a["sapma"] is not None else "-"
                    if _eski:
                        _gmd += f"| {_a['ad']} | {_sayi(_eski.get(_a['ay']))} | {_sayi(_a['tahmin'])} | {_gc} | {_sp} |\n"
                    else:
                        _gmd += f"| {_a['ad']} | {_sayi(_a['tahmin'])} | {_gc} | {_sp} |\n"
                st.markdown(_gmd)
                st.caption("Sapma = (gerçekleşen − tahmin) / tahmin. Yalnız verisi tam ve temiz aylar "
                           "ölçülür; hariç tutulan dönemler configs/tuketim_tahmin.json'da. "
                           f"Son veri: {_gm['son_veri']}.")

                _go = _gm.get("olcut")
                if _go:
                    _gk = st.columns(4)
                    with _gk[0]:
                        metrik_notlu("Ortalama sapma", f"%{_go['MAPE']:.1f}".replace(".", ","),
                                     f"{_go['n']} ay, mutlak")
                    with _gk[1]:
                        metrik_notlu("Net sapma", f"%{_go['NMBE']:+.1f}".replace(".", ","),
                                     "yıl toplamında (NMBE)")
                    with _gk[2]:
                        _gkt = max((a for a in _gm["aylar"] if a["sapma"] is not None),
                                   key=lambda a: abs(a["sapma"]))
                        metrik_notlu("En kötü ay", f"%{_go['en_kotu']:.1f}".replace(".", ","), _gkt["ad"])
                    with _gk[3]:
                        metrik_notlu("ASHRAE G14", "Geçer" if _go["ashrae_g14"] else "Kalır",
                                     "NMBE ±%5, CV(RMSE) ≤%15")

                # Gelecek ay + kojen planı (yalnız toplamda: şebeke = tüketim − GES − kojen)
                if _gm_hedef == "toplam":
                    _bugun = pd.Timestamp.today()
                    _gy, _ga = (_bugun.year + 1, 1) if _bugun.month == 12 else (_bugun.year, _bugun.month + 1)
                    from tuketim_tahmin.portal_ozet import AYLAR as _GM_AYLAR
                    st.markdown(f"**Gelecek ay: {_GM_AYLAR[_ga - 1]} {_gy}**")
                    _kg = st.number_input("Kojen planı: bu ay kaç gün çalışacak? (boş = son 90 günün düzeni)",
                                          min_value=0, max_value=31, value=None, step=1, key="gm_kojen_gun")
                    try:
                        _gt = _gunluk_model_gelecek_ay(_gy, _ga, None if _kg is None else int(_kg), _veri_imzasi())
                        _gn = st.columns(3)
                        with _gn[0]:
                            metrik_notlu("Beklenen toplam", f"{_sayi(float(_gt['tuketim']))} kWh",
                                         "ort. hava " + f"{_gt['ort_sicaklik']:.1f} °C".replace(".", ","))
                        with _gn[1]:
                            metrik_notlu("Kojen", f"{_sayi(float(_gt['kojen']))} kWh",
                                         "plan" if _gt["kojen_kaynak"] != "varsayim" else "son 90 günün düzeni")
                        with _gn[2]:
                            metrik_notlu("Beklenen şebeke", f"{_sayi(float(_gt['sebeke']))} kWh",
                                         "toplam − GES − kojen")
                    except Exception as _gt_e:
                        st.info(f"Gelecek ay hesaplanamadı: {type(_gt_e).__name__}")

                if _gm.get("kalite"):
                    with st.expander(f"Veri kalitesi: {len(_gm['kalite'])} bulgu (modele girmeyen günler)"):
                        for _b in _gm["kalite"][:60]:
                            st.markdown(f"- **{_b['tur']}** {_b['bas']} → {_b['son']} ({_b['gun']} gün): {_b['aciklama']}")


        # ═══ 3. TASARRUF ÖZETİ ═══
        if _fc_savings and _fc_savings.get("savings_total_kwh") is not None:
            with _bolum_karti("kart_tasarruf_ozeti", "📉 Beklenen vs Gerçekleşen Tasarruf"):
                st.caption(f"Alan artışına rağmen tüketim değişimi ({_fc_savings.get('prev_year', '')}→{_fc_savings.get('year', '')})")
            
                _sv = st.columns(4)
                with _sv[0]:
                    metrik_notlu("Beklenen Tüketim", f"{_fc_savings['expected_total']:,.0f} kWh".replace(",", "."),
                                 "(alan bazlı)")
                with _sv[1]:
                    st.metric("Gerçekleşen", f"{_fc_savings['curr_total']:,.0f} kWh".replace(",", "."))
                with _sv[2]:
                    # TASARRUF tüketimin tersidir: artı tasarruf iyi haber, yukarı ok
                    # YEŞİL kalır (Streamlit varsayılanı) — tüketim kartlarının tersi.
                    st.metric("Toplam Tasarruf", f"{_fc_savings['savings_total_kwh']:,.0f} kWh".replace(",", "."),
                              f"%{_fc_savings['savings_total_pct']:.1f}")
                with _sv[3]:
                    st.metric("Şebeke Tasarruf", f"{_fc_savings['savings_grid_kwh']:,.0f} kWh".replace(",", "."),
                              f"%{_fc_savings['savings_grid_pct']:.1f}")
            
        
        # ═══ 4. GELECEK AY TAHMİNİ ═══
        if _fc_next:
            with _bolum_karti("kart_gelecek_ay", f"🎯 Gelecek Ay Tahmini: {_fc_next.get('month_name', '')} {_fc_next.get('year', '')}"):
                _method = _fc_next.get("method", "trend")
                _method_label = "🤖 ML Model" if _method == "ml" else "📊 Trend"
                st.caption(f"Tahmin yöntemi: {_method_label}")
                _nm = st.columns(3)
                with _nm[0]:
                    _ntt = _fc_next.get('trend_total_pct', 0) or 0
                    # Trend sıfırsa (kıyas yılı yoksa öyle olur) ok anlam taşımasın
                    st.metric("Beklenen Toplam", f"{_fc_next.get('forecast_total', 0):,.0f} kWh".replace(",", "."),
                              f"Trend: {_ntt:+.1f}%",
                              delta_color="inverse" if abs(_ntt) >= 0.05 else "off")
                with _nm[1]:
                    _ntg = _fc_next.get('trend_grid_pct', 0) or 0
                    st.metric("Beklenen Şebeke", f"{_fc_next.get('forecast_grid', 0):,.0f} kWh".replace(",", "."),
                              f"Trend: {_ntg:+.1f}%",
                              delta_color="inverse" if abs(_ntg) >= 0.05 else "off")
                with _nm[2]:
                    if _fc_area > 0:
                        st.metric("Beklenen kWh/m²", f"{_fc_next.get('per_m2', 0):.1f} kWh/m²")
            
                # Ortalama koşullar (ML tahmini ise)
                if "avg_conditions" in _fc_next:
                    _ac = _fc_next["avg_conditions"]
                    st.caption(f"Baz koşullar: Dış hava {_ac.get('dis_hava', '-')}°C | Chiller set {_ac.get('chiller_set', '-')}°C | Chiller {_ac.get('chiller_adet', '-')} adet | Kazan {_ac.get('kazan_adet', '-')} adet")
        
        
        # ═══ 5. ML MODEL BİLGİLERİ ═══
        _model_info = _fc_result.get("model_info", {})
        with _bolum_karti("kart_ml_model", "🤖 ML Model Durumu"):
        
            if _model_info.get("is_trained"):
                _mi = st.columns(4)
                with _mi[0]:
                    _r2t = _model_info.get("r2_total", 0)
                    _quality = "Mükemmel" if _r2t > 0.9 else "İyi" if _r2t > 0.7 else "Orta" if _r2t > 0.5 else "Gelişiyor"
                    metrik_notlu("Toplam R² Skoru", f"{_r2t:.3f}", _quality)
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
                    # ÇUBUK NEDEN HTML: eskiden satırlar dolu blok karakteri
                    # int(oran*50) kere yazılarak çiziliyordu. İki yanlışı vardı:
                    #   1) %72,9 olan satır 36 blok yazıp tabloyu kaplayan dev
                    #      bir lacivert slab oluyordu (23.10.2026 ekran görüntüsü),
                    #   2) %2'nin altındaki satırlarda int(oran*50)=0 çıkıp
                    #      HİÇ çubuk basılmıyordu — "etki yok" gibi görünüyordu.
                    # Artık her satır kendi izinde orantılı çiziliyor; en küçük
                    # değer bile min-width ile 3 px görünür kalıyor.
                    _fi_sorted = sorted(_fi.items(), key=lambda x: x[1], reverse=True)
                    _fi_enb = max((v for _, v in _fi_sorted), default=0) or 1
                    _fi_satir = ""
                    for _fname, _fval in _fi_sorted:
                        _label = _fi_labels.get(_fname, _fname)
                        _gen = _fval / _fi_enb * 100.0
                        _fi_satir += (
                            "<div class='fi-satir'>"
                            f"<span class='fi-ad'>{_label}</span>"
                            "<span class='fi-iz'>"
                            f"<span class='fi-dolgu' style='width:{_gen:.1f}%'></span>"
                            "</span>"
                            f"<span class='fi-oran'>{_fval*100:.1f}%</span>"
                            "</div>"
                        )
                    st.markdown(
                        "<style>"
                        ".fi-liste{display:flex;flex-direction:column;gap:6px;margin:6px 0 2px;max-width:760px;}"
                        ".fi-satir{display:grid;grid-template-columns:minmax(120px,max-content)"
                        " minmax(0,1fr) 48px;align-items:center;gap:10px;}"
                        ".fi-ad{font-size:0.86rem;color:#24324d;white-space:nowrap;}"
                        ".fi-iz{height:10px;border-radius:6px;background:rgba(19,50,115,0.08);"
                        "overflow:hidden;}"
                        # min-width: %0,2'lik parametre bile 3 px görünür kalsın,
                        # ama oranlar yüzdeyle verildiği için birbirinden ayrılsın.
                        ".fi-dolgu{display:block;height:100%;border-radius:6px;min-width:3px;"
                        "background:linear-gradient(90deg,#2a78d6,#133273);}"
                        ".fi-oran{font-size:0.82rem;color:#4a5a78;text-align:right;"
                        "font-variant-numeric:tabular-nums;}"
                        "</style>"
                        f"<div class='fi-liste'>{_fi_satir}</div>",
                        unsafe_allow_html=True,
                    )
            
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
        
        
        # ═══ 6. SENARYO TAHMİNİ ═══
        with _bolum_karti("kart_senaryo", "🎛️ Senaryo Tahmini"):
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
