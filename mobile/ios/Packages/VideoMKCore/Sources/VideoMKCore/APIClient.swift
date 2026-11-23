import Foundation

public enum APIError: Error, Equatable, Sendable {
    case unauthorized
    case invalid(String)
    case quota(String)
    case notReady(VideoStatus)
    case network
    case server

    public var message: String {
        switch self {
        case .unauthorized: "Your session expired. Please sign in again."
        case .invalid(let m), .quota(let m): m
        case .notReady: "This video isn't ready yet."
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

    public init(config: AppConfig, auth: any AuthorizationProviding, session: URLSession = .shared, appVersion: String = "0") {
        self.config = config; self.auth = auth; self.session = session; self.appVersion = appVersion
    }

    public func listVideos() async throws -> [VideoItem] {
        let (data, _) = try await send("GET", ["videos"])
        return try decode(VideoListResponse.self, data).items
    }

    /// A presigned MP4 URL. Throws `.notReady` (with the current status) while the video is still being made.
    public func playbackURL(videoID: String) async throws -> URL {
        let (data, _) = try await send("GET", ["videos", videoID])
        guard let url = URL(string: try decode(PlaybackResponse.self, data).url) else { throw APIError.server }
        return url
    }

    /// `clientRequestID` makes a retry of the same attempt idempotent (no double charge, no second video).
    public func startGeneration(prompt: String, clientRequestID: String, options: CreateOptions = CreateOptions()) async throws -> String {
        var fields: [String: Any] = ["prompt": Brief.normalized(prompt), "client_request_id": clientRequestID, "target_minutes": options.minutes]
        if let look = options.look { fields["theme"] = look.rawValue }
        let body = try JSONSerialization.data(withJSONObject: fields)
        let (data, _) = try await send("POST", ["videos", "generate"], body: body)
        return try decode(StartResponse.self, data).videoID
    }

    // MARK: - plumbing

    private func send(_ method: String, _ path: [String], body: Data? = nil) async throws -> (Data, HTTPURLResponse) {
        let (token, userID) = try await auth.authorization()
        var url = config.apiBase.appendingPathComponent("users").appendingPathComponent(userID)
        for p in path { url.appendPathComponent(p) }
        var req = URLRequest(url: url, timeoutInterval: 30)
        req.httpMethod = method
        req.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        req.setValue("ios", forHTTPHeaderField: "X-Platform")
        req.setValue(appVersion, forHTTPHeaderField: "X-App-Version")
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
        case 409: throw APIError.notReady(VideoStatus(serverStatus: (try? JSONDecoder().decode(MessageResponse.self, from: data))?.status ?? ""))
        case 429: throw APIError.quota(Self.message(data) ?? "You've reached today's limit. Try again tomorrow.")
        default: throw APIError.server
        }
    }

    private static func message(_ data: Data) -> String? { (try? JSONDecoder().decode(MessageResponse.self, from: data))?.message }

    private func decode<T: Decodable>(_ type: T.Type, _ data: Data) throws -> T {
        do { return try JSONDecoder().decode(type, from: data) } catch { throw APIError.server }
    }
}
