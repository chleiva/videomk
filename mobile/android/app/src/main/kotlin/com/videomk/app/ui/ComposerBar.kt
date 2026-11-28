package com.videomk.app.ui

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.view.HapticFeedbackConstants
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.animation.animateColorAsState
import androidx.compose.animation.core.Animatable
import androidx.compose.animation.core.RepeatMode
import androidx.compose.animation.core.animateFloat
import androidx.compose.animation.core.infiniteRepeatable
import androidx.compose.animation.core.rememberInfiniteTransition
import androidx.compose.animation.core.tween
import androidx.compose.foundation.background
import androidx.compose.foundation.border
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.WindowInsets
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.ime
import androidx.compose.foundation.layout.navigationBars
import androidx.compose.foundation.layout.offset
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.union
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.layout.windowInsetsPadding
import androidx.compose.foundation.lazy.LazyRow
import androidx.compose.foundation.lazy.itemsIndexed
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TextField
import androidx.compose.material3.TextFieldDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableIntStateOf
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.rememberCoroutineScope
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.scale
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.ColorFilter
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.liveRegion
import androidx.compose.ui.semantics.LiveRegionMode
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.stateDescription
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.unit.dp
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import com.videomk.app.R
import androidx.core.content.ContextCompat
import com.videomk.app.core.AddPhotosLogic
import com.videomk.app.core.ComposerLogic
import com.videomk.app.core.ComposerStatus
import com.videomk.app.core.CreateOptions
import com.videomk.app.core.DictationPlan
import com.videomk.app.core.MediaLabels
import com.videomk.app.core.PhotoLimits
import com.videomk.app.core.StatusKind
import com.videomk.app.core.DictationEngine
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

@Composable
internal fun dictationHint(state: DictationEngine.State) {
    when (state) {
        is DictationEngine.State.Unavailable -> HintRow(state.message, Vmk.colors.warning, "dictationUnavailable")
        is DictationEngine.State.KeyboardHint -> HintRow(state.message, Vmk.colors.textSecondary, "dictationKeyboardHint")
        else -> Unit
    }
}

@Composable
private fun HintRow(message: String, color: Color, tag: String) {
    Row(Modifier.padding(top = 4.dp).testTag(tag), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(6.dp)) {
        Icon(Sym.Warning, null, tint = color, modifier = Modifier.size(16.dp))
        Text(message, style = MaterialTheme.typography.bodySmall, color = color)
    }
}

/** The single place for price, reason and fix: exactly one message at a time. */
@Composable
internal fun StatusLine(status: ComposerStatus, flash: Float, shake: Float, onFix: () -> Unit) {
    val color = when (status.kind) {
        StatusKind.TooLong -> Vmk.colors.danger
        StatusKind.NotAffordable, StatusKind.NoCredits -> Vmk.colors.warning
        StatusKind.Listening -> Vmk.colors.danger
        StatusKind.PhotoHint -> Vmk.colors.text
        else -> Vmk.colors.textSecondary
    }
    val icon = when (status.kind) {
        StatusKind.NotAffordable, StatusKind.NoCredits, StatusKind.TooLong -> Sym.Warning
        StatusKind.Listening -> Sym.GraphicEq
        else -> Sym.Bolt
    }
    val iconTint = when (status.kind) { StatusKind.Ready, StatusKind.Idle, StatusKind.PhotoHint, StatusKind.TooShort -> Vmk.colors.primary; else -> color }
    val tag = when (status.kind) {
        StatusKind.NotAffordable, StatusKind.NoCredits -> "notEnoughCredits"
        StatusKind.PhotoHint -> "photoCapacityHint"
        StatusKind.Ready, StatusKind.Idle -> "costLine"
        else -> "hintLine"
    }
    val bg = Vmk.colors.warningContainer.copy(alpha = flash)
    Column(
        Modifier.fillMaxWidth().offset(x = shake.dp).clip(RoundedCornerShape(10.dp)).background(bg).testTag("statusLine")
            .semantics { liveRegion = LiveRegionMode.Polite },
    ) {
        Row(Modifier.heightIn(min = 28.dp), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
            Icon(icon, null, tint = iconTint, modifier = Modifier.size(15.dp))
            Text(status.text, style = MaterialTheme.typography.bodySmall, fontWeight = FontWeight.Medium, color = color, modifier = Modifier.weight(1f).testTag(tag))
            if (status.fix != null && status.kind != StatusKind.PhotoHint) FixChip(status.fix.label(), status.fix.description(), Modifier.testTag("fixChip"), onFix)
        }
        if (status.fix != null && status.kind == StatusKind.PhotoHint) FixChip(status.fix.label(), status.fix.description(), Modifier.padding(start = 23.dp).testTag("fixChip"), onFix)
    }
}

/** The attached photos: a count row and a horizontally scrolling strip of small previews, each removable (phone and My media in one strip). */
@Composable
internal fun PhotoStrip(composer: ComposerViewModel) {
    val phone = composer.photos.size + composer.loading
    val library = composer.library.size
    val source = stringResource(when { phone > 0 && library > 0 -> R.string.composer_source_both; library > 0 -> R.string.composer_source_library; else -> R.string.composer_source_phone })
    val total = composer.photos.size + composer.library.size
    // plain copies for the lazy row: a lazy item lambda that reads the live SnapshotStateList can run after the list changed (library cleared or trimmed in an effect)
    // and crash with IndexOutOfBounds; a copy taken in composition always agrees with the count it was taken with
    val stripPhotos = composer.photos.toList()
    val stripLibrary = composer.library.toList().distinctBy { it.id }
    Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
        Row(Modifier.fillMaxWidth(), verticalAlignment = Alignment.CenterVertically) {
            Text(
                stringResource(R.string.composer_photos_of_max, total, PhotoLimits.MAX_PHOTOS), style = MaterialTheme.typography.labelLarge, fontWeight = FontWeight.SemiBold,
                color = Vmk.colors.textSecondary, modifier = Modifier.weight(1f).testTag("photosNote"),
            )
            Text(source, style = MaterialTheme.typography.labelMedium, color = Vmk.colors.textSecondary)
        }
        if (composer.loading > 0) Text(composer.preparingText, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("photosPreparing"))
        composer.notice?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.warning, modifier = Modifier.testTag("photosNotice")) }
        LazyRow(horizontalArrangement = Arrangement.spacedBy(8.dp), contentPadding = PaddingValues(end = 4.dp)) {
            itemsIndexed(stripPhotos, key = { _, p -> p.id }) { index, photo ->
                val photoDescription = stringResource(R.string.composer_photo_n_of, index + 1, total)
                StripTile(Modifier.semantics { contentDescription = photoDescription }.testTag("attachedPhoto"), stringResource(R.string.composer_remove_photo_n, index + 1), { composer.removePhoto(photo.id) }) {
                    photo.thumbnail?.let { Image(it, it.hashCode()) }
                }
            }
            itemsIndexed(stripLibrary, key = { _, p -> "lib-${p.id}" }) { _, photo ->
                val libraryDescription = stringResource(R.string.composer_from_library_photo, MediaLabels.photo(photo))
                StripTile(Modifier.semantics { contentDescription = libraryDescription }.testTag("attachedLibraryPhoto"), stringResource(R.string.composer_remove_from_video), { composer.removeLibrary(photo.id) }) {
                    PhotoThumb(photo, Modifier.size(56.dp))
                }
            }
            if (composer.loading > 0) item(key = "preparing") {
                Box(Modifier.size(56.dp).clip(RoundedCornerShape(12.dp)).background(Vmk.colors.surfaceRaised), contentAlignment = Alignment.Center) {
                    androidx.compose.material3.CircularProgressIndicator(Modifier.size(22.dp), strokeWidth = 2.dp)
                }
            }
        }
    }
}

@Composable
private fun Image(bitmap: android.graphics.Bitmap, key: Int) {
    androidx.compose.foundation.Image(bitmap.asImageBitmap(), null, contentScale = ContentScale.Crop, modifier = Modifier.size(56.dp))
}

@Composable
private fun StripTile(modifier: Modifier, removeLabel: String, onRemove: () -> Unit, content: @Composable () -> Unit) {
    Box(modifier.size(56.dp)) {
        Box(Modifier.size(56.dp).clip(RoundedCornerShape(12.dp))) { content() }
        // 18 dp to look at, 44 dp to hit
        Box(Modifier.align(Alignment.TopEnd).offset(x = 12.dp, y = (-12).dp).size(44.dp).clickable(onClickLabel = removeLabel, role = Role.Button, onClick = onRemove), contentAlignment = Alignment.Center) {
            Box(Modifier.size(18.dp).clip(CircleShape).background(Color.Black.copy(alpha = 0.7f)), contentAlignment = Alignment.Center) {
                Icon(Sym.Close, removeLabel, tint = Color.White, modifier = Modifier.size(12.dp))
            }
        }
    }
}
