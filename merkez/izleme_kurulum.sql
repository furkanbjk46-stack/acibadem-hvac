-- ============================================================
-- SYNAPSE İZLEME — kullanım fonksiyonu
-- ============================================================
-- Tablo boyutları, disk kullanımı ve veritabanı sağlığı REST üzerinden
-- okunamaz (PostgREST yalnızca tabloları ve fonksiyonları açar). Bu SQL,
-- SALT OKUR bir fonksiyon oluşturur; sema_diyagram_uret.py onu çağırır.
--
-- Çalıştırma: Supabase → SQL Editor → yapıştır → Run. Bir kez yeterli.
-- Tekrar çalıştırmak zararsızdır (CREATE OR REPLACE).
--
-- GÜVENLİK: fonksiyon yalnızca service_role'a açılır; anon ve authenticated
-- rollerinden yetki geri alınır. Lokasyon PC'leri anon anahtar kullandığı
-- için bu bilgiyi göremez.
-- ============================================================

CREATE OR REPLACE FUNCTION public.synapse_kullanim()
RETURNS jsonb
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = public, pg_catalog
AS $$
  SELECT jsonb_build_object(
    'olculme', now(),
    'veritabani_bayt', pg_database_size(current_database()),
    'tablolar', (
      SELECT coalesce(jsonb_agg(t ORDER BY (t->>'toplam_bayt')::bigint DESC), '[]'::jsonb)
      FROM (
        SELECT jsonb_build_object(
                 'tablo',        c.relname,
                 'toplam_bayt',  pg_total_relation_size(c.oid),
                 'veri_bayt',    pg_table_size(c.oid),
                 'indeks_bayt',  pg_indexes_size(c.oid),
                 'satir_tahmin', GREATEST(c.reltuples::bigint, 0)
               ) AS t
        FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'r'
      ) s
    ),
    'saglik', (
      SELECT jsonb_build_object(
               'onbellek_isabet_yuzde',
                 round(100 * sum(blks_hit)::numeric
                       / NULLIF(sum(blks_hit) + sum(blks_read), 0), 2),
               'aktif_baglanti',  (SELECT count(*) FROM pg_stat_activity
                                    WHERE datname = current_database()),
               'azami_baglanti',  current_setting('max_connections')::int,
               'islem_commit',    sum(xact_commit),
               'islem_rollback',  sum(xact_rollback),
               'kilitlenme',      sum(deadlocks)
             )
      FROM pg_stat_database WHERE datname = current_database()
    )
  );
$$;

REVOKE ALL ON FUNCTION public.synapse_kullanim() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.synapse_kullanim() TO service_role;

-- Doğrulama — tek satır JSON dönmeli:
SELECT jsonb_pretty(public.synapse_kullanim());

-- ============================================================
-- İSTEĞE BAĞLI — CANLI YÖNETİM EKRANI İÇİN
-- ============================================================
-- Synapse portalı Supabase'e ANON anahtarla bağlanır. Yukarıdaki yetki
-- yalnızca service_role'a verildiği için canlı Yönetim ekranı ölçümü
-- okuyamaz. İki seçenekten BİRİNİ uygulayın:
--
--   A) (Kolay) Fonksiyonu anon'a da açın. Fonksiyon yalnızca TOPLAM
--      boyut/sağlık döndürür; hiçbir satır verisi sızmaz. Anon anahtar
--      lokasyon PC'lerinde de bulunduğu için, o anahtarı ele geçiren biri
--      tablo adlarını ve boyutlarını görebilir — veriyi göremez.
--
--        GRANT EXECUTE ON FUNCTION public.synapse_kullanim() TO anon;
--
--   B) (Sıkı) Streamlit Cloud → App settings → Secrets içine service_role
--      anahtarını ekleyin; yalnızca Yönetim ekranı kullanır:
--
--        [supabase]
--        service_key = "eyJ..."
--
-- B daha güvenlidir; A daha pratiktir. Seçim sizin.
