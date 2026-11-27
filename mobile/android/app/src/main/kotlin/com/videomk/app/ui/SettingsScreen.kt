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

/**
 * Settings on the shared kit: groups of ONE row style (an icon, the words, then a value, a switch or a chevron), one switch colour, no dialogs. Signing out asks
 * nothing (it deletes nothing); what the photo switches mean is one sentence under them; only deleting the account opens a confirmation, as rule 8 says.
 */
@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(
    email: String?, onBack: () -> Unit, onSignOut: () -> Unit, onFeedback: (() -> Unit)? = null,
    deletion: DeletionState = DeletionState.Idle, onDeleteAccount: ((String) -> Unit)? = null, onCancelDeletion: () -> Unit = {}, onDeletionClosed: () -> Unit = {},
    initialSheetOpen: Boolean = false, initialTyped: String = "",
) {
    var deleteSheet by rememberSaveable { mutableStateOf(initialSheetOpen) }
    var typed by rememberSaveable { mutableStateOf(initialTyped) }
    val uri = LocalUriHandler.current
    Scaffold(
        containerColor = Vmk.colors.background,
        topBar = { VmkTopBar(title = stringResource(R.string.settings_title), onBack = onBack) },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(horizontal = Vmk.space.screen).padding(bottom = Vmk.space.xxl), verticalArrangement = Arrangement.spacedBy(Vmk.space.l)) {
            VmkGroup {
                if (email != null) VmkRow(email, Modifier.testTag("accountEmail"), icon = Sym.Person)
                VmkRow(stringResource(R.string.settings_sign_out), Modifier.testTag("signOutButton"), icon = Sym.Logout, onClick = onSignOut)
            }
            VmkGroup { LanguageSetting() }
            val context = androidx.compose.ui.platform.LocalContext.current
            val photoSettings = remember { com.videomk.app.data.PhotoSettings(context) }
            var dates by remember { mutableStateOf(photoSettings.useDates) }
            var places by remember { mutableStateOf(photoSettings.useLocations) }
            val organize = com.videomk.app.ui.LocalContainerOrNull.current?.organize
            Column(verticalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
                Overline(stringResource(R.string.settings_photos), Modifier.padding(horizontal = Vmk.space.l))
                VmkGroup {
                    VmkRow(stringResource(R.string.settings_photo_dates), Modifier.testTag("photoDatesSwitch"), checked = dates, onCheckedChange = { dates = it; photoSettings.useDates = it })
                    VmkRow(stringResource(R.string.settings_photo_locations), Modifier.testTag("photoLocationsSwitch"), checked = places, onCheckedChange = { places = it; photoSettings.useLocations = it })
                    organize?.let { OrganizeSetting(it) }
                }
                // one sentence in place of the (i) and its dialog
                Text(stringResource(R.string.settings_photos_footer), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(horizontal = Vmk.space.l).testTag("mediaPrivacyCopy"))
            }
            VmkGroup {
                if (onFeedback != null) VmkRow(stringResource(R.string.feedback_title), Modifier.testTag("feedbackRow"), icon = Sym.Chat, trailing = Sym.ChevronRight, onClick = onFeedback, onClickLabel = stringResource(R.string.feedback_open))
                val mailto = stringResource(R.string.settings_support_mailto)
                VmkRow(stringResource(R.string.settings_support), Modifier.testTag("supportLink"), icon = Sym.Mail, trailing = Sym.ChevronRight, onClick = { runCatching { uri.openUri(mailto) } }, onClickLabel = stringResource(R.string.settings_support_open))
                VmkRow(stringResource(R.string.settings_privacy_policy), icon = Sym.Shield, trailing = Sym.ChevronRight, onClick = { runCatching { uri.openUri("https://videomk.com/privacy") } }, onClickLabel = stringResource(R.string.settings_privacy_open))
                val termsUrl = stringResource(R.string.settings_terms_url)
                VmkRow(stringResource(R.string.settings_terms), icon = Sym.TextSnippet, trailing = Sym.ChevronRight, onClick = { runCatching { uri.openUri(termsUrl) } }, onClickLabel = stringResource(R.string.settings_terms_open))
            }
            VmkGroup { VmkRow(stringResource(R.string.settings_about), icon = Sym.Info, value = BuildConfig.VERSION_NAME) }
            // the confirmation sheet lists what is lost, so the row is just the words
            if (onDeleteAccount != null) VmkGroup { VmkRow(stringResource(R.string.deletion_card_button), Modifier.testTag("deleteAccountButton"), icon = Sym.DeleteForever, danger = true, onClick = { deleteSheet = true }) }
        }
    }
    if (deleteSheet && onDeleteAccount != null) {
        DeleteAccountSheet(
            state = deletion, typed = typed, onTyped = { typed = it }, onStart = onDeleteAccount, onCancelReauth = onCancelDeletion,
            onClose = { deleteSheet = false; typed = ""; onDeletionClosed() },
        )
    }
}

/** "Organize new uploads": a row with its value (Ask, Always, Never) and a menu. Reads and writes the server preference. */
@Composable
private fun OrganizeSetting(controller: com.videomk.app.data.OrganizeController) {
    val pref by controller.pref.collectAsState()
    androidx.compose.runtime.LaunchedEffect(Unit) { controller.refreshPref() }
    var open by remember { mutableStateOf(false) }
    androidx.compose.foundation.layout.Box(Modifier.fillMaxWidth().testTag("organizeSetting")) {
        VmkRow(stringResource(R.string.settings_organize_title), value = pref.label, trailing = Sym.ExpandMore, onClick = { open = true })
        VmkMenu(open, { open = false }) {
            for (o in com.videomk.app.core.OrganizePref.entries) VmkMenuItem(o.label, null, Modifier.testTag("organizePref-${o.wire}"), selected = o == pref) { open = false; controller.setPref(o) }
        }
    }
}
