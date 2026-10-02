#!/bin/zsh
# Smoke-tests the BUILT .app (not the source) against throwaway data.
#
# Launches dist/FlightGear NavData Manager.app with `open` (so it runs
# frontmost, like a user-opened app) twice -- a full pass and a
# "FlightGear not installed" pass -- with its database, scenery output and
# settings redirected to a temporary sandbox. Prints each check, copies
# screenshots + results to OUT_DIR (default ui_screenshots/packaged_smoke),
# deletes the sandbox, and exits non-zero if any check failed.
#
# Usage: tools/smoke_packaged_app.sh [OUT_DIR]
set -euo pipefail
cd "$(dirname "$0")/.."
APP="${FGNAV_APP:-$PWD/dist/FlightGear NavData Manager.app}"   # FGNAV_APP: test another build
OUT="${1:-ui_screenshots/packaged_smoke}"
REAL_DB="$HOME/Library/Application Support/FlightGearNavDataManager/navdata.sqlite"
[[ -d "$APP" ]] || { echo "build the app first: pyinstaller \"packaging/FlightGear NavData Manager.spec\""; exit 1; }

SB=$(mktemp -d "${TMPDIR:-/tmp}/fgnav_pkg.XXXX")
trap 'rm -rf "$SB"' EXIT
for run in full nofg; do
  mkdir -p "$SB/$run/data" "$SB/$run/settings" "$SB/$run/out"
  # Starts from an empty database, so results don't depend on your data.
  # FGNAV_SMOKE_REAL_COPY=1 starts from a COPY of it instead (only read).
  if [[ "${FGNAV_SMOKE_REAL_COPY:-0}" == 1 && -f "$REAL_DB" ]]; then cp "$REAL_DB" "$SB/$run/data/"; fi
done
mkdir -p "$SB/fixtures"
cp tests/infrastructure/fixtures/sample_faa_fix.csv "$SB/fixtures/"
printf 'ident,name,latitude,longitude,frequency,range_nm\nQQA,Test,10.0,20.0,375,50\n' > "$SB/fixtures/untyped_navaids.csv"

open -n -W --env FGNAV_DATA_DIR="$SB/full/data" --env FGNAV_SETTINGS_DIR="$SB/full/settings" \
  --env FGNAV_SMOKE_FIXTURES="$SB/fixtures" --env FGNAV_SMOKE_OUT="$SB/full/out" "$APP"
open -n -W --env FGNAV_DATA_DIR="$SB/nofg/data" --env FGNAV_SETTINGS_DIR="$SB/nofg/settings" \
  --env FGNAV_ASSUME_NO_FLIGHTGEAR=1 --env FGNAV_SMOKE_OUT="$SB/nofg/out" "$APP"

rm -rf "$OUT"; mkdir -p "$OUT"
cp "$SB"/full/out/*.png "$OUT/"
cp "$SB/nofg/out/01_fg_not_found_dashboard.png" "$OUT/14_fg_not_found_dashboard.png"
cp "$SB/full/out/results.json" "$OUT/smoke_results_full.json"
cp "$SB/nofg/out/results.json" "$OUT/smoke_results_no_flightgear.json"

python3 - "$OUT" <<'EOF'
import json, sys
failed = 0
for name in ("smoke_results_full.json", "smoke_results_no_flightgear.json"):
    r = json.load(open(f"{sys.argv[1]}/{name}"))
    print(f"== {name}: {r['passed']} passed, {r['failed']} failed (frozen={r['frozen']})")
    for x in r["results"]:
        print(("  OK   " if x["ok"] else "  FAIL ") + x["check"] + (f"  [{x['detail'][:100]}]" if not x["ok"] else ""))
    failed += r["failed"] + (0 if r["frozen"] else 1)
sys.exit(1 if failed else 0)
EOF
