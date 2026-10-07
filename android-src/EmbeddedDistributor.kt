package top.leoh.chat

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log
import java.security.SecureRandom

/**
 * 内置的 UnifiedPush 分发程序：leoh-chat 自己就是自己的“ntfy”，不用另装 App。
 *
 * UnifiedPush connector 在注册时向分发程序发 REGISTER 广播；这里给每个 token
 * 分配一个 ntfy.leoh.top 上的随机 up* 主题，回复 NEW_ENDPOINT，并让
 * [NtfyListenService] 开始监听。receiver 不导出，只有本 App 能调用。
 */
object EmbeddedDistributor {
    const val TAG = "LeoPush"
    const val SERVER = "https://ntfy.leoh.top"

    private const val PREFS = "leoh_embedded_distributor"
    private const val KEY_TOPIC_PREFIX = "topic:" // topic:<token> -> up...

    // UnifiedPush 协议常量（与 org.unifiedpush.android.connector 保持一致）
    const val ACTION_REGISTER = "org.unifiedpush.android.distributor.REGISTER"
    const val ACTION_UNREGISTER = "org.unifiedpush.android.distributor.UNREGISTER"
    const val ACTION_NEW_ENDPOINT = "org.unifiedpush.android.connector.NEW_ENDPOINT"
    const val ACTION_UNREGISTERED = "org.unifiedpush.android.connector.UNREGISTERED"
    const val ACTION_MESSAGE = "org.unifiedpush.android.connector.MESSAGE"
    const val EXTRA_TOKEN = "token"
    const val EXTRA_APPLICATION = "application"
    const val EXTRA_ENDPOINT = "endpoint"
    const val EXTRA_BYTES_MESSAGE = "bytesMessage"
    const val EXTRA_MESSAGE_ID = "id"

    private fun prefs(context: Context) =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    /** token -> topic */
    fun registrations(context: Context): Map<String, String> =
        prefs(context).all
            .filterKeys { it.startsWith(KEY_TOPIC_PREFIX) }
            .map { (k, v) -> k.removePrefix(KEY_TOPIC_PREFIX) to v.toString() }
            .toMap()

    fun hasRegistrations(context: Context) = registrations(context).isNotEmpty()

    fun endpointFor(topic: String) = "$SERVER/$topic?up=1"

    private fun newTopic(): String {
        // ntfy 只对 up* 主题开放匿名读写，主题名本身就是凭据，需足够随机
        val chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        val rnd = SecureRandom()
        return "up" + (1..16).map { chars[rnd.nextInt(chars.length)] }.joinToString("")
    }

    fun register(context: Context, token: String) {
        val p = prefs(context)
        val topic = p.getString(KEY_TOPIC_PREFIX + token, null) ?: newTopic().also {
            p.edit().putString(KEY_TOPIC_PREFIX + token, it).apply()
        }
        Log.i(TAG, "register -> $topic")
        context.sendBroadcast(Intent(ACTION_NEW_ENDPOINT).apply {
            setPackage(context.packageName)
            putExtra(EXTRA_TOKEN, token)
            putExtra(EXTRA_ENDPOINT, endpointFor(topic))
        })
        NtfyListenService.start(context)
    }

    fun unregister(context: Context, token: String) {
        prefs(context).edit().remove(KEY_TOPIC_PREFIX + token).apply()
        Log.i(TAG, "unregister")
        context.sendBroadcast(Intent(ACTION_UNREGISTERED).apply {
            setPackage(context.packageName)
            putExtra(EXTRA_TOKEN, token)
        })
        if (hasRegistrations(context)) NtfyListenService.start(context)
        else NtfyListenService.stop(context)
    }

    /** 把 ntfy 收到的消息交给 connector（再转给 Flutter 侧显示通知） */
    fun deliver(context: Context, topic: String, id: String, body: ByteArray) {
        val token = registrations(context).entries.firstOrNull { it.value == topic }?.key ?: return
        context.sendBroadcast(Intent(ACTION_MESSAGE).apply {
            setPackage(context.packageName)
            putExtra(EXTRA_TOKEN, token)
            putExtra(EXTRA_BYTES_MESSAGE, body)
            putExtra(EXTRA_MESSAGE_ID, id)
        })
    }
}

/** 接收 connector 发来的 REGISTER / UNREGISTER（不导出） */
class EmbeddedDistributorReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        val token = intent.getStringExtra(EmbeddedDistributor.EXTRA_TOKEN) ?: return
        val app = intent.getStringExtra(EmbeddedDistributor.EXTRA_APPLICATION)
        if (app != null && app != context.packageName) return
        when (intent.action) {
            EmbeddedDistributor.ACTION_REGISTER -> EmbeddedDistributor.register(context, token)
            EmbeddedDistributor.ACTION_UNREGISTER -> EmbeddedDistributor.unregister(context, token)
        }
    }
}

/** 开机、App 更新后恢复监听 */
class EmbeddedDistributorBootReceiver : BroadcastReceiver() {
    override fun onReceive(context: Context, intent: Intent) {
        if (EmbeddedDistributor.hasRegistrations(context)) NtfyListenService.start(context)
    }
}
