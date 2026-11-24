import CoreGraphics
import Foundation
import ImageIO
import Testing
import UniformTypeIdentifiers
@testable import VideoMKCore

/// A real JPEG with an orientation tag, GPS, a camera make and a date, as a phone writes it.
private func phoneJPEG(width: Int, height: Int, orientation: Int = 1) -> Data {
    let ctx = CGContext(data: nil, width: width, height: height, bitsPerComponent: 8, bytesPerRow: 0, space: CGColorSpaceCreateDeviceRGB(), bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue)!
    ctx.setFillColor(CGColor(red: 0.8, green: 0.2, blue: 0.2, alpha: 1)); ctx.fill(CGRect(x: 0, y: 0, width: width, height: height))
    let out = NSMutableData()
    let dest = CGImageDestinationCreateWithData(out, UTType.jpeg.identifier as CFString, 1, nil)!
    let props: [CFString: Any] = [
        kCGImagePropertyOrientation: orientation,
        kCGImagePropertyGPSDictionary: [kCGImagePropertyGPSLatitude: 39.57, kCGImagePropertyGPSLatitudeRef: "N", kCGImagePropertyGPSLongitude: 2.65, kCGImagePropertyGPSLongitudeRef: "E"],
        kCGImagePropertyTIFFDictionary: [kCGImagePropertyTIFFMake: "SomePhone Inc."],
        kCGImagePropertyExifDictionary: [kCGImagePropertyExifDateTimeOriginal: "2026:07:12 18:30:00"],
    ]
    CGImageDestinationAddImage(dest, ctx.makeImage()!, props as CFDictionary)
    precondition(CGImageDestinationFinalize(dest))
    return out as Data
}

private func properties(_ data: Data) -> [String: Any] {
    let src = CGImageSourceCreateWithData(data as CFData, nil)!
    return (CGImageSourceCopyPropertiesAtIndex(src, 0, nil) as? [String: Any]) ?? [:]
}

@Suite struct PhotoTests {
    @Test func photoPrepRotatesBoundsTheSizeAndKeepsOnlyPixels() throws {
        let original = phoneJPEG(width: 4000, height: 3000, orientation: 6)   // stored sideways; the tag says "rotate 90 degrees"
        let before = properties(original)
        #expect(before["{GPS}"] != nil && (before["{TIFF}"] as? [String: Any])?["Make"] as? String == "SomePhone Inc.")  // the test photo really carries metadata
        let prepared = try #require(PhotoPrep.jpeg(from: original))
        let after = properties(prepared)
        #expect(after["{GPS}"] == nil && (after["{Exif}"] as? [String: Any])?["DateTimeOriginal"] == nil)   // GPS, date and camera are gone
        #expect((after["{TIFF}"] as? [String: Any])?["Make"] == nil)
        #expect(after["Orientation"] == nil || (after["Orientation"] as? Int) == 1)
        #expect((after["PixelWidth"] as? Int, after["PixelHeight"] as? Int) == (1536, 2048))   // upright (portrait) and 2048 on the long side
        #expect(prepared.count < PhotoLimits.maxUploadBytes)
    }

    @Test func unreadableDataIsRefused() {
        #expect(PhotoPrep.jpeg(from: Data("not a picture".utf8)) == nil)
        #expect(PhotoPrep.jpeg(from: Data()) == nil)
    }

    @Test func multipartPutsTheSignedFieldsFirstAndTheFileLast() throws {
        let file = Data([0xFF, 0xD8, 0xFF, 0xE0, 0x00])
        let (body, type) = MultipartForm.body(fields: ["key": "uploads/u/a.jpg", "policy": "P", "Content-Type": "image/jpeg"], file: file, boundary: "BOUND")
        #expect(type == "multipart/form-data; boundary=BOUND")
        let text = String(decoding: body, as: UTF8.self)
        let order = ["name=\"Content-Type\"", "name=\"key\"", "name=\"policy\"", "name=\"file\""].map { text.range(of: $0)!.lowerBound }
        #expect(order == order.sorted())                       // the file is the last part
        #expect(body.range(of: file) != nil && text.hasSuffix("\r\n--BOUND--\r\n"))
    }
}

// The upload sequence uses the shared URLProtocol stub, so it joins the serialized suite.
extension CoreTests {
    private func slotsJSON(_ n: Int) -> Data {
        let items = (0..<n).map { #"{"id":"\#(String(format: "%016x", $0 + 1))","url":"https://bucket.s3.test/","fields":{"key":"uploads/u/\#($0).jpg","policy":"P","x-amz-signature":"S"}}"# }
        return Data(#"{"uploads":[\#(items.joined(separator: ","))],"max_bytes":10000000}"#.utf8)
    }

    @Test func photosUploadInOrderWithProgressAndWithoutTheLoginToken() async throws {
        nonisolated(unsafe) var seen: [(url: String, auth: String?, type: String?, bytes: Int)] = []
        nonisolated(unsafe) var count = 0
        StubProtocol.handler = { req in
            let body = req.bodyData ?? Data()
            seen.append((req.url!.absoluteString, req.value(forHTTPHeaderField: "Authorization"), req.value(forHTTPHeaderField: "Content-Type"), body.count))
            if req.url!.host == "bucket.s3.test" { count += 1; return (204, Data()) }
            return (200, self.slotsJSON(3))
        }
        let api = APIClient(config: config, auth: FixedAuth(), session: stubSession())
        nonisolated(unsafe) var steps: [String] = []
        let ids = try await PhotoUploader(api: api, session: stubSession()).upload([Data(repeating: 1, count: 10), Data(repeating: 2, count: 20), Data(repeating: 3, count: 30)]) { steps.append("\($0)/\($1)") }
        #expect(ids == ["0000000000000001", "0000000000000002", "0000000000000003"] && count == 3 && steps == ["0/3", "1/3", "2/3", "3/3"])
        let apiCall = seen.first { $0.url.hasSuffix("/users/user-1/uploads") }
        #expect(apiCall?.auth == "Bearer tok")                                                   // our API gets the token
        let s3Calls = seen.filter { $0.url.hasPrefix("https://bucket.s3.test") }
        #expect(s3Calls.count == 3 && s3Calls.allSatisfy { $0.auth == nil && ($0.type ?? "").hasPrefix("multipart/form-data") })   // storage never sees it
    }

    @Test func aFailedPhotoStopsTheSequenceAndSaysSo() async throws {
        nonisolated(unsafe) var posts = 0
        StubProtocol.handler = { req in
            if req.url!.host == "bucket.s3.test" { posts += 1; return posts == 2 ? (403, Data("denied".utf8)) : (204, Data()) }
            return (200, self.slotsJSON(3))
        }
        let api = APIClient(config: config, auth: FixedAuth(), session: stubSession())
        do { _ = try await PhotoUploader(api: api, session: stubSession()).upload([Data([1]), Data([2]), Data([3])]); Issue.record("expected a failure") }
        catch { #expect((error as? APIError)?.message == "A photo couldn't be uploaded. Please try again.") }
        #expect(posts == 2)                                                                        // the third photo was never attempted
        await #expect(throws: APIError.self) { _ = try await PhotoUploader(api: api, session: stubSession()).upload([]) }
        await #expect(throws: APIError.self) { _ = try await PhotoUploader(api: api, session: stubSession()).upload(Array(repeating: Data([1]), count: 11)) }
    }

    @Test func theVideoRequestCarriesThePhotoIds() async throws {
        nonisolated(unsafe) var body: [String: Any] = [:]
        StubProtocol.handler = { req in
            body = (try? JSONSerialization.jsonObject(with: req.bodyData ?? Data()) as? [String: Any]) ?? [:]
            return (202, Data(#"{"video_id":"abc"}"#.utf8))
        }
        let api = APIClient(config: config, auth: FixedAuth(), session: stubSession())
        _ = try await api.startGeneration(prompt: "A day out with the family", clientRequestID: "r", media: ["0000000000000001"])
        #expect(body["media"] as? [String] == ["0000000000000001"])
        _ = try await api.startGeneration(prompt: "A day out with the family", clientRequestID: "r")
        #expect(body["media"] == nil)                                                              // no photos: the field is not sent at all
    }
}

@Suite struct DictationPlanTests {
    typealias P = DictationPlan.Permission
    @Test func ourRecognizerIsUsedWheneverItCanWork_evenBeforePermissionsAreAsked() {
        #expect(DictationPlan.decide(speech: .undetermined, microphone: .undetermined, recognizerAvailable: true, keyboardDictationEnabled: false) == .useApp)
        #expect(DictationPlan.decide(speech: .granted, microphone: .granted, recognizerAvailable: true, keyboardDictationEnabled: true) == .useApp)
    }

    @Test func aDeniedPermissionOrAMissingRecognizerFallsBackToTheKeyboardWhenItsDictationIsOn() {
        for (s, m, r) in [(P.denied, P.granted, true), (.granted, .denied, true), (.granted, .granted, false), (.undetermined, .undetermined, false)] {
            guard case .useKeyboard(let why) = DictationPlan.decide(speech: s, microphone: m, recognizerAvailable: r, keyboardDictationEnabled: true) else { Issue.record("expected keyboard fallback for \(s) \(m) \(r)"); continue }
            #expect(why.contains("keyboard"))
        }
    }

    @Test func withNothingUsableTheMessageSaysHowToFixIt() {
        guard case .blocked(let mic) = DictationPlan.decide(speech: .granted, microphone: .denied, recognizerAvailable: true, keyboardDictationEnabled: false),
              case .blocked(let speech) = DictationPlan.decide(speech: .denied, microphone: .granted, recognizerAvailable: true, keyboardDictationEnabled: false),
              case .blocked(let none) = DictationPlan.decide(speech: .granted, microphone: .granted, recognizerAvailable: false, keyboardDictationEnabled: false)
        else { Issue.record("expected blocked"); return }
        #expect(mic.contains("microphone") && mic.contains("Keyboard"))
        #expect(speech.contains("speech recognition") && speech.contains("Keyboard"))
        #expect(none.contains("Settings") && none.contains("type"))
    }
}

@Suite struct DictationFailureTests {
    typealias F = DictationFailure
    private func c(_ domain: String = "kAFAssistantErrorDomain", code: Int, text: Bool = false, device: Bool = false, on: Bool = true) -> F {
        F.classify(domain: domain, code: code, gotText: text, onDevice: device, dictationEnabled: on)
    }

    @Test func anErrorAfterSpeechIsJustTheEndOfThePhrase() {
        #expect(c(code: 1110, text: true) == .finishQuietly && c("kLSRErrorDomain", code: 201, text: true) == .finishQuietly)
    }

    @Test func cancellationsAreQuiet() { #expect(c(code: 216) == .finishQuietly && c(code: 301) == .finishQuietly) }

    @Test func silenceGetsAFriendlyMessage() {
        guard case .message(let m) = c(code: 1110) else { Issue.record("expected message"); return }
        #expect(m.contains("didn't hear"))
    }

    @Test func dictationSwitchedOffIsSaidPlainlyOnceTheServerRecognizerFailedToo() {
        #expect(c("kLSRErrorDomain", code: 201, device: true, on: false) == .retryOnServer)          // never block on our own reading of the setting
        guard case .message(let m) = c("kLSRErrorDomain", code: 201, device: false, on: false) else { Issue.record("expected message"); return }
        #expect(m.contains("Dictation is turned off") && m.contains("Settings"))
    }

    @Test func aFailedOnDeviceModelRetriesOnTheServerOnce() {
        #expect(c("kLSRErrorDomain", code: 201, device: true) == .retryOnServer && c(code: 1101, device: true) == .retryOnServer)
        guard case .message(let m) = c(code: 1101, device: false) else { Issue.record("expected message"); return }   // already on the server: no more retries
        #expect(m.contains("1101"))
    }

    @Test func noNetworkSaysSo() {
        guard case .message(let m) = c("NSURLErrorDomain", code: -1009) else { Issue.record("expected message"); return }
        #expect(m.contains("internet"))
        guard case .message(let m2) = c(code: 203) else { Issue.record("expected message"); return }
        #expect(m2.contains("internet"))
    }
}
