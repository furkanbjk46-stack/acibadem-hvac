# guncelleme_yayinla.py
# Geliştirme makinesinde çalıştırılır.
# Sadece git'te değişmiş dosyaları Supabase'e yükler → lokasyonlar otomatik güncellenir.

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import os
import json
import subprocess
from datetime import datetime

# Yayınlanabilir dosyaların tam listesi (değişse bile buradan kontrol edilir)
IZIN_VERILEN_DOSYALAR = {
    "app_portal.py",
    "cloud_sync.py",
    "main_portal.py",
    "run_portal.py",
    "ai_progress.py",
    "daily_report.py",
    "monthly_summary_report.py",
    "location_manager.py",
    "portal_watchdog.py",
    "monthly_report/pdf_generator.py",
    "monthly_report/savings_engine.py",
    "monthly_report/data_merger.py",
    "monthly_report/hvac_history.py",
    "monthly_report/yoy_analyzer.py",
    "monthly_report/forecast_engine.py",
    "monthly_report/daily_comparison.py",
    "monthly_report/training_data.py",
    "rules/location_config.py",
    "rules/temperature_cascade.py",
    "static/index.html",
    "GUNCELLE.bat",
}

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "supabase_config.json")
SECRET_FILE = os.path.join(os.path.dirname(__file__), "supabase_secret.json")


def git_degisen_dosyalar(base_dir: str) -> list[str]:
    """
    Git ile gerçekten değişmiş dosyaları bul.
    - staged + unstaged değişiklikler (modified, added)
    - Silinmiş dosyaları hariç tutar
    - Git yolları repo kökünden gelir; base_dir'e göre normalize edilir.
    """
    # Git repo kökünü bul
    try:
        r_root = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=base_dir, capture_output=True, text=True, encoding="utf-8"
        )
        repo_root = r_root.stdout.strip().replace("/", os.sep)
    except Exception:
        repo_root = base_dir

    # base_dir'in repo köküne göre göreli prefix'ini hesapla
    # Örn: repo_root = "C:\...\hvac", base_dir = "C:\...\hvac\deneme"
    # → prefix = "deneme/"
    try:
        rel_prefix = os.path.relpath(base_dir, repo_root).replace("\\", "/") + "/"
        if rel_prefix == "./":
            rel_prefix = ""
    except Exception:
        rel_prefix = ""

    degisiklikler = set()

    def ekle(cikti: str):
        for satir in cikti.splitlines():
            satir = satir.strip()
            if not satir:
                continue
            satir_norm = satir.replace("\\", "/")
            # base_dir altındaki dosyalar: prefix'i soy
            if rel_prefix and satir_norm.startswith(rel_prefix):
                satir_norm = satir_norm[len(rel_prefix):]
            elif rel_prefix and not satir_norm.startswith(rel_prefix):
                continue  # başka klasöre ait dosyayı atla
            degisiklikler.add(satir_norm)

    try:
        # Unstaged değişiklikler
        r1 = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=ACM"],
            cwd=base_dir, capture_output=True, text=True, encoding="utf-8"
        )
        ekle(r1.stdout)

        # Staged değişiklikler
        r2 = subprocess.run(
            ["git", "diff", "--name-only", "--cached", "--diff-filter=ACM"],
            cwd=base_dir, capture_output=True, text=True, encoding="utf-8"
        )
        ekle(r2.stdout)

        # Untracked (yeni) dosyalar
        r3 = subprocess.run(
            ["git", "ls-files", "--others", "--exclude-standard"],
            cwd=base_dir, capture_output=True, text=True, encoding="utf-8"
        )
        ekle(r3.stdout)

    except Exception as e:
        print(f"  ⚠️  Git sorgusu başarısız: {e}")

    return sorted(degisiklikler)


def main():
    print("=" * 55)
    print("  HVAC Sistemi — Güncelleme Yayınlama Aracı")
    print("=" * 55)

    # Config oku
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Service role key oku
    if not os.path.exists(SECRET_FILE):
        print("\n❌ supabase_secret.json bulunamadı!")
        print("   Bu dosya sadece GM bilgisayarında bulunur.")
        input("\nDevam etmek için Enter'a basın...")
        return

    with open(SECRET_FILE, "r", encoding="utf-8") as f:
        secret = json.load(f)

    service_key = secret.get("service_role_key", "")
    if not service_key or "BURAYA" in service_key:
        print("\n❌ supabase_secret.json içinde geçerli bir service_role_key yok!")
        return

    from supabase import create_client
    client = create_client(cfg["supabase_url"], service_key)

    # Versiyon
    versiyon = input("\nVersiyon numarası girin (ör: 2.3): ").strip()
    if not versiyon:
        versiyon = datetime.now().strftime("%Y%m%d_%H%M")

    # Hedef lokasyon
    print("\nHedef lokasyon:")
    print("  1) Tüm lokasyonlar (all)")
    print("  2) Sadece altunizade")
    print("  3) Sadece maslak")
    secim = input("Seçim (1/2/3): ").strip()
    hedef_map = {"1": "all", "2": "altunizade", "3": "maslak"}
    hedef = hedef_map.get(secim, "all")

    base_dir = os.path.dirname(__file__)

    # Git ile sadece değişen dosyaları bul
    print("\nDeğişen dosyalar tespit ediliyor (git diff)...")
    degisen = git_degisen_dosyalar(base_dir)

    # İzin verilenlerle kesişim al (yol ayraçlarını normalize et)
    izin_normalize = {d.replace("\\", "/") for d in IZIN_VERILEN_DOSYALAR}
    gonderilecek = []
    for d in degisen:
        d_norm = d.replace("\\", "/")
        if d_norm in izin_normalize:
            gonderilecek.append(d_norm)

    if not gonderilecek:
        print("\n⚠️  Git'e göre değişen yayınlanabilir dosya yok.")
        print("   Tüm dosyaları göndermek ister misiniz? (e/h): ", end="")
        yanit = input().strip().lower()
        if yanit != "e":
            print("İptal edildi.")
            input("\nDevam etmek için Enter'a basın...")
            return
        # Tüm listeyi gönder (zorunlu mod)
        gonderilecek = sorted(izin_normalize)

    # Dosya içeriklerini oku
    print(f"\nGönderilecek dosyalar ({len(gonderilecek)} adet):")
    dosyalar = {}
    for dosya in gonderilecek:
        tam_yol = os.path.join(base_dir, dosya.replace("/", os.sep))
        if os.path.exists(tam_yol):
            with open(tam_yol, "r", encoding="utf-8") as f:
                dosyalar[dosya] = f.read()
            print(f"  ✅ {dosya}")
        else:
            print(f"  ⚠️  {dosya} — bulunamadı, atlandı")

    if not dosyalar:
        print("\n❌ Hiç dosya okunamadı!")
        return

    # Supabase'e yükle
    print(f"\nSupabase'e yükleniyor → hedef: {hedef}, versiyon: {versiyon}")
    kayit = {
        "versiyon": versiyon,
        "hedef": hedef,
        "dosyalar": dosyalar,
        "durum": "bekliyor",
    }
    client.table("guncellemeler").insert(kayit).execute()

    print(f"\n✅ Güncelleme yayınlandı!")
    print(f"   Versiyon : {versiyon}")
    print(f"   Hedef    : {hedef}")
    print(f"   Dosya    : {len(dosyalar)} adet")
    print(f"\n   Lokasyonlar bir sonraki heartbeat'te (maks 2 dk) güncellenecek.")

    input("\nDevam etmek için Enter'a basın...")


if __name__ == "__main__":
    main()
