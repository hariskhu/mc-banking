-- vault_manager.lua
-- Sits next to the vault, pushes left to compress, down to decompress
 
local FLOAT = 24  -- minimum nuggets/ingots to keep ready per material
local COMPRESS_THRESHOLD = 33  -- compress when we have this many nuggets/ingots
 
-- Peripheral setup
local vault = peripheral.find("create:item_vault")
if not vault then error("No vault found") end
 
-- The processing peripherals (left = compress up, down = decompress)
-- Adjust these names to match your actual peripheral names
local COMPRESS_SIDE   = "left"
local DECOMPRESS_SIDE = "bottom"
 
-- ── Material definitions ──────────────────────────────────────────────────────
-- Each material has nugget, ingot, and block forms with conversion ratios
local MATERIALS = {
    {
        name    = "Copper",
        nugget  = "create:copper_nugget",
        ingot   = "minecraft:copper_ingot",
        block   = "minecraft:copper_block",
        has_nugget = true,
    },
    {
        name    = "Zinc",
        nugget  = "create:zinc_nugget",
        ingot   = "create:zinc_ingot",
        block   = "create:zinc_block",
        has_nugget = true,
    },
    {
        name    = "Iron",
        nugget  = "minecraft:iron_nugget",
        ingot   = "minecraft:iron_ingot",
        block   = "minecraft:iron_block",
        has_nugget = true,
    },
    {
        name    = "Gold",
        nugget  = "minecraft:gold_nugget",
        ingot   = "minecraft:gold_ingot",
        block   = "minecraft:gold_block",
        has_nugget = true,
    },
    {
        name       = "Diamond",
        nugget     = "minecraft:diamond",
        ingot      = nil,  -- diamonds have no ingot form
        block      = "minecraft:diamond_block",
        has_nugget = false,  -- diamond IS the base unit
    },
}
 
-- ── Vault inventory helpers ───────────────────────────────────────────────────
local function count_item(mc_id)
    local total = 0
    for slot, item in pairs(vault.list()) do
        if item.name == mc_id then
            total = total + item.count
        end
    end
    return total
end
 
local function push_to_side(side, mc_id, quantity)
    local remaining = quantity
    local pushed    = 0

    for slot, item in pairs(vault.list()) do
        if remaining <= 0 then break end
        if item.name == mc_id then
            local to_push  = math.min(item.count, remaining)
            local actually = vault.pushItems(side, slot, to_push)
            pushed    = pushed + actually
            remaining = remaining - actually
        end
    end

    return pushed
end
 
-- ── Compression logic ─────────────────────────────────────────────────────────
-- For each material, check nugget and ingot counts.
-- If above COMPRESS_THRESHOLD, push the excess to the compression side
-- leaving exactly FLOAT nuggets/ingots behind.
local function compress_pass()
    for _, mat in ipairs(MATERIALS) do
        if mat.has_nugget then
            -- Check nuggets → compress to ingots
            local nugget_count = count_item(mat.nugget)
            if nugget_count >= COMPRESS_THRESHOLD then
                -- Keep FLOAT nuggets, compress the rest
                -- Round down to nearest 9 to avoid partial ingots
                local to_compress = nugget_count - FLOAT
                to_compress = math.floor(to_compress / 9) * 9
                if to_compress >= 9 then
                    print(("Compressing %d %s nuggets to ingots"):format(to_compress, mat.name))
                    push_to_side(COMPRESS_SIDE, mat.nugget, to_compress)
                    sleep(1)  -- wait for crafting to complete
                end
            end
 
            -- Check ingots → compress to blocks (only if we have ingot form)
            if mat.ingot then
                local ingot_count = count_item(mat.ingot)
                if ingot_count >= COMPRESS_THRESHOLD then
                    local to_compress = ingot_count - FLOAT
                    to_compress = math.floor(to_compress / 9) * 9
                    if to_compress >= 9 then
                        print(("Compressing %d %s ingots to blocks"):format(to_compress, mat.name))
                        push_to_side(COMPRESS_SIDE, mat.ingot, to_compress)
                        sleep(1)
                    end
                end
            end
        else
            -- Diamonds: base unit is diamond, compresses directly to blocks
            local diamond_count = count_item(mat.nugget)  -- "nugget" field holds "minecraft:diamond"
            if diamond_count >= COMPRESS_THRESHOLD then
                local to_compress = diamond_count - FLOAT
                to_compress = math.floor(to_compress / 9) * 9
                if to_compress >= 9 then
                    print(("Compressing %d diamonds to blocks"):format(to_compress))
                    push_to_side(COMPRESS_SIDE, mat.nugget, to_compress)
                    sleep(1)
                end
            end
        end
    end
end
 
-- ── Decompression logic ───────────────────────────────────────────────────────
-- For each material, if nugget/ingot count is below FLOAT,
-- decompress blocks → ingots → nuggets until we have enough.
local function decompress_pass()
    for _, mat in ipairs(MATERIALS) do
        if mat.has_nugget then
            -- Check nuggets first
            local nugget_count = count_item(mat.nugget)
            if nugget_count < FLOAT then
                local needed = FLOAT - nugget_count
                -- Try to get from ingots first
                if mat.ingot then
                    local ingot_count = count_item(mat.ingot)
                    if ingot_count > 0 then
                        -- How many ingots do we need to decompress?
                        local ingots_needed = math.ceil(needed / 9)
                        local ingots_to_use = math.min(ingot_count, ingots_needed)
                        print(("Decompressing %d %s ingots to nuggets"):format(ingots_to_use, mat.name))
                        push_to_side(DECOMPRESS_SIDE, mat.ingot, ingots_to_use)
                        sleep(1)
                    else
                        -- No ingots, try blocks
                        local block_count = count_item(mat.block)
                        if block_count > 0 then
                            -- Decompress one block to ingots first
                            print(("Decompressing 1 %s block to ingots"):format(mat.name))
                            push_to_side(DECOMPRESS_SIDE, mat.block, 1)
                            sleep(1)
                            -- Then decompress ingots to nuggets on next pass
                        end
                    end
                end
            end
 
            -- Check ingots (only if we have ingot form)
            if mat.ingot then
                local ingot_count = count_item(mat.ingot)
                if ingot_count < FLOAT then
                    local block_count = count_item(mat.block)
                    if block_count > 0 then
                        local blocks_needed = math.ceil((FLOAT - ingot_count) / 9)
                        local blocks_to_use = math.min(block_count, blocks_needed)
                        print(("Decompressing %d %s blocks to ingots"):format(blocks_to_use, mat.name))
                        push_to_side(DECOMPRESS_SIDE, mat.block, blocks_to_use)
                        sleep(1)
                    end
                end
            end
 
        else
            -- Diamonds: check diamond count, decompress from blocks if needed
            local diamond_count = count_item(mat.nugget)
            if diamond_count < FLOAT then
                local block_count = count_item(mat.block)
                if block_count > 0 then
                    local blocks_needed = math.ceil((FLOAT - diamond_count) / 9)
                    local blocks_to_use = math.min(block_count, blocks_needed)
                    print(("Decompressing %d diamond blocks"):format(blocks_to_use))
                    push_to_side(DECOMPRESS_SIDE, mat.block, blocks_to_use)
                    sleep(1)
                end
            end
        end
    end
end
 
-- ── Status display ────────────────────────────────────────────────────────────
local function print_status()
    print("\n=== Vault Status ===")
    for _, mat in ipairs(MATERIALS) do
        local base_unit  = mat.nugget
        local base_count = count_item(base_unit)
        local ingot_count = mat.ingot and count_item(mat.ingot) or 0
        local block_count = count_item(mat.block)
 
        if mat.has_nugget then
            print(("%s: %d nuggets, %d ingots, %d blocks"):format(
                mat.name, base_count, ingot_count, block_count
            ))
        else
            print(("%s: %d diamonds, %d blocks"):format(
                mat.name, base_count, block_count
            ))
        end
    end
    print("====================\n")
end
 
-- ── Main loop ─────────────────────────────────────────────────────────────────
local function balance()
    print("Running balance pass...")
    compress_pass()
    sleep(2)  -- wait for any crafting to settle
    decompress_pass()
    sleep(2)
    print_status()
end
 
print("Vault manager started. Balancing every 30 seconds.")
print_status()
 
while true do
    balance()
    sleep(30)
end