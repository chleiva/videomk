package com.videomk.app.ui

import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Box
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
    // the same row as every other setting: the name, the value and a chevron; the choices are a menu
    Box(Modifier.fillMaxWidth().testTag("languageSetting")) {
        VmkRow(stringResource(R.string.settings_language_title), icon = Sym.Language, value = nameOf(choice), trailing = Sym.ExpandMore, onClick = { open = true })
        VmkMenu(open, { open = false }) {
            AppLocale.choices.forEach { c ->
                VmkMenuItem(nameOf(c), null, Modifier.testTag("language-$c"), selected = choice == c) { open = false; if (choice != c) { choice = c; if (language.set(c)) (context as? android.app.Activity)?.recreate() } }
            }
        }
    }
}
