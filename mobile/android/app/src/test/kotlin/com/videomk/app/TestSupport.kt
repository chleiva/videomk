package com.videomk.app

import com.videomk.app.core.AppConfig
import com.videomk.app.core.Authorization
import com.videomk.app.core.AuthorizationProviding
import mockwebserver3.MockResponse
import mockwebserver3.MockWebServer
import java.util.Base64

fun fakeJwt(sub: String = "user-1", email: String? = "me@example.com", exp: Long = System.currentTimeMillis() / 1000 + 3600, authTime: Long? = null): String {
    val enc = Base64.getUrlEncoder().withoutPadding()
    val header = enc.encodeToString("""{"alg":"none"}""".toByteArray())
    val payload = enc.encodeToString("""{"sub":"$sub"${if (email != null) ""","email":"$email"""" else ""},"exp":$exp${if (authTime != null) ""","auth_time":$authTime""" else ""}}""".toByteArray())
    return "$header.$payload.sig"
}

fun json(code: Int = 200, body: String): MockResponse = MockResponse.Builder().code(code).addHeader("Content-Type", "application/json").body(body).build()

fun configFor(api: MockWebServer, auth: MockWebServer = api): AppConfig =
    AppConfig(api.url("/prod/"), auth.url("/"), "client-123")

class FixedAuth(private val token: String = "tok-abc", private val user: String = "user-1") : AuthorizationProviding {
    override suspend fun authorization() = Authorization(token, user)
}

