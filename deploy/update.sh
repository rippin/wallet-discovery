#!/usr/bin/env bash
# Run on the VPS: bash deploy/update.sh
set -Eeuo pipefail

main() {
  local script_dir repo_root expected_branch remote branch previous current running backup_name
  script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
  repo_root="$(cd -- "$script_dir/.." && pwd)"
  cd -- "$repo_root"
  expected_branch="codex/wallet-observatory"
  remote="https://github.com/rippin/wallet-discovery.git"
  trap 'printf "\nUpdate stopped. See the error above; no data volumes were deleted.\n" >&2' ERR

  for command in git docker; do
    command -v "$command" >/dev/null || { printf 'Missing command: %s\n' "$command" >&2; return 1; }
  done
  docker compose version >/dev/null
  docker info >/dev/null
  [[ "$(git rev-parse --show-toplevel)" == "$repo_root" ]] || { echo 'Run from the wallet-discovery checkout.' >&2; return 1; }
  branch="$(git branch --show-current)"
  [[ "$branch" == "$expected_branch" ]] || { printf 'Expected branch %s; found %s. Switch branches explicitly first.\n' "$expected_branch" "$branch" >&2; return 1; }
  case "$(git remote get-url origin)" in
    "$remote"|https://github.com/rippin/wallet-discovery|git@github.com:rippin/wallet-discovery.git) ;;
    *) echo 'Origin does not match rippin/wallet-discovery; refusing to pull.' >&2; return 1 ;;
  esac
  [[ -z "$(git status --porcelain)" ]] || { echo 'Local code changes or untracked files found. Commit or move them before updating.' >&2; return 1; }

  if [[ "${1:-}" != '--after-pull' ]]; then
    [[ $# == 0 ]] || { echo 'Usage: bash deploy/update.sh' >&2; return 1; }
    previous="$(git rev-parse HEAD)"
    echo 'Fetching repository updates…'
    git fetch origin "$expected_branch"
    # Never overwrite local commits or silently deploy a branch ahead of origin.
    git merge-base --is-ancestor HEAD "origin/$expected_branch" || { echo 'Local branch diverges from or is ahead of origin; reconcile it manually.' >&2; return 1; }
    git merge --ff-only "origin/$expected_branch"
    current="$(git rev-parse HEAD)"
    printf 'Revision: %s → %s\n' "$previous" "$current"
    # Execute the updated script from its beginning, not a partially replaced file.
    exec bash "$repo_root/deploy/update.sh" --after-pull
  fi

  # Support the conventional filename without sourcing credentials as shell code.
  # The application-specific file takes precedence when both exist.
  if [[ ! -f .env.observatory && -f .env ]]; then
    (umask 077; cp .env .env.observatory)
    echo 'Imported existing .env into .env.observatory. Future updates use .env.observatory; the original .env was preserved.'
  fi
  if [[ ! -f .env.observatory ]]; then
    if [[ ! -t 0 ]]; then
      echo 'Missing .env.observatory. Run interactively once to enter an RPC URL or Helius API key and password.' >&2
      return 1
    fi
    local credential api_key="" rpc_url="" password monthly=900000 cost=10
    echo 'First-time setup. Credentials are saved only in the ignored .env.observatory file.'
    read -r -s -p 'HTTPS RPC URL (Chainstack, Alchemy, etc.) or Helius API key: ' credential; printf '\n'
    if [[ "$credential" == https://* ]]; then
      # Restrict dotenv metacharacters so credentials are saved literally.
      [[ "$credential" =~ ^https://[a-zA-Z0-9.-]+(:[0-9]+)?(/[a-zA-Z0-9_./?=\&%+~-]*)?$ ]] || { echo 'Enter an HTTPS RPC URL without spaces, quotes, or dotenv variables.' >&2; return 1; }
      rpc_url="$credential"
      if [[ "$rpc_url" =~ ^https://([a-zA-Z0-9-]+\.)*chainstack\.com/ ]]; then
        monthly=2700000; cost=2
      fi
    else
      [[ "$credential" =~ ^[a-zA-Z0-9_-]+$ ]] || { echo 'Expected an HTTPS RPC URL or Helius API key.' >&2; return 1; }
      api_key="$credential"
    fi
    printf 'Initial local budget: %s units/month, %s units/request. Adjust these in .env.observatory for your plan.\n' "$monthly" "$cost"
    read -r -s -p 'Dashboard password (20+ characters; letters, numbers, dash, underscore): ' password; printf '\n'
    [[ ${#password} -ge 20 && "$password" =~ ^[a-zA-Z0-9_-]+$ ]] || { echo 'Password must be 20+ characters using the requested character set.' >&2; return 1; }
    (umask 077
      printf 'OBS_PASSWORD=%s\nHELIUS_API_KEY=%s\nOBS_RPC_URL=%s\nOBS_LIVE=1\nOBS_MONTHLY_CREDITS=%s\nOBS_RPC_CREDIT_COST=%s\nOBS_CYCLE_SECONDS=300\n' "$password" "$api_key" "$rpc_url" "$monthly" "$cost" > .env.observatory
    )
    unset password api_key rpc_url credential
  fi
  chmod 600 .env.observatory
  # Do not source this file as shell code or print its resolved values.
  docker compose config --quiet
  echo 'Building the updated image (the existing service stays running)…'
  docker compose build --pull observatory
  echo 'Validating configuration…'
  docker compose run --rm --no-deps -T --entrypoint python observatory -c '
import os, sys
password=os.getenv("OBS_PASSWORD", "")
live=os.getenv("OBS_LIVE", "0")
if len(password)<20: sys.exit("OBS_PASSWORD must contain at least 20 characters")
if live!="1": sys.exit("Set OBS_LIVE=1 in .env.observatory to enable live collection")
if not (os.getenv("HELIUS_API_KEY") or os.getenv("OBS_RPC_URL")): sys.exit("Set HELIUS_API_KEY or OBS_RPC_URL")
for key in ("OBS_MONTHLY_CREDITS", "OBS_RPC_CREDIT_COST", "OBS_CYCLE_SECONDS"):
    if int(os.getenv(key, "1"))<=0: sys.exit(key+" must be positive")
print("Configuration valid; credentials were not printed")
'

  running="$(docker compose ps --status running --quiet observatory)"
  if [[ -n "$running" ]]; then
    backup_name="observatory-$(date -u +%Y%m%dT%H%M%SZ)-$$.sqlite3"
    echo 'Saving a consistent pre-update database backup…'
    mkdir -p backups
    docker compose exec -T observatory python -c '
import os, sqlite3, sys
source=os.environ.get("OBS_DB", "/data/observatory.sqlite3")
if not os.path.isfile(source): sys.exit("Existing database not found; refusing to create an empty backup")
path="/tmp/"+sys.argv[1]
a=sqlite3.connect(source); b=sqlite3.connect(path)
a.backup(b); b.close(); a.close()
' "$backup_name"
    docker compose cp "observatory:/tmp/$backup_name" "backups/$backup_name"
    chmod 600 "backups/$backup_name"
    printf 'Backup saved: backups/%s\n' "$backup_name"
  fi

  echo 'Starting the updated service…'
  docker compose up -d --no-deps --wait --wait-timeout 90 observatory
  # Verify authenticated HTTP, not merely that Docker started a process.
  docker compose exec -T observatory python -c '
import base64, os, time, urllib.request, sys
credential=base64.b64encode(("research:"+os.environ["OBS_PASSWORD"]).encode()).decode()
for attempt in range(15):
    try:
        request=urllib.request.Request("http://127.0.0.1:8080/api/summary",headers={"Authorization":"Basic "+credential})
        with urllib.request.urlopen(request,timeout=3) as response:
            if response.status==200:
                print("Dashboard HTTP check passed"); break
    except Exception:
        time.sleep(2)
else: sys.exit("Dashboard did not become ready; inspect docker compose logs --tail=50 observatory")
'
  printf '\nUpdated successfully at %s.\n' "$(git rev-parse --short HEAD)"
  echo 'Dashboard: VPS loopback port 8080; use your HTTPS proxy or SSH tunnel.'
  echo 'Check Collection health for RPC errors and live observations. HTTP readiness does not prove provider access.'
}

main "$@"
