
$filePath = "c:\Users\Admin\Planning\production_scheduler\production_scheduler\public\js\ColorChart.vue"
$content = Get-Content -Path $filePath -Encoding utf8

$newContent = $content.ForEach({
    $line = $_
    
    # Navigation Buttons
    if ($line -match 'Kanban' -and $line -match 'view-btn') {
        $emoji = [char]::ConvertFromUtf32(0x1F4CB) # 📋
        return "            $emoji Kanban"
    }
    if ($line -match 'Matrix' -and $line -match 'view-btn') {
        $emoji = [char]::ConvertFromUtf32(0x1F4CA) # 📊
        return "            $emoji Matrix"
    }
    if ($line -match 'clearFilters' -and $line -match 'Clear') {
        $sym = [char]0x2715 # ✕
        return "      <button class=`"cc-clear-btn`" @click=`"clearFilters`">$sym Clear</button>"
    }
    if ($line -match 'autoAllocate' -and $line -match 'Auto Alloc') {
        $emoji = [char]::ConvertFromUtf32(0x1FA84) # 🪄
        return "        $emoji Auto Alloc"
    }
    
    # Sort Controls
    if ($line -match 'toggleUnitColor' -and $line -match 'getUnitSortConfig') {
        $sun = [char]::ConvertFromUtf32(0x2600) + [char]0xFE0F # ☀️
        $moon = [char]::ConvertFromUtf32(0x1F319) # 🌙
        return "                {{ getUnitSortConfig(unit).color === 'asc' ? '$sun' : '$moon' }}"
    }
    if ($line -match 'toggleUnitGsm' -and $line -match 'getUnitSortConfig') {
        $down = [char]::ConvertFromUtf32(0x2B07) + [char]0xFE0F # ⬇️
        $up = [char]::ConvertFromUtf32(0x2B06) + [char]0xFE0F # ⬆️
        return "                {{ getUnitSortConfig(unit).gsm === 'desc' ? '$down' : '$up' }}"
    }
    if ($line -match 'toggleUnitPriority' -and $line -match 'getUnitSortConfig') {
        $palette = [char]::ConvertFromUtf32(0x1F3A8) # 🎨
        $ruler = [char]::ConvertFromUtf32(0x1F4CF) # 📏
        return "                {{ getUnitSortConfig(unit).priority === 'color' ? '$palette' : '$ruler' }}"
    }
    
    # Capacity Warnings
    if ($line -match 'getMixRollCount' -and $line -match 'mix') {
        $warn = [char]::ConvertFromUtf32(0x26A0) + [char]0xFE0F # ⚠️
        return "              $warn {{ getMixRollCount(unit) }} mix{{ getMixRollCount(unit) > 1 ? 'es' : '' }}"
    }
    if ($line -match 'warning:' -and $line -match 'Over Limit') {
        $warn = [char]::ConvertFromUtf32(0x26A0) + [char]0xFE0F # ⚠️
        return '            warning: `' + $warn + ' Over Limit (${(total - limit).toFixed(2)}T)!` '
    }
    if ($line -match 'warning:' -and $line -match 'Near Limit') {
        $warn = [char]::ConvertFromUtf32(0x26A0) + [char]0xFE0F # ⚠️
        return "            warning: `$warn Near Limit` "
    }
    
    # Mix Label & Details (em-dash and bullet)
    if ($line -match 'cc-mix-label' -and $line -match 'qty') {
        $dash = [char]0x2014 # —
        return "          <span class=`"cc-mix-label`" :class=`"entry.mixType.toLowerCase().replace(' ', '-')`">" + ' {{ entry.mixType }} ' + $dash + ' ~{{ entry.qty }} Kg </span>'
    }
    if ($line -match 'cc-card-customer' -and $line -match 'customer') {
        $bullet = [char]0xB7 # ·
        return "                <span v-if=`"entry.partyCode !== entry.customer`" style=`"font-weight:400; color:#6b7280;`"> $bullet {{ entry.customer }}</span>"
    }
    if ($line -match 'cc-card-details' -and $line -match 'gsm') {
        $bullet = [char]0xB7 # ·
        return "                {{ entry.quality }} $bullet {{ entry.gsm }} GSM"
    }

    # Dialogs & Msgs
    if ($line -match 'title:' -and $line -match 'Capacity Full') {
        $warn = [char]::ConvertFromUtf32(0x26A0) + [char]0xFE0F # ⚠️
        return "                        title: '$warn Capacity Full',"
    }
    if ($line -match 'frappe.msgprint' -and $line -match 'Move Failed') {
        $errEmoji = [char]::ConvertFromUtf32(0x274C) # ❌
        return "                 frappe.msgprint(`"$errEmoji Move Failed`");"
    }
    if ($line -match 'title:' -and $line -match 'Rescue') {
        $rescue = [char]::ConvertFromUtf32(0x1F691) # 🚑
        return "        title: '$rescue Rescue / Re-Queue Orders',"
    }
    
    return $line
})

Set-Content -Path $filePath -Value $newContent -Encoding utf8
Write-Host "Successfully fixed encoding issues in ColorChart.vue using Fixed Pure ASCII PowerShell script"
