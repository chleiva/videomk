import Foundation
import Testing
@testable import VideoMKCore

@Suite struct DesignTokensTests {
    @Test func everyTextPairMeetsItsWcagMinimumInLightAndDark() {
        for pair in DesignTokens.colorPairs {
            for dark in [false, true] {
                let ratio = DesignTokens.contrast(pair.fg.hex(dark: dark), pair.bg.hex(dark: dark))
                #expect(ratio >= pair.minimum, "\(pair.name) \(dark ? "dark" : "light") is \(ratio), needs \(pair.minimum)")
            }
        }
    }

    @Test func tertiaryTextFixedAsSpecified() {
        #expect(DesignTokens.textTertiary.light == 0x5F6585 && DesignTokens.textTertiary.dark == 0x8A92B0)
        #expect(DesignTokens.contrast(0x5F6585, 0xEEF0F9) >= 4.9)
        #expect(DesignTokens.live == 0x22D3EE)
    }

    @Test func contrastMathMatchesKnownValues() {
        #expect(abs(DesignTokens.contrast(0x000000, 0xFFFFFF) - 21) < 0.001)
        #expect(abs(DesignTokens.contrast(0x777777, 0xFFFFFF) - 4.48) < 0.02)
    }

    @Test func scalesAreOnTheFourPointGridAndTouchTargetIs44() {
        let S = DesignTokens.Space.self
        let spaces = [S.xs, S.s, S.m, S.l, S.xl, S.xxl, S.xxxl]
        #expect(spaces.allSatisfy { $0.truncatingRemainder(dividingBy: 4) == 0 })
        #expect(DesignTokens.Size.minTouch == 44)
        #expect(DesignTokens.Haptic.allCases.count == 5)
    }
}

@Suite struct DayGroupTests {
    private var cal: Calendar { var c = Calendar(identifier: .gregorian); c.timeZone = TimeZone(identifier: "UTC")!; return c }
    @Test func groupsByCalendarDayNotByHours() {
        let now = Date(timeIntervalSince1970: 1_790_000_000)   // fixed
        let c = cal
        let startOfDay = c.startOfDay(for: now)
        #expect(DayGroup.of(startOfDay.addingTimeInterval(1), now: now, calendar: c) == .today)
        #expect(DayGroup.of(startOfDay.addingTimeInterval(-1), now: now, calendar: c) == .yesterday)
        #expect(DayGroup.of(startOfDay.addingTimeInterval(-86_400 - 1), now: now, calendar: c) == .earlier)
        #expect(DayGroup.of(nil, now: now, calendar: c) == .earlier)
    }
    @Test func keepsOrderAndDropsEmptyGroups() {
        let now = Date(timeIntervalSince1970: 1_790_000_000), c = cal
        let items = [(1, now), (2, now.addingTimeInterval(-86_400 * 5)), (3, now)]
        let g = DayGroup.grouped(items, date: { $0.1 }, now: now, calendar: c)
        #expect(g.map(\.group) == [.today, .earlier] && g[0].items.map(\.0) == [1, 3])
    }
}
