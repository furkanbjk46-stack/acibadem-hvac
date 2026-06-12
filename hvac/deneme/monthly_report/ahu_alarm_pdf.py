# -*- coding: utf-8 -*-
"""
AHU Alarm Tekrar Raporu (PDF)
================================
ahu_alarm_takip.ay_sonu_raporu() sonucunu, Mahal bazinda gruplanmis
bir PDF rapora donusturur.
"""
import os
from datetime import datetime
from fpdf import FPDF

from monthly_report.ahu_alarm_takip import ay_sonu_raporu, TEKRAR_ESIK

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # hvac/deneme
FONT_DIR = os.path.join(BASE_DIR, "fonts")
OUTPUT_DIR = os.path.join(BASE_DIR, "monthly_report", "ahu_alarm_raporlari")

NAVY = (0, 43, 94)
GRAY = (90, 90, 90)
LIGHT = (235, 240, 248)
RED = (200, 40, 40)

AY_ADLARI = [
    "", "Ocak", "Subat", "Mart", "Nisan", "Mayis", "Haziran",
    "Temmuz", "Agustos", "Eylul", "Ekim", "Kasim", "Aralik"
]


class AlarmPDF(FPDF):
    def __init__(self, yil, ay):
        super().__init__()
        self._yil = yil
        self._ay = ay

    def header(self):
        self.set_fill_color(*NAVY)
        self.rect(0, 0, self.w, 22, 'F')
        self.set_xy(10, 5)
        self.set_font("DejaVu", "B", 14)
        self.set_text_color(255, 255, 255)
        self.cell(0, 6, "AHU Alarm Tekrar Raporu", ln=1)
        self.set_x(10)
        self.set_font("DejaVu", "", 9)
        self.cell(0, 5, f"Acibadem HVAC Optimizasyon - {AY_ADLARI[self._ay]} {self._yil}", ln=1)
        self.ln(6)
        self.set_text_color(0, 0, 0)

    def footer(self):
        self.set_y(-12)
        self.set_font("DejaVu", "", 8)
        self.set_text_color(120, 120, 120)
        self.cell(0, 8, f"Sayfa {self.page_no()}", align="C")

    def section_title(self, text):
        self.ln(2)
        self.set_font("DejaVu", "B", 11)
        self.set_text_color(*NAVY)
        self.set_fill_color(*LIGHT)
        self.cell(0, 8, "  " + text, ln=1, fill=True)
        self.set_text_color(0, 0, 0)
        self.ln(1)


def olustur(yil: int, ay: int) -> str:
    """Verilen yil/ay icin PDF raporu uretir, dosya yolunu dondurur."""
    df = ay_sonu_raporu(yil, ay)

    os.makedirs(OUTPUT_DIR, exist_ok=True)
    dosya_adi = f"ahu_alarm_raporu_{yil:04d}{ay:02d}.pdf"
    out_path = os.path.join(OUTPUT_DIR, dosya_adi)

    pdf = AlarmPDF(yil, ay)
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("DejaVu", "", os.path.join(FONT_DIR, "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf"))
    pdf.add_page(orientation="L")

    pdf.set_font("DejaVu", "", 9.5)
    pdf.set_text_color(*GRAY)
    pdf.multi_cell(
        0, 5,
        f"Bu rapor, {AY_ADLARI[ay]} {yil} ayinda AHU santrallerinde tekrarlayan "
        f"alarm/uyarilarin ozetidir. Bir (Mahal, Ekipman, Kural) kombinasyonu ayni "
        f"ay icinde {TEKRAR_ESIK} veya daha fazla gun tetiklendiyse 'MUHTEMEL ARIZA - "
        f"SAHA KONTROLU ONERILIR' olarak isaretlenir."
    )
    pdf.set_text_color(0, 0, 0)
    pdf.ln(2)

    if df.empty:
        pdf.section_title("Sonuc")
        pdf.set_font("DejaVu", "", 10)
        pdf.cell(0, 8, "Bu ay icin kayitli alarm bulunmuyor.", ln=1)
        pdf.output(out_path)
        return out_path

    # Mahal bazinda grupla
    for mahal, grup in df.groupby("Mahal", sort=True):
        pdf.section_title(f"Mahal: {mahal or 'Tanimsiz'}")

        headers = ["Ekipman", "Kural", "Gun Sayisi", "Ilk Gorulme", "Son Gorulme", "Durum"]
        col_widths = [30, 55, 25, 32, 32, 100]

        pdf.set_font("DejaVu", "B", 8.5)
        pdf.set_fill_color(*NAVY)
        pdf.set_text_color(255, 255, 255)
        for h, w in zip(headers, col_widths):
            pdf.cell(w, 7, h, border=1, align="C", fill=True)
        pdf.ln()
        pdf.set_text_color(0, 0, 0)

        fill = False
        for _, row in grup.iterrows():
            ariza = row["Durum"] == "MUHTEMEL ARIZA - SAHA KONTROLU ONERILIR"
            pdf.set_font("DejaVu", "B" if ariza else "", 8)
            if ariza:
                pdf.set_text_color(*RED)
            pdf.set_fill_color(*LIGHT if fill else (255, 255, 255))

            vals = [
                str(row["Ekipman"]), str(row["Kural"]), str(int(row["Gun_Sayisi"])),
                str(row["Ilk_Gorulme"]), str(row["Son_Gorulme"]), str(row["Durum"]),
            ]
            for val, w in zip(vals, col_widths):
                pdf.cell(w, 7, val, border=1, fill=True)
            pdf.ln()
            pdf.set_text_color(0, 0, 0)
            fill = not fill

        pdf.ln(3)

    pdf.output(out_path)
    return out_path


if __name__ == "__main__":
    now = datetime.now()
    yol = olustur(now.year, now.month)
    print(f"Rapor olusturuldu: {yol}")
