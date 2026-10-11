# -*- coding: utf-8 -*-
"""Sabah analizinin VERİ KATMANI — tek kaynak.

NEDEN AYRI MODÜL:
Sabah analizi (app_merkez.py) metinleri doğrudan DataFrame'den kuruyordu ve
"kolon boş" ile "değer sıfır" aynı şeye dönüşüyordu: `df[col].sum()` eksik
kolona da 0 döner. 11.10.2026'da kojen verisi girilmemiş bir gün için model
"dünkü %100 şebeke bağlantısı kojenin arıza durumunu işaret etmektedir,
kojen sistemi derhal kontrol edilmelidir" dedi — ortada arıza yoktu, veri
yoktu. Bu ayrımı yapan mantık burada durur ve testi vardır.

Modül Streamlit'e, Supabase'e ve ağa DOKUNMAZ; girdi olarak hazır bir
DataFrame ve heartbeat sözlüğü alır.
"""

ESIKLER = {
    "yogunluk_alt": 0.5,     # kWh/m²/gün
    "yogunluk_ust": 1.5,
    "kojen_verim":  3.5,     # kWh/m³ (kojen üretimi / kojen gazı)
    "sebeke_bag":   30.0,    # %  (şebeke / (şebeke + kojen))
    "gaz_verim":    5.0,     # kWh/m³
}

# Günlük analizde kullanılan kalemler: etiket -> kolon adı
KALEMLER = {
    "elektrik":   "Toplam_Hastane_Tuketim_kWh",
    "sebeke":     "Sebeke_Tuketim_kWh",
    "kojen":      "Kojen_Uretim_kWh",
    "kojen_gaz":  "Kojen_Dogalgaz_m3",
    "kazan_gaz":  "Kazan_Dogalgaz_m3",
    "su":         "Su_Tuketimi_m3",
    "chiller":    "Chiller_Tuketim_kWh",
    "mcc":        "MCC_Tuketim_kWh",
}


def kalem_var(df, kolon):
    """Bu kalem GERÇEKTEN girilmiş mi? (kolon var ve en az bir dolu değer)

    Sıfır ile BOŞ ayrı şeylerdir: sıfır "üretim olmadı", boş "ölçüm yok".
    """
    try:
        return kolon in df.columns and bool(df[kolon].notna().any())
    except Exception:
        return False


def _topla(df, kolon):
    try:
        return float(df[kolon].sum()) if kolon in df.columns else 0.0
    except Exception:
        return 0.0


def _ortalama(df, kolon):
    try:
        if kolon not in df.columns:
            return None
        d = df[kolon].dropna()
        return float(d.mean()) if len(d) else None
    except Exception:
        return None


def gun_ozeti(df_gun, m2):
    """Bir günün (ya da dönemin) kalem özeti.

    Dönen sözlükte her sayısal değerin yanında `var_*` bayrağı bulunur:
    False ise o kalem GİRİLMEMİŞTİR ve değeri yorumlanmamalıdır.
    Oranlar yalnızca gereken kalemlerin HEPSİ girilmişse hesaplanır.
    """
    bos = (df_gun is None) or (hasattr(df_gun, "empty") and df_gun.empty)
    o = {"veri_yok_gun": bool(bos), "eksik": [], "m2": m2}
    if bos:
        o["eksik"] = sorted(KALEMLER.keys())
        for ad in KALEMLER:
            o["var_" + ad] = False
            o[ad] = None
        o.update({"yogunluk": None, "kojen_verim": None, "sebeke_bag": None,
                  "gaz_verim": None, "gaz": None, "chiller_set": None,
                  "chiller_yuk": None})
        return o

    for ad, kol in KALEMLER.items():
        v = kalem_var(df_gun, kol)
        o["var_" + ad] = v
        o[ad] = _topla(df_gun, kol) if v else None
        if not v:
            o["eksik"].append(ad)
    o["eksik"] = sorted(o["eksik"])

    o["chiller_set"] = _ortalama(df_gun, "Chiller_Set_Temp_C")
    o["chiller_yuk"] = _ortalama(df_gun, "Chiller_Load_Percent")

    # ── Türetilmiş oranlar ──
    o["yogunluk"] = (round(o["elektrik"] / m2, 2)
                     if o["var_elektrik"] and m2 else None)
    o["kojen_verim"] = (round(o["kojen"] / o["kojen_gaz"], 2)
                        if o["var_kojen"] and o["var_kojen_gaz"]
                        and o["kojen_gaz"] > 0 else None)
    # Şebeke bağımlılığı İKİ kalem de girilmişse anlamlıdır. Kojen boşken
    # payda=şebeke olur ve oran %100 çıkar; bu "kojen durdu" diye okunuyordu.
    o["sebeke_bag"] = (round(o["sebeke"] / (o["sebeke"] + o["kojen"]) * 100, 1)
                       if o["var_sebeke"] and o["var_kojen"]
                       and (o["sebeke"] + o["kojen"]) > 0 else None)
    _gaz = (o["kojen_gaz"] or 0) + (o["kazan_gaz"] or 0)
    o["gaz"] = _gaz if (o["var_kojen_gaz"] or o["var_kazan_gaz"]) else None
    o["gaz_verim"] = (round(o["elektrik"] / _gaz, 2)
                      if o["var_elektrik"] and o["gaz"] and _gaz > 0 else None)
    o["chiller_pay"] = (round(o["chiller"] / o["elektrik"] * 100, 1)
                        if o["var_chiller"] and o["var_elektrik"]
                        and o["elektrik"] > 0 else None)
    return o


def _gun_satirlari(df_lok, tarih):
    """Bir güne ait satırlar (Tarih kolonu datetime)."""
    try:
        return df_lok[df_lok["Tarih"].dt.date == tarih]
    except Exception:
        return df_lok.iloc[0:0]


def _dis_hava(df_gun):
    return _ortalama(df_gun, "Dis_Hava_Sicakligi_C")


def kiyas_noktalari(df_lok, hedef_tarih, m2):
    """Dünü KENDİ geçmişiyle karşılaştır: geçen hafta ve geçen yıl aynı gün.

    Sabit eşik ("0.5–1.5 kWh/m²/gün") bir hastanenin kendi normalini
    söylemez; 58.529 kWh tek başına ne iyi ne kötüdür. Aynı haftanın günü
    ve geçen yılın aynı günü, dış hava farkıyla birlikte, asıl zemindir.
    """
    import datetime as _dt
    cikti = []
    try:
        hedef = _gun_satirlari(df_lok, hedef_tarih)
    except Exception:
        return cikti
    if hedef.empty or not kalem_var(hedef, KALEMLER["elektrik"]):
        return cikti
    simdi_kwh = _topla(hedef, KALEMLER["elektrik"])
    simdi_dis = _dis_hava(hedef)

    for ad, gun_fark in (("geçen hafta aynı gün", 7), ("geçen yıl aynı gün", 364)):
        t = hedef_tarih - _dt.timedelta(days=gun_fark)
        g = _gun_satirlari(df_lok, t)
        if g.empty or not kalem_var(g, KALEMLER["elektrik"]):
            cikti.append({"ad": ad, "tarih": t, "veri": False})
            continue
        onceki = _topla(g, KALEMLER["elektrik"])
        onceki_dis = _dis_hava(g)
        cikti.append({
            "ad": ad, "tarih": t, "veri": True,
            "elektrik": onceki,
            "yogunluk": round(onceki / m2, 2) if m2 else None,
            "degisim": (round((simdi_kwh - onceki) / onceki * 100, 1)
                        if onceki > 0 else None),
            "dis_hava": round(onceki_dis, 1) if onceki_dis is not None else None,
            "dis_fark": (round(simdi_dis - onceki_dis, 1)
                         if (simdi_dis is not None and onceki_dis is not None) else None),
        })
    return cikti


def _pencere(df_lok, bitis, gun):
    """[bitis-gun+1 .. bitis] aralığındaki satırlar."""
    import datetime as _dt
    bas = bitis - _dt.timedelta(days=gun - 1)
    try:
        d = df_lok["Tarih"].dt.date
        return df_lok[(d >= bas) & (d <= bitis)]
    except Exception:
        return df_lok.iloc[0:0]


def _yon(degisim, buyuk_iyi=True, esik=3.0):
    """Değişim yönü: eşiğin altındaki oynama 'sabit' sayılır."""
    if degisim is None:
        return None
    if abs(degisim) < esik:
        return "sabit"
    artiyor = degisim > 0
    iyi = artiyor if buyuk_iyi else not artiyor
    return ("artıyor" if artiyor else "azalıyor") + (" (iyi)" if iyi else " (kötü)")


def trend(df_lok, hedef_tarih, pencere_gun=7):
    """Son N gün ile ÖNCEKİ N günü karşılaştırır — yön bilgisi.

    Tek gün + 30 günlük ortalama, "kojen verimi üç haftadır düşüyor" gibi
    arıza öncesi sinyali göstermez. Oranlar pencere TOPLAMLARINDAN hesaplanır
    (günlük oranların ortalaması, az üretilen günleri fazla ağırlıklandırır).
    """
    import datetime as _dt
    son   = _pencere(df_lok, hedef_tarih, pencere_gun)
    onc   = _pencere(df_lok, hedef_tarih - _dt.timedelta(days=pencere_gun), pencere_gun)
    cikti = {"pencere": pencere_gun,
             "kapsama": (int(son["Tarih"].dt.date.nunique()) if not son.empty else 0)}

    def _oran(df, tur):
        if df.empty:
            return None
        if tur == "elektrik_gun":
            if not kalem_var(df, KALEMLER["elektrik"]):
                return None
            gun = max(1, int(df["Tarih"].dt.date.nunique()))
            return round(_topla(df, KALEMLER["elektrik"]) / gun, 1)
        if tur == "kojen_verim":
            if not (kalem_var(df, KALEMLER["kojen"]) and kalem_var(df, KALEMLER["kojen_gaz"])):
                return None
            gaz = _topla(df, KALEMLER["kojen_gaz"])
            return round(_topla(df, KALEMLER["kojen"]) / gaz, 2) if gaz > 0 else None
        if tur == "sebeke_bag":
            if not (kalem_var(df, KALEMLER["sebeke"]) and kalem_var(df, KALEMLER["kojen"])):
                return None
            s, k = _topla(df, KALEMLER["sebeke"]), _topla(df, KALEMLER["kojen"])
            return round(s / (s + k) * 100, 1) if (s + k) > 0 else None
        return None

    for tur, buyuk_iyi in (("elektrik_gun", False), ("kojen_verim", True),
                           ("sebeke_bag", False)):
        a, b = _oran(onc, tur), _oran(son, tur)
        deg = (round((b - a) / a * 100, 1) if (a not in (None, 0) and b is not None)
               else None)
        cikti[tur] = {"onceki": a, "son": b, "degisim": deg,
                      "yon": _yon(deg, buyuk_iyi)}
    return cikti


def mekanik_ozet(bakim_ozet, tam=True):
    """Lokasyonun mekanik/saha durumu — kısa cümleler listesi.

    Enerji sayısı tek başına kök nedeni söylemez: "kojen verisi yok" ile
    "kojen analizörü bağlantı hatası" yan yana durunca anlam kazanır.
    """
    oz = bakim_ozet or {}
    if not isinstance(oz, dict) or not oz:
        return ["lokasyondan durum gelmiyor"]
    sat = []
    ariza, bakim = oz.get("toplam_ariza", 0) or 0, oz.get("toplam_bakim", 0) or 0
    if ariza or bakim:
        cihaz = ", ".join(
            c.get("ad", str(c)) if isinstance(c, dict) else str(c)
            for c in (oz.get("arizali_cihazlar") or [])[:3])
        sat.append("Arıza %d / bakım %d%s" % (ariza, bakim,
                                              (" (%s)" % cihaz) if cihaz else ""))
    else:
        sat.append("Arıza yok")

    va = oz.get("veri_alarm") or {}
    if va.get("toplam"):
        sat.append("VERİ ALARMI: " + "; ".join(
            str(m) for m in (va.get("mesajlar") or [])[:2]) or "VERİ ALARMI")

    o = oz.get("oto") or {}
    if o:
        sat.append("Oto-set: %s" % (o.get("metin") or o.get("sonuc") or "—"))
        if (o.get("dogrulama") or {}).get("sonuc") == "uygulanmadi":
            sat.append("Setler cihazda UYGULANMADI")
        setler = o.get("setler") or {}
        if tam and setler:
            sat.append("Yürürlükteki set: chiller %s°C, kollektör %s/%s°C (%s)"
                       % (setler.get("chiller"),
                          setler.get("GUNDUZ_KOLLEKTOR_SET"),
                          setler.get("GECE_KOLLEKTOR_SET"),
                          {"gunduz": "gündüz", "gece": "gece"}.get(o.get("donem"), "—")))
        if tam and (o.get("konum") or {}).get("kaynak") == "varsayilan":
            sat.append("Hava tahmini VARSAYILAN konumla alınıyor (profil girilmemiş)")

    ot = oz.get("oz_test") or {}
    if ot.get("durum") and ot["durum"] != "GECTI":
        sat.append("Mekanik Zeka öz testi KALDI (%s/%s)"
                   % (ot.get("gecen"), ot.get("toplam")))
    return sat
