plugins {
    alias(libs.plugins.android.application)
    alias(libs.plugins.kotlin.compose)
}

val versionNameValue: String = providers.gradleProperty("vmkVersionName").get()
val buildNumber: Int = providers.gradleProperty("vmkBuildNumber").map { it.toInt() }.get()
check(buildNumber in 1..2_100_000_000) { "vmkBuildNumber $buildNumber is outside what Google Play accepts as a version code" }

// Release signing comes from the environment or ~/.gradle/gradle.properties (VMK_KEYSTORE_PATH / vmkKeystorePath etc.), never from the repository.
// With any of them missing the release build is produced unsigned (assembleRelease / bundleRelease still succeed; sign before uploading).
fun signingValue(env: String, prop: String): String? =
    providers.environmentVariable(env).orElse(providers.gradleProperty(prop)).orNull?.takeIf { it.isNotBlank() }

val keystorePath = signingValue("VMK_KEYSTORE_PATH", "vmkKeystorePath")
val keystorePassword = signingValue("VMK_KEYSTORE_PASSWORD", "vmkKeystorePassword")
val signingKeyAlias = signingValue("VMK_KEY_ALIAS", "vmkKeyAlias")
val signingKeyPassword = signingValue("VMK_KEY_PASSWORD", "vmkKeyPassword") ?: keystorePassword
val releaseIsSigned = keystorePath != null && file(keystorePath).isFile && keystorePassword != null && signingKeyAlias != null && signingKeyPassword != null

// Production backend: not deployed yet. Fill these three in (or pass -PvmkProdApiBase=... etc.) when it is; until then a release build shows "Not configured",
// exactly like the iOS Release configuration. -PvmkReleaseBackend=qa builds a release-compiled app against QA (the iOS "Beta" equivalent).
fun backend(prop: String, qa: String, prod: String): String {
    val useQa = providers.gradleProperty("vmkReleaseBackend").orNull == "qa"
    return if (useQa) qa else providers.gradleProperty(prop).orElse(prod).get()
}
// Social sign-in buttons (Google, Apple) through the Cognito hosted UI. OFF unless the owner passes -PvmkAuthGoogle=true / -PvmkAuthApple=true
// (or sets them in ~/.gradle/gradle.properties): the identity providers must exist on the Cognito app client first (docs/AUTH_SOCIAL.md).
val authGoogle = providers.gradleProperty("vmkAuthGoogle").orElse("false").get().toBoolean()
val authApple = providers.gradleProperty("vmkAuthApple").orElse("false").get().toBoolean()
val qaApi = "https://rj1uhfqld0.execute-api.eu-west-1.amazonaws.com/prod"
val qaAuth = "https://videomk-qa-225438.auth.eu-west-1.amazoncognito.com"
val qaClient = "5j3hia3hdqa5g3gob8np0t5421"

android {
    namespace = "com.videomk.app"
    compileSdk = 37

    defaultConfig {
        applicationId = "com.videomk.app"
        minSdk = 26
        targetSdk = 36
        versionCode = buildNumber
        versionName = versionNameValue
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        manifestPlaceholders["authScheme"] = "com.videomk.app"
        manifestPlaceholders["authHost"] = "auth"
        manifestPlaceholders["authPath"] = "/callback"
        buildConfigField("boolean", "VMK_AUTH_GOOGLE", authGoogle.toString())
        buildConfigField("boolean", "VMK_AUTH_APPLE", authApple.toString())
        buildConfigField("String", "AUTH_REDIRECT_URI", "\"com.videomk.app://auth/callback\"")
    }

    signingConfigs {
        if (releaseIsSigned) {
            create("release") {
                storeFile = file(keystorePath!!)
                storePassword = keystorePassword
                keyAlias = signingKeyAlias
                keyPassword = signingKeyPassword
            }
        }
    }

    buildTypes {
        debug {
            buildConfigField("String", "API_BASE", "\"$qaApi\"")
            buildConfigField("String", "AUTH_DOMAIN", "\"$qaAuth\"")
            buildConfigField("String", "CLIENT_ID", "\"$qaClient\"")
        }
        release {
            buildConfigField("String", "API_BASE", "\"${backend("vmkProdApiBase", qaApi, "")}\"")
            buildConfigField("String", "AUTH_DOMAIN", "\"${backend("vmkProdAuthDomain", qaAuth, "")}\"")
            buildConfigField("String", "CLIENT_ID", "\"${backend("vmkProdClientId", qaClient, "")}\"")
            isMinifyEnabled = true
            isShrinkResources = true
            signingConfig = if (releaseIsSigned) signingConfigs.getByName("release") else null
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }
    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }
    buildFeatures {
        compose = true
        buildConfig = true
    }
    testOptions {
        unitTests.isReturnDefaultValues = true
    }
    packaging {
        resources.excludes += setOf("/META-INF/{AL2.0,LGPL2.1}", "META-INF/LICENSE*", "META-INF/DEPENDENCIES")
    }
    lint {
        abortOnError = true
        checkReleaseBuilds = true
        error += setOf("MissingTranslation", "ExtraTranslation")   // docs/I18N.md: a missing Spanish string is a bug
        disable += "ObsoleteSdkInt"   // the adaptive icon must stay in mipmap-anydpi-v26 (aapt2 does not accept it in an unqualified anydpi folder)
    }
}

dependencies {
    implementation(platform(libs.androidx.compose.bom))
    implementation(libs.androidx.core.ktx)
    implementation(libs.androidx.activity.compose)
    implementation(libs.androidx.compose.ui)
    implementation(libs.androidx.compose.foundation)
    implementation(libs.androidx.compose.material3)
    implementation(libs.androidx.compose.material.icons)
    implementation(libs.androidx.compose.ui.tooling.preview)
    implementation(libs.androidx.lifecycle.viewmodel.compose)
    implementation(libs.androidx.lifecycle.runtime.compose)
    implementation(libs.androidx.navigation.compose)
    implementation(libs.androidx.browser)
    implementation(libs.androidx.security.crypto)
    implementation(libs.androidx.exifinterface)
    implementation(libs.androidx.media3.exoplayer)
    implementation(libs.androidx.media3.ui)
    implementation(libs.okhttp)
    implementation(libs.kotlinx.serialization.json)
    implementation(libs.kotlinx.coroutines.android)
    implementation(libs.coil.compose)
    implementation(libs.coil.network.okhttp)
    debugImplementation(libs.androidx.compose.ui.tooling)
    debugImplementation(libs.androidx.compose.ui.test.manifest)

    testImplementation(libs.junit)
    testImplementation(libs.kotlinx.coroutines.test)
    testImplementation(libs.okhttp.mockwebserver)

    androidTestImplementation(platform(libs.androidx.compose.bom))
    androidTestImplementation(libs.androidx.test.ext.junit)
    androidTestImplementation(libs.androidx.test.runner)
    androidTestImplementation(libs.androidx.test.rules)
    androidTestImplementation(libs.androidx.test.uiautomator)
    androidTestImplementation(libs.androidx.compose.ui.test.junit4)
}
