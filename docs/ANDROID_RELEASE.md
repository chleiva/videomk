# Publishing the Android app (Google Play)

Status 2026-11-24: the app in `mobile/android` builds a signed release bundle (R8 on) and has been run on an emulator against QA. **Nothing has been published and no
Play Console account is touched by the repository.** This is the list of what the owner has to do, in order. Google changes Play Console wording and policy often: where a
step says "check", confirm in the console's own help before relying on it.

## 0. What is decided in the code
- Application id `com.videomk.app` (same as iOS). Once an app is created with an id in Play it can never change, so decide now.
- minSdk 26, targetSdk 36 (Play requires a recent target; 36 is current), compileSdk 37.
- Release builds have **no server address until production is deployed** (like the iOS Release configuration): they start and show "Not configured". For the first Play
  upload use the QA backend, the equivalent of TestFlight's Beta configuration: `-PvmkReleaseBackend=qa` (below). When production exists set `vmkProdApiBase`,
  `vmkProdAuthDomain`, `vmkProdClientId` (gradle properties, or edit the defaults in `mobile/android/app/build.gradle.kts`) and register the redirect
  `com.videomk.app://auth/callback` on the production Cognito mobile client (QA already has it; it is the same as iOS).
- No analytics, no ads, no crash-reporting SDK, no Google Play Services dependency at all. Network is HTTPS only (cleartext is off). Backup is off (the only local data is the
  encrypted sign-in session).
- Permissions: `INTERNET`, `ACCESS_NETWORK_STATE`, `RECORD_AUDIO` (dictation only, asked when the microphone button is first pressed; the app works without it). Photos use
  the system photo picker: **no storage or media permission**.

## 1. Google Play Console account
1. Create a developer account at https://play.google.com/console (one-time registration fee, identity verification). Choose *Organization* if the app is published by the company
   (needs a D-U-N-S number) or *Personal*.
2. **Check the testing requirement for new accounts**: newly created personal accounts must currently run a closed test with a minimum number of testers (12) for 14 days
   before they can apply for production access. Organization accounts are exempt. Plan for this lead time: start the closed/internal test early.
3. Fill the account's payments profile if you will sell credits later (not needed for a free app with no purchases).

## 2. Create the app
Play Console, *Create app*: name `videomk`, default language English (United States), App (not game), Free. Accept the declarations. Then complete the *Dashboard* tasks in
section 6 below.

## 3. Signing keys (do this before the first upload)
Play uses **Play App Signing**: Google keeps the key that signs what users install; you sign uploads with an *upload key*. Losing the upload key is recoverable (Google can reset
it); losing an app-signing key is not, which is why Google holds it.
1. Create the upload keystore **outside the repository** (never commit `*.jks`, `*.keystore`, `keystore.properties`; `.gitignore` already blocks them):
   ```
   mkdir -p ~/.videomk-secrets && chmod 700 ~/.videomk-secrets
   keytool -genkeypair -v -keystore ~/.videomk-secrets/videomk-upload.jks -alias videomk-upload -keyalg RSA -keysize 4096 -validity 10000
   ```
   Choose a long random password and store it in your password manager. **Back the file and the password up** (two places).
   A throwaway keystore of this kind was created for local release testing on the development machine (`~/.videomk-secrets/videomk-upload.jks`). Make the real one
   yourself, do not upload with the throwaway.

   **Which key Play accepts (checked 2026-11-27):** the registered Play upload key is `~/.videomk-secrets/videomk-play-upload.jks` (alias `videomk-upload`, password in
   `~/.videomk-secrets/play-upload-keystore.pw`; certificate SHA1 `29:D5:E6:37:05:9F:E9:95:86:C2:16:60:9A:7A:C1:26:B5:62:F3:53`). `~/.videomk-secrets/release-env.sh` still points at
   the older `videomk-upload.jks`, whose bundles Play rejects ("signed with the wrong key"). Sign Play uploads with `videomk-play-upload.jks`, verify the AAB certificate
   SHA1 before uploading, and keep the version code above the last upload (475200 on 2026-11-27; minutes since 2026-01-01 works).
2. The build reads the signing details from the environment (or `~/.gradle/gradle.properties`), never from files in the repo:
   ```
   export VMK_KEYSTORE_PATH=~/.videomk-secrets/videomk-upload.jks
   export VMK_KEYSTORE_PASSWORD=...       # the key password defaults to the same value; set VMK_KEY_PASSWORD if different
   export VMK_KEY_ALIAS=videomk-upload
   ```
   (Gradle property names: `vmkKeystorePath`, `vmkKeystorePassword`, `vmkKeyAlias`, `vmkKeyPassword`.) Without them `bundleRelease` still succeeds but the bundle is unsigned and
   cannot be uploaded.
3. On the first upload Play Console asks to enrol in Play App Signing: accept (it is the default for new apps).

## 4. Build the release bundle
```
cd mobile/android
export JAVA_HOME=...                       # JDK 17
export VMK_KEYSTORE_PATH=... VMK_KEYSTORE_PASSWORD=... VMK_KEY_ALIAS=...
./gradlew bundleRelease -PvmkReleaseBackend=qa -PvmkBuildNumber=1      # first internal-test build, against QA
# output: app/build/outputs/bundle/release/app-release.aab
# R8 mapping (for readable crash reports): app/build/outputs/mapping/release/mapping.txt  (Play Console takes it from the bundle automatically)
```
- `vmkBuildNumber` is Play's *version code*: it must be higher for every upload (an integer up to 2,100,000,000; a timestamp-like number such as minutes since 2026-01-01 works).
  `vmkVersionName` (in `gradle.properties`) is what people read.
- Check what you are about to upload: `./gradlew assembleRelease -PvmkReleaseBackend=qa` gives a signed APK you can install on a phone (`adb install`) to try the exact release code.
- Before every upload: `./gradlew testDebugUnitTest` and, on an emulator, `scripts/run-ui-tests.sh` (see `mobile/android/README.md`).
- 16 KB page size (required for new apps targeting Android 15+): the app has no native code of its own; the one library `.so` that AndroidX ships is 16 KB aligned (checked with
  `zipalign -c -P 16`).

## 5. Internal testing first
Play Console, *Testing > Internal testing > Create new release*: upload `app-release.aab`, release name (e.g. `0.1.0 (1)`), release notes. *Testers*: create an email list (people
need Google accounts) and share the opt-in link. Internal testing has no review delay and is the right place to put the QA-backend build. Then *Closed testing* (needed for the
new-account rule above), then *Open* or *Production*.

## 6. Dashboard declarations (Policy and programs / App content)
**Privacy policy URL (required).** A public https page. The app already links `https://videomk.com/privacy` (and `/terms`): those pages must exist before review. It must say at least what
`docs/PHOTOS.md` lists: photos are processed by an AI model to write and make the video, location data is removed, originals are deleted, copies are kept with the video until it is
deleted; the microphone/speech is used only for dictation; what account data is kept; how to delete the account and data.

**Data safety form** (answer for the current app; update when billing or deletion changes things):
| Data type | Collected | Shared | Purpose | Notes |
|---|---|---|---|---|
| Email address | Yes | No | Account management | From the sign-in page (Amazon Cognito, run by the developer in AWS). Required for the account. |
| User IDs (account id) | Yes | No | App functionality, account management | The Cognito subject id. |
| Photos | Yes (only the photos the user picks, or adds to My media) | No | App functionality | Photos attached to a video are uploaded to make it and processed by an AI model in the developer's cloud account (not shared with third parties for their own use); metadata/location removed on the phone and again on the server; originals deleted after processing. Photos the user adds to **My media** (optional private library) are stored encrypted in the developer's cloud account until the user deletes them (per photo, all at once, or by deleting the account) together with a preview and a numerical search fingerprint; the fingerprint is made by an AI model in the developer's own cloud account. Only the user can access them. Optional. |
| User-generated content: the text brief | Yes | No | App functionality | Sent to make the video. |
| Videos the user makes | Yes | No | App functionality | Stored until the user deletes them. |
| Voice or audio recordings / audio files | **No** | - | - | Dictation uses Android's speech recognizer on the device/Google's recognition service as chosen by the OS; the app does not receive, record or upload audio, only the recognised text. (Say so in the form: speech recognition is performed by the OS service, outside the app.) |
| Approximate location | **Yes** (optional) | No | App functionality | Read from the metadata of the photos the user picks (when the photo's source provides it: no location permission is requested) and rounded to 2 decimals (about 1 km) on the phone before it is sent with the video request, to name places in the story. User-controlled: Settings > Photos > "Use photo locations" (default on). Not shared, only the place NAME (city and country) is kept (also for My media photos), never the coordinates. Location is always removed from the uploaded photo files. |
| Precise location | No | | | Never collected: only the rounded approximate location above. |
| Photo capture time (part of "Photos" / app activity) | Yes (optional) | No | App functionality | The photo's EXIF capture time is sent with the video request to order and group photos by day. Settings > Photos > "Use photo dates" (default on). The timestamp is removed from the uploaded files. |
| Device or other IDs, analytics, crash logs, diagnostics | No | | | No analytics or crash SDK. (If you add Play Integrity later, declare device integrity data.) |
| Financial info | No | | | Update when Play Billing is added. |
- Data is encrypted in transit (HTTPS): **Yes**.
- Users can request deletion: **Yes** (in-app deletion exists: Settings > Delete account, contract in `docs/ACCOUNT_DELETION.md`). Answer Yes only for the build and stage that talk to a deployed backend with the deletion routes (qa first, then prod).
- **Web deletion URL** (Play Console > App content > Data safety > "Data deletion" > "Add a link that users can use to request deletion"): enter `https://videomk.com/delete-account`. The page exists (frontend `delete-account.astro`) and describes the in-app route, the email route for people who cannot sign in, what is deleted and how long it takes. Both Play's "delete account" link and the "delete some data without deleting the account" answer can use it (partial deletion: single videos and My media photos are deletable in the app, the page says so).
- No ads, no data sold, no data shared with third parties for advertising.

**Content rating** (IARC questionnaire): category *Utility/Productivity/Other*; no violence, sexual content, drugs, gambling in the app itself; **the app generates content from user input
with AI** and user-created content is shared only with the user themself (videos are private; the Share button hands a file to other apps): answer the user-generated-content and AI
questions accordingly. Expect an "Everyone" / "3+" type rating, confirm in the result.

**Target audience**: 13+ (or 18+); not designed for children (avoids the Families policy).

**Ads**: No. **App access**: the whole app needs sign-in, so give the reviewers working credentials (an email + password test account on the **production** or the QA stack that the
reviewed build points to) in *App access > Add instructions*. Create it with `aws cognito-idp admin-create-user` + `admin-set-user-password --permanent` and give it credits.
**Government / financial / health / news app**: No. **COVID**: No.

**AI-generated content policy**: Play expects apps that generate content with AI to let users report or flag offensive generated content from within the app. The app currently has no
report button. Decide before production (suggested: a "Report a problem" item in Settings and on the video page that opens a pre-filled email or a backend call).

**Account deletion**: Play requires apps that let people create an account to offer deletion **inside the app** and a **web URL** for deletion requests (entered in the Data safety form).
The Android app now has it (Settings > Delete account: confirmation sheet with the typed word DELETE, a recent sign-in check with re-authentication in a Custom Tab, then local data is cleared and the app signs out; contract in `docs/ACCOUNT_DELETION.md`). It works only against a backend deployed with the account routes, so test it on qa with a throwaway user (never a shared QA account: the deletion is real) before production. In the Play Console enter the web URL `https://videomk.com/delete-account` in the Data safety form (Data deletion section).

**Permissions declarations**: only `RECORD_AUDIO` (a normal runtime permission): no special declaration form. No foreground services, no photo/video permission declaration (the system photo
picker is used). **Advertising ID**: declare *No* (the app does not use it).

## 7. Store listing (Grow > Store presence > Main store listing)
Assets and text to prepare (none exist yet):
- App name (30 chars), **short description (80)**, **full description (4000)**; English now, Spanish is a natural second listing (the app already understands Spanish briefs).
- **App icon: 512x512 PNG**, 32-bit, up to 1 MB (the launcher icon in the app is a vector placeholder: a play triangle on the brand gradient; replace with the final art in
  `app/src/main/res/drawable/ic_launcher_*.xml` and export the same art as the 512 PNG).
- **Feature graphic: 1024x500** PNG/JPEG.
- **Phone screenshots**: at least 2, up to 8 (16:9 to 9:16, 320 to 3840 px per side). 7-inch and 10-inch tablet screenshots are optional (recommended: the layout adapts).
- Optional promo video (YouTube URL).
- Category (e.g. *Video Players & Editors* or *Productivity*), contact email (public), website, privacy policy URL.
- A *Spanish* translation of name, descriptions and screenshots if you want the es-ES / es-419 listings. **The app itself is now fully localized in Spanish** (docs/I18N.md; it follows the device language and has Settings > Language), so the
  Spanish listing is the remaining owner task. In Play Console add the languages under *Store presence > Main store listing > Manage translations* (Spanish (Spain) es-ES and Spanish (Latin America) es-419 can share one text),
  and prepare: app name (30), short description (80), full description (4000), Spanish phone screenshots (take them in the app set to Español; `mobile/android/README.md` says how to run the app on canned data), a Spanish
  feature graphic if it contains text, release notes per language (`<es-ES>...</es-ES>` tags), the localized privacy policy URL (`https://videomk.com/es/privacy`) and the data-safety and content-rating answers (language-neutral).
  The app label is `videomk` in both languages (a brand name).

## 8. Before the first production release
1. Production backend deployed; set the three `vmkProd*` values; the production Cognito mobile client has the redirect `com.videomk.app://auth/callback`; run the instrumented tests against it.
2. Privacy policy and terms pages live; account deletion and the content-report path built.
3. In-app purchases for credits: Play Billing is **not** built (the iOS app does not have purchases either). Credits must only be sold through Google Play for in-app digital goods:
   create the products in Play Console, add the billing library and a server-side purchase verification (a backend task) before enabling "Get more credits".
4. Abuse controls: the iOS plan uses DeviceCheck / App Attest for one welcome grant per device. Android needs the equivalent (Play Integrity API), a backend task; the app currently sends
   `X-Platform: android` and nothing else. Without it a person can create unlimited accounts for welcome credits.
5. Run the pre-launch report Play offers on internal-test uploads (automatic crawl on real devices) and fix anything it finds.
6. Bump `vmkBuildNumber`, build, upload to *Production* with staged rollout (e.g. 20%).

## 9. Day-to-day release routine
```
cd mobile/android
./gradlew testDebugUnitTest
scripts/run-ui-tests.sh                                   # emulator, QA (see README)
./gradlew bundleRelease -PvmkBuildNumber=<next> [-PvmkReleaseBackend=qa]
# upload app/build/outputs/bundle/release/app-release.aab in the Play Console
```
