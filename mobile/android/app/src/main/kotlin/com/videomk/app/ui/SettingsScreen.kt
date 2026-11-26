package com.videomk.app.ui

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
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.AutoAwesome
import androidx.compose.material.icons.automirrored.filled.ArrowBack
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
    email: String?, onBack: () -> Unit, onSignOut: () -> Unit,
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
            TopAppBar(
                title = { Text(stringResource(R.string.settings_title)) },
                navigationIcon = { IconButton(onClick = onBack, modifier = Modifier.size(48.dp)) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.common_back)) } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Vmk.colors.background, titleContentColor = Vmk.colors.text),
            )
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Card {
                Column {
                    Text(stringResource(R.string.settings_account), style = MaterialTheme.typography.titleSmall, color = Vmk.colors.textSecondary)
                    if (email != null) @OptIn(androidx.compose.foundation.layout.ExperimentalLayoutApi::class) androidx.compose.foundation.layout.FlowRow(
                        Modifier.fillMaxWidth().heightIn(min = 48.dp).semantics(mergeDescendants = true) {}, horizontalArrangement = Arrangement.SpaceBetween,
                        verticalArrangement = Arrangement.Center, itemVerticalAlignment = Alignment.CenterVertically,
                    ) {
                        Text(stringResource(R.string.settings_signed_in_as), color = Vmk.colors.text, modifier = Modifier.padding(end = 12.dp))
                        Text(email, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("accountEmail"))
                    }
                    TextButton(onClick = { confirm = true }, modifier = Modifier.heightIn(min = 48.dp).testTag("signOutButton")) { Text(stringResource(R.string.settings_sign_out), color = Vmk.colors.primary) }   // signing out is not destructive: no danger red
                }
            }
            Card { LanguageSetting() }
            val context = androidx.compose.ui.platform.LocalContext.current
            val photoSettings = remember { com.videomk.app.data.PhotoSettings(context) }
            var dates by remember { mutableStateOf(photoSettings.useDates) }
            var places by remember { mutableStateOf(photoSettings.useLocations) }
            Card {
                Column {
                    Text(stringResource(R.string.settings_photos), style = MaterialTheme.typography.titleSmall, color = Vmk.colors.textSecondary)
                    SwitchRow(stringResource(R.string.settings_photo_dates), stringResource(R.string.settings_photo_dates_hint), dates, "photoDatesSwitch") { dates = it; photoSettings.useDates = it }
                    SwitchRow(
                        stringResource(R.string.settings_photo_locations),
                        stringResource(R.string.settings_photo_locations_hint),
                        places, "photoLocationsSwitch",
                    ) { places = it; photoSettings.useLocations = it }
                    Text(stringResource(R.string.settings_media_privacy), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 8.dp).testTag("mediaPrivacyCopy"))
                    com.videomk.app.ui.LocalContainerOrNull.current?.organize?.let { OrganizeSetting(it) }
                }
            }
            if (onDeleteAccount != null) DeleteAccountCard { deleteSheet = true }
            Card {
                Column {
                    Text(stringResource(R.string.settings_about), style = MaterialTheme.typography.titleSmall, color = Vmk.colors.textSecondary)
                    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).semantics(mergeDescendants = true) {}, verticalAlignment = Alignment.CenterVertically) {
                        Text(stringResource(R.string.settings_version), color = Vmk.colors.text, modifier = Modifier.weight(1f))
                        Text(BuildConfig.VERSION_NAME, color = Vmk.colors.textSecondary)
                    }
                    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(onClickLabel = stringResource(R.string.settings_privacy_open)) { runCatching { uri.openUri("https://videomk.com/privacy") } }, verticalAlignment = Alignment.CenterVertically) {
                        Text(stringResource(R.string.settings_privacy_policy), color = MaterialTheme.colorScheme.primary)
                    }
                    val termsUrl = stringResource(R.string.settings_terms_url)
                    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(onClickLabel = stringResource(R.string.settings_terms_open)) { runCatching { uri.openUri(termsUrl) } }, verticalAlignment = Alignment.CenterVertically) {
                        Text(stringResource(R.string.settings_terms), color = MaterialTheme.colorScheme.primary)
                    }
                    val mailto = stringResource(R.string.settings_support_mailto)
                    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(onClickLabel = stringResource(R.string.settings_support_open)) { runCatching { uri.openUri(mailto) } }.testTag("supportLink"), verticalAlignment = Alignment.CenterVertically) {
                        Text(stringResource(R.string.settings_support), color = MaterialTheme.colorScheme.primary)
                    }
                }
            }
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
private fun SwitchRow(title: String, explanation: String, checked: Boolean, tag: String, onChange: (Boolean) -> Unit) {
    Row(
        Modifier.fillMaxWidth().heightIn(min = 56.dp).padding(vertical = 6.dp)
            .toggleable(value = checked, role = Role.Switch, onValueChange = onChange).testTag(tag),
        verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(12.dp),
    ) {
        Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(2.dp)) {
            Text(title, color = Vmk.colors.text)
            Text(explanation, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
        }
        Switch(checked = checked, onCheckedChange = null)
    }
}

/** "Organize new uploads: Ask / Always / Never": reads and writes the server preference. */
@Composable
private fun OrganizeSetting(controller: com.videomk.app.data.OrganizeController) {
    val pref by controller.pref.collectAsState()
    androidx.compose.runtime.LaunchedEffect(Unit) { controller.refreshPref() }
    val big = androidx.compose.ui.platform.LocalDensity.current.fontScale >= 1.5f
    Column(Modifier.fillMaxWidth().padding(top = 14.dp).testTag("organizeSetting"), verticalArrangement = Arrangement.spacedBy(10.dp)) {
        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(10.dp)) {
            Icon(androidx.compose.material.icons.Icons.Filled.AutoAwesome, null, tint = Vmk.colors.primary)
            Text(stringResource(R.string.settings_organize_title), style = MaterialTheme.typography.bodyLarge, fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold, color = Vmk.colors.text)
        }
        val shape = androidx.compose.foundation.shape.RoundedCornerShape(12.dp)
        val options = com.videomk.app.core.OrganizePref.entries
        @Composable fun seg(o: com.videomk.app.core.OrganizePref, modifier: Modifier) {
            val sel = o == pref
            androidx.compose.foundation.layout.Box(
                modifier.heightIn(min = 44.dp).clip(androidx.compose.foundation.shape.RoundedCornerShape(10.dp))
                    .then(if (sel) Modifier.background(if (Vmk.colors.dark) Vmk.colors.surface3 else Vmk.colors.surface) else Modifier)
                    .toggleable(value = sel, role = androidx.compose.ui.semantics.Role.RadioButton) { controller.setPref(o) }.testTag("organizePref-${o.wire}"),
                contentAlignment = Alignment.Center,
            ) { Text(o.label, style = MaterialTheme.typography.titleSmall, fontWeight = androidx.compose.ui.text.font.FontWeight.SemiBold, color = if (sel) Vmk.colors.text else Vmk.colors.textSecondary) }
        }
        if (big) Column(verticalArrangement = Arrangement.spacedBy(4.dp)) { options.forEach { seg(it, Modifier.fillMaxWidth()) } }
        else Row(Modifier.fillMaxWidth().clip(shape).background(Vmk.colors.surfaceRaised).padding(3.dp)) { options.forEach { seg(it, Modifier.weight(1f)) } }
        Text(stringResource(R.string.settings_organize_hint), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
    }
}
