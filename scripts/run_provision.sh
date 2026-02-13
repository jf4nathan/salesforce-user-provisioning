#!/usr/bin/env bash
set -euo pipefail

# Guardrail wrapper for provisioning:
# - Always runs the canonical entrypoint: scripts/core/provision_user.py
# - Requires CSV input to come from temp/
# - Requires output JSON to be written to temp/

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

SCRIPT_PATH="scripts/core/provision_user.py"
DEFAULT_OUTPUT="temp/provisioning_results.json"

if [[ ! -f "$SCRIPT_PATH" ]]; then
  echo "ERROR: Cannot find $SCRIPT_PATH from project root."
  exit 1
fi

CSV_PATH=""
OUTPUT_PATH=""

ARGS=()
while [[ $# -gt 0 ]]; do
  case "$1" in
    -h|--help)
      exec python3 "$SCRIPT_PATH" --help
      ;;
    --csv)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --csv requires a value."
        exit 1
      fi
      CSV_PATH="$2"
      ARGS+=("$1" "$2")
      shift 2
      ;;
    --output)
      if [[ $# -lt 2 ]]; then
        echo "ERROR: --output requires a value."
        exit 1
      fi
      OUTPUT_PATH="$2"
      ARGS+=("$1" "$2")
      shift 2
      ;;
    *)
      ARGS+=("$1")
      shift
      ;;
  esac
done

if [[ -z "$CSV_PATH" ]]; then
  echo "ERROR: --csv is required (must point to temp/*.csv)."
  exit 1
fi

if [[ -z "$OUTPUT_PATH" ]]; then
  OUTPUT_PATH="$DEFAULT_OUTPUT"
  ARGS+=("--output" "$OUTPUT_PATH")
fi

# Normalize and enforce temp/ guardrails (allow relative or absolute inputs)
CSV_ABS="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$CSV_PATH")"
OUT_ABS="$(python3 -c 'import os,sys; print(os.path.abspath(sys.argv[1]))' "$OUTPUT_PATH")"
TEMP_ABS="$(python3 -c 'import os; print(os.path.abspath("temp"))')"

case "$CSV_ABS" in
  "$TEMP_ABS"/*) ;;
  *)
    echo "ERROR: --csv must be under temp/. Got: $CSV_PATH"
    exit 1
    ;;
esac

case "$OUT_ABS" in
  "$TEMP_ABS"/*) ;;
  *)
    echo "ERROR: --output must be under temp/. Got: $OUTPUT_PATH"
    exit 1
    ;;
esac

if [[ ! -f "$CSV_ABS" ]]; then
  echo "ERROR: CSV file not found: $CSV_PATH"
  exit 1
fi

mkdir -p "$(dirname "$OUT_ABS")"

echo "Running provisioning with guardrails:"
echo "  Script: $SCRIPT_PATH"
echo "  CSV:    $CSV_PATH"
echo "  Output: $OUTPUT_PATH"
echo

exec python3 "$SCRIPT_PATH" "${ARGS[@]}"
