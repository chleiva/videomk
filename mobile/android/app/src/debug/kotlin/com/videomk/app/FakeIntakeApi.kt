package com.videomk.app

import com.videomk.app.core.*
import kotlinx.coroutines.delay
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Debug only: capabilities with every format ready and a request check whose answer is picked by a mode, so each sheet can be looked at without a server. */
class FakeIntakeApi(private val mode: () -> String) : IntakeApi {
    override suspend fun capabilities() = Capabilities(
        aspects = listOf(AspectInfo("16:9", "Landscape", true, false), AspectInfo("9:16", "Vertical", true, true), AspectInfo("1:1", "Square", true, true), AspectInfo("4:5", "Portrait", true, true)),
        resolutions = listOf(ResolutionInfo("720p", "720p"), ResolutionInfo("1080p", "1080p")),
        platforms = listOf(
            PlatformInfo("youtube", "YouTube", "16:9", "1080p", 3.0, null, emptyList(), "Landscape 16:9 · 1080p · about 3 min"),
            PlatformInfo("shorts", "YouTube Shorts", "9:16", "1080p", 0.75, 3.0, emptyList(), "Vertical 9:16 · 1080p · about 45 s"),
            PlatformInfo("tiktok", "TikTok", "9:16", "1080p", 0.5, 10.0, emptyList(), "Vertical 9:16 · 1080p · about 30 s"),
            PlatformInfo("reels", "Instagram Reels", "9:16", "1080p", 0.5, 3.0, emptyList(), "Vertical 9:16 · 1080p · about 30 s"),
            PlatformInfo("instagram_feed", "Instagram feed", "4:5", "1080p", 0.5, 1.0, listOf("1:1"), "Portrait 4:5 · 1080p · about 30 s"),
            PlatformInfo("linkedin", "LinkedIn", "4:5", "1080p", 1.0, 10.0, listOf("1:1", "16:9"), "Portrait 4:5 · 1080p · about 1 min"),
            PlatformInfo("x", "X", "16:9", "1080p", 0.75, 140.0 / 60.0, emptyList(), "Landscape 16:9 · 1080p · about 45 s"),
            PlatformInfo("other", "Just a video", "16:9", "1080p", 3.0, null, emptyList(), "Landscape 16:9 · 1080p · about 3 min"),
        ),
        languages = listOf(LanguageInfo("en", "English"), LanguageInfo("es", "Español")), minMinutes = 0.25, maxMinutes = 12.0,
        presets = listOf(0.25, 0.5, 0.75, 1.0, 2.0, 3.0, 5.0, 8.0, 12.0), intake = true,
    )

    private val questions = listOf(
        Question("audience", "Who is this for?", listOf(QuestionOption("kids", "Kids"), QuestionOption("beginners", "Beginners"), QuestionOption("experts", "Experts"), QuestionOption("everyone", "Everyone")), true, "Helps us pick the right words and pace."),
        Question("tone", "What tone?", listOf(QuestionOption("calm", "Calm"), QuestionOption("energetic", "Energetic"), QuestionOption("funny", "Funny"), QuestionOption("serious", "Serious")), true, "How should it feel?"),
        Question("focus", "What should it focus on?", listOf(QuestionOption("honey", "Making honey"), QuestionOption("hive", "Life in the hive"), QuestionOption("pollination", "Pollination"), QuestionOption("facts", "Fun facts")), true, "Pick the part that matters most."),
    )

    /** 36-character labels in English and Spanish, the longest the server now lets through, to check that chips never clip. */
    private fun longQuestions(es: Boolean) = if (es) listOf(
        Question("focus", "¿Qué periodo quieres cubrir?", listOf(QuestionOption("a", "Evolución biológica y primeros homínidos"), QuestionOption("b", "Civilizaciones antiguas hasta la edad media"), QuestionOption("c", "Hoy"), QuestionOption("d", "Futuro cercano y tecnología")), true, null),
    ) else listOf(
        Question("focus", "Which period should it cover?", listOf(QuestionOption("a", "Biological evolution and early hominids"), QuestionOption("b", "Ancient civilizations to the middle ages"), QuestionOption("c", "Today"), QuestionOption("d", "Near future and technology")), true, null),
    )

    override suspend fun brief(request: IntakeRequest): IntakeResult {
        return when (val m = mode()) {
            "longlabels", "longlabels_es" -> if (request.answers.isEmpty()) IntakeResult.Questions(longQuestions(m == "longlabels_es")) else IntakeResult.Ok(buildJsonObject { put("summary", if (m == "longlabels_es") "Evolución biológica y primeros homínidos" else "Biological evolution and early hominids") })
            "questions" -> if (request.answers.isEmpty()) IntakeResult.Questions(questions) else IntakeResult.Ok(buildJsonObject { put("summary", "For kids · Calm · Focus: Making honey") })
            "unsupported" -> IntakeResult.NotSupported("This request is outside what videomk can make. Try describing the topic in a different way.", "A calm story about a lighthouse keeper")
            "blocked" -> IntakeResult.Blocked("We can't make this video. Try a different idea.")
            "paused" -> IntakeResult.Paused("Creating videos is paused for now.", 3600)
            "slow" -> { delay(4000); IntakeResult.Ok(null) }
            "slowfail" -> { delay(60_000); IntakeResult.Ok(null) }
            else -> IntakeResult.Ok(null)
        }
    }
}
