# -*- coding: utf-8 -*-
"""
SIMULASYON SUNUCUSU — Supabase REST'in yerine gecen sahte servis.
=================================================================

AMAC: 21 lokasyonun tamamı entegre olmus gibi davranan bir ortam kurup
Synapse'in bakim/bildirim/oto-set/enerji analizi zincirlerini test etmek.

GUVENLIK: Bu sunucu YALNIZCA 127.0.0.1 uzerinde calisir ve veriyi bellekte
tutar. Canli Supabase'e HICBIR istek gitmez, hicbir satir yazilmaz.

KULLANIM:
    python merkez/_sim_sunucu.py            # 8099 portunda baslar
    python merkez/_sim_sunucu.py --port 9000

Portal bu adrese yonlendirildiginde (secrets: supabase.url = http://127.0.0.1:8099)
gercek kod yollari degismeden calisir.

Gonderilen komutlar ve loglar bellekte biriktirilir; su adreslerden okunabilir:
    /_sim/ozet     -> ne kadar komut/log/ayar yazildi
    /_sim/komutlar -> gonderilen tum komutlar
"""

import argparse
import json
import random
import sys
import threading
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

IST = timezone(timedelta(hours=3))

# ── Portaldaki HASTANELER listesiyle ayni kimlikler ────────────────────────
LOKASYONLAR = [
    ("maslak", "MASLAK"), ("altunizade", "ALTUNİZADE"), ("kozyatagi", "KOZYATAĞI"),
    ("taksim", "TAKSİM"), ("atakent", "ATAKENT"), ("atasehir", "ATAŞEHİR"),
    ("bakirkoy", "BAKIRKÖY"), ("fulya", "FULYA"), ("international", "INTERNAT."),
    ("kadikoy", "KADİKÖY"), ("kartal", "KARTAL"), ("ankara", "ANKARA"),
    ("bayindir", "BAYINDIR"), ("bursa", "BURSA"), ("kocaeli", "KOCAELİ"),
    ("eskisehir", "ESKİŞEHİR"), ("izmir", "İZMİR"), ("kayseri", "KAYSERİ"),
    ("adana", "ADANA"), ("adana_ort", "ADANA ORT."), ("bodrum", "BODRUM"),
]

CH_NOKTALAR = ["CH1_REM_SET", "CH2_REM_SET", "CH3_REM_SET", "CH4_REM_SET", "CH5_REM_SET"]
DIG_NOKTALAR = ["GUNDUZ_KOLLEKTOR_SET", "GECE_KOLLEKTOR_SET", "A_BLOK_FCU_SET",
                "B_BLOK_FCU_SET", "ZON1_KLIMA_SANTRALI_SET", "ZON2_KLIMA_SANTRALI_SET"]

# ══════════════════════════════════════════════════════════════════════════
# SENARYOLAR — hangi lokasyonda ne olacak
# ══════════════════════════════════════════════════════════════════════════
SENARYO = {
    # lokasyon        : (durum,        aciklama)
    "kartal":      ("cevrimdisi",  "3 saattir ping yok"),
    "bodrum":      ("kurulmadi",   "hic kurulmamis"),
    "fulya":       ("veri_yok",    "dun icin enerji verisi yok"),
    "izmir":       ("kritik_yuk",  "chiller %96 yukte"),
    "bursa":       ("set_yuksek",  "chiller set 10.5 C"),
    "ankara":      ("ariza",       "2 arizali bilesen"),
    "kayseri":     ("bakim",       "3 bilesen bakimda"),
    "atasehir":    ("aylik_bakim", "aylik bakim isaretlenmemis"),
}


def _bugun():
    return datetime.now(IST).date()


def veri_uret():
    """Tum tablolarin sentetik icerigini uretir."""
    rnd = random.Random(42)          # tekrarlanabilir olsun
    bugun = _bugun()
    dun = bugun - timedelta(days=1)

    lokasyonlar, energy, kartlar, noktalar, bildirimler = [], [], [], [], []

    for lok_id, kisa in LOKASYONLAR:
        senaryo = SENARYO.get(lok_id, ("normal", ""))[0]

        # ── lokasyonlar tablosu ──
        if senaryo == "kurulmadi":
            ping = None
        elif senaryo == "cevrimdisi":
            ping = (datetime.now(IST) - timedelta(hours=3)).isoformat(timespec="seconds")
        else:
            ping = datetime.now(IST).isoformat(timespec="seconds")

        ozet = {"toplam_ariza": 0, "toplam_bakim": 0, "arizali_cihazlar": []}
        if senaryo == "ariza":
            ozet = {"toplam_ariza": 2, "toplam_bakim": 0,
                    "arizali_cihazlar": [{"ad": "AHU-3 Üfleme Sensörü"}, {"ad": "AHU-7 Fan"}]}
        elif senaryo == "bakim":
            ozet = {"toplam_ariza": 0, "toplam_bakim": 3, "arizali_cihazlar": []}
        elif senaryo == "aylik_bakim":
            ozet = {"toplam_ariza": 0, "toplam_bakim": 0, "arizali_cihazlar": [],
                    "aylik_bakim": {"uyari": True, "ay": "Ağustos"}}

        lokasyonlar.append({
            "lokasyon_id": lok_id,
            "isim": kisa,
            "durum": "online" if senaryo not in ("kurulmadi", "cevrimdisi") else "offline",
            "versiyon": "6.9",
            "ping_zamani": ping,
            "son_sync": ping,
            "bakim_ozet": json.dumps(ozet, ensure_ascii=False),
        })

        if senaryo == "kurulmadi":
            continue     # veri yok, nokta yok

        # ── lokasyon_noktalar (oto-set komutlarinin gidecegi noktalar) ──
        for n in CH_NOKTALAR + DIG_NOKTALAR:
            noktalar.append({"lokasyon": lok_id, "nokta_adi": n,
                             "gateway_ip": "10.0.0.1", "dnet": 1,
                             "mac_hex": "0A0B0C", "obj_type": 2, "obj_inst": 1})

        # ── energy_data — son 40 gun ──
        taban = 45000 + rnd.randint(-8000, 25000)
        for i in range(40):
            gun = bugun - timedelta(days=i)
            if senaryo == "veri_yok" and gun == dun:
                continue                      # dun verisi bilerek eksik
            mevsim = 1.0 + 0.12 * rnd.random()
            toplam = round(taban * mevsim)
            mcc = round(toplam * 0.22)
            chiller = round(toplam * 0.16)
            vrf = round(toplam * 0.03)
            kojen = round(toplam * 0.35) if lok_id in ("maslak", "izmir", "ankara") else 0
            sebeke = toplam - kojen

            ch_set = 7.0
            ch_yuk = 55 + rnd.randint(-10, 20)
            if gun == dun and senaryo == "kritik_yuk":
                ch_yuk = 96
            if gun == dun and senaryo == "set_yuksek":
                ch_set = 10.5

            energy.append({
                "lokasyon_id": lok_id,
                "Tarih": gun.isoformat(),
                "Toplam_Hastane_Tuketim_kWh": toplam,
                "Sebeke_Tuketim_kWh": sebeke,
                "Kojen_Uretim_kWh": kojen,
                "MCC_Tuketim_kWh": mcc,
                "Chiller_Tuketim_kWh": chiller,
                "VRF_Split_Tuketim_kWh": vrf,
                "Toplam_Sogutma_Tuketim_kWh": chiller + vrf,
                "Diger_Yuk_kWh": max(0, toplam - mcc - chiller - vrf),
                "Kazan_Dogalgaz_m3": round(toplam * 0.004),
                "Kojen_Dogalgaz_m3": round(kojen / 6.2) if kojen else 0,
                "Su_Tuketimi_m3": round(toplam * 0.0009),
                "Dis_Hava_Sicakligi_C": 24 + rnd.randint(-4, 6),
                "Chiller_Set_Temp_C": ch_set,
                "Chiller_Load_Percent": ch_yuk,
                "TRDP1_kWh": round(sebeke * 0.42), "TRDP2_kWh": round(sebeke * 0.12),
                "TRDP3_kWh": round(sebeke * 0.16), "TRDP4_kWh": round(sebeke * 0.12),
            })

        # ── bakim_kartlari ──
        if senaryo == "ariza":
            kartlar.append({"lokasyon_id": lok_id, "cihaz": "AHU-3",
                            "kart": {"supply_sensor": "FAULTY", "notes": "sensör aralık dışı"},
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                            "updated_by": "SISTEM"})
        # ── bildirimler ──
        if senaryo in ("ariza", "kritik_yuk"):
            bildirimler.append({
                "id": len(bildirimler) + 1, "lokasyon": lok_id,
                "mesaj": f"{kisa}: otomatik analiz tamamlandı — dikkat gerektiren bulgu var",
                "gonderen": "SIMULASYON", "oncelik": "yuksek", "okundu": False,
                "created_at": datetime.now(timezone.utc).isoformat(),
            })

    # Oto-set: mevcut donemin TERSI kaydedilir ki ilk kontrolde gecis tetiklensin
    saat = datetime.now(IST).hour
    simdiki = "gunduz" if 5 <= saat < 22 else "gece"
    ters = "gece" if simdiki == "gunduz" else "gunduz"

    ayarlar = [
        {"key": "oto_set_aktif", "value": "true"},
        {"key": "oto_mod_chiller", "value": "serin"},
        {"key": "oto_mod_diger", "value": "sogutma"},
        {"key": "oto_donem", "value": ters},          # ← gecisi tetikler
        {"key": "oto_gunduz_saat", "value": "5"},
        {"key": "oto_gece_saat", "value": "22"},
        {"key": "m2_degerler", "value": json.dumps({l: 40000 for l, _ in LOKASYONLAR})},
    ]

    return {
        "lokasyonlar": lokasyonlar,
        "energy_data": energy,
        "bakim_kartlari": kartlar,
        "lokasyon_noktalar": noktalar,
        "bildirimler": bildirimler,
        "ayarlar": ayarlar,
        "oto_mod_log": [],
        "komutlar": [],
        "guncellemeler": [],
        "hvac_summary": [],
        "ai_analizler": [],
        "dis_hava_log": [],
        "lisanslar": [],
    }


VERI = veri_uret()
KILIT = threading.Lock()
SAYAC = {"komut": 0, "log": 0, "ayar_yazma": 0, "istek": 0}


# ══════════════════════════════════════════════════════════════════════════
# Mini PostgREST
# ══════════════════════════════════════════════════════════════════════════
def _filtre_uygula(satirlar, sorgu):
    """key=eq.x, lokasyon=in.(a,b), Tarih=gte.x gibi filtreleri uygular."""
    sonuc = satirlar
    for alan, degerler in sorgu.items():
        if alan in ("select", "order", "limit", "offset"):
            continue
        ifade = degerler[0]
        if "." not in ifade:
            continue
        op, _, deger = ifade.partition(".")
        if op == "eq":
            sonuc = [r for r in sonuc if str(r.get(alan)) == deger]
        elif op == "neq":
            sonuc = [r for r in sonuc if str(r.get(alan)) != deger]
        elif op == "in":
            liste = [x.strip().strip('"') for x in deger.strip("()").split(",")]
            sonuc = [r for r in sonuc if str(r.get(alan)) in liste]
        elif op == "gte":
            sonuc = [r for r in sonuc if str(r.get(alan)) >= deger]
        elif op == "lte":
            sonuc = [r for r in sonuc if str(r.get(alan)) <= deger]
        elif op == "gt":
            sonuc = [r for r in sonuc if str(r.get(alan)) > deger]
        elif op == "lt":
            sonuc = [r for r in sonuc if str(r.get(alan)) < deger]
    return sonuc


def _sirala(satirlar, sorgu):
    if "order" not in sorgu:
        return satirlar
    ifade = sorgu["order"][0]
    alan = ifade.split(".")[0]
    ters = "desc" in ifade
    try:
        return sorted(satirlar, key=lambda r: (r.get(alan) is None, r.get(alan)), reverse=ters)
    except TypeError:
        return satirlar


class Islek(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):
        pass                                    # sessiz

    def _yaz(self, govde, kod=200):
        veri = json.dumps(govde, ensure_ascii=False).encode("utf-8")
        self.send_response(kod)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(veri)))
        self.send_header("Content-Range", "0-%d/*" % max(0, len(govde) - 1)
                         if isinstance(govde, list) else "0-0/*")
        self.end_headers()
        self.wfile.write(veri)

    def _tablo(self):
        yol = urlparse(self.path).path
        if yol.startswith("/rest/v1/"):
            return yol[len("/rest/v1/"):]
        return None

    def do_GET(self):
        with KILIT:
            SAYAC["istek"] += 1
        yol = urlparse(self.path).path
        sorgu = parse_qs(urlparse(self.path).query)

        if yol == "/_sim/ozet":
            return self._yaz({"sayaclar": SAYAC,
                              "komut_sayisi": len(VERI["komutlar"]),
                              "log_sayisi": len(VERI["oto_mod_log"]),
                              "lokasyon_sayisi": len(VERI["lokasyonlar"]),
                              "enerji_satiri": len(VERI["energy_data"])})
        if yol == "/_sim/komutlar":
            return self._yaz(VERI["komutlar"])

        tablo = self._tablo()
        if tablo is None or tablo not in VERI:
            return self._yaz([], 200)

        satirlar = _sirala(_filtre_uygula(VERI[tablo], sorgu), sorgu)
        if "limit" in sorgu:
            satirlar = satirlar[:int(sorgu["limit"][0])]
        # Range basligi (supabase-py .range() bunu kullanir)
        aralik = self.headers.get("Range")
        if aralik and "-" in aralik:
            try:
                bas, son = aralik.split("-")
                satirlar = satirlar[int(bas):int(son) + 1]
            except ValueError:
                pass
        return self._yaz(satirlar)

    def _govde_oku(self):
        uzunluk = int(self.headers.get("Content-Length") or 0)
        if not uzunluk:
            return None
        try:
            return json.loads(self.rfile.read(uzunluk).decode("utf-8"))
        except Exception:
            return None

    def do_POST(self):
        tablo = self._tablo()
        govde = self._govde_oku()
        if tablo is None or govde is None:
            return self._yaz([], 200)
        kayitlar = govde if isinstance(govde, list) else [govde]
        with KILIT:
            VERI.setdefault(tablo, [])
            # UPSERT davranisi — gercek Supabase'de bu tablolarin birincil
            # anahtari var ve Prefer: resolution=merge-duplicates ile UZERINE
            # YAZILIR. Mock bunu taklit etmezse ayni cihaz icin mukerrer satir
            # olusur ve test yaniltici sonuc verir.
            ANAHTAR = {
                "ayarlar": ("key",),
                "bakim_kartlari": ("lokasyon_id", "cihaz"),
                "lokasyonlar": ("lokasyon_id",),
            }
            if tablo in ANAHTAR:
                alanlar = ANAHTAR[tablo]
                for k in kayitlar:
                    esles = [r for r in VERI[tablo]
                             if all(r.get(a) == k.get(a) for a in alanlar)]
                    if esles:
                        esles[0].update(k)
                    else:
                        VERI[tablo].append(k)
                if tablo == "ayarlar":
                    SAYAC["ayar_yazma"] += len(kayitlar)
            else:
                for k in kayitlar:
                    k.setdefault("created_at", datetime.now(timezone.utc).isoformat())
                VERI[tablo].extend(kayitlar)
                if tablo == "komutlar":
                    SAYAC["komut"] += len(kayitlar)
                if tablo == "oto_mod_log":
                    SAYAC["log"] += len(kayitlar)
        return self._yaz(kayitlar, 201)

    def do_PATCH(self):
        tablo = self._tablo()
        sorgu = parse_qs(urlparse(self.path).query)
        govde = self._govde_oku() or {}
        with KILIT:
            hedef = _filtre_uygula(VERI.get(tablo, []), sorgu)
            for r in hedef:
                r.update(govde)
        return self._yaz(hedef)

    def do_DELETE(self):
        tablo = self._tablo()
        sorgu = parse_qs(urlparse(self.path).query)
        with KILIT:
            silinecek = _filtre_uygula(VERI.get(tablo, []), sorgu)
            VERI[tablo] = [r for r in VERI.get(tablo, []) if r not in silinecek]
        return self._yaz([])


def sunucu_baslat(port: int = 8099) -> str:
    """Sunucuyu ARKA PLAN THREAD'inde baslatir ve adresini doner.

    Portalin kendi surecinden cagrilmak icindir: boylece sunum makinesinde
    ayrica Python calistirmaya gerek kalmaz, uygulama kendi verisini kendi
    servis eder. Yalnizca 127.0.0.1'e baglanir.
    """
    srv = ThreadingHTTPServer(("127.0.0.1", port), Islek)
    t = threading.Thread(target=srv.serve_forever, daemon=True,
                         name="sim-sunucu")
    t.start()
    return "http://127.0.0.1:%d" % port


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--port", type=int, default=8099)
    a = p.parse_args()
    print("SIMULASYON SUNUCUSU — http://127.0.0.1:%d" % a.port)
    print("  lokasyon : %d" % len(VERI["lokasyonlar"]))
    print("  enerji   : %d satir" % len(VERI["energy_data"]))
    print("  nokta    : %d" % len(VERI["lokasyon_noktalar"]))
    print("  senaryo  : %s" % ", ".join("%s=%s" % (k, v[0]) for k, v in SENARYO.items()))
    print("  CANLI SUPABASE'E HICBIR ISTEK GITMEZ.")
    ThreadingHTTPServer(("127.0.0.1", a.port), Islek).serve_forever()


if __name__ == "__main__":
    main()
