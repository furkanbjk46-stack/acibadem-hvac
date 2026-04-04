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

SILINECEK_LOKASYON = "maslak"

print(f"'{SILINECEK_LOKASYON}' test verileri Supabase'den siliniyor...")

try:
    r1 = client.table('energy_data').delete().eq('lokasyon_id', SILINECEK_LOKASYON).execute()
    print(f"✅ energy_data: {len(r1.data)} kayıt silindi")

    r2 = client.table('hvac_summary').delete().eq('lokasyon_id', SILINECEK_LOKASYON).execute()
    print(f"✅ hvac_summary: {len(r2.data)} kayıt silindi")

    r3 = client.table('lokasyonlar').delete().eq('lokasyon_id', SILINECEK_LOKASYON).execute()
    print(f"✅ lokasyonlar: {len(r3.data)} kayıt silindi")

    print(f"\n✅ '{SILINECEK_LOKASYON}' test verileri başarıyla temizlendi!")
except Exception as e:
    print(f"❌ Hata: {e}")
