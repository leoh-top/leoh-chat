// leoh-chat：机器人消息下面的 Telegram 式按钮。
//
// 机器人（tg-gateway）在消息 content 里放 `top.leoh.keyboard`：
//   [[{"text": "批准", "key": "1️⃣"}, {"text": "网页", "url": "https://..."}], ...]
// 点回调按钮 = 发一个 key 对应的 m.reaction，网关把它当作按下按钮；
// 网关为兼容其他客户端挂在消息上的同名表情，由 [botKeyboardKeys] 交给 MessageReactions 隐藏。

import 'package:fluffychat/utils/url_launcher.dart';
import 'package:material_ui/material_ui.dart';
import 'package:matrix/matrix.dart';

const String botKeyboardField = 'top.leoh.keyboard';

/// 解析出的按钮行；不是机器人键盘消息时返回 null
List<List<Map<String, String>>>? botKeyboardRows(Event event) {
  final raw = event.content[botKeyboardField];
  if (raw is! List) return null;
  final rows = <List<Map<String, String>>>[];
  for (final row in raw) {
    if (row is! List) continue;
    final cells = <Map<String, String>>[];
    for (final b in row) {
      if (b is! Map) continue;
      final text = b['text'];
      if (text is! String || text.isEmpty) continue;
      final url = b['url'];
      final key = b['key'];
      if (url is String && url.isNotEmpty) {
        cells.add({'text': text, 'url': url});
      } else if (key is String && key.isNotEmpty) {
        cells.add({'text': text, 'key': key});
      }
    }
    if (cells.isNotEmpty) rows.add(cells);
  }
  return rows.isEmpty ? null : rows;
}

/// 这条消息的按钮所用的表情 key（要从表情回应里隐藏）。传编辑后的显示事件。
Set<String> botKeyboardKeys(Event event) => {
  for (final row in botKeyboardRows(event) ?? const <List<Map<String, String>>>[])
    for (final b in row)
      if (b['key'] != null) b['key']!,
};

/// 是否有不属于按钮的表情回应（全是按钮表情时不显示回应栏）。
/// [event] 是原始事件（回应挂在它上面），按钮以编辑后的 [displayEvent] 为准。
bool hasNonKeyboardReactions(Event event, Event displayEvent, Timeline timeline) {
  final keys = botKeyboardKeys(displayEvent);
  return event
      .aggregatedEvents(timeline, RelationshipTypes.reaction)
      .any((e) => !keys.contains(e.content.tryGetMap<String, Object?>('m.relates_to')?.tryGet<String>('key')));
}

/// 去掉网关给其他客户端准备的文字版键盘（<div data-leoh-keyboard>）
String stripBotKeyboardHtml(String html) => html.replaceAll(
  RegExp(r'<div data-leoh-keyboard="1">[\s\S]*?</div>\s*$'),
  '',
);

class BotKeyboard extends StatefulWidget {
  /// 原始事件（按钮挂在它上面）
  final Event event;

  /// 编辑后的显示事件（按钮内容以它为准）
  final Event displayEvent;
  final Color color;

  const BotKeyboard({
    required this.event,
    required this.displayEvent,
    required this.color,
    super.key,
  });

  @override
  State<BotKeyboard> createState() => _BotKeyboardState();
}

class _BotKeyboardState extends State<BotKeyboard> {
  String? _pressing;

  Future<void> _press(String key) async {
    if (_pressing != null) return;
    setState(() => _pressing = key);
    try {
      await widget.event.room.sendReaction(widget.event.eventId, key);
    } catch (e, s) {
      Logs().w('[BotKeyboard] press failed', e, s);
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('按钮发送失败，请稍后再试')),
        );
      }
    } finally {
      // 机器人一般会马上编辑这条消息；留一会儿“处理中”，避免连点
      await Future.delayed(const Duration(milliseconds: 800));
      if (mounted) setState(() => _pressing = null);
    }
  }

  @override
  Widget build(BuildContext context) {
    final rows = botKeyboardRows(widget.displayEvent);
    if (rows == null) return const SizedBox.shrink();
    final color = widget.color;
    return Padding(
      padding: const EdgeInsets.fromLTRB(8, 0, 8, 8),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          for (final row in rows)
            Padding(
              padding: const EdgeInsets.only(top: 4),
              child: Row(
                children: [
                  for (var i = 0; i < row.length; i++) ...[
                    if (i > 0) const SizedBox(width: 4),
                    Expanded(child: _button(context, row[i], color)),
                  ],
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _button(BuildContext context, Map<String, String> b, Color color) {
    final url = b['url'];
    final key = b['key'];
    final busy = key != null && _pressing == key;
    return OutlinedButton(
      onPressed: _pressing != null && !busy
          ? null
          : url != null
          ? () => UrlLauncher(context, url).launchUrl()
          : () => _press(key!),
      style: OutlinedButton.styleFrom(
        foregroundColor: color,
        side: BorderSide(color: color.withAlpha(96)),
        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 10),
        minimumSize: const Size(0, 40),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      ),
      child: busy
          ? SizedBox(
              width: 16,
              height: 16,
              child: CircularProgressIndicator(strokeWidth: 2, color: color),
            )
          : Row(
              mainAxisSize: MainAxisSize.min,
              children: [
                Flexible(
                  child: Text(
                    b['text']!,
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                    textAlign: TextAlign.center,
                  ),
                ),
                if (url != null) ...[
                  const SizedBox(width: 4),
                  Icon(Icons.open_in_new, size: 14, color: color),
                ],
              ],
            ),
    );
  }
}
