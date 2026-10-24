# -*- coding: utf-8 -*-
"""Mekanik Zeka — LOKASYON ÖZ TESTİ.

    python oz_test.py            → testleri çalıştır, sonucu dosyaya yaz
    python oz_test.py --oku      → son sonucu yazdır (çalıştırmadan)

Neden gerekli: testler geliştirme makinesinde yeşil olsa bile HER LOKASYONUN
KENDİ AYARLARI vardır (configs/hvac_settings.json: üfleme bandı, tolerans,
chiller hedefi...). Aynı kod, farklı ayarla farklı karar verir. Bu yüzden
testler lokasyonun kendi ayarlarıyla, lokasyon PC'sinde de koşar.

Ne zaman çalışır: portal açılışında ve her güncellemeden sonra bir kez
(portal_watchdog tarafından, arka planda — portalın açılmasını geciktirmez).
Sonuç `configs/oz_test_sonuc.json` dosyasına yazılır ve heartbeat ile
Synapse'e gider; lokasyon kartında "öz test: 164/164" olarak görünür.

Testler sahadan gelen veriyi DEĞİL, kendi senaryolarını kullanır: motorun
doğru çalışıp çalışmadığını ölçer, santrallerin durumunu değil.
"""
import json
import os
import re
import subprocess
import sys
from datetime import datetime

BURASI = os.path.dirname(os.path.abspath(__file__))
SONUC_DOSYASI = os.path.join(BURASI, "configs", "oz_test_sonuc.json")

# (dosya, ek argümanlar) — değişmez kural taraması sahada kısa tutulur (hız)
TESTLER = [
    ("test_golden_mekanik_zeka.py", []),
    ("test_kural_katalogu.py", []),
    ("test_kural_tutarliligi.py", []),
    ("test_mod_cozumu.py", []),
    ("test_kural_onceligi.py", ["400"]),
    ("test_degismez_kurallar.py", ["800"]),
]

_SAYI = re.compile(r"(\d+)\s*/\s*(\d+)\s*PASS")


def _tek_test(dosya: str, ek) -> dict:
    yol = os.path.join(BURASI, dosya)
    if not os.path.exists(yol):
        return {"dosya": dosya, "durum": "YOK", "gecen": 0, "toplam": 0,
                "not": "test dosyası lokasyonda yok"}
    try:
        p = subprocess.run([sys.executable, yol] + list(ek), cwd=BURASI,
                           capture_output=True, text=True, encoding="utf-8",
                           errors="replace", timeout=300)
        cikti = (p.stdout or "") + (p.stderr or "")
    except subprocess.TimeoutExpired:
        return {"dosya": dosya, "durum": "ZAMAN_ASIMI", "gecen": 0, "toplam": 0}
    except Exception as e:
        return {"dosya": dosya, "durum": "CALISTIRILAMADI", "gecen": 0, "toplam": 0,
                "not": f"{type(e).__name__}: {e}"}

    gecen = toplam = 0
    for m in _SAYI.finditer(cikti):
        gecen, toplam = int(m.group(1)), int(m.group(2))     # son eşleşme = özet satırı
    if toplam == 0:
        # Değişmez kural motoru "SAĞLAM değişmez kural: 16/16" biçiminde yazar
        m = re.search(r"SAĞLAM değişmez kural:\s*(\d+)\s*/\s*(\d+)", cikti)
        if m:
            gecen, toplam = int(m.group(1)), int(m.group(2))

    kalan = [s.strip() for s in cikti.splitlines() if s.startswith("FAIL") or "✗" in s]
    return {
        "dosya": dosya,
        "durum": "GECTI" if (p.returncode == 0 and toplam and gecen == toplam) else "KALDI",
        "gecen": gecen, "toplam": toplam,
        "kalanlar": kalan[:5],
    }


def calistir() -> dict:
    basla = datetime.now()
    testler = [_tek_test(d, ek) for d, ek in TESTLER]
    gecen = sum(t["gecen"] for t in testler)
    toplam = sum(t["toplam"] for t in testler)
    kalan_dosya = [t["dosya"] for t in testler if t["durum"] != "GECTI"]

    sonuc = {
        "zaman": basla.isoformat(timespec="seconds"),
        "sure_sn": round((datetime.now() - basla).total_seconds(), 1),
        "gecen": gecen,
        "toplam": toplam,
        "durum": "GECTI" if not kalan_dosya else "KALDI",
        "kalan_dosyalar": kalan_dosya,
        "detay": testler,
    }
    try:
        os.makedirs(os.path.dirname(SONUC_DOSYASI), exist_ok=True)
        with open(SONUC_DOSYASI, "w", encoding="utf-8") as f:
            json.dump(sonuc, f, ensure_ascii=False, indent=1)
    except Exception:
        pass          # sonucu yazamamak öz testi başarısız saymaz
    # Saha teşhisi (veri toplama zinciri). Motor testlerinden AYRI bir soru
    # sorar: "veri doğru geliyor mu?". Kendi içinde kapalı — hata öz testi bozmaz.
    try:
        import saha_teshis
        saha_teshis.calistir()
    except Exception:
        pass
    return sonuc


def son_sonuc() -> dict:
    """Heartbeat için kısa özet. Test hiç çalışmadıysa boş sözlük."""
    try:
        with open(SONUC_DOSYASI, "r", encoding="utf-8") as f:
            s = json.load(f)
    except Exception:
        return {}
    return {
        "zaman": s.get("zaman"),
        "gecen": s.get("gecen"),
        "toplam": s.get("toplam"),
        "durum": s.get("durum"),
        "kalan_dosyalar": s.get("kalan_dosyalar") or [],
        "teshis": _teshis_ozet(),
        **_kalanlar_ve_ayarlar(s),
    }


def _kalanlar_ve_ayarlar(s: dict) -> dict:
    """Test KALDIYSA: kalan kontrollerin metni + lokasyonun motor ayarları.

    NEDEN: Maslak 21.10'dan beri 192/197 veriyordu; aynı testler geliştirme
    makinesinde tam geçiyordu. Heartbeat'te yalnız dosya adı vardı — hangi
    kontrol, hangi ayarla kaldı görülemiyordu. Testler lokasyonun KENDİ
    ayarlarıyla koştuğu için ayar dosyaları da gönderilir (yalnız eşik
    değerleri; ikisi birlikte ~2 KB). Test geçerken hiçbiri eklenmez.
    """
    if s.get("durum") == "GECTI":
        return {}
    kalanlar = []
    for t in s.get("detay") or []:
        if t.get("durum") != "GECTI":
            for satir in (t.get("kalanlar") or [])[:3]:
                kalanlar.append("%s: %s" % (t.get("dosya"), str(satir)[:200]))
    ayarlar = {}
    for ad in ("hvac_settings.json", "chiller_fcu_ayarlari.json"):
        try:
            with open(os.path.join(BURASI, "configs", ad), encoding="utf-8") as f:
                ayarlar[ad] = json.load(f)
        except Exception as e:
            ayarlar[ad] = "okunamadı: %s" % type(e).__name__
    return {"kalanlar": kalanlar[:10], "ayarlar": ayarlar}


def _teshis_ozet() -> dict:
    try:
        import saha_teshis
        return saha_teshis.son_ozet()
    except Exception:
        return {}


if __name__ == "__main__":
    if "--oku" in sys.argv:
        print(json.dumps(son_sonuc(), ensure_ascii=False, indent=1))
        sys.exit(0)
    s = calistir()
    for t in s["detay"]:
        print("  %-32s %-16s %s/%s" % (t["dosya"], t["durum"], t["gecen"], t["toplam"]))
        for k in t.get("kalanlar", []):
            print("       " + k[:150])
    print("\nÖZ TEST: %s — %d/%d (%.1f sn)" % (s["durum"], s["gecen"], s["toplam"], s["sure_sn"]))
    sys.exit(0 if s["durum"] == "GECTI" else 1)
