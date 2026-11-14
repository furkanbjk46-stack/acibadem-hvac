# -*- coding: utf-8 -*-
"""
SAYAÇ VERİSİ — sayac_gunluk (ince tablo, yol haritası D1) okuma yardımcıları
============================================================================

Lokasyon her sayacın günlük değerini ayrı satır olarak gönderir (veritabani/degisiklikler/006):
    lokasyon_id, tarih, sayac, deger, birim, tur
Yeni sayaç merkezde SQL sütunu açılmadan buraya gelir. Lokasyon detayındaki "Sayaçlar" grafiği
bu modülü kullanır. Ağ yok: istemci dışarıdan verilir (testte sahte istemci).
"""
from datetime import date, timedelta

TABLO = "sayac_gunluk"
TUR_ADI = {"trafo": "Trafo", "sebeke": "Şebeke", "uretim": "Üretim (kojen)", "chiller": "Chiller",
           "alt_sayac": "Alt sayaç"}
TUR_SIRA = ["sebeke", "trafo", "uretim", "chiller", "alt_sayac"]


def _sayfali(sorgu_kur, parti=1000, ust=200):
    satirlar = []
    for i in range(ust):
        r = sorgu_kur().range(i * parti, (i + 1) * parti - 1).execute()
        satirlar.extend(r.data or [])
        if len(r.data or []) < parti:
            break
    return satirlar


def sayac_listesi(client, lokasyon_id, bugun=None, gun=40):
    """Son `gun` günde verisi olan sayaçlar: [{"sayac", "tur", "birim"}] (tür, sonra ad sırasıyla).

    Tablo yoksa / erişilemezse [] — grafik seçeneği gösterilmez.
    """
    bas = ((bugun or date.today()) - timedelta(days=gun)).isoformat()
    try:
        satirlar = _sayfali(lambda: client.table(TABLO).select("sayac,tur,birim")
                            .eq("lokasyon_id", lokasyon_id).gte("tarih", bas))
    except Exception:
        return []
    tekil = {}
    for s in satirlar:
        tekil.setdefault(s.get("sayac"), {"sayac": s.get("sayac"), "tur": s.get("tur") or "alt_sayac",
                                          "birim": s.get("birim") or "kWh"})
    return sorted((v for k, v in tekil.items() if k),
                  key=lambda v: (TUR_SIRA.index(v["tur"]) if v["tur"] in TUR_SIRA else 99, _dogal(v["sayac"])))


def _dogal(ad):
    """MCC-2 < MCC-10."""
    import re
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", str(ad))]


def gunluk_degerler(client, lokasyon_id, sayaclar, bas, bit):
    """{sayac: {tarih(str): deger}} — yalnız seçilen sayaçlar ve tarih aralığı."""
    if not sayaclar:
        return {}
    try:
        satirlar = _sayfali(lambda: client.table(TABLO).select("tarih,sayac,deger")
                            .eq("lokasyon_id", lokasyon_id).in_("sayac", list(sayaclar))
                            .gte("tarih", str(bas)).lte("tarih", str(bit)).order("tarih"))
    except Exception:
        return {}
    sonuc = {s: {} for s in sayaclar}
    for r in satirlar:
        if r.get("sayac") in sonuc and r.get("deger") is not None:
            sonuc[r["sayac"]][str(r["tarih"])[:10]] = float(r["deger"])
    return sonuc


def varsayilan_secim(liste, en_cok=6):
    """İlk açılışta gösterilecek sayaçlar: ilk türün sayaçları (en çok `en_cok`)."""
    if not liste:
        return []
    ilk = liste[0]["tur"]
    return [s["sayac"] for s in liste if s["tur"] == ilk][:en_cok]


def ozet(degerler):
    """[(sayac, toplam, gun_sayisi)] — tablo / başlık için."""
    return [(s, sum(g.values()), len(g)) for s, g in degerler.items()]
