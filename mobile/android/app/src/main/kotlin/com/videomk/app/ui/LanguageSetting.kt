package com.videomk.app.ui

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
    Column(Modifier.fillMaxWidth().testTag("languageSetting"), verticalArrangement = Arrangement.spacedBy(2.dp)) {
        Text(stringResource(R.string.settings_language_title), style = MaterialTheme.typography.titleSmall, color = Vmk.colors.textSecondary)
        AppLocale.choices.forEach { c ->
            Row(
                Modifier.fillMaxWidth().heightIn(min = 48.dp).selectable(selected = choice == c, role = Role.RadioButton) {
                    if (choice != c) {
                        choice = c
                        if (language.set(c)) (context as? android.app.Activity)?.recreate()
                    }
                }.testTag("language-$c"),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                RadioButton(selected = choice == c, onClick = null)
                Text(
                    stringResource(when (c) { "en" -> R.string.settings_language_en; "es" -> R.string.settings_language_es; else -> R.string.settings_language_system }),
                    color = Vmk.colors.text, modifier = Modifier.padding(start = 12.dp),
                )
            }
        }
        Text(stringResource(R.string.settings_language_hint), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
    }
}
