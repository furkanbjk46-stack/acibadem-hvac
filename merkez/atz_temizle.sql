-- ============================================================================
--  ALTUNİZADE DENEME KURULUMU — VERİ TEMİZLİĞİ
--  Supabase Dashboard → SQL Editor → yapıştır → Run
-- ============================================================================
--
--  NEDEN: Altunizade deneme amaçlı kurulmuştu; sahada hiçbir nokta bağlantısı
--  yok, lokasyon 7 Temmuz 2026'dan beri çevrimdışı. Synapse'e bağlı tek gerçek
--  lokasyon Maslak.
--
--  KAPSAM (21.09.2026 envanteri):
--    guncellemeler   31  — bekleyen yamalar (v6.9 … v8.5)
--    energy_data    365  — günlük enerji satırları
--    lokasyonlar      1  — lokasyon kaydı / heartbeat
--    bakim_kartlari   1
--    lisanslar        1  — Altunizade PC'sinin lisansı
--    (hvac_summary, bildirimler, komutlar, lokasyon_noktalar: 0 kayıt)
--
--  SONUÇ: Synapse'te Altunizade kartı diğer kurulmamış hastaneler gibi
--  "kurulmadı" görünür. Hastane rehberindeki tanım (isim, harita konumu, m²)
--  kodda kalır — ileride gerçek kurulum yapılırsa aynı kimlikle devam eder.
--
--  GERİ ALINAMAZ. Aşağıda önce SAYIM, sonra SİLME var; tek işlem (transaction)
--  içinde çalışır — bir adım hata verirse hiçbiri uygulanmaz.
-- ============================================================================

-- ── 1) ÖNİZLEME — silinecek kayıt sayıları (önce bunu tek başına çalıştırın) ──
SELECT 'guncellemeler' AS tablo, count(*) FROM public.guncellemeler  WHERE hedef       = 'altunizade'
UNION ALL SELECT 'energy_data',     count(*) FROM public.energy_data    WHERE lokasyon_id = 'altunizade'
UNION ALL SELECT 'lokasyonlar',     count(*) FROM public.lokasyonlar    WHERE lokasyon_id = 'altunizade'
UNION ALL SELECT 'bakim_kartlari',  count(*) FROM public.bakim_kartlari WHERE lokasyon_id = 'altunizade'
UNION ALL SELECT 'lisanslar',       count(*) FROM public.lisanslar      WHERE lokasyon_id = 'altunizade'
UNION ALL SELECT 'hvac_summary',    count(*) FROM public.hvac_summary   WHERE lokasyon_id = 'altunizade'
UNION ALL SELECT 'bildirimler',     count(*) FROM public.bildirimler    WHERE lokasyon    = 'altunizade'
UNION ALL SELECT 'komutlar',        count(*) FROM public.komutlar       WHERE lokasyon    = 'altunizade';

-- ── 2) SİLME — önizleme beklendiği gibiyse bu bloğu çalıştırın ──────────────
BEGIN;
DELETE FROM public.guncellemeler  WHERE hedef       = 'altunizade';
DELETE FROM public.energy_data    WHERE lokasyon_id = 'altunizade';
DELETE FROM public.bakim_kartlari WHERE lokasyon_id = 'altunizade';
DELETE FROM public.hvac_summary   WHERE lokasyon_id = 'altunizade';
DELETE FROM public.bildirimler    WHERE lokasyon    = 'altunizade';
DELETE FROM public.komutlar       WHERE lokasyon    = 'altunizade';
DELETE FROM public.lisanslar      WHERE lokasyon_id = 'altunizade';
DELETE FROM public.lokasyonlar    WHERE lokasyon_id = 'altunizade';
COMMIT;

-- ── 3) DOĞRULAMA — hepsi 0 olmalı ────────────────────────────────────────────
-- (1. adımdaki SELECT'i tekrar çalıştırın)
