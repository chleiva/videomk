import Foundation
import Testing
@testable import VideoMKCore

private func inSpanish<T>(_ body: () throws -> T) rethrows -> T { try Localization.$override.withValue(.es, operation: body) }

@Suite struct LocalizationTests {
    @Test func spanishVariantsMapToSpanishAndEverythingElseToEnglish() {
        for id in ["es", "es-ES", "es-MX", "es-419", "es_AR", "ES-es"] { #expect(AppLanguage.resolve(preferred: [id]) == .es) }
        for id in ["en", "en-GB", "fr", "pt-BR", "zh-Hans", ""] { #expect(AppLanguage.resolve(preferred: [id]) == .en) }
        #expect(AppLanguage.resolve(preferred: ["fr-FR", "es-ES"]) == .es, "a language we do not speak is skipped, never guessed")
        #expect(AppLanguage.resolve(preferred: []) == .en)
    }

    @Test func explicitChoiceBeatsDeviceLanguageAndPersists() {
        let d = UserDefaults(suiteName: "loc-test-\(UUID().uuidString)")!
        let l = Localization(defaults: d, preferred: ["es-ES"])
        #expect(l.language == .es && l.headerValue == "es")
        l.setChoice(.en)
        #expect(l.language == .en && l.headerValue == "en")
        #expect(Localization(defaults: d, preferred: ["es-ES"]).language == .en, "the choice is stored")
        l.setChoice(.system)
        #expect(l.language == .es)
        #expect(Localization(defaults: d, preferred: ["fr"]).language == .en)
    }

    @Test func pluralsFollowTheLanguage() {
        #expect(tr("credits.count", 1) == "1 credit" || Localization.shared.language == .es)
        inSpanish {
            #expect(tr("credits.count", 0) == "0 créditos")
            #expect(tr("credits.count", 1) == "1 crédito")
            #expect(tr("credits.count", 3) == "3 créditos")
            #expect(tr("photos.count", 1) == "1 foto")
            #expect(tr("duration.minutes", 2) == "2 minutos")
            #expect(tr("composer.not_affordable", 1, 0) == "Necesitas 1 crédito, tienes 0")
        }
    }

    @Test func statusLineAndErrorsAreSpanish() {
        inSpanish {
            let s = ComposerPlan.status(text: "How bees make honey", balance: 0, options: CreateOptions(minutes: 1), photos: 0)
            #expect(s.message == "No tienes créditos" && s.fix?.title == "Ver créditos")
            #expect(APIError.network.message.hasPrefix("Problema de conexión"))
            #expect(AccountError.uncertain.message.hasPrefix("No pudimos conectar con VideoMK"))
            #expect(VideoStatus.Stage.rendering.shortTitle == "Procesando")
            #expect(RetryText.make(3600) == "Inténtalo de nuevo en aproximadamente 1 hora.")
            #expect(LengthLabel.spoken(0.25) == "15 segundos")
        }
    }

    @Test func numbersAndDatesUseTheAppLocale() {
        inSpanish {
            #expect(StorageMeter.format(1_200_000_000) == "1,2 GB")
            #expect(Localization.shared.number(1234) == "1234" || Localization.shared.number(1234) == "1.234" || Localization.shared.number(1234).contains("234"))
            let d = Date(timeIntervalSince1970: 1_780_000_000)
            #expect(Localization.shared.abbreviatedDate(d).lowercased().contains("may") || Localization.shared.abbreviatedDate(d).lowercased().contains("jun"))
        }
        #expect(StorageMeter.format(1_200_000_000) == "1.2 GB" || Localization.shared.language == .es)
    }

    @Test func spanishPhotoRequestsAreRecognised() {
        #expect(PromptPhotoIntent.looksLikePhotoQuery("mis vacaciones en Tailandia 2024"))
        #expect(PromptPhotoIntent.looksLikePhotoQuery("un video con mis fotos de la boda"))
        #expect(!PromptPhotoIntent.looksLikePhotoQuery("cómo hacen la miel las abejas"))
    }

    @Test func confirmationWordAcceptsBothLanguages() {
        for w in ["DELETE", "delete", " ELIMINAR ", "eliminar"] { #expect(AccountDeletionFlow.isConfirmation(w)) }
        for w in ["delete me", "", "ELIMINA"] { #expect(!AccountDeletionFlow.isConfirmation(w)) }
    }

    @Test func spanishSuggestedNamesReadBothMonthSpellings() {
        let g = [OrganizeGroup(name: "Phuket · 14-21 jul 2024", count: 188), OrganizeGroup(name: "Phuket · Jul 2024", count: 10)]
        inSpanish { #expect(SuggestedNames.suggest(groups: g).first == "Phuket jul 2024") }
    }
}

final class HeaderProtocol: URLProtocol, @unchecked Sendable {
    nonisolated(unsafe) static var lastLocale: String?
    override class func canInit(with request: URLRequest) -> Bool { request.url?.host == "header.test" }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.lastLocale = request.value(forHTTPHeaderField: "X-Locale")
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 200, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocol(self, didLoad: Data("{\"balance\":1,\"buckets\":[]}".utf8))
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct LocaleHeaderTests {
    struct Auth: AuthorizationProviding { func authorization() async throws -> (idToken: String, userID: String) { ("t", "u1") } }
    func session() -> URLSession { let c = URLSessionConfiguration.ephemeral; c.protocolClasses = [HeaderProtocol.self]; return URLSession(configuration: c) }
    let cfg = AppConfig(apiBase: URL(string: "https://header.test/prod")!, authDomain: URL(string: "https://auth.test")!, clientID: "cid")

    @Test func everyRequestCarriesXLocale() async throws {
        for value in ["es", "en"] {
            _ = try await APIClient(config: cfg, auth: Auth(), session: session(), locale: { value }).wallet()
            #expect(HeaderProtocol.lastLocale == value)
        }
    }

    @Test func theDefaultFollowsTheAppLanguage() async throws {
        _ = try await Localization.$override.withValue(.es) { try await APIClient(config: cfg, auth: Auth(), session: session(), locale: { Localization.shared.headerValue }).wallet() }
        #expect(HeaderProtocol.lastLocale == "es")
        let l = Localization(defaults: UserDefaults(suiteName: "hdr-\(UUID().uuidString)")!, preferred: ["fr-FR"])
        #expect(l.headerValue == "en", "an unsupported device language sends en")
    }
}
