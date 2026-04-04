from supabase import create_client

c = create_client(
    'https://qayjwkqnnjjsnnxovhei.supabase.co',
    'sb_publishable_m22uNXePA5Av6ocWHJsa5Q_OQFY36Oq'
)

# Mevcut sutunlari kontrol et
r = c.table('lokasyonlar').select('*').execute()
if r.data:
    print("Mevcut sutunlar:", list(r.data[0].keys()))
else:
    print("Tablo bos")

# ping_zamani ile upsert dene
import json
from datetime import datetime
test_info = {
    "lokasyon_id": "maslak",
    "isim": "Acibadem Maslak",
    "ping_zamani": datetime.now().isoformat(),
    "son_sync": datetime.now().isoformat(),
    "versiyon": "1.0",
    "durum": "online"
}
try:
    res = c.table('lokasyonlar').upsert(test_info, on_conflict="lokasyon_id").execute()
    print("Upsert BASARILI:", res.data)
except Exception as e:
    print("Upsert HATA:", e)
