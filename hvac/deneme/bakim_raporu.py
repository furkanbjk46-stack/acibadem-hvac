# -*- coding: utf-8 -*-
# bakim_raporu.py
# Aylık Bakım Raporu PDF üretici — her santral bir kart:
#   - Arızalı / bakımda bileşenler (renkli rozet)
#   - Açıklama (bakım kartındaki notlar)
#   - Ay bakım işareti durumu (yapıldı/yapılmadı + tarih)
# Aylık enerji raporu ile aynı zamanlayıcıda (ayın 5'i 17:00, önceki ayın raporu) üretilir.

import os
import json
import datetime
import logging
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARDS_FILE = os.path.join(BASE_DIR, "configs", "maintenance_cards.json")
TAKVIM_FILE = os.path.join(BASE_DIR, "configs", "bakim_takvimi.json")
OUT_DIR = os.path.join(BASE_DIR, "monthly_reports_summary")

BILESEN_ETIKET = {
    "heating_valve_body":   "Isıtma Vanası Gövde",
    "heating_valve_signal": "Isıtma Vanası 0-10V",
    "cooling_valve_body":   "Soğutma Vanası Gövde",
    "cooling_valve_signal": "Soğutma Vanası 0-10V",
    "supply_sensor":        "Üfleme Sensörü",
    "return_sensor":        "Emiş Sensörü",
    "pressure_sensor":      "Basınç Sensörü",
}

# Renkler (RGB)
KOYU    = (15, 23, 42)
CYAN    = (14, 116, 144)
KIRMIZI = (220, 38, 38)
AMBER   = (217, 119, 6)
YESIL   = (5, 150, 105)
GRI     = (100, 116, 139)
ACIK_GRI = (241, 245, 249)


def _add_dejavu(pdf):
    """DejaVu Unicode font ekle (Türkçe karakter desteği). Bulunamazsa Helvetica."""
    normal = [Path(BASE_DIR) / "fonts" / "DejaVuSans.ttf",
              Path("C:/Windows/Fonts/DejaVuSans.ttf"),
              Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")]
    bold = [Path(BASE_DIR) / "fonts" / "DejaVuSans-Bold.ttf",
            Path("C:/Windows/Fonts/DejaVuSans-Bold.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf")]
    try:
        n = next(p for p in normal if p.exists())
        b = next((p for p in bold if p.exists()), n)
        pdf.add_font("DejaVu", "", str(n))
        pdf.add_font("DejaVu", "B", str(b))
        return "DejaVu"
    except Exception:
        return "Helvetica"


def _oku(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def generate(year: int = None, month: int = None) -> str:
    """Bakım raporu PDF'ini üret ve dosya yolunu döndür.
    year/month verilmezse: önceki ay (aylık enerji raporuyla aynı kapsam)."""
    from fpdf import FPDF

    now = datetime.datetime.now()
    if year is None or month is None:
        onceki = (now.replace(day=1) - datetime.timedelta(days=1))
        year, month = onceki.year, onceki.month
    ay_str = f"{year:04d}-{month:02d}"
    AY_TR = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    ay_adi = f"{AY_TR[month]} {year}"

    cards = (_oku(CARDS_FILE).get("cards") or {})
    takvim_kayit = _oku(TAKVIM_FILE).get(ay_str) or {}

    # Denetim izi özeti: bu ay elle susturma sayısı + aktif susturmalar (kandırma paterni)
    AUDIT_FILE = os.path.join(BASE_DIR, "configs", "bakim_audit_log.jsonl")
    elle_susturma = 0
    try:
        with open(AUDIT_FILE, "r", encoding="utf-8") as f:
            for satir in f:
                try:
                    k = json.loads(satir)
                    if k.get("neden") == "elle susturma" and str(k.get("ts", "")).startswith(ay_str):
                        elle_susturma += 1
                except Exception:
                    pass
    except Exception:
        pass
    aktif_susturma = []
    simdi_iso = now.isoformat(timespec="seconds")
    for ad, c in cards.items():
        for k in BILESEN_ETIKET:
            sup = (c.get(k + "_meta") or {}).get("suppressed_until")
            if sup and sup > simdi_iso:
                aktif_susturma.append(f"{ad} · {BILESEN_ETIKET[k]}")
    bakim_yapildi = bool(takvim_kayit.get("yapildi"))
    bakim_tarih = takvim_kayit.get("tarih", "")

    pdf = FPDF(format="A4")
    pdf.set_auto_page_break(auto=True, margin=14)
    font = _add_dejavu(pdf)
    pdf.add_page()

    # ── Başlık bandı ──
    pdf.set_fill_color(*KOYU)
    pdf.rect(0, 0, 210, 26, "F")
    pdf.set_text_color(255, 255, 255)
    pdf.set_font(font, "B", 15)
    pdf.set_xy(10, 6)
    pdf.cell(0, 8, "AYLIK BAKIM RAPORU — Mekanik Zeka")
    pdf.set_font(font, "", 10)
    pdf.set_xy(10, 15)
    pdf.cell(0, 6, f"Dönem: {ay_adi}   |   Oluşturma: {now.strftime('%d.%m.%Y %H:%M')}")
    pdf.set_y(30)

    # ── Ay bakım işareti durumu ──
    if bakim_yapildi:
        pdf.set_fill_color(220, 252, 231)
        pdf.set_text_color(*YESIL)
        durum_txt = f"✓ {ay_adi} santral bakımları YAPILDI olarak işaretlendi ({bakim_tarih})"
    else:
        pdf.set_fill_color(254, 226, 226)
        pdf.set_text_color(*KIRMIZI)
        durum_txt = f"⚠ {ay_adi} ayında santral bakımları YAPILMAMIŞTIR (aylık bakım işareti girilmedi)."
    pdf.set_font(font, "B", 10)
    pdf.multi_cell(0, 8, durum_txt, fill=True)
    pdf.ln(2)

    # ── Özet ──
    toplam_ariza = sum(1 for c in cards.values()
                       for k in BILESEN_ETIKET if c.get(k) == "FAULTY")
    toplam_bakim = sum(1 for c in cards.values()
                       for k in BILESEN_ETIKET if c.get(k) == "MAINTENANCE")
    sorunlu = [ad for ad, c in cards.items()
               if any(c.get(k) in ("FAULTY", "MAINTENANCE") for k in BILESEN_ETIKET)]
    temiz = [ad for ad in cards if ad not in sorunlu]

    pdf.set_text_color(*KOYU)
    pdf.set_font(font, "B", 11)
    pdf.cell(0, 8, f"Özet: {len(cards)} santral  |  {len(sorunlu)} santralde kayıt  |  "
                   f"{toplam_ariza} ARIZALI bileşen  |  {toplam_bakim} BAKIMDA bileşen",
             new_x="LMARGIN", new_y="NEXT")
    # Denetim izi satırı (elle susturma paterni görünür kalsın — SAĞLAMLAŞTIRMA 4.3)
    pdf.set_font(font, "", 9)
    pdf.set_text_color(*(KIRMIZI if (elle_susturma or aktif_susturma) else GRI))
    _sus_txt = f"Denetim izi: bu ay {elle_susturma} elle susturma"
    if aktif_susturma:
        _sus_txt += "  |  AKTİF SUSTURULMUŞ: " + ", ".join(aktif_susturma[:6])
    pdf.cell(0, 6, _sus_txt, new_x="LMARGIN", new_y="NEXT")
    pdf.ln(2)

    def santral_karti(ad, card):
        """Tek santral kartı çiz."""
        arizali = [BILESEN_ETIKET[k] for k in BILESEN_ETIKET if card.get(k) == "FAULTY"]
        bakimda = [BILESEN_ETIKET[k] for k in BILESEN_ETIKET if card.get(k) == "MAINTENANCE"]
        notlar = (card.get("notes") or card.get("not") or "").strip()

        # Kart yüksekliği tahmini (sayfa taşması kontrolü)
        satir = 8 + (6 if arizali else 0) + (6 if bakimda else 0)
        not_satir = max(1, len(notlar) // 90 + 1) if notlar else 1
        h = satir + not_satir * 5 + 8
        if pdf.get_y() + h > 283:
            pdf.add_page()

        y0 = pdf.get_y()
        # Kart çerçevesi
        kenar = KIRMIZI if arizali else (AMBER if bakimda else (203, 213, 225))
        pdf.set_draw_color(*kenar)
        pdf.set_fill_color(*ACIK_GRI)
        pdf.rect(10, y0, 190, h, "DF")
        # Sol renk şeridi
        pdf.set_fill_color(*kenar)
        pdf.rect(10, y0, 2.2, h, "F")

        # Santral adı + durum rozeti
        pdf.set_xy(15, y0 + 2)
        pdf.set_font(font, "B", 11)
        pdf.set_text_color(*KOYU)
        pdf.cell(90, 6, ad)
        pdf.set_font(font, "B", 8)
        if arizali:
            pdf.set_text_color(*KIRMIZI); rozet = "ARIZALI BİLEŞEN VAR"
        elif bakimda:
            pdf.set_text_color(*AMBER); rozet = "BAKIMDA"
        else:
            pdf.set_text_color(*YESIL); rozet = "SORUN KAYDI YOK"
        pdf.cell(0, 6, rozet, align="R")
        pdf.ln(7)

        pdf.set_font(font, "", 9)
        if arizali:
            pdf.set_x(15)
            pdf.set_text_color(*KIRMIZI)
            pdf.cell(0, 5.5, "Arızalı: " + ", ".join(arizali), new_x="LMARGIN", new_y="NEXT")
        if bakimda:
            pdf.set_x(15)
            pdf.set_text_color(*AMBER)
            pdf.cell(0, 5.5, "Bakımda: " + ", ".join(bakimda), new_x="LMARGIN", new_y="NEXT")

        # Açıklama (notlar)
        pdf.set_x(15)
        pdf.set_text_color(*GRI)
        pdf.set_font(font, "", 9)
        pdf.multi_cell(180, 5, "Açıklama: " + (notlar if notlar else "—"))
        pdf.set_y(y0 + h + 3)

    # ── Sorunlu santraller önce ──
    if sorunlu:
        pdf.set_font(font, "B", 12)
        pdf.set_text_color(*KIRMIZI)
        pdf.cell(0, 8, "ARIZALI / BAKIMDA OLAN SANTRALLER", new_x="LMARGIN", new_y="NEXT")
        for ad in sorted(sorunlu):
            santral_karti(ad, cards[ad])
        pdf.ln(2)

    # ── Diğer santraller (kaydı olan ama sorunsuz) ──
    if temiz:
        pdf.set_font(font, "B", 12)
        pdf.set_text_color(*YESIL)
        pdf.cell(0, 8, "SORUN KAYDI OLMAYAN SANTRALLER", new_x="LMARGIN", new_y="NEXT")
        for ad in sorted(temiz):
            santral_karti(ad, cards[ad])

    if not cards:
        pdf.set_font(font, "", 11)
        pdf.set_text_color(*GRI)
        pdf.multi_cell(0, 7, "Bakım kartı kaydı bulunamadı.")

    # ── Kaydet ──
    os.makedirs(OUT_DIR, exist_ok=True)
    dosya = os.path.join(OUT_DIR, f"bakim_raporu_{year:04d}{month:02d}.pdf")
    pdf.output(dosya)
    logging.info(f"Aylık bakım raporu oluşturuldu: {dosya}")
    return dosya
