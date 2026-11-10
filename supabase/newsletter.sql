-- PlainBTC newsletter backend (Supabase project foliata, schema public).
-- Applied via Supabase migration "plainbtc_newsletter". Idempotent where possible.
-- Security model: anon can only call the SECURITY DEFINER RPCs below; tables have RLS on + no grants.
-- Emails are never readable through the Data API. Provider API key lives in supabase_vault
-- (secret name 'plainbtc_resend_key'), never in the repo.

create extension if not exists pg_net with schema extensions;
create extension if not exists pgcrypto with schema extensions;

create table if not exists public.newsletter_subscribers (
  id uuid primary key default gen_random_uuid(),
  email text not null,
  lang text not null default 'en',
  source text,
  status text not null default 'pending' check (status in ('pending','confirmed','unsubscribed')),
  confirm_token text not null default encode(extensions.gen_random_bytes(24),'hex'),
  unsubscribe_token text not null default encode(extensions.gen_random_bytes(24),'hex'),
  created_at timestamptz not null default now(),
  confirmed_at timestamptz,
  unsubscribed_at timestamptz,
  confirmation_sent_at timestamptz,
  confirmation_attempts int not null default 0,
  last_digest_at timestamptz,
  constraint newsletter_email_lower check (email = lower(email)),
  constraint newsletter_email_len check (char_length(email) <= 254)
);
create unique index if not exists newsletter_subscribers_email_key on public.newsletter_subscribers (email);
create unique index if not exists newsletter_subscribers_confirm_token_key on public.newsletter_subscribers (confirm_token);
create unique index if not exists newsletter_subscribers_unsub_token_key on public.newsletter_subscribers (unsubscribe_token);
alter table public.newsletter_subscribers enable row level security;
revoke all on public.newsletter_subscribers from anon, authenticated, public;

create table if not exists public.newsletter_signup_log (
  id bigserial primary key,
  created_at timestamptz not null default now(),
  ip_hash text
);
create index if not exists newsletter_signup_log_created_idx on public.newsletter_signup_log (created_at);
alter table public.newsletter_signup_log enable row level security;
revoke all on public.newsletter_signup_log from anon, authenticated, public;

create table if not exists public.newsletter_state (
  key text primary key,
  value jsonb not null,
  updated_at timestamptz not null default now()
);
alter table public.newsletter_state enable row level security;
revoke all on public.newsletter_state from anon, authenticated, public;

create table if not exists public.newsletter_admin (
  id int primary key default 1 check (id = 1),
  token_sha256 text not null
);
alter table public.newsletter_admin enable row level security;
revoke all on public.newsletter_admin from anon, authenticated, public;

create table if not exists public.newsletter_templates (
  lang text not null,
  kind text not null,
  subject text not null,
  html text not null,
  body_text text not null,
  primary key (lang, kind)
);
alter table public.newsletter_templates enable row level security;
revoke all on public.newsletter_templates from anon, authenticated, public;

-- ---------------------------------------------------------------- internal helpers
create or replace function public.nl_send_confirmation(p_id uuid) returns boolean
language plpgsql security definer set search_path = '' as $$
declare
  s public.newsletter_subscribers;
  t public.newsletter_templates;
  k text;
  cu text; uu text;
  h text; tx text;
begin
  select * into s from public.newsletter_subscribers where id = p_id;
  if not found or s.status <> 'pending' then return false; end if;
  select decrypted_secret into k from vault.decrypted_secrets where name = 'plainbtc_resend_key' limit 1;
  if k is null or k = '' then return false; end if;
  select * into t from public.newsletter_templates where lang = s.lang and kind = 'confirm';
  if not found then select * into t from public.newsletter_templates where lang = 'en' and kind = 'confirm'; end if;
  if not found then return false; end if;
  cu := 'https://plainbtc.com/api/confirm?token=' || s.confirm_token;
  uu := 'https://plainbtc.com/api/unsubscribe?token=' || s.unsubscribe_token;
  h := replace(replace(t.html, '{{confirm_url}}', cu), '{{unsubscribe_url}}', uu);
  tx := replace(replace(t.body_text, '{{confirm_url}}', cu), '{{unsubscribe_url}}', uu);
  perform net.http_post(
    url := 'https://api.resend.com/emails',
    headers := jsonb_build_object('Authorization', 'Bearer ' || k, 'Content-Type', 'application/json'),
    body := jsonb_build_object(
      'from', 'PlainBTC <news@plainbtc.com>',
      'to', jsonb_build_array(s.email),
      'subject', t.subject,
      'html', h,
      'text', tx,
      'headers', jsonb_build_object(
        'List-Unsubscribe', '<' || uu || '>',
        'List-Unsubscribe-Post', 'List-Unsubscribe=One-Click')
    ),
    timeout_milliseconds := 10000
  );
  update public.newsletter_subscribers
     set confirmation_sent_at = now(), confirmation_attempts = confirmation_attempts + 1
   where id = p_id;
  return true;
end $$;
revoke all on function public.nl_send_confirmation(uuid) from public, anon, authenticated;

create or replace function public.nl_is_admin(p_token text) returns boolean
language sql security definer set search_path = '' stable as $$
  select exists (select 1 from public.newsletter_admin
                 where token_sha256 = encode(extensions.digest(coalesce(p_token,''), 'sha256'), 'hex'));
$$;
revoke all on function public.nl_is_admin(text) from public, anon, authenticated;

-- ---------------------------------------------------------------- public RPCs (anon)
-- Always returns 'ok' for any syntactically valid address (no account enumeration).
create or replace function public.newsletter_subscribe(p_email text, p_lang text, p_source text, p_ip_hash text)
returns text language plpgsql security definer set search_path = '' as $$
declare
  e text := lower(btrim(coalesce(p_email,'')));
  l text := lower(left(coalesce(p_lang,'en'), 5));
  s public.newsletter_subscribers;
  n_global int; n_ip int;
begin
  if char_length(e) < 6 or char_length(e) > 254
     or e !~ '^[a-z0-9._%+''-]+@[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)*\.[a-z]{2,24}$' then
    return 'invalid';
  end if;
  if l not in ('en','es','pt','fr','de','ru','tr','id','ja','ko') then l := 'en'; end if;

  select count(*) into n_global from public.newsletter_signup_log where created_at > now() - interval '1 hour';
  if n_global >= 60 then return 'rate_limited'; end if;
  if p_ip_hash is not null then
    select count(*) into n_ip from public.newsletter_signup_log
     where ip_hash = p_ip_hash and created_at > now() - interval '1 hour';
    if n_ip >= 5 then return 'rate_limited'; end if;
  end if;
  insert into public.newsletter_signup_log (ip_hash) values (left(p_ip_hash, 64));

  select * into s from public.newsletter_subscribers where email = e;
  if not found then
    insert into public.newsletter_subscribers (email, lang, source)
      values (e, l, left(p_source, 300)) returning * into s;
    perform public.nl_send_confirmation(s.id);
  elsif s.status = 'confirmed' then
    null;  -- already subscribed; silently ok
  elsif s.status = 'unsubscribed' then
    update public.newsletter_subscribers
       set status = 'pending', lang = l, source = coalesce(left(p_source,300), source),
           confirmation_attempts = 0, confirmation_sent_at = null
     where id = s.id;
    perform public.nl_send_confirmation(s.id);
  else  -- pending: resend at most every 10 minutes, max 5 times
    if s.confirmation_attempts < 5 and (s.confirmation_sent_at is null or s.confirmation_sent_at < now() - interval '10 minutes') then
      update public.newsletter_subscribers set lang = l where id = s.id;
      perform public.nl_send_confirmation(s.id);
    end if;
  end if;
  return 'ok';
end $$;

create or replace function public.newsletter_confirm(p_token text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare s public.newsletter_subscribers;
begin
  if p_token is null or p_token !~ '^[0-9a-f]{48}$' then return jsonb_build_object('ok', false); end if;
  select * into s from public.newsletter_subscribers where confirm_token = p_token;
  if not found then return jsonb_build_object('ok', false); end if;
  if s.status <> 'confirmed' then
    update public.newsletter_subscribers
       set status = 'confirmed', confirmed_at = now(), unsubscribed_at = null where id = s.id;
  end if;
  return jsonb_build_object('ok', true, 'lang', s.lang);
end $$;

create or replace function public.newsletter_unsubscribe(p_token text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare s public.newsletter_subscribers;
begin
  if p_token is null or p_token !~ '^[0-9a-f]{48}$' then return jsonb_build_object('ok', false); end if;
  select * into s from public.newsletter_subscribers where unsubscribe_token = p_token;
  if not found then return jsonb_build_object('ok', false); end if;
  if s.status <> 'unsubscribed' then
    update public.newsletter_subscribers set status = 'unsubscribed', unsubscribed_at = now() where id = s.id;
  end if;
  return jsonb_build_object('ok', true, 'lang', s.lang);
end $$;

grant execute on function public.newsletter_subscribe(text,text,text,text) to anon, authenticated;
grant execute on function public.newsletter_confirm(text) to anon, authenticated;
grant execute on function public.newsletter_unsubscribe(text) to anon, authenticated;
revoke execute on function public.newsletter_subscribe(text,text,text,text) from public;
revoke execute on function public.newsletter_confirm(text) from public;
revoke execute on function public.newsletter_unsubscribe(text) from public;

-- ---------------------------------------------------------------- admin RPCs (secret admin token, hash stored in newsletter_admin)
create or replace function public.newsletter_admin_subscribers(p_admin text)
returns table (id uuid, email text, lang text, unsubscribe_token text, last_digest_at timestamptz)
language plpgsql security definer set search_path = '' as $$
begin
  if not public.nl_is_admin(p_admin) then raise exception 'forbidden' using errcode = '42501'; end if;
  return query select s.id, s.email, s.lang, s.unsubscribe_token, s.last_digest_at
                 from public.newsletter_subscribers s where s.status = 'confirmed' order by s.created_at;
end $$;

create or replace function public.newsletter_admin_get_state(p_admin text) returns jsonb
language plpgsql security definer set search_path = '' as $$
declare v jsonb;
begin
  if not public.nl_is_admin(p_admin) then raise exception 'forbidden' using errcode = '42501'; end if;
  select value into v from public.newsletter_state where key = 'digest';
  return coalesce(v, '{}'::jsonb);
end $$;

create or replace function public.newsletter_admin_set_state(p_admin text, p_value jsonb, p_sent_ids uuid[])
returns void language plpgsql security definer set search_path = '' as $$
begin
  if not public.nl_is_admin(p_admin) then raise exception 'forbidden' using errcode = '42501'; end if;
  insert into public.newsletter_state (key, value) values ('digest', p_value)
    on conflict (key) do update set value = excluded.value, updated_at = now();
  if p_sent_ids is not null then
    update public.newsletter_subscribers set last_digest_at = now() where id = any(p_sent_ids);
  end if;
end $$;

-- Re-sends confirmation mails for pending signups that never got one (e.g. provider key was added later).
create or replace function public.newsletter_admin_send_pending(p_admin text) returns int
language plpgsql security definer set search_path = '' as $$
declare r record; n int := 0;
begin
  if not public.nl_is_admin(p_admin) then raise exception 'forbidden' using errcode = '42501'; end if;
  for r in select id from public.newsletter_subscribers
            where status = 'pending' and confirmation_sent_at is null and created_at > now() - interval '7 days' loop
    if public.nl_send_confirmation(r.id) then n := n + 1; end if;
  end loop;
  return n;
end $$;

create or replace function public.newsletter_admin_stats(p_admin text) returns jsonb
language plpgsql security definer set search_path = '' as $$
begin
  if not public.nl_is_admin(p_admin) then raise exception 'forbidden' using errcode = '42501'; end if;
  return (select jsonb_build_object(
    'pending', count(*) filter (where status='pending'),
    'confirmed', count(*) filter (where status='confirmed'),
    'unsubscribed', count(*) filter (where status='unsubscribed')) from public.newsletter_subscribers);
end $$;

do $$ declare f text; begin
  foreach f in array array[
    'newsletter_admin_subscribers(text)','newsletter_admin_get_state(text)',
    'newsletter_admin_set_state(text,jsonb,uuid[])','newsletter_admin_send_pending(text)','newsletter_admin_stats(text)'] loop
    execute format('revoke execute on function public.%s from public', f);
    execute format('grant execute on function public.%s to anon, authenticated', f);
  end loop; end $$;
