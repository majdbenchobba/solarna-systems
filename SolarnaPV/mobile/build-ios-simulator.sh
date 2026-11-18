#!/usr/bin/env bash
set -euo pipefail

mobile_directory="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
project_directory="$(cd "${mobile_directory}/.." && pwd)"
output_directory="${project_directory}/outputs/deliverables"
output_zip="${output_directory}/Solarna-iOS-simulator.zip"
build_root="$(mktemp -d "${TMPDIR:-/tmp}/solarna-ios-simulator.XXXXXX")"

cleanup() {
  case "${build_root}" in
    "${TMPDIR:-/tmp}"/solarna-ios-simulator.*)
      rm -rf -- "${build_root}"
      ;;
  esac
}
trap cleanup EXIT

command -v xcodebuild >/dev/null
command -v ditto >/dev/null

cd "${mobile_directory}"
npm run prepare:web
npx cap sync ios

xcodebuild \
  -project ios/App/App.xcodeproj \
  -target App \
  -configuration Debug \
  -sdk iphonesimulator \
  SYMROOT="${build_root}/Build/Products" \
  OBJROOT="${build_root}/Build/Intermediates.noindex" \
  CODE_SIGNING_ALLOWED=NO \
  build

app_path="${build_root}/Build/Products/Debug-iphonesimulator/App.app"
if [[ ! -d "${app_path}" ]]; then
  echo "The iOS simulator application was not produced." >&2
  exit 1
fi

bundle_id="$(/usr/libexec/PlistBuddy -c "Print :CFBundleIdentifier" \
  "${app_path}/Info.plist")"
if [[ "${bundle_id}" != "tn.solarna.optimizer" ]]; then
  echo "Unexpected iOS bundle identifier: ${bundle_id}" >&2
  exit 1
fi

mkdir -p "${output_directory}"
rm -f -- "${output_zip}"
ditto -c -k --sequesterRsrc --keepParent "${app_path}" "${output_zip}"

echo "iOS simulator application: ${output_zip}"
