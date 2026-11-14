# -*- coding: utf-8 -*-
"""Port ayarı (kurulumda bir kez seçilir, sonra sabit), şablondan profil ve boş ayda otomatik rapor yok."""
import json
import os
import shutil
import socket
import sys
import tempfile

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import logging  # noqa: E402
logging.disable(logging.CRITICAL)
import portlar as P  # noqa: E402

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", str(ek)[:300])


d = tempfile.mkdtemp(prefix="portlar_")
os.makedirs(os.path.join(d, "ayar"))

# ── Okuma ──
c("ayar yoksa bugünkü portlar (Maslak değişmez)", P.yukle(d) == {"enerji": 8501, "mekanik_zeka": 8005})
with open(os.path.join(d, "ayar", "portlar.json"), "w") as f:
    json.dump({"enerji": 8502, "mekanik_zeka": "bozuk"}, f)
c("ayar okunur; bozuk alan varsayılana düşer", P.yukle(d) == {"enerji": 8502, "mekanik_zeka": 8005}, P.yukle(d))
c("adres yardımcıları", P.enerji_url(d) == "http://127.0.0.1:8502" and P.mekanik_zeka_url(d) == "http://127.0.0.1:8005")

# ── Kurulumda seçim ──
c("ayar varsa seçim dokunmaz", P.sec(d, _bos_mu=lambda p: False)["yazildi"] is False and P.enerji(d) == 8502)
os.remove(os.path.join(d, "ayar", "portlar.json"))
r = P.sec(d, _bos_mu=lambda p: True)
c("varsayılanlar boşsa onlar yazılır", r["yazildi"] and r["portlar"] == {"enerji": 8501, "mekanik_zeka": 8005}
  and r["degisen"] == [], r)
os.remove(os.path.join(d, "ayar", "portlar.json"))
dolu = {8005, 8006, 8501}
r = P.sec(d, _bos_mu=lambda p: p not in dolu)
c("varsayılan doluysa sıradaki boş port; sonra sabit", r["portlar"] == {"enerji": 8502, "mekanik_zeka": 8007}
  and sorted(r["degisen"]) == ["enerji", "mekanik_zeka"] and P.yukle(d) == r["portlar"], r)
c("sonraki kurulumda port kaymaz (QR etiketleri)", P.sec(d, _bos_mu=lambda p: True)["portlar"] == r["portlar"])

# ── Gerçek soket: dolu port bulunur ──
s = socket.socket()
s.bind(("127.0.0.1", 0))
s.listen(1)
dolu_port = s.getsockname()[1]
c("bos_mu: dinlenen port dolu", P.bos_mu(dolu_port) is False)
s.close()
c("bos_mu: kapatılınca boş", P.bos_mu(dolu_port) is True)

# ── Watchdog: port doluysa bekler, sonra uyarır, KAYDIRMAZ ──
import portal_watchdog as W  # noqa: E402
W.BASE_DIR, W._COCUK_ENV = d, {}
_eski = P.bos_mu
_cagri = {"n": 0}


def _bir_sure_dolu(p):
    _cagri["n"] += 1
    return _cagri["n"] > 4                    # ilk iki turda (2 port × 2) dolu, sonra boş


P.bos_mu = _bir_sure_dolu
bek = []
p = W._portlari_hazirla(30, bek.append)
c("watchdog: eski süreç portu bırakana kadar bekler", bek == [2, 2] and p == r["portlar"], (bek, p))
c("watchdog: çocuk süreçlere portal adresleri verilir",
  W._COCUK_ENV.get("STREAMLIT_URL") == "http://localhost:8502" and W._COCUK_ENV.get("PORTAL_URL") == "http://localhost:8007/")
P.bos_mu = lambda port: port != 8007
W._COCUK_ENV = {}
p = W._portlari_hazirla(0, bek.append)
durum = json.load(open(os.path.join(d, "durum", "portlar_durum.json"), encoding="utf-8"))
c("watchdog: hâlâ doluysa durum dosyasına yazar, port değişmez", p["mekanik_zeka"] == 8007
  and durum["dolu"] == [{"ad": "mekanik_zeka", "port": 8007}], durum)
P.bos_mu = _eski

# ── Agent'lar portu ayardan okur ──
import enerji_agent as C  # noqa: E402
c("Enerji agent'ı portal adresini lokasyonun ayarından alır", C.Ortam(dizin=d, bulut=None).portal_url == "http://127.0.0.1:8502")
c("açıkça verilen adres korunur", C.Ortam(dizin=d, bulut=None, portal_url="http://x:1").portal_url == "http://x:1")

# ── Kurulum: profil şablondan (koordinat), portlar seçilir ──
import kurulum_kontrol as K  # noqa: E402
k = tempfile.mkdtemp(prefix="kurulum_")
os.makedirs(os.path.join(k, "ornek_ayar", "atasehir"))
with open(os.path.join(k, "ornek_ayar", "atasehir", "lokasyon_profili.json"), "w", encoding="utf-8") as f:
    json.dump({"lokasyon_id": "atasehir", "ad": "Şablon adı", "enlem": 40.99, "boylam": 29.12,
               "isitma_hatlari": ["ATA-1"]}, f)
P.bos_mu = lambda port: True
kop = K.ilk_kurulum(k, "atasehir", "Acıbadem Ataşehir")
P.bos_mu = _eski
prof = json.load(open(os.path.join(k, "ayar", "lokasyon_profili.json"), encoding="utf-8"))
c("profil şablondan: koordinat ve hatlar gelir, verilen ad geçer",
  (prof["enlem"], prof["boylam"], prof["isitma_hatlari"], prof["ad"], prof["lokasyon_id"])
  == (40.99, 29.12, ["ATA-1"], "Acıbadem Ataşehir", "atasehir"), prof)
c("kurulum portları yazar", os.path.exists(os.path.join(k, "ayar", "portlar.json"))
  and any(x.startswith("portlar.json") for x in kop), kop)
k2 = tempfile.mkdtemp(prefix="kurulum_")
K.ilk_kurulum(k2, "yeni_lok", "Yeni")
prof2 = json.load(open(os.path.join(k2, "ayar", "lokasyon_profili.json"), encoding="utf-8"))
c("şablon yoksa eskisi gibi boş koordinatlı profil", prof2["ad"] == "Yeni" and prof2["enlem"] is None, prof2)
s = K.kontrol(k, tcp=lambda ip, port: True, http=lambda u: None, agent_turu=False)
c("kontrol listesinde Portlar satırı", any(x["kontrol"] == "Portlar" and "Enerji" in x["aciklama"] for x in s))

# ── Otomatik aylık rapor: veri yoksa üretilmez ──
import monthly_summary_report as MR  # noqa: E402
import pandas as pd  # noqa: E402
_eski_yukle = MR.load_energy_data
MR.load_energy_data = lambda: pd.DataFrame()
c("veri yokken önceki ay için 'veri yok'", MR.ay_verisi_var() is False)
y, m = MR.onceki_ay()
MR.load_energy_data = lambda: pd.DataFrame({"Tarih": [pd.Timestamp(y, m, 3).date()], "Toplam_Hastane_Tuketim_kWh": [100.0],
                                            "Chiller_Tuketim_kWh": [1.0], "Kazan_Dogalgaz_m3": [0.0],
                                            "Kojen_Dogalgaz_m3": [0.0]})
c("o ay bir gün bile varsa rapor üretilir", MR.ay_verisi_var() is True)
MR.load_energy_data = lambda: (_ for _ in ()).throw(OSError("okunamadı"))
c("okuma hatasında eski davranış (üretilir)", MR.ay_verisi_var() is True)
MR.load_energy_data = _eski_yukle

# ── Otomatik aylık bakım raporu: kart / takvim / denetim kaydı yoksa üretilmez ──
import bakim_raporu as BR  # noqa: E402
b = tempfile.mkdtemp(prefix="bakim_")
_eski_bk = (BR.CARDS_FILE, BR.TAKVIM_FILE, BR.AUDIT_FILE)
BR.CARDS_FILE, BR.TAKVIM_FILE, BR.AUDIT_FILE = (os.path.join(b, a) for a in ("kart.json", "takvim.json", "audit.jsonl"))
c("bakım: hiçbir kayıt yokken üretilmez", BR.veri_var(2026, 10) is False)
with open(BR.AUDIT_FILE, "w", encoding="utf-8") as f:
    f.write(json.dumps({"ts": "2026-09-30T10:00:00", "neden": "elle susturma"}) + "\nbozuk satır\n")
c("bakım: başka aya ait denetim kaydı sayılmaz", BR.veri_var(2026, 10) is False)
with open(BR.AUDIT_FILE, "a", encoding="utf-8") as f:
    f.write(json.dumps({"ts": "2026-10-05T10:00:00", "neden": "elle susturma"}) + "\n")
c("bakım: o aya ait denetim kaydı varsa üretilir", BR.veri_var(2026, 10) is True)
os.remove(BR.AUDIT_FILE)
with open(BR.TAKVIM_FILE, "w", encoding="utf-8") as f:
    json.dump({"2026-10": {"yapildi": True}}, f)
c("bakım: o ayın takvim işareti varsa üretilir", BR.veri_var(2026, 10) is True)
os.remove(BR.TAKVIM_FILE)
with open(BR.CARDS_FILE, "w", encoding="utf-8") as f:
    json.dump({"cards": {"MAS-1 Ahu-6": {}}}, f)
c("bakım: bakım kartı varsa üretilir", BR.veri_var(2026, 10) is True)
BR.CARDS_FILE, BR.TAKVIM_FILE, BR.AUDIT_FILE = _eski_bk
shutil.rmtree(b, ignore_errors=True)

for x in (d, k, k2):
    shutil.rmtree(x, ignore_errors=True)
print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
