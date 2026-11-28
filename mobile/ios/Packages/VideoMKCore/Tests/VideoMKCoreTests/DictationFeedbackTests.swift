import Foundation
import Testing
@testable import VideoMKCore

@Suite struct DictationFeedbackTests {
    private func recording(limit: Int = 360) -> VoiceFeedback { var s = VoiceFeedback(); s.apply(.request); s.apply(.granted(now: 1000, limit: limit)); return s }

    @Test func meterHasFixedBarsAndSilenceIsDots() {
        var m = LevelMeter(); let h = m.push(0)
        #expect(h.count == DictationFeedback.barCount && h.min()! == DictationFeedback.minBar && h.max()! <= 1)
    }
    @Test func attackIsFastReleaseIsSlow() {
        var m = LevelMeter(); m.push(0.1); let up = m.bars.last!
        #expect(up > 0.3)
        m.push(0.1); m.push(0.1); let loud = m.bars.last!; #expect(loud > up)
        m.push(0); let down = m.bars.last!
        #expect(down < loud && down > DictationFeedback.minBar + (loud - DictationFeedback.minBar) * 0.4)
    }
    @Test func constantInputDoesNotJitter() {
        var m = LevelMeter(); for _ in 0..<60 { m.push(0.2) }
        #expect(Set(m.bars.map { String(format: "%.3f", $0) }).count == 1)
        let before = m.bars.last!; m.push(1); #expect(m.bars.last! > before)
    }
    @Test func badInputIsClampedAndDeterministic() {
        var a = LevelMeter(), b = LevelMeter()
        for x in [0, 0.3, Double.nan, 5, -1, 0.1] { a.push(x); b.push(x) }
        #expect(a == b && a.bars.max()! <= 1)
        #expect(DictationFeedback.barHeight(1) == 1 && abs(DictationFeedback.barHeight(0) - 0.1) < 1e-9)
    }
    @Test func decibelsToLevel() {
        #expect(DictationFeedback.level(fromDecibels: -160) == 0 && DictationFeedback.level(fromDecibels: -50) == 0)
        #expect(abs(DictationFeedback.level(fromDecibels: 0) - 1) < 1e-6 && DictationFeedback.level(fromDecibels: -20) > 0.09 && DictationFeedback.level(fromDecibels: -20) < 0.11)
        #expect(DictationFeedback.level(fromDecibels: .nan) == 0 && DictationFeedback.level(fromDecibels: 6) == 1)
    }
    @Test func happyPathAndCancel() {
        var s = recording(); #expect(s.phase == .recording)
        s.apply(.stop(now: 5000)); #expect(s.phase == .transcribing)
        s.apply(.ok); #expect(s.phase == .inserted); s.apply(.dismiss); #expect(s.phase == .idle)
        var d = VoiceFeedback(); d.apply(.request); d.apply(.denied); #expect(d.phase == .idle)
        var c = recording(); c.apply(.cancel); #expect(c.phase == .idle)
        var w = recording(); w.apply(.stop(now: 2000)); w.apply(.cancel); #expect(w.phase == .idle)
    }
    @Test func failureThenRetryRestartsTheWaitClock() {
        var s = recording(); s.apply(.stop(now: 2000)); s.apply(.fail("network"))
        #expect(s.phase == .failed && s.failure == "network")
        s.apply(.retry(now: 9000)); #expect(s.phase == .transcribing && s.waitStartedAt == 9000 && s.failure == nil)
    }
    @Test func impossibleEventsDoNothing() {
        var s = VoiceFeedback(); s.apply(.stop(now: 1)); #expect(s.phase == .idle)
        var r = recording(); r.apply(.ok); #expect(r.phase == .recording); r.apply(.request); #expect(r.phase == .recording)
    }
    @Test func timerFormat() {
        #expect(DictationFeedback.timer(0) == "0:00" && DictationFeedback.timer(7) == "0:07" && DictationFeedback.timer(65) == "1:05" && DictationFeedback.timer(359.9) == "5:59" && DictationFeedback.timer(-3) == "0:00")
    }
    @Test func warningsAtThirtyAndTenSeconds() {
        func at(_ sec: Double) -> (level: DictationFeedback.Warning, remaining: Int) { var s = recording(); s.apply(.tick(now: 1000 + sec * 1000)); return s.warning }
        #expect(at(329).level == .none && at(330).level == .soon && at(349).level == .soon)
        #expect(at(350).level == .final && at(350).remaining == 10 && at(400).remaining == 0)
    }
    @Test func dailyAllowanceCanBeNearer() {
        #expect(DictationFeedback.effectiveLimit(maxClip: 360, secondsLeft: 45) == 45 && DictationFeedback.effectiveLimit(maxClip: 360, secondsLeft: 5000) == 360)
        #expect(DictationFeedback.effectiveLimit(maxClip: 360, secondsLeft: nil) == 360 && DictationFeedback.effectiveLimit(maxClip: 360, secondsLeft: -4) == 0)
        var s = recording(limit: 45); #expect(s.warning.level == .none); s.apply(.tick(now: 21_000)); #expect(s.warning.level == .soon)
    }
    @Test func waitHints() {
        func w(_ sec: Double) -> DictationFeedback.Wait { var s = recording(); s.apply(.stop(now: 2000)); s.apply(.tick(now: 2000 + sec * 1000)); return s.wait }
        #expect(w(7) == .normal && w(8) == .slow && w(59) == .slow && w(60) == .timeout && recording().wait == .normal)
    }
    @Test func announcementsChangeOnlyAtThresholds() {
        func key(_ sec: Double) -> String? { var s = recording(); s.apply(.tick(now: 1000 + sec * 1000)); return s.announcement }
        #expect(key(1) == key(100) && key(335) == "warn_soon" && key(355) == "warn_final" && key(358) == key(355) && VoiceFeedback().announcement == nil)
    }
    @Test func tickNeverGoesBackwards() {
        var s = recording(); s.apply(.tick(now: 4600)); s.apply(.tick(now: 2000)); #expect(s.now == 4600 && s.elapsed == 3)
    }
    @Test func onlyHiccupsAreRetryable() {
        #expect(BetterDictationFailure.failed.isRetryable && BetterDictationFailure.network.isRetryable)
        for f in [BetterDictationFailure.quota, .plan, .paused, .tooLong, .badAudio, .auth] { #expect(!f.isRetryable) }
    }
}
