# Dictation feedback (R183, 2026-11-28; branch `dictation-feedback`)

Owner test of the paid "Better dictation": it recorded and transcribed well, in other languages too, but nothing on screen said so, so he thought it was not working. Real-time text is not wanted (cost). What is wanted: the person must SEE that it is listening and that it is transcribing. Applies to web, iPhone and Android; free (native) dictation gets a listening indicator too.

## Research (WebSearch, 2 queries; secondary summaries, re-verify before quoting)
- Recorder UIs (voice messages, Zebra voice memo, Google Voice redesign, Wispr Flow, Superwhisper) show timer + live waveform + stop/send/cancel together; a moving waveform answers "did it hear me?"; a flat one tells the person to check the mic.
- A dictation UX guide recommends one status that moves Recording -> Transcribing -> Done, and waiting states that cut uncertainty without promising a speed.
- Cancel: easy and visible, hard to hit by accident; short clips cancel at once (Superwhisper confirms only over 30 s). We cancel without confirmation (nothing is lost but a few words said; the live preview text is restored to what it was).
- Apple: reserve haptics for meaningful moments; use system haptics; with Reduce Motion replace motion by a dissolve or colour change; VoiceOver can announce state. (Accessibility HIG page; reduced-motion evaluation criteria.)
- The project's own design bar (`docs/DESIGN_BAR_2026.md`): rule 7 "locked, honest waits" (three words and Cancel), rule 9 forgiving errors, haptic map (light on choice, success, warning on failure, none while typing), no sound, springs `.spring(0.35, 0.86)` / web 240-320 ms `cubic-bezier(.2,.8,.2,1)`, 44 pt / 48 dp / 44 px targets, state never by colour alone.

## Design
One **voice panel** replaces the pills and tool row while the mic works (same capsule family as the "Checking your request" capsule, `CREATE_SCREEN_*_VALUES.md`): `[Cancel] [bars + status line] [Stop]`. The prompt above stays visible so the live preview text keeps appearing. Height 72 (web 4.5 rem) so entering it does not move the card above; it grows only for the failed state.
- **Bars**: 24 on phones (28 on a wide web card), 3 px wide, scrolling history (newest right), height from the REAL input level. Smoothing: attack 0.6 per frame, release 0.12 (fast up, slow down), `MIN_BAR` 0.10 so silence is a row of dots, not a gap (and a flat row tells the person the mic hears nothing). Sampled at 25 fps, drawn without a framework re-render. Level to height: gain 3.2, square root.
- **Colour**: recording = danger red (dot, bars, Stop); transcribing = primary (bars, dot, spinner). Two states can never be confused: the Stop button disappears and a spinner takes its place, the bars turn brand colour and sweep slowly (2.4 s per sweep, the design bar's shimmer duration) instead of following the voice. Text states the phase in words (state never by colour alone).
- **Warning**: with 30 s left the status line says "N s left" in the warning colour; with 10 s left in danger. The limit is the nearer of the per-clip limit (6 min) and what is left of the daily allowance. The stop at the limit already existed.
- **Transcribing too long**: after 8 s the line becomes "Taking longer than usual..."; after 60 s the upload counts as failed. 
- **Failure**: network / server / timeout keep the recorded clip in memory and show "Couldn't transcribe" with **Retry** (resends the same clip) and **Use device dictation** (keeps the words the phone heard, shows the existing fallback note). Quota, plan, paused, too long are not retryable (retrying cannot help) and end as before with their one line.
- **Done**: the panel leaves, the inserted text gets a 1.2 s highlight fade, one light haptic where the platform has it, VoiceOver/TalkBack/aria-live "Text added".
- **Free (native) dictation**: same panel; no mic level is available from the recognizer, so the bars are replaced by a mic glyph with a pulsing ring; Stop and Cancel (Cancel restores the text as it was before dictation).
- **Reduced motion**: bars still follow the voice (it is information, not decoration) but without easing; the transcribing sweep becomes a still rising ramp, pulses stop, the spinner turns slowly, the panel cross-fades.

### State table
| State | Trigger | Shows | Controls | Announced (polite) | Haptic |
|---|---|---|---|---|---|
| idle | none | mic button | mic | none | none |
| requesting | mic tapped | mic (system permission prompt) | none | none | none |
| recording | permission granted | red dot, bars from real level, "Listening...", m:ss, red Stop | Stop (uploads), Cancel (discards, text restored) | "Listening" | light impact |
| recording, 30 s left | remaining <= 30 | "N s left" warning colour | same | "Recording stops in N seconds" | none |
| recording, 10 s left | remaining <= 10 | "N s left" danger colour | same | "Recording stops very soon" | none |
| transcribing | Stop or the limit | brand bars sweeping, "Transcribing...", spinner, no timer | Cancel (stops waiting; phone words stay) | "Transcribing your recording" | none |
| transcribing, slow | wait >= 8 s | "Taking longer than usual..." | Cancel | "Still transcribing, taking longer than usual" | none |
| failed | error or wait >= 60 s (retryable kinds) | warning glyph + "Couldn't transcribe" | Retry, Use device dictation | "Could not transcribe. Retry, or use device dictation." | warning (iOS), 20 ms (web) |
| inserted | text arrived | text highlight 1.2 s | none | "Text added" | success / light |
| cancelled | Cancel | panel gone, text as before | none | "Recording discarded" | none |
| denied | mic blocked | existing blocked note | none | note is a status | none |

The pure rules (level meter, phase machine, timer, thresholds, announcement keys) are written once per platform with the same test cases: web `frontend/src/lib/dictationFeedback.ts`, iOS `VideoMKCore/DictationFeedback.swift`, Android `core/DictationFeedback.kt`.

## Standards checklist
| Item | Web | iOS | Android |
|---|---|---|---|
| Touch targets | Stop 52 px, Cancel 44 px, buttons 44 px | Stop 52 pt, Cancel 44 pt min | Stop 52 dp, Cancel 48 dp |
| Contrast (text 4.5, graphics 3) | tokens only; danger/primary bars on surface-2 checked in light and dark screenshots; Stop glyph uses `--background` on danger (white failed 2.8:1 in dark) | semantic colours (`.red`, accent), system materials | M3 `error` / `primary` roles on `surfaceContainerHigh` |
| Screen reader | `role=group` + aria-label with time, one `aria-live=polite` line changed only at thresholds (no per-second chatter); bars `aria-hidden` | `accessibilityLabel` on group with time, `UIAccessibility.post(.announcement)` at thresholds, bars hidden | `liveRegion = Polite` on the status line, `contentDescription` on buttons, bars cleared from semantics |
| Reduced motion | `prefers-reduced-motion` block (ramp, no pulse, cross-fade) | `accessibilityReduceMotion` / `@Environment(\.accessibilityReduceMotion)` | `Settings.Global.ANIMATOR_DURATION_SCALE == 0` check via `LocalReduceMotion`-style flag |
| Text size | rem units; failed state wraps; German/Dutch checked at 320 px (Cancel becomes an X under 360 px) | Dynamic Type, status line wraps, caps at accessibility1 like the dock | sp units, font scale 2.0 wraps |
| Motion language | `--ease` 240-380 ms, 2.4 s shimmer | spring 0.35/0.86 for the panel, linear 80 ms for bars | M3 emphasized easing 300 ms for the panel, 80 ms linear for bars |
| Haptics | `navigator.vibrate` (Android browsers only) | `UIImpactFeedbackGenerator(.light)`, `UINotificationFeedbackGenerator` success/warning | `HapticFeedbackType` TextHandleMove / Confirm / Reject |
| No layout jump | panel 72 px, bar count fixed, tabular digits for the timer | same | same |
| Dark mode | tokens | semantic colours | dynamic colour scheme |
| Frame budget | 25 fps meter, direct DOM writes, 24 bars | `Canvas`/`TimelineView` at 25 fps, 24 rects | `Canvas`, one `State<List>` per sample, 24 rects |
| Keyboard/focus | native buttons, focus ring from `:focus-visible` | n/a | n/a |

References: Apple HIG Accessibility (haptics, Reduce Motion, VoiceOver), Playing haptics, Motion; App Store Connect reduced-motion criteria; Material 3 motion (easing and duration tokens) and accessibility (touch targets 48 dp, live regions); WCAG 2.2 AA (1.4.3 contrast, 1.4.11 non-text contrast, 2.4.7 focus visible, 2.5.8 target size, 4.1.3 status messages); WAI-ARIA live regions; the project design bar sections 4 to 6.

## Verification
Unit tests per platform, screenshots of every state (light, dark, Spanish, German and Dutch strings at 320 px, reduced motion) in `~/Downloads/videomk-looks/<platform>/dictation-feedback/` with a contact sheet. Not verified: the real microphone level on a device or browser (the meter reads the same stream the recorder uses; tests feed synthetic levels), haptic feel, VoiceOver and TalkBack on real devices, whether a second microphone consumer (the level meter) changes behaviour on any phone (iOS reads the recorder's own metering and Android `MediaRecorder.maxAmplitude`, so no second consumer there; web adds an `AnalyserNode` on the same stream).
