-- ═══════════════════════════════════════════════════════════════
-- CANLI TRAFO GÜCÜ (kW) — Supabase tablosu (TEK SEFERLİK KURULUM)
-- Supabase Dashboard → SQL Editor → bu dosyanın içeriğini yapıştır → Run
-- ═══════════════════════════════════════════════════════════════
-- Akış:
--   • Lokasyon PC'si (data_collector.py → canli_guc.py) TRDP sayaçlarını
--     ~15 saniyede bir okur; cloud_sync.py sonucu buraya yazar.
--   • Merkez portalda "Lokasyon detayı" penceresinin sağ sütunu bu tabloyu
--     10 saniyede bir okur (karsilastirma_panel.py, st.fragment).
--   • Satır sayısı SABİTTİR: her lokasyon × her sayaç için TEK satır,
--     üzerine yazılır. Tarihçe tutulmaz — bu tablo "şu an" tablosudur,
--     geçmiş tüketim energy_data'da durur.
--
-- Alanlar:
--   kw           anlık güç (kW). null = o tur okunamadı.
--   yontem       değer nereden geldi:
--                  register  → cihazın güç register'ı, kWh sayacıyla doğrulandı
--                  register? → güç register'ı, henüz doğrulanmadı
--                  sayac     → kWh sayacının farkından (register yok/çelişti)
--   aciklama     yöntem neden düştüyse gerekçesi (ekranda ipucu olarak çıkar)
--   olcum_zamani SAHADAKİ okuma anı — merkez bununla "akış durmuş mu" der;
--                sunucuya yazılma anı değildir.

create table if not exists canli_guc (
    lokasyon_id  text        not null,
    cihaz        text        not null,
    kw           double precision,
    yontem       text,
    aciklama     text,
    olcum_zamani timestamptz not null default now(),
    primary key (lokasyon_id, cihaz)
);

-- Mevcut tablolarla (energy_data, bakim_kartlari vb.) aynı erişim modeli:
-- anon/publishable key ile okuma-yazma (RLS kapalı).
alter table canli_guc disable row level security;
