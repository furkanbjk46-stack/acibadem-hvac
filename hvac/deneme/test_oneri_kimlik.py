# -*- coding: utf-8 -*-
"""Tasarruf önerisi kimliği ve kararlar (A1, 24.11.2026).

    python hvac/deneme/test_oneri_kimlik.py

Neden var: aylık rapor her üretildiğinde öneriler yeniden kaydediliyordu. Maslak'ın
31 "geri bildirimi" aslında 8 rapor ayındaki 13 öneriydi; aynı öneriye dakikalar
arayla hem "uygulandı" hem "uygulanmadı" denmişti. Sayılar bu yüzden hiçbir şey
ifade etmiyordu. Bu test:
  1) aynı kural + aynı dönem için tek kayıt tutulduğunu,
  2) ret için neden zorunlu olduğunu,
  3) eski kimliksiz dosyanın yedeklenip doğru tekilleştirildiğini,
  4) heartbeat özetinin tekilleşmiş sayıları gönderdiğini,
  5) ekranda toplu işaretlemenin kalmadığını
doğrular.
"""
import json
import os
import shutil
import sys
import tempfile

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import logging
logging.disable(logging.CRITICAL)

from monthly_report.training_data import TrainingDataCollector, RET_NEDENLERI
from oneri_kimlik import tekillestir

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


def oku(yol):
    with open(yol, encoding="utf-8") as f:
        return json.load(f)


GEC = tempfile.mkdtemp(prefix="oneri_")
try:
    # ── 1) Aynı kural + aynı dönem = tek kayıt ───────────────────────────
    yol = os.path.join(GEC, "ml_training_data.json")
    col = TrainingDataCollector(yol)
    oneri = {"rule_id": "EFFICIENCY_INDEX_DROP", "name": "Verimlilik", "severity": "WARNING",
             "message": "m1"}
    ozet = {"total_grid_consumption": 100.0}
    id1 = col.save_recommendation_context(oneri, ozet, {}, None, yil=2026, ay=2)
    id2 = col.save_recommendation_context(oneri, {"total_grid_consumption": 110.0}, {}, None, yil=2026, ay=2)
    id3 = col.save_recommendation_context(oneri, ozet, {}, None, yil=2026, ay=2)
    c("aynı ay raporu 3 kez üretilince tek kayıt", len(col.data) == 1, len(col.data))
    c("tekrar üretim aynı id'yi döner", id1 == id2 == id3, (id1, id2, id3))
    c("görülme sayısı artar", col.data[0].get("gorulme") == 3, col.data[0].get("gorulme"))
    c("son bağlam tutulur", col.data[0]["context"]["energy"]["total_grid_consumption"] == 100.0)
    c("kimlik kural|dönem", col.data[0]["kimlik"] == "EFFICIENCY_INDEX_DROP|2026-02", col.data[0]["kimlik"])
    c("öneri metni kaydedilir", col.data[0]["recommendation"].get("message") == "m1")

    col.save_recommendation_context(oneri, ozet, {}, None, yil=2026, ay=3)
    c("başka ay ayrı öneri", len(col.data) == 2, len(col.data))

    # Karar, rapor tekrar üretilince silinmez
    col.update_feedback(id1, "applied")
    col.save_recommendation_context(oneri, ozet, {}, None, yil=2026, ay=2)
    c("karar rapor tekrarında korunur", col.data[0]["feedback"]["status"] == "applied")
    c("dosyadan yeniden okununca da 2 kayıt", len(TrainingDataCollector(yol).data) == 2)

    # ── 2) Ret nedeni zorunlu ────────────────────────────────────────────
    id_mart = col.data[1]["id"]
    for ad, kw in (("nedensiz ret reddedilir", {"feedback": "not_applied"}),
                   ("'diğer' notsuz reddedilir", {"feedback": "not_applied", "neden": "diger"}),
                   ("geçersiz karar reddedilir", {"feedback": "uydurma"})):
        try:
            col.update_feedback(id_mart, **kw)
            c(ad, False)
        except ValueError:
            c(ad, True)
    c("ret nedeni ile kaydedilir", col.update_feedback(id_mart, "not_applied", neden="zaten_yapiliyor"))
    c("neden saklanır", col.data[1]["feedback"]["neden"] == "zaten_yapiliyor")
    col.update_feedback(id_mart, "applied")
    c("karar geçmişi tutulur", len(col.data[1]["karar_gecmisi"]) == 2)
    c("uygulandı kararında neden boş", col.data[1]["feedback"]["neden"] is None)
    st = col.get_statistics()
    c("istatistik öneri başına", st["total_records"] == 2 and st["with_feedback"] == 2, st)
    c("rapor üretim sayısı ayrı tutulur", st["report_runs"] == 5, st["report_runs"])
    c("ret nedenleri sabit listede 4 madde",
      set(RET_NEDENLERI) == {"uygulanamaz", "zaten_yapiliyor", "veri_yanlis", "diger"})

    col.update_feedback(id1, "pending")
    c("bekletilen öneri karar bekleyenlerde kalır",
      any(r["id"] == id1 for r in col.get_pending_feedback()))

    # ── 3) Eski kimliksiz dosya: yedek + tekilleştirme ───────────────────
    def eski(i, kural, grid, ts, durum, upd):
        return {"id": f"REC_{i}", "timestamp": ts,
                "recommendation": {"rule_id": kural, "name": kural},
                "context": {"energy": {"total_grid_consumption": grid, "total_cooling_consumption": 5,
                                       "avg_outdoor_temp": 9.7}},
                "feedback": {"status": durum, "notes": None, "updated_at": upd} if durum else None,
                "outcome": None}
    eskiler = [
        eski(0, "EFF", 945200.0, "2026-02-05T22:53", "applied", "2026-02-05T23:02"),
        eski(1, "EFF", 945200.0, "2026-02-05T23:07", "not_applied", "2026-02-05T23:09"),
        eski(2, "EFF", 945200.0, "2026-02-05T23:10", "applied", "2026-02-05T23:12"),
        eski(3, "EFF", 945200.0, "2026-09-24T10:26", "not_applied", "2026-10-02T09:15"),
        eski(4, "EFF", 735625.0, "2026-03-02T11:34", "not_applied", "2026-03-02T11:36"),
        eski(5, "SET", 945200.0, "2026-02-05T22:53", None, None),
    ]
    yol2 = os.path.join(GEC, "eski.json")
    with open(yol2, "w", encoding="utf-8") as f:
        json.dump(eskiler, f)
    col2 = TrainingDataCollector(yol2)
    yedek = os.path.join(GEC, "eski.kimliksiz_yedek.json")
    c("6 eski kayıt 3 öneriye iner", len(col2.data) == 3, len(col2.data))
    c("özgün dosyanın yedeği bırakılır", os.path.exists(yedek))
    c("yedek özgün 6 kaydı taşır", os.path.exists(yedek) and len(oku(yedek)) == 6)
    feb = [r for r in col2.data if r["recommendation"]["rule_id"] == "EFF" and r["gorulme"] == 4]
    c("şubat EFF 4 kaydı birleşti", len(feb) == 1)
    if feb:
        c("en son karar geçerli (02.10 ret)", feb[0]["feedback"]["status"] == "not_applied"
          and feb[0]["feedback"]["updated_at"].startswith("2026-10-02"), feb[0]["feedback"])
        c("tüm kararlar geçmişte", len(feb[0]["karar_gecmisi"]) == 4)
        c("ilk görülme korunur", feb[0]["timestamp"] == "2026-02-05T22:53")
        c("birleşen id'ler saklanır", feb[0]["birlesen_kayitlar"] == ["REC_0", "REC_1", "REC_2", "REC_3"])
    c("kararsız eski kayıt bekleyenlerde",
      any(r["recommendation"]["rule_id"] == "SET" for r in col2.get_pending_feedback()))
    c("tekilleşmiş dosyada kimliksiz kayıt kalmaz", all(r.get("kimlik") for r in oku(yol2)))
    c("tekilleştirme ikinci kez çalışınca değişmez", tekillestir(col2.data) == col2.data)
    # Yeniden açılınca yedek üzerine yazılmaz, veri değişmez
    c("ikinci açılış veriyi değiştirmez", TrainingDataCollector(yol2).data == col2.data)

    # Saha kopyası (Maslak 06.10.2026) varsa: 31 → 13 olmalı
    saha = os.path.join(BURASI, "..", "..", "_saha_deneme", "veri", "ml_training_data.json")
    if os.path.exists(saha):
        _s = oku(saha)
        if len(_s) == 31 and not any(r.get("kimlik") for r in _s):
            c("Maslak kopyası: 31 kayıt 13 öneriye iner", len(tekillestir(_s)) == 13, len(tekillestir(_s)))

    # ── 4) Heartbeat özeti tekilleşmiş sayar, dosyaya dokunmaz ───────────
    yol3 = os.path.join(GEC, "hb.json")
    with open(yol3, "w", encoding="utf-8") as f:
        json.dump(eskiler, f)
    import cloud_sync

    class _SahteLM:
        @staticmethod
        def get_manager():
            class _M:
                @staticmethod
                def get_data_path(ad):
                    return yol3
            return _M()
    _eski_lm = sys.modules.get("location_manager")
    sys.modules["location_manager"] = _SahteLM
    try:
        o = cloud_sync._geri_bildirim_ozet()
    finally:
        if _eski_lm is not None:
            sys.modules["location_manager"] = _eski_lm
        else:
            sys.modules.pop("location_manager", None)
    c("heartbeat eski dosyayı tekilleşmiş sayar", o.get("kayit") == 3 and o.get("geri_bildirim") == 2, o)
    c("heartbeat dosyayı değiştirmez", len(oku(yol3)) == 6)
    c("heartbeat ret nedenlerini taşır", o.get("red_nedeni") == {"belirtilmemis": 2}, o.get("red_nedeni"))
    _cs = open(os.path.join(BURASI, "cloud_sync.py"), encoding="utf-8").read()
    _fn = _cs.split("def _geri_bildirim_ozet")[1].split("\ndef ")[0]
    c("heartbeat rapor paketini yüklemez",
      "from oneri_kimlik import tekillestir" in _fn and "monthly_report" not in _fn)

    # ── 5) Ekranda toplu işaretleme yok ──────────────────────────────────
    _ap = open(os.path.join(BURASI, "app_portal.py"), encoding="utf-8").read()
    _bolum = _ap.split('"kart_ml_egitim"')[1].split("# ---------------- TAB 6")[0]
    c("'Tümünü Seç' kalktı", "Tümünü Seç" not in _bolum and "selected_feedbacks" not in _bolum)
    c("ret nedeni seçimi var", "RET_NEDENLERI" in _bolum and "neden=_neden" in _bolum)
    _se = open(os.path.join(BURASI, "monthly_report", "savings_engine.py"), encoding="utf-8").read()
    c("öneri motoru rapor dönemini geçirir", 'ay=unified_data.get("month")' in _se)
finally:
    shutil.rmtree(GEC, ignore_errors=True)

basarili = sum(1 for _, k, _ in T if k)
for ad, k, d in T:
    print(("  OK  " if k else "  HATA") + f"  {ad}" + ("" if k else f"  → {d}"))
print(f"\n{basarili}/{len(T)} geçti")
sys.exit(0 if basarili == len(T) else 1)
