package com.videomk.app.ui

import androidx.compose.foundation.Image
import androidx.compose.foundation.background
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.PlayArrow
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.clearAndSetSemantics
import androidx.compose.ui.text.LinkAnnotation
import androidx.compose.ui.text.SpanStyle
import androidx.compose.ui.text.TextLinkStyles
import androidx.compose.ui.text.buildAnnotatedString
import androidx.compose.ui.text.withLink
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp

@Composable
fun SignInScreen(state: AppState, onSignIn: () -> Unit) {
    Column(
        Modifier.fillMaxSize().background(Vmk.colors.background).statusBarsPadding().navigationBarsPadding().verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally,
    ) {
        Column(
            Modifier.weight(1f).padding(horizontal = 32.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp, Alignment.CenterVertically), horizontalAlignment = Alignment.CenterHorizontally,
        ) {
            Box(Modifier.size(96.dp).clip(RoundedCornerShape(24.dp)).background(Vmk.gradient).clearAndSetSemantics { }, contentAlignment = Alignment.Center) {
                Icon(Icons.Filled.PlayArrow, null, tint = Color.White, modifier = Modifier.size(56.dp))
            }
            Text("videomk", fontSize = 40.sp, fontWeight = FontWeight.Bold, color = Vmk.colors.text)
            Text(
                "Describe a video. We write it, voice it and draw it.", style = MaterialTheme.typography.titleMedium, textAlign = TextAlign.Center,
                color = Vmk.colors.textSecondary,
            )
        }
        Column(Modifier.widthIn(max = 480.dp).padding(horizontal = 24.dp).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(12.dp), horizontalAlignment = Alignment.CenterHorizontally) {
            if (state.phase == Phase.NotConfigured) {
                Text("Not configured. This build has no server address yet.", color = Vmk.colors.warning, textAlign = TextAlign.Center, modifier = Modifier.testTag("notConfigured"))
            }
            state.signInError?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.danger, textAlign = TextAlign.Center, modifier = Modifier.testTag("signInError")) }
            PrimaryButton(
                "Sign in or create account", onClick = onSignIn, enabled = !state.isSigningIn && state.phase != Phase.NotConfigured,
                modifier = Modifier.fillMaxWidth().testTag("signInButton"),
            ) {
                if (state.isSigningIn) CircularProgressIndicator(Modifier.size(24.dp), color = Color.White, strokeWidth = 2.dp)
                else Text("Sign in or create account", style = MaterialTheme.typography.titleMedium, color = Color.White)
            }
            LegalLine()
        }
    }
}

@Composable
fun LegalLine() {
    val link = TextLinkStyles(SpanStyle(color = MaterialTheme.colorScheme.primary))
    val text = buildAnnotatedString {
        append("By continuing you agree to the ")
        withLink(LinkAnnotation.Url("https://videomk.com/terms", link)) { append("Terms") }
        append(" and ")
        withLink(LinkAnnotation.Url("https://videomk.com/privacy", link)) { append("Privacy Policy") }
        append(".")
    }
    Text(text, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, textAlign = TextAlign.Center)
}
