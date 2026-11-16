-- Cookieless PlainBTC pageview beacons. No IP, no cookies.
-- Written by the Cloudflare Pages Function POST /api/hit (functions/api/hit.js).
-- Applied to project ygilpnmqkduzhdkxdyxj. This file matches the production definitions as read
-- from the database on 2026-11-16 (pg_get_functiondef, pg_indexes, pg_policy, table grants).
-- Query stats with:
--   SELECT * FROM public.plainbtc_daily_stats();              -- today, America/Chicago
--   SELECT * FROM public.plainbtc_daily_stats('2026-11-09');  -- a given Chicago day
-- plainbtc_daily_stats is a FUNCTION, not a table or view: always write the parentheses.
-- "SELECT * FROM public.plainbtc_daily_stats" without them fails with
-- relation "public.plainbtc_daily_stats" does not exist.

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
  'PlainBTC cookieless pageviews. No cookies, no raw IPs. visitor_hash is a daily salted hash for unique estimates.';

create index if not exists pageviews_ts_idx on public.pageviews (ts desc);
create index if not exists pageviews_path_idx on public.pageviews (path);
-- Matches the day filter in plainbtc_daily_stats.
create index if not exists pageviews_day_idx
  on public.pageviews (((timezone('America/Chicago', ts))::date));

alter table public.pageviews enable row level security;

drop policy if exists pageviews_anon_insert on public.pageviews;
create policy pageviews_anon_insert
  on public.pageviews
  for insert
  to anon, authenticated
  with check (true);

grant insert on table public.pageviews to anon, authenticated;
-- Supabase's default privileges grant ALL on new tables in schema public to anon and
-- authenticated. Take back reading and changing rows: the Data API may only INSERT.
revoke select, update, delete on table public.pageviews from anon, authenticated;
-- The dashboard / SQL editor uses the owner or service role.

create or replace function public.plainbtc_daily_stats(
  day_ct date default (timezone('America/Chicago', now()))::date
)
returns table (
  day date,
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
stable
security definer
set search_path to 'public'
as $function$
WITH base AS (
  SELECT *
  FROM public.pageviews p
  WHERE timezone('America/Chicago', p.ts)::date = day_ct
),
counts AS (
  SELECT
    day_ct AS day,
    count(*)::bigint AS pageviews,
    count(DISTINCT visitor_hash) FILTER (WHERE visitor_hash IS NOT NULL)::bigint AS uniques
  FROM base
),
paths AS (
  SELECT coalesce(jsonb_agg(row_to_json(t)::jsonb ORDER BY t.c DESC), '[]'::jsonb) AS top_paths
  FROM (
    SELECT path AS k, count(*)::int AS c FROM base GROUP BY path ORDER BY c DESC LIMIT 15
  ) t
),
refs AS (
  SELECT coalesce(jsonb_agg(row_to_json(t)::jsonb ORDER BY t.c DESC), '[]'::jsonb) AS top_referrers
  FROM (
    SELECT coalesce(nullif(referrer_host, ''), '(direct)') AS k, count(*)::int AS c
    FROM base GROUP BY 1 ORDER BY c DESC LIMIT 15
  ) t
),
utms AS (
  SELECT coalesce(jsonb_agg(row_to_json(t)::jsonb ORDER BY t.c DESC), '[]'::jsonb) AS top_utm_sources
  FROM (
    SELECT coalesce(nullif(utm_source, ''), '(none)') AS k, count(*)::int AS c
    FROM base GROUP BY 1 ORDER BY c DESC LIMIT 15
  ) t
),
langs AS (
  SELECT coalesce(jsonb_agg(row_to_json(t)::jsonb ORDER BY t.c DESC), '[]'::jsonb) AS by_lang
  FROM (
    SELECT coalesce(nullif(lang, ''), '?') AS k, count(*)::int AS c
    FROM base GROUP BY 1 ORDER BY c DESC
  ) t
),
countries AS (
  SELECT coalesce(jsonb_agg(row_to_json(t)::jsonb ORDER BY t.c DESC), '[]'::jsonb) AS by_country
  FROM (
    SELECT coalesce(nullif(country, ''), '?') AS k, count(*)::int AS c
    FROM base GROUP BY 1 ORDER BY c DESC LIMIT 20
  ) t
),
devices AS (
  SELECT coalesce(jsonb_agg(row_to_json(t)::jsonb ORDER BY t.c DESC), '[]'::jsonb) AS by_device
  FROM (
    SELECT coalesce(nullif(device, ''), '?') AS k, count(*)::int AS c
    FROM base GROUP BY 1 ORDER BY c DESC
  ) t
)
SELECT
  counts.day,
  counts.pageviews,
  counts.uniques,
  paths.top_paths,
  refs.top_referrers,
  utms.top_utm_sources,
  langs.by_lang,
  countries.by_country,
  devices.by_device
FROM counts, paths, refs, utms, langs, countries, devices;
$function$;

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
