package com.videomk.app.core

import okhttp3.HttpUrl
import okhttp3.HttpUrl.Companion.toHttpUrlOrNull

/** Where the app talks to. Values come from BuildConfig (set per build type), never from code. */
data class AppConfig(
    val apiBase: HttpUrl,
    val authDomain: HttpUrl,
    val clientId: String,
    val redirectUri: String = "com.videomk.app://auth/callback",
) {
    val callbackScheme: String get() = redirectUri.substringBefore("://")
    /** The registered logout URL of the app client (the hosted-UI /logout returns here). Same scheme and host as the sign-in redirect. */
    val signOutUri: String get() = redirectUri.substringBeforeLast('/') + "/signout"

    companion object {
        /** Null when the build has no server address (the production backend is not deployed yet): the app then shows "Not configured". */
        fun from(apiBase: String, authDomain: String, clientId: String, redirectUri: String = "com.videomk.app://auth/callback"): AppConfig? {
            val api = apiBase.takeIf { it.isNotBlank() }?.toHttpUrlOrNull() ?: return null
            val auth = authDomain.takeIf { it.isNotBlank() }?.toHttpUrlOrNull() ?: return null
            if (clientId.isBlank()) return null
            return AppConfig(api, auth, clientId, redirectUri)
        }
    }
}
