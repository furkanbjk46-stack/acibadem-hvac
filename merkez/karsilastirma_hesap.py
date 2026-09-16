# -*- coding: utf-8 -*-
"""
Lokasyon karşılaştırma — HESAP katmanı (Streamlit'siz, test edilebilir).

pages/ozet_karsilastirma_demo.py bu modülü kullanır. Buradaki her değer
energy_data / lokasyonlar tablolarındaki GERÇEK kolonlardan hesaplanır;
sayaçla ölçülmeyen bir kalem (aydınlatma, medikal/UPS, COP...) ÜRETİLMEZ.
Ölçülen kalemlerin toplamı hastane tüketimine ulaşmıyorsa kalan kısım
"Diğer / ayrı sayaçla ölçülmeyen" olarak gösterilir.
"""

import re
from datetime import datetime, timedelta, timezone

IST = timezone(timedelta(hours=3))

# Sistem dağılımı kalemleri: (ad, kolon(lar), renk)
# Kolon listesi verilirse o kolonlar toplanır; alt kırılım kolonları
# (Chiller1_kWh...) varsa üst kalem onlardan da doğrulanabilir.
KALEM_RENK = {
    "Chiller grupları": "#06b6d4",
    "Soğutma kuleleri": "#38bdf8",
    "MCC panoları (pompa, fan, AHU)": "#3b82f6",
    "VRF / split klimalar": "#a855f7",
    "Diğer / ayrı sayaçla ölçülmeyen": "#64748b",
}

_CHILLER_RE = re.compile(r"^Chiller(\d+)_kWh$")
_KULE_RE = re.compile(r"^Kule(\d+)_kWh$")
_MCC_RE = re.compile(r"^MCC(?:\d+|_[A-Z0-9_]+)_kWh$")


def _say(v):
    try:
        f = float(v)
        return f if f == f else 0.0          # NaN -> 0
    except (TypeError, ValueError):
        return 0.0


def _kolon_toplam(satirlar, kolon):
    return sum(_say(r.get(kolon)) for r in satirlar)


def esik_durumu(deger, esik, artis_iyi):
    """(kotu: bool|None, etiket: str).

    Tüketim metriklerinde (artis_iyi=False) eşik ÜST sınırdır; üretimde
    (kojen, artis_iyi=True) ALT sınırdır. Değer ya da eşik yoksa (None, "—").
    """
    if deger is None or esik is None:
        return None, "—"
    if artis_iyi:
        return (True, "Hedef altı") if deger < esik else (False, "Normal")
    return (True, "Eşik üstü") if deger > esik else (False, "Normal")


def sistem_dagilimi(satirlar):
    """Bir lokasyonun seçili dönemdeki satırlarından sistem bazlı dağılım.

    satirlar: energy_data kayıtları (dict listesi)
    Döner: {
      toplam, kalemler: [(ad, kWh, yuzde, renk)], chiller: [(ad, kWh)],
      kule: [(ad, kWh)], mcc: [(ad, kWh)], sebeke, kojen, olculen_oran
    }
    """
    toplam = _kolon_toplam(satirlar, "Toplam_Hastane_Tuketim_kWh")
    kolonlar = set()
    for r in satirlar:
        kolonlar.update(r.keys())

    def detay(regex, onek):
        cikti = []
        for k in sorted(kolonlar, key=lambda x: (len(x), x)):
            m = regex.match(k)
            if not m:
                continue
            v = _kolon_toplam(satirlar, k)
            if v > 0:
                ad = k[:-4].replace("_", " ")
                if onek == "CH":
                    ad = "CH-%s" % m.group(1)
                elif onek == "KULE":
                    ad = "Kule-%s" % m.group(1)
                cikti.append((ad, v))
        return cikti

    ch_detay = detay(_CHILLER_RE, "CH")
    kule_detay = detay(_KULE_RE, "KULE")
    mcc_detay = detay(_MCC_RE, "MCC")

    chiller = _kolon_toplam(satirlar, "Chiller_Tuketim_kWh") or sum(v for _, v in ch_detay)
    kule = sum(v for _, v in kule_detay)
    mcc = _kolon_toplam(satirlar, "MCC_Tuketim_kWh") or sum(v for _, v in mcc_detay)
    vrf = _kolon_toplam(satirlar, "VRF_Split_Tuketim_kWh")

    olculen = chiller + kule + mcc + vrf
    kalan = max(0.0, toplam - olculen)
    kalemler = []
    for ad, v in (("Chiller grupları", chiller), ("Soğutma kuleleri", kule),
                  ("MCC panoları (pompa, fan, AHU)", mcc), ("VRF / split klimalar", vrf),
                  ("Diğer / ayrı sayaçla ölçülmeyen", kalan)):
        if v > 0:
            kalemler.append((ad, v, (v / toplam * 100) if toplam else 0.0, KALEM_RENK[ad]))

    return {
        "toplam": toplam,
        "kalemler": kalemler,
        "chiller": ch_detay,
        "kule": kule_detay,
        "mcc": mcc_detay,
        "sebeke": _kolon_toplam(satirlar, "Sebeke_Tuketim_kWh"),
        "kojen": _kolon_toplam(satirlar, "Kojen_Uretim_kWh"),
        # Ölçülen kalemlerin toplamı hastane toplamını aşıyorsa sayaçlar
        # çakışıyor olabilir (ör. kule MCC'nin içinde de sayılıyor).
        "olculen_oran": (olculen / toplam * 100) if toplam else 0.0,
    }


def teshis(r, grup, dagilim, esik, artis_iyi, birim_metin, ondalik=2, beklenen_gun=None):
    """Veriye dayalı teşhis maddeleri. (seviye, baslik, maddeler) döner.

    r      : karşılaştırma satırı {"ikinci", "degisim", "gun", ...}
    grup   : {"ort_ikinci", "ort_sogutma_payi"}
    dagilim: sistem_dagilimi() çıktısı
    Yalnızca ölçülen değerlerden cümle kurulur; tahmin/öneri UYDURULMAZ.
    """
    maddeler = []
    kotu, _ = esik_durumu(r.get("ikinci"), esik, artis_iyi)
    v = r.get("ikinci")
    fmt = "%%.%df" % ondalik

    if v is not None and esik:
        fark = (v - esik) / esik * 100
        yon = "altında" if fark < 0 else "üzerinde"
        maddeler.append("Gösterge %s %s — hedefin (%s) %%%.1f %s."
                        % (fmt % v, birim_metin, fmt % esik, abs(fark), yon))
    go = grup.get("ort_ikinci")
    if v is not None and go:
        fark = (v - go) / go * 100
        maddeler.append("Grup ortalamasının (%s) %%%.1f %s."
                        % (fmt % go, abs(fark), "altında" if fark < 0 else "üzerinde"))
    if r.get("degisim") is not None:
        d = r["degisim"]
        maddeler.append("Önceki döneme göre %s%%%.1f." % ("▼" if d <= 0 else "▲", abs(d)))

    toplam = dagilim.get("toplam") or 0
    sog = sum(kwh for ad, kwh, _, _ in dagilim.get("kalemler", [])
              if ad in ("Chiller grupları", "Soğutma kuleleri", "VRF / split klimalar"))
    gs = grup.get("ort_sogutma_payi")
    if toplam and gs:
        pay = sog / toplam * 100
        maddeler.append("Soğutmanın (chiller + kule + VRF) toplam tüketimdeki payı %%%.1f "
                        "(grup ortalaması %%%.1f)." % (pay, gs))

    ch = dagilim.get("chiller") or []
    if len(ch) >= 2:
        ch_toplam = sum(k for _, k in ch)
        ad_max, k_max = max(ch, key=lambda x: x[1])
        ort = ch_toplam / len(ch)
        if ch_toplam and k_max > 1.5 * ort:
            maddeler.append("%s, chiller tüketiminin %%%.0f'ini tek başına karşılıyor "
                            "(%d chiller ortalamasının %.1f katı) — yük dağılımı dengesiz."
                            % (ad_max, k_max / ch_toplam * 100, len(ch), k_max / ort))

    yuk = r.get("ort_chiller_yuk")
    if yuk is not None and yuk >= 85:
        maddeler.append("Ortalama chiller yükü %%%.0f — kapasite sınırına yakın." % yuk)

    if beklenen_gun and r.get("gun") and r["gun"] < beklenen_gun:
        maddeler.append("Dönemde %d günün %d'inde veri var — eksik günler kıyası etkiler."
                        % (beklenen_gun, r["gun"]))

    if dagilim.get("olculen_oran", 0) > 105:
        maddeler.append("Ölçülen alt kalemler toplam tüketimin %%%.0f'i — sayaçlar "
                        "çakışıyor olabilir." % dagilim["olculen_oran"])

    if kotu is True:
        return "uyari", ("Hedefin altında üretim" if artis_iyi else "Hedef eşiğin üzerinde"), maddeler
    if kotu is False:
        return "normal", "Hedef aralığında", maddeler
    return "bilgi", "Hedef tanımlı değil", maddeler


def lokasyon_durumu(kayit, simdi=None):
    """lokasyonlar satırından çevrimiçi/oto-set/bakım özeti. Uydurma alan yok."""
    simdi = simdi or datetime.now(IST).replace(tzinfo=None)
    kayit = kayit or {}
    ping = kayit.get("ping_zamani")
    if not ping:
        baglanti = "Kurulmadı"
    else:
        try:
            z = datetime.fromisoformat(str(ping).replace("Z", "+00:00"))
            if z.tzinfo is not None:
                z = z.astimezone(IST).replace(tzinfo=None)
            dk = (simdi - z).total_seconds() / 60
            baglanti = "Çevrimiçi" if dk < 10 else "Çevrimdışı (%s)" % (
                "%.0f dk" % dk if dk < 120 else "%.0f saat" % (dk / 60))
        except Exception:
            baglanti = "Bilinmiyor"

    bo = kayit.get("bakim_ozet")
    if isinstance(bo, str):
        try:
            import json
            bo = json.loads(bo)
        except Exception:
            bo = {}
    bo = bo or {}
    oto = bo.get("oto") or {}
    dg = oto.get("dogrulama") or {}
    return {
        "baglanti": baglanti,
        "ariza": int(_say(bo.get("toplam_ariza"))),
        "bakim": int(_say(bo.get("toplam_bakim"))),
        "oto_metin": oto.get("metin") or "Bildirim yok",
        "oto_sonuc": oto.get("sonuc"),
        "dogrulama": dg.get("metin"),
    }
