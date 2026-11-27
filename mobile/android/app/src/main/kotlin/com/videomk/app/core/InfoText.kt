package com.videomk.app.core

/**
 * The server's description of a finished video is one text: what the video is about, then (after a blank line) the picture and footage credits and the sources.
 * The Info sheet shows them as two groups; the split is by meaning, not position: a paragraph that names a source (a link, "Photo by", "Video by", "Source",
 * "Credits", and the Spanish forms) belongs to the credits, and so does everything after the first such paragraph.
 */
object InfoText {
    data class Parts(val about: String, val credits: String)

    private val markers = listOf("http://", "https://", "photo by", "video by", "photos by", "videos by", "footage by", "source", "credits", "foto de", "fotos de", "video de", "videos de", "fuente", "créditos", "pexels", "unsplash", "wikipedia")

    fun split(text: String): Parts {
        val paragraphs = text.replace("\r\n", "\n").split(Regex("\n\\s*\n")).map { it.trim() }.filter { it.isNotEmpty() }
        val first = paragraphs.indexOfFirst { p -> val l = p.lowercase(); markers.any { l.contains(it) } }
        if (first < 0) return Parts(paragraphs.joinToString("\n\n"), "")
        return Parts(paragraphs.take(first).joinToString("\n\n"), paragraphs.drop(first).joinToString("\n\n"))
    }
}
