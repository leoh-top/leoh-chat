#!/usr/bin/env bash
# 从 FluffyChat 官方源码构建 leoh-chat 安卓 APK（无 Google/FCM，自签名）。macOS / 网页版由 GitHub Actions 构建。
# 用法: ./build-android.sh            产物: build/leoh-chat.apk
# 依赖: Android SDK (~/Library/Android/sdk)、JDK 17、rustup、rsvg-convert
# 签名: LEOH_SIGNING_DIR（默认 ~/.config/leoh/signing）下的 leoh-chat.jks + key.properties，不进仓库
set -euo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
ROOT=$HERE
# shellcheck source=versions.env
. "$HERE/versions.env"
SIGNING="${LEOH_SIGNING_DIR:-$HOME/.config/leoh/signing}"
# Gradle 不支持路径里有中文等非 ASCII 字符，构建目录放到 ASCII 路径，
# 再在项目里留一个 build 软链接方便找产物
B="${LEOH_CHAT_BUILD:-$HOME/.cache/leoh-chat-build}"
mkdir -p "$B"
[ -e "$ROOT/build" ] || ln -s "$B" "$ROOT/build"
SRC="$B/fluffychat"
FLUTTER="$B/flutter-sdk/bin/flutter"

export ANDROID_HOME="${ANDROID_HOME:-$HOME/Library/Android/sdk}"
export JAVA_HOME="${JAVA_HOME_17:-$(/usr/libexec/java_home -v 17)}"
export PATH="$HOME/.cargo/bin:$PATH"
# pub.dev 下载在这边经常卡住，用 Flutter 官方中国镜像
export PUB_HOSTED_URL="${PUB_HOSTED_URL:-https://pub.flutter-io.cn}"
export FLUTTER_STORAGE_BASE_URL="${FLUTTER_STORAGE_BASE_URL:-https://storage.flutter-io.cn}"
# Rust 工具链和 crates 也走 USTC 镜像（vodozemac 加密库要现编）
export RUSTUP_DIST_SERVER="${RUSTUP_DIST_SERVER:-https://mirrors.ustc.edu.cn/rust-static}"
rustup target add aarch64-linux-android >/dev/null
# cargo 的源替换只认配置文件，用独立 CARGO_HOME，不改全局 ~/.cargo
export CARGO_HOME="$B/cargo-home"
mkdir -p "$CARGO_HOME"
cat > "$CARGO_HOME/config.toml" <<'EOF'
[source.crates-io]
replace-with = "ustc"
[source.ustc]
registry = "sparse+https://mirrors.ustc.edu.cn/crates.io-index/"
EOF
# Maven Central 连不上：独立 GRADLE_USER_HOME + init 脚本换阿里云镜像（复用已下载的 Gradle 发行版）
export GRADLE_USER_HOME="$B/gradle-home"
mkdir -p "$GRADLE_USER_HOME/init.d"
cp "$HERE/maven-mirror.init.gradle" "$GRADLE_USER_HOME/init.d/"
[ -e "$GRADLE_USER_HOME/wrapper" ] || ln -s "$HOME/.gradle/wrapper" "$GRADLE_USER_HOME/wrapper"

[ -x "$FLUTTER" ] || git clone -q --depth 1 --branch "$FLUTTER_TAG" https://github.com/flutter/flutter.git "$B/flutter-sdk"

# 每次都从干净源码开始，保证改动可复现
rm -rf "$SRC"
git clone -q --depth 1 --branch "$FLUFFY_TAG" https://github.com/krille-chan/fluffychat.git "$SRC"
python3 "$HERE/rebrand.py" "$SRC"
install -m 600 "$SIGNING/leoh-chat.jks" "$B/leoh-chat.jks"
sed "s|^storeFile=.*|storeFile=$B/leoh-chat.jks|" "$SIGNING/key.properties" > "$SRC/android/key.properties"

cd "$SRC"
"$FLUTTER" config --android-sdk "$ANDROID_HOME" >/dev/null
"$FLUTTER" pub get
# 只打 arm64（现在的安卓手机都是 64 位），体积小一半
"$FLUTTER" build apk --release --target-platform android-arm64 --build-name "${FLUFFY_TAG#v}" --build-number "$(date +%y%m%d%H)"  # 递增，保证能覆盖升级

cp build/app/outputs/flutter-apk/app-release.apk "$B/leoh-chat.apk"
shasum -a 256 "$B/leoh-chat.apk"
