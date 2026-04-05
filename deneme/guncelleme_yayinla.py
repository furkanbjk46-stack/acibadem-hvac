# guncelleme_yayinla.py
# Geliştirme makinesinde çalıştırılır.
# Seçilen .py dosyalarını Supabase'e yükler → lokasyonlar otomatik güncellenir.

import sys
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')

import os
import json
from datetime import datetime

# Güncellemeye dahil edilecek dosyalar (değişiklik yaptıkça buraya ekle)
GUNCELLENECEK_DOSYALAR = [
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
    "GUNCELLE.bat",
]

CONFIG_FILE = os.path.join(os.path.dirname(__file__), "supabase_config.json")
SECRET_FILE = os.path.join(os.path.dirname(__file__), "supabase_secret.json")

def main():
    print("=" * 55)
    print("  HVAC Sistemi — Güncelleme Yayınlama Aracı")
    print("=" * 55)

    # Config oku
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    # Service role key oku (sadece GM bilgisayarında bulunur)
    if not os.path.exists(SECRET_FILE):
        print("\n❌ supabase_secret.json bulunamadı!")
        print("   Bu dosya sadece GM bilgisayarında bulunur.")
        print("   Supabase dashboard'dan service_role key'i alıp oluşturun.")
        input("\nDevam etmek için Enter'a basın...")
        return

    with open(SECRET_FILE, "r", encoding="utf-8") as f:
        secret = json.load(f)

    service_key = secret.get("service_role_key", "")
    if not service_key or "BURAYA" in service_key:
        print("\n❌ supabase_secret.json içinde geçerli bir service_role_key yok!")
        return

    from supabase import create_client
    # Service role key ile bağlan → RLS bypass → insert yetkisi var
    client = create_client(cfg["supabase_url"], service_key)

    # Versiyon
    versiyon = input("\nVersiyon numarası girin (ör: 2.1): ").strip()
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

    # Dosyaları oku
    print(f"\nDosyalar okunuyor...")
    base_dir = os.path.dirname(__file__)
    dosyalar = {}
    eksik = []

    for dosya in GUNCELLENECEK_DOSYALAR:
        tam_yol = os.path.join(base_dir, dosya)
        if os.path.exists(tam_yol):
            with open(tam_yol, "r", encoding="utf-8") as f:
                dosyalar[dosya] = f.read()
            print(f"  ✅ {dosya}")
        else:
            eksik.append(dosya)
            print(f"  ⚠️  {dosya} — bulunamadı, atlandı")

    if not dosyalar:
        print("\n❌ Hiç dosya bulunamadı!")
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
