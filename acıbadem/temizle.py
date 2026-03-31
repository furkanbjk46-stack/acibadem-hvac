import os
import sys

# Encoding fix for Windows
if hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8')
if hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8')

try:
    from supabase import create_client
except ImportError:
    print("Supabase kütüphanesi yok!")
    sys.exit(1)

url = "https://qayjwkqnnjjsnnxovhei.supabase.co"
key = "sb_publishable_m22uNXePA5Av6ocWHJsa5Q_OQFY36Oq"
client = create_client(url, key)

print("Buluttaki veriler temizleniyor...")

try:
    # Bütün veriyi silmek için 'id' = '0' olmayanı sil diyoruz (her şeyi kapsar)
    client.table('energy_data').delete().neq('lokasyon_id', 'sakin_olmayan_id').execute()
    client.table('hvac_summary').delete().neq('lokasyon_id', 'sakin_olmayan_id').execute()
    client.table('lokasyonlar').delete().neq('lokasyon_id', 'sakin_olmayan_id').execute()
    print("✅ Bütün bulut verileri başarıyla TERTEMİZ yapıldı!")
except Exception as e:
    print(f"❌ Bir hata oluştu: {e}")
