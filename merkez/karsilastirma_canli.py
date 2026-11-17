# -*- coding: utf-8 -*-
"""
KARŞILAŞTIRMA SAYFASI — "CANLI" GÖRÜNÜMÜ
========================================

Global Özet detay sayfasında (pages/ozet_karsilastirma.py ve sunum sürümü)
dönemlerin yanındaki "Canlı" seçeneği: lokasyonlar alt alta, anlık kW ve
ölçüm yaşı. karsilastirma_panel.py'den AYRI tutulur: o modül lokasyon detay
penceresinin gövdesidir ve pencere canlı veri göstermez (test_canli_izleme).

HTML üreten fonksiyonlar streamlit'e dokunmaz, doğrudan test edilebilir.
"""

from karsilastirma_panel import kutu, tr


# ── Satırlar (saf) ────────────────────────────────────────────────
# Karşılaştırma sayfasında dönemlerin yanındaki "Canlı" seçeneği. Değerler
# HESAPLANMAZ: app_merkez.canli_ozet_hesapla çıktısı (ana ekran kartlarının
# kullandığı sözlük) olduğu gibi okunur. Ham satırlar (fetch_canli_tum) yalnız
# taze ölçümü olmayan lokasyonun "son ölçüm ne zaman" bilgisi için kullanılır.
def canli_satirlari(canli, ham, hastaneler, alan="enerji", simdi=None):
    """[{id, ad, renk, kw, yas, eski_sayac, durum}] — ana ekranla aynı sıra
    (en çok çekenden aza, canlı değeri olmayan sonda).

    durum: "canli"     → taze ölçüm var, kw dolu
           "olcum_yok" → lokasyonun taze satırı var ama bu kalemin sayacı yok
           "eski"      → canli_guc'ta satırı var, hiçbiri taze değil
           "kurulmadi" → canli_guc'ta hiç satırı yok
    """
    import canli_izleme as _ci
    ham_lok = {}
    for s in ham or []:
        lid = s.get("lokasyon_id")
        if lid:
            ham_lok.setdefault(lid, []).append(s)
    satirlar = []
    for lid, bilgi in (hastaneler or {}).items():
        o = (canli or {}).get(lid)
        kw = o.get(alan) if o else None
        if o:
            durum = "canli" if kw is not None else "olcum_yok"
            yas, eski = o.get("yas"), o.get("eski_sayac") or 0
        elif lid in ham_lok:
            _y = [y for y in _ci.olcum_yaslari(ham_lok[lid], simdi).values() if y is not None]
            durum, yas, eski = "eski", (min(_y) if _y else None), len(ham_lok[lid])
        else:
            durum, yas, eski = "kurulmadi", None, 0
        satirlar.append({"id": lid, "ad": bilgi.get("kisa", lid), "renk": bilgi.get("renk", "#2a78d6"),
                         "kw": kw, "yas": yas, "eski_sayac": eski, "durum": durum})
    satirlar.sort(key=lambda r: (r["kw"] is not None, r["kw"] or 0), reverse=True)
    return satirlar


_CANLI_DURUM = {   # durum → (etiket, renk)
    "canli": ("CANLI", "#0ca30c"),
    "olcum_yok": ("ÖLÇÜM YOK", "#6b7280"),
    "eski": ("ESKİ ÖLÇÜM", "#c98500"),
    "kurulmadi": ("KURULMADI", "#6b7280"),
}


def canli_durum_metni(r):
    """Satırın sağındaki kısa açıklama: yaş ve (varsa) eski sayaç notu."""
    import canli_izleme as _ci
    d = r["durum"]
    if d == "kurulmadi":
        return "canlı sayaç bağlı değil"
    if d == "eski":
        return ("son ölçüm " + _ci.yas_metni(r["yas"])) if r["yas"] is not None \
            else "ölçüm zamanı okunamadı"
    m = _ci.yas_metni(r["yas"])
    if d == "olcum_yok":
        m = ("enerji sayacı yok · " + m) if m else "enerji sayacı yok"
    if r["eski_sayac"]:
        m += f" · {r['eski_sayac']} sayaç eski, toplama girmedi"
    return m


def canli_liste_html(satirlar):
    """Lokasyonlar alt alta: sıra, ad, anlık kW, durum + yaş."""
    parcalar = []
    for i, r in enumerate(satirlar, 1):
        etiket, drenk = _CANLI_DURUM.get(r["durum"], ("—", "#6b7280"))
        deger = tr(r["kw"]) if r["kw"] is not None else "—"
        sira = f"#{i}" if r["kw"] is not None else ""
        parcalar.append(
            f"<div style='display:grid;grid-template-columns:34px minmax(0,1fr) auto;gap:10px;"
            f"align-items:center;padding:9px 12px;border-bottom:1px solid rgba(19,50,115,0.08);'>"
            f"<span style='font-size:10px;color:#46536b;font-weight:700;'>{sira}</span>"
            f"<div style='min-width:0;'>"
            f"<div style='font-size:12px;font-weight:700;color:{r['renk']};letter-spacing:1px;"
            f"white-space:nowrap;overflow:hidden;text-overflow:ellipsis;'>{r['ad']}</div>"
            f"<div style='font-size:10px;color:#46536b;'>"
            f"<span style='color:{drenk};font-weight:600;'>{etiket}</span>"
            f" · {canli_durum_metni(r)}</div></div>"
            f"<div style='text-align:right;white-space:nowrap;'>"
            f"<span style='font-family:Inter,system-ui,-apple-system,Segoe UI,sans-serif;font-size:18px;"
            f"font-weight:800;color:{r['renk'] if r['kw'] is not None else '#9aa3b2'};'>{deger}</span>"
            f" <span style='font-size:9px;color:#46536b;'>kW</span></div></div>")
    return ("<div style='background:#fafaf8;border:1px solid rgba(24,26,30,0.10);border-radius:14px;"
            "overflow:hidden;'>" + "".join(parcalar) + "</div>")


def canli_bolum(st, ham, canli, hastaneler, alan, tazele_sn, bayat_sn):
    """Canlı görünümün tamamı (toplam kutusu + liste + not). Canlı ve demo
    sayfası bunu kendi zamanlı parçasının (st.fragment) içinden çağırır."""
    sat = canli_satirlari(canli, ham, hastaneler, alan)
    olcen = [r for r in sat if r["kw"] is not None]
    st.markdown(
        "<div style='display:flex;gap:8px;flex-wrap:wrap;margin-bottom:14px;'>"
        + kutu("Σ", "ANLIK TOPLAM", (tr(sum(r["kw"] for r in olcen)) + " kW") if olcen else "—",
               f"{len(olcen)}/{len(sat)} lokasyonda canlı ölçüm")
        + "</div>" + canli_liste_html(sat), unsafe_allow_html=True)
    st.caption(f"Kaynak: canlı sayaç ölçümleri · {tazele_sn} sn'de bir yenilenir · "
               f"{bayat_sn} sn'den eski ölçüm toplama girmez")
    return sat
