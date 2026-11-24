package com.videomk.app

import android.content.Context
import android.content.Intent
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.By
import androidx.test.uiautomator.BySelector
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.UiObject2
import androidx.test.uiautomator.Until
import org.junit.Assume
import java.io.File

/**
 * Black-box helpers: the app is driven through UiAutomator like a user would (resource ids are the Compose test tags, exposed in debug builds).
 * QA tokens come from instrumentation arguments (`-e vmk_id_token ... -e vmk_refresh_token ...`), never from the repository.
 */
object Ui {
    const val PKG = "com.videomk.app"
    val instrumentation get() = InstrumentationRegistry.getInstrumentation()
    val device: UiDevice get() = UiDevice.getInstance(instrumentation)
    val context: Context get() = instrumentation.targetContext
    private val args get() = InstrumentationRegistry.getArguments()

    fun requireTokens(): Pair<String, String> {
        val id = args.getString("vmk_id_token")
        Assume.assumeTrue("no QA token in the instrumentation arguments (-e vmk_id_token)", !id.isNullOrEmpty())
        return id!! to (args.getString("vmk_refresh_token") ?: "")
    }

    /** [tokens] overrides the QA session (to test an expired or revoked session). */
    fun launch(signedIn: Boolean, minutes: String? = null, photoFiles: String? = null, tokens: Pair<String, String>? = null) {
        device.pressHome()
        val intent = Intent(context, MainActivity::class.java).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TASK)
            .putExtra("vmk_debug_reset", "1")
        if (signedIn) {
            val (id, refresh) = tokens ?: requireTokens()
            intent.putExtra("vmk_debug_id_token", id).putExtra("vmk_debug_refresh_token", refresh)
        }
        minutes?.let { intent.putExtra("vmk_debug_default_minutes", it) }
        photoFiles?.let { intent.putExtra("vmk_debug_photo_files", it) }
        context.startActivity(intent)
        device.wait(Until.hasObject(By.pkg(PKG).depth(0)), 15_000)
    }

    fun refreshTokenOrSkip(): String = requireTokens().second

    /** An unsigned token that looks expired (the app only reads claims; the server is what validates). */
    fun staleIdToken(): String {
        val enc = java.util.Base64.getUrlEncoder().withoutPadding()
        val h = enc.encodeToString("{\"alg\":\"none\"}".toByteArray())
        val p = enc.encodeToString("{\"sub\":\"stale-user\",\"exp\":1000000000}".toByteArray())
        return "$h.$p.sig"
    }

    fun res(tag: String): BySelector = By.res(tag)
    fun find(tag: String, timeoutMs: Long = 15_000): UiObject2? = device.wait(Until.findObject(res(tag)), timeoutMs)
    fun has(tag: String): Boolean = device.hasObject(res(tag))
    fun require(tag: String, timeoutMs: Long = 15_000): UiObject2 = find(tag, timeoutMs) ?: error("'$tag' not found within ${timeoutMs}ms")

    fun waitGone(tag: String, timeoutMs: Long): Boolean = device.wait(Until.gone(res(tag)), timeoutMs)

    /** Menus and dialogs are separate windows without test tags: they are found by their text. */
    fun clickText(text: String, exists: Boolean = false, timeoutMs: Long = 10_000) {
        val o = device.wait(Until.findObject(By.text(text)), timeoutMs) ?: error("text '$text' not found")
        if (!exists) o.click()
    }

    fun appIsForeground(): Boolean = device.hasObject(By.pkg(PKG))

    fun shot(name: String) {
        val dir = File(context.getExternalFilesDir(null), "shots").apply { mkdirs() }
        device.takeScreenshot(File(dir, "$name.png"))
    }

    /** Where the debug photo hook can read test photos (copied there with adb: see README). */
    fun photoDir(): File = File(context.filesDir, "")
}
