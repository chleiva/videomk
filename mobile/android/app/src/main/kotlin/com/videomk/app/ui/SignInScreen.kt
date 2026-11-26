package com.videomk.app.ui

import androidx.annotation.DrawableRes
import androidx.compose.foundation.Image
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.BoxWithConstraints
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.width
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import com.videomk.app.R
import com.videomk.app.core.SignInProvider
import com.videomk.app.core.SocialSwitches
import com.videomk.app.core.label
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
fun SignInScreen(state: AppState, social: SocialSwitches = SocialSwitches(), onSignIn: (SignInProvider) -> Unit) {
    val busy = state.isSigningIn || state.phase == Phase.NotConfigured
    BoxWithConstraints(Modifier.fillMaxSize().background(Vmk.colors.background).statusBarsPadding().navigationBarsPadding()) {
    // at least the screen high so the buttons sit at the bottom, and taller (scrolling) when large text needs it: nothing overlaps or clips
    Column(
        Modifier.fillMaxWidth().heightIn(min = maxHeight).verticalScroll(rememberScrollState()),
        horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.SpaceBetween,
    ) {
        Column(
            Modifier.padding(horizontal = 32.dp, vertical = 32.dp),
            verticalArrangement = Arrangement.spacedBy(20.dp), horizontalAlignment = Alignment.CenterHorizontally,
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
            for (option in social.options) {
                val label = option.label(social.anySocial)
                val spinning = state.isSigningIn && state.signInProvider == option
                when (option) {
                    SignInProvider.Google -> SocialButton(label, R.drawable.ic_google_g, SocialStyle.google(Vmk.colors.dark), !busy, spinning, "googleButton") { onSignIn(option) }
                    SignInProvider.Apple -> SocialButton(label, R.drawable.ic_apple_logo, SocialStyle.apple(Vmk.colors.dark), !busy, spinning, "appleButton") { onSignIn(option) }
                    SignInProvider.Email -> PrimaryButton(
                        label, onClick = { onSignIn(option) }, enabled = !busy,
                        modifier = Modifier.fillMaxWidth().testTag("signInButton"),
                    ) {
                        if (spinning || (state.isSigningIn && state.signInProvider == null)) CircularProgressIndicator(Modifier.size(24.dp).semantics { contentDescription = "Signing in" }, color = Color.White, strokeWidth = 2.dp)
                        else Text(label, style = MaterialTheme.typography.titleMedium, color = Color.White, textAlign = TextAlign.Center)
                    }
                }
            }
            LegalLine()
        }
    }
    }
}

/** Official button colours. Google: white / #747775 outline / #1F1F1F text (light), #131314 / #8E918F / #E3E3E3 (dark). Apple: black with white (light screens), white with black (dark screens). */
data class SocialStyle(val fill: Color, val outline: Color?, val text: Color, val logoTint: Color?) {
    companion object {
        fun google(dark: Boolean) = if (dark) SocialStyle(Color(0xFF131314), Color(0xFF8E918F), Color(0xFFE3E3E3), null) else SocialStyle(Color.White, Color(0xFF747775), Color(0xFF1F1F1F), null)
        fun apple(dark: Boolean) = if (dark) SocialStyle(Color.White, null, Color.Black, Color.Black) else SocialStyle(Color.Black, null, Color.White, Color.White)
    }
}

/** A provider button: logo then wording, 52 dp minimum, grows with the font size and wraps instead of clipping. The logo is decoration; the wording is what TalkBack reads. */
@Composable
fun SocialButton(label: String, @DrawableRes logo: Int, style: SocialStyle, enabled: Boolean, spinning: Boolean, tag: String, onClick: () -> Unit) {
    val shape = RoundedCornerShape(Vmk.radius)
    Row(
        Modifier.fillMaxWidth().heightIn(min = 52.dp).alpha(if (enabled || spinning) 1f else 0.4f)
            .clip(shape).background(style.fill, shape).let { m -> style.outline?.let { m.border(1.dp, it, shape) } ?: m }
            .clickable(enabled = enabled, role = Role.Button, onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp)
            .semantics(mergeDescendants = true) { if (spinning) stateDescription = "Signing in" }
            .testTag(tag),
        horizontalArrangement = Arrangement.Center, verticalAlignment = Alignment.CenterVertically,
    ) {
        if (spinning) CircularProgressIndicator(Modifier.size(20.dp), color = style.text, strokeWidth = 2.dp)
        else Image(painterResource(logo), null, Modifier.size(20.dp).clearAndSetSemantics { }, colorFilter = style.logoTint?.let { ColorFilter.tint(it) })
        Spacer(Modifier.width(12.dp))
        Text(label, style = MaterialTheme.typography.titleMedium, color = style.text, textAlign = TextAlign.Center, modifier = Modifier.weight(1f, fill = false))
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
