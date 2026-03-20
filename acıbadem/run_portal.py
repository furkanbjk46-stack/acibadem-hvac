"""
run.py
Tek komutla HVAC (FastAPI) + Enerji (Streamlit) portalını başlatır.

Bu dosya, aşağıdaki dosya adlarıyla çalışır:
- main_portal.py  (FastAPI / HVAC)
- app_portal.py   (Streamlit / Enerji)

İstersen isimleri main.py ve app.py olarak da kullanabilirsin.
Çalıştır:
    python run.py
Aç:
    http://localhost:8005
"""
from __future__ import annotations

import os
import sys
import time
import subprocess
import signal

import uvicorn


FASTAPI_APP = os.environ.get("FASTAPI_APP", "main_portal:app")
STREAMLIT_FILE = os.environ.get("STREAMLIT_FILE", "app_portal.py")
STREAMLIT_PORT = os.environ.get("STREAMLIT_PORT", "8501")
PORTAL_URL = os.environ.get("PORTAL_URL", "http://localhost:8005/")
STREAMLIT_URL = os.environ.get("STREAMLIT_URL", f"http://localhost:{STREAMLIT_PORT}")


def start_streamlit() -> subprocess.Popen:
    # Streamlit'i iframe içinde kullanacağımız için CORS/XSRF'i kapatıyoruz (lokalde portal amaçlı).
    args = [
        sys.executable, "-m", "streamlit", "run", STREAMLIT_FILE,
        "--server.port", STREAMLIT_PORT,
        "--server.headless", "true",
        "--server.enableCORS", "false",
        "--server.enableXsrfProtection", "false",
    ]

    env = os.environ.copy()
    env.setdefault("PORTAL_URL", PORTAL_URL)
    env.setdefault("STREAMLIT_URL", STREAMLIT_URL)

    # Windows'ta CTRL+BREAK gönderebilmek için
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_PROCESS_GROUP  # type: ignore[attr-defined]

    return subprocess.Popen(args, env=env, creationflags=creationflags)


def stop_process(p: subprocess.Popen):
    if p.poll() is not None:
        return
    try:
        if os.name == "nt":
            p.send_signal(signal.CTRL_BREAK_EVENT)  # type: ignore[attr-defined]
            time.sleep(1.0)
        p.terminate()
        p.wait(timeout=5)
    except Exception:
        try:
            p.kill()
        except Exception:
            pass


def main():
    streamlit_proc = start_streamlit()
    try:
        uvicorn.run(FASTAPI_APP, host="0.0.0.0", port=8005, log_level="info")
    finally:
        stop_process(streamlit_proc)


if __name__ == "__main__":
    main()
