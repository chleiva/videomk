package com.videomk.app.core

import kotlinx.serialization.json.JsonObject
import java.time.Instant

/**
 * The account's plan as capabilities and the wallet report it (docs/PLANS.md section 5). Read-only today: nothing can be bought (`can_upgrade` is false),
 * so the app shows the name and the limits and never a buy button. Every field is optional: a server without plans sends none of this.
 */
data class PlanInfo(
    val id: String, val name: String,
    /** The longest video this plan makes, in seconds (30 on Free today). */
    val maxSeconds: Int? = null,
    val resolutions: List<String> = emptyList(),
    val watermarkForced: Boolean = false,
    val photosPerVideo: Int? = null,
    val storageBytes: Long? = null,
) {
    val isFree: Boolean get() = id == "free"

    companion object {
        fun fromJson(o: JsonObject?): PlanInfo? {
            o ?: return null
            val id = o.str("id") ?: return null
            val l = o.obj("limits")
            return PlanInfo(
                id, o.str("name")?.takeIf { it.isNotBlank() } ?: id.replaceFirstChar { it.uppercase() },
                maxSeconds = l?.int("max_seconds"), resolutions = l?.arr("resolutions")?.mapNotNull { (it as? kotlinx.serialization.json.JsonPrimitive)?.content } ?: emptyList(),
                watermarkForced = l?.bool("watermark_forced") ?: false, photosPerVideo = l?.int("photos_per_video"), storageBytes = l?.num("storage_bytes")?.toLong(),
            )
        }
    }
}

/**
 * What a Free account may do right now (`free` in the wallet and capabilities). [available] false comes with one [reason] (`off`, `app_only`, `not_available`,
 * `paused`, `used`, `monthly_cap`) and the server's own sentence in [message], shown as received.
 */
data class FreeInfo(val available: Boolean, val reason: String? = null, val message: String? = null, val creditsLeft: Int? = null, val maxSeconds: Int? = null, val budgetPaused: Boolean = false, val resumesAt: Instant? = null) {
    companion object {
        fun fromJson(o: JsonObject?): FreeInfo? {
            o ?: return null
            return FreeInfo(o.bool("available") ?: true, o.str("reason"), o.str("message")?.takeIf { it.isNotBlank() }, o.int("credits_left"), o.int("max_seconds"), o.bool("budget_paused") ?: false, parseInstant(o.str("resumes_at")))
        }
    }
}

/** The plan fields shared by the wallet and capabilities. */
data class PlanState(val plan: PlanInfo? = null, val free: FreeInfo? = null, val freeCreation: String? = null, val canUpgrade: Boolean = false) {
    companion object {
        val NONE = PlanState()
        fun fromJson(o: JsonObject): PlanState = PlanState(PlanInfo.fromJson(o.obj("plan")), FreeInfo.fromJson(o.obj("free")), o.str("free_creation"), o.bool("can_upgrade") ?: false)
    }
}

/** One video of the public showcase (`GET /gallery`): what a Free account that cannot create is shown instead of an empty Create. Links last an hour: never stored. */
data class GalleryVideo(val id: String, val title: String, val videoUrl: String, val posterUrl: String?, val aspect: String?, val seconds: Double?) {
    companion object {
        fun listFromJson(o: JsonObject): List<GalleryVideo> = o.arr("videos")?.mapNotNull { e ->
            e.asObject()?.let { v ->
                val id = v.str("id") ?: return@let null; val url = v.str("video_url") ?: return@let null
                GalleryVideo(id, v.str("title").orEmpty(), url, v.str("poster_url"), v.str("aspect"), v.num("seconds"))
            }
        } ?: emptyList()
    }
}

/**
 * Create for an account that cannot make a video right now (docs/PLANS.md section 3): a Free account whose free creation is off, used up or paused and that has
 * no credit to spend sees the server's sentence, the plan names and the showcase, never an empty or broken form.
 */
object CreateGate {
    /** Null: Create works as usual. */
    data class Locked(val message: String?, val resumesAt: Instant?, val reason: String?)

    fun locked(wallet: WalletInfo?, caps: PlanState): Locked? {
        if (wallet?.unlimited == true) return null
        val free = wallet?.plans?.free ?: caps.free ?: return null
        val plan = wallet?.plans?.plan ?: caps.plan
        if (free.available || (plan != null && !plan.isFree)) return null
        if ((wallet?.balance ?: 0) > 0) return null   // paid or welcome credits still there: they can be spent
        return Locked(free.message, free.resumesAt, free.reason)
    }
}
