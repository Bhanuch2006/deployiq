#!/bin/bash
# Upload hashed assets first, then the entry document. Never delete old assets
# during a release: an already-open page might still refer to them.
set -euo pipefail
: "${DASHBOARD_BUCKET_NAME:?Set the DashboardBucketName repository variable}"
: "${DASHBOARD_DISTRIBUTION_ID:?Set the DashboardDistributionId repository variable}"
[[ "$DASHBOARD_BUCKET_NAME" =~ ^[a-z0-9][a-z0-9.-]+$ ]] || { echo 'Invalid bucket name'; exit 2; }
[[ "$DASHBOARD_DISTRIBUTION_ID" =~ ^[A-Z0-9]+$ ]] || { echo 'Invalid distribution ID'; exit 2; }
[[ -s frontend/dist/index.html ]] || { echo 'Build the frontend before publishing'; exit 2; }
aws s3 sync frontend/dist/ "s3://$DASHBOARD_BUCKET_NAME/" \
  --exclude index.html --cache-control 'public,max-age=31536000,immutable' --only-show-errors
aws s3 cp frontend/dist/index.html "s3://$DASHBOARD_BUCKET_NAME/index.html" \
  --content-type 'text/html; charset=utf-8' --cache-control 'no-cache,max-age=0,must-revalidate' --only-show-errors
aws cloudfront create-invalidation --distribution-id "$DASHBOARD_DISTRIBUTION_ID" \
  --paths / /index.html --query Invalidation.Id --output text
