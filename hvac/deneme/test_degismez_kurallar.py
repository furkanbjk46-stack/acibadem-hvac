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
# Kuralların TANIMI kural_denetim.py'dedir; motor da (main_portal çıkış
# denetimi) aynı dosyayı kullanır. Böylece testin aradığı kural ile sahada
# uygulanan kural birbirinden ayrılamaz.
import kural_denetim


def _sar(fn):
    """kural_denetim imzasını bu dosyanın (r, p, az, s) imzasına uyarlar."""
    def _ic(r, p, az, s):
        em = az.determine_effective_mode(p)
        if fn in (kural_denetim.K07, kural_denetim.K12):
            return fn(r, p, az, mp.INSTRUCTION_GUIDE, effective_mode=em)
        return fn(r, p, az, mp.INSTRUCTION_GUIDE)
    return _ic


def K13(r, p, az, s):
    """Aynı girdi aynı sonucu vermeli (kararlılık).

    Yalnızca testte vardır: motorun iki kez çalıştırılmasını gerektirir,
    sahada her analizde tekrarlamak gereksiz maliyettir.
    """
    tekrar = dict(s)
    tekrar["ad"] = None          # temiz geçmişle aynı girdi
    r2, _, _ = _calistir(tekrar)
    if (r2.rule, r2.severity, r2.score) != (r.rule, r.severity, r.score):
        return f"aynı girdi farklı sonuç: {(r.rule, r.severity, r.score)} vs {(r2.rule, r2.severity, r2.score)}"


KURALLAR = [(fn.__name__, (fn.__doc__ or "").strip(), _sar(fn))
            for fn in kural_denetim.KURALLAR]
KURALLAR.append(("K13", K13.__doc__.splitlines()[0], K13))
ACIKLAMA = dict(kural_denetim.ACIKLAMA)
ACIKLAMA["K13"] = "aynı girdi aynı sonucu verir"


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
