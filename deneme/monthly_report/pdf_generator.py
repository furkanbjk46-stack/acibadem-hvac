# pdf_generator.py
# Aylık Birleşik Tasarruf Raporu PDF oluşturucu
# Modern stil — Günlük/Aylık raporlarla aynı görsel dil

from __future__ import annotations
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple
import io
import tempfile
import os

from fpdf import FPDF


class MonthlyReportPDFGenerator:
    """
    Aylık Birleşik Tasarruf Raporu PDF oluşturucu.
    HVAC + Enerji verilerini, YoY karşılaştırmasını ve tasarruf önerilerini içerir.
    Günlük/Aylık raporlarla aynı modern stil ve renk paleti.
    """

    # ─── Renk Paleti (günlük/aylık ile aynı) ───
    ACCENT = (59, 130, 246)
    HEADER_BG = (15, 23, 42)
    SUCCESS = (16, 185, 129)
    WARNING_C = (245, 158, 11)
    DANGER = (239, 68, 68)
    WHITE = (255, 255, 255)
    GRAY = (156, 163, 175)

    AYLAR = {
        1: "Ocak", 2: "Subat", 3: "Mart", 4: "Nisan",
        5: "Mayis", 6: "Haziran", 7: "Temmuz", 8: "Agustos",
        9: "Eylul", 10: "Ekim", 11: "Kasim", 12: "Aralik"
    }

    def __init__(self):
        self.pdf = None

    def _sanitize(self, text: str) -> str:
        """Emoji/sembol temizleme — Türkçe karakterler korunur (Unicode font ile)"""
        if text is None:
            return ""

        replacements = {
            "•": "-", "→": "->", "←": "<-", "↑": "^", "↓": "v",
            "📊": "[GRAFIK]", "📥": "[INDIR]", "📈": "[TREND]", "📉": "[TREND]",
            "🔹": "*", "⚠️": "[!]", "✅": "[OK]", "❌": "[X]", "🚨": "[!]",
            "ℹ️": "[i]", "🔴": "[KRITIK]", "🟡": "[UYARI]", "🟢": "[OK]", "⚪": "[-]",
            "❄️": "[SOGUTMA]", "🔧": "[BAKIM]", "🔍": "[ANALIZ]", "💰": "[TASARRUF]",
            "🌡️": "[SICAKLIK]", "🏭": "[SISTEM]", "📏": "[OLCUM]", "💧": "[SU]",
        }

        result = str(text)
        for special_char, ascii_char in replacements.items():
            result = result.replace(special_char, ascii_char)
        return result

    def _setup_unicode_font(self):
        """PDF nesnesine DejaVu Unicode font ekler."""
        from pathlib import Path
        base = Path(__file__).resolve().parent.parent
        font_candidates = [
            base / "fonts" / "DejaVuSans.ttf",
            Path("C:/Windows/Fonts/DejaVuSans.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
        ]
        bold_candidates = [
            base / "fonts" / "DejaVuSans-Bold.ttf",
            Path("C:/Windows/Fonts/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"),
        ]
        italic_candidates = [
            base / "fonts" / "DejaVuSans-Oblique.ttf",
            Path("C:/Windows/Fonts/DejaVuSans-Oblique.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Oblique.ttf"),
        ]
        reg = next((p for p in font_candidates if p.exists()), None)
        bold = next((p for p in bold_candidates if p.exists()), None)
        italic = next((p for p in italic_candidates if p.exists()), None)
        if reg:
            self.pdf.add_font("DejaVu", "", str(reg), uni=True)
            if bold:
                self.pdf.add_font("DejaVu", "B", str(bold), uni=True)
            self.pdf.add_font("DejaVu", "I", str(italic) if italic else str(reg), uni=True)
            return "DejaVu"
        return "Helvetica"

    # ─── Yardımcı: Bölüm Başlığı ───
    def _section_title(self, title: str, color: Tuple[int, int, int] = None):
        if color is None:
            color = self.ACCENT
        self.pdf.ln(4)
        self.pdf.set_fill_color(*color)
        self.pdf.rect(10, self.pdf.get_y(), 3, 8, 'F')
        self.pdf.set_font(self.font, 'B', 13)
        self.pdf.set_text_color(40, 40, 40)
        self.pdf.set_x(16)
        self.pdf.cell(0, 8, self._sanitize(title), 0, 1)
        self.pdf.ln(2)

    # ─── Yardımcı: KPI Kutusu ───
    def _info_box(self, x: float, y: float, w: float, h: float,
                  label: str, value: str, sub: str = "",
                  color: Tuple[int, int, int] = None):
        if color is None:
            color = self.ACCENT
        self.pdf.set_fill_color(245, 247, 250)
        self.pdf.rect(x, y, w, h, 'F')
        self.pdf.set_fill_color(*color)
        self.pdf.rect(x, y + 2, 2, h - 4, 'F')

        self.pdf.set_font(self.font, '', 8)
        self.pdf.set_text_color(120, 120, 120)
        self.pdf.set_xy(x + 6, y + 3)
        self.pdf.cell(w - 10, 4, self._sanitize(label), 0, 0)

        self.pdf.set_font(self.font, 'B', 14)
        self.pdf.set_text_color(30, 30, 30)
        self.pdf.set_xy(x + 6, y + 9)
        self.pdf.cell(w - 10, 8, self._sanitize(value), 0, 0)

        if sub:
            self.pdf.set_font(self.font, '', 7)
            if "+" in sub:
                self.pdf.set_text_color(*self.DANGER)
            elif "-" in sub:
                self.pdf.set_text_color(*self.SUCCESS)
            else:
                self.pdf.set_text_color(*self.GRAY)
            self.pdf.set_xy(x + 6, y + 18)
            self.pdf.cell(w - 10, 4, self._sanitize(sub), 0, 0)

    # ─── Yardımcı: Modern Tablo ───
    def _modern_table(self, headers: list, rows_data: list, col_widths: list,
                      header_color: Tuple[int, int, int] = None):
        if header_color is None:
            header_color = self.HEADER_BG
        rh = 7
        self.pdf.set_fill_color(*header_color)
        self.pdf.set_text_color(*self.WHITE)
        self.pdf.set_font(self.font, 'B', 9)
        for i, hdr in enumerate(headers):
            self.pdf.cell(col_widths[i], rh, self._sanitize(hdr), 0, 0, 'L', fill=True)
        self.pdf.ln()
        self.pdf.set_font(self.font, '', 9)
        for r_idx, row in enumerate(rows_data):
            is_bold = row.get("bold", False) if isinstance(row, dict) else False
            cells = row.get("cells", row) if isinstance(row, dict) else row
            if is_bold:
                self.pdf.set_font(self.font, 'B', 9)
            if r_idx % 2 == 0:
                self.pdf.set_fill_color(250, 250, 252)
            else:
                self.pdf.set_fill_color(255, 255, 255)
            self.pdf.set_text_color(40, 40, 40)
            for i, cell_val in enumerate(cells):
                self.pdf.cell(col_widths[i], rh, self._sanitize(str(cell_val)), 0, 0, 'L', fill=True)
            self.pdf.ln()
            if is_bold:
                self.pdf.set_font(self.font, '', 9)
        self.pdf.set_draw_color(*self.ACCENT)
        total_w = sum(col_widths)
        self.pdf.line(self.pdf.get_x(), self.pdf.get_y(),
                      self.pdf.get_x() + total_w, self.pdf.get_y())
        self.pdf.set_draw_color(0, 0, 0)

    def generate(self, year: int, month: int,
                 unified_data: Dict,
                 yoy_analysis: Dict,
                 recommendations: List[Dict],
                 charts: Dict[str, bytes] = None,
                 forecast_data: Dict = None) -> bytes:
        """
        PDF rapor oluştur.

        Args:
            year: Rapor yılı
            month: Rapor ayı
            unified_data: Birleşik veri
            yoy_analysis: YoY karşılaştırma sonuçları
            recommendations: Tasarruf önerileri

        Returns:
            bytes: PDF içeriği
        """
        self.pdf = FPDF()
        self.pdf.set_auto_page_break(auto=True, margin=18)
        self.font = self._setup_unicode_font()  # DejaVu varsa kullan, yoksa Helvetica
        self.pdf.add_page()

        # Başlık
        self._add_header(year, month)

        # Özet Göstergeler
        self._add_summary_section(unified_data.get("summary", {}))

        # Maliyet Özeti
        self._add_cost_section(unified_data.get("summary", {}))

        # YoY Karşılaştırma
        self._add_yoy_section(yoy_analysis)

        # Tahmin ve Trend (varsa)
        if forecast_data:
            self._add_forecast_section(year, forecast_data)

        # Tasarruf Önerileri
        self._add_recommendations_section(recommendations)

        # HVAC Özet
        self._add_hvac_section(unified_data.get("summary", {}))

        # Grafikler (Varsa)
        if charts:
            self._add_charts_section(charts)

        # Footer
        self._add_footer()

        # fpdf2 ile uyumlu output
        output = self.pdf.output(dest='S')
        if isinstance(output, (bytes, bytearray)):
            return bytes(output)
        else:
            return output.encode('latin-1')

    def _add_header(self, year: int, month: int):
        """Rapor başlığı — koyu arka plan, beyaz text, accent çizgi"""
        self.pdf.set_fill_color(*self.HEADER_BG)
        self.pdf.rect(0, 0, 210, 42, 'F')
        self.pdf.set_fill_color(*self.ACCENT)
        self.pdf.rect(0, 42, 210, 1.5, 'F')

        self.pdf.set_font(self.font, 'B', 18)
        self.pdf.set_text_color(*self.WHITE)
        self.pdf.set_y(8)
        self.pdf.cell(0, 10, self._sanitize("AYLIK BIRLESIK TASARRUF RAPORU"), 0, 1, 'C')

        self.pdf.set_font(self.font, '', 12)
        self.pdf.set_text_color(*self.GRAY)
        ay_adi = self.AYLAR.get(month, str(month))
        self.pdf.cell(0, 7, self._sanitize(f"{ay_adi} {year}"), 0, 1, 'C')

        self.pdf.set_font(self.font, 'I', 9)
        self.pdf.cell(0, 5,
                      self._sanitize(f"Olusturma: {datetime.now().strftime('%d.%m.%Y %H:%M')} | Acibadem Hastanesi"),
                      0, 1, 'C')
        self.pdf.ln(8)

    def _add_summary_section(self, summary: Dict):
        """Özet göstergeler — KPI kutuları"""
        self._section_title("OZET GOSTERGELER", self.ACCENT)

        grid = summary.get("total_grid_consumption", 0)
        cooling = summary.get("total_cooling_consumption", 0)
        hospital = summary.get("total_hospital_consumption", 0)
        gas = summary.get("total_gas", 0)
        chiller_set = summary.get("avg_chiller_set_temp")
        outdoor = summary.get("avg_outdoor_temp")
        vrf = summary.get("total_vrf_consumption", 0)
        water = summary.get("total_water_consumption", 0)
        efficiency_index = summary.get("efficiency_index")

        box_y = self.pdf.get_y()
        bw = 60
        bh = 25
        gap = 3
        xs = 10

        self._info_box(xs, box_y, bw, bh,
                       "Sebeke Tuketimi", f"{grid:,.0f} kWh".replace(",", "."),
                       "", self.ACCENT)
        self._info_box(xs + bw + gap, box_y, bw, bh,
                       "Sogutma Tuketimi", f"{cooling:,.0f} kWh".replace(",", "."),
                       f"Oran: %{(cooling/hospital*100):.1f}" if hospital > 0 else "", (99, 102, 241))
        self._info_box(xs + 2*(bw + gap), box_y, bw, bh,
                       "Hastane Toplam", f"{hospital:,.0f} kWh".replace(",", "."),
                       "", self.SUCCESS)

        self.pdf.set_y(box_y + bh + 4)
        box_y2 = self.pdf.get_y()

        self._info_box(xs, box_y2, bw, bh,
                       "Toplam Dogalgaz", f"{gas:,.0f} m3".replace(",", "."),
                       "", self.DANGER)
        if chiller_set is not None:
            self._info_box(xs + bw + gap, box_y2, bw, bh,
                           "Ort. Chiller Set", f"{chiller_set:.1f} C",
                           "", self.WARNING_C)
        else:
            self._info_box(xs + bw + gap, box_y2, bw, bh,
                           "Ort. Chiller Set", "Veri Yok",
                           "", self.GRAY)
        if outdoor is not None:
            self._info_box(xs + 2*(bw + gap), box_y2, bw, bh,
                           "Ort. Dis Hava", f"{outdoor:.1f} C",
                           "", self.GRAY)
        else:
            self._info_box(xs + 2*(bw + gap), box_y2, bw, bh,
                           "Ort. Dis Hava", "Veri Yok",
                           "", self.GRAY)

        self.pdf.set_y(box_y2 + bh + 4)

        # Ek metrikler varsa 3. satır
        has_extra = vrf > 0 or water > 0 or efficiency_index is not None
        if has_extra:
            box_y3 = self.pdf.get_y()
            col_idx = 0
            if vrf > 0:
                self._info_box(xs + col_idx*(bw + gap), box_y3, bw, bh,
                               "VRF/Split Tuketimi", f"{vrf:,.0f} kWh".replace(",", "."),
                               "", (139, 92, 246))
                col_idx += 1
            if water > 0:
                self._info_box(xs + col_idx*(bw + gap), box_y3, bw, bh,
                               "Su Tuketimi", f"{water:,.0f} m3".replace(",", "."),
                               "", (59, 130, 200))
                col_idx += 1
            if efficiency_index is not None:
                self._info_box(xs + col_idx*(bw + gap), box_y3, bw, bh,
                               "Verimlilik Indeksi", f"{efficiency_index:,.0f} kWh/C".replace(",", "."),
                               "", self.ACCENT)
            self.pdf.set_y(box_y3 + bh + 6)
        else:
            self.pdf.ln(4)

    def _add_cost_section(self, summary: Dict):
        """Maliyet özeti — KPI kutuları ile"""
        try:
            import json
            settings_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "configs", "hvac_settings.json")
            prices = {}
            if os.path.exists(settings_path):
                with open(settings_path, "r", encoding="utf-8") as f:
                    prices = json.load(f)

            p_elec = float(prices.get("UNIT_PRICE_ELECTRICITY", 0))
            p_gas = float(prices.get("UNIT_PRICE_GAS", 0))
            p_water = float(prices.get("UNIT_PRICE_WATER", 0))

            if p_elec <= 0 and p_gas <= 0 and p_water <= 0:
                return

            total_grid = summary.get("total_grid_consumption", 0)
            total_gas = summary.get("total_gas", 0)
            total_water = summary.get("total_water_consumption", 0)

            cost_elec = total_grid * p_elec if p_elec > 0 else 0
            cost_gas = total_gas * p_gas if p_gas > 0 else 0
            cost_water = total_water * p_water if p_water > 0 else 0
            cost_total = cost_elec + cost_gas + cost_water

            self._section_title("MALIYET OZETI (TL)", self.WARNING_C)

            cost_y = self.pdf.get_y()
            cw = 45
            cg = 2.5

            if p_elec > 0:
                self._info_box(10, cost_y, cw, 25,
                               "Elektrik", f"{cost_elec:,.0f} TL".replace(",", "."),
                               f"{p_elec:.2f} TL/kWh", self.ACCENT)
            if p_gas > 0:
                self._info_box(10 + cw + cg, cost_y, cw, 25,
                               "Dogalgaz", f"{cost_gas:,.0f} TL".replace(",", "."),
                               f"{p_gas:.2f} TL/m3", self.DANGER)
            if p_water > 0:
                self._info_box(10 + 2*(cw + cg), cost_y, cw, 25,
                               "Su", f"{cost_water:,.0f} TL".replace(",", "."),
                               f"{p_water:.2f} TL/m3", (59, 130, 200))
            self._info_box(10 + 3*(cw + cg), cost_y, cw, 25,
                           "TOPLAM", f"{cost_total:,.0f} TL".replace(",", "."),
                           "", self.SUCCESS)

            self.pdf.set_y(cost_y + 30)
        except Exception:
            pass

    def _add_yoy_section(self, yoy_analysis: Dict):
        """Geçen yıl karşılaştırma — modern tablo ile"""
        self._section_title("GECEN YIL KARSILASTIRMASI (YoY)", (99, 102, 241))

        comparisons = yoy_analysis.get("comparisons", {})

        key_metrics = [
            "total_hospital_consumption",
            "total_grid_consumption",
            "total_cooling_consumption",
            "total_gas",
            "avg_chiller_set_temp",
        ]

        table_rows = []
        for metric_key in key_metrics:
            data = comparisons.get(metric_key, {})
            label = data.get("label", metric_key)
            current = data.get("current")
            previous = data.get("previous")
            change_pct = data.get("change_percent")
            status = data.get("status", "neutral")
            unit = data.get("unit", "")

            if current is None:
                continue

            cur_str = f"{current:,.1f} {unit}".replace(",", ".")
            prev_str = f"{previous:,.1f} {unit}".replace(",", ".") if previous is not None else "Veri Yok"
            pct_str = f"%{change_pct:+.1f}" if change_pct is not None else "-"

            if status == "positive":
                pct_str += " (OLUMLU)"
            elif status == "negative":
                pct_str += " (OLUMSUZ)"

            table_rows.append([label, cur_str, prev_str, pct_str])

        if table_rows:
            self._modern_table(
                ["Gosterge", "Bu Yil", "Gecen Yil", "Degisim"],
                table_rows,
                [60, 45, 45, 40]
            )
        else:
            self.pdf.set_font(self.font, 'I', 10)
            self.pdf.set_text_color(*self.GRAY)
            self.pdf.cell(0, 8, self._sanitize("Gecen yil verisi bulunmamaktadir."), 0, 1)

        self.pdf.ln(6)

    def _add_recommendations_section(self, recommendations: List[Dict]):
        """Tasarruf önerileri — renkli kartlar ile"""
        self._section_title("TASARRUF ONERILERI", self.SUCCESS)

        if not recommendations:
            self.pdf.set_font(self.font, 'I', 10)
            self.pdf.set_text_color(*self.GRAY)
            self.pdf.cell(0, 8, self._sanitize("Bu donem icin tasarruf onerisi bulunmamaktadir."), 0, 1)
            self.pdf.ln(4)
            return

        for i, rec in enumerate(recommendations, 1):
            severity = rec.get("severity", "INFO")
            name = rec.get("name", "")
            message = rec.get("message", "")
            savings = rec.get("savings_potential", "")

            # Severity'ye göre renk
            if severity == "CRITICAL":
                box_color = self.DANGER
                label = "[KRITIK]"
            elif severity == "WARNING":
                box_color = self.WARNING_C
                label = "[UYARI]"
            else:
                box_color = self.ACCENT
                label = "[BILGI]"

            # Kartın başlangıç Y'si
            card_y = self.pdf.get_y()

            # Sayfa kontrolü — yeni sayfaya geçme ihtimali
            if card_y > 260:
                self.pdf.add_page()
                card_y = self.pdf.get_y()

            # Kart arka planı (hafif gri)
            self.pdf.set_fill_color(248, 249, 252)
            self.pdf.rect(10, card_y, 190, 6, 'F')

            # Sol renk çizgisi
            self.pdf.set_fill_color(*box_color)
            self.pdf.rect(10, card_y, 2, 6, 'F')

            # Başlık satırı
            header_text = f"{i}. {label} {name[:50]}"
            if savings:
                header_text += f" ({savings})"

            self.pdf.set_font(self.font, 'B', 10)
            self.pdf.set_text_color(30, 30, 30)
            self.pdf.set_xy(14, card_y)
            self.pdf.cell(0, 6, self._sanitize(header_text), 0, 1)

            # Mesaj (çok satırlı)
            self.pdf.set_font(self.font, '', 8)
            self.pdf.set_text_color(80, 80, 80)
            for line in message.split("\n"):
                line = line.strip()
                if line:
                    clean_line = self._sanitize(f"     {line}")
                    max_len = 95
                    while len(clean_line) > max_len:
                        break_point = clean_line.rfind(' ', 0, max_len)
                        if break_point == -1:
                            break_point = max_len
                        self.pdf.cell(0, 4, clean_line[:break_point], 0, 1)
                        clean_line = "        " + clean_line[break_point:].strip()
                    if clean_line.strip():
                        self.pdf.cell(0, 4, clean_line, 0, 1)

            self.pdf.ln(3)

        self.pdf.ln(2)

    def _add_hvac_section(self, summary: Dict):
        """HVAC özet — KPI kutuları ile"""
        self._section_title("HVAC SANTRAL OZETI", (139, 92, 246))

        total_ahu = summary.get("total_ahu_analyzed", 0)
        cooling_pct = summary.get("cooling_mode_percentage", 0)
        heating_pct = summary.get("heating_mode_percentage", 0)
        critical = summary.get("total_critical_issues", 0)
        avg_dt = summary.get("avg_delta_t")

        box_y = self.pdf.get_y()
        bw = 60
        bh = 25
        gap = 3
        xs = 10

        self._info_box(xs, box_y, bw, bh,
                       "Analiz Edilen Santral", f"{total_ahu} adet",
                       "", self.ACCENT)
        self._info_box(xs + bw + gap, box_y, bw, bh,
                       "Sogutma Modunda", f"%{cooling_pct:.1f}",
                       "", (99, 102, 241))
        self._info_box(xs + 2*(bw + gap), box_y, bw, bh,
                       "Isitma Modunda", f"%{heating_pct:.1f}",
                       "", self.DANGER)

        self.pdf.set_y(box_y + bh + 4)
        box_y2 = self.pdf.get_y()

        # Kritik sorun
        crit_color = self.DANGER if critical > 0 else self.SUCCESS
        self._info_box(xs, box_y2, bw, bh,
                       "Kritik Sorun", f"{critical} adet",
                       "", crit_color)

        if avg_dt is not None:
            self._info_box(xs + bw + gap, box_y2, bw, bh,
                           "Ort. Su DeltaT", f"{avg_dt:.1f} C",
                           "", self.GRAY)

        self.pdf.set_y(box_y2 + bh + 6)
    def _add_forecast_section(self, year: int, forecast_data: Dict):
        """Tahmin ve trend bölümü"""
        try:
            yearly = forecast_data.get("yearly_summary", [])
            monthly_fc = forecast_data.get("monthly_forecast", [])
            savings = forecast_data.get("savings", {})
            b_area = forecast_data.get("building_area", 0)

            if not yearly and not monthly_fc:
                return

            self.pdf.add_page()
            self._section_title("TUKETIM TAHMINI VE TREND", (139, 92, 246))

            # 1. Çok yıllık özet tablosu
            if yearly and len(yearly) >= 2:
                self.pdf.set_font(self.font, 'B', 10)
                self.pdf.set_text_color(40, 40, 40)
                self.pdf.cell(0, 6, self._sanitize("Cok Yillik Ozet"), 0, 1)
                self.pdf.ln(2)

                headers = ["Yil", "Gun", "Toplam (kWh)", "Sebeke (kWh)", "Chiller (kWh)"]
                if b_area > 0:
                    headers.append("kWh/m2")
                widths = [20, 15, 45, 45, 40]
                if b_area > 0:
                    widths.append(25)

                rows = []
                for ys in yearly:
                    row = [
                        str(ys["year"]),
                        str(ys["days"]),
                        f"{ys['total_kwh']:,.0f}".replace(",", "."),
                        f"{ys['grid_kwh']:,.0f}".replace(",", "."),
                        f"{ys['chiller_kwh']:,.0f}".replace(",", "."),
                    ]
                    if b_area > 0:
                        row.append(f"{ys['kwh_per_m2']:.1f}")
                    rows.append(row)

                self._modern_table(headers, rows, widths)
                self.pdf.ln(4)

            # 2. Aylık tahmin tablosu
            if monthly_fc:
                self.pdf.set_font(self.font, 'B', 10)
                self.pdf.set_text_color(40, 40, 40)
                self.pdf.cell(0, 6, self._sanitize(f"{year} Aylik Tuketim Tahmini"), 0, 1)
                self.pdf.ln(2)

                prev_y = monthly_fc[0]["prev_year"] if monthly_fc else ""
                last_y = monthly_fc[0]["last_year"] if monthly_fc else ""

                fc_headers = ["Ay", str(prev_y), str(last_y), "Trend", "Tahmin", "Gercek", "Sapma"]
                fc_widths = [22, 28, 28, 18, 28, 28, 18]

                fc_rows = []
                for fc in monthly_fc:
                    actual_str = "-"
                    sapma_str = "-"
                    if fc.get("actual_total") is not None:
                        actual_str = f"{fc['actual_total']:,.0f}".replace(",", ".")
                        if fc.get("is_partial"):
                            actual_str += f" ({fc['actual_days']}g)"
                        if fc.get("deviation_total_pct") is not None:
                            sapma_str = f"{fc['deviation_total_pct']:+.1f}%"

                    fc_rows.append([
                        fc["month_name"],
                        f"{fc['prev_total']:,.0f}".replace(",", "."),
                        f"{fc['last_total']:,.0f}".replace(",", "."),
                        f"{fc['trend_total_pct']:+.1f}%",
                        f"{fc['forecast_total']:,.0f}".replace(",", "."),
                        actual_str,
                        sapma_str,
                    ])

                self._modern_table(fc_headers, fc_rows, fc_widths)
                self.pdf.ln(4)

            # 3. Tasarruf KPI kutuları
            if savings and savings.get("savings_total_kwh") is not None:
                self.pdf.ln(2)
                self.pdf.set_font(self.font, 'B', 10)
                self.pdf.set_text_color(40, 40, 40)
                self.pdf.cell(0, 6, self._sanitize("Beklenen vs Gerceklesen Tasarruf"), 0, 1)
                self.pdf.ln(2)

                sy = self.pdf.get_y()
                bw = 45
                gap = 3

                sav_total = savings.get("savings_total_kwh", 0)
                sav_grid = savings.get("savings_grid_kwh", 0)
                sav_color = self.SUCCESS if sav_total >= 0 else self.DANGER
                sav_g_color = self.SUCCESS if sav_grid >= 0 else self.DANGER

                self._info_box(10, sy, bw, 25,
                               "Beklenen Tuketim",
                               f"{savings.get('expected_total', 0):,.0f}".replace(",", "."),
                               "kWh (alan bazli)", (139, 92, 246))
                self._info_box(10 + bw + gap, sy, bw, 25,
                               "Gerceklesen",
                               f"{savings.get('curr_total', 0):,.0f}".replace(",", "."),
                               "kWh", self.ACCENT)
                self._info_box(10 + 2*(bw + gap), sy, bw, 25,
                               "Toplam Tasarruf",
                               f"{sav_total:,.0f} kWh".replace(",", "."),
                               f"%{savings.get('savings_total_pct', 0):.1f}", sav_color)
                self._info_box(10 + 3*(bw + gap), sy, bw, 25,
                               "Sebeke Tasarruf",
                               f"{sav_grid:,.0f} kWh".replace(",", "."),
                               f"%{savings.get('savings_grid_pct', 0):.1f}", sav_g_color)

                self.pdf.set_y(sy + 30)

        except Exception:
            pass  # Tahmin hatası PDF akışını durdurmasın

    def _add_charts_section(self, charts: Dict[str, bytes]):
        """Grafikler bölümü"""
        self.pdf.add_page()
        self._section_title("DETAYLI GRAFIKLER", (99, 102, 241))

        for title, img_bytes in charts.items():
            if img_bytes:
                # Grafik başlığı (sol renkli çubuk)
                self.pdf.set_font(self.font, 'B', 11)
                self.pdf.set_text_color(40, 40, 40)
                self.pdf.set_fill_color(*self.ACCENT)
                self.pdf.rect(10, self.pdf.get_y(), 3, 6, 'F')
                self.pdf.set_x(16)
                self.pdf.cell(0, 6, self._sanitize(title), 0, 1)
                self.pdf.ln(1)

                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".png") as tmp:
                        tmp.write(img_bytes)
                        tmp_path = tmp.name

                    self.pdf.image(tmp_path, x=10, w=190)
                    self.pdf.ln(5)

                    os.unlink(tmp_path)
                except Exception as e:
                    self.pdf.set_font(self.font, '', 9)
                    self.pdf.set_text_color(*self.DANGER)
                    self.pdf.cell(0, 10, self._sanitize(f"[Grafik eklenemedi: {title}]"), 0, 1)
                    self.pdf.set_text_color(40, 40, 40)

                self.pdf.ln(4)

    def _add_footer(self):
        """Sayfa altı — koyu bar"""
        self.pdf.ln(6)
        footer_y = self.pdf.get_y()
        if footer_y > 270:
            self.pdf.add_page()
            footer_y = self.pdf.get_y()

        self.pdf.set_fill_color(*self.HEADER_BG)
        self.pdf.rect(0, footer_y, 210, 12, 'F')
        self.pdf.set_font(self.font, 'I', 8)
        self.pdf.set_text_color(*self.GRAY)
        self.pdf.set_y(footer_y + 2)
        self.pdf.cell(0, 8,
                      self._sanitize(f"Bu rapor HVAC Enerji Yonetim Sistemi tarafindan "
                                     f"{datetime.now().strftime('%d.%m.%Y %H:%M')} tarihinde otomatik olusturulmustur."),
                      0, 0, 'C')
