using System.Collections.Generic;
using System.Globalization;
using System.Text;

public static class CharacterSheetPayloadBuilder
{
    public static string Build(CharacterData character, string campaignId, string ownerId)
    {
        if (character == null)
        {
            return "{}";
        }

        StringBuilder sb = new StringBuilder();
        sb.Append("{");

        bool wrote = false;
        if (!string.IsNullOrWhiteSpace(character.id) && !IsLocalOnlyId(character.id))
        {
            AppendStringField(sb, ref wrote, "id", character.id);
        }

        AppendStringField(sb, ref wrote, "name", DefaultIfEmpty(character.characterName, "New Hero"));
        AppendStringField(sb, ref wrote, "owner_id", DefaultIfEmpty(ownerId, "player-001"));
        AppendStringField(sb, ref wrote, "owner_display", DefaultIfEmpty(ownerId, "player-001"));
        AppendStringField(sb, ref wrote, "campaign_id", DefaultIfEmpty(campaignId, "campaign-001"));
        AppendStringField(sb, ref wrote, "edition", NormalizeEdition(character.edition));
        AppendBoolField(sb, ref wrote, "non_standard", character.nonStandard);
        AppendBoolField(sb, ref wrote, "dm_approved", character.dmApproved);
        AppendStringField(sb, ref wrote, "alignment", character.alignment);

        AppendObjectField(sb, ref wrote, "species", BuildSpecies(character));
        AppendObjectField(sb, ref wrote, "background", BuildBackground(character));
        AppendArrayField(sb, ref wrote, "class_levels", BuildClassLevels(character));
        AppendObjectField(sb, ref wrote, "ability_scores", BuildAbilityScores(character));
        AppendObjectField(sb, ref wrote, "hit_points", BuildHitPoints(character));
        AppendObjectField(sb, ref wrote, "speed", BuildSpeed(character));
        AppendIntField(sb, ref wrote, "armor_class_cache", 10 + AbilityModifier(DefaultStat(character.dexterity)));
        AppendIntField(sb, ref wrote, "proficiency_bonus", GuessProficiencyBonus(character.level));
        AppendObjectField(sb, ref wrote, "skills", BuildSkills(character.skills));
        AppendObjectField(sb, ref wrote, "saving_throws", BuildSavingThrows(character));
        AppendArrayField(sb, ref wrote, "inventory", BuildInventory(character.inventory));
        AppendArrayField(sb, ref wrote, "conditions", BuildStringArray(character.conditions));
        AppendArrayField(sb, ref wrote, "prepared_spells", BuildStringArray(character.preparedSpells));
        AppendObjectField(sb, ref wrote, "currency", BuildCurrency(character.currencySummary));
        AppendObjectField(sb, ref wrote, "spell_slots", "{\"slots\":{},\"pact_slots\":{\"current\":0,\"maximum\":0},\"pact_level\":0}");

        if (!string.IsNullOrWhiteSpace(character.spellcastingAbility))
        {
            AppendStringField(sb, ref wrote, "spellcasting_ability", NormalizeAbilityName(character.spellcastingAbility));
        }

        sb.Append("}");
        return sb.ToString();
    }

    private static string BuildSpecies(CharacterData character)
    {
        return "{\"name\":\"" + Escape(DefaultIfEmpty(character.species, "Human")) + "\",\"traits\":[]}";
    }

    private static string BuildBackground(CharacterData character)
    {
        return "{\"name\":\"" + Escape(DefaultIfEmpty(character.backgroundName, "Adventurer")) + "\",\"feature\":\"Ready for play\"}";
    }

    private static string BuildClassLevels(CharacterData character)
    {
        StringBuilder sb = new StringBuilder();
        sb.Append("[");
        sb.Append("{");
        AppendString(sb, "class_name", DefaultIfEmpty(character.characterClass, "Fighter")); sb.Append(',');
        AppendInt(sb, "level", character.level <= 0 ? 1 : character.level); sb.Append(',');
        AppendString(sb, "subclass", character.subclass); sb.Append(',');
        AppendBool(sb, "is_primary", true);
        sb.Append("}");
        sb.Append("]");
        return sb.ToString();
    }

    private static string BuildAbilityScores(CharacterData character)
    {
        StringBuilder sb = new StringBuilder();
        sb.Append("{");
        AppendInt(sb, "strength", DefaultStat(character.strength)); sb.Append(',');
        AppendInt(sb, "dexterity", DefaultStat(character.dexterity)); sb.Append(',');
        AppendInt(sb, "constitution", DefaultStat(character.constitution)); sb.Append(',');
        AppendInt(sb, "intelligence", DefaultStat(character.intelligence)); sb.Append(',');
        AppendInt(sb, "wisdom", DefaultStat(character.wisdom)); sb.Append(',');
        AppendInt(sb, "charisma", DefaultStat(character.charisma));
        sb.Append("}");
        return sb.ToString();
    }

    private static string BuildHitPoints(CharacterData character)
    {
        int current = character.hp <= 0 ? 1 : character.hp;
        int maximum = character.EffectiveMaxHp <= 0 ? current : character.EffectiveMaxHp;
        StringBuilder sb = new StringBuilder();
        sb.Append("{");
        AppendInt(sb, "current", current); sb.Append(',');
        AppendInt(sb, "maximum", maximum); sb.Append(',');
        AppendInt(sb, "hit_dice_total", character.level <= 0 ? 1 : character.level); sb.Append(',');
        AppendInt(sb, "hit_dice_used", 0);
        sb.Append("}");
        return sb.ToString();
    }

    private static string BuildSpeed(CharacterData character)
    {
        int walk = character.walkSpeed <= 0 ? 30 : character.walkSpeed;
        return "{\"walk\":" + walk + ",\"fly\":0,\"swim\":0,\"climb\":0,\"burrow\":0,\"temp_modifier\":0}";
    }

    private static string BuildSkills(string rawSkills)
    {
        string[] keys = new string[]
        {
            "acrobatics","animal_handling","arcana","athletics","deception","history","insight","intimidation",
            "investigation","medicine","nature","perception","performance","persuasion","religion","sleight_of_hand","stealth","survival"
        };

        StringBuilder sb = new StringBuilder();
        sb.Append('{');
        for (int i = 0; i < keys.Length; i++)
        {
            if (i > 0) sb.Append(',');
            AppendString(sb, keys[i], GuessSkillLevel(rawSkills, keys[i]));
        }
        sb.Append('}');
        return sb.ToString();
    }

    private static string BuildSavingThrows(CharacterData character)
    {
        StringBuilder sb = new StringBuilder();
        sb.Append('{');
        AppendString(sb, "strength", DefaultStat(character.strength) >= 14 ? "proficient" : "untrained"); sb.Append(',');
        AppendString(sb, "dexterity", DefaultStat(character.dexterity) >= 14 ? "proficient" : "untrained"); sb.Append(',');
        AppendString(sb, "constitution", DefaultStat(character.constitution) >= 14 ? "proficient" : "untrained"); sb.Append(',');
        AppendString(sb, "intelligence", DefaultStat(character.intelligence) >= 14 ? "proficient" : "untrained"); sb.Append(',');
        AppendString(sb, "wisdom", DefaultStat(character.wisdom) >= 14 ? "proficient" : "untrained"); sb.Append(',');
        AppendString(sb, "charisma", DefaultStat(character.charisma) >= 14 ? "proficient" : "untrained");
        sb.Append('}');
        return sb.ToString();
    }

    private static string BuildInventory(string rawInventory)
    {
        List<string> items = SplitCommaSeparated(rawInventory);
        StringBuilder sb = new StringBuilder();
        sb.Append('[');
        for (int i = 0; i < items.Count; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append('{');
            AppendString(sb, "name", items[i]); sb.Append(',');
            AppendInt(sb, "quantity", 1); sb.Append(',');
            AppendBool(sb, "equipped", false);
            sb.Append('}');
        }
        sb.Append(']');
        return sb.ToString();
    }

    private static string BuildStringArray(string raw)
    {
        List<string> items = SplitCommaSeparated(raw);
        StringBuilder sb = new StringBuilder();
        sb.Append('[');
        for (int i = 0; i < items.Count; i++)
        {
            if (i > 0) sb.Append(',');
            sb.Append('"').Append(Escape(items[i])).Append('"');
        }
        sb.Append(']');
        return sb.ToString();
    }

    private static string BuildCurrency(string raw)
    {
        float gold = 0f;
        float silver = 0f;
        float copper = 0f;
        float platinum = 0f;
        float electrum = 0f;

        if (!string.IsNullOrWhiteSpace(raw))
        {
            string[] parts = raw.Split(',');
            for (int i = 0; i < parts.Length; i++)
            {
                string item = parts[i].Trim().ToLowerInvariant();
                if (item.Length == 0) continue;
                if (item.EndsWith("gp")) gold = ParseCurrencyNumber(item, "gp");
                else if (item.EndsWith("sp")) silver = ParseCurrencyNumber(item, "sp");
                else if (item.EndsWith("cp")) copper = ParseCurrencyNumber(item, "cp");
                else if (item.EndsWith("pp")) platinum = ParseCurrencyNumber(item, "pp");
                else if (item.EndsWith("ep")) electrum = ParseCurrencyNumber(item, "ep");
            }
        }

        return "{\"gold\":" + gold.ToString(CultureInfo.InvariantCulture) + ",\"silver\":" + silver.ToString(CultureInfo.InvariantCulture) + ",\"copper\":" + copper.ToString(CultureInfo.InvariantCulture) + ",\"platinum\":" + platinum.ToString(CultureInfo.InvariantCulture) + ",\"electrum\":" + electrum.ToString(CultureInfo.InvariantCulture) + "}";
    }

    private static float ParseCurrencyNumber(string raw, string suffix)
    {
        float value;
        string number = raw.Replace(suffix, string.Empty).Trim();
        return float.TryParse(number, NumberStyles.Float, CultureInfo.InvariantCulture, out value) ? value : 0f;
    }

    private static List<string> SplitCommaSeparated(string raw)
    {
        List<string> values = new List<string>();
        if (string.IsNullOrWhiteSpace(raw)) return values;
        string[] parts = raw.Split(',');
        for (int i = 0; i < parts.Length; i++)
        {
            string item = parts[i].Trim();
            if (item.Length > 0) values.Add(item);
        }
        return values;
    }

    private static int GuessProficiencyBonus(int level)
    {
        if (level >= 17) return 6;
        if (level >= 13) return 5;
        if (level >= 9) return 4;
        if (level >= 5) return 3;
        return 2;
    }

    private static string GuessSkillLevel(string rawSkills, string key)
    {
        if (string.IsNullOrWhiteSpace(rawSkills)) return "untrained";
        string normalized = rawSkills.ToLowerInvariant();
        return normalized.Contains(key.Replace('_', ' ')) || normalized.Contains(key) ? "proficient" : "untrained";
    }

    private static int DefaultStat(int value)
    {
        if (value <= 0) return 10;
        if (value > 20) return 20;
        return value;
    }

    private static int AbilityModifier(int score)
    {
        return (score - 10) / 2;
    }

    private static string NormalizeEdition(string raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return "2024";
        string value = raw.Trim().ToLowerInvariant();
        if (value.Contains("2014")) return "2014";
        return "2024";
    }

    private static string NormalizeAbilityName(string raw)
    {
        string value = raw.Trim().ToLowerInvariant();
        if (value.StartsWith("str")) return "strength";
        if (value.StartsWith("dex")) return "dexterity";
        if (value.StartsWith("con")) return "constitution";
        if (value.StartsWith("int")) return "intelligence";
        if (value.StartsWith("wis")) return "wisdom";
        if (value.StartsWith("cha")) return "charisma";
        return value;
    }

    private static bool IsLocalOnlyId(string id)
    {
        if (string.IsNullOrWhiteSpace(id)) return true;
        return id.StartsWith("char_") || id.StartsWith("local-");
    }

    private static string DefaultIfEmpty(string value, string fallback)
    {
        return string.IsNullOrWhiteSpace(value) ? fallback : value.Trim();
    }

    private static void AppendStringField(StringBuilder sb, ref bool wrote, string key, string value)
    {
        if (wrote) sb.Append(',');
        AppendString(sb, key, value);
        wrote = true;
    }

    private static void AppendIntField(StringBuilder sb, ref bool wrote, string key, int value)
    {
        if (wrote) sb.Append(',');
        AppendInt(sb, key, value);
        wrote = true;
    }

    private static void AppendBoolField(StringBuilder sb, ref bool wrote, string key, bool value)
    {
        if (wrote) sb.Append(',');
        AppendBool(sb, key, value);
        wrote = true;
    }

    private static void AppendObjectField(StringBuilder sb, ref bool wrote, string key, string objectJson)
    {
        if (wrote) sb.Append(',');
        sb.Append('"').Append(Escape(key)).Append("\":").Append(objectJson);
        wrote = true;
    }

    private static void AppendArrayField(StringBuilder sb, ref bool wrote, string key, string arrayJson)
    {
        if (wrote) sb.Append(',');
        sb.Append('"').Append(Escape(key)).Append("\":").Append(arrayJson);
        wrote = true;
    }

    private static void AppendString(StringBuilder sb, string key, string value)
    {
        sb.Append('"').Append(Escape(key)).Append("\":\"").Append(Escape(value)).Append('"');
    }

    private static void AppendInt(StringBuilder sb, string key, int value)
    {
        sb.Append('"').Append(Escape(key)).Append("\":").Append(value);
    }

    private static void AppendBool(StringBuilder sb, string key, bool value)
    {
        sb.Append('"').Append(Escape(key)).Append("\":").Append(value ? "true" : "false");
    }

    public static string Escape(string value)
    {
        return (value ?? string.Empty)
            .Replace("\\", "\\\\")
            .Replace("\"", "\\\"")
            .Replace("\n", "\\n")
            .Replace("\r", string.Empty);
    }
}
