if SERVER then
    AddCSLuaFile("dynamic_model_importer/sh_core.lua")
    util.AddNetworkString("dynamic_model_importer_request_list")
    util.AddNetworkString("dynamic_model_importer_send_list")
    util.AddNetworkString("dynamic_model_importer_chat")
    util.AddNetworkString("dynamic_model_importer_request_override")
    util.AddNetworkString("dynamic_model_importer_send_override")
    util.AddNetworkString("dynamic_model_importer_save_override")
    util.AddNetworkString("dynamic_model_importer_select_override_model")
end

include("dynamic_model_importer/sh_core.lua")

if list then
    list.Add("OverrideMaterials", DynamicModelImporter.InvisibleMaterialPath)
end

local function write_entry(entry)
    net.WriteString(tostring(entry.model_id or ""))
    net.WriteString(tostring(entry.display_name or entry.model_id or ""))
    net.WriteString(tostring(entry.category_readable or ""))
    net.WriteString(tostring(entry.model_path or ""))
    net.WriteBool(tobool(entry.has_player_model))
    net.WriteBool(tobool(entry.legacy))
end

if SERVER then
    function DynamicModelImporter.SendToolModelSelection(ply, toolName, modelPath)
        if not IsValid(ply) then return end
        local safePath = DynamicModelImporter.NormalizeOverrideModelPath(modelPath)
        if not safePath then return end
        net.Start("dynamic_model_importer_select_override_model")
            net.WriteString(tostring(toolName or ""))
            net.WriteString(safePath)
        net.Send(ply)
    end

    local function send_model_list(ply)
        local list = DynamicModelImporter.ListAvailableModels()
        net.Start("dynamic_model_importer_send_list")
            net.WriteUInt(#list, 16)
            for _, entry in ipairs(list) do
                write_entry(entry)
            end
        net.Send(ply)
    end

    local function send_model_override(ply, modelPath)
        local safePath = DynamicModelImporter.NormalizeOverrideModelPath(modelPath)
        if not safePath then return end
        net.Start("dynamic_model_importer_send_override")
            net.WriteString(safePath)
            net.WriteString(util.TableToJSON(DynamicModelImporter.GetModelPathOverride(safePath), false) or "{}")
        net.Send(ply)
    end

    net.Receive("dynamic_model_importer_request_list", function(_, ply)
        if not IsValid(ply) then return end
        send_model_list(ply)
    end)

    net.Receive("dynamic_model_importer_request_override", function(_, ply)
        if not IsValid(ply) then return end
        local modelPath = DynamicModelImporter.NormalizeOverrideModelPath(net.ReadString())
        if not modelPath then
            DynamicModelImporter.Chat(ply, "Invalid model path.")
            return
        end
        send_model_override(ply, modelPath)
    end)

    net.Receive("dynamic_model_importer_save_override", function(_, ply)
        if not IsValid(ply) then return end
        local modelPath = DynamicModelImporter.NormalizeOverrideModelPath(net.ReadString())
        local rawOverride = net.ReadString()
        if not modelPath then
            DynamicModelImporter.Chat(ply, "Invalid model path.")
            return
        end
        if not DynamicModelImporter.CanEditOverrides(ply) then
            DynamicModelImporter.Chat(ply, "Only admins can save Dynamic Model Importer repairs on this server.")
            send_model_override(ply, modelPath)
            return
        end
        local parsed = util.JSONToTable(rawOverride or "{}", true, true)
        DynamicModelImporter.SetModelPathOverride(modelPath, DynamicModelImporter.SanitizeModelOverride(parsed))
        DynamicModelImporter.ApplySavedOverridesForModelPath(modelPath)
        send_model_override(ply, modelPath)
        DynamicModelImporter.Chat(ply, "Saved repairs for model path: %s", modelPath)
    end)

else
    DynamicModelImporter.LastModelList = DynamicModelImporter.LastModelList or {}
    DynamicModelImporter.LastModelOverrides = DynamicModelImporter.LastModelOverrides or {}

    net.Receive("dynamic_model_importer_chat", function()
        local message = net.ReadString()
        local count = net.ReadUInt(4)
        local args = {}
        for i = 1, count do
            args[i] = net.ReadString()
        end
        local unpack_args = unpack or table.unpack
        chat.AddText(Color(120, 190, 255), "[Dynamic Model Importer] ", color_white, DynamicModelImporter.LF(message, unpack_args(args)))
    end)

    net.Receive("dynamic_model_importer_send_list", function()
        local count = net.ReadUInt(16)
        local list = {}
        for i = 1, count do
            list[i] = {
                model_id = net.ReadString(),
                display_name = net.ReadString(),
                category_readable = net.ReadString(),
                model_path = net.ReadString(),
                has_player_model = net.ReadBool(),
                legacy = net.ReadBool(),
            }
        end
        DynamicModelImporter.LastModelList = list
        hook.Run("DynamicModelImporterListUpdated", list)
    end)

    net.Receive("dynamic_model_importer_send_override", function()
        local modelPath = DynamicModelImporter.NormalizeOverrideModelPath(net.ReadString())
        local rawOverride = net.ReadString()
        if not modelPath then return end
        local parsed = util.JSONToTable(rawOverride or "{}", true, true)
        local override = DynamicModelImporter.SanitizeModelOverride(parsed)
        DynamicModelImporter.LastModelOverrides[modelPath] = override
        hook.Run("DynamicModelImporterOverrideUpdated", modelPath, override)
    end)

    net.Receive("dynamic_model_importer_select_override_model", function()
        local toolName = net.ReadString()
        local modelPath = DynamicModelImporter.NormalizeOverrideModelPath(net.ReadString())
        if not modelPath then return end
        if toolName == "hide_material" then
            RunConsoleCommand("dynamic_model_importer_hide_material_model_path", modelPath)
            hook.Run("DynamicModelImporterHideMaterialTargetSelected", modelPath)
        elseif toolName == "jigglebone" then
            RunConsoleCommand("dynamic_model_importer_jigglebone_model_path", modelPath)
            hook.Run("DynamicModelImporterJiggleboneTargetSelected", modelPath)
        end
    end)

    concommand.Add("dynamic_model_importer_refresh", function()
        net.Start("dynamic_model_importer_request_list")
        net.SendToServer()
    end)

end
