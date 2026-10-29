-- ════════════════════════════════════════════════════════════════════════════
-- RLS DURUM RAPORU (29.10.2026) — YALNIZ OKUR, hiçbir şeyi değiştirmez
-- ════════════════════════════════════════════════════════════════════════════
-- Ortak anon anahtar merkez/configs/merkez_config.json'da ve repo HERKESE AÇIK.
-- Bu sorgu her tablo için: RLS açık mı, anon/authenticated hangi işlemlere
-- izinli (politika), tablo yetkisi (GRANT) ne — tek tabloda gösterir.
-- Supabase Dashboard → SQL Editor → yapıştır → Run → sonucu paylaşın.
-- ════════════════════════════════════════════════════════════════════════════

SELECT
    c.relname                                         AS tablo,
    c.relrowsecurity                                  AS rls_acik,
    COALESCE((SELECT string_agg(p.cmd || ' → ' || array_to_string(p.roles, ','), ' | ' ORDER BY p.cmd)
              FROM pg_policies p
              WHERE p.schemaname = 'public' AND p.tablename = c.relname), '— politika yok —') AS politikalar,
    COALESCE((SELECT string_agg(DISTINCT g.privilege_type, ',' ORDER BY g.privilege_type)
              FROM information_schema.role_table_grants g
              WHERE g.table_schema = 'public' AND g.table_name = c.relname AND g.grantee = 'anon'), '') AS anon_grant
FROM pg_class c
JOIN pg_namespace n ON n.oid = c.relnamespace
WHERE n.nspname = 'public' AND c.relkind = 'r'
ORDER BY c.relrowsecurity, c.relname;
