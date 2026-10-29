-- ════════════════════════════════════════════════════════════════════════════
-- RLS TEMİZLİK — ADIM 1 (29.10.2026) · risksiz, mevcut hiçbir özelliği bozmaz
-- ════════════════════════════════════════════════════════════════════════════
-- rls_durum_raporu.sql sonucuna göre:
--   1) anon / authenticated rollerinde TRUNCATE, TRIGGER, REFERENCES yetkisi
--      vardı. Uygulama bunları HİÇ kullanmaz (PostgREST yalnız SELECT/INSERT/
--      UPDATE/DELETE yapar); TRUNCATE ise RLS'e takılmadan tabloyu boşaltır.
--   2) guncellemeler ve lisanslar'da aynı izin hem "public" hem "anon" için
--      iki kez tanımlı. "public" kopyası kaldırılır; anon kopyası kalır, yani
--      lokasyonun yama okuma/durum yazma ve lisans okuma işlemi AYNEN sürer.
-- DOKUNULMAYANLAR (ayrı adımda, kod değişikliğiyle): energy_data, hvac_summary.
-- service_role etkilenmez. Tekrar çalıştırılabilir.
-- ════════════════════════════════════════════════════════════════════════════

-- 1) Gereksiz tablo yetkileri
DO $$
DECLARE t RECORD;
BEGIN
  FOR t IN SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace
           WHERE n.nspname = 'public' AND c.relkind = 'r'
  LOOP
    EXECUTE format('REVOKE TRUNCATE, TRIGGER, REFERENCES ON TABLE public.%I FROM anon, authenticated', t.relname);
  END LOOP;
END $$;

-- 2) Çift tanımlı "public" politikaları kaldır — YALNIZ aynı işlem için anon
--    politikası da varsa (anon'un yetkisi kaybolmasın diye koşullu)
DO $$
DECLARE p RECORD;
BEGIN
  FOR p IN SELECT pp.policyname, pp.tablename, pp.cmd FROM pg_policies pp
           WHERE pp.schemaname = 'public'
             AND pp.tablename IN ('guncellemeler', 'lisanslar')
             AND pp.roles = '{public}'
             AND EXISTS (SELECT 1 FROM pg_policies a
                         WHERE a.schemaname = 'public' AND a.tablename = pp.tablename
                           AND a.cmd = pp.cmd AND 'anon' = ANY(a.roles))
  LOOP
    EXECUTE format('DROP POLICY %I ON public.%I', p.policyname, p.tablename);
    RAISE NOTICE 'kaldirildi: % (% %)', p.policyname, p.tablename, p.cmd;
  END LOOP;
END $$;

NOTIFY pgrst, 'reload schema';

-- Kontrol: bu iki tabloda kalan politikalar (yalnız anon) ve anon yetkileri
SELECT tablename, cmd, roles FROM pg_policies
WHERE schemaname = 'public' AND tablename IN ('guncellemeler', 'lisanslar') ORDER BY 1, 2;
SELECT table_name, string_agg(privilege_type, ',' ORDER BY privilege_type) AS anon_grant
FROM information_schema.role_table_grants
WHERE table_schema = 'public' AND grantee = 'anon' GROUP BY 1 ORDER BY 1;
