#!/usr/bin/env bash
# Local validation harness for migration 047 (P0-0 database hardening).
#
# Spins up a throwaway Postgres 17 container, builds a fixture that replicates
# the exact production preconditions for every object 047 touches, applies 047,
# and asserts the intended end state plus no-regression for service_role.
#
# Touches NO Supabase project and NO production data.
#
#   bash scripts/tests/run_047_local.sh
#
# Exit 0 = migration applies cleanly and all assertions pass.

set -euo pipefail

CONTAINER="ao-047-test"
PGPASS="p0test"
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO="$(cd "$HERE/../.." && pwd)"

cleanup() { docker rm -f "$CONTAINER" >/dev/null 2>&1 || true; }
trap cleanup EXIT
cleanup

echo "[1/6] starting postgres:17 container"
docker run -d --name "$CONTAINER" -e POSTGRES_PASSWORD="$PGPASS" postgres:17 >/dev/null

echo "[2/6] waiting for readiness"
for i in $(seq 1 60); do
  if docker exec "$CONTAINER" pg_isready -U postgres -q 2>/dev/null; then break; fi
  sleep 1
done
docker exec "$CONTAINER" pg_isready -U postgres -q

psql_run() {  # $1 = label, $2 = file
  echo "      applying $(basename "$2")"
  docker exec -i "$CONTAINER" psql -U postgres -d postgres \
    -v ON_ERROR_STOP=1 --quiet < "$2"
}

echo "[3/6] building fixture (production preconditions)"
psql_run fixture "$HERE/047_fixture.sql"

echo "[4/6] capturing pre-apply baseline"
docker exec -i "$CONTAINER" psql -U postgres -d postgres -t -A -F' | ' <<'SQL'
SELECT 'anon-executable functions', count(*)::text
  FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname IN ('public','platform','product_graph') AND p.prokind='f'
    AND has_function_privilege('anon', p.oid, 'EXECUTE')
UNION ALL
SELECT 'tables with RLS off (public)', count(*)::text
  FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='public' AND c.relkind='r' AND NOT c.relrowsecurity
UNION ALL
SELECT 'anon table grants', count(*)::text
  FROM information_schema.role_table_grants
  WHERE table_schema='public' AND grantee='anon'
UNION ALL
SELECT 'authenticated_* policies', count(*)::text
  FROM pg_policies WHERE schemaname='public' AND policyname LIKE 'authenticated_%';
SQL

echo "[5/6] applying migration 047"
psql_run migration "$REPO/supabase/migrations/047_p0_0_database_hardening.sql"

echo "[6/6] running assertions"
docker exec -i "$CONTAINER" psql -U postgres -d postgres \
  -v ON_ERROR_STOP=1 < "$HERE/047_assertions.sql"

echo
echo "RESULT: migration 047 applied cleanly and all assertions passed."
echo "Scope note: validates 047's own SQL against replicated preconditions."
echo "It does NOT replay migrations 001-046 and is not a substitute for the"
echo "post-apply production checks listed at the end of 047."
