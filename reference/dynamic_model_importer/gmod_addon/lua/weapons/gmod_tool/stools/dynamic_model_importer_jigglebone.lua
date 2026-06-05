if SERVER then
    AddCSLuaFile()
    AddCSLuaFile("dynamic_model_importer/sh_core.lua")
end

include("dynamic_model_importer/sh_core.lua")

TOOL.Category = "#dynamic_model_importer.category"
TOOL.Name = "#tool.dynamic_model_importer_jigglebone.name"
TOOL.Command = nil
TOOL.ConfigName = ""

TOOL.ClientConVar = {
    model_path = "",
}

local function L(raw)
    return DynamicModelImporter.L(raw)
end

local function get_target(trace, owner)
    local ent = trace and trace.Entity
    if not IsValid(ent) then ent = owner end
    if IsValid(ent) and IsValid(ent.AttachedEntity) then ent = ent.AttachedEntity end
    return ent
end

local function read_convar_string(name, fallback)
    local cvar = GetConVar(name)
    if not cvar then return fallback or "" end
    return cvar:GetString()
end

local function copy_model_override(override)
    local sanitized = DynamicModelImporter.SanitizeModelOverride(override)
    local copied = DynamicModelImporter.EmptyModelOverride()
    for key, value in pairs(sanitized.hidden_submaterials) do
        copied.hidden_submaterials[key] = value
    end
    copied.no_jiggle.all = sanitized.no_jiggle.all
    for key, value in pairs(sanitized.no_jiggle.bones) do
        copied.no_jiggle.bones[key] = value
    end
    return copied
end

local function selected_list_line(list)
    if not IsValid(list) then return nil end
    local rowIndex = list:GetSelectedLine()
    if not rowIndex then return nil end
    return list:GetLine(rowIndex)
end

local request_override
local save_override

if CLIENT then
    language.Add("dynamic_model_importer.category", L("Model Importer"))
    language.Add("tool.dynamic_model_importer_jigglebone.name", L("Jigglebone tool for Imported model"))
    language.Add("tool.dynamic_model_importer_jigglebone.desc", L("Disable jigglebones for any model path."))
    language.Add("tool.dynamic_model_importer_jigglebone.0", L("Right-click an NPC, ragdoll, or player to select its model. Left-click toggles all jigglebones."))
end

if CLIENT then
    function request_override(modelPath)
        modelPath = DynamicModelImporter.NormalizeOverrideModelPath(modelPath)
        if not modelPath then return end
        net.Start("dynamic_model_importer_request_override")
            net.WriteString(modelPath)
        net.SendToServer()
    end

    function save_override(modelPath, override)
        modelPath = DynamicModelImporter.NormalizeOverrideModelPath(modelPath)
        if not modelPath then return end
        net.Start("dynamic_model_importer_save_override")
            net.WriteString(modelPath)
            net.WriteString(util.TableToJSON(DynamicModelImporter.SanitizeModelOverride(override), false) or "{}")
        net.SendToServer()
    end

    local function select_model_path(modelPath)
        modelPath = DynamicModelImporter.NormalizeOverrideModelPath(modelPath)
        if not modelPath then
            notification.AddLegacy(L("Target has no valid model path."), NOTIFY_ERROR, 3)
            return false
        end
        RunConsoleCommand("dynamic_model_importer_jigglebone_model_path", modelPath)
        request_override(modelPath)
        hook.Run("DynamicModelImporterJiggleboneTargetSelected", modelPath)
        notification.AddLegacy(DynamicModelImporter.LF("Selected model: %s", modelPath), NOTIFY_GENERIC, 2)
        return true
    end

    function TOOL:RightClick(trace)
        local modelPath = DynamicModelImporter.EntityModelPath(get_target(trace, LocalPlayer()))
        if modelPath then select_model_path(modelPath) end
        return true
    end

    function TOOL:LeftClick(trace)
        return true
    end
else
    local function send_override_to_player(ply, modelPath)
        if not IsValid(ply) then return end
        modelPath = DynamicModelImporter.NormalizeOverrideModelPath(modelPath)
        if not modelPath then return end
        net.Start("dynamic_model_importer_send_override")
            net.WriteString(modelPath)
            net.WriteString(util.TableToJSON(DynamicModelImporter.GetModelPathOverride(modelPath), false) or "{}")
        net.Send(ply)
    end

    local function selected_or_target_model_path(tool, trace, ply)
        local targetModelPath = DynamicModelImporter.EntityModelPath(get_target(trace, ply))
        if targetModelPath then return targetModelPath end
        return DynamicModelImporter.NormalizeOverrideModelPath(tool:GetClientInfo("model_path"))
    end

    function TOOL:LeftClick(trace)
        local ply = self:GetOwner()
        local modelPath = selected_or_target_model_path(self, trace, ply)
        if not modelPath then
            DynamicModelImporter.Chat(ply, "Target has no valid model path.")
            return false
        end
        if not DynamicModelImporter.CanEditOverrides(ply) then
            DynamicModelImporter.Chat(ply, "Only admins can save Dynamic Model Importer repairs on this server.")
            return false
        end

        local override = DynamicModelImporter.GetModelPathOverride(modelPath)
        if override.no_jiggle.all then
            override.no_jiggle.all = false
            override.no_jiggle.bones = {}
        else
            override.no_jiggle.all = true
            override.no_jiggle.bones = {}
        end

        DynamicModelImporter.SetModelPathOverride(modelPath, override)
        DynamicModelImporter.ApplySavedOverridesForModelPath(modelPath)
        send_override_to_player(ply, modelPath)
        DynamicModelImporter.Chat(ply, "Saved repairs for model path: %s", modelPath)
        return true
    end

    function TOOL:RightClick(trace)
        local ent = get_target(trace, self:GetOwner())
        local modelPath = DynamicModelImporter.EntityModelPath(ent)
        if not modelPath then return false end
        DynamicModelImporter.SendToolModelSelection(self:GetOwner(), "jigglebone", modelPath)
        return true
    end
end

function TOOL:Reload(trace)
    return false
end

if CLIENT then
    function TOOL.BuildCPanel(panel)
        panel:AddControl("Header", {
            Description = L("Right-click an NPC, ragdoll, or player to select its model. Left-click toggles all jigglebones.")
        })

        local state = {
            model_path = DynamicModelImporter.NormalizeOverrideModelPath(read_convar_string("dynamic_model_importer_jigglebone_model_path", "")),
            preview = nil,
            bones = {},
            override = DynamicModelImporter.EmptyModelOverride(),
        }

        local status = vgui.Create("DLabel")
        status:SetWrap(true)
        status:SetAutoStretchVertical(true)
        status:SetTextColor(color_white)
        panel:AddItem(status)

        local selected = panel:TextEntry(L("Selected model path"), "dynamic_model_importer_jigglebone_model_path")
        selected:SetEditable(false)

        local boneList = vgui.Create("DListView")
        boneList:SetTall(260)
        boneList:SetMultiSelect(false)
        boneList:AddColumn(L("Index"))
        boneList:AddColumn(L("Bone"))
        boneList:AddColumn(L("No jiggle"))
        panel:AddItem(boneList)

        local disableBoneButton = panel:Button(L("Disable selected bone jiggle"))
        local restoreBoneButton = panel:Button(L("Restore selected bone jiggle"))
        local disableAllButton = panel:Button(L("Disable all jiggle"))
        local restoreAllButton = panel:Button(L("Restore all jiggle"))

        local function set_status(text)
            if IsValid(status) then status:SetText(L(text or "")) end
        end

        local function cleanup_preview()
            if IsValid(state.preview) then state.preview:Remove() end
            state.preview = nil
        end

        local function bone_disabled(name)
            return state.override.no_jiggle.all or state.override.no_jiggle.bones[name] == true
        end

        local function populate_bones()
            boneList:Clear()
            for _, boneInfo in ipairs(state.bones) do
                local line = boneList:AddLine(tostring(boneInfo.index), boneInfo.name, bone_disabled(boneInfo.name) and L("yes") or L("no"))
                line.BoneName = boneInfo.name
            end
        end

        local function inspect_model()
            cleanup_preview()
            state.bones = {}
            if not state.model_path then
                set_status("Select a model by right-clicking an NPC, ragdoll, or player.")
                populate_bones()
                return
            end
            local model = ClientsideModel(state.model_path, RENDERGROUP_OTHER)
            if not IsValid(model) then
                set_status(string.format(L("Could not inspect model: %s"), state.model_path))
                populate_bones()
                return
            end
            model:SetNoDraw(true)
            state.preview = model
            local boneCount = model:GetBoneCount() or 0
            for index = 0, math.max(boneCount - 1, -1) do
                state.bones[#state.bones + 1] = {
                    index = index,
                    name = tostring(model:GetBoneName(index) or ("bone_" .. index)),
                }
            end
            populate_bones()
            set_status("Loaded repair settings.")
        end

        local function load_model_path(modelPath)
            modelPath = DynamicModelImporter.NormalizeOverrideModelPath(modelPath)
            if not modelPath then return end
            state.model_path = modelPath
            state.override = copy_model_override((DynamicModelImporter.LastModelOverrides or {})[modelPath])
            RunConsoleCommand("dynamic_model_importer_jigglebone_model_path", modelPath)
            request_override(modelPath)
            inspect_model()
        end

        local function save_current()
            if not state.model_path then
                set_status("Select a model by right-clicking an NPC, ragdoll, or player.")
                return
            end
            state.override = DynamicModelImporter.SanitizeModelOverride(state.override)
            save_override(state.model_path, state.override)
            populate_bones()
        end

        disableBoneButton.DoClick = function()
            local line = selected_list_line(boneList)
            if not line or not line.BoneName then
                set_status("No bone selected.")
                return
            end
            if not state.override.no_jiggle.all then
                state.override.no_jiggle.bones[line.BoneName] = true
            end
            save_current()
        end

        restoreBoneButton.DoClick = function()
            local line = selected_list_line(boneList)
            if not line or not line.BoneName then
                set_status("No bone selected.")
                return
            end
            if state.override.no_jiggle.all then
                state.override.no_jiggle.all = false
                state.override.no_jiggle.bones = {}
                for _, boneInfo in ipairs(state.bones) do
                    if boneInfo.name ~= line.BoneName then
                        state.override.no_jiggle.bones[boneInfo.name] = true
                    end
                end
            else
                state.override.no_jiggle.bones[line.BoneName] = nil
            end
            save_current()
        end

        disableAllButton.DoClick = function()
            state.override.no_jiggle.all = true
            state.override.no_jiggle.bones = {}
            save_current()
        end

        restoreAllButton.DoClick = function()
            state.override.no_jiggle.all = false
            state.override.no_jiggle.bones = {}
            save_current()
        end

        local targetHookID = "DynamicModelImporterJiggleboneTarget_" .. tostring(panel)
        hook.Add("DynamicModelImporterJiggleboneTargetSelected", targetHookID, load_model_path)

        local overrideHookID = "DynamicModelImporterJiggleboneOverride_" .. tostring(panel)
        hook.Add("DynamicModelImporterOverrideUpdated", overrideHookID, function(modelPath, override)
            if DynamicModelImporter.NormalizeOverrideModelPath(modelPath) ~= state.model_path then return end
            state.override = copy_model_override(override)
            populate_bones()
            set_status("Loaded repair settings.")
        end)

        panel.OnRemove = function()
            cleanup_preview()
            hook.Remove("DynamicModelImporterJiggleboneTargetSelected", targetHookID)
            hook.Remove("DynamicModelImporterOverrideUpdated", overrideHookID)
        end

        timer.Simple(0, function()
            if IsValid(panel) and state.model_path then
                load_model_path(state.model_path)
            else
                set_status("Select a model by right-clicking an NPC, ragdoll, or player.")
            end
        end)
    end
end
