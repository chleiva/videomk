package com.videomk.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.filled.ExpandMore
import androidx.compose.material.icons.filled.Check
import androidx.compose.material3.DropdownMenu
import androidx.compose.material3.DropdownMenuItem
import androidx.compose.material3.Icon
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.selection.selectable
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.RadioButton
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.res.stringResource
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.unit.dp
import com.videomk.app.R
import com.videomk.app.core.AppLocale
import com.videomk.app.data.AppLanguage

/** Settings > Language: Same as my phone | English | Español (docs/I18N.md: the explicit choice wins over the device language). */
@Composable
fun LanguageSetting() {
    val context = LocalContext.current
    val language = remember { AppLanguage(context) }
    var choice by remember { mutableStateOf(language.choice) }
    var open by remember { mutableStateOf(false) }
    @Composable fun nameOf(c: String) = stringResource(when (c) { "en" -> R.string.settings_language_en; "es" -> R.string.settings_language_es; else -> R.string.settings_language_system })
    // one row: the name on the left, the value and a chevron on the right; the choices are a menu (no footer: the app language does not change the language of videos)
    Box(Modifier.fillMaxWidth().testTag("languageSetting")) {
        Row(
            Modifier.fillMaxWidth().heightIn(min = 56.dp).clickable(role = Role.DropdownList, onClickLabel = stringResource(R.string.settings_language_title)) { open = true },
            verticalAlignment = Alignment.CenterVertically,
        ) {
            Text(stringResource(R.string.settings_language_title), color = Vmk.colors.text, style = MaterialTheme.typography.bodyLarge, modifier = Modifier.weight(1f))
            Text(nameOf(choice), color = Vmk.colors.textSecondary, style = MaterialTheme.typography.bodyMedium)
            Icon(Icons.Filled.ExpandMore, null, tint = Vmk.colors.textSecondary)
        }
        DropdownMenu(expanded = open, onDismissRequest = { open = false }, containerColor = Vmk.colors.surface) {
            AppLocale.choices.forEach { c ->
                DropdownMenuItem(
                    text = { Text(nameOf(c), fontWeight = if (choice == c) FontWeight.Bold else FontWeight.Normal) },
                    trailingIcon = { if (choice == c) Icon(Icons.Filled.Check, null, tint = Vmk.colors.primary) },
                    onClick = { open = false; if (choice != c) { choice = c; if (language.set(c)) (context as? android.app.Activity)?.recreate() } },
                    modifier = Modifier.testTag("language-$c"),
                )
            }
        }
    }
}
