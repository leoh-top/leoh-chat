package top.leoh.chat

import android.annotation.SuppressLint
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.Network
import android.net.Uri
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import android.provider.Settings
import android.util.Base64
import android.util.Log
import org.json.JSONObject
import java.io.BufferedReader
import java.io.InputStreamReader
import java.net.HttpURLConnection
import java.net.URL

/**
 * 常驻前台服务：用 ntfy 的 JSON 流接口长连 ntfy.leoh.top，收到推送就交给
 * [EmbeddedDistributor.deliver]。断线自动重连（指数退避，网络恢复时立即重连），
 * 重连时用 since=<上次时间> 补拉断线期间的消息（ntfy 缓存 24 小时）。
 */
class NtfyListenService : Service() {
    @Volatile private var running = false
    @Volatile private var conn: HttpURLConnection? = null
    private var worker: Thread? = null
    private var netCallback: ConnectivityManager.NetworkCallback? = null
    private val recentIds = ArrayDeque<String>()

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        goForeground()
        running = true
        worker = Thread(::loop, "leoh-ntfy").apply { isDaemon = true; start() }
        val cm = getSystemService(ConnectivityManager::class.java)
        netCallback = object : ConnectivityManager.NetworkCallback() {
            // 换网络（Wi-Fi ⇄ 流量）时旧连接会挂住，主动断开让循环立刻重连
            override fun onAvailable(network: Network) { reconnectNow() }
        }.also { runCatching { cm.registerDefaultNetworkCallback(it) } }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_RESUBSCRIBE) reconnectNow()
        return START_STICKY
    }

    override fun onDestroy() {
        running = false
        reconnectNow()
        netCallback?.let { cb ->
            runCatching { getSystemService(ConnectivityManager::class.java).unregisterNetworkCallback(cb) }
        }
        super.onDestroy()
    }

    private fun reconnectNow() {
        runCatching { conn?.disconnect() }
    }

    private fun loop() {
        var backoff = 2_000L
        while (running) {
            val pushTopics = EmbeddedDistributor.registrations(this).values.distinct()
            if (pushTopics.isEmpty()) { stopSelf(); return }
            // 同一条长连接顺带订阅“新版本”广播，不额外耗电
            val topics = pushTopics + UpdateHint.TOPIC
            val ok = runCatching { stream(topics) }
                .onFailure { Log.w(EmbeddedDistributor.TAG, "stream: ${it.javaClass.simpleName}: ${it.message}") }
                .getOrDefault(false)
            if (!running) return
            backoff = if (ok) 2_000L else (backoff * 2).coerceAtMost(120_000L)
            try { Thread.sleep(backoff) } catch (_: InterruptedException) { return }
        }
    }

    /** 返回 true 表示曾成功连上（下次快速重连） */
    private fun stream(topics: List<String>): Boolean {
        val prefs = getSharedPreferences(PREFS, MODE_PRIVATE)
        // 首次连接不补拉；之后从上次收到的时间点续上，重复的靠 recentIds 去掉
        val since = prefs.getLong(KEY_SINCE, 0L)
        val url = buildString {
            append(EmbeddedDistributor.SERVER).append('/').append(topics.joinToString(",")).append("/json")
            if (since > 0) append("?since=").append(since)
        }
        val c = (URL(url).openConnection() as HttpURLConnection).apply {
            connectTimeout = 20_000
            readTimeout = 100_000 // 服务端 45 秒一次 keepalive
            // Cloudflare 会拦 Java 默认 UA，带上自己的
            setRequestProperty("User-Agent", "leoh-chat/${versionName()} (Android; $packageName)")
        }
        conn = c
        try {
            if (c.responseCode != 200) {
                Log.w(EmbeddedDistributor.TAG, "HTTP ${c.responseCode}")
                return false
            }
            BufferedReader(InputStreamReader(c.inputStream, Charsets.UTF_8)).use { r ->
                while (running) {
                    val line = r.readLine() ?: break
                    if (line.isBlank()) continue
                    handle(JSONObject(line), prefs)
                }
            }
            return true
        } finally {
            conn = null
            runCatching { c.disconnect() }
        }
    }

    private fun handle(j: JSONObject, prefs: android.content.SharedPreferences) {
        val time = j.optLong("time")
        when (j.optString("event")) {
            "open" -> Log.i(EmbeddedDistributor.TAG, "connected")
            "message" -> {
                val id = j.optString("id")
                if (id in recentIds) return
                recentIds.addLast(id); while (recentIds.size > 50) recentIds.removeFirst()
                val raw = j.optString("message")
                if (j.optString("topic") == UpdateHint.TOPIC) {
                    UpdateHint.onAnnounce(this, raw)
                } else {
                    val body = if (j.optString("encoding") == "base64") Base64.decode(raw, Base64.DEFAULT)
                               else raw.toByteArray(Charsets.UTF_8)
                    EmbeddedDistributor.deliver(this, j.optString("topic"), id, body)
                }
            }
        }
        if (time > 0) prefs.edit().putLong(KEY_SINCE, time).apply()
    }

    private fun versionName(): String =
        runCatching { packageManager.getPackageInfo(packageName, 0).versionName }.getOrNull() ?: "0"

    private fun goForeground() {
        val nm = getSystemService(NotificationManager::class.java)
        if (Build.VERSION.SDK_INT >= 26) {
            nm.createNotificationChannel(NotificationChannel(CHANNEL, "后台保持连接", NotificationManager.IMPORTANCE_MIN).apply {
                description = "leoh-chat 需要这条通知才能在后台及时收到新消息，可以在这里把它设为静默"
                setShowBadge(false)
            })
        }
        val open = PendingIntent.getActivity(
            this, 0, packageManager.getLaunchIntentForPackage(packageName),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT,
        )
        @Suppress("DEPRECATION")
        val b = if (Build.VERSION.SDK_INT >= 26) Notification.Builder(this, CHANNEL) else Notification.Builder(this)
        val n = b.setSmallIcon(R.drawable.notifications_icon)
            .setContentTitle("leoh-chat 正在接收新消息")
            .setContentText("点此打开 leoh-chat")
            .setContentIntent(open)
            .setOngoing(true)
            .setShowWhen(false)
            .build()
        if (Build.VERSION.SDK_INT >= 34) {
            startForeground(NOTIFICATION_ID, n, FOREGROUND_SERVICE_TYPE_REMOTE_MESSAGING)
        } else {
            startForeground(NOTIFICATION_ID, n)
        }
    }

    companion object {
        private const val CHANNEL = "leoh_push_keepalive"
        private const val NOTIFICATION_ID = 7301
        private const val PREFS = "leoh_ntfy_listen"
        private const val KEY_SINCE = "since"
        private const val KEY_ASKED_BATTERY = "asked_battery"
        private const val ACTION_RESUBSCRIBE = "top.leoh.chat.RESUBSCRIBE"
        // ServiceInfo.FOREGROUND_SERVICE_TYPE_REMOTE_MESSAGING（API 34）
        private const val FOREGROUND_SERVICE_TYPE_REMOTE_MESSAGING = 512

        fun start(context: Context) {
            try {
                val i = Intent(context, NtfyListenService::class.java).setAction(ACTION_RESUBSCRIBE)
                if (Build.VERSION.SDK_INT >= 26) context.startForegroundService(i) else context.startService(i)
            } catch (e: Exception) {
                // Android 12+ 不允许从后台启动前台服务；下次打开 App 时会再启动
                Log.w(EmbeddedDistributor.TAG, "start failed: $e")
            }
            askIgnoreBatteryOptimizations(context)
        }

        fun stop(context: Context) {
            context.stopService(Intent(context, NtfyListenService::class.java))
        }

        /** 第一次注册时弹系统对话框“允许 leoh-chat 始终在后台运行”，只问一次 */
        @SuppressLint("BatteryLife")
        private fun askIgnoreBatteryOptimizations(context: Context) {
            val prefs = context.getSharedPreferences(PREFS, MODE_PRIVATE)
            if (prefs.getBoolean(KEY_ASKED_BATTERY, false)) return
            val pm = context.getSystemService(PowerManager::class.java)
            if (pm.isIgnoringBatteryOptimizations(context.packageName)) return
            prefs.edit().putBoolean(KEY_ASKED_BATTERY, true).apply()
            runCatching {
                context.startActivity(
                    Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS, Uri.parse("package:${context.packageName}"))
                        .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                )
            }.onFailure { Log.w(EmbeddedDistributor.TAG, "battery prompt: $it") }
        }
    }
}
