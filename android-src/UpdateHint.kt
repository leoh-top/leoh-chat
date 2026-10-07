package top.leoh.chat

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Log
import org.json.JSONObject

/**
 * 发版时 deploy.sh 往 ntfy 主题 [TOPIC] 发一条 {"version","build","notes"}。
 * 推送长连接收到后：版本比本机新就弹一条“发现新版本”通知，并记下标记；
 * Dart 侧（leoh_update.dart）打开 App 时通过 MethodChannel 读到标记，立即检查更新，不受定时限制。
 */
object UpdateHint {
    const val TOPIC = "leoh-chat-updates"
    private const val PREFS = "leoh_update_hint"
    private const val KEY_BUILD = "announced_build"
    private const val CHANNEL = "leoh_app_update"
    private const val NOTIFICATION_ID = 7302

    fun onAnnounce(context: Context, raw: String) {
        val j = runCatching { JSONObject(raw) }.getOrNull() ?: return
        val build = j.optLong("build")
        if (build <= currentBuild(context)) return
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        if (prefs.getLong(KEY_BUILD, 0) >= build) return // 同一版本只提醒一次
        prefs.edit().putLong(KEY_BUILD, build).apply()
        Log.i(EmbeddedDistributor.TAG, "update announced: $build")
        notify(context, j.optString("version"), j.optString("notes"))
    }

    /** Dart 调用：有未处理的新版本广播就返回 true（只返回一次） */
    fun take(context: Context): Boolean {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val build = prefs.getLong(KEY_BUILD, 0)
        if (build <= currentBuild(context)) return false
        if (prefs.getLong("taken_build", 0) >= build) return false
        prefs.edit().putLong("taken_build", build).apply()
        context.getSystemService(NotificationManager::class.java).cancel(NOTIFICATION_ID)
        return true
    }

    private fun currentBuild(context: Context): Long = runCatching {
        val info = context.packageManager.getPackageInfo(context.packageName, 0)
        if (Build.VERSION.SDK_INT >= 28) info.longVersionCode else @Suppress("DEPRECATION") info.versionCode.toLong()
    }.getOrDefault(Long.MAX_VALUE)

    private fun notify(context: Context, version: String, notes: String) {
        val nm = context.getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) {
            nm.createNotificationChannel(
                NotificationChannel(CHANNEL, "App 更新", NotificationManager.IMPORTANCE_DEFAULT),
            )
        }
        val open = PendingIntent.getActivity(
            context, 1, context.packageManager.getLaunchIntentForPackage(context.packageName)
                ?.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        @Suppress("DEPRECATION")
        val b = if (Build.VERSION.SDK_INT >= 26) android.app.Notification.Builder(context, CHANNEL)
                else android.app.Notification.Builder(context)
        nm.notify(
            NOTIFICATION_ID,
            b.setSmallIcon(R.drawable.notifications_icon)
                .setContentTitle("leoh-chat 有新版本 $version")
                .setContentText(notes.ifBlank { "点此打开并更新" })
                .setContentIntent(open)
                .setAutoCancel(true)
                .build(),
        )
    }
}
