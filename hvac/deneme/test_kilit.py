# -*- coding: utf-8 -*-
"""Tek kopya garantisi testleri — GERCEK iki ayri surecle, ag YOK.

    python hvac/deneme/test_kilit.py

NEDEN VAR: Oto-set ayni gecisi saniyeler arayla 2-3 kez uyguluyordu.
app_portal.py her Streamlit calismasinda start_background_sync()'i korumasiz
cagiriyor, watchdog'un ayri cloud_sync.py sureci de calisiyordu.
"""
import os
import re
import subprocess
import sys
import threading
import time
import types

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
import logging
logging.disable(logging.CRITICAL)
import kilit

T = []


def c(ad, kosul, detay=""):
    T.append((ad, bool(kosul), detay))


AD = "test_%d" % os.getpid()

# ── 1) Surec kilidi: baska SURECTE sahipken alinamaz, o olunce alinir ─────
tutucu = subprocess.Popen(
    [sys.executable, "-c",
     "import sys,time; sys.path.insert(0, r'%s'); import kilit; "
     "print('ALDI' if kilit.surec_kilidi_al('%s') else 'ALAMADI', flush=True); "
     "time.sleep(4)" % (BURASI, AD)],
    stdout=subprocess.PIPE, text=True)
satir = tutucu.stdout.readline().strip()
c("[surec] ilk surec kilidi aldi", satir == "ALDI", satir)
c("[surec] ikinci surec ALAMAZ", kilit.surec_kilidi_al(AD) is False)
tutucu.wait(timeout=15)
c("[surec] sahip surec kapaninca kilit devralinir", kilit.surec_kilidi_al(AD) is True)
c("[surec] ayni surecte tekrar cagri True (zaten sahip)", kilit.surec_kilidi_al(AD) is True)

# ── 2) Kisa kilit: ayni surecte thread'ler ve baska surec ─────────────────
with kilit.kisa_kilit(AD + "_k") as a1:
    with kilit.kisa_kilit(AD + "_k") as a2:
        c("[kisa] ayni isimde ic ice ikinci istek ALAMAZ", a1 is True and a2 is False, (a1, a2))
    r = subprocess.run(
        [sys.executable, "-c",
         "import sys; sys.path.insert(0, r'%s'); import kilit\n"
         "with kilit.kisa_kilit('%s_k') as a: print('ALDI' if a else 'ALAMADI')" % (BURASI, AD)],
        capture_output=True, text=True, timeout=30)
    c("[kisa] baska surec kilit tutulurken ALAMAZ", r.stdout.strip() == "ALAMADI", r.stdout + r.stderr)
with kilit.kisa_kilit(AD + "_k") as a3:
    c("[kisa] birakilinca yeniden alinir", a3 is True)
r = subprocess.run(
    [sys.executable, "-c",
     "import sys; sys.path.insert(0, r'%s'); import kilit\n"
     "with kilit.kisa_kilit('%s_k') as a: print('ALDI' if a else 'ALAMADI')" % (BURASI, AD)],
    capture_output=True, text=True, timeout=30)
c("[kisa] birakilinca baska surec de alir", r.stdout.strip() == "ALDI", r.stdout + r.stderr)

_hata = None
try:
    with kilit.kisa_kilit(AD + "_h") as a:
        raise ValueError("govdede hata")
except ValueError:
    pass
with kilit.kisa_kilit(AD + "_h") as a:
    c("[kisa] govdede istisna olsa da kilit birakilir", a is True)

# ── 3) start_background_sync: ayni surecte TEK baslatma ───────────────────
import cloud_sync

baslatilan = []


class SahteThread:
    def __init__(self, target=None, daemon=None, name=None):
        self.name = name

    def start(self):
        baslatilan.append(self.name)


_orj = (cloud_sync.load_config, cloud_sync.get_supabase_client, cloud_sync.threading.Thread)
cloud_sync.load_config = lambda: {"supabase_url": "https://sahte", "supabase_key": "x",
                                  "lokasyon_id": "test"}
cloud_sync.get_supabase_client = lambda cfg: None
cloud_sync.threading.Thread = SahteThread
try:
    cloud_sync._ARKA_PLAN["basladi"] = False
    _orj_al = kilit.surec_kilidi_al
    kilit.surec_kilidi_al = lambda ad: True
    s1 = cloud_sync.start_background_sync()
    for _ in range(5):                     # Streamlit'in tekrar tekrar calistirmasi
        cloud_sync.start_background_sync()
    c("[sync] ilk cagri True doner", s1 is True, s1)
    c("[sync] 6 cagriya ragmen dongu thread'leri YALNIZCA 1 kez baslar",
      sorted(baslatilan) == ["cloud-sync", "heartbeat"], baslatilan)

    # Esanli cagrilar (iki Streamlit oturumu ayni anda)
    baslatilan.clear()
    cloud_sync._ARKA_PLAN["basladi"] = False
    ts = [threading.Thread.__mro__[0]] if False else []
    import threading as _gercek_th
    _ths = [_gercek_th._DummyThread] if False else []
    _bariyer = _gercek_th.Barrier(8)
    def _cagir():
        _bariyer.wait()
        cloud_sync.start_background_sync()
    # cloud_sync.threading.Thread sahteye cevrildigi icin gercek Thread'i
    # modul disindan kullanmak gerekir
    _gercek_thread_cls = _orj[2]
    _is = [_gercek_thread_cls(target=_cagir) for _ in range(8)]
    for t in _is:
        t.start()
    for t in _is:
        t.join()
    c("[sync] 8 esanli cagride de YALNIZCA 1 baslatma",
      sorted(baslatilan) == ["cloud-sync", "heartbeat"], baslatilan)

    # Baska surec sahipken
    baslatilan.clear()
    cloud_sync._ARKA_PLAN["basladi"] = False
    kilit.surec_kilidi_al = lambda ad: False
    s2 = cloud_sync.start_background_sync()
    c("[sync] kilit baska surecteyse False doner", s2 is False, s2)
    c("[sync] kilit baska surecteyse HIC dongu baslamaz", baslatilan == [], baslatilan)
    kilit.surec_kilidi_al = lambda ad: True
    s3 = cloud_sync.start_background_sync()
    c("[sync] kilit bosalinca devralinir", s3 is True and len(baslatilan) == 2, (s3, baslatilan))
finally:
    kilit.surec_kilidi_al = _orj_al
    cloud_sync.load_config, cloud_sync.get_supabase_client, cloud_sync.threading.Thread = _orj
    cloud_sync._ARKA_PLAN["basladi"] = False

# ── 4) Kaynak kontrolleri: watchdog ve portal ─────────────────────────────
_portal = open(os.path.join(BURASI, "app_portal.py"), encoding="utf-8").read()
_m = re.search(r'if os\.environ\.get\("HVAC_WATCHDOG"\) != "1":\s*\n\s*try:\s*\n\s*from cloud_sync import start_background_sync\s*\n\s*start_background_sync\(\)',
               _portal)
c("[kaynak] app_portal watchdog altinda sync BASLATMAZ", bool(_m))
c("[kaynak] app_portal'da korumasiz baska start_background_sync cagrisi yok",
  len(re.findall(r"start_background_sync\(\)", _portal)) == 1)

_wd = open(os.path.join(BURASI, "portal_watchdog.py"), encoding="utf-8").read()
c("[kaynak] watchdog cocuk ortaminda HVAC_WATCHDOG=1",
  'HVAC_WATCHDOG="1"' in _wd)
_popen = re.findall(r"subprocess\.Popen\(\s*\[sys\.executable, \"(?:-m|cloud_sync|data_)", _wd)
_env_li = len(re.findall(r"cwd=BASE_DIR, env=_COCUK_ENV", _wd))
c("[kaynak] watchdog'un bes cocuk surecinin hepsi bu ortamla baslar", _env_li == 5, _env_li)

_oto = open(os.path.join(BURASI, "oto_set.py"), encoding="utf-8").read()
c("[kaynak] oto_set.kontrol kilit altinda", 'kisa_kilit("oto_set")' in _oto)

# Temizlik
for _ek in ("", "_k", "_h"):
    try:
        os.remove(kilit._dosya(AD + _ek))
    except OSError:
        pass

gecen = sum(1 for _, k, _ in T if k)
for ad, k, d in T:
    print(("PASS " if k else "FAIL ") + ad + ("" if k else "   [%s]" % (d,)))
print("\n%d/%d PASS" % (gecen, len(T)))
sys.exit(0 if gecen == len(T) else 1)
