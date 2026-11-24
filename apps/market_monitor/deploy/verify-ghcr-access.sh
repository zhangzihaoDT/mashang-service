#!/usr/bin/env bash
# Check Package metadata plus Registry V2 access without persisting credentials.
set -euo pipefail
: "${IMAGE:?}"
: "${PACKAGE_API:?}"
tag="${1:?Pass a known existing tag}"

package="${PACKAGE_API#https://api.github.com/}"
visibility="$(gh api "$package" --jq '.visibility // "unknown"')"
if [[ "$visibility" != private ]]; then
  echo "::error::GHCR package must be Private. API reports $visibility."
  exit 1
fi
anonymous_response="$(curl -qsS --retry 2 -w $'\n%{http_code}' --get \
  --data-urlencode 'service=ghcr.io' \
  --data-urlencode "scope=repository:${IMAGE#ghcr.io/}:pull" https://ghcr.io/token)"
status="${anonymous_response##*$'\n'}"
if [[ "$status" == 200 ]]; then
  anonymous_token="$(jq -er '.token // .access_token' <<< "${anonymous_response%$'\n'*}")"
  status="$(printf 'Authorization: Bearer %s\n' "$anonymous_token" | curl -qsS --retry 2 \
    -H @- -H 'Accept: application/vnd.oci.image.manifest.v1+json, application/vnd.docker.distribution.manifest.v2+json' \
    -o /dev/null -w '%{http_code}' "https://ghcr.io/v2/${IMAGE#ghcr.io/}/manifests/$tag")"
fi
case "$status" in
  401|403) printf 'Package is Private; anonymous pull of %s denied (HTTP %s).\n' "$tag" "$status" ;;
  *) echo "::error::Expected anonymous pull to be denied; received HTTP $status."; exit 1 ;;
esac
