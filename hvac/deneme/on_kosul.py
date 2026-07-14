# -*- coding: utf-8 -*-
# on_kosul.py — MEKANİK ZEKA SAĞLAMLAŞTIRMA FAZ 2 + FAZ 3
#
# Analiz ÖN KOŞUL KAPISI: 1) Start/Stop → 2) Basınç onayı → 3) Sensör aralık onayı.
# Karar tablosu SAGLAMLASTIRMA_NOTU Bölüm 3.1'in birebir kod karşılığıdır.
#
# Ek sorumluluklar:
#   - Debounce: kapı durumu ancak 2 ardışık okuma aynı sonucu verirse değişir (3.2)
#   - Takılı değer + sıçrama karantinası (3.3)
#   - Dijital bakım kartına OTOMATİK işaret + 24s susturma + audit log (FAZ 3 / 4.x)
#
# İLKE: Bu modül HİÇBİR BACnet yazma çağrısı yapmaz — yalnızca okur/karar verir (Not 10.5).

import os
import json
import logging
import datetime

logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DURUM_FILE = os.path.join(BASE_DIR, "configs", "on_kosul_durum.json")
CARDS_FILE = os.path.join(BASE_DIR, "configs", "maintenance_cards.json")
AUDIT_FILE = os.path.join(BASE_DIR, "configs", "bakim_audit_log.jsonl")

# Varsayılanlar — main_portal CONFIG bunları override edebilir (FAZ 5 anahtarları)
DEFAULTS = {
    "PRESSURE_RUN_MIN_PA": 20.0,     # üstü = fan çalışıyor
    "PRESSURE_FAULT_MAX_PA": 1500.0, # üstü = sensör arızası (saturasyon)
    "SENSOR_VALID_MIN_C": 1.0,
    "SENSOR_VALID_MAX_C": 50.0,
    "MANUAL_SUPPRESS_HOURS": 24,
    "DEBOUNCE_OKUMA": 2,             # durum değişimi için ardışık aynı sonuç
    "DUZELME_OKUMA": 3,              # sensör 'düzeldi' için ardışık geçerli okuma
    "TAKILI_OKUMA": 12,              # ~6 saat (30 dk döngü)
    "TAKILI_TOLERANS": 0.05,
    "SICRAMA_ESIK_C": 15.0,
    "SKIP_ESKALASYON_GUN": 7,
}

# ================================================================
# DURUM DOSYASI
# ================================================================

def _durum_oku() -> dict:
    try:
        with open(DURUM_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _durum_yaz(d: dict):
    try:
        os.makedirs(os.path.dirname(DURUM_FILE), exist_ok=True)
        with open(DURUM_FILE, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=1)
    except Exception as e:
        logger.warning("on_kosul durum dosyası yazılamadı: %s", e)


# ================================================================
# BAKIM KARTI OTOMASYONU (FAZ 3) — SİSTEM baskın, elle susturma 24s
# ================================================================

SENSOR_ALANLARI = ("supply_sensor", "return_sensor", "pressure_sensor")


def _simdi() -> str:
    return datetime.datetime.now().isoformat(timespec="seconds")


def _audit(santral: str, alan: str, eski: str, yeni: str, kim: str, neden: str):
    """Append-only denetim izi (kandırma paterni buradan görünür)."""
    try:
        os.makedirs(os.path.dirname(AUDIT_FILE), exist_ok=True)
        with open(AUDIT_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps({
                "ts": _simdi(), "santral": santral, "alan": alan,
                "eski": eski, "yeni": yeni, "kim": kim, "neden": neden,
            }, ensure_ascii=False) + "\n")
    except Exception as e:
        logger.warning("Audit log yazılamadı: %s", e)


def _kartlari_oku() -> dict:
    try:
        with open(CARDS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"last_updated": None, "updated_by": None, "cards": {}}


def _kartlari_yaz(data: dict):
    try:
        os.makedirs(os.path.dirname(CARDS_FILE), exist_ok=True)
        with open(CARDS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.warning("Bakım kartı yazılamadı: %s", e)


def sistem_isaret_koy(santral: str, alan: str, neden: str, cfg: dict = None):
    """SİSTEM kaynaklı FAULTY işareti. Kurallar (Not 4.2):
    - Açık SİSTEM kaydı varsa tekrar yazmaz (spam engeli)
    - Personel elle OK'a çektiyse (suppressed_until dolu ve süresi geçmemiş) dokunmaz;
      süre dolduysa FAULTY otomatik GERİ yazılır."""
    cfg = {**DEFAULTS, **(cfg or {})}
    data = _kartlari_oku()
    cards = data.setdefault("cards", {})
    kart = cards.setdefault(santral, {})
    meta_key = alan + "_meta"
    meta = kart.get(meta_key) or {}
    simdi = _simdi()

    # Susturma aktif mi?
    sup = meta.get("suppressed_until")
    if sup:
        if simdi < sup:
            return False  # personel susturması sürüyor — dokunma (raporda SUSTURULDU görünür)
        # süre doldu, sensör hâlâ arızalı → işaret geri gelir (susturma temizlenir)
        meta["suppressed_until"] = None

    if kart.get(alan) == "FAULTY" and meta.get("source") == "SISTEM":
        return False  # açık SİSTEM kaydı var — spam yok

    eski = kart.get(alan, "OK")
    kart[alan] = "FAULTY"
    meta.update({
        "source": "SISTEM",
        "auto_reason": neden,
        "auto_since": simdi,
        "suppressed_until": meta.get("suppressed_until"),
    })
    meta.setdefault("history", []).append(
        {"ts": simdi, "kim": "SISTEM", "eski": eski, "yeni": "FAULTY", "neden": neden})
    kart[meta_key] = meta
    kart["_updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    data["last_updated"] = simdi
    data["updated_by"] = "SISTEM"
    _kartlari_yaz(data)
    _audit(santral, alan, eski, "FAULTY", "SISTEM", neden)
    logger.info("Bakım kartı SİSTEM işareti: %s.%s FAULTY (%s)", santral, alan, neden)
    return True


def sistem_isaret_kaldir(santral: str, alan: str, neden: str = "3 ardışık geçerli okuma"):
    """Sensör düzeldi: SADECE source=SISTEM olan FAULTY kalkar.
    Personelin ELLE koyduğu FAULTY'ye sistem dokunmaz (Not 4.2 madde 4)."""
    data = _kartlari_oku()
    kart = (data.get("cards") or {}).get(santral)
    if not kart:
        return False
    meta = kart.get(alan + "_meta") or {}
    if kart.get(alan) != "FAULTY" or meta.get("source") != "SISTEM":
        return False
    simdi = _simdi()
    kart[alan] = "OK"
    meta["source"] = "SISTEM"
    meta["auto_reason"] = ""
    meta["suppressed_until"] = None
    meta.setdefault("history", []).append(
        {"ts": simdi, "kim": "SISTEM", "eski": "FAULTY", "yeni": "OK", "neden": neden})
    kart[alan + "_meta"] = meta
    kart["_updated_at"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    _kartlari_yaz(data)
    _audit(santral, alan, "FAULTY", "OK", "SISTEM", neden)
    return True


def elle_ok_suppress(santral: str, alan: str, kim: str = "Operatör", cfg: dict = None):
    """Personel elle FAULTY→OK çekti: işaret silinmez, 24 saatlik susturma yazılır.
    (main_portal save_maintenance yolundan çağrılır — Not 4.2 madde 1-2)"""
    cfg = {**DEFAULTS, **(cfg or {})}
    data = _kartlari_oku()
    kart = (data.get("cards") or {}).get(santral)
    if not kart:
        return False
    meta = kart.get(alan + "_meta") or {}
    if meta.get("source") != "SISTEM":
        return False  # SİSTEM kaydı yoksa normal elle değişimdir, susturma mantığı işlemez
    bitis = (datetime.datetime.now()
             + datetime.timedelta(hours=cfg["MANUAL_SUPPRESS_HOURS"])).isoformat(timespec="seconds")
    meta["suppressed_until"] = bitis
    meta.setdefault("history", []).append(
        {"ts": _simdi(), "kim": kim, "eski": "FAULTY", "yeni": "OK",
         "neden": f"elle temizleme → {cfg['MANUAL_SUPPRESS_HOURS']}s susturma"})
    kart[alan + "_meta"] = meta
    _kartlari_yaz(data)
    _audit(santral, alan, "FAULTY", "OK", kim, "elle susturma")
    return True


# ================================================================
# SENSÖR SAĞLIK KONTROLLERİ (aralık + takılı + sıçrama)
# ================================================================

def _sensor_gecerli(deger, cfg) -> bool:
    if deger is None:
        return False
    try:
        v = float(deger)
    except (TypeError, ValueError):
        return False
    return cfg["SENSOR_VALID_MIN_C"] <= v <= cfg["SENSOR_VALID_MAX_C"]


def _sensor_izle(kayit: dict, sensor_adi: str, deger, cfg) -> dict:
    """Sensör geçmişini günceller; döner: {gecerli, karantina, takili, duzeldi}.
    - Sıçrama: önceki geçerli okumaya göre >15°C fark → bu okuma karantina
    - Takılı: son 12 okuma ±0.05 bandında sabit
    - Düzeldi: son 3 okuma geçerli aralıkta"""
    s = kayit.setdefault("sensorler", {}).setdefault(sensor_adi, {"degerler": [], "gecerli_sayac": 0})
    sonuc = {"gecerli": _sensor_gecerli(deger, cfg), "karantina": False,
             "takili": False, "duzeldi": False}

    if deger is not None:
        try:
            v = float(deger)
            onceki = s["degerler"][-1] if s["degerler"] else None
            # Sıçrama karantinası: yalnız ÖNCEKİ değer de geçerli aralıktaysa anlamlı —
            # arızalı değerden (örn. 0.2) geçerliye dönüş sıçrama DEĞİL, düzelmedir.
            onceki_gecerli = (onceki is not None
                              and cfg["SENSOR_VALID_MIN_C"] <= onceki <= cfg["SENSOR_VALID_MAX_C"])
            if (onceki_gecerli and sonuc["gecerli"]
                    and abs(v - onceki) > cfg["SICRAMA_ESIK_C"]):
                sonuc["karantina"] = True  # tek okuma karantina; kayda yine ekleriz (2. okuma kıyası için)
            s["degerler"].append(round(v, 2))
            s["degerler"] = s["degerler"][-max(cfg["TAKILI_OKUMA"], 12):]
        except (TypeError, ValueError):
            pass

    # Takılı kontrol (yalnız geçerli değerlerde anlamlı)
    d = s["degerler"]
    if len(d) >= cfg["TAKILI_OKUMA"]:
        son = d[-cfg["TAKILI_OKUMA"]:]
        if max(son) - min(son) <= 2 * cfg["TAKILI_TOLERANS"]:
            sonuc["takili"] = True

    # Düzelme sayacı — TAKILI şüphesi sürerken 'düzeldi' üretilmez
    # (takılı değer aralık içinde göründüğü için sayaç yanıltıcı olur)
    if sonuc["gecerli"] and not sonuc["karantina"] and not sonuc["takili"]:
        s["gecerli_sayac"] = s.get("gecerli_sayac", 0) + 1
        s["gecersiz_sayac"] = 0
    else:
        s["gecerli_sayac"] = 0
        # Geçersiz sayacı: okuma VAR ama aralık dışı (None = okuma yok, sayılmaz)
        if deger is not None and not sonuc["gecerli"]:
            s["gecersiz_sayac"] = s.get("gecersiz_sayac", 0) + 1
    if s["gecerli_sayac"] >= cfg["DUZELME_OKUMA"] and not sonuc["takili"]:
        sonuc["duzeldi"] = True
    # 2 ardışık aralık-dışı okuma → kalıcı arıza şüphesi (kapı kararından bağımsız;
    # örn. STOP'taki santralde üfleme 0.04 okunuyorsa sensör yine arızalıdır — G13)
    sonuc["kalici_gecersiz"] = s.get("gecersiz_sayac", 0) >= cfg["DEBOUNCE_OKUMA"]

    return sonuc


# ================================================================
# KAPI — KARAR TABLOSU (Not 3.1 birebir)
# ================================================================

def _ham_karar(start, basinc, basinc_nokta_var, ufleme_ok, donus_ok, cfg) -> dict:
    """Tek okumalık ham kapı kararı. Dönüş: {karar, bulgu, notlar:[...], isaretler:[(alan,neden)]}"""
    r = {"karar": "ANALIZ", "bulgu": None, "notlar": [], "isaretler": []}
    p_run = cfg["PRESSURE_RUN_MIN_PA"]
    p_max = cfg["PRESSURE_FAULT_MAX_PA"]

    start_var = start is not None
    calisiyor_komutu = start_var and float(start) >= 0.5

    # ── START/STOP kapısı ──
    if start_var and not calisiyor_komutu:  # STOP
        if basinc is not None and float(basinc) > p_run:
            r["bulgu"] = "LOKAL_CALISMA"   # kumanda dışı çalışma — analiz yine yapılır
            r["notlar"].append("BMS komutu STOP ama basınç var — lokal çalıştırma")
            # analize devam (santral fiilen çalışıyor)
        else:
            r["karar"] = "SKIP_STOP"
            return r

    # ── BASINÇ kapısı (START veya lokal-çalışan) ──
    if basinc_nokta_var and basinc is not None:
        b = float(basinc)
        if b <= 0.0 or b > p_max:
            r["karar"] = "SKIP_BASINC_SENSOR_ARIZA"
            r["isaretler"].append(("pressure_sensor",
                                   f"Basınç sensörü arıza şüphesi: {b:.0f} Pa (geçerli: 0<p<={p_max:.0f})"))
            return r
        if calisiyor_komutu and b <= p_run:
            r["karar"] = "SKIP_FAN"        # analiz atlanır ama alarm üretilir
            r["bulgu"] = "FAN_BASMIYOR"
            return r
        r["basinc_dogrulandi"] = True      # basınç okundu ve geçerli → 3/3
    elif basinc_nokta_var and basinc is None:
        # Nokta tanımlı ama okuma gelmedi. Fan çalıştığı KOMUTLANMIŞSA basınç
        # doğrulanamaması veri sorunudur (SKIP_VERI_YOK). Aksi halde (start bilinmiyor
        # / STOP-lokal) analizi BLOKLAMAYIZ — hava/SAT + sensör aralık analizi sürer,
        # onay 2/3 olarak raporlanır (eskiden tüm santral SKIP_VERI_YOK'a düşüyordu).
        if calisiyor_komutu:
            r["karar"] = "SKIP_VERI_YOK"   # okuma başarısız — iletişim, arıza DEĞİL
            r["notlar"].append("Basınç okuması alınamadı (BACnet) — fan komutu AÇIK")
            return r
        r["notlar"].append("basınç okunamadı — 2/3 onay")
    else:
        r["notlar"].append("basınç doğrulaması yok (2/3 onay)")

    # ── SENSÖR aralık kapısı ──
    if not ufleme_ok:
        r["karar"] = "SKIP_SENSOR_ARIZA"
        r["isaretler"].append(("supply_sensor", "Aralık dışı/geçersiz üfleme okuması"))
        return r
    if not donus_ok:
        r["karar"] = "SKIP_SENSOR_ARIZA"
        r["isaretler"].append(("return_sensor", "Aralık dışı/geçersiz emiş okuması"))
        return r

    return r


def kapi_degerlendir(lokasyon: str, ahu_adi: str,
                     start=None, basinc=None, basinc_nokta_var: bool = True,
                     ufleme=None, donus=None, ufleme_var: bool = True, donus_var: bool = True,
                     cfg: dict = None) -> dict:
    """Ana giriş: santral için 3 kapılı ön koşul değerlendirmesi.

    ufleme_var/donus_var: nokta hiç TANIMLI değilse False geç — aralık kapısı o sensörü atlar
    (eksik nokta VERI_EKSIK kuralının konusudur, sensör arızası değildir).

    Dönüş: {karar, bulgu, notlar, onay, skip_gun, takili:{...}}
    Debounce: karar ancak 2 ardışık aynı ham sonuçta değişir."""
    cfg = {**DEFAULTS, **(cfg or {})}
    durum = _durum_oku()
    key = f"{lokasyon}|{ahu_adi}"
    kayit = durum.setdefault(key, {})

    # Sensör sağlık izleme (takılı/sıçrama/düzelme) — start/basınçtan bağımsız çalışır
    u_izle = _sensor_izle(kayit, "supply", ufleme, cfg) if ufleme_var else None
    d_izle = _sensor_izle(kayit, "return", donus, cfg) if donus_var else None

    # null okuma (deger None) sensör ARIZASI değildir — 'veri gelmedi'dir; aralık
    # kapısında atlanır (eksik/gelmeyen emiş VERI_EKSIK kuralının konusudur, sensör
    # arızası değil). SADECE değer VAR ama aralık dışıysa (örn. 0.04°C / 80°C) arıza sayılır.
    ufleme_ok = True
    if ufleme_var and ufleme is not None:
        ufleme_ok = u_izle["gecerli"] and not u_izle["karantina"]
    donus_ok = True
    if donus_var and donus is not None:
        donus_ok = d_izle["gecerli"] and not d_izle["karantina"]

    ham = _ham_karar(start, basinc, basinc_nokta_var, ufleme_ok, donus_ok, cfg)

    # ── Debounce: son ham kararlar ──
    gecmis = kayit.setdefault("ham_kararlar", [])
    gecmis.append(ham["karar"])
    kayit["ham_kararlar"] = gecmis[-max(cfg["DEBOUNCE_OKUMA"], 2):]

    onceki = kayit.get("kapi_karari")
    if onceki is None:
        kayit["kapi_karari"] = ham["karar"]          # ilk okuma: ham karar geçerli
    elif ham["karar"] != onceki:
        son = kayit["ham_kararlar"][-cfg["DEBOUNCE_OKUMA"]:]
        if len(son) >= cfg["DEBOUNCE_OKUMA"] and len(set(son)) == 1:
            kayit["kapi_karari"] = ham["karar"]      # 2 ardışık aynı → değiş
        # aksi halde önceki karar sürer (salınım koruması)
    karar = kayit["kapi_karari"]

    # skip başlangıcı / eskalasyon
    if karar.startswith("SKIP"):
        kayit.setdefault("skip_baslangic", _simdi())
    else:
        kayit.pop("skip_baslangic", None)
    skip_gun = 0
    if kayit.get("skip_baslangic"):
        try:
            bas = datetime.datetime.fromisoformat(kayit["skip_baslangic"])
            skip_gun = (datetime.datetime.now() - bas).days
        except Exception:
            pass

    # ── Bakım kartı otomasyonu (karar debounce'tan geçtiyse) ──
    # KANONİK kart anahtarı: 'LOKASYON AD' (büyük harf). Aynı ad birden çok lokasyonda
    # olabildiği için (Ahu-6 hem MAS-1 hem MAS-2) sistem işaretini lokasyonla niteleriz —
    # aksi halde ad-yalnız ('Ahu-6') ayrı/mükerrer kart oluşuyordu. main_portal.kart_key
    # ile BİREBİR aynı format olmalı (operatörün 'MAS-1 AHU-6' kartıyla eşleşsin).
    _kart_key = (f"{(lokasyon or '').strip()} {(ahu_adi or '').strip()}".strip()).upper()
    if karar == ham["karar"]:
        for alan, neden in ham["isaretler"]:
            sistem_isaret_koy(_kart_key, alan, neden, cfg)
    # Takılı sensör + kalıcı aralık-dışı işaretleri (kapı kararından bağımsız — G13:
    # STOP'taki santralde bile 0.04°C okuyan sensör arızalıdır)
    for sensor_adi, izle, alan in (("supply", u_izle, "supply_sensor"),
                                   ("return", d_izle, "return_sensor")):
        if izle and izle["takili"]:
            sistem_isaret_koy(_kart_key, alan,
                              f"TAKILI SENSÖR şüphesi: {cfg['TAKILI_OKUMA']} okumadır değişmiyor", cfg)
        if izle and izle.get("kalici_gecersiz"):
            sistem_isaret_koy(_kart_key, alan,
                              "Aralık dışı okuma (2 ardışık) — geçerli: "
                              f"{cfg['SENSOR_VALID_MIN_C']:.0f}-{cfg['SENSOR_VALID_MAX_C']:.0f}°C", cfg)
        if izle and izle["duzeldi"]:
            sistem_isaret_kaldir(_kart_key, alan)

    _durum_yaz(durum)

    # Onay sayısı (rapor için): toplam kapı = basınç noktası varsa 3, yoksa 2.
    # Basınç noktası var ama okuma gelmediyse (doğrulanmadı) o kapı düşülür → 2/3.
    kapilar = 3 if basinc_nokta_var else 2
    _dogrulanan = kapilar
    if basinc_nokta_var and not ham.get("basinc_dogrulandi"):
        _dogrulanan = kapilar - 1
    return {
        "karar": karar,
        "bulgu": ham["bulgu"] if karar == ham["karar"] else None,
        "notlar": ham["notlar"],
        "onay": f"{_dogrulanan}/{kapilar}" if karar == "ANALIZ" else "-",
        "skip_gun": skip_gun,
        "eskalasyon": skip_gun >= cfg["SKIP_ESKALASYON_GUN"],
    }
