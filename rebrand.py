#!/usr/bin/env python3
"""把干净的 FluffyChat 源码改成 leoh-chat（安卓 / macOS / 网页）：改名、换包名、换图标、预置服务器。

用法: rebrand.py <fluffychat 源码目录>
只做文本替换和文件改动，可在新 checkout 上重复执行（每处替换都会校验命中）。
"""
import pathlib
import re
import shutil
import subprocess
import sys

APP_NAME_ZH = "leoh-chat"
APP_NAME_EN = "leoh-chat"
PKG = "top.leoh.chat"           # Android 包名 / applicationId
SCHEME = "top.leoh.chat"        # 深链 scheme
SSO_SCHEME = "top.leoh.chat.auth"  # SSO 回跳 scheme，需加进 Synapse sso.client_whitelist
HOMESERVER = "matrix.leoh.top"
SITE = "https://chat.leoh.top"
PUSH_GW = "https://ntfy.leoh.top/_matrix/push/v1/notify"

src = pathlib.Path(sys.argv[1]).resolve()
icons = pathlib.Path(__file__).resolve().parent / "icon"


def sub(rel, old, new):
    """替换并校验命中，防止上游改动后静默失效；已替换过则跳过。"""
    p = src / rel
    t = p.read_text(encoding="utf-8")
    if old not in t:
        if new in t:
            return
        sys.exit(f"pattern not found in {rel}: {old!r}")
    p.write_text(t.replace(old, new), encoding="utf-8")


# --- Android 包名、名称、scheme ---
sub("android/app/build.gradle.kts", 'namespace = "chat.fluffy.fluffychat"', f'namespace = "{PKG}"')
sub("android/app/build.gradle.kts", 'applicationId = "chat.fluffy.fluffychat"', f'applicationId = "{PKG}"')
# AGP 8.11 认不出新版 SDK 的 platforms/android-37.0 目录结构，用 36 编译
sub("android/app/build.gradle.kts", "compileSdk = 37", "compileSdk = 36")
sub("android/app/src/main/AndroidManifest.xml", 'android:label="FluffyChat"', f'android:label="{APP_NAME_ZH}"')
sub("android/app/src/main/AndroidManifest.xml", 'android:scheme="im.fluffychat.auth"', f'android:scheme="{SSO_SCHEME}"')
sub("android/app/src/main/AndroidManifest.xml", 'android:scheme="im.fluffychat"', f'android:scheme="{SCHEME}"')

# 不带 FCM：删掉指向空类的 Firebase 推送服务声明（只走 UnifiedPush/ntfy）
sub("android/app/src/main/AndroidManifest.xml",
    '''        <service android:name=".FcmPushService"
          android:exported="false">
          <intent-filter>
            <action android:name="com.google.firebase.MESSAGING_EVENT"/>
          </intent-filter>
        </service>
''', "")

# --- 内置推送：leoh-chat自己当 UnifiedPush 分发程序，不用另装 ntfy ---
manifest = "android/app/src/main/AndroidManifest.xml"
sub(manifest, '<uses-permission android:name="android.permission.FOREGROUND_SERVICE_SHORT_SERVICE" />',
    '<uses-permission android:name="android.permission.FOREGROUND_SERVICE_SHORT_SERVICE" />\n'
    '    <uses-permission android:name="android.permission.FOREGROUND_SERVICE_REMOTE_MESSAGING" />\n'
    '    <uses-permission android:name="android.permission.REQUEST_IGNORE_BATTERY_OPTIMIZATIONS" />\n'
    '    <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />')
sub(manifest, "    </application>", """        <!-- 内置 UnifiedPush 分发程序（见 app/android-src） -->
        <receiver android:name=".EmbeddedDistributorReceiver" android:exported="false">
            <intent-filter>
                <action android:name="org.unifiedpush.android.distributor.REGISTER"/>
                <action android:name="org.unifiedpush.android.distributor.UNREGISTER"/>
            </intent-filter>
        </receiver>
        <receiver android:name=".EmbeddedDistributorBootReceiver" android:exported="false">
            <intent-filter>
                <action android:name="android.intent.action.BOOT_COMPLETED"/>
                <action android:name="android.intent.action.MY_PACKAGE_REPLACED"/>
            </intent-filter>
        </receiver>
        <service android:name=".NtfyListenService"
            android:exported="false"
            android:foregroundServiceType="remoteMessaging"/>
    </application>""")

bp = "lib/utils/background_push.dart"
# 有内置分发程序时直接选它并注册，不弹“选择推送方式”对话框
sub(bp, """  Future<void> setupPush(BuildContext context) async {
    if (PlatformInfos.isAndroid &&""", """  Future<void> setupPush(BuildContext context) async {
    if (PlatformInfos.isAndroid &&
        (await UnifiedPush.getDistributors()).contains(AppConfig.embeddedDistributor)) {
      if (await UnifiedPush.getDistributor() != AppConfig.embeddedDistributor) {
        await UnifiedPush.saveDistributor(AppConfig.embeddedDistributor);
      }
      await UnifiedPush.register(instance: 'default', features: UPFunctions().features);
      return;
    }
    if (PlatformInfos.isAndroid &&""")
sub("lib/config/app_config.dart", "  static const String appSsoUrlScheme",
    f"  // 内置 UnifiedPush 分发程序就是 App 自己\n  static const String embeddedDistributor = '{PKG}';\n  static const String appSsoUrlScheme")

# --- 机器人按钮（Telegram inline keyboard 的对应物，见 app/dart-src/bot_keyboard.dart） ---
shutil.copy(pathlib.Path(__file__).resolve().parent / "dart-src/bot_keyboard.dart",
            src / "lib/pages/chat/events/bot_keyboard.dart")
ev = "lib/pages/chat/events/"
sub(ev + "message.dart", "import 'message_content.dart';", "import 'bot_keyboard.dart';\nimport 'message_content.dart';")
sub(ev + "message.dart", """    final hasReactions = event.hasAggregatedEvents(
      timeline,
      RelationshipTypes.reaction,
    );""", """    final hasReactions = hasNonKeyboardReactions(event, displayEvent, timeline);""")
sub(ev + "message.dart", """                                            MessageContent(
                                              displayEvent,
                                              textColor: textColor,
                                              linkColor: linkColor,
                                              onInfoTab: onInfoTab,
                                              borderRadius: borderRadius,
                                              timeline: timeline,
                                              selected: selected,
                                              bigEmojis: bigEmojis,
                                            ),""", """                                            MessageContent(
                                              displayEvent,
                                              textColor: textColor,
                                              linkColor: linkColor,
                                              onInfoTab: onInfoTab,
                                              borderRadius: borderRadius,
                                              timeline: timeline,
                                              selected: selected,
                                              bigEmojis: bigEmojis,
                                            ),
                                            BotKeyboard(
                                              event: event,
                                              displayEvent: displayEvent,
                                              color: linkColor,
                                            ),""")
sub(ev + "message_content.dart", "import 'audio_player.dart';", "import 'audio_player.dart';\nimport 'bot_keyboard.dart';")
sub(ev + "message_content.dart", """            var html = AppSettings.renderHtml.value && event.isRichMessage
                ? event.formattedText
                : event.body.replaceAll('<', '&lt;').replaceAll('>', '&gt;');""", """            var html = AppSettings.renderHtml.value && event.isRichMessage
                ? event.formattedText
                : event.body.replaceAll('<', '&lt;').replaceAll('>', '&gt;');
            if (botKeyboardRows(event) != null) html = stripBotKeyboardHtml(html);""")
sub(ev + "message_reactions.dart", "import 'package:matrix/matrix.dart';", "import 'package:matrix/matrix.dart';\n\nimport 'bot_keyboard.dart';")
sub(ev + "message_reactions.dart", """    for (final e in allReactionEvents) {
      final key = e.content
          .tryGetMap<String, Object?>('m.relates_to')
          ?.tryGet<String>('key');
      if (key != null) {""", """    // 按钮用的表情由 BotKeyboard 画成按钮，这里不再重复显示
    final keyboardKeys = botKeyboardKeys(event.getDisplayEvent(timeline));
    for (final e in allReactionEvents) {
      final key = e.content
          .tryGetMap<String, Object?>('m.relates_to')
          ?.tryGet<String>('key');
      if (key != null && !keyboardKeys.contains(key)) {""")

# --- 机器人命令菜单、可点击命令、机器人通讯录（见 app/dart-src/bot_commands.dart） ---
shutil.copy(pathlib.Path(__file__).resolve().parent / "dart-src/bot_commands.dart",
            src / "lib/pages/chat/bot_commands.dart")
row = "lib/pages/chat/chat_input_row.dart"
sub(row, "import 'package:fluffychat/pages/chat/recording_input_row.dart';",
    "import 'package:fluffychat/pages/chat/bot_commands.dart';\nimport 'package:fluffychat/pages/chat/recording_input_row.dart';")
sub(row, """                  Container(
                    height: height,
                    width: 48,
                    alignment: Alignment.center,
                    child: IconButton(
                      tooltip: L10n.of(context).emojis,""", """                  BotCommandMenuButton(room: controller.room, height: height),
                  Container(
                    height: height,
                    width: 48,
                    alignment: Alignment.center,
                    child: IconButton(
                      tooltip: L10n.of(context).emojis,""")
hm = ev + "html_message.dart"
sub(hm, "import 'package:fluffychat/l10n/l10n.dart';", "import 'package:fluffychat/l10n/l10n.dart';\nimport 'package:fluffychat/pages/chat/bot_commands.dart';")
sub(hm, "              onTap: () => UrlLauncher(context, href, node.text).launchUrl(),",
    "              onTap: () => handleBotCommandLink(context, room, href)\n"
    "                  ? null\n"
    "                  : UrlLauncher(context, href, node.text).launchUrl(),")
npv = "lib/pages/new_private_chat/new_private_chat_view.dart"
sub(npv, "import 'package:fluffychat/pages/new_private_chat/new_private_chat.dart';",
    "import 'package:fluffychat/pages/chat/bot_commands.dart';\nimport 'package:fluffychat/pages/new_private_chat/new_private_chat.dart';")
sub(npv, """                          if (PlatformInfos.isMobile)
                            ListTile(
                              leading: CircleAvatar(
                                backgroundColor:
                                    theme.colorScheme.primaryContainer,""", """                          const LeohBotList(),
                          if (PlatformInfos.isMobile)
                            ListTile(
                              leading: CircleAvatar(
                                backgroundColor:
                                    theme.colorScheme.primaryContainer,""")

# --- 应用内更新（见 app/dart-src/leoh_update.dart、app/android-src/ApkInstaller.kt） ---
shutil.copy(pathlib.Path(__file__).resolve().parent / "dart-src/leoh_update.dart", src / "lib/utils/leoh_update.dart")
sub("pubspec.yaml", "  flutter_vodozemac:", "  crypto: ^3.0.6\n  flutter_vodozemac:")
sub(manifest, '<uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />',
    '<uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />\n'
    '    <uses-permission android:name="android.permission.REQUEST_INSTALL_PACKAGES" />')
sub(manifest, "        <!-- 内置 UnifiedPush 分发程序（见 app/android-src） -->", """        <provider android:name=".UpdateFileProvider"
            android:authorities="${applicationId}.update_provider"
            android:exported="false"
            android:grantUriPermissions="true">
            <meta-data android:name="android.support.FILE_PROVIDER_PATHS" android:resource="@xml/leoh_update_paths"/>
        </provider>
        <!-- 内置 UnifiedPush 分发程序（见 app/android-src） -->""")
(src / "android/app/src/main/res/xml").mkdir(parents=True, exist_ok=True)
(src / "android/app/src/main/res/xml/leoh_update_paths.xml").write_text(
    '<?xml version="1.0" encoding="utf-8"?>\n<paths>\n    <cache-path name="updates" path="updates/"/>\n</paths>\n')
# 已登录的老账号还连着 matrix.leoh.top（走 CF，单次上传 100M 上限），启动时切到 mx.leoh.top（仅 DNS，不限大小）
sub("lib/utils/client_manager.dart",
    "    if (clients.length > 1 && clients.any((c) => !c.isLogged())) {",
    "    for (final client in clients) {\n"
    "      if (client.homeserver?.host == 'matrix.leoh.top') {\n"
    "        client.homeserver = client.homeserver!.replace(host: 'mx.leoh.top');\n"
    "      }\n"
    "    }\n"
    "    if (clients.length > 1 && clients.any((c) => !c.isLogged())) {")

cl = "lib/pages/chat_list/chat_list.dart"
sub(cl, "import 'package:fluffychat/utils/localized_exception_extension.dart';",
    "import 'package:fluffychat/utils/leoh_update.dart';\nimport 'package:fluffychat/utils/localized_exception_extension.dart';")
sub(cl, "        UpdateNotifier.showUpdateAvailableBanner(context);",
    "        UpdateNotifier.showUpdateAvailableBanner(context);\n        LeohUpdate.start(context);")

kt_old = src / "android/app/src/main/kotlin/chat/fluffy/fluffychat"
kt_new = src / "android/app/src/main/kotlin" / pathlib.Path(*PKG.split("."))
if kt_old.exists():
    kt_new.mkdir(parents=True, exist_ok=True)
    for f in kt_old.iterdir():
        t = f.read_text(encoding="utf-8").replace("package chat.fluffy.fluffychat", f"package {PKG}")
        (kt_new / f.name).write_text(t, encoding="utf-8")
    shutil.rmtree(src / "android/app/src/main/kotlin/chat")
for f in (pathlib.Path(__file__).resolve().parent / "android-src").glob("*.kt"):
    shutil.copy(f, kt_new / f.name)
ma = kt_new / "MainActivity.kt"
mt = ma.read_text(encoding="utf-8")
if "ApkInstaller" not in mt:
    old_eng = "            engine = eng\n"
    assert old_eng in mt, "MainActivity.provideEngine changed upstream"
    mt = mt.replace(old_eng, "            engine = eng\n            ApkInstaller.register(eng, context.applicationContext)\n")
    ma.write_text(mt, encoding="utf-8")

# --- Dart 配置 ---
cfg = "lib/config/app_config.dart"
sub(cfg, "Color(0xFF261386)", "Color(0xFF0E9F8A)")
sub(cfg, "'im.fluffychat://chat/'", f"'{SCHEME}://chat/'")
sub(cfg, "pushNotificationsChannelId = 'fluffychat_push'", "pushNotificationsChannelId = 'leoh_chat_push'")
sub(cfg, "pushNotificationsAppId = 'chat.fluffy.fluffychat'", f"pushNotificationsAppId = '{PKG}'")
sub(cfg, "appId = 'im.fluffychat.app'", f"appId = '{PKG}.app'")
sub(cfg, "appOpenUrlScheme = 'im.fluffychat'", f"appOpenUrlScheme = '{SCHEME}'")
sub(cfg, "appSsoUrlScheme = 'im.fluffychat.auth'", f"appSsoUrlScheme = '{SSO_SCHEME}'")
sub(cfg, "allowOtherHomeservers = true", "allowOtherHomeservers = false")
sub(cfg, "enableRegistration = true", "enableRegistration = false")

keys = "lib/config/setting_keys.dart"
sub(keys, "'https://push.fluffychat.im/_matrix/push/v1/notify'", f"'{PUSH_GW}'")
sub(keys, "'chat.fluffy.application_name', 'FluffyChat'", f"'chat.fluffy.application_name', '{APP_NAME_ZH}'")
sub(keys, "'chat.fluffy.default_homeserver', 'matrix.org'", f"'chat.fluffy.default_homeserver', '{HOMESERVER}'")
sub(keys, "'chat.fluffy.preset_homeserver', ''", f"'chat.fluffy.preset_homeserver', '{HOMESERVER}'")
sub(keys, "0xFF5625BA", "0xFF0E9F8A")
sub(keys, "'chat.fluffy.website_url', 'https://fluffychat.im'", f"'chat.fluffy.website_url', '{SITE}'")
sub(keys, "'https://fluffychat.im/assets/favicon.png'", f"'{SITE}/icon.png'")
sub(keys, "'https://fluffychat.im/privacy'", f"'{SITE}/'")
sub(keys, "'chat.fluffy.tos_url', 'https://fluffychat.im/tos'", f"'chat.fluffy.tos_url', '{SITE}/'")
sub("lib/utils/start_push_foreground_service.dart", "notificationTitle: 'FluffyChat'", f"notificationTitle: '{APP_NAME_ZH}'")
sub("lib/utils/fluffy_share.dart", "?client=im.fluffychat", f"?client={SCHEME}")

# --- 界面文字：中文/英文里的产品名 ---
for arb, name in (("lib/l10n/intl_zh.arb", APP_NAME_ZH), ("lib/l10n/intl_en.arb", APP_NAME_EN)):
    p = src / arb
    t = p.read_text(encoding="utf-8")
    t = t.replace("https://fluffychat.im", SITE).replace("fluffychat.im", SITE.removeprefix("https://"))
    # 只替换字符串值里的产品名，不动 key（如 newMessageInFluffyChat）
    t = re.sub(r'(:\s*")((?:[^"\\]|\\.)*)(")',
               lambda m: m.group(1) + m.group(2).replace("FluffyChat", name) + m.group(3), t)
    p.write_text(t, encoding="utf-8")


# --- 图标 ---
def render(svg, out, size):
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), str(icons / svg), "-o", str(out)], check=True)


res = src / "android/app/src/main/res"
for d, scale in (("mdpi", 1), ("hdpi", 1.5), ("xhdpi", 2), ("xxhdpi", 3), ("xxxhdpi", 4)):
    render("background.svg", res / f"drawable-{d}/ic_launcher_background.png", int(108 * scale))
    render("foreground.svg", res / f"drawable-{d}/ic_launcher_foreground.png", int(108 * scale))
    render("monochrome.svg", res / f"drawable-{d}/ic_launcher_monochrome.png", int(108 * scale))
    render("monochrome.svg", res / f"drawable-{d}/notifications_icon.png", int(24 * scale))
    render("full.svg", res / f"drawable-{d}/splash.png", int(177 * scale))
    render("full.svg", res / f"mipmap-{d}/ic_launcher.png", int(48 * scale))
# 原版在 drawable/ 下还有矢量前景，会和新 PNG 冲突
for f in ("ic_launcher_foreground.xml", "ic_launcher_monochrome.xml"):
    (res / "drawable" / f).unlink(missing_ok=True)

logo = src / "assets/logo"
for rel, svg, size in (("mini/logo_mini.png", "full.svg", 500), ("mini/logo_mono_mini.png", "monochrome.svg", 500),
                       ("img/logo.png", "full.svg", 2000), ("img/logo_foreground.png", "foreground.svg", 2000),
                       ("img/logo_background.png", "background.svg", 2000), ("img/logo_mono.png", "monochrome.svg", 2000)):
    render(svg, logo / rel, size)


def compose(name, parts, scale=1.0):
    """把几个 432x432 的 SVG 叠在一起并居中缩放，生成临时 SVG（放在 icons 目录外的构建目录里）。"""
    inner = "".join(re.search(r"<svg[^>]*>(.*)</svg>", (icons / p).read_text(encoding="utf-8"), re.S).group(1)
                    for p in parts)
    out = src / ".leoh-icons" / name
    out.parent.mkdir(exist_ok=True)
    out.write_text(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 432 432">'
                   f'<g transform="translate(216 216) scale({scale}) translate(-216 -216)">{inner}</g></svg>',
                   encoding="utf-8")
    return out


def render_path(svg_path, out, size):
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size), str(svg_path), "-o", str(out)], check=True)


# --- macOS：改名、包名、免签名（ad-hoc），图标 ---
xc = "macos/Runner/Configs/AppInfo.xcconfig"
sub(xc, "PRODUCT_NAME = FluffyChat", f"PRODUCT_NAME = {APP_NAME_EN}")
sub(xc, "PRODUCT_BUNDLE_IDENTIFIER = im.fluffychat.app", f"PRODUCT_BUNDLE_IDENTIFIER = {PKG}")
sub(xc, "Copyright © 2023 FluffyChat authors.", "Copyright © FluffyChat and leoh-chat authors.")
pbx = "macos/Runner.xcodeproj/project.pbxproj"
sub(pbx, "PRODUCT_BUNDLE_IDENTIFIER = im.fluffychat.app;", f"PRODUCT_BUNDLE_IDENTIFIER = {PKG};")
sub(pbx, "PRODUCT_NAME = FluffyChat;", f'PRODUCT_NAME = "{APP_NAME_EN}";')
sub(pbx, "FluffyChat.app", f"{APP_NAME_EN}.app")
sub(pbx, "INFOPLIST_KEY_CFBundleDisplayName = FluffyChat;", f'INFOPLIST_KEY_CFBundleDisplayName = "{APP_NAME_EN}";')
sub(pbx, "Copyright © 2023 FluffyChat authors.", "Copyright © FluffyChat and leoh-chat authors.")
sub("macos/Runner.xcodeproj/xcshareddata/xcschemes/Runner.xcscheme", "FluffyChat.app", f"{APP_NAME_EN}.app")
sub("macos/Runner/Info.plist", "with your contacts in FluffyChat.", f"with your contacts in {APP_NAME_EN}.")
# 没有苹果开发者账号：和上游 CI 一样用 ad-hoc 签名，去掉需要开发者证书的钥匙串分组
sub(pbx, 'CODE_SIGN_IDENTITY = "Apple Development";', 'CODE_SIGN_IDENTITY = "-";')
sub(pbx, "CODE_SIGN_STYLE = Automatic;", "CODE_SIGN_STYLE = Manual;")
p = src / pbx
p.write_text(re.sub(r"DEVELOPMENT_TEAM = [A-Z0-9]+;", 'DEVELOPMENT_TEAM = "";', p.read_text(encoding="utf-8")),
             encoding="utf-8")
for ent in ("macos/Runner/DebugProfile.entitlements", "macos/Runner/Release.entitlements"):
    p = src / ent
    p.write_text(re.sub(r"\s*<key>keychain-access-groups</key>\s*<array\s*/>", "", p.read_text(encoding="utf-8")),
                 encoding="utf-8")
# macOS 图标惯例四周留白约 10%
mac_icon = compose("mac.svg", ["full.svg"], 0.8)
for size in (16, 32, 64, 128, 256, 512, 1024):
    render_path(mac_icon, src / f"macos/Runner/Assets.xcassets/AppIcon.appiconset/app_icon_{size}.png", size)

# --- 网页版（chat.leoh.top）：改名、图标、字体走本站、下载提示条 ---
web = "web/index.html"
sub(web, '<meta name="description" content="The cutest messenger in the Matrix network.">',
    f'<meta name="description" content="{APP_NAME_ZH}">')
sub(web, '<meta name="apple-mobile-web-app-title" content="FluffyChat">',
    f'<meta name="apple-mobile-web-app-title" content="{APP_NAME_ZH}">')
sub(web, "<title>FluffyChat</title>", f"<title>{APP_NAME_ZH}</title>")
# 缺字时 Flutter 默认从 fonts.gstatic.com 下载中文/表情字体，国内连不上；改成本站反代 /gfonts/
sub(web, "initializeEngine({ useColorEmoji: true })",
    "initializeEngine({ useColorEmoji: true, fontFallbackBaseUrl: '/gfonts/' })")
sub(web, "</body>", '  <script src="leoh-download-banner.js" defer></script>\n</body>')
shutil.copy(pathlib.Path(__file__).resolve().parent / "web-src/download-banner.js", src / "web/leoh-download-banner.js")
shutil.copy(pathlib.Path(__file__).resolve().parent / "web-src/sw.js", src / "web/sw.js")
mf = "web/manifest.json"
sub(mf, '"name": "FluffyChat"', f'"name": "{APP_NAME_ZH}"')
sub(mf, '"short_name": "FluffyChat"', f'"short_name": "{APP_NAME_ZH}"')
sub(mf, '"description": "The cutest messenger in the Matrix network"', f'"description": "{APP_NAME_ZH}"')
sub(mf, '"theme_color": "#41a2bc"', '"theme_color": "#0E9F8A"')
for rel, size in (("favicon.png", 32), ("icons/Icon-16.png", 16), ("icons/Icon-32.png", 32),
                  ("icons/Icon-48.png", 48), ("icons/Icon-192.png", 192), ("icons/Icon-512.png", 512)):
    render("full.svg", src / "web" / rel, size)
maskable = compose("maskable.svg", ["background.svg", "foreground.svg"])
for size in (192, 512):
    render_path(maskable, src / f"web/icons/Icon-maskable-{size}.png", size)

print("rebrand ok:", src)
