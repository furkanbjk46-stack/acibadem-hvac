# training_data.py
# Tasarruf önerisi kayıtları ve kullanıcı kararları.
#
# A1 (24.11.2026, tasarruf öğrenme tasarımı):
#   - Her önerinin bir KİMLİĞİ var: kural + rapor dönemi (ör. "EFFICIENCY_INDEX_DROP|2026-02").
#     Aynı ayın raporu kaç kez üretilirse üretilsin öneri TEK kayıttır; tekrar
#     görülmesi yalnız "gorulme" sayacını ve son bağlamı günceller, kararı silmez.
#     Önceden her rapor üretimi yeni kayıt açıyordu: Maslak'ın 31 kaydı aslında
#     8 rapor ayındaki 13 öneriydi; aynı öneriye dakikalar arayla hem "uygulandı"
#     hem "uygulanmadı" denmişti.
#   - Ret için neden zorunlu (sabit liste). Toplu işaretleme ekrandan kalktı.
#   - Eski (kimliksiz) kayıtlar ilk yüklemede tekilleştirilir; özgün dosyanın
#     yedeği yanına bırakılır. Aynı önerinin birden çok kararından EN SONUNCUSU
#     geçerli sayılır, hepsi "karar_gecmisi"nde saklanır.

from __future__ import annotations
import os
import sys as _sys_y
_sys_y.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import yollar  # dosya yolları (ayar/ durum/ veri/; Faz 1)
import json
import logging
import shutil
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger(__name__)

SURUM = 2  # kayıt biçimi: 2 = kimlikli

# Karar durumları
KARAR_DURUMLARI = ("applied", "not_applied", "partially_applied", "pending")

# Ret nedenleri (sabit liste — öğrenme adımı bunlara göre davranacak)
RET_NEDENLERI = {
    "uygulanamaz": "Uygulanamaz (işletme gereği)",
    "zaten_yapiliyor": "Zaten yapılıyor",
    "veri_yanlis": "Veri yanlış / öneri hatalı",
    "diger": "Diğer (not yazın)",
}


def oneri_kimligi(rule_id: str, yil: Optional[int], ay: Optional[int]) -> str:
    """Kural + rapor dönemi. Dönem bilinmiyorsa kimlik çağıran tarafından verilir."""
    return f"{rule_id or 'BILINMIYOR'}|{int(yil):04d}-{int(ay):02d}"


# Eski kayıtların tekilleştirilmesi hafif modülde: heartbeat (cloud_sync) rapor
# paketini (fpdf/matplotlib) yüklemeden kullanabilsin.
from oneri_kimlik import tekillestir, eski_kimlik as _eski_kimlik  # noqa: E402,F401


class TrainingDataCollector:
    """Tasarruf önerisi kayıtları (kimlikli) + kullanıcı kararları."""

    try:
        from location_manager import get_manager as _get_loc_mgr
        DATA_FILE = _get_loc_mgr().get_data_path("ml_training_data.json")
    except Exception as e:
        logging.getLogger(__name__).warning(f"location_manager yüklenemedi, varsayılan yol kullanılıyor: {e}")
        DATA_FILE = yollar.yol("ml_training_data.json",
                               os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def __init__(self, data_file: str = None):
        self.data_file = data_file or self.DATA_FILE
        self.data = self._load_data()

    # ── dosya ────────────────────────────────────────────────────────────
    def _load_data(self) -> List[Dict]:
        """Kayıtları yükle; kimliksiz eski kayıt varsa bir kez tekilleştir."""
        if not os.path.exists(self.data_file):
            return []
        try:
            with open(self.data_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            logger.error(f"Training data yükleme hatası ({self.data_file}): {e}")
            return []
        if not isinstance(data, list):
            return []
        if any(not r.get("kimlik") for r in data):
            yedek = self.data_file.replace(".json", "") + ".kimliksiz_yedek.json"
            try:
                if not os.path.exists(yedek):
                    shutil.copy2(self.data_file, yedek)
                once = len(data)
                data = tekillestir(data)
                self.data = data
                self._save_data()
                logger.info(f"Öneri kayıtları tekilleştirildi: {once} → {len(data)} (yedek: {yedek})")
            except Exception as e:
                logger.error(f"Öneri kayıtları tekilleştirilemedi: {e}")
        return data

    def _save_data(self):
        """Atomik yaz: yarım kalmış dosya kararları silmesin."""
        try:
            gecici = self.data_file + ".tmp"
            with open(gecici, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2, default=str)
            os.replace(gecici, self.data_file)
        except Exception as e:
            logger.error(f"Training data kaydetme hatası ({self.data_file}): {e}")

    def _bul(self, record_id: str) -> Optional[Dict]:
        for r in self.data:
            if r.get("id") == record_id or r.get("kimlik") == record_id:
                return r
        return None

    # ── öneri kaydı ──────────────────────────────────────────────────────
    def save_recommendation_context(self,
                                    recommendation: Dict,
                                    energy_summary: Dict = None,
                                    hvac_summary: Dict = None,
                                    yoy_data: Dict = None,
                                    yil: Optional[int] = None,
                                    ay: Optional[int] = None):
        """Öneriyi kaydet. Aynı kural + aynı dönem zaten varsa YENİ KAYIT AÇMAZ:
        bağlamı tazeler, görülme sayısını artırır, kararı korur.
        Dönemsiz çağrı (yil/ay yok) eski davranışa düşmesin diye günün ayı kullanılır."""
        rule_id = recommendation.get("rule_id")
        if yil is None or ay is None:
            simdi = datetime.now()
            yil, ay = simdi.year, simdi.month
        kimlik = oneri_kimligi(rule_id, yil, ay)
        simdi_iso = datetime.now().isoformat()

        oneri = {
            "rule_id": rule_id,
            "name": recommendation.get("name"),
            "severity": recommendation.get("severity"),
            "category": recommendation.get("category"),
            "savings_potential": recommendation.get("savings_potential"),
            "message": recommendation.get("message"),
        }
        baglam = {
            "energy": self._extract_key_metrics(energy_summary) if energy_summary else {},
            "hvac": self._extract_key_metrics(hvac_summary) if hvac_summary else {},
        }
        yoy = self._extract_yoy_changes(yoy_data) if yoy_data else {}

        mevcut = self._bul(kimlik)
        if mevcut is not None:
            mevcut["recommendation"] = oneri
            mevcut["context"] = baglam
            mevcut["yoy_changes"] = yoy
            mevcut["son_gorulme"] = simdi_iso
            mevcut["gorulme"] = int(mevcut.get("gorulme") or 1) + 1
            self._save_data()
            return mevcut["id"]

        record = {
            "id": f"REC_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{len(self.data)}",
            "kimlik": kimlik,
            "donem": f"{int(yil):04d}-{int(ay):02d}",
            "timestamp": simdi_iso,
            "son_gorulme": simdi_iso,
            "gorulme": 1,
            "recommendation": oneri,
            "context": baglam,
            "yoy_changes": yoy,
            "feedback": None,      # kullanıcı kararı
            "karar_gecmisi": [],
            "outcome": None,       # ölçülen sonuç (A3)
        }
        self.data.append(record)
        self._save_data()
        return record["id"]

    def _extract_key_metrics(self, summary: Dict) -> Dict:
        """Özet verilerden önemli metrikleri çıkar"""
        if not summary:
            return {}
        key_fields = [
            "total_grid_consumption",
            "total_cooling_consumption",
            "total_gas",
            "avg_chiller_set_temp",
            "avg_outdoor_temp",
            "hvac_avg_delta_t",
            "hvac_total_critical",
            "hvac_avg_cooling_pct",
            "hvac_avg_heating_pct",
        ]
        return {k: summary.get(k) for k in key_fields if summary.get(k) is not None}

    def _extract_yoy_changes(self, yoy_data: Dict) -> Dict:
        """YoY değişikliklerini çıkar"""
        if not yoy_data:
            return {}
        comparisons = yoy_data.get("comparisons", {})
        changes = {}
        for metric, data in comparisons.items():
            if data.get("change_percent") is not None:
                changes[metric] = {
                    "current": data.get("current"),
                    "previous": data.get("previous"),
                    "change_pct": data.get("change_percent"),
                    "trend": data.get("trend"),
                    "status": data.get("status"),
                }
        return changes

    # ── karar ────────────────────────────────────────────────────────────
    def update_feedback(self, record_id: str, feedback: str, notes: str = None,
                        neden: str = None) -> bool:
        """Kullanıcı kararını yaz.

        feedback: "applied", "not_applied", "partially_applied", "pending"
        neden:    yalnız "not_applied" için, RET_NEDENLERI anahtarı (zorunlu)
        notes:    serbest not ("diger" nedeninde zorunlu)
        """
        if feedback not in KARAR_DURUMLARI:
            raise ValueError(f"Geçersiz karar: {feedback}")
        if feedback == "not_applied":
            if neden not in RET_NEDENLERI:
                raise ValueError("Ret için neden seçilmeli")
            if neden == "diger" and not (notes or "").strip():
                raise ValueError("'Diğer' nedeni için not yazılmalı")
        else:
            neden = None

        record = self._bul(record_id)
        if record is None:
            return False
        karar = {
            "status": feedback,
            "neden": neden,
            "notes": (notes or "").strip() or None,
            "updated_at": datetime.now().isoformat(),
        }
        record["feedback"] = karar
        record.setdefault("karar_gecmisi", []).append(dict(karar))
        self._save_data()
        return True

    def update_outcome(self, record_id: str,
                       actual_savings: float = None,
                       success: bool = None,
                       notes: str = None):
        """Ölçülen sonucu yaz (A3'te ölçüm modülü dolduracak)."""
        record = self._bul(record_id)
        if record is None:
            return False
        record["outcome"] = {
            "actual_savings": actual_savings,
            "success": success,
            "notes": notes,
            "updated_at": datetime.now().isoformat()
        }
        self._save_data()
        return True

    # ── sorgu ────────────────────────────────────────────────────────────
    def get_pending_feedback(self) -> List[Dict]:
        """Karar bekleyen öneriler: hiç karar verilmemiş ya da "beklet" denmiş.
        Yeni dönem önce gelir."""
        bekleyen = [r for r in self.data
                    if not r.get("feedback") or (r["feedback"].get("status") == "pending")]
        return sorted(bekleyen, key=lambda r: (r.get("donem") or "", r.get("son_gorulme") or ""),
                      reverse=True)

    def get_statistics(self) -> Dict:
        """Öneri ve karar istatistikleri (her öneri bir kez sayılır)."""
        total = len(self.data)
        kararli = [r for r in self.data
                   if r.get("feedback") and r["feedback"].get("status") not in (None, "pending")]
        with_outcome = sum(1 for r in self.data if r.get("outcome"))

        rule_counts: Dict[str, int] = {}
        for r in self.data:
            rule_id = (r.get("recommendation") or {}).get("rule_id", "UNKNOWN")
            rule_counts[rule_id] = rule_counts.get(rule_id, 0) + 1

        durum: Dict[str, int] = {}
        neden: Dict[str, int] = {}
        for r in kararli:
            s = r["feedback"]["status"]
            durum[s] = durum.get(s, 0) + 1
            if s == "not_applied":
                n = r["feedback"].get("neden") or "belirtilmemis"
                neden[n] = neden.get(n, 0) + 1

        return {
            "total_records": total,
            "with_feedback": len(kararli),
            "with_outcome": with_outcome,
            "feedback_rate": (len(kararli) / total * 100) if total > 0 else 0,
            "outcome_rate": (with_outcome / total * 100) if total > 0 else 0,
            "rule_distribution": rule_counts,
            "decision_distribution": durum,
            "reject_reasons": neden,
            "report_runs": sum(int(r.get("gorulme") or 1) for r in self.data),
            "ready_for_ml": total >= 100,
        }
