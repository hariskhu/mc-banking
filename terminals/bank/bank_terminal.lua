local TERMINAL_ID = -1                         -- set per terminal
local TOKEN       = "your-token-here"          -- set per terminal
local HOST        = "mc-bank.duckdns.org:8000"
local WS_URL      = ("ws://%s/ws/terminal/%d?token=%s"):format(HOST, TERMINAL_ID, TOKEN)
local RECONNECT_DELAY = 30  -- seconds between reconnect attempts
local VALID_CURRENCIES = {
    ["create:copper_nugget"]    = true, ["minecraft:copper_ingot"] = true, ["minecraft:copper_block"] = true,
    ["create:zinc_nugget"]      = true, ["create:zinc_ingot"]      = true, ["create:zinc_block"]      = true,
    ["minecraft:iron_nugget"]   = true, ["minecraft:iron_ingot"]   = true, ["minecraft:iron_block"]   = true,
    ["minecraft:gold_nugget"]   = true, ["minecraft:gold_ingot"]   = true, ["minecraft:gold_block"]   = true,
    ["minecraft:diamond"]       = true, ["minecraft:diamond_block"] = true,
}
local COMPRESS_FORMS = {
    ["create:copper_nugget"]  = { ingot = "minecraft:copper_ingot", block = "minecraft:copper_block", per_ingot = 9, per_block = 81 },
    ["create:zinc_nugget"]    = { ingot = "create:zinc_ingot",      block = "create:zinc_block",      per_ingot = 9, per_block = 81 },
    ["minecraft:iron_nugget"] = { ingot = "minecraft:iron_ingot",   block = "minecraft:iron_block",   per_ingot = 9, per_block = 81 },
    ["minecraft:gold_nugget"] = { ingot = "minecraft:gold_ingot",   block = "minecraft:gold_block",   per_ingot = 9, per_block = 81 },
    ["minecraft:diamond"]     = { ingot = nil,                      block = "minecraft:diamond_block", per_ingot = 1, per_block = 9  },
}

-- ── Peripherals ───────────────────────────────────────────────────────────────
local barrel  = peripheral.find("minecraft:barrel")
local vault = peripheral.find("create:item_vault")
local monitor = peripheral.find("monitor")
local speaker = peripheral.find("note_block") or peripheral.find("speaker")
local deposit_pending = false

if not barrel then
    error("No barrel found — check peripheral connections")
end

if not vault then
    error("No Create vault found — check peripheral connections")
end

-- ── Item dispensing ───────────────────────────────────────────────────────────
-- Maps mc_id to the nugget equivalent count for conversion
local NUGGET_CONVERSIONS = {
    ["create:copper_nugget"]    = { nugget = "create:copper_nugget",    per_ingot = 9, per_block = 81  },
    ["create:zinc_nugget"]      = { nugget = "create:zinc_nugget",      per_ingot = 9, per_block = 81  },
    ["minecraft:iron_nugget"]   = { nugget = "minecraft:iron_nugget",   per_ingot = 9, per_block = 81  },
    ["minecraft:gold_nugget"]   = { nugget = "minecraft:gold_nugget",   per_ingot = 9, per_block = 81  },
    ["minecraft:diamond"]       = { nugget = "minecraft:diamond",       per_ingot = 1, per_block = 9   },
}

local function push_items_to_barrel(mc_id, quantity)
    local barrel_name = peripheral.getName(barrel)
    local forms       = COMPRESS_FORMS[mc_id]
    local remaining   = quantity
    local pushed_nuggets = 0

    if not forms then
        -- Unknown material, push as-is
        for slot, item in pairs(vault.list()) do
            if remaining <= 0 then break end
            if item.name == mc_id then
                local to_push  = math.min(item.count, remaining)
                local actually = vault.pushItems(barrel_name, slot, to_push)
                pushed_nuggets = pushed_nuggets + actually
                remaining      = remaining - actually
            end
        end
        return pushed_nuggets
    end

    -- Push blocks first
    local blocks_needed = math.floor(remaining / forms.per_block)
    if blocks_needed > 0 and forms.block then
        for slot, item in pairs(vault.list()) do
            if blocks_needed <= 0 then break end
            if item.name == forms.block then
                local to_push  = math.min(item.count, blocks_needed)
                local actually = vault.pushItems(barrel_name, slot, to_push)
                pushed_nuggets = pushed_nuggets + (actually * forms.per_block)
                remaining      = remaining - (actually * forms.per_block)
                blocks_needed  = blocks_needed - actually
            end
        end
    end

    -- Push ingots next
    if forms.ingot then
        local ingots_needed = math.floor(remaining / forms.per_ingot)
        if ingots_needed > 0 then
            for slot, item in pairs(vault.list()) do
                if ingots_needed <= 0 then break end
                if item.name == forms.ingot then
                    local to_push  = math.min(item.count, ingots_needed)
                    local actually = vault.pushItems(barrel_name, slot, to_push)
                    pushed_nuggets = pushed_nuggets + (actually * forms.per_ingot)
                    remaining      = remaining - (actually * forms.per_ingot)
                    ingots_needed  = ingots_needed - actually
                end
            end
        end
    end

    -- Push remaining as nuggets/base units
    if remaining > 0 then
        for slot, item in pairs(vault.list()) do
            if remaining <= 0 then break end
            if item.name == mc_id then
                local to_push  = math.min(item.count, remaining)
                local actually = vault.pushItems(barrel_name, slot, to_push)
                pushed_nuggets = pushed_nuggets + actually
                remaining      = remaining - actually
            end
        end
    end

    return pushed_nuggets
end

local function slots_needed_for_withdrawal(mc_id, quantity)
    local forms = COMPRESS_FORMS[mc_id]
    if not forms then return math.ceil(quantity / 64) end

    local remaining = quantity
    local slots     = 0

    -- Blocks
    if forms.block then
        local blocks = math.floor(remaining / forms.per_block)
        if blocks > 0 then
            slots     = slots + math.ceil(blocks / 64)
            remaining = remaining - (blocks * forms.per_block)
        end
    end

    -- Ingots
    if forms.ingot and remaining > 0 then
        local ingots = math.floor(remaining / forms.per_ingot)
        if ingots > 0 then
            slots     = slots + math.ceil(ingots / 64)
            remaining = remaining - (ingots * forms.per_ingot)
        end
    end

    -- Nuggets/base units
    if remaining > 0 then
        slots = slots + math.ceil(remaining / 64)
    end

    return slots
end

local function free_barrel_slots()
    local used = 0
    for slot, item in pairs(barrel.list()) do
        used = used + 1
    end
    return 27 - used
end

local function dispense_items(items)
    local all_ok  = true
    local results = {}

    -- Check barrel capacity before dispensing anything
    local total_slots_needed = 0
    for _, item in ipairs(items) do
        total_slots_needed = total_slots_needed + slots_needed_for_withdrawal(item.mc_id, item.quantity)
    end

    local free_slots = free_barrel_slots()
    if total_slots_needed > free_slots then
        print(("Barrel too full: need %d slots, have %d"):format(total_slots_needed, free_slots))
        return false, {}, "Barrel does not have enough space. Please clear it first."
    end

    for _, item in ipairs(items) do
        local mc_id    = item.mc_id
        local quantity = item.quantity
        local pushed   = push_items_to_barrel(mc_id, quantity)

        table.insert(results, {
            mc_id    = mc_id,
            quantity = pushed,
        })

        if pushed < quantity then
            all_ok = false
            print(("Warning: only dispensed %d of %d %s"):format(pushed, quantity, mc_id))
        end
    end

    return all_ok, results, nil
end

-- ── Display helpers ───────────────────────────────────────────────────────────
local function clear_monitor()
    if not monitor then return end
    monitor.setBackgroundColor(colors.black)
    monitor.clear()
    monitor.setCursorPos(1, 1)
end

local function write_monitor(text, color, x, y)
    if not monitor then return end
    
    local final_x = x or 1
    local final_y = y or 1

    -- If "center" is requested, calculate the exact starting coordinate
    if x == "center" then
        local w, h = monitor.getSize()
        final_x = math.floor((w - #text) / 2) + 1
    end

    monitor.setCursorPos(final_x, final_y)
    monitor.setTextColor(color or colors.white)
    monitor.write(text)
end

local function show_idle()
    clear_monitor()
    write_monitor("BANK TERMINAL",    colors.yellow, "center", 1)
    write_monitor("ID: " .. tostring(TERMINAL_ID), colors.cyan, "center", 2)
    write_monitor("----------------", colors.gray,   "center", 3)
    write_monitor("Claim terminal",   colors.white,  "center", 5)
    write_monitor("to deposit or",    colors.white,  "center", 6)
    write_monitor("withdraw items.",  colors.white,  "center", 7)
    write_monitor("/claim_terminal",  colors.aqua,   "center", 9)
    write_monitor("----------------", colors.gray,   "center", 11)
    write_monitor("Status: READY",    colors.lime,   "center", 12)
end

local function show_status(line1, line2, line3, status_color)
    clear_monitor()
    write_monitor("BANK TERMINAL",    colors.yellow, "center", 1)
    write_monitor("================", colors.gray,   "center", 2)
    if line1 then write_monitor(line1, colors.white, "center", 4) end
    if line2 then write_monitor(line2, colors.white, "center", 5) end
    if line3 then write_monitor(line3, colors.white, "center", 6) end
    write_monitor("================", colors.gray,   "center", 9)
    local status_text = (status_color == colors.red and "ERROR" or "OK")
    write_monitor(status_text, status_color or colors.lime, "center", 10)
end

local function show_connecting()
    clear_monitor()
    write_monitor("BANK TERMINAL",    colors.yellow, "center", 1)
    write_monitor("----------------", colors.gray,   "center", 2)
    write_monitor("Connecting...",    colors.orange, "center", 4)
    write_monitor("Please wait.",     colors.white,  "center", 5)
end

local function show_claimed(name)
    clear_monitor()
    write_monitor("BANK TERMINAL",    colors.yellow, "center", 1)
    write_monitor("----------------", colors.gray,   "center", 2)
    write_monitor("Claimed by:",      colors.white,  "center", 4)
    write_monitor(name,               colors.cyan,   "center", 5)
    write_monitor("----------------", colors.gray,   "center", 6)
    write_monitor("Deposit: place",   colors.white,  "center", 8)
    write_monitor("items in barrel.", colors.white,  "center", 9)
    write_monitor("Withdraw: use",    colors.white,  "center", 11)
    write_monitor("/withdraw",        colors.aqua,   "center", 12)
end

-- ── Alert sound ───────────────────────────────────────────────────────────────
local function alert()
    if speaker then
        speaker.playNote("harp", 1.0, 10)
    end
    -- Pulse redstone below for note block
    redstone.setOutput("bottom", true)
    sleep(0.1)
    redstone.setOutput("bottom", false)
end

-- ── Item counting ─────────────────────────────────────────────────────────────
local function count_nuggets(inv)
    local mats = {
        ["create:copper_nugget"]      = 0,
        ["minecraft:copper_ingot"]    = 0,
        ["minecraft:copper_block"]    = 0,
        ["create:zinc_nugget"]        = 0,
        ["create:zinc_ingot"]         = 0,
        ["create:zinc_block"]         = 0,
        ["minecraft:iron_nugget"]     = 0,
        ["minecraft:iron_ingot"]      = 0,
        ["minecraft:iron_block"]      = 0,
        ["minecraft:gold_nugget"]     = 0,
        ["minecraft:gold_ingot"]      = 0,
        ["minecraft:gold_block"]      = 0,
        ["minecraft:diamond"]         = 0,
        ["minecraft:diamond_block"]   = 0,
    }

    for slot, item in pairs(inv.list()) do
        if mats[item.name] ~= nil then
            mats[item.name] = mats[item.name] + item.count
        end
    end

    return {
        { mc_id = "create:copper_nugget",   quantity = (mats["minecraft:copper_block"] * 81) + (mats["minecraft:copper_ingot"] * 9) + mats["create:copper_nugget"] },
        { mc_id = "create:zinc_nugget",     quantity = (mats["create:zinc_block"]      * 81) + (mats["create:zinc_ingot"]      * 9) + mats["create:zinc_nugget"]   },
        { mc_id = "minecraft:iron_nugget",  quantity = (mats["minecraft:iron_block"]   * 81) + (mats["minecraft:iron_ingot"]   * 9) + mats["minecraft:iron_nugget"] },
        { mc_id = "minecraft:gold_nugget",  quantity = (mats["minecraft:gold_block"]   * 81) + (mats["minecraft:gold_ingot"]   * 9) + mats["minecraft:gold_nugget"] },
        { mc_id = "minecraft:diamond",      quantity = (mats["minecraft:diamond_block"] * 9) + mats["minecraft:diamond"]                                            },
    }
end

local function has_items(nugget_list)
    for _, entry in ipairs(nugget_list) do
        if entry.quantity > 0 then return true end
    end
    return false
end

local function filter_items(nugget_list)
    local filtered = {}
    for _, entry in ipairs(nugget_list) do
        if entry.quantity > 0 then
            table.insert(filtered, entry)
        end
    end
    return filtered
end

-- ── WebSocket message handler ─────────────────────────────────────────────────
local ws = nil  -- global so handlers can close it

local function send(data)
    if ws then
        ws.send(textutils.serialiseJSON(data))
    end
end

local function handle_message(raw)
    local ok, msg = pcall(textutils.unserialiseJSON, raw)
    if not ok or not msg then
        print("Bad message: " .. tostring(raw))
        return
    end

    local t = msg.type
    local p = msg.payload or {}

    if t == "pong" then
        -- keepalive acknowledged, nothing to do

    elseif t == "claim_active" then
        alert()
        show_claimed(p.display_name or "Unknown")

    elseif t == "claim_released" then
        show_idle()

    elseif t == "deposit_accepted" then
        deposit_pending = false
        alert()
        show_status("Processing...", "Moving items", "to vault.", colors.yellow)
        
        -- PHYSICALLY MOVE THE ITEMS NOW
        local items_moved = pull_items_from_barrel()
        print("Vault pulled " .. items_moved .. " items from deposit barrel.")
        local total_str = ("%.2f"):format(p.total)
        show_status(
            "Deposit accepted!",
            "$" .. total_str,
            "credited to account.",
            colors.lime
        )
        sleep(5)
        show_idle()

    elseif t == "deposit_rejected" then
        deposit_pending = false
        alert()
        show_status("Deposit rejected.", p.reason or "", nil, colors.red)
        sleep(5)
        show_idle()

    elseif t == "dispense" then
        alert()
        show_status("Dispensing...", "Please wait.", nil, colors.yellow)

        local ok, results = dispense_items(p.items or {})

        if ok then
            send({
                type    = "dispense_confirm",
                payload = {
                    discord_id = p.discord_id,
                    items      = results,
                }
            })
            show_status("Collect your", "items from the", "barrel!", colors.lime)
        else
            -- Partial dispense — still confirm with what was actually pushed
            -- so the backend knows what happened
            send({
                type    = "dispense_confirm",
                payload = {
                    discord_id = p.discord_id,
                    items      = results,
                    partial    = true,
                }
            })
            show_status("Partial fill!", "Some items may", "be missing.", colors.orange)
        end

        sleep(10)
        show_idle()

    elseif t == "deposit_ready_ack" then
        -- Server acknowledged our deposit_ready, waiting for player confirmation
        show_status("Items received.", "Check Discord", "to confirm.", colors.yellow)

    elseif t == "disconnect" then
        print("Server requested disconnect: " .. (p.reason or "unknown"))
        if ws then ws.close() end
        ws = nil

    else
        print("Unknown message type: " .. tostring(t))
    end
end

-- ── Deposit trigger ───────────────────────────────────────────────────────────
-- The terminal doesn't know the player's discord_id on its own.
-- The player must have claimed the terminal via /claim_terminal first.
-- When the server sends claim_active it includes their discord_id,
-- which we store here so deposit_ready can include it.
local claimed_discord_id = nil

local function on_claim_active(p)
    claimed_discord_id = p.discord_id
    alert()
    show_claimed(p.display_name or p.discord_id)
end

local function on_claim_released()
    claimed_discord_id = nil
    show_idle()
end

-- Override handle_message to capture discord_id from claim
local _base_handle = handle_message
handle_message = function(raw)
    local ok, msg = pcall(textutils.unserialiseJSON, raw)
    if ok and msg then
        if msg.type == "claim_active" then
            on_claim_active(msg.payload or {})
            return
        elseif msg.type == "claim_released" then
            on_claim_released()
            return
        end
    end
    _base_handle(raw)
end

-- ── Keepalive ─────────────────────────────────────────────────────────────────
local function keepalive_loop()
    while true do
        sleep(30)
        send({ type = "ping" })
    end
end

-- ── Barrel watcher ────────────────────────────────────────────────────────────
-- Watches for items being placed in the barrel when a claim is active,
-- then automatically sends deposit_ready to the backend.
local last_item_count = 0

local function barrel_watch_loop()
    while true do
        sleep(1)
        if claimed_discord_id and not deposit_pending then
            local items    = count_nuggets(barrel)
            local filtered = filter_items(items)
            local total    = 0
            for _, e in ipairs(filtered) do total = total + e.quantity end

            if total > 0 and total ~= last_item_count then
                last_item_count = total
                sleep(5)
                items    = count_nuggets(barrel)
                filtered = filter_items(items)
                total    = 0
                for _, e in ipairs(filtered) do total = total + e.quantity end

                if total > 0 and not deposit_pending then
                    deposit_pending = true
                    send({
                        type    = "deposit_ready",
                        payload = {
                            discord_id = claimed_discord_id,
                            items      = filtered,
                        }
                    })
                    show_status("Items detected.", "Check Discord", "to confirm.", colors.yellow)
                end
            elseif total == 0 then
                last_item_count = 0
            end
        end
    end
end

-- ── Main connection loop ──────────────────────────────────────────────────────
local function main()
    show_connecting()

    while true do
        print("Connecting to " .. WS_URL)
        local ok, err = pcall(function()
            ws = http.websocket(WS_URL)
            if not ws then
                error("WebSocket connection failed")
            end

            print("Connected!")
            show_idle()

            -- Run keepalive and barrel watcher in parallel with message loop
            parallel.waitForAny(
                -- Message receive loop
                function()
                    while true do
                        local raw, binary = ws.receive()
                        if not raw then
                            print("Connection closed by server")
                            break
                        end
                        handle_message(raw)
                    end
                end,
                -- Keepalive
                keepalive_loop,
                -- Barrel watcher
                barrel_watch_loop
            )
        end)

        if not ok then
            print("Connection error: " .. tostring(err))
        end

        -- Clean up
        ws = nil
        claimed_discord_id = nil
        last_item_count    = 0
        deposit_pending    = false
        show_connecting()
        print("Reconnecting in " .. RECONNECT_DELAY .. " seconds...")
        sleep(RECONNECT_DELAY)
    end
end

main()