using TMPro;
using UnityEngine;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public class CharacterEditorUIController : MonoBehaviour
{
    [Header("Basic Inputs")]
    public TMP_InputField nameInput;
    public TMP_InputField classInput;
    public TMP_InputField levelInput;
    public TMP_InputField hpInput;
    public TMP_InputField mpInput;

    [Header("Attribute Inputs")]
    public TMP_InputField strengthInput;
    public TMP_InputField dexterityInput;
    public TMP_InputField intelligenceInput;

    [Header("Text Inputs")]
    public TMP_InputField skillsInput;
    public TMP_InputField inventoryInput;

    [Header("Advanced Inputs")]
    public TMP_InputField maxHpInput;
    public TMP_InputField subclassInput;
    public TMP_InputField constitutionInput;
    public TMP_InputField wisdomInput;
    public TMP_InputField charismaInput;
    public TMP_InputField speciesInput;
    public TMP_InputField backgroundInput;
    public TMP_InputField alignmentInput;
    public TMP_InputField walkSpeedInput;
    public TMP_InputField editionInput;
    public TMP_InputField buildMethodInput;
    public TMP_InputField spellcastingAbilityInput;
    public TMP_InputField conditionsInput;
    public TMP_InputField languagesInput;
    public TMP_InputField toolProficienciesInput;
    public TMP_InputField currencyInput;

    [Header("Buttons")]
    public Button saveButton;
    public Button cancelButton;

    private CharacterDatabase database;
    private CharacterData editingCharacter;
    private bool isNewCharacter;

    private RectTransform advancedPanelRect;
    private RectTransform advancedContentRect;

    private void Start()
    {
        AutoBindReferences();
        EnsureAdvancedPanel();
        BindButtons();

        database = CharacterSaveService.Load();

        if (CharacterEditorContext.isEditing && !string.IsNullOrEmpty(CharacterEditorContext.editingCharacterId))
        {
            editingCharacter = database.characters.Find(c => c.id == CharacterEditorContext.editingCharacterId);
            isNewCharacter = editingCharacter == null;
        }
        else
        {
            isNewCharacter = true;
        }

        if (editingCharacter == null)
        {
            CreateNewCharacter();
        }

        if (editingCharacter != null)
        {
            editingCharacter.NormalizeCompatibilityFields();
        }

        LoadCharacterToInputs();
    }

    private void AutoBindReferences()
    {
        if (nameInput == null) nameInput = FindInputField("NameInput");
        if (classInput == null) classInput = FindInputField("ClassInput");
        if (levelInput == null) levelInput = FindInputField("LevelInput");
        if (hpInput == null) hpInput = FindInputField("HPInput");
        if (mpInput == null) mpInput = FindInputField("MPInput");
        if (strengthInput == null) strengthInput = FindInputField("StrengthInput");
        if (dexterityInput == null) dexterityInput = FindInputField("DexterityInput");
        if (intelligenceInput == null) intelligenceInput = FindInputField("IntelligenceInput");
        if (skillsInput == null) skillsInput = FindInputField("SkillsInput");
        if (inventoryInput == null) inventoryInput = FindInputField("InventoryInput");
        if (saveButton == null) saveButton = FindButton("SaveButton");
        if (cancelButton == null) cancelButton = FindButton("CancelButton");
    }

    private void BindButtons()
    {
        BindButton(saveButton, SaveCharacter);
        BindButton(cancelButton, CancelCharacter);
    }

    private void BindButton(Button button, UnityEngine.Events.UnityAction action)
    {
        if (button == null) return;
        button.onClick.RemoveAllListeners();
        button.onClick.AddListener(action);
    }

    private void CreateNewCharacter()
    {
        editingCharacter = new CharacterData
        {
            id = System.Guid.NewGuid().ToString(),
            characterName = "New Hero",
            characterClass = "Fighter",
            subclass = "Champion",
            level = 1,
            hp = 20,
            maxHp = 20,
            mp = 5,
            strength = 12,
            dexterity = 10,
            constitution = 10,
            intelligence = 8,
            wisdom = 10,
            charisma = 10,
            species = "Human",
            backgroundName = "Adventurer",
            background = "Adventurer",
            alignment = "Neutral Good",
            walkSpeed = 30,
            speedWalk = 30,
            edition = "2024",
            buildMethod = "standard_array",
            spellcastingAbility = string.Empty,
            conditions = string.Empty,
            languages = string.Empty,
            toolProficiencies = string.Empty,
            currencySummary = string.Empty,
            currency = string.Empty,
            skills = string.Empty,
            inventory = string.Empty
        };
    }

    private void LoadCharacterToInputs()
    {
        if (editingCharacter == null) return;

        SetText(nameInput, editingCharacter.characterName);
        SetText(classInput, editingCharacter.characterClass);
        SetText(levelInput, editingCharacter.level.ToString());
        SetText(hpInput, editingCharacter.hp.ToString());
        SetText(mpInput, editingCharacter.mp.ToString());
        SetText(strengthInput, editingCharacter.strength.ToString());
        SetText(dexterityInput, editingCharacter.dexterity.ToString());
        SetText(intelligenceInput, editingCharacter.intelligence.ToString());
        SetText(skillsInput, editingCharacter.skills);
        SetText(inventoryInput, editingCharacter.inventory);

        SetText(maxHpInput, editingCharacter.MaxHpSafe.ToString());
        SetText(subclassInput, editingCharacter.subclass);
        SetText(constitutionInput, ToDefaultStat(editingCharacter.constitution).ToString());
        SetText(wisdomInput, ToDefaultStat(editingCharacter.wisdom).ToString());
        SetText(charismaInput, ToDefaultStat(editingCharacter.charisma).ToString());
        SetText(speciesInput, editingCharacter.SpeciesSafe);
        SetText(backgroundInput, editingCharacter.BackgroundSafe);
        SetText(alignmentInput, DefaultIfEmpty(editingCharacter.alignment, "Neutral Good"));
        SetText(walkSpeedInput, editingCharacter.SpeedSafe.ToString());
        SetText(editionInput, editingCharacter.EditionSafe);
        SetText(buildMethodInput, editingCharacter.BuildMethodSafe);
        SetText(spellcastingAbilityInput, editingCharacter.spellcastingAbility);
        SetText(conditionsInput, editingCharacter.conditions);
        SetText(languagesInput, editingCharacter.languages);
        SetText(toolProficienciesInput, editingCharacter.toolProficiencies);
        SetText(currencyInput, editingCharacter.CurrencySafe);
    }

    public void SaveCharacter()
    {
        if (editingCharacter == null) return;

        editingCharacter.characterName = GetTextOrDefault(nameInput, "New Hero");
        editingCharacter.characterClass = GetTextOrDefault(classInput, "Fighter");
        editingCharacter.level = ParseInt(levelInput, 1);
        editingCharacter.hp = ParseInt(hpInput, 20);
        editingCharacter.mp = ParseInt(mpInput, 5);
        editingCharacter.strength = ParseStat(strengthInput, 10);
        editingCharacter.dexterity = ParseStat(dexterityInput, 10);
        editingCharacter.intelligence = ParseStat(intelligenceInput, 10);
        editingCharacter.skills = GetRawText(skillsInput);
        editingCharacter.inventory = GetRawText(inventoryInput);

        editingCharacter.maxHp = ParseInt(maxHpInput, editingCharacter.hp);
        editingCharacter.subclass = GetRawText(subclassInput);
        editingCharacter.constitution = ParseStat(constitutionInput, 10);
        editingCharacter.wisdom = ParseStat(wisdomInput, 10);
        editingCharacter.charisma = ParseStat(charismaInput, 10);
        editingCharacter.species = GetTextOrDefault(speciesInput, "Human");
        editingCharacter.backgroundName = GetTextOrDefault(backgroundInput, "Adventurer");
        editingCharacter.background = editingCharacter.backgroundName;
        editingCharacter.alignment = GetTextOrDefault(alignmentInput, "Neutral Good");
        editingCharacter.walkSpeed = ParseInt(walkSpeedInput, 30);
        editingCharacter.speedWalk = editingCharacter.walkSpeed;
        editingCharacter.edition = NormalizeEdition(GetTextOrDefault(editionInput, "2024"));
        editingCharacter.buildMethod = GetTextOrDefault(buildMethodInput, "standard_array");
        editingCharacter.spellcastingAbility = NormalizeAbilityName(GetRawText(spellcastingAbilityInput));
        editingCharacter.conditions = GetRawText(conditionsInput);
        editingCharacter.languages = GetRawText(languagesInput);
        editingCharacter.toolProficiencies = GetRawText(toolProficienciesInput);
        editingCharacter.currencySummary = GetRawText(currencyInput);
        editingCharacter.currency = editingCharacter.currencySummary;

        editingCharacter.NormalizeCompatibilityFields();

        if (isNewCharacter)
        {
            database.characters.Add(editingCharacter);
        }

        CharacterSaveService.Save(database);
        ResetEditorContext();
        SceneManager.LoadScene("CharacterVaultScene");
    }

    public void CancelCharacter()
    {
        ResetEditorContext();
        SceneManager.LoadScene("CharacterVaultScene");
    }

    private void EnsureAdvancedPanel()
    {
        if (maxHpInput != null && subclassInput != null && conditionsInput != null)
        {
            return;
        }

        Canvas canvas = GetComponentInParent<Canvas>();
        if (canvas == null) canvas = FindFirstObjectByType<Canvas>(FindObjectsInactive.Include);
        if (canvas == null || nameInput == null) return;

        GameObject existing = GameObject.Find("AdvancedCharacterFieldsPanel");
        if (existing != null)
        {
            Destroy(existing);
        }

        GameObject panelObject = new GameObject("AdvancedCharacterFieldsPanel", typeof(RectTransform), typeof(Image));
        panelObject.transform.SetParent(canvas.transform, false);
        advancedPanelRect = panelObject.GetComponent<RectTransform>();
        advancedPanelRect.anchorMin = new Vector2(1f, 1f);
        advancedPanelRect.anchorMax = new Vector2(1f, 1f);
        advancedPanelRect.pivot = new Vector2(1f, 1f);
        advancedPanelRect.sizeDelta = new Vector2(360f, 640f);
        advancedPanelRect.anchoredPosition = new Vector2(-22f, -95f);
        panelObject.GetComponent<Image>().color = new Color(0.17f, 0.18f, 0.24f, 0.96f);

        CreateStaticLabel(advancedPanelRect, "Advanced Character Fields", new Vector2(14f, -12f), 15f, FontStyles.Bold);
        CreateStaticLabel(advancedPanelRect, "Use mouse wheel to scroll", new Vector2(14f, -33f), 10.5f, FontStyles.Normal, new Color(0.84f, 0.87f, 0.93f, 0.95f));

        GameObject viewportObject = new GameObject("Viewport", typeof(RectTransform), typeof(Image), typeof(Mask));
        viewportObject.transform.SetParent(advancedPanelRect, false);
        RectTransform viewportRect = viewportObject.GetComponent<RectTransform>();
        viewportRect.anchorMin = new Vector2(0f, 0f);
        viewportRect.anchorMax = new Vector2(1f, 1f);
        viewportRect.offsetMin = new Vector2(10f, 12f);
        viewportRect.offsetMax = new Vector2(-10f, -52f);
        Image viewportImage = viewportObject.GetComponent<Image>();
        viewportImage.color = new Color(1f, 1f, 1f, 0.02f);
        viewportObject.GetComponent<Mask>().showMaskGraphic = false;

        GameObject contentObject = new GameObject("Content", typeof(RectTransform));
        contentObject.transform.SetParent(viewportObject.transform, false);
        advancedContentRect = contentObject.GetComponent<RectTransform>();
        advancedContentRect.anchorMin = new Vector2(0f, 1f);
        advancedContentRect.anchorMax = new Vector2(1f, 1f);
        advancedContentRect.pivot = new Vector2(0.5f, 1f);
        advancedContentRect.offsetMin = new Vector2(0f, 0f);
        advancedContentRect.offsetMax = new Vector2(0f, 0f);

        ScrollRect scrollRect = panelObject.AddComponent<ScrollRect>();
        scrollRect.viewport = viewportRect;
        scrollRect.content = advancedContentRect;
        scrollRect.horizontal = false;
        scrollRect.vertical = true;
        scrollRect.scrollSensitivity = 26f;
        scrollRect.movementType = ScrollRect.MovementType.Clamped;

        float y = -6f;
        maxHpInput = CreateAdvancedField("Max HP", ref y, nameInput, "20");
        subclassInput = CreateAdvancedField("Subclass", ref y, nameInput, "Champion");
        constitutionInput = CreateAdvancedField("Constitution", ref y, nameInput, "10");
        wisdomInput = CreateAdvancedField("Wisdom", ref y, nameInput, "10");
        charismaInput = CreateAdvancedField("Charisma", ref y, nameInput, "10");
        speciesInput = CreateAdvancedField("Species", ref y, nameInput, "Human");
        backgroundInput = CreateAdvancedField("Background", ref y, nameInput, "Adventurer");
        alignmentInput = CreateAdvancedField("Alignment", ref y, nameInput, "Neutral Good");
        walkSpeedInput = CreateAdvancedField("Walk Speed", ref y, nameInput, "30");
        editionInput = CreateAdvancedField("Edition", ref y, nameInput, "2024");
        buildMethodInput = CreateAdvancedField("Build Method", ref y, nameInput, "standard_array");
        spellcastingAbilityInput = CreateAdvancedField("Spellcasting Ability", ref y, nameInput, "wisdom");
        conditionsInput = CreateAdvancedField("Conditions", ref y, skillsInput != null ? skillsInput : nameInput, "poisoned, exhausted", 92f);
        languagesInput = CreateAdvancedField("Languages", ref y, skillsInput != null ? skillsInput : nameInput, "Common, Elvish", 92f);
        toolProficienciesInput = CreateAdvancedField("Tool Proficiencies", ref y, skillsInput != null ? skillsInput : nameInput, "Herbalism kit", 92f);
        currencyInput = CreateAdvancedField("Currency", ref y, nameInput, "gp:10, sp:5");

        advancedContentRect.sizeDelta = new Vector2(0f, -y + 8f);
    }

    private TMP_InputField CreateAdvancedField(string label, ref float y, TMP_InputField template, string placeholder, float height = 44f)
    {
        CreateStaticLabel(advancedContentRect, label, new Vector2(4f, y), 13f, FontStyles.Bold);
        y -= 24f;

        TMP_InputField field = Instantiate(template, advancedContentRect);
        field.name = label.Replace(" ", string.Empty) + "Input";
        RectTransform fieldRect = field.GetComponent<RectTransform>();
        fieldRect.anchorMin = new Vector2(0f, 1f);
        fieldRect.anchorMax = new Vector2(1f, 1f);
        fieldRect.pivot = new Vector2(0.5f, 1f);
        fieldRect.anchoredPosition = new Vector2(0f, y);
        fieldRect.sizeDelta = new Vector2(-8f, height);

        TMP_Text textComponent = field.textComponent;
        if (textComponent != null)
        {
            textComponent.text = string.Empty;
            textComponent.fontSize = Mathf.Max(20f, textComponent.fontSize);
            textComponent.enableWordWrapping = height > 60f;
            textComponent.alignment = TextAlignmentOptions.TopLeft;
            RectTransform textRect = textComponent.GetComponent<RectTransform>();
            if (textRect != null)
            {
                textRect.offsetMin = new Vector2(10f, 8f);
                textRect.offsetMax = new Vector2(-10f, -8f);
            }
        }

        if (field.placeholder is TMP_Text placeholderText)
        {
            placeholderText.text = placeholder;
            placeholderText.fontSize = textComponent != null ? textComponent.fontSize : 20f;
            placeholderText.enableWordWrapping = height > 60f;
            placeholderText.alignment = TextAlignmentOptions.TopLeft;
            RectTransform placeholderRect = placeholderText.GetComponent<RectTransform>();
            if (placeholderRect != null)
            {
                placeholderRect.offsetMin = new Vector2(10f, 8f);
                placeholderRect.offsetMax = new Vector2(-10f, -8f);
            }
        }

        field.lineType = height > 60f ? TMP_InputField.LineType.MultiLineNewline : TMP_InputField.LineType.SingleLine;
        field.characterLimit = 0;
        field.verticalScrollbar = null;
        field.text = string.Empty;

        y -= height + 12f;
        return field;
    }

    private TMP_Text CreateStaticLabel(Transform parent, string text, Vector2 anchoredTopLeft, float fontSize, FontStyles style, Color? color = null)
    {
        GameObject go = new GameObject(text.Replace(" ", string.Empty) + "Label", typeof(RectTransform), typeof(TextMeshProUGUI));
        go.transform.SetParent(parent, false);
        RectTransform rect = go.GetComponent<RectTransform>();
        rect.anchorMin = new Vector2(0f, 1f);
        rect.anchorMax = new Vector2(0f, 1f);
        rect.pivot = new Vector2(0f, 1f);
        rect.anchoredPosition = anchoredTopLeft;
        rect.sizeDelta = new Vector2(320f, 22f);

        TMP_Text tmp = go.GetComponent<TMP_Text>();
        tmp.text = text;
        tmp.fontSize = fontSize;
        tmp.fontStyle = style;
        tmp.color = color ?? Color.white;
        tmp.alignment = TextAlignmentOptions.Left;
        tmp.enableWordWrapping = false;
        return tmp;
    }

    private TMP_InputField FindInputField(string objectName)
    {
        TMP_InputField[] fields = GetComponentsInChildren<TMP_InputField>(true);
        for (int i = 0; i < fields.Length; i++)
        {
            if (fields[i].name == objectName)
            {
                return fields[i];
            }
        }
        return null;
    }

    private Button FindButton(string objectName)
    {
        Button[] buttons = GetComponentsInChildren<Button>(true);
        for (int i = 0; i < buttons.Length; i++)
        {
            if (buttons[i].name == objectName)
            {
                return buttons[i];
            }
        }
        return null;
    }

    private static void SetText(TMP_InputField field, string value)
    {
        if (field != null) field.text = value ?? string.Empty;
    }

    private static int ParseInt(TMP_InputField inputField, int fallbackValue)
    {
        if (inputField == null) return fallbackValue;
        int result;
        return int.TryParse(inputField.text, out result) ? result : fallbackValue;
    }

    private static int ParseStat(TMP_InputField inputField, int fallbackValue)
    {
        int value = ParseInt(inputField, fallbackValue);
        if (value < 1) return 1;
        if (value > 30) return 30;
        return value;
    }

    private static string GetTextOrDefault(TMP_InputField inputField, string fallbackValue)
    {
        string value = GetRawText(inputField);
        return string.IsNullOrWhiteSpace(value) ? fallbackValue : value;
    }

    private static string GetRawText(TMP_InputField inputField)
    {
        return inputField == null ? string.Empty : (inputField.text ?? string.Empty).Trim();
    }

    private static int ToDefaultStat(int value)
    {
        return value > 0 ? value : 10;
    }

    private static string DefaultIfEmpty(string value, string fallback)
    {
        return string.IsNullOrWhiteSpace(value) ? fallback : value;
    }

    private static string NormalizeEdition(string value)
    {
        if (string.IsNullOrWhiteSpace(value)) return "2024";
        string compact = value.Trim();
        if (compact.Contains("2014")) return "2014";
        return "2024";
    }

    private static string NormalizeAbilityName(string raw)
    {
        if (string.IsNullOrWhiteSpace(raw)) return string.Empty;
        string value = raw.Trim().ToLowerInvariant();
        if (value.StartsWith("str")) return "strength";
        if (value.StartsWith("dex")) return "dexterity";
        if (value.StartsWith("con")) return "constitution";
        if (value.StartsWith("int")) return "intelligence";
        if (value.StartsWith("wis")) return "wisdom";
        if (value.StartsWith("cha")) return "charisma";
        return value;
    }

    private void ResetEditorContext()
    {
        CharacterEditorContext.isEditing = false;
        CharacterEditorContext.editingCharacterId = null;
    }
}
