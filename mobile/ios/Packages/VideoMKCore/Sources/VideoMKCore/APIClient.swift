import Foundation

public enum APIError: Error, Equatable, Sendable {
    case unauthorized
    case invalid(String)
    case quota(String)
    case notReady(VideoStatus)
    /// The video changed since it was loaded, or a render is already running (editor only).
    case conflict(String)
    case network
    case server
    case insufficientCredits(balance: Int, needed: Int)
    /// The safety check stopped the request. Nothing was charged.
    case blocked(String)
    /// Creation is paused for this account for a while.
    case paused(String, retryAfter: Int?)

    public var message: String {
        switch self {
        case .unauthorized: tr("err.session_expired")
        case .invalid(let m), .quota(let m): m
        case .notReady: tr("err.video_not_ready")
        case .conflict(let m): m
        case .insufficientCredits(let have, let need): tr("err.insufficient_credits", need, have)
        case .blocked(let m): m
        case .paused(let m, _): m
        case .network: tr("err.network")
        case .server: tr("err.server")
        }
    }
}

public enum RetryResult: Equatable, Sendable {
    case started(photos: Int?, unusable: Int)
    case alreadyRunning
    case unsupported
    case refused(code: String, message: String)
}

public protocol AuthorizationProviding: Sendable {
    /// A valid ID token (refreshed if needed) and the user id (the token's `sub`).
    func authorization() async throws -> (idToken: String, userID: String)
}

public struct APIClient: Sendable {
    private let config: AppConfig
    private let auth: any AuthorizationProviding
    private let session: URLSession
    private let appVersion: String
    private let region: @Sendable () -> String?
    private let locale: @Sendable () -> String
    /// `region`: the device's region setting (ISO country code). The server uses it only to pick a default voice accent.
    public init(config: AppConfig, auth: any AuthorizationProviding, session: URLSession = .shared, appVersion: String = "0",
                region: @escaping @Sendable () -> String? = { Locale.current.region?.identifier },
                locale: @escaping @Sendable () -> String = { Localization.shared.headerValue }) {
        self.config = config; self.auth = auth; self.session = session; self.appVersion = appVersion; self.region = region; self.locale = locale
    }

    public func requestUploads(count: Int) async throws -> [UploadSlot] {
        let body = try JSONSerialization.data(withJSONObject: ["count": count])
        let (data, _) = try await send("POST", ["uploads"], body: body)
        return try decode(UploadSlotsResponse.self, data).uploads
    }

    public func wallet() async throws -> WalletInfo {
        let (data, _) = try await send("GET", ["wallet"])
        return try decode(WalletInfo.self, data)
    }

    public func listVideos() async throws -> [VideoItem] {
        let (data, _) = try await send("GET", ["videos"])
        return try decode(VideoListResponse.self, data).items
    }

    /// What the server says about a video while it is being made, from the video's own status answer (the body of the 200 or of the 409 "not ready yet").
    /// nil when the server does not send `making` (older servers) or the answer cannot be read: the screen then keeps its calm fallback.
    public func makingInfo(videoID: String) async throws -> MakingInfo? {
        let (data, _) = try await perform("GET", ["videos", videoID])
        return MakingInfo.fromStatusBody(data)
    }

    /// A presigned MP4 URL. Throws `.notReady` (with the current status) while the video is still being made.
    public func playbackURL(videoID: String) async throws -> URL { try await playback(videoID: videoID).url }

    public func playback(videoID: String) async throws -> PlaybackInfo {
        let (data, _) = try await send("GET", ["videos", videoID])
        let r = try decode(PlaybackResponse.self, data)
        guard let url = URL(string: r.url) else { throw APIError.server }
        return PlaybackInfo(url: url, description: r.description)
    }

    /// `clientRequestID` makes a retry of the same attempt idempotent (no double charge, no second video).
    public func startGeneration(prompt: String, clientRequestID: String, options: CreateOptions = CreateOptions(), media: [String] = [], mediaMeta: [String: PhotoMeta] = [:], libraryMedia: [String] = [], brief: [String: String]? = nil, deck: String? = nil, sendMinutes: Bool = true) async throws -> String {
        var fields: [String: Any] = ["client_request_id": clientRequestID]
        // a presentation: the prompt is optional (who it is for) and the length is only sent when the person chose one (absent: the deck's own, charged exactly that)
        if deck == nil || Brief.isValid(prompt) { fields["prompt"] = Brief.normalized(prompt) }
        if sendMinutes { fields["target_minutes"] = options.minutes }
        if let deck { fields["deck"] = deck }
        if !media.isEmpty { fields["media"] = media }
        if !libraryMedia.isEmpty { fields["library_media"] = libraryMedia }
        let meta = mediaMeta.filter { media.contains($0.key) && !$0.value.isEmpty }.mapValues(\.json).filter { !$0.value.isEmpty }
        if !meta.isEmpty { fields["media_meta"] = meta }
        if let look = options.look { fields["theme"] = look.rawValue }
        if !options.captions { fields["captions"] = false }   // on is the server default: only the choice to turn them off is sent
        fields["platform"] = options.platform; fields["aspect"] = options.aspect; fields["resolution"] = options.resolution
        if options.language != "auto" { fields["language"] = options.language }
        if let brief, !brief.isEmpty { fields["brief"] = brief }
        let body = try JSONSerialization.data(withJSONObject: fields)
        let (data, _) = try await send("POST", ["videos", "generate"], body: body)
        return try decode(StartResponse.self, data).videoID
    }

    /// "Try again" on a video that did not finish: the SAME video starts again on the server with everything it was made with (photos, options, language, watermark), no second row.
    /// Never resends anything from the phone. `.unsupported` is an older server without the route: the caller must not rebuild the request (that would drop the attachments).
    public func retryVideo(videoID: String) async throws -> RetryResult {
        let (data, http) = try await perform("POST", ["videos", videoID, "retry"])
        return try RetryRules.result(status: http.statusCode, body: data)
    }

    /// Removes a video that did not finish (failed, cancelled or refused). A made video is never deleted here (409). False: the server does not have the route.
    public func deleteVideo(videoID: String) async throws -> Bool {
        let (data, http) = try await perform("DELETE", ["videos", videoID])
        return try RetryRules.removed(status: http.statusCode, body: data)
    }

    // MARK: editor

    public func editorSnapshot(videoID: String) async throws -> EditorSnapshot {
        let (data, _) = try await send("GET", ["videos", videoID, "plan"], conflictIsEdit: true)
        return try decode(EditorSnapshot.self, data)
    }

    /// Returns the new revision. Throws `.conflict` when the base revision is stale or a render is running.
    public func applyEdits(videoID: String, baseRev: Int, ops: [EditOp], mode: RenderMode) async throws -> Int {
        let body = try JSONSerialization.data(withJSONObject: ["base_rev": baseRev, "ops": ops.map(\.json), "mode": mode.rawValue] as [String: Any])
        let (data, _) = try await send("POST", ["videos", videoID, "edits"], body: body, conflictIsEdit: true)
        struct R: Decodable { let rev: Int }
        return try decode(R.self, data).rev
    }

    // MARK: - plumbing

    /// The authenticated request without any status mapping: only a missing session or a network failure throws. The library client maps statuses itself.
    func perform(_ method: String, _ path: [String], query: [URLQueryItem] = [], body: Data? = nil) async throws -> (Data, HTTPURLResponse) {
        let (token, userID) = try await auth.authorization()
        var url = config.apiBase.appendingPathComponent("users").appendingPathComponent(userID)
        for p in path { url.appendPathComponent(p) }
        if !query.isEmpty, var c = URLComponents(url: url, resolvingAgainstBaseURL: false) { c.queryItems = query; url = c.url ?? url }
        var req = URLRequest(url: url, timeoutInterval: 30)
        req.httpMethod = method
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("ios", forHTTPHeaderField: "X-Platform")
        req.setValue(appVersion, forHTTPHeaderField: "X-App-Version")
        req.setValue(TimeZone.current.identifier, forHTTPHeaderField: "X-Timezone")  // where the user's day ends, for the daily free credits
        if let region = region(), region.count == 2 { req.setValue(region.uppercased(), forHTTPHeaderField: "X-Region") }
        req.setValue(locale(), forHTTPHeaderField: "X-Locale")   // the app language (en|es): the server answers in it (docs/I18N.md)
        if let body { req.httpBody = body; req.setValue("application/json", forHTTPHeaderField: "Content-Type") }

        let data: Data, resp: URLResponse
        do { (data, resp) = try await session.data(for: req) }
        catch is CancellationError { throw CancellationError() }
        catch { throw APIError.network }
        guard let http = resp as? HTTPURLResponse else { throw APIError.server }
        return (data, http)
    }

    private func send(_ method: String, _ path: [String], body: Data? = nil, conflictIsEdit: Bool = false) async throws -> (Data, HTTPURLResponse) {
        let (data, http) = try await perform(method, path, body: body)

        switch http.statusCode {
        case 200..<300: return (data, http)
        case 401, 403: throw APIError.unauthorized
        case 400:
            if (try? JSONDecoder().decode(MessageResponse.self, from: data))?.status == "blocked" { throw APIError.blocked(Self.message(data) ?? tr("err.blocked")) }
            throw APIError.invalid(Self.message(data) ?? tr("err.brief_invalid"))
        case 409 where conflictIsEdit: throw APIError.conflict(Self.message(data) ?? tr("err.video_changed"))
        case 409: throw APIError.notReady(VideoStatus(serverStatus: (try? JSONDecoder().decode(MessageResponse.self, from: data))?.status ?? ""))
        case 402:
            struct Short: Decodable { let balance: Int?; let needed: Int? }
            let s = try? JSONDecoder().decode(Short.self, from: data)
            throw APIError.insufficientCredits(balance: s?.balance ?? 0, needed: s?.needed ?? 1)
        case 429:
            struct Paused: Decodable { let status: String?; let message: String?; let retry_after: Int? }
            if let p = try? JSONDecoder().decode(Paused.self, from: data), p.status == "paused" { throw APIError.paused(p.message ?? tr("err.paused"), retryAfter: p.retry_after) }
            throw APIError.quota(Self.message(data) ?? tr("err.daily_limit"))
        default: throw APIError.server
        }
    }

    private static func message(_ data: Data) -> String? { (try? JSONDecoder().decode(MessageResponse.self, from: data))?.message }

    private func decode<T: Decodable>(_ type: T.Type, _ data: Data) throws -> T {
        do { return try JSONDecoder().decode(type, from: data) } catch { throw APIError.server }
    }
}
