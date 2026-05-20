local barrel = peripheral.find("minecraft:barrel")
local vault = peripheral.find("create:item_vault")

function count_nugs(inv)
    local mats = {
        ["create:copper_nugget"] = 0,
        ["minecraft:copper_ingot"] = 0,
        ["minecraft:copper_block"] = 0,

        ["create:zinc_nugget"] = 0,
        ["create:zinc_ingot"] = 0,
        ["create:zinc_block"] = 0,

        ["minecraft:iron_nugget"] = 0,
        ["minecraft:iron_ingot"] = 0,
        ["minecraft:iron_block"] = 0,

        ["minecraft:gold_nugget"] = 0,
        ["minecraft:gold_ingot"] = 0,
        ["minecraft:gold_block"] = 0,

        ["minecraft:diamond"] = 0,
        ["minecraft:diamond_block"] = 0
    }

    local inv_name = peripheral.getName(inv)
    for slot, item in pairs(inv.list()) do
        print(("[%s] %d x %s in slot %d"):format(inv_name, item.count, item.name, slot))
        if mats[item.name] ~= nil then
            mats[item.name] = mats[item.name] + item.count
        end
    end

    local copper_sum = (mats["minecraft:copper_block"] * 81) + (mats["minecraft:copper_ingot"] * 9) + mats["create:copper_nugget"]
    local zinc_sum = (mats["create:zinc_block"] * 81) + (mats["create:zinc_ingot"] * 9) + mats["create:zinc_nugget"]
    local iron_sum = (mats["minecraft:iron_block"] * 81) + (mats["minecraft:iron_ingot"] * 9) + mats["minecraft:iron_nugget"]
    local gold_sum = (mats["minecraft:gold_block"] * 81) + (mats["minecraft:gold_ingot"] * 9) + mats["minecraft:gold_nugget"]
    local diamond_sum = (mats["minecraft:diamond_block"] * 9) + mats["diamond"]

    return {
        copper = copper_sum,
        zinc = zinc_sum,
        iron = iron_sum,
        gold = gold_sum,
        diamond = diamond_sum
    }
end

local barrel_inv = count_nugs(barrel)
for mat, num in pairs(barrel_inv) do
    print(("%s: %d"):format(mat, num))
end