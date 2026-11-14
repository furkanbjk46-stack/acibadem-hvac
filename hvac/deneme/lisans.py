# lisans.py
# Makine ID tabanlı lisans dogrulama sistemi
# Supabase'deki 'lisanslar' tablosunu kontrol eder

from __future__ import annotations
import yollar  # dosya yolları (ayar/ durum/ veri/; Faz 1)
import subprocess, json, os, sys
from pathlib import Path

# ── Makine ID ────────────────────────────────────────
def _anakart_uuid():
    """Anakart (SMBIOS) UUID'si; okunamazsa None.

    Önce wmic; yeni Windows 11 sürümlerinde wmic kaldırıldığı için (12.11.2026: geliştirme PC'sinde
    yok) PowerShell'den aynı değer okunur — 'wmic csproduct' = Win32_ComputerSystemProduct, aynı UUID.
    """
    komutlar = (
        "wmic csproduct get uuid",
        'powershell -NoProfile -NonInteractive -Command "(Get-CimInstance -ClassName '
        'Win32_ComputerSystemProduct).UUID"',
    )
    for komut in komutlar:
        try:
            cikti = subprocess.check_output(komut, shell=True, stderr=subprocess.DEVNULL,
                                            timeout=30).decode(errors="ignore")
        except Exception:
            continue
        for line in cikti.splitlines():
            uid = line.strip()
            if uid and uid.upper() != "UUID":
                return uid
    return None


def makine_kimlikleri() -> list:
    """Bu PC'nin kabul edilen kimlikleri: [anakart UUID, ağ kartı adresi] (tekrarsız).

    Lisans ikisinden biriyle tanımlı olabilir: wmic'in olmadığı PC eskiden ağ kartı adresine düşüyordu.
    Kontrol ikisini de sorar; böyle lisanslanmış bir PC UUID okunabilir olunca da çalışmaya devam eder.
    """
    import uuid
    kimlikler = [k for k in (_anakart_uuid(), str(uuid.getnode())) if k]
    return list(dict.fromkeys(kimlikler))


def get_makine_id() -> str:
    """Lisans için gösterilen / kaydedilen kimlik: anakart UUID'si, okunamazsa ağ kartı adresi."""
    return makine_kimlikleri()[0]


# ── Supabase config ───────────────────────────────────
CONFIG_PATH = Path(yollar.yol("supabase_config.json", str(Path(__file__).parent)))

def _load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ── Lisans kontrolu ───────────────────────────────────
# Açılışta ağ henüz hazır değilse (PC yeni açıldı, ad çözümleme gecikiyor) tek deneme
# "getaddrinfo failed" ile düşüp programı HİÇ başlatmıyordu (11.11.2026, Maslak).
# Yalnızca BAĞLANTI hatası yeniden denenir; "lisans yok / pasif" cevabı hemen döner.
# Watchdog'un alt süreçlerinde (Enerji portalı her sayfa etkileşiminde çağırır) yeniden
# deneme YAPILMAZ: aksi halde bağlantı sorununda her tıklama 1 dk beklerdi.
BAGLANTI_DENEME = 6
BAGLANTI_BEKLEME_SN = 10
# Geçerli sonuç süreç belleğinde tutulur: Enerji portalı her etkileşimde yeniden sorup
# her tıklamaya bir ağ isteği ekliyordu. Geçersiz/hatalı sonuç tutulmaz.
GECERLI_ONBELLEK_SN = 600
_SON_GECERLI = {"zaman": 0.0, "sonuc": None}


def lisans_kontrol(deneme: int = None, bekleme: float = None, _bekle=None) -> dict:
    """Bağlantı hatasında yeniden dener (watchdog açılışında 6 × 10 sn ≈ 1 dk).
    Geçerli sonuç GECERLI_ONBELLEK_SN boyunca bellekten döner. Dönüş: _lisans_kontrol_tek ile aynı."""
    import time
    if _SON_GECERLI["sonuc"] and time.monotonic() - _SON_GECERLI["zaman"] < GECERLI_ONBELLEK_SN:
        return dict(_SON_GECERLI["sonuc"])
    if deneme is None:
        deneme = 1 if os.environ.get("HVAC_WATCHDOG") == "1" else BAGLANTI_DENEME
    deneme = max(1, int(deneme))
    bekleme = BAGLANTI_BEKLEME_SN if bekleme is None else bekleme
    _bekle = _bekle or time.sleep
    sonuc = None
    for i in range(deneme):
        sonuc = _lisans_kontrol_tek()
        if sonuc.get("gecerli"):
            _SON_GECERLI.update({"zaman": time.monotonic(), "sonuc": dict(sonuc)})
        if sonuc.get("gecerli") or not str(sonuc.get("hata") or "").startswith("Lisans sunucusuna"):
            return sonuc                        # geçerli, ya da kesin "lisans yok" cevabı
        if i < deneme - 1:
            print("Lisans sunucusuna ulasilamadi (%d/%d), %d sn sonra tekrar denenecek..."
                  % (i + 1, deneme, bekleme), flush=True)
            _bekle(bekleme)
    return sonuc


# ── Lisans talebi (008_lisans_talepleri, 14.11.2026) ─────────────────────────────────
# Lisansı olmayan PC merkeze kendisi talep bırakır (makine kimliği, lokasyon, bilgisayar adı);
# Synapse → Yönetim → Lisanslar'da onaylanınca lisans aktif açılır ve watchdog (onay beklerken
# dakikada bir yeniden sorar) programı kendiliğinden başlatır. Makine ID kimseye okutulmaz.
TALEP_MESAJ = {
    "bekliyor": "Lisans onayi bekleniyor — talep Synapse'e gonderildi (Yonetim > Lisanslar'dan onaylanacak).",
    "reddedildi": "Bu cihazin lisans talebi Synapse'te reddedildi (Yonetim > Lisanslar).",
    "sinir": "Bu lokasyonda cok sayida bekleyen lisans talebi var; Synapse'te bekleyenleri karara baglayin.",
}


def _surum() -> str:
    for goreli in ("durum/son_yama.json", "yama_surumu.json"):
        try:
            with open(Path(__file__).parent.joinpath(*goreli.split("/")), encoding="utf-8") as f:
                v = (json.load(f) or {}).get("versiyon")
            if v:
                return str(v)
        except (OSError, ValueError):
            continue
    return ""


def talep_birak(sb, lokasyon_id: str, kimlikler: list) -> str | None:
    """Merkeze lisans talebi bırakır / tazeler. Dönüş: 'bekliyor' | 'reddedildi' | 'aktif' | 'sinir';
    merkezde işlev yoksa (008 uygulanmamış) ya da hata varsa None — eski davranış sürer."""
    if not lokasyon_id or not kimlikler:
        return None
    try:
        import socket
        r = sb.rpc("lisans_talep_et", {
            "p_lokasyon": lokasyon_id, "p_makine": kimlikler[0], "p_kimlikler": list(kimlikler),
            "p_makine_adi": socket.gethostname()[:80], "p_surum": _surum()}).execute()
        d = r.data
        return d if isinstance(d, str) else None
    except Exception:
        return None


def _lisans_kontrol_tek() -> dict:
    """
    Donus: {
        "gecerli": True/False,
        "makine_id": "...",
        "lokasyon_id": "...",
        "hata": None / "hata mesaji"
    }
    """
    kimlikler = makine_kimlikleri()
    makine_id = kimlikler[0]

    # supabase_config.json yoksa: GELISTIRME ORTAMI — lisans kontrolu atlanir.
    # (Lokasyon PC'lerinde bu dosya her zaman vardir; sadece dev/repo'da yoktur.)
    if not CONFIG_PATH.exists():
        return {
            "gecerli": True,
            "makine_id": makine_id,
            "lokasyon_id": "",
            "makine_adi": "Gelistirme Ortami (config yok)",
            "hata": None,
        }

    try:
        cfg = _load_config()
        url = cfg["supabase_url"]
        key = cfg["supabase_key"]
        import location_manager as _lm_k   # kimlik: lokasyon profili (Faz 1)
        lok_id = _lm_k.lokasyon_id(str(CONFIG_PATH.parent.parent) if CONFIG_PATH.parent.name == "ayar"
                                   else str(CONFIG_PATH.parent), cfg.get("lokasyon_id", ""))

        from supabase import create_client
        try:  # lokasyon anahtarı varsa istekler onunla imzalanır (sb_kimlik.py)
            import sb_kimlik
            sb = sb_kimlik.istemci(url, key)
        except ImportError:
            sb = create_client(url, key)

        sonuc = (
            sb.table("lisanslar")
            .select("aktif, lokasyon_id, makine_adi, makine_id")
            .in_("makine_id", kimlikler)
            .eq("lokasyon_id", lok_id)
            .execute()
        )
        satirlar = sonuc.data if isinstance(sonuc.data, list) else ([sonuc.data] if sonuc.data else [])
        aktif = [s for s in satirlar if s.get("aktif")]

        if aktif:
            return {
                "gecerli": True,
                "makine_id": aktif[0].get("makine_id") or makine_id,
                "lokasyon_id": lok_id,
                "makine_adi": aktif[0].get("makine_adi", ""),
                "hata": None,
            }
        else:
            talep = talep_birak(sb, lok_id, kimlikler)
            return {
                "gecerli": False,
                "makine_id": makine_id,
                "lokasyon_id": lok_id,
                "talep": talep,
                "hata": TALEP_MESAJ.get(talep, "Bu cihaz icin lisans tanimli degil veya pasif."),
            }

    except Exception as e:
        err = str(e)
        # Tablo bulunamazsa (ilk kurulum) gec
        if "no rows" in err.lower() or "pgrst116" in err.lower():
            return {
                "gecerli": False,
                "makine_id": makine_id,
                "lokasyon_id": lok_id if "lok_id" in dir() else "",
                "hata": "Lisans bulunamadi. Lutfen yetkili ile iletisime gecin.",
            }
        return {
            "gecerli": False,
            "makine_id": makine_id,
            "lokasyon_id": "",
            "hata": f"Lisans sunucusuna baglanılamadi: {err}",
        }
