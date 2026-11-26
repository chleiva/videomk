package com.videomk.app

import com.videomk.app.core.ApiClient
import com.videomk.app.core.FeedbackApi
import com.videomk.app.core.FeedbackContext
import com.videomk.app.core.FeedbackDraft
import com.videomk.app.core.FeedbackFlow
import com.videomk.app.core.FeedbackKind
import com.videomk.app.core.FeedbackResult
import com.videomk.app.core.FeedbackRules
import com.videomk.app.core.FeedbackStage
import kotlinx.coroutines.runBlocking
import mockwebserver3.MockWebServer
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test
import java.io.File
import javax.xml.parsers.DocumentBuilderFactory

class FeedbackTest {
    private class Fake(val results: ArrayDeque<FeedbackResult>) : FeedbackApi {
        val sent = mutableListOf<Triple<String, FeedbackKind?, FeedbackContext>>()
        override suspend fun sendFeedback(text: String, kind: FeedbackKind?, context: FeedbackContext): FeedbackResult { sent += Triple(text, kind, context); return results.removeFirst() }
    }

    @Test fun `text rules are 3 to 2000 after trimming`() {
        assertFalse(FeedbackRules.isValid("  ab ")); assertTrue(FeedbackRules.isValid(" abc "))
        assertTrue(FeedbackRules.isValid("x".repeat(2000))); assertFalse(FeedbackRules.isValid("x".repeat(2001)))
        assertEquals(2000, FeedbackRules.clamp("y".repeat(2500)).length)
    }

    @Test fun `a failed send keeps the text and retry works, success clears the draft`() = runBlocking {
        val api = Fake(ArrayDeque(listOf(FeedbackResult.Offline, FeedbackResult.RateLimited, FeedbackResult.Sent)))
        val draft = FeedbackDraft(); val flow = FeedbackFlow(api, draft, FeedbackContext.Settings)
        flow.edit("It is great but slow"); flow.pick(FeedbackKind.Idea)
        flow.send(); assertEquals(FeedbackStage.Failed(FeedbackResult.Offline), flow.stage.value); assertEquals("It is great but slow", draft.text)
        flow.send(); assertEquals(FeedbackStage.Failed(FeedbackResult.RateLimited), flow.stage.value); assertEquals(FeedbackKind.Idea, draft.kind)
        flow.send(); assertEquals(FeedbackStage.Sent, flow.stage.value); assertEquals("", draft.text); assertEquals(null, draft.kind)
        assertEquals(3, api.sent.size); assertEquals(FeedbackContext.Settings, api.sent[0].third)
    }

    @Test fun `too short text is not sent`() = runBlocking {
        val api = Fake(ArrayDeque()); val flow = FeedbackFlow(api, FeedbackDraft(), FeedbackContext.AfterVideo)
        flow.edit("hi"); assertFalse(flow.canSend); flow.send(); assertTrue(api.sent.isEmpty())
    }

    @Test fun `the request matches the contract and statuses map`() = runBlocking {
        val server = MockWebServer(); server.start()
        try {
            repeat(5) { server.enqueue(json(code = listOf(202, 429, 400, 500, 202)[it], body = if (it == 0) """{"ok":true}""" else """{"error":"x"}""")) }
            val api = ApiClient(configFor(server), FixedAuth(), appVersion = "1.2.3", locale = { "es" })
            assertEquals(FeedbackResult.Sent, api.sendFeedback("  Me encanta  ", FeedbackKind.Problem, FeedbackContext.RatingPrompt))
            val req = server.takeRequest()
            assertEquals("/prod/users/user-1/feedback", req.url.encodedPath); assertEquals("POST", req.method)
            assertEquals("Bearer tok-abc", req.headers["Authorization"])
            val body = kotlinx.serialization.json.Json.parseToJsonElement(req.body!!.utf8()).toString()
            assertEquals("""{"text":"Me encanta","kind":"problem","app":"android","version":"1.2.3","locale":"es","context":"rating_prompt"}""", body)
            assertEquals(FeedbackResult.RateLimited, api.sendFeedback("hello", null, FeedbackContext.Settings))
            assertEquals(FeedbackResult.Invalid, api.sendFeedback("hello", null, FeedbackContext.Settings))
            assertEquals(FeedbackResult.Failed, api.sendFeedback("hello", null, FeedbackContext.Settings))
            server.takeRequest(); server.takeRequest(); server.takeRequest()
            assertEquals(FeedbackResult.Sent, api.sendFeedback("hello", null, FeedbackContext.Settings))
            assertFalse(server.takeRequest().body!!.utf8().contains("\"kind\""))   // no chip: no kind field
        } finally { server.close() }
    }

    @Test fun `every feedback and rating string has an English and a Spanish text`() {
        fun names(dir: String): Set<String> {
            val nodes = DocumentBuilderFactory.newInstance().newDocumentBuilder().parse(File("src/main/res/$dir/strings_feedback.xml")).documentElement.getElementsByTagName("string")
            return (0 until nodes.length).map { (nodes.item(it) as org.w3c.dom.Element).getAttribute("name") }.toSet()
        }
        val en = names("values"); val es = names("values-es")
        assertEquals(en, es)
        for (k in listOf("feedback_title", "feedback_intro", "feedback_thanks_body", "rating_ask_title", "rating_rate", "rating_already")) assertTrue(k, k in en)
    }
}
