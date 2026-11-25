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

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun SettingsScreen(email: String?, onBack: () -> Unit, onSignOut: () -> Unit) {
    var confirm by rememberSaveable { mutableStateOf(false) }
    val uri = LocalUriHandler.current
    Scaffold(
        containerColor = Vmk.colors.background,
        topBar = {
            TopAppBar(
                title = { Text("Settings") },
                navigationIcon = { IconButton(onClick = onBack, modifier = Modifier.size(48.dp)) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Vmk.colors.background, titleContentColor = Vmk.colors.text),
            )
        },
    ) { padding ->
        Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Card {
                Column {
                    Text("Account", style = MaterialTheme.typography.titleSmall, color = Vmk.colors.textSecondary)
                    if (email != null) Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).semantics(mergeDescendants = true) {}, verticalAlignment = Alignment.CenterVertically) {
                        Text("Signed in as", color = Vmk.colors.text, modifier = Modifier.weight(1f))
                        Text(email, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("accountEmail"))
                    }
                    TextButton(onClick = { confirm = true }, modifier = Modifier.heightIn(min = 48.dp).testTag("signOutButton")) { Text("Sign out", color = Vmk.colors.danger) }
                }
            }
            val context = androidx.compose.ui.platform.LocalContext.current
            val photoSettings = remember { com.videomk.app.data.PhotoSettings(context) }
            var dates by remember { mutableStateOf(photoSettings.useDates) }
            var places by remember { mutableStateOf(photoSettings.useLocations) }
            Card {
                Column {
                    Text("Photos", style = MaterialTheme.typography.titleSmall, color = Vmk.colors.textSecondary)
                    SwitchRow("Use photo dates", "Puts your photos in the order they were taken and groups them by day", dates, "photoDatesSwitch") { dates = it; photoSettings.useDates = it }
                    SwitchRow(
                        "Use photo locations",
                        "Names the places in your story. An approximate location (about 1 km) is sent, never the exact spot, and it is not kept after your video is planned. Location is always removed from the photo files themselves.",
                        places, "photoLocationsSwitch",
                    ) { places = it; photoSettings.useLocations = it }
                    Text(PRIVACY_COPY, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 8.dp).testTag("mediaPrivacyCopy"))
                }
            }
            Card {
                Column {
                    Text("About", style = MaterialTheme.typography.titleSmall, color = Vmk.colors.textSecondary)
                    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).semantics(mergeDescendants = true) {}, verticalAlignment = Alignment.CenterVertically) {
                        Text("Version", color = Vmk.colors.text, modifier = Modifier.weight(1f))
                        Text(BuildConfig.VERSION_NAME, color = Vmk.colors.textSecondary)
                    }
                    Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(onClickLabel = "Open the privacy policy") { runCatching { uri.openUri("https://videomk.com/privacy") } }, verticalAlignment = Alignment.CenterVertically) {
                        Text("Privacy Policy", color = MaterialTheme.colorScheme.primary)
                    }
                }
            }
        }
    }
    if (confirm) {
        AlertDialog(
            onDismissRequest = { confirm = false },
            title = { Text("Sign out of videomk?") },
            confirmButton = { TextButton(onClick = { confirm = false; onSignOut() }, modifier = Modifier.heightIn(min = 48.dp).testTag("confirmSignOut")) { Text("Sign out", color = Vmk.colors.danger) } },
            dismissButton = { TextButton(onClick = { confirm = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text("Cancel") } },
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
