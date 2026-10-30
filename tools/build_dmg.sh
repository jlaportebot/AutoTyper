#!/usr/bin/env bash
# Build AutoTyper-<version>-macos-<arch>.dmg on a macOS machine.
#
# Usage: tools/build_dmg.sh [output-dir]   build, ad-hoc sign and package (default: dist)
#        tools/build_dmg.sh --check        only check this script's syntax (works on Linux)
#
# Set PYTHON to choose the interpreter that runs PyInstaller.
set -euo pipefail

readonly APP_NAME="AutoTyper"
readonly ADHOC_IDENTITY="-"

die() {
    echo "error: $*" >&2
    exit 1
}

project_version() {
    local version
    version="$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml | head -n 1)"
    [ -n "$version" ] || die "no version found in pyproject.toml"
    echo "$version"
}

machine_label() {
    case "$(uname -m)" in
        arm64) echo "arm64" ;;
        x86_64) echo "x64" ;;
        *) die "unsupported machine '$(uname -m)'" ;;
    esac
}

build_app() {
    local out_dir="$1"
    echo "==> building $APP_NAME.app"
    "${PYTHON:-python3}" -m PyInstaller --clean --noconfirm \
        --distpath "$out_dir" --workpath build/pyinstaller AutoTyper.spec
    [ -d "$out_dir/$APP_NAME.app" ] || die "$out_dir/$APP_NAME.app was not produced"
}

sign_app() {
    local app="$1"
    echo "==> ad-hoc signing $app"
    codesign --force --deep --sign "$ADHOC_IDENTITY" "$app"
    codesign --verify --deep --strict --verbose=2 "$app"
}

stage_dmg() {
    local app="$1" staging="$2"
    echo "==> staging $staging"
    rm -rf "$staging"
    mkdir -p "$staging"
    ditto "$app" "$staging/$APP_NAME.app"
    ln -s /Applications "$staging/Applications"
}

create_dmg() {
    local staging="$1" dmg="$2"
    echo "==> creating $dmg"
    hdiutil create -volname "$APP_NAME" -srcfolder "$staging" -ov -format UDZO "$dmg"
}

report() {
    local dmg="$1"
    echo "==> built $dmg"
    echo "size: $(du -h "$dmg" | cut -f 1) ($(stat -f %z "$dmg") bytes)"
    hdiutil imageinfo "$dmg"
}

main() {
    if [ "${1:-}" = "--check" ]; then
        bash -n "${BASH_SOURCE[0]}"
        echo "syntax ok: ${BASH_SOURCE[0]}"
        return
    fi
    [ "$(uname -s)" = "Darwin" ] || die "this script must run on macOS (use --check elsewhere)"
    local root out_dir="${1:-dist}" dmg
    root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    mkdir -p "$out_dir"
    out_dir="$(cd "$out_dir" && pwd)"
    cd "$root"
    dmg="$out_dir/$APP_NAME-$(project_version)-macos-$(machine_label).dmg"

    build_app "$out_dir"
    sign_app "$out_dir/$APP_NAME.app"
    stage_dmg "$out_dir/$APP_NAME.app" build/dmg-staging
    create_dmg build/dmg-staging "$dmg"
    report "$dmg"
}

main "$@"
