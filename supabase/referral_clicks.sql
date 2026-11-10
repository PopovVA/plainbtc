-- Cookieless PlainBTC referral click beacons. No IP, no cookies.
-- Applied to project ygilpnmqkduzhdkxdyxj. Query stats with:
--   SELECT * FROM public.plainbtc_click_stats((timezone('America/Chicago', now()))::date);

create table if not exists public.referral_clicks (
  id bigint generated always as identity primary key,
  ts timestamptz not null default now(),
  partner text not null,
  path text,
  lang text,
  referrer_host text,
  utm_source text
);

comment on table public.referral_clicks is
  'Cookieless PlainBTC referral click beacons. No IP addresses and no cookies are stored.';

create index if not exists referral_clicks_ts_idx on public.referral_clicks (ts desc);
create index if not exists referral_clicks_partner_ts_idx on public.referral_clicks (partner, ts desc);

alter table public.referral_clicks enable row level security;

drop policy if exists referral_clicks_anon_insert on public.referral_clicks;
create policy referral_clicks_anon_insert
  on public.referral_clicks
  for insert
  to anon
  with check (true);

grant insert on table public.referral_clicks to anon;
-- No SELECT for anon. The dashboard / SQL editor uses the owner or service role.

create or replace function public.plainbtc_click_stats(d date)
returns table (clicks bigint, by_partner jsonb, by_path jsonb)
language sql
security definer
set search_path = public
stable
as $$
  with day as (
    select *
    from public.referral_clicks
    where ts >= ((d::timestamp) at time zone 'America/Chicago')
      and ts <  (((d + 1)::timestamp) at time zone 'America/Chicago')
  ),
  p as (
    select coalesce(
      jsonb_agg(jsonb_build_object('k', partner, 'c', c) order by c desc, partner),
      '[]'::jsonb
    ) as j
    from (select partner, count(*)::int as c from day group by partner) s
  ),
  pg as (
    select coalesce(
      jsonb_agg(jsonb_build_object('k', path, 'c', c) order by c desc, path),
      '[]'::jsonb
    ) as j
    from (select path, count(*)::int as c from day group by path) s
  )
  select
    (select count(*) from day),
    (select j from p),
    (select j from pg);
$$;

comment on function public.plainbtc_click_stats(date) is
  'Referral click counts for one America/Chicago calendar day, grouped by partner and page path.';

revoke all on function public.plainbtc_click_stats(date) from public, anon;
grant execute on function public.plainbtc_click_stats(date) to authenticated;
