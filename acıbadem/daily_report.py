# daily_report.py
# Günlük Özet PDF Raporu Oluşturucu
# Her gün saat 17:00'da önceki günün verilerini derleyerek modern PDF rapor üretir.

from __future__ import annotations

import os
import json
import io
import tempfile
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
    REPORTS_DIR = _lm.get_data_path("daily_reports")
except Exception:
    DATA_FILE = os.path.join(BASE_DIR, "energy_data.csv")
    SETTINGS_FILE = os.path.join(BASE_DIR, "configs", "hvac_settings.json")
    REPORTS_DIR = os.path.join(BASE_DIR, "daily_reports")
GAS_TO_KWH = 10.64  # 1 m³ doğalgaz ≈ 10.64 kWh

# ─── PDF Metin Temizleme (sadece emoji/sembol → ASCII, Türkçe korunur) ───
def _sanitize(text: str) -> str:
    if text is None:
        return ""
    replacements = {
        "•": "-", "→": "->", "←": "<-", "↑": "^", "↓": "v",
        "📊": "", "✅": "[OK]", "❌": "[X]", "⚠️": "[!]",
        "📈": "", "📉": "", "🔹": "*", "❄️": "", "🔥": "",
        "🟢": "[+]", "🟡": "[-]", "🔴": "[!]",
        "📄": "", "📐": "", "⚡": "", "🏥": "",
    }
    for char, rep in replacements.items():
        text = text.replace(char, rep)
    return text


def _setup_unicode_font(pdf):
    """PDF nesnesine DejaVu Unicode font ekler — Türkçe karakterler doğru basılır."""
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
    return "Helvetica"  # fallback


# ─── Veri Yükleme ───
def load_energy_data() -> pd.DataFrame:
    """energy_data.csv'den enerji verilerini yükle."""
    if not os.path.exists(DATA_FILE):
        return pd.DataFrame()
    df = pd.read_csv(DATA_FILE)
    if "Tarih" in df.columns:
        df["Tarih"] = pd.to_datetime(df["Tarih"], format="%Y-%m-%d", errors="coerce").dt.date
    return df


def load_hvac_history() -> pd.DataFrame:
    """HVAC analiz geçmişini yükle."""
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
    """Hastane m² bilgisini settings'ten yükle."""
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


def load_last_analysis() -> List[Dict]:
    """Son HVAC analiz sonuçlarını yükle."""
    try:
        results_file = os.path.join(BASE_DIR, "configs", "last_analysis.json")
        if os.path.exists(results_file):
            with open(results_file, "r", encoding="utf-8") as f:
                return json.load(f)
    except Exception:
        pass
    return []


# ─── Plotly Grafik Üretimi ───
def create_energy_pie_chart(total_kwh: float, chiller_kwh: float, gas_kwh: float) -> Optional[bytes]:
    """Enerji dağılım pasta grafiği oluştur."""
    if not HAS_PLOTLY:
        return None
    
    other = max(0, total_kwh - chiller_kwh - gas_kwh)
    labels = ["Sogutma (Chiller)", "Isitma (Dogalgaz)", "Diger"]
    values = [chiller_kwh, gas_kwh, other]
    colors = ["#3b82f6", "#ef4444", "#8b5cf6"]
    
    fig = go.Figure(data=[go.Pie(
        labels=labels, values=values,
        hole=0.45,
        marker=dict(colors=colors, line=dict(color='#1a2332', width=2)),
        textinfo='label+percent',
        textfont=dict(size=13, color='white'),
        insidetextorientation='radial'
    )])
    fig.update_layout(
        paper_bgcolor='#1a2332',
        plot_bgcolor='#1a2332',
        font=dict(color='white', size=12),
        showlegend=True,
        legend=dict(
            orientation="h", yanchor="bottom", y=-0.15,
            xanchor="center", x=0.5, font=dict(color='white', size=11)
        ),
        margin=dict(l=20, r=20, t=30, b=40),
        width=500, height=350,
        title=dict(text="Enerji Dagilim", font=dict(size=16, color='white'))
    )
    return pio.to_image(fig, format="png", scale=2)


def create_weekly_trend_chart(df: pd.DataFrame, report_date: date) -> Optional[bytes]:
    """Son 7 günlük tüketim trend grafiği."""
    if not HAS_PLOTLY or df.empty:
        return None
    
    end = report_date
    start = end - timedelta(days=6)
    mask = (df["Tarih"] >= start) & (df["Tarih"] <= end)
    week_df = df[mask].sort_values("Tarih")
    
    if week_df.empty:
        return None
    
    dates = [d.strftime("%d/%m") for d in week_df["Tarih"]]
    totals = week_df["Toplam_Hastane_Tuketim_kWh"].fillna(0).tolist()
    chillers = week_df["Chiller_Tuketim_kWh"].fillna(0).tolist()
    
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=dates, y=totals, name="Toplam",
        line=dict(color="#3b82f6", width=3),
        fill='tozeroy', fillcolor='rgba(59,130,246,0.15)',
        mode='lines+markers', marker=dict(size=8)
    ))
    fig.add_trace(go.Scatter(
        x=dates, y=chillers, name="Chiller",
        line=dict(color="#10b981", width=2, dash='dot'),
        mode='lines+markers', marker=dict(size=6)
    ))
    fig.update_layout(
        paper_bgcolor='#1a2332',
        plot_bgcolor='#0f172a',
        font=dict(color='white', size=12),
        xaxis=dict(gridcolor='rgba(255,255,255,0.1)', title="Tarih"),
        yaxis=dict(gridcolor='rgba(255,255,255,0.1)', title="kWh"),
        legend=dict(
            orientation="h", yanchor="bottom", y=-0.25,
            xanchor="center", x=0.5, font=dict(color='white', size=11)
        ),
        margin=dict(l=50, r=20, t=40, b=50),
        width=550, height=300,
        title=dict(text="Son 7 Gun Tuketim Trendi", font=dict(size=14, color='white'))
    )
    return pio.to_image(fig, format="png", scale=2)


def create_health_gauge(score: int) -> Optional[bytes]:
    """Sistem sağlık göstergesi gauge grafiği."""
    if not HAS_PLOTLY:
        return None
    
    color = "#10b981" if score >= 80 else "#f59e0b" if score >= 50 else "#ef4444"
    
    fig = go.Figure(go.Indicator(
        mode="gauge+number",
        value=score,
        number=dict(suffix="%", font=dict(size=36, color='white')),
        gauge=dict(
            axis=dict(range=[0, 100], tickwidth=2, tickcolor='white',
                      tickfont=dict(color='white', size=10)),
            bar=dict(color=color, thickness=0.6),
            bgcolor='rgba(255,255,255,0.05)',
            borderwidth=2, bordercolor='rgba(255,255,255,0.2)',
            steps=[
                dict(range=[0, 50], color="rgba(239,68,68,0.15)"),
                dict(range=[50, 80], color="rgba(245,158,11,0.15)"),
                dict(range=[80, 100], color="rgba(16,185,129,0.15)"),
            ],
        ),
    ))
    fig.update_layout(
        paper_bgcolor='#1a2332',
        font=dict(color='white'),
        margin=dict(l=30, r=30, t=30, b=10),
        width=280, height=200,
    )
    return pio.to_image(fig, format="png", scale=2)


# ─── PDF Sınıfı ───
class DailyReportPDF(FPDF):
    
    ACCENT = (59, 130, 246)     # Mavi
    DARK_BG = (26, 35, 50)     # Koyu arka plan
    HEADER_BG = (15, 23, 42)   # Başlık arka plan
    SUCCESS = (16, 185, 129)   # Yeşil
    WARNING_C = (245, 158, 11) # Turuncu
    DANGER = (239, 68, 68)     # Kırmızı
    WHITE = (255, 255, 255)
    GRAY = (156, 163, 175)
    
    def __init__(self, report_date: date):
        super().__init__()
        self.report_date = report_date
        self.set_auto_page_break(auto=True, margin=20)
        self.font = _setup_unicode_font(self)  # DejaVu varsa Türkçe karakter desteği
    
    def header(self):
        # Gradient header simulation
        self.set_fill_color(*self.HEADER_BG)
        self.rect(0, 0, 210, 40, 'F')
        
        # Accent line
        self.set_fill_color(*self.ACCENT)
        self.rect(0, 40, 210, 1.5, 'F')
        
        # Title
        self.set_font(self.font, 'B', 18)
        self.set_text_color(*self.WHITE)
        self.set_y(8)
        self.cell(0, 10, _sanitize("GUNLUK ENERJI & HVAC RAPORU"), 0, 1, 'C')
        
        # Date
        self.set_font(self.font, '', 11)
        self.set_text_color(*self.GRAY)
        date_str = self.report_date.strftime("%d.%m.%Y")
        self.cell(0, 6, _sanitize(f"Rapor Tarihi: {date_str} | Olusturma: {datetime.now().strftime('%H:%M')}"), 0, 1, 'C')
        
        # Hospital name
        self.set_font(self.font, 'I', 9)
        self.cell(0, 5, _sanitize("Acibadem Hastanesi - Enerji Yonetim Sistemi"), 0, 1, 'C')
        self.ln(8)
    
    def footer(self):
        self.set_y(-15)
        self.set_font(self.font, 'I', 8)
        self.set_text_color(*self.GRAY)
        self.cell(0, 10, f'Sayfa {self.page_no()}/{{nb}}', 0, 0, 'C')
    
    def section_title(self, icon: str, title: str, color: Tuple[int, int, int] = None):
        """Modern bölüm başlığı."""
        if color is None:
            color = self.ACCENT
        self.ln(4)
        self.set_fill_color(*color)
        self.rect(10, self.get_y(), 3, 8, 'F')
        self.set_font(self.font, 'B', 13)
        self.set_text_color(40, 40, 40)
        self.set_x(16)
        self.cell(0, 8, _sanitize(f"{icon} {title}"), 0, 1)
        self.ln(2)
    
    def info_box(self, x: float, y: float, w: float, h: float,
                 label: str, value: str, sub: str = "", 
                 color: Tuple[int, int, int] = None):
        """Bilgi kutusu (KPI kartı)."""
        if color is None:
            color = self.ACCENT
        
        # Arka plan
        self.set_fill_color(245, 247, 250)
        self.rounded_rect(x, y, w, h, 3, 'F')
        
        # Sol renk çizgisi
        self.set_fill_color(*color)
        self.rect(x, y + 2, 2, h - 4, 'F')
        
        # Label
        self.set_font(self.font, '', 8)
        self.set_text_color(120, 120, 120)
        self.set_xy(x + 6, y + 3)
        self.cell(w - 10, 4, _sanitize(label), 0, 0)
        
        # Value
        self.set_font(self.font, 'B', 14)
        self.set_text_color(30, 30, 30)
        self.set_xy(x + 6, y + 9)
        self.cell(w - 10, 8, _sanitize(value), 0, 0)
        
        # Sub
        if sub:
            self.set_font(self.font, '', 7)
            color_sub = self.SUCCESS if "+" not in sub else self.DANGER if "-" in sub else self.GRAY
            self.set_text_color(*color_sub)
            self.set_xy(x + 6, y + 18)
            self.cell(w - 10, 4, _sanitize(sub), 0, 0)
    
    def rounded_rect(self, x, y, w, h, r, style=''):
        """Yuvarlatılmış köşeli dikdörtgen (basitleştirilmiş)."""
        # fpdf2 rounded_rect yerine basit rect kullanıyoruz
        self.rect(x, y, w, h, style)
    
    def add_image_from_bytes(self, img_bytes: bytes, x: float, y: float, w: float):
        """Plotly grafik resmini PDF'e ekle."""
        if img_bytes is None:
            return
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        try:
            tmp.write(img_bytes)
            tmp.close()
            self.image(tmp.name, x=x, y=y, w=w)
        finally:
            try:
                os.unlink(tmp.name)
            except Exception:
                pass


# ─── Ana Rapor Üretici ───
class DailyReportGenerator:
    
    def __init__(self):
        os.makedirs(REPORTS_DIR, exist_ok=True)
    
    def generate(self, target_date: date = None) -> str:
        """
        Günlük rapor PDF'i oluştur.
        
        Args:
            target_date: Rapor tarihi (varsayılan: dün)
        
        Returns:
            str: Oluşturulan PDF dosya yolu
        """
        if target_date is None:
            target_date = date.today() - timedelta(days=1)
        
        compare_date = target_date - timedelta(days=1)
        
        # Verileri yükle
        df = load_energy_data()
        hvac_df = load_hvac_history()
        building_area = load_building_area()
        
        # Rapor günü verileri
        report_row = self._get_day_data(df, target_date)
        compare_row = self._get_day_data(df, compare_date)
        hvac_day = self._get_hvac_day(hvac_df, target_date)
        
        # PDF oluştur
        pdf = DailyReportPDF(target_date)
        pdf.alias_nb_pages()
        pdf.add_page()
        
        # 1. ENERJI ÖZET KUTULARI
        self._add_energy_summary(pdf, report_row, compare_row)
        
        # 2. m² METRİKLERİ
        if building_area > 0:
            self._add_m2_metrics(pdf, report_row, building_area)
        
        # 2.5. MALİYET ÖZETİ
        prices = load_unit_prices()
        has_price = prices["electricity"] > 0 or prices["gas"] > 0
        if has_price:
            self._add_cost_summary(pdf, report_row, prices)
        
        # 3. HVAC PERFORMANS ÖZETİ 
        self._add_hvac_summary(pdf, hvac_day)
        
        # 4. GRAFİKLER
        self._add_charts(pdf, df, report_row, target_date)
        
        # 5. SANTRAL VERİMLİLİK TABLOSU
        self._add_equipment_table(pdf, hvac_day)
        
        # 6. GENEL DEĞERLENDİRME
        self._add_evaluation(pdf, report_row, compare_row, hvac_day, building_area)
        
        # Kaydet
        filename = f"gunluk_rapor_{target_date.strftime('%Y%m%d')}.pdf"
        filepath = os.path.join(REPORTS_DIR, filename)
        pdf.output(filepath)
        
        return filepath
    
    def _get_day_data(self, df: pd.DataFrame, d: date) -> Dict:
        """Belirli bir günün enerji verilerini dict olarak al."""
        if df.empty:
            return {}
        mask = df["Tarih"] == d
        rows = df[mask]
        if rows.empty:
            return {}
        row = rows.iloc[0]
        return {
            "total": float(row.get("Toplam_Hastane_Tuketim_kWh", 0) or 0),
            "chiller": float(row.get("Chiller_Tuketim_kWh", 0) or 0),
            "grid": float(row.get("Sebeke_Tuketim_kWh", 0) or 0),
            "gas_kazan": float(row.get("Kazan_Dogalgaz_m3", 0) or 0),
            "gas_kojen": float(row.get("Kojen_Dogalgaz_m3", 0) or 0),
            "vrf": float(row.get("VRF_Split_Tuketim_kWh", 0) or 0),
            "oat": float(row.get("Dis_Hava_Sicakligi_C", 0) or 0),
            "chiller_set": float(row.get("Chiller_Set_C", 0) or 0),
        }
    
    def _get_hvac_day(self, df: pd.DataFrame, d: date) -> Dict:
        """HVAC analiz geçmişinden günlük özet."""
        if df.empty:
            return {}
        mask = df["Tarih"] == d
        rows = df[mask]
        if rows.empty:
            return {}
        row = rows.iloc[-1]  # Son analiz
        return {
            "critical": int(row.get("Kritik_Sorun_Adet", 0) or 0),
            "warning": int(row.get("Uyari_Adet", 0) or 0),
            "optimal": int(row.get("Optimal_Adet", 0) or 0),
            "total_eq": int(row.get("Toplam_Ekipman", 0) or 0),
            "avg_score": float(row.get("Ort_Skor", 0) or 0),
        }
    
    def _pct_change(self, current: float, previous: float) -> str:
        """Yüzde değişim string'i."""
        if previous <= 0:
            return ""
        pct = ((current - previous) / previous) * 100
        sign = "+" if pct > 0 else ""
        return f"{sign}{pct:.1f}% onceki gune gore"
    
    def _add_energy_summary(self, pdf: DailyReportPDF, report: Dict, compare: Dict):
        """Enerji özet kutuları."""
        pdf.section_title("", "ENERJI OZETI", pdf.ACCENT)
        
        total = report.get("total", 0)
        chiller = report.get("chiller", 0)
        gas = report.get("gas_kazan", 0) + report.get("gas_kojen", 0)
        grid = report.get("grid", 0)
        
        comp_total = compare.get("total", 0)
        comp_chiller = compare.get("chiller", 0)
        comp_gas = compare.get("gas_kazan", 0) + compare.get("gas_kojen", 0)
        
        y = pdf.get_y()
        box_w = 44
        gap = 3
        
        pdf.info_box(10, y, box_w, 26, "Toplam Tuketim",
                     f"{total:,.0f} kWh".replace(",", "."),
                     self._pct_change(total, comp_total), pdf.ACCENT)
        
        pdf.info_box(10 + box_w + gap, y, box_w, 26, "Chiller (Sogutma)",
                     f"{chiller:,.0f} kWh".replace(",", "."),
                     self._pct_change(chiller, comp_chiller), (16, 185, 129))
        
        pdf.info_box(10 + 2*(box_w + gap), y, box_w, 26, "Dogalgaz",
                     f"{gas:,.0f} m3".replace(",", "."),
                     self._pct_change(gas, comp_gas), (239, 68, 68))
        
        pdf.info_box(10 + 3*(box_w + gap), y, box_w, 26, "Sebeke",
                     f"{grid:,.0f} kWh".replace(",", "."),
                     "", (139, 92, 246))
        
        pdf.set_y(y + 30)
    
    def _add_m2_metrics(self, pdf: DailyReportPDF, report: Dict, area: float):
        """m² başına tüketim kutuları."""
        pdf.section_title("", "m2 BASINA TUKETIM", (139, 92, 246))
        
        total = report.get("total", 0)
        chiller = report.get("chiller", 0)
        gas = (report.get("gas_kazan", 0) + report.get("gas_kojen", 0)) * GAS_TO_KWH
        
        y = pdf.get_y()
        box_w = 60
        gap = 5
        
        pdf.info_box(10, y, box_w, 22, "Sogutma kWh/m2",
                     f"{chiller / area:.3f}",
                     f"Alan: {area:,.0f} m2".replace(",", "."), (59, 130, 246))
        
        pdf.info_box(10 + box_w + gap, y, box_w, 22, "Isitma kWh/m2",
                     f"{gas / area:.3f}",
                     "", (239, 68, 68))
        
        pdf.info_box(10 + 2*(box_w + gap), y, box_w, 22, "Toplam kWh/m2",
                     f"{total / area:.3f}",
                     "", (139, 92, 246))
        
        pdf.set_y(y + 26)
    
    def _add_cost_summary(self, pdf: DailyReportPDF, report: Dict, prices: Dict):
        """Maliyet özet kutuları."""
        pdf.section_title("", "MALIYET OZETI (TL)", (245, 158, 11))
        
        total_kwh = report.get("total", 0)
        grid_kwh = report.get("grid", 0)
        gas_m3 = report.get("gas_kazan", 0) + report.get("gas_kojen", 0)
        
        cost_elec = grid_kwh * prices["electricity"] if prices["electricity"] > 0 else 0
        cost_gas = gas_m3 * prices["gas"] if prices["gas"] > 0 else 0
        cost_total = cost_elec + cost_gas
        
        y = pdf.get_y()
        bw = 60
        gap = 5
        
        if prices["electricity"] > 0:
            pdf.info_box(10, y, bw, 22, "Sebeke Elektrik Maliyeti",
                         f"{cost_elec:,.0f} TL".replace(",", "."),
                         f"{prices['electricity']:.2f} TL/kWh | {grid_kwh:,.0f} kWh".replace(",", "."), (59, 130, 246))
        
        if prices["gas"] > 0:
            pdf.info_box(10 + bw + gap, y, bw, 22, "Dogalgaz Maliyeti",
                         f"{cost_gas:,.0f} TL".replace(",", "."),
                         f"{prices['gas']:.2f} TL/m3", (239, 68, 68))
        
        pdf.info_box(10 + 2*(bw + gap), y, bw, 22, "Toplam Maliyet",
                     f"{cost_total:,.0f} TL".replace(",", "."),
                     "", (245, 158, 11))
        
        pdf.set_y(y + 26)
    
    def _add_hvac_summary(self, pdf: DailyReportPDF, hvac: Dict):
        """HVAC performans özeti."""
        pdf.section_title("", "HVAC PERFORMANS OZETI", (16, 185, 129))
        
        critical = hvac.get("critical", 0)
        warning = hvac.get("warning", 0)
        optimal = hvac.get("optimal", 0)
        total_eq = hvac.get("total_eq", 0)
        
        # Sağlık skoru
        penalty = (critical * 15) + (warning * 5)
        health = max(0, 100 - penalty)
        
        y = pdf.get_y()
        box_w = 35
        gap = 3
        
        pdf.info_box(10, y, box_w, 24, "Kritik",
                     str(critical), "", pdf.DANGER)
        pdf.info_box(10 + box_w + gap, y, box_w, 24, "Uyari",
                     str(warning), "", pdf.WARNING_C)
        pdf.info_box(10 + 2*(box_w + gap), y, box_w, 24, "Optimal",
                     str(optimal), "", pdf.SUCCESS)
        pdf.info_box(10 + 3*(box_w + gap), y, box_w, 24, "Toplam",
                     str(total_eq), "", pdf.GRAY)
        
        # Sağlık skoru gauge
        health_color = pdf.SUCCESS if health >= 80 else pdf.WARNING_C if health >= 50 else pdf.DANGER
        pdf.info_box(10 + 4*(box_w + gap), y, box_w + 5, 24, "Saglik Skoru",
                     f"%{health}",
                     "Iyi" if health >= 80 else "Dikkat" if health >= 50 else "Kritik",
                     health_color)
        
        pdf.set_y(y + 28)
    
    def _add_charts(self, pdf: DailyReportPDF, df: pd.DataFrame, report: Dict, target_date: date):
        """Grafikler bölümü."""
        pdf.section_title("", "GRAFIKLER", (245, 158, 11))
        
        total = report.get("total", 0)
        chiller = report.get("chiller", 0)
        gas_kwh = (report.get("gas_kazan", 0) + report.get("gas_kojen", 0)) * GAS_TO_KWH
        
        y_start = pdf.get_y()
        
        # Pasta grafiği
        try:
            pie_img = create_energy_pie_chart(total, chiller, gas_kwh)
            if pie_img:
                pdf.add_image_from_bytes(pie_img, 10, y_start, 90)
        except Exception:
            pass
        
        # Haftalık trend
        try:
            trend_img = create_weekly_trend_chart(df, target_date)
            if trend_img:
                pdf.add_image_from_bytes(trend_img, 105, y_start, 95)
        except Exception:
            pass
        
        pdf.set_y(y_start + 65)
    
    def _add_equipment_table(self, pdf: DailyReportPDF, hvac: Dict):
        """Ekipman durum özet tablosu."""
        # HVAC analiz sonuçları yoksa basit tablo
        pdf.section_title("", "EKIPMAN DURUM OZETI", (59, 130, 246))
        
        # Tablo başlığı
        pdf.set_font(pdf.font, 'B', 9)
        pdf.set_fill_color(30, 41, 59)
        pdf.set_text_color(255, 255, 255)
        
        col_widths = [55, 25, 25, 30, 25, 30]
        headers = ["Gosterge", "Deger", "Birim", "Durum", "Skor", "Oneri"]
        
        for i, (header, w) in enumerate(zip(headers, col_widths)):
            pdf.cell(w, 8, _sanitize(header), 1, 0, 'C', True)
        pdf.ln()
        
        # Veri satırları
        pdf.set_font(pdf.font, '', 8)
        pdf.set_text_color(50, 50, 50)
        
        rows = [
            ("Kritik Sorun Sayisi", str(hvac.get("critical", "-")), "adet",
             "Kritik" if hvac.get("critical", 0) > 0 else "Iyi",
             "-", "Acil mudahale" if hvac.get("critical", 0) > 0 else "-"),
            ("Uyari Sayisi", str(hvac.get("warning", "-")), "adet",
             "Dikkat" if hvac.get("warning", 0) > 0 else "Iyi",
             "-", "Takip" if hvac.get("warning", 0) > 0 else "-"),
            ("Optimal Cihaz", str(hvac.get("optimal", "-")), "adet",
             "Iyi", "-", "-"),
            ("Ortalama Skor", f"{hvac.get('avg_score', 0):.1f}", "/10",
             "Iyi" if hvac.get('avg_score', 0) < 4 else "Dikkat",
             f"{hvac.get('avg_score', 0):.1f}", "-"),
        ]
        
        for i, (label, val, unit, status, score, reco) in enumerate(rows):
            bg = (248, 250, 252) if i % 2 == 0 else (255, 255, 255)
            pdf.set_fill_color(*bg)
            
            pdf.cell(col_widths[0], 7, _sanitize(label), 1, 0, 'L', True)
            pdf.cell(col_widths[1], 7, _sanitize(val), 1, 0, 'C', True)
            pdf.cell(col_widths[2], 7, _sanitize(unit), 1, 0, 'C', True)
            
            # Durum rengi
            if status == "Kritik":
                pdf.set_text_color(239, 68, 68)
            elif status == "Dikkat":
                pdf.set_text_color(245, 158, 11)
            else:
                pdf.set_text_color(16, 185, 129)
            pdf.cell(col_widths[3], 7, _sanitize(status), 1, 0, 'C', True)
            pdf.set_text_color(50, 50, 50)
            
            pdf.cell(col_widths[4], 7, _sanitize(score), 1, 0, 'C', True)
            pdf.cell(col_widths[5], 7, _sanitize(reco), 1, 0, 'C', True)
            pdf.ln()
        
        pdf.ln(4)
    
    def _add_evaluation(self, pdf: DailyReportPDF, report: Dict, compare: Dict, hvac: Dict, area: float):
        """Otomatik genel değerlendirme metni."""
        pdf.section_title("", "GENEL DEGERLENDIRME", (16, 185, 129))
        
        total = report.get("total", 0)
        comp_total = compare.get("total", 0)
        critical = hvac.get("critical", 0)
        warning = hvac.get("warning", 0)
        penalty = (critical * 15) + (warning * 5)
        health = max(0, 100 - penalty)
        
        # Değerlendirme metni oluştur
        lines = []
        
        # Enerji değerlendirmesi
        if comp_total > 0:
            pct = ((total - comp_total) / comp_total) * 100
            if pct < -5:
                lines.append(f"[+] Enerji tuketimi onceki gune gore %{abs(pct):.1f} azalmistir. Olumlu trend.")
            elif pct > 5:
                lines.append(f"[!] Enerji tuketimi onceki gune gore %{pct:.1f} artmistir. Incelenmesi oneriliyor.")
            else:
                lines.append(f"[-] Enerji tuketimi onceki gunle benzer seviyededir (%{pct:+.1f}).")
        else:
            lines.append("[-] Onceki gun verisi bulunamadigindan karsilastirma yapilamadi.")
        
        # HVAC değerlendirmesi
        if health >= 80:
            lines.append(f"[+] Sistem sagligi iyi durumda (%{health}). Kritik sorun bulunmamaktadir.")
        elif health >= 50:
            lines.append(f"[-] Sistem sagligi dikkat gerektiriyor (%{health}). {critical} kritik, {warning} uyari mevcut.")
        else:
            lines.append(f"[!] DIKKAT: Sistem sagligi kritik seviyede (%{health}). {critical} kritik sorun acil mudahale bekliyor.")
        
        # m² değerlendirmesi
        if area > 0 and total > 0:
            kwh_m2 = total / area
            lines.append(f"[-] Metrekare basina toplam tuketim: {kwh_m2:.3f} kWh/m2 ({area:,.0f} m2 alan uzerinden).")
        
        # Sonuç
        if health >= 80 and (comp_total <= 0 or ((total - comp_total) / comp_total * 100) < 5):
            lines.append("")
            lines.append("SONUC: Sistem genel olarak iyi performans gostermektedir. Rutin takip yeterlidir.")
        elif health < 50:
            lines.append("")
            lines.append("SONUC: Acil mudahale gerektiren sorunlar mevcuttur. Detayli analiz icin HVAC portali incelenmelidir.")
        else:
            lines.append("")
            lines.append("SONUC: Sistem kabul edilebilir seviyededir. Uyarilarin takibi onemlidir.")
        
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
        
        # Alt bilgi kutusu
        pdf.set_fill_color(240, 245, 255)
        pdf.rect(10, pdf.get_y(), 190, 12, 'F')
        pdf.set_font(pdf.font, 'I', 8)
        pdf.set_text_color(100, 100, 100)
        pdf.set_x(15)
        pdf.cell(180, 12, _sanitize(
            f"Bu rapor HVAC Enerji Yonetim Sistemi tarafindan {datetime.now().strftime('%d.%m.%Y %H:%M')} tarihinde otomatik olusturulmustur."
        ), 0, 1)


# ─── Doğrudan çalıştırma ───
if __name__ == "__main__":
    gen = DailyReportGenerator()
    path = gen.generate()
    print(f"Rapor olusturuldu: {path}")
