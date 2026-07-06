-- ═══════════════════════════════════════════════════════════════
-- QR SAHA BAKIM KARTLARI — Supabase tablosu (TEK SEFERLİK KURULUM)
-- Supabase Dashboard → SQL Editor → bu dosyanın içeriğini yapıştır → Run
-- ═══════════════════════════════════════════════════════════════
-- Akış:
--   • Lokasyon PC'si (cloud_sync.py) kartları 2 dakikada bir buraya
--     gönderir ve sahadan yapılan değişiklikleri buradan çeker.
--   • Sahadaki QR etiketi merkez portalı açar (?bakim=<cihaz>&lok=<lokasyon>),
--     teknisyen durumu değiştirir → bu tabloya yazılır.
--   • Cihaz listesinin sahibi LOKASYON portalıdır: lokalde silinen cihazın
--     satırı buradan da otomatik silinir.

create table if not exists bakim_kartlari (
    lokasyon_id text        not null,
    cihaz       text        not null,
    kart        jsonb       not null default '{}'::jsonb,
    updated_at  timestamptz not null default now(),
    updated_by  text        default '',
    primary key (lokasyon_id, cihaz)
);

-- Mevcut tablolarla (energy_data vb.) aynı erişim modeli:
-- anon/publishable key ile okuma-yazma (RLS kapalı).
alter table bakim_kartlari disable row level security;
