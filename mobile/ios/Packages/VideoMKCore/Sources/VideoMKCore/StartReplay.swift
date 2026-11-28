import Foundation

/// A create whose answer was lost on the way back (cellular): the request may well have been accepted.
public enum StartReplay {
    /// Runs [start]; on a network failure waits and runs it once more. The caller must keep the SAME client request id for both runs:
    /// the server then returns the video it already started instead of making and charging a second one.
    public static func once<T>(after delay: Duration = .milliseconds(1500), _ start: () async throws -> T) async throws -> T {
        do { return try await start() }
        catch let e as APIError where e == .network {
            try await Task.sleep(for: delay)
            return try await start()
        }
    }
}
