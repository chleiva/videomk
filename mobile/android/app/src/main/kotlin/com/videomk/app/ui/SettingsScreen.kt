package com.videomk.app.ui

import androidx.compose.foundation.layout.wrapContentHeight
import androidx.compose.ui.semantics.heading
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.AlertDialog
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Switch
import androidx.compose.foundation.selection.toggleable
import androidx.compose.ui.semantics.Role
import androidx.compose.material3.Text
import androidx.compose.material3.TextButton
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.foundation.background
import androidx.compose.ui.draw.clip
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import com.videomk.app.BuildConfig
import androidx.compose.ui.res.stringResource
import com.videomk.app.R
import com.videomk.app.core.DeletionState

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    email: String?, onBack: () -> Unit, onSignOut: () -> Unit, onFeedback: (() -> Unit)? = null,
    deletion: DeletionState = DeletionState.Idle, onDeleteAccount: ((String) -> Unit)? = null, onCancelDeletion: () -> Unit = {}, onDeletionClosed: () -> Unit = {},
    initialSheetOpen: Boolean = false, initialTyped: String = "",
) {
    var confirm by rememberSaveable { mutableStateOf(false) }
    var deleteSheet by rememberSaveable { mutableStateOf(initialSheetOpen) }
    var typed by rememberSaveable { mutableStateOf(initialTyped) }
    val uri = LocalUriHandler.current
    Scaffold(
        containerColor = Vmk.colors.background,
        topBar = {
            VmkTopBar(title = stringResource(R.string.settings_title), onBack = onBack)
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(horizontal = Vmk.space.screen).padding(bottom = 24.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            // account: the email is the header row; signing out is a plain row (not destructive: no red)
            Card {
                Column {
                    if (email != null) Text(email, style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text, modifier = Modifier.heightIn(min = 48.dp).wrapContentHeight(Alignment.CenterVertically).testTag("accountEmail"))
                    SettingsRow(stringResource(R.string.settings_sign_out), color = Vmk.colors.primary, tag = "signOutButton") { confirm = true }
                }
            }
            Card { LanguageSetting() }
            val context = androidx.compose.ui.platform.LocalContext.current
            val photoSettings = remember { com.videomk.app.data.PhotoSettings(context) }
            var dates by remember { mutableStateOf(photoSettings.useDates) }
            var places by remember { mutableStateOf(photoSettings.useLocations) }
            var photoInfo by rememberSaveable { mutableStateOf(false) }
            val organize = com.videomk.app.ui.LocalContainerOrNull.current?.organize
            // photos: two switches and the organize row; the three explanations live behind one (i)
            Card {
                Column {
                    Row(verticalAlignment = Alignment.CenterVertically) {
                        Text(stringResource(R.string.settings_photos), style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text, modifier = Modifier.weight(1f).semantics { heading() })
                        GlassIconButton(Sym.Info, stringResource(R.string.settings_photos_info), { photoInfo = true }, Modifier.testTag("photosInfo"), size = 44.dp)
                    }
                    SwitchRow(stringResource(R.string.settings_photo_dates), dates, "photoDatesSwitch") { dates = it; photoSettings.useDates = it }
                    SwitchRow(stringResource(R.string.settings_photo_locations), places, "photoLocationsSwitch") { places = it; photoSettings.useLocations = it }
                    organize?.let { OrganizeSetting(it) }
                }
            }
            if (photoInfo) androidx.compose.material3.AlertDialog(
                onDismissRequest = { photoInfo = false }, title = { Text(stringResource(R.string.settings_photos)) },
                text = {
                    Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                        Text(stringResource(R.string.settings_photo_dates_hint), style = MaterialTheme.typography.bodyMedium)
                        Text(stringResource(R.string.settings_photo_locations_hint), style = MaterialTheme.typography.bodyMedium)
                        Text(stringResource(R.string.settings_organize_hint), style = MaterialTheme.typography.bodyMedium)
                        Text(stringResource(R.string.settings_media_privacy), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("mediaPrivacyCopy"))
                    }
                },
                confirmButton = { TextButton(onClick = { photoInfo = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.common_done)) } },
            )
            Card {
                Column {
                    if (onFeedback != null) FeedbackRow(onFeedback)
                    val mailto = stringResource(R.string.settings_support_mailto)
                    SettingsRow(stringResource(R.string.settings_support), tag = "supportLink", onClickLabel = stringResource(R.string.settings_support_open)) { runCatching { uri.openUri(mailto) } }
                }
            }
            Card {
                Column {
                    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).semantics(mergeDescendants = true) {}, verticalAlignment = Alignment.CenterVertically) {
                        Text(stringResource(R.string.settings_about), color = Vmk.colors.text, modifier = Modifier.weight(1f))
                        Text(BuildConfig.VERSION_NAME, color = Vmk.colors.textSecondary)
                    }
                    SettingsRow(stringResource(R.string.settings_privacy_policy), onClickLabel = stringResource(R.string.settings_privacy_open)) { runCatching { uri.openUri("https://videomk.com/privacy") } }
                    val termsUrl = stringResource(R.string.settings_terms_url)
                    SettingsRow(stringResource(R.string.settings_terms), onClickLabel = stringResource(R.string.settings_terms_open)) { runCatching { uri.openUri(termsUrl) } }
                }
            }
            // the confirmation screen already lists what is lost, so the row is just the words, in red
            if (onDeleteAccount != null) Card { SettingsRow(stringResource(R.string.deletion_card_button), color = Vmk.colors.danger, tag = "deleteAccountButton") { deleteSheet = true } }
        }
    }
    if (deleteSheet && onDeleteAccount != null) {
        DeleteAccountSheet(
            state = deletion, typed = typed, onTyped = { typed = it }, onStart = onDeleteAccount, onCancelReauth = onCancelDeletion,
            onClose = { deleteSheet = false; typed = ""; onDeletionClosed() },
        )
    }
    if (confirm) {
        AlertDialog(
            onDismissRequest = { confirm = false },
            title = { Text(stringResource(R.string.settings_sign_out_confirm)) },
            confirmButton = { TextButton(onClick = { confirm = false; onSignOut() }, modifier = Modifier.heightIn(min = 48.dp).testTag("confirmSignOut")) { Text(stringResource(R.string.settings_sign_out), color = Vmk.colors.primary) } },
            dismissButton = { TextButton(onClick = { confirm = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.common_cancel)) } },
        )
    }
}

@Composable
private fun SwitchRow(title: String, checked: Boolean, tag: String, onChange: (Boolean) -> Unit) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 56.dp).toggleable(value = checked, role = Role.Switch, onValueChange = onChange).padding(vertical = Vmk.space.s).testTag(tag),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Text(title, color = Vmk.colors.text, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
        Switch(checked = checked, onCheckedChange = null)
    }
}

/** A plain one-line row: the words only (a value or a chevron only when it adds something). */
@Composable
private fun SettingsRow(text: String, color: androidx.compose.ui.graphics.Color = Vmk.colors.text, tag: String? = null, onClickLabel: String? = null, onClick: () -> Unit) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 52.dp).clickable(onClickLabel = onClickLabel, role = Role.Button, onClick = onClick).then(if (tag != null) Modifier.testTag(tag) else Modifier),
        verticalAlignment = Alignment.CenterVertically,
    ) { Text(text, color = color, style = MaterialTheme.typography.bodyLarge, fontWeight = if (color == Vmk.colors.danger) androidx.compose.ui.text.font.FontWeight.SemiBold else null) }
}

/** "Organize new uploads": a row with its value (Ask, Always, Never) and a menu; the explanation is behind the Photos (i). Reads and writes the server preference. */
@Composable
private fun OrganizeSetting(controller: com.videomk.app.data.OrganizeController) {
    val pref by controller.pref.collectAsState()
    androidx.compose.runtime.LaunchedEffect(Unit) { controller.refreshPref() }
    var open by remember { mutableStateOf(false) }
    androidx.compose.foundation.layout.Box(Modifier.fillMaxWidth().testTag("organizeSetting")) {
        Row(Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(role = Role.DropdownList, onClickLabel = stringResource(R.string.settings_organize_title)) { open = true }.padding(vertical = Vmk.space.s), verticalAlignment = Alignment.CenterVertically) {
            Text(stringResource(R.string.settings_organize_title), style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.text, modifier = Modifier.weight(1f))
            Text(pref.label, style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary)
            Icon(Sym.ExpandMore, null, tint = Vmk.colors.textSecondary)
        }
        androidx.compose.material3.DropdownMenu(expanded = open, onDismissRequest = { open = false }, containerColor = Vmk.colors.surface) {
            for (o in com.videomk.app.core.OrganizePref.entries) androidx.compose.material3.DropdownMenuItem(
                text = { Text(o.label, fontWeight = if (o == pref) androidx.compose.ui.text.font.FontWeight.Bold else androidx.compose.ui.text.font.FontWeight.Normal) },
                trailingIcon = { if (o == pref) Icon(Sym.Check, null, tint = Vmk.colors.primary) },
                onClick = { open = false; controller.setPref(o) }, modifier = Modifier.testTag("organizePref-${o.wire}"),
            )
        }
    }
}
