package com.videomk.app.ui

import androidx.compose.runtime.setValue
import androidx.compose.runtime.getValue
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.foundation.layout.height
import androidx.compose.material3.Icon
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.liveRegion

import androidx.compose.foundation.shape.CircleShape
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
import androidx.compose.ui.res.stringResource
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
import androidx.compose.foundation.layout.aspectRatio
import androidx.compose.runtime.remember
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.verticalScroll
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

/**
 * Sign-in (docs/DESIGN_BAR_2026.md, `phone_1_signin`): a sample of what the app makes fills the top of the screen (a still; a muted looping clip when
 * `res/raw/sample_intro.mp4` exists), with the sentence that made it; below, the mark, the promise and the ways in. Provider buttons are drawn only when this build
 * has them switched on; with them, email steps back to a text button ("Use email"); alone, it is the one primary button.
 */
@Composable
fun SignInScreen(state: AppState, social: SocialSwitches = SocialSwitches(), onSignIn: (SignInProvider) -> Unit) {
    val signingInText = stringResource(R.string.auth_signing_in)
    val busy = state.isSigningIn || state.phase == Phase.NotConfigured
    val bg = Vmk.colors.background
    BoxWithConstraints(Modifier.fillMaxSize().background(bg)) {
        val full = maxHeight
        // the sample: decoration for the eye, silent for TalkBack (the promise below says the same in words)
        Box(Modifier.fillMaxWidth().height(full * 0.64f).clearAndSetSemantics { }) {
            val clip = sampleVideoRes(androidx.compose.ui.platform.LocalContext.current)
            // our own footage: a still from the sample video, and over it the same video as a silent loop (the still alone when animations are off)
            Image(painterResource(R.drawable.signin_sample), null, Modifier.fillMaxSize(), contentScale = androidx.compose.ui.layout.ContentScale.Crop)
            if (clip != null && !reduceMotion(androidx.compose.ui.platform.LocalContext.current)) SignInSample(clip, Modifier.fillMaxSize(), fill = true)
            Box(Modifier.fillMaxSize().background(androidx.compose.ui.graphics.Brush.verticalGradient(0f to Color.Black.copy(alpha = 0.18f), 0.35f to Color.Transparent, 0.62f to Color.Transparent, 1f to bg)))
            // no words on the footage: it speaks for itself (the screen's budget is 12 words plus the buttons)
        }
        // at least the screen high so the buttons sit at the bottom, and taller (scrolling over the picture) when large text needs it: nothing overlaps or clips
        Column(Modifier.fillMaxWidth().heightIn(min = full).verticalScroll(rememberScrollState()).statusBarsPadding().navigationBarsPadding(), verticalArrangement = Arrangement.Bottom, horizontalAlignment = Alignment.CenterHorizontally) {
            Spacer(Modifier.height(full * 0.22f))
            Column(
                Modifier.fillMaxWidth().background(androidx.compose.ui.graphics.Brush.verticalGradient(0f to bg.copy(alpha = 0f), 0.22f to bg.copy(alpha = 0.94f), 0.4f to bg, 1f to bg)).widthIn(max = 520.dp)
                    .padding(horizontal = Vmk.space.xxl).padding(top = Vmk.space.xxxl, bottom = Vmk.space.l),
                verticalArrangement = Arrangement.spacedBy(Vmk.space.m),
            ) {
                LogoMark(Modifier.clearAndSetSemantics { }, size = 56.dp)
                Text(stringResource(R.string.auth_tagline), style = MaterialTheme.typography.headlineLarge, color = Vmk.colors.text, modifier = Modifier.padding(top = Vmk.space.s, bottom = Vmk.space.m).semantics { heading() }.testTag("tagline"))
                if (state.phase == Phase.NotConfigured) Text(stringResource(R.string.auth_not_configured), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.warning, modifier = Modifier.testTag("notConfigured"))
                state.signInError?.let {
                    Row(Modifier.semantics { liveRegion = androidx.compose.ui.semantics.LiveRegionMode.Assertive }, verticalAlignment = Alignment.Top, horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
                        Icon(Sym.Warning, null, tint = Vmk.colors.danger, modifier = Modifier.size(18.dp))
                        Text(it, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.text, modifier = Modifier.testTag("signInError"))
                    }
                }
                // Apple first, as in the mockup (never less prominent than another provider's button), then Google, then email
                for (option in social.options.sortedBy { it != SignInProvider.Apple }) {
                    val label = option.label(social.anySocial)
                    val spinning = state.isSigningIn && state.signInProvider == option
                    when (option) {
                        SignInProvider.Google -> SocialButton(label, R.drawable.ic_google_g, SocialStyle.google(Vmk.colors.dark), !busy, spinning, "googleButton") { onSignIn(option) }
                        SignInProvider.Apple -> SocialButton(label, R.drawable.ic_apple_logo, SocialStyle.apple(Vmk.colors.dark), !busy, spinning, "appleButton") { onSignIn(option) }
                        // alone it is the one primary button; beside the provider buttons it steps back to a text button so there is one clear hierarchy
                        SignInProvider.Email -> {
                            val emailSpinning = spinning || (state.isSigningIn && state.signInProvider == null)
                            if (social.anySocial) Box(
                                Modifier.fillMaxWidth().heightIn(min = Vmk.minTouch).alpha(if (busy && !emailSpinning) 0.4f else 1f).clip(CircleShape)
                                    .clickable(enabled = !busy, role = Role.Button) { onSignIn(option) }.padding(horizontal = Vmk.space.l, vertical = Vmk.space.m).testTag("signInButton"),
                                contentAlignment = Alignment.Center,
                            ) {
                                if (emailSpinning) LiveRing(Modifier.semantics { contentDescription = signingInText })
                                else Text(label, style = MaterialTheme.typography.titleMedium, color = Vmk.colors.primary, textAlign = TextAlign.Center)
                            } else PrimaryButton(label, onClick = { onSignIn(option) }, enabled = !busy || emailSpinning, modifier = Modifier.fillMaxWidth().testTag("signInButton")) {
                                if (emailSpinning) LiveRing(Modifier.semantics { contentDescription = signingInText }, track = Color.White.copy(alpha = 0.3f), color = Color.White)
                                else Text(label, style = VmkType.cta, color = androidx.compose.material3.LocalContentColor.current, textAlign = TextAlign.Center)
                            }
                        }
                    }
                }
                Box(Modifier.fillMaxWidth().padding(top = Vmk.space.xs), contentAlignment = Alignment.Center) { LegalLine() }
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
    val signingInText = stringResource(R.string.auth_signing_in)
    val shape = CircleShape
    Row(
        Modifier.fillMaxWidth().heightIn(min = Vmk.primaryButton).alpha(if (enabled || spinning) 1f else 0.4f)
            .clip(shape).background(style.fill, shape).let { m -> style.outline?.let { m.border(1.dp, it, shape) } ?: m }
            .clickable(enabled = enabled, role = Role.Button, onClick = onClick)
            .padding(horizontal = 16.dp, vertical = 12.dp)
            .semantics(mergeDescendants = true) { if (spinning) stateDescription = signingInText }
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
    val template = stringResource(R.string.auth_legal_line, "\u0001", "\u0002")
    val termsLabel = stringResource(R.string.auth_terms)
    val privacyLabel = stringResource(R.string.auth_privacy_policy)
    val text = buildAnnotatedString {
        // the sentence is one resource; the two links are put in where its placeholders are
        var rest = template
        while (rest.isNotEmpty()) {
            val i = rest.indexOfFirst { it == '\u0001' || it == '\u0002' }
            if (i < 0) { append(rest); break }
            append(rest.substring(0, i))
            if (rest[i] == '\u0001') withLink(LinkAnnotation.Url("https://videomk.com/terms", link)) { append(termsLabel) }
            else withLink(LinkAnnotation.Url("https://videomk.com/privacy", link)) { append(privacyLabel) }
            rest = rest.substring(i + 1)
        }
    }
    Box(Modifier.heightIn(min = Vmk.minTouch), contentAlignment = Alignment.Center) { Text(text, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, textAlign = TextAlign.Center) }
}

/** The id of `res/raw/sample_intro`, or null while that asset does not exist (none ships today: the owner has not supplied one). */
fun sampleVideoRes(context: android.content.Context): Int? =
    context.resources.getIdentifier("sample_intro", "raw", context.packageName).takeIf { it != 0 }

/**
 * A muted, looped sample clip above the sign-in buttons. It never makes a sound. It is drawn on a TextureView that stays invisible until the first frame is on it,
 * so the still underneath shows from the first moment (a SurfaceView would punch a black hole until the decoder starts), then it fades in. The picture is
 * centre-cropped to fill, like the still.
 */
@androidx.annotation.OptIn(androidx.media3.common.util.UnstableApi::class)
@Composable
fun SignInSample(res: Int, modifier: Modifier = Modifier, fill: Boolean = false) {
    val context = androidx.compose.ui.platform.LocalContext.current
    var shown by remember { androidx.compose.runtime.mutableStateOf(false) }
    var videoRatio by remember { androidx.compose.runtime.mutableFloatStateOf(0f) }
    val player = remember {
        androidx.media3.exoplayer.ExoPlayer.Builder(context).build().apply {
            volume = 0f; repeatMode = androidx.media3.common.Player.REPEAT_MODE_ALL
            setMediaItem(androidx.media3.common.MediaItem.fromUri("android.resource://${context.packageName}/$res")); prepare(); playWhenReady = true
        }
    }
    androidx.compose.runtime.DisposableEffect(player) {
        val l = object : androidx.media3.common.Player.Listener {
            override fun onRenderedFirstFrame() { shown = true }
            override fun onVideoSizeChanged(size: androidx.media3.common.VideoSize) { if (size.height > 0) videoRatio = size.width.toFloat() / size.height }
        }
        player.addListener(l)
        onDispose { player.removeListener(l); player.release() }
    }
    // the app left the screen: the loop stops; back: it goes on
    androidx.lifecycle.compose.LifecycleStartEffect(player) { player.play(); onStopOrDispose { player.pause() } }
    val alpha by androidx.compose.animation.core.animateFloatAsState(if (shown) 1f else 0f, androidx.compose.animation.core.tween(300), label = "sample")
    androidx.compose.foundation.layout.BoxWithConstraints((if (fill) modifier else modifier.fillMaxWidth().aspectRatio(16f / 9f).clip(RoundedCornerShape(Vmk.radii.videoCard))).clipToBounds().clearAndSetSemantics { }) {
        val viewRatio = if (maxHeight.value > 0f) maxWidth.value / maxHeight.value else 1f
        // a TextureView stretches the video over itself: scale the longer side up so it fills and crops from the centre
        val sx = if (videoRatio > 0f && videoRatio > viewRatio) videoRatio / viewRatio else 1f
        val sy = if (videoRatio > 0f && videoRatio < viewRatio) viewRatio / videoRatio else 1f
        androidx.compose.ui.viewinterop.AndroidView(
            factory = { c -> android.view.TextureView(c).also { player.setVideoTextureView(it) } },
            modifier = Modifier.fillMaxSize().graphicsLayer { this.alpha = alpha; scaleX = sx; scaleY = sy },
        )
    }
}
