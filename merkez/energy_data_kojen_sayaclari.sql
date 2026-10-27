-- ════════════════════════════════════════════════════════════════════════════
-- energy_data: KOJEN-1..4 ÜRETİM SAYAÇLARI (27.10.2026)
-- ════════════════════════════════════════════════════════════════════════════
-- Lokasyonlar günlük satıra her kojenin üretimini ayrı yazacak:
--   Kojen3_kWh / Kojen4_kWh  Siemens PAC3200 sayacından otomatik (data_bridge)
--   Kojen1_kWh / Kojen2_kWh  sayaç bağlanana kadar formdan elle
-- Kojen_Uretim_kWh = dördünün toplamı (enerji_hesap.py).
--
-- ⚠ SIRA ÖNEMLİ: lokasyona yama gönderilmeden ÖNCE çalıştırılmalı — tabloda
--   olmayan sütun gelirse cloud_sync'in toplu insert'i TAMAMEN reddedilir ve
--   o lokasyonun enerji verisi buluta hiç gitmez.
-- Güvenli: yalnız sütun EKLER (IF NOT EXISTS), veri silmez/değiştirmez.
-- Tekrar çalıştırılabilir. Tip mevcut kWh sütunlarıyla aynı (real).
-- ════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.energy_data
  ADD COLUMN IF NOT EXISTS "Kojen1_kWh" real,
  ADD COLUMN IF NOT EXISTS "Kojen2_kWh" real,
  ADD COLUMN IF NOT EXISTS "Kojen3_kWh" real,
  ADD COLUMN IF NOT EXISTS "Kojen4_kWh" real;

NOTIFY pgrst, 'reload schema';

-- Kontrol: 4 satır, real
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'energy_data'
  AND column_name IN ('Kojen1_kWh', 'Kojen2_kWh', 'Kojen3_kWh', 'Kojen4_kWh');
