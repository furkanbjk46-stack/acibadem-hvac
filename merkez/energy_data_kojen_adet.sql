-- ════════════════════════════════════════════════════════════════════════════
-- energy_data: KOJEN ADEDİ (24.10.2026)
-- ════════════════════════════════════════════════════════════════════════════
-- Lokasyonlar günlük satıra çalışan kojen sayısını yazacak (BACnet KOJEN-1..4
-- DURUM BILGISI, data_bridge.py). Chiller_Adet / Kazan_Adet ile aynı tip.
--
-- ⚠ SIRA ÖNEMLİ: lokasyona yama gönderilmeden ÖNCE çalıştırılmalı — tabloda
--   olmayan sütun gelirse cloud_sync'in toplu insert'i TAMAMEN reddedilir.
-- Güvenli: yalnız sütun ekler, tekrar çalıştırılabilir.
-- ════════════════════════════════════════════════════════════════════════════

ALTER TABLE public.energy_data
  ADD COLUMN IF NOT EXISTS "Kojen_Adet" integer;

NOTIFY pgrst, 'reload schema';

-- Kontrol: 1 satır, integer
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_schema = 'public' AND table_name = 'energy_data' AND column_name = 'Kojen_Adet';
