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
