# -*- coding: utf-8 -*-
"""Tasarruf önerisi kimliği — eski (kimliksiz) kayıtların tekilleştirilmesi.

A1 (24.11.2026). Bu modül bilerek bağımlılıksızdır: hem monthly_report/training_data
hem de heartbeat (cloud_sync) kullanır; heartbeat rapor paketini yüklememeli.
"""
import hashlib
from typing import Dict, List


def eski_kimlik(rec: Dict) -> str:
    """Kimliksiz eski kayıt: dönem yazılmamış. Aynı ayın raporu aynı enerji
    toplamlarını taşıdığı için bağlamın parmak izi dönem yerine geçer."""
    e = (rec.get("context") or {}).get("energy") or {}
    iz = "|".join(str(e.get(k)) for k in ("total_grid_consumption", "total_cooling_consumption",
                                            "avg_outdoor_temp"))
    ozet = hashlib.sha1(iz.encode("utf-8")).hexdigest()[:8]
    kural = (rec.get("recommendation") or {}).get("rule_id") or "BILINMIYOR"
    return f"{kural}|eski-{ozet}"


def tekillestir(kayitlar: List[Dict]) -> List[Dict]:
    """Eski biçimdeki (kimliksiz) kayıtları kimlik başına tek kayda indirir.
    Kimlikli kayıtlara dokunmaz. Sıra: ilk görülme zamanı."""
    gruplar: Dict[str, List[Dict]] = {}
    sira: List[str] = []
    for r in kayitlar:
        k = r.get("kimlik") or eski_kimlik(r)
        if k not in gruplar:
            gruplar[k] = []
            sira.append(k)
        gruplar[k].append(r)

    sonuc = []
    for k in sira:
        rs = gruplar[k]
        if len(rs) == 1 and rs[0].get("kimlik"):
            sonuc.append(rs[0])
            continue
        rs = sorted(rs, key=lambda r: r.get("timestamp") or "")
        ilk, son = rs[0], rs[-1]
        gecmis = []
        for r in rs:
            gecmis.extend(r.get("karar_gecmisi") or [])
            fb = r.get("feedback")
            if fb and fb.get("status") and not r.get("karar_gecmisi"):
                gecmis.append(dict(fb))
        gecmis.sort(key=lambda f: f.get("updated_at") or "")
        yeni = dict(son)
        yeni["id"] = ilk.get("id")
        yeni["kimlik"] = k
        yeni["donem"] = ilk.get("donem")
        yeni["timestamp"] = ilk.get("timestamp")
        yeni["son_gorulme"] = son.get("son_gorulme") or son.get("timestamp")
        yeni["gorulme"] = sum(int(r.get("gorulme") or 1) for r in rs)
        yeni["feedback"] = dict(gecmis[-1]) if gecmis else None
        yeni["karar_gecmisi"] = gecmis
        yeni["birlesen_kayitlar"] = [r.get("id") for r in rs] if len(rs) > 1 else []
        yeni.setdefault("outcome", None)
        sonuc.append(yeni)
    return sonuc
