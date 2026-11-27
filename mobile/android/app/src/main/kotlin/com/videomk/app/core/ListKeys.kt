package com.videomk.app.core

/** Keys for lazy lists built from data that may repeat: a repeated key crashes a Compose list with "Key was already used". */
object ListKeys {
    /** The same labels, each made unique by a counter on the second and later copies ("Mallorca", "Mallorca#1"); order and first copies are unchanged. */
    fun unique(labels: List<String>): List<String> {
        val seen = HashMap<String, Int>()
        return labels.map { l -> val n = seen.getOrDefault(l, 0); seen[l] = n + 1; if (n == 0) l else "$l#$n" }
    }
}
