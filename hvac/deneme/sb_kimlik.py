# -*- coding: utf-8 -*-
"""
SUPABASE KİMLİĞİ — lokasyon anahtarı (29.10.2026, denetim kritik madde 2)
========================================================================

NEDEN: Bütün lokasyonlar ve merkez aynı "anon" anahtarla bağlanıyordu; anahtar
herkese açık repoda duruyor. Anahtarı bulan biri her lokasyonun enerji
geçmişini silip değiştirebiliyordu. Artık her lokasyon PC'sinin KENDİ imzalı
anahtarı (JWT: role=authenticated, lokasyon_id=<lokasyon>) var; Supabase
kuralları (merkez/rls_lokasyon_anahtari_A.sql) bu anahtara YALNIZ kendi
lokasyonunun satırlarında izin verir.

GEÇİŞ GÜVENLİ: anahtar dosyası (configs/lokasyon_anahtari.json) YOKSA her şey
bugünkü gibi ortak anahtarla çalışır. Dosya PC'ye elle konur — yamayla
GÖNDERİLMEZ (yama tablosunu ortak anahtarla herkes okuyabilir, anahtar sızardı).
configs/ klasörü yamalarda ve USB güncellemesinde korunur; anahtar silinmez.

Kullanım (Supabase'e bağlanan HER yer):
    import sb_kimlik
    client = sb_kimlik.istemci(url, key)              # supabase-py
    headers = sb_kimlik.basliklar(key, {"Content-Type": "application/json"})
"""
import json
import os

BURASI = os.path.dirname(os.path.abspath(__file__))
ANAHTAR_DOSYA = os.path.join(BURASI, "configs", "lokasyon_anahtari.json")


def lokasyon_anahtari():
    """Bu PC'nin lokasyon anahtarı (JWT) ya da None (dosya yok / bozuk)."""
    try:
        with open(ANAHTAR_DOSYA, encoding="utf-8") as f:
            t = (json.load(f).get("jwt") or "").strip()
        return t if t.count(".") == 2 else None
    except Exception:
        return None


def yetki(key: str) -> str:
    """Authorization başlığı: lokasyon anahtarı varsa o, yoksa ortak anahtar."""
    return "Bearer " + (lokasyon_anahtari() or key)


def basliklar(key: str, ek: dict = None) -> dict:
    """urllib istekleri için başlıklar (apikey her zaman ortak/publishable anahtar)."""
    h = {"apikey": key, "Authorization": yetki(key)}
    if ek:
        h.update(ek)
    return h


def istemci(url: str, key: str):
    """supabase-py istemcisi; lokasyon anahtarı varsa istekler onunla imzalanır."""
    from supabase import create_client
    c = create_client(url, key)
    t = lokasyon_anahtari()
    if not t:
        return c
    # supabase-py 2.x: istekler options.headers["Authorization"] ile imzalanır;
    # postgrest istemcisi tembel kurulur → sıfırlanınca yeni başlıkla kurulur.
    # (postgrest.auth() 2.28'de başlığı kalıcı değiştirmiyordu — test_sb_kimlik.)
    try:
        c.options.headers["Authorization"] = "Bearer " + t
        c._postgrest = None
    except Exception:
        pass
    try:
        _ses = c.postgrest.session.headers
        if _ses.get("Authorization") != "Bearer " + t:
            c.postgrest.auth(t)          # eski sürümler
    except Exception:
        pass                             # olmazsa ortak anahtarla devam (bugünkü davranış)
    return c
