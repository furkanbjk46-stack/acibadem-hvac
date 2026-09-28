# -*- coding: utf-8 -*-
"""
SYNAPSE TEMA — AÇIK (BEYAZ) TEMA TOKENLARI
==========================================

Renkler ve yazı tipi, Elektrik Analiz Paneli referansından alınmıştır.
Kod içinde renk sabiti yazmak yerine buradaki tokenlar kullanılır; tema
değişirse tek dosya düzenlenir.

Yazı tipi: system-ui yığını (Windows'ta Segoe UI). Referansta harici font
yoktur — Google Fonts çağrısı kaldırıldı, sayfa daha hızlı açılır.
"""

FONT = 'system-ui,-apple-system,Roboto,sans-serif'

# ── Yüzeyler ve metin ────────────────────────────────────────────────────
SAYFA      = "#ffffff"
YUZEY      = "#ffffff"
YUZEY_2    = "#f3f6fb"
MUREKKEP   = "#0f1f3d"      # ana metin
MUREKKEP_2 = "#24324d"      # ikincil metin
SOLUK      = "#46536b"      # etiket / açıklama
IZGARA     = "#e8edf4"      # grafik ızgarası, ayraç
EKSEN      = "#c9d2e0"
CERCEVE    = "rgba(19,50,115,.22)"
GOLGE      = "0 1px 2px rgba(19,50,115,.07),0 10px 24px -12px rgba(19,50,115,.28)"

# ── Vurgu ────────────────────────────────────────────────────────────────
LACIVERT   = "#133273"      # başlıklar, ana vurgu
BASLIK_GRD = "linear-gradient(90deg,#133273,#1d4f9c 55%,#3aa0e0)"

# ── Durum renkleri ───────────────────────────────────────────────────────
IYI        = "#0ca30c"
UYARI      = "#fab219"
CIDDI      = "#ec835a"
KRITIK     = "#d03b3b"
IYI_YAZI   = "#006300"      # açık zeminde okunur yeşil metin
UYARI_YAZI = "#8a5a00"
KRITIK_YAZI = "#b42525"

# ── Seri (grafik) renkleri ───────────────────────────────────────────────
S1 = "#2a78d6"   # birincil mavi
S2 = "#eb6834"   # turuncu
S3 = "#1baf7a"   # yeşil
S4 = "#eda100"   # sarı
S5 = "#e87ba4"   # pembe
S6 = "#008300"   # koyu yeşil
S7 = "#4a3aa7"   # mor
S8 = "#e34948"   # kırmızı

# Sistem kalemlerinin sabit renkleri (grafik + panel aynı rengi kullansın)
CHILLER = "#256abf"
KULE    = S1
MCC     = "#6da7ec"
VRF     = S7
SEBEKE  = S7
KOJEN   = IYI
OLCULMEYEN = SOLUK


def kart(dolgu="14px"):
    """Standart kart kutusu (inline style metni)."""
    return (f"background:{YUZEY};border:1px solid {CERCEVE};border-radius:10px;"
            f"padding:{dolgu};box-shadow:{GOLGE};")


def etiket():
    """Kartların üstündeki küçük büyük harfli etiket."""
    return (f"font-size:9px;letter-spacing:1.5px;text-transform:uppercase;"
            f"color:{SOLUK};margin-bottom:4px;")
