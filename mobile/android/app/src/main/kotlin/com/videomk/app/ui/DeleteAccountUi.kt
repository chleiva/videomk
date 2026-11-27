package com.videomk.app.ui

import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.imePadding
import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.layout.widthIn
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.CircularProgressIndicator
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.ModalBottomSheet
import androidx.compose.material3.OutlinedTextField
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.rememberModalBottomSheetState
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.rememberUpdatedState
import androidx.compose.ui.Alignment
import androidx.compose.ui.ExperimentalComposeUiApi
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.alpha
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import com.videomk.app.core.AppleStep
import com.videomk.app.core.DeletionState
import com.videomk.app.core.DeletionText
import androidx.compose.ui.res.stringResource
import com.videomk.app.R
import com.videomk.app.core.ReauthStep

/** The Settings card that leads to the confirmation sheet. */
@Composable
internal fun DeleteAccountCard(onOpen: () -> Unit) {
    Card {
        Column(verticalArrangement = Arrangement.spacedBy(4.dp)) {
            Text(stringResource(R.string.deletion_card_title), style = MaterialTheme.typography.titleSmall, color = Vmk.colors.textSecondary, modifier = Modifier.semantics { heading() })
            Text(DeletionText.SETTINGS_BODY, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.text)
            TextButton(onClick = onOpen, modifier = Modifier.heightIn(min = 48.dp).testTag("deleteAccountButton")) {
                Text(stringResource(R.string.deletion_card_button), color = Vmk.colors.danger, fontWeight = FontWeight.SemiBold)
            }
        }
    }
}

/** Filled red button for the one action that cannot be undone. White text on the light red, dark text on the lighter dark-mode red (contrast above 4.5:1 in both). */
@Composable
internal fun DestructiveButton(text: String, enabled: Boolean, onClick: () -> Unit, modifier: Modifier = Modifier) {
    // the same pill and size as the primary button, in the danger colour; disabled is the kit's opaque quiet fill
    val shape = androidx.compose.foundation.shape.CircleShape
    Box(
        modifier.fillMaxWidth().heightIn(min = Vmk.primaryButton)
            .clip(shape).background(if (enabled) Vmk.colors.danger else Vmk.colors.surface3, shape)
            .clickable(enabled = enabled, role = Role.Button, onClick = onClick).padding(horizontal = Vmk.space.xxl, vertical = Vmk.space.m),
        contentAlignment = Alignment.Center,
    ) { Text(text, style = VmkType.cta, color = if (!enabled) Vmk.colors.textSecondary else MaterialTheme.colorScheme.onError, textAlign = TextAlign.Center) }
}

/**
 * The confirmation sheet. [state] drives it: the form (Idle), the spinner (Working), the "sign in again" page (Reauth) and the failure (Failed).
 * While a request is in flight the sheet cannot be dismissed. [onStart] gets the typed word and is only enabled when it is exactly DELETE.
 */
@OptIn(ExperimentalMaterial3Api::class, ExperimentalComposeUiApi::class)
@Composable
internal fun DeleteAccountSheet(
    state: DeletionState, typed: String, onTyped: (String) -> Unit,
    onStart: (String) -> Unit, onCancelReauth: () -> Unit, onClose: () -> Unit,
) {
    val busy = state is DeletionState.Working
    val busyNow by rememberUpdatedState(busy)
    val shape = RoundedCornerShape(topStart = 30.dp, topEnd = 30.dp)
    ModalBottomSheet(
        onDismissRequest = { if (!busyNow && state !is DeletionState.Reauth) onClose() },
        sheetState = rememberModalBottomSheetState(skipPartiallyExpanded = true, confirmValueChange = { !busyNow && state !is DeletionState.Reauth }),
        shape = shape, containerColor = Vmk.colors.surface,
    ) {
        Column(
            Modifier.fillMaxWidth().imePadding().verticalScroll(rememberScrollState()).padding(horizontal = 20.dp).padding(bottom = 16.dp).navigationBarsPadding()
                .semantics { if (com.videomk.app.BuildConfig.DEBUG) testTagsAsResourceId = true }.testTag("deleteAccountSheet"),
            verticalArrangement = Arrangement.spacedBy(12.dp),
        ) {
            when (state) {
                is DeletionState.Working -> Progress(stringResource(R.string.deletion_working_title), stringResource(R.string.deletion_working_body), null, onCancelReauth)
                is DeletionState.Reauth -> Progress(
                    stringResource(R.string.deletion_reauth_title),
                    stringResource(if (state.step == ReauthStep.LoggingOut) R.string.deletion_reauth_opening else R.string.deletion_reauth_body),
                    stringResource(R.string.common_cancel), onCancelReauth,
                )
                is DeletionState.Failed -> {
                    Header()
                    Text(
                        DeletionText.message(state.reason), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.text,
                        modifier = Modifier.fillMaxWidth().clip(RoundedCornerShape(12.dp)).background(Vmk.colors.dangerContainer).padding(12.dp).testTag("deleteAccountError"),
                    )
                    DestructiveButton(stringResource(R.string.common_try_again), enabled = true, onClick = { onStart(typed) }, modifier = Modifier.testTag("deleteAccountRetry"))
                    TextButton(onClick = onClose, modifier = Modifier.fillMaxWidth().heightIn(min = 48.dp).testTag("deleteAccountClose")) { Text(stringResource(R.string.common_close), color = Vmk.colors.textSecondary, fontWeight = FontWeight.SemiBold) }
                }
                else -> Form(typed, onTyped, onStart, onClose)
            }
        }
    }
}

@Composable
private fun Header() {
    Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp)) {
        Box(Modifier.size(44.dp).clip(CircleShape).background(Vmk.colors.dangerContainer), contentAlignment = Alignment.Center) {
            Icon(Sym.DeleteForever, null, tint = Vmk.colors.danger, modifier = Modifier.size(26.dp))
        }
        Text(stringResource(R.string.deletion_header), style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.weight(1f).semantics { heading() })
    }
}

@Composable
private fun Form(typed: String, onTyped: (String) -> Unit, onStart: (String) -> Unit, onClose: () -> Unit) {
    Header()
    Text(stringResource(R.string.deletion_deletes_title), style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.text, fontWeight = FontWeight.SemiBold)
    Column(verticalArrangement = Arrangement.spacedBy(6.dp)) {
        DeletionText.deletes.forEach { item ->
            Row(horizontalArrangement = Arrangement.spacedBy(10.dp)) {
                Text("•", color = Vmk.colors.danger, fontWeight = FontWeight.Bold)
                Text(item, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.text, modifier = Modifier.weight(1f))
            }
        }
    }
    Text(DeletionText.IRREVERSIBLE, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.danger, fontWeight = FontWeight.Bold)
    Text(stringResource(R.string.deletion_next_title), style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.text, fontWeight = FontWeight.SemiBold)
    Text(DeletionText.NEXT, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary)
    Text(DeletionText.REAUTH_NOTE, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary)
    Text(stringResource(R.string.deletion_type_to_confirm, DeletionText.CONFIRM_WORD), style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.text, fontWeight = FontWeight.SemiBold)
    val typeToConfirm = stringResource(R.string.deletion_type_to_confirm, DeletionText.CONFIRM_WORD)
    VmkField(typed, onTyped, Modifier.semantics { contentDescription = typeToConfirm }.testTag("deleteConfirmField"), keyboardOptions = KeyboardOptions(capitalization = KeyboardCapitalization.Characters, autoCorrectEnabled = false))
    DestructiveButton(stringResource(R.string.deletion_confirm_button), enabled = typed.trim() == DeletionText.CONFIRM_WORD, onClick = { onStart(typed) }, modifier = Modifier.testTag("deleteAccountConfirm"))
    TextAction(stringResource(R.string.common_cancel), onClose, Modifier.fillMaxWidth().testTag("deleteAccountCancel"), color = Vmk.colors.textSecondary)
}

@Composable
private fun Progress(title: String, body: String, cancel: String?, onCancel: () -> Unit) {
    Column(Modifier.fillMaxWidth().padding(top = 8.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(12.dp)) {
        CircularProgressIndicator(Modifier.size(40.dp).semantics { contentDescription = title }, color = Vmk.colors.primary)
        Text(title, style = MaterialTheme.typography.titleLarge, fontWeight = FontWeight.Bold, color = Vmk.colors.text, textAlign = TextAlign.Center, modifier = Modifier.semantics { heading() }.testTag("deleteProgressTitle"))
        Text(body, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, textAlign = TextAlign.Center)
        if (cancel != null) TextButton(onClick = onCancel, modifier = Modifier.heightIn(min = 48.dp).testTag("deleteReauthCancel")) { Text(cancel, color = Vmk.colors.textSecondary, fontWeight = FontWeight.SemiBold) }
    }
}

/** Shown after the server accepted: everything local is already gone and the session is closed. */
@Composable
internal fun DeletionDoneScreen(apple: AppleStep, onOpenApple: () -> Unit, onDone: () -> Unit) {
    Box(Modifier.fillMaxSize().background(Vmk.colors.background).statusBarsPadding().navigationBarsPadding().testTag("deletionDone")) {
        Column(
            Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(horizontal = 24.dp, vertical = 32.dp),
            horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.Center,
        ) {
            Column(Modifier.widthIn(max = 480.dp), horizontalAlignment = Alignment.CenterHorizontally, verticalArrangement = Arrangement.spacedBy(16.dp)) {
                Box(Modifier.size(72.dp).clip(CircleShape).background(Vmk.colors.successContainer), contentAlignment = Alignment.Center) {
                    Icon(Sym.CheckCircle, null, tint = Vmk.colors.success, modifier = Modifier.size(40.dp))
                }
                Text(DeletionText.DONE_TITLE, style = MaterialTheme.typography.headlineSmall, fontWeight = FontWeight.Bold, color = Vmk.colors.text, textAlign = TextAlign.Center, modifier = Modifier.semantics { heading() })
                Text(DeletionText.DONE_BODY, style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.textSecondary, textAlign = TextAlign.Center)
                when (apple) {
                    is AppleStep.Available -> {
                        Text(DeletionText.APPLE_AVAILABLE, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.text, textAlign = TextAlign.Center)
                        PrimaryButton(stringResource(R.string.deletion_apple_button), onOpenApple, Modifier.testTag("deleteAppleButton"))
                    }
                    AppleStep.Manual -> Text(DeletionText.APPLE_MANUAL, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.text, textAlign = TextAlign.Center, modifier = Modifier.testTag("deleteAppleManual"))
                    AppleStep.Done -> Text(DeletionText.APPLE_DONE, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.success, textAlign = TextAlign.Center, modifier = Modifier.testTag("deleteAppleDone"))
                    AppleStep.None -> Unit
                }
                if (apple is AppleStep.Available) TextButton(onClick = onDone, modifier = Modifier.heightIn(min = 48.dp).testTag("deletionDoneButton")) { Text(stringResource(R.string.deletion_skip_close), color = Vmk.colors.textSecondary, fontWeight = FontWeight.SemiBold) }
                else PrimaryButton(stringResource(R.string.common_done), onDone, Modifier.testTag("deletionDoneButton"))
            }
        }
    }
}

/** For the debug fixture only (the real screen is shown by [VideoMkRoot]). */
@Composable
fun DeletionDoneScreenForFixture(apple: AppleStep) = DeletionDoneScreen(apple, onOpenApple = {}, onDone = {})
