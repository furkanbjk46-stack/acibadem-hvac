# -*- coding: utf-8 -*-
"""
ÖĞRENME — kuralın bu lokasyondaki güveni, eşiği ve susturma
===========================================================

A5 (24.11.2026, tasarım: merkez/sunum/tasarruf_ogrenme_tasarimi.html §5).

Öğrenme "kaç öneriye evet dendi"den DEĞİL, ölçülen sonuçtan beslenir. Kaynak yalnız
bu lokasyonun bulgu defteridir (veri/tasarruf_bulgulari.json); bir lokasyonun
öğrendiği başka lokasyona kopyalanmaz, Synapse yalnız özeti görür.

Kural = bulgu kodunun gün tipi eki atılmış hali (HAFTA_SONU_ISITMA_PAZAR ve
_CUMARTESI aynı kuraldır).

  başarı     ölçümde 'doğrulandı' (1), 'belirsiz' (0,5)
  başarısız  ölçümde 'tutmadı' (1); 'veri yanlış' reddi (1); 'zaten yapılıyor' reddi (0,5)
             (bulgu var olmayan bir alışkanlığı göstermiş demektir)
  güven      (başarı + 1) / (başarı + başarısız + 2)  — kanıt yokken 0,5
  seviye     yeni (kanıt yok) · yüksek · orta · düşük (raporda alta iner) · susturuldu
  eşik çarpanı 1,25 ^ (tutmadı + veri yanlış), en fazla 3 — kural bu lokasyonda daha
             büyük farkı görmeden tetiklenmez

'Uygulanamaz' ve 'ölçülemez' kuralın doğruluğu hakkında bilgi vermez; sayılmaz.
Oto-set ve BACnet'e hiçbir şey yazılmaz: öğrenme yalnız raporu ve sıralamayı etkiler.
"""
from __future__ import annotations

import re
from typing import Dict, Iterable, List, Optional

DUSUK_GUVEN = 0.35
SUSTUR_GUVEN = 0.25
YUKSEK_GUVEN = 0.65
DUSUK_EN_AZ_BASARISIZ = 2
SUSTUR_EN_AZ_BASARISIZ = 3
CARPAN_TABAN = 1.25
EN_FAZLA_CARPAN = 3.0
EN_FAZLA_BULGU = 5            # raporda öne çıkan en fazla bulgu (tasarım §1)

SEVIYE_ETIKET = {"yeni": "Yeni (henüz sonuç yok)", "yuksek": "Yüksek", "orta": "Orta",
                 "dusuk": "Düşük — raporda alta indi", "susturuldu": "Susturuldu"}
_SIRA = {"yuksek": 0, "orta": 1, "yeni": 1, "dusuk": 2, "susturuldu": 3}


def kural_adi(kod: str) -> str:
    return re.sub(r"_(PAZAR|CUMARTESI|HAFTA_ICI)$", "", str(kod or ""))


def _kural_kaydi() -> Dict:
    return {"basari": 0.0, "basarisiz": 0.0, "dogrulandi": 0, "belirsiz": 0, "tutmadi": 0, "olculemez": 0,
            "olculuyor": 0, "uygulandi": 0, "red": {}, "bulgular": []}


def kural_ozeti(kayitlar: Iterable[Dict]) -> Dict[str, Dict]:
    """Defter kayıtları → kural başına güven, seviye, eşik çarpanı."""
    out: Dict[str, Dict] = {}
    for r in kayitlar:
        if not isinstance(r, dict) or not r.get("kod"):
            continue
        k = out.setdefault(kural_adi(r["kod"]), _kural_kaydi())
        k["bulgular"].append(r["kod"])
        # Geçmiş ölçümler (bulgu yeniden sorulup tekrar uygulandıysa) + güncel ölçüm
        sonuclar = [o.get("durum") for o in (r.get("olcum_gecmisi") or []) if isinstance(o, dict)]
        if r.get("durum") in ("dogrulandi", "belirsiz", "tutmadi", "olculemez", "olculuyor"):
            sonuclar.append(r["durum"])
        for d in sonuclar:
            d = "tutmadi" if d == "artis" else d
            if d in k:
                k[d] += 1
        for kg in r.get("karar_gecmisi") or []:
            if kg.get("karar") == "uygulandi":
                k["uygulandi"] += 1
            elif kg.get("karar") == "reddedildi":
                n = kg.get("neden") or "belirtilmemis"
                k["red"][n] = k["red"].get(n, 0) + 1
    for ad, k in out.items():
        k["basari"] = k["dogrulandi"] + 0.5 * k["belirsiz"]
        k["basarisiz"] = k["tutmadi"] + k["red"].get("veri_yanlis", 0) + 0.5 * k["red"].get("zaten_yapiliyor", 0)
        kanit = k["basari"] + k["basarisiz"]
        k["guven"] = (k["basari"] + 1) / (kanit + 2)
        if kanit == 0:
            k["seviye"] = "yeni"
        elif k["guven"] <= SUSTUR_GUVEN and k["basarisiz"] >= SUSTUR_EN_AZ_BASARISIZ:
            k["seviye"] = "susturuldu"
        elif k["guven"] < DUSUK_GUVEN and k["basarisiz"] >= DUSUK_EN_AZ_BASARISIZ:
            k["seviye"] = "dusuk"
        elif k["guven"] >= YUKSEK_GUVEN and k["basari"] >= 2:
            k["seviye"] = "yuksek"
        else:
            k["seviye"] = "orta"
        k["esik_carpani"] = min(EN_FAZLA_CARPAN,
                                CARPAN_TABAN ** (k["tutmadi"] + k["red"].get("veri_yanlis", 0)))
    return out


def esik_carpanlari(ozet: Dict[str, Dict]) -> Dict[str, float]:
    return {ad: k["esik_carpani"] for ad, k in ozet.items() if k["esik_carpani"] > 1.0}


def kural_seviyesi(ozet: Dict[str, Dict], kod: str) -> str:
    return (ozet.get(kural_adi(kod)) or {}).get("seviye", "yeni")


def sirala(bulgular: List[Dict], ozet: Dict[str, Dict]) -> List[Dict]:
    """Güvenli kural önce; aynı seviyede 'Öneri' olan ve tasarrufu hesaplanan önce.
    Susturulan kural listeden çıkar."""
    def anahtar(b):
        sev = kural_seviyesi(ozet, b["kod"])
        oneri = 0 if b.get("durum") in ("aday", "Öneri") else 1
        return (_SIRA.get(sev, 1), oneri, 0 if b.get("tasarruf") else 1)
    return sorted([b for b in bulgular if kural_seviyesi(ozet, b["kod"]) != "susturuldu"], key=anahtar)


def guven_metni(ozet: Dict[str, Dict], kod: str) -> Optional[str]:
    k = ozet.get(kural_adi(kod))
    if not k or k["seviye"] == "yeni":
        return None
    parca = []
    if k["dogrulandi"]:
        parca.append(f"{k['dogrulandi']} doğrulandı")
    if k["belirsiz"]:
        parca.append(f"{k['belirsiz']} belirsiz")
    if k["tutmadi"]:
        parca.append(f"{k['tutmadi']} tutmadı")
    if k["red"].get("veri_yanlis"):
        parca.append(f"{k['red']['veri_yanlis']} kez 'veri yanlış'")
    if k["red"].get("zaten_yapiliyor"):
        parca.append(f"{k['red']['zaten_yapiliyor']} kez 'zaten yapılıyor'")
    m = f"Bu kuralın bu lokasyondaki güveni: %{k['guven'] * 100:.0f} ({', '.join(parca)})"
    if k["seviye"] == "dusuk":
        m += " — düşük, raporda alta indi"
    if k["esik_carpani"] > 1.0:
        from tasarruf.aliskanlik import tr_sayi
        m += f"; tetik eşiği {tr_sayi(k['esik_carpani'], 2)} katına çıkarıldı"
    return m + "."


def susturulan_kurallar(ozet: Dict[str, Dict]) -> List[str]:
    return sorted(ad for ad, k in ozet.items() if k["seviye"] == "susturuldu")


def synapse_ozeti(ozet: Dict[str, Dict]) -> List[Dict]:
    """Heartbeat için küçük liste: yalnız kanıtı olan kurallar."""
    return [{"kural": ad, "guven": round(k["guven"], 2), "seviye": k["seviye"],
             "dogrulandi": k["dogrulandi"], "tutmadi": k["tutmadi"]}
            for ad, k in sorted(ozet.items()) if k["seviye"] != "yeni"]
