package com.videomk.app.ui

import androidx.compose.runtime.setValue
import androidx.compose.material.icons.filled.Info
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
import androidx.compose.material.icons.filled.CardGiftcard
import androidx.compose.material.icons.filled.Schedule
import androidx.compose.material3.Button
import androidx.compose.material3.ExperimentalMaterial3Api
import androidx.compose.material3.HorizontalDivider
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.material3.TopAppBar
import androidx.compose.material3.TopAppBarDefaults
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.collectAsState
import androidx.compose.runtime.getValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.videomk.app.core.WalletBucket
import java.text.DateFormat
import java.time.Duration
import java.time.Instant
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import com.videomk.app.R
import com.videomk.app.core.Txt
import java.util.Date

@OptIn(ExperimentalMaterial3Api::class)
@Composable
fun WalletScreen(app: AppViewModel, onBack: () -> Unit) {
    val state by app.state.collectAsState()
    LaunchedEffect(Unit) { app.refreshWallet() }
    Scaffold(
        containerColor = Vmk.colors.background,
        topBar = {
            TopAppBar(
                title = { Text(stringResource(R.string.wallet_title)) },
                navigationIcon = { IconButton(onClick = onBack, modifier = Modifier.size(48.dp)) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.common_back)) } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Vmk.colors.background, titleContentColor = Vmk.colors.text),
            )
        },
    ) { padding ->
        val w = state.wallet
        if (w == null) { FullScreenSpinner(Modifier.padding(padding)); return@Scaffold }
        Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            // the unlimited test account is a debug-build thing only: a release build shows the plain number
            val unlimited = w.unlimited && com.videomk.app.BuildConfig.DEBUG
            WalletHero(if (unlimited) "∞" else "${w.balance}", pluralStringResource(R.plurals.wallet_credit_word, if (unlimited) 2 else w.balance))
            Card {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text(stringResource(R.string.wallet_what_you_have), style = MaterialTheme.typography.titleSmall, color = Vmk.colors.textSecondary, modifier = Modifier.semantics { heading() })
                    if (w.buckets.isEmpty()) Text(stringResource(R.string.wallet_none), color = Vmk.colors.textSecondary)
                    w.buckets.forEachIndexed { i, b ->
                        if (i > 0) HorizontalDivider(color = Vmk.colors.textSecondary.copy(alpha = 0.15f))
                        Row(Modifier.fillMaxWidth().heightIn(min = 48.dp).semantics(mergeDescendants = true) {}.testTag("bucketRow"), verticalAlignment = Alignment.CenterVertically) {
                            Column(Modifier.weight(1f)) {
                                Text(bucketTitle(b.kind), color = Vmk.colors.text)
                                expiry(b)?.let { Text(it, style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary) }
                            }
                            Text("${b.remaining}", style = MaterialTheme.typography.titleMedium, color = Vmk.colors.text)
                        }
                    }
                }
            }
            // one line about the free credits (when the next ones arrive, else the daily rule), then the (i) with the rules
            Text(
                w.nextFreeAt?.let { stringResource(R.string.wallet_next_free, relative(it)) } ?: pluralStringResource(R.plurals.wallet_daily_rule, w.dailyCredits, w.dailyCredits),
                style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.fillMaxWidth().padding(horizontal = 4.dp),
            )
            var rules by androidx.compose.runtime.saveable.rememberSaveable { androidx.compose.runtime.mutableStateOf(false) }
            Row(
                Modifier.fillMaxWidth().heightIn(min = 48.dp).clickable(role = androidx.compose.ui.semantics.Role.Button, onClickLabel = stringResource(R.string.wallet_cost_title)) { rules = true }.padding(horizontal = 4.dp).testTag("creditsExplainer"),
                verticalAlignment = Alignment.CenterVertically,
            ) {
                Text(stringResource(R.string.wallet_cost_title), style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.text, modifier = Modifier.weight(1f))
                Icon(Icons.Filled.Info, null, tint = Vmk.colors.primary)
            }
            if (rules) androidx.compose.material3.AlertDialog(
                onDismissRequest = { rules = false }, title = { Text(stringResource(R.string.wallet_cost_title)) }, text = { Text(stringResource(R.string.wallet_how_short), style = MaterialTheme.typography.bodyMedium) },
                confirmButton = { androidx.compose.material3.TextButton(onClick = { rules = false }, modifier = Modifier.heightIn(min = 48.dp)) { Text(stringResource(R.string.common_done)) } },
            )
        }
    }
}

fun bucketTitle(k: WalletBucket.Kind): String = Txt.s(when (k) {
    WalletBucket.Kind.Daily -> R.string.wallet_bucket_daily
    WalletBucket.Kind.Signup -> R.string.wallet_bucket_signup
    WalletBucket.Kind.Paid -> R.string.wallet_bucket_paid
    WalletBucket.Kind.Refund -> R.string.wallet_bucket_refund
    WalletBucket.Kind.Other -> R.string.wallet_bucket_other
})

fun expiry(b: WalletBucket): String? {
    val d = b.expiresAt ?: return Txt.s(R.string.wallet_never_expire)
    if (b.kind == WalletBucket.Kind.Daily) return Txt.s(R.string.wallet_expire_tonight)
    return Txt.s(R.string.wallet_expire_on, DateFormat.getDateInstance(DateFormat.MEDIUM, Txt.locale).format(Date.from(d)))
}

/** "in 3 hours", from the locale's plurals (the system relative-time helper follows the device language, not the app's). */
private fun relative(t: Instant): String {
    val minutes = Duration.between(Instant.now(), t).toMinutes()
    return when {
        minutes < 1 -> Txt.s(R.string.wallet_in_a_moment)
        minutes < 60 -> Txt.n(R.plurals.wallet_in_minutes, minutes.toInt())
        minutes < 60 * 24 -> Txt.n(R.plurals.wallet_in_hours, ((minutes + 30) / 60).toInt())
        else -> Txt.n(R.plurals.wallet_in_days, ((minutes + 720) / 1440).toInt())
    }
}
