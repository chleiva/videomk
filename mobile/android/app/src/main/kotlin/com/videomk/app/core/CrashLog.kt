package com.videomk.app.core

import java.io.File
import java.io.PrintWriter
import java.io.StringWriter

/**
 * Writes the last crash to a small file in the app's private storage, so the next support conversation has a stack trace even when the store's crash
 * reports lag by hours. Only class names and frames are written (no exception message: it can hold a file name or a typed word), no account data.
 * The previous handler still runs afterwards, so the system's "app stopped" behaviour and the store's own reporting are untouched.
 */
object CrashLog {
    const val FILE = "last-crash.txt"
    private const val MAX_CHARS = 8_000

    fun render(t: Throwable, thread: String, version: String, now: Long): String {
        val sw = StringWriter()
        var c: Throwable? = t
        var depth = 0
        PrintWriter(sw).use { w ->
            w.println("VideoMK $version  thread=$thread  at=$now")
            while (c != null && depth < 4) {
                w.println((if (depth == 0) "" else "caused by ") + c!!.javaClass.name)
                for (f in c!!.stackTrace.take(30)) w.println("    at $f")
                c = c!!.cause; depth++
            }
        }
        return sw.toString().take(MAX_CHARS)
    }

    fun install(dir: File, version: String) {
        val previous = Thread.getDefaultUncaughtExceptionHandler()
        Thread.setDefaultUncaughtExceptionHandler { thread, error ->
            runCatching { File(dir, FILE).writeText(render(error, thread.name, version, System.currentTimeMillis())) }
            previous?.uncaughtException(thread, error)
        }
    }

    fun last(dir: File): String? = runCatching { File(dir, FILE).takeIf { it.exists() }?.readText() }.getOrNull()
}
