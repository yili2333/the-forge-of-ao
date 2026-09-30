using System.IO;
using UnityEngine;

public static class CharacterSaveService
{
    private static string SavePath
    {
        get { return Path.Combine(Application.persistentDataPath, "characters.json"); }
    }

    public static CharacterDatabase Load()
    {
        if (!File.Exists(SavePath))
        {
            CharacterDatabase defaultDatabase = CreateDefaultDatabase();
            Save(defaultDatabase);
            return defaultDatabase;
        }

        string json = File.ReadAllText(SavePath);
        if (string.IsNullOrWhiteSpace(json))
        {
            CharacterDatabase emptyDatabase = CreateDefaultDatabase();
            Save(emptyDatabase);
            return emptyDatabase;
        }

        CharacterDatabase database = JsonUtility.FromJson<CharacterDatabase>(json);
        if (database == null || database.characters == null)
        {
            database = CreateDefaultDatabase();
            Save(database);
        }

        for (int i = 0; i < database.characters.Count; i++)
        {
            CharacterData character = database.characters[i];
            if (character == null)
            {
                continue;
            }

            if (character.maxHp <= 0)
            {
                character.maxHp = character.hp > 0 ? character.hp : 10;
            }
            if (character.constitution <= 0)
            {
                character.constitution = 10;
            }
            if (character.wisdom <= 0)
            {
                character.wisdom = 10;
            }
            if (character.charisma <= 0)
            {
                character.charisma = 10;
            }
            if (character.speedWalk <= 0)
            {
                character.speedWalk = 30;
            }
            if (string.IsNullOrWhiteSpace(character.species))
            {
                character.species = "Human";
            }
            if (string.IsNullOrWhiteSpace(character.background))
            {
                character.background = "Adventurer";
            }
            if (string.IsNullOrWhiteSpace(character.buildMethod))
            {
                character.buildMethod = "standard_array";
            }
            if (string.IsNullOrWhiteSpace(character.edition))
            {
                character.edition = "2024";
            }
        }

        return database;
    }

    public static void Save(CharacterDatabase database)
    {
        string json = JsonUtility.ToJson(database, true);
        File.WriteAllText(SavePath, json);
    }

    private static CharacterDatabase CreateDefaultDatabase()
    {
        CharacterDatabase database = new CharacterDatabase();

        database.characters.Add(new CharacterData
        {
            id = "char_local_001",
            characterName = "Aldric",
            characterClass = "Paladin",
            subclass = "Oath of Devotion",
            level = 3,
            hp = 28,
            maxHp = 28,
            mp = 3,
            strength = 16,
            dexterity = 10,
            constitution = 14,
            intelligence = 8,
            wisdom = 12,
            charisma = 15,
            speedWalk = 30,
            species = "Human",
            background = "Soldier",
            alignment = "Lawful Good",
            buildMethod = "standard_array",
            edition = "2024",
            skills = "athletics: proficient, persuasion: proficient, insight: proficient",
            savingThrows = "wisdom, charisma",
            languages = "Common, Celestial",
            inventory = "Longsword|weapon|1|equipped\nShield|shield|1|equipped\nChain Mail|armor|1|equipped|16\nPotion of Healing|consumable|2",
            currency = "gp: 25, sp: 4, cp: 0",
            spellcastingAbility = "charisma",
            preparedSpells = "1|Paladin|Bless\n1|Paladin|Shield of Faith",
            notes = "Frontline defender."
        });

        database.characters.Add(new CharacterData
        {
            id = "char_local_002",
            characterName = "Mira",
            characterClass = "Wizard",
            subclass = "Evocation",
            level = 2,
            hp = 16,
            maxHp = 16,
            mp = 4,
            strength = 8,
            dexterity = 14,
            constitution = 12,
            intelligence = 17,
            wisdom = 13,
            charisma = 10,
            speedWalk = 30,
            species = "Elf",
            background = "Sage",
            alignment = "Neutral Good",
            buildMethod = "standard_array",
            edition = "2024",
            skills = "arcana: proficient, investigation: proficient, history: proficient",
            savingThrows = "intelligence, wisdom",
            languages = "Common, Elvish, Draconic",
            inventory = "Quarterstaff|weapon|1|equipped\nSpellbook|gear|1\nComponent Pouch|gear|1\nPotion of Healing|consumable|1",
            currency = "gp: 18, sp: 7, cp: 0",
            spellcastingAbility = "intelligence",
            preparedSpells = "0|Wizard|Light\n1|Wizard|Magic Missile\n1|Wizard|Shield\n1|Wizard|Detect Magic",
            notes = "Backline blaster and utility caster."
        });

        return database;
    }
}
