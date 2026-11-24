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

    public var message: String {
        switch self {
        case .unauthorized: "Your session expired. Please sign in again."
        case .invalid(let m), .quota(let m): m
        case .notReady: "This video isn't ready yet."
        case .conflict(let m): m
        case .insufficientCredits(let have, let need): "This video needs \(need) credit\(need == 1 ? "" : "s") and you have \(have)."
        case .network: "Network problem. Check your connection and try again."
        case .server: "Something went wrong on our side. Please try again."
        }
    }
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

    /// `region`: the device's region setting (ISO country code). The server uses it only to pick a default voice accent.
    public init(config: AppConfig, auth: any AuthorizationProviding, session: URLSession = .shared, appVersion: String = "0",
                region: @escaping @Sendable () -> String? = { Locale.current.region?.identifier }) {
        self.config = config; self.auth = auth; self.session = session; self.appVersion = appVersion; self.region = region
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

    /// A presigned MP4 URL. Throws `.notReady` (with the current status) while the video is still being made.
    public func playbackURL(videoID: String) async throws -> URL { try await playback(videoID: videoID).url }

    public func playback(videoID: String) async throws -> PlaybackInfo {
        let (data, _) = try await send("GET", ["videos", videoID])
        let r = try decode(PlaybackResponse.self, data)
        guard let url = URL(string: r.url) else { throw APIError.server }
        return PlaybackInfo(url: url, description: r.description)
    }

    /// `clientRequestID` makes a retry of the same attempt idempotent (no double charge, no second video).
    public func startGeneration(prompt: String, clientRequestID: String, options: CreateOptions = CreateOptions(), media: [String] = []) async throws -> String {
        var fields: [String: Any] = ["prompt": Brief.normalized(prompt), "client_request_id": clientRequestID, "target_minutes": options.minutes]
        if !media.isEmpty { fields["media"] = media }
        if let look = options.look { fields["theme"] = look.rawValue }
        if !options.captions { fields["captions"] = false }   // on is the server default: only the choice to turn them off is sent
        let body = try JSONSerialization.data(withJSONObject: fields)
        let (data, _) = try await send("POST", ["videos", "generate"], body: body)
        return try decode(StartResponse.self, data).videoID
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

    private func send(_ method: String, _ path: [String], body: Data? = nil, conflictIsEdit: Bool = false) async throws -> (Data, HTTPURLResponse) {
        let (token, userID) = try await auth.authorization()
        var url = config.apiBase.appendingPathComponent("users").appendingPathComponent(userID)
        for p in path { url.appendPathComponent(p) }
        var req = URLRequest(url: url, timeoutInterval: 30)
        req.httpMethod = method
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("ios", forHTTPHeaderField: "X-Platform")
        req.setValue(appVersion, forHTTPHeaderField: "X-App-Version")
        req.setValue(TimeZone.current.identifier, forHTTPHeaderField: "X-Timezone")  // where the user's day ends, for the daily free credits
        if let region = region(), region.count == 2 { req.setValue(region.uppercased(), forHTTPHeaderField: "X-Region") }
        if let body { req.httpBody = body; req.setValue("application/json", forHTTPHeaderField: "Content-Type") }

        let data: Data, resp: URLResponse
        do { (data, resp) = try await session.data(for: req) }
        catch is CancellationError { throw CancellationError() }
        catch { throw APIError.network }
        guard let http = resp as? HTTPURLResponse else { throw APIError.server }

        switch http.statusCode {
        case 200..<300: return (data, http)
        case 401, 403: throw APIError.unauthorized
        case 400: throw APIError.invalid(Self.message(data) ?? "That brief can't be used.")
        case 409 where conflictIsEdit: throw APIError.conflict(Self.message(data) ?? "This video changed. Reload to continue.")
        case 409: throw APIError.notReady(VideoStatus(serverStatus: (try? JSONDecoder().decode(MessageResponse.self, from: data))?.status ?? ""))
        case 402:
            struct Short: Decodable { let balance: Int?; let needed: Int? }
            let s = try? JSONDecoder().decode(Short.self, from: data)
            throw APIError.insufficientCredits(balance: s?.balance ?? 0, needed: s?.needed ?? 1)
        case 429: throw APIError.quota(Self.message(data) ?? "You've reached today's limit. Try again tomorrow.")
        default: throw APIError.server
        }
    }

    private static func message(_ data: Data) -> String? { (try? JSONDecoder().decode(MessageResponse.self, from: data))?.message }

    private func decode<T: Decodable>(_ type: T.Type, _ data: Data) throws -> T {
        do { return try JSONDecoder().decode(type, from: data) } catch { throw APIError.server }
    }
}
