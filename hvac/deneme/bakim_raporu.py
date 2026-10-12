# -*- coding: utf-8 -*-
# bakim_raporu.py
# Aylık Bakım Raporu PDF üretici — otomatik (ayın 5'i 17:00, önceki ay).
#
# BİÇİM: Dijital Bakım Kartı ekranından elle üretilen PDF ile AYNI kalıp
# (static/index.html → "DİJİTAL BAKIM VE BİLEŞEN DURUM RAPORU"):
#   1) Kurumsal başlık bandı
#   2) Beş özet kutusu
#   3) Santral × 7 bileşen MATRİSİ (her hücre bileşenin durumu) + özet + öncelik rozeti
#   4) Lejant
#   5) ARIZA VE BAKIM DETAYI tablosu (bileşen adları, not, son güncelleme)
#   6) Sayfa altı: kaynak + sayfa no
# Aylık rapora özgü iki satır (ay bakım işareti ve denetim izi) başlığın altında
# bant olarak durur — elle üretilen raporda bu bilgi yoktur, kaybolmasın.
#
# İki yerde ayrı ayrı bakım PDF'i çizilir (burada fpdf2, ekranda jsPDF). Biçim
# değişikliği YALNIZCA ikisinde birden yapılır; test_bakim_raporu.py iki kalıbın
# da aynı başlıkları/sütunları ürettiğini doğrular.

import os
import json
import datetime
import logging
from pathlib import Path

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARDS_FILE = os.path.join(BASE_DIR, "configs", "maintenance_cards.json")
TAKVIM_FILE = os.path.join(BASE_DIR, "configs", "bakim_takvimi.json")
AUDIT_FILE = os.path.join(BASE_DIR, "configs", "bakim_audit_log.jsonl")
OUT_DIR = os.path.join(BASE_DIR, "monthly_reports_summary")

# Bileşen sırası ekrandaki ile AYNI (index.html → components)
BILESENLER = ["heating_valve_body", "heating_valve_signal",
              "cooling_valve_body", "cooling_valve_signal",
              "supply_sensor", "return_sensor", "pressure_sensor"]

BILESEN_ETIKET = {
    "heating_valve_body":   "Isıtma Vanası Gövde",
    "heating_valve_signal": "Isıtma Vanası 0-10V",
    "cooling_valve_body":   "Soğutma Vanası Gövde",
    "cooling_valve_signal": "Soğutma Vanası 0-10V",
    "supply_sensor":        "Üfleme Sensörü",
    "return_sensor":        "Emiş Sensörü",
    "pressure_sensor":      "Basınç Sensörü",
}

# Tablo başlığında iki satır (ekrandaki compHead ile aynı)
BILESEN_BASLIK = {
    "heating_valve_body":   "Isıtma Vana\nGövde",
    "heating_valve_signal": "Isıtma Vana\n0-10V",
    "cooling_valve_body":   "Soğutma Vana\nGövde",
    "cooling_valve_signal": "Soğutma Vana\n0-10V",
    "supply_sensor":        "Üfleme\nSensörü",
    "return_sensor":        "Emiş\nSensörü",
    "pressure_sensor":      "Basınç\nSensörü",
}

# Renkler (RGB) — ekrandaki PDF ile birebir
NAVY     = (0, 43, 94)
KIRMIZI  = (211, 47, 47)
TURUNCU  = (217, 119, 6)
YESIL    = (46, 125, 50)
GRI      = (150, 150, 150)
METIN    = (51, 51, 51)
SOLUK    = (102, 102, 102)
CIZGI    = (220, 220, 220)
KUTU_ZEMIN = (248, 250, 252)
OK_ZEMIN = (232, 245, 233)

KENAR = 30.0          # margin (pt)
SAYFA_W = 842.0       # A4 yatay
SAYFA_H = 595.0


def _oku(path):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


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


def _tarih_tr(iso):
    if not iso:
        return "—"
    try:
        s = str(iso).replace("Z", "+00:00")
        d = datetime.datetime.fromisoformat(s)
        return d.strftime("%d.%m.%Y %H:%M")
    except Exception:
        return "—"


def santral_ozetleri(cards):
    """Kartları ekrandaki PDF ile AYNI özet yapısına çevirir.

    Dönen her kayıt: santral adı, bileşen durumları, arızalı/bakımdaki bileşen
    adları, özet metni ve öncelik rozeti. Sıra: önce arızalılar, sonra
    bakımdakiler, sonra ada göre (ekrandaki summary.sort ile aynı)."""
    toplam = len(BILESENLER)
    ozetler = []
    for ad, kart in (cards or {}).items():
        durumlar, arizali, bakimda = {}, [], []
        for comp in BILESENLER:
            val = kart.get(comp) or "OK"
            durumlar[comp] = val
            if val == "FAULTY":
                arizali.append(BILESEN_ETIKET[comp])
            elif val == "MAINTENANCE":
                bakimda.append(BILESEN_ETIKET[comp])
        f, m = len(arizali), len(bakimda)
        saglam = sum(1 for c in BILESENLER if durumlar[c] == "OK")
        if f:
            rozet, rozet_renk = "KRİTİK / ACİL", KIRMIZI
        elif m:
            rozet, rozet_renk = "ORTA", TURUNCU
        else:
            rozet, rozet_renk = "DÜŞÜK", (158, 158, 158)
        if m == toplam:
            ozet = "Santral bakımda\n(%d / %d bileşen)" % (toplam, toplam)
        elif f + m == 0:
            ozet = "Sağlam %d / %d" % (saglam, toplam)
        else:
            ozet = "\n".join([s for s in ("%d arızalı" % f if f else "",
                                          "%d bakımda" % m if m else "") if s])
        ozetler.append({
            "ad": ad, "durumlar": durumlar, "arizali": arizali, "bakimda": bakimda,
            "f": f, "m": m, "saglam": saglam, "ozet": ozet,
            "rozet": rozet, "rozet_renk": rozet_renk,
            "notlar": (kart.get("notes") or kart.get("not") or "").strip(),
            "guncel": kart.get("_updated_at"),
        })
    ozetler.sort(key=lambda s: (0 if s["f"] else 1, 0 if s["m"] else 1, s["ad"]))
    return ozetler


class _Cizim:
    """fpdf2 üzerinde jsPDF/autoTable kalıbını çizen küçük yardımcı."""

    def __init__(self, pdf, font):
        self.pdf = pdf
        self.font = font
        self.dejavu = (font == "DejaVu")

    def g(self, metin):
        """Helvetica'ya düşüldüyse Unicode işaretleri ASCII'ye indir."""
        if self.dejavu:
            return metin
        for a, b in (("✓", "OK"), ("—", "-"), ("⚠", "!"), ("İ", "I"),
                     ("ı", "i"), ("Ş", "S"), ("ş", "s"), ("Ğ", "G"), ("ğ", "g"),
                     ("Ö", "O"), ("ö", "o"), ("Ü", "U"), ("ü", "u"), ("Ç", "C"),
                     ("ç", "c")):
            metin = metin.replace(a, b)
        return metin

    def yazi(self, x, y, metin, boy=8, kalin=False, renk=METIN, hiza="L", gen=None):
        p = self.pdf
        p.set_font(self.font, "B" if kalin else "", boy)
        p.set_text_color(*renk)
        metin = self.g(metin)
        if hiza == "C" and gen:
            x = x + (gen - p.get_string_width(metin)) / 2.0
        elif hiza == "R" and gen:
            x = x + gen - p.get_string_width(metin)
        p.text(x, y, metin)

    def sar(self, metin, gen, boy=8, kalin=False):
        """Metni sütun genişliğine göre satırlara böl ('\\n' korunur)."""
        p = self.pdf
        p.set_font(self.font, "B" if kalin else "", boy)
        satirlar = []
        for parca in str(metin).split("\n"):
            parca = self.g(parca)
            if not parca:
                satirlar.append("")
                continue
            kelime, aktif = parca.split(" "), ""
            for k in kelime:
                deneme = (aktif + " " + k).strip()
                if p.get_string_width(deneme) <= gen or not aktif:
                    aktif = deneme
                else:
                    satirlar.append(aktif)
                    aktif = k
            satirlar.append(aktif)
        return satirlar or [""]

    def kutu(self, x, y, w, h, zemin=None, kenar=None, kalinlik=0.6, yuvarlak=0):
        p = self.pdf
        stil = ""
        if zemin:
            p.set_fill_color(*zemin)
            stil += "F"
        if kenar:
            p.set_draw_color(*kenar)
            p.set_line_width(kalinlik)
            stil += "D"
        if not stil:
            return
        if yuvarlak:
            p.rect(x, y, w, h, stil, round_corners=True, corner_radius=yuvarlak)
        else:
            p.rect(x, y, w, h, stil)


def _baslik_bandi(ciz, alt_satir):
    """Kurumsal başlık: navy ikon + başlık + bilgi satırı + ayraç çizgisi."""
    p, m = ciz.pdf, KENAR
    p.set_fill_color(*NAVY)
    p.rect(m, 24, 44, 44, "F", round_corners=True, corner_radius=6)
    p.set_draw_color(255, 255, 255)
    p.set_line_width(1.6)
    p.line(m + 9, 36, m + 29, 36)
    p.line(m + 9, 46, m + 33, 46)
    p.line(m + 9, 56, m + 25, 56)

    ciz.yazi(m + 56, 42, "DİJİTAL BAKIM VE BİLEŞEN DURUM RAPORU", 15, True, NAVY)
    ciz.yazi(m + 56, 58, alt_satir, 9, False, SOLUK)
    p.set_draw_color(*NAVY)
    p.set_line_width(2)
    p.line(m, 78, SAYFA_W - m, 78)


def _ozet_kutulari(ciz, kutular, y=88):
    gen = (SAYFA_W - 2 * KENAR - 4 * 10) / 5.0
    for i, (etiket, deger, renk) in enumerate(kutular):
        x = KENAR + i * (gen + 10)
        ciz.kutu(x, y, gen, 40, KUTU_ZEMIN, renk, 1, 4)
        ciz.pdf.set_fill_color(*renk)
        ciz.pdf.rect(x, y, 4, 40, "F")
        ciz.yazi(x + 14, y + 24, deger, 16, True, renk)
        ciz.yazi(x + 14, y + 35, etiket, 7.5, False, SOLUK)


def _durum_bandi(ciz, y, metin, renk, zemin):
    """Aylık rapora özgü bant: ay bakım işareti / denetim izi."""
    ciz.kutu(KENAR, y, SAYFA_W - 2 * KENAR, 22, zemin, renk, 1, 4)
    ciz.yazi(KENAR + 12, y + 15, metin, 9, True, renk)
    return y + 28


def generate(year: int = None, month: int = None) -> str:
    """Bakım raporu PDF'ini üret ve dosya yolunu döndür.
    year/month verilmezse: önceki ay (aylık enerji raporuyla aynı kapsam)."""
    from fpdf import FPDF

    now = datetime.datetime.now()
    if year is None or month is None:
        onceki = (now.replace(day=1) - datetime.timedelta(days=1))
        year, month = onceki.year, onceki.month
    ay_str = "%04d-%02d" % (year, month)
    AY_TR = ["", "Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran",
             "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"]
    ay_adi = "%s %d" % (AY_TR[month], year)

    cards = (_oku(CARDS_FILE).get("cards") or {})
    takvim_kayit = _oku(TAKVIM_FILE).get(ay_str) or {}
    ozetler = santral_ozetleri(cards)

    # Denetim izi: bu ay elle susturma sayısı + hâlâ aktif susturmalar
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
    simdi_iso = now.isoformat(timespec="seconds")
    aktif_susturma = [f"{ad} · {BILESEN_ETIKET[k]}"
                      for ad, c in cards.items() for k in BILESENLER
                      if ((c.get(k + "_meta") or {}).get("suppressed_until") or "") > simdi_iso]

    pdf = FPDF(orientation="L", unit="pt", format="A4")
    pdf.set_auto_page_break(False)
    font = _add_dejavu(pdf)
    ciz = _Cizim(pdf, font)
    pdf.add_page()

    _baslik_bandi(ciz, "Tarih / Saat: %s   |   Dönem: %s   |   Kapsam: Tüm Santraller"
                       "   |   Santral: %d" % (now.strftime("%d.%m.%Y %H:%M"), ay_adi, len(ozetler)))

    arizali_santral = sum(1 for s in ozetler if s["f"])
    bakimda_santral = sum(1 for s in ozetler if not s["f"] and s["m"])
    arizali_bilesen = sum(s["f"] for s in ozetler)
    bakimda_bilesen = sum(s["m"] for s in ozetler)
    _ozet_kutulari(ciz, [
        ("SANTRAL", str(len(ozetler)), NAVY),
        ("ARIZALI SANTRAL", str(arizali_santral), KIRMIZI),
        ("BAKIMDAKİ SANTRAL", str(bakimda_santral), TURUNCU),
        ("ARIZALI BİLEŞEN", str(arizali_bilesen), KIRMIZI),
        ("BAKIMDAKİ BİLEŞEN", str(bakimda_bilesen), TURUNCU),
    ])

    # ── Aylık rapora özgü bantlar ──
    y = 140
    if takvim_kayit.get("yapildi"):
        y = _durum_bandi(ciz, y, "✓ %s santral bakımları YAPILDI olarak işaretlendi (%s)"
                         % (ay_adi, takvim_kayit.get("tarih", "")), YESIL, (220, 252, 231))
    else:
        y = _durum_bandi(ciz, y, "⚠ %s ayında santral bakımları YAPILMAMIŞTIR "
                         "(aylık bakım işareti girilmedi)." % ay_adi, KIRMIZI, (254, 226, 226))
    _sus = "Denetim izi: bu ay %d elle susturma" % elle_susturma
    if aktif_susturma:
        _sus += "   |   AKTİF SUSTURULMUŞ: " + ", ".join(aktif_susturma[:6])
    y = _durum_bandi(ciz, y, _sus,
                     KIRMIZI if (elle_susturma or aktif_susturma) else SOLUK,
                     (254, 226, 226) if (elle_susturma or aktif_susturma) else KUTU_ZEMIN)

    if not ozetler:
        ciz.yazi(KENAR, y + 14, "Bakım kartı kaydı bulunamadı.", 11, False, SOLUK)
        return _kaydet(pdf, ciz, year, month)

    # ── 2) Santral × bileşen matrisi ──
    HUCRE = {
        "FAULTY":      ("ARIZALI", KIRMIZI, (255, 255, 255)),
        "MAINTENANCE": ("BAKIMDA", TURUNCU, (255, 255, 255)),
        "OK":          ("✓", OK_ZEMIN, YESIL),
        "N/A":         ("—", (240, 240, 240), GRI),
    }
    _comp_gen = (SAYFA_W - 2 * KENAR - 92 - 82 - 92) / len(BILESENLER)
    genislikler = [92] + [_comp_gen] * len(BILESENLER) + [82, 92]
    basliklar = ["Santral"] + [BILESEN_BASLIK[c] for c in BILESENLER] + ["Özet", "Öncelik"]

    def _baslik_satiri(y0):
        h = 28
        x = KENAR
        for i, b in enumerate(basliklar):
            ciz.kutu(x, y0, genislikler[i], h, NAVY, CIZGI, 0.6)
            satir = b.split("\n")
            ty = y0 + (h - len(satir) * 9) / 2 + 7.5
            for s in satir:
                ciz.yazi(x, ty, s, 7.5, True, (255, 255, 255), "C", genislikler[i])
                ty += 9
            x += genislikler[i]
        return y0 + h

    y = _baslik_satiri(y + 2)

    for s in ozetler:
        ozet_satir = s["ozet"].split("\n")
        h = max(24.0, len(ozet_satir) * 10 + 12)
        if y + h > SAYFA_H - 40:
            pdf.add_page()
            y = _baslik_satiri(50)
        x = KENAR
        # Santral adı
        ciz.kutu(x, y, genislikler[0], h, (255, 255, 255), CIZGI, 0.6)
        ciz.yazi(x + 6, y + h / 2 + 3, s["ad"], 8, True, METIN)
        x += genislikler[0]
        # Bileşen hücreleri
        for i, comp in enumerate(BILESENLER):
            yazi, zemin, renk = HUCRE.get(s["durumlar"][comp], HUCRE["OK"])
            ciz.kutu(x, y, genislikler[1 + i], h, zemin, CIZGI, 0.6)
            ciz.yazi(x, y + h / 2 + 3, yazi, 8 if yazi in ("ARIZALI", "BAKIMDA") else 10,
                     True, renk, "C", genislikler[1 + i])
            x += genislikler[1 + i]
        # Özet
        gi = len(BILESENLER) + 1
        ciz.kutu(x, y, genislikler[gi], h, (255, 255, 255), CIZGI, 0.6)
        renk = KIRMIZI if s["f"] else (TURUNCU if s["m"] else YESIL)
        ty = y + (h - len(ozet_satir) * 10) / 2 + 7.5
        for satir in ozet_satir:
            ciz.yazi(x, ty, satir, 7.5, True, renk, "C", genislikler[gi])
            ty += 10
        x += genislikler[gi]
        # Öncelik rozeti
        ciz.kutu(x, y, genislikler[gi + 1], h, (255, 255, 255), CIZGI, 0.6)
        pdf.set_font(font, "B", 7.5)
        _txt = ciz.g(s["rozet"])
        bw = pdf.get_string_width(_txt) + 14
        bh = 15
        bx = x + (genislikler[gi + 1] - bw) / 2
        by = y + (h - bh) / 2
        pdf.set_fill_color(*s["rozet_renk"])
        pdf.rect(bx, by, bw, bh, "F", round_corners=True, corner_radius=7)
        ciz.yazi(bx, by + bh / 2 + 2.6, s["rozet"], 7.5, True, (255, 255, 255), "C", bw)
        y += h

    # ── Lejant ──
    y += 14
    if y > SAYFA_H - 60:
        pdf.add_page()
        y = 50
    lx = KENAR
    for renk, yazi in ((KIRMIZI, "ARIZALI — müdahale gerekli"),
                       (TURUNCU, "BAKIMDA — bakım sürüyor"),
                       (YESIL, "✓ Sağlam"),
                       (GRI, "— Bu santralde yok (N/A)")):
        pdf.set_fill_color(*renk)
        pdf.rect(lx, y - 6, 8, 8, "F")
        ciz.yazi(lx + 12, y + 1, yazi, 7.5, False, (90, 90, 90))
        pdf.set_font(font, "", 7.5)
        lx += pdf.get_string_width(ciz.g(yazi)) + 34

    # ── 3) Arıza ve bakım detayı ──
    detay = [s for s in ozetler if s["f"] or s["m"] or s["notlar"]]
    if detay:
        y += 26
        if y > SAYFA_H - 90:
            pdf.add_page()
            y = 50
        ciz.yazi(KENAR, y, "ARIZA VE BAKIM DETAYI", 11, True, NAVY)
        y += 8
        d_gen = [92, 170, 170, SAYFA_W - 2 * KENAR - 92 - 170 - 170 - 92, 92]
        d_bas = ["Santral", "Arızalı Bileşenler", "Bakımdaki Bileşenler", "Not", "Son Güncelleme"]

        def _detay_baslik(y0):
            x = KENAR
            for i, b in enumerate(d_bas):
                ciz.kutu(x, y0, d_gen[i], 20, NAVY, CIZGI, 0.6)
                ciz.yazi(x + 5, y0 + 13.5, b, 8, True, (255, 255, 255))
                x += d_gen[i]
            return y0 + 20

        y = _detay_baslik(y)
        for i, d in enumerate(detay):
            hucreler = [
                (d["ad"], METIN, True),
                ("\n".join(d["arizali"]) if d["arizali"] else "—", KIRMIZI, True),
                (("Tüm bileşenler\n(santral bakımda)" if d["m"] == len(BILESENLER)
                  else ("\n".join(d["bakimda"]) if d["bakimda"] else "—")), TURUNCU, True),
                (d["notlar"] or "—", METIN, False),
                (_tarih_tr(d["guncel"]), METIN, False),
            ]
            sarilmis = [ciz.sar(t, d_gen[j] - 10, 8, kal) for j, (t, _, kal) in enumerate(hucreler)]
            h = max(20.0, max(len(s) for s in sarilmis) * 10 + 10)
            if y + h > SAYFA_H - 40:
                pdf.add_page()
                y = _detay_baslik(50)
            zemin = (249, 249, 249) if i % 2 else (255, 255, 255)
            x = KENAR
            for j, (metin, renk, kalin) in enumerate(hucreler):
                ciz.kutu(x, y, d_gen[j], h, zemin, CIZGI, 0.6)
                _bos = (metin == "—")
                ty = y + 13.5
                for satir in sarilmis[j]:
                    if j == 4:
                        ciz.yazi(x, ty, satir, 8, False, METIN, "C", d_gen[j])
                    else:
                        ciz.yazi(x + 5, ty, satir, 8,
                                 kalin and not _bos, (170, 170, 170) if _bos else renk)
                    ty += 10
                x += d_gen[j]
            y += h

    return _kaydet(pdf, ciz, year, month)


def _kaydet(pdf, ciz, year, month) -> str:
    """Sayfa altı bilgisi + dosyaya yazım."""
    toplam = pdf.pages_count if hasattr(pdf, "pages_count") else len(pdf.pages)
    for i in range(1, toplam + 1):
        pdf.page = i
        ciz.yazi(KENAR, SAYFA_H - 16, "Synergy — Mekanik Zeka · Dijital Bakım Kartları",
                 7.5, False, (140, 150, 165))
        ciz.yazi(SAYFA_W - KENAR - 60, SAYFA_H - 16, "Sayfa %d / %d" % (i, toplam),
                 7.5, False, (140, 150, 165))
    os.makedirs(OUT_DIR, exist_ok=True)
    dosya = os.path.join(OUT_DIR, "bakim_raporu_%04d%02d.pdf" % (year, month))
    pdf.output(dosya)
    logging.info("Aylık bakım raporu oluşturuldu: %s", dosya)
    return dosya
