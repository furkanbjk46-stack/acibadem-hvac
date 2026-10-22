# -*- coding: utf-8 -*-
"""
SYNAPSE — İZLEYİCİ (salt okunur) oturumu için yazma engeli
=========================================================

İzleyici linkiyle (?izle=<jeton>, bkz. giris.py) gelen kişi TÜM sayfaları ve
TÜM lokasyonları görebilir ama HİÇBİR veriyi değiştiremez.

Arayüzdeki yazma düğmeleri izleyicide ayrıca kapatılır; ancak asıl güvence
BURADADIR: düğmelerden biri gözden kaçsa bile, izleyici oturumunda
veritabanına giden her yazma isteği en alt katmanda reddedilir.

    • supabase istemcisi : insert / upsert / update / delete → PermissionError
                           (rpc yalnızca izinli okuma fonksiyonlarında)
    • urllib (REST)      : POST / PATCH / PUT / DELETE → PermissionError
                           (izinli okuma RPC'leri hariç)

Streamlit tüm oturumları TEK süreçte çalıştırır; yamalar süreç geneline bir
kez kurulur ama her çağrıda O ANKİ oturumun izleyici olup olmadığına bakar.
Yönetici oturumları hiçbir şekilde etkilenmez.
"""

import threading

# Yazma yapmayan, izleyicide serbest olan RPC'ler (POST ile çağrılır ama okur)
IZINLI_RPC = {"synapse_kullanim"}

_YAZMA_METODLARI = {"POST", "PATCH", "PUT", "DELETE"}
_kuruldu = False
_kilit = threading.Lock()


def izleyici_mi() -> bool:
    """Şu an çalışan Streamlit oturumu izleyici mi? (oturum dışında: False)"""
    try:
        import streamlit as st
        return bool(st.session_state.get("izleyici"))
    except Exception:
        return False


class YazmaEngellendi(PermissionError):
    pass


def _engelle(ne: str):
    raise YazmaEngellendi("İzleyici oturumu salt okunur — %s engellendi" % ne)


# ── supabase istemcisi ────────────────────────────────────────────────────
class _SaltOkunurTablo:
    """Sorgu kurucusunu sarar; yazma metodlarını izleyicide kapatır."""

    def __init__(self, ic):
        self._ic = ic

    def __getattr__(self, ad):
        if ad in ("insert", "upsert", "update", "delete") and izleyici_mi():
            def _yasak(*a, **k):
                _engelle("tablo %s" % ad)
            return _yasak
        return getattr(self._ic, ad)


class _SaltOkunurIstemci:
    def __init__(self, ic):
        self._ic = ic

    def table(self, *a, **k):
        return _SaltOkunurTablo(self._ic.table(*a, **k))

    from_ = table

    def rpc(self, ad, *a, **k):
        if izleyici_mi() and ad not in IZINLI_RPC:
            _engelle("rpc %s" % ad)
        return self._ic.rpc(ad, *a, **k)

    def __getattr__(self, ad):
        return getattr(self._ic, ad)


def _rpc_izinli(adres: str) -> bool:
    yol = adres.split("?", 1)[0].rstrip("/")
    for ad in IZINLI_RPC:
        if yol.endswith("/rest/v1/rpc/" + ad):
            return True
    return False


def kur():
    """Yamaları süreç geneline BİR KEZ kurar (tekrar çağrılması zararsız)."""
    global _kuruldu
    with _kilit:
        if _kuruldu:
            return
        # supabase.create_client
        try:
            import supabase as _sb
            _asil_create = _sb.create_client

            def _create_client(*a, **k):
                return _SaltOkunurIstemci(_asil_create(*a, **k))

            _create_client.__wrapped__ = _asil_create
            _sb.create_client = _create_client
        except Exception:
            pass

        # urllib.request.urlopen
        import urllib.request as _ur
        _asil_urlopen = _ur.urlopen

        def _urlopen(istek, *a, **k):
            if izleyici_mi() and isinstance(istek, _ur.Request):
                metod = (istek.get_method() or "GET").upper()
                if metod in _YAZMA_METODLARI and not _rpc_izinli(istek.full_url):
                    _engelle("%s isteği" % metod)
            elif izleyici_mi() and (k.get("data") if "data" in k
                                    else (a[0] if a else None)) is not None:
                _engelle("POST isteği")   # urlopen(adres, data) → POST
            return _asil_urlopen(istek, *a, **k)

        _urlopen.__wrapped__ = _asil_urlopen
        _ur.urlopen = _urlopen
        _kuruldu = True
