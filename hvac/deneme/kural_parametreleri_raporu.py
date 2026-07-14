# -*- coding: utf-8 -*-
"""
HVAC Delta-T Motoru - Kural Parametreleri ve Esik Degerleri Raporu (PDF)
"""
import os
from fpdf import FPDF

FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")

NAVY = (0, 43, 94)
GRAY = (90, 90, 90)
LIGHT = (235, 240, 248)
RED = (200, 40, 40)
ORANGE = (210, 120, 0)
GREEN = (40, 130, 70)


class PDF(FPDF):
    def header(self):
        self.set_fill_color(*NAVY)
        self.rect(0, 0, 210, 22, 'F')
        self.set_xy(10, 5)
        self.set_font("DejaVu", "B", 14)
        self.set_text_color(255, 255, 255)
        self.cell(0, 6, "HVAC Delta-T Motoru - Kural Parametreleri ve Esik Degerleri", ln=1)
        self.set_x(10)
        self.set_font("DejaVu", "", 9)
        self.cell(0, 5, "Acibadem HVAC & Enerji Portali - Sistem Tanim Dokumani Eki", ln=1)
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

    def note(self, text):
        self.set_font("DejaVu", "", 8.5)
        self.set_text_color(*GRAY)
        self.multi_cell(0, 4.5, text)
        self.set_text_color(0, 0, 0)
        self.ln(1)

    def table(self, headers, rows, col_widths, row_height=None):
        self.set_font("DejaVu", "B", 8.5)
        self.set_fill_color(*NAVY)
        self.set_text_color(255, 255, 255)
        for h, w in zip(headers, col_widths):
            self.cell(w, 7, h, border=1, align="C", fill=True)
        self.ln()
        self.set_text_color(0, 0, 0)
        self.set_font("DejaVu", "", 8)
        fill = False
        for row in rows:
            # determine line count needed for last column (description)
            x0 = self.get_x()
            y0 = self.get_y()
            max_lines = 1
            for val, w in zip(row, col_widths):
                txt = str(val)
                # estimate lines
                lines = self.multi_cell(w, 5, txt, border=0, align="L", split_only=True)
                max_lines = max(max_lines, len(lines))
            h = max_lines * 5
            if y0 + h > 277:
                self.add_page()
                self.set_font("DejaVu", "B", 8.5)
                self.set_fill_color(*NAVY)
                self.set_text_color(255, 255, 255)
                for hd, w in zip(headers, col_widths):
                    self.cell(w, 7, hd, border=1, align="C", fill=True)
                self.ln()
                self.set_text_color(0, 0, 0)
                self.set_font("DejaVu", "", 8)
                x0 = self.get_x()
                y0 = self.get_y()

            self.set_fill_color(248, 249, 252) if fill else self.set_fill_color(255, 255, 255)
            for i, (val, w) in enumerate(zip(row, col_widths)):
                x = self.get_x()
                y = self.get_y()
                self.multi_cell(w, 5, str(val), border=1, align="L", fill=True)
                self.set_xy(x + w, y)
            self.ln(h)
            fill = not fill


def build():
    pdf = PDF(orientation="L", unit="mm", format="A4")  # Landscape - genis tablolar icin
    pdf.set_auto_page_break(auto=True, margin=15)
    pdf.add_font("DejaVu", "", os.path.join(FONT_DIR, "DejaVuSans.ttf"))
    pdf.add_font("DejaVu", "B", os.path.join(FONT_DIR, "DejaVuSans-Bold.ttf"))
    pdf.add_page()

    # ================= 1. Genel ΔT Hedefleri =================
    pdf.section_title("1) Genel ΔT Hedefleri ve Toleranslar")
    headers = ["Parametre", "Deger", "Aciklama", "Referans Aldigi Veri"]
    cw = [55, 22, 75, 125]
    rows = [
        ["TARGET_DT_AHU", "5.0°C", "AHU hedef ΔT (sogutma modu)",
         "Inlet/Outlet (coil su giris-cikis); yoksa Plant Supply/Return. AHU+sogutma+OAT varsa ±2°C OAT bias eklenir"],
        ["TARGET_DT_FCU", "5.0°C", "FCU hedef ΔT (sogutma modu)",
         "Inlet/Outlet (coil su) -> fallback Plant Supply/Return"],
        ["TARGET_DT_CHILLER", "5.0°C", "Chiller hedef ΔT",
         "Plant Supply/Return (chillerda Inlet/Outlet genelde yok)"],
        ["TARGET_DT_COLLECTOR", "3.0°C", "Kollektor (ana toplayici) hedef ΔT",
         "Plant Supply (°C) ve Plant Return (°C) - kollektor giris/cikis sicakliklari. delta_t = |Plant Return - Plant Supply|"],
        ["TARGET_DT_HEAT_EXCHANGER", "8.0°C", "Esanjor hedef ΔT",
         "Inlet/Outlet (birincil/ikincil devre su sicakliklari)"],
        ["TARGET_DT_HEAT", "15.0°C", "Isitma devresi (chiller haric, AHU/FCU disi tipler) hedef ΔT",
         "Inlet/Outlet su sicakliklari, isitma modunda ΔT = Inlet - Outlet"],
        ["(AHU/FCU isitma)", "10.0°C", "AHU/FCU coil isitma modunda hedef ΔT (ozel durum)",
         "Inlet/Outlet, Mode = Heating"],
        ["TOLERANCE_CRITICAL", "±2.0°C (kodda su an KULLANILMIYOR)", "ΔT, hedeften bu kadar saparsa kritik tolerans disi sayilir",
         "Hesaplanan delta_t vs target_delta_t farki"],
        ["TOLERANCE_NORMAL", "±3.0°C", "Normal tolerans bandi (BAND_LOW/BAND_HIGH/IN_BAND esigi - FCU)",
         "Hesaplanan delta_t vs target_delta_t farki"],
    ]
    pdf.table(headers, rows, cw)
    pdf.ln(2)
    pdf.note(
        "ΔT hesaplama onceligi (calculate_delta_t): 1) Inlet (°C) / Outlet (°C) varsa kullanilir (su tarafi, coil giris-cikis) "
        "-> isitmada Inlet-Outlet, sogutmada Outlet-Inlet. 2) Inlet/Outlet yoksa Plant Supply (°C) / Plant Return (°C) fallback olarak "
        "kullanilir -> |Plant Return - Plant Supply|.\n"
        "Air ΔT (sadece AHU gostergesi, ayri): Supply (°C) (ufleme havasi) ve Return (°C) (donus havasi) -> |Return - Supply|."
    )

    # ================= 2. SAT Esikleri =================
    pdf.add_page()
    pdf.section_title("2) SAT (Ufleme) Esikleri")
    headers2 = ["Parametre", "Deger", "Referans Aldigi Veri"]
    cw2 = [55, 30, 192]
    rows2 = [
        ["SAT_COOLING_MIN / MAX", "15.0°C / 18.0°C",
         "SAT (°C) sahasi (ufleme sicakligi); sogutma modunda bu bandin disina cikarsa SAT_LOW/SAT_HIGH"],
        ["SAT_HEATING_MIN / MAX", "28.0°C / 31.0°C", "SAT (°C), isitma modunda"],
        ["SAT_COOLING/HEATING_THRESHOLD", "±1.0°C", "SAT (°C) vs Set (°C) karsilastirmasi (set'ten sapma toleransi)"],
        ["HEAT_SAT_LOW_THRESHOLD", "28.0°C",
         "SAT (°C) - LOW_FLOW_DETECTED tetikleyicisi: ΔT (Inlet/Outlet, su) hedefi karsiliyor AMA SAT bu degerin altindaysa "
         "-> su isiniyor ama havaya aktarilamiyor (debi/pompa supheli)"],
    ]
    pdf.table(headers2, rows2, cw2)

    # ================= 3. Vana / Kapasite / Approach =================
    pdf.ln(4)
    pdf.section_title("3) Vana / Kapasite / Approach Esikleri")
    rows3 = [
        ["HIGH_VALVE_THRESHOLD", "%90",
         "Heat Valve (%) ve Cool Valve (%) - vana aciklik sinyali. >=90 ise 'tam acik' kabul edilir "
         "(HEAT_EFF_LOW, COOL_EFF_LOW, LOW_DT_SYNDROME tetikleyicisi)"],
        ["VALVE_SIMUL_THRESHOLD", "%5",
         "Heat Valve (%) VE Cool Valve (%) ayni anda >=5 ise SIMUL_HEAT_COOL (eszamanli isitma+sogutma)"],
        ["APPROACH_MAX", "10.0°C",
         "Cool Valve (%) >=%90 ve approach (Supply hava - Inlet su) > 10°C ise COOL_EFF_LOW"],
        ["COMFORT_DEPARTURE", "3.0°C", "Room (°C) vs Set (°C) -> |Room - Set| > 3.0 ise COMFORT_OVERRIDE"],
        ["LOW_DT_THRESHOLD", "3.0°C",
         "Hesaplanan delta_t (Inlet/Outlet veya Plant) <=3.0°C iken vana >=%90 ise LOW_DT_SYNDROME"],
    ]
    pdf.table(headers2, rows3, cw2)
    pdf.ln(2)
    pdf.note(
        "Approach hesabi (approach_supply / approach_return): Inlet/Outlet (su) ile Supply/Return (hava, AHU ufleme/donus) "
        "farki - su tarafi sicakliginin hava tarafina ne kadar 'ulastigini' gosterir."
    )

    # ================= 4. Chiller =================
    pdf.section_title("4) Chiller Esikleri")
    rows4 = [
        ["CHILLER_BYPASS_DT", "1.0°C",
         "Plant Supply/Return (veya Inlet/Outlet) farki < 1.0°C -> su pratikte hic isi tasimiyor -> bypass/ariza supheli"],
        ["CHILLER_LOW_DT_THRESHOLD", "3.0°C", "Ayni ΔT kaynagi, < 3.0°C -> dusuk verimlilik"],
    ]
    pdf.table(headers2, rows4, cw2)

    # ================= 5. OAT Bias =================
    pdf.ln(4)
    pdf.section_title("5) OAT Bias (Sadece AHU, Sogutma Modu)")
    rows5 = [
        ["OAT_BIAS_MAX", "±2.0°C",
         "OAT (°C) dis hava sicakligi - dusuk dis hava sicakliginda hedef ΔT azaltilir, yuksekte artirilir "
         "(AHU hedef ΔT'sine eklenir)"],
    ]
    pdf.table(headers2, rows5, cw2)

    # ================= 6. Skorlama =================
    pdf.ln(4)
    pdf.section_title("6) Skorlama Parametreleri")
    rows6 = [
        ["SCORE_DEPARTURE_WEIGHT", "2.0", "(delta_t - target_delta_t) farki x 2.0 (kod sabiti, ust sinir +6.0) -> skora eklenir"],
        ["SCORE_LOW_DT_BONUS", "+4.0", "LOW_DT_SYNDROME tetiklendiginde ek puan"],
        ["SCORE_COMFORT_PENALTY", "+2.0", "COMFORT_OVERRIDE tetiklendiginde ek puan (Room vs Set sapmasi)"],
        ["SCORE_CRITICAL_THRESHOLD", "7.0", "Toplam skor >=7.0 -> genel kategori CRITICAL"],
    ]
    pdf.table(headers2, rows6, cw2)

    # ================= 7. Kural Ozeti =================
    pdf.add_page()
    pdf.section_title("7) Kural Ozeti - Skor / Kategori / Tetikleyici Veri Noktalari")
    headers7 = ["Kural", "Skor", "Kategori", "Gecerli Ekipman", "Kullandigi Sahalar / Tetikleyici"]
    cw7 = [50, 15, 25, 35, 152]
    rows7 = [
        ["FAN_BASMIYOR", "9.5", "CRITICAL", "Sadece AHU (basinc noktali)",
         "Start=ACIK + kanal basinci <=20 Pa (2 ardisik) -> fan hava basmiyor"],
        ["TERS_DT", "8.5", "CRITICAL", "Sadece AHU",
         "Sogutmada hava dT < -1.0C (ufleme emisten sicak)"],
        ["LOKAL_CALISMA", "6.0", "WARNING", "Sadece AHU (start noktali)",
         "Start=KAPALI + basinc >20 Pa -> BMS disi lokal calistirma"],
        ["VERI_EKSIK", "5.0", "WARNING", "AHU",
         "SAT hedef disi + EMIS verisi yok -> teshis dogrulanamaz"],
        ["SIMUL_HEAT_COOL", "10.0", "CRITICAL", "AHU + FCU", "Heat Valve (%) ve Cool Valve (%) >= %5"],
        ["CHILLER_BYPASS", "9.0", "CRITICAL", "Sadece CHILLER", "Plant/Inlet-Outlet ΔT < 1.0°C"],
        ["NOT_COOLING", "9.0", "CRITICAL", "AHU + FCU", "SAT (°C), Mode=Cooling, SAT > Set+tol, vana >=%70"],
        ["NOT_HEATING", "9.0", "CRITICAL", "AHU + FCU", "SAT (°C), Mode=Heating, SAT < Set-tol, vana >=%70"],
        ["LOW_FLOW_DETECTED", "8.0", "CRITICAL", "AHU + FCU (Chiller haric)",
         "Inlet/Outlet ΔT >= 15°C VE SAT < 28°C (isitma modu; AHU haric)"],
        ["INSUFFICIENT_CAPACITY", "6.0", "WARNING", "Sadece FCU",
         "Room (°C) vs Set (°C) sapmasi + ilgili Valve (%) (>2°C sapma, vana >%80)"],
        ["HEAT_EFF_LOW", "7.0", "CRITICAL", "Sadece AHU",
         "Heat Valve >=%90 + ufleme (SAT) < SAT_HEATING_MIN (28°C)"],
        ["COOL_EFF_LOW", "7.0", "CRITICAL", "Sadece AHU",
         "Cool Valve >=%90 + Approach (Supply-Inlet) > APPROACH_MAX (10°C)"],
        ["CHILLER_LOW_DT", "6.0", "WARNING", "Sadece CHILLER", "Plant/Inlet-Outlet ΔT < 3.0°C"],
        ["AIR_DT_LOW_COOL", "5.0", "WARNING", "Sadece AHU", "Cool Valve >=%90 ama hava ΔT < 3.0°C"],
        ["LOW_DT_SYNDROME", "5.0", "WARNING", "AHU + FCU", "Ilgili Valve >=%90 ama ΔT <= 3.0°C"],
        ["SAT_WARNING / HIGH / LOW", "5.0", "WARNING", "AHU + FCU (farkli esikler)", "SAT (°C) vs SAT_MIN/MAX bandi"],
        ["HIGH_DT", "5.0", "WARNING", "Sadece AHU", "ΔT > target_delta_t + tolerans"],
        ["LOW_DT", "4.0", "WARNING", "Sadece AHU", "ΔT < target_delta_t - tolerans"],
        ["COMFORT_OVERRIDE", "4.0", "WARNING", "AHU + FCU", "|Room - Set| > 3.0°C"],
        ["BAND_LOW / BAND_HIGH", "3.0", "WARNING", "Sadece FCU", "ΔT vs target ± 3.0°C bandi"],
        ["IN_BAND / NORMAL", "0.0", "OPTIMAL", "AHU + FCU", "ΔT bant icinde"],
    ]
    pdf.table(headers7, rows7, cw7)

    pdf.ln(3)
    pdf.note(
        "Cakisma onceliklendirmesi: Ayni cihazda birden fazla kuralin kosulu ayni anda saglanirsa, skoru daha yuksek olan kural "
        "kazanir (orn. HEAT_EFF_LOW skor 7 > INSUFFICIENT_CAPACITY skor 6 -> HEAT_EFF_LOW gosterilir). "
        "Bu onceliklendirme INSTRUCTION_GUIDE skor tablosuna gore otomatik yapilir; esit skorlarda onceden set edilen kural korunur."
    )

    out_path = os.path.join(os.path.dirname(__file__), "static", "outputs", "kural_parametreleri_raporu.pdf")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    pdf.output(out_path)
    print("OK:", out_path)


if __name__ == "__main__":
    build()
