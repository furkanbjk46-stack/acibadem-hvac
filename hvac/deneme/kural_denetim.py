# -*- coding: utf-8 -*-
"""Mekanik Zeka — DEĞİŞMEZ KURALLAR (tek kaynak).

Motorun HER sonuçta bozmaması gereken doğrular burada tanımlıdır. İki yerden
kullanılır:

  1) ÇALIŞMA ANINDA — `main_portal.tutarlilik_kontrol` her santralin sonucunu
     ekrana basmadan önce buradan geçirir. İhlal bulunursa sonuç DEĞİŞTİRİLMEZ;
     satır "tutarsız" olarak işaretlenir ve loga yazılır (hatayı gizlemek değil
     görünür kılmak esastır).
  2) TESTTE — `test_degismez_kurallar.py` binlerce rastgele senaryoda aynı
     kuralları arar.

Kurallar iki yerde ayrı ayrı yazılsaydı zamanla birbirinden ayrılırdı; bu yüzden
tek dosyadadır. Yeni kural eklerken: saf fonksiyon yaz, ihlal varsa açıklama
metni döndür, yoksa None.
"""
from typing import Any, Dict, List, Optional

GECERLI_ONEM = {"OPTIMAL", "INFO", "WARNING", "CRITICAL"}
SESSIZ_KURALLAR = {"NORMAL", "IN_BAND", "STANDBY"}
SOGUTMA_KURALLARI = {"NOT_COOLING", "COOL_EFF_LOW", "AIR_DT_LOW_COOL", "CHILLER_LOW_DT"}
ISITMA_KURALLARI = {"NOT_HEATING", "HEAT_EFF_LOW"}
KRITIK_SKOR = 7.0
UYARI_SKOR = 6.0


def _vana(profile, hangi: str) -> float:
    v = getattr(profile.valves, hangi, None) if getattr(profile, "valves", None) else None
    return v or 0.0


def _calisiyor(profile, az) -> bool:
    if az is not None and hasattr(az, "_cihaz_calisiyor"):
        return az._cihaz_calisiyor(profile)
    return _vana(profile, "cooling") >= 0.5 or _vana(profile, "heating") >= 0.5


# ── Kurallar ────────────────────────────────────────────────────────────
def K01(r, p, az, rehber):
    """her üretilen kuralın talimat açıklaması vardır"""
    if r.rule and rehber is not None and r.rule not in rehber:
        return f"kural '{r.rule}' için talimat açıklaması yok"


def K02(r, p, az, rehber):
    """önem değeri tanımlı kümededir"""
    if r.severity not in GECERLI_ONEM:
        return f"tanımsız önem: {r.severity!r}"


def K03(r, p, az, rehber):
    """NORMAL/IN_BAND/STANDBY satırın önemi OPTIMAL'dir"""
    if r.rule in SESSIZ_KURALLAR and r.severity != "OPTIMAL":
        return f"kural {r.rule} ama önem {r.severity}"


def K04(r, p, az, rehber):
    """skor 0-10 aralığındadır"""
    if r.score is not None and not (0.0 <= r.score <= 10.0):
        return f"skor aralık dışı: {r.score}"


def K05(r, p, az, rehber):
    """normal satırın skoru uyarı eşiğinin altındadır"""
    if r.rule in SESSIZ_KURALLAR and (r.score or 0) >= UYARI_SKOR:
        return f"kural {r.rule} ama skor {r.score}"


def K06(r, p, az, rehber):
    """hedef ΔT pozitiftir"""
    if r.target_delta_t is not None and r.target_delta_t <= 0:
        return f"hedef ΔT pozitif değil: {r.target_delta_t}"


def K07(r, p, az, rehber, effective_mode=None):
    """mod ile kural çelişmez (ısıtmada soğutma alarmı yok)"""
    if getattr(p, "type", "") not in ("AHU", "FCU"):
        return
    em = (effective_mode or "").upper()
    if not em:
        return
    if "HEAT" in em and r.rule in SOGUTMA_KURALLARI:
        return f"mod ISITMA ama soğutma kuralı {r.rule}"
    if "COOL" in em and r.rule in ISITMA_KURALLARI:
        return f"mod SOGUTMA ama ısıtma kuralı {r.rule}"


def K08(r, p, az, rehber):
    """çalışmayan cihazda kritik alarm üretilmez"""
    if getattr(p, "type", "") not in ("AHU", "FCU") or _calisiyor(p, az):
        return
    if _vana(p, "cooling") < 0.5 and _vana(p, "heating") < 0.5 and r.severity == "CRITICAL":
        return f"cihaz çalışmıyor ama KRİTİK: {r.rule}"


def K09(r, p, az, rehber):
    """veri eksikliği yalnızca çalışan cihazda kritiktir"""
    if r.rule != "MISSING_DATA":
        return
    calisiyor = _calisiyor(p, az)
    if r.severity == "CRITICAL" and not calisiyor:
        return "cihaz çalışmıyor ama veri eksikliği KRİTİK"
    if r.severity != "CRITICAL" and calisiyor:
        return "cihaz çalışıyor, veri yok ama kritik değil"


def K10(r, p, az, rehber):
    """üfleme durumu OPTIMAL iken üfleme alarmı olmaz"""
    if r.sat_status == "OPTIMAL" and r.rule in ("SAT_HIGH", "SAT_LOW", "SAT_WARNING"):
        return f"sat_status OPTIMAL ama kural {r.rule}"


def K11(r, p, az, rehber):
    """normal satırda kritik dili kullanılmaz"""
    if r.rule in SESSIZ_KURALLAR and "KRİTİK" in (r.action or "").upper():
        return f"kural {r.rule} ama eylem metni: {r.action!r}"


def K12(r, p, az, rehber, effective_mode=None):
    """soğutmada önerilen üfleme emişten sıcak olamaz"""
    em = (effective_mode or "").upper()
    ret = p.temperatures.return_ if p.temperatures.return_ is not None else p.temperatures.room
    if "COOL" in em and r.recommended_sat is not None and ret is not None and r.recommended_sat >= ret:
        return f"soğutmada öneri {r.recommended_sat} ≥ emiş {ret}"


def K14(r, p, az, rehber):
    """kritik bulgunun skoru uyarı eşiğinin altında olmaz"""
    if r.severity == "CRITICAL" and (r.score or 0) < UYARI_SKOR:
        return f"KRİTİK ama skor {r.score}"


def K15(r, p, az, rehber):
    """kural atanmışsa eylem metni doludur"""
    if r.rule and not (r.action or "").strip():
        return f"kural {r.rule} ama eylem metni boş"


def K16(r, p, az, rehber):
    """skor kritik eşiğin üstündeyse önem de kritiktir"""
    if (r.score or 0) >= KRITIK_SKOR and r.severity != "CRITICAL":
        return f"skor {r.score} ama önem {r.severity} ({r.rule})"


KURALLAR = [K01, K02, K03, K04, K05, K06, K07, K08, K09, K10, K11, K12, K14, K15, K16]
ACIKLAMA = {f.__name__: (f.__doc__ or "").strip() for f in KURALLAR}


def denetle(result, profile, analyzer=None, rehber=None,
            effective_mode: Optional[str] = None) -> List[Dict[str, str]]:
    """Bir analiz sonucunu değişmez kurallardan geçirir.

    Dönüş: ihlal listesi — [{"kod": "K14", "mesaj": "..."}]. Boş liste = tutarlı.
    Denetimin kendisi ASLA analizi çökertmez; kural içinde hata olursa ihlal
    olarak raporlanır ve devam edilir.
    """
    ihlaller = []
    for fn in KURALLAR:
        try:
            if fn in (K07, K12):
                mesaj = fn(result, profile, analyzer, rehber, effective_mode=effective_mode)
            else:
                mesaj = fn(result, profile, analyzer, rehber)
        except Exception as e:            # denetim hatası analizi durdurmaz
            mesaj = f"denetim kuralı çalışmadı: {type(e).__name__}"
        if mesaj:
            ihlaller.append({"kod": fn.__name__, "mesaj": mesaj})
    return ihlaller
