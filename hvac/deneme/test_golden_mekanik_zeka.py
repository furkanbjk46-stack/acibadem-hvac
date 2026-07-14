# -*- coding: utf-8 -*-
# test_golden_mekanik_zeka.py — SAĞLAMLAŞTIRMA FAZ 6
#
# 13.07 tarihli iki analiz Excel'inden türetilmiş, girdi→beklenen çıktı sabitlenmiş
# 14 golden vaka. Her kod/config değişikliğinden sonra koşulur:
#   python test_golden_mekanik_zeka.py        (assert tabanlı, pytest gerekmez)
#   python -m pytest test_golden_mekanik_zeka.py -v   (pytest varsa)
# 14 vaka yeşil olmadan YAYIN YOK.

import sys
import os
import json
import tempfile
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import logging
logging.disable(logging.CRITICAL)

import on_kosul as ok
import main_portal as mp

# ── Test izolasyonu: on_kosul geçici dosyalarla, bakım kartı boş ──
_tmp = tempfile.mkdtemp(prefix="golden_")
ok.DURUM_FILE = os.path.join(_tmp, "durum.json")
ok.CARDS_FILE = os.path.join(_tmp, "cards.json")
ok.AUDIT_FILE = os.path.join(_tmp, "audit.jsonl")
mp.get_maintenance_card = lambda n, loc=None: {}

az = mp.HVACAnalyzer()


def _prof(name="Ahu-G", lok="MAS-1", mode="COOLING", start=None, pa=None, **kw):
    t = mp.TemperatureData(
        sat=kw.get("sat"), supply=kw.get("supply"), return_=kw.get("ret"),
        room=kw.get("room"), setpoint=kw.get("setp"),
        inlet=kw.get("inlet"), outlet=kw.get("outlet"),
        plant_supply=kw.get("ps"), plant_return=kw.get("pr"),
    )
    v = mp.ValveData(cooling=kw.get("cv"), heating=kw.get("hv", 0))
    p = mp.EquipmentProfile(type="AHU", name=name, location=lok, mode=mode,
                            temperatures=t, valves=v)
    p.start_stop = start
    p.pressure_pa = pa
    return p


def _analiz(p):
    return az.analyze_equipment(p, None, None, None, 1.0, 3.0)


def _kart(ad):
    try:
        return json.load(open(ok.CARDS_FILE, encoding="utf-8"))["cards"].get(ad, {})
    except Exception:
        return {}


# ═══════════════ GOLDEN VAKALAR ═══════════════

def test_G1_eksik_emis_not_cooling_uretmez():
    """G1: üfleme hedef üstü, emiş YOK, vana %100 → NOT_COOLING DEĞİL; VERI_EKSIK."""
    r = _analiz(_prof(name="G1", sat=20.0, ret=None, setp=22.0, cv=100))
    assert r.rule != "NOT_COOLING", f"G1: NOT_COOLING üretilmemeli (rule={r.rule})"
    assert r.rule == "VERI_EKSIK" and r.severity == "WARNING", f"G1: VERI_EKSIK bekleniyordu ({r.rule}/{r.severity})"


def test_G2_arizali_emis_analiz_yok_kart_isareti():
    """G2: emiş 0.17°C (aralık dışı) + start verisi → analiz atlanır, return_sensor FAULTY."""
    for _ in range(2):  # debounce
        r = _analiz(_prof(name="G2", start=1.0, pa=300.0, sat=20.0, ret=0.17, setp=20.0, cv=80))
    assert r.rule == "SKIP_SENSOR_ARIZA", f"G2: SKIP bekleniyordu ({r.rule})"
    assert _kart("MAS-1 G2").get("return_sensor") == "FAULTY", "G2: return_sensor FAULTY işareti yok"


def test_G3_comfort_coil_kritigini_maskeleyemez():
    """G3: coil etkisiz (approach yüksek) + oda-set sapması >3 → COOL_EFF_LOW kazanır."""
    r = _analiz(_prof(name="G3", sat=23.1, ret=26.7, room=26.7, setp=21.0, cv=100, inlet=8.0, outlet=13.0))
    assert r.rule == "COOL_EFF_LOW", f"G3: COOL_EFF_LOW bekleniyordu, comfort maskeledi mi? ({r.rule})"
    assert r.severity == "CRITICAL"


def test_G4_ters_dt_negatif_raporlanir():
    """G4: soğutmada üfleme 33.9 > emiş 26.6 → TERS_DT/NOT_COOLING + ΔT NEGATİF."""
    r = _analiz(_prof(name="G4", sat=33.9, ret=26.6, setp=23.0, cv=100))
    assert r.rule in ("TERS_DT", "NOT_COOLING"), f"G4: kritik ters-çalışma bekleniyordu ({r.rule})"
    assert r.severity == "CRITICAL"
    assert r.delta_t is not None and r.delta_t < 0, f"G4: ΔT negatif raporlanmalı ({r.delta_t})"


def test_G5_dinamik_hedef_sahte_critical_uretmez():
    """G5: üfleme 15.3 / emiş 21.7 (15:39'un 6'lı sahte CRITICAL grubu) →
    dinamik hedef ≈ 5.2 → NORMAL (eski sabit hedef 10.5 ile CRITICAL LOW_DT oluyordu)."""
    r = _analiz(_prof(name="G5", sat=15.3, ret=21.7, setp=16.0, cv=100))
    assert r.rule not in ("LOW_DT", "LOW_DT_SYNDROME"), f"G5: sahte LOW_DT ({r.rule})"
    assert r.severity != "CRITICAL", f"G5: CRITICAL olmamalı ({r.severity}/{r.rule})"
    assert 4.0 <= r.target_delta_t <= 8.0, f"G5: dinamik hedef 4-8 bandında olmalı ({r.target_delta_t})"


def test_G6_plant_fallback_ahu_da_yasak():
    """G6: emiş yok, plant ΔT 1.85 mevcut → AHU'da plant ΔT kullanılmaz,
    LOW_DT_SYNDROME üretilmez."""
    r = _analiz(_prof(name="G6", sat=17.0, ret=None, setp=17.0, cv=100, ps=7.0, pr=8.85))
    assert r.rule != "LOW_DT_SYNDROME", f"G6: plant ΔT ile LOW_DT_SYNDROME üretilmemeli ({r.rule})"
    assert "Plant" not in (r.dt_source or ""), f"G6: ΔT kaynağı plant olamaz ({r.dt_source})"


def test_G7_stop_basincli_lokal_calisma():
    """G7: start=STOP, basınç 45 Pa → LOKAL_CALISMA bulgusu + analiz yapılır."""
    r = None
    for _ in range(2):
        r = _analiz(_prof(name="G7", start=0.0, pa=45.0, sat=16.5, ret=22.0, setp=16.5, cv=60))
    assert r.rule != "SKIP_STOP", "G7: analiz yapılmalıydı"
    assert r.rule == "LOKAL_CALISMA" or "LOKAL" in (r.reason or ""), f"G7: LOKAL_CALISMA izi yok ({r.rule}/{r.reason})"


def test_G8_fan_basmiyor():
    """G8: start=START, basınç 5 Pa (2 ardışık) → FAN_BASMIYOR (CRITICAL 9.5)."""
    r = None
    for _ in range(2):
        r = _analiz(_prof(name="G8", start=1.0, pa=5.0, sat=17.0, ret=24.0, setp=22.0, cv=80))
    assert r.rule == "FAN_BASMIYOR", f"G8: FAN_BASMIYOR bekleniyordu ({r.rule})"
    assert r.severity == "CRITICAL" and r.score >= 9.5


def test_G9_basinc_sensor_arizasi():
    """G9: start=START, basınç 0 Pa → SKIP + pressure_sensor FAULTY işareti."""
    r = None
    for _ in range(2):
        r = _analiz(_prof(name="G9", start=1.0, pa=0.0, sat=17.0, ret=24.0, setp=22.0, cv=80))
    assert r.rule == "SKIP_BASINC_SENSOR_ARIZA", f"G9: ({r.rule})"
    assert _kart("MAS-1 G9").get("pressure_sensor") == "FAULTY", "G9: pressure_sensor işareti yok"


def test_G10_elle_susturma_24s_sonra_geri_gelir():
    """G10: SİSTEM FAULTY → personel elle OK → 24s susturma → süre dolunca
    sensör hâlâ arızalıysa FAULTY otomatik geri gelir + history kaydı."""
    ok.sistem_isaret_koy("G10", "supply_sensor", "aralık dışı 0.0")
    ok.elle_ok_suppress("G10", "supply_sensor", "Personel")
    d = json.load(open(ok.CARDS_FILE, encoding="utf-8"))
    meta = d["cards"]["G10"]["supply_sensor_meta"]
    assert meta["suppressed_until"], "G10: susturma yazılmadı"
    assert ok.sistem_isaret_koy("G10", "supply_sensor", "hâlâ 0") is False, "G10: susturma sırasında yazmamalı"
    # süreyi geçmişe çek → geri gelmeli
    meta["suppressed_until"] = (datetime.datetime.now() - datetime.timedelta(hours=1)).isoformat(timespec="seconds")
    d["cards"]["G10"]["supply_sensor"] = "OK"
    json.dump(d, open(ok.CARDS_FILE, "w", encoding="utf-8"))
    assert ok.sistem_isaret_koy("G10", "supply_sensor", "hâlâ 0") is True, "G10: süre dolunca geri gelmedi"
    hist = _kart("G10")["supply_sensor_meta"]["history"]
    assert len(hist) >= 3, "G10: history eksik"


def test_G11_config_governance_reddeder():
    """G11: TARGET_AIR_DT_AHU_COOL=10 → doğrulama reddeder (limit 4-8)."""
    hatalar = mp.config_dogrula({**mp.CONFIG, "TARGET_AIR_DT_AHU_COOL": 10})
    assert hatalar and "TARGET_AIR_DT_AHU_COOL" in hatalar[0], f"G11: reddedilmedi ({hatalar})"
    # Eski çift anahtar da reddedilir (S7)
    assert mp.config_dogrula({**mp.CONFIG, "TARGET_DT_AHU": 5}), "G11: eski anahtar reddedilmeli"


def test_G12_tutarsiz_sat_onerisi_bosaltilir():
    """G12: soğutmada önerilen SAT 27°C (emiş 25.4) → öneri boşaltılır + not."""
    r = mp.AnalysisResult()
    r.recommended_sat = 27.0
    p = _prof(name="G12", ret=25.4, sat=20.0, setp=22.0, cv=80)
    r = az.tutarlilik_kontrol(r, p, "COOLING")
    assert r.recommended_sat is None, "G12: tutarsız öneri boşaltılmadı"
    assert "tutarsız" in r.reason.lower() or "Öneri" in r.reason, "G12: not düşülmedi"


def test_G13_stop_santralde_arizali_ufleme_isareti():
    """G13: STOP santral, üfleme 0.04 (2 ardışık) → satır analiz dışı (ΔT çöpü yok)
    + supply_sensor arıza işareti (karar-bağımsız aralık kontrolü)."""
    r = None
    for _ in range(2):
        r = _analiz(_prof(name="G13", start=0.0, pa=2.0, sat=0.04, ret=22.0, setp=22.0, cv=0))
    assert r.rule == "SKIP_STOP", f"G13: ({r.rule})"
    assert r.delta_t is None, f"G13: ΔT boş olmalı ({r.delta_t})"
    assert _kart("MAS-1 G13").get("supply_sensor") == "FAULTY", "G13: supply_sensor işareti yok"


def test_G14_takili_sensor():
    """G14: üfleme 12 okuma boyunca sabit 21.34 → TAKILI SENSÖR işareti."""
    for _ in range(12):
        _analiz(_prof(name="G14", start=1.0, pa=300.0, sat=21.34, ret=24.0, setp=22.0, cv=60))
    kart = _kart("MAS-1 G14")
    assert kart.get("supply_sensor") == "FAULTY", "G14: takılı sensör işareti yok"
    assert "TAKILI" in (kart.get("supply_sensor_meta") or {}).get("auto_reason", ""), "G14: neden TAKILI değil"


# ═══════════════ ÇALIŞTIRICI (pytest'siz) ═══════════════
if __name__ == "__main__":
    vakalar = [v for ad, v in sorted(globals().items()) if ad.startswith("test_G")]
    gecen, kalan = 0, []
    for v in vakalar:
        try:
            v()
            gecen += 1
            print(f"PASS  {v.__name__}")
        except AssertionError as e:
            kalan.append((v.__name__, str(e)))
            print(f"FAIL  {v.__name__}: {e}")
        except Exception as e:
            kalan.append((v.__name__, f"HATA: {e}"))
            print(f"ERROR {v.__name__}: {e}")
    print(f"\n===== GOLDEN: {gecen}/{len(vakalar)} PASS =====")
    if kalan:
        sys.exit(1)
