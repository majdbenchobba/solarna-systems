#!/bin/sh
set -eu

if [ "$#" -gt 1 ]; then
  echo "Usage: ./build-ios-release.sh [https://solarna.example.com]" >&2
  exit 2
fi

api_url=${1:-}
script_directory=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
repository_mode=0
if [ -f "$script_directory/package.json" ] &&
   [ -d "$script_directory/ios/App" ]; then
  repository_mode=1
  project_directory=$(dirname "$script_directory")
  xcode_project="ios/App/App.xcodeproj"
  output_directory="$project_directory/outputs/deliverables/ios"
elif [ -d "$script_directory/App" ]; then
  project_directory=$script_directory
  xcode_project="App/App.xcodeproj"
  output_directory="$script_directory/outputs"
else
  echo "The Solarna iOS project was not found." >&2
  exit 1
fi
team_id=${SOLARNA_IOS_TEAM_ID:-}
bundle_id=${SOLARNA_IOS_BUNDLE_ID:-tn.solarna.optimizer}
version=${SOLARNA_IOS_VERSION:-0.5.0}
build_number=${SOLARNA_IOS_BUILD_NUMBER:-10}
export_options=${SOLARNA_IOS_EXPORT_OPTIONS_PLIST:-}

if [ "$(uname -s)" != "Darwin" ]; then
  echo "iOS release builds require macOS." >&2
  exit 1
fi
if [ -z "$team_id" ]; then
  echo "Set SOLARNA_IOS_TEAM_ID to the Apple Developer team ID." >&2
  exit 1
fi
case "$team_id" in
  *[!A-Za-z0-9]*|"") echo "SOLARNA_IOS_TEAM_ID is invalid." >&2; exit 1 ;;
esac
case "$bundle_id" in
  *[!A-Za-z0-9.-]*|.*|*.) echo "SOLARNA_IOS_BUNDLE_ID is invalid." >&2; exit 1 ;;
esac
case "$build_number" in
  *[!0-9]*|"") echo "SOLARNA_IOS_BUILD_NUMBER must be a positive integer." >&2; exit 1 ;;
esac

if [ -n "$api_url" ]; then
  if [ "$repository_mode" -ne 1 ]; then
    echo "A fixed server URL can only be embedded from the full repository." >&2
    exit 1
  fi
  node -e '
const value = process.argv[1];
const url = new URL(value);
if (url.protocol !== "https:" || url.username || url.password ||
    url.pathname !== "/" || url.search || url.hash) process.exit(1);
' "$api_url" || {
    echo "The server URL must be an HTTPS origin." >&2
    exit 1
  }
fi

for command in xcodebuild; do
  command -v "$command" >/dev/null 2>&1 || {
    echo "$command is required." >&2
    exit 1
  }
done
if [ "$repository_mode" -eq 1 ]; then
  for command in node npm npx; do
    command -v "$command" >/dev/null 2>&1 || {
      echo "$command is required." >&2
      exit 1
    }
  done
fi
if [ -n "$export_options" ] && [ ! -f "$export_options" ]; then
  echo "SOLARNA_IOS_EXPORT_OPTIONS_PLIST does not exist." >&2
  exit 1
fi

timestamp=$(date -u +%Y%m%dT%H%M%SZ)
archive_path="$output_directory/Solarna-$timestamp.xcarchive"
export_path="$output_directory/Solarna-$timestamp"
mkdir -p "$output_directory"

restore_web_bundle() {
  if [ "$repository_mode" -eq 1 ]; then
    cd "$script_directory"
    npm run prepare:web >/dev/null 2>&1 || true
    npx cap sync ios >/dev/null 2>&1 || true
  fi
}
trap restore_web_bundle EXIT HUP INT TERM

cd "$script_directory"
if [ "$repository_mode" -eq 1 ]; then
  if [ -n "$api_url" ]; then
    npm run prepare:web -- --api-url "$api_url"
  else
    npm run prepare:web
  fi
  npx cap sync ios
fi

xcodebuild \
  -project "$xcode_project" \
  -scheme App \
  -configuration Release \
  -destination "generic/platform=iOS" \
  -archivePath "$archive_path" \
  DEVELOPMENT_TEAM="$team_id" \
  PRODUCT_BUNDLE_IDENTIFIER="$bundle_id" \
  MARKETING_VERSION="$version" \
  CURRENT_PROJECT_VERSION="$build_number" \
  CODE_SIGN_STYLE=Automatic \
  -allowProvisioningUpdates \
  clean archive

echo "Signed iOS archive: $archive_path"

if [ -n "$export_options" ]; then
  xcodebuild \
    -exportArchive \
    -archivePath "$archive_path" \
    -exportPath "$export_path" \
    -exportOptionsPlist "$export_options" \
    -allowProvisioningUpdates
  ipa=$(find "$export_path" -maxdepth 1 -type f -name '*.ipa' -print -quit)
  if [ -z "$ipa" ]; then
    echo "Xcode completed without producing an IPA." >&2
    exit 1
  fi
  echo "Signed iOS IPA: $ipa"
fi
