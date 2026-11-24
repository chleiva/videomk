package com.videomk.app.ui

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
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.videomk.app.core.WalletBucket
import java.text.DateFormat
import java.time.Instant
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
                title = { Text("Credits") },
                navigationIcon = { IconButton(onClick = onBack, modifier = Modifier.size(48.dp)) { Icon(Icons.AutoMirrored.Filled.ArrowBack, "Back") } },
                colors = TopAppBarDefaults.topAppBarColors(containerColor = Vmk.colors.background, titleContentColor = Vmk.colors.text),
            )
        },
    ) { padding ->
        val w = state.wallet
        if (w == null) { FullScreenSpinner(Modifier.padding(padding)); return@Scaffold }
        Column(Modifier.fillMaxSize().padding(padding).verticalScroll(rememberScrollState()).padding(16.dp), verticalArrangement = Arrangement.spacedBy(16.dp)) {
            Card(Modifier.testTag("balanceCard")) {
                Column(Modifier.fillMaxWidth().semantics(mergeDescendants = true) {}, horizontalAlignment = Alignment.CenterHorizontally) {
                    Text(if (w.unlimited) "∞" else "${w.balance}", fontSize = 56.sp, fontWeight = FontWeight.Bold, color = Vmk.colors.text, modifier = Modifier.testTag("balanceValue"))
                    Text(if (w.unlimited) "unlimited (test account)" else if (w.balance == 1) "credit" else "credits", color = Vmk.colors.textSecondary)
                }
            }
            Card {
                Column(verticalArrangement = Arrangement.spacedBy(8.dp)) {
                    Text("What you have", style = MaterialTheme.typography.titleSmall, color = Vmk.colors.textSecondary)
                    if (w.buckets.isEmpty()) Text("No credits right now.", color = Vmk.colors.textSecondary)
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
            Card {
                Column(verticalArrangement = Arrangement.spacedBy(10.dp)) {
                    w.nextFreeAt?.let {
                        Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                            Icon(Icons.Filled.Schedule, null, tint = MaterialTheme.colorScheme.primary)
                            Text("Next free credits: ${relative(it)}", color = Vmk.colors.text)
                        }
                    }
                    Row(horizontalArrangement = Arrangement.spacedBy(10.dp), verticalAlignment = Alignment.CenterVertically) {
                        Icon(Icons.Filled.CardGiftcard, null, tint = MaterialTheme.colorScheme.primary)
                        Text(
                            if (w.dailyCredits == 1) "1 free credit every day. It expires that night." else "${w.dailyCredits} free credits every day. They expire that night.",
                            color = Vmk.colors.text,
                        )
                    }
                    Text(
                        "1 credit makes up to 1 minute of video, rounded up: a 10-second video and a 60-second video cost 1 credit, a 61-second video costs 2. Free credits expire; credits you buy never do.",
                        style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary,
                    )
                }
            }
            Column(verticalArrangement = Arrangement.spacedBy(6.dp), horizontalAlignment = Alignment.CenterHorizontally, modifier = Modifier.fillMaxWidth()) {
                Button(onClick = {}, enabled = false, modifier = Modifier.heightIn(min = 48.dp)) { Text("Get more credits") }
                Text("Buying credits is coming soon.", style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary, textAlign = TextAlign.Center)
            }
        }
    }
}

fun bucketTitle(k: WalletBucket.Kind) = when (k) {
    WalletBucket.Kind.Daily -> "Free today"
    WalletBucket.Kind.Signup -> "Welcome credits"
    WalletBucket.Kind.Paid -> "Purchased"
    WalletBucket.Kind.Refund -> "Returned credits"
    WalletBucket.Kind.Other -> "Credits"
}

fun expiry(b: WalletBucket): String? {
    val d = b.expiresAt ?: return "Never expire"
    if (b.kind == WalletBucket.Kind.Daily) return "Expire tonight"
    return "Expire " + DateFormat.getDateInstance(DateFormat.MEDIUM).format(Date.from(d))
}

private fun relative(t: Instant): String =
    android.text.format.DateUtils.getRelativeTimeSpanString(t.toEpochMilli(), System.currentTimeMillis(), android.text.format.DateUtils.MINUTE_IN_MILLIS).toString()
