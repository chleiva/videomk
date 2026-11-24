package com.videomk.app.core

import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.booleanOrNull
import kotlinx.serialization.json.doubleOrNull
import kotlinx.serialization.json.intOrNull
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import java.time.Instant

/**
 * Tolerant JSON reading, like the iOS client's `try? decode`: a missing or wrongly typed optional field is just absent, never a crash.
 * Only the fields a screen cannot work without are required (they throw [ApiError.Server] through [requireString] and friends).
 */
internal val lenientJson = Json { ignoreUnknownKeys = true; isLenient = true }

internal fun parseObject(text: String): JsonObject =
    try { lenientJson.parseToJsonElement(text).jsonObject } catch (e: Exception) { throw ApiError.Server }

internal fun JsonElement?.asObject(): JsonObject? = this as? JsonObject
internal fun JsonElement?.asArray(): List<JsonElement>? = try { this?.jsonArray } catch (e: Exception) { null }

internal fun JsonObject.str(key: String): String? = (this[key] as? JsonPrimitive)?.takeIf { it.isString }?.content
internal fun JsonObject.num(key: String): Double? = (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.doubleOrNull
internal fun JsonObject.int(key: String): Int? = (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.intOrNull
internal fun JsonObject.bool(key: String): Boolean? = (this[key] as? JsonPrimitive)?.takeIf { !it.isString }?.booleanOrNull
internal fun JsonObject.obj(key: String): JsonObject? = this[key] as? JsonObject
internal fun JsonObject.arr(key: String): List<JsonElement>? = this[key].asArray()

internal fun JsonObject.requireString(key: String): String = str(key) ?: throw ApiError.Server
internal fun JsonObject.requireInt(key: String): Int = int(key) ?: throw ApiError.Server

internal fun parseInstant(s: String?): Instant? = s?.let { try { Instant.parse(it) } catch (e: Exception) {
    try { java.time.OffsetDateTime.parse(it).toInstant() } catch (e2: Exception) { null }
} }

internal fun epochSeconds(d: Double?): Instant? = d?.let { Instant.ofEpochMilli((it * 1000).toLong()) }
