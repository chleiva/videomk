import Foundation
import Testing
@testable import VideoMKCore

private func json(_ s: String) -> Data { Data(s.utf8) }

@Suite struct RetryRulesTests {
    @Test func aRestartedVideoReportsItsPhotos() throws {
        // the owner's case: 64 photos asked, 63 came back
        let r = try RetryRules.result(status: 202, body: json(#"{"message":"workflow restarted","video_id":"v1","status":"STARTED_PROCESSING","retries":1,"photos":63,"photos_unusable":1}"#))
        #expect(r == .started(photos: 63, unusable: 1))
        #expect(try RetryRules.result(status: 202, body: json(#"{"photos":45}"#)) == .started(photos: 45, unusable: 0))
    }

    @Test func aSecondTapStartsNothing() throws {
        #expect(try RetryRules.result(status: 200, body: json(#"{"message":"already running"}"#)) == .alreadyRunning)
    }

    @Test func anOlderServerIsUnsupportedNotAnError() throws {
        // API Gateway's own answers for a route that does not exist carry no `code`
        #expect(try RetryRules.result(status: 403, body: json(#"{"message":"Missing Authentication Token"}"#)) == .unsupported)
        #expect(try RetryRules.result(status: 404, body: Data()) == .unsupported)
    }

    @Test func refusalsCarryTheServersWords() throws {
        #expect(try RetryRules.result(status: 409, body: json(#"{"code":"attachments_unavailable","message":"The photos are gone.","photos":64,"missing":3}"#)) == .refused(code: "attachments_unavailable", message: "The photos are gone."))
        #expect(try RetryRules.result(status: 409, body: json(#"{"code":"retry_limit","message":"Tried 3 times."}"#)) == .refused(code: "retry_limit", message: "Tried 3 times."))
        #expect(try RetryRules.result(status: 404, body: json(#"{"code":"not_found","message":"No such video."}"#)) == .refused(code: "not_found", message: "No such video."))
    }

    @Test func creditsAndSessionProblemsAreThrown() {
        #expect(throws: APIError.unauthorized) { try RetryRules.result(status: 401, body: Data()) }
        #expect(throws: APIError.insufficientCredits(balance: 1, needed: 2)) { try RetryRules.result(status: 402, body: json(#"{"balance":1,"needed":2}"#)) }
        #expect(throws: APIError.server) { try RetryRules.result(status: 500, body: Data()) }
    }

    @Test func removeIsTrueWhenGoneAndFalseOnAnOlderServer() throws {
        #expect(try RetryRules.removed(status: 200, body: Data()))
        #expect(try RetryRules.removed(status: 204, body: Data()))
        #expect(try RetryRules.removed(status: 404, body: json(#"{"code":"not_found"}"#)))
        #expect(try !RetryRules.removed(status: 403, body: json(#"{"message":"Missing Authentication Token"}"#)))
        #expect(throws: APIError.conflict("A finished video is not removed here.")) { try RetryRules.removed(status: 409, body: json(#"{"code":"not_removable","message":"A finished video is not removed here."}"#)) }
    }

    /// The 60-photo video that came back with none: a request is never rebuilt from the prompt unless the video is KNOWN to have had no attachments.
    @Test func aVideoIsNeverAskedForAgainWithoutItsAttachments() {
        #expect(RetryRules.mayResendFromPrompt(attachments: 0, briefIsValid: true, fromPresentation: false))
        #expect(!RetryRules.mayResendFromPrompt(attachments: 64, briefIsValid: true, fromPresentation: false))
        #expect(!RetryRules.mayResendFromPrompt(attachments: 1, briefIsValid: true, fromPresentation: false))
        #expect(!RetryRules.mayResendFromPrompt(attachments: nil, briefIsValid: true, fromPresentation: false))   // made in an earlier session: unknown counts as "had attachments"
        #expect(!RetryRules.mayResendFromPrompt(attachments: 0, briefIsValid: false, fromPresentation: false))
        #expect(!RetryRules.mayResendFromPrompt(attachments: 0, briefIsValid: true, fromPresentation: true))
    }

    @Test func theListSaysWhetherTryAgainIsWorthOffering() throws {
        let d = JSONDecoder()
        let off = try d.decode(VideoItem.self, from: json(#"{"video_id":"v1","status":"FAILED","can_retry":false}"#))
        let on = try d.decode(VideoItem.self, from: json(#"{"video_id":"v2","status":"FAILED","can_retry":true}"#))
        let old = try d.decode(VideoItem.self, from: json(#"{"video_id":"v3","status":"FAILED"}"#))
        #expect(off.canRetry == false && on.canRetry == true && old.canRetry == nil)
    }
}
