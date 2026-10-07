package top.leoh.chat

import android.content.Context
import android.content.Intent
import android.net.Uri
import android.os.Build
import android.provider.Settings
import androidx.core.content.FileProvider
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import java.io.File

/**
 * 应用内更新：Dart 侧下载并校验好 APK 后，经 MethodChannel 调这里交给系统安装器。
 * Android 不允许商店之外的 App 静默升级，系统会弹一次“是否安装此更新”。
 */
object ApkInstaller {
    private const val CHANNEL = "top.leoh.chat/update"

    fun register(engine: FlutterEngine, context: Context) {
        MethodChannel(engine.dartExecutor.binaryMessenger, CHANNEL).setMethodCallHandler { call, result ->
            when (call.method) {
                "takeUpdateHint" -> result.success(UpdateHint.take(context))
                "canInstall" -> result.success(
                    Build.VERSION.SDK_INT < 26 || context.packageManager.canRequestPackageInstalls(),
                )
                "openInstallPermission" -> {
                    // 第一次更新时要允许“安装未知应用”，跳到本 App 的这个开关
                    context.startActivity(
                        Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES, Uri.parse("package:${context.packageName}"))
                            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
                    )
                    result.success(null)
                }
                "install" -> {
                    val path = call.argument<String>("path")
                    if (path == null) { result.error("ARG", "path missing", null); return@setMethodCallHandler }
                    val uri = FileProvider.getUriForFile(context, "${context.packageName}.update_provider", File(path))
                    context.startActivity(
                        Intent(Intent.ACTION_VIEW)
                            .setDataAndType(uri, "application/vnd.android.package-archive")
                            .addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION or Intent.FLAG_ACTIVITY_NEW_TASK),
                    )
                    result.success(null)
                }
                else -> result.notImplemented()
            }
        }
    }
}

/** 只暴露缓存目录里的 updates/ 子目录给系统安装器 */
class UpdateFileProvider : FileProvider()
