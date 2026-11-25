package com.videomk.app.ui

import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateListOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.lifecycle.ViewModel
import androidx.lifecycle.viewModelScope
import com.videomk.app.core.ApiError
import com.videomk.app.core.ArrivalPoller
import com.videomk.app.core.ArrivalTracker
import com.videomk.app.core.MediaApi
import com.videomk.app.core.MediaCache
import com.videomk.app.core.MediaCollection
import com.videomk.app.core.MediaFilter
import com.videomk.app.core.MediaListing
import com.videomk.app.core.MediaPhoto
import com.videomk.app.core.MediaSummary
import com.videomk.app.core.SearchChip
import com.videomk.app.core.SearchDebouncer
import com.videomk.app.core.SearchResult
import com.videomk.app.core.SearchState
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch

/**
 * One view of My media: the whole library, one collection, or the picker sheet in the composer. Holds the timeline (cursor paging), the search with its
 * understood chips, the selection and the collections. Screens only read these fields and call the functions.
 */
class MediaViewModel(
    private val api: MediaApi?, private val collectionId: String? = null, private val cache: MediaCache? = null,
    private val limit: Int = Int.MAX_VALUE, private val tracker: ArrivalTracker = ArrivalTracker(),
) : ViewModel() {
    private val listing = MediaListing()
    var summary by mutableStateOf<MediaSummary?>(null); private set
    var collections by mutableStateOf<List<MediaCollection>>(emptyList()); private set
    var photos by mutableStateOf<List<MediaPhoto>>(emptyList()); private set      // what the grid shows right now (timeline or search result)
    var loading by mutableStateOf(true); private set
    var loadingMore by mutableStateOf(false); private set
    var error by mutableStateOf<String?>(null); private set
    var offline by mutableStateOf(false); private set
    var search by mutableStateOf(SearchState()); private set
    var understoodChips by mutableStateOf<List<SearchChip>>(emptyList()); private set
    var searching by mutableStateOf(false); private set
    val selection = mutableStateListOf<String>()
    var selecting by mutableStateOf(false); private set
    var viewerIndex by mutableStateOf<Int?>(null)
    var notice by mutableStateOf<String?>(null)
    var fromPrompt by mutableStateOf(false); private set
    private var searchResult: SearchResult? = null
    private var started = false

    /** Photos uploaded but not listed yet (the server is preparing them): the "Getting N photos ready" line. */
    var gettingReady by mutableStateOf(0); private set
    var refreshing by mutableStateOf(false); private set
    private var seenUploaded = 0
    private val poller = ArrivalPoller(viewModelScope, tracker, { refreshHead() })

    /** Fetches the first page and the summary, puts new photos at the top (scroll position, paging and selection untouched). Returns the library's photo count, or null on failure. */
    private suspend fun refreshHead(): Int? {
        val a = api ?: return null
        return try {
            val page = a.items(60, null, MediaFilter(collection = collectionId))
            listing.mergeHead(page); offline = false
            if (searchResult == null) photos = listing.items
            val s = a.summary(); summary = s
            runCatching { collections = a.collections() }
            gettingReady = tracker.missing(s.count)
            s.count
        } catch (e: CancellationException) { throw e } catch (e: Exception) { null }
    }

    /** The queue says [uploadedTotal] photos have been uploaded so far; the new ones are awaited until the server lists them. Duplicates never raise this number. */
    fun onUploaded(uploadedTotal: Int) {
        if (uploadedTotal < seenUploaded) seenUploaded = 0
        val delta = uploadedTotal - seenUploaded
        seenUploaded = uploadedTotal
        if (delta <= 0) return
        tracker.expect(summary?.count ?: listing.items.size, delta)
        gettingReady = tracker.missing(summary?.count ?: listing.items.size)
        if (!search.active) poller.start()
    }

    /** The screen became visible again (tab, foreground, picker opened): refresh now and keep waiting for anything still pending. */
    fun onVisible() {
        if (!started) return
        viewModelScope.launch { refreshHead() }
        if (tracker.pending && !search.active) poller.start()
    }

    fun stopWaiting() { poller.stop() }

    fun pullRefresh() {
        viewModelScope.launch { refreshing = true; refreshHead(); refreshing = false }
    }

    private val debouncer = SearchDebouncer(viewModelScope, 400) { q -> runSearch(q) }

    /** Semantic results are ordered by relevance: the grid keeps that order and shows no month headers. */
    val flatOrder: Boolean get() = searchResult?.isSemantic == true
    val hasMore: Boolean get() = if (searchResult != null) searchResult?.cursor != null else listing.hasMore

    fun start() { if (!started) { started = true; refresh() } }

    fun refresh() {
        val a = api ?: run { loading = false; error = "My media isn't available in this build."; return }
        viewModelScope.launch {
            loading = photos.isEmpty(); error = null
            try {
                val page = a.items(60, null, MediaFilter(collection = collectionId))
                listing.replace(page); offline = false
                if (collectionId == null) cache?.savePage("first", page)
                if (searchResult == null) photos = listing.items
                runCatching { summary = a.summary(); collections = a.collections() }
            } catch (e: CancellationException) { throw e
            } catch (e: ApiError.Network) {
                offline = true
                val cached = if (collectionId == null) cache?.loadPage("first") else null
                if (cached != null && photos.isEmpty()) { listing.replace(cached); photos = listing.items } else if (photos.isEmpty()) error = e.message
            } catch (e: ApiError) { error = e.message } catch (e: Exception) { error = ApiError.Server.message }
            loading = false
        }
    }

    fun loadMore() {
        val a = api ?: return
        if (loadingMore || !hasMore) return
        searchResult?.let { r ->
            viewModelScope.launch {
                loadingMore = true
                try {
                    val next = a.search(search.query.trim(), 60, search.dropped, r.cursor)
                    searchResult = SearchResult(next.understood, r.items + next.items.filter { n -> r.items.none { it.id == n.id } }, next.mode, next.cursor)
                    photos = searchResult!!.items
                } catch (e: CancellationException) { throw e } catch (e: Exception) { /* the next scroll tries again */ }
                loadingMore = false
            }
            return
        }
        viewModelScope.launch {
            loadingMore = true
            try { listing.append(a.items(60, listing.cursor, MediaFilter(collection = collectionId))); photos = listing.items } catch (e: CancellationException) { throw e } catch (e: Exception) { /* the next scroll tries again */ }
            loadingMore = false
        }
    }

    /** Thumbnail links last an hour: when the screen comes back after a while, fetch the first page again and swap in fresh links. */
    fun refreshLinksIfStale() {
        val a = api ?: return
        if (!listing.linksStale()) return
        viewModelScope.launch { runCatching { listing.refreshLinks(a.items(60, null, MediaFilter(collection = collectionId)).items); if (searchResult == null) photos = listing.items } }
    }

    // search

    fun onQuery(text: String) { search = search.withQuery(text); debouncer.submit(text); if (text.isNotBlank()) poller.stop() }

    /** "Photos from your prompt": search with the video prompt, then preselect everything found (up to the limit), chips visible so the person can adjust. */
    fun promptSearch(text: String) {
        search = search.withQuery(text); debouncer.cancel()
        viewModelScope.launch { runSearch(text.trim()); fromPrompt = understoodChips.isNotEmpty() || photos.isNotEmpty(); if (photos.isNotEmpty()) preselect(photos.map { it.id }) }
    }

    fun clearSearch() { debouncer.cancel(); search = SearchState(); searchResult = null; understoodChips = emptyList(); fromPrompt = false; photos = listing.items; if (tracker.pending) poller.start() }

    fun dropChip(label: String) {
        search = search.drop(label)
        viewModelScope.launch { runSearch(search.query.trim(), search.dropped) }
    }

    private suspend fun runSearch(q: String, drop: List<String> = emptyList()) {
        val a = api ?: return
        if (q.isBlank()) { clearSearch(); return }
        searching = true
        try {
            val r = a.search(q, if (limit < 100) 100 else 60, drop)
            searchResult = r; understoodChips = r.understood.chips; photos = r.items
        } catch (e: CancellationException) { throw e
        } catch (e: ApiError) { notice = e.message } catch (e: Exception) { notice = ApiError.Server.message }
        searching = false
    }

    // selection

    fun startSelecting(id: String) { selecting = true; if (id !in selection && selection.size < limit) selection.add(id) }
    fun toggle(id: String) {
        if (id in selection) selection.remove(id) else if (selection.size < limit) selection.add(id) else notice = "You can choose up to $limit photos."
        if (selection.isEmpty() && limit == Int.MAX_VALUE) selecting = false
    }
    fun selectAllInView() {
        selecting = true
        for (p in photos) if (p.id !in selection && selection.size < limit) selection.add(p.id)
        if (selection.size >= limit && photos.size > selection.size) notice = "Selected the first $limit."
    }
    fun preselect(ids: List<String>) { selection.clear(); selection.addAll(ids.take(limit)); selecting = true }
    fun clearSelection() { selection.clear(); selecting = false }

    /** The picker sheet starts in selection mode with what is already chosen. */
    fun startPicker(existing: List<String>) { selection.clear(); selection.addAll(existing.take(limit)); selecting = true }
    fun selectedPhotos(): List<MediaPhoto> = selection.mapNotNull { id -> photos.firstOrNull { it.id == id } ?: listing.get(id) }

    // actions

    fun deleteSelected() { deleteIds(selection.toList()); clearSelection() }

    fun deleteIds(ids: List<String>) {
        val a = api ?: return
        if (ids.isEmpty()) return
        viewModelScope.launch {
            try {
                for (chunk in ids.chunked(100)) a.delete(chunk)
                listing.remove(ids); photos = photos.filter { it.id !in ids }
                searchResult = searchResult?.let { r -> SearchResult(r.understood, r.items.filter { it.id !in ids }, r.mode) }
                notice = if (ids.size == 1) "Photo deleted." else "${ids.size} photos deleted."
                runCatching { summary = a.summary(); collections = a.collections() }
            } catch (e: CancellationException) { throw e } catch (e: ApiError) { notice = e.message } catch (e: Exception) { notice = ApiError.Server.message }
        }
    }

    fun addToCollection(collection: MediaCollection, ids: List<String>) {
        val a = api ?: return
        viewModelScope.launch {
            try {
                for (chunk in ids.chunked(100)) a.editCollection(collection.id, add = chunk)
                notice = "Added to ${collection.name}."
                runCatching { collections = a.collections() }
                photos = photos.map { if (it.id in ids) it.copy(collections = (it.collections + collection.id).distinct()) else it }
                photos.filter { it.id in ids }.forEach { listing.update(it) }
            } catch (e: CancellationException) { throw e } catch (e: ApiError) { notice = e.message } catch (e: Exception) { notice = ApiError.Server.message }
        }
        clearSelection()
    }

    fun removeFromCollection(ids: List<String>) {
        val a = api ?: return
        val cid = collectionId ?: return
        viewModelScope.launch {
            try {
                for (chunk in ids.chunked(100)) a.editCollection(cid, remove = chunk)
                listing.remove(ids); photos = photos.filter { it.id !in ids }
                runCatching { collections = a.collections() }
            } catch (e: CancellationException) { throw e } catch (e: ApiError) { notice = e.message } catch (e: Exception) { notice = ApiError.Server.message }
        }
        clearSelection()
    }

    fun createCollection(name: String, then: (MediaCollection) -> Unit = {}) {
        val a = api ?: return
        if (name.isBlank()) return
        viewModelScope.launch {
            try { val c = a.createCollection(name.trim()); collections = collections + c; then(c) } catch (e: CancellationException) { throw e } catch (e: ApiError) { notice = e.message } catch (e: Exception) { notice = ApiError.Server.message }
        }
    }

    fun renameCollection(id: String, name: String) {
        val a = api ?: return
        viewModelScope.launch {
            try { val c = a.updateCollection(id, name = name); collections = collections.map { if (it.id == id) c else it } } catch (e: CancellationException) { throw e } catch (e: ApiError) { notice = e.message } catch (e: Exception) { notice = ApiError.Server.message }
        }
    }

    fun deleteCollection(id: String, done: () -> Unit = {}) {
        val a = api ?: return
        viewModelScope.launch {
            try { a.deleteCollection(id); collections = collections.filter { it.id != id }; done() } catch (e: CancellationException) { throw e } catch (e: ApiError) { notice = e.message } catch (e: Exception) { notice = ApiError.Server.message }
        }
    }

    /** The photo's own read (with the full-size link, valid 10 minutes) for the viewer. */
    suspend fun fullPhoto(id: String): MediaPhoto? = try { api?.item(id) } catch (e: CancellationException) { throw e } catch (e: Exception) { null }

    /** After an upload finished: the new photos belong at the top. */

}
