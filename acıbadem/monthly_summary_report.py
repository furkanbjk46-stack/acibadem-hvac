# monthly_summary_report.py
# Aylık Özet PDF Raporu Oluşturucu
# Her ayın 1'inde önceki ayın verilerini derleyerek modern PDF rapor üretir.

from __future__ import annotations

import os
import json
import io
import tempfile
import calendar
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

from fpdf import FPDF

# Plotly grafik üretimi
try:
    import plotly.graph_objects as go
    import plotly.io as pio
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# ─── Sabitler ───
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# Lokasyon bazlı dosya yolları (fallback: eski hardcoded yollar)
try:
    from location_manager import get_manager as _get_loc_mgr
    _lm = _get_loc_mgr()
    DATA_FILE = _lm.get_data_path("energy_data.csv")
    SETTINGS_FILE = _lm.get_data_path("configs/hvac_settings.json")
    REPORTS_DIR = _lm.get_data_path("monthly_reports_summary")
except Exception:
    DATA_FILE = os.path.join(BASE_DIR, "energy_data.csv")
    SETTINGS_FILE = os.path.join(BASE_DIR, "configs", "hvac_settings.json")
    REPORTS_DIR = os.path.join(BASE_DIR, "monthly_reports_summary")
GAS_TO_KWH = 10.64


def _calculate_chiller_cop(load_percent: float) -> float:
    """2000 KW Chiller Performans Eğrisi — doğrusal interpolasyon."""
    import bisect
    _curve = [
        (10.0, 2.52), (20.0, 4.59), (25.0, 5.37), (30.0, 6.04),
        (40.0, 7.25), (50.0, 7.98), (60.0, 7.52), (70.0, 6.98),
        (75.0, 6.68), (80.0, 6.38), (90.0, 5.72), (100.0, 5.05),
    ]
    loads = [x[0] for x in _curve]
    cops  = [x[1] for x in _curve]
    p = max(0.0, min(100.0, float(load_percent)))
    if p <= loads[0]:
        return cops[0]
    if p >= loads[-1]:
        return cops[-1]
    i = bisect.bisect_right(loads, p)
    x0, y0 = loads[i - 1], cops[i - 1]
    x1, y1 = loads[i],     cops[i]
    return round(y0 + (y1 - y0) * (p - x0) / (x1 - x0), 2)


AYLAR = {
    1: "Ocak", 2: "Subat", 3: "Mart", 4: "Nisan",
    5: "Mayis", 6: "Haziran", 7: "Temmuz", 8: "Agustos",
    9: "Eylul", 10: "Ekim", 11: "Kasim", 12: "Aralik"
}

# ─── PDF Metin Temizleme (sadece emoji/sembol → ASCII, Türkçe korunur) ───
def _sanitize(text: str) -> str:
    if text is None:
        return ""
    replacements = {
        "•": "-", "→": "->", "←": "<-", "↑": "^", "↓": "v",
    }
    for char, rep in replacements.items():
        text = text.replace(char, rep)
    return text


def _setup_unicode_font(pdf):
    """PDF nesnesine DejaVu Unicode font ekler."""
    from pathlib import Path
    font_candidates = [
        Path(BASE_DIR) / "fonts" / "DejaVuSans.ttf",
        Path("C:/Windows/Fonts/DejaVuSans.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    bold_candidates = [
        Path(BASE_DIR) / "fonts" / "DejaVuSans-Bold.ttf",
        Path("C:/Windows/Fonts/DejaVuSans-Bold.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
    ]
    italic_candidates = [
        Path(BASE_DIR) / "fonts" / "DejaVuSans-Oblique.ttf",
        Path("C:/Windows/Fonts/DejaVuSans-Oblique.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"),
    ]
    reg = next((p for p in font_candidates if p.exists()), None)
    bold = next((p for p in bold_candidates if p.exists()), None)
    italic = next((p for p in italic_candidates if p.exists()), None)
    if reg:
        pdf.add_font("DejaVu", "", str(reg), uni=True)
        if bold:
            pdf.add_font("DejaVu", "B", str(bold), uni=True)
        pdf.add_font("DejaVu", "I", str(italic) if italic else str(reg), uni=True)
        return "DejaVu"
    return "Helvetica"


# ─── Veri Yükleme ───
def load_energy_data() -> pd.DataFrame:
    if not os.path.exists(DATA_FILE):
        return pd.DataFrame()
    df = pd.read_csv(DATA_FILE)
    if "Tarih" in df.columns:
        df["Tarih"] = pd.to_datetime(df["Tarih"], format="%Y-%m-%d", errors="coerce").dt.date
    return df


def load_hvac_history() -> pd.DataFrame:
    try:
        from monthly_report.hvac_history import HVACHistoryManager
        mgr = HVACHistoryManager()
        df = mgr.load_history()
        if not df.empty and "Tarih" in df.columns:
            df["Tarih"] = pd.to_datetime(df["Tarih"], format="%Y-%m-%d", errors="coerce").dt.date
        return df
    except Exception:
        return pd.DataFrame()


def load_building_area() -> float:
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return float(data.get("BUILDING_AREA_M2", 0))
    except Exception:
        pass
    return 0.0


def load_unit_prices() -> Dict:
    """Birim fiyatları settings'ten yükle."""
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                return {
                    "electricity": float(data.get("UNIT_PRICE_ELECTRICITY", 0)),
                    "gas": float(data.get("UNIT_PRICE_GAS", 0)),
                    "water": float(data.get("UNIT_PRICE_WATER", 0)),
                }
    except Exception:
        pass
    return {"electricity": 0, "gas": 0, "water": 0}


# ─── Plotly Grafik Üretimi ───
def create_monthly_pie_chart(total_kwh: float, chiller_kwh: float, gas_kwh: float) -> Optional[bytes]:
    if not HAS_PLOTLY:
        return None
    other = max(0, total_kwh - chiller_kwh - gas_kwh)
    labels = ["Sogutma (Chiller)", "Isitma (Dogalgaz)", "Diger"]
    values = [chiller_kwh, gas_kwh, other]
    colors = ["#3b82f6", "#ef4444", "#8b5cf6"]
    
    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values, hole=0.45,
        marker=dict(colors=colors, line=dict(color='#1a2332', width=2)),
        textinfo='label+percent',
        textfont=dict(size=13, color='white'),
        insidetextorientation='radial'
    )])
    fig.update_layout(
        paper_bgcolor='#1a2332', plot_bgcolor='#1a2332',
        font=dict(color='white', size=12), showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=-0.15, xanchor="center", x=0.5,
                    font=dict(color='white', size=11)),
        margin=dict(l=20, r=20, t=30, b=40), width=500, height=350,
        title=dict(text="Aylik Enerji Dagilimi", font=dict(size=16, color='white'))
    )
    return pio.to_image(fig, format="png", scale=2)


def create_daily_trend_chart(df: pd.DataFrame, year: int, month: int) -> Optional[bytes]:
    """Ay içindeki günlük tüketim trend grafiği."""
    if not HAS_PLOTLY or df.empty:
        return None
    
    start = date(year, month, 1)
    last_day = calendar.monthrange(year, month)[1]
    end = date(year, month, last_day)
    
    mask = (df["Tarih"] >= start) & (df["Tarih"] <= end)
    month_df = df[mask].sort_values("Tarih")
    if month_df.empty:
        return None
    
    dates = [d.strftime("%d") for d in month_df["Tarih"]]
    totals = month_df["Toplam_Hastane_Tuketim_kWh"].fillna(0).tolist()
    chillers = month_df["Chiller_Tuketim_kWh"].fillna(0).tolist()
    
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=dates, y=totals, name="Toplam kWh",
        marker_color='rgba(59,130,246,0.7)',
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=chillers, name="Chiller kWh",
        line=dict(color="#10b981", width=2),
        mode='lines+markers', marker=dict(size=5)
    ))
    fig.update_layout(
        paper_bgcolor='#1a2332', plot_bgcolor='#0f172a',
        font=dict(color='white', size=11),
        xaxis=dict(gridcolor='rgba(255,255,255,0.1)', title="Gun"),
        yaxis=dict(gridcolor='rgba(255,255,255,0.1)', title="kWh"),
        legend=dict(orientation="h", yanchor="bottom", y=-0.25, xanchor="center", x=0.5,
                    font=dict(color='white', size=11)),
        margin=dict(l=50, r=20, t=40, b=50), width=550, height=300,
        barmode='overlay',
        title=dict(text="Gunluk Tuketim Trendi", font=dict(size=14, color='white'))
    )
    return pio.to_image(fig, format="png", scale=2)


def create_comparison_bar_chart(current: Dict, previous: Dict) -> Optional[bytes]:
    """Mevcut ay vs önceki ay karşılaştırma bar grafiği."""
    if not HAS_PLOTLY:
        return None
    
    categories = ["Toplam kWh", "Chiller kWh", "Dogalgaz m3"]
    curr_vals = [current.get("total", 0), current.get("chiller", 0), current.get("gas", 0)]
    prev_vals = [previous.get("total", 0), previous.get("chiller", 0), previous.get("gas", 0)]
    
    fig = go.Figure()
    fig.add_trace(go.Bar(name="Onceki Ay", x=categories, y=prev_vals,
                         marker_color='rgba(156,163,175,0.6)'))
    fig.add_trace(go.Bar(name="Bu Ay", x=categories, y=curr_vals,
                         marker_color='rgba(59,130,246,0.8)'))
    fig.update_layout(
        paper_bgcolor='#1a2332', plot_bgcolor='#0f172a',
        font=dict(color='white', size=12),
        xaxis=dict(gridcolor='rgba(255,255,255,0.1)'),
        yaxis=dict(gridcolor='rgba(255,255,255,0.1)'),
        legend=dict(orientation="h", yanchor="bottom", y=-0.2, xanchor="center", x=0.5,
                    font=dict(color='white', size=11)),
        margin=dict(l=50, r=20, t=40, b=50), width=550, height=300,
        barmode='group',
        title=dict(text="Aylik Karsilastirma", font=dict(size=14, color='white'))
    )
    return pio.to_image(fig, format="png", scale=2)


# ─── PDF Sınıfı ───
class MonthlyReportPDF(FPDF):
    
    ACCENT = (59, 130, 246)
    HEADER_BG = (15, 23, 42)
    SUCCESS = (16, 185, 129)
    WARNING_C = (245, 158, 11)
    DANGER = (239, 68, 68)
    WHITE = (255, 255, 255)
    GRAY = (156, 163, 175)
    
    def __init__(self, year: int, month: int):
        super().__init__()
        self.year = year
        self.month = month
        self.set_auto_page_break(auto=True, margin=20)
        self.font = _setup_unicode_font(self)  # DejaVu varsa Türkçe karakter desteği
    
    def header(self):
        self.set_fill_color(*self.HEADER_BG)
        self.rect(0, 0, 210, 42, 'F')
        self.set_fill_color(*self.ACCENT)
        self.rect(0, 42, 210, 1.5, 'F')
        
        self.set_font(self.font, 'B', 18)
        self.set_text_color(*self.WHITE)
        self.set_y(8)
        self.cell(0, 10, _sanitize("AYLIK ENERJI & HVAC OZET RAPORU"), 0, 1, 'C')
        
        self.set_font(self.font, '', 12)
        self.set_text_color(*self.GRAY)
        ay_adi = AYLAR.get(self.month, str(self.month))
        self.cell(0, 7, _sanitize(f"{ay_adi} {self.year}"), 0, 1, 'C')
        
        self.set_font(self.font, 'I', 9)
        self.cell(0, 5, _sanitize(f"Olusturma: {datetime.now().strftime('%d.%m.%Y %H:%M')} | Acibadem Hastanesi"), 0, 1, 'C')
        self.ln(8)
    
    def footer(self):
        self.set_y(-15)
        self.set_font(self.font, 'I', 8)
        self.set_text_color(*self.GRAY)
        self.cell(0, 10, f'Sayfa {self.page_no()}/{{nb}}', 0, 0, 'C')
    
    def section_title(self, title: str, color: Tuple[int, int, int] = None):
        if color is None:
            color = self.ACCENT
        self.ln(4)
        self.set_fill_color(*color)
        self.rect(10, self.get_y(), 3, 8, 'F')
        self.set_font(self.font, 'B', 13)
        self.set_text_color(40, 40, 40)
        self.set_x(16)
        self.cell(0, 8, _sanitize(title), 0, 1)
        self.ln(2)
    
    def info_box(self, x, y, w, h, label, value, sub="", color=None):
        if color is None:
            color = self.ACCENT
        self.set_fill_color(245, 247, 250)
        self.rect(x, y, w, h, 'F')
        self.set_fill_color(*color)
        self.rect(x, y + 2, 2, h - 4, 'F')
        
        self.set_font(self.font, '', 8)
        self.set_text_color(120, 120, 120)
        self.set_xy(x + 6, y + 3)
        self.cell(w - 10, 4, _sanitize(label), 0, 0)
        
        self.set_font(self.font, 'B', 14)
        self.set_text_color(30, 30, 30)
        self.set_xy(x + 6, y + 9)
        self.cell(w - 10, 8, _sanitize(value), 0, 0)
        
        if sub:
            self.set_font(self.font, '', 7)
            self.set_text_color(*self.GRAY)
            self.set_xy(x + 6, y + 18)
            self.cell(w - 10, 4, _sanitize(sub), 0, 0)
    
    def add_image_from_bytes(self, img_bytes, x, y, w, h=0):
        if img_bytes is None:
            return
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        try:
            tmp.write(img_bytes)
            tmp.close()
            self.image(tmp.name, x=x, y=y, w=w, h=h)
            if h > 0:
                self.set_y(y + h)
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass


# ─── Ana Rapor Üretici ───
class MonthlyReportGenerator:
    
    def __init__(self):
        os.makedirs(REPORTS_DIR, exist_ok=True)
    
    def generate(self, year: int = None, month: int = None) -> str:
        """
        Aylık rapor PDF'i oluştur.
        Varsayılan: önceki ay.
        """
        if year is None or month is None:
            today = date.today()
            first = today.replace(day=1)
            prev = first - timedelta(days=1)
            year, month = prev.year, prev.month
        
        # Önceki ay bilgileri
        if month == 1:
            prev_year, prev_month = year - 1, 12
        else:
            prev_year, prev_month = year, month - 1
        
        # Verileri yükle
        df = load_energy_data()
        hvac_df = load_hvac_history()
        building_area = load_building_area()
        
        # Ay verileri
        current = self._get_month_data(df, year, month)
        previous = self._get_month_data(df, prev_year, prev_month)
        hvac_month = self._get_hvac_month(hvac_df, year, month)
        
        # PDF oluştur
        pdf = MonthlyReportPDF(year, month)
        pdf.alias_nb_pages()
        pdf.add_page()
        
        # 1. ENERJI ÖZET
        self._add_energy_summary(pdf, current, previous)
        
        # 2. m² METRİKLERİ
        if building_area > 0:
            self._add_m2_metrics(pdf, current, building_area)
        
        # 2.5. MALİYET ÖZETİ
        prices = load_unit_prices()
        has_price = prices["electricity"] > 0 or prices["gas"] > 0
        if has_price:
            self._add_cost_summary(pdf, current, previous, prices)
        
        # 3. HVAC PERFORMANS
        self._add_hvac_summary(pdf, hvac_month)
        
        # 4. GRAFİKLER
        self._add_charts(pdf, df, current, previous, year, month)
        
        # 5. GÜNLÜK DETAY TABLOSU
        self._add_daily_table(pdf, df, year, month)
        
        # 6. GENEL DEĞERLENDİRME
        self._add_evaluation(pdf, current, previous, hvac_month, building_area, year, month)
        
        # Kaydet
        ay_adi = AYLAR.get(month, str(month))
        filename = f"aylik_rapor_{year}_{month:02d}_{ay_adi}.pdf"
        filepath = os.path.join(REPORTS_DIR, filename)
        pdf.output(filepath)
        return filepath
    
    def _get_month_data(self, df: pd.DataFrame, year: int, month: int) -> Dict:
        if df.empty:
            return {"total": 0, "chiller": 0, "gas": 0, "grid": 0, "vrf": 0, "days": 0,
                    "avg_total": 0, "avg_chiller": 0, "max_total": 0, "min_total": 0}
        
        mask = df["Tarih"].apply(lambda d: d.year == year and d.month == month if d else False)
        mdf = df[mask]
        if mdf.empty:
            return {"total": 0, "chiller": 0, "gas": 0, "grid": 0, "vrf": 0, "days": 0,
                    "avg_total": 0, "avg_chiller": 0, "max_total": 0, "min_total": 0}
        
        total = float(mdf["Toplam_Hastane_Tuketim_kWh"].fillna(0).sum())
        chiller = float(mdf["Chiller_Tuketim_kWh"].fillna(0).sum())
        gas_k = float(mdf["Kazan_Dogalgaz_m3"].fillna(0).sum())
        gas_j = float(mdf["Kojen_Dogalgaz_m3"].fillna(0).sum())
        gas = gas_k + gas_j
        grid = float(mdf.get("Sebeke_Tuketim_kWh", pd.Series([0])).fillna(0).sum())
        vrf = float(mdf.get("VRF_Split_Tuketim_kWh", pd.Series([0])).fillna(0).sum())
        days = len(mdf)

        totals_series = mdf["Toplam_Hastane_Tuketim_kWh"].fillna(0)

        # Chiller yük yüzdesi (sadece girilmiş günlerin ortalaması)
        if "Chiller_Load_Percent" in mdf.columns:
            _load_vals = mdf["Chiller_Load_Percent"].dropna()
            _load_vals = _load_vals[_load_vals > 0]
            avg_chiller_load = float(_load_vals.mean()) if len(_load_vals) > 0 else None
        else:
            avg_chiller_load = None

        return {
            "total": total, "chiller": chiller, "gas": gas, "grid": grid, "vrf": vrf,
            "days": days,
            "avg_total": total / days if days > 0 else 0,
            "avg_chiller": chiller / days if days > 0 else 0,
            "max_total": float(totals_series.max()),
            "min_total": float(totals_series.min()),
            "avg_chiller_load": avg_chiller_load,
        }
    
    def _get_hvac_month(self, df: pd.DataFrame, year: int, month: int) -> Dict:
        if df.empty:
            return {}
        mask = df["Tarih"].apply(lambda d: d.year == year and d.month == month if d else False)
        mdf = df[mask]
        if mdf.empty:
            return {}
        return {
            "critical": int(mdf.get("Kritik_Sorun_Adet", pd.Series([0])).fillna(0).sum()),
            "warning": int(mdf.get("Uyari_Adet", pd.Series([0])).fillna(0).sum()),
            "optimal": int(mdf.get("Optimal_Adet", pd.Series([0])).fillna(0).sum()),
            "total_eq": int(mdf.get("Toplam_Ekipman", pd.Series([0])).fillna(0).sum()),
            "avg_score": float(mdf.get("Ort_Skor", pd.Series([0])).fillna(0).mean()),
            "analysis_days": len(mdf),
        }
    
    def _pct_change(self, current: float, previous: float) -> str:
        if previous <= 0:
            return ""
        pct = ((current - previous) / previous) * 100
        sign = "+" if pct > 0 else ""
        return f"{sign}{pct:.1f}% onceki aya gore"
    
    def _add_energy_summary(self, pdf: MonthlyReportPDF, current: Dict, previous: Dict):
        pdf.section_title("AYLIK ENERJI OZETI", pdf.ACCENT)
        
        y = pdf.get_y()
        bw = 44
        gap = 3
        
        pdf.info_box(10, y, bw, 26, "Toplam Tuketim",
                     f"{current['total']:,.0f} kWh".replace(",", "."),
                     self._pct_change(current["total"], previous["total"]), pdf.ACCENT)
        pdf.info_box(10 + bw + gap, y, bw, 26, "Chiller",
                     f"{current['chiller']:,.0f} kWh".replace(",", "."),
                     self._pct_change(current["chiller"], previous["chiller"]), (16, 185, 129))
        pdf.info_box(10 + 2*(bw + gap), y, bw, 26, "Dogalgaz",
                     f"{current['gas']:,.0f} m3".replace(",", "."),
                     self._pct_change(current["gas"], previous["gas"]), (239, 68, 68))
        pdf.info_box(10 + 3*(bw + gap), y, bw, 26, "Veri Girilen Gun",
                     str(current["days"]),
                     f"/ {calendar.monthrange(pdf.year, pdf.month)[1]} gun", (139, 92, 246))
        
        pdf.set_y(y + 30)
        
        # Günlük ortalamalar satırı
        y2 = pdf.get_y()
        bw2 = 45
        
        pdf.info_box(10, y2, bw2, 22, "Gunluk Ort. Tuketim",
                     f"{current['avg_total']:,.0f} kWh".replace(",", "."), "", pdf.ACCENT)
        pdf.info_box(10 + bw2 + gap, y2, bw2, 22, "Gunluk Ort. Chiller",
                     f"{current['avg_chiller']:,.0f} kWh".replace(",", "."), "", (16, 185, 129))
        pdf.info_box(10 + 2*(bw2 + gap), y2, bw2, 22, "Max Gun",
                     f"{current['max_total']:,.0f} kWh".replace(",", "."), "", (239, 68, 68))
        pdf.info_box(10 + 3*(bw2 + gap), y2, bw2, 22, "Min Gun",
                     f"{current['min_total']:,.0f} kWh".replace(",", "."), "", (16, 185, 129))
        
        pdf.set_y(y2 + 26)
    
    def _add_m2_metrics(self, pdf: MonthlyReportPDF, current: Dict, area: float):
        pdf.section_title("m2 BASINA AYLIK TUKETIM", (139, 92, 246))
        
        y = pdf.get_y()
        bw = 60
        gap = 5
        
        gas_kwh = current["gas"] * GAS_TO_KWH
        
        pdf.info_box(10, y, bw, 22, "Sogutma kWh/m2",
                     f"{current['chiller'] / area:.3f}",
                     f"Alan: {area:,.0f} m2".replace(",", "."), (59, 130, 246))
        pdf.info_box(10 + bw + gap, y, bw, 22, "Isitma kWh/m2",
                     f"{gas_kwh / area:.3f}", "", (239, 68, 68))
        pdf.info_box(10 + 2*(bw + gap), y, bw, 22, "Toplam kWh/m2",
                     f"{current['total'] / area:.3f}", "", (139, 92, 246))
        
        pdf.set_y(y + 26)
    
    def _add_cost_summary(self, pdf: MonthlyReportPDF, current: Dict, previous: Dict, prices: Dict):
        """Aylık maliyet özet kutuları."""
        pdf.section_title("AYLIK MALIYET OZETI (TL)", (245, 158, 11))
        
        cost_elec = current["grid"] * prices["electricity"] if prices["electricity"] > 0 else 0
        cost_gas = current["gas"] * prices["gas"] if prices["gas"] > 0 else 0
        cost_total = cost_elec + cost_gas
        
        # Önceki ay maliyeti
        prev_cost_elec = previous["grid"] * prices["electricity"] if prices["electricity"] > 0 else 0
        prev_cost_gas = previous["gas"] * prices["gas"] if prices["gas"] > 0 else 0
        prev_cost_total = prev_cost_elec + prev_cost_gas
        
        avg_daily_cost = cost_total / current["days"] if current["days"] > 0 else 0
        
        y = pdf.get_y()
        bw = 45
        gap = 3
        
        if prices["electricity"] > 0:
            pdf.info_box(10, y, bw, 22, "Elektrik Maliyeti",
                         f"{cost_elec:,.0f} TL".replace(",", "."),
                         f"{prices['electricity']:.2f} TL/kWh", (59, 130, 246))
        
        if prices["gas"] > 0:
            pdf.info_box(10 + bw + gap, y, bw, 22, "Dogalgaz Maliyeti",
                         f"{cost_gas:,.0f} TL".replace(",", "."),
                         f"{prices['gas']:.2f} TL/m3", (239, 68, 68))
        
        pdf.info_box(10 + 2*(bw + gap), y, bw, 22, "Toplam Maliyet",
                     f"{cost_total:,.0f} TL".replace(",", "."),
                     self._pct_change(cost_total, prev_cost_total), (245, 158, 11))
        
        pdf.info_box(10 + 3*(bw + gap), y, bw, 22, "Gunluk Ort. Maliyet",
                     f"{avg_daily_cost:,.0f} TL".replace(",", "."),
                     "", (139, 92, 246))
        
        pdf.set_y(y + 26)
    
    def _add_hvac_summary(self, pdf: MonthlyReportPDF, hvac: Dict):
        pdf.section_title("AYLIK HVAC PERFORMANS OZETI", (16, 185, 129))
        
        critical = hvac.get("critical", 0)
        warning = hvac.get("warning", 0)
        optimal = hvac.get("optimal", 0)
        days = hvac.get("analysis_days", 0)
        avg_score = hvac.get("avg_score", 0)
        
        penalty_avg = 0
        if days > 0:
            penalty_avg = ((critical * 15) + (warning * 5)) / days
        health = max(0, int(100 - penalty_avg))
        
        y = pdf.get_y()
        bw = 35
        gap = 3
        
        pdf.info_box(10, y, bw, 24, "Toplam Kritik", str(critical), "", pdf.DANGER)
        pdf.info_box(10 + bw + gap, y, bw, 24, "Toplam Uyari", str(warning), "", pdf.WARNING_C)
        pdf.info_box(10 + 2*(bw + gap), y, bw, 24, "Toplam Optimal", str(optimal), "", pdf.SUCCESS)
        pdf.info_box(10 + 3*(bw + gap), y, bw, 24, "Analiz Gunu", str(days), "", pdf.GRAY)
        
        health_color = pdf.SUCCESS if health >= 80 else pdf.WARNING_C if health >= 50 else pdf.DANGER
        pdf.info_box(10 + 4*(bw + gap), y, bw + 5, 24, "Ort. Saglik",
                     f"%{health}",
                     "Iyi" if health >= 80 else "Dikkat" if health >= 50 else "Kritik",
                     health_color)
        
        pdf.set_y(y + 28)
    
    def _add_charts(self, pdf: MonthlyReportPDF, df, current, previous, year, month):
        if pdf.get_y() > 140:
            pdf.add_page()
        pdf.section_title("GRAFIKLER", (245, 158, 11))
        
        y_start = pdf.get_y()
        
        # Pasta grafiği
        try:
            gas_kwh = current["gas"] * GAS_TO_KWH
            pie_img = create_monthly_pie_chart(current["total"], current["chiller"], gas_kwh)
            if pie_img:
                pdf.add_image_from_bytes(pie_img, 10, y_start, 90, h=65)
        except Exception:
            pass
        
        # Karşılaştırma grafiği
        try:
            comp_img = create_comparison_bar_chart(current, previous)
            if comp_img:
                pdf.add_image_from_bytes(comp_img, 105, y_start, 95, h=65)
        except Exception:
            pass
        
        pdf.set_y(y_start + 65)
        
        # Yeni sayfa — günlük trend
        pdf.add_page()
        pdf.section_title("GUNLUK TUKETIM TRENDI", (59, 130, 246))
        
        try:
            trend_img = create_daily_trend_chart(df, year, month)
            if trend_img:
                pdf.add_image_from_bytes(trend_img, 15, pdf.get_y(), 180, h=75)
        except Exception:
            pass
    
    def _add_daily_table(self, pdf: MonthlyReportPDF, df: pd.DataFrame, year: int, month: int):
        """Günlük detay tablosu."""
        if pdf.get_y() > 220:
            pdf.add_page()
        pdf.section_title("GUNLUK DETAY TABLOSU", (59, 130, 246))
        
        if df.empty:
            pdf.set_font(pdf.font, 'I', 10)
            pdf.set_text_color(120, 120, 120)
            pdf.set_x(10)
            pdf.cell(190, 8, _sanitize("Veri bulunamadi"), 0, 1)
            return
        
        mask = df["Tarih"].apply(lambda d: d.year == year and d.month == month if d else False)
        mdf = df[mask].sort_values("Tarih")
        
        if mdf.empty:
            pdf.set_font(pdf.font, 'I', 10)
            pdf.set_text_color(120, 120, 120)
            pdf.set_x(10)
            pdf.cell(190, 8, _sanitize("Bu ay icin veri bulunamadi"), 0, 1)
            return
        
        # Tablo başlığı
        pdf.set_font(pdf.font, 'B', 8)
        pdf.set_fill_color(30, 41, 59)
        pdf.set_text_color(255, 255, 255)
        
        cols = [("Tarih", 25), ("Toplam kWh", 30), ("Chiller kWh", 28), 
                ("Dogalgaz m3", 27), ("Sebeke kWh", 27), ("VRF kWh", 23),
                ("Dis Hava C", 23)]
        
        for header, w in cols:
            pdf.cell(w, 7, _sanitize(header), 1, 0, 'C', True)
        pdf.ln()
        
        # Satırlar
        pdf.set_font(pdf.font, '', 7)
        for i, (_, row) in enumerate(mdf.iterrows()):
            if pdf.get_y() > 245:
                pdf.add_page()
                pdf.set_font(pdf.font, 'B', 8)
                pdf.set_fill_color(30, 41, 59)
                pdf.set_text_color(255, 255, 255)
                for header, w in cols:
                    pdf.cell(w, 7, _sanitize(header), 1, 0, 'C', True)
                pdf.ln()
                pdf.set_font(pdf.font, '', 7)
            
            bg = (248, 250, 252) if i % 2 == 0 else (255, 255, 255)
            pdf.set_fill_color(*bg)
            pdf.set_text_color(50, 50, 50)
            
            d = row.get("Tarih", "")
            d_str = d.strftime("%d.%m") if hasattr(d, 'strftime') else str(d)
            
            vals = [
                d_str,
                f"{float(row.get('Toplam_Hastane_Tuketim_kWh', 0) or 0):,.0f}".replace(",", "."),
                f"{float(row.get('Chiller_Tuketim_kWh', 0) or 0):,.0f}".replace(",", "."),
                f"{float(row.get('Kazan_Dogalgaz_m3', 0) or 0) + float(row.get('Kojen_Dogalgaz_m3', 0) or 0):,.0f}".replace(",", "."),
                f"{float(row.get('Sebeke_Tuketim_kWh', 0) or 0):,.0f}".replace(",", "."),
                f"{float(row.get('VRF_Split_Tuketim_kWh', 0) or 0):,.0f}".replace(",", "."),
                f"{float(row.get('Dis_Hava_Sicakligi_C', 0) or 0):.1f}",
            ]
            
            for j, ((_, w), v) in enumerate(zip(cols, vals)):
                pdf.cell(w, 6, _sanitize(v), 1, 0, 'C', True)
            pdf.ln()
        
        pdf.ln(4)
    
    def _add_evaluation(self, pdf, current, previous, hvac, area, year, month):
        pdf.section_title("GENEL DEGERLENDIRME", (16, 185, 129))
        
        ay_adi = AYLAR.get(month, str(month))
        lines = []
        
        # Enerji değerlendirmesi
        if previous["total"] > 0:
            pct = ((current["total"] - previous["total"]) / previous["total"]) * 100
            if pct < -5:
                lines.append(f"[+] {ay_adi} ayi toplam tuketim onceki aya gore %{abs(pct):.1f} azalmistir.")
            elif pct > 5:
                lines.append(f"[!] {ay_adi} ayi toplam tuketim onceki aya gore %{pct:.1f} artmistir.")
            else:
                lines.append(f"[-] {ay_adi} ayi tuketimi onceki ayla benzer seviyededir (%{pct:+.1f}).")
        else:
            lines.append(f"[-] Onceki ay verisi bulunamadi.")
        
        # Tüketim detayları
        lines.append(f"[-] {current['days']} gun veri girilmis, gunluk ortalama: {current['avg_total']:,.0f} kWh.".replace(",", "."))
        
        if current["max_total"] > 0:
            lines.append(f"[-] En yuksek gun: {current['max_total']:,.0f} kWh, en dusuk: {current['min_total']:,.0f} kWh.".replace(",", "."))
        
        # HVAC
        critical = hvac.get("critical", 0)
        warning = hvac.get("warning", 0)
        if critical > 0 or warning > 0:
            lines.append(f"[!] Ay boyunca toplam {critical} kritik sorun ve {warning} uyari kaydedilmistir.")
        else:
            lines.append(f"[+] Ay boyunca kritik sorun kaydedilmemistir.")
        
        # Chiller COP değerlendirmesi
        avg_load = current.get("avg_chiller_load")
        if avg_load is not None and avg_load > 0:
            cop = _calculate_chiller_cop(avg_load)
            lines.append(f"[-] Hesaplanan Ortalama Chiller COP: {cop:.2f} (Ort. Kapasite: %{avg_load:.1f})")

        # m² değerlendirmesi
        if area > 0 and current["total"] > 0:
            kwh_m2 = current["total"] / area
            lines.append(f"[-] Aylik metrekare basina tuketim: {kwh_m2:.3f} kWh/m2.")

        # Maliyet değerlendirmesi
        prices = load_unit_prices()
        if prices["electricity"] > 0 or prices["gas"] > 0:
            cost_elec = current["grid"] * prices["electricity"]
            cost_gas = current["gas"] * prices["gas"]
            cost_total = cost_elec + cost_gas
            lines.append(f"[-] Aylik tahmini toplam maliyet: {cost_total:,.0f} TL.".replace(",", "."))
        
        # Sonuç
        lines.append("")
        if critical == 0 and (previous["total"] <= 0 or ((current["total"] - previous["total"]) / previous["total"] * 100) < 5):
            lines.append(f"SONUC: {ay_adi} {year} genel olarak iyi performans donemi olmustur.")
        elif critical > 10:
            lines.append(f"SONUC: {ay_adi} {year} doneminde ciddi sorunlar yasanmistir. Detayli inceleme onerilir.")
        else:
            lines.append(f"SONUC: {ay_adi} {year} kabul edilebilir seviyededir. Uyarilarin takibi onemlidir.")
        
        # PDF'e yaz
        pdf.set_font(pdf.font, '', 10)
        pdf.set_text_color(50, 50, 50)
        
        for line in lines:
            if not line.strip():
                pdf.ln(3)
                continue
            pdf.set_x(10)
            if line.startswith("[+]"):
                pdf.set_text_color(16, 185, 129)
            elif line.startswith("[!]"):
                pdf.set_text_color(239, 68, 68)
            elif line.startswith("SONUC"):
                pdf.set_font(pdf.font, 'B', 10)
                pdf.set_text_color(59, 130, 246)
            else:
                pdf.set_text_color(80, 80, 80)
            pdf.multi_cell(190, 6, _sanitize(line))
            pdf.set_font(pdf.font, '', 10)
        
        pdf.ln(4)
        
        # Alt bilgi
        pdf.set_fill_color(240, 245, 255)
        pdf.rect(10, pdf.get_y(), 190, 12, 'F')
        pdf.set_font(pdf.font, 'I', 8)
        pdf.set_text_color(100, 100, 100)
        pdf.set_x(15)
        pdf.cell(180, 12, _sanitize(
            f"Bu rapor HVAC Enerji Yonetim Sistemi tarafindan {datetime.now().strftime('%d.%m.%Y %H:%M')} tarihinde otomatik olusturulmustur."
        ), 0, 1)


if __name__ == "__main__":
    gen = MonthlyReportGenerator()
    path = gen.generate()
    print(f"Rapor olusturuldu: {path}")
