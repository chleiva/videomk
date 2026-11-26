package com.videomk.app.data

import android.content.Context
import android.util.Log
import coil3.SingletonImageLoader
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File

/** Runs every step, whatever the others did; returns the names of the steps that threw (never their messages: they could name a path or a value). */
class WipeSteps {
    private val failed = mutableListOf<String>()
    fun step(name: String, block: () -> Unit) { try { block() } catch (e: Exception) { failed += name } }
    val failures: List<String> get() = failed
}

/** Deletes what is inside [dir] and keeps [dir]. A file that cannot be deleted does not stop the rest. Returns false if anything is left. */
fun deleteChildren(dir: File?): Boolean {
    val kids = dir?.listFiles() ?: return true
    var all = true
    for (k in kids) if (!k.deleteRecursively()) all = false
    return all
}

/**
 * Everything the app keeps on the device for the person, removed after the server accepted an account deletion:
 * the session tokens (EncryptedSharedPreferences), the preference files, the image caches (Coil memory and disk), every cache file (picked photos,
 * cached My media pages, shared videos), every file (upload queue, organize job), databases, no-backup files and external caches.
 * Language-like settings that belong to the device are plain preferences too and go with it: the app has none that matter.
 */
object LocalDataWiper {
    private const val TAG = "LocalDataWiper"
    /** The preference files the app writes (see PhotoSettings, CreatePrefsStore, SecureTokenStore). Anything else the app may add must be listed here (the wiper test checks the sources for getSharedPreferences). */
    val PREFERENCE_FILES = listOf("videomk_settings", "videomk_create", "vmk_session", "app_language", "videomk_rating")

    suspend fun wipe(context: Context, stopWork: () -> Unit, clearTokens: () -> Unit, deckCache: File? = null) = withContext(Dispatchers.IO) {
        val app = context.applicationContext
        val s = WipeSteps()
        s.step("stop-work", stopWork)               // uploads and organize jobs must not write files after the wipe
        s.step("tokens", clearTokens)
        s.step("image-memory") { SingletonImageLoader.get(app).memoryCache?.clear() }
        s.step("image-disk") { SingletonImageLoader.get(app).diskCache?.clear() }
        s.step("prefs") {
            for (name in PREFERENCE_FILES) {
                app.getSharedPreferences(name, Context.MODE_PRIVATE).edit().clear().commit()   // the open instance is emptied too, then the file goes
                app.deleteSharedPreferences(name)
            }
        }
        s.step("deck-cache") { deckCache?.let { check(it.deleteRecursively() || !it.exists()) } }   // the temporary copy of a presentation being uploaded (also inside the cache folder below)
        s.step("cache") { check(deleteChildren(app.cacheDir)) }
        s.step("external-cache") { app.externalCacheDirs.forEach { deleteChildren(it) } }
        s.step("files") { check(deleteChildren(app.filesDir)) }
        s.step("no-backup") { deleteChildren(app.noBackupFilesDir) }
        s.step("databases") { app.databaseList().forEach { app.deleteDatabase(it) } }
        if (s.failures.isNotEmpty()) Log.w(TAG, "local wipe: steps with problems: ${s.failures.joinToString()}")
    }
}
