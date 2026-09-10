# -*- coding: utf-8 -*-
"""Sunum simulasyonunun verisi tutarli mi, sayfalama sonlaniyor mu?

Calistirmak icin:  python merkez/test_sim_veri.py
Ag baglantisi gerekmez; sunucu 8123 portunda yerel olarak ayaga kalkar.
Canli Supabase'e HICBIR istek gitmez.
"""
import os, sys
from collections import defaultdict

KOK = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(KOK, "merkez"))
import _sim_sunucu as S

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", ek)


V = S.veri_uret()
en = V["energy_data"]
lok_ids = {l for l, _, _ in S.LOKASYONLAR}

# ── Kimlik butunlugu: portal ile ayni id'ler ──────────────────────────────
sys.path.insert(0, KOK)
import re
kaynak = open(os.path.join(KOK, "merkez", "app_merkez.py"), encoding="utf-8").read()
blok = kaynak.split("HASTANELER", 1)[1][:6000]
portal_ids = set(re.findall(r'^\s*"([a-z_]+)":\s*\{"isim"', blok, re.M))
c("portal ile ayni lokasyon kimlikleri", lok_ids == portal_ids,
  "sim fazla=%s portal fazla=%s" % (lok_ids - portal_ids, portal_ids - lok_ids))

# ── Kapsam ────────────────────────────────────────────────────────────────
per_lok = defaultdict(list)
for r in en:
    per_lok[r["lokasyon_id"]].append(r)

kurulu = [l for l in lok_ids if S.SENARYO.get(l, ("normal",))[0] != "kurulmadi"]
c("kurulu her lokasyonun verisi var", all(len(per_lok[l]) > 400 for l in kurulu),
  {l: len(per_lok[l]) for l in kurulu if len(per_lok[l]) <= 400})
c("kurulmamis lokasyonun verisi yok", len(per_lok["bodrum"]) == 0)

tarihler = sorted({r["Tarih"] for r in en})
c("gecmis 14 aydan uzun", (len(tarihler) > 400), len(tarihler))
c("gecen yilin ayni ayini kapsiyor", tarihler[0][:4] < tarihler[-1][:4], tarihler[0])

# ── Mevsimsellik ──────────────────────────────────────────────────────────
aylik = defaultdict(int)
for r in en:
    aylik[r["Tarih"][:7]] += r["Toplam_Hastane_Tuketim_kWh"]
sirali = sorted(aylik.items())
yaz = [v for k, v in sirali if k[5:7] in ("07", "08")]
kis = [v for k, v in sirali if k[5:7] in ("01", "02")]
c("yaz tuketimi kistan yuksek", min(yaz) > max(kis), "yaz=%s kis=%s" % (min(yaz), max(kis)))

sog = defaultdict(int)
gaz = defaultdict(int)
for r in en:
    sog[r["Tarih"][5:7]] += r["Toplam_Sogutma_Tuketim_kWh"]
    gaz[r["Tarih"][5:7]] += r["Kazan_Dogalgaz_m3"]
c("sogutma yazin zirve yapar", max(sog, key=sog.get) in ("07", "08"), max(sog, key=sog.get))
c("kazan dogalgazi kisin zirve yapar", max(gaz, key=gaz.get) in ("12", "01", "02"),
  max(gaz, key=gaz.get))

# ── Enerji dengesi ────────────────────────────────────────────────────────
c("sebeke + kojen = toplam",
  all(r["Sebeke_Tuketim_kWh"] + r["Kojen_Uretim_kWh"] == r["Toplam_Hastane_Tuketim_kWh"]
      for r in en))
c("sogutma = chiller + vrf",
  all(r["Chiller_Tuketim_kWh"] + r["VRF_Split_Tuketim_kWh"] == r["Toplam_Sogutma_Tuketim_kWh"]
      for r in en))
c("alt kalemler toplami asmaz",
  all(r["MCC_Tuketim_kWh"] + r["Toplam_Sogutma_Tuketim_kWh"] <= r["Toplam_Hastane_Tuketim_kWh"]
      for r in en))
c("negatif deger yok",
  all(v >= 0 for r in en for k, v in r.items()
      if k.endswith(("_kWh", "_m3")) and isinstance(v, (int, float))))

# ── kWh/m2/gun gercekci mi ────────────────────────────────────────────────
m2 = {l: m for l, _, m in S.LOKASYONLAR}
son = max(tarihler)
yogunluk = {r["lokasyon_id"]: r["Toplam_Hastane_Tuketim_kWh"] / m2[r["lokasyon_id"]]
            for r in en if r["Tarih"] == son}
c("kWh/m2/gun 0.8-2.5 araliginda",
  all(0.8 <= v <= 2.5 for v in yogunluk.values()),
  {k: round(v, 2) for k, v in yogunluk.items() if not 0.8 <= v <= 2.5})

# ── Senaryolar ────────────────────────────────────────────────────────────
dun = (S._bugun() - S.timedelta(days=1)).isoformat()
c("fulya'nin dun verisi bilerek eksik",
  not any(r["Tarih"] == dun for r in per_lok["fulya"]))
c("izmir dun kritik yukte",
  any(r["Tarih"] == dun and r["Chiller_Load_Percent"] == 96 for r in per_lok["izmir"]))
c("bursa dun set yuksek",
  any(r["Tarih"] == dun and r["Chiller_Set_Temp_C"] == 10.5 for r in per_lok["bursa"]))

# ── Sehirlere gore dis hava / chiller set farki ───────────────────────────
# Kart artik her lokasyonun KENDI degerini listeliyor; 21 hastane ayni
# sicakligi gosterirse sunumda anlamsiz durur.
son_gun = {r["lokasyon_id"]: r for r in en if r["Tarih"] == son}
dis_degerler = {k: v["Dis_Hava_Sicakligi_C"] for k, v in son_gun.items()}
c("her lokasyonun dis hava degeri var", all(v is not None for v in dis_degerler.values()))
c("dis hava lokasyona gore farklilasiyor", len(set(dis_degerler.values())) > 5,
  sorted(set(dis_degerler.values())))
c("Adana Kayseri'den sicak", dis_degerler["adana"] > dis_degerler["kayseri"],
  (dis_degerler["adana"], dis_degerler["kayseri"]))
# Ayni sehirdeki hastaneler ayni havayi gormeli (sunumda celiski olmasin).
c("Adana ve Adana Ortopedia ayni havada",
  dis_degerler["adana"] == dis_degerler["adana_ortopedia"],
  (dis_degerler["adana"], dis_degerler["adana_ortopedia"]))
_ist = ["maslak", "altunizade", "kadikoy", "taksim", "fulya", "atakent"]
c("Istanbul hastaneleri ayni havada", len({dis_degerler[l] for l in _ist}) == 1,
  {l: dis_degerler[l] for l in _ist})
c("dis hava makul aralikta (-5 .. 42)",
  all(-5 <= v <= 42 for v in dis_degerler.values()),
  sorted(dis_degerler.values())[:3] + sorted(dis_degerler.values())[-3:])

set_degerler = {k: v["Chiller_Set_Temp_C"] for k, v in son_gun.items()}
c("her lokasyonun chiller set degeri var", all(v is not None for v in set_degerler.values()))
c("chiller set 6.0-11.0 araliginda",
  all(6.0 <= v <= 11.0 for v in set_degerler.values()),
  sorted(set(set_degerler.values())))
c("sicak sehirde set daha dusuk (oto-set mantigi)",
  set_degerler["adana"] <= set_degerler["kayseri"],
  (set_degerler["adana"], set_degerler["kayseri"]))

# ── m2 ayari ──────────────────────────────────────────────────────────────
import json
m2_ayar = json.loads([a for a in V["ayarlar"] if a["key"] == "m2_degerler"][0]["value"])
c("m2 ayari portal degerleriyle ayni", m2_ayar == m2)

# ── Oto-set noktalari ─────────────────────────────────────────────────────
nokta_lok = {n["lokasyon"] for n in V["lokasyon_noktalar"]}
c("kurulu lokasyonlarin BACnet noktalari var", nokta_lok == set(kurulu),
  nokta_lok ^ set(kurulu))

# ── HTTP KATMANI: sayfalama (sunumu kilitleyen hata buradaydi) ────────────
import urllib.request

ADRES = S.sunucu_baslat(8123)


def cek(yol, aralik=None):
    h = {}
    if aralik:
        h["Range"] = aralik
    r = urllib.request.Request(ADRES + yol, headers=h)
    return json.load(urllib.request.urlopen(r, timeout=30))


toplam_satir = len(cek("/rest/v1/energy_data"))
c("sayfalama yoksa tum satirlar doner", toplam_satir == len(en), toplam_satir)

# supabase-py .range() -> offset & limit SORGU PARAMETRESI olarak gelir.
s0 = cek("/rest/v1/energy_data?order=Tarih.asc&offset=0&limit=1000")
s1 = cek("/rest/v1/energy_data?order=Tarih.asc&offset=1000&limit=1000")
c("offset=0 ilk 1000 satiri doner", len(s0) == 1000, len(s0))
c("offset=1000 FARKLI satirlari doner  [sonsuz dongu regresyonu]",
  len(s1) == 1000 and s0 != s1)
son_sayfa = cek("/rest/v1/energy_data?order=Tarih.asc&offset=8000&limit=1000")
c("son sayfa sayfa boyundan kucuk  [dongunun bitis kosulu]",
  0 < len(son_sayfa) < 1000, len(son_sayfa))

# Portalin sayfalama dongusunu birebir taklit et — sonlanmali.
toplandi, ofset, adim = 0, 0, 1000
for _tur in range(50):
    p = cek("/rest/v1/energy_data?order=Tarih.asc&offset=%d&limit=%d" % (ofset, adim))
    toplandi += len(p)
    if len(p) < adim:
        break
    ofset += adim
else:
    toplandi = -1
c("sayfalama dongusu sonlaniyor ve tum satirlari topluyor", toplandi == len(en), toplandi)

# Range basligiyla sayfalama yapan istemciler de desteklenmeli.
c("Range '0-999' calisir", len(cek("/rest/v1/energy_data", "0-999")) == 1000)
c("Range 'items=0-999' calisir", len(cek("/rest/v1/energy_data", "items=0-999")) == 1000)

c("lokasyon filtresi calisiyor",
  {r["lokasyon_id"] for r in cek("/rest/v1/energy_data?lokasyon_id=eq.maslak")} == {"maslak"})

print("\ngun sayisi: %d  |  toplam satir: %d  |  lokasyon: %d"
      % (len(tarihler), len(en), len(V["lokasyonlar"])))
print("aylik toplam (son 6 ay):")
for k, v in sirali[-6:]:
    print("   %s  %12s kWh" % (k, format(v, ",d")))

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
raise SystemExit(1 if basarisiz else 0)
