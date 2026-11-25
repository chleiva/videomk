import Foundation
import Testing
@testable import VideoMKCore

private func tmpDir() -> URL { FileManager.default.temporaryDirectory.appendingPathComponent("vmk-test-\(UUID().uuidString)") }
private func jpeg(_ n: UInt8, size: Int = 100) -> Data { Data([n] + [UInt8](repeating: n &+ 1, count: size - 1)) }
private func utcCalendar(_ tz: String = "UTC") -> Calendar { var c = Calendar(identifier: .gregorian); c.timeZone = TimeZone(identifier: tz)!; c.locale = Locale(identifier: "en_US"); return c }

@Suite struct MediaModelTests {
    @Test func decodesTheContractPhotoSummaryUploadsAndSearch() throws {
        let photo = try JSONDecoder().decode(LibraryPhoto.self, from: Data(#"{"id":"a1","taken":"2024-07-12T18:30:00","added":"2026-11-25T10:00:00Z","place":"Phuket, Thailand","w":1536,"h":2048,"bytes":1400000,"thumb_url":"https://t.test/a1","collections":["c1"]}"#.utf8))
        #expect(photo.id == "a1" && photo.thumbURL?.absoluteString == "https://t.test/a1" && photo.collections == ["c1"] && photo.url == nil && photo.place == "Phuket, Thailand")
        let bare = try JSONDecoder().decode(LibraryPhoto.self, from: Data(#"{"id":"a2","added":"x","w":1,"h":2,"bytes":3}"#.utf8))
        #expect(bare.taken == nil && bare.collections.isEmpty && bare.thumbURL == nil)
        let s = try JSONDecoder().decode(LibrarySummary.self, from: Data(#"{"plan":"pro","limit_bytes":100000000000,"used_bytes":5,"count":2,"can_upgrade":false,"years":[{"year":2024,"count":2}],"places":[{"name":"Phuket","country":"Thailand","count":2}],"collections":[{"id":"c1","name":"Trip","emoji":"x","count":2,"cover_id":"a1"}]}"#.utf8))
        #expect(s.plan == "pro" && !s.canUpgrade && s.years[0].year == 2024 && s.places[0].country == "Thailand" && s.collections[0].coverID == "a1")
        let u = try JSONDecoder().decode(UploadsResponse.self, from: Data(#"{"uploads":[{"index":0,"status":"upload","id":"i","url":"https://s3.test/","fields":{"key":"k"}},{"index":1,"status":"duplicate","duplicate_of":"z"},{"index":2,"status":"no_space"},{"index":3,"status":"rejected","reason":"bad"},{"index":4,"status":"surprise"}],"used_bytes":1,"limit_bytes":2}"#.utf8))
        #expect(u.uploads.map(\.status) == [.upload, .duplicate, .noSpace, .rejected, .unknown] && u.uploads[1].duplicateOf == "z")
        let r = try JSONDecoder().decode(SearchResponse.self, from: Data(#"{"understood":{"text":"","places":["Thailand"],"chips":[{"kind":"place","label":"Thailand"},{"kind":"date","label":"2024"}]},"items":[],"mode":"timeline"}"#.utf8))
        #expect(r.understood.chips.map(\.label) == ["Thailand", "2024"] && r.mode == "timeline")
    }

    @Test func uploadRequestsOmitMissingFields() throws {
        let data = try JSONEncoder().encode(UploadRequestItem(size: 10, sha256: "ab"))
        let obj = try #require(JSONSerialization.jsonObject(with: data) as? [String: Any])
        #expect(Set(obj.keys) == ["size", "sha256"])
    }

}

@Suite struct MediaUpdateTests {
    @Test func summaryReadOnlyAndCollectionCoverLinkDecode() throws {
        let s = try JSONDecoder().decode(LibrarySummary.self, from: Data(#"{"plan":"free","limit_bytes":100,"used_bytes":150,"read_only":true,"count":1,"can_upgrade":true,"collections":[{"id":"c1","name":"T","count":1,"cover_id":"a","cover_thumb_url":"https://t.test/a"}]}"#.utf8))
        #expect(s.readOnly && s.collections[0].coverThumbURL?.absoluteString == "https://t.test/a")
        let old = try JSONDecoder().decode(LibrarySummary.self, from: Data(#"{"limit_bytes":1,"used_bytes":0}"#.utf8))
        #expect(!old.readOnly)
    }

    @Test func searchResponseCarriesACursorOnlyInTimelineMode() throws {
        let r = try JSONDecoder().decode(SearchResponse.self, from: Data(#"{"understood":{"places":[],"chips":[]},"items":[],"mode":"timeline","cursor":"x+/="}"#.utf8))
        #expect(r.cursor == "x+/=")
        let s = try JSONDecoder().decode(SearchResponse.self, from: Data(#"{"understood":{"places":[],"chips":[]},"items":[],"mode":"semantic"}"#.utf8))
        #expect(s.cursor == nil)
    }

    @Test func fakeSearchPagesInTimelineModeAndKeepsRelevanceOrderInSemanticMode() async throws {
        let api = FakeLibraryAPI.demo(count: 150)
        let p1 = try await api.search(query: "my photos", limit: 100, drop: [], cursor: nil)
        let p2 = try await api.search(query: "my photos", limit: 100, drop: [], cursor: p1.cursor)
        #expect(p1.mode == "timeline" && p1.items.count == 100 && p1.cursor != nil && Set(p1.items.map(\.id)).isDisjoint(with: p2.items.map(\.id)))
        let seen = await api.searches.last?.cursor
        #expect(seen == p1.cursor)                                           // the cursor goes back exactly as received
        await api.setSemantic(true)
        let sem = try await api.search(query: "beach", limit: 100, drop: [], cursor: nil)
        #expect(sem.mode == "semantic" && sem.cursor == nil && sem.items.count == 100)
        let timeline = try await api.search(query: "beach", limit: 100, drop: [], cursor: nil)
        #expect(sem.items.map(\.id) == timeline.items.map(\.id))             // same order every time: the server's relevance order is kept as given
    }

    @Test func fakeSummaryIsReadOnlyOverTheLimitAndCollectionsCarryTheCoverLink() async throws {
        let api = FakeLibraryAPI(photos: [LibraryPhoto(id: "a", bytes: 150, thumbURL: URL(string: "https://t.test/a"), collections: ["c1"])], collections: [LibraryCollection(id: "c1", name: "T")], limitBytes: 100)
        let s = try await api.summary()
        #expect(s.readOnly && s.collections[0].coverID == "a" && s.collections[0].coverThumbURL?.absoluteString == "https://t.test/a")
        await api.setLimit(1000)
        #expect(try await api.summary().readOnly == false)
    }
}

@Suite struct StorageMeterTests {
    @Test func statesFollowTheThresholds() {
        #expect(StorageMeter(used: 0, limit: 2_000_000_000).state == .ok)
        #expect(StorageMeter(used: 1_699_999_999, limit: 2_000_000_000).state == .ok)
        #expect(StorageMeter(used: 1_700_000_000, limit: 2_000_000_000).state == .warning)   // 85 %
        #expect(StorageMeter(used: 1_999_999_999, limit: 2_000_000_000).state == .warning)
        #expect(StorageMeter(used: 2_000_000_000, limit: 2_000_000_000).state == .full)
        #expect(StorageMeter(used: 5, limit: 0).state == .full && StorageMeter(used: 0, limit: 0).state == .ok)
    }
    @Test func labelsUseDecimalUnits() {
        #expect(StorageMeter(used: 1_200_000_000, limit: 2_000_000_000).label == "1.2 GB of 2 GB")
        #expect(StorageMeter(used: 640_000_000, limit: 100_000_000_000).label == "640 MB of 100 GB")
        #expect(StorageMeter(used: 0, limit: 2_000_000_000).fraction == 0 && StorageMeter(used: 3, limit: 2).fraction == 1)
    }
}

@Suite struct GroupingTests {
    private func p(_ id: String, taken: String? = nil, added: String = "2026-01-01T00:00:00Z") -> LibraryPhoto { LibraryPhoto(id: id, taken: taken, added: added) }

    @Test func monthsNewestFirstByCaptureDateElseAddedDate() {
        let cal = utcCalendar()
        let s = MediaGrouping.sections([p("a", taken: "2024-07-02T10:00:00"), p("b", taken: "2025-01-15T10:00:00"), p("c", taken: "2024-07-30T08:00:00"), p("d", added: "2025-03-05T12:00:00Z")], calendar: cal)
        #expect(s.map(\.id) == ["2025-03", "2025-01", "2024-07"])
        #expect(s[2].items.map(\.id) == ["c", "a"] && s[2].title == "July 2024" && s[0].items.map(\.id) == ["d"])
    }

    @Test func addedTimeIsReadInThePersonsCalendar() {
        let late = p("x", added: "2025-03-31T23:30:00Z")
        #expect(MediaGrouping.sections([late], calendar: utcCalendar("UTC"))[0].id == "2025-03")
        #expect(MediaGrouping.sections([late], calendar: utcCalendar("Pacific/Auckland"))[0].id == "2025-04")     // already April 1st there
        #expect(MediaGrouping.sections([p("w", taken: "2025-03-31T23:30:00")], calendar: utcCalendar("Pacific/Auckland"))[0].id == "2025-03")   // wall-clock is not shifted
    }

    @Test func busyMonthsSplitIntoDays() {
        let many = (0..<5).map { p("a\($0)", taken: "2024-07-0\(1 + $0 % 2)T10:00:0\($0)") }
        let s = MediaGrouping.sections(many, calendar: utcCalendar(), dayThreshold: 4)
        #expect(s.map(\.id) == ["2024-07-02", "2024-07-01"] && s.reduce(0) { $0 + $1.items.count } == 5)
        #expect(s[0].title.contains("2024") && s[0].title.contains("2"))
    }

    @Test func undatedPhotosGoLastAndNothingIsLost() {
        let s = MediaGrouping.sections([p("n", added: "garbage"), p("a", taken: "2024-07-02T10:00:00")], calendar: utcCalendar())
        #expect(s.map(\.id) == ["2024-07", "unknown"] && MediaGrouping.sections([], calendar: utcCalendar()).isEmpty)
    }

    @Test func voiceOverReadsDateAndPlace() {
        let l = MediaGrouping.accessibilityLabel(LibraryPhoto(id: "a", taken: "2024-07-12T18:30:00", place: "Phuket, Thailand"), calendar: utcCalendar())
        #expect(l.hasPrefix("Photo, ") && l.contains("2024") && l.hasSuffix("Phuket, Thailand"))
        #expect(MediaGrouping.accessibilityLabel(LibraryPhoto(id: "b", added: "bad"), calendar: utcCalendar()) == "Photo")
    }
}

@Suite struct SearchLogicTests {
    @Test func planTrimsAndIgnoresTinyQueries() {
        #expect(SearchPlan.decide("") == .timeline && SearchPlan.decide("  a ") == .timeline)
        #expect(SearchPlan.decide("  beach   in Thailand  2024 ") == .search("beach in Thailand 2024"))
    }

    @Test func debouncerRunsOnlyTheLastJob() async throws {
        let counter = HitCounter()
        let d = SearchDebouncer(delay: .milliseconds(60))
        for q in ["b", "be", "bea", "beach"] { d.schedule { await counter.hit(q) } }
        try await Task.sleep(for: .milliseconds(250))
        let h1 = await counter.hits
        #expect(h1 == ["beach"])
        d.schedule { await counter.hit("x") }; d.cancel()
        try await Task.sleep(for: .milliseconds(150))
        let h2 = await counter.hits
        #expect(h2 == ["beach"])
    }

    @Test func promptsThatDescribePhotosAreRecognised() {
        for yes in ["a video of my holidays in Thailand in 2024", "Make a video from my photos of the wedding", "our trip to Lisbon", "pictures from 2023", "use my library"] { #expect(PromptPhotoIntent.looksLikePhotoQuery(yes), "\(yes)") }
        for no in ["A history of the Roman Empire in five minutes", "How volcanoes work", "", "cats"] { #expect(!PromptPhotoIntent.looksLikePhotoQuery(no), "\(no)") }
    }

    @Test func theTotalOfPhoneAndLibraryPhotosIsCappedAtOneHundred() {
        #expect(ComposerPhotos.total(phone: 30, library: 50) == 80 && ComposerPhotos.room(phone: 30, library: 50) == 20 && ComposerPhotos.room(phone: 70, library: 50) == 0)
        #expect(PhotoCapacity.hint(photos: ComposerPhotos.total(phone: 30, library: 70), minutes: 1) != nil)   // the length hint sees all 100
    }
}

private actor HitCounter { var hits: [String] = []; func hit(_ s: String) { hits.append(s) } }

@Suite struct LibraryStoreTests {
    @Test func thumbnailsAreCachedByPhotoIdNotUrl() async throws {
        let api = FakeLibraryAPI(photos: [LibraryPhoto(id: "a", thumbURL: URL(string: "https://t.test/a?sig=1"))])
        let counter = HitCounter()
        let store = PhotoLibraryStore(directory: tmpDir(), api: api) { url in await counter.hit(url.absoluteString); return Data([1, 2, 3]) }
        let a1 = LibraryPhoto(id: "a", thumbURL: URL(string: "https://t.test/a?sig=1"))
        let a2 = LibraryPhoto(id: "a", thumbURL: URL(string: "https://t.test/a?sig=2"))   // same photo, new link
        let t1 = await store.thumbnail(for: a1), t2 = await store.thumbnail(for: a2)
        #expect(t1 == Data([1, 2, 3]) && t2 == Data([1, 2, 3]))
        let n = await counter.hits.count
        #expect(n == 1)
    }

    @Test func diskCacheSurvivesANewStoreAndForgetRemoves() async throws {
        let dir = tmpDir(); let api = FakeLibraryAPI()
        let a = LibraryPhoto(id: "a", thumbURL: URL(string: "https://t.test/a"))
        let first = PhotoLibraryStore(directory: dir, api: api) { _ in Data([9]) }
        _ = await first.thumbnail(for: a)
        let second = PhotoLibraryStore(directory: dir, api: api) { _ in throw LibraryAPIError.network }
        let cached = await second.thumbnail(for: a)
        #expect(cached == Data([9]))                 // offline: still shown
        await second.forget(["a"])
        let gone = await second.thumbnail(for: a)
        #expect(gone == nil)
    }

    @Test func anExpiredLinkIsRefreshedOnce() async throws {
        let fresh = URL(string: "https://t.test/fresh")!
        let api = FakeLibraryAPI(photos: [LibraryPhoto(id: "a", thumbURL: fresh)])
        let store = PhotoLibraryStore(directory: tmpDir(), api: api) { url in if url == fresh { return Data([7]) } else { throw LibraryAPIError.unauthorized } }
        let t = await store.thumbnail(for: LibraryPhoto(id: "a", thumbURL: URL(string: "https://t.test/old")))
        let known = await store.photo("a")?.thumbURL
        #expect(t == Data([7]) && known == fresh)
    }

    @Test func pagesKeepTheOpaqueCursorExactly() async throws {
        let store = PhotoLibraryStore(directory: tmpDir(), api: FakeLibraryAPI()) { _ in Data() }
        let cursor = "eyJwb3MiOiI/KyA9In0=%2F"
        await store.savePage(ItemsPage(items: [LibraryPhoto(id: "a")], cursor: cursor), key: ItemsFilter().cacheKey)
        let page = await store.cachedPage(key: ItemsFilter().cacheKey)
        #expect(page?.cursor == cursor && page?.items.map(\.id) == ["a"])
        let other = await store.cachedPage(key: "other")
        #expect(other == nil)
    }

    @Test func fakeApiHandsTheCursorBackUntouched() async throws {
        let api = FakeLibraryAPI.demo(count: 130)
        let p1 = try await api.items(limit: 60, cursor: nil, filter: ItemsFilter())
        let p2 = try await api.items(limit: 60, cursor: p1.cursor, filter: ItemsFilter())
        #expect(p1.items.count == 60 && p2.items.count == 60 && Set(p1.items.map(\.id)).isDisjoint(with: p2.items.map(\.id)))
        let seenCursor = await api.lastCursorSeen
        #expect(seenCursor == p1.cursor)
    }
}

@Suite struct UploadQueueTests {
    private func prepared(_ n: Int) -> [PreparedUpload] { (0..<n).map { PreparedUpload(data: jpeg(UInt8($0 % 200 + 10), size: 100 + $0), taken: "2024-07-12T18:30:00", lat: 39.57, lon: 2.65) } }
    private func wait(_ q: LibraryUploadQueue, _ until: @Sendable (QueueProgress) -> Bool) async {
        for _ in 0..<400 { if until(await q.progress()) { return }; try? await Task.sleep(for: .milliseconds(10)) }
    }

    @Test func uploadsEverythingInBatchesThreeAtATimeAndSendsOnlyTheContractFields() async throws {
        let api = FakeLibraryAPI(); let poster = FakeFilePoster(delay: .milliseconds(5))
        let q = LibraryUploadQueue(directory: tmpDir(), api: api, poster: poster, backoff: [.milliseconds(1)])
        var many: [PreparedUpload] = []
        for n in 0..<120 { many.append(PreparedUpload(data: Data([UInt8(n % 250), UInt8(n / 250), 7, 9, UInt8(n % 7)]), taken: "2024-07-12T18:30:00", lat: 39.57, lon: 2.65)) }
        await q.enqueue(many)
        await wait(q) { $0.isFinished && !$0.running }
        let p = await q.progress()
        #expect(p.done == 120 && p.processed == 120 && p.failed == 0 && p.doneBytes == p.totalBytes)
        let sizes = await api.uploadRequests.map(\.count)
        #expect(sizes == [100, 20])
        let peak = await poster.peak
        #expect(peak <= 3 && peak > 1)
        let firstItem = await api.uploadRequests.first?.first
        let first = try #require(firstItem)
        let keys = try #require(JSONSerialization.jsonObject(with: JSONEncoder().encode(first)) as? [String: Any]).keys
        #expect(Set(keys) == ["size", "sha256", "taken", "lat", "lon"] && first.sha256.count == 64)
    }

    @Test func shaIsOfTheExactBytesUploaded() async throws {
        let api = FakeLibraryAPI()
        let q = LibraryUploadQueue(directory: tmpDir(), api: api, poster: FakeFilePoster())
        let bytes = jpeg(42, size: 300)
        await q.enqueue([PreparedUpload(data: bytes)])
        await wait(q) { $0.isFinished && !$0.running }
        let sent = await api.uploadRequests[0][0]
        #expect(sent.sha256 == LibraryUploadQueue.sha256(bytes) && sent.size == 300)
        #expect(LibraryUploadQueue.sha256(Data("abc".utf8)) == "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad")
    }

    @Test func duplicatesAreSkippedAndCounted() async throws {
        let api = FakeLibraryAPI(); let poster = FakeFilePoster()
        let q = LibraryUploadQueue(directory: tmpDir(), api: api, poster: poster)
        await api.registerExisting(sha256: LibraryUploadQueue.sha256(jpeg(1)))     // jpeg(1) is already in the library
        await q.enqueue([PreparedUpload(data: jpeg(1)), PreparedUpload(data: jpeg(2))])
        await wait(q) { $0.isFinished && !$0.running }
        await q.enqueue([PreparedUpload(data: jpeg(1)), PreparedUpload(data: jpeg(3))])
        await wait(q) { $0.processed == 4 && !$0.running }
        let p = await q.progress()
        let posted = await poster.posts.count
        #expect(p.done == 2 && p.duplicates == 2 && posted == 2)
    }

    @Test func whenStorageRunsOutThePhotosThatFitGoUpAndTheRestAreNamed() async throws {
        let api = FakeLibraryAPI(limitBytes: 350)
        let q = LibraryUploadQueue(directory: tmpDir(), api: api, poster: FakeFilePoster())
        await q.enqueue((0..<5).map { PreparedUpload(data: jpeg(UInt8($0 + 1), size: 100)) })
        await wait(q) { $0.isFinished && !$0.running }
        let p = await q.progress()
        #expect(p.done == 3 && p.noSpace == 2 && p.needsAttention && p.failed == 0)
    }

    @Test func aFullAccountMarksEverythingAsDidNotFit() async throws {
        let api = FakeLibraryAPI(limitBytes: 0)
        let q = LibraryUploadQueue(directory: tmpDir(), api: api, poster: FakeFilePoster())
        await q.enqueue((0..<4).map { PreparedUpload(data: jpeg(UInt8($0 + 1))) })
        await wait(q) { $0.isFinished && !$0.running }
        let p = await q.progress()
        #expect(p.noSpace == 4 && p.done == 0)
        #expect((try? FileManager.default.contentsOfDirectory(atPath: tmpDir().path))?.isEmpty ?? true)
    }

    @Test func aFailingPhotoIsRetriedThreeTimesThenFailedAndCanBeRetried() async throws {
        let api = FakeLibraryAPI(); let poster = FakeFilePoster()
        await poster.failing(firstByte: 5, times: 3)
        let q = LibraryUploadQueue(directory: tmpDir(), api: api, poster: poster, backoff: [.milliseconds(1)])
        await q.enqueue([PreparedUpload(data: jpeg(4)), PreparedUpload(data: jpeg(5)), PreparedUpload(data: jpeg(6))])
        await wait(q) { $0.isFinished && !$0.running }
        var p = await q.progress()
        #expect(p.done == 2 && p.failed == 1)
        await q.retryFailed()
        await wait(q) { $0.done == 3 && !$0.running }
        p = await q.progress()
        #expect(p.done == 3 && p.failed == 0)
    }

    @Test func aPhotoThatFailsOnceSucceedsOnTheNextTry() async throws {
        let poster = FakeFilePoster(); await poster.failing(firstByte: 5, times: 2)
        let q = LibraryUploadQueue(directory: tmpDir(), api: FakeLibraryAPI(), poster: poster, backoff: [.milliseconds(1)])
        await q.enqueue([PreparedUpload(data: jpeg(5))])
        await wait(q) { $0.isFinished && !$0.running }
        let d = await q.progress().done
        #expect(d == 1)
    }

    @Test func offlineKeepsEverythingPausedWithAMessageAndResumeFinishes() async throws {
        let api = FakeLibraryAPI(); await api.setFailNext(.network)
        let q = LibraryUploadQueue(directory: tmpDir(), api: api, poster: FakeFilePoster())
        await q.enqueue([PreparedUpload(data: jpeg(1)), PreparedUpload(data: jpeg(2))])
        await wait(q) { $0.paused && !$0.running }
        var p = await q.progress()
        #expect(p.queued == 2 && p.paused && p.lastError != nil && p.failed == 0)       // nothing lost
        await q.resume()
        await wait(q) { $0.done == 2 && !$0.running }
        p = await q.progress()
        #expect(p.done == 2 && p.lastError == nil)
    }

    @Test func pauseStopsNewWorkAndCancelForgetsTheRest() async throws {
        let api = FakeLibraryAPI(); let poster = FakeFilePoster(delay: .milliseconds(30))
        let dir = tmpDir()
        let q = LibraryUploadQueue(directory: dir, api: api, poster: poster)
        await q.pause()
        await q.enqueue((0..<10).map { PreparedUpload(data: jpeg(UInt8($0 + 1))) })
        try await Task.sleep(for: .milliseconds(100))
        let queuedNow = await q.progress().queued
        let requested = await api.uploadRequests.count
        #expect(queuedNow == 10 && requested == 0)    // paused: nothing started
        await q.resume()
        try await Task.sleep(for: .milliseconds(20))
        await q.cancel()
        let p = await q.progress()
        #expect(p.total == 0)
        try await Task.sleep(for: .milliseconds(200))
        #expect((try? FileManager.default.contentsOfDirectory(atPath: dir.path).filter { $0.hasSuffix(".jpg") })?.isEmpty ?? true)
    }

    @Test func theQueueSurvivesARelaunchAndResumes() async throws {
        let dir = tmpDir()
        let api = FakeLibraryAPI(); let poster = FakeFilePoster()
        let first = LibraryUploadQueue(directory: dir, api: api, poster: poster)
        await first.pause()
        await first.enqueue((0..<5).map { PreparedUpload(data: jpeg(UInt8($0 + 1)), taken: "2024-07-12T18:30:00") })
        let q1 = await first.progress().queued
        #expect(q1 == 5)
        // "relaunch": a new queue over the same folder
        let second = LibraryUploadQueue(directory: dir, api: api, poster: poster)
        let q2 = await second.progress().queued
        let firstTaken = await second.snapshot().first?.taken
        #expect(q2 == 5 && firstTaken == "2024-07-12T18:30:00")
        await second.start()
        await wait(second) { $0.done == 5 && !$0.running }
        let d2 = await second.progress().done
        let posted = await poster.posts.count
        #expect(d2 == 5 && posted == 5)
    }

    @Test func anInterruptedUploadGoesBackInLineAndAMissingFileIsFailedNotDropped() async throws {
        let dir = tmpDir()
        try FileManager.default.createDirectory(at: dir, withIntermediateDirectories: true)
        try jpeg(1).write(to: dir.appendingPathComponent("a.jpg"))
        let saved = [QueueItem(id: "a", file: "a.jpg", size: 100, sha256: "x", state: .uploading), QueueItem(id: "b", file: "gone.jpg", size: 100, sha256: "y", state: .queued)]
        try JSONEncoder().encode(saved).write(to: dir.appendingPathComponent("queue.json"))
        let q = LibraryUploadQueue(directory: dir, api: FakeLibraryAPI(), poster: FakeFilePoster())
        let items = await q.snapshot()
        #expect(items[0].state == .queued && items[1].state == .failed && items[1].reason != nil)
    }

    @Test func dismissClearsFinishedEntries() async throws {
        let q = LibraryUploadQueue(directory: tmpDir(), api: FakeLibraryAPI(), poster: FakeFilePoster())
        await q.enqueue([PreparedUpload(data: jpeg(1))])
        await wait(q) { $0.isFinished && !$0.running }
        await q.dismissFinished()
        let empty = await q.progress().isEmpty
        #expect(empty)
    }
}

extension CoreTests {
    @Test func generateCarriesLibraryMediaOnlyWhenThereIsSome() async throws {
        nonisolated(unsafe) var body: [String: Any] = [:]
        StubProtocol.handler = { req in body = (try? JSONSerialization.jsonObject(with: req.bodyData ?? Data()) as? [String: Any]) ?? [:]; return (202, Data(#"{"video_id":"abc"}"#.utf8)) }
        let api = APIClient(config: config, auth: FixedAuth(), session: stubSession())
        _ = try await api.startGeneration(prompt: "A day out with the family", clientRequestID: "r", libraryMedia: ["l1", "l2"])
        #expect(body["library_media"] as? [String] == ["l1", "l2"] && body["media"] == nil)
        _ = try await api.startGeneration(prompt: "A day out with the family", clientRequestID: "r", media: ["m1"])
        #expect(body["library_media"] == nil && body["media"] as? [String] == ["m1"])
    }
    @Test func libraryClientUsesTheUsersLibraryPathsAndPassesTheCursorThrough() async throws {
        nonisolated(unsafe) var seen: [URLRequest] = []
        StubProtocol.handler = { req in seen.append(req); return (200, Data(#"{"items":[],"cursor":"next+/="}"#.utf8)) }
        let client = LibraryClient(api: APIClient(config: config, auth: FixedAuth(), session: stubSession()))
        let page = try await client.items(limit: 60, cursor: "a+b/c=", filter: ItemsFilter(from: "2024-01-01", collection: "c1"))
        #expect(page.cursor == "next+/=")
        let url = try #require(seen.last?.url)
        #expect(url.path == "/prod/users/user-1/library/items")
        let items = URLComponents(url: url, resolvingAgainstBaseURL: false)?.queryItems ?? []
        #expect(items.first { $0.name == "cursor" }?.value == "a+b/c=" && items.first { $0.name == "limit" }?.value == "60")
        #expect(items.first { $0.name == "from" }?.value == "2024-01-01" && items.first { $0.name == "collection" }?.value == "c1" && !items.contains { $0.name == "place" })
    }

    @Test func libraryClientRoutesAndBodies() async throws {
        nonisolated(unsafe) var last: (method: String, path: String, body: [String: Any]) = ("", "", [:])
        StubProtocol.handler = { req in
            last = (req.httpMethod ?? "", req.url!.path, (try? JSONSerialization.jsonObject(with: req.bodyData ?? Data()) as? [String: Any]) ?? [:])
            if req.url!.path.hasSuffix("/search") { return (200, Data(#"{"understood":{"places":[],"chips":[]},"items":[],"mode":"semantic"}"#.utf8)) }
            if req.url!.path.hasSuffix("/items/delete") { return (200, Data(#"{"deleted":2,"used_bytes":5}"#.utf8)) }
            return (200, Data(#"{"id":"c9","name":"N","count":0}"#.utf8))
        }
        let client = LibraryClient(api: APIClient(config: config, auth: FixedAuth(), session: stubSession()))
        _ = try await client.search(query: "beach", limit: nil, drop: ["2024"], cursor: "c+/=")
        #expect(last.path == "/prod/users/user-1/library/search" && last.method == "POST" && last.body["query"] as? String == "beach" && last.body["drop"] as? [String] == ["2024"] && last.body["limit"] == nil && last.body["cursor"] as? String == "c+/=")
        _ = try await client.search(query: "beach", limit: 20, drop: [], cursor: nil)
        #expect(last.body["drop"] == nil && last.body["limit"] as? Int == 20 && last.body["cursor"] == nil)
        let r = try await client.delete(ids: ["a", "b"])
        #expect(r.deleted == 2 && last.path.hasSuffix("/library/items/delete") && last.body["ids"] as? [String] == ["a", "b"])
        _ = try await client.createCollection(name: "N", emoji: nil)
        #expect(last.path.hasSuffix("/library/collections") && last.body["emoji"] == nil)
        _ = try await client.updateCollection(id: "c9", name: "M", emoji: "x")
        #expect(last.path.hasSuffix("/library/collections/c9"))
        try await client.editCollection(id: "c9", add: ["a"], remove: [])
        #expect(last.path.hasSuffix("/library/collections/c9/items") && last.body["add"] as? [String] == ["a"] && last.body["remove"] == nil)
        try await client.deleteCollection(id: "c9")
        #expect(last.path.hasSuffix("/library/collections/c9/delete"))
        await #expect(throws: LibraryAPIError.self) { _ = try await client.delete(ids: []) }
        await #expect(throws: LibraryAPIError.self) { _ = try await client.requestUploads([]) }
    }

    @Test func libraryClientMapsErrorStatuses() async throws {
        let client = LibraryClient(api: APIClient(config: config, auth: FixedAuth(), session: stubSession()))
        StubProtocol.handler = { _ in (402, Data(#"{"code":"storage_full","used_bytes":2000,"limit_bytes":2000}"#.utf8)) }
        await #expect(throws: LibraryAPIError.storageFull(usedBytes: 2000, limitBytes: 2000)) { _ = try await client.requestUploads([UploadRequestItem(size: 1, sha256: "a")]) }
        StubProtocol.headers = ["Retry-After": "30"]
        StubProtocol.handler = { _ in (429, Data()) }
        await #expect(throws: LibraryAPIError.rateLimited(retryAfter: 30)) { _ = try await client.summary() }
        StubProtocol.headers = [:]
        for (code, err) in [(404, LibraryAPIError.notFound), (409, .conflict), (413, .tooLarge), (401, .unauthorized), (403, .unauthorized), (500, .server)] {
            StubProtocol.handler = { _ in (code, Data()) }
            await #expect(throws: err) { _ = try await client.summary() }
        }
        StubProtocol.handler = { _ in (200, Data("not json".utf8)) }
        await #expect(throws: LibraryAPIError.server) { _ = try await client.summary() }
    }
}
