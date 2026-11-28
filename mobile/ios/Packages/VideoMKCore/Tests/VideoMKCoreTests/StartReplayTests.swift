import Foundation
import Testing
@testable import VideoMKCore

private actor Counter { var n = 0; func next() -> Int { n += 1; return n } }

@Suite struct StartReplayTests {
    @Test func aLostAnswerIsReplayedOnceAndAccepted() async throws {
        let c = Counter()
        let id = try await StartReplay.once(after: .milliseconds(1)) { () async throws -> String in
            if await c.next() == 1 { throw APIError.network }
            return "video-1"
        }
        #expect(id == "video-1")
        #expect(await c.n == 2)
    }

    @Test func twoNetworkFailuresEndAsNetworkAfterExactlyTwoTries() async {
        let c = Counter()
        await #expect(throws: APIError.network) {
            try await StartReplay.once(after: .milliseconds(1)) { () async throws -> String in _ = await c.next(); throw APIError.network }
        }
        #expect(await c.n == 2)
    }

    @Test func aRefusalIsNeverReplayed() async {
        let c = Counter()
        await #expect(throws: APIError.quota("Daily limit")) {
            try await StartReplay.once(after: .milliseconds(1)) { () async throws -> String in _ = await c.next(); throw APIError.quota("Daily limit") }
        }
        #expect(await c.n == 1)
    }
}
