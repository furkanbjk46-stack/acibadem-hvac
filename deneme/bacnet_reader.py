# bacnet_reader.py
# BACnet/IP + Modbus TCP → HVAC analiz + energy_data.csv otomatik kayıt.
# Tüm yapılandırma configs/bacnet_points.json dosyasından okunur.
# Gereksinim: pip install BAC0 pymodbus pandas

from __future__ import annotations

import asyncio
import csv
import json
import logging
import socket
import threading
import time
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

logger = logging.getLogger(__name__)

BASE_DIR   = Path(__file__).parent
CFG_FILE   = BASE_DIR / "configs" / "bacnet_points.json"
ENERGY_CSV = BASE_DIR / "energy_data.csv"
HVAC_CSV   = BASE_DIR / "hvac_analysis_history.csv"
BELIMO_CSV = BASE_DIR / "belimo_data.csv"
SAYAC_CACHE = BASE_DIR / "configs" / "_sayac_cache.json"

ENERGY_SUTUNLAR = [
    "Tarih", "Chiller_Set_Temp_C", "Chiller_Adet", "Absorption_Chiller_Adet",
    "Kazan_Adet", "Mas1_Isitma_Temp", "Mas1_Kazan_Temp", "Mas1_Sogutma_Temp",
    "Mas2_Isitma_Temp", "Mas2_Kazan_Temp", "Mas2_Sogutma_Temp", "Kar_Eritme_Aktif",
    "Sebeke_Tuketim_kWh", "Kojen_Uretim_kWh", "Kazan_Dogalgaz_m3", "Kojen_Dogalgaz_m3",
    "Su_Tuketimi_m3", "Chiller_Tuketim_kWh", "MCC_Tuketim_kWh", "VRF_Split_Tuketim_kWh",
    "Dis_Hava_Sicakligi_C", "Chiller_Load_Percent", "Toplam_Hastane_Tuketim_kWh",
    "Toplam_Sogutma_Tuketim_kWh", "Diger_Yuk_kWh",
]


# ── Config ────────────────────────────────────────────────


def _cfg() -> dict[str, Any]:
    with open(CFG_FILE, encoding="utf-8") as f:
        return json.load(f)


# ── Yardımcılar ───────────────────────────────────────────


def _local_ip(target: str) -> str:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect((target, 1))
            return s.getsockname()[0]
    except Exception:
        return ""


def _pymodbus_major() -> int:
    try:
        import pymodbus
        return int(pymodbus.__version__.split(".")[0])
    except Exception:
        return 3


def _mk(slave: int) -> dict:
    return {"slave": slave} if _pymodbus_major() >= 3 else {"unit": slave}


# ── Sayaç delta ───────────────────────────────────────────


def _sayac_delta(anahtar: str, yeni: float) -> float | None:
    cache: dict[str, float] = {}
    if SAYAC_CACHE.exists():
        try:
            with open(SAYAC_CACHE, encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            pass

    eski = cache.get(anahtar)
    cache[anahtar] = yeni
    SAYAC_CACHE.parent.mkdir(parents=True, exist_ok=True)
    with open(SAYAC_CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)

    if eski is None:
        return None
    delta = yeni - eski
    return round(delta, 4) if delta >= 0 else None


# ── Modbus okuma ──────────────────────────────────────────


def _modbus_oku(nokta: dict[str, Any]) -> float | None:
    try:
        from pymodbus.client import ModbusTcpClient
    except ImportError:
        logger.warning("pymodbus yüklü değil: pip install pymodbus")
        return None

    ip    = nokta["ip"]
    port  = nokta.get("port", 502)
    slave = nokta.get("slave", 1)
    rtype = nokta.get("register_type", "input")
    reg   = nokta.get("register", 0)
    count = nokta.get("register_count", 1)
    scale = nokta.get("scale", 1.0)
    fmt   = nokta.get("format", "uint16")

    client = __import__("pymodbus.client", fromlist=["ModbusTcpClient"]).ModbusTcpClient(ip, port=port)
    try:
        if not client.connect():
            logger.warning(f"Modbus bağlantı hatası: {ip}:{port}")
            return None
        kw = _mk(slave)
        rr = client.read_input_registers(reg, count=count, **kw) if rtype == "input" \
             else client.read_holding_registers(reg, count=count, **kw)
        if rr.isError():
            logger.warning(f"Modbus okuma hatası ({ip} reg={reg}): {rr}")
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


# ── Belimo vana okuma ─────────────────────────────────────


def oku_belimo_vanalar(cfg: dict) -> list[dict[str, Any]]:
    """
    Tüm Belimo vanalarını Modbus TCP ile okur.
    Sonuçları belimo_data.csv'ye yazar, liste olarak döner.
    """
    try:
        from pymodbus.client import ModbusTcpClient
    except ImportError:
        return []

    vanalar = cfg.get("belimo_vanalar", {})
    satirlar: list[dict[str, Any]] = []
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    for ad, v in vanalar.items():
        if not v.get("ip") or v["ip"] == "0.0.0.0":
            continue
        ip    = v["ip"]
        port  = v.get("port", 502)
        slave = v.get("slave", 1)

        client = ModbusTcpClient(ip, port=port)
        satir: dict[str, Any] = {"timestamp": ts, "vana": ad, "ip": ip, "baglanti": 0}
        try:
            if not client.connect():
                satirlar.append(satir)
                continue
            satir["baglanti"] = 1
            kw = _mk(slave)

            ir_map = v.get("input_registers", {})
            if ir_map:
                count = max(int(k) for k in ir_map) + 1
                rr = client.read_input_registers(0, count=count, **kw)
                if not rr.isError():
                    for idx_s, meta in ir_map.items():
                        idx = int(idx_s)
                        if idx < len(rr.registers):
                            satir[meta["ad"]] = round(rr.registers[idx] * meta["scale"], 3)

            hr_map = v.get("holding_registers", {})
            if hr_map:
                count = max(int(k) for k in hr_map) + 1
                hr = client.read_holding_registers(0, count=count, **kw)
                if not hr.isError():
                    for idx_s, meta in hr_map.items():
                        idx = int(idx_s)
                        if idx < len(hr.registers):
                            satir[meta["ad"]] = round(hr.registers[idx] * meta["scale"], 3)

        except Exception as e:
            logger.error(f"Belimo okuma hatası ({ip}): {e}")
        finally:
            client.close()

        _csv_append(BELIMO_CSV, satir)
        satirlar.append(satir)
        _log_vana(ad, satir)

    return satirlar


def _log_vana(ad: str, s: dict) -> None:
    if not s.get("baglanti"):
        logger.warning(f"[Belimo] {ad} — BAĞLANTI YOK")
        return
    parts = [f"{k}={v}" for k, v in s.items() if k not in ("timestamp", "vana", "ip", "baglanti")]
    logger.info(f"[Belimo] {ad} — " + "  ".join(parts))


# ── BACnet okuma ──────────────────────────────────────────


async def _bacnet_baslat(cfg: dict):
    import BAC0
    baglanti = cfg["baglanti"]
    desigo_ip = baglanti["desigo_ip"]
    local_port = baglanti.get("local_port", 47809)
    lip = _local_ip(desigo_ip)
    bacnet = BAC0.lite(ip=f"{lip}/24", port=local_port) if lip else BAC0.lite(port=local_port)
    await asyncio.sleep(3)
    return bacnet


async def _who_is_gonder(bacnet, cfg: dict, hedef_idler: set[int]) -> dict[str, str]:
    baglanti  = cfg["baglanti"]
    desigo_ip = baglanti["desigo_ip"]
    desigo_port = baglanti.get("desigo_port", 47808)
    cihazlar  = cfg.get("cihazlar", {})

    scan_ips = list({v["ip"] for v in cihazlar.values() if v.get("ip")})
    for ip in scan_ips:
        for dev_id in hedef_idler:
            try:
                await bacnet.who_is(
                    low_limit=dev_id, high_limit=dev_id,
                    address=f"{ip}:{desigo_port}"
                )
            except Exception:
                pass
    await asyncio.sleep(8)

    raw = getattr(bacnet, "discoveredDevices", None) or {}
    addrs: dict[str, str] = {}
    for dev_id in hedef_idler:
        if dev_id in raw:
            info = raw[dev_id]
            addr = info.get("address", str(info)) if isinstance(info, dict) else str(info)
            addrs[str(dev_id)] = addr
            logger.info(f"BACnet cihaz {dev_id} bulundu → {addr}")
        else:
            logger.warning(f"BACnet cihaz {dev_id} bulunamadı.")
    return addrs


async def _oku_nokta(bacnet, addr: str, btype: str, instance: int) -> float | None:
    adres = f"{addr} {btype}:{instance} presentValue"
    try:
        return float(await bacnet.read(adres))
    except Exception as e:
        logger.warning(f"BACnet okuma ({adres}): {e}")
        return None


async def _async_oku_ahu(cfg: dict) -> list[dict[str, Any]]:
    """AHU noktalarını okuyup ham satır listesi döner (HVAC analiz girdisi)."""
    try:
        import BAC0  # noqa
    except ImportError:
        logger.error("BAC0 yüklü değil: pip install BAC0")
        return []

    ahu_listesi  = cfg.get("ahu_noktalari", {})
    ortak        = cfg.get("ortak_noktalar", {})
    cihazlar     = cfg.get("cihazlar", {})

    if not ahu_listesi:
        return []

    needed: set[int] = set()
    for nd in ortak.values():
        if isinstance(nd, dict) and cihazlar.get(str(nd.get("device", "")), {}).get("ip"):
            needed.add(int(nd["device"]))
    for ahu in ahu_listesi.values():
        if not isinstance(ahu, dict):
            continue
        for nd in ahu.values():
            if isinstance(nd, dict) and cihazlar.get(str(nd.get("device", "")), {}).get("ip"):
                needed.add(int(nd["device"]))

    if not needed:
        logger.warning("AHU: hiç aktif BACnet cihazı yok (IP boş).")
        return []

    bacnet = await _bacnet_baslat(cfg)
    addrs  = await _who_is_gonder(bacnet, cfg, needed)

    async def oku(nd: dict) -> float | None:
        dev_id = str(nd.get("device", ""))
        addr   = addrs.get(dev_id)
        if not addr:
            return None
        return await _oku_nokta(bacnet, addr, nd["type"], nd["instance"])

    plant_supply = await oku(ortak["plant_supply"]) if "plant_supply" in ortak else None
    plant_return = await oku(ortak["plant_return"]) if "plant_return" in ortak else None
    oat          = await oku(ortak["oat"])          if "oat"          in ortak else None

    satirlar: list[dict[str, Any]] = []
    for ahu_adi, noktalar in ahu_listesi.items():
        if not isinstance(noktalar, dict):
            continue
        sat           = await oku(noktalar["sat"])           if "sat"           in noktalar else None
        room          = await oku(noktalar["room"])          if "room"          in noktalar else None
        cooling_valve = await oku(noktalar["cooling_valve"]) if "cooling_valve" in noktalar else None
        heating_valve = await oku(noktalar["heating_valve"]) if "heating_valve" in noktalar else None

        if sat is None:
            logger.warning(f"{ahu_adi}: SAT okunamadı, atlandı.")
            continue

        satirlar.append({
            "Name":              ahu_adi,
            "Type":              "AHU",
            "SAT (°C)":          sat,
            "Room (°C)":         room,
            "Cool Valve (%)":    cooling_valve,
            "Heat Valve (%)":    heating_valve,
            "Plant Supply (°C)": plant_supply,
            "Plant Return (°C)": plant_return,
            "OAT (°C)":          oat,
        })

    try:
        bacnet.disconnect()
    except Exception:
        pass

    return satirlar


async def _async_oku_enerji(cfg: dict) -> dict[str, Any]:
    """Enerji noktalarını (BACnet + Modbus) okuyup {sutun: değer} döner."""
    noktalar = cfg.get("enerji_noktalari", {})
    cihazlar = cfg.get("cihazlar", {})
    sonuc: dict[str, Any] = {}

    # Aktif BACnet noktaları
    bacnet_noktalar = [
        (k, v) for k, v in noktalar.items()
        if isinstance(v, dict) and v.get("etkin", False) and v.get("kaynak") == "bacnet"
        and cihazlar.get(str(v.get("device", "")), {}).get("ip")
    ]

    if bacnet_noktalar:
        try:
            import BAC0  # noqa
            needed = {int(nd["device"]) for _, nd in bacnet_noktalar}
            bacnet = await _bacnet_baslat(cfg)
            addrs  = await _who_is_gonder(bacnet, cfg, needed)

            for sutun, nd in bacnet_noktalar:
                addr = addrs.get(str(nd["device"]))
                if addr:
                    val = await _oku_nokta(bacnet, addr, nd["type"], nd["instance"])
                    if val is not None:
                        sonuc[sutun] = round(val, 2)

            try:
                bacnet.disconnect()
            except Exception:
                pass
        except ImportError:
            logger.error("BAC0 yüklü değil.")

    # Aktif Modbus noktaları (sync, executor'da çalıştır)
    modbus_noktalar = [
        (k, v) for k, v in noktalar.items()
        if isinstance(v, dict) and v.get("etkin", False) and v.get("kaynak") == "modbus"
        and v.get("ip", "0.0.0.0") != "0.0.0.0"
    ]

    loop = asyncio.get_event_loop()
    for sutun, nd in modbus_noktalar:
        val = await loop.run_in_executor(None, _modbus_oku, nd)
        if val is None:
            continue
        if nd.get("deger_tipi") == "sayac":
            delta = _sayac_delta(sutun, val)
            if delta is not None:
                sonuc[sutun] = delta
        else:
            sonuc[sutun] = val

    # Hesaplanan alanlar
    for sutun, nd in noktalar.items():
        if not nd.get("etkin", False) or nd.get("kaynak") != "hesap":
            continue
        try:
            env = {k: v for k, v in sonuc.items() if isinstance(v, (int, float))}
            sonuc[sutun] = round(eval(nd["formul"], {"__builtins__": {}}, env), 4)  # noqa: S307
        except Exception:
            pass

    return sonuc


# ── CSV yardımcıları ──────────────────────────────────────


def _csv_append(path: Path, satir: dict[str, Any]) -> None:
    file_exists = path.exists()
    with open(path, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=list(satir.keys()))
        if not file_exists:
            writer.writeheader()
        writer.writerow(satir)


def upsert_energy_csv(tarih: date, degerler: dict[str, Any]) -> str:
    if not degerler:
        return "bos"

    tarih_str = tarih.strftime("%Y-%m-%d")

    df = pd.read_csv(ENERGY_CSV, dtype=str) if ENERGY_CSV.exists() \
         else pd.DataFrame(columns=ENERGY_SUTUNLAR)

    for col in ENERGY_SUTUNLAR:
        if col not in df.columns:
            df[col] = ""

    yeni = {col: "" for col in ENERGY_SUTUNLAR}
    yeni["Tarih"] = tarih_str
    for k, v in degerler.items():
        if k in yeni:
            yeni[k] = "" if v is None else str(v)

    eslesme = df["Tarih"] == tarih_str
    if eslesme.any():
        for k, v in yeni.items():
            if v != "":
                df.loc[eslesme, k] = v
        durum = "guncellendi"
    else:
        df = pd.concat([df, pd.DataFrame([yeni])], ignore_index=True)
        durum = "eklendi"

    df = df[ENERGY_SUTUNLAR]
    df.to_csv(ENERGY_CSV, index=False, encoding="utf-8")
    logger.info(f"energy_data.csv {durum}: {tarih_str}  ({len(degerler)} alan)")
    return durum


def _kaydet_hvac(satirlar: list[dict[str, Any]]) -> None:
    if not satirlar:
        return
    file_exists = HVAC_CSV.exists()
    with open(HVAC_CSV, "a", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=satirlar[0].keys())
        if not file_exists:
            writer.writeheader()
        writer.writerows(satirlar)
    logger.info(f"{len(satirlar)} AHU satırı hvac_analysis_history.csv'ye eklendi.")


# ── Ana okuma fonksiyonu (sync wrapper) ───────────────────


def oku_ve_kaydet(tarih: date | None = None) -> dict[str, Any]:
    """
    Tüm kaynakları okur, her iki CSV'ye yazar.
    Döner: {'enerji': {sutun: deger}, 'ahu_adet': N, 'belimo_adet': N}
    """
    if tarih is None:
        tarih = date.today()

    cfg = _cfg()

    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        enerji_degerleri = loop.run_until_complete(_async_oku_enerji(cfg))
        ahu_satirlari    = loop.run_until_complete(_async_oku_ahu(cfg))
    finally:
        loop.close()
        asyncio.set_event_loop(None)

    # Belimo
    belimo_satirlari = oku_belimo_vanalar(cfg)

    # HVAC analiz
    if ahu_satirlari:
        try:
            from main_portal import analyze_data  # noqa
            ts = datetime.now().strftime("%Y-%m-%d %H:%M")

            async def _analiz():
                return await analyze_data(
                    rows=ahu_satirlari,
                    oat=str(ahu_satirlari[0].get("OAT (°C)", "")),
                    engine="auto",
                    tol_crit="3.0",
                    tol_norm="1.5",
                )

            _loop2 = asyncio.new_event_loop()
            asyncio.set_event_loop(_loop2)
            try:
                analiz = _loop2.run_until_complete(_analiz())
            finally:
                _loop2.close()
                asyncio.set_event_loop(None)

            sonuclar = analiz.get("results", [])
            for r in sonuclar:
                r["Tarih"] = ts
            _kaydet_hvac(sonuclar)
        except Exception as e:
            logger.error(f"HVAC analiz hatası: {e}")

    # energy_data.csv UPSERT
    upsert_energy_csv(tarih, enerji_degerleri)

    return {
        "enerji":      enerji_degerleri,
        "ahu_adet":    len(ahu_satirlari),
        "belimo_adet": len(belimo_satirlari),
    }


# ── Arka plan servisi ─────────────────────────────────────

_thread: threading.Thread | None = None
_stop   = threading.Event()


def baslat(kayit_saati: str = "23:50", kontrol_dk: int = 60) -> None:
    """
    Portal başladığında çağrılır. Her gece kayit_saati'nde otomatik okuma yapar.
    """
    global _thread

    if _thread and _thread.is_alive():
        return

    if not CFG_FILE.exists():
        logger.warning("bacnet_points.json bulunamadı — servis pasif.")
        return

    _stop.clear()

    def _loop():
        logger.info(f"BACnet reader servisi başladı (kayıt saati={kayit_saati})")
        son_tarih: date | None = None

        while not _stop.is_set():
            simdi    = datetime.now()
            bugun    = simdi.date()
            saat_str = simdi.strftime("%H:%M")

            h, m = map(int, kayit_saati.split(":"))
            pencere_bas = f"{h:02d}:{max(0, m - 30):02d}"

            if pencere_bas <= saat_str <= kayit_saati and son_tarih != bugun:
                logger.info(f"Otomatik okuma başlıyor: {bugun}")
                try:
                    sonuc = oku_ve_kaydet(bugun)
                    logger.info(
                        f"Tamamlandı: enerji={len(sonuc['enerji'])} alan, "
                        f"AHU={sonuc['ahu_adet']}, Belimo={sonuc['belimo_adet']}"
                    )
                    son_tarih = bugun
                except Exception as e:
                    logger.error(f"Okuma döngü hatası: {e}")

            _stop.wait(kontrol_dk * 60)

    _thread = threading.Thread(target=_loop, daemon=True, name="bacnet-reader")
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

    tarih_arg = date.today()
    if len(sys.argv) > 1:
        try:
            tarih_arg = date.fromisoformat(sys.argv[1])
        except ValueError:
            print(f"Geçersiz tarih: {sys.argv[1]}  (beklenen: YYYY-MM-DD)")
            sys.exit(1)

    if not CFG_FILE.exists():
        print(f"HATA: {CFG_FILE} bulunamadı.")
        sys.exit(1)

    print(f"\n=== BACnet Reader — {tarih_arg} ===\n")
    sonuc = oku_ve_kaydet(tarih_arg)

    print(f"\nEnerji verileri ({len(sonuc['enerji'])} alan):")
    for k, v in sonuc["enerji"].items():
        print(f"  {k}: {v}")

    print(f"\nAHU satırları: {sonuc['ahu_adet']}")
    print(f"Belimo vanaları: {sonuc['belimo_adet']}")
    print(f"\n→ energy_data.csv ve hvac_analysis_history.csv güncellendi.")
