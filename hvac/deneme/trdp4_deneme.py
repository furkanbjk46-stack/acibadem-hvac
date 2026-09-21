# -*- coding: utf-8 -*-
"""TRDP-4 DENEME OKUMASI — sahada bir kez çalıştırılır.

    python trdp4_deneme.py        (veya çift tıklama)

AMAÇ: Yarın 07:00'deki otomatik okumayı beklemeden, SİSTEMİN KENDİ okuma
kodunun (data_collector.modbus_get_kwh) TRDP-4'ü okuyabildiğini doğrulamak.
Harici bir kütüphane (pymodbus) KULLANMAZ — üretimdeki fonksiyonun aynısını
çağırır; burada okunuyorsa her sabah da okunur.

GÜVENLİ:
  - Yalnızca OKUR. Cihaza hiçbir şey yazmaz.
  - analizor_guncel_veriler.csv ve modbus_daily_ref.json dosyalarına
    DOKUNMAZ — yarınki günlük tüketim farkı bozulmaz.
  - Sonucu ekrana, trdp4_deneme_sonuc.txt dosyasına ve Supabase bildirimler
    tablosuna (okundu=true → personel ekranında banner ÇIKMAZ) yazar; böylece
    merkezden de görülebilir.
"""
import json
import os
import socket
import struct
import sys
import urllib.request
from datetime import datetime

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
os.chdir(BURASI)

import data_collector as dc   # ÜRETİMDEKİ okuyucu

satirlar = []


def yaz(s=""):
    print(s)
    satirlar.append(s)


def cihaz(ad):
    for a in dc.ANALYZERS:
        if a["name"] == ad:
            return a
    return None


def tcp_acik_mi(ip, port=502, sure=3):
    try:
        s = socket.socket()
        s.settimeout(sure)
        s.connect((ip, port))
        s.close()
        return True, ""
    except Exception as e:
        return False, f"{type(e).__name__}: {e}"


def ham_oku(ip, adres):
    """Teşhis için: aynı paket, farklı adres (801 / 800)."""
    try:
        s = socket.socket()
        s.settimeout(3)
        s.connect((ip, 502))
        s.send(b"\x00\x01\x00\x00\x00\x06\x01\x03" + struct.pack(">HH", adres, 4))
        r = s.recv(1024)
        s.close()
        if len(r) >= 17:
            return round(struct.unpack(">d", r[9:17])[0] / 1000, 3)
        return f"kısa yanıt ({len(r)} bayt): {r.hex()}"
    except Exception as e:
        return f"{type(e).__name__}: {e}"


yaz("=" * 58)
yaz(" TRDP-4 DENEME OKUMASI — " + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
yaz("=" * 58)

t4 = cihaz("TRDP-4")
t3 = cihaz("TRDP-3")
if not t4:
    yaz("[HATA] TRDP-4 data_collector.py listesinde YOK — v8.5 yaması inmemiş olabilir.")
    sonuc_kisa = "TRDP-4 listede yok (v8.5 inmemis)"
    deger4 = None
else:
    yaz(f"Cihaz  : {t4['name']}  {t4['ip']}  ({t4['brand']})")
    acik, neden = tcp_acik_mi(t4["ip"])
    yaz(f"TCP 502: {'AÇIK' if acik else 'KAPALI — ' + neden}")

    # ── Asıl test: ÜRETİMDEKİ fonksiyon ──
    deger4 = dc.modbus_get_kwh(t4)
    if deger4 is not None:
        yaz("")
        yaz(f"  >> SİSTEM OKUMASI BAŞARILI: {deger4:,.3f} kWh <<")
        yaz("")
        sonuc_kisa = f"BASARILI {deger4:,.3f} kWh"
    else:
        yaz("")
        yaz("  >> SİSTEM OKUMASI BAŞARISIZ (modbus_get_kwh None döndü) <<")
        yaz("")
        # Teşhis: adres farkı mı, bağlantı mı?
        yaz("Teşhis — aynı paket farklı adreslerle:")
        yaz(f"  adres 801 : {ham_oku(t4['ip'], 801)}")
        yaz(f"  adres 800 : {ham_oku(t4['ip'], 800)}")
        sonuc_kisa = "BASARISIZ (teşhis dosyada)"

# Karşılaştırma: aynı yöntemle okunan TRDP-3 (çalıştığı bilinen Siemens)
if t3:
    deger3 = dc.modbus_get_kwh(t3)
    yaz(f"Referans TRDP-3 ({t3['ip']}): "
        + (f"{deger3:,.3f} kWh — aynı yöntem çalışıyor" if deger3 is not None else "OKUNAMADI"))

yaz("")
yaz("Not: Bu okuma günlük referansa YAZILMADI; yarınki tüketim hesabı etkilenmez.")
yaz("İlk günlük TRDP-4 tüketimi: yarın 07:00 okuması referans olur, ertesi gün yazılır.")

# ── Sonucu kaydet ──
try:
    with open(os.path.join(BURASI, "trdp4_deneme_sonuc.txt"), "w", encoding="utf-8") as f:
        f.write("\n".join(satirlar))
except Exception:
    pass

# ── Merkezden görülebilsin: bildirim (okundu=true → banner çıkmaz) ──
# Geliştirme makinesinde denerken TRDP4_DENEME_GONDERME=1 ile kapatılır
# (yoksa hastane ağı dışından sahte "başarısız" kaydı düşer).
try:
    if os.environ.get("TRDP4_DENEME_GONDERME") == "1":
        raise RuntimeError("gonderim kapali (yerel deneme)")
    with open(os.path.join(BURASI, "supabase_config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    url, key = cfg.get("supabase_url", ""), cfg.get("supabase_key", "")
    if url and key:
        veri = json.dumps({
            "lokasyon": cfg.get("lokasyon_id", "maslak"),
            "mesaj": "[SISTEM TESTI] TRDP-4 deneme okumasi: " + sonuc_kisa,
            "gonderen": "Sistem Testi",
            "oncelik": "bilgi",
            "okundu": True,
        }).encode("utf-8")
        urllib.request.urlopen(urllib.request.Request(
            url + "/rest/v1/bildirimler", data=veri, method="POST",
            headers={"apikey": key, "Authorization": "Bearer " + key,
                     "Content-Type": "application/json", "Prefer": "return=minimal"}),
            timeout=8)
        print("\n[+] Sonuç merkeze iletildi.")
except Exception as e:
    print(f"\n[-] Sonuç merkeze iletilemedi (okuma sonucu yine geçerli): {e}")

try:
    input("\nKapatmak için Enter...")   # çift tıklamada pencere hemen kapanmasın
except (EOFError, OSError):
    pass
