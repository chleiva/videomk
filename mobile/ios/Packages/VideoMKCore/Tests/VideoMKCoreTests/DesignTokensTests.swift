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

    /// The table of docs/DESIGN_BAR_2026.md section 4, value for value.
    @Test func coloursAreTheDesignBarTable() {
        let T = DesignTokens.self
        #expect(T.background.light == 0xF7F7FA && T.background.dark == 0x06070D)
        #expect(T.surface.light == 0xFFFFFF && T.surface.dark == 0x11131D)
        #expect(T.surface2.light == 0xEEEFF4 && T.surface2.dark == 0x1A1D2B)
        #expect(T.surface3.light == 0xE4E6EE && T.surface3.dark == 0x242838)
        #expect(T.text.light == 0x0B0C14 && T.text.dark == 0xF4F5FA)
        #expect(T.textSecondary.light == 0x5C6175 && T.textSecondary.dark == 0xA2A8BC)
        #expect(T.textTertiary.light == 0x8B90A3 && T.textTertiary.dark == 0x70768C)
        #expect(T.primary.light == 0x4B45E0 && T.primary.dark == 0xAAA8FF)
        #expect(T.primaryContainer.light == 0xECEBFF && T.primaryContainer.dark == 0x22224A)
        #expect(T.danger.light == 0xD92D20 && T.danger.dark == 0xFF6B5E)
        #expect(T.gradientStart.light == 0x3B36C8 && T.gradientStart.dark == 0x3B36C8, "the action gradient is the same in light and dark")
        #expect(T.gradientEnd.light == 0x7A4BE6 && T.gradientEnd.dark == 0x7A4BE6)
        #expect(T.makingStart == 0x2B2F9A && T.makingEnd == 0x6A3FC4 && T.live == 0x22D3EE)
    }

    /// text3 is for placeholders and decoration only, so it is in no AA pair; the live accent is only used on the brand gradient or on dark.
    @Test func tertiaryIsNeverAnEssentialPairAndLiveStaysOffWhite() {
        #expect(!DesignTokens.colorPairs.contains { $0.name.hasPrefix("textTertiary") })
        #expect(DesignTokens.contrast(DesignTokens.live, DesignTokens.makingEnd) >= 3, "the sparkle on the lightest point of the Making card")
        #expect(DesignTokens.contrast(DesignTokens.live, 0xFFFFFF) < 3, "cyan on white fails: it must never be used there")
    }

    @Test func typeRolesAreTheSevenOfTheTablePlusThePrompt() {
        let R = DesignTokens.TypeRole.self
        #expect(R.allCases.count == 8 && R.prompt.size == 28 && R.prompt.weight == .semibold)
        #expect(R.largeTitle.size == 34 && R.title.size == 22 && R.headline.size == 17 && R.body.size == 17 && R.subhead.size == 15 && R.footnote.size == 13 && R.caption.size == 12)
        #expect(R.largeTitle.weight == .bold && R.headline.weight == .semibold && R.body.weight == .regular && R.caption.weight == .medium)
        #expect(R.allCases.allSatisfy { $0.line > $0.size })
    }

    @Test func hapticsFollowTheMap() {
        let H = DesignTokens.Haptic.self
        #expect(H.selection.kind == .light && H.send.kind == .medium && H.warning.kind == .warning)
        #expect(H.videoReady.kind == .success && H.shareDone.kind == .success && H.uploadDone.kind == .success)
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
        #expect(DesignTokens.Haptic.allCases.count == 6)
        #expect(DesignTokens.Space.gutter == 20 && DesignTokens.Space.screenMargin == 20, "one gutter, everywhere")
        #expect(DesignTokens.Radius.thumb == 14 && (22...26).contains(DesignTokens.Radius.card) && (22...26).contains(DesignTokens.Radius.videoCard))
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
