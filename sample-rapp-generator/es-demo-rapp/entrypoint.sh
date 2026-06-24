#!/bin/sh
set -e

# Simple entrypoint - predictions already baked into image
echo "Starting Energy Saving rApp..."

# Check if predictions exist
if [ -f /app/data/predictions_vector.json ]; then
  PRED_COUNT=$(jq '. | length' /app/data/predictions_vector.json)
  echo "Using predictions from image: $PRED_COUNT values"
  echo " First 10 values:"
  jq '.[:10]' /app/data/predictions_vector.json
else
  echo " No predictions file found, will use fallback hardcoded predictions"
fi

cd /app
exec "$@"
