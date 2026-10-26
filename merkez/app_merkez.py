# app_merkez.py
# Acıbadem Genel Merkez — Tek Sayfa Komuta Merkezi
# Harita ortada, widget'lar etrafında — Koyu Mavi / Neon
# v: 2026-05-27

from __future__ import annotations
import os, json, logging
import numpy as np
import streamlit as st
import streamlit.components.v1 as _components
import pandas as pd
import plotly.graph_objects as go
from datetime import datetime, timedelta

st.set_page_config(
    page_title="ACIBADEM-SYNAPSE",
    page_icon="🏥",
    layout="wide",
    initial_sidebar_state="collapsed",
)

# İzleyici (salt okunur) oturumlarında veritabanına yazmayı en alt katmanda
# engeller — bkz. salt_okuma.py. Diğer modüller içe aktarılmadan ÖNCE kurulur.
import salt_okuma as _salt_okuma
_salt_okuma.kur()

from streamlit_autorefresh import st_autorefresh
# Otomatik yenileme yalnızca GİRİŞ YAPILMIŞ portal ekranlarında çalışır.
#   - QR bakım sayfasında: form doldurulurken sıfırlanmasın
#   - Giriş ekranında: 10 sn'de bir yenileme, yazılan kullanıcı adı/parolayı
#     siler ve girişi imkânsız hale getirirdi
#   - Karşılaştırma sayfasında (demo VE canlı): detay penceresi açıkken 10 sn'lik
#     yenileme pencereyi kapatıyordu. Sayfa dönem toplamlarını gösteriyor,
#     10 saniyede bir tazelenmesine zaten gerek yok.
#   - OTO SET pop-up'ı açıkken: modal pencere yenilemede kapanıyor, saat
#     girilirken kullanıcının elinden kayıyordu. Pop-up açıkken yenileme
#     durur (kapatınca tekrar başlar).
#   - Lokasyon detayı açıkken (demo VE canlı, 25.10.2026): Canlı İzleme
#     kendi bloğunu kendisi yeniler. 1,5-3 sn süren tam sayfa yenilemesi
#     hem o akışı her 10 sn'de durduruyor hem de bu sırada yapılan
#     tıklamaları (sekme, Geri) bekletiyordu — geçişler geç açılıyordu.
#     Detaydaki diğer veriler günlük; tam yenilemeye gerek yok.
if ("bakim" not in st.query_params and st.session_state.get("giris_ok")
        and not st.session_state.get("detay_ozet")
        and not st.session_state.get("_oto_popup")
        and not st.session_state.get("detay_lokasyon")):
    st_autorefresh(interval=10000, key="autorefresh")  # 10 saniye

# ============ CSS ============
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700;800&display=swap');

/* ── TİPOGRAFİ ──
   Kurumsal tek aile: Inter. Rakamlar tabular (tnum) — tablolarda ve
   kartlarda alt alta hizalanır, para/kWh değerleri zıplamaz. */
html, body, [data-testid="stAppViewContainer"], .stApp, button, input, select, textarea {
    font-family: Inter,system-ui,-apple-system,Segoe UI,sans-serif !important;
    font-feature-settings: "tnum" 1, "cv05" 1;
    -webkit-font-smoothing: antialiased;
    text-rendering: optimizeLegibility;
}
h1,h2,h3,h4,h5,h6 { letter-spacing:-0.02em !important; font-weight:650 !important; }

html, body, [data-testid="stAppViewContainer"] {
    background-color: #ecebe8 !important;
    background-image: none !important;
}
[data-testid="stAppViewContainer"] {
    background-color: #ecebe8 !important;
    background-image: none !important;
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

/* Harita iframe tam ekran */
[data-testid="column"]:nth-child(2) iframe {
    position: fixed !important;
    top: 0 !important; left: 0 !important;
    width: 100vw !important; height: 100vh !important;
    z-index: 1 !important; border: none !important;
}

/* TABLET DÜZENİ (641–1180px, ör. iPad dikey/yatay) — üç kolon yan yana
   sığmıyor: sol/sağ kartlar ~180px'e düşüp kesiliyor, OTO SET yazıları
   dikey kırılıyordu. Bu aralıkta harita en üste tam genişlikte alınır,
   lokasyon kolonu ile sağ kolon altında yan yana durur.
   (640px altını Streamlit zaten alt alta diziyor.) Ana düzen bloğu,
   sol kolondaki .ana-duzen-isaret işaretinden bulunur. */
@media (min-width: 641px) and (max-width: 1180px) {
    [data-testid="stHorizontalBlock"]:has(.ana-duzen-isaret) {
        flex-wrap: wrap !important;
        row-gap: 0.75rem !important;
    }
    [data-testid="stHorizontalBlock"]:has(.ana-duzen-isaret) > div {
        flex: 1 1 calc(50% - 1rem) !important;
        width: calc(50% - 1rem) !important;
        min-width: 0 !important;
    }
    [data-testid="stHorizontalBlock"]:has(.ana-duzen-isaret) > div:nth-child(2) {
        order: -1;
        flex-basis: 100% !important;
        width: 100% !important;
    }
    /* Yalnızca HARİTA çerçevesi (data: adresli); aynı kolondaki 0 px'lik
       yardımcı bileşenler (canlı değer iletici) büyütülmez. */
    [data-testid="stHorizontalBlock"]:has(.ana-duzen-isaret) > div:nth-child(2) iframe[src^="data:"],
    [data-testid="stHorizontalBlock"]:has(.ana-duzen-isaret) > div:nth-child(2)
        [data-testid="stElementContainer"]:has(> iframe[src^="data:"]) {
        height: 62vh !important;
        min-height: 420px !important;
        flex: 0 0 auto !important;   /* Streamlit kabı 900px flex-basis veriyor */
    }
    /* Yarım genişlikte iki kart yan yana sığmıyor → tek sütun */
    .lok-scroll { grid-template-columns: 1fr !important; }
}

/* Tüm yazılar — lokasyon detay sayfası (st.container(key="detay_gecis_katmani") içinde inline exec ile çalışıyor) kendi renklerini korusun */
h1:not(.st-key-detay_gecis_katmani *),h2:not(.st-key-detay_gecis_katmani *),h3:not(.st-key-detay_gecis_katmani *),h4:not(.st-key-detay_gecis_katmani *),h5:not(.st-key-detay_gecis_katmani *),h6:not(.st-key-detay_gecis_katmani *) { color: #0f1f3d !important; font-family: Inter,system-ui,-apple-system,Segoe UI,sans-serif !important; font-weight: 650 !important; }
p:not(.st-key-detay_gecis_katmani *), span:not(.st-key-detay_gecis_katmani *), div:not(.st-key-detay_gecis_katmani *), label:not(.st-key-detay_gecis_katmani *) { color: #0f1f3d !important; font-family: Inter,system-ui,-apple-system,Segoe UI,sans-serif !important; }

/* Streamlit Material ikon istisnası — _arrow_right gibi ikonların bozulmaması için */
span[data-testid="stIconMaterial"],
[data-testid="stExpanderToggleIcon"] span,
button span[data-testid="stIconMaterial"] {
    font-family: 'Material Symbols Rounded' !important;
    color: inherit !important;
}

/* Metrik */
[data-testid="stMetricValue"]  { color: #2a78d6 !important; font-size: 22px !important; font-weight: 800 !important; font-family: Inter,system-ui,-apple-system,Segoe UI,sans-serif !important;  }
[data-testid="stMetricLabel"]  { color:#46536b !important; font-size: 10px !important; letter-spacing: 1px !important; text-transform: uppercase !important; }
[data-testid="stMetricDelta"]  { color: #0ca30c !important; }
[data-testid="metric-container"] {
    background:#fafaf8 !important;
    !important;
    border: 1px solid rgba(24,26,30,0.10) !important;
    border-radius: 8px !important;
    padding: 12px !important;
    box-shadow: none !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 3px; }
::-webkit-scrollbar-track { background: #f1f0ed; }
::-webkit-scrollbar-thumb { background: rgba(19,50,115,0.3); border-radius: 3px; }

/* Neon kart */
.nk {
    background: #fafaf8;
    border: 1px solid rgba(24,26,30,0.10);
    border-radius: 14px;
    padding: 14px;
    margin-bottom: 10px;
    box-shadow: 0 1px 1px rgba(20,22,26,.05),0 10px 22px -12px rgba(20,22,26,.22),inset 0 1px 0 rgba(255,255,255,.95);
}
.nk-green { border-color:rgb(12,163,12) !important; }
.nk-red   { border-color:rgb(208,59,59) !important; }
.nk-gray  { border-color:#133273 !important; opacity: 0.65; }
/* Lokasyon kartı çerçevesi lokasyonun KENDİ renginde (durum noktası ayrı) */
.nk.lok-kart, .nk.lok-kart:hover { border:1.5px solid var(--lokrenk, #133273) !important;
    box-shadow:0 0 0 1px color-mix(in srgb, var(--lokrenk, #133273) 12%, transparent),
               0 10px 20px -16px var(--lokrenk, #133273) !important; }
.nk {
    display: block !important;
    text-decoration: none !important;
    cursor: pointer;
    transition: border-color 0.2s, transform 0.15s;
}
.nk:hover { transform: translateY(-2px); border-color: #133273 !important; box-shadow: 0 2px 4px rgba(19,50,115,.06),0 14px 30px -16px rgba(19,50,115,.28); }

.lok-scroll {
    max-height: 492px;
    overflow-y: auto;
    overflow-x: hidden;
    padding-right: 3px;
    scrollbar-width: thin;
    scrollbar-color:#133273 rgba(243,246,251,0.6);
    display: grid;
    /* Sığdığı kadar sütun: yakınlaştırınca / dar ekranda TEK sıraya iner,
       kartlar kesilip kaybolmaz */
    grid-template-columns: repeat(auto-fill, minmax(178px, 1fr));
    gap: 10px;
}
.lok-scroll .nk { margin-bottom: 0 !important; }
.lok-scroll::-webkit-scrollbar { width: 4px; }
.lok-scroll::-webkit-scrollbar-track { background: rgba(243,246,251,0.6); border-radius: 2px; }
.lok-scroll::-webkit-scrollbar-thumb { background: rgba(19,50,115,0.28); border-radius: 2px; }
.lok-scroll::-webkit-scrollbar-thumb:hover { background: rgba(19,50,115,0.55); }

.sec { font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif; font-size:10px; color:#133273;
       letter-spacing:2px; text-transform:uppercase; border-bottom:1px solid rgba(24,26,30,0.10);
       padding-bottom:5px; margin-bottom:10px; }

.alrt-r { background:rgba(208,59,59,0.12); border:1px solid rgba(208,59,59,0.35);
           border-radius:8px; padding:7px 10px; margin:3px 0; font-size:11px; color:#b42525 !important; }
.alrt-y { background:rgba(250,178,25,0.12); border:1px solid rgba(250,178,25,0.35);
           border-radius:8px; padding:7px 10px; margin:3px 0; font-size:11px; color:#8a5a00 !important; }
.alrt-g { background:rgba(12,163,12,0.12); border:1px solid rgba(12,163,12,0.35);
           border-radius:8px; padding:7px 10px; margin:3px 0; font-size:11px; color:#006300 !important; }

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
      0 0 10px rgba(19,50,115,0.4),
      0 0 25px rgba(19,50,115,0.2),
      0 0 50px rgba(19,50,115,0.08);
    opacity: 0.82;
  }
  50% {
    text-shadow:
      0 0 20px rgba(19,50,115,1),
      0 0 45px rgba(19,50,115,0.7),
      0 0 90px rgba(19,50,115,0.35),
      0 0 140px rgba(19,50,115,0.15);
    opacity: 1;
  }
}
@keyframes neon-breathe-sub {
  0%, 100% { opacity: 0.35; letter-spacing: 4px; }
  50%       { opacity: 0.65; letter-spacing: 3.2px; }
}

.btn-refresh button {
    background: rgba(14, 165, 233, 0.15) !important;
    color: #2a78d6 !important; border: 1px solid rgba(14, 165, 233, 0.3) !important;
    border-radius: 6px !important; font-size: 11px !important;
    padding: 4px 12px !important; font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif,sans-serif !important;
}
.btn-refresh button:hover {
    background: rgba(14, 165, 233, 0.25) !important;
    color: #ffffff !important;
}

/* Alarm expander */
[data-testid="stExpander"] {
    background:#fafaf8 !important;
    border: 1px solid rgba(24,26,30,0.10) !important;
    border-radius: 8px !important;
    margin-bottom: 5px !important;
}
[data-testid="stExpander"]:has(.alrt-exp-r) {
    border-color:rgb(208,59,59) !important;
    background: rgba(208,59,59,0.05) !important;
}
[data-testid="stExpander"]:has(.alrt-exp-y) {
    border-color:rgb(250,178,25) !important;
    background: rgba(250,178,25,0.04) !important;
}
[data-testid="stExpanderToggleIcon"] { color:#133273 !important; }
.alrt-detay-r {
    background: rgba(208,59,59,0.10); border-left: 3px solid #d03b3b;
    border-radius: 6px; padding: 8px 12px; margin: 4px 0;
    font-size: 12px; color: #b42525 !important;
}
.alrt-detay-y {
    background: rgba(250,178,25,0.10); border-left: 3px solid #c98500;
    border-radius: 6px; padding: 8px 12px; margin: 4px 0;
    font-size: 12px; color: #8a5a00 !important;
}
.alarm-detay-kart {
    background: rgba(0,0,0,0.25);
    border: 1px solid rgba(24,26,30,0.10);
    border-radius: 8px; padding: 10px 14px; margin-top: 8px;
}
.btn-goto button {
    background: rgba(14, 165, 233, 0.15) !important;
    color: #2a78d6 !important;
    border: 1px solid rgba(14, 165, 233, 0.3) !important;
    border-radius: 6px !important;
    font-size: 11px !important;
    padding: 4px 14px !important;
    width: 100% !important;
}
.btn-goto button:hover { background: rgba(14, 165, 233, 0.25) !important; color: #ffffff !important; }
</style>
""", unsafe_allow_html=True)


# Animasyonlu simgeler: tek kaynak (ikonlar.py) — ana ekran ve Dashboard aynı
import ikonlar as _ik
if getattr(_ik, "SURUM", 0) < 4:          # yayın sonrası eski modül önbellekte kalmasın
    import importlib as _il_ik
    _ik = _il_ik.reload(_ik)
st.markdown(_ik.CSS, unsafe_allow_html=True)

# ============ SABİT VERİ ============
HASTANELER = {
    # ── İstanbul ──
    "maslak":       {"isim": "Acıbadem Maslak",        "kisa": "MASLAK",        "lat": 41.1273, "lon": 29.0246, "m2": 15000, "renk": "#2a78d6"},
    "altunizade":   {"isim": "Acıbadem Altunizade",    "kisa": "ALTUNİZADE",    "lat": 41.0189, "lon": 29.0458, "m2": 10000, "renk": "#c98500"},
    "kozyatagi":    {"isim": "Acıbadem Kozyatağı",     "kisa": "KOZYATAĞİ",    "lat": 40.9766, "lon": 29.0928, "m2": 12000, "renk": "#0ca30c"},
    "taksim":       {"isim": "Acıbadem Taksim",        "kisa": "TAKSİM",        "lat": 41.0417, "lon": 28.9827, "m2":  8000, "renk": "#4a3aa7"},
    "atakent":      {"isim": "Acıbadem Atakent",       "kisa": "ATAKENT",       "lat": 41.0349, "lon": 28.7789, "m2": 20000, "renk": "#eb6834"},
    "atasehir":     {"isim": "Acıbadem Ataşehir",      "kisa": "ATAŞEHİR",      "lat": 40.9934, "lon": 29.1213, "m2": 14000, "renk": "#256abf"},
    "bakirkoy":     {"isim": "Acıbadem Bakırköy",      "kisa": "BAKIRKÖY",      "lat": 40.9776, "lon": 28.8731, "m2": 12000, "renk": "#84cc16"},
    "fulya":        {"isim": "Acıbadem Fulya",         "kisa": "FULYA",         "lat": 41.0557, "lon": 28.9994, "m2":  9000, "renk": "#e87ba4"},
    "international":{"isim": "Acıbadem International", "kisa": "INTERNAT.",     "lat": 40.9590, "lon": 28.8354, "m2": 18000, "renk": "#14b8a6"},
    "kadikoy":      {"isim": "Acıbadem Kadıköy",       "kisa": "KADİKÖY",       "lat": 41.0072, "lon": 29.0429, "m2":  8000, "renk": "#ec4899"},
    "kartal":       {"isim": "Acıbadem Kartal",        "kisa": "KARTAL",        "lat": 40.8860, "lon": 29.2041, "m2": 11000, "renk": "#d03b3b"},
    # ── Ankara ──
    "ankara":         {"isim": "Acıbadem Ankara",          "kisa": "ANKARA",       "lat": 39.9179, "lon": 32.8626, "m2": 16000, "renk": "#fb7185"},
    "bayindir":       {"isim": "Acıbadem Bayındır Söğütözü","kisa": "BAYINDIR",    "lat": 39.8980, "lon": 32.8240, "m2": 12000, "renk": "#f43f5e"},
    # ── Bursa ──
    "bursa":          {"isim": "Acıbadem Bursa",            "kisa": "BURSA",        "lat": 40.2090, "lon": 28.9790, "m2": 13000, "renk": "#c98500"},
    # ── Kocaeli ──
    "kocaeli":        {"isim": "Acıbadem Kocaeli",          "kisa": "KOCAELİ",      "lat": 40.7654, "lon": 29.9408, "m2": 10000, "renk": "#0ca30c"},
    # ── Eskişehir ──
    "eskisehir":      {"isim": "Acıbadem Eskişehir",        "kisa": "ESKİŞEHİR",    "lat": 39.7767, "lon": 30.5206, "m2":  9000, "renk": "#818cf8"},
    # ── İzmir ──
    "izmir":          {"isim": "Acıbadem İzmir Kent",       "kisa": "İZMİR",        "lat": 38.4192, "lon": 27.1287, "m2": 15000, "renk": "#2a78d6"},
    # ── Kayseri ──
    "kayseri":        {"isim": "Acıbadem Kayseri",          "kisa": "KAYSERİ",      "lat": 38.7225, "lon": 35.4875, "m2": 11000, "renk": "#a78bfa"},
    # ── Adana ──
    "adana":          {"isim": "Acıbadem Adana",            "kisa": "ADANA",        "lat": 37.0000, "lon": 35.3213, "m2": 12000, "renk": "#f472b6"},
    "adana_ortopedia":{"isim": "Acıbadem Adana Ortopedia",  "kisa": "ADANA ORT.",   "lat": 37.0100, "lon": 35.3350, "m2":  5000, "renk": "#e87ba4"},
    # ── Muğla / Bodrum ──
    "bodrum":         {"isim": "Acıbadem Bodrum",           "kisa": "BODRUM",       "lat": 37.0344, "lon": 27.4305, "m2":  7000, "renk": "#2dd4bf"},
}

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "configs", "merkez_config.json")

# ── SUNUM haritası: Genel Müdürlük (Ataşehir) + lokasyonlardan gelen akan oklar ──
# Harita HTML'ine YALNIZCA demo modunda eklenir. Düz metin (f-string değil):
# süslü parantezler tek yazılır. Oklar kendi Leaflet panesinde, işaretçilerin
# ALTINDA çizilir; kaydırmada/yakınlaştırmada yeniden hesaplanır.
_SALDIRI_JS = r"""
// ══ SUNUM: GENEL MÜDÜRLÜK + SALDIRI OKLARI (yalnız demo) ══
(function () {
  var GM_ID = 'atasehir';
  var GM = hospitals.filter(function (h) { return h.id === GM_ID; })[0];
  if (!GM) return;
  var NS = 'http://www.w3.org/2000/svg';
  // Haritadaki lokasyon durum renkleriyle AYNI (Python: d_renk)
  var RENK = { 'Çevrimiçi': '#0ca30c', 'Çevrimdışı': '#d03b3b', 'Kurulmadı': '#6b7280' };
  var azHareket = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  var gmRenk = RENK['Çevrimiçi'];

  var css = document.createElement('style');
  css.textContent =
    '.sd-taban{fill:none;stroke-width:2;stroke-linecap:round;opacity:.55}' +
    '.sd-akis{fill:none;stroke-width:2;stroke-linecap:round;stroke-dasharray:2 11;animation:sdAkis 1.1s linear infinite;opacity:.95}' +
    '.sd-akis.hizli{animation-duration:.6s}' +
    '.sd-kuyruk{fill:none;stroke-width:3.4;stroke-linecap:round}' +
    '.sd-ok{filter:drop-shadow(0 0 4px currentColor)}' +
    '.sd-grup{filter:drop-shadow(0 0 3px currentColor)}' +
    '@keyframes sdAkis{to{stroke-dashoffset:-26}}' +
    '@keyframes sdHalka{0%{transform:scale(.35);opacity:.75}100%{transform:scale(2.3);opacity:0}}' +
    '@keyframes sdBina{0%,100%{transform:translateY(0)}50%{transform:translateY(-2px)}}' +
    '@keyframes sdPencere{0%,100%{opacity:.35}50%{opacity:1}}' +
    '.gm-kap{position:relative;width:64px;height:78px;pointer-events:auto}' +
    '.gm-halka{position:absolute;left:12px;top:30px;width:40px;height:40px;border-radius:50%;' +
      'border:2px solid ' + gmRenk + ';animation:sdHalka 2.4s ease-out infinite}' +
    '.gm-halka.h2{animation-delay:.8s}.gm-halka.h3{animation-delay:1.6s}' +
    '.gm-bina{position:absolute;left:16px;top:6px;width:32px;height:44px;animation:sdBina 3s ease-in-out infinite;' +
      'filter:drop-shadow(0 2px 4px rgba(19,50,115,.35)) drop-shadow(0 0 8px ' + gmRenk + '66)}' +
    '.gm-bina .pc{animation:sdPencere 2.2s ease-in-out infinite}' +
    '.gm-bina .pc.g1{animation-delay:.4s}.gm-bina .pc.g2{animation-delay:.9s}.gm-bina .pc.g3{animation-delay:1.4s}' +
    '.gm-etiket{position:absolute;left:50%;top:54px;transform:translateX(-50%);white-space:nowrap;' +
      'font:800 8px Inter,system-ui,sans-serif;letter-spacing:1.4px;color:#133273;background:rgba(250,250,248,.92);' +
      'border:1px solid ' + gmRenk + ';border-radius:6px;padding:2px 6px;box-shadow:0 0 8px ' + gmRenk + '55}' +
    '.sd-lejant{position:absolute;left:10px;bottom:10px;z-index:800;background:rgba(250,250,248,.92);' +
      'border:1px solid rgba(19,50,115,.14);border-radius:10px;padding:8px 10px;font:600 10px Inter,system-ui,sans-serif;' +
      'color:#24324d;box-shadow:0 6px 16px -10px rgba(20,22,26,.35);pointer-events:none}' +
    '.sd-lejant b{display:block;font-size:8px;letter-spacing:1.6px;color:#133273;margin-bottom:5px}' +
    '.sd-lejant i{display:inline-block;width:16px;height:3px;border-radius:2px;margin-right:6px;vertical-align:middle}' +
    '.sd-lejant i.n{width:8px;height:8px;border-radius:50%;margin:0 10px 0 4px}' +
    '.sd-lejant div{margin-top:3px}';
  document.head.appendChild(css);

  // ── Genel Müdürlük binası (Ataşehir) ──
  var binaSvg =
    '<svg class="gm-bina" viewBox="0 0 32 44" xmlns="http://www.w3.org/2000/svg">' +
      '<rect x="3" y="40" width="26" height="3" rx="1" fill="#0f1f3d"/>' +
      '<path d="M5 40V12l11-8 11 8v28z" fill="#133273"/>' +
      '<path d="M16 4l11 8v28H16z" fill="#0f2a63"/>' +
      '<rect x="13" y="1" width="6" height="4" rx="1" fill="' + gmRenk + '"/>' +
      '<g fill="#7dd3fc">' +
        '<rect class="pc" x="8" y="15" width="4" height="4" rx=".6"/><rect class="pc g2" x="14" y="15" width="4" height="4" rx=".6"/><rect class="pc g1" x="20" y="15" width="4" height="4" rx=".6"/>' +
        '<rect class="pc g3" x="8" y="22" width="4" height="4" rx=".6"/><rect class="pc g1" x="14" y="22" width="4" height="4" rx=".6"/><rect class="pc g2" x="20" y="22" width="4" height="4" rx=".6"/>' +
        '<rect class="pc g2" x="8" y="29" width="4" height="4" rx=".6"/><rect class="pc g3" x="20" y="29" width="4" height="4" rx=".6"/>' +
      '</g>' +
      '<rect x="13.5" y="31" width="5" height="9" rx=".8" fill="' + gmRenk + '"/>' +
    '</svg>';
  L.marker([GM.lat, GM.lon], {
    icon: L.divIcon({
      className: '',
      html: '<div class="gm-kap"><div class="gm-halka"></div><div class="gm-halka h2"></div><div class="gm-halka h3"></div>' +
            binaSvg + '<div class="gm-etiket">GENEL MÜDÜRLÜK</div></div>',
      iconSize: [64, 78], iconAnchor: [32, 50]
    }),
    zIndexOffset: 1000
  }).addTo(map).bindTooltip('Acıbadem Genel Müdürlük · Ataşehir', { direction: 'top', offset: [0, -48] });

  // ── Lejant ──
  var lej = document.createElement('div');
  lej.className = 'sd-lejant';
  lej.innerHTML = '<b>MERKEZ BAĞLANTILARI · SİMÜLASYON</b>' +
    '<div><i style="background:' + RENK['Çevrimiçi'] + '"></i>Çevrimiçi</div>' +
    '<div><i class="n" style="background:' + RENK['Çevrimdışı'] + '"></i>Çevrimdışı</div>' +
    '<div><i class="n" style="background:' + RENK['Kurulmadı'] + '"></i>Kurulmadı</div>';
  map.getContainer().appendChild(lej);

  // ── Ok katmanı: kendi panesinde, işaretçilerin altında ──
  var pane = map.createPane('saldiriPane');
  pane.style.zIndex = 450;
  pane.style.pointerEvents = 'none';
  var svg = document.createElementNS(NS, 'svg');
  svg.style.position = 'absolute';
  svg.style.overflow = 'visible';
  pane.appendChild(svg);

  var OKLAR = [];
  hospitals.forEach(function (h, i) {
    // Ok YALNIZCA çevrimiçi lokasyonlardan çıkar
    if (h.id === GM_ID || h.durum !== 'Çevrimiçi') return;
    var renk = h.renk || RENK['Çevrimiçi'];   // noktanın kendi rengi
    var aktif = true;
    var saldiri = false;
    var g = document.createElementNS(NS, 'g');
    g.setAttribute('class', 'sd-grup');
    g.style.color = renk;
    function yol(sinif) {
      var p = document.createElementNS(NS, 'path');
      p.setAttribute('class', sinif);
      p.setAttribute('stroke', renk);
      g.appendChild(p);
      return p;
    }
    var taban = yol('sd-taban');
    if (!aktif) { taban.setAttribute('stroke-dasharray', '3 6'); }
    var akis = aktif ? yol('sd-akis' + (saldiri ? ' hizli' : '')) : null;
    var kuyruk = null, ok = null;
    if (aktif && !azHareket) {
      kuyruk = yol('sd-kuyruk');
      ok = document.createElementNS(NS, 'path');
      ok.setAttribute('d', 'M8 0L-5 -5.5L-2 0L-5 5.5Z');
      ok.setAttribute('fill', renk);
      ok.setAttribute('class', 'sd-ok');
      g.appendChild(ok);
    }
    svg.appendChild(g);
    OKLAR.push({
      h: h, taban: taban, akis: akis, kuyruk: kuyruk, ok: ok, uzunluk: 0,
      sure: saldiri ? 1500 + (i % 4) * 180 : 2600 + (i % 5) * 260,
      faz: (i * 0.37) % 1
    });
  });

  function ciz() {
    var boyut = map.getSize();
    var solUst = map.containerPointToLayerPoint([0, 0]);
    L.DomUtil.setPosition(svg, solUst);
    svg.setAttribute('width', boyut.x);
    svg.setAttribute('height', boyut.y);
    var hedef = map.latLngToContainerPoint([GM.lat, GM.lon]);
    hedef = L.point(hedef.x, hedef.y - 6);
    OKLAR.forEach(function (o) {
      var kaynak = map.latLngToContainerPoint([o.h.lat, o.h.lon]);
      var dx = hedef.x - kaynak.x, dy = hedef.y - kaynak.y;
      var d = Math.sqrt(dx * dx + dy * dy) || 1;
      var nx = -dy / d, ny = dx / d;
      if (ny > 0) { nx = -nx; ny = -ny; }              // kavis hep yukarı
      var yuk = Math.max(14, Math.min(d * 0.38, 320));
      var cx = (kaynak.x + hedef.x) / 2 + nx * yuk, cy = (kaynak.y + hedef.y) / 2 + ny * yuk;
      var dStr = 'M' + kaynak.x.toFixed(1) + ' ' + kaynak.y.toFixed(1) +
                 ' Q' + cx.toFixed(1) + ' ' + cy.toFixed(1) +
                 ' ' + hedef.x.toFixed(1) + ' ' + hedef.y.toFixed(1);
      o.taban.setAttribute('d', dStr);
      if (o.akis) o.akis.setAttribute('d', dStr);
      if (o.kuyruk) {
        o.kuyruk.setAttribute('d', dStr);
        o.uzunluk = o.kuyruk.getTotalLength();
      }
    });
    animasyon(performance.now());
  }

  function animasyon(simdi) {
    OKLAR.forEach(function (o) {
      if (!o.kuyruk || o.uzunluk < 4) {
        if (o.kuyruk) { o.kuyruk.style.opacity = 0; o.ok.style.opacity = 0; }
        return;
      }
      var L_ = o.uzunluk;
      var t = ((simdi / o.sure) + o.faz) % 1;
      var s = t * L_;
      var kuyrukBoy = Math.min(70, L_ * 0.45);
      o.kuyruk.setAttribute('stroke-dasharray', kuyrukBoy + ' ' + (L_ + kuyrukBoy));
      o.kuyruk.setAttribute('stroke-dashoffset', (kuyrukBoy - s).toFixed(1));
      var sol = t < 0.1 ? t / 0.1 : (t > 0.9 ? (1 - t) / 0.1 : 1);   // uçta yumuşak giriş/çıkış
      o.kuyruk.style.opacity = (0.95 * sol).toFixed(2);
      var p = o.kuyruk.getPointAtLength(s);
      var q = o.kuyruk.getPointAtLength(Math.max(0, s - 1.5));
      var aci = Math.atan2(p.y - q.y, p.x - q.x) * 180 / Math.PI;
      o.ok.setAttribute('transform', 'translate(' + p.x.toFixed(1) + ' ' + p.y.toFixed(1) + ') rotate(' + aci.toFixed(1) + ')');
      o.ok.style.opacity = sol.toFixed(2);
    });
  }

  function dongu(simdi) { animasyon(simdi); requestAnimationFrame(dongu); }
  map.on('zoomstart', function () { pane.style.opacity = 0; });
  map.on('zoomend', function () { ciz(); pane.style.transition = 'opacity .25s'; pane.style.opacity = 1; });
  map.on('move resize viewreset', ciz);
  [0, 150, 450, 1300].forEach(function (ms) { setTimeout(ciz, ms); });
  if (!azHareket) requestAnimationFrame(dongu);
})();
"""

@st.cache_resource(show_spinner=False)
def _demo_sunucusu_baslat():
    """Sunum modunda örnek veri sunucusunu UYGULAMA İÇİNDE başlatır.

    Böylece sunum yapılacak bilgisayarda Python kurulu olması gerekmez:
    portal kendi verisini kendisi servis eder. Uygulama Streamlit Cloud'a
    ikinci bir demo uygulaması olarak kurulduğunda da çalışır — tarayıcıdan
    adrese girmek yeterlidir.
    """
    import sys as _sys
    _sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import _sim_sunucu
    return _sim_sunucu.sunucu_baslat(8099)


def _demo_modu() -> bool:
    """Sunum modu açık mı? (ortam değişkeni veya secrets)"""
    if os.environ.get("SYNAPSE_DEMO", "").strip() == "1":
        return True
    try:
        return str(st.secrets.get("demo", {}).get("aktif", "")).lower() in ("1", "true", "evet")
    except Exception:
        return False


def _gizli_oku(bolum: str, anahtar: str, varsayilan: str = "") -> str:
    """st.secrets'tan güvenli okuma.

    Sunum uygulamasında secrets dosyası HİÇ YOKTUR; st.secrets'a dokunmak
    Streamlit'in sayfaya "No secrets found" uyarısı basmasına yol açıyor ve bu
    sunumda görünüyordu. Demo modunda secrets'a hiç bakılmaz.
    """
    if _demo_modu():
        return varsayilan
    try:
        return str(st.secrets.get(bolum, {}).get(anahtar, "") or varsayilan)
    except Exception:
        return varsayilan


def load_config():
    # ── SUNUM/DEMO MODU ──
    # Portal canlı Supabase yerine ÖRNEK VERİ sunucusuna bağlanır.
    # Streamlit Cloud'daki gerçek uygulamada ne bu ortam değişkeni ne de
    # [demo] secrets bölümü bulunur; dolayısıyla ÜRETİM ETKİLENMEZ.
    if _demo_modu():
        return {"supabase_url": _demo_sunucusu_baslat(), "supabase_key": "simulasyon"}

    # Harici simülasyon sunucusu (SUNUM_BASLAT.bat ile yerel kullanım)
    _sim = os.environ.get("SYNAPSE_SIM_URL", "").strip()
    if _sim:
        return {"supabase_url": _sim,
                "supabase_key": os.environ.get("SYNAPSE_SIM_KEY", "simulasyon")}

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

    # 2) Fallback: wttr.in (Cloudflare CDN üzerinde, çok güvenilir)
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

# Sunumda (demo) ekran saniyede bir akar; önbellek yarım sn (1 sn olunca her
# ikinci yenileme aynı değeri getiriyordu, akış 2 sn'ye düşüyordu). Gerçekte 12.
_CANLI_TTL = 0.5 if _demo_modu() else 12


@st.cache_data(ttl=_CANLI_TTL, show_spinner=False)
def fetch_canli_guc(url, key, lokasyon_id):
    """Lokasyonun canlı sayaç gücü (kW) — (olcumler, yas_sn).

    TTL 12 sn: saha 15 saniyede bir yazıyor, daha sık sormak AYNI veriyi
    tekrar indirmek demek. 27 sayaçta bu fark günde 63 MB ile 21 MB
    arasında: ekranda hiçbir değişiklik olmadan trafik üçte bire iner.
    Çizginin akması eksenin kaymasından gelir, sorgu sıklığından değil.

    Yaş, SAHADAKİ ölçüm zamanından hesaplanır (sorgu zamanından değil):
    lokasyon okumayı kesmişse panel bunu "akış durmuş" diye gösterebilsin.
    """
    try:
        from supabase import create_client
        from datetime import datetime, timezone
        c = create_client(url, key)
        r = (c.table("canli_guc").select("*")
             .eq("lokasyon_id", lokasyon_id).order("cihaz").execute())
        satirlar = r.data or []
        if not satirlar:
            return [], None
        yas = None
        for s in satirlar:
            try:
                t = datetime.fromisoformat(str(s.get("olcum_zamani")).replace("Z", "+00:00"))
                simdi = datetime.now(timezone.utc) if t.tzinfo else datetime.now()
                _y = (simdi - t).total_seconds()
                yas = _y if yas is None else min(yas, _y)
            except Exception:
                pass
        return satirlar, yas
    except Exception:
        return [], None


# ── ANA EKRAN İÇİN ANLIK DEĞERLER (tüm lokasyonlar) ──────────────────────
# Lokasyon kartları, harita penceresi ve Global Özet artık günlük kWh değil
# canli_guc tablosundaki ANLIK kW'ı gösterir. Tek sorguda tüm lokasyonlar
# alınır (lokasyon başına ayrı istek atılmaz).
CANLI_BAYAT_SN = 300   # son ölçüm bundan eskiyse "canlı değil" sayılır

@st.cache_data(ttl=_CANLI_TTL, show_spinner=False)
def fetch_canli_tum(url, key):
    try:
        from supabase import create_client
        c = create_client(url, key)
        r = c.table("canli_guc").select("lokasyon_id,cihaz,kw,olcum_zamani").execute()
        return r.data or []
    except Exception:
        return []


def canli_ozet_hesapla(satirlar):
    """{lokasyon_id: {"sebeke", "sogutma", "kojen", "yas"}} — kW, ölçülmeyen kalem None.

    Şebeke = TRDP sayaçlarının toplamı, soğutma = chiller + kule (canlı izleme
    panelindeki gruplarla aynı). Kojen sayacı canlı okunmuyor; ileride
    "KOJEN..." adlı bir sayaç tabloya yazılırsa kendiliğinden dolar.
    Son ölçümü CANLI_BAYAT_SN'den eski lokasyon "canlı değil" sayılır.
    """
    from datetime import timezone as _tz
    try:
        import canli_izleme as _ci
        _grup = _ci.grup_bul
    except Exception:
        def _grup(ad):
            ad = str(ad or "").upper()
            if ad.startswith("TRDP-"):
                return "enerji"
            if ad.startswith(("CHILLER-", "CH-", "KULE-")):
                return "sogutma"
            return "diger"
    ozet = {}
    for s in satirlar or []:
        lok = s.get("lokasyon_id")
        kw = s.get("kw")
        if not lok or kw is None:
            continue
        try:
            kw = float(kw)
        except (TypeError, ValueError):
            continue
        o = ozet.setdefault(lok, {"sebeke": None, "sogutma": None, "kojen": None,
                                  "dogalgaz": None, "su": None, "yas": None, "t": None})
        try:
            t = datetime.fromisoformat(str(s.get("olcum_zamani")).replace("Z", "+00:00"))
            simdi = datetime.now(_tz.utc) if t.tzinfo else datetime.now()
            y = (simdi - t).total_seconds()
            o["yas"] = y if o["yas"] is None else min(o["yas"], y)
            # Son ölçümün zamanı (epoch): ekrandaki geçiş bununla eşlenir
            _te = t.timestamp()
            o["t"] = _te if o["t"] is None else max(o["t"], _te)
        except Exception:
            pass
        ad = str(s.get("cihaz") or "").upper()
        # Kojen / gaz (m³/h) / su (m³/h) sahada bugün canlı okunmuyor; bu
        # adlarla satır gelirse (bugün yalnız sunum verisi) kendiliğinden dolar.
        if ad.startswith("KOJEN"):
            alan = "kojen"
        elif ad.startswith("DOGALGAZ-"):
            alan = "dogalgaz"
        elif ad.startswith("SU-"):
            alan = "su"
        else:
            alan = {"enerji": "sebeke", "sogutma": "sogutma"}.get(_grup(ad))
        if alan:
            o[alan] = (o[alan] or 0.0) + kw
    # Bayat lokasyonlar canlı sayılmaz
    return {k: v for k, v in ozet.items()
            if v["yas"] is None or v["yas"] <= CANLI_BAYAT_SN}


def _canli_akis_betigi(taban: dict, mod: str = "dalga") -> str:
    """Saniyelik akış betiği (canli_izleme.akis_betigi; detay sayfası da kullanır).
    mod="gecis": gerçek sistem — önceki → son gerçek ölçüm arası geçiş.
    mod="dalga": yalnız sunum."""
    import canli_izleme as _ci
    return _ci.akis_betigi(taban, mod)


CANLI_ALANLAR = ("sebeke", "sogutma", "kojen", "dogalgaz", "su")


def canli_gecis_hesapla(canli: dict, durum: dict) -> dict:
    """{(lok, alan): {"o","d","t","s"}} — her kalemin önceki ve son GERÇEK ölçümü.
    durum oturumda saklanır (st.session_state); aynı ölçüm iki kez "yeni" sayılmaz."""
    import canli_izleme as _ci
    sonuc = {}
    for lok, v in (canli or {}).items():
        for alan in CANLI_ALANLAR:
            g = _ci.gecis_izle(durum, (lok, alan), v.get(alan), v.get("t"))
            if g:
                sonuc[(lok, alan)] = g
    return sonuc


def gecis_toplami(gecisler: list):
    """Birden çok kalemin toplam geçişi. Önceki toplam = her kalemin önceki
    ölçümü (yoksa son ölçümü); gösterilen toplam da iki gerçek toplamın
    arasında kalır. Hiçbirinin önceki ölçümü yoksa None (sayı sabit durur)."""
    gecisler = [g for g in gecisler if g]
    if not gecisler or all(g["o"] is None or not g["s"] for g in gecisler):
        return None
    return {"o": sum(g["o"] if g["o"] is not None else g["d"] for g in gecisler),
            "d": sum(g["d"] for g in gecisler), "t": max(g["t"] for g in gecisler),
            "s": max(g["s"] for g in gecisler if g["s"])}


def gecis_ozellik(g, carpan: float = 1.0) -> str:
    """Akış betiği için HTML öznitelikleri (önceki ölçüm yoksa boş)."""
    if not g or g.get("o") is None or not g.get("s"):
        return ""
    return (f' data-onceki="{g["o"] * carpan:.3f}" data-t="{g["t"]:.3f}"'
            f' data-sure="{g["s"]:.1f}"')


def kw_metin(x, ond=0):
    """1234.5 → '1.235' (ond=0) / '1.234,5' (ond=1); None → '—'."""
    if x is None:
        return "—"
    s = f"{x:,.{ond}f}"
    if ond:
        tam, kesir = s.split(".")
        return tam.replace(",", ".") + "," + kesir
    return s.replace(",", ".")


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
# HAVA TAHMİNİ — yalnızca GÖSTERİM için
# ═══════════════════════════════════════════════════════════════
# Oto-set KURAL TABLOSU burada DEĞİLDİR. Eşikler, histerezis ve set
# değerleri yalnızca hvac/deneme/oto_set.py içinde durur; kararı lokasyon
# PC'si verir ve BACnet ile doğrudan yazar. Merkez yalnızca kuralı yayınlar
# (geçiş saatleri, açık/kapalı) ve durumu gösterir.
#
# 01.10.2026: Buradaki kopya (_CH_SET/_DIG_SET/_DIG_ESIK ve komut gönderen
# _oto_set_kontrol) SİLİNDİ. Çalışmıyordu ama iki kaynak olması tehlikeliydi:
# biri yorumu kaldırıp thread'i başlatsa komutlar ÇİFT gidecekti ve iki tablo
# zamanla ayrışırsa portal başka, saha başka değer gösterecekti.


def _fetch_tahmin() -> dict | None:
    """Open-Meteo'dan bugünün ve yarının max/min sıcaklıklarını döner.

    HANGİ DEĞER NEREDE KULLANILIR:
      * Gündüz seti (varsayılan 05:00) → BUGÜNÜN max'ı.
        05:00'te başlayan gündüz bugünün gündüzüdür; yarının max'ına bakmak
        bir gün kayması yaratıyordu (bugün 30°C / yarın 22°C gibi günlerde
        sıcak bir güne ılıman set gidiyordu).
      * Gece seti (varsayılan 22:00) → YARININ min'i.
        22:00'de başlayan gece takvimde yarına sarkar ve en düşük sıcaklık
        yarın sabaha doğru oluşur; doğru referans yarının min'idir.
    """
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
        _mx = _d["daily"]["temperature_2m_max"]
        _mn = _d["daily"]["temperature_2m_min"]
        return {
            "bugun_max": round(_mx[0], 1),
            "bugun_min": round(_mn[0], 1),
            "yarin_max": round(_mx[1], 1),
            "yarin_min": round(_mn[1], 1),
        }
    except Exception:
        return None


# Geçiş saati varsayılanları — YALNIZCA GÖSTERİM içindir. Ayarlar tablosunda
# değer yoksa ekranda bu saatler görünür; sahaya set gönderen karar lokasyonda
# ve orada varsayılan saat bilerek YOKTUR (kural okunamazsa hiçbir şey yapılmaz).
_OTO_GUNDUZ_VARSAYILAN = 5    # gündüz setleri bu saatte gider
_OTO_GECE_VARSAYILAN   = 22   # gece setleri bu saatte gider


def _donem_hesapla(saat: int, gunduz_saat: int, gece_saat: int) -> str:
    """Saate göre dönem. Gece yarısını aşan aralıklar da desteklenir."""
    if gunduz_saat == gece_saat:
        return "gunduz"
    if gunduz_saat < gece_saat:          # ör. 5 → 22
        return "gunduz" if gunduz_saat <= saat < gece_saat else "gece"
    return "gunduz" if (saat >= gunduz_saat or saat < gece_saat) else "gece"


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


# NOT: Oto-set kontrolü ve onu çalıştıran arka plan thread'i buradan
# kaldırıldı (01.10.2026). Sebep, Streamlit Cloud uygulamayı kimse açmayınca
# uyutuyordu; setler belirlenen saatte değil biri portalı açtığında gidiyordu
# (ayar 08:00/23:00 iken sahadan ölçülenler: 31.08 00:32, 30.08 08:56,
# 29.08 11:35). Karar 7/24 çalışan lokasyon PC'sine taşındı:
# hvac/deneme/oto_set.py — cloud_sync döngüsünden dakikada bir çağrılır.


# m² değerlerini Supabase'den yükle (yoksa config/default kullan)
m2_config = {}
if bagli:
    m2_config = fetch_m2_supabase(url, key)
if not m2_config:
    m2_config = config.get("m2_degerler", {})
for lok_id in HASTANELER:
    if lok_id in m2_config:
        HASTANELER[lok_id]["m2"] = int(m2_config[lok_id])

# ═══════════ QR SAHA BAKIM KARTI (telefon) — ?bakim=<cihaz>&lok=<lokasyon> ═══════════
# Sahadaki QR etiketleri buraya yönlenir. Kartlar Supabase `bakim_kartlari` tablosunda
# tutulur; lokasyon PC'si cloud_sync ile 2 dakikada bir çift yönlü senkronize eder.
BAKIM_BILESENLER = [
    "heating_valve_body", "heating_valve_signal",
    "cooling_valve_body", "cooling_valve_signal",
    "supply_sensor", "return_sensor", "pressure_sensor",
]
BAKIM_BILESEN_ETIKET = {
    "heating_valve_body":   "Isıtma Vanası Gövde",
    "heating_valve_signal": "Isıtma Vanası 0-10V",
    "cooling_valve_body":   "Soğutma Vanası Gövde",
    "cooling_valve_signal": "Soğutma Vanası 0-10V",
    "supply_sensor":        "Üfleme Sensör",
    "pressure_sensor":      "Basınç Sensörü",
    "return_sensor":        "Emiş Sensör",
}
BAKIM_DURUMLAR = ["OK", "FAULTY", "MAINTENANCE", "N/A"]
BAKIM_DURUM_ETIKET = {
    "OK": "✅ Sağlam", "FAULTY": "❌ Arızalı",
    "MAINTENANCE": "🔧 Bakımda", "N/A": "⚪ Yok",
}

def _qr_bakim_sayfasi():
    from datetime import timezone as _qtz

    cihaz = (st.query_params.get("bakim") or "").strip()
    lok   = (st.query_params.get("lok") or "").strip().lower()

    # Mobil dostu kompakt başlık
    st.markdown(f"""
    <div style="text-align:center; padding:8px 0 4px;">
      <div style="font-size:10px; color:#46536b; letter-spacing:2px;">ACIBADEM SYNAPSE — SAHA</div>
      <div style="font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif; font-size:26px; font-weight:600; color:#0f1f3d;">
        🔧 Dijital Bakım Kartı
      </div>
    </div>
    """, unsafe_allow_html=True)

    if not bagli:
        st.error("Supabase bağlantısı yok — sistem yöneticisine bildirin.")
        return

    # ── Saha PIN koruması (secrets'ta [saha] pin tanımlıysa) ──
    saha_pin = _gizli_oku("saha", "pin")
    if not saha_pin:
        saha_pin = str(config.get("saha_pin", "") or "")
    if saha_pin and not st.session_state.get("saha_pin_ok"):
        girilen = st.text_input("Saha PIN", type="password", placeholder="PIN girin")
        if st.button("Giriş", use_container_width=True):
            if girilen == saha_pin:
                st.session_state["saha_pin_ok"] = True
                st.rerun()
            else:
                st.error("PIN hatalı")
        return

    from supabase import create_client as _qcc
    try:
        _qc = _qcc(url, key)
    except Exception as e:
        st.error(f"Bağlantı hatası: {e}")
        return

    # ── Lokasyon seçimi (QR'da lok yoksa) ──
    if lok not in HASTANELER:
        lok = st.selectbox(
            "Lokasyon", list(HASTANELER.keys()),
            format_func=lambda k: HASTANELER[k]["isim"],
        )

    st.markdown(
        f"<div style='text-align:center; font-size:12px; color:#2a78d6; letter-spacing:1px; "
        f"margin-bottom:8px;'>{HASTANELER[lok]['isim'].upper()}</div>",
        unsafe_allow_html=True,
    )

    # ── Lokasyonun kayıtlı kartlarını çek ──
    try:
        r = _qc.table("bakim_kartlari").select("cihaz,kart,updated_at,updated_by") \
            .eq("lokasyon_id", lok).order("cihaz").range(0, 999).execute()
        satirlar = {x["cihaz"]: x for x in (r.data or [])}
    except Exception as e:
        st.error(f"Bakım kartları okunamadı: {e}")
        st.caption("`bakim_kartlari` tablosu oluşturulmamış olabilir (merkez/bakim_kartlari_tablo.sql).")
        return

    if not satirlar:
        st.warning(
            f"**{HASTANELER[lok]['isim']}** için henüz senkronize edilmiş bakım kartı yok. "
            "Kartlar lokasyon portalında tanımlanır ve PC internete bağlanınca buraya gelir."
        )
        return

    # ── Cihaz seçimi (QR'da cihaz yoksa veya kayıtlı değilse liste göster) ──
    if cihaz not in satirlar:
        if cihaz:
            st.warning(f"**{cihaz}** bu lokasyonda kayıtlı değil — listeden seçin.")
        cihaz = st.selectbox("Santral / Cihaz", sorted(satirlar.keys()))

    satir = satirlar[cihaz]
    kart = dict(satir.get("kart") or {})

    st.markdown(
        f"<div style='text-align:center; background:rgba(19,50,115,0.1); "
        f"border:1px solid rgba(19,50,115,0.35); border-radius:14px; padding:10px; "
        f"font-size:22px; font-weight:700; color:#0f1f3d; margin-bottom:6px;'>{cihaz}</div>",
        unsafe_allow_html=True,
    )
    son_g = str(satir.get("updated_at") or "")[:16].replace("T", " ")
    st.caption(f"Son güncelleme: {son_g} UTC — {satir.get('updated_by') or '-'}")

    # ── Bileşen durumları formu ──
    with st.form(key=f"qr_bakim_form_{lok}_{cihaz}"):
        yeni_kart = {}
        for comp in BAKIM_BILESENLER:
            mevcut = kart.get(comp, "OK")
            idx = BAKIM_DURUMLAR.index(mevcut) if mevcut in BAKIM_DURUMLAR else 0
            yeni_kart[comp] = st.selectbox(
                BAKIM_BILESEN_ETIKET[comp], BAKIM_DURUMLAR, index=idx,
                format_func=lambda s: BAKIM_DURUM_ETIKET.get(s, s),
                key=f"qrb_{lok}_{cihaz}_{comp}",
            )
        yeni_kart["notes"] = st.text_input(
            "📝 Not", value=str(kart.get("notes", "") or ""),
            placeholder="Opsiyonel not...", key=f"qrb_{lok}_{cihaz}_notes",
        )
        kaydet = st.form_submit_button("💾 Kaydet", use_container_width=True)

    if kaydet:
        try:
            simdi = datetime.now(_qtz.utc).isoformat()
            _qc.table("bakim_kartlari").upsert({
                "lokasyon_id": lok,
                "cihaz": cihaz,
                "kart": yeni_kart,
                "updated_at": simdi,
                "updated_by": "saha-qr",
            }, on_conflict="lokasyon_id,cihaz").execute()
            st.success("✅ Kaydedildi — lokasyon portalına birkaç dakika içinde yansır.")
        except Exception as e:
            st.error(f"Kaydedilemedi: {e}")

    # Durum özeti rozetleri
    sorunlu = [BAKIM_BILESEN_ETIKET[c] for c in BAKIM_BILESENLER if kart.get(c) in ("FAULTY", "MAINTENANCE")]
    if sorunlu:
        st.caption("Kayıtlı sorunlar: " + ", ".join(sorunlu))

if "bakim" in st.query_params:
    _qr_bakim_sayfasi()
    st.stop()

# ============ GİRİŞ KAPISI ============
# Buraya kadar olan tek şey QR bakım sayfasıdır (yukarıda st.stop() ile biter) —
# saha personeli QR okuttuğunda parola sorulmaz, mevcut akış korunur.
# Bu satırdan SONRAKİ her şey (GM portalı) kimlik doğrulaması ister.
#
# Neden zorunlu: portal Supabase'e service_role anahtarıyla bağlanır ve
# service_role RLS'i bypass eder → portala erişebilen veritabanına tam yetkilidir.
import giris
giris.giris_kapisi()   # giriş yoksa giriş ekranını basar ve durdurur

# İzleyici linkiyle gelindiyse: her şey görünür, hiçbir şey değiştirilemez
_IZLEYICI = giris.izleyici_mi()
if _IZLEYICI:
    st.markdown(
        "<div style='position:fixed;top:10px;left:50%;transform:translateX(-50%);"
        "z-index:999999;background:#eef3fb;border:1px solid rgba(19,50,115,.25);"
        "color:#133273;font-size:10px;font-weight:700;letter-spacing:1px;"
        "padding:4px 12px;border-radius:999px;'>👁 İZLEYİCİ MODU — SALT OKUNUR</div>",
        unsafe_allow_html=True)

now = datetime.now()  # timezone-naive — pandas karsilastirmalari icin
try:
    import pytz as _pytz
    now_display = datetime.now(_pytz.timezone("Europe/Istanbul"))
except ImportError:
    from datetime import timezone as _tz
    now_display = datetime.now(_tz(timedelta(hours=3)))
dun  = (now - timedelta(days=1)).strftime("%Y-%m-%d")

# ============ HEADER ============
# "ACIBADEM SAĞLIK GRUBU" büyük; üzerinden lacivert→mavi parıltı akar.
# Altında küçük "Enerji Canlı İzleme" + atan canlı noktası.
# Lokasyon detayına girilince başlık gösterilmez (üstte boşluk kalmasın).
#
# ÜST BOŞLUK: görünmez yardımcı öğeler (stil blokları, 0 px bileşenler, gizli
# düğmeler) üst düzeyde her biri 16 px aralık ekliyordu → üst düzey aralık
# sıfırlanır, görünen bölümler kendi boşluğunu taşır.
st.markdown("""
<style>
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"]{ gap:0 !important; }
[data-testid="stMainBlockContainer"] > [data-testid="stVerticalBlock"] > [data-testid="stHorizontalBlock"]{ margin-top:14px; }
/* Bölüm başlıkları (Lokasyon Durumu, Hastane Enerji Ağı, Canlı Uyarılar...) */
.sec{ font-size:12px !important; font-weight:700 !important; letter-spacing:1.4px !important; color:#133273 !important;
      display:flex !important; align-items:center; gap:7px; padding-bottom:7px !important; }
/* Detay ekranında başlık yok: sağ üstteki 3 düğme rozetlerin ÜSTÜNDE durur */
.st-key-detay_gecis_katmani{ padding-top:48px; gap:0 !important; }
.st-key-detay_gecis_katmani > [data-testid="stLayoutWrapper"]:has(.st-key-detay_sekmeler){ margin-top:6px; }
</style>
""", unsafe_allow_html=True)

if not st.session_state.get("detay_lokasyon"):
  st.markdown("""
<style>
@keyframes bsAkis{0%{background-position:0% 50%;}100%{background-position:200% 50%;}}
@keyframes bsYukselis{from{opacity:0;transform:translateY(6px);letter-spacing:6px;}to{opacity:1;transform:none;letter-spacing:4px;}}
@keyframes bsCizgi{0%,100%{transform:scaleX(.35);opacity:.5;}50%{transform:scaleX(1);opacity:1;}}
.bs-kutu{text-align:center;padding:2px 0 20px;}
.bs-ana{display:inline-block;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;font-size:34px;
  font-weight:800;letter-spacing:4px;line-height:1.25;
  background:linear-gradient(90deg,#0f1f3d 0%,#133273 25%,#2a78d6 45%,#7fb2ee 50%,#2a78d6 55%,#133273 75%,#0f1f3d 100%);
  background-size:200% 100%;-webkit-background-clip:text;background-clip:text;-webkit-text-fill-color:transparent;
  color:#0f1f3d;animation:bsYukselis .8s ease-out both, bsAkis 6s linear infinite;}
.bs-cizgi{width:160px;height:2px;margin:6px auto 7px;border-radius:2px;
  background:linear-gradient(90deg,transparent,#2a78d6,transparent);animation:bsCizgi 3s ease-in-out infinite;}
.bs-alt{display:inline-flex;align-items:center;gap:7px;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;
  font-size:12px;font-weight:600;color:#2a78d6;letter-spacing:2.5px;text-transform:uppercase;}
@media (prefers-reduced-motion: reduce){.bs-ana,.bs-cizgi{animation:none;}}
</style>
<div class="bs-kutu">
  <div class="bs-ana">ACIBADEM SAĞLIK GRUBU</div>
  <div class="bs-cizgi"></div>
  <div class="bs-alt">""" + _ik.nokta("#0ca30c", 7) + """Enerji Canlı İzleme</div>
</div>
""", unsafe_allow_html=True)

# ============ ÇIKIŞ BUTONU ============
# Sabit konumda (üst sağ) — sayfa akışına girmez, böylece header'ın ortalanmış
# düzenini bozmaz ve detay/rapor dahil TÜM ekranlarda aynı yerde durur.
# right:72px → Streamlit'in kendi üst-sağ menüsüyle çakışmasın diye.
st.markdown("""
<style>
/* Kapsayici tam genislikte birakilir ve icerik SAGA YASLANIR.
   Genisligi daraltmayi denemek ise yaramadi: Streamlit kapsayiciya kendi
   genisligini veriyor, sag kenar hizalaninca sol kenar ekran disina tasip
   buton sol ust kosede kesik gorunuyordu.
   pointer-events:none -> gorunmez serit altindaki sayfayi tiklamayi engellemesin;
   butonda tekrar acilir. */
.st-key-cikis_kutusu{
    min-width:96px !important;
    position:fixed !important; top:16px !important;
    left:0 !important; right:0 !important; width:100% !important;
    /* Streamlit'in kendi ust seridi (stHeader) z-index:999990 ve fixed;
       daha dusuk bir deger verilirse buton GORUNUR ama tiklama seride gider
       ve buton olu kalir. Bu yuzden onun uzerine cikilir. */
    z-index:999999 !important;
    /* Simgeler YAN YANA ve sagda: kapsayici satir flex'e cevrilir.
       (Dikey flex'te justify-content butonu asagi yaslardi.) */
    display:flex !important; flex-direction:row !important;
    justify-content:flex-end !important; align-items:center !important;
    padding:0 72px 0 0 !important; gap:8px !important;
    pointer-events:none !important;   /* alttaki sayfa tiklanabilir kalsin */
}
/* Ara katmanlar tam genislikte kaliyor; daraltilmazsa hizalama ise yaramaz */
.st-key-cikis_kutusu [data-testid="stElementContainer"],
.st-key-cikis_kutusu [data-testid="stButton"],
.st-key-cikis_kutusu .stTooltipIcon{
    width:auto !important; min-width:0 !important;
}
.st-key-cikis_kutusu [data-testid="stButton"]{pointer-events:auto !important;}
.st-key-cikis_kutusu .stButton button{white-space:nowrap !important; min-height:34px !important;}
.st-key-cikis_kutusu .stButton button{
    background:rgba(243,246,251,0.55) !important;
    border:1px solid rgba(19,50,115,0.28) !important;
    color:#24324d !important;
    font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif,sans-serif !important;
    /* Simge butonu: kare oranli, ortalanmis */
    font-size:15px !important; line-height:1 !important;
    padding:0 !important; border-radius:9px !important;
    width:34px !important; height:34px !important;
    display:flex !important; align-items:center !important; justify-content:center !important;
    box-shadow:0 10px 22px -12px rgba(20,22,26,.22) !important;
    transition:background .18s ease, border-color .18s ease, color .18s ease !important;
}
.st-key-cikis_kutusu .stButton button:hover{
    background:#133273 !important;
    border-color:#133273 !important;
    color:#ffffff !important;
}
</style>
""", unsafe_allow_html=True)

with st.container(key="cikis_kutusu"):
    # Yalnizca simge — metin yok. Ne ise yaradigi help balonunda yazili.
    # DIKKAT: burada st.columns KULLANILMAZ; kapsayici sabit konumlu bir
    # seritdir, sutun eklenince butonlar sayfa genisligine yayiliyor.
    # Yan yana dizilim CSS'te (flex-direction:row) yapilir.
    st.markdown(
        "<style>"
        + _ik.etiket_css(".st-key-cikis_kutusu a.ayar-ac", "ayar", 17)
        + _ik.etiket_css(".st-key-yonetim_btn button p", "yonetim", 17)
        + _ik.etiket_css(".st-key-cikis_btn button p", "cikis", 17)
        + ".st-key-cikis_kutusu .stButton button p{font-size:0 !important;line-height:0 !important;margin:0 !important;}"
        + ".st-key-cikis_kutusu .stButton button p::before{margin-right:0 !important;vertical-align:0 !important;}"
        + ".st-key-cikis_kutusu .stButton button:hover p::before{background:#ffffff !important;}"
        + ".st-key-cikis_kutusu [data-testid=stElementContainer]:has(a.ayar-ac){pointer-events:auto !important;}"
        + ".st-key-cikis_kutusu a.ayar-ac{display:flex !important;align-items:center;justify-content:center;"
          "width:34px;height:34px;border-radius:9px;border:1px solid rgba(19,50,115,0.28);"
          "background:rgba(243,246,251,0.55);box-shadow:0 10px 22px -12px rgba(20,22,26,.22);"
          "transition:background .18s ease;cursor:pointer;text-decoration:none !important;}"
        + ".st-key-cikis_kutusu a.ayar-ac::before{margin-right:0 !important;vertical-align:0 !important;}"
        + ".st-key-cikis_kutusu a.ayar-ac:hover{background:#133273;border-color:#133273;}"
        + ".st-key-cikis_kutusu a.ayar-ac:hover::before{background:#ffffff !important;}"
        # Ayarlar paneli yalnızca ana sayfada var; diğer ekranlarda düğme gizlenir
        # Detay ekranında düğmeler biraz daha yukarıda (başlık yok; rozetlerin üstü)
        + "body:has(.st-key-detay_gecis_katmani) div.st-key-cikis_kutusu{top:8px !important;}"
        + ".st-key-ayar_ana_btn{position:fixed !important;left:-9999px !important;width:1px;height:1px;overflow:hidden;}"
        + "</style>", unsafe_allow_html=True)
    if not _IZLEYICI:
        # Ayarlar paneli TARAYICIDA açılıp kapanır: düğme Streamlit butonu
        # değil, düz bir bağlantı. Böylece açarken / kapatırken program baştan
        # çalışmaz (önceki pencere sürümünde her tıklama sayfayı yeniliyordu).
        st.markdown('<a class="ayar-ac" href="#" title="Sistem ayarları" aria-label="Sistem ayarları"></a>',
                    unsafe_allow_html=True)
        # Detay / yönetim ekranındayken Ayarlar: görünmez düğme ana sayfaya döner,
        # panel orada kendiliğinden açılır (aşağıdaki betik).
        if st.button("ana", key="ayar_ana_btn"):
            for _k in ("detay_lokasyon", "detay_ozet", "yonetim", "detay_sekme"):
                st.session_state.pop(_k, None)
            st.rerun()
    if st.button("Yönetim", key="yonetim_btn", help="Yönetim — sunucu ve veri durumu"):
        st.session_state["yonetim"] = True
        st.rerun()
    if st.button("Çıkış", key="cikis_btn", help="Oturumu kapat"):
        giris.cikis_yap()
        st.rerun()

# Ayarlar paneli aç / kapat: tamamen tarayıcıda (düğme, ×, arka plan, Esc).
# Panel yalnızca ana sayfada var; başka ekrandan basılırsa ana sayfaya dönülür
# ve panel orada açılır. Her çizimde yeniden bağlanır (bekleyen açma için).
_components.html("""
<script>
(function () {
  var d; try { d = window.parent.document; } catch (e) { return; }
  var w = d.defaultView;
  function ac(v) { d.body.classList.toggle('ayarlar-acik', v); }
  function bekleyen() {
    try {
      if (w.sessionStorage.getItem('synapse_ayar_ac') && d.querySelector('.st-key-ayarlar_panel')) {
        w.sessionStorage.removeItem('synapse_ayar_ac'); ac(true);
      }
    } catch (e) {}
  }
  [300, 1200, 2500].forEach(function (ms) { setTimeout(bekleyen, ms); });
  if (w.__synapseAyarTik) d.removeEventListener('click', w.__synapseAyarTik, true);
  if (w.__synapseAyarTus) d.removeEventListener('keydown', w.__synapseAyarTus, true);
  w.__synapseAyarTik = function (ev) {
    var t = ev.target;
    if (t.closest && t.closest('a.ayar-ac')) {
      ev.preventDefault();
      if (d.querySelector('.st-key-ayarlar_panel')) { ac(!d.body.classList.contains('ayarlar-acik')); return; }
      try { w.sessionStorage.setItem('synapse_ayar_ac', '1'); } catch (e) {}
      var b = d.querySelector('.st-key-ayar_ana_btn button'); if (b) b.click();
      return;
    }
    if (t.closest && t.closest('a.ayar-kapat')) { ev.preventDefault(); ac(false); return; }
    if (d.body.classList.contains('ayarlar-acik') && (t === d.body || t === d.documentElement)) ac(false);
  };
  w.__synapseAyarTus = function (ev) { if (ev.key === 'Escape') ac(false); };
  d.addEventListener('click', w.__synapseAyarTik, true);
  d.addEventListener('keydown', w.__synapseAyarTus, true);
})();
</script>
<!-- cizim: %s -->
""" % datetime.now().strftime("%H%M%S%f"), height=0)

# ── SUNUM/DEMO UYARISI ──
# Simülasyon sunucusuna bağlıyken ekranda görünür bir işaret durur; böylece
# demo ekranının görüntüsü gerçek veriyle karıştırılmaz. Üretimde (canlı
# Supabase) bu blok hiç çalışmaz.
if "127.0.0.1" in url or "localhost" in url:
    st.markdown(
        "<div style='position:fixed;top:10px;left:18px;z-index:999999;"
        "background:rgba(250,178,25,0.16);border:1px solid rgba(250,178,25,0.55);"
        "color:#8a5a00;border-radius:8px;padding:5px 12px;font-size:10px;"
        "letter-spacing:1.6px;text-transform:uppercase;font-weight:700;"
        "font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;'>"
        "● Simülasyon — Örnek Veri</div>",
        unsafe_allow_html=True)

# ── Lokasyon detay yönlendirmesi (kart ikonu tıklanınca) — aynı sayfada, animasyonlu ──
if "detay" in st.query_params:
    _lok = st.query_params["detay"]
    if _lok in HASTANELER:
        st.session_state["detay_lokasyon"] = _lok
        # Dış bağlantı: ?detay=maslak&sekme=canli → detay Canlı İzleme
        # sekmesinde açılır (lokasyon_detay.py bayrağı bir kez kullanıp siler).
        if (st.query_params.get("sekme") or "").strip().lower() == "canli":
            st.session_state["detay_sekme"] = "canli"
        st.query_params.clear()
        st.rerun()

# ── Global özet karşılaştırma yönlendirmesi (metrik kartına tıklanınca) ──
# Karşılaştırma sayfasının tanıdığı metrikler. ozet_karsilastirma.py içindeki
# METRIKLER ile aynı olmalı — test_ozet_karsilastirma.py bunu doğrular.
OZET_METRIKLERI = ("enerji", "dogalgaz", "sogutma", "su", "kojen")

if "ozet" in st.query_params:
    _oz = st.query_params["ozet"]
    if _oz in OZET_METRIKLERI:
        st.session_state["detay_ozet"] = _oz
        st.query_params.clear()
        st.rerun()

# ── Yönetim ekranı (canlı sunucu/veri durumu) ──
if "yonetim" in st.query_params:
    st.session_state["yonetim"] = True
    st.query_params.clear()
    st.rerun()

if st.session_state.get("yonetim"):
    with st.container(key="yonetim_katmani"):
        _yon_dosya = os.path.join(os.path.dirname(__file__), "pages", "yonetim.py")
        with open(_yon_dosya, "r", encoding="utf-8") as _f:
            _yon_kaynak = _f.read()
        exec(compile(_yon_kaynak, _yon_dosya, "exec"), globals())
    st.stop()

if st.session_state.get("detay_ozet"):
    with st.container(key="ozet_gecis_katmani"):
        # Sunum modunda genişletilmiş sürüm (tıklanabilir detay penceresi,
        # hedef eşikleri, sistem dağılımı). Canlı portal mevcut sayfayı kullanır.
        # Demo dosyası BİLEREK pages/ dışında: Streamlit pages/ altındaki her
        # dosyayı kenar menüsüne ekliyor, canlı portalın menüsünde görünüyordu.
        _oz_dosya = (os.path.join(os.path.dirname(__file__), "sunum", "ozet_karsilastirma_demo.py")
                     if _demo_modu() else
                     os.path.join(os.path.dirname(__file__), "pages", "ozet_karsilastirma.py"))
        with open(_oz_dosya, "r", encoding="utf-8") as _f:
            _oz_kaynak = _f.read()
        exec(compile(_oz_kaynak, _oz_dosya, "exec"), globals())
    st.stop()

if st.session_state.get("detay_lokasyon"):
    st.markdown("""
    <style>
    @keyframes detayGirisAnim {
        from { opacity: 0; transform: translateY(16px) scale(0.99); }
        to   { opacity: 1; transform: translateY(0) scale(1); }
    }
    .st-key-detay_gecis_katmani { animation: detayGirisAnim 0.4s ease-out; }
    </style>
    """, unsafe_allow_html=True)

    with st.container(key="detay_gecis_katmani"):
        _detay_dosya = os.path.join(os.path.dirname(__file__), "pages", "lokasyon_detay.py")
        with open(_detay_dosya, "r", encoding="utf-8") as _f:
            _detay_kaynak = _f.read()
        # app_merkez zaten kendi set_page_config'ini çağırdı — detay sayfasınınkini atla
        import re as _detay_re
        _detay_kaynak = _detay_re.sub(
            r"st\.set_page_config\(.*?\)\n", "", _detay_kaynak, count=1, flags=_detay_re.DOTALL
        )
        exec(compile(_detay_kaynak, _detay_dosya, "exec"), globals())

    st.stop()

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
    """Kartta gösterilen günün bir önceki VERİLİ gününün kWh değeri (% değişim için).
    SYN-3 fix: dun_kwh dün yoksa son mevcut güne düşer — burada da aynı referans gün
    bulunup ondan önceki son verili gün alınır; eskiden sabit (bugün-2) kullanılıyordu
    ve yanlış gün çifti kıyaslanabiliyordu."""
    if df_all.empty or lok_id not in aktif_loklar:
        return 0
    lok_df = df_all[df_all["lokasyon_id"] == lok_id]
    if lok_df.empty or "Toplam_Hastane_Tuketim_kWh" not in lok_df.columns:
        return 0
    # dun_kwh ile aynı referans günü belirle (dün varsa dün, yoksa son verili gün)
    gunler = sorted(lok_df["Tarih"].dropna().dt.strftime("%Y-%m-%d").unique())
    if not gunler:
        return 0
    ref = dun if dun in gunler else gunler[-1]
    oncekiler = [g for g in gunler if g < ref]
    if not oncekiler:
        return 0
    d = lok_df[lok_df["Tarih"].dt.strftime("%Y-%m-%d") == oncekiler[-1]]
    return d["Toplam_Hastane_Tuketim_kWh"].sum()

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
    # .ana-duzen-isaret: tablet CSS'inin ana 3'lü düzeni bulması için işaret
    st.markdown('<div class="sec"><span class="ana-duzen-isaret"></span>' + _ik.ikon("konum", 17)
                + 'LOKASYON DURUMU</div>', unsafe_allow_html=True)

    # ANLIK değerler: kartlar, harita penceresi ve Global Özet bunu kullanır
    CANLI = canli_ozet_hesapla(fetch_canli_tum(url, key))
    # Önceki/son gerçek ölçüm (ekrandaki saniyelik geçiş için)
    GECIS = canli_gecis_hesapla(CANLI, st.session_state.setdefault("_canli_gecis", {}))

    def anlik_sebeke(lok_id):
        return (CANLI.get(lok_id) or {}).get("sebeke")

    # En çok ANLIK şebeke çekenden aza; canlı ölçümü olmayanlar sona
    lok_sira = sorted(
        HASTANELER.items(),
        key=lambda x: (anlik_sebeke(x[0]) is not None, anlik_sebeke(x[0]) or 0),
        reverse=True
    )

    # Tüm kartları tek HTML bloğu olarak oluştur → scrollable div içine sar
    tum_kartlar = '<div class="lok-scroll">'

    for i, (lok_id, lok_info) in enumerate(lok_sira):
        online, fark_dk = online_bilgi(lok_id)
        renk     = lok_info["renk"]
        if fark_dk is None:
            card_cls   = "nk nk-gray"
            durum_renk = "#6b7280"
            durum_lbl  = "KURULMADI"
        elif online:
            card_cls   = "nk nk-green"
            durum_renk = "#0ca30c"
            durum_lbl  = "ÇEVRİMİÇİ"
        else:
            card_cls   = "nk nk-red"
            durum_renk = "#d03b3b"
            durum_lbl  = "ÇEVRİMDIŞI"

        # Kartta ANLIK şebeke gücü (kW). Yoğunluk: W/m² (anlık kW × 1000 / alan)
        kw_anlik  = anlik_sebeke(lok_id)
        kwh_str   = kw_metin(kw_anlik)
        m2_lok    = lok_info.get("m2", 10000)
        verim_str = (kw_metin(kw_anlik * 1000 / m2_lok, 1)
                     if kw_anlik is not None and m2_lok else "—")
        # Bu iki sayı tarayıcıda saniyede bir akar (_canli_akis_betigi): gerçekte
        # önceki → son ölçüm geçişi, sunumda dalga. İkisi aynı fazda.
        _g_seb = GECIS.get((lok_id, "sebeke"))
        _akis_kw = (f' class="canli-sayi" data-deger="{kw_anlik:.1f}" data-ond="0" data-faz="{lok_id}"'
                    + gecis_ozellik(_g_seb) if kw_anlik is not None else "")
        _akis_wm2 = (f' class="canli-sayi" data-deger="{kw_anlik * 1000 / m2_lok:.2f}" data-ond="1" data-faz="{lok_id}"'
                     + gecis_ozellik(_g_seb, 1000.0 / m2_lok) if kw_anlik is not None and m2_lok else "")
        sira_badge = f'<span style="position:absolute;top:8px;left:10px;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;font-size:8px;color:#46536b;font-weight:700;">#{i+1}</span>' if (i < 4 and kw_anlik is not None) else ""

        # Dün/önceki gün % kıyası anlık değerde anlamsız → gösterilmez
        degisim_html = ""


        rr = int(renk[1:3],16); rg = int(renk[3:5],16); rb = int(renk[5:7],16)
        dr = int(durum_renk[1:3],16); dg = int(durum_renk[3:5],16); db = int(durum_renk[5:7],16)

        tum_kartlar += (
            # data-lok + lok-kart: tıklama JS ile yakalanıp gizli Streamlit
            # butonuna yönlendirilir → sayfa YENİDEN YÜKLENMEZ (aşağıya bak).
            # href yine de duruyor: JS çalışmazsa eski tam sayfa yolu yedek kalır.
            f'<a class="{card_cls} lok-kart" data-lok="{lok_id}" '
            f'href="?detay={lok_id}" target="_self" title="{lok_info["kisa"]} detayına git" '
            f'style="padding:14px;position:relative;--lokrenk:{renk};">'
            + sira_badge +
            f'<div style="display:flex;align-items:center;gap:14px;">'
            f'<div style="position:relative;width:58px;height:58px;flex-shrink:0;display:flex;align-items:center;justify-content:center;">'
            f'<div style="position:absolute;top:-5px;left:-5px;right:-5px;bottom:-5px;border-radius:50%;'
            f'background:radial-gradient(circle,rgba({rr},{rg},{rb},0.14) 0%,rgba({rr},{rg},{rb},0.04) 55%,transparent 75%);'
            f'animation:breathe-ring 3s ease-in-out infinite;"></div>'
            f'<div style="font-size:36px;line-height:1;position:relative;z-index:1;'
            f'">🏥</div>'
            f'<div style="position:absolute;top:2px;right:2px;z-index:2;width:11px;height:11px;'
            f'border-radius:50%;background:rgba({dr},{dg},{db},1);border:2px solid #ffffff;'
            f'"></div>'
            f'</div>'
            f'<div style="flex:1;min-width:0;">'
            f'<div style="font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;font-size:10px;font-weight:700;'
            f'color:{renk};letter-spacing:1.5px;'
            f'margin-bottom:1px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{lok_info["kisa"]}</div>'
            f'<div style="font-size:8px;color:{durum_renk};font-weight:600;margin-bottom:5px;">{durum_lbl}</div>'
            f'<div style="display:flex;align-items:baseline;gap:4px;margin-bottom:3px;">'
            f'<span style="font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;font-size:16px;font-weight:900;'
            f'color:{renk};line-height:1;"><span{_akis_kw}>{kwh_str}</span></span>'
            f'<span style="font-size:8px;color:#46536b;">kW</span>'
            f'<span style="margin-left:4px;">{degisim_html}</span>'
            f'</div>'
            f'<div style="display:inline-flex;align-items:center;gap:5px;'
            f'background:rgba(19,50,115,0.05);border-radius:5px;padding:3px 8px;'
            f'border:1px solid rgba(19,50,115,0.10);">'
            f'<span style="font-size:7px;color:#46536b;text-transform:uppercase;letter-spacing:1px;">W/m²</span>'
            f'<span style="font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;font-size:11px;color:#2a78d6;font-weight:700;"><span{_akis_wm2}>{verim_str}</span></span>'
            f'</div>'
            f'</div></div></a>'
        )

    tum_kartlar += '</div>'
    st.markdown(tum_kartlar, unsafe_allow_html=True)

    # ── Lokasyon kartı geçişi: SAYFA YENİDEN YÜKLENMEDEN ──
    #
    # Kartlar ham <a href="?detay=..."> bağlantısıydı; tıklayınca TAM SAYFA
    # YÜKLEMESİ oluyordu. Bunun iki bedeli vardı:
    #   1) yeni oturum açıldığı için oturum çerezden geri kuruluyor, arada
    #      "Oturum doğrulanıyor" ekranı görünüyordu
    #   2) tüm sayfa (veri + grafikler) sıfırdan yükleniyordu — yavaş
    #
    # Çözüm: kart tıklaması JS ile yakalanır ve görünmez bir Streamlit
    # butonuna tıklatılır. Buton normal bir Streamlit etkileşimi olduğu için
    # uygulama AYNI OTURUM içinde yeniden çalışır; sayfa yeniden yüklenmez.
    #
    # Güvenlik ağı: buton bulunamazsa (JS engellenirse, seçici değişirse)
    # varsayılan davranış korunur ve eski href yolu çalışır.
    # CSS butonlardan ÖNCE gönderilir: sonra gönderilirse butonlar ilk çizimde
    # bir an görünüp sonra kayboluyor (yüklenirken ekranda "git" yazıları belirir).
    st.markdown("""
    <style>
    /* Butonlar ekran dışında tutulur. display:none KULLANILMAZ — bazı
       tarayıcılarda gizli öğeye programatik tıklama güvenilir çalışmaz. */
    .st-key-gizli_detay_butonlari{
        position:fixed !important; left:-9999px !important; top:0 !important;
        width:1px !important; height:1px !important; overflow:hidden !important;
    }
    </style>
    """, unsafe_allow_html=True)

    with st.container(key="gizli_detay_butonlari"):
        for _lok_id, _ in lok_sira:
            if st.button("git", key=f"gizli_detay_{_lok_id}"):
                st.session_state["detay_lokasyon"] = _lok_id
                st.rerun()

    _components.html("""
    <script>
    (function(){
      var d;
      try { d = window.parent.document; } catch(e) { return; }  // erişilemezse yedek yol kalsın
      var kartlar = d.querySelectorAll('a.lok-kart');
      for (var i = 0; i < kartlar.length; i++){
        var a = kartlar[i];
        if (a.dataset.baglandi === '1') continue;   // her rerun'da tekrar bağlanmasın
        a.dataset.baglandi = '1';
        a.addEventListener('click', function(ev){
          var lok = this.getAttribute('data-lok');
          var btn = d.querySelector('.st-key-gizli_detay_' + lok + ' button');
          if (btn){
            ev.preventDefault();      // tam sayfa yüklemesini engelle
            btn.click();              // aynı oturumda rerun
          }
          // btn yoksa: preventDefault cagrilmaz, href ile eski yol calisir
        });
      }
    })();
    </script>
    """, height=0)

    st.markdown("<div style='margin-top:8px;'></div>", unsafe_allow_html=True)

    # ── Global Özet (ANLIK) ──
    # Tüm lokasyonların canlı sayaçlarından ANLIK toplamlar (kW). Geçmiş /
    # aylık değerler kaldırıldı (22.10.2026). Canlı sayacı olmayan kalemlerde
    # sayı uydurulmaz: "canlı sayaç yok" yazılır; sayaç bağlanınca kendiliğinden dolar.
    st.markdown('<div class="sec">' + _ik.ikon("enerji", 17) + 'GLOBAL ÖZET — ANLIK</div>', unsafe_allow_html=True)

    def _canli_topla(alan):
        degerler = [v[alan] for v in CANLI.values() if v.get(alan) is not None]
        return (sum(degerler), len(degerler)) if degerler else (None, 0)

    _sebeke_top, _sebeke_n = _canli_topla("sebeke")
    _sog_top, _sog_n       = _canli_topla("sogutma")
    _koj_top, _koj_n       = _canli_topla("kojen")
    _gaz_top, _gaz_n       = _canli_topla("dogalgaz")
    _su_top, _su_n         = _canli_topla("su")
    # Toplam enerji = şebeke + kojen üretimi (kojen canlı ölçülüyorsa)
    _top_enerji = (None if _sebeke_top is None and _koj_top is None
                   else (_sebeke_top or 0) + (_koj_top or 0))
    _yaslar = [v["yas"] for v in CANLI.values() if v.get("yas") is not None]

    def _alt(n, ek=""):
        return f"{n} lokasyon canlı{ek}" if n else ""

    # (etiket, değer | None, alt satır, birim, tıklama anahtarı) — anahtar SONDA
    # kalır: test_ozet_karsilastirma kart listesini buradan okur.
    _metrikler = [
        ("Toplam Enerji", _top_enerji,
         _alt(_sebeke_n, " · şebeke + kojen" if _koj_n else " · şebeke (kojen canlı ölçülmüyor)"),
         "kW", "enerji"),
        ("Doğalgaz",      _gaz_top, _alt(_gaz_n, " · kazan + kojen"), "m³/h", "dogalgaz"),
        ("Soğutma",       _sog_top, _alt(_sog_n, " · chiller + kule"), "kW", "sogutma"),
        ("Su",            _su_top, _alt(_su_n), "m³/h", "su"),
        ("Kojen Üretim",  _koj_top, _alt(_koj_n), "kW", "kojen"),
    ]

    # Özet kaleminin geçişi: hangi canlı alanların toplamı olduğu
    _OZET_ALAN = {"enerji": ("sebeke", "kojen"), "dogalgaz": ("dogalgaz",),
                  "sogutma": ("sogutma",), "su": ("su",), "kojen": ("kojen",)}

    for _lbl, _deger, _alt_metin, _birim, _ozet_key in _metrikler:
        _g_ozet = gecis_toplami([GECIS.get((_l, _a)) for _l in CANLI
                                 for _a in _OZET_ALAN.get(_ozet_key, ())])
        if _deger is None:
            _deger_html = ('<span style="font-size:10px;font-weight:600;color:#9aa3b2;">'
                           'canlı sayaç yok</span>')
        else:
            _deger_html = (f'<span style="font-size:12px;font-weight:700;color:#2a78d6;'
                           f'font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;">'
                           f'<span class="canli-sayi" data-deger="{_deger:.2f}" data-ond="0" '
                           f'data-faz="ozet-{_ozet_key}"{gecis_ozellik(_g_ozet)}>'
                           f'{kw_metin(_deger)}</span> {_birim}</span>')
        _alt_html = (f'<div style="font-size:9px;color:#46536b;margin-top:2px;">'
                     f'<span style="display:inline-block;width:6px;height:6px;border-radius:50%;'
                     f'background:#0ca30c;margin-right:4px;vertical-align:middle;"></span>{_alt_metin}</div>') if _alt_metin else ""

        # Tıklanabilir metrikler <a> ile sarılır (karşılaştırma sayfasını açar);
        # JS gizli butona tıklatır → aynı oturumda rerun, sayfa yeniden yüklenmez.
        _ic = f"""
          <div style="display:flex; justify-content:space-between; align-items:center;">
            <span style="font-size:11px; color:#46536b; display:inline-flex; align-items:center; gap:7px;">{_ik.ikon(_ozet_key, 18)}{_lbl}{
                ' <span style="font-size:9px;color:#133273;">›</span>'
                if _ozet_key else ''}</span>
            {_deger_html}
          </div>
          {_alt_html}"""
        _kr = _ik.renk(_ozet_key)
        _stil = (f"--k:{_kr};padding:7px 10px; margin:3px 0; background:#fafaf8;"
                 f"border-radius:8px; border:1.5px solid {_kr};"
                 f"box-shadow:0 6px 14px -12px {_kr};"
                 "display:block; text-decoration:none;")
        if _ozet_key:
            st.markdown(
                f'<a class="ozet-kart" data-ozet="{_ozet_key}" href="?ozet={_ozet_key}" '
                f'style="{_stil}cursor:pointer;">{_ic}</a>',
                unsafe_allow_html=True)
        else:
            st.markdown(f'<div style="{_stil}">{_ic}</div>', unsafe_allow_html=True)

    # Not: ölçüm yaşı ekrana yazılmıyor — sahadaki saat dilimi kayması
    # (olcum_zamani 3 saat ileri görünüyor) düzeltilene kadar yanlış çıkar.
    if _yaslar:
        st.markdown(
            '<div style="font-size:9px;color:#6b7280;margin:2px 2px 0;">'
            'Anlık değerler · '
            + ("her saniye güncellenir" if _demo_modu() else "10 sn'de bir yenilenir")
            + '</div>',
            unsafe_allow_html=True)

    if _metrikler:
        # Tıklanabilir metrikler için gizli butonlar + JS köprüsü
        _tiklanabilir = [k for *_, k in _metrikler if k]
        if _tiklanabilir:
            st.markdown("""
            <style>
            .st-key-gizli_ozet_butonlari{
                position:fixed !important; left:-9999px !important; top:0 !important;
                width:1px !important; height:1px !important; overflow:hidden !important;
            }
            a.ozet-kart:hover{ border-color:var(--k,#133273) !important; filter:brightness(1.03); }
            </style>
            """, unsafe_allow_html=True)
            with st.container(key="gizli_ozet_butonlari"):
                for _k in _tiklanabilir:
                    if st.button("git", key=f"gizli_ozet_{_k}"):
                        st.session_state["detay_ozet"] = _k
                        st.rerun()
            _components.html("""
            <script>
            (function(){
              var d;
              try { d = window.parent.document; } catch(e) { return; }
              var kartlar = d.querySelectorAll('a.ozet-kart');
              for (var i = 0; i < kartlar.length; i++){
                var a = kartlar[i];
                if (a.dataset.baglandi === '1') continue;
                a.dataset.baglandi = '1';
                a.addEventListener('click', function(ev){
                  var k = this.getAttribute('data-ozet');
                  var btn = d.querySelector('.st-key-gizli_ozet_' + k + ' button');
                  if (btn){ ev.preventDefault(); btn.click(); }
                  // btn yoksa href ile eski yol calisir
                });
              }
            })();
            </script>
            """, height=0)

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
        d_renk = "#0ca30c" if online else ("#6b7280" if fark_dk is None else "#d03b3b")
        # Nokta boyu minimal (26.10.2026): eskiden 10-22 px, şimdi 7-12 px
        boyut  = max(7, min(12, kwh / 2500)) if kwh > 0 else 6
        harita_js.append({
            "id":    lok_id,
            "isim":  lok_info["isim"],
            "kisa":  lok_info["kisa"],
            "lat":   lok_info["lat"],
            "lon":   lok_info["lon"],
            "durum": durum,
            "m2":    f"{lok_info['m2']:,}",
            "renk":  d_renk,
            "boyut": boyut,
            "online": bool(online),
        })

    hjs = json.dumps(harita_js, ensure_ascii=False)

    # ── Açılış görünümü: İSTANBUL ─────────────────────────────────────────
    # Harita Türkiye geneline (zoom 5) açılıyordu; hastanelerin çoğu İstanbul'da
    # olduğu için her yenilemede elle yakınlaştırmak gerekiyordu. Artık İstanbul
    # sınırındaki lokasyonlara göre otomatik çerçevelenir. Kullanıcı uzaklaştırıp
    # diğer şehirleri görebilir; bir kez haritaya dokunduktan sonra görünüm
    # ZORLANMAZ (aşağıdaki kullaniciOynadi bayrağı).
    # Sınır İstanbul İLİ ile kısıtlı: doğu ucu Pendik/Tuzla (~29.35). Kocaeli
    # (lon 29.94) dahil edilince çerçeve doğuya kayıp İstanbul'u küçültüyordu.
    _IST_SINIR = {"lat": (40.75, 41.45), "lon": (27.90, 29.60)}
    _ist = [(h["lat"], h["lon"]) for h in harita_js
            if _IST_SINIR["lat"][0] <= h["lat"] <= _IST_SINIR["lat"][1]
            and _IST_SINIR["lon"][0] <= h["lon"] <= _IST_SINIR["lon"][1]]
    if len(_ist) >= 2:
        _odak = json.dumps([[min(p[0] for p in _ist), min(p[1] for p in _ist)],
                            [max(p[0] for p in _ist), max(p[1] for p in _ist)]])
    elif len(_ist) == 1:
        _odak = json.dumps([[_ist[0][0] - 0.12, _ist[0][1] - 0.18],
                            [_ist[0][0] + 0.12, _ist[0][1] + 0.18]])
    else:
        _odak = "null"   # İstanbul'da lokasyon yoksa Türkiye geneli görünümü kalır

    # ── SUNUM: Genel Müdürlük + lokasyonlardan gelen hareketli kavisli oklar ──
    # YALNIZCA demo/simülasyon modunda haritaya eklenir (üretim haritası aynı kalır).
    # Ataşehir'e genel müdürlük binası konur; diğer her lokasyondan oraya kavisli,
    # akan bir ok çizilir — YALNIZCA çevrimiçi lokasyonlardan (turkuaz).
    # Çevrimdışı ve kurulmamış lokasyonlardan ok çıkmaz.
    _saldiri_js = _SALDIRI_JS if _demo_modu() else ""

    harita_html = f"""<!DOCTYPE html>
<html><head>
<meta charset="utf-8">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<!-- Altlık MapLibre vektör; işaretçiler Leaflet'te kalsın diye köprü eklentisi -->
<link rel="stylesheet" href="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.css"/>
<script src="https://unpkg.com/maplibre-gl@4.7.1/dist/maplibre-gl.js"></script>
<script src="https://unpkg.com/@maplibre/maplibre-gl-leaflet@0.0.22/leaflet-maplibre-gl.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ background:#fafaf8; }}
#map {{ width:100%; height:100vh; background:#fafaf8; }}
.leaflet-container {{ background:#ecebe8 !important; font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif,sans-serif; }}
.leaflet-popup-content-wrapper {{
    background:#fafaf8 !important;
    !important;
    border:1px solid rgba(24,26,30,0.10) !important;
    border-radius:14px !important;
    box-shadow:0 1px 1px rgba(20,22,26,.05),0 10px 22px -12px rgba(20,22,26,.22),inset 0 1px 0 rgba(255,255,255,.95) !important;
    padding:0 !important;
}}
.leaflet-popup-content {{ margin:0 !important; color:#0f1f3d !important; }}
.leaflet-popup-tip-container {{ display:none; }}
.leaflet-popup-close-button {{ color:#133273 !important; font-size:16px !important; top:8px !important; right:10px !important; }}
.leaflet-control-zoom a {{
    background:rgba(243,246,251, 0.7) !important;
    color:#2a78d6 !important;
    border-color:#133273 !important;
}}
.leaflet-control-zoom a:hover {{ background:rgba(243,246,251, 0.9) !important; }}

/* Altlık koyu vektör olduğu için CSS ile koyultma gerekmiyor;
   yalnızca portalın lacivert tonuna hafifçe yaklaştırılır. */
.leaflet-gl-layer {{
    filter: saturate(0.6) hue-rotate(-10deg) brightness(0.95);
}}

/* Veri OpenStreetMap kaynaklı — lisans atıf zorunlu kılar, küçük gösterilir. */
.leaflet-control-attribution {{
    background:rgba(2,6,23,0.55) !important;
    color:#46536b !important;
    font-size:8px !important;
    padding:1px 5px !important;
    border-radius:4px 0 0 0 !important;
}}
.leaflet-control-attribution a {{ color:#133273 !important; text-decoration:none; }}
@keyframes breathe-outer {{
    0%,100% {{ opacity:0.08; transform:scale(0.94); }}
    50%      {{ opacity:0.20; transform:scale(1.10); }}
}}
@keyframes breathe-inner {{
    0%,100% {{ opacity:0.18; transform:scale(0.97); }}
    50%     {{ opacity:0.38; transform:scale(1.06); }}
}}
</style>
</head><body>
<div id="map"></div>
<script>
var map = L.map('map', {{
    center: [39.0, 35.0],
    zoom: 5,
    minZoom: 4,                 // uzaklaşınca Türkiye geneli görünebilsin
    zoomControl: true,
    attributionControl: true,   // OSM lisansı atıf zorunlu kılıyor (CSS ile küçültüldü)
    preferCanvas: true
}});

// VersaTiles "eclipse" — koyu vektör altlık, API anahtarı GEREKTİRMEZ.
//
// GEÇMİŞ: Önce CartoDB "dark_all" kullanılıyordu; CARTO politikasını
// değiştirip anahtarsız isteklere "API KEY REQUIRED" filigranı basmaya
// başladı. Ardından OpenStreetMap denendi ama sokak detayı yüzünden kontrol
// paneli için fazla kalabalıktı.
//
// Altlık MapLibre (vektör), işaretçiler ise Leaflet. İkisini birleştirmek için
// maplibre-gl-leaflet köprüsü kullanılır: böylece mevcut hastane ikonları,
// nefes alan glow halkaları ve popup'lar olduğu gibi korunur.
// YEDEK ALTLIK (tablet/iPad) — MapLibre WebGL2 ister ve harita data: URL
// iframe'inde açıldığı için bazı tarayıcılarda (özellikle iPad Safari) worker
// başlatamayıp altlığı hiç çizmez: işaretçiler görünür, harita bomboş kalır.
// WebGL2 yoksa, MapLibre hata verirse ya da 5 sn içinde yüklenmezse
// anahtarsız açık gri RASTER altlığa geçilir.
var glKatman = null;
var yedekAktif = false;
function yedekAltlik() {{
    if (yedekAktif) return;
    yedekAktif = true;
    try {{ if (glKatman) {{ map.removeLayer(glKatman); }} }} catch (e) {{}}
    glKatman = null;
    L.tileLayer(
        'https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{{z}}/{{y}}/{{x}}',
        {{ maxZoom: 16, attribution: '&copy; Esri, OpenStreetMap' }}
    ).addTo(map);
}}
function webgl2Var() {{
    try {{ return !!document.createElement('canvas').getContext('webgl2'); }}
    catch (e) {{ return false; }}
}}
if (typeof L.maplibreGL !== 'function' || !webgl2Var()) {{
    yedekAltlik();
}} else {{
    try {{
        glKatman = L.maplibreGL({{
            style: 'https://tiles.versatiles.org/assets/styles/gray/style.json',
            attribution: '&copy; OpenStreetMap'
        }}).addTo(map);
        var _ml = glKatman.getMaplibreMap ? glKatman.getMaplibreMap() : null;
        var _yuklendi = false;
        if (_ml) {{
            _ml.on('load', function() {{ _yuklendi = true; }});
            _ml.on('error', function() {{ if (!_yuklendi) {{ yedekAltlik(); }} }});
        }}
        setTimeout(function() {{ if (!_yuklendi) {{ yedekAltlik(); }} }}, 5000);
    }} catch (e) {{
        yedekAltlik();
    }}
}}

// BOYUT TAZELEME — Streamlit bileşen çerçevesi ilk anda sıfır/yanlış
// yükseklikte açılabiliyor. MapLibre o anda çizim yapamaz ve kendiliğinden
// yenilemez; sonuç: işaretçiler görünür ama ALTLIK BOŞ kalır.
// Bu yüzden yerleşim oturduktan sonra hem Leaflet hem MapLibre yeniden ölçülür.
// AÇILIŞ ODAĞI — İstanbul. Kullanıcı haritaya dokunduğu anda (tekerlek, sürükleme,
// zoom düğmesi) görünüm bir daha ZORLANMAZ; uzaklaşıp diğer şehirlere bakabilir.
var ISTANBUL_SINIR = {_odak};
var kullaniciOynadi = false;
['wheel', 'mousedown', 'touchstart', 'dblclick'].forEach(function(olay) {{
    map.getContainer().addEventListener(olay, function() {{ kullaniciOynadi = true; }}, {{ passive: true }});
}});
map.on('zoomstart', function(e) {{ if (e.hard) {{ kullaniciOynadi = true; }} }});

function haritayiOdakla() {{
    if (kullaniciOynadi || !ISTANBUL_SINIR) return;
    try {{
        map.fitBounds(ISTANBUL_SINIR, {{ padding: [38, 38], maxZoom: 11, animate: false }});
    }} catch (e) {{}}
}}

function haritaTazele() {{
    try {{
        map.invalidateSize();
        var ml = (glKatman && glKatman.getMaplibreMap) ? glKatman.getMaplibreMap() : null;
        if (ml) {{ ml.resize(); }}
        // Çerçeve boyutu oturduktan SONRA odaklanılır: ilk anda kap yüksekliği
        // 0 olabiliyor, o anda yapılan fitBounds yanlış zoom veriyordu.
        haritayiOdakla();
    }} catch (e) {{}}
}}
[100, 400, 1200].forEach(function(ms) {{ setTimeout(haritaTazele, ms); }});
window.addEventListener('resize', haritaTazele);
if (window.ResizeObserver) {{
    new ResizeObserver(haritaTazele).observe(document.getElementById('map'));
}}

var hospitals = {hjs};
var CANLI_HARITA = {{}};   // lok_id → {{sebeke, kojen}} (kW metni ya da null)
var POPUPLAR = [];

hospitals.forEach(function(h) {{
    var s  = h.boyut;
    var c  = h.renk;
    var hs = s / 2;

    // ── Dış glow halkası ──
    L.marker([h.lat, h.lon], {{
        icon: L.divIcon({{
            className:'',
            html:'<div style="width:'+(s*2.2)+'px;height:'+(s*2.2)+'px;background:'+c+';border-radius:50%;animation:breathe-outer 3s ease-in-out infinite;"></div>',
            iconSize:[s*2.2, s*2.2], iconAnchor:[s*1.1, s*1.1]
        }}),
        interactive:false, zIndexOffset:-200
    }}).addTo(map);

    // ── İç glow halkası ──
    L.marker([h.lat, h.lon], {{
        icon: L.divIcon({{
            className:'',
            html:'<div style="width:'+(s*1.5)+'px;height:'+(s*1.5)+'px;background:'+c+';border-radius:50%;animation:breathe-inner 3s ease-in-out infinite;"></div>',
            iconSize:[s*1.5, s*1.5], iconAnchor:[s*0.75, s*0.75]
        }}),
        interactive:false, zIndexOffset:-100
    }}).addTo(map);

    // ── Ana nokta ──
    var dot = L.marker([h.lat, h.lon], {{
        icon: L.divIcon({{
            className:'',
            html:'<div style="width:'+s+'px;height:'+s+'px;background:'+c+';border-radius:50%;border:1.5px solid rgba(19,50,115,0.28);box-shadow:0 0 6px '+c+',0 0 3px rgba(19,50,115,0.25);"></div>',
            iconSize:[s, s], iconAnchor:[hs, hs]
        }}),
        zIndexOffset:100
    }}).addTo(map);

    // ── Etiket ──
    L.marker([h.lat, h.lon], {{
        icon: L.divIcon({{
            className:'',
            html:'<div style="color:#0f1f3d;font-size:8px;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;font-weight:700;white-space:nowrap;letter-spacing:1.5px;text-shadow:0 1px 3px rgba(255,255,255,0.95),0 0 6px rgba(255,255,255,0.9);padding-left:4px;padding-top:2px;">'+h.kisa+'</div>',
            iconSize:[100,16], iconAnchor:[-hs-2, hs-2]
        }}),
        interactive:false, zIndexOffset:300
    }}).addTo(map);

    // ── Popup: ANLIK şebeke + kojen ──
    // Değerler haritaya ana sayfadan postMessage ile gelir (aşağıda). Harita
    // HTML'i bu yüzden her yenilemede DEĞİŞMEZ: iframe yeniden yüklenmez,
    // yakınlaştırma ve açık pencere kaybolmaz.
    function popupIcerik() {{
        var v = CANLI_HARITA[h.id] || {{}};
        function satir(ikon, ad, deger) {{
            var sag = (deger === null || deger === undefined)
                ? '<span style="font-size:10px;color:#9aa3b2;font-weight:600;">canlı sayaç yok</span>'
                : '<b style="color:#0f1f3d;font-size:14px;">'+deger+'</b> <span style="font-size:10px;color:#46536b;">kW</span>';
            return '<div style="display:flex;justify-content:space-between;align-items:baseline;gap:12px;font-size:11px;color:#24324d;margin-bottom:5px;">'
                 + '<span>'+ikon+' '+ad+'</span><span>'+sag+'</span></div>';
        }}
        return '<div style="padding:14px 16px;min-width:190px;">' +
            '<div style="font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;font-size:9px;color:'+c+';font-weight:700;letter-spacing:2px;margin-bottom:6px;">'+h.isim.toUpperCase()+'</div>' +
            '<div style="display:flex;align-items:center;gap:5px;margin-bottom:10px;">' +
            '<div style="width:7px;height:7px;border-radius:50%;background:'+c+';box-shadow:0 0 6px '+c+';"></div>' +
            '<span style="font-size:9px;color:'+c+';font-weight:600;">'+h.durum+'</span></div>' +
            satir('⚡', 'Şebeke', v.sebeke) +
            satir('⚙️', 'Kojen üretim', v.kojen) +
            '<div style="font-size:9px;color:#6b7280;margin-top:6px;">Anlık değer · 📐 '+h.m2+' m²</div>' +
            '</div>';
    }}
    dot.bindPopup(popupIcerik, {{ maxWidth:240, className:'' }});
    POPUPLAR.push({{ dot: dot, icerik: popupIcerik }});
}});
{_saldiri_js}

// Ana sayfadan gelen anlık değerler: {{tip:'synapse-canli', veri:{{lok:{{sebeke,kojen}}}}}}
window.addEventListener('message', function(ev) {{
    var m = ev.data;
    if (!m || m.tip !== 'synapse-canli' || !m.veri) return;
    CANLI_HARITA = m.veri;
    POPUPLAR.forEach(function(p) {{
        var pu = p.dot.getPopup();
        if (pu && pu.isOpen()) {{ pu.setContent(p.icerik()); }}
    }});
}});
</script>
</body></html>"""

    st.markdown('<div class="sec">' + _ik.ikon("harita", 17) + 'HASTANE ENERJİ AĞI</div>', unsafe_allow_html=True)
    import base64, streamlit.components.v1 as _cv1
    _b64 = base64.b64encode(harita_html.encode("utf-8")).decode()
    # Taban boy 640 px (eskiden 900). Son boyu aşağıdaki hizalama betiği verir:
    # üç sütunun alt kenarı aynı hizaya gelir.
    _cv1.iframe(f"data:text/html;base64,{_b64}", height=640, scrolling=False)

    # Haritaya ANLIK değerleri ilet (iframe yeniden yüklenmeden). Harita her
    # yenilemede aynı kalır; değerler postMessage ile gider. İlk açılışta
    # harita henüz yüklenmemiş olabilir → birkaç kez tekrar gönderilir.
    _harita_canli = {
        _lid: {"sebeke": (kw_metin(_v["sebeke"]) if _v.get("sebeke") is not None else None),
               "kojen":  (kw_metin(_v["kojen"])  if _v.get("kojen")  is not None else None)}
        for _lid, _v in CANLI.items()
    }
    _components.html("""
<script>
(function () {
  var veri = %s;
  function gonder() {
    var d;
    try { d = window.parent.document; } catch (e) { return; }
    var cerceveler = d.querySelectorAll('iframe[src^="data:text/html;base64"]');
    for (var i = 0; i < cerceveler.length; i++) {
      try { cerceveler[i].contentWindow.postMessage({tip: 'synapse-canli', veri: veri}, '*'); } catch (e) {}
    }
  }
  [0, 400, 1200, 3000].forEach(function (ms) { setTimeout(gonder, ms); });
})();
</script>
""" % json.dumps(_harita_canli, ensure_ascii=False), height=0)

    # ── Saniyelik akış ──
    # Ana sayfanın tamamı 1,5-3 sn'de çiziliyor; saniyede bir yeniden çizmek
    # ekranı sürekli "çalışıyor" bırakırdı. Bunun yerine tarayıcı kartları,
    # W/m²'yi, global özeti ve harita penceresini her saniye günceller:
    #   GERÇEK SİSTEM: sahadan gelen önceki ölçümden son ölçüme geçiş — her
    #   değer iki gerçek ölçümün arasında, yeni değer UYDURULMAZ.
    #   SUNUM: örnek değerin etrafında ±%4 dalga.
    if _demo_modu():
        _akis_taban = {_lid: {"sebeke": _v.get("sebeke"), "kojen": _v.get("kojen")}
                       for _lid, _v in CANLI.items()}
        _components.html(_canli_akis_betigi(_akis_taban, "dalga"), height=0)
    else:
        _akis_taban = {_lid: {_a: (GECIS.get((_lid, _a)) if gecis_ozellik(GECIS.get((_lid, _a)))
                                   else _v.get(_a)) for _a in ("sebeke", "kojen")}
                       for _lid, _v in CANLI.items()}
        _components.html(_canli_akis_betigi(_akis_taban, "gecis"), height=0)

    # ── Veri hazırlığı: Chiller Set & Dış Hava (sağ kolonda gösterilecek) ──
    chiller_vals = {}
    dis_hava_val = fetch_dis_hava()
    _CANLI_ROZET = ("<span style='display:inline-flex;align-items:center;gap:4px;'>"
                    + _ik.nokta("#0ca30c", 6) + "Canlı</span>")
    _DB_ROZET = ("<span style='display:inline-flex;align-items:center;gap:3px;'>"
                 + _ik.ikon("grafik", 11) + "DB</span>")
    _dis_hava_kaynak = _CANLI_ROZET if dis_hava_val is not None else _DB_ROZET
    if dis_hava_val is not None:
        _dis_hava_log_yaz(url, key, dis_hava_val, "lokasyon_pc")
    min_val = max_val = min_isim = max_isim = min_renk = max_renk = None
    # Her lokasyonun KENDİ chiller set'i ve KENDİ dış hava değeri.
    # Kart eskiden yalnızca min/max rozetini ve İstanbul'un dış havasını
    # gösteriyordu; Ankara/İzmir/Adana gibi farklı iklimlerdeki hastanelerin
    # değerleri hiç görünmüyordu.
    lok_sicaklik = {}
    if not df_all.empty and "Chiller_Set_Temp_C" in df_all.columns:
        son_veri = df_all.sort_values("Tarih").groupby("lokasyon_id").last().reset_index()
        for _, row in son_veri.iterrows():
            lok_id = row["lokasyon_id"]
            _set = float(row["Chiller_Set_Temp_C"]) \
                if pd.notna(row.get("Chiller_Set_Temp_C", float("nan"))) else None
            _dis = float(row["Dis_Hava_Sicakligi_C"]) \
                if pd.notna(row.get("Dis_Hava_Sicakligi_C", float("nan"))) else None
            if _set is not None:
                chiller_vals[lok_id] = _set
            if _set is not None or _dis is not None:
                lok_sicaklik[lok_id] = {"set": _set, "dis": _dis}
            if dis_hava_val is None and _dis is not None:
                dis_hava_val = _dis
                _dis_hava_kaynak = _DB_ROZET
        if chiller_vals:
            min_lok = min(chiller_vals, key=chiller_vals.get)
            max_lok = max(chiller_vals, key=chiller_vals.get)
            min_val = chiller_vals[min_lok]
            max_val = chiller_vals[max_lok]
            min_renk = HASTANELER.get(min_lok, {}).get("renk", "#2a78d6")
            max_renk = HASTANELER.get(max_lok, {}).get("renk", "#c98500")
            min_isim = HASTANELER.get(min_lok, {}).get("kisa", min_lok)
            max_isim = HASTANELER.get(max_lok, {}).get("kisa", max_lok)


# ════════════════════════════════
# SAĞ KOLON
# ════════════════════════════════
with sag:
    # ── Canlı Uyarılar ──
    st.markdown('<div class="sec" style="display:flex;align-items:center;gap:6px;">'
                + _ik.ikon("alarm", 17) + 'CANLI UYARILAR</div>', unsafe_allow_html=True)

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
        # Veri toplama alarmları (lokasyon heartbeat'i: bakim_ozet.veri_alarm)
        # Analizör bağlantı hatası ya da boş günlük veri. Lokasyondaki Enerji
        # portalının bildirim çubuğuyla AYNI listedir (veri_alarm.py üretir).
        _va = ozet.get("veri_alarm") or {}
        if _va.get("toplam"):
            _kritik = _va.get("kritik", 0)
            for _m in (_va.get("mesajlar") or [])[:2]:
                lok_uyari_map[lok_id].append(
                    ("r" if _kritik else "y", f"{'🔌' if _kritik else '📉'} {isim}: {_m}"))
            _kalan = _va["toplam"] - len(_va.get("mesajlar") or [])
            if _kalan > 0:
                lok_uyari_map[lok_id].append(
                    ("y", f"📉 {isim}: {_kalan} analizör uyarısı daha"))

        # Aylık bakım işareti uyarısı (ayın 25'inden itibaren, lokasyon heartbeat'inden gelir)
        aylik = ozet.get("aylik_bakim") or {}
        if aylik.get("uyari"):
            lok_uyari_map[lok_id].append(
                ("r", f"🔧 {isim}: {aylik.get('ay','Bu ay')} santral bakımları YAPILMADI (işaret girilmedi)")
            )

    # 2) Enerji verisi uyarıları
    if not df_all.empty:
        son_gun = df_all[df_all["Tarih"].dt.strftime("%Y-%m-%d") == dun]
        for lok_id in aktif_loklar:
            isim = HASTANELER.get(lok_id, {}).get("kisa", lok_id)
            lok_son = son_gun[son_gun["lokasyon_id"] == lok_id]
            if lok_son.empty:
                lok_uyari_map.setdefault(lok_id, []).append(("r", f"⚠️ {isim}: Dün için veri yok"))
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
            "<div style='background:rgba(12,163,12,0.07);border:1px solid rgba(12,163,12,0.2);"
            "border-radius:8px;padding:8px 12px;font-size:11px;color:#006300;'>✅ Tüm sistemler normal</div>",
            unsafe_allow_html=True
        )
    else:
        uyari_html = "<div style='max-height:195px;overflow-y:auto;padding-right:4px;scrollbar-width:thin;scrollbar-color:#133273 transparent;'>"
        for lid, uyarilar in lok_ile_uyari:
            lok_inf  = HASTANELER.get(lid, {})
            isim     = lok_inf.get("kisa", lid)
            has_crit = any(s == "r" for s, _ in uyarilar)
            kart_bg  = "rgba(208,59,59,0.06)" if has_crit else "rgba(250,178,25,0.06)"
            kart_br  = "rgba(208,59,59,0.30)" if has_crit else "rgba(250,178,25,0.25)"
            dot_renk = "#d03b3b" if has_crit else "#c98500"
            satirlar = ""
            for sev, msg in uyarilar:
                s_renk = "#b42525" if sev == "r" else "#8a5a00"
                s_bg   = "rgba(208,59,59,0.08)" if sev == "r" else "rgba(250,178,25,0.08)"
                satirlar += (
                    f"<div style='background:{s_bg};border-radius:5px;padding:4px 8px;"
                    f"margin-top:4px;font-size:10px;color:{s_renk};'>{msg}</div>"
                )
            uyari_html += (
                f"<details style='background:{kart_bg};border:1px solid {kart_br};"
                f"border-radius:8px;padding:6px 10px;margin-bottom:5px;cursor:pointer;'>"
                f"<summary style='list-style:none;display:flex;align-items:center;gap:6px;"
                f"font-size:11px;font-weight:600;color:#24324d;'>"
                + _ik.ikon("alarm", 15, dot_renk) +
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
    .slider.on{background:#0ca30c;box-shadow:0 0 10px rgba(12,163,12,0.5);border-color:rgb(12,163,12);}
    .slider.off{background:#374151;box-shadow:none;}
    .slider:before{content:"";position:absolute;height:20px;width:20px;left:3px;bottom:2px;
        background:white;border-radius:50%;transition:.35s;box-shadow:0 1px 3px rgba(19,50,115,.16);}
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
    # Sunumda örnek veri sunucusuna yazılmaz; anahtarın yine de çalıştığı
    # görülsün diye durum oturumda tutulur.
    if _demo_modu() and "_demo_oto_aktif" in st.session_state:
        _oto_aktif_su = bool(st.session_state["_demo_oto_aktif"])
    # DURUM ARTIK LOKASYONDAN GELİYOR.
    # Oto-set kararı lokasyon PC'sinde veriliyor ve durumu lokasyon bazlı
    # anahtara yazıyor: oto_set_son_kontrol_<lokasyon>. En güncel olanı
    # gösteririz. Eski tek anahtar (oto_set_son_kontrol) yedek olarak kalır.
    try:
        with _oaur.urlopen(_oaur.Request(
            url + "/rest/v1/ayarlar?key=like.oto_set_son_kontrol*&select=key,value",
            headers={"apikey":key,"Authorization":"Bearer "+key}), timeout=4) as r:
            _kayitlar = _oajson.loads(r.read())
        _adaylar = []
        for _kv in _kayitlar:
            try:
                _j = _oajson.loads(_kv["value"])
                _j["_kaynak_anahtar"] = _kv["key"]
                _adaylar.append(_j)
            except Exception:
                pass
        if _adaylar:
            _os = sorted(_adaylar, key=lambda x: str(x.get("zaman", "")))[-1]
    except Exception: pass
    try:
        with _oaur.urlopen(_oaur.Request(
            url + "/rest/v1/oto_mod_log?order=created_at.desc&limit=60"
                 "&select=tip,eski_mod,yeni_mod,tahmin_ort,komut_sayisi,created_at,lokasyonlar",
            headers={"apikey":key,"Authorization":"Bearer "+key}), timeout=4) as r:
            _ml_data = _oajson.loads(r.read())
    except Exception: pass

    # ── DURUM LOG'DAN TÜRETİLİR ──────────────────────────────────────────
    # Karar lokasyon PC'sinde veriliyor ve lokasyon `ayarlar` tablosuna
    # YAZAMAZ (anon anahtara yazma yetkisi bilinçli olarak verilmedi —
    # GitHub'da açık olan anahtarla ayar değiştirilebilmesi güvenlik açığı
    # olurdu). Lokasyonun yazabildiği tek yer `oto_mod_log`. Bu yüzden kartın
    # durumu oradan türetilir; yukarıdaki `ayarlar` okuması yalnızca merkezin
    # eski kayıtları için yedektir ve log daha yeniyse devre dışı kalır.
    def _log_zamani(kayit):
        """created_at (UTC) → İstanbul saatinde ISO metin.

        Karşılaştırma ve gösterim aynı saat diliminde olmalı: merkezin eski
        `ayarlar` kaydı İstanbul saatiyle yazılıyordu, log ise UTC. Dönüşüm
        yapılmazsa 3 saatlik fark yüzünden eski kayıt yeni görünür.
        """
        from datetime import timezone as _tzz
        try:
            return datetime.fromisoformat(
                str(kayit.get("created_at", "")).replace("Z", "+00:00")
            ).astimezone(_tzz(timedelta(hours=3))).isoformat()
        except Exception:
            return ""

    try:
        _ch_k  = next((x for x in _ml_data if str(x.get("tip","")).startswith("chiller")), None)
        _dig_k = next((x for x in _ml_data if str(x.get("tip","")).startswith("diger")), None)
        _son_z = max([_log_zamani(x) for x in (_ch_k, _dig_k) if x] or [""])
        # Log VARSA o kazanır. `ayarlar` kaydını artık kimse yazmıyor (merkezin
        # karar döngüsü kapatıldı), dolayısıyla oradaki değer yalnızca geçmişten
        # kalmadır; zaman karşılaştırmasıyla seçmek, geçiş anında yazılmış eski
        # bir kaydın saatlerce kartta kalmasına yol açıyordu.
        if _son_z:
            _t = _fetch_tahmin() or {}
            _yeni = [x for x in (_ch_k, _dig_k) if x and _log_zamani(x) == _son_z]
            _os = {
                "zaman": _son_z,
                "ref_sicaklik": (_ch_k or _dig_k or {}).get("tahmin_ort", "—"),
                "bugun_max": _t.get("bugun_max", "—"),
                "yarin_min": _t.get("yarin_min", "—"),
                "chiller_mod": (_ch_k or {}).get("yeni_mod", "—"),
                "diger_mod":   (_dig_k or {}).get("yeni_mod", "—"),
                # Yalnızca son turda gönderilenler sayılır; bir önceki dönemin
                # kaydı hâlâ listede olabilir.
                "komut_sayisi": sum(int(x.get("komut_sayisi") or 0) for x in _yeni),
                "lokasyonlar": (_ch_k or _dig_k or {}).get("lokasyonlar", ""),
            }
    except Exception: pass

    # Toggle değerleri
    # Durum metni kartın başlığından kaldırıldı (bilgi anahtarın renginde);
    # yalnızca anahtarın ipucu metni için tutulur.
    _sw_ipucu = ("Senaryo AKTİF — kapatmak için tıkla" if _oto_aktif_su
                 else "Senaryo KAPALI — BACnet komut gönderilmiyor, açmak için tıkla")

    # OTO SET durum değerleri
    _os_zaman   = _os.get("zaman","")[:16].replace("T"," ")
    _os_ref     = _os.get("ref_sicaklik", _os.get("tahmin_ort", "—"))
    # Gündüz seti bugünün max'ına, gece seti yarının min'ine bakar
    _os_max     = _os.get("bugun_max", _os.get("yarin_max","—"))
    _os_min     = _os.get("yarin_min","—")
    _os_ch      = _os.get("chiller_mod","—")
    _os_dig     = _os.get("diger_mod","—")
    _os_cnt     = _os.get("komut_sayisi", 0)
    _os_donem   = _os.get("donem","")
    _donem_ikon = "🌞" if _os_donem=="gunduz" else ("🌙" if _os_donem=="gece" else "")

    # ── LOKASYONLARIN OTO-SET SAĞLIĞI ─────────────────────────────────────
    # Lokasyon her heartbeat'te son turda ne yaptığını bildirir
    # (bakim_ozet.oto). Sistem sessizce durduğunda burada görünür — 10 gün
    # boyunca hiç komut gitmediği hâlde kimsenin fark etmemesinin sebebi
    # böyle bir göstergenin olmamasıydı.
    _oto_saglik = []
    _setler_lok = {}            # {lokasyon_id: setler} — lokasyon başına
    _varsayilan_konum = []      # profili girilmemiş (İstanbul'a düşen) lokasyonlar
    _ozel_saatli = []           # genel kural yerine kendi geçiş saatiyle çalışanlar
    _oz_test_saglik = []
    _geri_bildirim_saglik = []
    try:
        with _oaur.urlopen(_oaur.Request(
            url + "/rest/v1/lokasyonlar?select=lokasyon_id,bakim_ozet,ping_zamani",
            headers={"apikey": key, "Authorization": "Bearer " + key}), timeout=4) as r:
            for _lr in _oajson.loads(r.read()):
                _bo = _lr.get("bakim_ozet")
                if isinstance(_bo, str):
                    try:
                        _bo = _oajson.loads(_bo)
                    except Exception:
                        _bo = {}
                _o = (_bo or {}).get("oto")
                if isinstance(_o, dict):
                    _oto_saglik.append((_lr["lokasyon_id"], _o))
                    # Yürürlükteki set değerleri SAHADAN gelir; merkez kendi
                    # tablosunu tutmaz (kural yalnızca oto_set.py'de).
                    # LOKASYON BAŞINA saklanır: setler hastaneye göre değişir
                    # (farklı blok/zon yapısı, farklı işletme tablosu). Tek bir
                    # lokasyonunkini hepsiymiş gibi göstermek yanıltırdı.
                    if isinstance(_o.get("setler"), dict) and _o["setler"]:
                        _setler_lok[_lr["lokasyon_id"]] = _o["setler"]
                    # Hava tahmini koordinatı: lokasyon profilini girmemiş
                    # bir hastane İstanbul varsayılanıyla karar verir. Farklı
                    # şehirde bu SESSİZ bir hatadır (eşik aylarca yanlış
                    # tarafta kalır), bu yüzden ana ekranda sayılır.
                    if (_o.get("konum") or {}).get("kaynak") == "varsayilan":
                        _varsayilan_konum.append(_lr["lokasyon_id"])
                    # Geçiş saatleri lokasyona özel olabilir (ayarlar tablosunda
                    # `oto_gunduz_saat_<lokasyon>` gibi). Hangi hastanenin genel
                    # kuraldan ayrıldığını sahanın bildirdiği kuraldan öğreniriz.
                    if (_o.get("kural") or {}).get("ozel"):
                        _ozel_saatli.append(_lr["lokasyon_id"])
                # Mekanik Zeka öz testi: lokasyon KENDİ ayarlarıyla testleri
                # koşar (oz_test.py). Aynı kod farklı ayarla farklı karar verir;
                # "bende yeşildi" yetmez, sahada da yeşil olmalı.
                _ot = (_bo or {}).get("oz_test")
                if isinstance(_ot, dict) and _ot.get("toplam"):
                    _oz_test_saglik.append((_lr["lokasyon_id"], _ot))
                # Tasarruf önerisi geri bildirimi: öğrenme döngüsünü kurmadan
                # önce sahada ne kadar veri biriktiğini görmek için.
                _gb = (_bo or {}).get("geri_bildirim")
                if isinstance(_gb, dict) and _gb.get("kayit") is not None:
                    _geri_bildirim_saglik.append((_lr["lokasyon_id"], _gb))
    except Exception:
        pass

    # ── Dönem saatleri (kullanıcı tarafından değiştirilebilir) ──
    def _oto_saat_oku(anahtar, varsayilan):
        try:
            with _oaur.urlopen(_oaur.Request(
                url + f"/rest/v1/ayarlar?key=eq.{anahtar}&select=value",
                headers={"apikey": key, "Authorization": "Bearer " + key}), timeout=4) as r:
                d = _oajson.loads(r.read())
            return int(float(d[0]["value"])) if d else varsayilan
        except Exception:
            return varsayilan

    _g_saat  = _oto_saat_oku("oto_gunduz_saat", _OTO_GUNDUZ_VARSAYILAN)
    _ge_saat = _oto_saat_oku("oto_gece_saat",   _OTO_GECE_VARSAYILAN)

    # Panelde ANLIK dönem gösterilir (son kontroldeki değil) — kullanıcı
    # sistemin şu an hangi durumda olduğunu görebilmeli.
    _simdi_saat  = now_display.hour   # İstanbul saati (yukarıda hesaplanıyor)
    _simdi_donem = _donem_hesapla(_simdi_saat, _g_saat, _ge_saat)
    _sd_ikon     = _ik.ikon("gunduz" if _simdi_donem == "gunduz" else "gece", 13)
    _sd_ad       = "GÜNDÜZ" if _simdi_donem == "gunduz" else "GECE"
    _sd_renk     = "#c98500" if _simdi_donem == "gunduz" else "#818cf8"
    _sonraki     = ("%02d:00" % _ge_saat) if _simdi_donem == "gunduz" else ("%02d:00" % _g_saat)
    # Mod adları; SET DEĞERLERİ sahadan gelir (lokasyon detayında gösterilir).
    # Burada sabit
    # set tablosu TUTULMAZ: 01.10'da saha tablosu değiştiğinde buradaki kopya
    # eski değeri göstermeye devam ederdi.
    # Mod adı ayarlar/log'dan gelmiyorsa (ilk kurulum, eski kayıt) sahanın
    # heartbeat'te bildirdiği moda düş — panelde "—" kalmasın.
    # Mod da tek lokasyondan alınmaz: lokasyonlar farklı modda olabilir.
    # Hepsi aynıysa o mod yazılır, değilse "farklı" denir.
    if _os_ch in ("", "—", None) or _os_dig in ("", "—", None):
        _modlar_ch = {(_o or {}).get("chiller_mod") for _l, _o in _oto_saglik
                      if (_o or {}).get("chiller_mod")}
        _modlar_dig = {(_o or {}).get("diger_mod") for _l, _o in _oto_saglik
                       if (_o or {}).get("diger_mod")}
        if _os_ch in ("", "—", None) and _modlar_ch:
            _os_ch = _modlar_ch.pop() if len(_modlar_ch) == 1 else "farkli"
        if _os_dig in ("", "—", None) and _modlar_dig:
            _os_dig = _modlar_dig.pop() if len(_modlar_dig) == 1 else "farkli"
    _CH_IKON = {"koc_soguk": "❄️", "serin": "🌤️", "ilimli": "☀️", "sicak": "🔥"}
    _ch_label   = "%s %s" % (_CH_IKON.get(_os_ch, ""), {"koc_soguk": "Koç soğuk",
                  "serin": "Serin", "ilimli": "Ilımlı", "sicak": "Sıcak",
                  "farkli": "lokasyona göre farklı"}.get(_os_ch, _os_ch))
    _dig_label  = {"yogun_sogutma": "🔆 Yoğun soğutma", "sogutma": "☀️ Soğutma",
                   "isitma": "❄️ Isıtma",
                   "farkli": "lokasyona göre farklı"}.get(_os_dig, _os_dig)
    # NOT: "⚡ N komut gönderildi" satırı karttan KALDIRILDI (11.10.2026) —
    # aynı bilgi geçiş kayıtları penceresinde komut sayısıyla zaten duruyor.

    # Lokasyon sağlık satırları: her lokasyonun son turda ne yaptığı.
    # Normal bekleme yeşil/soluk, gerçek bir engel (tahmin yok, kural
    # okunamadı, BACnet hatası) turuncu-kırmızı gösterilir.
    _SAGLIK_RENK = {
        "yazildi": "#0ca30c", "gecis_yok": "#46536b",
        "tahmin_yok": "#c98500", "kural_okunamadi": "#d03b3b",
        "yazma_hatasi": "#d03b3b", "hata": "#d03b3b",
        "nokta_yok": "#c98500", "kapali": "#46536b",
        "henuz_calismadi": "#c98500", "modul_yok": "#d03b3b",
        "sahada_farkli": "#d03b3b", "dogrulanamadi": "#c98500",
        "uygulanmadi": "#d03b3b", "mesgul": "#46536b",
    }

    # Bir lokasyonun GERÇEK sorunu: anlık tur sonucu normal olsa bile (her
    # dakika "gecis_yok" yazılır) son geçişin sahadaki sonucu ya da chiller'ın
    # seti uygulamaması kalıcı olarak gösterilir.
    _SON_YAZIM_METIN = {
        "yazma_hatasi":  "Son geçişte BACnet yazma hatası",
        "sahada_farkli": "Son geçiş: cihazda farklı değer var",
        "dogrulanamadi": "Son geçiş: cihazdan geri okunamadı",
    }

    def _saglik_sorunu(o):
        _k = str(o.get("sonuc", ""))
        # "mesgul": iki tur çakıştı, biri atlandı — kilit işini yapıyor, sorun değil
        if _k not in ("gecis_yok", "yazildi", "kapali", "mesgul"):
            return _k, str(o.get("metin") or _k)
        _sy = o.get("son_yazim_sonuc")
        if _sy in _SON_YAZIM_METIN:
            return _sy, _SON_YAZIM_METIN[_sy]
        _dg = o.get("dogrulama") or {}
        if _dg.get("sonuc") == "uygulanmadi":
            _uy = ", ".join(str(x).replace("_REM_SET", "") for x in (_dg.get("uymayan") or []))
            return "uygulanmadi", "Set cihazda UYGULANMADI" + (f" ({_uy})" if _uy else "")
        return None, None
    # YALNIZCA dikkat gerektirenler satır satır listelenir; normal beklemedeki
    # lokasyonlar tek satırda özetlenir. Hepsini listelemek kartı 715px'e
    # çıkarıyor, metinleri kırpıyor ve asıl uyarıyı gürültüde kaybediyordu.
    _sorunlu = []
    for _l, _o in _oto_saglik:
        _kod, _metin = _saglik_sorunu(_o)
        if _kod:
            _sorunlu.append((_l, _o, _kod, _metin))
    _normal_sayi = len(_oto_saglik) - len(_sorunlu)

    # SAHA DURUMU artık kendi kartında ve LİSTE olarak gösterilir; 5 satırdan
    # sonrası kaydırmaya girer (kart boyu sabit kalsın, uzun liste kartı
    # 700 px'e çıkarmasın).
    _SAHA_SATIR_PX = 30
    _SAHA_GORUNUR = 5
    _saha_satirlar = []        # (html, ) — sıralı
    for _lid, _o, _sn, _mt in sorted(_sorunlu, key=lambda x: x[0]):
        _ad = HASTANELER.get(_lid, {}).get("kisa", _lid)
        _rk = _SAGLIK_RENK.get(_sn, "#c98500")
        _zm = str(_o.get("zaman") or "")[11:16]
        _saha_satirlar.append(
            f"<div style='font-size:9px;padding:3px 0;line-height:1.35;"
            f"border-bottom:1px solid rgba(24,26,30,0.07);'>"
            f"<span style='color:{_rk};'>●</span> "
            f"<b style='color:#24324d;'>{_ad}</b> "
            f"<span style='color:#46536b;'>{_zm}</span><br>"
            f"<span style='color:{_rk};'>{_mt}</span></div>"
        )

    # NOT: Mekanik Zeka öz testi ve öneri geri bildirimi göstergeleri buradan
    # KALDIRILDI (20.09.2026). Bunlar lokasyona özgü bilgilerdir; genel özet
    # kartında toplanınca lokasyon sayısı arttıkça okunamaz hale geliyordu.
    # Artık her lokasyonun kendi detay sayfasında "SİSTEM SAĞLIĞI" bölümünde
    # gösterilir (pages/lokasyon_detay.py). Genel kartta yalnızca DİKKAT
    # GEREKTİREN oto-set durumları kalır — orası bir alarm yüzeyidir.
    if _oz_test_saglik:
        _oz_kalan = [(l, o) for l, o in _oz_test_saglik if o.get("durum") != "GECTI"]
        for _lid, _o in sorted(_oz_kalan, key=lambda x: x[0]):
            _ad = HASTANELER.get(_lid, {}).get("kisa", _lid)
            _saha_satirlar.append(
                f"<div style='font-size:9px;padding:3px 0;line-height:1.35;"
                f"border-bottom:1px solid rgba(24,26,30,0.07);'>"
                f"<span style='color:#d03b3b;'>●</span> "
                f"<b style='color:#24324d;'>{_ad}</b><br>"
                f"<span style='color:#d03b3b;'>Mekanik Zeka öz testi KALDI "
                f"({_o.get('gecen')}/{_o.get('toplam')}) — detay sayfasına bakın</span></div>"
            )

    # Mod geçiş değerleri
    # startswith kullanılır: dönem geçişinde mod değişmediğinde kayıtlar
    # "chiller_yenileme"/"diger_yenileme" tipiyle yazılıyor. Tam eşitlik
    # arandığında rozet günlük normal işleyişte "🧊 0 · 🌀 0 · Σ 2" gibi
    # bozuk görünüyordu (simülasyonda yakalandı).
    _ml_ch  = [x for x in _ml_data if str(x.get("tip","")).startswith("chiller")]
    _ml_dig = [x for x in _ml_data if str(x.get("tip","")).startswith("diger")]
    _ml_top = len(_ml_data)
    # Mod değişmediyse (dönem yenilemesi) yön oku yerine ↔️ gösterilir;
    # aksi halde "serin → serin" satırı yanıltıcı biçimde ⬇️ görünüyordu.
    _SIRA = ["koc_soguk","serin","ilimli","sicak",
             "isitma","sogutma","yogun_sogutma"]
    _eski_yeni_ikon = lambda e, y: ("↔️" if e == y else
                                    ("⬆️" if _SIRA.index(y) > _SIRA.index(e) else "⬇️"))
    # "Son geçiş" yalnızca GERÇEK mod değişimlerinden seçilir; günlük yeniden
    # gönderim kayıtları (*_yenileme) buraya girmez, yoksa "ilimli → ilimli"
    # gibi geçiş olmayan bir satır gösterilirdi.
    _ml_gecisler = [x for x in _ml_data if x["tip"] in ("chiller", "diger")]
    _son_gecis_html = ""
    if _ml_gecisler:
        _ml_son = _ml_gecisler[0]
        _son_tip = ((_ik.ikon("sogutma", 12) + " Chiller") if _ml_son["tip"] == "chiller"
                    else (_ik.ikon("kollektor", 12) + " Kol/FCU/AHU"))
        try: _son_ok = _eski_yeni_ikon(_ml_son["eski_mod"], _ml_son["yeni_mod"])
        except: _son_ok = "↔️"
        _son_gecis_html = (
            f"<div style='font-size:9px;border-top:1px solid rgba(24,26,30,0.10);"
            f"padding-top:6px;margin-top:6px;color:#46536b;'>"
            f"Son geçiş: {_son_tip} &nbsp;{_son_ok}&nbsp; "
            f"<b style='color:#24324d;'>{_ml_son['eski_mod']}</b> → "
            f"<b style='color:#2a78d6;'>{_ml_son['yeni_mod']}</b> &nbsp;·&nbsp; "
            f"<span style='color:#c98500;'>{_ml_son['tahmin_ort']}°C</span></div>"
        )

    # ── Yürürlükteki set değerleri ──────────────────────────────────────
    # Değerler lokasyonların heartbeat'inden gelir (bakim_ozet.oto.setler);
    # merkezde kural tablosu YOK.
    #
    # ÇOK LOKASYON: setler hastaneye göre değişir (her hastane kendi dış
    # havasına ve kendi işletme tablosuna göre çalışır). Bu yüzden ana
    # ekranda DEĞER gösterilmez; yalnızca "hepsi aynı mı, kaçı farklı"
    # özeti verilir. Değerler lokasyon detay sayfasındadır.
    _ANAHTARLAR = ("chiller", "GUNDUZ_KOLLEKTOR_SET", "GECE_KOLLEKTOR_SET",
                   "A_BLOK_FCU_SET", "B_BLOK_FCU_SET",
                   "ZON1_KLIMA_SANTRALI_SET", "ZON2_KLIMA_SANTRALI_SET")

    def _kiyas_anahtari(setler):
        return tuple(setler.get(a) for a in _ANAHTARLAR)

    _gruplar = {}
    for _lid, _st in _setler_lok.items():
        _gruplar.setdefault(_kiyas_anahtari(_st), []).append(_lid)
    if _gruplar:
        # En çok lokasyonun bildirdiği değer kümesi "aynı" kabul edilir;
        # ayrışanlar isimle sayılır. Değerin kendisi burada kullanılmaz.
        _cogunluk = max(_gruplar.items(), key=lambda kv: len(kv[1]))
        _ayni_sayi = len(_cogunluk[1])
        _farkli_lok = [l for k, ls in _gruplar.items() if k != _cogunluk[0] for l in ls]
    else:
        _ayni_sayi, _farkli_lok = 0, []

    # SETLER özet şeridi karttan KALDIRILDI (11.10.2026): ayrışma bilgisi ve
    # konum uyarısı birer DURUM satırıdır, yerleri SAHA DURUMU listesidir.
    # Değerler zaten lokasyon detayında.
    if _farkli_lok:
        _saha_satirlar.insert(0,
            f"<div style='font-size:9px;padding:3px 0;line-height:1.35;"
            f"border-bottom:1px solid rgba(24,26,30,0.07);'>"
            f"<span style='color:#8a5a00;'>●</span> "
            f"<b style='color:#24324d;'>SETLER</b><br>"
            f"<span style='color:#8a5a00;'>%d lokasyon aynı · %d farklı set (%s%s)"
            f"</span></div>"
            % (_ayni_sayi, len(_farkli_lok),
               ", ".join(HASTANELER.get(l, {}).get("kisa", l)
                         for l in _farkli_lok[:3]),
               "…" if len(_farkli_lok) > 3 else ""))
    elif not _setler_lok:
        _saha_satirlar.insert(0,
            "<div style='font-size:9px;padding:3px 0;line-height:1.35;"
            "border-bottom:1px solid rgba(24,26,30,0.07);'>"
            "<span style='color:#c98500;'>●</span> "
            "<b style='color:#24324d;'>SETLER</b><br>"
            "<span style='color:#c98500;'>Lokasyonlardan set bildirilmedi</span></div>")

    # Hava tahmini koordinatı lokasyonun kendi profilinden gelir; profili
    # girilmemiş hastane İstanbul'a düşer ve yanlış şehrin dış havasına göre
    # karar verir. Kurulum sonrası unutulan bu adım görünür kalsın.
    if _varsayilan_konum:
        _saha_satirlar.insert(0,
            f"<div style='font-size:9px;padding:3px 0;line-height:1.35;"
            f"border-bottom:1px solid rgba(24,26,30,0.07);'>"
            f"<span style='color:#c98500;'>●</span> "
            f"<b style='color:#24324d;'>KONUM</b><br>"
            f"<span style='color:#c98500;'>%d lokasyon varsayılan konumda "
            f"(İstanbul): %s</span></div>"
            % (len(_varsayilan_konum),
               ", ".join(HASTANELER.get(l, {}).get("kisa", l)
                         for l in _varsayilan_konum[:3])
               + ("…" if len(_varsayilan_konum) > 3 else "")))

    # ── SAHA DURUMU kartı ──
    # Başlık + liste; 5 satırdan sonrası kaydırmaya girer.
    if _oto_saglik or _saha_satirlar:
        if _normal_sayi:
            _saha_satirlar.append(
                f"<div style='font-size:9px;padding:3px 0;color:rgb(12,163,12);'>"
                f"✓ {_normal_sayi} lokasyon normal</div>")
    else:
        # Hiç lokasyon bildirim yapmıyorsa bu da bir bilgidir: ya yama
        # inmemiştir ya da süreç çalışmıyordur. Sessiz kalmak yanıltır.
        _saha_satirlar.append(
            "<div style='font-size:9px;padding:3px 0;color:#c98500;'>"
            "⚠ Lokasyonlardan oto-set durumu gelmiyor</div>")

    _saha_kaydir = ("max-height:%dpx;overflow-y:auto;" % (_SAHA_SATIR_PX * _SAHA_GORUNUR)
                    if len(_saha_satirlar) > _SAHA_GORUNUR else "")
    _saglik_html = (
        "<div style='background:#f1f0ed;border:1px solid rgba(24,26,30,0.10);"
        "border-radius:10px;padding:7px 10px;margin-top:10px;'>"
        "<div style='font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;"
        "font-size:8px;font-weight:700;letter-spacing:1.5px;color:#133273;"
        "margin-bottom:3px;'>SAHA DURUMU</div>"
        f"<div style='{_saha_kaydir}'>" + "".join(_saha_satirlar) + "</div></div>"
    )

    # Sağ kolon kartlarının ORTAK başlığı — tek kaynak. Dört kart aynı
    # punto, aynı renk, aynı ayırıcı çizgiyi kullanır; her kart kendi
    # başlığını yazdığında puntolar (8 px / 15 px) tutmuyordu.
    # Kartın SON satırı alt kenara yapışıyordu: Streamlit öğe kapsayıcısının
    # yüksekliği içindeki markdown'dan küçük hesaplanıyor ve kabın
    # padding-bottom'u yutuluyor. Boşluk içeriğin sonuna açıkça eklenir.
    _KART_ALT = "<div style='height:10px;'></div>"

    def _kart_basligi(metin, sag=""):
        return (
            "<div style='display:flex;align-items:center;"
            "justify-content:space-between;gap:8px;margin-bottom:10px;'>"
            "<span style='font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;"
            "font-size:15px;font-weight:800;color:#133273;letter-spacing:1.5px;"
            "display:inline-flex;align-items:center;gap:8px;'>"
            + metin + "</span>"
            + (f"<span style='font-size:9px;color:#46536b;white-space:nowrap;'>{sag}</span>"
               if sag else "")
            + "</div>"
            "<div style='border-top:1px solid rgba(24,26,30,0.10);'></div>"
        )

    # ── OTO SET — TEK KART ───────────────────────────────────────────────
    # Panel üç ayrı parçaya dağılmıştı: HTML kart, altında serbest duran
    # düğme, altında expander, altında bir düğme daha. Her biri kendi
    # çerçevesiyle göründüğü için ekran dağınıktı. Artık hepsi TEK kabın
    # (st.container) içinde; kart çerçevesi kabın kendisine verilir, içerik
    # çerçevesizdir ve düğmeler eşit iki sütunda simetrik durur.
    st.markdown("""
    <style>
    /* ── SYNAPSE KART KALIBI ──
       Sağ kolondaki dört kart (oto set, dış hava, enerji zekası, sabah
       analizi) AYNI kalıbı kullanır: çerçeve kabın kendisindedir, içerik
       çerçevesizdir. Her kart kendi HTML'inde ayrı kutu çizdiğinde
       kenarlıklar, köşe yarıçapları ve başlık boyutları tutmuyordu. */
    .st-key-oto_set_karti,
    .st-key-dis_hava_karti,
    .st-key-enerji_zekasi_karti,
    .st-key-sabah_analiz_karti {
        background:#fafaf8;
        border:1px solid rgba(24,26,30,0.10);
        border-radius:14px;
        padding:0;
        margin-bottom:12px;
        /* overflow:hidden YOK: Streamlit kaba ve öğe kapsayıcısına hesaplanmış
           yükseklik veriyor, verdiğimiz alt boşluk bu yüksekliğin dışında
           kalıyor ve kırpılıyordu — son satır kart dibine yapışık görünürdü.
           Köşeler zaten kabın kendi arka planıyla yuvarlanıyor. */
        height:auto !important;
        min-height:fit-content !important;
        box-shadow:0 1px 1px rgba(20,22,26,.05),
                   0 10px 22px -12px rgba(20,22,26,.22),
                   inset 0 1px 0 rgba(255,255,255,.95);
    }
    /* Streamlit öğe kapsayıcıları genişliği parent'tan MİRAS alıyor; kaba
       padding verilirse içerik taşıyor. Bu yüzden boşluk çocuklara verilir. */
    .st-key-oto_set_karti > div,
    .st-key-dis_hava_karti > div,
    .st-key-enerji_zekasi_karti > div,
    .st-key-sabah_analiz_karti > div {
        box-sizing:border-box;
        padding-left:16px;
        padding-right:16px;
        /* Kap flex sütun: çocuk FLEX ITEM olduğu için kabın hesaplanmış
           yüksekliğine SIKIŞIYOR (shrink) ve verdiğimiz alt boşluk eksiliyordu
           — son satır kart dibine yapışık görünürdü. Çocuk küçülmesin, kap da
           içeriğe göre büyüsün. */
        height:auto !important;
        flex-shrink:0 !important;
    }
    .st-key-oto_set_karti > div:first-child,
    .st-key-dis_hava_karti > div:first-child,
    .st-key-enerji_zekasi_karti > div:first-child,
    .st-key-sabah_analiz_karti > div:first-child { padding-top:14px; }
    .st-key-oto_set_karti > div:last-child,
    .st-key-dis_hava_karti > div:last-child,
    .st-key-enerji_zekasi_karti > div:last-child,
    .st-key-sabah_analiz_karti > div:last-child { padding-bottom:18px; }
    /* İç öğeler de genişliği miras aldığı için padding'in içinde kalmaz;
       %100'e sabitlenince kutunun içine oturur (sağ kenar taşması gider). */
    .st-key-oto_set_karti > div > *,
    .st-key-oto_set_karti [data-testid="stMarkdown"],
    .st-key-oto_set_karti [data-testid="stMarkdownContainer"],
    .st-key-dis_hava_karti > div > *,
    .st-key-dis_hava_karti [data-testid="stMarkdown"],
    .st-key-dis_hava_karti [data-testid="stMarkdownContainer"],
    .st-key-enerji_zekasi_karti > div > *,
    .st-key-enerji_zekasi_karti [data-testid="stMarkdown"],
    .st-key-enerji_zekasi_karti [data-testid="stMarkdownContainer"],
    .st-key-sabah_analiz_karti > div > *,
    .st-key-sabah_analiz_karti [data-testid="stMarkdown"],
    .st-key-sabah_analiz_karti [data-testid="stMarkdownContainer"] {
        width:100% !important;
        max-width:100%;
    }
    /* Kart içindeki düğmeler: OTO SET'teki ölçüyle aynı */
    .st-key-sabah_analiz_karti .stButton {
        display:flex; line-height:0; margin-bottom:8px;
    }
    .st-key-sabah_analiz_karti .stButton > button {
        display:flex !important;
        width:100% !important;
        min-height:34px !important;
        border-radius:10px !important;
        border:1px solid rgba(24,26,30,0.18) !important;
        background:rgba(19,50,115,0.04) !important;
    }
    .st-key-sabah_analiz_karti .stButton > button p {
        font-size:11px; font-weight:700; color:#133273; margin:0;
    }
    .st-key-sabah_analiz_karti .stButton > button:hover {
        border-color:rgba(19,50,115,0.45) !important;
        background:rgba(19,50,115,0.07) !important;
    }
    .st-key-oto_set_karti [data-testid="stVerticalBlock"] { gap:8px; }
    /* Kart dar bir sütunda duruyor (≈300 px): Streamlit bu genişlikte
       sütunları alt alta yığıyor ve anahtar rozetin yanından kayıyordu.
       Yan yana kalsınlar. */
    .st-key-oto_set_karti [data-testid="stHorizontalBlock"] {
        flex-wrap:nowrap !important;
        gap:6px !important;
    }
    .st-key-oto_set_karti [data-testid="stHorizontalBlock"] > div {
        min-width:0 !important;
        /* Sütunların içerik yükseklikleri farklı (rozet 52, saat kartı
           52+tarih). Dikey ortalamada kutuların üst kenarı kayıyordu;
           hepsi satırın ÜSTÜNDEN başlar, tarih aşağı sarkar. */
        display:flex !important;
        flex-direction:column;
        justify-content:flex-start;
    }
    /* Sütunun içindeki dikey blok da içeriği ortalıyor (saat sütununda
       tarih satırı olduğu için kutu aşağı kayıyordu) — o da üstten başlasın */
    .st-key-oto_set_karti [data-testid="stHorizontalBlock"]
        [data-testid="stVerticalBlock"] {
        justify-content:flex-start !important;
        gap:2px !important;
    }
    .st-key-oto_set_karti [data-testid="stHorizontalBlock"]
        [data-testid="stElementContainer"] { margin:0 !important; }
    /* Düğme inline-flex: satır taban çizgisi yüzünden üstünde ~17 px boşluk
       kalıyor ve kutu rozetten aşağıda duruyordu. Blok seviyesine alınır. */
    .st-key-oto_set_karti .stButton { display:flex; line-height:0; }
    .st-key-oto_set_karti .stButton > button { display:flex !important; }
    /* Anahtar sütunu anahtarın kendi genişliğinde SABİT: yakınlaştırınca
       oransal sütun 54 px'ten dar kalıyor ve anahtar kart dışına taşıyordu */
    .st-key-oto_set_karti [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:first-child {
        flex:0 0 56px !important; width:56px !important; min-width:56px !important; max-width:56px !important;
    }
    /* Kutular en az 84 px: kart daralınca (yakınlaştırma) sıkışıp "G…" diye
       kesilmek yerine alt satıra geçer */
    .st-key-oto_set_karti [data-testid="stHorizontalBlock"] { flex-wrap:wrap !important; row-gap:8px !important; }
    .st-key-oto_set_karti [data-testid="stHorizontalBlock"] > [data-testid="stColumn"]:not(:first-child) {
        min-width:84px !important; flex:1 1 84px !important;
    }
    /* Anahtar 30 px: 52 px'lik kutuların ortasına hizalansın */
    .st-key-oto_switch_on button, .st-key-oto_switch_off button {
        margin-top:11px !important;
    }

    /* ── Senaryo anahtarı (Apple tarzı) ──
       Açıkken yeşil, kapalıyken kırmızı; topuz tarafa kayar. Durum iki ayrı
       key ile ayrılır (st-key-...on / ...off), böylece renk ve topuz konumu
       CSS'te kalır, metin gerektirmez. */
    .st-key-oto_switch_on button, .st-key-oto_switch_off button {
        width:54px !important; min-width:54px !important;
        height:30px !important; min-height:30px !important;
        border-radius:999px !important; border:none !important;
        padding:0 !important; position:relative; overflow:hidden;
        box-shadow:inset 0 1px 3px rgba(20,22,26,.25) !important;
        transition:background .2s ease;
    }
    .st-key-oto_switch_on button  { background:#30d158 !important; }
    .st-key-oto_switch_off button { background:#ff453a !important; }
    .st-key-oto_switch_on button *, .st-key-oto_switch_off button * {
        font-size:0 !important; opacity:0;
    }
    .st-key-oto_switch_on button::after, .st-key-oto_switch_off button::after {
        content:""; position:absolute; top:3px; width:24px; height:24px;
        border-radius:50%; background:#fff;
        box-shadow:0 1px 3px rgba(20,22,26,.35);
        transition:left .2s ease;
    }
    .st-key-oto_switch_on button::after  { left:27px; }
    .st-key-oto_switch_off button::after { left:3px; }
    .st-key-oto_switch_on button:hover, .st-key-oto_switch_off button:hover {
        filter:brightness(1.06);
    }

    /* ── Rozet görünümlü düğmeler (GÜNDÜZ kartıyla aynı ölçü) ── */
    .st-key-oto_saat_kart button, .st-key-oto_liste_kart button {
        width:100% !important;
        height:52px !important; min-height:52px !important;
        overflow:hidden;
        border-radius:8px !important;
        border:1px solid rgba(24,26,30,0.18) !important;
        background:rgba(19,50,115,0.04) !important;
        padding:4px 10px !important;
        line-height:1.3;
    }
    .st-key-oto_saat_kart button p, .st-key-oto_liste_kart button p {
        font-size:11px; font-weight:700; color:#133273; margin:0;
    }
    """ + _ik.etiket_css(".st-key-oto_saat_kart button p:first-child", "saat", 14)
        + _ik.etiket_css(".st-key-oto_liste_kart button p:first-child", "kayit", 14) + """
    .st-key-oto_saat_kart button:hover, .st-key-oto_liste_kart button:hover {
        border-color:rgba(19,50,115,0.45) !important;
        background:rgba(19,50,115,0.07) !important;
    }
    </style>
    """, unsafe_allow_html=True)

    _oto_kart = st.container(key="oto_set_karti")

    with _oto_kart:
        st.markdown(
            f"<div>"
            # ── Satır 1: Başlık ──
            # ── Satır 1: KART BAŞLIĞI (ortak kalıp) ──
            # Durum metni ("AKTİF · Senaryo çalışıyor") kaldırıldı: aynı bilgiyi
            # başlığın altındaki anahtar rengiyle veriyoruz.
            + _kart_basligi(_ik.ikon("oto", 22) + "OTO SET") +
            f"</div>",
            unsafe_allow_html=True
        )

        # ── Satır 2: Anahtar + dönem rozeti + iki kart düğme ──────────────
        # Senaryo anahtarı GÜNDÜZ rozetinin yanında duruyor (durumu okurken
        # aynı yerde açıp kapatmak için). Geçiş saatleri ve geçiş listesi de
        # aynı ölçüde kart düğmelerdir; aşağı doğru liste açmak yerine
        # POP-UP (st.dialog) açarlar — kart boyu sabit kalır.
        # Dört öğe TEK SATIRDA: anahtar + dönem rozeti + iki kart düğme.
        # Üç kutu eşit genişlik ve eşit yükseklikte (52 px) durur.
        # vertical_alignment="center" kullanılmaz: Streamlit bunu kısa sütuna
        # margin-top vererek yapıyor ve kutuların üst kenarı kayıyordu
        # (GÜNDÜZ rozeti 7 px aşağıda kalmıştı). Hizayı CSS yapar.
        _k_sw, _k_rozet, _k_saat, _k_liste = st.columns(
            [0.42, 1, 1, 1], vertical_alignment="top")

        with _k_sw:
            _sw_key = "oto_switch_on" if _oto_aktif_su else "oto_switch_off"
            if st.button(" ", key=_sw_key, help=_sw_ipucu, disabled=_IZLEYICI):
                _yeni_deger = "false" if _oto_aktif_su else "true"
                if _demo_modu():
                    # Sunumda örnek veri sunucusuna yazılmaz; anahtar yine de
                    # çalışsın diye durum oturumda tutulur.
                    st.session_state["_demo_oto_aktif"] = (_yeni_deger == "true")
                else:
                    try:
                        _pay = _oajson.dumps({"key": "oto_set_aktif",
                                              "value": _yeni_deger}).encode()
                        _oaur.urlopen(_oaur.Request(
                            url+"/rest/v1/ayarlar", data=_pay, method="POST",
                            headers={"apikey": key, "Authorization": "Bearer "+key,
                                     "Content-Type": "application/json",
                                     "Prefer": "resolution=merge-duplicates"}), timeout=4)
                    except Exception as _e:
                        st.session_state["_oto_switch_hata"] = str(_e)
                st.rerun()

        with _k_rozet:
            st.markdown(
                f"<div style='background:rgba(19,50,115,0.04);border:1px solid {_sd_renk}55;"
                f"border-radius:8px;padding:4px 10px;height:52px;box-sizing:border-box;"
                f"display:flex;flex-direction:column;justify-content:center;"
                f"overflow:hidden;'>"
                f"<div style='font-size:11px;font-weight:700;color:{_sd_renk};"
                f"display:flex;align-items:center;gap:3px;white-space:nowrap;'>"
                f"{_sd_ikon} {_sd_ad}</div>"
                f"<div style='font-size:9px;color:#46536b;margin-top:1px;'>"
                f"sıradaki geçiş {_sonraki}</div>"
                f"</div>", unsafe_allow_html=True)

        with _k_saat:
            # Kısa tutulur: düğme rozetle aynı yükseklikte kalmalı
            _saat_alt = "%02d:00 · %02d:00" % (_g_saat, _ge_saat)
            if _ozel_saatli:
                _saat_alt += " · %d özel" % len(_ozel_saatli)
            if st.button("Saatler  \n%s" % _saat_alt,
                         key="oto_saat_kart", use_container_width=True):
                st.session_state["_oto_popup"] = "saat"
                st.rerun()
            # Son durum zamanı: sıcaklık satırının sağında kayıp duruyordu,
            # ait olduğu yer saat kartının altı.
            if _os_zaman:
                st.markdown(
                    f"<div style='font-size:8px;color:#46536b;text-align:center;"
                    f"margin-top:-4px;'>{_os_zaman}</div>", unsafe_allow_html=True)

        with _k_liste:
            if st.button("Kayıtlar  \n%s" % ("%d kayıt" % len(_ml_data)
                                                      if _ml_data else "kayıt yok"),
                         key="oto_liste_kart", use_container_width=True,
                         disabled=not _ml_data):
                st.session_state["_oto_popup"] = "liste"
                st.rerun()

        if st.session_state.pop("_oto_switch_hata", None):
            st.error("Senaryo anahtarı yazılamadı — ağ/izin hatası.")

        st.markdown(
            f"<div>"
            # ── Satır 3: Sıcaklık + zaman ──
            f"<div style='display:flex;align-items:baseline;justify-content:space-between;margin-bottom:8px;'>"
            f"<div style='display:flex;align-items:baseline;gap:6px;'>"
            f"<span style='font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;font-size:18px;font-weight:900;"
            f"color:#2a78d6;text-shadow:0 0 12px rgba(19,50,115,0.5);'>{_donem_ikon} {_os_ref}°C</span>"
            f"<span style='font-size:9px;color:#46536b;'>"
            f"bugün max:{_os_max} · yarın min:{_os_min}</span>"
            f"</div>"
            f"</div>"
            # ── Satır 4: Saha durumu kartı + son geçiş ──
            f"{_saglik_html}"
            f"{_son_gecis_html}"
            + _KART_ALT +
            f"</div>",
            unsafe_allow_html=True
        )

    # ── POP-UP'LAR ───────────────────────────────────────────────────────
    # Geçiş saatleri ve geçiş kayıtları kartın altında aşağı doğru açılıyordu;
    # liste uzadıkça kart büyüyor ve yanındaki kartlarla hizası bozuluyordu.
    # Artık ikisi de modal pencerede açılır, kart boyu sabit kalır.
    @st.dialog("🕐 Geçiş saatleri (genel)")
    def _oto_saat_popup():
        if _ozel_saatli:
            st.info("Kendi geçiş saatiyle çalışan lokasyonlar: %s — bu "
                    "lokasyonlar aşağıdaki genel saatten ETKİLENMEZ, saatleri "
                    "kendi lokasyon detaylarından değiştirilir."
                    % ", ".join(HASTANELER.get(l, {}).get("kisa", l)
                                for l in _ozel_saatli))
        _sc1, _sc2 = st.columns(2)
        with _sc1:
            _yeni_g = st.number_input("Gündüz başlangıcı", min_value=0, max_value=23,
                                      value=int(_g_saat), step=1, key="oto_gunduz_saat_in",
                                      help="Gündüz setleri bu saatte gönderilir")
        with _sc2:
            _yeni_ge = st.number_input("Gece başlangıcı", min_value=0, max_value=23,
                                       value=int(_ge_saat), step=1, key="oto_gece_saat_in",
                                       help="Gece setleri bu saatte gönderilir")
        st.caption("Setler yalnızca bu saatlerde gönderilir. Gün ortasında hava "
                   "tahmini değişse bile komut gitmez, bir sonraki geçişte uygulanır.")
        if _yeni_g == _yeni_ge:
            st.warning("Gündüz ve gece saati aynı olamaz.")
        _p1, _p2 = st.columns(2)
        with _p1:
            if st.button("Kaydet", key="oto_saat_kaydet", use_container_width=True,
                         type="primary", disabled=(_yeni_g == _yeni_ge or _demo_modu() or _IZLEYICI)):
                for _k, _v in (("oto_gunduz_saat", _yeni_g), ("oto_gece_saat", _yeni_ge)):
                    _oaur.urlopen(_oaur.Request(
                        url + "/rest/v1/ayarlar",
                        data=_oajson.dumps({"key": _k, "value": str(int(_v))}).encode(),
                        method="POST",
                        headers={"apikey": key, "Authorization": "Bearer " + key,
                                 "Content-Type": "application/json",
                                 "Prefer": "resolution=merge-duplicates"}), timeout=4)
                st.session_state["_oto_popup"] = None
                st.rerun()
        with _p2:
            if st.button("Kapat", key="oto_saat_kapat", use_container_width=True):
                st.session_state["_oto_popup"] = None
                st.rerun()
        if _demo_modu():
            st.caption("Sunum modu — ayar yazılmaz.")

    @st.dialog("📋 Geçiş kayıtları", width="large")
    def _oto_liste_popup():
        _gecis_satirlari = ""
        for _mk in _ml_data[:20]:
            _mk_z  = _mk["created_at"][:16].replace("T", " ")
            _mk_tip = str(_mk.get("tip", ""))
            _mk_ti  = "🧊" if _mk_tip.startswith("chiller") else "🌀"
            # Mod değişmeyen (dönem geçişi) kayıtlar ayırt edilsin
            _mk_et  = " <span style='color:#46536b;'>· yenileme</span>" \
                      if _mk_tip.endswith("_yenileme") else ""
            try:
                _mk_ok = _eski_yeni_ikon(_mk["eski_mod"], _mk["yeni_mod"])
            except Exception:
                _mk_ok = "↔️"
            _gecis_satirlari += (
                f"<div style='font-size:11px;padding:5px 0;"
                f"border-bottom:1px solid rgba(24,26,30,0.10);'>"
                f"<span style='color:#46536b;'>{_mk_z}</span>"
                f" &nbsp;{_mk_ti} {_mk_ok}&nbsp; "
                f"<b style='color:#24324d;'>{_mk['eski_mod']}</b>"
                f" → <b style='color:#2a78d6;'>{_mk['yeni_mod']}</b>"
                f" &nbsp;<span style='color:#c98500;'>{_mk['tahmin_ort']}°C</span>"
                f" &nbsp;<span style='color:rgb(12,163,12);'>{_mk['komut_sayisi']} komut</span>"
                f"{_mk_et}"
                f"</div>"
            )
        st.markdown(_gecis_satirlari or "<i>Kayıt yok</i>", unsafe_allow_html=True)
        if st.button("Kapat", key="oto_liste_kapat", use_container_width=True):
            st.session_state["_oto_popup"] = None
            st.rerun()

    _acik_popup = st.session_state.get("_oto_popup")
    if _acik_popup == "saat":
        _oto_saat_popup()
    elif _acik_popup == "liste" and _ml_data:
        _oto_liste_popup()

    # ── Chiller Set & Dış Hava Kartı ──
    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
    # ── Chiller Set & Dış Hava — Birleşik Kart ──
    _ch_ic = ""
    if dis_hava_val is not None:
        _ch_ic += (
            f"<div style='display:flex;align-items:baseline;gap:6px;margin-bottom:8px;'>"
            f"<span style='font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;font-size:18px;font-weight:900;"
            f"color:#c98500;text-shadow:0 0 12px rgba(250,178,25,0.5);'>"
            f"<span style='display:inline-flex;align-items:center;gap:4px;'>"
            f"{_ik.ikon('termometre', 18)}{dis_hava_val:.1f}°C</span></span>"
            f"<span style='font-size:9px;color:#46536b;display:inline-flex;align-items:center;gap:4px;'>Dış Hava İstanbul"
            f" &nbsp;·&nbsp; {_dis_hava_kaynak}</span>"
            f"</div>"
        )
    _rozet_ic = ""
    if min_val is not None:
        _rozet_ic += (
            f"<div style='background:rgba(19,50,115,0.08);border:1px solid rgba(19,50,115,0.2);"
            f"border-radius:6px;padding:3px 10px;font-size:9px;color:#24324d;'>"
            f"<span style='display:inline-flex;align-items:center;gap:4px;'>{_ik.ikon('sogutma', 12)}Min</span> &nbsp;<b style='color:#2a78d6;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;'>{min_val:.1f}°C</b>"
            f"&nbsp;<span style='color:{min_renk};'>{min_isim}</span></div>"
        )
    if max_val is not None and max_isim != min_isim:
        _rozet_ic += (
            f"<div style='background:rgba(208,59,59,0.08);border:1px solid rgba(208,59,59,0.2);"
            f"border-radius:6px;padding:3px 10px;font-size:9px;color:#24324d;'>"
            f"<span style='display:inline-flex;align-items:center;gap:4px;'>{_ik.ikon('termometre', 12, '#d03b3b')}Max</span> &nbsp;<b style='color:#d03b3b;font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;'>{max_val:.1f}°C</b>"
            f"&nbsp;<span style='color:{max_renk};'>{max_isim}</span></div>"
        )
    # ── Lokasyon lokasyon liste ──
    # Yönetim sunumunda "hangi hastane hangi sette çalışıyor" sorusunun
    # cevabı min/max rozetinden okunamıyordu; tüm lokasyonlar listelenir.
    # Sıralama: en düşük set üstte (en çok enerji harcayan yerleşim).
    _liste_ic = ""
    if lok_sicaklik:
        _sirali = sorted(
            lok_sicaklik.items(),
            key=lambda kv: (kv[1]["set"] is None, kv[1]["set"] if kv[1]["set"] is not None else 0)
        )
        for _lid, _v in _sirali:
            _ad = HASTANELER.get(_lid, {}).get("kisa", _lid)
            _rk = HASTANELER.get(_lid, {}).get("renk", "#2a78d6")
            _s = f"{_v['set']:.1f}°C" if _v["set"] is not None else "—"
            _d = f"{_v['dis']:.1f}°C" if _v["dis"] is not None else "—"
            # Alışılmadık set değerleri (7 °C bandı dışı) dikkat çeksin
            _s_renk = "#2a78d6"
            if _v["set"] is not None and not (6.0 <= _v["set"] <= 9.0):
                _s_renk = "#c98500"
            # Sabit 3 kolonlu grid: dar sag kolonda satirlar alt alta kirilmasin.
            # Emoji kullanilmaz — basliktaki HAVA/SET etiketleri yeterli ve
            # emoji genisligi 165px'lik kolonda satiri ikiye boluyordu.
            _liste_ic += (
                f"<div style='display:grid;grid-template-columns:1fr auto auto;"
                f"align-items:center;column-gap:6px;padding:3px 0;white-space:nowrap;"
                f"border-bottom:1px solid rgba(24,26,30,0.10);'>"
                f"<span style='font-size:9px;color:{_rk};overflow:hidden;"
                f"text-overflow:ellipsis;'>{_ad}</span>"
                f"<span style='font-size:9px;color:#46536b;"
                f"min-width:34px;text-align:right;'>{_d}</span>"
                f"<span style='font-size:10px;font-weight:700;color:{_s_renk};"
                f"font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;"
                f"min-width:34px;text-align:right;'>{_s}</span>"
                f"</div>"
            )
        _liste_ic = (
            f"<div class='dis-hava-liste' style='margin-top:10px;max-height:190px;overflow-y:auto;'>"
            f"<div style='display:grid;grid-template-columns:1fr auto auto;"
            f"column-gap:6px;font-size:7px;letter-spacing:1px;white-space:nowrap;"
            f"color:#133273;padding-bottom:4px;'>"
            f"<span>HASTANE</span>"
            f"<span style='min-width:34px;text-align:right;'>HAVA</span>"
            f"<span style='min-width:34px;text-align:right;'>SET</span></div>"
            f"{_liste_ic}</div>"
        )

    if dis_hava_val is not None or min_val is not None or _liste_ic:
        with st.container(key="dis_hava_karti"):
            st.markdown(
                "<div>"
                + _kart_basligi(_ik.ikon("termometre", 22) + "DIŞ HAVA & CHİLLER SET")
                + "<div style='margin-top:10px;'></div>"
                + _ch_ic
                + f"<div style='display:flex;gap:5px;flex-wrap:wrap;'>{_rozet_ic}</div>"
                + _liste_ic
                + _KART_ALT
                + "</div>",
                unsafe_allow_html=True
            )
    else:
        st.markdown("<div class='alrt-y'>⚠️ Chiller set verisi bulunamadı</div>", unsafe_allow_html=True)

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

    # Eksik veri / sıfır ayrımı ve mekanik özet TEK KAYNAKTA: ai_veri.py
    # (testi merkez/test_ai_analiz.py). Burada ikinci bir kopya tutulmaz.
    import ai_veri as _aiv
    _col_var = _aiv.kalem_var

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

            # ── Doğalgaz & Su ── (gerçek şema: Kazan+Kojen doğalgaz, Su_Tuketimi_m3)
            _kojen_gaz_m3 = _col_sum(_lok_df, "Kojen_Dogalgaz_m3")
            _gaz_m3   = _col_sum(_lok_df, "Kazan_Dogalgaz_m3") + _kojen_gaz_m3
            _su_m3    = _col_sum(_lok_df, "Su_Tuketimi_m3")

            # ── Chiller anlık ──
            _cs_raw   = _col_mean(_lok_df, "Chiller_Set_Temp_C")
            _cl_raw   = _col_mean(_lok_df, "Chiller_Load_Percent")

            if _kwh <= 0:
                continue

            # ── Türetilmiş verimlilik metrikleri ──
            _kwh_m2_gun  = round(_kwh / _gun_say / _m2_val, 2)       # kWh/m²/gün
            # Kojen verimi = kojen kWh / SADECE kojen gazı (SY-1 fix: önceden kazan gazı da
            # paydadaydı → kışın kojen verimi yapay düşük görünüyordu)
            _kojen_verim = round(_kojen / _kojen_gaz_m3, 2) if _kojen_gaz_m3 > 0 else None   # kWh/m³
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

        # Enerji Zekası kartı kaldırıldı (22.10.2026). Metrikler aşağıdaki
        # Otomatik Sabah Analizi için hesaplanmaya devam ediyor.
        # ── AI yetki kontrolü ──
        _api_key = _gizli_oku("anthropic", "api_key")

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
            _analiz_tarihi = _bugun if _su_an.hour >= 9 else (_su_an - pd.Timedelta(days=1)).date()

            _sb_metin, _sb_zaman = _sb_analiz_oku(_analiz_tarihi)

            _yenile_btn = False  # varsayılan

            # Çalıştırma koşulu: DB'de bugün yoksa VEYA yenile butonuna basıldıysa
            _calistir = ((_sb_metin is None) or _yenile_btn) and not _IZLEYICI

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

                def _mekanik_blok(lid, tam=True):
                    """Lokasyonun MEKANİK/SAHA durumu (heartbeat: bakim_ozet).

                    Enerji sayıları tek başına yanıltıcı: 'kojen verisi yok'
                    ile 'kojen analizörü bağlantı hatası' aynı tabloda yan
                    yana durunca kök neden görünür hale geliyor.
                    """
                    _ld = lok_dict.get(lid, {})
                    _oz = _ld.get("bakim_ozet") or {}
                    if isinstance(_oz, str):
                        try:
                            _oz = json.loads(_oz)
                        except Exception:
                            _oz = {}
                    return "    Mekanik : " + " | ".join(
                        _aiv.mekanik_ozet(_oz, tam=tam)) + "\n"

                def _lok_df(lid):
                    """Lokasyonun TÜM geçmişi (geçen yıl kıyası için gerekir)."""
                    return df_all[df_all["lokasyon_id"] == lid]

                def _kiyas_blok(lid, kisa=False):
                    """Dünü kendi geçmişiyle kıyaslayan satırlar."""
                    _m2v = HASTANELER.get(lid, {}).get("m2", 10000)
                    _kn = _aiv.kiyas_noktalari(_lok_df(lid), _dun_dt.date(), _m2v)
                    if not _kn:
                        return ""
                    if kisa:
                        _p = [("%s %+.1f%%" % (k["ad"].split()[1][:3], k["degisim"]))
                              for k in _kn if k.get("veri") and k.get("degisim") is not None]
                        return ("  Kıyas: " + ", ".join(_p) + "\n") if _p else ""
                    _s = "  ▷ Kıyas (dün ile):\n"
                    for k in _kn:
                        if not k.get("veri"):
                            _s += "    %s (%s): veri yok\n" % (k["ad"],
                                                               k["tarih"].strftime("%d.%m.%Y"))
                            continue
                        _s += "    %s (%s): %s kWh" % (k["ad"],
                                                       k["tarih"].strftime("%d.%m.%Y"),
                                                       format(int(k["elektrik"]), ","))
                        if k.get("degisim") is not None:
                            _s += "  →  dün %+.1f%%" % k["degisim"]
                        if k.get("dis_hava") is not None:
                            _s += "  |  dış hava %.1f°C" % k["dis_hava"]
                            if k.get("dis_fark") is not None:
                                _s += " (dün %+.1f°C)" % k["dis_fark"]
                        _s += "\n"
                    return _s

                _TREND_AD = {"elektrik_gun": ("Elektrik", "kWh/gün"),
                             "kojen_verim": ("Kojen verimi", "kWh/m³"),
                             "sebeke_bag": ("Şebeke payı", "%")}

                def _trend_blok(lid, kisa=False):
                    """Son 7 gün ile önceki 7 günün karşılaştırması (yön)."""
                    _tr = _aiv.trend(_lok_df(lid), _dun_dt.date(), 7)
                    _par = []
                    for _k, (_ad, _br) in _TREND_AD.items():
                        _t = _tr.get(_k) or {}
                        if _t.get("son") is None or _t.get("onceki") is None:
                            continue
                        _par.append((_ad, _br, _t))
                    if not _par:
                        return ""
                    if kisa:
                        return ("  Trend7g: " + ", ".join(
                            "%s %+.1f%%" % (a, t["degisim"])
                            for a, _b, t in _par if t.get("degisim") is not None) + "\n")
                    _s = "  ▷ Trend (son 7 gün / önceki 7 gün):\n"
                    for _ad, _br, _t in _par:
                        _s += "    %s: %s → %s %s" % (_ad, _t["onceki"], _t["son"], _br)
                        if _t.get("degisim") is not None:
                            _s += "  (%+.1f%%, %s)" % (_t["degisim"], _t.get("yon") or "—")
                        _s += "\n"
                    if _tr.get("kapsama", 7) < 7:
                        _s += "    ⓘ Son 7 günün yalnızca %d gününde veri var\n" % _tr["kapsama"]
                    return _s

                def _dun_blok_tam(lid, mv):
                    """TIER 1 — tam detay bloğu.

                    Kalem GİRİLMEMİŞSE "veri girilmedi" yazılır; satır sessizce
                    atlanmaz. Atlandığında AI eksik veriyi "üretim durdu" diye
                    okuyup arıza yorumu yapıyordu.
                    """
                    _ddf = _dun_verisi(lid)
                    _m2v = HASTANELER.get(lid, {}).get("m2", 10000)
                    b = f"【{mv['isim']}】{' ⚠️ANORMAL' if mv['anormal'] else ''}\n"
                    if not _ddf.empty:
                        _v_kwh = _col_var(_ddf, "Toplam_Hastane_Tuketim_kWh")
                        _v_koj = _col_var(_ddf, "Kojen_Uretim_kWh")
                        _v_kgz = _col_var(_ddf, "Kojen_Dogalgaz_m3")
                        _v_kaz = _col_var(_ddf, "Kazan_Dogalgaz_m3")
                        _v_seb = _col_var(_ddf, "Sebeke_Tuketim_kWh")
                        _v_su  = _col_var(_ddf, "Su_Tuketimi_m3")
                        dkwh = _col_sum(_ddf, "Toplam_Hastane_Tuketim_kWh")
                        dkojgaz = _col_sum(_ddf, "Kojen_Dogalgaz_m3")
                        dgaz = _col_sum(_ddf, "Kazan_Dogalgaz_m3") + dkojgaz
                        dkoj = _col_sum(_ddf, "Kojen_Uretim_kWh")
                        dseb = _col_sum(_ddf, "Sebeke_Tuketim_kWh")
                        dsu  = _col_sum(_ddf, "Su_Tuketimi_m3")
                        dcs  = _col_mean(_ddf, "Chiller_Set_Temp_C")
                        dcl  = _col_mean(_ddf, "Chiller_Load_Percent")
                        _eksik = []
                        b += f"  ▶ Dün ({_dun_str}):\n"
                        if _v_kwh:
                            b += f"    Elektrik : {dkwh:,.0f} kWh  ({round(dkwh/_m2v,2)} kWh/m²/gün)\n"
                        else:
                            _eksik.append("elektrik")
                        if _v_koj:
                            b += f"    Kojen    : {dkoj:,.0f} kWh"
                            if _v_kgz and dkojgaz > 0:
                                b += f"  |  Verim: {round(dkoj/dkojgaz,2)} kWh/m³ (≥3.5)"
                            elif not _v_kgz:
                                b += "  |  kojen gazı girilmedi, verim hesaplanamadı"
                            b += "\n"
                        else:
                            _eksik.append("kojen üretimi")
                        # Şebeke oranı YALNIZCA iki kalem de girilmişse hesaplanır.
                        # Kojen boşken payda=şebeke olup oran %100 çıkıyor ve
                        # "kojen devre dışı" gibi okunuyordu.
                        if _v_seb and _v_koj and (dseb + dkoj) > 0:
                            b += f"    Şebeke bağ.: %{round(dseb/(dseb+dkoj)*100,1)}  (<%30 ideal)\n"
                        elif _v_seb and not _v_koj:
                            b += (f"    Şebeke    : {dseb:,.0f} kWh  "
                                  f"(kojen verisi girilmediği için oran HESAPLANMADI)\n")
                        elif not _v_seb:
                            _eksik.append("şebeke tüketimi")
                        if _v_kgz or _v_kaz:
                            b += f"    Doğalgaz : {dgaz:,.0f} m³"
                            if _v_kwh and dgaz > 0:
                                b += f"  |  Genel verim: {round(dkwh/dgaz,2)} kWh/m³"
                            b += "\n"
                        else:
                            _eksik.append("doğalgaz")
                        if _v_su:
                            b += f"    Su       : {dsu:,.0f} m³\n"
                        else:
                            _eksik.append("su")
                        if not np.isnan(dcs):
                            b += f"    Chiller  : {round(dcs,1)}°C"
                            if not np.isnan(dcl):
                                b += f"  |  Yük %{round(dcl,0):.0f}"
                            b += "\n"
                        if _eksik:
                            b += ("    ⓘ VERİ GİRİLMEMİŞ KALEMLER: " + ", ".join(_eksik)
                                  + " — bunlar SIFIR DEĞİL, veri yok.\n")
                    else:
                        b += f"  ▶ Dün: bu güne ait hiç veri girilmemiş (arıza göstergesi DEĞİL)\n"
                    b += _mekanik_blok(lid)
                    b += _kiyas_blok(lid)
                    b += _trend_blok(lid)
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
                        # "yok" = veri girilmedi, "-" = hesaplanamadı. İkisi de
                        # SIFIR değildir; AI bunları arıza sanmamalı.
                        _v_koj = _col_var(_ddf, "Kojen_Uretim_kWh")
                        _v_seb = _col_var(_ddf, "Sebeke_Tuketim_kWh")
                        _v_kwh = _col_var(_ddf, "Toplam_Hastane_Tuketim_kWh")
                        _v_kgz = _col_var(_ddf, "Kojen_Dogalgaz_m3")
                        dkwh = _col_sum(_ddf, "Toplam_Hastane_Tuketim_kWh")
                        dkojgaz = _col_sum(_ddf, "Kojen_Dogalgaz_m3")
                        dkoj = _col_sum(_ddf, "Kojen_Uretim_kWh")
                        dseb = _col_sum(_ddf, "Sebeke_Tuketim_kWh")
                        kv   = (round(dkoj/dkojgaz, 2) if (_v_koj and _v_kgz and dkojgaz > 0)
                                else ("veri yok" if not (_v_koj and _v_kgz) else "-"))
                        sb   = (f"%{round(dseb/(dseb+dkoj)*100,1)}"
                                if (_v_seb and _v_koj and (dseb+dkoj) > 0)
                                else ("kojen verisi yok" if _v_seb else "veri yok"))
                        yo   = round(dkwh/_m2v, 2) if _v_kwh else "veri yok"
                        return (f"  {mv['isim']}{flag}: {yo} kWh/m²/gün  |  "
                                f"Kojen verim {kv}  |  Şebeke {sb}  |  30g ort {mv['kwh_m2']}\n"
                                + _mekanik_blok(lid, tam=False)
                                + _kiyas_blok(lid, kisa=True)
                                + _trend_blok(lid, kisa=True))
                    else:
                        return (f"  {mv['isim']}{flag}: güne ait veri girilmemiş  |  "
                                f"30g ort {mv['kwh_m2']} kWh/m²/gün\n"
                                + _mekanik_blok(lid, tam=False))

                def _dun_blok_mini(lid, mv):
                    """TIER 3 — minimal, sadece anahtar değerler."""
                    _ddf = _dun_verisi(lid)
                    _m2v = HASTANELER.get(lid, {}).get("m2", 10000)
                    flag = "⚠️" if mv["anormal"] else "✓"
                    if not _ddf.empty:
                        _v_koj = _col_var(_ddf, "Kojen_Uretim_kWh")
                        _v_seb = _col_var(_ddf, "Sebeke_Tuketim_kWh")
                        _v_kwh = _col_var(_ddf, "Toplam_Hastane_Tuketim_kWh")
                        _v_kgz = _col_var(_ddf, "Kojen_Dogalgaz_m3")
                        dkwh = _col_sum(_ddf, "Toplam_Hastane_Tuketim_kWh")
                        dkojgaz = _col_sum(_ddf, "Kojen_Dogalgaz_m3")
                        dkoj = _col_sum(_ddf, "Kojen_Uretim_kWh")
                        dseb = _col_sum(_ddf, "Sebeke_Tuketim_kWh")
                        # "vy" = veri yok (sıfır DEĞİL)
                        kv   = (round(dkoj/dkojgaz, 2)
                                if (_v_koj and _v_kgz and dkojgaz > 0) else "vy")
                        sb   = (f"%{round(dseb/(dseb+dkoj)*100,1)}"
                                if (_v_seb and _v_koj and (dseb+dkoj) > 0) else "vy")
                        yo   = round(dkwh/_m2v, 2) if _v_kwh else "vy"
                        _mek = _mekanik_blok(lid, tam=False).strip()
                        _mek = _mek.replace("Mekanik :", "").strip()
                        _ky = _kiyas_blok(lid, kisa=True).strip().replace("Kıyas: ", "")
                        return (f"  [{flag}] {mv['isim']}: {yo} kWh/m²  Koj:{kv}  Şeb:{sb}"
                                + (f"  [{_ky}]" if _ky else "")
                                + f"  — {_mek}\n")
                    else:
                        return f"  [?] {mv['isim']}: güne ait veri girilmemiş\n"

                # ── Referans satırı (tüm tier'larda ortak) ──
                _ref = (
                    "Referans: Yoğunluk 0.5–1.5 kWh/m²/gün | "
                    "Kojen ≥3.5 kWh/m³ | Şebeke <%30 | Gaz verimi ≥5.0 kWh/m³\n"
                    # 11.10.2026: kojen verisi girilmediği gün model "kojen
                    # arızalı, derhal kontrol edin" dedi. Eksik veri bir arıza
                    # kanıtı değildir; arıza bilgisi MEKANİK satırından gelir.
                    "VERİ KURALI: 'veri yok / veri girilmedi / vy' yazan kalem SIFIR DEĞİLDİR, "
                    "ölçüm girilmemiştir. Bu kalemler için arıza, duruş ya da bakım yorumu YAPMA; "
                    "yalnızca 'veri girişi eksik, kontrol edilsin' de. Arıza/bakım/bağlantı "
                    "iddiasını SADECE 'Mekanik' satırındaki bilgilere dayandır.\n"
                    # Sabit eşik bir hastanenin kendi normalini söylemez:
                    # 58.529 kWh tek başına ne iyi ne kötüdür.
                    "KIYAS KURALI: Değerlendirmeyi önce 'Kıyas' (geçen hafta / geçen yıl "
                    "aynı gün) ve 'Trend' satırlarına dayandır, sabit eşikler ikincildir. "
                    "Tüketim farkını yorumlarken DIŞ HAVA farkını hesaba kat: hava daha "
                    "sıcak/soğukken tüketimin artması tek başına sapma değildir.\n\n"
                )

                # ════════════════ TIER 1: 1-3 lokasyon ════════════════
                if _lok_n <= 3:
                    _lok_bloklari = [_dun_blok_tam(lid, mv) for lid, mv in _sirali]
                    _max_tok = 700
                    _yonerge = (
                        "Türkçe, mühendis dilinde:\n"
                        "1. Dün nasıl geçti — kendi geçmişine göre (geçen hafta/geçen yıl "
                        "aynı gün, dış hava farkıyla); eksik kalem varsa önce onu söyle\n"
                        "2. Eğilim — 7 günlük trend neyi gösteriyor (düzeliyor mu, "
                        "bozuluyor mu)\n"
                        "3. En kritik bulgu ve kök nedeni — enerji sayısıyla mekanik "
                        "durumu (arıza, veri alarmı, oto-set) BİRLİKTE yorumla\n"
                        "4. Bugün yapılacak 1 somut aksiyon\n"
                        "Maksimum 230 kelime."
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

                # Diğer kartlarla AYNI kalıp: çerçeve kabın kendisinde,
                # başlık ortak biçimde, düğme kartın İÇİNDE. Önceden kart
                # kendi kutusunu çiziyor, düğme negatif margin ile dışarıdan
                # yapıştırılıyordu.
                with st.container(key="sabah_analiz_karti"):
                    st.markdown(
                        "<div>"
                        + _kart_basligi(_ik.ikon("zeka", 22) + "OTOMATİK SABAH ANALİZİ",
                                        ("<span style='display:inline-flex;align-items:center;gap:4px;'>"
                                         + _ik.ikon("saat", 11) + _ai_zaman_str + "</span>")
                                        if _ai_zaman_str else "")
                        + "<div class='sabah-kaydir' style='margin-top:10px;font-size:11px;color:#24324d;"
                          "line-height:1.7;max-height:220px;overflow-y:auto;"
                          "scrollbar-width:thin;scrollbar-color:#133273 transparent;'>"
                        + _ai_temiz.replace("\n", "<br>")
                        + "</div>"
                          "<div style='border-top:1px solid rgba(24,26,30,0.10);"
                          "margin:10px 0 2px;'></div>"
                          "</div>",
                        unsafe_allow_html=True)
                    if st.button("🔄 Yeniden Analiz Et", key="btn_ai_yenile",
                                 use_container_width=True, disabled=_IZLEYICI):
                        _sb_metin = None
                        st.rerun()

    else:
        st.markdown(
            "<div class='alrt-y'>📊 Henüz yeterli veri yok.</div>",
            unsafe_allow_html=True)

    st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)


# ============ FOOTER ============
st.markdown(f"""
<div style="text-align:center; padding:10px 0 4px; border-top:1px solid rgba(24,26,30,0.10); margin-top:10px;">
  <span style="font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif; font-size:9px; color:#133273; letter-spacing:2px;">
    ACIBADEM ENERJİ YÖNETİM SİSTEMİ &nbsp;·&nbsp; {now_display.strftime('%d.%m.%Y %H:%M')}
  </span>
</div>
""", unsafe_allow_html=True)

# ============ SÜTUN HİZALAMA ============
# Lokasyon durumu | harita | sağ paneller: üçünün ALT kenarı aynı hizada.
# Hedef: en uzun sütun (sağ paneldeki sabah analizi metni gerekirse 160 px'e
# kadar kısalır). Sol sütunda lokasyon listesi uzar, haritanın boyu ayarlanır,
# sağda sabah analizi kutusu uzar/kısalır. Tablet/telefonda (sütunlar alt alta)
# hiçbir şey yapılmaz. Her çizimde ve pencere boyu değişince yeniden hesaplanır.
_components.html("""
<script>
(function () {
  var d; try { d = window.parent.document; } catch (e) { return; }
  var w = d.defaultView;
  function alt(el) {
    var b = 0;
    el.querySelectorAll(':scope > div > [data-testid="stElementContainer"], :scope > [data-testid="stVerticalBlock"] > *').forEach(function (c) {
      var r = c.getBoundingClientRect(); if (r.height > 1) b = Math.max(b, r.bottom);
    });
    return b;
  }
  function hizala() {
    var blok = d.querySelector('[data-testid="stHorizontalBlock"]:has(.ana-duzen-isaret)');
    if (!blok) return;
    var k = blok.children; if (k.length < 3) return;
    var sol = k[0], orta = k[1], sag = k[2];
    var liste = sol.querySelector('.lok-scroll');
    var harita = orta.querySelector('iframe[src^="data:"]');
    var hKap = harita ? harita.closest('[data-testid="stElementContainer"]') : null;
    var sabah = sag.querySelector('.sabah-kaydir');
    var hava = sag.querySelector('.dis-hava-liste');
    var sagBlok = sag.querySelector(':scope > [data-testid="stVerticalBlock"]') || sag;
    // sıfırla (önceki ayarlar ölçümü bozmasın)
    if (liste) { liste.style.height = ''; liste.style.maxHeight = ''; }
    if (harita) { harita.style.height = '640px'; if (hKap) hKap.style.height = '640px'; }
    if (sabah) sabah.style.maxHeight = '';
    if (hava) hava.style.maxHeight = '';
    sagBlok.style.maxHeight = ''; sagBlok.style.overflowY = '';
    // yan yana değilse (tablet/telefon) dur
    var t0 = sol.getBoundingClientRect().top, t1 = sag.getBoundingClientRect().top;
    if (Math.abs(t0 - t1) > 40 || w.innerWidth <= 1180) return;
    var aSol = alt(sol), aOrta = alt(orta), aSag = alt(sag);
    var esSabah = sabah ? Math.max(0, sabah.getBoundingClientRect().height - 160) : 0;
    var esHava = hava ? Math.max(0, hava.getBoundingClientRect().height - 90) : 0;
    // Harita en fazla 860 px'e uzar (taban 640 + 220): sağ panel çok uzunsa
    // haritayı değil sağ paneli kısaltırız.
    var hedef = Math.min(Math.max(aSol, aOrta, aSag - esSabah - esHava), aOrta + 220);
    var fazla = aSag - hedef;
    if (fazla > 0 && sabah) { var k1 = Math.min(fazla, esSabah); sabah.style.maxHeight = (sabah.getBoundingClientRect().height - k1) + 'px'; fazla -= k1; }
    if (fazla > 0 && hava) { var k2 = Math.min(fazla, esHava); hava.style.maxHeight = (hava.getBoundingClientRect().height - k2) + 'px'; fazla -= k2; }
    if (fazla > 0) {   // son çare: sağ sütun kendi içinde kayar
      sagBlok.style.maxHeight = (hedef - sagBlok.getBoundingClientRect().top) + 'px';
      sagBlok.style.overflowY = 'auto';
    }
    aSag = Math.min(alt(sag), hedef);
    if (liste) {
      var lh = liste.getBoundingClientRect().height;
      liste.style.maxHeight = 'none';
      liste.style.height = Math.max(160, lh + (hedef - aSol)) + 'px';
    }
    if (harita) {
      var hh = 640 + (hedef - aOrta);
      harita.style.height = hh + 'px'; if (hKap) hKap.style.height = hh + 'px';
    }
    if (sabah && hedef > aSag) {   // sağ panel kısaysa sabah analizi uzar
      var sh = sabah.getBoundingClientRect().height;
      sabah.style.maxHeight = (sh + (hedef - aSag)) + 'px';
    }
  }
  [80, 500, 1500, 3500].forEach(function (ms) { setTimeout(hizala, ms); });
  if (w.__synapseHizala) w.removeEventListener('resize', w.__synapseHizala);
  w.__synapseHizala = function () { clearTimeout(w.__synapseHizalaZ); w.__synapseHizalaZ = setTimeout(hizala, 150); };
  w.addEventListener('resize', w.__synapseHizala);
})();
</script>
<!-- cizim: %s -->
""" % now_display.strftime("%H%M%S"), height=0)

# ============ AYARLAR ============
if _IZLEYICI:
    st.stop()   # Ayarlar (bağlantı anahtarı, mesaj, uzaktan komut) izleyicide yok

# Ayarlar sayfanın altında değil: sağ üstteki "Ayarlar" düğmesi bu paneli
# TARAYICIDA açar/kapatır (Streamlit yeniden çalışmaz, sayfa yenilenmez).
# İçerik her çizimde gizli olarak hazırdır; panel açıkken 10 sn'lik yenileme
# paneli kapatmaz (açık/kapalı bilgisi sayfadadır, sunucuda değil).
st.markdown("""
<style>
.st-key-ayarlar_panel{display:none !important;}
@keyframes ayarGir{from{opacity:0;transform:translate(-50%,-12px);}to{opacity:1;transform:translate(-50%,0);}}
body.ayarlar-acik .st-key-ayarlar_panel{display:flex !important;flex-direction:column;position:fixed !important;
  top:64px;left:50%;transform:translateX(-50%);width:min(1100px,94vw);max-height:calc(100vh - 90px);
  overflow-y:auto;z-index:1000001;background:#fff;border-radius:16px;padding:16px 22px 20px;
  border:1px solid rgba(24,26,30,.10);box-shadow:0 30px 80px -20px rgba(15,31,61,.45);animation:ayarGir .22s ease;}
body.ayarlar-acik::after{content:"";position:fixed;inset:0;background:rgba(15,31,61,.32);z-index:1000000;}
.ayar-ust{display:flex;align-items:center;justify-content:space-between;margin-bottom:6px;}
.ayar-ust b{font-size:15px;font-weight:800;color:#133273;letter-spacing:1.2px;display:inline-flex;align-items:center;gap:8px;}
.ayar-kapat{width:32px;height:32px;border-radius:9px;display:flex;align-items:center;justify-content:center;
  color:#46536b !important;text-decoration:none !important;font-size:20px;line-height:1;border:1px solid rgba(24,26,30,.12);}
.ayar-kapat:hover{background:#d03b3b;color:#fff !important;border-color:#d03b3b;}
</style>
""", unsafe_allow_html=True)

with st.container(key="ayarlar_panel"):
    st.markdown('<div class="ayar-ust"><b>' + _ik.ikon("ayar", 20) + 'SİSTEM AYARLARI</b>'
                '<a class="ayar-kapat" href="#" title="Kapat" aria-label="Kapat">×</a></div>',
                unsafe_allow_html=True)

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
        durum_renk_map = {"tamamlandi": "#0ca30c", "bekliyor": "#c98500", "iptal": "#6b7280", "hata": "#d03b3b"}
        durum_icon_map = {"tamamlandi": "✅", "bekliyor": "⏳", "iptal": "❌", "hata": "🚨"}
        if not gunc:
            st.info("Henüz güncelleme kaydı yok.")
        for r in gunc:
            dr = durum_renk_map.get(r["durum"], "#aaa")
            di = durum_icon_map.get(r["durum"], "?")
            tarih = r["created_at"][:16].replace("T", " ")
            st.markdown(f"""
            <div style="padding:7px 10px; margin:3px 0; background:#fafaf8;
                        border-radius:8px; border-left:3px solid {dr};">
              <div style="font-size:12px; color:#e0f2fe; font-weight:600;">{di} {r['versiyon']}
                <span style="color:#46536b; font-size:11px;">→ {r['hedef']}</span>
              </div>
              <div style="font-size:10px; color:{dr};">{r['durum'].upper()} &nbsp;·&nbsp;
                <span style="color:#46536b;">{tarih}</span>
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
                <div style="padding:8px 12px; margin:4px 0; background:#fafaf8;
                            border-radius:8px; border:1px solid rgba(19,50,115,0.1);
                            display:flex; justify-content:space-between; align-items:center;">
                  <span style="font-size:12px; color:#e0f2fe; font-weight:600;">🏥 {isim}</span>
                  <span style="font-size:10px; color:#46536b;">Son ping: {ping}</span>
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

        # Sınırlar lokasyondaki güvenlik kapısıyla AYNI (bacnet_writer
        # KOMUT_DEGER_MIN/MAX). Önceden 0–99 kabul ediliyordu: 3 °C yazan
        # kullanıcı "gönderildi" görüyor, komut lokasyonda sessizce hata oluyordu.
        # test_bacnet_writer.py iki tarafın eşitliğini doğrular.
        _uc_deger = st.number_input(
            "Hedef Değer (°C)",
            min_value=5.0, max_value=40.0, value=7.0, step=0.5,
            key="uc_deger"
        )

        # Son komutlar tablosu
        try:
            _uc_son_komutlar = (
                _ucc_client.table("komutlar")
                .select("nokta_adi,hedef_deger,durum,hata_mesaji,created_at,executed_at")
                .eq("lokasyon", _uc_lok_id)
                .order("created_at", desc=True)
                # Oto-set her geçişte ~11 satır yazar; gece + gündüz birlikte
                # görünsün diye 50.
                .limit(50)
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
                    "bekliyor":      "🟡",
                    "tamamlandi":    "✅",   # cihazdan geri okunarak doğrulandı
                    "dogrulanamadi": "⚠️",   # cihaz kabul etti ama geri okunamadı
                    "suresi_doldu":  "⌛",   # lokasyon geç aldı, uygulanmadı
                    "hata":          "❌",
                }
                for _k in _uc_son_komutlar:
                    # created_at UTC gelir; ekranda İstanbul saati gösterilir
                    try:
                        from datetime import timezone as _ktz
                        _zaman = (datetime.fromisoformat(str(_k.get("created_at", "")).replace("Z", "+00:00"))
                                  .astimezone(_ktz(timedelta(hours=3))).strftime("%Y-%m-%d %H:%M"))
                    except Exception:
                        _zaman = (_k.get("created_at", "")[:16].replace("T", " "))
                    _icon  = _durum_renk.get(_k["durum"], "⏳")
                    _hm    = str(_k.get("hata_mesaji") or "")
                    # Oto-set'in yazdığı satırlar (lokasyon PC'si) 🤖 ile ayrılır
                    if _hm.startswith("OTO-SET"):
                        _icon += " 🤖"
                    _hata  = f" — {_hm}" if _hm else ""
                    st.markdown(
                        f"{_icon} `{_k['nokta_adi']}` → **{_k['hedef_deger']}°C** "
                        f"<span style='color:#133273;font-size:11px;'>{_zaman}{_hata}</span>",
                        unsafe_allow_html=True
                    )
            else:
                st.caption("Henüz komut gönderilmedi.")


# (Panel aç / kapat betiği sağ üst düğmelerin yanında — her ekranda çalışır.)
