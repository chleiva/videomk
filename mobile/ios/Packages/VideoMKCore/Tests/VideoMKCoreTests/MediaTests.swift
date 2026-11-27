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

private actor Seen { var values: [Int] = []; func add(_ n: Int) { values.append(n) } }

private actor CallLog { var n = 0; func hit() -> Int { n += 1; return n } }

@Suite struct ReadyWaitTests {
    private let quick = ReadyWait(fast: .milliseconds(4), slow: .milliseconds(8), fastPolls: 3, giveUp: .milliseconds(120))

    @Test func theScheduleIsTwoSecondsThenFourUntilNinetyAndNeverLonger() {
        let d = ReadyWait().delays()
        #expect(d.prefix(5).allSatisfy { $0 == .seconds(2) } && d[5] == .seconds(4))
        let total = d.reduce(Duration.zero, +)
        #expect(total >= .seconds(90) && total <= .seconds(94))
    }

    @Test func photosThatAppearAfterAFewCallsAreWaitedFor() async throws {
        let api = FakeLibraryAPI(); await api.setReadyAfter(3)
        let q = LibraryUploadQueue(directory: FileManager.default.temporaryDirectory.appendingPathComponent("vmk-\(UUID())"), api: api, poster: FakeFilePoster())
        let base = try await api.summary().count
        await q.enqueue([PreparedUpload(data: jpeg(1)), PreparedUpload(data: jpeg(2))])
        for _ in 0..<400 { let p = await q.progress(); if p.isFinished && !p.running { break }; try? await Task.sleep(for: .milliseconds(5)) }
        let progress = await q.progress()
        #expect(try await api.summary().count == base)                                  // a single reload right after the upload sees nothing: the flaw
        let target = try #require(ReadyWait.target(baseline: base, progress: progress))
        #expect(target == base + 2)
        let outcome = await quick.run(target: target) { try? await api.summary().count }
        #expect(outcome == .ready)
        let items = try await api.items(limit: 60, cursor: nil, filter: ItemsFilter())
        #expect(items.items.count == 2)
    }

    @Test func pollingStopsAtTheCap() async throws {
        let api = FakeLibraryAPI(); await api.setReadyAfter(100_000)
        _ = try await api.requestUploads([UploadRequestItem(size: 1, sha256: "a")])
        let log = CallLog()
        let outcome = await quick.run(target: 1) { _ = await log.hit(); return try? await api.summary().count }
        #expect(outcome == .gaveUp)
        let calls = await log.n
        #expect(calls == quick.delays().count + 1)                                       // one immediate poll plus one per delay, then it stops
    }

    @Test func cancellingStopsTheWait() async throws {
        let wait = ReadyWait(fast: .milliseconds(20), slow: .milliseconds(20), fastPolls: 1, giveUp: .seconds(5))
        let t = Task { await wait.run(target: 1) { 0 } }
        try await Task.sleep(for: .milliseconds(50)); t.cancel()
        #expect(await t.value == .cancelled)
    }

    @Test func aBatchOfOnlyDuplicatesNeverWaits() {
        var p = QueueProgress(); p.total = 3; p.duplicates = 3
        #expect(ReadyWait.target(baseline: 10, progress: p) == nil)
        p.done = 2
        #expect(ReadyWait.target(baseline: 10, progress: p) == 12)                       // duplicates are not counted
    }

    @Test func startingAgainReplacesTheRunningWaitSoOnlyOneRunsAtATime() async throws {
        let watcher = ReadyWatcher()
        let slow = ReadyWait(fast: .milliseconds(10), slow: .milliseconds(10), fastPolls: 2, giveUp: .seconds(5))
        for _ in 0..<4 { watcher.start(slow, target: 1, poll: { 0 }); try await Task.sleep(for: .milliseconds(15)) }
        #expect(watcher.started == 4 && watcher.peakActive == 1 && watcher.isRunning)
        let done = CallLog()
        watcher.start(quick, target: 1, poll: { 1 }, finished: { _ in Task { _ = await done.hit() } })
        try await Task.sleep(for: .milliseconds(80))
        #expect(await done.n == 1 && !watcher.isRunning)
        watcher.start(slow, target: 1, poll: { 0 }); watcher.stop()
        try await Task.sleep(for: .milliseconds(40))
        #expect(!watcher.isRunning)
    }
}

@Suite struct ComposerPlanTests {
    private func s(_ text: String = "A short film about my golden retriever", balance: Int? = 5, minutes: Double = 3, photos: Int = 0, dictating: Bool = false, sending: Bool = false) -> ComposerStatus {
        ComposerPlan.status(text: text, balance: balance, options: CreateOptions(minutes: minutes), photos: photos, dictating: dictating, sending: sending)
    }

    @Test func priceBeforeAnythingIsTyped() {
        let st = s("")
        #expect(st.kind == .price && st.message == "A 3 minute video costs 3 credits" && !st.canSend && st.fix == nil)
    }

    @Test func readyShowsPriceAndWhatIsLeft() {
        let st = s()
        #expect(st.kind == .ready && st.message == "3 credits · you'll have 2 left" && st.canSend)
        #expect(s(balance: 1, minutes: 1).message == "1 credit · you'll have 0 left" && s(balance: nil).message == "3 credits")
    }

    @Test func tooShortCountsDown() {
        let st = s("hello")
        #expect(st.kind == .tooShort && st.message == "Add a few more words (5 to go)" && !st.canSend && st.isProblem)
    }

    @Test func notAffordableOffersTheLongestLengthThatFits() {
        let st = s(balance: 1)
        #expect(st.kind == .notAffordable && st.message == "Needs 3 credits, you have 1" && !st.canSend)
        #expect(st.fix == .useMinutes(1, credits: 1) && st.fix?.title == "Use 1 min · ⚡1")
        #expect(s(balance: 4, minutes: 5).fix == .useMinutes(3, credits: 3))      // 3 min is the longest option within 4 credits
        #expect(s(balance: 2, minutes: 12).fix == .useMinutes(2, credits: 2))
    }

    @Test func notAffordableShowsEvenBeforeTyping() {
        #expect(s("", balance: 1).kind == .notAffordable)
    }

    @Test func noCreditsOffersAddCredits() {
        let st = s(balance: 0)
        #expect(st.kind == .noCredits && st.message == "You have no credits" && st.fix == .addCredits && !st.canSend)
    }

    @Test func tooLongBeatsEverything() {
        let st = s(String(repeating: "a ", count: 1100), balance: 0)
        #expect(st.kind == .tooLong && st.message.hasSuffix("Please shorten it.") && st.message.contains("2,000") && !st.canSend)
    }

    @Test func photoHintReplacesThePriceAndOffersTheLengthFix() {
        let st = s(minutes: 1, photos: 100)
        #expect(st.kind == .photoHint && st.message.hasPrefix("About 51 of your 100 photos fit in 1 minute") && st.canSend)
        #expect(st.fix == .useMinutes(2, credits: 2) && st.fix?.title == "Use 2 min · ⚡2")
        #expect(s(balance: 1, minutes: 1, photos: 100).fix == nil)               // the longer length is not affordable: no chip, the hint still shows
        #expect(s(minutes: 2, photos: 100).kind == .ready)                       // 100 photos fit in 2 minutes
    }

    @Test func priorityIsTooLongThenCostThenShortThenPhotosThenPrice() {
        #expect(s("hi", balance: 1, photos: 100).kind == .notAffordable)          // cost beats too short
        #expect(s("hi", balance: 5, minutes: 1, photos: 100).kind == .tooShort)   // too short beats the photo hint
    }

    @Test func dictatingAndSendingStatesNeverSend() {
        #expect(s(dictating: true).message == "Listening…" && !s(dictating: true).canSend)
        #expect(s(sending: true).message == "Starting your video…" && !s(sending: true).canSend)
    }

    @Test func announcementsNameTheReasonAndTheFix() {
        #expect(s(balance: 1).announcement.contains("Needs 3 credits, you have 1") && s(balance: 1).announcement.contains("Use 1 min"))
        #expect(s("hello").announcement == "Add a few more words (5 to go)")
    }
}

@Suite struct AttachSelectionTests {
    @Test func selectionPersistsAcrossBothSourcesAndSumsUp() {
        var sel = AttachSelection(attached: 0)
        sel.setPhone(["p1", "p2", "p3", "p4"])
        #expect(sel.selected == 4 && sel.buttonTitle() == "Add 4" && sel.title() == "4 selected")
        for id in ["a", "b", "c"] { sel.toggleLibrary(id) }
        #expect(sel.selected == 7 && sel.buttonTitle() == "Add 7")
        #expect(sel.subline(minutes: 1) == "4 from this phone, 3 from My media. About 51 fit in 1 minute.")
        #expect(sel.libraryOrder("b") == 2 && sel.libraryOrder("zzz") == nil)
    }

    @Test func emptyAndSingleSourceSublines() {
        var sel = AttachSelection()
        #expect(sel.buttonTitle() == "Add" && sel.title() == "Nothing selected" && sel.subline(minutes: 1) == "Up to 100 photos. About 51 fit in 1 minute.")
        sel.setPhone(["p1", "p2", "p3", "p4"])
        #expect(sel.subline(minutes: 1) == "Up to 100 photos. About 51 fit in 1 minute.")
        sel.attached = 90
        #expect(sel.subline(minutes: 2) == "94 of 100 photos. About 102 fit in 2 minutes.")
    }

    @Test func theLimitIsSharedAndBlocksTheRest() {
        var sel = AttachSelection(attached: 20)
        sel.setPhone((0..<60).map { "p\($0)" })
        #expect(sel.phoneCap == 80 && sel.libraryCap == 20)
        for n in 0..<20 { let ok = sel.toggleLibrary("l\(n)"); #expect(ok) }
        #expect(sel.isFull && sel.total == 100 && sel.phoneCap == 60 && sel.libraryCap == 20)
        let blocked = sel.toggleLibrary("one-more")
        #expect(!blocked)                                   // blocked, the view explains why
        let freed = sel.toggleLibrary("l0")
        #expect(freed && !sel.isFull)                           // deselecting frees a slot
        sel.setPhone((0..<200).map { "q\($0)" })
        #expect(sel.phone.count == 61 && sel.total == 100)                         // the phone selection is clamped to what fits
    }
}

@Suite struct UploadJourneyTests {
    private func item(_ s: QueueItem.State, id: String? = nil) -> QueueItem {
        QueueItem(id: "i", file: "f", size: 10, sha256: "x", state: s, libraryID: id)
    }

    @Test func tileStatesFollowTheQueueItem() {
        func st(_ s: QueueItem.State, paused: Bool = false, offline: Bool = false, listed: Bool = false) -> UploadTileState { UploadTiles.state(of: item(s), paused: paused, offline: offline, listed: listed) }
        #expect(st(.queued) == .queued && st(.uploading) == .uploading && st(.failed) == .failed && st(.duplicate) == .alreadyThere)
        #expect(st(.done) == .processing && st(.done, listed: true) == .done)                 // done on the server, not listed yet: "Getting it ready"
        #expect(st(.queued, paused: true) == .waiting && st(.queued, offline: true) == .waiting && st(.noSpace) == .waiting)
        #expect(st(.uploading, paused: true) == .uploading)                                    // in-flight files finish
    }

    @Test func theBatchSettlesOnlyWhenEveryUploadedPhotoIsListed() {
        var a = item(.done, id: "L1"), b = item(.duplicate), c = item(.failed)
        a = QueueItem(id: "a", file: "f", size: 1, sha256: "a", state: .done, libraryID: "L1")
        b = QueueItem(id: "b", file: "f", size: 1, sha256: "b", state: .duplicate)
        c = QueueItem(id: "c", file: "f", size: 1, sha256: "c", state: .failed)
        #expect(!UploadTiles.isSettled([a, b, c], listedIDs: []))
        #expect(UploadTiles.isSettled([a, b, c], listedIDs: ["L1"]))
        #expect(!UploadTiles.isSettled([a, QueueItem(id: "d", file: "f", size: 1, sha256: "d", state: .uploading)], listedIDs: ["L1"]))
        #expect(!UploadTiles.isSettled([], listedIDs: []))
        #expect(UploadTiles.showsProcessingLabel(processingCount: 12) && !UploadTiles.showsProcessingLabel(processingCount: 13))
    }

    @Test func theBarSaysWhatIsHappening() throws {
        var p = QueueProgress(); p.total = 120; p.done = 38; p.queued = 70; p.uploading = 4; p.failed = 8; p.totalBytes = 1_200_000_000; p.doneBytes = 560_000_000
        let up = try #require(UploadBarState.make(p, gettingReady: 6, elapsed: 60))
        #expect(up.kind == .uploading && up.title == "Uploading 38 of 120" && up.subtitle.hasPrefix("640 MB left · about") && up.added == 38 && up.gettingReady == 6 && up.needYou == 8 && up.waiting == 74)
        p.paused = true
        #expect(UploadBarState.make(p)?.title == "Paused · 38 of 120" && UploadBarState.make(p)?.subtitle == "Pausing after the current photos")
        p.paused = false; p.lastError = "No connection."
        #expect(UploadBarState.make(p)?.kind == .offline && UploadBarState.make(p)?.title == "Waiting for a connection")
        #expect(UploadBarState.make(QueueProgress()) == nil)
    }

    @Test func storageFullAndAttentionStates() throws {
        var p = QueueProgress(); p.total = 100; p.done = 38; p.noSpace = 62
        let full = try #require(UploadBarState.make(p))
        #expect(full.kind == .storageFull && full.title == "Your storage is full" && full.subtitle.hasPrefix("62 photos are waiting."))
        var q = QueueProgress(); q.total = 10; q.done = 5; q.failed = 5
        #expect(UploadBarState.make(q)?.kind == .needsAttention && UploadBarState.make(q)?.title == "5 need you")
    }

    @Test func oneSummaryPerBatch() {
        var p = QueueProgress(); p.total = 132; p.done = 120; p.duplicates = 12
        #expect(UploadSummary.message(p) == .init(text: "120 photos added. 12 were already there.", action: "Got it"))
        p.duplicates = 0; p.total = 120
        #expect(UploadSummary.message(p)?.text == "120 photos added.")
        p.done = 108; p.failed = 5; p.total = 113
        #expect(UploadSummary.message(p) == .init(text: "108 photos added. 5 photos need your attention.", action: "Review"))
        var one = QueueProgress(); one.total = 1; one.done = 1
        #expect(UploadSummary.message(one)?.text == "1 photo added.")
        var dup = QueueProgress(); dup.total = 3; dup.duplicates = 3
        #expect(UploadSummary.message(dup)?.text == "3 were already there.")
        var running = QueueProgress(); running.total = 3; running.queued = 1
        #expect(UploadSummary.message(running) == nil)
    }
}

@Suite struct MakingProgressTests {
    @Test func fourStepsFillInOrderAndTheCurrentOneIsNamed() {
        let early = MakingProgress.info(stage: .writing, secondsInStage: 4, minutes: 3)
        #expect(early.current == 0 && early.segments[0] > 0 && early.segments[0] < 1 && early.segments[1] == 0)
        let mid = MakingProgress.info(stage: .voiceAndVisuals, secondsInStage: 40, minutes: 3)
        #expect(mid.segments[0] == 1 && mid.current >= 1 && mid.current <= 2 && mid.segments[3] == 0)
        let late = MakingProgress.info(stage: .rendering, secondsInStage: 30, minutes: 3)
        #expect(late.current == 3 && late.segments[0] == 1 && late.segments[1] == 1 && late.segments[2] == 1)
    }

    @Test func theLineIsHonestAboutWhatItKnows() {
        let l = MakingProgress.info(stage: .voiceAndVisuals, secondsInStage: 10, minutes: 3).line
        #expect(l.hasPrefix("Making voice and pictures") && l.contains("left.") && !l.contains("scene"))
        #expect(MakingProgress.info(stage: .rendering, secondsInStage: 1000, minutes: 1).line.hasSuffix("Less than a minute left."))
        #expect(MakingProgress.timeLeft(stage: .starting, secondsInStage: 0, minutes: 3).hasPrefix("About "))
    }
}

@Suite struct UploadAnnouncerTests {
    private func progress(done: Int, total: Int = 120) -> QueueProgress { var p = QueueProgress(); p.total = total; p.done = done; p.queued = total - done; return p }

    @Test func progressIsAggregatedAndRateLimited() {
        var a = UploadAnnouncer()
        let t0 = Date(timeIntervalSince1970: 1000)
        #expect(a.progressMessage(progress(done: 5), now: t0) == nil)                        // under 10 %
        #expect(a.progressMessage(progress(done: 12), now: t0) == "Uploaded 12 of 120 photos.")
        #expect(a.progressMessage(progress(done: 30), now: t0.addingTimeInterval(5)) == nil)    // enough photos but under 15 s
        #expect(a.progressMessage(progress(done: 30), now: t0.addingTimeInterval(16)) == "Uploaded 30 of 120 photos.")
        #expect(a.progressMessage(progress(done: 33), now: t0.addingTimeInterval(60)) == nil)   // under another 10 %
    }

    @Test func stateChangesAreSaidOnceAndNeverForPlainProgress() {
        var a = UploadAnnouncer()
        var p = progress(done: 10)
        #expect(a.stateMessage(UploadBarState.make(p)) == nil)
        p.paused = true
        #expect(a.stateMessage(UploadBarState.make(p)) == "Upload paused")
        #expect(a.stateMessage(UploadBarState.make(p)) == nil)
        p.paused = false; p.lastError = "x"
        #expect(a.stateMessage(UploadBarState.make(p)) == "Waiting for connection")
        var full = QueueProgress(); full.total = 5; full.noSpace = 5
        #expect(a.stateMessage(UploadBarState.make(full)) == "Storage is full")
    }
}

@Suite struct OrganizeTests {
    private func group(_ name: String, _ n: Int, existing: Bool = false) -> OrganizeGroup { OrganizeGroup(name: name, count: n, existing: existing, sampleIDs: ["a", "b", "c"]) }

    @Test func thePolicyFollowsThePreferenceAndTheThreshold() {
        #expect(OrganizePolicy.decide(pref: .ask, ready: 29) == .nothing && OrganizePolicy.decide(pref: .ask, ready: 30) == .showSheet && OrganizePolicy.decide(pref: .ask, ready: 842) == .showSheet)
        #expect(OrganizePolicy.decide(pref: .always, ready: 10) == .runSilently && OrganizePolicy.decide(pref: .always, ready: 299) == .runSilently && OrganizePolicy.decide(pref: .always, ready: 300) == .runWithProgress)
        #expect(OrganizePolicy.decide(pref: .never, ready: 5000) == .nothing)
    }

    @Test func sinceIsUtcAndAMinuteBeforeTheBatchStarted() {
        let start = Date(timeIntervalSince1970: 1_800_000_060)       // 2027-01-15T08:01:00Z
        #expect(OrganizeSince.stamp(batchStart: start) == "2027-01-15T08:00:00")
    }

    @Test func thePreferenceMapsToTheSwitchBothWays() throws {
        #expect(OrganizePref.always.switchIsOn && !OrganizePref.ask.switchIsOn && !OrganizePref.never.switchIsOn)
        #expect(OrganizePref.fromSwitch(true) == .always && OrganizePref.fromSwitch(false) == .ask)
        #expect(try JSONDecoder().decode(LibraryPrefs.self, from: Data(#"{"organize":"weird"}"#.utf8)).organize == .ask)
        #expect(try JSONDecoder().decode(LibrarySummary.self, from: Data(#"{"limit_bytes":1,"used_bytes":0,"prefs":{"organize":"always"}}"#.utf8)).prefs.organize == .always)
        #expect(try JSONDecoder().decode(LibrarySummary.self, from: Data(#"{"limit_bytes":1,"used_bytes":0}"#.utf8)).prefs.organize == .ask)
    }

    @Test func modelsDecodeThePreviewTheApplyAnswerAndTheAutoFlag() throws {
        let p = try JSONDecoder().decode(OrganizePreview.self, from: Data(#"{"total":842,"organized":805,"skipped":37,"home":"London","groups":[{"name":"London · Apr 2026","count":214,"existing":true,"sample_ids":["a","b"]},{"name":"Jun 2025","count":52}]}"#.utf8))
        #expect(p.total == 842 && p.skipped == 37 && p.groups[0].existing && p.groups[0].sampleIDs == ["a", "b"] && !p.groups[1].existing && p.groups[1].sampleIDs.isEmpty)
        let r = try JSONDecoder().decode(OrganizeApplyResult.self, from: Data(#"{"collection_id":"c9","applied":300,"remaining":505,"created":1}"#.utf8))
        #expect(r.collectionID == "c9" && r.remaining == 505 && r.updated == 0)
        let c = try JSONDecoder().decode(LibraryCollection.self, from: Data(#"{"id":"x","name":"London · Apr 2026","count":3,"auto":true}"#.utf8))
        #expect(c.auto)
        #expect(try JSONDecoder().decode(LibraryCollection.self, from: Data(#"{"id":"x","name":"n"}"#.utf8)).auto == false)
    }

    @Test func suggestedNamesUseTheMainPlaceAndTheDateRange() {
        let thailand = [group("Phuket · 14-21 Jul 2024", 188), group("Bangkok · 3-6 Aug 2024", 12)]
        #expect(SuggestedNames.suggest(groups: thailand) == ["Phuket Aug 2024", "Jul 2024 - Aug 2024"])
        let spread = [group("London · Apr 2026", 214), group("London · May 2026", 71), group("London · Jul 2026", 60), group("Jun 2025", 52)]
        let s = SuggestedNames.suggest(groups: spread)
        #expect(s.first == "London 2026" && s.last == "Jun 2025 - Jul 2026")                     // spans more than 2 months: place and year
        #expect(SuggestedNames.suggest(groups: [group("May 2026", 80), group("Jun 2026", 70)]) == ["May 2026 - Jun 2026"])   // no place: only the range
        #expect(SuggestedNames.suggest(groups: [group("Lisbon · 3-6 Oct 2025", 40), group("Rome · 8-10 Oct 2025", 40), group("Paris · 20-24 Oct 2025", 40)]) == ["Oct 2025"])   // no place above 60 %
        #expect(SuggestedNames.suggest(groups: []).isEmpty)
        #expect(SuggestedNames.isValid("Thailand") && !SuggestedNames.isValid("  ") && !SuggestedNames.isValid(String(repeating: "a", count: 61)))
    }

    @Test func theLoopCallsApplyUntilNothingRemainsWithRealProgress() async throws {
        let api = FakeLibraryAPI()
        await api.setOrganizeScript(OrganizePreview(total: 842, organized: 805, skipped: 37, groups: [group("London · Apr 2026", 600), group("Jun 2025", 205)]))
        let runner = OrganizeRunner(api: api)
        let seen = Seen()
        await runner.setObserver { j in if let j { Task { await seen.add(j.done) } } }
        await runner.start(mode: .auto, since: "2026-11-25T08:00:00", total: 805)
        for _ in 0..<400 { if await runner.job?.state == .finished { break }; try? await Task.sleep(for: .milliseconds(5)) }
        let job = try #require(await runner.job)
        #expect(job.state == .finished && job.done == 805 && job.remaining == 0 && job.created == 2)
        let calls = await api.organizeCalls
        #expect(calls.count == 3 && calls.allSatisfy { $0.mode == "auto" && $0.since == "2026-11-25T08:00:00" })       // 300 + 300 + 205
        try await Task.sleep(for: .milliseconds(30))
        let done = await seen.values
        #expect(done.contains(300) && done.contains(600) && done.last == 805 && done == done.sorted())
        #expect(OrganizeSummary.message(job) == .init(text: "Organized into 2 collections", action: "View"))
    }

    @Test func singleModeKeepsFillingTheSameCollection() async throws {
        let api = FakeLibraryAPI()
        await api.setOrganizeScript(OrganizePreview(total: 700, organized: 700, skipped: 0, groups: [group("Jun 2025", 700)]))
        let runner = OrganizeRunner(api: api)
        await runner.start(mode: .single, since: nil, name: "Thailand Jul 2024", total: 700)
        for _ in 0..<400 { if await runner.job?.state == .finished { break }; try? await Task.sleep(for: .milliseconds(5)) }
        let calls = await api.organizeCalls
        #expect(calls.count == 3 && calls[0].collectionID == nil && calls[1].collectionID != nil && calls[1].collectionID == calls[2].collectionID && calls.allSatisfy { $0.name == "Thailand Jul 2024" })
        #expect(OrganizeSummary.message(try #require(await runner.job))?.text == "Organized into 1 collection")
        let made = try await api.collections().filter { $0.name == "Thailand Jul 2024" }
        #expect(made.count == 1)
    }

    @Test func cancelStopsAndKeepsWhatWasMade() async throws {
        let api = FakeLibraryAPI()
        await api.setOrganizeScript(OrganizePreview(total: 9000, organized: 9000, skipped: 0, groups: [group("Jun 2025", 9000)]), chunk: 100)
        await api.setOrganizeDelay(.milliseconds(20))
        let runner = OrganizeRunner(api: api)
        await runner.start(mode: .auto, since: nil, total: 9000)
        try await Task.sleep(for: .milliseconds(70))
        await runner.cancel()
        let job = try #require(await runner.job)
        #expect(job.state == .cancelled && job.remaining > 0)
        let before = await api.organizeCalls.count
        try await Task.sleep(for: .milliseconds(60))
        let after = await api.organizeCalls.count
        #expect(before == after)                                                    // nothing is called after Stop
        #expect(try await api.collections().contains { $0.auto })                   // the collection made so far stays
        #expect(OrganizeBarState.make(job) == nil)
    }

    @Test func offlinePausesAndResumesByItself() async throws {
        let api = FakeLibraryAPI()
        await api.setOrganizeScript(OrganizePreview(total: 400, organized: 400, skipped: 0, groups: [group("Jun 2025", 400)]))
        await api.setFailNext(.network)
        let runner = OrganizeRunner(api: api, backoff: .milliseconds(10))
        await runner.start(mode: .auto, since: nil, total: 400)
        var sawWaiting = false
        for _ in 0..<400 { let s = await runner.job?.state; if s == .waiting { sawWaiting = true }; if s == .finished { break }; try? await Task.sleep(for: .milliseconds(2)) }
        let job = try #require(await runner.job)
        #expect(sawWaiting && job.state == .finished && job.remaining == 0)
    }

    @Test func aServerErrorStopsWithTryAgainAndRetryContinues() async throws {
        let api = FakeLibraryAPI()
        await api.setOrganizeScript(OrganizePreview(total: 400, organized: 400, skipped: 0, groups: [group("Jun 2025", 400)]))
        await api.setFailNext(.server)
        let runner = OrganizeRunner(api: api)
        await runner.start(mode: .auto, since: nil, total: 400)
        for _ in 0..<200 { if await runner.job?.state == .failed { break }; try? await Task.sleep(for: .milliseconds(5)) }
        let failed = try #require(await runner.job)
        #expect(failed.state == .failed && OrganizeBarState.make(failed)?.title == "Couldn't finish organizing")
        await runner.retry()
        for _ in 0..<200 { if await runner.job?.state == .finished { break }; try? await Task.sleep(for: .milliseconds(5)) }
        #expect(await runner.job?.state == .finished)
    }

    @Test func aKilledAppResumesTheJobFromDisk() async throws {
        let file = FileManager.default.temporaryDirectory.appendingPathComponent("org-\(UUID()).json")
        let api = FakeLibraryAPI()
        await api.setOrganizeScript(OrganizePreview(total: 600, organized: 600, skipped: 0, groups: [group("Jun 2025", 600)]))
        var saved = OrganizeJob(mode: .auto, since: "2026-11-25T08:00:00", total: 600); saved.remaining = 300
        try JSONEncoder().encode(saved).write(to: file)
        let runner = OrganizeRunner(api: api, file: file)
        let loaded = await runner.job
        #expect(loaded?.done == 300 && OrganizeBarState.make(loaded)?.subtitle == "You can leave this screen.")
        await runner.resumeIfNeeded()
        #expect(OrganizeBarState.make(await runner.job)?.title.hasPrefix("Resuming…") == true)
        for _ in 0..<400 { if await runner.job?.state == .finished { break }; try? await Task.sleep(for: .milliseconds(5)) }
        #expect(await runner.job?.state == .finished && !FileManager.default.fileExists(atPath: file.path))   // done: the file is gone
        let calls = await api.organizeCalls
        #expect(calls.first?.since == "2026-11-25T08:00:00")
    }

    @Test func barTextsAreReal() {
        var j = OrganizeJob(mode: .auto, since: nil, total: 9800); j.remaining = 8600
        #expect(OrganizeBarState.make(j)?.title == "Organizing… 1,200 of 9,800" && OrganizeBarState.make(j)?.subtitle == "You can leave this screen.")
        #expect(OrganizeBarState.make(j, uploadActive: true)?.subtitle == "Organizing after the upload")
        j.state = .waiting
        #expect(OrganizeBarState.make(j)?.title == "Waiting for a connection" && OrganizeBarState.make(j)?.subtitle == "1,200 of 9,800 organized")
        var done = j; done.state = .finished; done.created = 14; done.updated = 0
        #expect(OrganizeSummary.message(done) == .init(text: "Organized into 14 collections", action: "View"))
        done.created = 1
        #expect(OrganizeSummary.message(done)?.text == "Organized into 1 collection")
        done.created = 0
        #expect(OrganizeSummary.message(done) == .init(text: "Everything is already organized", action: nil))
    }

    @Test func announcementsAreAggregated() {
        var a = OrganizeAnnouncer()
        var j = OrganizeJob(mode: .auto, since: nil, total: 9800)
        let t0 = Date(timeIntervalSince1970: 5000)
        j.remaining = 9600
        #expect(a.message(j, now: t0) == nil)
        j.remaining = 8600
        #expect(a.message(j, now: t0) == "Organized 1,200 of 9,800 photos")
        j.remaining = 7000
        #expect(a.message(j, now: t0.addingTimeInterval(3)) == nil)
        #expect(a.message(j, now: t0.addingTimeInterval(20)) == "Organized 2,800 of 9,800 photos")
        j.state = .waiting
        #expect(a.message(j, now: t0.addingTimeInterval(40)) == "Waiting for a connection")
        #expect(a.message(j, now: t0.addingTimeInterval(41)) == nil)
    }
}

@Suite struct SelectAllTests {
    private let view = (1...38).map { "p\($0)" }

    @Test func labelsSayWhatWillHappen() {
        #expect(SelectAll.label(viewCount: 38, hasMore: false, allSelected: false) == "Select all 38")
        #expect(SelectAll.label(viewCount: 60, hasMore: true, allSelected: false) == "Select all (up to 100)")
        #expect(SelectAll.label(viewCount: 38, hasMore: false, allSelected: true) == "Clear")
    }

    @Test func everythingInViewIsAddedAndKeepsWhatWasChosenBefore() {
        let r = SelectAll.apply(view: view, selected: ["p3", "other"], room: 100)
        #expect(r.selected.count == 39 && r.selected.prefix(2) == ["p3", "other"] && !r.limited && SelectAll.allSelected(view: view, selected: r.selected))
        #expect(SelectAll.allSelected(view: view, selected: r.selected) && !SelectAll.allSelected(view: view, selected: ["p1"]) && !SelectAll.allSelected(view: [], selected: ["p1"]))
    }

    @Test func theLimitStopsItAndSaysSo() {
        let big = (1...150).map { "q\($0)" }
        let r = SelectAll.apply(view: big, selected: [], room: 100)
        #expect(r.selected.count == 100 && r.limited && r.selected.last == "q100")                 // the first 100, in order
        // 30 photos already chosen from the phone: only 70 more fit
        let mixed = SelectAll.apply(view: big, selected: [], room: AttachSelection(attached: 0, phone: (1...30).map { "ph\($0)" }).libraryCap)
        #expect(mixed.selected.count == 70 && mixed.limited)
        #expect(SelectAll.limitNote == "Selected the first 100: the limit for one video")
        let exact = SelectAll.apply(view: view, selected: [], room: 38)
        #expect(exact.selected.count == 38 && !exact.limited)                                       // it fits exactly: no note
    }

    @Test func clearTakesBackOnlyWhatIsInView() {
        let all = SelectAll.apply(view: view, selected: ["elsewhere"], room: 100).selected
        #expect(SelectAll.clear(view: view, selected: all) == ["elsewhere"])
    }
}
