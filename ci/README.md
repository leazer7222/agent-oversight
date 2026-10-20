# CI workflow - staged here, not yet active

`github-workflow-ci.yml` is the complete CI pipeline for this repository. It is
**not** at `.github/workflows/ci.yml` yet, and therefore does not run.

## Why it is parked here

GitHub refuses a push that creates or updates a file under `.github/workflows/`
unless the pushing token carries the `workflow` OAuth scope:

```
! [remote rejected] refusing to allow an OAuth App to create or update
  workflow `.github/workflows/ci.yml` without `workflow` scope
```

The two accounts available to this machine each have one half of what is needed:

| Account | Push to this repo | `workflow` scope |
|---|---|---|
| `leazer7222` (owner) | yes | **no** |
| `reformai-admin` | **no** | yes |

The SSH key on this machine also authenticates as `reformai-admin`, so it does
not help. Rather than block the security deployment on this, the workflow file
is parked here and the rest of the branch ships.

## Activating it - one of these, then move the file

1. `gh auth refresh --hostname github.com --scopes workflow` as `leazer7222`
   (opens a browser for approval), or
2. grant `reformai-admin` push access to the repo, since it already has the
   scope, or
3. create `.github/workflows/ci.yml` through the GitHub web UI and paste the
   contents of `github-workflow-ci.yml`.

Then:

```bash
git mv ci/github-workflow-ci.yml .github/workflows/ci.yml
git rm ci/README.md
git commit -m "Activate CI workflow"
```

## What it runs

Five jobs, none of which need live services, because a gate that requires
production credentials is a gate that gets skipped:

| Job | Checks |
|---|---|
| `migrations` | `check_migrations.py --from-migration 047` |
| `python-tests` | 88 tests across 5 suites, named individually so an import failure registers as a failure rather than as zero tests |
| `typescript` | `tsc --noEmit`, plus lint |
| `api-authorization` | 499 static checks that no route loses its tenant or admin guard |
| `secrets` | self-tested credential scanner |

Every one of these was run locally against this branch and passed.
