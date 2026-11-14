# -*- coding: utf-8 -*-
"""Lisans talebi (008): lisansı olmayan PC talep bırakır, watchdog / kurulum onayı bekler. Ağ yok."""
import os
import sys

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import logging  # noqa: E402
logging.disable(logging.CRITICAL)
import lisans as L  # noqa: E402
import portal_watchdog as W  # noqa: E402
import kurulum_kontrol as K  # noqa: E402

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", str(ek)[:300])


class SahteSB:
    def __init__(self, cevap=None, hata=None):
        self.cevap, self.hata, self.cagri = cevap, hata, []

    def rpc(self, ad, veri):
        self.cagri.append((ad, veri))
        sb = self

        class _Is:
            def execute(self):
                if sb.hata:
                    raise sb.hata
                return type("R", (), {"data": sb.cevap})()
        return _Is()


# ── talep_birak ──
sb = SahteSB("bekliyor")
r = L.talep_birak(sb, "atasehir", ["UUID-1", "1234"])
c("talep merkeze gider ve durumu döner", r == "bekliyor" and sb.cagri[0][0] == "lisans_talep_et", sb.cagri)
v = sb.cagri[0][1]
c("talep: lokasyon, ana kimlik, bütün kimlikler, bilgisayar adı",
  v["p_lokasyon"] == "atasehir" and v["p_makine"] == "UUID-1" and v["p_kimlikler"] == ["UUID-1", "1234"]
  and v["p_makine_adi"], v)
c("merkezde işlev yoksa (008 uygulanmamış) eski davranış: None",
  L.talep_birak(SahteSB(hata=RuntimeError("PGRST202 function not found")), "atasehir", ["U"]) is None)
c("lokasyon kimliği yoksa talep yok", L.talep_birak(SahteSB("bekliyor"), "", ["U"]) is None)
c("bekleyen talep için anlaşılır mesaj", "Synapse" in L.TALEP_MESAJ["bekliyor"])

# ── watchdog: onay beklerken kapanmaz ──
BEK = {"gecerli": False, "talep": "bekliyor", "makine_id": "UUID-1", "lokasyon_id": "atasehir", "hata": "x"}
sira = [dict(BEK), RuntimeError("ag yok"), {"gecerli": True, "makine_adi": "ATASEHIR-PC"}]
bekleme = []


def kontrol():
    s = sira.pop(0)
    if isinstance(s, Exception):
        raise s
    return s


r = W.lisans_onayini_bekle(dict(BEK), aralik_sn=60, _kontrol=kontrol, _bekle=bekleme.append, en_cok_tur=10)
c("onay gelince geçerli sonuç döner (ağ hatası beklemeyi bozmaz)", r.get("gecerli") and bekleme == [60, 60, 60],
  (r, bekleme))
bekleme = []
r = W.lisans_onayini_bekle({"gecerli": False, "talep": None, "hata": "yok"}, _kontrol=kontrol, _bekle=bekleme.append)
c("talep bırakılamadıysa (eski merkez) beklemez", not r["gecerli"] and bekleme == [])
r = W.lisans_onayini_bekle(dict(BEK), _kontrol=lambda: dict(BEK), _bekle=lambda s: None, en_cok_tur=3)
c("onay gelmezse geçersiz kalır (watchdog sonra kapanır)", not r["gecerli"] and r["talep"] == "bekliyor")
c("geçerli lisansta hiç beklenmez", W.lisans_onayini_bekle({"gecerli": True}, _bekle=bekleme.append) == {"gecerli": True})

# ── kurulum kontrolü: son adımda onayı bekler ──
sira2 = [dict(BEK), dict(BEK), {"gecerli": True}]
c("kurulum: onay gelince devam", K.lisans_onayini_bekle(600, lisans=lambda: sira2.pop(0), _bekle=lambda s: None))
c("kurulum: talep yoksa beklemeden döner",
  K.lisans_onayini_bekle(600, lisans=lambda: {"gecerli": False, "talep": None}, _bekle=lambda s: 1 / 0) is False)
sonuc = K.kontrol(BURASI, tcp=lambda *a: True, http=lambda u: 200, agent_turu=False, lisans=lambda: dict(BEK))
satir = [s for s in sonuc if s["kontrol"] == "Lisans"]
c("kurulum raporu: 'Synapse'ten onaylayın' yazar",
  not satir or ("Lisanslar" in satir[0]["aciklama"] and "UUID-1" in satir[0]["aciklama"]), satir)

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
