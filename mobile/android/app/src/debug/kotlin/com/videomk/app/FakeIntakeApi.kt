package com.videomk.app

import com.videomk.app.core.*
import kotlinx.coroutines.delay
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/** Debug only: capabilities with every format ready and a request check whose answer is picked by a mode, so each sheet can be looked at without a server. */
class FakeIntakeApi(private val deck: Boolean = false, private val looksJson: ((String) -> String?)? = null, private val mode: () -> String) : IntakeApi {
    /**
     * `files/fake_looks`: the server's look picker (`looks.look` and `looks.cast`), read from the backend's own capabilities answer (debug assets `looks_en.json` / `looks_es.json`,
     * made by `mobile/ios/scripts/gen_look_fixtures.py`). Its content picks a variant: "plan" (Cartoon needs the Pro plan), "hidden" (this stage has no Whiteboard), "minlen" (Whiteboard needs 30 s). Absent: an older server.
     */
    private fun lookPicker(): LookCaps? {
        val variant = runCatching { java.io.File("/data/data/com.videomk.app/files/fake_looks").takeIf { it.exists() }?.readText()?.trim() }.getOrNull() ?: return null
        val caps = runCatching { LookCaps.fromJson(parseObject(looksJson?.invoke(Txt.localeTag) ?: return null).obj("looks")) }.getOrNull() ?: return null
        return when (variant) {
            "plan" -> caps.copy(options = caps.options.map { if (it.id == "cartoon") it.copy(allowed = false, requiresPlan = "pro") else it })
            "minlen" -> caps.copy(options = caps.options.map { if (it.id == "whiteboard") it.copy(minSeconds = 30.0) else it })
            "hidden" -> caps.copy(options = caps.options.map { if (it.id == "whiteboard") it.copy(available = false) else it })
            else -> caps
        }
    }

    /** The same `files/fake_plan` as the fake backend: "free" and "locked" cap the lengths at 30 s, lock 4K and fix the watermark; "pro" offers the watermark choices. */
    private val planMode: String get() = runCatching { java.io.File("/data/data/com.videomk.app/files/fake_plan").readText().trim() }.getOrDefault("")
    override suspend fun capabilities(): Capabilities {
        val free = planMode == "free" || planMode == "locked"
        return base().copy(
            lookPicker = lookPicker(),
            resolutions = listOf(ResolutionInfo("720p", "720p"), ResolutionInfo("1080p", "1080p"), ResolutionInfo("2160p", "4K", 2, !free && planMode != "pro" && planMode.isNotEmpty() || planMode.isEmpty(), if (planMode.isEmpty()) null else "max")),
            looks = LooksCaps(
                listOf(StyleOption("auto", "Auto", "We choose: photos and footage, with cartoon scenes only where they suit the topic."), StyleOption("cartoon", "Illustrated", "Adds animated cartoon scenes. Good for children's topics and simple ideas."),
                    StyleOption("real", "Real", "Only photos and footage, never cartoon scenes."), StyleOption("whiteboard", "Whiteboard", "Drawn by hand on a board, step by step.")),
                "auto", listOf(BackgroundWish("gas-brand-dark", "Purple 3D gas", "with a purple 3D background"), BackgroundWish("gas-ember-dark", "Warm 3D embers", "with a warm 3D background"), BackgroundWish("none", "Still background", "no moving background")),
            ),
            watermark = if (free || planMode.isEmpty()) WatermarkCaps(true, "The VideoMK watermark is included on this plan.")
                else WatermarkCaps(false, null, listOf(WatermarkChoice("none", "None"), WatermarkChoice("videomk", "videomk"), WatermarkChoice("custom", "Your logo", false, null, "max")),
                    listOf(WatermarkChoice("always", "Always visible", true, "Stays in the corner for the whole video."), WatermarkChoice("moments", "Now and then", true, "Fades in for a few seconds near the start and about every 30 seconds.")), "moments"),
            plans = if (planMode.isEmpty()) PlanState.NONE else PlanState(PlanInfo(if (free) "free" else "pro", if (free) "Free" else "Pro", if (free) 30 else 300), null, "welcome"),
            planMaxSeconds = when { free -> 30; planMode == "pro" -> 300; else -> null }, longerPlan = when { free -> "pro"; planMode == "pro" -> "max"; else -> null },
        )
    }

    private fun base() = Capabilities(
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
        deck = if (deck) DeckCaps(50, 60, listOf("pptx", "pdf")) else null,
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
            "unsupported" -> IntakeResult.NotSupported("This request is outside what VideoMK can make. Try describing the topic in a different way.", "A calm story about a lighthouse keeper")
            "blocked" -> IntakeResult.Blocked("We can't make this video. Try a different idea.")
            "paused" -> IntakeResult.Paused("Creating videos is paused for now.", 3600)
            "slow" -> { delay(4000); IntakeResult.Ok(null) }
            "slowfail" -> { delay(60_000); IntakeResult.Ok(null) }
            else -> IntakeResult.Ok(null)
        }
    }
}
