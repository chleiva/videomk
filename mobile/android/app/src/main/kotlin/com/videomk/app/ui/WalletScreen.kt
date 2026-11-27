package com.videomk.app.ui

import androidx.compose.foundation.layout.navigationBarsPadding
import androidx.compose.runtime.setValue
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
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.testTagsAsResourceId
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.background
import androidx.compose.ui.draw.clip
import java.time.Duration
import java.time.Instant
import androidx.compose.ui.res.pluralStringResource
import androidx.compose.ui.res.stringResource
import com.videomk.app.R
import com.videomk.app.core.Txt
import java.util.Date

/**
 * Credits, as a sheet that answers the three questions a person has there: how many, when more arrive, and what the plan allows. The number, one line about the
 * next free credit (hidden when the server grants none), the plan with its limits, what is in the balance and when it ends, and the price rule in one line.
 * Nothing can be bought yet (`can_upgrade` is false): the plans are named as coming, and there is no button that leads nowhere.
 */
@OptIn(ExperimentalMaterial3Api::class, androidx.compose.ui.ExperimentalComposeUiApi::class)
@Composable
fun CreditsSheet(app: AppViewModel, onDismiss: () -> Unit) {
    val state by app.state.collectAsState()
    LaunchedEffect(Unit) { app.refreshWallet() }
    androidx.compose.material3.ModalBottomSheet(onDismissRequest = onDismiss, sheetState = androidx.compose.material3.rememberModalBottomSheetState(skipPartiallyExpanded = true), containerColor = Vmk.colors.surface, shape = androidx.compose.foundation.shape.RoundedCornerShape(topStart = Vmk.radii.sheet, topEnd = Vmk.radii.sheet)) {
        Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal = Vmk.space.sheet).navigationBarsPadding().padding(bottom = Vmk.space.xxl).semantics { if (com.videomk.app.BuildConfig.DEBUG) testTagsAsResourceId = true }.testTag("creditsSheet"), verticalArrangement = Arrangement.spacedBy(Vmk.space.l)) {
            SheetHeader(stringResource(R.string.wallet_title), onDismiss, closeTag = "creditsClose")
            val w = state.wallet
            if (w == null) { Box(Modifier.fillMaxWidth().heightIn(min = 120.dp), contentAlignment = Alignment.Center) { LiveRing(size = 28.dp) }; return@Column }
            // the unlimited test account is a debug-build thing only: a release build shows the plain number
            val unlimited = w.unlimited && com.videomk.app.BuildConfig.DEBUG
            val number = if (unlimited) "∞" else "${w.balance}"
            val word = pluralStringResource(R.plurals.wallet_credit_word, if (unlimited) 2 else w.balance)
            val spoken = stringResource(R.string.wallet_hero_desc, "$number $word")
            Row(Modifier.semantics(mergeDescendants = true) { contentDescription = spoken }.testTag("balanceCard"), verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(Vmk.space.s)) {
                Icon(Sym.Bolt, null, tint = Vmk.colors.primary, modifier = Modifier.size(32.dp))
                Text(number, style = VmkType.hero, color = Vmk.colors.text, modifier = Modifier.testTag("balanceValue"))
                Text(word, style = MaterialTheme.typography.titleMedium, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = Vmk.space.l))
            }
            // when more arrive: only when the server really grants a free credit
            w.nextFreeAt?.takeIf { w.nextFreeCredits > 0 }?.let { at ->
                Text(pluralStringResource(R.plurals.wallet_next_free_credit, w.nextFreeCredits, com.videomk.app.core.PlanText.freeCredit(at)), style = MaterialTheme.typography.bodyLarge, color = Vmk.colors.text, modifier = Modifier.testTag("nextFreeCredit"))
            }
            // free videos paused or not available: the server's own sentence
            w.plans.free?.takeIf { !it.available && it.message != null && w.balance == 0 }?.let { f ->
                Text(f.message!! + (f.resumesAt?.let { " " + stringResource(R.string.stop_resumes, com.videomk.app.core.PlanText.moment(it)) } ?: ""), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("freeMessage"))
            }
            VmkGroup(onSheet = true) {
                w.plans.plan?.let { plan ->
                    val limits = listOfNotNull(
                        plan.maxSeconds?.let { stringResource(R.string.wallet_plan_longest, com.videomk.app.core.Lengths.short(it / 60.0)) },
                        plan.resolutions.lastOrNull()?.let { if (it.lowercase() == "2160p") "4K" else it },
                        if (plan.watermarkForced) stringResource(R.string.wallet_plan_watermark) else null,
                    ).joinToString(" · ").ifEmpty { null }
                    VmkRow(stringResource(R.string.wallet_plan), Modifier.testTag("planRow"), subtitle = limits, value = plan.name)
                }
                // what the balance is made of and when each part ends; never "no credits" above a balance
                for (b in w.buckets.filter { it.remaining > 0 }) VmkRow(bucketTitle(b.kind), Modifier.testTag("bucketRow"), subtitle = expiry(b), value = "${b.remaining}")
            }
            Text(stringResource(R.string.wallet_how_short), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("creditsExplainer"))
            if (w.plans.plan != null && !w.plans.canUpgrade) Text(stringResource(R.string.plans_coming_soon), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.testTag("plansSoon"))
        }
    }
}

fun bucketTitle(k: WalletBucket.Kind): String = Txt.s(when (k) {
    WalletBucket.Kind.Daily -> R.string.wallet_bucket_daily
    WalletBucket.Kind.Signup -> R.string.wallet_bucket_signup
    WalletBucket.Kind.Paid -> R.string.wallet_bucket_paid
    WalletBucket.Kind.Refund -> R.string.wallet_bucket_refund
    WalletBucket.Kind.Plan -> R.string.wallet_bucket_plan
    WalletBucket.Kind.Other -> R.string.wallet_bucket_other
})

fun expiry(b: WalletBucket): String? {
    val d = b.expiresAt ?: return Txt.s(R.string.wallet_never_expire)
    if (b.kind == WalletBucket.Kind.Daily) return Txt.s(R.string.wallet_expire_tonight)
    return Txt.s(R.string.wallet_expire_on, DateFormat.getDateInstance(DateFormat.MEDIUM, Txt.locale).format(Date.from(d)))
}

