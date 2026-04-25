# veri_toplayici.py
# BACnet/IP ve Modbus TCP noktalarından otomatik veri toplar,
# energy_data.csv'ye günlük UPSERT yapar.
# Gereksinim: pip install BAC0 pymodbus pandas

from __future__ import annotations

import asyncio
import csv
import json
import logging
import os
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

BASE_DIR    = Path(__file__).parent
HARITA_FILE = BASE_DIR / "configs" / "nokta_haritasi.json"
DATA_FILE   = BASE_DIR / "energy_data.csv"

# energy_data.csv sütun sırası (Excel import ile uyumlu)
SUTUN_SIRASI = [
    "Tarih",
    "Chiller_Set_Temp_C",
    "Chiller_Adet",
    "Absorption_Chiller_Adet",
    "Kazan_Adet",
    "Mas1_Isitma_Temp",
    "Mas1_Kazan_Temp",
    "Mas1_Sogutma_Temp",
    "Mas2_Isitma_Temp",
    "Mas2_Kazan_Temp",
    "Mas2_Sogutma_Temp",
    "Kar_Eritme_Aktif",
    "Sebeke_Tuketim_kWh",
    "Kojen_Uretim_kWh",
    "Kazan_Dogalgaz_m3",
    "Kojen_Dogalgaz_m3",
    "Su_Tuketimi_m3",
    "Chiller_Tuketim_kWh",
    "MCC_Tuketim_kWh",
    "VRF_Split_Tuketim_kWh",
    "Dis_Hava_Sicakligi_C",
    "Chiller_Load_Percent",
    "Toplam_Hastane_Tuketim_kWh",
    "Toplam_Sogutma_Tuketim_kWh",
    "Diger_Yuk_kWh",
]


# ── Config yükleme ────────────────────────────────────────


def _load_harita() -> dict[str, Any]:
    with open(HARITA_FILE, encoding="utf-8") as f:
        return json.load(f)


def _load_bacnet_config() -> dict[str, Any]:
    bacnet_cfg_path = BASE_DIR / "configs" / "bacnet_points.json"
    if bacnet_cfg_path.exists():
        with open(bacnet_cfg_path, encoding="utf-8") as f:
            return json.load(f)
    return {}


# ── pymodbus uyumluluk ────────────────────────────────────


def _pymodbus_major() -> int:
    try:
        import pymodbus
        return int(pymodbus.__version__.split(".")[0])
    except Exception:
        return 3


def _mk(slave: int) -> dict:
    return {"slave": slave} if _pymodbus_major() >= 3 else {"unit": slave}


# ── Modbus okuma ──────────────────────────────────────────


def _oku_modbus(nokta: dict[str, Any]) -> float | None:
    try:
        from pymodbus.client import ModbusTcpClient
    except ImportError:
        logger.warning("pymodbus yuklu degil: pip install pymodbus")
        return None

    ip     = nokta["ip"]
    port   = nokta.get("port", 502)
    slave  = nokta.get("slave", 1)
    rtype  = nokta.get("register_type", "input")
    reg    = nokta.get("register", 0)
    count  = nokta.get("register_count", 2)
    scale  = nokta.get("scale", 1.0)
    fmt    = nokta.get("veri_formati", "uint16")

    client = ModbusTcpClient(ip, port=port)
    try:
        if not client.connect():
            logger.warning(f"Modbus baglanti hatasi: {ip}:{port}")
            return None

        kw = _mk(slave)
        if rtype == "holding":
            rr = client.read_holding_registers(reg, count=count, **kw)
        else:
            rr = client.read_input_registers(reg, count=count, **kw)

        if rr.isError():
            logger.warning(f"Modbus okuma hatasi ({ip} reg={reg}): {rr}")
            return None

        regs = rr.registers
        if fmt == "uint32_hi_lo" and len(regs) >= 2:
            raw = (regs[0] << 16) | regs[1]
        elif fmt == "uint32_lo_hi" and len(regs) >= 2:
            raw = (regs[1] << 16) | regs[0]
        else:
            raw = regs[0]

        return round(raw * scale, 4)

    except Exception as e:
        logger.error(f"Modbus istisna ({ip}): {e}")
        return None
    finally:
        client.close()


# ── BACnet okuma ──────────────────────────────────────────


async def _oku_bacnet_noktalar(
    nokta_listesi: list[tuple[str, dict]],
    bacnet_cfg: dict,
) -> dict[str, Any]:
    """
    nokta_listesi: [(sutun_adi, nokta_def), ...]
    Döner: {sutun_adi: deger}
    """
    try:
        import BAC0
    except ImportError:
        logger.error("BAC0 yuklu degil: pip install BAC0")
        return {}

    device_ips   = bacnet_cfg.get("device_ips", {})
    local_port   = bacnet_cfg.get("local_port", 47809)
    desigo_port  = bacnet_cfg.get("desigo_port", 47808)

    import socket
    def _local_ip(target: str) -> str:
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
                s.connect((target, 1))
                return s.getsockname()[0]
        except Exception:
            return ""

    any_ip = next((v for v in device_ips.values() if v), "")
    local_ip = _local_ip(any_ip) if any_ip else ""

    try:
        bacnet = BAC0.lite(ip=f"{local_ip}/24", port=local_port) if local_ip else BAC0.lite(port=local_port)
        await asyncio.sleep(3)
    except Exception as e:
        logger.error(f"BAC0 baslatılamadi: {e}")
        return {}

    # Gereken cihaz ID'lerini topla
    needed_ids: set[int] = set()
    for _, nd in nokta_listesi:
        did = nd.get("device") or (nd.get("sayim_noktalari", [{}])[0] if nd.get("sayim_noktalari") else {}).get("device")
        if did and device_ips.get(str(did)):
            needed_ids.add(int(did))

    # Unicast Who-Is
    scan_ips = list({v for v in device_ips.values() if v})
    for ip in scan_ips:
        for dev_id in needed_ids:
            try:
                await bacnet.who_is(
                    low_limit=dev_id, high_limit=dev_id,
                    address=f"{ip}:{desigo_port}"
                )
            except Exception:
                pass
    await asyncio.sleep(8)

    raw_disc = getattr(bacnet, "discoveredDevices", None) or {}
    device_addresses: dict[str, str] = {}
    for dev_id in needed_ids:
        if dev_id in raw_disc:
            info = raw_disc[dev_id]
            addr = info.get("address", str(info)) if isinstance(info, dict) else str(info)
            device_addresses[str(dev_id)] = addr
        else:
            logger.warning(f"BACnet cihaz {dev_id} bulunamadi.")

    async def _oku(nd: dict) -> float | None:
        dev_id = str(nd.get("device", ""))
        addr   = device_addresses.get(dev_id)
        if not addr:
            return None
        adres = f"{addr} {nd['type']}:{nd['instance']} presentValue"
        try:
            return float(await bacnet.read(adres))
        except Exception as e:
            logger.warning(f"BACnet okuma hatasi ({adres}): {e}")
            return None

    sonuclar: dict[str, Any] = {}
    for sutun, nd in nokta_listesi:
        deger_tipi = nd.get("deger_tipi", "anlik")

        if deger_tipi == "sayim":
            # Kaç nokta aktif → sayı döndür
            adet = 0
            for np in nd.get("sayim_noktalari", []):
                val = await _oku(np)
                if val is not None and val > 0:
                    adet += 1
            sonuclar[sutun] = adet

        elif deger_tipi == "anlik":
            val = await _oku(nd)
            if val is not None:
                sonuclar[sutun] = val

        # sayac tipi BACnet için de kullanılabilir (ham değer — delta hesabı ayrıca yapılır)
        elif deger_tipi == "sayac":
            val = await _oku(nd)
            if val is not None:
                sonuclar[f"_ham_{sutun}"] = val

    try:
        bacnet.disconnect()
    except Exception:
        pass

    return sonuclar


# ── Sayaç delta hesabı ────────────────────────────────────

_SAYAC_CACHE_FILE = BASE_DIR / "configs" / "_sayac_cache.json"


def _sayac_cache_oku() -> dict[str, float]:
    if _SAYAC_CACHE_FILE.exists():
        try:
            with open(_SAYAC_CACHE_FILE, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def _sayac_cache_yaz(cache: dict[str, float]) -> None:
    _SAYAC_CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(_SAYAC_CACHE_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def _sayac_delta(sutun: str, yeni_deger: float) -> float | None:
    """
    Sayaç için gün başı ile gün sonu farkını hesaplar.
    İlk okumada sadece cache'e yazar, None döner.
    """
    cache = _sayac_cache_oku()
    eski  = cache.get(sutun)
    cache[sutun] = yeni_deger
    _sayac_cache_yaz(cache)

    if eski is None:
        return None

    delta = yeni_deger - eski
    if delta < 0:
        logger.warning(f"Sayac geri gitmis ({sutun}): eski={eski} yeni={yeni_deger} — sifirlanmis olabilir.")
        return None
    return round(delta, 4)


# ── Hesaplanan alanlar ────────────────────────────────────


def _hesapla(formul: str, satirli: dict[str, Any]) -> float | None:
    try:
        env = {k: v for k, v in satirli.items() if isinstance(v, (int, float))}
        return round(eval(formul, {"__builtins__": {}}, env), 4)  # noqa: S307
    except Exception as e:
        logger.debug(f"Hesap hatasi ({formul}): {e}")
        return None


# ── Tek veri toplama turu ─────────────────────────────────


async def _async_topla() -> dict[str, Any]:
    harita      = _load_harita()
    bacnet_cfg  = _load_bacnet_config()
    sutun_har   = harita.get("sutun_haritasi", {})

    # Aktif noktaları kaynak tipine göre ayır
    bacnet_noktalar: list[tuple[str, dict]] = []
    modbus_noktalar: list[tuple[str, dict]] = []
    hesap_noktalar:  list[tuple[str, dict]] = []

    for sutun, nd in sutun_har.items():
        if not nd.get("etkin", True):
            continue
        kaynak = nd.get("kaynak", "bacnet")
        if kaynak == "bacnet":
            bacnet_noktalar.append((sutun, nd))
        elif kaynak == "modbus":
            modbus_noktalar.append((sutun, nd))
        elif kaynak == "hesap":
            hesap_noktalar.append((sutun, nd))

    satir: dict[str, Any] = {}

    # BACnet noktaları
    if bacnet_noktalar:
        logger.info(f"BACnet: {len(bacnet_noktalar)} nokta okunuyor...")
        bc_sonuc = await _oku_bacnet_noktalar(bacnet_noktalar, bacnet_cfg)
        for sutun, nd in bacnet_noktalar:
            deger_tipi = nd.get("deger_tipi", "anlik")
            if deger_tipi == "sayac":
                ham = bc_sonuc.get(f"_ham_{sutun}")
                if ham is not None:
                    delta = _sayac_delta(sutun, ham)
                    if delta is not None:
                        satir[sutun] = delta
            else:
                if sutun in bc_sonuc:
                    satir[sutun] = bc_sonuc[sutun]

    # Modbus noktaları (thread pool içinde, BACnet'in aksine sync)
    if modbus_noktalar:
        logger.info(f"Modbus: {len(modbus_noktalar)} nokta okunuyor...")
        loop = asyncio.get_event_loop()
        for sutun, nd in modbus_noktalar:
            val = await loop.run_in_executor(None, _oku_modbus, nd)
            if val is None:
                continue
            if nd.get("deger_tipi") == "sayac":
                delta = _sayac_delta(sutun, val)
                if delta is not None:
                    satir[sutun] = delta
            else:
                satir[sutun] = val

    # Hesaplanan alanlar (diğerleri tamamlandıktan sonra)
    for sutun, nd in hesap_noktalar:
        formul = nd.get("formul", "")
        val    = _hesapla(formul, satir)
        if val is not None:
            satir[sutun] = val

    return satir


def topla() -> dict[str, Any]:
    """Sync wrapper — thread içinden çağrılabilir."""
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        return loop.run_until_complete(_async_topla())
    finally:
        loop.close()
        asyncio.set_event_loop(None)


# ── energy_data.csv UPSERT ────────────────────────────────


def upsert_energy_data(tarih: date, degerler: dict[str, Any]) -> str:
    """
    energy_data.csv'ye tarih bazlı UPSERT yapar.
    Satır varsa günceller, yoksa ekler.
    Döner: "eklendi" | "guncellendi" | "bos"
    """
    if not degerler:
        logger.warning("Hic veri yok, UPSERT atlandi.")
        return "bos"

    tarih_str = tarih.strftime("%Y-%m-%d")

    # Mevcut veriyi yükle
    if DATA_FILE.exists():
        df = pd.read_csv(DATA_FILE, dtype=str)
    else:
        df = pd.DataFrame(columns=SUTUN_SIRASI)

    # Güncel sütunlar + yeni sütunlar birleştir
    for col in SUTUN_SIRASI:
        if col not in df.columns:
            df[col] = ""

    yeni_satir = {col: "" for col in SUTUN_SIRASI}
    yeni_satir["Tarih"] = tarih_str
    for k, v in degerler.items():
        if k in yeni_satir:
            yeni_satir[k] = "" if v is None else str(v)

    eslesme = df["Tarih"] == tarih_str
    if eslesme.any():
        # Sadece dolu alanları güncelle (boş gelenleri ezme)
        for k, v in yeni_satir.items():
            if v != "":
                df.loc[eslesme, k] = v
        durum = "guncellendi"
    else:
        yeni_df = pd.DataFrame([yeni_satir])
        df = pd.concat([df, yeni_df], ignore_index=True)
        durum = "eklendi"

    df = df[SUTUN_SIRASI]
    df.to_csv(DATA_FILE, index=False, encoding="utf-8")
    logger.info(f"energy_data.csv {durum}: {tarih_str}  ({len(degerler)} alan)")
    return durum


# ── Arka plan servisi ─────────────────────────────────────

_thread: threading.Thread | None = None
_stop   = threading.Event()


def baslat() -> None:
    """
    Portal başladığında çağrılır.
    Yapılandırılan saatte günlük veri toplar ve energy_data.csv'ye yazar.
    """
    global _thread

    if _thread and _thread.is_alive():
        return

    if not HARITA_FILE.exists():
        logger.warning("nokta_haritasi.json bulunamadi — veri_toplayici pasif.")
        return

    harita = _load_harita()
    kayit_saati   = harita.get("zamanlama", {}).get("kayit_saati", "23:50")
    kontrol_dk    = harita.get("zamanlama", {}).get("okuma_araligi_dk", 60)
    geri_doldur_h = harita.get("zamanlama", {}).get("geri_doldur_saat", 1)

    _stop.clear()

    def _loop():
        logger.info(f"Veri toplayici basladi — kayit saati={kayit_saati}, kontrol={kontrol_dk}dk")
        son_tarih: date | None = None

        while not _stop.is_set():
            simdi = datetime.now()
            bugun = simdi.date()

            # Kayıt saatinde veya geri doldurma penceresinde tetikle
            saat_str = simdi.strftime("%H:%M")
            h, m     = map(int, kayit_saati.split(":"))
            kayit_dt = simdi.replace(hour=h, minute=m, second=0, microsecond=0)
            geri_bas = kayit_dt - timedelta(hours=geri_doldur_h)

            tetikle = (geri_bas.strftime("%H:%M") <= saat_str <= kayit_saati) and son_tarih != bugun

            if tetikle:
                logger.info(f"Veri toplama baslıyor ({bugun})...")
                try:
                    degerler = topla()
                    durum    = upsert_energy_data(bugun, degerler)
                    son_tarih = bugun
                    logger.info(f"Tamamlandi: {bugun} — {durum}, {len(degerler)} alan.")
                except Exception as e:
                    logger.error(f"Toplama hatasi: {e}")

            _stop.wait(kontrol_dk * 60)

    _thread = threading.Thread(target=_loop, daemon=True, name="veri-toplayici")
    _thread.start()


def durdur() -> None:
    _stop.set()


# ── Komut satırı ─────────────────────────────────────────

if __name__ == "__main__":
    import sys

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    if not HARITA_FILE.exists():
        print(f"HATA: {HARITA_FILE} bulunamadi.")
        sys.exit(1)

    tarih_arg = date.today()
    if len(sys.argv) > 1:
        try:
            tarih_arg = date.fromisoformat(sys.argv[1])
        except ValueError:
            print(f"HATA: Gecersiz tarih formatı: {sys.argv[1]}  (beklenen: YYYY-MM-DD)")
            sys.exit(1)

    print(f"\n=== Veri Toplama ({tarih_arg}) ===\n")
    degerler = topla()

    print("\nOkunan değerler:")
    for k, v in degerler.items():
        print(f"  {k}: {v}")

    if degerler:
        durum = upsert_energy_data(tarih_arg, degerler)
        print(f"\n→ energy_data.csv: {durum}")
    else:
        print("\n⚠ Hiç aktif/erişilebilir nokta yok. nokta_haritasi.json içinde 'etkin': true olan noktaları kontrol edin.")
