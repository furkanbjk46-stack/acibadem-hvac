# -*- coding: utf-8 -*-
"""
Lokasyon detayı grafikleri — ay karşılaştırması ve Excel verisi (saf hesap)
==========================================================================

Girdi energy_data kayıtlarıdır (dict listesi); Streamlit ve pandas gerekmez,
bu yüzden ağsız test edilir (test_grafik_veri.py).

Excel dosyasının kendisi (openpyxl) xlsx_uret() içinde üretilir; kütüphane
yalnız çağrıldığında yüklenir, yoksa sayfa değil yalnız indirme etkilenir.
"""
import io
import math
import re
from datetime import date, datetime

# Dönem toplamı anlamsız kolonlar (sıcaklık, set, yük): günlük ortalama alınır
_ORTALAMA_KOLONLAR = {"Chiller_Set_Temp_C", "Dis_Hava_Sicakligi_C", "Chiller_Load_Percent", "Kojen_Adet"}

_TOPLAM = ("Toplam Hastane Tüketim (kWh)", "Toplam_Hastane_Tuketim_kWh")
_SEBEKE = ("Şebeke Tüketim (kWh)", "Sebeke_Tuketim_kWh")
_KOJEN = ("Kojen Üretim (kWh)", "Kojen_Uretim_kWh")

# tip → (sabit kolonlar, adından bulunan kolonlar, grafik türü, grafikteki kolon sayısı)
_TABLOLAR = {
    "tuketim": ([_TOPLAM, _SEBEKE, _KOJEN], None, "bar", 1),
    "su": ([("Su Tüketimi (m³)", "Su_Tuketimi_m3")], None, "bar", 1),
    "sebeke": ([_SEBEKE, _TOPLAM], None, "bar", 1),
    "trafo": ([], r"TRDP\d+_kWh", "bar", None),
    "kojen": ([_KOJEN, ("Kojen Doğalgaz (m³)", "Kojen_Dogalgaz_m3"), ("Kojen Adet", "Kojen_Adet")], None, "bar", 1),
    "kazan": ([("Kazan Doğalgaz (m³)", "Kazan_Dogalgaz_m3")], None, "bar", 1),
    "chiller": ([("Chiller Set (°C)", "Chiller_Set_Temp_C"), ("Dış Hava (°C)", "Dis_Hava_Sicakligi_C"),
                 ("Chiller Yük (%)", "Chiller_Load_Percent")], None, "line", 2),
    "sogutma": ([("Soğutma Tüketim (kWh)", "Toplam_Sogutma_Tuketim_kWh"), ("Chiller Tüketim (kWh)", "Chiller_Tuketim_kWh"),
                 ("VRF / Split (kWh)", "VRF_Split_Tuketim_kWh")], r"(Chiller|Kule)\d+_kWh", "bar", 1),
    "mcc": ([("MCC Tüketim (kWh)", "MCC_Tuketim_kWh")], r"MCC[_\dA-Za-z]*_kWh", "bar", 1),
}


def sayi(x):
    """Sayıya çevirir; boş / NaN / metin → None (0 SAYILMAZ: veri yok demektir)."""
    if x is None or isinstance(x, bool):
        return None
    try:
        v = float(x)
    except (TypeError, ValueError):
        return None
    return None if math.isnan(v) or math.isinf(v) else v


def gun(t):
    """Timestamp / datetime / date → date; çözülemezse None."""
    if isinstance(t, datetime):
        return None if t != t else t.date()     # NaT kendine eşit değildir
    if isinstance(t, date):
        return t
    try:
        return datetime.fromisoformat(str(t)[:10]).date()
    except ValueError:
        return None


def _toplam_ekle(hedef, anahtar, v):
    hedef[anahtar] = hedef.get(anahtar, 0.0) + v


def ay_kiyas(kayitlar, yil, ay, kolon="Toplam_Hastane_Tuketim_kWh"):
    """Seçili ay ile geçen yılın aynı ayını GÜN GÜN karşılaştırır.

    Fark yüzdesi yalnız İKİ YILDA DA verisi olan günlerden hesaplanır: kısmi ay
    tam ayla ya da eksik günlü ay dolu ayla kıyaslanınca sahte "az tüketim" çıkar.
    Ayın başı dönem dışı kalmaz: tarih karşılaştırması saat içermez.
    """
    bu, gec = {}, {}
    for k in kayitlar or []:
        t, v = gun(k.get("Tarih")), sayi(k.get(kolon))
        if t is None or v is None or t.month != ay:
            continue
        if t.year == yil:
            _toplam_ekle(bu, t.day, v)
        elif t.year == yil - 1:
            _toplam_ekle(gec, t.day, v)
    bu = dict(sorted(bu.items()))
    gec = dict(sorted(gec.items()))
    ortak = sorted(set(bu) & set(gec))
    bu_top = sum(bu[g] for g in ortak)
    gec_top = sum(gec[g] for g in ortak)
    return {
        "bu": bu, "gec": gec, "ortak_gun": len(ortak), "bu_top": bu_top, "gec_top": gec_top,
        "fark_pct": (bu_top - gec_top) / gec_top * 100 if gec_top > 0 else None,
    }


def _kolon_sira(k):
    m = re.search(r"\d+", k)
    return (re.sub(r"\d+", "", k), int(m.group()) if m else 0, k)


def _gunluk_tablo(kayitlar, tanim, desen, ek=None):
    """Tarih başına tek satır. Toplanan kolonlar toplanır, _ORTALAMA_KOLONLAR ortalanır.
    Hiç verisi olmayan kolon tabloya girmez."""
    kolonlar = list(tanim)
    if desen:
        adlar = {a for k in kayitlar for a in k if re.fullmatch(desen, str(a))}
        sabit = {k for _, k in tanim}
        for a in sorted(adlar - sabit, key=_kolon_sira):
            kolonlar.append((a[:-4].replace("_", " ") + " (kWh)", a))
    gunler = {}
    for k in kayitlar:
        t = gun(k.get("Tarih"))
        if t is not None:
            gunler.setdefault(t, []).append(k)
    dolu = [(b, a) for b, a in kolonlar if any(sayi(k.get(a)) is not None for k in kayitlar)]
    satirlar = []
    for t in sorted(gunler):
        satir = [t]
        for _, a in dolu:
            vs = [v for v in (sayi(k.get(a)) for k in gunler[t]) if v is not None]
            if not vs:
                satir.append(None)
            else:
                satir.append(sum(vs) / len(vs) if a in _ORTALAMA_KOLONLAR else sum(vs))
        satirlar.append(satir)
    return ["Tarih"] + [b for b, _ in dolu], satirlar, [a for _, a in dolu]


def _ozet(sutunlar, satirlar, kolonlar):
    cikti = []
    for i, ad in enumerate(sutunlar[1:], start=1):
        vs = [s[i] for s in satirlar if s[i] is not None]
        if not vs:
            continue
        ortalama_kolon = kolonlar is not None and kolonlar[i - 1] in _ORTALAMA_KOLONLAR
        cikti.append([ad, None if ortalama_kolon else sum(vs), sum(vs) / len(vs), min(vs), max(vs)])
    return cikti


def _kirilim_satirlari(kalemler, toplam):
    return [[ad, v, (v / toplam * 100 if toplam else None)] for ad, v in kalemler if v > 0]


def _kolon_top(kayitlar, kolon):
    return sum(v for v in (sayi(k.get(kolon)) for k in kayitlar) if v is not None)


def _sogutma_kolon(kayitlar):
    for a in ("Toplam_Sogutma_Tuketim_kWh", "Chiller_Tuketim_kWh"):
        if any(a in k for k in kayitlar):
            return a
    return None


def grafik_tablosu(tip, kayitlar, m2=None, tum_kayitlar=None, yil=None, ay=None, ay_adi="", gec_ay_adi=""):
    """Seçili grafiğin Excel paketi: {"tablolar": [...], "ozet": [...]} ya da veri yoksa None.

    tablo = {"ad", "sutunlar", "satirlar", "grafik": {"tur", "baslik", "seri_sayisi"} | None}
    """
    kayitlar = kayitlar or []
    if tip == "ay_karsilastir":
        k = ay_kiyas(tum_kayitlar, yil, ay)
        if not k["bu"] and not k["gec"]:
            return None
        satirlar = []
        for g in sorted(set(k["bu"]) | set(k["gec"])):
            b, e = k["bu"].get(g), k["gec"].get(g)
            ortak = b is not None and e is not None
            satirlar.append([g, e, b, (b - e) if ortak else None,
                             ((b - e) / e * 100) if ortak and e else None])
        ozet = [["Karşılaştırılan gün sayısı", k["ortak_gun"]],
                ["%s toplam (kWh, ortak günler)" % gec_ay_adi, k["gec_top"]],
                ["%s toplam (kWh, ortak günler)" % ay_adi, k["bu_top"]]]
        if k["fark_pct"] is not None:
            ozet.append(["Fark (%)", k["fark_pct"]])
        return {"ozet_sutunlar": ["Gösterge", "Değer"], "ozet": ozet, "tablolar": [{
            "ad": "Veri", "sutunlar": ["Gün", gec_ay_adi + " (kWh)", ay_adi + " (kWh)", "Fark (kWh)", "Fark (%)"],
            "satirlar": satirlar, "grafik": {"tur": "bar", "baslik": "Günlük tüketim", "seri_sayisi": 2}}]}

    if not kayitlar:
        return None

    if tip == "verimlilik":
        sutunlar, satirlar, kolonlar = _gunluk_tablo(kayitlar, [_TOPLAM], None)
        if len(sutunlar) < 2:
            return None
        if m2:
            sutunlar = sutunlar + ["kWh/m²"]
            satirlar = [s + [(s[1] / m2 if s[1] is not None else None)] for s in satirlar]
        return {"ozet_sutunlar": ["Kalem", "Toplam", "Ortalama", "En düşük", "En yüksek"],
                "ozet": _ozet(sutunlar, satirlar, None),
                "tablolar": [{"ad": "Veri", "sutunlar": sutunlar, "satirlar": satirlar,
                              "grafik": {"tur": "line", "baslik": "kWh/m²", "seri_kolon": len(sutunlar) - 1,
                                         "seri_sayisi": 1} if m2 else None}]}

    if tip == "kpi_ozet":
        top = _kolon_top(kayitlar, "Toplam_Hastane_Tuketim_kWh")
        koj = _kolon_top(kayitlar, "Kojen_Uretim_kWh")
        sog = _sogutma_kolon(kayitlar)
        satirlar = [["Elektrik Tüketimi", top, "kWh"], ["Kojen Üretimi", koj, "kWh"]]
        if top > 0:
            satirlar.append(["Kojen Karşılama Oranı", koj / top * 100, "%"])
        satirlar += [["Kojen Doğalgaz", _kolon_top(kayitlar, "Kojen_Dogalgaz_m3"), "m³"],
                     ["Kazan Doğalgaz", _kolon_top(kayitlar, "Kazan_Dogalgaz_m3"), "m³"],
                     ["Su Tüketimi", _kolon_top(kayitlar, "Su_Tuketimi_m3"), "m³"],
                     ["Şebeke Tüketimi", _kolon_top(kayitlar, "Sebeke_Tuketim_kWh"), "kWh"],
                     ["MCC Tüketimi", _kolon_top(kayitlar, "MCC_Tuketim_kWh"), "kWh"]]
        if sog:
            satirlar.append(["Soğutma Tüketimi", _kolon_top(kayitlar, sog), "kWh"])
        if m2 and top > 0:
            satirlar.append(["kWh/m²", top / m2, "kWh/m²"])
        return {"tablolar": [{"ad": "KPI", "sutunlar": ["Gösterge", "Değer", "Birim"],
                              "satirlar": satirlar, "grafik": None}]}

    if tip == "enerji_kirilim":
        top = _kolon_top(kayitlar, "Toplam_Hastane_Tuketim_kWh")
        if top <= 0:
            return None
        koj = _kolon_top(kayitlar, "Kojen_Uretim_kWh")
        seb = _kolon_top(kayitlar, "Sebeke_Tuketim_kWh")
        sog_k = _sogutma_kolon(kayitlar)
        sog = _kolon_top(kayitlar, sog_k) if sog_k else 0
        mcc = _kolon_top(kayitlar, "MCC_Tuketim_kWh")
        return {"tablolar": [
            {"ad": "Kaynak", "sutunlar": ["Kalem", "kWh", "Pay (%)"],
             "satirlar": _kirilim_satirlari([("Kojen", koj), ("Şebeke", seb), ("Diğer", max(top - koj - seb, 0))], top),
             "grafik": {"tur": "pie", "baslik": "Kaynak kırılımı", "seri_sayisi": 1}},
            {"ad": "Tüketim", "sutunlar": ["Kalem", "kWh", "Pay (%)"],
             "satirlar": _kirilim_satirlari([("Soğutma", sog), ("MCC", mcc), ("Diğer", max(top - sog - mcc, 0))], top),
             "grafik": {"tur": "pie", "baslik": "Tüketim kırılımı", "seri_sayisi": 1}},
        ]}

    tanim = _TABLOLAR.get(tip)
    if tanim is None:
        return None
    sabit, desen, tur, seri = tanim
    sutunlar, satirlar, kolonlar = _gunluk_tablo(kayitlar, sabit, desen)
    if len(sutunlar) < 2 or not satirlar:
        return None
    return {"ozet_sutunlar": ["Kalem", "Toplam", "Ortalama", "En düşük", "En yüksek"],
            "ozet": _ozet(sutunlar, satirlar, kolonlar),
            "tablolar": [{"ad": "Veri", "sutunlar": sutunlar, "satirlar": satirlar,
                          "grafik": {"tur": tur, "baslik": "", "seri_sayisi": seri or len(sutunlar) - 1}}]}


def _yaz_tablo(ws, bas_satir, sutunlar, satirlar):
    from openpyxl.styles import Alignment, Font, PatternFill
    for j, ad in enumerate(sutunlar, start=1):
        h = ws.cell(row=bas_satir, column=j, value=ad)
        h.font = Font(bold=True, color="FFFFFF")
        h.fill = PatternFill("solid", fgColor="133273")
        h.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
    for i, satir in enumerate(satirlar, start=bas_satir + 1):
        for j, v in enumerate(satir, start=1):
            c = ws.cell(row=i, column=j, value=v)
            if isinstance(v, date):
                c.number_format = "dd.mm.yyyy"
            elif isinstance(v, float):
                c.number_format = "#,##0.00"
    for j, ad in enumerate(sutunlar, start=1):
        en = max([len(str(ad))] + [len("%.2f" % s[j - 1]) if isinstance(s[j - 1], float) else len(str(s[j - 1] or ""))
                                   for s in satirlar[:200]])
        ws.column_dimensions[ws.cell(row=bas_satir, column=j).column_letter].width = min(max(en + 3, 12), 34)


def _ekle_grafik(ws, tablo, bas_satir):
    from openpyxl.chart import BarChart, LineChart, PieChart, Reference
    g = tablo.get("grafik")
    son = bas_satir + len(tablo["satirlar"])
    if not g or son <= bas_satir:
        return
    kategori = Reference(ws, min_col=1, min_row=bas_satir + 1, max_row=son)
    if g["tur"] == "pie":
        ch = PieChart()
        ch.add_data(Reference(ws, min_col=2, min_row=bas_satir, max_row=son), titles_from_data=True)
        ch.set_categories(kategori)
    else:
        ch = LineChart() if g["tur"] == "line" else BarChart()
        ilk = g.get("seri_kolon", 1) + 1
        for j in range(ilk, min(ilk + g["seri_sayisi"], len(tablo["sutunlar"]) + 1)):
            ch.add_data(Reference(ws, min_col=j, min_row=bas_satir, max_row=son), titles_from_data=True)
        ch.set_categories(kategori)
        # openpyxl 3.1: delete=False yazılmazsa Excel eksenleri gizler
        ch.x_axis.delete = False
        ch.y_axis.delete = False
        if isinstance(tablo["satirlar"][0][0], date):
            ch.x_axis.number_format = "dd.mm"
        ch.y_axis.number_format = "#,##0"
        ch.legend.position = "b"
    ch.title = g.get("baslik") or None
    ch.height, ch.width = 9.5, 22
    ws.add_chart(ch, "%s%d" % (ws.cell(row=1, column=len(tablo["sutunlar"]) + 2).column_letter, bas_satir))


def xlsx_uret(baslik, lokasyon, donem, paket, olusturma=None) -> bytes:
    """paket (grafik_tablosu çıktısı) → .xlsx. İlk sayfa özet, sonrakiler veri + grafik."""
    from openpyxl import Workbook
    from openpyxl.styles import Font
    wb = Workbook()
    oz = wb.active
    oz.title = "Özet"
    oz["A1"] = baslik
    oz["A1"].font = Font(bold=True, size=14, color="133273")
    bilgi = [("Lokasyon", lokasyon), ("Dönem", donem)]
    if olusturma:
        bilgi.append(("Oluşturulma", olusturma))
    for i, (a, d) in enumerate(bilgi, start=2):
        oz.cell(row=i, column=1, value=a).font = Font(bold=True)
        oz.cell(row=i, column=2, value=d)
    oz.column_dimensions["A"].width = 34
    if paket.get("ozet"):
        _yaz_tablo(oz, len(bilgi) + 3, paket["ozet_sutunlar"], paket["ozet"])
        oz.column_dimensions["A"].width = 38
    for t in paket["tablolar"]:
        ws = wb.create_sheet(t["ad"])
        _yaz_tablo(ws, 1, t["sutunlar"], t["satirlar"])
        ws.freeze_panes = "B2"
        _ekle_grafik(ws, t, 1)
    tampon = io.BytesIO()
    wb.save(tampon)
    return tampon.getvalue()
