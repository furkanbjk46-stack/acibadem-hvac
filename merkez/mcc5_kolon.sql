-- ============================================================
-- MCC-5 SÜTUNU — energy_data
-- ============================================================
-- MCC-5 analizörü (Janitza, 172.17.91.104) 29.09.2026'da sahada devreye
-- alındı. Lokasyon programı günlük satıra artık MCC5_kWh yazıyor.
--
-- ⚠️ SIRA ÖNEMLİ: Bu SQL, lokasyon yaması (v8.9) gönderilmeden ÖNCE
-- çalıştırılmalıdır. Sütun yokken satırda MCC5_kWh gelirse PostgREST
-- "column does not exist" hatası verir ve ENERJİ SENKRONU TAMAMEN DURUR.
--
-- Çalıştırma: Supabase → SQL Editor → yapıştır → Run.
-- Tekrar çalıştırılması zararsızdır (IF NOT EXISTS).
-- ============================================================

ALTER TABLE energy_data
    ADD COLUMN IF NOT EXISTS "MCC5_kWh" numeric;

-- Doğrulama — bu sorgu satır döndürmeli:
SELECT column_name, data_type
FROM information_schema.columns
WHERE table_name = 'energy_data'
  AND column_name IN ('MCC5_kWh', 'TRDP2_kWh')
ORDER BY column_name;

-- NOT: TRDP-2 için yeni sütuna gerek YOK — TRDP2_kWh zaten mevcuttu,
-- şimdiye kadar boş geliyordu. 29.09.2026'dan itibaren Janitza
-- (172.17.91.119) üzerinden otomatik dolacak.
