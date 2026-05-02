
$filePath = "c:\Users\Admin\Planning\production_scheduler\production_scheduler\public\js\ColorChart.vue"
$content = Get-Content -Path $filePath -Encoding utf8

$newContent = $content.ForEach({
    $line = $_
    
    # Navigation Buttons
    if ($line -match 'Kanban' -and $line -match 'view-btn') {
        return "            📋 Kanban"
    }
    if ($line -match 'Matrix' -and $line -match 'view-btn') {
        return "            📊 Matrix"
    }
    if ($line -match 'clearFilters' -and $line -match 'Clear') {
        return '      <button class="cc-clear-btn" @click="clearFilters">✕ Clear</button>'
    }
    if ($line -match 'autoAllocate' -and $line -match 'Auto Alloc') {
        return "        🪄 Auto Alloc"
    }
    
    # Sort Controls
    if ($line -match 'toggleUnitColor' -and $line -match 'getUnitSortConfig') {
        return "                {{ getUnitSortConfig(unit).color === 'asc' ? '☀️' : '🌙' }}"
    }
    if ($line -match 'toggleUnitGsm' -and $line -match 'getUnitSortConfig') {
        return "                {{ getUnitSortConfig(unit).gsm === 'desc' ? '⬇️' : '⬆️' }}"
    }
    if ($line -match 'toggleUnitPriority' -and $line -match 'getUnitSortConfig') {
        return "                {{ getUnitSortConfig(unit).priority === 'color' ? '🎨' : '📏' }}"
    }
    
    # Capacity Warnings
    if ($line -match 'getMixRollCount' -and $line -match 'mix') {
        return "              ⚠️ {{ getMixRollCount(unit) }} mix{{ getMixRollCount(unit) > 1 ? 'es' : '' }}"
    }
    if ($line -match 'warning:' -and $line -match 'Over Limit') {
        return '            warning: `⚠️ Over Limit (${(total - limit).toFixed(2)}T)!` '
    }
    if ($line -match 'warning:' -and $line -match 'Near Limit') {
        return "            warning: `⚠️ Near Limit` "
    }
    
    # Dialogs & Msgs
    if ($line -match 'title:' -and $line -match 'Capacity Full') {
        return "                        title: '⚠️ Capacity Full',"
    }
    if ($line -match 'frappe.msgprint' -and $line -match 'Move Failed') {
        return '                 frappe.msgprint("❌ Move Failed");'
    }
    if ($line -match 'title:' -and $line -match 'Rescue') {
        return "        title: '🚑 Rescue / Re-Queue Orders',"
    }
    
    return $line
})

Set-Content -Path $filePath -Value $newContent -Encoding utf8
Write-Host "Successfully fixed encoding issues in ColorChart.vue using ASCII matching"
