package com.videomk.app.core

/**
 * "Make another" on a finished video (docs/DESIGN_BAR_2026.md signature 5): the same idea as a Short, in the other language or as a 30-second cut.
 * There is no remix endpoint yet, so a chip only opens Create prefilled (the idea, with one choice changed); nothing is sent and nothing is charged until the
 * person taps Create there. A chip is offered only when it can really do that on this server: no dead buttons.
 */
enum class RemixKind { Short, Spanish, English, Cut30 }

object Remix {
    const val SHORT_PLATFORM = "shorts"
    const val CUT_MINUTES = 0.5

    /** The idea to start from: what the person wrote (known for videos made in this session), else the video's title. Null when neither is a usable description. */
    fun prompt(brief: String?, title: String?): String? = listOfNotNull(brief, title).map { Brief.normalized(it) }.firstOrNull { Brief.isValid(it) }

    /**
     * What can be offered for [video] with the server's [caps], in the app language [appLanguage] ("en" or "es"): a Short when the video is not already tall and the
     * server makes Shorts; the other language when the server lists it; a 30-second cut when the video is clearly longer and the server offers that length.
     */
    fun offers(video: VideoItem, caps: Capabilities, appLanguage: String, hasPrompt: Boolean): List<RemixKind> {
        if (!hasPrompt || video.status != VideoStatus.Complete) return emptyList()
        val out = ArrayList<RemixKind>()
        if (!video.isTall && CreatePlatforms.chip(caps, SHORT_PLATFORM)?.enabled == true) out += RemixKind.Short
        val other = if (appLanguage == "es") RemixKind.English else RemixKind.Spanish
        if (caps.languages.any { it.id == languageOf(other) }) out += other
        if ((video.durationSeconds ?: 0.0) > 45.0 && caps.presets.any { Math.abs(it - CUT_MINUTES) < 1e-9 }) out += RemixKind.Cut30
        return out
    }

    fun languageOf(kind: RemixKind): String? = when (kind) { RemixKind.Spanish -> "es"; RemixKind.English -> "en"; else -> null }

    /** The one choice a chip changes; everything else stays what Create would have chosen. Null when the server cannot do it (the options are then left alone). */
    fun apply(options: CreateOptions, kind: RemixKind, caps: Capabilities): CreateOptions? = when (kind) {
        RemixKind.Short -> CreatePlatforms.chip(caps, SHORT_PLATFORM)?.takeIf { it.enabled }?.let { CreatePlatforms.select(options, it, false, caps.presets) }
        RemixKind.Spanish, RemixKind.English -> languageOf(kind)?.takeIf { l -> caps.languages.any { it.id == l } }?.let { options.copy(language = it) }
        RemixKind.Cut30 -> if (caps.presets.any { Math.abs(it - CUT_MINUTES) < 1e-9 }) DeckOptions.chooseLength(options, CUT_MINUTES) else null
    }
}
