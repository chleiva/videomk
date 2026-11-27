# VideoMK iPhone: Look picker and cast, review captures

Produced 2026-11-27 by the UI tests `VideoMKLookUITests.testCaptures` and `testCaptureReal` (debug build of branch `ccr-3c41ecff-680028`, app code at commit 47e2adb plus the capture test), on the in-app fake server with the backend's own capabilities answer as fixture (`mobile/ios/VideoMKUITests/Fixtures/looks_en.json`, `looks_es.json`). Not the real backend.

In this folder the mode is the file name's suffix (`02-sheet-auto_dark.jpg`); the full-size PNG set was handed over outside the repository. Modes:

| Suffix | Simulator | Mode |
|---|---|---|
| `_light` | iPhone 17 Pro, iOS 26.5 | light, English |
| `_dark` | iPhone 17 Pro, iOS 26.5 | dark, English |
| `_es` | iPhone 17 Pro, iOS 26.5 | light, Spanish |
| `_large` | iPhone 17 Pro, iOS 26.5 | light, English, largest Dynamic Type (system AX5; the app lays out up to its ceiling, AX3) |
| `_small` | iPhone SE (3rd generation), iOS 26.5 (the smallest supported iPhone; a temporary simulator, deleted afterwards) | light, English |

| File | State |
|---|---|
| `01-create-auto_<mode>.jpg` | Create with the three pills; Look is Auto (the default) |
| `02-sheet-auto_<mode>.jpg` | Picker, Auto selected |
| `03-create-whiteboard_<mode>.jpg` | Create, pill says Whiteboard |
| `03b-create-real_<mode>.jpg` | Create, pill says Real |
| `04-sheet-whiteboard_<mode>.jpg` | Picker, Whiteboard selected |
| `04b-sheet-real_<mode>.jpg` | Picker, Real selected |
| `05-sheet-cartoon-auto_<mode>.jpg` | Picker, Cartoon selected; cast: 0 chosen (Auto); board switch off |
| `06-sheet-cartoon-one_<mode>.jpg` | Cast: 1 chosen (Fox); the line says who presents |
| `07-sheet-cartoon-talk_<mode>.jpg` | Cast: 2 chosen (Fox, Bruno); the server's conversation line; board switch on |
| `08-create-cartoon-talk_<mode>.jpg` | Create, pill says "Cartoon · Fox + Bruno" |
| `09-sheet-cartoon-three-full_<mode>.jpg` | Cast: 3 chosen, a fourth was tapped: "Choose up to 3." |
| `10-create-cartoon-three_<mode>.jpg` | Create, pill with three characters ("Cartoon · Priya + 2") |
| `11-sheet-length-moved_<mode>.jpg` | A conversation chosen in a 15 s video: the length was moved to 30 s and the sheet says so |
| `12-sheet-plan-locked_<mode>.jpg` | A look the plan does not allow (Cartoon, "Pro plan"): shown, locked, no purchase button |
| `13-sheet-one-hidden_<mode>.jpg` | A look this stage does not have (Whiteboard, `available: false`): hidden |
| `14-create-photos-reset_<mode>.jpg` | Photos attached after choosing Cartoon: back to Auto with one line |
| `15-sheet-with-photos_<mode>.jpg` | Picker with photos attached: only Auto and Real, one line says why |
| `16-sheet-shape-hint_<mode>.jpg` | Whiteboard in a vertical video: the "looks best in" hint |
| `17-making-note_<mode>.jpg` | Making screen with the server's note (the look was adapted) |
| `18-older-server-menu_<mode>.jpg` | A server without `looks.look`: the older Look menu, unchanged |
| `19-info-look_<mode>.jpg` | Info sheet of a finished video with the applied look and why |

Only with `_large` and `_small` (the tall sheet scrolls there): `05b-sheet-cartoon-auto-scrolled_<mode>.jpg`, `05c-sheet-cartoon-auto-end_<mode>.jpg`, `07b-sheet-cartoon-talk-end_<mode>.jpg`.

Known fixture artefacts, not app behaviour: the prompt and the Making and Info content are fake demo data and stay in English in `_es`; the Making hero is a placeholder picture.
