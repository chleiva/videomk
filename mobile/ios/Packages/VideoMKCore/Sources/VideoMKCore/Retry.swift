import Foundation

/// "Try again" and "Remove" on a video that did not finish: how the server's answers are read, and the one rule that protects attachments (docs/CREATE_API.md, retry).
/// Pure, so the rules are unit-tested without a network.
public enum RetryRules {
    private struct Body: Decodable { let photos: Int?; let photos_unusable: Int?; let code: String?; let message: String?; let balance: Int?; let needed: Int? }

    /// The answer to `POST /users/{user}/videos/{video}/retry`.
    /// 202 started (with how many photos came back), 200 already running, 409/400/404-with-a-code refused (limit reached, attachments gone, not allowed),
    /// a bare 403/404 is API Gateway saying the server has no such route (`.unsupported`).
    public static func result(status: Int, body: Data) throws -> RetryResult {
        let r = try? JSONDecoder().decode(Body.self, from: body)
        let fallback = tr("err.server")
        switch status {
        case 202: return .started(photos: r?.photos, unusable: max(0, r?.photos_unusable ?? 0))
        case 200: return .alreadyRunning
        case 401: throw APIError.unauthorized
        case 402: throw APIError.insufficientCredits(balance: r?.balance ?? 0, needed: r?.needed ?? 1)
        case 429: throw APIError.quota(r?.message ?? tr("err.daily_limit"))
        case 403, 404:
            guard let code = r?.code else { return .unsupported }
            return .refused(code: code, message: r?.message ?? fallback)
        case 409: return .refused(code: r?.code ?? "refused", message: r?.message ?? fallback)
        case 400: return .refused(code: r?.code ?? "invalid", message: r?.message ?? fallback)
        default: throw APIError.server
        }
    }

    /// The answer to `DELETE /users/{user}/videos/{video}`: true when the video is gone (also when it already was), false when the server has no such route.
    public static func removed(status: Int, body: Data) throws -> Bool {
        let r = try? JSONDecoder().decode(Body.self, from: body)
        switch status {
        case 200, 202, 204: return true
        case 401: throw APIError.unauthorized
        case 404 where r?.code == "not_found": return true
        case 403, 404: return false
        case 409: throw APIError.conflict(r?.message ?? tr("err.server"))
        default: throw APIError.server
        }
    }

    /// An older server without the retry route: may the phone ask for the same video again the old way (a brand-new request built from the prompt)?
    /// Only when the video is KNOWN to have been made with no attachments in this session. Unknown counts as "had attachments": a request is never rebuilt without its photos.
    public static func mayResendFromPrompt(attachments: Int?, briefIsValid: Bool, fromPresentation: Bool) -> Bool {
        attachments == 0 && briefIsValid && !fromPresentation
    }
}
