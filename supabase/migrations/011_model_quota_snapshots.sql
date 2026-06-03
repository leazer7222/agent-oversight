-- Model-specific quota snapshots
create table model_quota_snapshots (
  id                   uuid primary key default gen_random_uuid(),
  provider_account_id  uuid references provider_accounts(id) on delete cascade,
  model_name           text not null,
  model_label          text, -- e.g., 'High', 'Thinking'
  quota_remaining_pct  float check (quota_remaining_pct between 0 and 100),
  resets_at            timestamptz,
  snapshotted_at       timestamptz not null default now(),
  expires_at           timestamptz
);

create index on model_quota_snapshots (provider_account_id, model_name, snapshotted_at desc);

alter table model_quota_snapshots enable row level security;
create policy "auth read model_quota_snapshots" on model_quota_snapshots for select using (auth.role() = 'authenticated');
