// leoh-chat：机器人命令菜单（Telegram 输入框左边的“菜单”按钮）、可点击的命令、机器人通讯录。
//
// tg-gateway 把机器人用 setMyCommands 注册的命令写进房间状态 `top.leoh.bot_commands`：
//   {"prefix": "!", "commands": [{"command": "start", "description": "开始"}, ...]}
// 消息里的命令是 <a href="leoh-cmd:!start">，点了就直接发这个命令。

import 'package:fluffychat/widgets/avatar.dart';
import 'package:fluffychat/widgets/future_loading_dialog.dart';
import 'package:fluffychat/widgets/matrix.dart';
import 'package:go_router/go_router.dart';
import 'package:material_ui/material_ui.dart';
import 'package:matrix/matrix.dart';

const String botCommandsState = 'top.leoh.bot_commands';
const String botCommandScheme = 'leoh-cmd:';

/// 我们服务器上的机器人（新建聊天页的“机器人”分组；退出私聊后从这里一点就能回来）
const List<({String mxid, String name, String about})> leohBots = [
  (mxid: '@idbot:matrix.leoh.top', name: 'Leoh ID 机器人', about: '账号、邀请、权限'),
  (mxid: '@ncbot:matrix.leoh.top', name: 'Nextcloud 机器人', about: '网盘'),
  (mxid: '@hermes:matrix.leoh.top', name: 'Hermes 助手', about: 'AI 助手'),
];

class BotCommand {
  final String command;
  final String description;
  const BotCommand(this.command, this.description);
}

/// 房间里的机器人命令；没有就返回空列表
List<BotCommand> botCommands(Room room) {
  final content = room.getState(botCommandsState)?.content;
  final list = content?['commands'];
  if (list is! List) return const [];
  return [
    for (final c in list)
      if (c is Map && c['command'] is String && (c['command'] as String).isNotEmpty)
        BotCommand(c['command'] as String, (c['description'] as String?) ?? ''),
  ];
}

String botCommandPrefix(Room room) {
  final p = room.getState(botCommandsState)?.content['prefix'];
  return p is String && p.isNotEmpty ? p : '!';
}

/// 发送一条命令（菜单项、可点击命令都走这里）
Future<void> sendBotCommand(BuildContext context, Room room, String text) async {
  try {
    await room.sendTextEvent(text, parseCommands: false);
  } catch (e, s) {
    Logs().w('[BotCommands] send failed', e, s);
    if (context.mounted) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('发送失败，请稍后再试')),
      );
    }
  }
}

/// 处理消息里的 leoh-cmd: 链接；不是的话返回 false 交给默认逻辑
bool handleBotCommandLink(BuildContext context, Room room, String url) {
  if (!url.startsWith(botCommandScheme)) return false;
  final cmd = Uri.decodeComponent(url.substring(botCommandScheme.length)).trim();
  if (cmd.isNotEmpty) sendBotCommand(context, room, cmd);
  return true;
}

/// 输入框左边的“菜单”按钮，只在有机器人命令的房间显示
class BotCommandMenuButton extends StatelessWidget {
  final Room room;
  final double height;
  const BotCommandMenuButton({required this.room, required this.height, super.key});

  @override
  Widget build(BuildContext context) {
    final commands = botCommands(room);
    if (commands.isEmpty) return const SizedBox.shrink();
    final theme = Theme.of(context);
    return Container(
      height: height,
      width: 48,
      alignment: Alignment.center,
      child: IconButton(
        tooltip: '命令菜单',
        color: theme.colorScheme.onPrimaryContainer,
        icon: const Icon(Icons.menu),
        onPressed: () => _open(context, commands),
      ),
    );
  }

  Future<void> _open(BuildContext context, List<BotCommand> commands) async {
    final prefix = botCommandPrefix(room);
    final picked = await showModalBottomSheet<String>(
      context: context,
      showDragHandle: true,
      builder: (c) => SafeArea(
        child: ListView(
          shrinkWrap: true,
          children: [
            for (final cmd in commands)
              ListTile(
                leading: const Icon(Icons.chevron_right),
                title: Text('$prefix${cmd.command}'),
                subtitle: cmd.description.isEmpty ? null : Text(cmd.description),
                onTap: () => Navigator.of(c).pop('$prefix${cmd.command}'),
              ),
          ],
        ),
      ),
    );
    if (picked != null && context.mounted) {
      await sendBotCommand(context, room, picked);
    }
  }
}

/// 新建聊天页里的“机器人”分组：点一下进入已有私聊，没有就新建（退出过也能回来）
class LeohBotList extends StatelessWidget {
  const LeohBotList({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 4),
          child: Text(
            '机器人',
            style: TextStyle(color: theme.colorScheme.primary, fontWeight: FontWeight.bold),
          ),
        ),
        for (final bot in leohBots)
          ListTile(
            leading: Avatar(name: bot.name),
            title: Text(bot.name),
            subtitle: Text(bot.about),
            trailing: const Icon(Icons.chevron_right),
            onTap: () => _open(context, bot.mxid),
          ),
      ],
    );
  }

  Future<void> _open(BuildContext context, String mxid) async {
    final client = Matrix.of(context).client;
    final result = await showFutureLoadingDialog(
      context: context,
      future: () => client.startDirectChat(mxid, enableEncryption: false),
    );
    final roomId = result.result;
    if (roomId != null && context.mounted) context.go('/rooms/$roomId');
  }
}
