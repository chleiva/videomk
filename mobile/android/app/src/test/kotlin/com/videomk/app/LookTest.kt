package com.videomk.app

import com.videomk.app.core.*
import kotlinx.coroutines.runBlocking
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import mockwebserver3.MockWebServer
import org.junit.Assert.*
import org.junit.Test
import java.io.File

/**
 * The chosen look (docs/CREATE_API.md "Video look (chosen and enforced)"): decoding of `looks.look` and `looks.cast` (present, absent, partial, the backend's own
 * answer), the request fields, and every rule of the picker. The fixture is the backend's capabilities answer (`mobile/ios/scripts/gen_look_fixtures.py`), the same
 * file the debug build's fake server reads.
 */
class LookTest {
    private fun obj(text: String): JsonObject = Json.parseToJsonElement(text).jsonObject
    private fun caps(text: String): LookCaps? = LookCaps.fromJson(obj(text))
    private fun fixture(tag: String = "en"): LookCaps = LookCaps.fromJson(obj(File("src/debug/assets/looks_$tag.json").readText()).jsonObject["looks"]!!.jsonObject)!!

    private val contract = """{
      "look": {"param": "look", "default": "auto", "enforced": true, "options": [
        {"id": "auto", "label": "Auto", "note": "Picked for your topic", "preview": "data:image/jpeg;base64,AAAA", "available": true, "allowed": true, "requires_plan": null, "with_photos": true, "with_deck": true, "min_seconds": 15, "aspects": ["16:9", "9:16"], "best_aspects": ["16:9"], "cast": false, "extras": []},
        {"id": "real", "label": "Real", "note": "Photos and footage", "with_photos": true, "with_deck": true, "cast": false, "extras": []},
        {"id": "whiteboard", "label": "Whiteboard", "note": "Drawn by hand", "with_photos": false, "with_deck": false, "best_aspects": ["16:9", "1:1"], "cast": false, "extras": []},
        {"id": "cartoon", "label": "Cartoon", "note": "Characters explain it", "with_photos": false, "with_deck": false, "min_seconds": 15, "cast": true,
         "extras": [{"id": "board", "label": "Characters explain at a board", "note": "A board beside them is drawn by hand as they speak.", "available": true}]}]},
      "cast": {"param": "cast", "default": "auto", "min": 1, "max": 3, "available": true,
        "auto": {"id": "auto", "label": "Auto", "note": "We pick for you. Or choose up to 3."},
        "conversation": {"from": 2, "min_seconds": 20, "note": "They talk it through."},
        "members": [{"id": "ines", "name": "Inés", "role": "Teacher", "kind": "person", "topic": "Learning", "thumbnail": "data:image/png;base64,AAAA"},
                    {"id": "fox", "name": "Fox", "role": "Guide for children", "kind": "animal", "topic": "For children"},
                    {"id": "bear", "name": "Bruno", "kind": "animal"}, {"id": "cat", "name": "Mika", "kind": "animal"}, {"id": "david", "name": "David", "kind": "person"}]}
    }"""
    private val looks = caps(contract)!!
    private val presets = listOf(0.25, 0.5, 0.75, 1.0, 2.0, 3.0)

    // decoding

    @Test fun `decodes the contract`() {
        assertEquals(listOf("auto", "real", "whiteboard", "cartoon"), looks.options.map { it.id })
        val auto = looks.option("auto")!!
        assertTrue(auto.isAuto); assertEquals("Picked for your topic", auto.note); assertEquals("data:image/jpeg;base64,AAAA", auto.preview)
        assertEquals(15.0, auto.minSeconds, 0.0); assertEquals(listOf("16:9", "9:16"), auto.aspects); assertNull(auto.requiresPlan)
        val wb = looks.option("whiteboard")!!
        assertFalse(wb.withPhotos); assertFalse(wb.withDeck); assertEquals(listOf("16:9", "1:1"), wb.bestAspects)
        val cartoon = looks.option("cartoon")!!
        assertTrue(cartoon.cast); assertEquals(listOf(LookExtra("board", "Characters explain at a board", "A board beside them is drawn by hand as they speak.", true)), cartoon.extras)
        val cast = looks.cast!!
        assertEquals(1, cast.min); assertEquals(3, cast.max); assertEquals(2, cast.conversationFrom); assertEquals(20.0, cast.conversationMinSeconds, 0.0)
        assertEquals("We pick for you. Or choose up to 3.", cast.autoNote); assertEquals("They talk it through.", cast.conversationNote)
        assertEquals("Inés", cast.member("ines")!!.name); assertEquals("Guide for children", cast.member("fox")!!.role)
        // people first, then animals, each in the server's order
        assertEquals(listOf("ines", "david", "fox", "bear", "cat"), cast.grouped.map { it.id })
    }

    @Test fun `absent means the app behaves as before`() {
        assertNull(LookCaps.fromJson(null))
        assertNull(caps("""{}"""))
        assertNull(caps("""{"style": {"options": [{"id": "auto", "label": "Auto"}]}}"""))
        assertNull(caps("""{"look": {"options": []}}"""))
        assertNull(caps("""{"look": "cartoon"}"""))
        // the whole capabilities answer: the older style object alone gives no picker, and nothing else changes
        val c = Capabilities.fromJson(obj("""{"aspects":[{"id":"16:9","ready":true}],"resolutions":[{"id":"1080p"}],"looks":{"style":{"options":[{"id":"auto","label":"Auto"},{"id":"real","label":"Real"}]}}}"""))
        assertNull(c.lookPicker); assertNotNull(c.looks)
        assertEquals(LookChoice(), LookRules.normalized(LookChoice("cartoon", listOf("fox")), null).choice)
        assertFalse(LookRules.hasCast(LookChoice("cartoon"), null))
    }

    @Test fun `partial and malformed answers are read leniently`() {
        val c = caps("""{"look": {"options": [
            {"id": "auto"}, {"label": "No id"}, 7, {"id": "auto", "label": "Twice"}, {"id": "has space"},
            {"id": "cartoon", "label": "  ", "note": 5, "preview": "http://example.com/x.jpg", "min_seconds": "20", "aspects": "16:9", "cast": "yes", "extras": [{"label": "x"}, {"id": "board"}]}]},
          "cast": {"max": 0, "min": 9, "members": [{"id": "auto", "name": "Auto"}, {"id": "fox"}, {"id": "fox", "name": "Again"}, "x"], "conversation": {"from": 1}}}""")!!
        assertEquals(listOf("auto", "cartoon"), c.options.map { it.id })
        val cartoon = c.option("cartoon")!!
        assertEquals("cartoon", cartoon.label); assertNull(cartoon.note); assertNull(cartoon.preview); assertEquals(20.0, cartoon.minSeconds, 0.0)
        assertTrue(cartoon.available); assertTrue(cartoon.allowed); assertTrue(cartoon.withPhotos); assertFalse(cartoon.cast); assertEquals(emptyList<String>(), cartoon.aspects)
        assertEquals(listOf(LookExtra("board", "board")), cartoon.extras)
        val cast = c.cast!!
        assertEquals(1, cast.max); assertEquals(1, cast.min); assertEquals(2, cast.conversationFrom)
        assertEquals(listOf(CastMember("fox", "fox")), cast.members)      // "auto" is never a face, a repeated id is read once
        assertNull(caps("""{"look": {"options": [{"id": "real"}]}}""")!!.cast)
    }

    @Test fun `the backend's own answer decodes in both languages`() {
        for (tag in listOf("en", "es")) {
            val f = fixture(tag)
            assertEquals(listOf("auto", "real", "whiteboard", "cartoon"), f.options.map { it.id })
            for (o in f.options) {
                assertTrue("${o.id} has a picture", DataUri.bytes(o.preview)!!.size > 1000)
                assertTrue("${o.id}: the note is one short line without a full stop", o.note!!.length <= 24 && !o.note!!.endsWith("."))
            }
            assertEquals(10, f.cast!!.members.size); assertEquals(3, f.cast!!.max)
            assertTrue(f.cast!!.members.all { DataUri.bytes(it.thumbnail)!!.size > 500 })
            assertEquals(listOf("person", "person", "person", "person", "animal", "animal", "animal", "animal", "animal", "animal"), f.cast!!.grouped.map { it.kind })
            assertTrue(f.option("cartoon")!!.cast); assertEquals("board", f.option("cartoon")!!.extras.single().id)
            assertEquals(4, LookRules.tiles(f).size)
        }
        assertEquals(listOf("Auto", "Real", "Pizarra", "Animado"), fixture("es").options.map { it.label })
        assertEquals("Los personajes explican en una pizarra", fixture("es").option("cartoon")!!.extras.single().label)
        assertEquals("Bruno", fixture().cast!!.member("bear")!!.name)
    }

    @Test fun `a data uri is bytes and anything else is nothing`() {
        assertArrayEquals(byteArrayOf(1, 2, 3), DataUri.bytes("data:image/png;base64,AQID"))
        assertNull(DataUri.bytes(null)); assertNull(DataUri.bytes("https://example.com/a.png")); assertNull(DataUri.bytes("data:image/png;base64,"))
    }

    // the request

    private fun fields(c: LookChoice): JsonObject = kotlinx.serialization.json.buildJsonObject { c.putInto(this) }

    @Test fun `auto sends nothing`() {
        assertEquals(0, fields(LookChoice()).size)
        assertEquals(0, fields(LookChoice("auto", listOf("fox"), listOf("board"))).size)
        val body = IntakeRequest("How bees make honey", CreateOptions(), 0).toJson()["options"]!!.jsonObject
        assertFalse(body.containsKey("look")); assertFalse(body.containsKey("cast")); assertFalse(body.containsKey("extras"))
    }

    @Test fun `a chosen look is sent as the contract says`() {
        assertEquals("""{"look":"whiteboard"}""", fields(LookChoice("whiteboard")).toString())
        assertEquals("""{"look":"cartoon","cast":["fox"]}""", fields(LookChoice("cartoon", listOf("fox"))).toString())      // one id is still a list
        assertEquals("""{"look":"cartoon","cast":["fox","bear"],"extras":["board"]}""", fields(LookChoice("cartoon", listOf("fox", "bear"), listOf("board"))).toString())
        val o = IntakeRequest("How bees make honey", CreateOptions(style = "real", lookChoice = LookChoice("cartoon", listOf("fox", "bear"))), 0).toJson()["options"]!!.jsonObject
        assertEquals("cartoon", o["look"]!!.jsonPrimitive.content); assertEquals(listOf("fox", "bear"), o["cast"]!!.jsonArray.map { it.jsonPrimitive.content })
        assertFalse("a chosen look replaces the older style wish", o.containsKey("style"))
    }

    @Test fun `generate sends the chosen look and reads what was applied`() = runBlocking {
        val server = MockWebServer().apply { start() }
        try {
            val api = ApiClient(configFor(server), FixedAuth())
            server.enqueue(json(202, """{"message":"workflow started","video_id":"v-9","look":{"chosen":"cartoon","applied":"cartoon","enforced":true,"recipe":"conversation_board","cast":["fox","bear"],"extras":["board"],"reason":null}}"""))
            val started = api.startVideo("How bees make honey, explained for kids", "r-1", CreateOptions(minutes = 1.0, lookChoice = LookChoice("cartoon", listOf("fox", "bear"), listOf("board"))))
            assertEquals(StartedVideo("v-9", AppliedLook("cartoon", "cartoon", listOf("fox", "bear"), listOf("board"))), started)
            val body = Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
            assertEquals("cartoon", body["look"]!!.jsonPrimitive.content)
            assertEquals(listOf("fox", "bear"), body["cast"]!!.jsonArray.map { it.jsonPrimitive.content })
            assertEquals(listOf("board"), body["extras"]!!.jsonArray.map { it.jsonPrimitive.content })
            assertFalse(body.containsKey("style")); assertFalse(body.containsKey("presenter"))

            // Auto: no new key at all, and an answer without `look` is fine (an older server)
            server.enqueue(json(202, """{"video_id":"v-10"}"""))
            assertEquals(StartedVideo("v-10"), api.startVideo("How bees make honey, explained for kids", "r-2", CreateOptions(minutes = 1.0)))
            val plain = Json.parseToJsonElement(server.takeRequest().body!!.utf8()).jsonObject
            assertTrue(listOf("look", "cast", "extras").none { plain.containsKey(it) })
            assertEquals("v-10", run { server.enqueue(json(202, """{"video_id":"v-10"}""")); api.startGeneration("How bees make honey, explained for kids", "r-3") })
        } finally { server.close() }
    }

    @Test fun `the start answer is read leniently`() {
        val s = StartedVideo.fromJson(obj("""{"video_id":"v1","note":" Made from your photos: the Cartoon look is not used with your own photos. ","look":{"chosen":"cartoon","applied":"real","enforced":false,"recipe":null,"extras":[],"reason":"own_photos"}}"""))
        assertEquals("Made from your photos: the Cartoon look is not used with your own photos.", s.note)
        assertEquals(AppliedLook("cartoon", "real", reason = "own_photos"), s.look)
        assertEquals(StartedVideo("v2"), StartedVideo.fromJson(obj("""{"video_id":"v2","look":"cartoon","note":7}""")))
        assertEquals(StartedVideo("v3"), StartedVideo.fromJson(obj("""{"video_id":"v3","look":{"enforced":true},"note":""}""")))
        assertEquals(AppliedLook("cartoon", "cartoon"), StartedVideo.fromJson(obj("""{"video_id":"v4","look":{"chosen":"cartoon","applied":"cartoon","cast":"auto"}}""")).look)      // "auto" is no list of ids
        try { StartedVideo.fromJson(obj("""{"look":{"chosen":"real"}}""")); fail("no video id is an error") } catch (e: ApiError) { assertEquals(ApiError.Server, e) }
    }

    @Test fun `the video record keeps the applied look and Info says it`() {
        val v = VideoItem.fromJson(obj("""{"video_id":"v1","status":"COMPLETE","look":{"chosen":"auto","applied":"whiteboard","recipe":"whiteboard","cast":[],"extras":[],"why":"A step-by-step process is clearest drawn.","by":"auto","share":1.0,"repaired":0,"reason":null}}"""))
        assertEquals(AppliedLook("auto", "whiteboard", why = "A step-by-step process is clearest drawn.", byAuto = true), v.look)
        assertEquals("Whiteboard · chosen for you", v.look!!.infoLine(looks))
        assertEquals("Whiteboard · chosen for you", v.look!!.infoLine(null))      // the server no longer lists looks: our word for the known ones
        val mine = AppliedLook.fromJson(obj("""{"chosen":"cartoon","applied":"cartoon","cast":["fox","bear"],"by":"you"}"""))!!
        assertFalse(mine.byAuto); assertEquals("Cartoon · Fox + Bruno", mine.infoLine(looks))
        assertNull(AppliedLook("auto", "auto").infoLine(looks)); assertNull(AppliedLook(applied = "mystery").infoLine(null))
        assertNull(VideoItem.fromJson(obj("""{"video_id":"v2","status":"COMPLETE"}""")).look)
        assertNull(VideoItem.fromJson(obj("""{"video_id":"v3","status":"COMPLETE","look":"whiteboard"}""")).look)
    }

    // the rules

    @Test fun `four tiles, auto first, and only the unavailable ones hidden`() {
        assertEquals(listOf("auto", "real", "whiteboard", "cartoon"), LookRules.tiles(looks).map { it.id })
        assertTrue(LookRules.tiles(looks).none { it.locked })
        val gone = looks.copy(options = looks.options.map { if (it.id == "whiteboard") it.copy(available = false) else it })
        assertEquals(listOf("auto", "real", "cartoon"), LookRules.tiles(gone).map { it.id })
        assertEquals(LookChoice(), LookRules.select("whiteboard", LookChoice(), gone))
        assertEquals(LookRules.Normalized(LookChoice(), LookRules.Reset.Gone), LookRules.normalized(LookChoice("whiteboard"), gone))
        val many = looks.copy(options = looks.options + LookOption("fifth", "Fifth"))
        assertEquals(4, LookRules.tiles(many).size)
    }

    @Test fun `a look the plan does not include stays in place, dimmed, with the plan's name, and cannot be chosen`() {
        val plan = looks.copy(options = looks.options.map { if (it.id == "cartoon") it.copy(allowed = false, requiresPlan = "pro") else it })
        val tile = LookRules.tiles(plan).last()
        assertEquals("cartoon", tile.id); assertEquals(LookRules.Block.Plan, tile.blocked); assertTrue(tile.locked)
        assertEquals("Pro plan", LookRules.reason(tile))
        assertEquals("Not in your plan", LookRules.reason(LookRules.Tile(tile.option.copy(requiresPlan = null), LookRules.Block.Plan)))
        assertEquals(LookChoice("real"), LookRules.select("cartoon", LookChoice("real"), plan))
        assertEquals(LookRules.Reset.Plan, LookRules.normalized(LookChoice("cartoon"), plan).reset)
    }

    @Test fun `with photos or a presentation the drawn looks stay in place, blocked, with the reason`() {
        val photos = LookRules.tiles(looks, LookRules.Attached(photos = true))
        assertEquals(listOf(null, null, LookRules.Block.Photos, LookRules.Block.Photos), photos.map { it.blocked })
        assertEquals("Not with photos", LookRules.reason(photos[2]))
        val deck = LookRules.tiles(looks, LookRules.Attached(deck = true))
        assertEquals(listOf(null, null, LookRules.Block.Deck, LookRules.Block.Deck), deck.map { it.blocked })
        assertEquals("Not with slides", LookRules.reason(deck[3]))
        assertNull(LookRules.reason(photos[0]))
        assertEquals(LookChoice(), LookRules.select("cartoon", LookChoice(), looks, LookRules.Attached(photos = true)))
        assertEquals(LookChoice("real"), LookRules.select("real", LookChoice(), looks, LookRules.Attached(photos = true)))
    }

    @Test fun `attaching photos after choosing goes back to auto and says so in one line`() {
        val chosen = LookChoice("cartoon", listOf("fox", "bear"), listOf("board"))
        assertEquals(LookRules.Normalized(chosen, null), LookRules.normalized(chosen, looks))
        val r = LookRules.normalized(chosen, looks, LookRules.Attached(photos = true))
        assertEquals(LookChoice(), r.choice); assertEquals(LookRules.Reset.Photos, r.reset)
        assertEquals("Look set to Auto. Cartoon can't use your photos.", LookRules.resetLine(r.reset!!, "Cartoon"))
        assertEquals(LookRules.Reset.Deck, LookRules.normalized(LookChoice("whiteboard"), looks, LookRules.Attached(deck = true)).reset)
        assertEquals("Look set to Auto. Whiteboard can't use a presentation.", LookRules.resetLine(LookRules.Reset.Deck, "Whiteboard"))
        assertEquals("Look set to Auto. Whiteboard is not available.", LookRules.resetLine(LookRules.Reset.Gone, "Whiteboard"))
        // a look that is made from photos stays, and Auto never needs a line
        assertEquals(LookRules.Normalized(LookChoice("real"), null), LookRules.normalized(LookChoice("real"), looks, LookRules.Attached(photos = true)))
        assertEquals(LookRules.Normalized(LookChoice(), null), LookRules.normalized(LookChoice(), looks, LookRules.Attached(photos = true)))
    }

    @Test fun `the cast is one to three, and two or three are a conversation`() {
        var c = LookChoice("cartoon")
        fun tap(id: String): LookRules.CastTap { val (n, t) = LookRules.toggle(id, c, looks); c = n; return t }
        assertFalse(LookRules.isConversation(c, looks))
        assertEquals(LookRules.CastTap.Added, tap("fox")); assertFalse(LookRules.isConversation(c, looks))
        assertEquals(LookRules.CastTap.Added, tap("bear")); assertTrue(LookRules.isConversation(c, looks))
        assertEquals(LookRules.CastTap.Added, tap("cat")); assertTrue(LookRules.castIsFull(c, looks))
        assertEquals(LookRules.CastTap.Full, tap("ines")); assertEquals(listOf("fox", "bear", "cat"), c.cast)      // the order they were chosen in
        assertEquals(LookRules.CastTap.Removed, tap("bear")); assertEquals(listOf("fox", "cat"), c.cast); assertFalse(LookRules.castIsFull(c, looks))
        assertEquals(LookRules.CastTap.Full, tap("nobody")); assertEquals(listOf("fox", "cat"), c.cast)
        // what comes back from storage is kept inside what the server lists
        assertEquals(listOf("fox", "bear", "cat"), LookRules.normalized(LookChoice("cartoon", listOf("fox", "gone", "fox", "bear", "cat", "ines")), looks).choice.cast)
        assertEquals(emptyList<String>(), LookRules.normalized(LookChoice("whiteboard", listOf("fox"), listOf("board")), looks).choice.cast)
        assertEquals(emptyList<String>(), LookRules.normalized(LookChoice("whiteboard", listOf("fox"), listOf("board")), looks).choice.extras)
    }

    @Test fun `one line says what the cast means, in both languages`() {
        assertEquals("We pick for you. Or choose up to 3.", LookRules.castLine(LookChoice("cartoon"), looks))      // the server's own sentence
        assertEquals("We pick for you. Or choose up to 3.", LookRules.castLine(LookChoice("cartoon"), looks.copy(cast = looks.cast!!.copy(autoNote = null))))
        assertEquals("Fox presents.", LookRules.castLine(LookChoice("cartoon", listOf("fox")), looks))
        assertEquals("Fox and Bruno talk it through.", LookRules.castLine(LookChoice("cartoon", listOf("fox", "bear")), looks))
        assertEquals("Fox, Bruno and Mika talk it through.", LookRules.castLine(LookChoice("cartoon", listOf("fox", "bear", "cat")), looks))
        assertEquals("Auto", LookRules.castSpoken(LookChoice("cartoon"), looks))
        assertEquals("Fox and Bruno, Characters explain at a board", LookRules.castSpoken(LookChoice("cartoon", listOf("fox", "bear"), listOf("board")), looks))
        val old = Txt.provider
        try {
            Txt.provider = JvmStringProvider("es")
            assertEquals("Fox presenta.", LookRules.castLine(LookChoice("cartoon", listOf("fox")), looks))
            assertEquals("Fox y Bruno lo conversan.", LookRules.castLine(LookChoice("cartoon", listOf("fox", "bear")), looks))
            assertEquals("Fox, Bruno e Inés lo conversan.", LookRules.castLine(LookChoice("cartoon", listOf("fox", "bear", "ines")), looks))
            assertEquals("Elegimos por ti. O elige hasta 3.", LookRules.castLine(LookChoice("cartoon"), looks.copy(cast = looks.cast!!.copy(autoNote = null))))
            assertEquals("Estilo cambiado a Auto. Animado no usa tus fotos.", LookRules.resetLine(LookRules.Reset.Photos, "Animado"))
            assertEquals("No con fotos", LookRules.reason(LookRules.tiles(looks, LookRules.Attached(photos = true))[2]))
            assertEquals("Duración cambiada a 30 s. Una conversación necesita 20 s o más.", LookRules.movedLine(LookRules.LengthNudge(0.5, 20.0, true), LookChoice("cartoon", listOf("fox", "bear")), looks))
            assertEquals("Pizarra · elegido para ti", AppliedLook("auto", "whiteboard", byAuto = true).infoLine(null))
        } finally { Txt.provider = old }
    }

    @Test fun `another look drops the cast and the extra, the same look keeps them`() {
        val chosen = LookChoice("cartoon", listOf("fox", "bear"), listOf("board"))
        assertEquals(chosen, LookRules.select("cartoon", chosen, looks))
        assertEquals(LookChoice("whiteboard"), LookRules.select("whiteboard", chosen, looks))
        assertEquals(LookChoice(), LookRules.select("auto", chosen, looks))
        assertEquals(chosen, LookRules.select("nothing", chosen, looks))
        assertEquals(listOf("board"), LookRules.setExtra("board", true, LookRules.setExtra("board", true, LookChoice("cartoon"))).extras)
        assertEquals(emptyList<String>(), LookRules.setExtra("board", false, chosen).extras)
    }

    @Test fun `the characters pill shows only for a look that has characters or a switch`() {
        assertFalse(LookRules.hasCast(LookChoice(), looks)); assertFalse(LookRules.hasCast(LookChoice("real"), looks)); assertFalse(LookRules.hasCast(LookChoice("whiteboard"), looks))
        assertTrue(LookRules.hasCast(LookChoice("cartoon"), looks))
        val noFaces = looks.copy(cast = looks.cast!!.copy(members = emptyList()))
        assertTrue("the board switch alone is still worth the pill", LookRules.hasCast(LookChoice("cartoon"), noFaces))
        assertFalse(LookRules.hasCast(LookChoice("cartoon"), noFaces.copy(options = noFaces.options.map { it.copy(extras = emptyList()) })))
        assertFalse(LookRules.hasCast(LookChoice("cartoon"), looks.copy(cast = looks.cast!!.copy(available = false), options = looks.options.map { it.copy(extras = emptyList()) })))
    }

    @Test fun `a conversation moves a short video to the shortest length that works, and says so`() {
        val talk = LookChoice("cartoon", listOf("fox", "bear"))
        assertEquals(20.0, LookRules.minSeconds(talk, looks), 0.0); assertEquals(15.0, LookRules.minSeconds(LookChoice("cartoon", listOf("fox")), looks), 0.0)
        val nudge = LookRules.lengthNudge(talk, looks, 0.25, presets)!!
        assertEquals(LookRules.LengthNudge(0.5, 20.0, true), nudge)
        assertEquals("Length changed to 30 s. A conversation needs 20 s or more.", LookRules.movedLine(nudge, talk, looks))
        assertEquals("A conversation needs 20 s.", LookRules.needsLine(nudge, talk, looks))
        assertNull(LookRules.lengthNudge(talk, looks, 0.5, presets)); assertNull(LookRules.lengthNudge(talk, looks, 3.0, presets))
        assertNull(LookRules.lengthNudge(LookChoice("cartoon", listOf("fox")), looks, 0.25, presets))
        assertNull("no preset is long enough: nothing to move to", LookRules.lengthNudge(talk, looks, 0.25, listOf(0.25)))
        assertNull(LookRules.lengthNudge(talk, null, 0.25, presets))
    }

    @Test fun `a look with its own minimum moves the length too`() {
        val slow = looks.copy(options = looks.options.map { if (it.id == "whiteboard") it.copy(minSeconds = 45.0) else it })
        val nudge = LookRules.lengthNudge(LookChoice("whiteboard"), slow, 0.5, presets)!!
        assertEquals(LookRules.LengthNudge(0.75, 45.0, false), nudge)
        assertEquals("Length changed to 45 s. Whiteboard needs 45 s or more.", LookRules.movedLine(nudge, LookChoice("whiteboard"), slow))
        assertEquals("Whiteboard needs 45 s.", LookRules.needsLine(nudge, LookChoice("whiteboard"), slow))
    }

    @Test fun `the pill says the look only, in the server's words`() {
        assertEquals("Auto", LookRules.pillLabel(LookChoice(), looks))
        assertEquals("Whiteboard", LookRules.pillLabel(LookChoice("whiteboard"), looks))
        assertEquals("Cartoon", LookRules.pillLabel(LookChoice("cartoon", listOf("fox", "bear"), listOf("board")), looks))
        assertEquals("Animado", LookRules.pillLabel(LookChoice("cartoon", listOf("fox")), fixture("es")))
        assertEquals("Auto", LookRules.pillLabel(LookChoice("gone"), looks))
        assertEquals("Picked for your topic", LookRules.note(looks.option("auto")!!))
        assertEquals("Drawn by hand, step by step", LookRules.note(LookOption("whiteboard", "Whiteboard", "Drawn by hand, step by step.")))      // an older server's sentence loses its full stop
    }

    @Test fun `the last choice is remembered and kept inside what the server lists`() {
        val full = Capabilities.FALLBACK.copy(presets = presets, lookPicker = looks, looks = LooksCaps(listOf(StyleOption("auto", "Auto"), StyleOption("real", "Real"))))
        val chosen = CreateOptions(minutes = 1.0, style = "real", lookChoice = LookChoice("cartoon", listOf("fox", "bear"), listOf("board")))
        val stored = CreatePrefs.fromJson(CreatePrefs.of(chosen).toJson())!!
        assertEquals(LookChoice("cartoon", listOf("fox", "bear"), listOf("board")), stored.pick)
        val back = CreateDefaults.resolve(stored, full)
        assertEquals(chosen.lookChoice, back.lookChoice)
        assertEquals("with the picker the older style wish is not kept", "auto", back.style)
        // an older server: the remembered look is not used and nothing new would be sent
        val older = CreateDefaults.resolve(stored, Capabilities.FALLBACK.copy(presets = presets))
        assertEquals(LookChoice(), older.lookChoice)
        // the server dropped a character and the board: what is left is kept
        val less = full.copy(lookPicker = looks.copy(cast = looks.cast!!.copy(members = looks.cast!!.members.filter { it.id != "bear" }), options = looks.options.map { it.copy(extras = emptyList()) }))
        assertEquals(LookChoice("cartoon", listOf("fox")), CreateDefaults.resolve(stored, less).lookChoice)
        // preferences from before the picker read as Auto, and Auto stores nothing
        assertEquals(LookChoice(), CreatePrefs.fromJson("""{"platform":"youtube","minutes":1,"look":"paper"}""")!!.pick)
        assertFalse(CreatePrefs.of(CreateOptions()).toJson().contains("pick"))
    }
}
