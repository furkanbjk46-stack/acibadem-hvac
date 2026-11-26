# -*- coding: utf-8 -*-
"""
TASARRUF BULGULARI — kimlik, yaşam döngüsü, ölçüm
================================================

A3 (24.11.2026, tasarım: merkez/sunum/tasarruf_ogrenme_tasarimi.html §3–4).

Alışkanlık profilinden (aliskanlik.py) çıkan her bulgu KALICI bir kayıttır.
Kimlik = bulgu kodu (ör. SET_DIS_HAVA): alışkanlık 12 aylık pencereden çıkar,
her ay yeniden görülmesi YENİ bulgu değildir — aynı bulgu güncellenir, kararı korunur.

Yaşam döngüsü (durum):
  raporda     → raporda gösterildi, karar bekliyor
  bekletildi  → "sonra bakılacak"
  reddedildi  → neden zorunlu; "uygulanamaz" 6 ay susturur
  olculuyor   → uygulandı (tarihiyle); ölçüm dönemi doluyor
  dogrulandi  → ölçülen tasarruf hata payının üstünde
  belirsiz    → fark hata payı içinde (tasarruf diye yazılmaz)
  tutmadi     → tüketim beklentinin üstünde
  olculemez   → uygulandı ama bu kalemde günlük veriden ölçülemiyor
Kapandı sayılanlar (reddedildi, dogrulandi, belirsiz, tutmadi) aynı alışkanlık
sürse de yeniden "karar bekliyor"a düşmez; reddedilen "uygulanamaz" dışında
ise 6 ay sonra yeniden sorulur (koşullar değişmiş olabilir).

ÖLÇÜLEBİLİRLİK: Bulgunun tahmini tasarrufu, ölçülecek kalemin aylık toplamına
oranlanır ve o kalemde ölçümün tipik hata payıyla (Maslak: toplam ~%6, soğutma
~%26, kazan gazı ~%60) kıyaslanır. Tasarruf paydan küçükse rapor bunu baştan
söyler: "uygulansa da günlük sayaçlarla doğrulanamaz". Yanlış "tasarruf
doğrulandı" demektense "ölçülemez" demek doğrudur.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

BURASI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

RET_NEDENLERI = {
    "uygulanamaz": "Uygulanamaz (işletme gereği)",
    "zaten_yapiliyor": "Zaten yapılıyor",
    "veri_yanlis": "Veri yanlış / bulgu hatalı",
    "diger": "Diğer (not yazın)",
}
DURUM_ETIKET = {
    "raporda": "Karar bekliyor", "bekletildi": "Bekletildi", "reddedildi": "Reddedildi",
    "olculuyor": "Ölçülüyor", "dogrulandi": "Tasarruf doğrulandı", "belirsiz": "Ölçüldü — belirsiz",
    "tutmadi": "Tutmadı (tüketim arttı)", "olculemez": "Uygulandı — ölçülemedi",
}
KARAR_BEKLEYEN = ("raporda", "bekletildi")
KAPALI = ("reddedildi", "dogrulandi", "belirsiz", "tutmadi", "olculemez")
SUSTURMA_GUN = 182
AYNI_NEDEN_SUSTURMA_GUN = 365   # A5: aynı nedenle ikinci kez reddedilen bulgu bir yıl sorulmaz
YENIDEN_SORMA_GUN = 182

# Bulgu kodu → ölçülecek kalem
OLCUT = {"SET_DIS_HAVA": "sogutma", "HAFTA_SONU_ISITMA_PAZAR": "gaz",
         "HAFTA_SONU_ISITMA_CUMARTESI": "gaz", "SU_ARTISI_HAFTA_ICI": "su", "SU_ARTISI_PAZAR": "su",
         # A4: gün içi bulgular sayaçla değil, santral okumalarındaki davranışla ölçülür
         "VANA_CAKISMASI": "gun_ici", "GECE_SUREKLI_CALISMA": "gun_ici", "ES_ZAMANLI_ISITMA_SOGUTMA": "gun_ici"}
OLCULEBILIRLIK_YENILE_GUN = 30


def varsayilan_yol() -> str:
    try:
        from location_manager import get_manager
        return get_manager().get_data_path("veri/tasarruf_bulgulari.json")
    except Exception:
        import yollar
        return yollar.yol("veri/tasarruf_bulgulari.json", BURASI)


class BulguDefteri:
    def __init__(self, yol: Optional[str] = None):
        self.yol = yol or varsayilan_yol()
        self.kayitlar: Dict[str, Dict] = self._yukle()

    # ── dosya ────────────────────────────────────────────────────────────
    def _yukle(self) -> Dict[str, Dict]:
        if not os.path.exists(self.yol):
            return {}
        try:
            with open(self.yol, encoding="utf-8") as f:
                v = json.load(f)
            return v if isinstance(v, dict) else {}
        except Exception as e:
            logger.error(f"Bulgu defteri okunamadı ({self.yol}): {e}")
            return {}

    def kaydet(self):
        try:
            os.makedirs(os.path.dirname(self.yol), exist_ok=True)
            gecici = self.yol + ".tmp"
            with open(gecici, "w", encoding="utf-8") as f:
                json.dump(self.kayitlar, f, ensure_ascii=False, indent=2, default=str)
            os.replace(gecici, self.yol)
        except Exception as e:
            logger.error(f"Bulgu defteri yazılamadı ({self.yol}): {e}")

    # ── profilden güncelle ───────────────────────────────────────────────
    def profilden_guncelle(self, profil: Dict, bugun: Optional[date] = None,
                           olculebilirlik_hesapla=None) -> List[str]:
        """Profildeki bulguları deftere yazar. Döner: bu raporda gösterilecek kimlikler.
        olculebilirlik_hesapla(olcut) → tipik hata payı (oran); verilmezse hesaplanmaz."""
        bugun = bugun or date.today()
        simdi = datetime.now().isoformat(timespec="seconds")
        donem = profil.get("donem")
        gosterilecek = []
        for b in profil.get("bulgular", []):
            k = b["kod"]
            r = self.kayitlar.get(k)
            if r is None:
                r = {"kimlik": k, "kod": k, "ilk_gorulme": simdi, "donemler": [], "durum": "raporda",
                     "karar": None, "karar_gecmisi": [], "olcum": None, "olcut": OLCUT.get(k)}
                self.kayitlar[k] = r
            r.update({"baslik": b["baslik"], "kanit": b["kanit"], "oneri": b["oneri"],
                      "tasarruf": b.get("tasarruf"), "profil_durumu": b["durum"],
                      "supheli_olcutler": b.get("supheli_olcutler", []), "son_gorulme": simdi})
            if not r.get("olcut") and OLCUT.get(k):
                r["olcut"] = OLCUT[k]               # sonradan ölçüm yöntemi tanımlanan eski kayıt
            if b.get("santraller") and (r.get("karar") or {}).get("karar") != "uygulandi":
                r["santraller"] = b["santraller"]   # uygulandıktan sonra ölçülecek liste sabit kalır
            if donem and donem not in r["donemler"]:
                r["donemler"].append(donem)
                r["donemler"].sort()
            # Kapalı bulgu süresi dolunca yeniden sorulur (uygulanamaz → susturma bitince)
            if r["durum"] in KAPALI:
                tarih = (r.get("karar") or {}).get("tarih") or r.get("ilk_gorulme", "")[:10]
                sinir = r.get("susturma_bitis") or str(
                    (pd.Timestamp(tarih) + pd.Timedelta(days=YENIDEN_SORMA_GUN)).date())
                if r["durum"] == "reddedildi" and str(bugun) >= sinir:
                    r["durum"] = "raporda"
                    r["yeniden_soruldu"] = str(bugun)
            if olculebilirlik_hesapla and r.get("olcut"):
                self._olculebilirlik(r, profil, bugun, olculebilirlik_hesapla)
            if not self.susturuldu_mu(k, bugun):
                gosterilecek.append(k)
        self.kaydet()
        return gosterilecek

    def _olculebilirlik(self, r: Dict, profil: Dict, bugun: date, hesapla):
        o = r.get("olculebilirlik") or {}
        if o.get("tarih") and (bugun - date.fromisoformat(o["tarih"])).days < OLCULEBILIRLIK_YENILE_GUN \
                and o.get("pay") is not None:
            pay = o["pay"]
        else:
            try:
                pay = hesapla(r["olcut"])
            except Exception as e:
                logger.debug(f"Ölçülebilirlik hesaplanamadı: {e}")
                pay = None
        ts = r.get("tasarruf") or {}
        aylik = None
        hw = (profil.get("haftalik") or {}).get(r["olcut"]) or {}
        if hw.get("hafta_ici") is not None:
            aylik = hw["hafta_ici"] * 30
        oran = (ts.get("deger") / aylik) if (ts.get("deger") and aylik) else None
        if pay is None or oran is None:
            sonuc = "bilinmiyor"
        else:
            sonuc = "olculebilir" if oran > pay else "olculemez"
        r["olculebilirlik"] = {"tarih": str(bugun), "pay": pay, "beklenen_oran": oran, "sonuc": sonuc}

    # ── karar ────────────────────────────────────────────────────────────
    def karar_ver(self, kimlik: str, karar: str, neden: Optional[str] = None, notlar: Optional[str] = None,
                  uygulama_tarihi: Optional[str] = None, bugun: Optional[date] = None) -> Dict:
        """karar: 'uygulandi' | 'reddedildi' | 'bekletildi'"""
        bugun = bugun or date.today()
        r = self.kayitlar.get(kimlik)
        if r is None:
            raise KeyError(kimlik)
        if karar == "reddedildi":
            if neden not in RET_NEDENLERI:
                raise ValueError("Ret için neden seçilmeli")
            if neden == "diger" and not (notlar or "").strip():
                raise ValueError("'Diğer' nedeni için not yazılmalı")
        elif karar == "uygulandi":
            uygulama_tarihi = str(pd.Timestamp(uygulama_tarihi or bugun).date())
            if uygulama_tarihi > str(bugun):
                raise ValueError("Uygulama tarihi gelecekte olamaz")
            neden = None
        elif karar == "bekletildi":
            neden = None
        else:
            raise ValueError(f"Geçersiz karar: {karar}")
        k = {"karar": karar, "neden": neden, "notlar": (notlar or "").strip() or None,
             "uygulama_tarihi": uygulama_tarihi if karar == "uygulandi" else None,
             "tarih": str(bugun), "zaman": datetime.now().isoformat(timespec="seconds")}
        onceki_red = {kg.get("neden") for kg in r.get("karar_gecmisi") or [] if kg.get("karar") == "reddedildi"}
        # A5: biten ölçüm silinmeden geçmişe yazılır (kural güveni bunu sayar)
        o = r.get("olcum") or {}
        if o.get("durum") in ("dogrulandi", "belirsiz", "artis", "olculemez"):
            r.setdefault("olcum_gecmisi", []).append(dict(o))
        r["karar"] = k
        r.setdefault("karar_gecmisi", []).append(dict(k))
        r["durum"] = {"uygulandi": "olculuyor", "reddedildi": "reddedildi", "bekletildi": "bekletildi"}[karar]
        r["olcum"] = None
        r.pop("susturma_bitis", None)
        if karar == "reddedildi" and neden in onceki_red and neden != "diger":
            r["susturma_bitis"] = str(bugun + timedelta(days=AYNI_NEDEN_SUSTURMA_GUN))
        elif karar == "reddedildi" and neden in ("uygulanamaz", "zaten_yapiliyor"):
            r["susturma_bitis"] = str(bugun + timedelta(days=SUSTURMA_GUN))
        self.kaydet()
        return r

    def susturuldu_mu(self, kimlik: str, bugun: Optional[date] = None) -> bool:
        r = self.kayitlar.get(kimlik) or {}
        s = r.get("susturma_bitis")
        if bool(s) and str(bugun or date.today()) < s:
            return True
        # A5: kural bu lokasyonda tekrar tekrar tutmadıysa bulgu sorulmaz
        from tasarruf.ogrenme import kural_seviyesi
        return kural_seviyesi(self.ogrenme(), kimlik) == "susturuldu"

    def ogrenme(self) -> Dict:
        """Kural başına güven / seviye / eşik çarpanı (tasarruf/ogrenme.py)."""
        from tasarruf.ogrenme import kural_ozeti
        return kural_ozeti(self.kayitlar.values())

    # ── ölçüm ────────────────────────────────────────────────────────────
    def olcumleri_guncelle(self, df: pd.DataFrame, olc=None, gun_ici=None) -> List[str]:
        """Ölçülmekte olan bulguları ölçer. Döner: durumu değişen kimlikler.
        gun_ici: (santral özeti, bina özeti) — 'gun_ici' ölçütlü bulgular (A4) için; yoksa onlar atlanır."""
        varsayilan = olc is None
        if varsayilan:
            from tasarruf.olcum import olc
        degisen = []
        yazildi = False
        g = None
        for k, r in self.kayitlar.items():
            if r.get("durum") != "olculuyor" or not r.get("olcut"):
                continue
            uyg = (r.get("karar") or {}).get("uygulama_tarihi")
            if not uyg:
                continue
            try:
                if r["olcut"] == "gun_ici":
                    if gun_ici is None:
                        continue
                    from tasarruf import gun_ici as GI
                    sonuc = GI.olc(gun_ici[0], k, uyg, santraller=r.get("santraller"))
                else:
                    if varsayilan and g is None and r["olcut"] != "su":
                        from tasarruf.olcum import _gunluk
                        g = _gunluk(df)       # günlük tablo bir kez kurulur, ölçümler paylaşır
                    sonuc = olc(df, r["olcut"], uyg, g=g) if r["olcut"] != "su" else olc(df, "su", uyg)
            except Exception as e:
                logger.warning(f"{k} ölçülemedi: {e}")
                continue
            ozet = {x: sonuc.get(x) for x in ("durum", "olcut", "birim", "uygulama", "gun", "beklenen",
                                               "gercek", "tasarruf", "oran", "hata_payi", "yontem", "aciklama")}
            ozet["olcum_zamani"] = datetime.now().isoformat(timespec="seconds")
            r["olcum"] = ozet
            yazildi = True
            yeni = {"dogrulandi": "dogrulandi", "belirsiz": "belirsiz", "artis": "tutmadi",
                    "olculemez": "olculemez"}.get(sonuc["durum"])
            if yeni:
                r["durum"] = yeni
                degisen.append(k)
        if yazildi:
            self.kaydet()
        return degisen

    # ── sorgular ─────────────────────────────────────────────────────────
    def karar_bekleyenler(self, bugun: Optional[date] = None) -> List[Dict]:
        return [r for k, r in self.kayitlar.items()
                if r.get("durum") in KARAR_BEKLEYEN and not self.susturuldu_mu(k, bugun)]

    def sonuclar(self) -> List[Dict]:
        """Uygulanmış bulgular ve ölçüm sonuçları (rapordaki 'Önceki önerilerin sonucu')."""
        return [r for r in self.kayitlar.values() if (r.get("karar") or {}).get("karar") == "uygulandi"]

    def ozet(self) -> Dict:
        say = {}
        for r in self.kayitlar.values():
            say[r.get("durum")] = say.get(r.get("durum"), 0) + 1
        dogrulanan = [r["olcum"] for r in self.kayitlar.values()
                      if r.get("durum") == "dogrulandi" and r.get("olcum")]
        return {"bulgu": len(self.kayitlar), "durum": say,
                "dogrulanan_tasarruf": [{"olcut": o["olcut"], "birim": o["birim"], "tasarruf": o["tasarruf"]}
                                        for o in dogrulanan]}


def olculebilirlik_hesaplayici(df: pd.DataFrame, bugun: Optional[date] = None):
    """Kalem başına tipik ölçüm hata payı: son 28 günü 'uygulama' sayıp plasebo ölçümleri."""
    from tasarruf import olcum as O
    g = O._gunluk(df) if df is not None else None
    onbellek = {}

    def hesapla(olcut):
        if olcut in onbellek:
            return onbellek[olcut]
        if olcut == "su":
            su = pd.to_numeric(df.get("Su_Tuketimi_m3"), errors="coerce") if df is not None else None
            son_su = pd.to_datetime(df["Tarih"])[su.notna()].max() if su is not None and su.notna().any() else None
            onbellek[olcut] = (O.olc(df, "su", son_su - pd.Timedelta(days=O.OLCUM_GUN - 1)).get("hata_payi")
                               if son_su is not None else None)
            return onbellek[olcut]
        if olcut not in O.MODEL_HEDEF or g is None:
            onbellek[olcut] = None
            return None
        hedef = O.MODEL_HEDEF[olcut]
        son = g.loc[g[hedef].notna(), "tarih"].max()
        if pd.isna(son):
            onbellek[olcut] = None
            return None
        anchor = son - pd.Timedelta(days=O.OLCUM_GUN - 1)
        en_iyi = None
        for dongu in O.YONTEMLER.values():
            pl = O._plasebo(g, hedef, anchor, O.OLCUM_GUN, dongu)
            if len(pl) >= 3:
                import numpy as np
                pay = O.hata_payi(pl)
                en_iyi = pay if en_iyi is None else min(en_iyi, pay)
        onbellek[olcut] = en_iyi
        return en_iyi
    return hesapla
