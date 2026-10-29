# -*- coding: utf-8 -*-
"""
LOKASYON ANAHTARI ÜRETİCİ — yalnız geliştirme PC'sinde çalışır (saha paketine girmez)
===================================================================================

Her lokasyon PC'si için imzalı anahtar (JWT, HS256) üretir:
    role=authenticated, lokasyon_id=<lokasyon>, 3 yıl geçerli
Supabase kuralları (merkez/rls_lokasyon_anahtari_A.sql) bu anahtara YALNIZ o
lokasyonun satırlarında izin verir.

İmza anahtarı (Supabase JWT Secret) hvac/deneme/supabase_secret.json → "jwt_secret"
alanından okunur; o dosya git'e GİRMEZ. Çıktı da repo DIŞINA yazılır.

    python lokasyon_anahtari_uret.py maslak
    → Masaüstü\\lokasyon_anahtarlari\\maslak\\lokasyon_anahtari.json

Üretilen dosya lokasyon PC'sinde:  <program klasörü>\\configs\\lokasyon_anahtari.json
JWT Secret değiştirilirse (rotate) bütün anahtarlar geçersiz olur → yeniden üretilir.
"""
import base64
import hashlib
import hmac
import json
import os
import sys
import time

KOK = os.path.dirname(os.path.abspath(__file__))
GIZLI = os.path.join(KOK, "hvac", "deneme", "supabase_secret.json")
GECERLILIK_YIL = 3


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def uret(lokasyon_id: str, gizli: str, simdi: int = None) -> str:
    simdi = int(simdi or time.time())
    baslik = {"alg": "HS256", "typ": "JWT"}
    govde = {"role": "authenticated", "aud": "authenticated", "iss": "supabase",
             "sub": "lokasyon-" + lokasyon_id, "lokasyon_id": lokasyon_id,
             "iat": simdi, "exp": simdi + GECERLILIK_YIL * 365 * 86400}
    h = _b64(json.dumps(baslik, separators=(",", ":")).encode())
    g = _b64(json.dumps(govde, separators=(",", ":")).encode())
    imza = _b64(hmac.new(gizli.encode(), (h + "." + g).encode(), hashlib.sha256).digest())
    return h + "." + g + "." + imza


def main():
    if len(sys.argv) != 2 or not sys.argv[1].strip():
        print(__doc__)
        sys.exit(1)
    lok = sys.argv[1].strip().lower()
    gizli = json.load(open(GIZLI, encoding="utf-8")).get("jwt_secret")
    if not gizli:
        sys.exit("supabase_secret.json içinde jwt_secret yok")
    hedef_dizin = os.path.join(os.path.expanduser("~"), "OneDrive", "Masaüstü", "lokasyon_anahtarlari", lok)
    if not os.path.isdir(os.path.dirname(os.path.dirname(hedef_dizin))):
        hedef_dizin = os.path.join(os.path.expanduser("~"), "Desktop", "lokasyon_anahtarlari", lok)
    os.makedirs(hedef_dizin, exist_ok=True)
    yol = os.path.join(hedef_dizin, "lokasyon_anahtari.json")
    tok = uret(lok, gizli)
    with open(yol, "w", encoding="utf-8") as f:
        json.dump({"lokasyon_id": lok, "jwt": tok,
                   "uretildi": time.strftime("%Y-%m-%d"),
                   "gecerlilik_yil": GECERLILIK_YIL,
                   "_not": "Lokasyon PC'sinde <program>\\configs\\lokasyon_anahtari.json olarak durur. "
                           "Paylaşmayın, e-postayla göndermeyin, repoya koymayın."}, f, ensure_ascii=False, indent=2)
    print("Üretildi:", yol)


if __name__ == "__main__":
    main()
