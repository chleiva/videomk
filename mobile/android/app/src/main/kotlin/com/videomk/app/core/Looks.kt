package com.videomk.app.core

import com.videomk.app.R
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull

/*
 * The chosen, enforced look of a video (docs/CREATE_API.md, "Video look (chosen and enforced)"): what the server offers (`capabilities.looks.look` and `.cast`),
 * what the person picked (`look`, `cast`, `extras`), the rules of the picker, and what the answers say was applied. Everything is read leniently: a missing or
 * malformed part is simply absent, and without `looks.look` the app keeps the behaviour it had before the picker existed. Same rules as the iPhone app
 * (`LookChoice.swift`); no Android classes, so all of it runs in plain JVM tests.
 */

/** A switch a look allows (`extras[]`: today the board). The label is the server's. */
data class LookExtra(val id: String, val label: String, val note: String? = null, val available: Boolean = true)

/** One tile of the picker. Labels, notes and the picture are the server's, never hard-coded. */
data class LookOption(
    val id: String, val label: String, val note: String? = null,
    /** A JPEG data URI (320x180). */
    val preview: String? = null,
    /** This stage has the look; false: the tile is hidden. */
    val available: Boolean = true,
    /** This account's plan may use it; false: shown in place, dimmed, with the plan's name. */
    val allowed: Boolean = true, val requiresPlan: String? = null,
    val withPhotos: Boolean = true, val withDeck: Boolean = true,
    val minSeconds: Double = 0.0, val aspects: List<String> = emptyList(), val bestAspects: List<String> = emptyList(),
    /** true: Create shows the Characters pill. */
    val cast: Boolean = false, val extras: List<LookExtra> = emptyList(),
) {
    val isAuto: Boolean get() = id == LookChoice.AUTO
}

data class CastMember(val id: String, val name: String, val role: String? = null, val kind: String = "person", val topic: String? = null, /** A PNG data URI (112 px). */ val thumbnail: String? = null)

data class CastCaps(
    val min: Int = 1, val max: Int = 3, val available: Boolean = true, val autoLabel: String? = null, val autoNote: String? = null,
    val conversationFrom: Int = 2, val conversationMinSeconds: Double = 0.0, val conversationNote: String? = null, val members: List<CastMember> = emptyList(),
) {
    fun member(id: String): CastMember? = members.firstOrNull { it.id == id }

    /** The members in the server's order, people first, then animals, then anything else: one group per kind. */
    val grouped: List<CastMember> get() {
        val order = members.map { it.kind }.distinct()
        fun rank(k: String) = when (k) { "person" -> 0; "animal" -> 1; else -> 2 }
        return order.sortedWith(compareBy({ rank(it) }, { order.indexOf(it) })).flatMap { k -> members.filter { it.kind == k } }
    }
}

/** `capabilities.looks.look` and `.cast`. Null from a server without the picker. */
data class LookCaps(val options: List<LookOption>, val cast: CastCaps? = null) {
    fun option(id: String): LookOption? = options.firstOrNull { it.id == id }

    companion object {
        /** From the `looks` object of capabilities. Null when `looks.look` is absent or lists nothing usable: the app then behaves as before the picker. */
        fun fromJson(looks: JsonObject?): LookCaps? {
            val raw = looks?.obj("look")?.arr("options") ?: return null
            val seen = HashSet<String>()
            val options = raw.mapNotNull { e ->
                val o = e.asObject() ?: return@mapNotNull null
                val id = o.word("id")?.takeIf { seen.add(it) } ?: return@mapNotNull null
                val extras = o.arr("extras")?.mapNotNull { x -> x.asObject()?.let { xo -> xo.word("id")?.let { xid -> LookExtra(xid, xo.line("label") ?: xid, xo.line("note"), xo.bool("available") ?: true) } } } ?: emptyList()
                LookOption(
                    id, o.line("label") ?: id, o.line("note"), o.dataUri("preview"), o.bool("available") ?: true, o.bool("allowed") ?: true, o.line("requires_plan"),
                    o.bool("with_photos") ?: true, o.bool("with_deck") ?: true, o.seconds("min_seconds") ?: 0.0, o.words("aspects"), o.words("best_aspects"), o.bool("cast") ?: false, extras,
                )
            }
            if (options.isEmpty()) return null
            val cast = looks.obj("cast")?.let { c ->
                val ids = HashSet<String>()
                val members = c.arr("members")?.mapNotNull { m ->
                    val x = m.asObject() ?: return@mapNotNull null
                    val id = x.word("id")?.takeIf { it != LookChoice.AUTO && ids.add(it) } ?: return@mapNotNull null
                    CastMember(id, x.line("name") ?: id, x.line("role"), x.word("kind") ?: "person", x.line("topic"), x.dataUri("thumbnail"))
                } ?: emptyList()
                val auto = c.obj("auto"); val talk = c.obj("conversation")
                val top = maxOf(1, c.count("max") ?: 3)
                CastCaps(
                    maxOf(1, minOf(c.count("min") ?: 1, top)), top, c.bool("available") ?: true, auto?.line("label"), auto?.line("note"),
                    maxOf(2, talk?.count("from") ?: 2), talk?.seconds("min_seconds") ?: 0.0, talk?.line("note"), members,
                )
            }
            return LookCaps(options, cast)
        }
    }
}

// lenient readers: anything of the wrong type or shape is simply absent

/** A short identifier ("cartoon", "16:9"): a non-empty string without spaces. */
private fun JsonElement?.asWord(): String? = (this as? JsonPrimitive)?.takeIf { it.isString }?.content?.trim()?.takeIf { it.isNotEmpty() && it.length <= 64 && !it.contains(' ') }
private fun JsonObject.word(key: String): String? = this[key].asWord()
private fun JsonObject.words(key: String): List<String> = (this[key] as? JsonArray)?.mapNotNull { it.asWord() } ?: emptyList()
/** A piece of text to show: trimmed, never empty. */
private fun JsonObject.line(key: String): String? = str(key)?.trim()?.takeIf { it.isNotEmpty() }
private fun JsonObject.seconds(key: String): Double? = (this[key] as? JsonPrimitive)?.let { if (it.isString) it.content.toDoubleOrNull() else it.doubleOrNull }?.takeIf { it.isFinite() && it >= 0 }
private fun JsonObject.count(key: String): Int? = (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.let { it.intOrNull ?: it.doubleOrNull?.toInt() }
/** A picture sent inline; anything that is not an image data URI is no picture. */
private fun JsonObject.dataUri(key: String): String? = str(key)?.takeIf { it.startsWith("data:image/") && it.contains(";base64,") }

object DataUri {
    /** The bytes of `data:image/...;base64,...`; null for anything else. */
    fun bytes(uri: String?): ByteArray? {
        uri ?: return null
        if (!uri.startsWith("data:")) return null
        val comma = uri.indexOf(',').takeIf { it >= 0 } ?: return null
        return runCatching { java.util.Base64.getMimeDecoder().decode(uri.substring(comma + 1)) }.getOrNull()?.takeIf { it.isNotEmpty() }
    }
}

/** What the person picked. `auto` with no cast and no extras sends nothing at all, so a server from before the contract is unaffected. */
data class LookChoice(val look: String = AUTO, /** Empty = "auto". */ val cast: List<String> = emptyList(), val extras: List<String> = emptyList()) {
    val isAuto: Boolean get() = look == AUTO

    /** The request fields, exactly as the contract writes them (the body of `generate`, and `options` of `brief`): nothing for Auto. */
    val requestLook: String? get() = look.takeIf { it != AUTO }
    val requestCast: List<String>? get() = cast.takeIf { look != AUTO && it.isNotEmpty() }
    val requestExtras: List<String>? get() = extras.takeIf { look != AUTO && it.isNotEmpty() }

    fun putInto(b: kotlinx.serialization.json.JsonObjectBuilder) {
        requestLook?.let { b.put("look", JsonPrimitive(it)) }
        requestCast?.let { b.put("cast", JsonArray(it.map { id -> JsonPrimitive(id) })) }
        requestExtras?.let { b.put("extras", JsonArray(it.map { id -> JsonPrimitive(id) })) }
    }

    companion object { const val AUTO = "auto" }
}

/** The rules of the picker. Pure, so every one of them is unit-tested. */
object LookRules {
    /** What is attached decides which looks can be made (the person's own photos or slides are the pictures of the video). */
    data class Attached(val photos: Boolean = false, val deck: Boolean = false) {
        val any: Boolean get() = photos || deck
        companion object { val NOTHING = Attached() }
    }

    /** Why a tile is shown but cannot be chosen: the plan does not include it, or it is not made from the attached photos or slides. */
    enum class Block { Plan, Photos, Deck }
    data class Tile(val option: LookOption, val blocked: Block?) {
        val locked: Boolean get() = blocked != null
        val id: String get() = option.id
    }

    enum class Reset { Photos, Deck, Plan, Gone }
    data class Normalized(val choice: LookChoice, val reset: Reset?)

    /**
     * At most four tiles in the server's order, always in the same places. Hidden: only a look this stage does not have. A look that is not made from what is
     * attached, or that the plan does not include, stays in place, dimmed, with its reason (one treatment for "you cannot have this").
     */
    fun tiles(caps: LookCaps, attached: Attached = Attached.NOTHING): List<Tile> = caps.options.filter { it.available }.take(4).map { o ->
        Tile(o, if (attached.photos && !o.withPhotos) Block.Photos else if (attached.deck && !o.withDeck) Block.Deck else if (!o.allowed) Block.Plan else null)
    }

    /** Keeps a choice inside what can be made now. [Normalized.reset] says why when the look itself had to go back to Auto. */
    fun normalized(choice: LookChoice, caps: LookCaps?, attached: Attached = Attached.NOTHING): Normalized {
        caps ?: return Normalized(LookChoice(), null)                       // an older server: nothing is sent
        if (choice.look == LookChoice.AUTO) return Normalized(LookChoice(), null)
        val o = caps.option(choice.look)?.takeIf { it.available } ?: return Normalized(LookChoice(), Reset.Gone)
        if (attached.photos && !o.withPhotos) return Normalized(LookChoice(), Reset.Photos)
        if (attached.deck && !o.withDeck) return Normalized(LookChoice(), Reset.Deck)
        if (!o.allowed) return Normalized(LookChoice(), Reset.Plan)
        val cast = caps.cast?.takeIf { o.cast && it.available }
        val usable = o.extras.filter { it.available }.map { it.id }.toSet()
        return Normalized(choice.copy(cast = cast?.let { c -> choice.cast.filter { c.member(it) != null }.distinct().take(c.max) } ?: emptyList(), extras = choice.extras.filter { it in usable }.distinct()), null)
    }

    /** A tap on a tile. Locked and hidden tiles change nothing. Choosing another look drops the cast and the extras of the one before. */
    fun select(id: String, choice: LookChoice, caps: LookCaps, attached: Attached = Attached.NOTHING): LookChoice {
        if (tiles(caps, attached).none { it.id == id && !it.locked }) return choice
        return if (id == choice.look) choice else LookChoice(id)
    }

    enum class CastTap { Added, Removed, Full }

    /** A tap on a face: chooses it, or lets it go; a fourth is refused ([CastTap.Full]: the picker dims those faces, so this is only the safety net). */
    fun toggle(member: String, choice: LookChoice, caps: LookCaps): Pair<LookChoice, CastTap> {
        val cast = caps.cast?.takeIf { it.member(member) != null } ?: return choice to CastTap.Full
        if (member in choice.cast) return choice.copy(cast = choice.cast - member) to CastTap.Removed
        if (choice.cast.size >= cast.max) return choice to CastTap.Full
        return choice.copy(cast = choice.cast + member) to CastTap.Added
    }

    fun setExtra(id: String, on: Boolean, choice: LookChoice): LookChoice = choice.copy(extras = (choice.extras - id).let { if (on) it + id else it })

    /** Two or three chosen: they talk to each other. */
    fun isConversation(choice: LookChoice, caps: LookCaps?): Boolean = caps?.cast?.let { choice.cast.size >= it.conversationFrom } ?: false

    /** The limit is reached: the faces that are not chosen are dimmed and do nothing. */
    fun castIsFull(choice: LookChoice, caps: LookCaps?): Boolean = caps?.cast?.let { choice.cast.size >= it.max } ?: false

    /** The chosen look has characters to choose (or a switch of its own): Create shows the Characters pill. */
    fun hasCast(choice: LookChoice, caps: LookCaps?): Boolean {
        val o = caps?.option(choice.look)?.takeIf { !it.isAuto } ?: return false
        return (o.cast && caps?.cast?.let { it.available && it.members.isNotEmpty() } == true) || o.extras.any { it.available }
    }

    /** The shortest video this choice works in, in seconds. */
    fun minSeconds(choice: LookChoice, caps: LookCaps?): Double {
        val o = caps?.option(choice.look) ?: return 0.0
        return maxOf(o.minSeconds, if (isConversation(choice, caps)) caps?.cast?.conversationMinSeconds ?: 0.0 else 0.0)
    }

    /** [minutes]: the length to use (the shortest preset the choice works in). [conversation]: it is the conversation, not the look, that needs it. */
    data class LengthNudge(val minutes: Double, val needSeconds: Double, val conversation: Boolean)

    /** The chosen length is shorter than the choice needs: the preset to move to. Null when the length is fine or no preset is long enough. */
    fun lengthNudge(choice: LookChoice, caps: LookCaps?, minutes: Double, presets: List<Double>): LengthNudge? {
        val need = minSeconds(choice, caps)
        if (need <= 0 || minutes * 60 + 1e-6 >= need) return null
        val fix = presets.sorted().firstOrNull { it * 60 + 1e-6 >= need } ?: return null
        return LengthNudge(fix, need, isConversation(choice, caps) && (caps?.option(choice.look)?.minSeconds ?: 0.0) < need)
    }

    // words

    /** The names of the chosen characters, in the order they were chosen. */
    fun castNames(ids: List<String>, caps: LookCaps?): List<String> = ids.map { caps?.cast?.member(it)?.name ?: it }

    /** "Fox", "Fox and Bruno", "Fox, Bruno and Mika" (Spanish: "y", and "e" before a name that starts with the sound i). */
    fun list(names: List<String>): String {
        if (names.isEmpty()) return ""
        if (names.size == 1) return names[0]
        val e = Txt.localeTag == "es" && names.last().lowercase(Txt.locale).let { it.startsWith("i") || it.startsWith("í") || it.startsWith("hi") || it.startsWith("hí") }
        val head = names.dropLast(1)
        return if (head.size == 1) Txt.s(if (e) R.string.looks_list_two_e else R.string.looks_list_two, head[0], names.last())
        else Txt.s(if (e) R.string.looks_list_more_e else R.string.looks_list_more, head.joinToString(", "), names.last())
    }

    /** What the pill says: the look only ("Auto", "Whiteboard", "Cartoon"). The cast is shown as faces, never as names in the pill. */
    fun pillLabel(choice: LookChoice, caps: LookCaps?): String = caps?.option(choice.look)?.takeIf { !it.isAuto }?.label ?: caps?.option(LookChoice.AUTO)?.label ?: Txt.s(R.string.create_look_auto)

    /** The one line under the faces: "We pick for you. Or choose up to 3." (the server's own sentence when it sends one), "Fox presents.", "Fox and Bruno talk it through." */
    fun castLine(choice: LookChoice, caps: LookCaps?): String {
        val names = castNames(choice.cast, caps)
        return when (names.size) {
            0 -> caps?.cast?.autoNote ?: Txt.s(R.string.looks_cast_none, caps?.cast?.max ?: 3)
            1 -> Txt.s(R.string.looks_cast_one, names[0])
            else -> Txt.s(R.string.looks_cast_talk, list(names))
        }
    }

    /** What TalkBack says for the Characters pill: "Auto" or the names, then the switches that are on. */
    fun castSpoken(choice: LookChoice, caps: LookCaps?): String {
        val names = castNames(choice.cast, caps)
        val extras = choice.extras.mapNotNull { id -> caps?.option(choice.look)?.extras?.firstOrNull { it.id == id }?.label }
        return (listOf(if (names.isEmpty()) caps?.cast?.autoLabel ?: Txt.s(R.string.create_look_auto) else list(names)) + extras).joinToString(", ")
    }

    /** One line saying why the look went back to Auto ("Look set to Auto. Cartoon can't use your photos."). */
    fun resetLine(reason: Reset, was: String): String = Txt.s(when (reason) { Reset.Photos -> R.string.looks_reset_photos; Reset.Deck -> R.string.looks_reset_deck; Reset.Plan, Reset.Gone -> R.string.looks_reset_gone }, was)

    /** Why a dimmed tile cannot be chosen, in the place of its note: "Pro plan", "Not with photos", "Not with slides". */
    fun reason(tile: Tile): String? = when (tile.blocked) {
        Block.Plan -> tile.option.requiresPlan?.let { Txt.s(R.string.looks_plan, it.replaceFirstChar { c -> c.uppercase(Txt.locale) }) } ?: Txt.s(R.string.looks_plan_none)
        Block.Photos -> Txt.s(R.string.looks_no_photos)
        Block.Deck -> Txt.s(R.string.looks_no_deck)
        null -> null
    }

    /** The server's note as one line without its full stop (an older server still sends sentences). */
    fun note(o: LookOption): String? = o.note?.trimEnd('.', ' ')?.takeIf { it.isNotEmpty() }

    /** "Length changed to 30 s. A conversation needs 20 s or more." */
    fun movedLine(nudge: LengthNudge, choice: LookChoice, caps: LookCaps?): String {
        val name = if (nudge.conversation) null else caps?.option(choice.look)?.label
        val need = Lengths.short(nudge.needSeconds / 60)
        return if (name != null) Txt.s(R.string.looks_length_moved_look, Lengths.short(nudge.minutes), name, need) else Txt.s(R.string.looks_length_moved_talk, Lengths.short(nudge.minutes), need)
    }

    /** "A conversation needs 20 s." (the length was shortened after the choice: Create offers the way back). */
    fun needsLine(nudge: LengthNudge, choice: LookChoice, caps: LookCaps?): String {
        val name = if (nudge.conversation) null else caps?.option(choice.look)?.label
        val need = Lengths.short(nudge.needSeconds / 60)
        return if (name != null) Txt.s(R.string.looks_needs_look, name, need) else Txt.s(R.string.looks_needs_talk, need)
    }
}

/** What an answer (`brief`, the 202 of `generate`) or the video record says about the look: what was asked, what the video gets, and why. */
data class AppliedLook(
    val chosen: String? = null, val applied: String? = null,
    /** Empty: none, or "auto". */
    val cast: List<String> = emptyList(), val extras: List<String> = emptyList(),
    /** not_available | own_photos | deck | too_short */
    val reason: String? = null,
    /** The video record: one sentence on why this look. */
    val why: String? = null,
    /** The video record: the director chose it. */
    val byAuto: Boolean = false,
) {
    /** "Whiteboard", "Cartoon · Fox + Bruno": the server's own label when the capabilities list the look, else our word for the known looks. Null for nothing to show. */
    fun title(caps: LookCaps?): String? {
        val id = (applied ?: chosen)?.takeIf { it != LookChoice.AUTO } ?: return null
        val name = caps?.option(id)?.label ?: when (id) { "real" -> Txt.s(R.string.looks_name_real); "whiteboard" -> Txt.s(R.string.looks_name_whiteboard); "cartoon", "presenters" -> Txt.s(R.string.looks_name_cartoon); else -> return null }
        val names = LookRules.castNames(cast, caps)
        return if (names.isEmpty()) name else "$name · ${names.joinToString(" + ")}"
    }

    /** The line of the Info sheet: the title, and "chosen for you" when the director picked it. */
    fun infoLine(caps: LookCaps?): String? = title(caps)?.let { if (byAuto) Txt.s(R.string.looks_chosen_for_you, it) else it }

    companion object {
        fun fromJson(o: JsonObject?): AppliedLook? {
            o ?: return null
            val applied = o.word("applied"); val chosen = o.word("chosen")
            if (applied == null && chosen == null) return null
            val by = o.word("by")
            return AppliedLook(chosen, applied, o.words("cast"), o.words("extras"), o.word("reason"), o.line("why"), by == "auto" || (o["by"] == null && chosen == LookChoice.AUTO))
        }
    }
}

/** The 202 of `generate`: the video, and (optional) what look it gets and one sentence when the look had to be adapted. */
data class StartedVideo(val videoId: String, val look: AppliedLook? = null, val note: String? = null) {
    companion object {
        /** Throws only when there is no `video_id`: a malformed `look` or `note` never fails the start. */
        fun fromJson(o: JsonObject): StartedVideo = StartedVideo(o.requireString("video_id"), AppliedLook.fromJson(o.obj("look")), o.line("note"))
    }
}
