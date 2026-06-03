const { createClient } = require('@supabase/supabase-js');
const fs = require('fs');

const env = {};
if (fs.existsSync('.env.local')) {
  fs.readFileSync('.env.local', 'utf8').split('\n').forEach(line => {
    const [key, ...rest] = line.split('=');
    if (key && rest.length) env[key.trim()] = rest.join('=').trim();
  });
}

const supabase = createClient(env.NEXT_PUBLIC_SUPABASE_URL, env.SUPABASE_SERVICE_ROLE_KEY);

async function seedGeminiQuota() {
  const companyId = '87fb6e0d-ebff-4344-9b75-07c1a1a213ac'; // Personal

  console.log('--- Ensuring Google Provider Account exists ---');
  const { data: account, error: accError } = await supabase
    .from('provider_accounts')
    .upsert({
      provider: 'google',
      company_id: companyId,
      display_name: 'Google AI Studio (Gemini)',
      is_active: true,
      quota_reset_period: 'weekly',
      quota_reset_anchor: 1 // Monday
    }, { onConflict: 'provider,company_id' })
    .select();

  if (accError) {
    console.error('Error upserting provider account:', accError);
    return;
  }
  const accountId = account[0].id;
  console.log('Provider account confirmed:', accountId);

  const expiresAt = new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString();

  console.log('--- Seeding Initial Quota Snapshot ---');
  const snapshots = [
    { window_type: 'five_hour', quota_remaining_pct: 100 },
    { window_type: 'seven_day', quota_remaining_pct: 100 },
    { window_type: 'primary',   quota_remaining_pct: 100 }
  ];

  for (const snap of snapshots) {
    const { error: snapError } = await supabase
      .from('provider_quota_snapshots')
      .insert({
        provider_account_id: accountId,
        quota_remaining_pct: snap.quota_remaining_pct,
        snapshot_source: 'user_confirmed',
        confidence: 'high',
        window_type: snap.window_type,
        snapshotted_at: new Date().toISOString(),
        expires_at: expiresAt
      });

    if (snapError) {
      console.error(`Error inserting ${snap.window_type} snapshot:`, snapError);
    } else {
      console.log(`${snap.window_type} snapshot seeded successfully.`);
    }
  }

  console.log('\nDone! Gemini data should now appear in the dashboard.');
}

seedGeminiQuota().catch(console.error);
