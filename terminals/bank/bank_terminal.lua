-- bank_terminal.lua
local TERMINAL_ID = 1                          -- set per terminal
local TOKEN       = "your-token-here"          -- set per terminal
local HOST        = "mc-bank.duckdns.org:8000"
local WS_URL      = ("ws://%s/ws/terminal/%d?token=%s"):format(HOST, TERMINAL_ID, TOKEN)
local RECONNECT_DELAY = 30  -- seconds between reconnect attempts

-- ── Peripherals ───────────────────────────────────────────────────────────────
local barrel  = peripheral.find("minecraft:barrel")
local monitor = peripheral.find("monitor")
local speaker = peripheral.find("note_block") or peripheral.find("speaker")

if not barrel then
    error("No barrel found — check peripheral connections")
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
    if x and y then monitor.setCursorPos(x, y) end
    monitor.setTextColor(color or colors.white)
    monitor.write(text)
end

local function show_idle()
    clear_monitor()
    write_monitor("  BANK TERMINAL", colors.yellow, 1, 1)
    write_monitor("────────────────", colors.gray, 1, 2)
    write_monitor("  Place items   ", colors.white, 1, 4)
    write_monitor("  in the barrel ", colors.white, 1, 5)
    write_monitor("  then /deposit ", colors.white, 1, 6)
    write_monitor("  in Discord.   ", colors.white, 1, 7)
    write_monitor("────────────────", colors.gray, 1, 9)
    write_monitor("  Status: READY ", colors.lime, 1, 10)
end

local function show_status(line1, line2, line3, status_color)
    clear_monitor()
    write_monitor("  BANK TERMINAL", colors.yellow, 1, 1)
    write_monitor("────────────────", colors.gray, 1, 2)
    if line1 then write_monitor("  " .. line1, colors.white, 1, 4) end
    if line2 then write_monitor("  " .. line2, colors.white, 1, 5) end
    if line3 then write_monitor("  " .. line3, colors.white, 1, 6) end
    write_monitor("────────────────", colors.gray, 1, 9)
    write_monitor("  " .. (status_color == colors.red and "ERROR" or "OK") .. "            ", status_color or colors.lime, 1, 10)
end

local function show_connecting()
    clear_monitor()
    write_monitor("  BANK TERMINAL", colors.yellow, 1, 1)
    write_monitor("────────────────", colors.gray, 1, 2)
    write_monitor("  Connecting... ", colors.orange, 1, 4)
end

local function show_claimed(name)
    clear_monitor()
    write_monitor("  BANK TERMINAL", colors.yellow, 1, 1)
    write_monitor("────────────────", colors.gray, 1, 2)
    write_monitor("  Claimed by:   ", colors.white, 1, 4)
    write_monitor("  " .. name,       colors.cyan,  1, 5)
    write_monitor("  Place items   ", colors.white, 1, 7)
    write_monitor("  in barrel &   ", colors.white, 1, 8)
    write_monitor("  confirm in    ", colors.white, 1, 9)
    write_monitor("  Discord.      ", colors.white, 1, 10)
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
        alert()
        show_status(
            "Deposit accepted!",
            "$" .. tostring(p.total),
            "credited to account.",
            colors.lime
        )
        sleep(5)
        show_idle()

    elseif t == "deposit_rejected" then
        alert()
        show_status("Deposit rejected.", p.reason or "", nil, colors.red)
        sleep(5)
        show_idle()

    elseif t == "dispense" then
        alert()
        show_status("Dispensing...", "Please wait.", nil, colors.yellow)

        -- Push items from vault into barrel
        -- The Create vault is on the back, barrel on the front
        -- We use a turtle or the vault peripheral to move items
        -- For now signal the vault via redstone and confirm
        -- (actual item movement logic depends on your Create setup)

        -- TODO: implement item movement from vault to barrel
        -- Once items are in barrel, send confirmation
        send({
            type = "dispense_confirm",
            payload = {
                discord_id = p.discord_id,
                items      = p.items,
            }
        })

        show_status("Collect your", "items from the", "barrel!", colors.lime)
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
        if claimed_discord_id then
            local items     = count_nuggets(barrel)
            local filtered  = filter_items(items)
            local total     = 0
            for _, e in ipairs(filtered) do total = total + e.quantity end

            if total > 0 and total ~= last_item_count then
                last_item_count = total
                -- Debounce — wait a moment in case player is still depositing
                sleep(2)
                items    = count_nuggets(barrel)
                filtered = filter_items(items)
                total    = 0
                for _, e in ipairs(filtered) do total = total + e.quantity end

                if total > 0 then
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
        show_connecting()
        print("Reconnecting in " .. RECONNECT_DELAY .. " seconds...")
        sleep(RECONNECT_DELAY)
    end
end

main()