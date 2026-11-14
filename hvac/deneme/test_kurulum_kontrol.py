# -*- coding: utf-8 -*-
"""Kurulum kontrolü (F4): sıfırdan bir lokasyon (Ataşehir) — profil, şablon, eksikler, ağ erişimi."""
import json
import os
import shutil
import sys
import tempfile

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import kurulum_kontrol as K  # noqa: E402

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", str(ek)[:300])


def durum(sonuc, ad):
    return next((s["durum"] for s in sonuc if s["kontrol"].startswith(ad)), None)


d = tempfile.mkdtemp(prefix="kurulum_")
# Ataşehir şablonu: yalnız sayaç listesi hazırlanmış (keşiften sonra)
os.makedirs(os.path.join(d, "ornek_ayar", "atasehir"))
with open(os.path.join(d, "ornek_ayar", "atasehir", "sayaclar.json"), "w", encoding="utf-8") as f:
    json.dump({"sayaclar": [{"ad": "TRDP-1", "ip": "10.1.1.1", "marka": "siemens", "tur": "trafo", "sutun": "TRDP1_kWh"},
                            {"ad": "CH-1", "ip": "10.1.1.2", "marka": "janitza", "tur": "chiller", "sutun": "Chiller1_kWh"}]}, f)

kop = K.ilk_kurulum(d, "atasehir", "Acıbadem Ataşehir")
profil = json.load(open(os.path.join(d, "ayar", "lokasyon_profili.json"), encoding="utf-8"))
c("ilk kurulum profili yazar", profil["lokasyon_id"] == "atasehir" and profil["ad"] == "Acıbadem Ataşehir")
c("lokasyonun şablonu ayar/'a kopyalanır; portlar seçilir",
  [x for x in kop if not x.startswith("portlar.json")] == ["sayaclar.json"]
  and os.path.exists(os.path.join(d, "ayar", "sayaclar.json")) and os.path.exists(os.path.join(d, "ayar", "portlar.json")), kop)
c("klasör düzeni kurulur", all(os.path.isdir(os.path.join(d, k)) for k in ("ayar", "durum", "veri")))

erisilen = {"10.1.1.1"}
s = K.kontrol(d, tcp=lambda ip, port: ip in erisilen, http=lambda u: None, agent_turu=False)
c("profil tamam, koordinat yok → uyarı", durum(s, "Lokasyon profili") == K.TAMAM and durum(s, "Koordinat") == K.UYARI)
c("sayaç listesi tamam", durum(s, "Sayaç listesi") == K.TAMAM)
c("BACnet eşlemesi, AHU noktaları, şablon ve merkez bağlantısı eksik",
  all(durum(s, x) == K.EKSIK for x in ("BACnet eşlemesi", "AHU nokta", "BACnet okuma şablonu", "Merkez bağlantısı")), s)
c("ulaşılamayan sayaç adıyla bildirilir", durum(s, "Sayaçlara ağ erişimi") == K.UYARI
  and "CH-1" in next(x["aciklama"] for x in s if x["kontrol"].startswith("Sayaçlara")))
c("sonuç durum/kurulum_kontrol.json'a yazılır", os.path.exists(os.path.join(d, "durum", "kurulum_kontrol.json")))

# Bağlantı ayarlı, merkez yanıt veriyor
with open(os.path.join(d, "ayar", "supabase_config.json"), "w", encoding="utf-8") as f:
    json.dump({"supabase_url": "https://thapps.example/synapse-db", "supabase_key": "x"}, f)
s = K.kontrol(d, tcp=lambda ip, port: True, http=lambda u: 401, agent_turu=False,
              lisans=lambda: {"gecerli": False, "hata": "Bu cihaz icin lisans tanimli degil", "makine_id": "UUID-1"})
c("merkez 401 (anahtarsız istek) = ulaşılıyor", durum(s, "Merkez bağlantısı") == K.TAMAM)
c("bütün sayaçlara ulaşılınca tamam", durum(s, "Sayaçlara ağ erişimi") == K.TAMAM)
_lis = next(x for x in s if x["kontrol"] == "Lisans")
c("lisans yoksa EKSİK ve makine kimliği gösterilir", _lis["durum"] == K.EKSIK and "UUID-1" in _lis["aciklama"], _lis)
c("sürüm dosyası yoksa uyarı", durum(s, "Program sürümü") == K.UYARI)
with open(os.path.join(d, "yama_surumu.json"), "w", encoding="utf-8") as f:
    json.dump({"versiyon": "14.0+abc"}, f)
s = K.kontrol(d, tcp=lambda ip, port: True, http=lambda u: 401, agent_turu=False,
              lisans=lambda: {"gecerli": True, "makine_id": "UUID-1", "makine_adi": "Ataşehir PC"})
c("lisans geçerli → tamam; sürüm dosyadan", durum(s, "Lisans") == K.TAMAM and durum(s, "Program sürümü") == K.TAMAM
  and "14.0+abc" in next(x["aciklama"] for x in s if x["kontrol"] == "Program sürümü"))

# Portalları bekleme: ikisi de açılınca döner, süre dolunca False
_cagri = []
c("portallar açılınca bekleme biter",
  K.portallari_bekle(60, http=lambda u: (_cagri.append(u) or (200 if len(_cagri) > 4 else None)), _bekle=lambda x: None))
c("açılmazsa süre dolunca False", K.portallari_bekle(0, http=lambda u: None, _bekle=lambda x: None) is False)

# Var olan kurulumda ilk kurulum hiçbir ayarı ezmez
with open(os.path.join(d, "ayar", "sayaclar.json"), "w", encoding="utf-8") as f:
    json.dump({"sayaclar": [{"ad": "ELLE", "ip": "1.1.1.1", "tur": "trafo", "sutun": "X_kWh"}]}, f)
K.ilk_kurulum(d, "atasehir", "başka ad")
c("tekrar çalıştırmak profili ve ayarları ezmez",
  json.load(open(os.path.join(d, "ayar", "lokasyon_profili.json"), encoding="utf-8"))["ad"] == "Acıbadem Ataşehir"
  and json.load(open(os.path.join(d, "ayar", "sayaclar.json"), encoding="utf-8"))["sayaclar"][0]["ad"] == "ELLE")

shutil.rmtree(d, ignore_errors=True)
print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
