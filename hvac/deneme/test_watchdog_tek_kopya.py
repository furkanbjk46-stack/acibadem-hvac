# -*- coding: utf-8 -*-
"""Watchdog tek kopya: ikinci watchdog kapanır; tam yeniden başlatmada yeni watchdog eskisini bekler."""
import os
import subprocess
import sys
import time

BURASI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BURASI)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass
import logging  # noqa: E402
logging.disable(logging.CRITICAL)
import portal_watchdog as W  # noqa: E402

gecti = basarisiz = 0


def c(ad, kosul, ek=""):
    global gecti, basarisiz
    if kosul:
        gecti += 1
        print("PASS", ad)
    else:
        basarisiz += 1
        print("FAIL", ad, " ", str(ek)[:300])


# Sahte kilit: n. denemede serbest kalır
def sahte(serbest_deneme):
    s = {"n": 0}

    def al(ad):
        s["n"] += 1
        return s["n"] >= serbest_deneme
    return al, s


bekle = []
al, s = sahte(1)
c("kilit boşsa hemen alır", W.tek_kopya(60, bekle.append, al) and s["n"] == 1 and not bekle)
al, s = sahte(4)
bekle.clear()
c("eski watchdog kapanana kadar bekler (tam yeniden başlatma)", W.tek_kopya(60, bekle.append, al) and s["n"] == 4
  and bekle == [2, 2, 2])
al, s = sahte(10 ** 6)
c("süre dolarsa vazgeçer", W.tek_kopya(0.05, lambda x: time.sleep(0.01), al) is False)

# Gerçek kilit, iki süreç: tutan süreç kapanınca kilit serbest kalır
tutucu = subprocess.Popen([sys.executable, "-c",
                           "import sys,time;sys.path.insert(0,r'%s');import kilit;"
                           "print(kilit.surec_kilidi_al('watchdog'),flush=True);time.sleep(4)" % BURASI],
                          stdout=subprocess.PIPE, text=True)
ilk = tutucu.stdout.readline().strip()
denetci = subprocess.run([sys.executable, "-c",
                          "import sys;sys.path.insert(0,r'%s');import portal_watchdog as W;"
                          "print(W.tek_kopya(0.5))" % BURASI], capture_output=True, text=True, timeout=60)
c("başka süreç tutarken ikinci watchdog kilidi alamaz", ilk == "True" and denetci.stdout.strip().endswith("False"),
  (ilk, denetci.stdout, denetci.stderr[-300:]))
t0 = time.time()
bekleyen = subprocess.run([sys.executable, "-c",
                           "import sys;sys.path.insert(0,r'%s');import portal_watchdog as W;"
                           "print(W.tek_kopya(30))" % BURASI], capture_output=True, text=True, timeout=60)
tutucu.wait(timeout=30)
c("tutan süreç kapanınca bekleyen watchdog kilidi alır", bekleyen.stdout.strip().endswith("True")
  and time.time() - t0 < 30, (bekleyen.stdout, bekleyen.stderr[-300:]))

print("\n%d/%d PASS" % (gecti, gecti + basarisiz))
sys.exit(1 if basarisiz else 0)
