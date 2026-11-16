-- Cookieless PlainBTC pageview beacons. No IP, no cookies.
-- Written by the Cloudflare Pages Function POST /api/hit (functions/api/hit.js).
-- Applied to project ygilpnmqkduzhdkxdyxj. Query stats with:
--   SELECT * FROM public.plainbtc_daily_stats((timezone('America/Chicago', now()))::date);
-- plainbtc_daily_stats is a FUNCTION, not a table or view: always call it with a date argument.

create table if not exists public.pageviews (
  id bigint generated always as identity primary key,
  ts timestamptz not null default now(),
  path text not null,
  lang text,
  referrer_host text,
  utm_source text,
  utm_medium text,
  utm_campaign text,
  country text,
  device text,
  visitor_hash text
);

comment on table public.pageviews is
  'Cookieless PlainBTC pageview beacons. No IP addresses and no cookies are stored; visitor_hash is a daily salted SHA-256 truncated to 16 hex chars.';

create index if not exists pageviews_ts_idx on public.pageviews (ts desc);
-- Supports count(distinct visitor_hash) inside one Chicago day.
create index if not exists pageviews_ts_visitor_hash_idx on public.pageviews (ts desc, visitor_hash);

alter table public.pageviews enable row level security;

drop policy if exists pageviews_anon_insert on public.pageviews;
create policy pageviews_anon_insert
  on public.pageviews
  for insert
  to anon
  with check (true);

grant insert on table public.pageviews to anon;
-- No SELECT for anon. The dashboard / SQL editor uses the owner or service role.

create or replace function public.plainbtc_daily_stats(d date)
returns table (
  pageviews bigint,
  uniques bigint,
  top_paths jsonb,
  top_referrers jsonb,
  top_utm_sources jsonb,
  by_lang jsonb,
  by_country jsonb,
  by_device jsonb
)
language sql
security definer
set search_path = public
stable
as $$
  with day as (
    select *
    from public.pageviews
    where ts >= ((d::timestamp) at time zone 'America/Chicago')
      and ts <  (((d + 1)::timestamp) at time zone 'America/Chicago')
  ),
  paths as (
    select coalesce(
      jsonb_agg(jsonb_build_object('k', path, 'c', c) order by c desc, path),
      '[]'::jsonb
    ) as j
    from (select path, count(*)::int as c from day group by path) s
  ),
  referrers as (
    select coalesce(
      jsonb_agg(jsonb_build_object('k', referrer_host, 'c', c) order by c desc, referrer_host),
      '[]'::jsonb
    ) as j
    from (select referrer_host, count(*)::int as c from day group by referrer_host) s
  ),
  utm_sources as (
    select coalesce(
      jsonb_agg(jsonb_build_object('k', utm_source, 'c', c) order by c desc, utm_source),
      '[]'::jsonb
    ) as j
    from (select utm_source, count(*)::int as c from day group by utm_source) s
  ),
  langs as (
    select coalesce(
      jsonb_agg(jsonb_build_object('k', lang, 'c', c) order by c desc, lang),
      '[]'::jsonb
    ) as j
    from (select lang, count(*)::int as c from day group by lang) s
  ),
  countries as (
    select coalesce(
      jsonb_agg(jsonb_build_object('k', country, 'c', c) order by c desc, country),
      '[]'::jsonb
    ) as j
    from (select country, count(*)::int as c from day group by country) s
  ),
  devices as (
    select coalesce(
      jsonb_agg(jsonb_build_object('k', device, 'c', c) order by c desc, device),
      '[]'::jsonb
    ) as j
    from (select device, count(*)::int as c from day group by device) s
  )
  select
    (select count(*) from day),
    (select count(distinct visitor_hash) from day),
    (select j from paths),
    (select j from referrers),
    (select j from utm_sources),
    (select j from langs),
    (select j from countries),
    (select j from devices);
$$;

comment on function public.plainbtc_daily_stats(date) is
  'Pageview totals for one America/Chicago calendar day: pageviews, uniques, and {k,c} JSON arrays for paths, referrer hosts, utm_sources, languages, countries and devices.';

revoke all on function public.plainbtc_daily_stats(date) from public;
-- In Supabase, "from public" is not enough: the project's default privileges on schema public
-- grant EXECUTE on every new function directly to anon, authenticated and service_role, and
-- revoking from PUBLIC leaves those direct grants in place. Without the next line this
-- security definer function would answer POST /rest/v1/rpc/plainbtc_daily_stats with the
-- public anon key and hand out paths, referrers and countries.
revoke execute on function public.plainbtc_daily_stats(date) from anon, authenticated;
grant execute on function public.plainbtc_daily_stats(date) to service_role;
-- Owner / service role only, on purpose. Unlike plainbtc_click_stats (granted to anon because
-- tools/click_stats.py calls it with the public anon key), nothing in this repo calls
-- plainbtc_daily_stats: it is read in the Supabase SQL editor. Grant execute to anon only if a
-- repo tool ever needs it with the public anon key.
