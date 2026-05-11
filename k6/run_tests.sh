#!/bin/bash
# Run k6 load tests

BASE_URL="${BASE_URL:-http://localhost:8000}"
API_KEY="${API_KEY:-}"
REPORT_DIR="${REPORT_DIR:-./k6/results}"

mkdir -p "$REPORT_DIR"

echo "Running k6 load tests against $BASE_URL"
echo "Report directory: $REPORT_DIR"

# Run k6 with environment variables
k6 run \
  --env BASE_URL="$BASE_URL" \
  --env API_KEY="$API_KEY" \
  --out json="$REPORT_DIR/k6-results.json" \
  k6/load_test.js

echo "Results saved to $REPORT_DIR/"