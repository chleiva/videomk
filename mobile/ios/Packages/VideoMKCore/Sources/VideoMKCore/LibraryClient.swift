import Foundation

/// Everything the Media tab needs from the server. Real: `LibraryClient`. Tests and previews: `FakeLibraryAPI`.
public protocol LibraryAPI: Sendable {
    func summary() async throws -> LibrarySummary
    func requestUploads(_ items: [UploadRequestItem]) async throws -> UploadsResponse
    func items(limit: Int, cursor: String?, filter: ItemsFilter) async throws -> ItemsPage
    func item(id: String) async throws -> LibraryPhoto
    func delete(ids: [String]) async throws -> DeleteResult
    func search(query: String, limit: Int?, drop: [String], cursor: String?) async throws -> SearchResponse
    func collections() async throws -> [LibraryCollection]
    func createCollection(name: String, emoji: String?) async throws -> LibraryCollection
    func updateCollection(id: String, name: String?, emoji: String?) async throws -> LibraryCollection
    func deleteCollection(id: String) async throws
    func editCollection(id: String, add: [String], remove: [String]) async throws
}

/// Posts a file to a presigned S3 form. Separate from `LibraryAPI` because it never carries the login token.
public protocol FilePosting: Sendable {
    func post(_ file: Data, to url: URL, fields: [String: String]) async throws
}

public struct S3FilePoster: FilePosting {
    let session: URLSession
    public init(session: URLSession = .shared) { self.session = session }
    public func post(_ file: Data, to url: URL, fields: [String: String]) async throws {
        var req = URLRequest(url: url, timeoutInterval: 120)
        req.httpMethod = "POST"
        let form = MultipartForm.body(fields: fields, file: file)     // the file is the LAST part, as S3 requires
        req.setValue(form.contentType, forHTTPHeaderField: "Content-Type")
        // deliberately no Authorization header: the presigned fields are the credential
        do {
            let (_, resp) = try await session.upload(for: req, from: form.body)
            guard let code = (resp as? HTTPURLResponse)?.statusCode, (200..<300).contains(code) else { throw LibraryAPIError.server }
        } catch let e as LibraryAPIError { throw e }
        catch is CancellationError { throw CancellationError() }
        catch { throw LibraryAPIError.network }
    }
}

public struct LibraryClient: LibraryAPI {
    let api: APIClient
    public init(api: APIClient) { self.api = api }

    private func call<T: Decodable>(_ method: String, _ path: [String], query: [URLQueryItem] = [], body: (any Encodable)? = nil, as type: T.Type = T.self) async throws -> T {
        let data = try await raw(method, path, query: query, body: body)
        do { return try JSONDecoder().decode(T.self, from: data) } catch { throw LibraryAPIError.server }
    }

    private func raw(_ method: String, _ path: [String], query: [URLQueryItem] = [], body: (any Encodable)? = nil) async throws -> Data {
        let payload = try body.map { try JSONEncoder().encode(AnyEncodable($0)) }
        let data: Data, http: HTTPURLResponse
        do { (data, http) = try await api.perform(method, ["library"] + path, query: query, body: payload) }
        catch let e as APIError { throw e == .network ? LibraryAPIError.network : e == .unauthorized ? LibraryAPIError.unauthorized : LibraryAPIError.server }
        switch http.statusCode {
        case 200..<300: return data
        case 400: throw LibraryAPIError.invalid(((try? JSONDecoder().decode(MessageResponse.self, from: data))?.message) ?? "That request can't be used.")
        case 401, 403: throw LibraryAPIError.unauthorized
        case 404: throw LibraryAPIError.notFound
        case 409: throw LibraryAPIError.conflict
        case 413: throw LibraryAPIError.tooLarge
        case 429: throw LibraryAPIError.rateLimited(retryAfter: http.value(forHTTPHeaderField: "Retry-After").flatMap { Int($0) })
        case 402:
            struct Full: Decodable { let used_bytes: Int?; let limit_bytes: Int? }
            let f = try? JSONDecoder().decode(Full.self, from: data)
            throw LibraryAPIError.storageFull(usedBytes: f?.used_bytes ?? 0, limitBytes: f?.limit_bytes ?? 0)
        default: throw LibraryAPIError.server
        }
    }

    public func summary() async throws -> LibrarySummary { try await call("GET", ["summary"]) }

    public func requestUploads(_ items: [UploadRequestItem]) async throws -> UploadsResponse {
        guard (1...100).contains(items.count) else { throw LibraryAPIError.invalid("Between 1 and 100 photos per request.") }
        return try await call("POST", ["uploads"], body: ["items": items])
    }

    public func items(limit: Int, cursor: String?, filter: ItemsFilter) async throws -> ItemsPage {
        var q = [URLQueryItem(name: "limit", value: String(limit))]
        if let cursor, !cursor.isEmpty { q.append(URLQueryItem(name: "cursor", value: cursor)) }     // opaque: passed through untouched
        for (k, v) in [("from", filter.from), ("to", filter.to), ("collection", filter.collection), ("place", filter.place)] { if let v, !v.isEmpty { q.append(URLQueryItem(name: k, value: v)) } }
        return try await call("GET", ["items"], query: q)
    }

    public func item(id: String) async throws -> LibraryPhoto { try await call("GET", ["items", id]) }

    public func delete(ids: [String]) async throws -> DeleteResult {
        guard (1...100).contains(ids.count) else { throw LibraryAPIError.invalid("Between 1 and 100 photos per request.") }
        return try await call("POST", ["items", "delete"], body: ["ids": ids])
    }

    public func search(query: String, limit: Int?, drop: [String], cursor: String?) async throws -> SearchResponse {
        struct Body: Encodable { let query: String; let limit: Int?; let drop: [String]?; let cursor: String? }
        return try await call("POST", ["search"], body: Body(query: query, limit: limit, drop: drop.isEmpty ? nil : drop, cursor: (cursor?.isEmpty ?? true) ? nil : cursor))
    }

    public func collections() async throws -> [LibraryCollection] {
        struct R: Decodable { let collections: [LibraryCollection] }
        return try await call("GET", ["collections"], as: R.self).collections
    }

    public func createCollection(name: String, emoji: String?) async throws -> LibraryCollection {
        struct Body: Encodable { let name: String; let emoji: String? }
        return try await call("POST", ["collections"], body: Body(name: name, emoji: emoji))
    }

    public func updateCollection(id: String, name: String?, emoji: String?) async throws -> LibraryCollection {
        struct Body: Encodable { let name: String?; let emoji: String? }
        return try await call("POST", ["collections", id], body: Body(name: name, emoji: emoji))
    }

    public func deleteCollection(id: String) async throws { _ = try await raw("POST", ["collections", id, "delete"], body: [String: String]()) }

    public func editCollection(id: String, add: [String], remove: [String]) async throws {
        struct Body: Encodable { let add: [String]?; let remove: [String]? }
        _ = try await raw("POST", ["collections", id, "items"], body: Body(add: add.isEmpty ? nil : add, remove: remove.isEmpty ? nil : remove))
    }
}

struct AnyEncodable: Encodable {
    let value: any Encodable
    init(_ v: any Encodable) { value = v }
    func encode(to encoder: Encoder) throws { try value.encode(to: encoder) }
}
