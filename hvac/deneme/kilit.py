# kilit.py
# Süreçler arası basit dosya kilidi — dış kütüphane gerektirmez.
#
# NEDEN VAR: Oto-set aynı geçişi saniyeler arayla 2-3 kez uyguluyordu
# (13.09 08:00'de 2, 14.09 08:00'de 3 kez; sayı günden güne artıyordu).
# Sebep: app_portal.py her Streamlit çalışmasında start_background_sync()'i
# çağırıyordu ve korumasız olduğu için portal her açıldığında bir döngü daha
# ekleniyordu; üstüne watchdog'un ayrı cloud_sync.py süreci de çalışıyordu.
# Kilit, bu işlerin makine başına TEK süreçte ve TEK seferde yürümesini sağlar.
#
# İşletim sistemi kilidi süreç ölünce kendiliğinden kalkar: çöken bir süreç
# kilidi "sonsuza kadar" tutamaz.

import os
import threading
from contextlib import contextmanager

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

_ic_kilitler = {}      # ad -> threading.Lock (aynı süreçteki thread'ler için)
_tutulan = {}          # ad -> açık dosya (süreç ömrü boyunca tutulan kilitler)
_kayit_kilidi = threading.Lock()


def _dosya(ad):
    return os.path.join(BASE_DIR, ".kilit_%s.lock" % ad)


def _kilitle(f):
    """Engellemeden kilitlemeyi dener. Alındıysa True."""
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError:
        return False


def _coz(f):
    try:
        if os.name == "nt":
            import msvcrt
            f.seek(0)
            msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except OSError:
        pass


def surec_kilidi_al(ad):
    """Süreç ÖMRÜ BOYUNCA tutulan kilidi almaya çalışır.

    True  : bu süreç sahip (ilk kez aldı ya da zaten sahipti)
    False : başka bir süreç sahip
    """
    with _kayit_kilidi:
        if ad in _tutulan:
            return True
        f = open(_dosya(ad), "a+")
        if _kilitle(f):
            _tutulan[ad] = f
            return True
        f.close()
        return False


@contextmanager
def kisa_kilit(ad):
    """Kısa süreli kilit. `with kisa_kilit("x") as alindi:` — alındıysa True.

    Beklemez: meşgulse hemen False verir, çağıran o turu atlar.
    Hem aynı süreçteki thread'lere hem başka süreçlere karşı korur.
    """
    with _kayit_kilidi:
        ic = _ic_kilitler.setdefault(ad, threading.Lock())
    if not ic.acquire(blocking=False):
        yield False
        return
    f = None
    try:
        f = open(_dosya(ad), "a+")
        alindi = _kilitle(f)
        try:
            yield alindi
        finally:
            if alindi:
                _coz(f)
    finally:
        if f is not None:
            f.close()
        ic.release()
