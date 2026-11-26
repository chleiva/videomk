package com.videomk.app.data

import android.content.ContentResolver
import android.net.Uri
import android.provider.OpenableColumns
import com.videomk.app.core.DeckPick

/**
 * What the system document picker handed over. The grant it carries is temporary and is deliberately never made persistable (no takePersistableUriPermission):
 * the file is read once, right now, into a private copy. Name and size come from the provider's own columns; neither is logged.
 */
object DeckPicker {
    fun pickOf(resolver: ContentResolver, uri: Uri): DeckPick {
        var name: String? = null
        var size: Long? = null
        try {
            resolver.query(uri, arrayOf(OpenableColumns.DISPLAY_NAME, OpenableColumns.SIZE), null, null, null)?.use { c ->
                if (c.moveToFirst()) {
                    c.getColumnIndex(OpenableColumns.DISPLAY_NAME).takeIf { it >= 0 && !c.isNull(it) }?.let { name = c.getString(it) }
                    c.getColumnIndex(OpenableColumns.SIZE).takeIf { it >= 0 && !c.isNull(it) }?.let { size = c.getLong(it) }
                }
            }
        } catch (e: Exception) { /* a provider that will not say: the copy checks the size itself */ }
        val mime = try { resolver.getType(uri) } catch (e: Exception) { null }
        return DeckPick(name, mime, size) { try { resolver.openInputStream(uri) } catch (e: Exception) { null } }
    }
}
