// leoh-chat 应用内更新（安卓）：发版时服务器经推送长连接广播（UpdateHint.kt，会弹系统通知），
// 打开 App 时据此立即检查；另外每天兜底查一次。读 chat.leoh.top/dl/version.json，有新版就提示，
// 点“更新”在 App 内下载、校验 SHA-256，再交给系统安装器（系统会确认一次）。
//
// version.json: {"version": "2.10.0", "build": 26100620, "url": "/dl/leoh-chat-26100620.apk",
//                "sha256": "...", "notes": "这次更新了什么", "force": false}

import 'dart:convert';
import 'dart:io';

import 'package:crypto/crypto.dart';
import 'package:flutter/foundation.dart' show kIsWeb;
import 'package:flutter/services.dart';
import 'package:http/http.dart' as http;
import 'package:material_ui/material_ui.dart';
import 'package:matrix/matrix.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:path_provider/path_provider.dart';
import 'package:shared_preferences/shared_preferences.dart';

abstract class LeohUpdate {
  static final Uri _manifest = Uri.parse('https://chat.leoh.top/dl/version.json');
  static const _channel = MethodChannel('top.leoh.chat/update');
  static const _skipKey = 'leoh_update_skipped_build';
  static const _checkedKey = 'leoh_update_checked_at';
  static bool _running = false;
  static AppLifecycleListener? _lifecycle;

  /// 聊天列表首次显示时调用：马上检查一次，之后每次 App 回到前台再检查（点更新通知打开时生效）
  static void start(BuildContext context) {
    check(context);
    _lifecycle ??= AppLifecycleListener(onResume: () {
      if (context.mounted) check(context);
    });
  }

  /// 打开聊天列表时调用：收到过新版本推送就立即查，否则每天最多查一次；失败静默
  static Future<void> check(BuildContext context, {bool manual = false}) async {
    if (kIsWeb || !Platform.isAndroid || _running) return;
    _running = true;
    try {
      final prefs = await SharedPreferences.getInstance();
      final now = DateTime.now().millisecondsSinceEpoch;
      final hinted = await _channel.invokeMethod<bool>('takeUpdateHint') == true;
      if (!manual && !hinted && now - (prefs.getInt(_checkedKey) ?? 0) < 24 * 3600 * 1000) return;
      await prefs.setInt(_checkedKey, now);

      final res = await http.get(_manifest).timeout(const Duration(seconds: 15));
      if (res.statusCode != 200) return;
      final info = jsonDecode(utf8.decode(res.bodyBytes)) as Map<String, Object?>;
      final build = (info['build'] as num?)?.toInt() ?? 0;
      final current = int.tryParse((await PackageInfo.fromPlatform()).buildNumber) ?? 0;
      if (build <= current) {
        if (manual && context.mounted) _snack(context, '已经是最新版本');
        return;
      }
      final force = info['force'] == true;
      if (!manual && !force && prefs.getInt(_skipKey) == build) return;
      if (!context.mounted) return;

      final ok = await showDialog<bool>(
        context: context,
        barrierDismissible: !force,
        builder: (c) => AlertDialog(
          title: Text('发现新版本 ${info['version'] ?? ''}'),
          content: Text((info['notes'] as String?)?.trim().isNotEmpty == true
              ? info['notes'] as String
              : '有新版本可以更新。'),
          actions: [
            if (!force)
              TextButton(
                onPressed: () {
                  prefs.setInt(_skipKey, build);
                  Navigator.of(c).pop(false);
                },
                child: const Text('以后再说'),
              ),
            FilledButton(onPressed: () => Navigator.of(c).pop(true), child: const Text('更新')),
          ],
        ),
      );
      if (ok == true && context.mounted) {
        await _downloadAndInstall(context, info);
      }
    } catch (e, s) {
      Logs().w('[LeohUpdate] check failed', e, s);
    } finally {
      _running = false;
    }
  }

  static Future<void> _downloadAndInstall(BuildContext context, Map<String, Object?> info) async {
    final url = _manifest.resolve(info['url'] as String);
    final expected = (info['sha256'] as String).toLowerCase();
    final dir = Directory('${(await getTemporaryDirectory()).path}/updates');
    if (dir.existsSync()) dir.deleteSync(recursive: true);
    dir.createSync(recursive: true);
    final file = File('${dir.path}/leoh-chat-${info['build']}.apk');

    final progress = ValueNotifier<double?>(null);
    var cancelled = false;
    final client = http.Client();
    if (!context.mounted) return;
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (c) => AlertDialog(
        title: const Text('正在下载更新'),
        content: ValueListenableBuilder<double?>(
          valueListenable: progress,
          builder: (_, v, _) => Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              LinearProgressIndicator(value: v),
              const SizedBox(height: 8),
              Text(v == null ? '' : '${(v * 100).toStringAsFixed(0)}%'),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () {
              cancelled = true;
              client.close();
              Navigator.of(c).pop();
            },
            child: const Text('取消'),
          ),
        ],
      ),
    );

    try {
      final resp = await client.send(http.Request('GET', url));
      if (resp.statusCode != 200) throw 'HTTP ${resp.statusCode}';
      final total = resp.contentLength ?? 0;
      final sink = file.openWrite();
      var got = 0;
      await for (final chunk in resp.stream) {
        sink.add(chunk);
        got += chunk.length;
        if (total > 0) progress.value = got / total;
      }
      await sink.close();
      final digest = (await sha256.bind(file.openRead()).first).toString();
      if (digest != expected) throw '安装包校验失败，请稍后重试';
      if (context.mounted) Navigator.of(context, rootNavigator: true).pop();

      if (await _channel.invokeMethod<bool>('canInstall') != true) {
        if (!context.mounted) return;
        await showDialog(
          context: context,
          builder: (c) => AlertDialog(
            title: const Text('需要允许安装'),
            content: const Text('第一次更新需要允许 leoh-chat “安装未知应用”。打开开关后按返回键回到 leoh-chat，会自动继续安装。'),
            actions: [
              FilledButton(
                onPressed: () {
                  Navigator.of(c).pop();
                  _channel.invokeMethod('openInstallPermission');
                },
                child: const Text('去设置'),
              ),
            ],
          ),
        );
        // 等用户从设置页回来（最多 3 分钟），拿到权限就直接装
        for (var i = 0; i < 180; i++) {
          await Future.delayed(const Duration(seconds: 1));
          if (await _channel.invokeMethod<bool>('canInstall') == true) break;
        }
        if (await _channel.invokeMethod<bool>('canInstall') != true) return;
      }
      await _channel.invokeMethod('install', {'path': file.path});
    } catch (e, s) {
      if (cancelled) return;
      Logs().w('[LeohUpdate] download failed', e, s);
      if (context.mounted) {
        Navigator.of(context, rootNavigator: true).maybePop();
        _snack(context, '更新失败：$e');
      }
    } finally {
      client.close();
    }
  }

  static void _snack(BuildContext context, String text) =>
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(text)));
}
