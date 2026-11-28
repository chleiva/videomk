# Free dictation fixes (2026-11-28)

The mic in the Create box (free, on-device or platform speech recognition) was reported poor. Three faults, fixed on iPhone, Android and web.

## What was wrong
- **Android** (`DictationController.kt`): used the recognizer's default silence lengths, so it ended after a short pause; `onResults` and `onError` (NO_MATCH, SPEECH_TIMEOUT, BUSY) ended dictation. Each result REPLACED the field with `base + text`.
- **iOS** (`Dictation.swift`): one recognition task only. Apple ends a task after about a minute, after a silence or on an error, and the code then stopped everything; words said after that were lost. Errors after any speech were treated as "finished quietly".
- **Web** (`dictation.ts`): `continuous` sessions are ended by the browser after silence or about a minute; nothing restarted them. The box was set to `base + transcript of this session`, so a restart or a change in the box lost text.
- **Language, all three**: iOS and Android used the phone's preferred languages (an English phone with the app in Spanish listened in English); web used es-ES for every Spanish speaker.

## The fix
Shared rules, written as pure code with unit tests on each platform (same cases): `DictationText` (base + separator + running transcript; fold a finished segment into the base; if the field is not what we last wrote, the person edited it, so the field becomes the new base and the recognizer restarts), `DictationRestartPolicy` (restart after any end by itself; stop only on Stop, 5 minutes, 90 s (iOS: 60 s) with nothing said, or 3-4 failures in under a second each), and the language choice.
- **Android**: `EXTRA_SPEECH_INPUT_COMPLETE_SILENCE_LENGTH_MILLIS` 8 s, `..POSSIBLY_COMPLETE..` 6 s, minimum length 15 s; a new recognizer starts 300 ms after any end (1 s after RECOGNIZER_BUSY); results are appended; permission, language-unsupported (ERROR 12/13, API 31+) and no-network-before-any-text end with a message (keyboard fallback when available). The controller implements `DictationEngine` (core/Dictation.kt); `ComposerViewModel` and the screens only know that interface, so a paid engine can be plugged in.
- **iOS**: the audio engine runs once per dictation; recognition tasks come and go on top of it. A task is rotated at 50 s (audio is queued meanwhile, not lost), or restarted when it ends (final, error, interruption); its transcript is folded into the base. `addsPunctuation`, `contextualStrings` (VideoMK, Otto), on-device when the locale supports it (server otherwise, as before). Phone calls/Siri pause and resume it; a route change restarts the engine. `DictationEngine` protocol in VideoMKCore (the screen still holds the concrete `Dictation`; swapping it is a one-line change).
- **Web**: `startDictation({ lang, getText, setText, onEnd, maxLength })` owns composition and restarts; the Composer only passes getters. New end reason `language` shows `create.dictate_language`. The textarea stays read-only while listening, so hand edits during web dictation cannot happen today; the rebase is there for programmatic changes.
- **Language**: the APP language (iOS `Localization.shared.language`, Android `Txt.localeTag`, web `locale`) decides; the phone's region only picks the variant (es-MX, en-GB, ...). iOS: if the recognizer has no locale for it, the phone's other preferred language is used and a line says so (`dictation.language_fallback`, shown above the box while listening). Android: unsupported language shows `dictation_language_unavailable[_keyboard]` and stops (it never listens in another language silently). Web: `language-not-supported` shows a message. Strings in English and Spanish on all three; iOS gates pass.
- **Not done (follow-up)**: a dictation-only language picker in the Options sheet. The app language (Settings > Language) is the choice for now. The "Better dictation" paid engine is not started.

## Not verified (no microphone in a simulator)
Real recognition, whether Google's recognizer honours the silence extras (some ignore them; the restart covers that, but a restart can play the recognizer's start sound), the 50 s rotation without lost words on a real phone, interruptions and route changes, on-device model availability for Spanish, and `contextualStrings` effect. The iOS app compiles for the simulator; Android compiles and unit tests pass; the web tests run on fake recognizers.
Android start/stop sounds on restart are not suppressed (muting system streams can leave a phone muted if the app is killed).

## Phone test (say each, in English then in Spanish with the app set to that language)
1. "A video about how bees make honey." Stop. Expect the text.
2. Tap the mic, say "A video about bees", count to 10 in silence, then say "and how they dance". Expect one text with both parts, still listening during the pause.
3. Type "Please make it fun." first, tap the mic, say "for my niece who is seven". Expect the typed text kept and the speech appended.
4. Stop, tap the mic again, say "and add a funny owl". Expect the earlier text kept, new words appended.
5. Speak for 70 seconds without stopping (read a paragraph aloud). Expect no gap or lost sentence around the 60 s mark. Then Settings > Language to the other language, repeat 1, and check it listens in that language (Spanish app on an English phone must produce Spanish).
