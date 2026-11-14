# -*- coding: utf-8 -*-
"""
LOKASYON DONANIMI — ayar panelinin çekirdeği (14.11.2026, yayın sonrası ilk iş)
==============================================================================

Saha ekibi analizör ve BMS (BACnet) listelerini EXCEL olarak verir ya da panelden tek tek girer.
İki yol da aynı tablolardan geçer: oku → doğrula → önizleme (fark) → onay → yedek + yaz.

Tablolar (sütun adları standart şablonla aynı: belgeler/lokasyon_donanim_sablonu/):
  analizorler : AD, IP ADRESI, BİNA, MARKA, TÜR, KRİTİK, NOT          → ayar/sayaclar.json
  bms         : Gateway IP … Point Name, Durum                        → ayar/bacnet_okuma_sablonu.xlsx
  ahu         : Bina, Santral, Nokta Tipi, Gateway IP … Obj. Instance → ayar/bacnet_noktalari.json

IP'si olmayan analizör (sayaç henüz bağlı değil) ile "okunacak" / "yazılabilir değer" BMS noktaları
programın okuduğu dosyalara GİRMEZ; ayar/donanim_bekleyen.json'da saklanır (liste kaybolmasın).
Yazılabilir noktalar oto-set'in kendi ayarındadır (korunan alan): panel yalnız listeler.

Kayıt: önce yedek (durum/donanim_yedek/<zaman>/), sonra atomik yazım, sonra _restart.flag
(portal_watchdog programı yeniden başlatır; analizör listesi açılışta okunur). Değişiklik ayar/
altında olduğu için ayar_kaydi ile merkeze de gider (K1).
"""
import hashlib
import hmac
import io
import ipaddress
import json
import os
import re
import shutil
import tempfile
from datetime import datetime

import yollar

BURASI = os.path.dirname(os.path.abspath(__file__))

AN_SUTUN = ["AD", "IP ADRESI", "BİNA", "MARKA", "TÜR", "KRİTİK", "NOT"]
BMS_SUTUN = ["Gateway IP", "Network (DNET)", "MAC (DADR)", "Device Instance ID", "Object Type",
             "Object Instance", "Point Name", "Durum"]
AHU_SUTUN = ["Bina", "Santral", "Nokta Tipi", "Gateway IP", "Network (DNET)", "MAC (DADR)",
             "Object Type", "Object Instance"]
SUTUNLAR = {"analizorler": AN_SUTUN, "bms": BMS_SUTUN, "ahu": AHU_SUTUN}
TABLO_ADI = {"analizorler": "Analizörler", "bms": "BMS okuma noktaları", "ahu": "AHU noktaları"}

MARKALAR = ("Siemens", "Janitza")
TURLER = ("trafo", "sebeke", "uretim", "chiller", "alt_sayac", "kontrol")
EVET_HAYIR = ("Evet", "Hayır")
OKUNAN, YAZILABILIR, OKUNACAK = "okunan değer", "yazılabilir değer", "okunacak"
DURUMLAR = (OKUNAN, YAZILABILIR, OKUNACAK)
NOKTA_TIPLERI = ("SAT (°C)", "Return (°C)", "Set (°C)", "Heat Valve (%)", "Cool Valve (%)",
                 "Start/Stop", "Basınç (Pa)")
TAMSAYI = ("Network (DNET)", "Device Instance ID", "Object Type", "Object Instance")

SAYAC_DOSYA = "ayar/sayaclar.json"
SABLON_DOSYA = "configs/hedefli_okuma_sablonu_2.xlsx"     # yollar: ayar/bacnet_okuma_sablonu.xlsx
NOKTA_DOSYA = "configs/ahu_nokta_konfig.json"              # yollar: ayar/bacnet_noktalari.json
BEKLEYEN_DOSYA = "ayar/donanim_bekleyen.json"
SIFRE_DOSYA = "ayar/panel_sifresi.json"                    # merkeze gitmez (ayar_kaydi.GIZLI)
YEDEK_KLASOR = "durum/donanim_yedek"
GUNLUK_DOSYA = "durum/donanim_paneli_gunluk.jsonl"
SABLON_SAYFA = "Sheet1"


# ═══════════════════════════ yardımcılar ═══════════════════════════
_TR = str.maketrans("ıİğĞüÜşŞöÖçÇ", "iIgGuUsSoOcC")


def _katla(s) -> str:
    """Karşılaştırma için: Türkçe harf / büyük-küçük / boşluk farkı yok sayılır."""
    return re.sub(r"[^a-z0-9]", "", str(s or "").translate(_TR).lower())


def _bos(v) -> bool:
    if v is None or type(v).__name__ in ("NAType", "NaTType"):     # pandas pd.NA / NaT (panel tablosu)
        return True
    try:
        if v != v:            # NaN
            return True
    except Exception:
        pass
    return isinstance(v, str) and not v.strip()


def _metin(v):
    if _bos(v):
        return None
    if isinstance(v, float) and v.is_integer():
        v = int(v)
    return str(v).strip()


def _tamsayi(v):
    if _bos(v):
        return None
    if isinstance(v, bool):
        raise ValueError
    if isinstance(v, (int,)):
        return int(v)
    if isinstance(v, float):
        if not v.is_integer():
            raise ValueError
        return int(v)
    s = str(v).strip()
    return int(float(s)) if re.fullmatch(r"-?\d+(\.0+)?", s) else int(s)


def _secim(v, secenekler):
    """Serbest yazımı seçeneğe oturt (büyük-küçük / Türkçe harf farkı); bulunamazsa olduğu gibi."""
    if _bos(v):
        return None
    k = _katla(v)
    for s in secenekler:
        if _katla(s) == k:
            return s
    return str(v).strip()


def _durum(v):
    if _bos(v):
        return OKUNAN
    k = _katla(v)
    if "yaz" in k:
        return YAZILABILIR
    if "okunacak" in k or "eklenecek" in k:
        return OKUNACAK
    if "okun" in k:
        return OKUNAN
    return str(v).strip()


def _evet(v):
    if isinstance(v, bool):
        return "Evet" if v else "Hayır"
    if _bos(v):
        return None
    k = _katla(v)
    if k in ("evet", "e", "1", "true", "kritik", "var"):
        return "Evet"
    if k in ("hayir", "h", "0", "false", "yok"):
        return "Hayır"
    return str(v).strip()


def _ip_gecerli(s) -> bool:
    try:
        return isinstance(ipaddress.ip_address(str(s).strip()), ipaddress.IPv4Address)
    except ValueError:
        return False


def _mac(v):
    """'0x011C' biçimi (BMS listesindeki gibi); sayı girilmişse onaltılıya çevrilir."""
    if _bos(v):
        return None
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return "0x%04X" % int(v)
    s = str(v).strip()
    if re.fullmatch(r"0[xX][0-9A-Fa-f]+", s):
        return "0x" + s[2:].upper()
    return s


def _mac_gecerli(s) -> bool:
    return bool(re.fullmatch(r"0x[0-9A-F]+", str(s or "")))


def _atomik_yaz(yol, veri: bytes):
    os.makedirs(os.path.dirname(yol), exist_ok=True)
    fd, gecici = tempfile.mkstemp(prefix=".donanim_", dir=os.path.dirname(yol))
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(veri)
        os.replace(gecici, yol)
    except BaseException:
        try:
            os.remove(gecici)
        except OSError:
            pass
        raise


def _json_oku(yol, varsayilan):
    try:
        with open(yol, encoding="utf-8-sig") as f:
            return json.load(f)
    except (OSError, ValueError):
        return varsayilan


# ═══════════════════════════ mevcut durum ═══════════════════════════
def _yollar(base):
    return {"sayac": yollar.yol(SAYAC_DOSYA, base), "sablon": yollar.yol(SABLON_DOSYA, base),
            "nokta": yollar.yol(NOKTA_DOSYA, base), "bekleyen": yollar.yol(BEKLEYEN_DOSYA, base)}


def mevcut(base: str = None) -> dict:
    """Programın şu an kullandığı donanım listesi, panel tablosu biçiminde."""
    base = base or BURASI
    y = _yollar(base)
    bekleyen = _json_oku(y["bekleyen"], {})
    veri = {"analizorler": [], "bms": [], "ahu": []}

    sj = _json_oku(y["sayac"], {})
    for s in (sj.get("sayaclar") if isinstance(sj, dict) else sj) or []:
        veri["analizorler"].append({
            "AD": s.get("ad"), "IP ADRESI": s.get("ip") or None, "BİNA": s.get("bina"),
            "MARKA": _secim(s.get("marka"), MARKALAR), "TÜR": s.get("tur"),
            "KRİTİK": "Evet" if s.get("kritik") else "Hayır", "NOT": s.get("not")})
    for s in bekleyen.get("analizorler") or []:
        veri["analizorler"].append({k: s.get(k) for k in AN_SUTUN})

    if os.path.exists(y["sablon"]):
        import openpyxl
        wb = openpyxl.load_workbook(y["sablon"], read_only=True, data_only=True)
        ws = wb.worksheets[0]
        satirlar = list(ws.iter_rows(values_only=True))
        wb.close()
        if satirlar:
            bas = [_katla(c) for c in satirlar[0]]
            for r in satirlar[1:]:
                if all(_bos(c) for c in r):
                    continue
                d = {}
                for ad in BMS_SUTUN[:-1]:
                    i = bas.index(_katla(ad)) if _katla(ad) in bas else None
                    d[ad] = r[i] if i is not None and i < len(r) else None
                d["Durum"] = OKUNAN
                veri["bms"].append(_bms_satir(d))
    for s in bekleyen.get("bms") or []:
        veri["bms"].append(_bms_satir(s))

    for n in _json_oku(y["nokta"], []) or []:
        veri["ahu"].append({
            "Bina": n.get("lokasyon"), "Santral": n.get("ahu_adi"), "Nokta Tipi": n.get("nokta_tipi"),
            "Gateway IP": n.get("gateway_ip"), "Network (DNET)": n.get("dnet"), "MAC (DADR)": n.get("mac_hex"),
            "Object Type": n.get("obj_type"), "Object Instance": n.get("obj_inst")})
    return veri


def _bms_satir(d):
    s = {}
    for ad in BMS_SUTUN:
        v = d.get(ad)
        if ad in TAMSAYI:
            try:
                v = _tamsayi(v)
            except (TypeError, ValueError):
                v = _metin(v)
        elif ad == "MAC (DADR)":
            v = _mac(v)
        elif ad == "Durum":
            v = _durum(v)
        else:
            v = _metin(v)
        s[ad] = v
    return s


def _dogal(s):
    return [int(p) if p.isdigit() else p.lower() for p in re.split(r"(\d+)", str(s or ""))]


def ahu_sirala(liste: list) -> list:
    """Santral santral: Bina, santral no (Ahu-3 < Ahu-10), nokta tipi standart sırada — her santralin
    noktaları alt alta (dosyada Start/Basınç sonradan eklendiği için en sonda duruyordu)."""
    sira = {t: i for i, t in enumerate(NOKTA_TIPLERI)}
    return sorted(liste, key=lambda s: (_dogal(s.get("Bina")), _dogal(s.get("Santral")),
                                        sira.get(s.get("Nokta Tipi"), 99)))


def ahu_eksikler(liste: list) -> dict:
    """{nokta tipi: [santral, ...]} — bir santralde hiç olmayan nokta tipleri (panelde uyarı)."""
    santral = {}
    for s in liste:
        if s.get("Bina") and s.get("Santral"):
            santral.setdefault((s["Bina"], s["Santral"]), set()).add(s.get("Nokta Tipi"))
    eksik = {}
    for (bina, ad), tipler in sorted(santral.items(), key=lambda x: (_dogal(x[0][0]), _dogal(x[0][1]))):
        for t in NOKTA_TIPLERI:
            if t not in tipler:
                eksik.setdefault(t, []).append("%s %s" % (bina, ad))
    return eksik


def sistem_karsiligi(base: str = None) -> dict:
    """{Point Name: programdaki karşılığı} — panelde bilgi sütunu (bacnet_esleme'den)."""
    try:
        import bacnet_esleme
        es = bacnet_esleme.yukle(base or BURASI)
    except Exception:
        return {}
    hat = {}
    for h in es.get("isitma_hatlari") or []:
        for alan, ad in (("isitma", "ısıtma"), ("kazan", "kazan"), ("sogutma", "soğutma")):
            if h.get(alan):
                hat[h[alan]] = "%s %s" % (h.get("ad"), ad)
    return {n: (k + (" (" + hat[k] + ")" if k in hat else "")) for n, k in (es.get("noktalar") or {}).items()}


# ═══════════════════════════ Excel ═══════════════════════════
_BASLIK_ESI = {   # katlanmış başlık → standart sütun (kullanıcının ilk Maslak dosyaları da okunur)
    "ad": "AD", "analizorler": "AD", "analizor": "AD", "sayac": "AD", "sayacadi": "AD",
    "ipadresi": "IP ADRESI", "ipadresileri": "IP ADRESI", "ip": "IP ADRESI",
    "bina": "BİNA", "marka": "MARKA", "tur": "TÜR", "kritik": "KRİTİK", "not": "NOT", "aciklama": "NOT",
}


def _sayfa_turu(baslik_katli, sayfa_adi):
    ad = _katla(sayfa_adi)
    if "desigo" in ad or "roture" in baslik_katli:
        return None
    if "santral" in baslik_katli and "noktatipi" in baslik_katli:
        return "ahu"
    if "pointname" in baslik_katli and "gatewayip" in baslik_katli:
        return "bms"
    if ("ipadresi" in baslik_katli or "ipadresileri" in baslik_katli) and \
            any(k in baslik_katli for k in ("ad", "analizorler", "analizor", "sayac", "sayacadi")):
        return "analizorler"
    return None


def excel_oku(icerik) -> dict:
    """Excel (bytes ya da dosya yolu) → {"analizorler"?, "bms"?, "ahu"?, "_uyari": [...]}.
    Yalnız dosyada bulunan tablolar döner; panel yalnız onları değiştirir."""
    import openpyxl
    kaynak = io.BytesIO(icerik) if isinstance(icerik, (bytes, bytearray)) else icerik
    wb = openpyxl.load_workbook(kaynak, data_only=True, read_only=True)
    sonuc = {"_uyari": []}
    for ws in wb.worksheets:
        satirlar = [r for r in ws.iter_rows(values_only=True)]
        satirlar = [r for r in satirlar if r and any(not _bos(c) for c in r)]
        if not satirlar:
            continue
        bas = [_katla(c) for c in satirlar[0]]
        tur = _sayfa_turu(bas, ws.title)
        if not tur or tur in sonuc:
            continue
        if tur == "analizorler":
            eslem = {}
            for i, b in enumerate(bas):
                std = _BASLIK_ESI.get(b)
                if std and std not in eslem.values():
                    eslem[i] = std
        else:
            hedef = {_katla(a): a for a in SUTUNLAR[tur]}
            eslem = {}
            for i, b in enumerate(bas):
                if b in hedef and hedef[b] not in eslem.values():
                    eslem[i] = hedef[b]
        tablo, son_bina = [], None
        for r in satirlar[1:]:
            d = {a: None for a in SUTUNLAR[tur]}
            for i, std in eslem.items():
                d[std] = r[i] if i < len(r) else None
            if all(_bos(v) for v in d.values()):
                continue
            if tur == "analizorler":
                if _bos(d["AD"]):
                    continue                      # ör. not satırı
                if _bos(d["BİNA"]):
                    d["BİNA"] = son_bina          # ilk Maslak listesi: bina grubun ilk satırında
                son_bina = d["BİNA"]
                d = {"AD": _metin(d["AD"]), "IP ADRESI": _metin(d["IP ADRESI"]), "BİNA": _metin(d["BİNA"]),
                     "MARKA": _secim(d["MARKA"], MARKALAR), "TÜR": _secim(d["TÜR"], TURLER),
                     "KRİTİK": _evet(d["KRİTİK"]), "NOT": _metin(d["NOT"])}
                if d["IP ADRESI"] in ("None",):
                    d["IP ADRESI"] = None
            elif tur == "bms":
                if _bos(d["Point Name"]) and _bos(d["Gateway IP"]):
                    continue
                d = _bms_satir(d)
            else:
                d = _ahu_satir(d)
            tablo.append(d)
        sonuc[tur] = tablo
        sonuc["_uyari"].append("'%s' sayfası → %s (%d satır)" % (ws.title, TABLO_ADI[tur], len(tablo)))
    wb.close()
    if len(sonuc) == 1:
        sonuc["_uyari"].append("Dosyada tanınan sayfa yok: ilk satırda standart sütun adları olmalı "
                               "(boş şablonu panelden indirip onu doldurun).")
    return sonuc


def _ahu_satir(d):
    s = {}
    for ad in AHU_SUTUN:
        v = d.get(ad)
        if ad in TAMSAYI:
            try:
                v = _tamsayi(v)
            except (TypeError, ValueError):
                v = _metin(v)
        elif ad == "MAC (DADR)":
            v = _mac(v)
        elif ad == "Nokta Tipi":
            v = _secim(v, NOKTA_TIPLERI)
        else:
            v = _metin(v)
        s[ad] = v
    return s


def normalize(veri: dict) -> dict:
    """Panel tablosundan (DataFrame satırları) gelen değerleri Excel ile aynı biçime getirir."""
    cikti = {}
    for tur, satirlar in veri.items():
        if tur not in SUTUNLAR:
            continue
        liste = []
        for r in satirlar:
            if all(_bos(r.get(a)) for a in SUTUNLAR[tur]):
                continue                           # panelde eklenip boş bırakılan satır
            if tur == "analizorler":
                liste.append({"AD": _metin(r.get("AD")), "IP ADRESI": _metin(r.get("IP ADRESI")),
                              "BİNA": _metin(r.get("BİNA")), "MARKA": _secim(r.get("MARKA"), MARKALAR),
                              "TÜR": _secim(r.get("TÜR"), TURLER), "KRİTİK": _evet(r.get("KRİTİK")),
                              "NOT": _metin(r.get("NOT"))})
            elif tur == "bms":
                liste.append(_bms_satir(r))
            else:
                liste.append(_ahu_satir(r))
        cikti[tur] = liste
    return cikti


def tamamla(yeni: dict, eski: dict) -> list:
    """Eski biçimli Excel'de (MARKA / TÜR / KRİTİK sütunu yok) eksik alanları mevcut kayıttan doldurur:
    satır IP'den (yoksa addan) eşleşir. yeni yerinde değişir; dönüş: açıklama satırları."""
    notlar = []
    an = yeni.get("analizorler")
    if not an:
        return notlar
    ip_e = {s["IP ADRESI"]: s for s in eski.get("analizorler") or [] if s.get("IP ADRESI")}
    ad_e = {_katla(s["AD"]): s for s in eski.get("analizorler") or [] if s.get("AD")}
    doldurulan, ad_degisen = 0, []
    for s in an:
        e = ip_e.get(s.get("IP ADRESI")) or ad_e.get(_katla(s.get("AD")))
        if not e:
            continue
        dolan = False
        for a in ("MARKA", "TÜR", "KRİTİK", "BİNA"):
            if _bos(s.get(a)) and not _bos(e.get(a)):
                s[a] = e[a]
                dolan = True
        doldurulan += dolan
        if e.get("AD") and s.get("AD") and _katla(e["AD"]) != _katla(s["AD"]):
            ad_degisen.append("%s → %s" % (e["AD"], s["AD"]))
    if doldurulan:
        notlar.append("%d analizörün boş MARKA / TÜR / KRİTİK alanı programdaki kayıttan tamamlandı." % doldurulan)
    if ad_degisen:
        notlar.append("DİKKAT — aynı IP'de farklı ad (%d): %s. Kaydederseniz sayaç yeni adla görünür; geçmiş "
                      "günlük veri eski adla kalır. Programdaki adı korumak için Excel'deki adı düzeltin."
                      % (len(ad_degisen), ", ".join(ad_degisen)))
    return notlar


# ═══════════════════════════ doğrulama ═══════════════════════════
def dogrula(veri: dict, base: str = None) -> tuple:
    """(hatalar, uyarilar). Hata varsa kayıt yapılmaz. Satır numarası = tablodaki sıra (1'den)."""
    hatalar, uyarilar = [], []

    an = veri.get("analizorler")
    if an is not None:
        gor_ad, gor_ip = {}, {}
        for i, s in enumerate(an, 1):
            yer = "Analizör %d (%s)" % (i, s.get("AD") or "adsız")
            if not s.get("AD"):
                hatalar.append("%s: AD boş." % yer)
            else:
                k = _katla(s["AD"])
                if k in gor_ad:
                    hatalar.append("%s: AD %d. satırla aynı — her analizörün adı tekil olmalı." % (yer, gor_ad[k]))
                gor_ad.setdefault(k, i)
            ip = s.get("IP ADRESI")
            if ip:
                if not _ip_gecerli(ip):
                    hatalar.append("%s: IP adresi geçersiz: %s" % (yer, ip))
                elif ip in gor_ip:
                    hatalar.append("%s: IP %d. satırla aynı (%s)." % (yer, gor_ip[ip], ip))
                gor_ip.setdefault(ip, i)
                if s.get("MARKA") not in MARKALAR:
                    hatalar.append("%s: MARKA seçilmeli (Siemens / Janitza)." % yer)
                if s.get("TÜR") not in TURLER:
                    hatalar.append("%s: TÜR seçilmeli (%s)." % (yer, " / ".join(TURLER)))
            else:
                if s.get("MARKA") and s["MARKA"] not in MARKALAR:
                    hatalar.append("%s: MARKA geçersiz: %s" % (yer, s["MARKA"]))
                if s.get("TÜR") and s["TÜR"] not in TURLER:
                    hatalar.append("%s: TÜR geçersiz: %s" % (yer, s["TÜR"]))
            if s.get("KRİTİK") and s["KRİTİK"] not in EVET_HAYIR:
                hatalar.append("%s: KRİTİK Evet ya da Hayır olmalı." % yer)
        if an and not any(s.get("IP ADRESI") for s in an):
            uyarilar.append("Hiçbir analizörün IP adresi yok — program enerji sayacı okumayacak.")

    bms = veri.get("bms")
    if bms is not None:
        gor_ad, gor_adres = {}, {}
        for i, s in enumerate(bms, 1):
            yer = "BMS noktası %d (%s)" % (i, s.get("Point Name") or "adsız")
            if not s.get("Point Name"):
                hatalar.append("%s: Point Name boş." % yer)
            if s.get("Durum") not in DURUMLAR:
                hatalar.append("%s: Durum geçersiz: %s (okunan değer / yazılabilir değer / okunacak)."
                               % (yer, s.get("Durum")))
                continue
            if s["Durum"] == OKUNACAK:
                continue
            hatalar.extend(_adres_hatalari(yer, s, ("Device Instance ID",)))
            if s["Durum"] == OKUNAN and s.get("Point Name"):
                k = _katla(s["Point Name"])
                if k in gor_ad:
                    hatalar.append("%s: Point Name %d. satırla aynı — okunan noktaların adı tekil olmalı."
                                   % (yer, gor_ad[k]))
                gor_ad.setdefault(k, i)
            adres = tuple(s.get(a) for a in ("Gateway IP", "Network (DNET)", "MAC (DADR)", "Object Type",
                                             "Object Instance"))
            if all(v is not None for v in adres):
                if adres in gor_adres:
                    uyarilar.append("%s: adresi %d. satırla aynı." % (yer, gor_adres[adres]))
                gor_adres.setdefault(adres, i)
        es = sistem_karsiligi(base)
        if es:
            yok = [s["Point Name"] for s in bms if s.get("Durum") == OKUNAN and s.get("Point Name")
                   and s["Point Name"] not in es]
            if yok:
                uyarilar.append("Bilgi: %d okunan noktanın programda hesap karşılığı yok (%s…) — değer okunur ve "
                                "kaydedilir, hesaba girmez. Hesaba girmesi için STANDART NOKTA ADLARI'ndaki adı "
                                "kullanın." % (len(yok), ", ".join(yok[:5])))

    ahu = veri.get("ahu")
    if ahu is not None:
        gor = {}
        for i, s in enumerate(ahu, 1):
            yer = "AHU noktası %d (%s %s %s)" % (i, s.get("Bina") or "?", s.get("Santral") or "?",
                                                 s.get("Nokta Tipi") or "?")
            for a in ("Bina", "Santral", "Nokta Tipi"):
                if not s.get(a):
                    hatalar.append("%s: %s boş." % (yer, a))
            if s.get("Nokta Tipi") and s["Nokta Tipi"] not in NOKTA_TIPLERI:
                hatalar.append("%s: Nokta Tipi listede yok: %s" % (yer, s["Nokta Tipi"]))
            hatalar.extend(_adres_hatalari(yer, s, ()))
            k = (_katla(s.get("Bina")), _katla(s.get("Santral")), s.get("Nokta Tipi"))
            if all(k):
                if k in gor:
                    hatalar.append("%s: aynı santral + nokta tipi %d. satırda da var." % (yer, gor[k]))
                gor.setdefault(k, i)
    return hatalar, uyarilar


def _adres_hatalari(yer, s, ek):
    h = []
    if not _ip_gecerli(s.get("Gateway IP")):
        h.append("%s: Gateway IP geçersiz: %s" % (yer, s.get("Gateway IP")))
    if not _mac_gecerli(s.get("MAC (DADR)")):
        h.append("%s: MAC (DADR) 0x ile başlayan onaltılı olmalı (ör. 0x011C): %s" % (yer, s.get("MAC (DADR)")))
    for a in ("Network (DNET)", "Object Type", "Object Instance") + tuple(ek):
        if not isinstance(s.get(a), int) or s[a] < 0:
            h.append("%s: %s tamsayı olmalı: %s" % (yer, a, s.get(a)))
    return h


# ═══════════════════════════ önizleme ═══════════════════════════
def _anahtar(tur, s):
    if tur == "analizorler":
        return _katla(s.get("AD"))
    if tur == "bms":
        return (_katla(s.get("Point Name")), s.get("Durum") == OKUNAN)   # adres değişimi = "değişen"
    return (_katla(s.get("Bina")), _katla(s.get("Santral")), s.get("Nokta Tipi"))


def _etiket(tur, s):
    if tur == "analizorler":
        return "%s (%s)" % (s.get("AD"), s.get("IP ADRESI") or "IP yok")
    if tur == "bms":
        return "%s — %s" % (s.get("Point Name"), s.get("Durum"))
    return "%s %s · %s" % (s.get("Bina"), s.get("Santral"), s.get("Nokta Tipi"))


def fark(eski: dict, yeni: dict) -> dict:
    """{tur: {"eklenen": [...], "silinen": [...], "degisen": [(etiket, [(alan, eski, yeni)])]}}"""
    sonuc = {}
    for tur in SUTUNLAR:
        if tur not in yeni:
            continue
        e = {_anahtar(tur, s): s for s in eski.get(tur) or []}
        y = {_anahtar(tur, s): s for s in yeni[tur]}
        d = {"eklenen": [_etiket(tur, y[k]) for k in y if k not in e],
             "silinen": [_etiket(tur, e[k]) for k in e if k not in y], "degisen": []}
        for k in y:
            if k in e:
                alanlar = [(a, e[k].get(a), y[k].get(a)) for a in SUTUNLAR[tur]
                           if (e[k].get(a) or None) != (y[k].get(a) or None)]
                if alanlar:
                    d["degisen"].append((_etiket(tur, y[k]), alanlar))
        sonuc[tur] = d
    return sonuc


def fark_var(f: dict) -> bool:
    return any(d["eklenen"] or d["silinen"] or d["degisen"] for d in f.values())


def sutun_uret(ad: str, kullanilan=()) -> str:
    """Yeni sayacın energy_data sütunu: 'STEP-UP/3' → 'S_STEP_UP_3_kWh'. 'S_' öneki hesaplanan
    sütunlarla (Sebeke_kWh vb.) çakışmayı önler. Günlük değer bu sütundan sayac_gunluk'a gider."""
    govde = re.sub(r"_+", "_", re.sub(r"[^A-Za-z0-9]", "_", str(ad).translate(_TR).upper())).strip("_") or "SAYAC"
    aday, n = "S_%s_kWh" % govde, 2
    while aday in set(kullanilan):
        aday, n = "S_%s_%d_kWh" % (govde, n), n + 1
    return aday


_TUR_ETKI = {
    "trafo": "Şebeke toplamına (trafoların toplamı) eklenir. Şebekeden çekilmeyen enerjiyi ölçüyorsa "
             "(ör. kojen step-up trafosu) trafo SEÇMEYİN — çift sayım olur.",
    "sebeke": "Net şebeke giriş sayacı: Şebeke değeri bu sayaçtan hesaplanır. Lokasyonda tek olmalı.",
    "uretim": "Kojen / jeneratör üretim toplamına girer. Başka üretim sayaçlarının toplamını ölçüyorsa "
              "(ör. iki kojenin ortak step-up trafosu) 'kontrol' seçin — yoksa üretim iki kez sayılır.",
    "chiller": "Chiller tüketimine ve 'MCC + Chiller' toplamına girer.",
    "alt_sayac": "'MCC + Chiller' toplamına girer (MCC panosu, kule vb.).",
    "kontrol": "Hiçbir toplama girmez: okunur, günlük değeri kaydedilir ve merkezde görünür (karşılaştırma). "
               "Enerji yönden bağımsız okunur.",
}


def tur_uyarilari(eski: dict, yeni: dict) -> list:
    """Yeni eklenen ya da türü değişen (IP'li) analizörün hangi toplama girdiği — önizlemede gösterilir."""
    if "analizorler" not in yeni:
        return []
    once = {_katla(s.get("AD")): s.get("TÜR") for s in eski.get("analizorler") or [] if s.get("IP ADRESI")}
    cikti = []
    for s in yeni["analizorler"]:
        if s.get("IP ADRESI") and s.get("TÜR") in _TUR_ETKI and once.get(_katla(s.get("AD"))) != s["TÜR"]:
            cikti.append("%s → %s: %s" % (s.get("AD"), s["TÜR"], _TUR_ETKI[s["TÜR"]]))
    sebeke = [s["AD"] for s in yeni["analizorler"] if s.get("IP ADRESI") and s.get("TÜR") == "sebeke"]
    if len(sebeke) > 1:
        cikti.append("Birden çok 'sebeke' sayacı var (%s) — Şebeke değeri yalnız ilkinden hesaplanır."
                     % ", ".join(sebeke))
    return cikti


# ═══════════════════════════ kayıt ═══════════════════════════
def kaydet(veri: dict, base: str = None, kullanici: str = "", yeniden_baslat: bool = True) -> dict:
    """Doğrulanmış tabloları ayar dosyalarına yazar (yalnız veri'de olan tablolar).
    Hata varsa ValueError. Dönüş: {"yazilan": [...], "yedek": klasör}."""
    base = base or BURASI
    veri = normalize(veri)
    hatalar, _ = dogrula(veri, base)
    if hatalar:
        raise ValueError("Doğrulama hatası: " + "; ".join(hatalar[:5]))
    y = _yollar(base)
    eski = mevcut(base)
    f = fark(eski, veri)
    veri = {t: v for t, v in veri.items() if t in f and fark_var({t: f[t]})}   # yalnız değişen tablolar
    if not veri:
        return {"yazilan": [], "yedek": None, "ozet": {}}
    bekleyen = _json_oku(y["bekleyen"], {})
    if not isinstance(bekleyen, dict):
        bekleyen = {}
    yazilacak = {}

    if "analizorler" in veri:
        sj = _json_oku(y["sayac"], {})
        if not isinstance(sj, dict):
            sj = {"sayaclar": sj or []}
        onceki = list(sj.get("sayaclar") or [])
        ad_sutun = {_katla(s.get("ad")): s.get("sutun", "") for s in onceki}
        ip_sutun = {s.get("ip"): s.get("sutun", "") for s in onceki if s.get("ip")}
        liste, bek = [], []
        kullanilan = {x for x in list(ad_sutun.values()) + list(ip_sutun.values()) if x}
        for s in veri["analizorler"]:
            if not s.get("IP ADRESI"):
                bek.append(dict(s))
                continue
            sutun = ad_sutun.get(_katla(s["AD"]))
            if sutun is None:
                sutun = ip_sutun.get(s["IP ADRESI"])          # ad değişti, sayaç aynı: geçmiş sütun korunur
            if not sutun:
                sutun = sutun_uret(s["AD"], kullanilan)      # yeni sayaç: günlük değeri bu sütuna yazılır
                kullanilan.add(sutun)
            k = {"ad": s["AD"], "ip": s["IP ADRESI"], "marka": s["MARKA"].lower(), "tur": s["TÜR"],
                 "sutun": sutun or "", "kritik": s.get("KRİTİK") == "Evet"}
            if s.get("BİNA"):
                k["bina"] = s["BİNA"]
            if s.get("NOT"):
                k["not"] = s["NOT"]
            liste.append(k)
        sj["sayaclar"] = liste
        yazilacak[y["sayac"]] = (json.dumps(sj, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
        bekleyen["analizorler"] = bek

    if "bms" in veri:
        import openpyxl
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = SABLON_SAYFA
        ws.append(BMS_SUTUN[:-1])
        for s in veri["bms"]:
            if s["Durum"] == OKUNAN:
                ws.append([s[a] for a in BMS_SUTUN[:-1]])
        b = io.BytesIO()
        wb.save(b)
        yazilacak[y["sablon"]] = b.getvalue()
        bekleyen["bms"] = [dict(s) for s in veri["bms"] if s["Durum"] != OKUNAN]

    if "ahu" in veri:
        liste = [{"ahu_adi": s["Santral"], "lokasyon": s["Bina"], "nokta_tipi": s["Nokta Tipi"],
                  "gateway_ip": s["Gateway IP"], "dnet": s["Network (DNET)"], "mac_hex": s["MAC (DADR)"],
                  "obj_type": s["Object Type"], "obj_inst": s["Object Instance"]} for s in veri["ahu"]]
        yazilacak[y["nokta"]] = (json.dumps(liste, ensure_ascii=False, indent=1) + "\n").encode("utf-8")

    if "analizorler" in veri or "bms" in veri:
        bekleyen["_aciklama"] = ("Ayar paneli: henüz okunmayan donanım (IP'si olmayan analizör; 'okunacak' ve "
                                 "'yazılabilir değer' BMS noktaları). Program bu dosyayı OKUMAZ; liste kaybolmasın "
                                 "diye saklanır. Panelden düzenleyin.")
        yazilacak[y["bekleyen"]] = (json.dumps(bekleyen, ensure_ascii=False, indent=1) + "\n").encode("utf-8")

    degisen = yazilacak

    zaman = datetime.now().strftime("%Y%m%d_%H%M%S")
    yedek = os.path.join(yollar.klasor(YEDEK_KLASOR + "/", base), zaman)
    os.makedirs(yedek, exist_ok=True)
    for p in degisen:
        if os.path.exists(p):
            shutil.copy2(p, os.path.join(yedek, os.path.basename(p)))
    for p, icerik in degisen.items():
        _atomik_yaz(p, icerik)

    ozet = {t: {k: len(v) for k, v in d.items()} for t, d in f.items() if t in veri}
    try:
        g = yollar.yol(GUNLUK_DOSYA, base)
        os.makedirs(os.path.dirname(g), exist_ok=True)
        with open(g, "a", encoding="utf-8") as fh:
            fh.write(json.dumps({"zaman": datetime.now().isoformat(timespec="seconds"), "kullanici": kullanici,
                                 "dosyalar": [os.path.relpath(p, base) for p in degisen], "ozet": ozet,
                                 "yedek": os.path.relpath(yedek, base)}, ensure_ascii=False) + "\n")
    except OSError:
        pass
    if yeniden_baslat:
        try:
            with open(os.path.join(base, "_restart.flag"), "w", encoding="utf-8") as fh:
                fh.write("donanim paneli " + zaman)
        except OSError:
            pass
    return {"yazilan": [os.path.relpath(p, base) for p in degisen], "yedek": yedek, "ozet": ozet}


# ═══════════════════════════ Excel'e yazma (şablon / mevcut liste) ═══════════════════════════
def excel_yaz(veri: dict = None, lokasyon_adi: str = "", base: str = None) -> bytes:
    """Standart şablon biçiminde tek Excel. veri None ise boş şablon (örnek satırlı)."""
    import openpyxl
    from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
    from openpyxl.worksheet.datavalidation import DataValidation

    F = "Arial"
    bas_dolgu = PatternFill("solid", fgColor="012D75")
    girdi = PatternFill("solid", fgColor="FFF7D6")
    ince = Side(style="thin", color="C9D1E0")
    kenar = Border(left=ince, right=ince, top=ince, bottom=ince)
    bos = veri is None
    karsilik = sistem_karsiligi(base) if not bos else {}

    def sayfa(wb, ad, sutunlar, gen, satirlar, listeler):
        ws = wb.create_sheet(ad)
        for i, (s, g) in enumerate(zip(sutunlar, gen), 1):
            c = ws.cell(row=1, column=i, value=s)
            c.font = Font(name=F, bold=True, color="FFFFFF", size=10)
            c.fill = bas_dolgu
            c.border = kenar
            c.alignment = Alignment(horizontal="center", vertical="center", wrap_text=True)
            ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = g
        ws.row_dimensions[1].height = 30
        ws.freeze_panes = "A2"
        for r, satir in enumerate(satirlar, 2):
            for i, v in enumerate(satir, 1):
                c = ws.cell(row=r, column=i, value=v)
                c.font = Font(name=F, size=10)
                c.border = kenar
        son = max(len(satirlar) + 1, 2) + 200
        if bos:
            for r in range(len(satirlar) + 2, son + 1):
                for i in range(1, len(sutunlar) + 1):
                    c = ws.cell(row=r, column=i)
                    c.fill = girdi
                    c.border = kenar
        for kolon, secenek in listeler:
            dv = DataValidation(type="list", formula1='"%s"' % ",".join(secenek), allow_blank=True,
                                showErrorMessage=True, error="Listeden seçin: " + ", ".join(secenek))
            ws.add_data_validation(dv)
            dv.add("%s2:%s%d" % (kolon, kolon, son))
        return ws

    wb = openpyxl.Workbook()
    wb.remove(wb.active)
    if bos:
        an = [["TRDP-1", "10.20.30.41", "A-BLOK", "Janitza", "trafo", "Evet", "ÖRNEK SATIR — silip kendi satırlarınızı girin"]]
        bms = [["10.20.30.2", 2, "0x011C", 2098211, 0, 33, "DIS HAVA", OKUNAN, None]]
        ahu = [["A-BLOK", "Ahu-1", "SAT (°C)", "10.20.30.8", 16, "0x0101", 0, 22]]
    else:
        an = [[s.get(a) for a in AN_SUTUN] for s in veri.get("analizorler") or []]
        bms = [[s.get(a) for a in BMS_SUTUN] + [karsilik.get(s.get("Point Name"))
                                                 or ("oto-set yazar" if s.get("Durum") == YAZILABILIR else None)]
               for s in veri.get("bms") or []]
        ahu = [[s.get(a) for a in AHU_SUTUN] for s in veri.get("ahu") or []]
    sayfa(wb, "ANALIZORLER", AN_SUTUN, [18, 16, 10, 12, 12, 9, 60], an,
          [("D", MARKALAR), ("E", TURLER), ("F", EVET_HAYIR)])
    sayfa(wb, "SAHA OKUMA LISTESI", BMS_SUTUN + ["Sistem karşılığı"], [15, 12, 12, 16, 11, 12, 34, 18, 40], bms,
          [("H", DURUMLAR)])
    sayfa(wb, "AHU NOKTALARI", AHU_SUTUN, [10, 12, 18, 15, 12, 12, 11, 12], ahu, [("C", NOKTA_TIPLERI)])
    ws = wb.create_sheet("ACIKLAMA")
    ws.column_dimensions["A"].width = 24
    ws.column_dimensions["B"].width = 100
    ws["A1"] = "Lokasyon donanımı" + (" — " + lokasyon_adi if lokasyon_adi else "") + \
               (" (boş şablon)" if bos else " (%s)" % datetime.now().strftime("%d.%m.%Y %H:%M"))
    ws["A1"].font = Font(name=F, bold=True, size=13, color="012D75")
    for r, (a, b) in enumerate([
        ("Nasıl doldurulur", "Her sayfa bir liste. Seçimli sütunlarda açılır listeden seçin. İlk satırdaki sütun "
                             "adlarını değiştirmeyin. Doldurulan dosyayı Enerji portalı → Lokasyon Donanımı "
                             "panelinden yükleyin; panel doğrular, önizleme gösterir, onaydan sonra kaydeder."),
        ("ANALIZORLER", "AD tekil ve kalıcı (geçmiş veri bu adla tutulur). IP'si olmayan satır bekleyen "
                        "listede durur, okunmaz. TÜR: trafo · sebeke · uretim (kojen) · chiller · alt_sayac · kontrol "
                        "(okunur, hiçbir toplama girmez; ör. iki kojenin ortak step-up sayacı)."),
        ("SAHA OKUMA LISTESI", "Durum: okunan değer = program okur · yazılabilir değer = oto-set yazar (bu panel "
                               "değiştirmez, yalnız listeler) · okunacak = henüz okunmuyor."),
        ("AHU NOKTALARI", "Mekanik Zeka'nın okuduğu santral noktaları. Bina + Santral + Nokta Tipi tekil olmalı."),
        ("Sistem karşılığı", "Bilgi sütunu (program doldurur); yüklemede okunmaz."),
    ], 3):
        ws.cell(row=r, column=1, value=a).font = Font(name=F, bold=True, size=10)
        c = ws.cell(row=r, column=2, value=b)
        c.font = Font(name=F, size=10)
        c.alignment = Alignment(wrap_text=True, vertical="top")
    out = io.BytesIO()
    wb.save(out)
    return out.getvalue()


def son_kayitlar(base: str = None, adet: int = 5) -> list:
    """Panelden yapılan son kayıtlar (yeniden başlatmadan sonra da görünsün diye dosyadan)."""
    try:
        with open(yollar.yol(GUNLUK_DOSYA, base or BURASI), encoding="utf-8") as f:
            satirlar = f.read().split(chr(10))
    except OSError:
        return []
    cikti = []
    for s in reversed([x for x in satirlar if x.strip()]):
        try:
            cikti.append(json.loads(s))
        except ValueError:
            continue
        if len(cikti) >= adet:
            break
    return cikti


# ═══════════════════════════ şifre ═══════════════════════════
_TUR_SAYISI = 200_000


def sifre_var(base: str = None) -> bool:
    d = _json_oku(yollar.yol(SIFRE_DOSYA, base or BURASI), {})
    return isinstance(d, dict) and bool(d.get("ozet")) and bool(d.get("tuz"))


def sifre_belirle(sifre: str, base: str = None):
    if len(sifre or "") < 6:
        raise ValueError("Şifre en az 6 karakter olmalı.")
    tuz = os.urandom(16)
    ozet = hashlib.pbkdf2_hmac("sha256", sifre.encode("utf-8"), tuz, _TUR_SAYISI)
    p = yollar.yol(SIFRE_DOSYA, base or BURASI)
    _atomik_yaz(p, json.dumps({"tuz": tuz.hex(), "ozet": ozet.hex(), "tur": _TUR_SAYISI,
                               "tarih": datetime.now().isoformat(timespec="seconds")}).encode("utf-8"))


def sifre_dogru(sifre: str, base: str = None) -> bool:
    d = _json_oku(yollar.yol(SIFRE_DOSYA, base or BURASI), {})
    try:
        ozet = hashlib.pbkdf2_hmac("sha256", (sifre or "").encode("utf-8"), bytes.fromhex(d["tuz"]),
                                   int(d.get("tur") or _TUR_SAYISI))
        return hmac.compare_digest(ozet.hex(), d["ozet"])
    except (KeyError, TypeError, ValueError):
        return False
