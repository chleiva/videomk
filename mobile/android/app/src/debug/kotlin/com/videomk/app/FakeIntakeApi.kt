package com.videomk.app

import com.videomk.app.core.*
import kotlinx.coroutines.delay
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Debug only: capabilities with every format ready and a request check whose answer is picked by a mode, so each sheet can be looked at without a server. */
class FakeIntakeApi(private val mode: () -> String) : IntakeApi {
    override suspend fun capabilities() = Capabilities(
        aspects = listOf(AspectInfo("16:9", "Landscape", true, false), AspectInfo("9:16", "Vertical", false, true), AspectInfo("1:1", "Square", false, false), AspectInfo("4:5", "Portrait", false, false)),
        resolutions = listOf(ResolutionInfo("1080p", "1080p")), platforms = emptyList(), languages = listOf(LanguageInfo("en", "English"), LanguageInfo("es", "Español")), intake = true,
    )

    private val questions = listOf(
        Question("audience", "Who is this for?", listOf(QuestionOption("kids", "Kids"), QuestionOption("beginners", "Beginners"), QuestionOption("experts", "Experts"), QuestionOption("everyone", "Everyone")), true, "Helps us pick the right words and pace."),
        Question("tone", "What tone?", listOf(QuestionOption("calm", "Calm"), QuestionOption("energetic", "Energetic"), QuestionOption("funny", "Funny"), QuestionOption("serious", "Serious")), true, "How should it feel?"),
        Question("focus", "What should it focus on?", listOf(QuestionOption("honey", "Making honey"), QuestionOption("hive", "Life in the hive"), QuestionOption("pollination", "Pollination"), QuestionOption("facts", "Fun facts")), true, "Pick the part that matters most."),
    )

    override suspend fun brief(request: IntakeRequest): IntakeResult {
        return when (mode()) {
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
