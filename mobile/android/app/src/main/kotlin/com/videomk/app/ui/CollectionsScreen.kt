package com.videomk.app.ui

import androidx.compose.ui.res.stringResource
import androidx.compose.ui.res.pluralStringResource
import com.videomk.app.R
import com.videomk.app.core.Txt
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.PaddingValues
import androidx.compose.foundation.layout.Row
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.fillMaxWidth
import androidx.compose.foundation.layout.heightIn
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.layout.statusBarsPadding
import androidx.compose.foundation.lazy.LazyColumn
import androidx.compose.foundation.lazy.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.automirrored.filled.ArrowBack
import androidx.compose.material.icons.filled.Add
import androidx.compose.material.icons.filled.MoreHoriz
import androidx.compose.material3.Icon
import androidx.compose.material3.IconButton
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Scaffold
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.platform.testTag
import androidx.compose.ui.semantics.Role
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.heading
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import com.videomk.app.core.MediaCollection
import com.videomk.app.core.MediaPhoto
import com.videomk.app.core.OrganizePref

/** "See all": every collection as a row, with the Auto mark for the ones made for you. */
@Composable
fun CollectionsScreen(vm: MediaViewModel, pref: OrganizePref, onBack: () -> Unit, onOpen: (String) -> Unit) {
    var menuFor by remember { mutableStateOf<MediaCollection?>(null) }
    var rename by remember { mutableStateOf<MediaCollection?>(null) }
    var delete by remember { mutableStateOf<MediaCollection?>(null) }
    var create by remember { mutableStateOf(false) }
    Scaffold(
        containerColor = Vmk.colors.background, contentWindowInsets = androidx.compose.foundation.layout.WindowInsets(0),
        topBar = {
            Row(Modifier.fillMaxWidth().statusBarsPadding().padding(horizontal = 4.dp), verticalAlignment = Alignment.CenterVertically) {
                IconButton(onClick = onBack, modifier = Modifier.size(48.dp)) { Icon(Icons.AutoMirrored.Filled.ArrowBack, stringResource(R.string.common_back), tint = Vmk.colors.primary) }
                Box(Modifier.weight(1f))
                IconButton(onClick = { create = true }, modifier = Modifier.size(48.dp).testTag("newCollection")) { Icon(Icons.Filled.Add, stringResource(R.string.media_new_collection), tint = Vmk.colors.primary) }
            }
        },
    ) { padding ->
        LazyColumn(Modifier.fillMaxSize().padding(padding).testTag("collectionsList"), contentPadding = PaddingValues(horizontal = 16.dp, vertical = 8.dp)) {
            item {
                Text(stringResource(R.string.media_collections), style = MaterialTheme.typography.headlineMedium, fontWeight = FontWeight.Bold, letterSpacing = (-0.9).sp, color = Vmk.colors.text, modifier = Modifier.semantics { heading() })
                Text(stringResource(R.string.collections_subtitle), style = MaterialTheme.typography.bodyMedium, color = Vmk.colors.textSecondary, modifier = Modifier.padding(top = 4.dp, bottom = 12.dp))
            }
            items(vm.collections.sortedByDescending { it.auto }, key = { it.id }) { c ->
                Row(
                    Modifier.fillMaxWidth().heightIn(min = 80.dp).clickable(role = Role.Button, onClickLabel = stringResource(R.string.media_open_collection)) { onOpen(c.id) }.padding(vertical = 8.dp)
                        .semantics(mergeDescendants = true) { contentDescription = Txt.n(if (c.auto) R.plurals.media_collection_desc_auto else R.plurals.media_collection_desc, c.count, c.name) }.testTag("collectionRow"),
                    verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(14.dp),
                ) {
                    Box(Modifier.size(60.dp).clip(RoundedCornerShape(16.dp)).background(Vmk.colors.surfaceRaised), contentAlignment = Alignment.Center) {
                        if (c.coverId != null && c.coverThumbUrl != null) PhotoThumb(MediaPhoto(c.coverId, null, "", null, 0, 0, 0, c.coverThumbUrl), Modifier.fillMaxSize()) else Text(c.emoji ?: "🖼️", style = MaterialTheme.typography.titleLarge)
                    }
                    Column(Modifier.weight(1f), verticalArrangement = Arrangement.spacedBy(4.dp)) {
                        Text(c.name, style = MaterialTheme.typography.titleMedium, fontWeight = FontWeight.SemiBold, color = Vmk.colors.text, maxLines = 2, overflow = TextOverflow.Ellipsis)
                        Row(verticalAlignment = Alignment.CenterVertically, horizontalArrangement = Arrangement.spacedBy(8.dp)) {
                            if (c.auto) AutoChip(Modifier.testTag("autoChip"))
                            Text(pluralStringResource(R.plurals.media_photos, c.count, c.count), style = MaterialTheme.typography.bodySmall, color = Vmk.colors.textSecondary)
                        }
                    }
                    Box {
                        IconButton(onClick = { menuFor = c }, modifier = Modifier.size(48.dp).testTag("collectionMore")) { Icon(Icons.Filled.MoreHoriz, stringResource(R.string.collections_more_for, c.name), tint = Vmk.colors.textSecondary) }
                        CollectionMenu(menuFor?.id == c.id, { menuFor = null }, onRename = { rename = c; menuFor = null }, onDelete = { delete = c; menuFor = null })
                    }
                }
            }
        }
    }
    if (create) NameDialog(stringResource(R.string.media_new_collection), "", stringResource(R.string.media_create), onDismiss = { create = false }) { vm.createCollection(it); create = false }
    rename?.let { c -> NameDialog(stringResource(R.string.media_rename_collection), c.name, stringResource(R.string.common_save), onDismiss = { rename = null }) { vm.renameCollection(c.id, it); rename = null } }   // the Auto chip stays
    delete?.let { c -> DeleteCollectionDialog(c, pref, onDismiss = { delete = null }) { vm.deleteCollection(c.id); delete = null } }
}
