# lisans.py
# Makine ID tabanlı lisans dogrulama sistemi
# Supabase'deki 'lisanslar' tablosunu kontrol eder

from __future__ import annotations
import subprocess, json, os, sys
from pathlib import Path

# ── Makine ID ────────────────────────────────────────
def get_makine_id() -> str:
    """Windows motherboard UUID'sini dondurur."""
    try:
        result = subprocess.check_output(
            "wmic csproduct get uuid",
            shell=True, stderr=subprocess.DEVNULL
        ).decode().strip().split("\n")
        for line in result:
            uid = line.strip()
            if uid and uid.upper() != "UUID":
                return uid
    except Exception:
        pass
    # Fallback: MAC adresi
    import uuid
    return str(uuid.getnode())


# ── Supabase config ───────────────────────────────────
CONFIG_PATH = Path(__file__).parent / "supabase_config.json"

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


def _lisans_kontrol_tek() -> dict:
    """
    Donus: {
        "gecerli": True/False,
        "makine_id": "...",
        "lokasyon_id": "...",
        "hata": None / "hata mesaji"
    }
    """
    makine_id = get_makine_id()

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
        lok_id = cfg.get("lokasyon_id", "")

        from supabase import create_client
        try:  # lokasyon anahtarı varsa istekler onunla imzalanır (sb_kimlik.py)
            import sb_kimlik
            sb = sb_kimlik.istemci(url, key)
        except ImportError:
            sb = create_client(url, key)

        sonuc = (
            sb.table("lisanslar")
            .select("aktif, lokasyon_id, makine_adi")
            .eq("makine_id", makine_id)
            .eq("lokasyon_id", lok_id)
            .single()
            .execute()
        )

        if sonuc.data and sonuc.data.get("aktif"):
            return {
                "gecerli": True,
                "makine_id": makine_id,
                "lokasyon_id": lok_id,
                "makine_adi": sonuc.data.get("makine_adi", ""),
                "hata": None,
            }
        else:
            return {
                "gecerli": False,
                "makine_id": makine_id,
                "lokasyon_id": lok_id,
                "hata": "Bu cihaz icin lisans tanimli degil veya pasif.",
            }

    except Exception as e:
        err = str(e)
        # Tablo bulunamazsa (ilk kurulum) gec
        if "no rows" in err.lower() or "pgrst116" in err.lower():
            return {
                "gecerli": False,
                "makine_id": makine_id,
                "lokasyon_id": cfg.get("lokasyon_id", "") if "cfg" in dir() else "",
                "hata": "Lisans bulunamadi. Lutfen yetkili ile iletisime gecin.",
            }
        return {
            "gecerli": False,
            "makine_id": makine_id,
            "lokasyon_id": "",
            "hata": f"Lisans sunucusuna baglanılamadi: {err}",
        }
