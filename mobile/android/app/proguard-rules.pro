# R8 rules for the release build. Libraries ship their own consumer rules; this file records what the app itself relies on.
-keepattributes SourceFile,LineNumberTable
-renamesourcefileattribute SourceFile
-dontwarn okhttp3.internal.platform.**
-dontwarn org.conscrypt.**
-dontwarn org.bouncycastle.**
-dontwarn org.openjsse.**

# Play review-ktx references a compile-time-only annotation from Play services base
-dontwarn com.google.android.gms.common.annotation.NoNullnessRewrite
