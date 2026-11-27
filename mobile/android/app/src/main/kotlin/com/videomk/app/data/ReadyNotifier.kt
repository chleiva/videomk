package com.videomk.app.data

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import androidx.core.app.NotificationCompat
import androidx.core.app.NotificationManagerCompat
import com.videomk.app.MainActivity
import com.videomk.app.R
import com.videomk.app.core.MakingEvents
import com.videomk.app.core.Txt
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow

/**
 * "Tell me when it's ready" (the one switch on the Making screen). A local notification, posted by the app itself when it sees a video finish while it is not on
 * screen: there is no push yet, so this works for as long as Android keeps the app alive in the background (the app keeps checking, slowly, while the switch is on).
 * The choice is a plain preference; nothing is sent anywhere. Never throws: a notification is a courtesy.
 */
class ReadyNotifier(private val context: Context) : MakingEvents {
    private val prefs = context.getSharedPreferences("vmk_notify", Context.MODE_PRIVATE)
    private val _wanted = MutableStateFlow(runCatching { prefs.getBoolean(KEY, false) }.getOrDefault(false))
    /** What the person chose (the switch). */
    val wanted: StateFlow<Boolean> get() = _wanted
    /** The app is on screen: it shows the result itself, so nothing is posted. */
    @Volatile var appVisible = true

    fun permitted(): Boolean = runCatching { NotificationManagerCompat.from(context).areNotificationsEnabled() }.getOrDefault(false)
    /** The switch is on and the system allows notifications. */
    val active: Boolean get() = _wanted.value && permitted()

    fun set(on: Boolean) { _wanted.value = on; runCatching { prefs.edit().putBoolean(KEY, on).apply() } }

    override fun onFinished(videoId: String, title: String, ready: Boolean) {
        if (!active || appVisible) return
        runCatching {
            val nm = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
            nm.createNotificationChannel(NotificationChannel(CHANNEL, Txt.s(R.string.notify_channel), NotificationManager.IMPORTANCE_DEFAULT))
            val open = PendingIntent.getActivity(context, 0, Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_SINGLE_TOP), PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT)
            val n = NotificationCompat.Builder(context, CHANNEL).setSmallIcon(R.drawable.ic_play_sparkle)
                .setContentTitle(Txt.s(if (ready) R.string.notify_ready_title else R.string.notify_failed_title)).setContentText(title)
                .setContentIntent(open).setAutoCancel(true).build()
            nm.notify(videoId.hashCode(), n)
        }
    }

    private companion object { const val KEY = "ready"; const val CHANNEL = "video_ready" }
}
