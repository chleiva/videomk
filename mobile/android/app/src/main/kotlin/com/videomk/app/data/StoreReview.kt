package com.videomk.app.data

import android.app.Activity
import android.content.ActivityNotFoundException
import android.content.Intent
import android.net.Uri
import com.google.android.play.core.review.ReviewManagerFactory
import com.google.android.play.core.ktx.launchReview
import com.google.android.play.core.ktx.requestReview
import kotlinx.coroutines.CancellationException

/**
 * "Rate videomk". Uses the Google Play In-App Review API: the rating happens in a Google sheet on top of the app. It is quota limited by Google
 * and deliberately gives no result (the app cannot tell whether the sheet was shown, or whether the person rated), which is why the prompt never
 * reacts to the outcome. When the flow is unavailable (no Play Store, an error, the quota) the Play Store listing opens instead: `market://` first, https as the fallback.
 */
object StoreReview {
    fun listingUris(applicationId: String): List<Uri> = listOf(Uri.parse("market://details?id=$applicationId"), Uri.parse("https://play.google.com/store/apps/details?id=$applicationId"))

    suspend fun rate(activity: Activity, applicationId: String) {
        try {
            val manager = ReviewManagerFactory.create(activity)
            val info = manager.requestReview()
            manager.launchReview(activity, info)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            openListing(activity, applicationId)
        }
    }

    fun openListing(activity: Activity, applicationId: String) {
        for (uri in listingUris(applicationId)) {
            try { activity.startActivity(Intent(Intent.ACTION_VIEW, uri)); return } catch (e: ActivityNotFoundException) { /* try the next one */ } catch (e: Exception) { return }
        }
    }
}
