-- ════════════════════════════════════════════════════════════════════════════
-- energy_data: HAVA SÜTUNLARI (24.10.2026)
-- ════════════════════════════════════════════════════════════════════════════
-- Lokasyonlar artık günlük satıra şunları yazıyor (hava_durumu.py):
--   Dis_Hava_Nem_Yuzde            bina nem sensörü (BACnet "DIS HAVA NEM", 07:05 anlık)
--   Hava_*                        lokasyonun KENDİ koordinatından internetten günlük hava
--
-- ⚠ SIRA ÖNEMLİ: Bu SQL, lokasyona yama gönderilmeden ÖNCE çalıştırılmalı.
--   cloud_sync energy_data'yı toplu insert eder; tabloda olmayan bir sütun
--   gelirse insert TAMAMEN reddedilir ve o lokasyonun enerji verisi buluta
--   hiç gitmez.
--
-- Güvenli: yalnız sütun EKLER (IF NOT EXISTS), veri silmez/değiştirmez.
-- Tekrar çalıştırılabilir. Sayısal tipler mevcut sütunlarla aynı (real).
-- ════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.energy_data
  ADD COLUMN IF NOT EXISTS "Dis_Hava_Nem_Yuzde"          real,
  ADD COLUMN IF NOT EXISTS "Hava_Sicaklik_Ort_C"         real,
  ADD COLUMN IF NOT EXISTS "Hava_Sicaklik_Max_C"         real,
  ADD COLUMN IF NOT EXISTS "Hava_Sicaklik_Min_C"         real,
  ADD COLUMN IF NOT EXISTS "Hava_Nem_Ort_Yuzde"          real,
  ADD COLUMN IF NOT EXISTS "Hava_Yagis_mm"               real,
  ADD COLUMN IF NOT EXISTS "Hava_Bulut_Yuzde"            real,
  ADD COLUMN IF NOT EXISTS "Hava_Gunes_Radyasyon_kWh_m2" real,
  ADD COLUMN IF NOT EXISTS "Hava_Ruzgar_Ort_kmh"         real,
  ADD COLUMN IF NOT EXISTS "Hava_Durumu"                 text;

-- PostgREST yeni sütunları hemen görsün (yoksa birkaç dakika eski şemayla çalışır)
NOTIFY pgrst, 'reload schema';

-- Kontrol: 10 satır dönmeli
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'energy_data'
  AND (column_name LIKE 'Hava\_%' OR column_name = 'Dis_Hava_Nem_Yuzde')
ORDER BY column_name;
