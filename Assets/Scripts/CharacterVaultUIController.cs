using System.Collections.Generic;
using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public class CharacterVaultUIController : MonoBehaviour
{
    [Header("List")]
    public Transform characterListContent;
    public GameObject characterListItemPrefab;

    [Header("Detail")]
    public TMP_Text nameText;
    public TMP_Text classText;
    public TMP_Text levelText;
    public TMP_Text hpText;
    public TMP_Text mpText;
    public TMP_Text strengthText;
    public TMP_Text dexterityText;
    public TMP_Text intelligenceText;
    public TMP_Text skillsText;
    public TMP_Text inventoryText;

    [Header("Buttons")]
    public Button backButton;
    public Button createButton;
    public Button editButton;
    public Button deleteButton;
    public Button uploadButton;
    public Button refreshButton;

    private CharacterDatabase database;
    private CharacterData selectedCharacter;
    private readonly List<CharacterListItemUI> listItems = new List<CharacterListItemUI>();
    private readonly CharacterApiService characterApiService = new CharacterApiService();

    private TMP_Text advancedDetailText;

    private void Start()
    {
        AutoBindReferences();
        BindButtons();
        EnsureAdvancedDetailPanel();

        database = CharacterSaveService.Load();
        for (int i = 0; i < database.characters.Count; i++)
        {
            if (database.characters[i] != null)
            {
                database.characters[i].NormalizeCompatibilityFields();
            }
        }

        RefreshList();

        if (database.characters.Count > 0)
        {
            SelectCharacter(database.characters[0]);
        }
        else
        {
            ClearDetail();
        }
    }

    private void Update()
    {
        Keyboard keyboard = Keyboard.current;
        if (keyboard == null) return;

        if (keyboard.escapeKey.wasPressedThisFrame)
        {
            BackToHome();
            return;
        }

        if (keyboard.eKey.wasPressedThisFrame)
        {
            EditCharacter();
            return;
        }

        if (keyboard.rKey.wasPressedThisFrame)
        {
            RefreshSelectedCharacter();
            return;
        }

        if (keyboard.deleteKey.wasPressedThisFrame || keyboard.backspaceKey.wasPressedThisFrame)
        {
            DeleteSelectedCharacter();
        }
    }

    public void BackToHome()
    {
        SceneManager.LoadScene("HomeScene");
    }

    public void CreateCharacter()
    {
        CharacterEditorContext.isEditing = false;
        CharacterEditorContext.editingCharacterId = null;
        SceneManager.LoadScene("CharacterEditorScene");
    }

    public void SelectCharacter(CharacterData character)
    {
        selectedCharacter = character;
        if (selectedCharacter != null)
        {
            selectedCharacter.NormalizeCompatibilityFields();
        }

        UpdateDetail();
        UpdateSelectionVisual();
    }

    public void DeleteSelectedCharacter()
    {
        if (selectedCharacter == null)
        {
            Debug.Log("No character selected.");
            return;
        }

        database.characters.Remove(selectedCharacter);
        CharacterSaveService.Save(database);

        selectedCharacter = null;
        RefreshList();

        if (database.characters.Count > 0)
        {
            SelectCharacter(database.characters[0]);
        }
        else
        {
            ClearDetail();
        }
    }

    public void EditCharacter()
    {
        if (selectedCharacter == null)
        {
            Debug.Log("No character selected.");
            return;
        }

        CharacterEditorContext.isEditing = true;
        CharacterEditorContext.editingCharacterId = selectedCharacter.id;
        SceneManager.LoadScene("CharacterEditorScene");
    }

    public async void UploadSelectedCharacter()
    {
        if (selectedCharacter == null)
        {
            Debug.Log("No character selected.");
            return;
        }

        RoomSessionContext.SetCharacter(selectedCharacter.id);
        CharacterUploadResult result = await characterApiService.UploadCharacterAsync(selectedCharacter);
        CharacterSaveService.Save(database);
        Debug.Log("[CharacterVault] Upload result: " + result.status + " - " + result.summary);
        UpdateDetail();
    }

    public async void RefreshSelectedCharacter()
    {
        if (selectedCharacter == null)
        {
            Debug.Log("No character selected.");
            return;
        }

        CharacterData refreshed = await characterApiService.RefreshCharacterDetailAsync(selectedCharacter);
        if (refreshed != null)
        {
            refreshed.NormalizeCompatibilityFields();
            CharacterSaveService.Save(database);
        }

        UpdateDetail();
        RefreshList();
        UpdateSelectionVisual();
    }

    public void OnRefreshButtonClicked()
    {
        RefreshSelectedCharacter();
    }

    private void AutoBindReferences()
    {
        if (characterListContent == null) characterListContent = FindChildTransform("Content");
        if (nameText == null) nameText = FindChildText("NameText");
        if (classText == null) classText = FindChildText("ClassText");
        if (levelText == null) levelText = FindChildText("LevelText");
        if (hpText == null) hpText = FindChildText("HPText");
        if (mpText == null) mpText = FindChildText("MPText");
        if (strengthText == null) strengthText = FindChildText("StrengthText");
        if (dexterityText == null) dexterityText = FindChildText("DexterityText");
        if (intelligenceText == null) intelligenceText = FindChildText("IntelligenceText");
        if (skillsText == null) skillsText = FindChildText("SkillsText");
        if (inventoryText == null) inventoryText = FindChildText("InventoryText");

        if (backButton == null) backButton = FindChildButton("BackButton");
        if (createButton == null) createButton = FindChildButton("CreateButton");
        if (editButton == null) editButton = FindChildButton("EditButton");
        if (deleteButton == null) deleteButton = FindChildButton("DeleteButton");
        if (uploadButton == null) uploadButton = FindChildButton("UploadButton");
        if (refreshButton == null) refreshButton = FindChildButton("RefreshButton");
    }

    private void BindButtons()
    {
        BindButton(backButton, BackToHome);
        BindButton(createButton, CreateCharacter);
        BindButton(editButton, EditCharacter);
        BindButton(deleteButton, DeleteSelectedCharacter);
        BindButton(uploadButton, UploadSelectedCharacter);

        if (refreshButton != null)
        {
            BindButton(refreshButton, OnRefreshButtonClicked);
        }
        else
        {
            Debug.Log("[CharacterVault] RefreshButton not assigned yet. Create one manually and bind it in Inspector.");
        }
    }

    private void BindButton(Button button, UnityEngine.Events.UnityAction action)
    {
        if (button == null) return;
        button.onClick.RemoveAllListeners();
        button.onClick.AddListener(action);
    }

    private void EnsureAdvancedDetailPanel()
    {
        if (advancedDetailText != null) return;

        Canvas canvas = GetComponentInParent<Canvas>();
        if (canvas == null) canvas = FindFirstObjectByType<Canvas>(FindObjectsInactive.Include);
        if (canvas == null) return;

        GameObject existing = GameObject.Find("CharacterVaultAdvancedPanel");
        if (existing != null)
        {
            Destroy(existing);
        }

        GameObject panelObject = new GameObject("CharacterVaultAdvancedPanel", typeof(RectTransform), typeof(Image));
        panelObject.transform.SetParent(canvas.transform, false);
        RectTransform panelRect = panelObject.GetComponent<RectTransform>();
        panelRect.anchorMin = new Vector2(1f, 1f);
        panelRect.anchorMax = new Vector2(1f, 1f);
        panelRect.pivot = new Vector2(1f, 1f);
        panelRect.sizeDelta = new Vector2(300f, 500f);
        panelRect.anchoredPosition = new Vector2(-18f, -122f);
        panelObject.GetComponent<Image>().color = new Color(0.16f, 0.18f, 0.24f, 0.95f);

        CreatePanelLabel(panelRect, "Character Sync Detail", new Vector2(14f, -12f), 15f, FontStyles.Bold);
        CreatePanelLabel(panelRect, "Scroll for more", new Vector2(14f, -34f), 10.5f, FontStyles.Normal, new Color(0.84f, 0.87f, 0.93f, 0.95f));

        GameObject viewportObject = new GameObject("Viewport", typeof(RectTransform), typeof(Image), typeof(Mask));
        viewportObject.transform.SetParent(panelRect, false);
        RectTransform viewportRect = viewportObject.GetComponent<RectTransform>();
        viewportRect.anchorMin = new Vector2(0f, 0f);
        viewportRect.anchorMax = new Vector2(1f, 1f);
        viewportRect.offsetMin = new Vector2(10f, 12f);
        viewportRect.offsetMax = new Vector2(-10f, -54f);
        viewportObject.GetComponent<Image>().color = new Color(1f, 1f, 1f, 0.02f);
        viewportObject.GetComponent<Mask>().showMaskGraphic = false;

        GameObject contentObject = new GameObject("Content", typeof(RectTransform));
        contentObject.transform.SetParent(viewportObject.transform, false);
        RectTransform contentRect = contentObject.GetComponent<RectTransform>();
        contentRect.anchorMin = new Vector2(0f, 1f);
        contentRect.anchorMax = new Vector2(1f, 1f);
        contentRect.pivot = new Vector2(0.5f, 1f);
        contentRect.offsetMin = new Vector2(0f, 0f);
        contentRect.offsetMax = new Vector2(0f, 0f);
        contentRect.sizeDelta = new Vector2(0f, 860f);

        ScrollRect scrollRect = panelObject.AddComponent<ScrollRect>();
        scrollRect.viewport = viewportRect;
        scrollRect.content = contentRect;
        scrollRect.horizontal = false;
        scrollRect.vertical = true;
        scrollRect.scrollSensitivity = 26f;
        scrollRect.movementType = ScrollRect.MovementType.Clamped;

        GameObject textObject = new GameObject("AdvancedDetailText", typeof(RectTransform), typeof(TextMeshProUGUI));
        textObject.transform.SetParent(contentRect, false);
        RectTransform textRect = textObject.GetComponent<RectTransform>();
        textRect.anchorMin = new Vector2(0f, 1f);
        textRect.anchorMax = new Vector2(1f, 1f);
        textRect.pivot = new Vector2(0.5f, 1f);
        textRect.anchoredPosition = new Vector2(0f, -4f);
        textRect.sizeDelta = new Vector2(-8f, 840f);

        advancedDetailText = textObject.GetComponent<TMP_Text>();
        advancedDetailText.fontSize = 18f;
        advancedDetailText.color = Color.white;
        advancedDetailText.alignment = TextAlignmentOptions.TopLeft;
        advancedDetailText.enableWordWrapping = true;
        advancedDetailText.overflowMode = TextOverflowModes.Overflow;
    }

    private TMP_Text CreatePanelLabel(Transform parent, string text, Vector2 anchoredTopLeft, float fontSize, FontStyles style, Color? color = null)
    {
        GameObject go = new GameObject(text.Replace(" ", string.Empty) + "Label", typeof(RectTransform), typeof(TextMeshProUGUI));
        go.transform.SetParent(parent, false);
        RectTransform rect = go.GetComponent<RectTransform>();
        rect.anchorMin = new Vector2(0f, 1f);
        rect.anchorMax = new Vector2(0f, 1f);
        rect.pivot = new Vector2(0f, 1f);
        rect.anchoredPosition = anchoredTopLeft;
        rect.sizeDelta = new Vector2(240f, 22f);

        TMP_Text tmp = go.GetComponent<TMP_Text>();
        tmp.text = text;
        tmp.fontSize = fontSize;
        tmp.fontStyle = style;
        tmp.color = color ?? Color.white;
        tmp.alignment = TextAlignmentOptions.Left;
        tmp.enableWordWrapping = false;
        return tmp;
    }

    private TMP_Text FindChildText(string objectName)
    {
        TMP_Text[] texts = GetComponentsInChildren<TMP_Text>(true);
        for (int i = 0; i < texts.Length; i++)
        {
            if (texts[i].name == objectName)
            {
                return texts[i];
            }
        }
        return null;
    }

    private Button FindChildButton(string objectName)
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

    private Transform FindChildTransform(string objectName)
    {
        Transform[] transforms = GetComponentsInChildren<Transform>(true);
        for (int i = 0; i < transforms.Length; i++)
        {
            if (transforms[i].name == objectName)
            {
                return transforms[i];
            }
        }
        return null;
    }

    private void RefreshList()
    {
        if (characterListContent == null) return;

        foreach (Transform child in characterListContent)
        {
            Destroy(child.gameObject);
        }

        listItems.Clear();

        foreach (CharacterData character in database.characters)
        {
            GameObject itemObject = Instantiate(characterListItemPrefab, characterListContent);
            CharacterListItemUI itemUI = itemObject.GetComponent<CharacterListItemUI>();
            itemUI.Setup(character, this);
            listItems.Add(itemUI);
        }

        UpdateSelectionVisual();
    }

    private void UpdateDetail()
    {
        if (selectedCharacter == null)
        {
            ClearDetail();
            return;
        }

        selectedCharacter.NormalizeCompatibilityFields();

        nameText.text = "Name: " + selectedCharacter.DisplayName;
        classText.text = "Class: " + selectedCharacter.DisplayClass;
        levelText.text = "Level: " + selectedCharacter.level;
        hpText.text = "HP: " + selectedCharacter.hp;
        mpText.text = "MP: " + selectedCharacter.mp;
        strengthText.text = "Strength: " + selectedCharacter.strength;
        dexterityText.text = "Dexterity: " + selectedCharacter.dexterity;
        intelligenceText.text = "Intelligence: " + selectedCharacter.intelligence;
        skillsText.text = "Skills: " + EmptyDash(selectedCharacter.skills);
        inventoryText.text = "Inventory: " + EmptyDash(selectedCharacter.inventory);

        if (UploadWorkflowContext.UploadedCharacterId == selectedCharacter.id && UploadWorkflowContext.LastAuditResult != null)
        {
            inventoryText.text += "\n\nLast Upload: " + UploadWorkflowContext.LastAuditResult.status;
        }

        if (advancedDetailText != null)
        {
            advancedDetailText.text =
                "Status: " + (selectedCharacter.syncedWithBackend ? "Synced" : "Local") + "\n\n" +
                "Species: " + selectedCharacter.SpeciesSafe + "\n" +
                "Background: " + selectedCharacter.BackgroundSafe + "\n" +
                "Alignment: " + EmptyDash(selectedCharacter.alignment) + "\n" +
                "Edition: " + selectedCharacter.EditionSafe + "\n" +
                "Subclass: " + EmptyDash(selectedCharacter.subclass) + "\n\n" +
                "Max HP: " + selectedCharacter.MaxHpSafe + "\n" +
                "Con / Wis / Cha: " + selectedCharacter.constitution + " / " + selectedCharacter.wisdom + " / " + selectedCharacter.charisma + "\n" +
                "Walk Speed: " + selectedCharacter.SpeedSafe + "\n" +
                "AC / Init / PP: " + ValueOrDash(selectedCharacter.armorClass) + " / " + ValueOrDash(selectedCharacter.initiativeBonus) + " / " + ValueOrDash(selectedCharacter.passivePerception) + "\n" +
                "Spell Save DC / Attack: " + ValueOrDash(selectedCharacter.spellSaveDc) + " / " + ValueOrDash(selectedCharacter.spellAttackBonus) + "\n\n" +
                "Conditions: " + EmptyDash(selectedCharacter.conditions) + "\n" +
                "Spellcasting: " + EmptyDash(selectedCharacter.spellcastingAbility) + "\n" +
                "Spell Stats: " + EmptyDash(selectedCharacter.SpellStatsSafe) + "\n\n" +
                "Languages: " + EmptyDash(selectedCharacter.languages) + "\n" +
                "Tools: " + EmptyDash(selectedCharacter.toolProficiencies) + "\n" +
                "Currency: " + EmptyDash(selectedCharacter.CurrencySafe) + "\n\n" +
                "Approval: " + (selectedCharacter.dmApproved ? "Approved" : "Pending") +
                (string.IsNullOrWhiteSpace(selectedCharacter.ApprovalNoteSafe) ? string.Empty : "\nNote: " + selectedCharacter.ApprovalNoteSafe) + "\n\n" +
                "Updated: " + EmptyDash(selectedCharacter.updatedAt) + "\n\n" +
                "Context: " + EmptyDash(selectedCharacter.contextText) + "\n\n" +
                "Derived: " + EmptyDash(selectedCharacter.derivedSummary);
        }
    }

    private void ClearDetail()
    {
        nameText.text = "Name: -";
        classText.text = "Class: -";
        levelText.text = "Level: -";
        hpText.text = "HP: -";
        mpText.text = "MP: -";
        strengthText.text = "Strength: -";
        dexterityText.text = "Dexterity: -";
        intelligenceText.text = "Intelligence: -";
        skillsText.text = "Skills: -";
        inventoryText.text = "Inventory: -";

        if (advancedDetailText != null)
        {
            advancedDetailText.text = "No character selected.";
        }
    }

    private void UpdateSelectionVisual()
    {
        foreach (CharacterListItemUI item in listItems)
        {
            bool isSelected = selectedCharacter != null && item.BoundCharacterId == selectedCharacter.id;
            item.SetSelected(isSelected);
        }
    }

    private static string EmptyDash(string value)
    {
        return string.IsNullOrWhiteSpace(value) ? "-" : value;
    }

    private static string ValueOrDash(int value)
    {
        return value > 0 ? value.ToString() : "-";
    }
}