#!/bin/sh
# This script runs during docker build to fetch and save predictions into the image

set -e

URL="http://10.237.129.136:30080"
WORKDIR="/app/data"

mkdir -p $WORKDIR
cd $WORKDIR

echo "🔍 Fetching latest prediction file during build..."

# Use sed instead of grep -oP for Alpine compatibility
LATEST=$(curl -s $URL/ | sed -n 's/.*href="\([^"]*\.json\)".*/\1/p' | sort -r | head -n 1)

if [ -z "$LATEST" ]; then
  echo "No prediction file found - will use fallback predictions"
  exit 0
fi

echo "Downloading $LATEST"
curl -s -O "$URL/$LATEST"

echo "Extracting prediction vector"
jq '.response.predictions[0]' "$LATEST" > predictions_vector.json

echo "Prediction vector saved to image"
echo "Total values: $(jq '. | length' predictions_vector.json)"

