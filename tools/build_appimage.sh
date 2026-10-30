#!/usr/bin/env bash
# Build AutoTyper-<version>-linux-<arch>.AppImage from the PyInstaller binary.
#
# Usage: tools/build_appimage.sh <x86_64|aarch64> [output-dir]
#
# Expects the one-file binary at <output-dir>/AutoTyper (built by
# `pyinstaller AutoTyper.spec`) and builds it first when it is missing.
# PyInstaller cannot cross-compile, so run this on a machine of the target
# architecture. Set PYTHON to choose the interpreter used for that build.
set -euo pipefail

readonly APP_NAME="AutoTyper"
readonly RUNTIME_BASE="https://github.com/AppImage/type2-runtime/releases/latest/download"
readonly TOOL_BASE="https://github.com/AppImage/appimagetool/releases/latest/download"
readonly CURL_RETRIES=3

die() {
    echo "error: $*" >&2
    exit 1
}

usage() {
    echo "usage: $0 <x86_64|aarch64> [output-dir]" >&2
    exit 2
}

project_version() {
    local version
    version="$(sed -n 's/^version = "\(.*\)"$/\1/p' pyproject.toml | head -n 1)"
    [ -n "$version" ] || die "no version found in pyproject.toml"
    echo "$version"
}

elf_description_for() {
    case "$1" in
        x86_64) echo "x86-64" ;;
        aarch64) echo "ARM aarch64" ;;
        *) die "unsupported architecture '$1' (use x86_64 or aarch64)" ;;
    esac
}

ensure_binary() {
    local binary="$1" out_dir="$2" arch="$3" wanted
    if [ ! -x "$binary" ]; then
        echo "==> building the PyInstaller binary"
        "${PYTHON:-python3}" -m PyInstaller --clean --noconfirm \
            --distpath "$out_dir" --workpath build/pyinstaller AutoTyper.spec
    fi
    [ -x "$binary" ] || die "$binary was not produced"
    wanted="$(elf_description_for "$arch")"
    file -b "$binary" | grep -q "$wanted" \
        || die "$binary is not a $arch binary: $(file -b "$binary")"
}

stage_appdir() {
    local appdir="$1" binary="$2"
    echo "==> staging $appdir"
    rm -rf "$appdir"
    mkdir -p "$appdir/usr/bin"
    install -m 755 "$binary" "$appdir/usr/bin/$APP_NAME"
    install -m 755 packaging/linux/AppRun "$appdir/AppRun"
    install -m 644 packaging/linux/AutoTyper.desktop "$appdir/$APP_NAME.desktop"
    install -m 644 assets/autotyper.png "$appdir/$APP_NAME.png"
    ln -s "$APP_NAME.png" "$appdir/.DirIcon"
}

validate_desktop_entry() {
    local entry="$1/$APP_NAME.desktop"
    if command -v desktop-file-validate >/dev/null 2>&1; then
        desktop-file-validate "$entry"
        echo "==> desktop entry is valid"
    else
        echo "warning: desktop-file-validate not found, skipping the check" >&2
    fi
}

fetch() {
    local url="$1" target="$2"
    if [ -s "$target" ]; then
        echo "==> cached $(basename "$target")"
        return
    fi
    echo "==> downloading $url"
    curl --fail --location --silent --show-error --retry "$CURL_RETRIES" \
        --output "$target.part" "$url"
    mv "$target.part" "$target"
}

build_image() {
    local arch="$1" appdir="$2" image="$3" cache="$4"
    local runtime="$cache/runtime-$arch" tool="$cache/appimagetool-$arch.AppImage"
    mkdir -p "$cache"
    fetch "$RUNTIME_BASE/runtime-$arch" "$runtime"
    fetch "$TOOL_BASE/appimagetool-$arch.AppImage" "$tool"
    chmod +x "$runtime" "$tool"
    echo "==> running appimagetool"
    ARCH="$arch" APPIMAGE_EXTRACT_AND_RUN=1 "$tool" --appimage-extract-and-run \
        --runtime-file "$runtime" --no-appstream "$appdir" "$image"
}

report() {
    local image="$1"
    echo "==> built $image"
    echo "size: $(du -h "$image" | cut -f 1) ($(wc -c < "$image") bytes)"
    file "$image"
}

main() {
    [ "$#" -ge 1 ] && [ "$#" -le 2 ] || usage
    local arch="$1" out_dir="${2:-dist}" root version image
    elf_description_for "$arch" >/dev/null
    root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
    mkdir -p "$out_dir"
    out_dir="$(cd "$out_dir" && pwd)"
    cd "$root"
    version="$(project_version)"
    image="$out_dir/$APP_NAME-$version-linux-$arch.AppImage"

    ensure_binary "$out_dir/$APP_NAME" "$out_dir" "$arch"
    stage_appdir build/AppDir "$out_dir/$APP_NAME"
    validate_desktop_entry build/AppDir
    build_image "$arch" build/AppDir "$image" build/appimage-cache
    report "$image"
}

main "$@"
