# -*- coding: utf-8 -*-
"""Mekanik Zeka — DEĞİŞMEZ KURAL motoru (property-based test).

    python hvac/deneme/test_degismez_kurallar.py [senaryo_sayisi] [tohum]

Tek tek vaka yazmak yerine, motorun HER girdide bozmaması gereken doğruları
("değişmez kural" / invariant) tanımlar; senaryoları rastgele üretir ve kuralı
bozan bir örnek arar. Bilinmeyen hataları yakalamak içindir: vaka listesi
yazarken aklımıza gelmeyen kombinasyonları makine bulur.

Bozulma bulunursa EN KÜÇÜK karşı örnek raporlanır (girdi sadeleştirme ile).
"""
import logging
import os
import random
import sys
import tempfile

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
logging.disable(logging.CRITICAL)

import on_kosul as ok
import main_portal as mp

_tmp = tempfile.mkdtemp(prefix="degismez_")
ok.DURUM_FILE = os.path.join(_tmp, "durum.json")
ok.CARDS_FILE = os.path.join(_tmp, "cards.json")
ok.AUDIT_FILE = os.path.join(_tmp, "audit.jsonl")
mp.get_maintenance_card = lambda n, loc=None: {}

SAYI = int(sys.argv[1]) if len(sys.argv) > 1 else 50000
TOHUM = int(sys.argv[2]) if len(sys.argv) > 2 else 20260920

GECERLI_ONEM = {"OPTIMAL", "WARNING", "CRITICAL", "INFO"}
SOGUTMA_KURALLARI = {"NOT_COOLING", "COOL_EFF_LOW", "AIR_DT_LOW_COOL", "CHILLER_LOW_DT"}
ISITMA_KURALLARI = {"NOT_HEATING", "HEAT_EFF_LOW"}
SESSIZ_KURALLAR = {"NORMAL", "IN_BAND", "STANDBY"}


# ── Senaryo üretimi ──────────────────────────────────────────────────────
def _uret(rnd):
    """Rastgele ama FİZİKSEL OLARAK MÜMKÜN bir senaryo üretir."""
    def t(a, b, bos=0.15):
        return None if rnd.random() < bos else round(rnd.uniform(a, b), 1)

    def vana():
        return rnd.choice([0, 0, 0.3, 5, 15, 39, 40, 41, 60, 69, 70, 80, 89, 90, 100,
                           round(rnd.uniform(0, 100), 1)])

    return {
        "tip": rnd.choice(["AHU", "AHU", "AHU", "FCU", "Collector", "Chiller"]),
        "mod": rnd.choice(["AUTO", "AUTO", "", "COOLING", "HEATING", "Sogutma", "Isitma"]),
        "sat": t(8, 45), "supply": t(8, 45), "ret": t(12, 32), "room": t(12, 38),
        "setp": t(18, 26, 0.05), "inlet": t(4, 75), "outlet": t(4, 75),
        "oat": t(-8, 42), "cv": vana(), "hv": vana(),
        "start": rnd.choice([None, None, 0, 1]),
        "basinc": rnd.choice([None, None, 0, 120, 450]),
    }


_sayac = [0]


def _profil(s):
    # Her senaryo AYRI cihaz adı alır: on_kosul kapısı ardışık okumaları hatırlar
    # (2/3 onay); aynı adı kullanmak senaryoları birbirine karıştırır.
    s.setdefault("ad", None)
    if not s["ad"]:
        _sayac[0] += 1
        s["ad"] = f"E{_sayac[0]}"
    T = mp.TemperatureData(supply=s["supply"], return_=s["ret"], inlet=s["inlet"],
                           outlet=s["outlet"], room=s["room"], setpoint=s["setp"],
                           sat=s["sat"], plant_supply=None, plant_return=None, oat=s["oat"])
    V = mp.ValveData(cooling=s["cv"], heating=s["hv"])
    p = mp.EquipmentProfile(type=s["tip"], name=s["ad"], location="MAS-1", mode=s["mod"],
                            temperatures=T, valves=V)
    for alan, deger in (("start_stop", s["start"]), ("pressure_pa", s["basinc"])):
        if hasattr(p, alan):
            setattr(p, alan, deger)
    return p


_AZ = mp.HVACAnalyzer()     # motor bir kez kurulur (her senaryoda kurmak yavaş)


def _calistir(s):
    p = _profil(s)
    return _AZ.analyze_equipment(p, None, None, s["oat"], 1.0, 5.0), p, _AZ


# ── Değişmez kurallar ────────────────────────────────────────────────────
# Her kural: (kod, açıklama, fonksiyon) — fonksiyon bozulma varsa metin döner.
def K01(r, p, az, s):
    if r.rule and r.rule not in mp.INSTRUCTION_GUIDE:
        return f"kural '{r.rule}' için talimat açıklaması yok"

def K02(r, p, az, s):
    if r.severity not in GECERLI_ONEM:
        return f"tanımsız önem: {r.severity!r}"

def K03(r, p, az, s):
    if r.rule in SESSIZ_KURALLAR and r.severity != "OPTIMAL":
        return f"kural {r.rule} ama önem {r.severity} (normal satır uyarı gösteriyor)"

def K04(r, p, az, s):
    if r.score is not None and not (0.0 <= r.score <= 10.0):
        return f"skor aralık dışı: {r.score}"

def K05(r, p, az, s):
    if r.rule in SESSIZ_KURALLAR and r.score is not None and r.score >= 6.0:
        return f"kural {r.rule} ama skor {r.score} (uyarı eşiğinin üstünde)"

def K06(r, p, az, s):
    if r.target_delta_t is not None and r.target_delta_t <= 0:
        return f"hedef ΔT pozitif değil: {r.target_delta_t}"

def K07(r, p, az, s):
    """Mod ile kural çelişmesin: ısıtmada soğutma alarmı üretilemez."""
    if p.type not in ("AHU", "FCU"):
        return   # chiller/kollektör vanası yoktur; mod kıyası anlamsız
    em = (az.determine_effective_mode(p) or "").upper()
    if "HEAT" in em and r.rule in SOGUTMA_KURALLARI:
        return f"mod ISITMA ama soğutma kuralı {r.rule}"
    if "COOL" in em and r.rule in ISITMA_KURALLARI:
        return f"mod SOGUTMA ama ısıtma kuralı {r.rule}"

def K08(r, p, az, s):
    """Talep yokken (iki vana da kapalı) kritik alarm üretilemez."""
    if p.type not in ("AHU", "FCU") or az._cihaz_calisiyor(p):
        return   # çalışan cihaz (start/basınç) kritik üretebilir
    cv = p.valves.cooling or 0
    hv = p.valves.heating or 0
    if cv < 0.5 and hv < 0.5 and r.severity == "CRITICAL":
        return f"iki vana da kapalı ama KRİTİK: {r.rule}"

def K09(r, p, az, s):
    """Veri eksikliği: yalnızca cihaz ÇALIŞIYORSA kritik olabilir."""
    if r.rule != "MISSING_DATA":
        return
    calisiyor = az._cihaz_calisiyor(p)
    if r.severity == "CRITICAL" and not calisiyor:
        return "cihaz çalışmıyor ama veri eksikliği KRİTİK"
    if r.severity != "CRITICAL" and calisiyor:
        return "cihaz çalışıyor, veri yok ama kritik değil (kör uçuş görünmüyor)"

def K10(r, p, az, s):
    """Üfleme durumu OPTIMAL iken üfleme alarmı olamaz."""
    if r.sat_status == "OPTIMAL" and r.rule in ("SAT_HIGH", "SAT_LOW", "SAT_WARNING"):
        return f"sat_status OPTIMAL ama kural {r.rule}"

def K11(r, p, az, s):
    """Normal satırda kritik dili kullanılamaz (operatörü yanıltır)."""
    if r.rule in SESSIZ_KURALLAR and "KRİTİK" in (r.action or "").upper():
        return f"kural {r.rule} ama eylem metni: {r.action!r}"

def K12(r, p, az, s):
    """Soğutmada önerilen üfleme, emişten sıcak olamaz."""
    em = (az.determine_effective_mode(p) or "").upper()
    ret = p.temperatures.return_ if p.temperatures.return_ is not None else p.temperatures.room
    if "COOL" in em and r.recommended_sat is not None and ret is not None and r.recommended_sat >= ret:
        return f"soğutmada öneri {r.recommended_sat} ≥ emiş {ret}"

def K13(r, p, az, s):
    """Aynı girdi aynı sonucu vermeli (kararlılık)."""
    tekrar = dict(s)
    tekrar["ad"] = None          # temiz geçmişle aynı girdi
    r2, _, _ = _calistir(tekrar)
    if (r2.rule, r2.severity, r2.score) != (r.rule, r.severity, r.score):
        return f"aynı girdi farklı sonuç: {(r.rule, r.severity, r.score)} vs {(r2.rule, r2.severity, r2.score)}"

def K14(r, p, az, s):
    """Kritik bulgunun skoru, uyarı eşiğinin altında kalamaz."""
    if r.severity == "CRITICAL" and r.score is not None and r.score < 6.0:
        return f"KRİTİK ama skor {r.score}"

def K16(r, p, az, s):
    """Skor kritik eşiğin üstündeyse önem de kritik olmalı (K14'ün aynası)."""
    if r.score is not None and r.score >= 7.0 and r.severity != "CRITICAL":
        return f"skor {r.score} ama önem {r.severity} ({r.rule})"


def K15(r, p, az, s):
    """Kural atanmışsa eylem metni boş kalamaz (arayüzde boş satır)."""
    if r.rule and not (r.action or "").strip():
        return f"kural {r.rule} ama eylem metni boş"


KURALLAR = [
    (f.__name__, f.__doc__ or "", f) for f in
    (K01, K02, K03, K04, K05, K06, K07, K08, K09, K10, K11, K12, K13, K14, K15, K16)
]
ACIKLAMA = {
    "K01": "her üretilen kuralın talimat açıklaması vardır",
    "K02": "önem değeri tanımlı kümededir",
    "K03": "NORMAL/IN_BAND/STANDBY satırın önemi OPTIMAL'dir",
    "K04": "skor 0-10 aralığındadır",
    "K05": "normal satırın skoru uyarı eşiğinin altındadır",
    "K06": "hedef ΔT pozitiftir",
    "K07": "mod ile kural çelişmez (ısıtmada soğutma alarmı yok)",
    "K08": "iki vana da kapalıyken kritik alarm üretilmez",
    "K09": "veri eksikken kritik teşhis konulmaz",
    "K10": "üfleme durumu OPTIMAL iken üfleme alarmı olmaz",
    "K11": "normal satırda kritik dili kullanılmaz",
    "K12": "soğutmada önerilen üfleme emişten sıcak olamaz",
    "K13": "aynı girdi aynı sonucu verir",
    "K14": "kritik bulgunun skoru uyarı eşiğinin altında olmaz",
    "K15": "kural atanmışsa eylem metni doludur",
    "K16": "skor kritik eşiğin üstündeyse önem de kritiktir",
}


# ── Karşı örneği sadeleştirme ────────────────────────────────────────────
def _sadelestir(s, kod, fn):
    """Kuralı bozan senaryodan gereksiz alanları çıkarıp en küçük örneği bulur."""
    s = dict(s)
    for alan in ("supply", "inlet", "outlet", "oat", "room", "ret", "sat", "setp",
                 "start", "basinc"):
        if s.get(alan) is None:
            continue
        deneme = dict(s)
        deneme[alan] = None
        try:
            r, p, az = _calistir(deneme)
            if fn(r, p, az, deneme):
                s = deneme
        except Exception:
            pass
    return s


def _yaz(s):
    onemli = {k: v for k, v in s.items() if v is not None}
    return ", ".join(f"{k}={v}" for k, v in onemli.items())


# ── Çalıştır ─────────────────────────────────────────────────────────────
def main():
    rnd = random.Random(TOHUM)
    ihlal = {}          # kod -> (adet, ilk_senaryo, mesaj)
    istisna = []
    print(f"Mekanik Zeka değişmez kural taraması — {SAYI} senaryo, tohum {TOHUM}\n")

    for i in range(SAYI):
        s = _uret(rnd)
        try:
            r, p, az = _calistir(s)
        except Exception as e:
            if len(istisna) < 5:
                istisna.append((type(e).__name__, str(e)[:120], _yaz(s)))
            continue
        for kod, _doc, fn in KURALLAR:
            if kod == "K13" and i % 50:      # kararlılık her senaryoda pahalı
                continue
            try:
                mesaj = fn(r, p, az, s)
            except Exception as e:
                mesaj = f"kural kontrolü çöktü: {type(e).__name__}"
            if mesaj:
                adet, ilk, ilk_mesaj = ihlal.get(kod, (0, None, None))
                ihlal[kod] = (adet + 1, ilk if ilk else s, ilk_mesaj or mesaj)

    print(f"çökme (istisna): {len(istisna)}")
    for ad, msj, gir in istisna:
        print(f"   {ad}: {msj}\n      girdi: {gir}")

    saglam = [k for k, _, _ in KURALLAR if k not in ihlal]
    print(f"\nSAĞLAM değişmez kural: {len(saglam)}/{len(KURALLAR)}")
    for k in saglam:
        print(f"   ✓ {k}  {ACIKLAMA[k]}")

    if ihlal:
        print(f"\nBOZULAN değişmez kural: {len(ihlal)}")
        for kod, _doc, fn in KURALLAR:
            if kod not in ihlal:
                continue
            adet, ornek, mesaj = ihlal[kod]
            kucuk = _sadelestir(ornek, kod, fn)
            try:
                r, p, az = _calistir(kucuk)
                mesaj = fn(r, p, az, kucuk) or mesaj
                sonuc = f"{r.rule} / {r.severity} / skor {r.score}"
            except Exception:
                sonuc = "?"
            oran = 100.0 * adet / SAYI
            print(f"\n   ✗ {kod}  {ACIKLAMA[kod]}")
            print(f"     {adet} senaryoda bozuldu (%{oran:.2f})")
            print(f"     bulgu : {mesaj}")
            print(f"     sonuc : {sonuc}")
            print(f"     girdi : {_yaz(kucuk)}")

    return 0 if (not ihlal and not istisna) else 1


if __name__ == "__main__":
    sys.exit(main())
