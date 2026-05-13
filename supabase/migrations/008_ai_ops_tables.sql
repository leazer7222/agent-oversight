-- Provider accounts: one row per provider a user/company has configured
create table provider_accounts (
  id                   uuid primary key default gen_random_uuid(),
  company_id           uuid references companies(id) on delete cascade,
  provider             text not null check (provider in ('anthropic','openai','google')),
  account_type         text not null default 'subscription' check (account_type in ('subscription','api')),
  display_name         text,
  quota_reset_period   text check (quota_reset_period in ('weekly','monthly')),
  quota_reset_anchor   int,  -- day of week 0-6 (weekly) or day of month 1-31 (monthly)
  plan_tier            text, -- 'plus','pro','team','api' — informational
  is_active            boolean not null default true,
  created_at           timestamptz not null default now(),
  updated_at           timestamptz not null default now(),
  unique(company_id, provider)
);

-- Health snapshots: polled from provider status page APIs
create table provider_health_snapshots (
  id          uuid primary key default gen_random_uuid(),
  provider    text not null,
  status      text not null check (status in ('healthy','degraded','down','unknown')),
  latency_ms  int,
  details     jsonb,
  source_url  text,
  checked_at  timestamptz not null default now()
);
create index on provider_health_snapshots (provider, checked_at desc);

-- Quota snapshots: confirmed, estimated, or extension-read
create table provider_quota_snapshots (
  id                   uuid primary key default gen_random_uuid(),
  provider_account_id  uuid references provider_accounts(id) on delete cascade,
  snapshot_source      text not null check (snapshot_source in ('user_confirmed','browser_extension','api','estimated')),
  quota_remaining_pct  float check (quota_remaining_pct between 0 and 100),
  confidence           text not null check (confidence in ('high','moderate','low')),
  notes                text,
  snapshotted_at       timestamptz not null default now(),
  expires_at           timestamptz
);
create index on provider_quota_snapshots (provider_account_id, snapshotted_at desc);

-- Recommendation events: audit log of every generated recommendation
create table recommendation_events (
  id                   uuid primary key default gen_random_uuid(),
  company_id           uuid references companies(id),
  recommended_provider text,
  confidence           text,
  headline             text,
  reasons              jsonb,
  secondary_provider   text,
  secondary_note       text,
  cautions             jsonb,
  input_signals        jsonb,
  generated_at         timestamptz not null default now(),
  valid_until          timestamptz
);

-- Recommendation feedback: thumbs up/down per recommendation
create table recommendation_feedback (
  id                   uuid primary key default gen_random_uuid(),
  recommendation_id    uuid references recommendation_events(id) on delete cascade,
  was_accurate         boolean,
  actual_provider_used text,
  notes                text,
  feedback_at          timestamptz not null default now()
);

-- RLS: allow authenticated reads, service role full access
alter table provider_accounts         enable row level security;
alter table provider_health_snapshots enable row level security;
alter table provider_quota_snapshots  enable row level security;
alter table recommendation_events     enable row level security;
alter table recommendation_feedback   enable row level security;

create policy "auth read provider_accounts"         on provider_accounts         for select using (auth.role() = 'authenticated');
create policy "auth read provider_health_snapshots" on provider_health_snapshots for select using (auth.role() = 'authenticated');
create policy "auth read provider_quota_snapshots"  on provider_quota_snapshots  for select using (auth.role() = 'authenticated');
create policy "auth read recommendation_events"     on recommendation_events     for select using (auth.role() = 'authenticated');
create policy "auth read recommendation_feedback"   on recommendation_feedback   for select using (auth.role() = 'authenticated');
