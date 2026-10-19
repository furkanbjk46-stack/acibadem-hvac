# -*- coding: utf-8 -*-
"""Sahte saha sunucusu — Mekanik Zeka'yı veri olmadan test etmek için.

    python simulasyon_sunucu.py --portal-ile          # portalı da başlatır
    python simulasyon_sunucu.py                       # portal zaten açıksa
    python simulasyon_sunucu.py --mevsim yaz          # soğutma senaryosu
    python simulasyon_sunucu.py --mevsim ara          # ikisi birden
    python simulasyon_sunucu.py --temizle             # çıkarken izleri sil

SAHADA ÇALIŞTIRILMAZ. Yanında supabase_config.json gören bir kurulumda
(yani gerçek bir lokasyon PC'sinde) çalışmayı reddeder — ürettiği sahte
analiz buluta ve Synapse'e giderdi. Bu dosya lokasyon yamalarına da
EKLENMEZ; geliştirme makinesinde kalır.

── NASIL ÇALIŞIR ─────────────────────────────────────────────────────────
Hesap zincirinin hiçbir parçası taklit edilmez. Yalnızca EN ALTTAKİ saha
okuması, yani tek bir fonksiyon (ahu_collector._bacnet_oku) sahte bir
cihazla değiştirilir. Bunun üstündeki her şey — nokta eşleme, satır kurma,
talep/üretim hesabı, kural motoruna POST, sonuç ve geçmiş kaydı — sahada
çalışan kodun TA KENDİSİDİR. Dolayısıyla burada gördüğünüz ekran, sahadaki
ekranla aynı yoldan üretilir.

Taklit edilen dört şey (hepsi dış dünya):
  _bacnet_oku              → sahte BACnet cihazı (bu dosyadaki simülasyon)
  _oat_cek                 → internet yerine mevsim eğrisi
  _csv_tazelik_kontrol     → CSV yok, uyarı anlamsız
  _bildirim_gunde_bir_gonder → Supabase'e TEK BİR bildirim bile gitmez

Nokta haritası gerçektir: configs/ahu_nokta_konfig.json (56 santral, 386
nokta) ve configs/hedefli_okuma_sablonu_2.xlsx (kazan/chiller/kolektör).
Yani santral adları, mahaller ve adresler sahadakiyle birebir aynıdır.

── SİMÜLE EDİLEN SAAT ────────────────────────────────────────────────────
Her tur simüle saati --dakika-adim kadar ilerletir (varsayılan 10 dk, yani
sahadaki analiz periyodu). Gerçek zamanda --aralik saniye bekler. Varsayılan
ayarla bir gün ~5 dakikada dolar: grafik hemen şekillenir, sabahtan akşama
yükün nasıl değiştiği görülür.
"""
import argparse
import json
import math
import os
import random
import signal
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

PORTAL_SAGLIK = "http://localhost:8005/api/health"

# Dış hava gece/gündüz bandı ve tesisin hangi hizmete açık olduğu.
# "ara" bandı bilerek geniştir (Nisan/Ekim): sabah ısıtma, öğleden sonra
# soğutma çalışsın ki iki talep-üretim kartı da aynı gün içinde denensin.
MEVSIM = {
    #            gece   gündüz  ısıtma  soğutma
    "kis": {"oat_alt": 1.0, "oat_ust": 9.0, "isitma": True, "sogutma": False},
    "ara": {"oat_alt": 12.0, "oat_ust": 26.0, "isitma": True, "sogutma": True},
    "yaz": {"oat_alt": 22.0, "oat_ust": 34.0, "isitma": False, "sogutma": True},
}


# ════════════════════════════════════════════════════════════════════
# SİMÜLASYON DURUMU
# ════════════════════════════════════════════════════════════════════

class Saha:
    """Tek bir anın saha görüntüsü: dış hava, kolektörler, chiller, kazan, AHU'lar.

    ÖNEMLİ: Bir turda aynı nokta birden çok kez okunur (ör. KAZAN-1 INLET ve
    KAZAN-1 OUTLET ayrı çağrılardır) ve santralin yedi noktası tek tek gelir.
    Bu yüzden her değer tur başına BİR KEZ hesaplanıp saklanır; yoksa aynı
    kazanın giriş ve çıkışı farklı anlara ait olur, oda sıcaklığı da her
    nokta okumasında bir adım daha kayar. Önbellek ilerle() ile boşalır.
    """

    # Üretim tarafı talebin üstünde çalışır: kazanlar FCU ısıtmasını, kar
    # eritmeyi ve kullanım sıcak suyunu da besler, chiller'lar FCU filosunu.
    # Bu paylar ölçülmediği için ekrandaki talep yalnızca AHU'dur — simülasyon
    # da aynı gerçeği taşısın diye üretim bu oranla kademelenir.
    ISITMA_EK_YUK = 1.18
    SOGUTMA_EK_YUK = 1.12

    def __init__(self, mevsim: str, tohum: int, arizali: bool):
        self.mevsim = mevsim
        self.m = MEVSIM[mevsim]
        self.rnd = random.Random(tohum)
        self.arizali = arizali
        self.saat = datetime.now().replace(minute=0, second=0, microsecond=0)
        self.ahu_durum = {}      # (ad, mahal) → {"oda": .., "set": ..}  (turlar arası taşınır)
        # Sahada her santral aynı anda bozulmaz: arıza senaryoları SABİT
        # santrallere bağlanır ki ekranda tutarlı görünsün.
        self.arizalar = {}
        self._anlik = {}         # tur içi önbellek
        self.adim_dk = 10        # simüle adım; bina tepkisi bununla ölçeklenir
        self.santraller = []
        self.kapasite_sogutma = self._kapasite("ahu_tasarim_kapasiteleri.json")
        self.kapasite_isitma = self._kapasite("ahu_tasarim_isitma_kapasiteleri.json")
        self.kazan_birim, self.kazan_adedi, self.chiller_birim, self.chiller_adedi = self._tesis()
        self.kazan_tasarim_dt = self._tasarim_dt()

    @staticmethod
    def _kapasite(ad: str) -> dict:
        try:
            with open(os.path.join(BURASI, "configs", ad), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    @staticmethod
    def _tesis() -> tuple:
        try:
            with open(os.path.join(BURASI, "configs", "chiller_fcu_ayarlari.json"),
                      encoding="utf-8") as f:
                a = json.load(f)
            return (float(a.get("kazan_birim_kw", 1950)), int(a.get("kazan_adedi", 3)),
                    float(a.get("chiller_birim_kw", 2000)), int(a.get("chiller_adedi", 5)))
        except Exception:
            return 1950.0, 3, 2000.0, 5

    @staticmethod
    def _tasarim_dt() -> float:
        try:
            with open(os.path.join(BURASI, "configs", "hvac_settings.json"),
                      encoding="utf-8") as f:
                return float(json.load(f).get("TARGET_DT_HEAT_EXCHANGER", 8.0))
        except Exception:
            return 8.0

    def santralleri_tanit(self, santraller: list):
        """Santral listesini ve sabit arıza kurbanlarını belirler.

        Arıza kurbanları tur içinde SEÇİLMEZ; yoksa her turda başka santral
        bozulur ve ekranda tutarsız bir tablo çıkar.
        """
        self.santraller = sorted(santraller)
        if not self.arizali or not self.santraller:
            return
        s = self.santraller
        self.arizalar = {s[len(s) // 4]: "durdu",
                         s[len(s) // 2]: "sensor",
                         s[(3 * len(s)) // 4]: "basmiyor"}

    # ── talep: AHU vanaları × tasarım kapasitesi (ekrandakiyle aynı mantık) ──
    def _talepler(self) -> tuple:
        if "talep" in self._anlik:
            return self._anlik["talep"]
        isitma = sogutma = 0.0
        for ad, mahal in self.santraller:
            v = self.ahu(ad, mahal)
            qh = (self.kapasite_isitma.get(mahal) or {}).get(ad)
            qc = (self.kapasite_sogutma.get(mahal) or {}).get(ad)
            if qh:
                isitma += qh * (v.get("Heat Valve (%)") or 0) / 100.0
            if qc:
                sogutma += qc * (v.get("Cool Valve (%)") or 0) / 100.0
        self._anlik["talep"] = (round(isitma, 1), round(sogutma, 1))
        return self._anlik["talep"]

    # ── dış hava: mevsim bandı içinde günlük sinüs ──────────────────
    @property
    def oat(self) -> float:
        if "oat" not in self._anlik:
            d = self.saat.hour + self.saat.minute / 60.0
            # en soğuk 05:00, en sıcak 15:00
            oran = (1 - math.cos((d - 5) / 24 * 2 * math.pi)) / 2
            taban = self.m["oat_alt"] + (self.m["oat_ust"] - self.m["oat_alt"]) * oran
            self._anlik["oat"] = round(taban + self.rnd.uniform(-0.6, 0.6), 1)
        return self._anlik["oat"]

    @property
    def gunduz(self) -> bool:
        return 7 <= self.saat.hour < 19

    # ── yük oranı: 0 (boş bina) .. 1 (tam yük) ──────────────────────
    @property
    def yuk(self) -> float:
        temel = 0.85 if self.gunduz else 0.35
        if self.mevsim == "kis":
            sapma = max(0.0, (16.0 - self.oat) / 16.0)
        elif self.mevsim == "yaz":
            sapma = max(0.0, (self.oat - 22.0) / 12.0)
        else:
            sapma = 0.45
        return max(0.1, min(1.0, temel * (0.55 + 0.75 * sapma)))

    # ── hangi tesis hizmete açık ────────────────────────────────────
    # Mevsim yalnızca TESİSİN açık olup olmadığını söyler; vananın açılmasına
    # mahal sıcaklığı karar verir. Buna dış hava eşiği eklenirse (ör. "17°C
    # üstünde ısıtma yok") ara mevsimde ölü bant oluşur: oda set'in altında
    # kalır, ısıtma kapalıdır, soğutma da oda soğuk diye açılmaz ve sistem
    # gün boyu sıfırda takılır.
    @property
    def isitma_var(self) -> bool:
        return self.m["isitma"]

    @property
    def sogutma_var(self) -> bool:
        return self.m["sogutma"]

    # ── merkezi ekipman ─────────────────────────────────────────────
    @staticmethod
    def _kademe(hedef_kw: float, birim_kw: float, azami_adet: int) -> tuple:
        """Talebi karşılayacak en az ekipman + her birinin yük oranı.

        Sahadaki mantık budur: yetmeyince bir sonraki devreye girer, yük
        çalışanlar arasında paylaşılır. Tek bir ekipman %25'in altına
        düşmez (sürekli yanıp sönmesin)."""
        if hedef_kw <= 1 or birim_kw <= 0:
            return 0, 0.0
        adet = max(1, min(azami_adet, math.ceil(hedef_kw / birim_kw)))
        oran = max(0.25, min(1.0, hedef_kw / (adet * birim_kw)))
        return adet, oran

    def kazanlar(self) -> list:
        """[(durum, inlet, outlet)] — üç kazan. Devreye alma AHU talebine göre."""
        if "kazan" in self._anlik:
            return self._anlik["kazan"]
        isitma_talep, _ = self._talepler()
        adet, oran = (0, 0.0) if not self.isitma_var else self._kademe(
            isitma_talep * self.ISITMA_EK_YUK, self.kazan_birim, self.kazan_adedi)

        donus = 48.0 + 6 * (1 - oran)
        sonuc = []
        for n in range(3):
            if n < adet:
                # Debi sabit kabul edildiği için yük oranı doğrudan ΔT'ye yansır
                dt = self.kazan_tasarim_dt * oran + self.rnd.uniform(-0.25, 0.25)
                sonuc.append((1.0, round(donus, 1), round(donus + dt, 1)))
            else:
                sonuc.append((0.0, round(donus, 1), round(donus + 0.2, 1)))
        self._anlik["kazan"] = sonuc
        return sonuc

    def chillerlar(self) -> list:
        """[(durum, inlet, outlet, yuzde)] — beş chiller, talebe göre kademeli."""
        if "chiller" in self._anlik:
            return self._anlik["chiller"]
        _, sogutma_talep = self._talepler()
        adet, oran = (0, 0.0) if not self.sogutma_var else self._kademe(
            sogutma_talep * self.SOGUTMA_EK_YUK, self.chiller_birim, self.chiller_adedi)

        gidis = 7.0 + 1.5 * (1 - oran)
        sonuc = []
        for n in range(5):
            if n < adet:
                dt = 3.0 + 2.5 * oran
                yuzde = round(min(99.0, oran * 100 + self.rnd.uniform(-3, 3)), 1)
                sonuc.append((1.0, round(gidis + dt, 1), round(gidis, 1), yuzde))
            else:
                sonuc.append((0.0, round(gidis + 0.2, 1), round(gidis, 1), 0.0))
        self._anlik["chiller"] = sonuc
        return sonuc

    def kolektor(self) -> dict:
        if "kolektor" in self._anlik:
            return self._anlik["kolektor"]
        kaz = self.kazanlar()
        acik = [k for k in kaz if k[0] == 1.0]
        isitma_gidis = acik[0][2] if acik else 45.0
        isitma_donus = (acik[0][1] if acik else 43.0) + self.rnd.uniform(-0.3, 0.3)
        ch = self.chillerlar()
        ch_acik = [c for c in ch if c[0] == 1.0]
        sogutma_gidis = ch_acik[0][2] if ch_acik else 13.0
        sogutma_donus = (ch_acik[0][1] if ch_acik else 13.4) + self.rnd.uniform(-0.3, 0.3)
        self._anlik["kolektor"] = {
            "MAS-1 ISITMA SICAKLIK": round(isitma_gidis, 1),
            "MAS-2 ISITMA SICAKLIK": round(isitma_gidis - 0.6, 1),
            "KOLLEKTOR ISITMA DONUS SICAKLIK": round(isitma_donus, 1),
            "MAS-1 SOGUTMA SICAKLIK": round(sogutma_gidis, 1),
            "MAS-2 SOGUTMA SICAKLIK": round(sogutma_gidis + 0.4, 1),
            "KOLLEKTOR SOGUTMA DONUS SICAKLIK": round(sogutma_donus, 1),
            "MAS-1 KAZAN SICAKLIK": round(isitma_gidis + 2, 1),
            "MAS-2 KAZAN SICAKLIK": round(isitma_gidis + 1.4, 1),
            "DIS HAVA": self.oat,
            "CH SET": round(sogutma_gidis, 1),
            "ABS DURUM BILGISI": 0.0,
        }
        return self._anlik["kolektor"]

    # ── santraller ──────────────────────────────────────────────────
    def ahu(self, ad: str, mahal: str) -> dict:
        """Tek santralin nokta değerleri. Oda sıcaklığı turdan tura taşınır."""
        anahtar = (ad, mahal)
        onbellek = self._anlik.setdefault("ahu", {})
        if anahtar in onbellek:
            return onbellek[anahtar]

        d = self.ahu_durum.get(anahtar)
        if d is None:
            d = {"set": 22.0, "oda": 22.0 + self.rnd.uniform(-1.0, 1.0)}
            self.ahu_durum[anahtar] = d

        # Oda, dış havaya doğru sürüklenir; vana bunu geri çeker.
        # Vana açıklığı sapmayla orantılıdır: 0.3°C ölü bant, 2°C'de tam açık.
        # Eşikli (aç/kapa) davranış tek turda 4000 kW'lık sahte sıçramalar
        # üretiyordu — sahada da vana oransaldır.
        fark = d["oda"] - d["set"]          # + = oda sıcak
        OLU_BANT = 0.3
        TAM_ACIK = 2.0

        def _oran(x):
            return max(0.0, min(1.0, (x - OLU_BANT) / (TAM_ACIK - OLU_BANT)))

        heat = cool = 0.0
        if self.isitma_var and fark < -OLU_BANT:
            heat = round(100 * _oran(-fark) * (0.45 + 0.55 * self.yuk), 1)
        elif self.sogutma_var and fark > OLU_BANT:
            cool = round(100 * _oran(fark) * (0.45 + 0.55 * self.yuk), 1)

        # Üfleme: ısıtmada 28-31, soğutmada 15-18 bandında kalsın
        if heat > 0:
            sat = 28.0 + 3.0 * (heat / 100.0)
        elif cool > 0:
            sat = 18.0 - 3.0 * (cool / 100.0)
        else:
            sat = d["oda"] + self.rnd.uniform(-0.4, 0.4)

        # Oda bir sonraki tura doğru hareket eder. Etki, simüle adımla
        # ölçeklenir — yoksa --dakika-adim değişince bina bambaşka davranır.
        olcek = self.adim_dk / 10.0
        itis = (heat - cool) / 100.0 * 0.55 * olcek
        cevre = (self.oat - d["oda"]) * 0.03 * olcek
        d["oda"] = round(max(14.0, min(32.0, d["oda"] + itis + cevre)), 1)

        v = {
            "SAT (°C)": round(sat, 1),
            "Return (°C)": d["oda"],
            "Cool Valve (%)": round(cool, 1),
            "Heat Valve (%)": round(heat, 1),
            "Set (°C)": d["set"],
            "Start/Stop": 1.0,
            "Basınç (Pa)": round(220 + 60 * self.yuk + self.rnd.uniform(-15, 15), 1),
        }

        if self.arizali:
            v.update(self._ariza(anahtar))
        onbellek[anahtar] = v
        return v

    def _ariza(self, anahtar) -> dict:
        """Üç sabit arıza senaryosu — ön koşul kapısı ve kural motoru çalışsın.

        Sahada her gün birkaç santral ya duruyor ya sensörü ölüyor. Bunlar
        olmadan ekran hep yeşil görünür, "Analiz Dışı" filtresi ve kapı
        kuralları hiç denenmemiş olur. Kurbanlar ariza_ata() ile SABİTLENİR.
        """
        tip = self.arizalar.get(anahtar)
        if tip == "durdu":
            return {"Start/Stop": 0.0, "Cool Valve (%)": 0.0, "Heat Valve (%)": 0.0,
                    "Basınç (Pa)": 3.0}
        if tip == "sensor":
            return {"SAT (°C)": None}
        if tip == "basmiyor":
            return {"Basınç (Pa)": 2.0}
        return {}

    def ilerle(self, dakika: int):
        self.saat += timedelta(minutes=dakika)
        self._anlik.clear()      # yeni tur = yeni anlık görüntü


# ════════════════════════════════════════════════════════════════════
# SAHTE BACNET CİHAZI
# ════════════════════════════════════════════════════════════════════

def _adres(n: dict) -> tuple:
    return (str(n["gateway_ip"]), int(n["dnet"]), str(n["mac_hex"]),
            int(n["obj_type"]), int(n["obj_inst"]))


def harita_kur(ac) -> tuple:
    """Gerçek nokta konfiglerinden adres → nokta kimliği haritası."""
    ahu_konfig = ac.load_ahu_config()
    enerji_konfig = ac.load_energy_config()

    harita = {}
    for n in ahu_konfig:
        harita[_adres(n)] = ("ahu", n["ahu_adi"], n["lokasyon"], n["nokta_tipi"])
    cakisma = 0
    for n in enerji_konfig:
        a = _adres(n)
        if a in harita:
            cakisma += 1
            continue
        harita[a] = ("enerji", n["point_name"])
    return harita, ahu_konfig, enerji_konfig, cakisma


def sahte_bacnet_yap(saha: Saha, harita: dict):
    """ahu_collector._bacnet_oku yerine geçecek fonksiyonu üretir."""
    def _oku(gateway_ip, dnet, mac_hex, obj_type, obj_inst, **kw):
        kimlik = harita.get((str(gateway_ip), int(dnet), str(mac_hex),
                             int(obj_type), int(obj_inst)))
        if kimlik is None:
            return None
        if kimlik[0] == "ahu":
            _, ad, mahal, tip = kimlik
            return saha.ahu(ad, mahal).get(tip)

        ad = kimlik[1]
        kol = saha.kolektor()
        if ad in kol:
            return kol[ad]

        kaz = saha.kazanlar()
        for n in (1, 2, 3):
            durum, inlet, outlet = kaz[n - 1]
            if ad == f"KAZAN-{n} DURUM BILGISI":
                return durum
            if ad == f"KAZAN-{n} INLET":
                return inlet
            if ad == f"KAZAN-{n} OUTLET":
                return outlet

        ch = saha.chillerlar()
        for n in (1, 2, 3, 4, 5):
            durum, inlet, outlet, yuzde = ch[n - 1]
            if ad == f"CH-{n} DURUM BILGISI":
                return durum
            if ad.startswith(f"CH-{n} INLET"):
                return inlet
            if ad.startswith(f"CH-{n} OUTLET"):
                return outlet
            if ad == f"CH-{n} CALISMA YUZDELIK":
                return yuzde
            if ad == f"CH-{n} IC SET":
                return outlet
        return None
    return _oku


# ════════════════════════════════════════════════════════════════════
# PORTAL SÜRECİ
# ════════════════════════════════════════════════════════════════════

def portal_ayakta_mi(timeout=2.0) -> bool:
    try:
        with urllib.request.urlopen(PORTAL_SAGLIK, timeout=timeout) as r:
            return r.status == 200
    except Exception:
        return False


def portal_baslat(bekle=40) -> subprocess.Popen | None:
    if portal_ayakta_mi():
        print("• Portal zaten ayakta (8005) — yeniden başlatılmadı.")
        return None
    print("• Mekanik Zeka başlatılıyor (8005)...")
    p = subprocess.Popen([sys.executable, "main_portal.py"], cwd=BURASI)
    for _ in range(bekle):
        time.sleep(1)
        if portal_ayakta_mi():
            print("• Portal hazır: http://localhost:8005/hvac")
            return p
        if p.poll() is not None:
            print("DURDURULDU: portal süreci kapandı (çıkış %s)" % p.returncode)
            return p
    print("UYARI: portal %d sn içinde yanıt vermedi — yine de devam ediliyor." % bekle)
    return p


# ════════════════════════════════════════════════════════════════════
# ANA DÖNGÜ
# ════════════════════════════════════════════════════════════════════

def _yamala(ac, saha, harita):
    """Sahaya bakan dört fonksiyonu değiştirir. Üretim kodu dosyada DEĞİŞMEZ."""
    ac._bacnet_oku = sahte_bacnet_yap(saha, harita)
    ac._oat_cek = lambda *a, **k: saha.oat
    ac._csv_tazelik_kontrol = lambda *a, **k: None
    # Supabase'e sahte analiz bildirimi GİTMEZ
    ac._bildirim_gunde_bir_gonder = lambda *a, **k: None


def _ozet(sonuc: dict, saha: Saha) -> str:
    kpi = sonuc.get("kpi", {}) if sonuc else {}
    return (
        "{saat}  dış {oat:>5.1f}°C  |  soğutma talep {st:>6.0f} / üretim {su:>6.0f} kW"
        "  |  ısıtma talep {it:>6.0f} / üretim {iu:>6.0f} kW ({yon})"
        "  |  {kaz} kazan {ch} chiller  |  🔴{k} 🟡{u} 🟢{o}"
    ).format(
        saat=saha.saat.strftime("%d.%m %H:%M"), oat=saha.oat,
        st=sonuc.get("talep_sogutma_kw", 0), su=sonuc.get("uretilen_sogutma_kw", 0),
        it=sonuc.get("talep_isitma_kw", 0), iu=sonuc.get("uretilen_isitma_kw", 0),
        yon=sonuc.get("isitma_uretim_yontem") or "-",
        kaz=sonuc.get("calisan_kazan_adet", 0), ch=sonuc.get("calisan_chiller_adet", 0),
        k=kpi.get("crit", 0), u=kpi.get("warn", 0), o=kpi.get("optimal", 0),
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Mekanik Zeka için sahte saha sunucusu (SADECE LOCAL)")
    ap.add_argument("--mevsim", choices=["kis", "ara", "yaz"], default="kis",
                    help="kis=ısıtma, yaz=soğutma, ara=ikisi birden (varsayılan: kis)")
    ap.add_argument("--aralik", type=float, default=20.0,
                    help="turlar arası gerçek bekleme, saniye (varsayılan: 20)")
    ap.add_argument("--dakika-adim", type=int, default=10,
                    help="her turda simüle saat kaç dakika ilerlesin (varsayılan: 10)")
    ap.add_argument("--tur", type=int, default=0,
                    help="kaç tur sonra dursun (0 = Ctrl+C'ye kadar)")
    ap.add_argument("--portal-ile", action="store_true",
                    help="main_portal.py'yi de başlat ve çıkarken kapat")
    ap.add_argument("--arizasiz", action="store_true",
                    help="arıza senaryolarını üretme (her santral sağlam)")
    ap.add_argument("--temizle", action="store_true",
                    help="çıkarken üretilen test çıktılarını sil")
    ap.add_argument("--tohum", type=int, default=20261019)
    ap.add_argument("--zorla", action="store_true", help=argparse.SUPPRESS)
    a = ap.parse_args()

    if os.path.exists(os.path.join(BURASI, "supabase_config.json")) and not a.zorla:
        print("DURDURULDU: burası bir LOKASYON kurulumu (supabase_config.json var).\n"
              "Sahte analiz buluta ve Synapse'e giderdi. Geliştirme makinesinde çalıştırın.")
        return 2

    print("═" * 78)
    print("  SAHTE SAHA SUNUCUSU — SADECE LOCAL TEST, SAHA VERİSİ DEĞİL")
    print("  Mevsim: %s | tur aralığı: %.0f sn | simüle adım: %d dk"
          % (a.mevsim, a.aralik, a.dakika_adim))
    print("═" * 78)

    import ahu_collector as ac

    # Nokta haritası geliştirme kopyasında configs/ altında duruyor
    if not os.path.exists(ac.AHU_CONFIG_FILE):
        alternatif = os.path.join(BURASI, "configs", "ahu_nokta_konfig.json")
        if os.path.exists(alternatif):
            ac.AHU_CONFIG_FILE = alternatif
            print("• Nokta haritası: configs/ahu_nokta_konfig.json")
        else:
            print("DURDURULDU: ahu_nokta_konfig.json bulunamadı — hangi santrallerin\n"
                  "okunacağı bilinmiyor.")
            return 2

    saha = Saha(a.mevsim, a.tohum, arizali=not a.arizasiz)
    saha.adim_dk = a.dakika_adim
    harita, ahu_konfig, enerji_konfig, cakisma = harita_kur(ac)
    santraller = {(n["ahu_adi"], n["lokasyon"]) for n in ahu_konfig}
    saha.santralleri_tanit(list(santraller))
    santral = len(santraller)
    print("• %d santral / %d AHU noktası, %d enerji noktası simüle edilecek"
          % (santral, len(ahu_konfig), len(enerji_konfig)))
    if cakisma:
        print("  (uyarı: %d enerji noktası AHU adresiyle çakıştı, atlandı)" % cakisma)
    if not a.arizasiz:
        print("• Arıza senaryoları açık: 1 santral STOP, 1 sensör arızası, 1 fan basmıyor")

    _yamala(ac, saha, harita)

    portal = portal_baslat() if a.portal_ile else None
    if not portal_ayakta_mi():
        print("UYARI: 8005 yanıt vermiyor. Portalı ayrıca başlatın veya --portal-ile kullanın.")

    uretilen = []
    durduruldu = {"ok": False}

    def _dur(signum, frame):
        durduruldu["ok"] = True
        print("\n• Durduruluyor...")
    signal.signal(signal.SIGINT, _dur)

    tur = 0
    try:
        while not durduruldu["ok"] and (a.tur == 0 or tur < a.tur):
            tur += 1
            sonuc = ac.hvac_analiz_calistir()
            if sonuc:
                print("%3d. %s" % (tur, _ozet(sonuc, saha)))
            else:
                print("%3d. analiz üretilemedi — portal 8005 ayakta mı?" % tur)
            uretilen.append(saha.saat)
            saha.ilerle(a.dakika_adim)
            if a.tur == 0 or tur < a.tur:
                for _ in range(int(a.aralik * 10)):
                    if durduruldu["ok"]:
                        break
                    time.sleep(0.1)
    finally:
        if portal is not None and portal.poll() is None:
            print("• Portal kapatılıyor (PID %d)" % portal.pid)
            portal.terminate()
            try:
                portal.wait(timeout=10)
            except Exception:
                portal.kill()
        if a.temizle:
            _temizle()
        print("• %d tur üretildi. Ekran: http://localhost:8005/hvac" % tur)
    return 0


def _temizle():
    """Simülasyonun bıraktığı test çıktılarını siler (saha dosyası değildir)."""
    silinen = 0
    for yol in (os.path.join(BURASI, "configs", "uretim_tuketim_gecmis.json"),
                os.path.join(BURASI, "hvac_ahu_analiz_sonuclari.json")):
        try:
            if os.path.exists(yol):
                os.remove(yol)
                silinen += 1
        except OSError:
            pass
    for klasor in ("ahu_okuma_gecmis", "ahu_analiz_gecmis", os.path.join("static", "outputs")):
        yol = os.path.join(BURASI, klasor)
        if not os.path.isdir(yol):
            continue
        for ad in os.listdir(yol):
            try:
                os.remove(os.path.join(yol, ad))
                silinen += 1
            except OSError:
                pass
    print("• Test çıktıları silindi (%d dosya)" % silinen)


if __name__ == "__main__":
    raise SystemExit(main())
