using System;
using System.Collections.Generic;
using System.Globalization;

[Serializable]
public class CharacterData
{
    public string id;
    public string characterName;
    public string characterClass;
    public string subclass;

    public int level;
    public int hp;
    public int maxHp;
    public int mp;

    public int strength;
    public int dexterity;
    public int constitution;
    public int intelligence;
    public int wisdom;
    public int charisma;

    // 兼容两套命名：旧版 speedWalk / 新版 walkSpeed
    public int speedWalk;
    public int walkSpeed;
    public int exhaustionLevel;

    public string species;
    public string speciesLineage;

    // 兼容两套命名：旧版 background / 新版 backgroundName
    public string background;
    public string backgroundName;

    public string alignment;
    public string buildMethod;
    public string edition;

    public string skills;
    public string savingThrows;
    public string languages;
    public string toolProficiencies;
    public string inventory;
    public string conditions;

    // 兼容两套命名：旧版 currency / 新版 currencySummary
    public string currency;
    public string currencySummary;

    public string spellcastingAbility;
    public string preparedSpells;
    public string notes;
    public string backstory;
    public string appearance;

    // 后端联调字段
    public string ownerId;
    public string ownerDisplay;
    public string campaignId;
    public bool dmApproved;
    public bool nonStandard;
    public bool syncedWithBackend;

    public int armorClass;
    public int passivePerception;
    public int passiveInvestigation;
    public int passiveInsight;
    public int initiativeBonus;
    public int speedEffective;
    public int spellSaveDc;
    public int spellAttackBonus;

    public string contextText;
    public string derivedSummary;

    // 兼容两套命名：旧版 spellStatsByClassSummary / 新版 spellStatsByClass
    public string spellStatsByClass;
    public string spellStatsByClassSummary;

    // 兼容两套命名：旧版 dmApprovalNote / 新版 approvalNote
    public string dmApprovalNote;
    public string approvalNote;

    public string updatedAt;

    public string DisplayName
    {
        get { return string.IsNullOrWhiteSpace(characterName) ? "Unnamed Character" : characterName; }
    }

    public string DisplayClass
    {
        get
        {
            string baseClass = string.IsNullOrWhiteSpace(characterClass) ? "Unknown Class" : characterClass;
            return string.IsNullOrWhiteSpace(subclass) ? baseClass : baseClass + " (" + subclass + ")";
        }
    }

    public int CurrentHpSafe
    {
        get { return hp > 0 ? hp : 1; }
    }

    public int MaxHpSafe
    {
        get
        {
            if (maxHp > 0) return maxHp;
            return hp > 0 ? hp : 1;
        }
    }

    public int EffectiveMaxHp
    {
        get { return MaxHpSafe; }
    }

    public int SpeedSafe
    {
        get
        {
            if (walkSpeed > 0) return walkSpeed;
            if (speedWalk > 0) return speedWalk;
            if (speedEffective > 0) return speedEffective;
            return 30;
        }
    }

    public string EditionSafe
    {
        get { return string.IsNullOrWhiteSpace(edition) ? "2024" : edition; }
    }

    public string BuildMethodSafe
    {
        get { return string.IsNullOrWhiteSpace(buildMethod) ? "standard_array" : buildMethod; }
    }

    public string SpeciesSafe
    {
        get { return string.IsNullOrWhiteSpace(species) ? "Human" : species; }
    }

    public string BackgroundSafe
    {
        get
        {
            if (!string.IsNullOrWhiteSpace(backgroundName)) return backgroundName;
            return string.IsNullOrWhiteSpace(background) ? "Adventurer" : background;
        }
    }

    public string CurrencySafe
    {
        get
        {
            if (!string.IsNullOrWhiteSpace(currencySummary)) return currencySummary;
            return currency ?? string.Empty;
        }
    }

    public string SpellStatsSafe
    {
        get
        {
            if (!string.IsNullOrWhiteSpace(spellStatsByClass)) return spellStatsByClass;
            return spellStatsByClassSummary ?? string.Empty;
        }
    }

    public string ApprovalNoteSafe
    {
        get
        {
            if (!string.IsNullOrWhiteSpace(approvalNote)) return approvalNote;
            return dmApprovalNote ?? string.Empty;
        }
    }

    public void NormalizeCompatibilityFields()
    {
        if (walkSpeed <= 0 && speedWalk > 0) walkSpeed = speedWalk;
        if (speedWalk <= 0 && walkSpeed > 0) speedWalk = walkSpeed;

        if (string.IsNullOrWhiteSpace(backgroundName) && !string.IsNullOrWhiteSpace(background)) backgroundName = background;
        if (string.IsNullOrWhiteSpace(background) && !string.IsNullOrWhiteSpace(backgroundName)) background = backgroundName;

        if (string.IsNullOrWhiteSpace(currencySummary) && !string.IsNullOrWhiteSpace(currency)) currencySummary = currency;
        if (string.IsNullOrWhiteSpace(currency) && !string.IsNullOrWhiteSpace(currencySummary)) currency = currencySummary;

        if (string.IsNullOrWhiteSpace(spellStatsByClass) && !string.IsNullOrWhiteSpace(spellStatsByClassSummary)) spellStatsByClass = spellStatsByClassSummary;
        if (string.IsNullOrWhiteSpace(spellStatsByClassSummary) && !string.IsNullOrWhiteSpace(spellStatsByClass)) spellStatsByClassSummary = spellStatsByClass;

        if (string.IsNullOrWhiteSpace(approvalNote) && !string.IsNullOrWhiteSpace(dmApprovalNote)) approvalNote = dmApprovalNote;
        if (string.IsNullOrWhiteSpace(dmApprovalNote) && !string.IsNullOrWhiteSpace(approvalNote)) dmApprovalNote = approvalNote;

        if (maxHp <= 0 && hp > 0) maxHp = hp;
        if (constitution <= 0) constitution = 10;
        if (wisdom <= 0) wisdom = 10;
        if (charisma <= 0) charisma = 10;
        if (walkSpeed <= 0 && speedWalk <= 0) { walkSpeed = 30; speedWalk = 30; }
        if (string.IsNullOrWhiteSpace(species)) species = "Human";
        if (string.IsNullOrWhiteSpace(backgroundName) && string.IsNullOrWhiteSpace(background))
        {
            backgroundName = "Adventurer";
            background = "Adventurer";
        }
        if (string.IsNullOrWhiteSpace(buildMethod)) buildMethod = "standard_array";
        if (string.IsNullOrWhiteSpace(edition)) edition = "2024";
    }

    public IEnumerable<string> SplitCsv(string raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) yield break;

        string[] parts = raw.Replace("\n", ",").Split(',');
        for (int i = 0; i < parts.Length; i++)
        {
            string value = parts[i] != null ? parts[i].Trim() : string.Empty;
            if (!string.IsNullOrWhiteSpace(value)) yield return value;
        }
    }

    public float GetCurrencyValue(string coin)
    {
        string rawCurrency = CurrencySafe;
        if (string.IsNullOrWhiteSpace(rawCurrency) || string.IsNullOrWhiteSpace(coin)) return 0f;

        string normalizedCoin = coin.Trim().ToLowerInvariant();
        string[] parts = rawCurrency.Replace("\n", ",").Split(',');
        for (int i = 0; i < parts.Length; i++)
        {
            string token = parts[i] != null ? parts[i].Trim() : string.Empty;
            if (string.IsNullOrWhiteSpace(token)) continue;

            int separator = token.IndexOf(':');
            if (separator <= 0) separator = token.IndexOf('=');

            string key;
            string valueText;
            if (separator > 0)
            {
                key = token.Substring(0, separator).Trim().ToLowerInvariant();
                valueText = token.Substring(separator + 1).Trim();
            }
            else
            {
                key = token.ToLowerInvariant();
                valueText = string.Empty;
                string digits = string.Empty;
                for (int c = 0; c < token.Length; c++)
                {
                    char ch = token[c];
                    if (char.IsDigit(ch) || ch == '.' || ch == '-') digits += ch;
                }
                if (key.Contains(normalizedCoin)) valueText = digits;
            }

            if (!key.Contains(normalizedCoin)) continue;

            float parsed;
            if (float.TryParse(valueText, NumberStyles.Float, CultureInfo.InvariantCulture, out parsed))
            {
                return parsed;
            }
        }

        return 0f;
    }
}
