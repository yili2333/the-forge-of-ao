using System;
using System.Collections.Generic;
using System.IO;
using System.Text.RegularExpressions;
using TMPro;
using UnityEngine;
using UnityEngine.Events;
using UnityEngine.InputSystem;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public partial class RoomUIController : MonoBehaviour
{
    [Header("Room Info")]
    public TMP_Text roomInfoText;

    [Header("Simple Character Card")]
    public TMP_Text cardTitleText;
    public TMP_Text cardNameText;
    public TMP_Text cardClassText;
    public TMP_Text cardLevelText;
    public TMP_Text cardHpText;
    public Button viewDetailsButton;

    [Header("Character Detail Popup")]
    public GameObject detailPopupPanel;
    public TMP_Text detailPopupTitleText;
    public TMP_Text detailNameText;
    public TMP_Text detailClassText;
    public TMP_Text detailLevelText;
    public TMP_Text detailHpText;
    public TMP_Text detailMpText;
    public TMP_Text detailStrengthText;
    public TMP_Text detailDexterityText;
    public TMP_Text detailIntelligenceText;
    public TMP_Text detailSkillsText;
    public TMP_Text detailInventoryText;
    public Button closeDetailButton;

    [Header("Party Members")]
    public Transform partyMemberListContent;
    public GameObject partyMemberItemPrefab;
    public TMP_Text partyEmptyText;

    [Header("Scene Area")]
    public Image scenePreviewImage;
    public TMP_Text scenePreviewLabelText;
    public TMP_InputField scenePromptInput;
    public Button generateSceneButton;
    public TMP_Text sceneTitleText;
    public TMP_Text sceneDescriptionText;

    [Header("Chat / Log")]
    public TMP_Text chatLogText;
    public TMP_InputField chatInput;
    public Button sendButton;

    private CharacterDatabase database;
    private readonly List<CharacterData> partyCharacters = new List<CharacterData>();
    private string selectedCharacterId = string.Empty;

    private readonly RoomApiService roomApiService = new RoomApiService();
    private readonly RuleAiApiService ruleAiApiService = new RuleAiApiService();
    private readonly CharacterApiService characterApiService = new CharacterApiService();
    private readonly SceneApiService sceneApiService = new SceneApiService();
    private readonly CampaignApiService campaignApiService = new CampaignApiService();

    private WebSocketSessionClient webSocketClient;
    private CharacterAuditResult currentAuditResult;
    private AudioSource ambientAudioSource;
    private AudioClip currentAmbientClip;
    private Texture2D currentSceneTexture;

    private TMP_Text connectionStatusText;
    private TMP_Text modeStatusText;
    private TMP_Text auditStatusText;
    private Button modeToggleButton;
    private Button reconnectButton;
    private Button rollD20Button;
    private Button loadLocalImageButton;
    private Button bgmToggleButton;
    private Button volumeDownButton;
    private Button volumeUpButton;
    private Button approveAuditButton;
    private Button rejectAuditButton;
    private Button requestChangesButton;
    private LayoutElement chatLogLayoutElement;

    private InputMode currentInputMode = InputMode.Chat;
    private float nextReconnectAttemptTime;
    private readonly List<string> fullLogLines = new List<string>();
    private int logViewStartIndex;
    private bool followLatestLog = true;
    private const int VisibleLogLineCount = 9;
    private const int MaxDisplayedLineLength = 0;

    private enum InputMode
    {
        Chat,
        RuleAi
    }

    private async void Start()
    {
        AutoBindReferences();

        database = CharacterSaveService.Load();
        partyCharacters.Clear();

        if (database != null && database.characters != null)
        {
            partyCharacters.AddRange(database.characters);
        }

        await LoadLiveRoomDataAsync();
        InitializeSelectedCharacter();
        LoadRoomInfo();
        RefreshSimpleCard();
        LoadPartyMembers();
        await RefreshSelectedCharacterDetailsAsync();
        SetupDetailPopupControls();
        HideDetailPopup();
        InitializeChatLog();
        ConfigureChatLogDisplay();
        InitializeSceneArea();
        SetupSceneControls();
        SetupChatControls();
        BuildRuntimeOverlay();
        BuildAdvancedRuntimeOverlay();
        InitializeAmbientAudio();
        UpdateModeUi();
        UpdateBgmUi();
        nextReconnectAttemptTime = Time.unscaledTime + 6f;

        await InitializeRoomConnectionAsync();
        await RefreshAuditPanelAsync();
    }

    private void Update()
    {
        PumpWebSocketMessages();
        AutoReconnectIfNeeded();

        Keyboard keyboard = Keyboard.current;
        if (keyboard == null)
        {
            return;
        }

        HandleLogScrollInput(keyboard);

        if (keyboard.escapeKey.wasPressedThisFrame)
        {
            if (detailPopupPanel != null && detailPopupPanel.activeSelf)
            {
                HideDetailPopup();
            }
            else
            {
                ReturnToHomeScene();
            }

            return;
        }

        bool pressedEnter = keyboard.enterKey.wasPressedThisFrame || keyboard.numpadEnterKey.wasPressedThisFrame;
        if (chatInput != null && chatInput.isFocused && pressedEnter)
        {
            SendChatMessage();
        }
    }

    private void HandleLogScrollInput(Keyboard keyboard)
    {
        Mouse mouse = Mouse.current;
        float scrollDelta = mouse != null ? mouse.scroll.ReadValue().y : 0f;

        if (keyboard.homeKey.wasPressedThisFrame)
        {
            SetLogWindowStart(0);
            return;
        }

        if (keyboard.endKey.wasPressedThisFrame)
        {
            JumpLogToLatest();
            return;
        }

        if (keyboard.pageUpKey.wasPressedThisFrame || scrollDelta > 0.01f)
        {
            SetLogWindowStart(logViewStartIndex - 1);
            return;
        }

        if (keyboard.pageDownKey.wasPressedThisFrame || scrollDelta < -0.01f)
        {
            SetLogWindowStart(logViewStartIndex + 1);
        }
    }

    private async void OnDestroy()
    {
        if (webSocketClient != null)
        {
            await webSocketClient.DisconnectAsync();
            webSocketClient = null;
        }

        if (currentAmbientClip != null)
        {
            Destroy(currentAmbientClip);
        }

        if (currentSceneTexture != null)
        {
            Destroy(currentSceneTexture);
        }
    }

    private void AutoBindReferences()
    {
        if (roomInfoText == null) roomInfoText = FindChildComponent<TMP_Text>("RoomInfoText");
        if (cardTitleText == null) cardTitleText = FindChildComponent<TMP_Text>("UploadedTitleText");
        if (cardNameText == null) cardNameText = FindChildComponent<TMP_Text>("UploadedNameText");
        if (cardClassText == null) cardClassText = FindChildComponent<TMP_Text>("UploadedClassText");
        if (cardLevelText == null) cardLevelText = FindChildComponent<TMP_Text>("UploadedLevelText");
        if (cardHpText == null) cardHpText = FindChildComponent<TMP_Text>("UploadedHpText");
        if (viewDetailsButton == null) viewDetailsButton = FindChildComponent<Button>("ViewDetailsButton");

        if (detailPopupPanel == null)
        {
            Transform popup = FindChildTransform("CharacterDetailPopup");
            if (popup != null) detailPopupPanel = popup.gameObject;
        }

        if (detailPopupTitleText == null) detailPopupTitleText = FindChildComponent<TMP_Text>("DetailPopupTitleText");
        if (detailNameText == null) detailNameText = FindChildComponent<TMP_Text>("DetailNameText");
        if (detailClassText == null) detailClassText = FindChildComponent<TMP_Text>("DetailClassText");
        if (detailLevelText == null) detailLevelText = FindChildComponent<TMP_Text>("DetailLevelText");
        if (detailHpText == null) detailHpText = FindChildComponent<TMP_Text>("DetailHpText");
        if (detailMpText == null) detailMpText = FindChildComponent<TMP_Text>("DetailMpText");
        if (detailStrengthText == null) detailStrengthText = FindChildComponent<TMP_Text>("DetailStrengthText");
        if (detailDexterityText == null) detailDexterityText = FindChildComponent<TMP_Text>("DetailDexterityText");
        if (detailIntelligenceText == null) detailIntelligenceText = FindChildComponent<TMP_Text>("DetailIntelligenceText");
        if (detailSkillsText == null) detailSkillsText = FindChildComponent<TMP_Text>("DetailSkillsText");
        if (detailInventoryText == null) detailInventoryText = FindChildComponent<TMP_Text>("DetailInventoryText");
        if (closeDetailButton == null) closeDetailButton = FindChildComponent<Button>("CloseDetailButton");

        if (partyMemberListContent == null) partyMemberListContent = FindChildTransform("PartyMemberListContent");
        if (partyEmptyText == null) partyEmptyText = FindChildComponent<TMP_Text>("PartyEmptyText");

        if (scenePromptInput == null) scenePromptInput = FindChildComponent<TMP_InputField>("ScenePromptInput");
        if (generateSceneButton == null) generateSceneButton = FindChildComponent<Button>("GenerateSceneButton");
        if (sceneTitleText == null) sceneTitleText = FindChildComponent<TMP_Text>("SceneTitleText");
        if (sceneDescriptionText == null) sceneDescriptionText = FindChildComponent<TMP_Text>("SceneDescriptionText");
        if (scenePreviewLabelText == null) scenePreviewLabelText = FindChildComponent<TMP_Text>("Text (TMP)");
        if (scenePreviewImage == null)
        {
            Transform centerPanel = FindChildTransform("CenterPanel");
            if (centerPanel != null)
            {
                scenePreviewImage = centerPanel.GetComponent<Image>();
            }
        }

        if (chatLogText == null) chatLogText = FindChildComponent<TMP_Text>("ChatLogText");
        if (chatInput == null) chatInput = FindChildComponent<TMP_InputField>("ChatInput");
        if (sendButton == null) sendButton = FindChildComponent<Button>("SendButton");

        if (partyMemberItemPrefab == null)
        {
            GameObject prefab = Resources.Load<GameObject>("PartyMemberItem");
            if (prefab != null) partyMemberItemPrefab = prefab;
        }
    }

    private T FindChildComponent<T>(string objectName) where T : Component
    {
        T[] components = GetComponentsInChildren<T>(true);
        for (int i = 0; i < components.Length; i++)
        {
            if (components[i].name == objectName)
            {
                return components[i];
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

    private async System.Threading.Tasks.Task LoadLiveRoomDataAsync()
    {
        if (BackendConfig.UseMockServices)
        {
            return;
        }

        try
        {
            List<CharacterData> liveCharacters = await characterApiService.LoadCampaignCharactersAsync(RoomSessionContext.roomId);
            if (liveCharacters != null && liveCharacters.Count > 0)
            {
                partyCharacters.Clear();
                partyCharacters.AddRange(liveCharacters);
            }

            SessionSnapshotLite latestSession = await campaignApiService.GetLatestSessionAsync(RoomSessionContext.roomId);
            if (latestSession != null && latestSession.success && !string.IsNullOrWhiteSpace(latestSession.activeEncounterMapId))
            {
                BackendConfig.EncounterMapId = latestSession.activeEncounterMapId;
            }

            if (RoomSessionContext.IsDM)
            {
                CampaignOverviewLite overview = await campaignApiService.GetCampaignOverviewAsync(RoomSessionContext.roomId);
                if (overview != null && overview.success && !string.IsNullOrWhiteSpace(overview.activeEncounterMapId) && (string.IsNullOrWhiteSpace(BackendConfig.EncounterMapId) || BackendConfig.EncounterMapId == "main"))
                {
                    BackendConfig.EncounterMapId = overview.activeEncounterMapId;
                }
            }
        }
        catch (Exception ex)
        {
            Debug.Log("[RoomUI] Live room bootstrap failed: " + ex.Message);
        }
    }

    private void InitializeSelectedCharacter()
    {
        string uploadedId = !string.IsNullOrEmpty(UploadWorkflowContext.UploadedCharacterId)
            ? UploadWorkflowContext.UploadedCharacterId
            : CharacterUploadContext.uploadedCharacterId;

        if (!string.IsNullOrEmpty(uploadedId))
        {
            selectedCharacterId = uploadedId;
            RoomSessionContext.SetCharacter(uploadedId);
            return;
        }

        selectedCharacterId = partyCharacters.Count > 0 ? partyCharacters[0].id : string.Empty;
        RoomSessionContext.SetCharacter(selectedCharacterId);
    }

    private void LoadRoomInfo()
    {
        if (roomInfoText != null)
        {
            roomInfoText.text = "Room: " + RoomSessionContext.roomId + " | Role: " + RoomSessionContext.role + " | Owner: " + BackendConfig.OwnerId;
        }
    }

    private CharacterData GetSelectedCharacter()
    {
        if (string.IsNullOrEmpty(selectedCharacterId))
        {
            return null;
        }

        return partyCharacters.Find(c => c.id == selectedCharacterId);
    }

    private CharacterData GetUploadedOrSelectedCharacter()
    {
        if (!string.IsNullOrEmpty(CharacterUploadContext.uploadedCharacterId))
        {
            CharacterData uploaded = partyCharacters.Find(c => c.id == CharacterUploadContext.uploadedCharacterId);
            if (uploaded != null)
            {
                return uploaded;
            }
        }

        return GetSelectedCharacter();
    }

    private void RefreshSimpleCard()
    {
        CharacterData selectedCharacter = GetSelectedCharacter();

        if (selectedCharacter == null)
        {
            ClearSimpleCard();
            return;
        }

        bool isUploaded = selectedCharacter.id == CharacterUploadContext.uploadedCharacterId;

        if (cardTitleText != null) cardTitleText.text = isUploaded ? "Uploaded Character" : "Selected Character";
        if (cardNameText != null) cardNameText.text = "Name: " + selectedCharacter.DisplayName;
        if (cardClassText != null)
        {
            string classLine = "Class: " + selectedCharacter.DisplayClass;
            if (!string.IsNullOrWhiteSpace(selectedCharacter.ownerDisplay))
            {
                classLine += " | Owner: " + selectedCharacter.ownerDisplay;
            }
            cardClassText.text = classLine;
        }
        if (cardLevelText != null)
        {
            string levelLine = "Level: " + Mathf.Max(1, selectedCharacter.level);
            if (selectedCharacter.armorClass > 0)
            {
                levelLine += " | AC: " + selectedCharacter.armorClass;
            }
            cardLevelText.text = levelLine;
        }
        if (cardHpText != null)
        {
            string hpLine = selectedCharacter.hp > 0 ? "HP: " + selectedCharacter.hp : "HP: ?";
            if (selectedCharacter.passivePerception > 0)
            {
                hpLine += " | PP: " + selectedCharacter.passivePerception;
            }
            cardHpText.text = hpLine;
        }

        if (viewDetailsButton != null)
        {
            viewDetailsButton.interactable = true;
        }
    }

    private void ClearSimpleCard()
    {
        if (cardTitleText != null) cardTitleText.text = "Character Card";
        if (cardNameText != null) cardNameText.text = "Name: -";
        if (cardClassText != null) cardClassText.text = "Class: -";
        if (cardLevelText != null) cardLevelText.text = "Level: -";
        if (cardHpText != null) cardHpText.text = "HP: -";

        if (viewDetailsButton != null)
        {
            viewDetailsButton.interactable = false;
        }
    }

    private void LoadPartyMembers()
    {
        if (partyMemberListContent == null || partyMemberItemPrefab == null)
        {
            return;
        }

        foreach (Transform child in partyMemberListContent)
        {
            Destroy(child.gameObject);
        }

        int count = 0;

        foreach (CharacterData character in partyCharacters)
        {
            GameObject itemObject = Instantiate(partyMemberItemPrefab, partyMemberListContent);
            PartyMemberItemUI itemUI = itemObject.GetComponent<PartyMemberItemUI>();

            if (itemUI != null)
            {
                bool isUploaded = character.id == CharacterUploadContext.uploadedCharacterId;
                bool isSelected = character.id == selectedCharacterId;
                itemUI.Setup(character, isUploaded, isSelected, OnPartyMemberClicked);
            }

            count++;
        }

        if (partyEmptyText != null)
        {
            partyEmptyText.gameObject.SetActive(count == 0);
        }
    }

    private void OnPartyMemberClicked(CharacterData clickedCharacter)
    {
        if (clickedCharacter == null)
        {
            return;
        }

        selectedCharacterId = clickedCharacter.id;
        RoomSessionContext.SetCharacter(clickedCharacter.id);
        RefreshSimpleCard();
        LoadPartyMembers();

        if (detailPopupPanel != null && detailPopupPanel.activeSelf)
        {
            ShowDetailPopup();
        }

        _ = RefreshSelectedCharacterDetailsAsync();
        _ = RefreshAuditPanelAsync();
    }

    private void SetupDetailPopupControls()
    {
        if (viewDetailsButton != null)
        {
            viewDetailsButton.onClick.RemoveAllListeners();
            viewDetailsButton.onClick.AddListener(ShowDetailPopup);
        }

        if (closeDetailButton != null)
        {
            closeDetailButton.onClick.RemoveAllListeners();
            closeDetailButton.onClick.AddListener(HideDetailPopup);
        }
    }

    public void ShowDetailPopup()
    {
        CharacterData selectedCharacter = GetSelectedCharacter();

        if (selectedCharacter == null || detailPopupPanel == null)
        {
            return;
        }

        if (detailPopupTitleText != null) detailPopupTitleText.text = selectedCharacter.DisplayName + " Details";
        if (detailNameText != null)
        {
            string nameLine = "Name: " + selectedCharacter.DisplayName;
            if (!string.IsNullOrWhiteSpace(selectedCharacter.ownerId))
            {
                nameLine += " | Owner: " + selectedCharacter.ownerId;
            }
            detailNameText.text = nameLine;
        }
        if (detailClassText != null) detailClassText.text = "Class: " + selectedCharacter.DisplayClass;
        if (detailLevelText != null)
        {
            string line = "Level: " + Mathf.Max(1, selectedCharacter.level);
            if (selectedCharacter.armorClass > 0) line += " | AC: " + selectedCharacter.armorClass;
            if (selectedCharacter.initiativeBonus != 0) line += " | Init: " + (selectedCharacter.initiativeBonus > 0 ? "+" : string.Empty) + selectedCharacter.initiativeBonus;
            detailLevelText.text = line;
        }
        if (detailHpText != null)
        {
            string hpLine = "HP: " + (selectedCharacter.hp > 0 ? selectedCharacter.hp.ToString() : "?");
            if (selectedCharacter.passivePerception > 0) hpLine += " | Passive Perception: " + selectedCharacter.passivePerception;
            detailHpText.text = hpLine;
        }
        if (detailMpText != null)
        {
            string mpLine = "HP Max / Extra: " + (selectedCharacter.mp > 0 ? selectedCharacter.mp.ToString() : "-");
            if (selectedCharacter.speedEffective > 0) mpLine += " | Speed: " + selectedCharacter.speedEffective + " ft";
            detailMpText.text = mpLine;
        }
        if (detailStrengthText != null) detailStrengthText.text = "Strength: " + selectedCharacter.strength;
        if (detailDexterityText != null) detailDexterityText.text = "Dexterity: " + selectedCharacter.dexterity;
        if (detailIntelligenceText != null)
        {
            string intLine = "Intelligence: " + selectedCharacter.intelligence;
            if (!string.IsNullOrWhiteSpace(selectedCharacter.conditions)) intLine += " | Conditions: " + selectedCharacter.conditions;
            detailIntelligenceText.text = intLine;
        }
        if (detailSkillsText != null)
        {
            string skillsText = !string.IsNullOrWhiteSpace(selectedCharacter.derivedSummary)
                ? selectedCharacter.derivedSummary
                : (!string.IsNullOrWhiteSpace(selectedCharacter.contextText) ? selectedCharacter.contextText : selectedCharacter.skills);
            detailSkillsText.text = "Summary: " + skillsText;
        }
        if (detailInventoryText != null)
        {
            string inventoryLine = !string.IsNullOrWhiteSpace(selectedCharacter.inventory) ? selectedCharacter.inventory : "-";
            if (selectedCharacter.dmApproved) inventoryLine += " | DM Approved";
            detailInventoryText.text = "Inventory: " + inventoryLine;
        }

        detailPopupPanel.SetActive(true);
    }

    public void HideDetailPopup()
    {
        if (detailPopupPanel != null)
        {
            detailPopupPanel.SetActive(false);
        }
    }

    private void InitializeChatLog()
    {
        fullLogLines.Clear();
        AppendSystemMessage("Room created.");
        AppendSystemMessage("Joined " + RoomSessionContext.roomId + " as " + RoomSessionContext.role + ".");
        AppendSystemMessage("Owner ID: " + BackendConfig.OwnerId + " | HTTP " + BackendConfig.HttpHost + ":" + BackendConfig.HttpPort + " | WS " + BackendConfig.WsHost + ":" + BackendConfig.WsPort + ".");
        AppendSystemMessage("Use the bottom strip for Chat / Rule AI / d20 / local scene image / BGM.");
        AppendSystemMessage("Type /help to list local commands.");

        if (!string.IsNullOrEmpty(CharacterUploadContext.uploadedCharacterId))
        {
            CharacterData uploadedCharacter = partyCharacters.Find(c => c.id == CharacterUploadContext.uploadedCharacterId);
            if (uploadedCharacter != null)
            {
                AppendSystemMessage("Character uploaded - " + uploadedCharacter.characterName + ".");
            }
        }
    }

    private void ConfigureChatLogDisplay()
    {
        if (chatLogText == null)
        {
            return;
        }

        chatLogText.alignment = TextAlignmentOptions.TopLeft;
        chatLogText.textWrappingMode = TextWrappingModes.Normal;
        chatLogText.enableWordWrapping = true;
        chatLogText.overflowMode = TextOverflowModes.Overflow;
        chatLogText.lineSpacing = -4f;

        chatLogLayoutElement = chatLogText.GetComponent<LayoutElement>();
        if (chatLogLayoutElement == null)
        {
            chatLogLayoutElement = chatLogText.gameObject.AddComponent<LayoutElement>();
        }

        float fixedHeight = chatLogText.rectTransform.rect.height;
        if (fixedHeight < 180f)
        {
            fixedHeight = 180f;
        }

        chatLogLayoutElement.minHeight = fixedHeight;
        chatLogLayoutElement.preferredHeight = fixedHeight;
        chatLogLayoutElement.flexibleHeight = 1f;
    }

    private void ReturnToHomeScene()
    {
        SceneManager.LoadScene("HomeScene");
    }


    private void InitializeSceneArea()
    {
        HideLegacyOpenWorldMapButton();

        if (sceneTitleText != null) sceneTitleText.text = "Current Scene";
        if (sceneDescriptionText != null) sceneDescriptionText.text = "No scene generated yet.";
        if (scenePreviewLabelText != null) scenePreviewLabelText.text = "Scene Preview";
        if (scenePreviewImage != null)
        {
            scenePreviewImage.color = new Color(0.55f, 0.60f, 0.68f, 1f);
        }

        if (scenePromptInput != null && RoomSessionContext.IsDM)
        {
            scenePromptInput.text = "Dimly lit alchemy lab, green potions, stone walls";
        }
    }


    private void HideLegacyOpenWorldMapButton()
    {
        Button[] buttons = FindObjectsByType<Button>(FindObjectsInactive.Include, FindObjectsSortMode.None);
        for (int i = 0; i < buttons.Length; i++)
        {
            Button button = buttons[i];
            if (button == null)
            {
                continue;
            }

            if (button.name == "WorldMapButton")
            {
                continue;
            }

            Transform parent = button.transform.parent;
            string parentName = parent != null ? parent.name : string.Empty;
            if (parentName == "RuntimeBottomStrip" || parentName == "AdvancedRuntimePanel" || parentName == "AdvancedRuntimeStrip")
            {
                continue;
            }

            TMP_Text label = button.GetComponentInChildren<TMP_Text>(true);
            if (label != null && string.Equals(label.text.Trim(), "Open World Map", StringComparison.OrdinalIgnoreCase))
            {
                button.gameObject.SetActive(false);
            }
        }
    }

    private void SetupSceneControls()
    {
        if (generateSceneButton != null)
        {
            generateSceneButton.onClick.RemoveAllListeners();
            generateSceneButton.onClick.AddListener(GenerateSceneFromBackend);
            generateSceneButton.interactable = RoomSessionContext.IsDM;
        }

        if (scenePromptInput != null)
        {
            scenePromptInput.interactable = RoomSessionContext.IsDM;
            if (!RoomSessionContext.IsDM)
            {
                scenePromptInput.text = "Only DM can generate scenes. /load path.png still works locally in editor or with a file path.";
            }
        }
    }

    private void SetupChatControls()
    {
        if (sendButton != null)
        {
            sendButton.onClick.RemoveAllListeners();
            sendButton.onClick.AddListener(SendChatMessage);
        }
    }

    private async System.Threading.Tasks.Task RefreshSelectedCharacterDetailsAsync()
    {
        CharacterData selectedCharacter = GetSelectedCharacter();
        if (selectedCharacter == null || BackendConfig.UseMockServices)
        {
            return;
        }

        await characterApiService.RefreshCharacterDetailAsync(selectedCharacter);
        RefreshSimpleCard();
        LoadPartyMembers();

        if (detailPopupPanel != null && detailPopupPanel.activeSelf)
        {
            ShowDetailPopup();
        }
    }

    private async System.Threading.Tasks.Task AppendLiveBootstrapNotesAsync()
    {
        if (BackendConfig.UseMockServices)
        {
            return;
        }

        if (RoomSessionContext.IsDM)
        {
            CampaignOverviewLite overview = await campaignApiService.GetCampaignOverviewAsync(RoomSessionContext.roomId);
            if (overview != null && overview.success)
            {
                AppendSystemMessage(overview.summary);
            }
        }

        SessionSnapshotLite latestSession = await campaignApiService.GetLatestSessionAsync(RoomSessionContext.roomId);
        if (latestSession != null && latestSession.success)
        {
            AppendSystemMessage(latestSession.summary + (string.IsNullOrWhiteSpace(latestSession.activeEncounterMapId) ? string.Empty : " Active map: " + latestSession.activeEncounterMapId + "."));
        }

        int? monsterCount = await campaignApiService.GetMonsterCountAsync();
        if (monsterCount.HasValue)
        {
            AppendSystemMessage("Monster database ready: " + monsterCount.Value + " monsters available.");
        }
    }

    private async System.Threading.Tasks.Task InitializeRoomConnectionAsync()
    {
        SetConnectionStatus("Checking backend...");
        BackendProbeResult probe = await roomApiService.ProbeBackendAsync();

        if (!probe.reachable)
        {
            SetConnectionStatus(BackendConfig.UseMockServices ? "Local mode" : "Offline");
            AppendSystemMessage(probe.summary);
            if (BackendConfig.UseMockServices)
            {
                AppendSystemMessage("Backend not reachable. Running in local prototype mode.");
            }
            nextReconnectAttemptTime = Time.unscaledTime + 8f;
            return;
        }

        if (webSocketClient != null)
        {
            await webSocketClient.DisconnectAsync();
        }

        webSocketClient = new WebSocketSessionClient();
        string activeCharacterId = GetUploadedOrSelectedCharacter() != null ? GetUploadedOrSelectedCharacter().id : RoomSessionContext.currentCharacterId;
        bool connected = await webSocketClient.ConnectAsync(RoomSessionContext.roomId, BackendConfig.OwnerId, RoomSessionContext.RoleParam, activeCharacterId);

        if (connected)
        {
            SetConnectionStatus("Realtime sync online");
            AppendSystemMessage("Connected to backend WebSocket session.");

            if (EncounterBoardController.Instance != null)
            {
                EncounterBoardController.Instance.WsClient = webSocketClient;
                await EncounterBoardController.Instance.LoadFromBackendAsync(RoomSessionContext.roomId, BackendConfig.EncounterMapId, RoomSessionContext.IsDM);
            }

            await RefreshSelectedCharacterDetailsAsync();
            await AppendLiveBootstrapNotesAsync();
        }
        else
        {
            SetConnectionStatus("Backend online, socket offline");
            AppendSystemMessage("Backend responded, but realtime socket did not connect. Staying in local mode.");
            nextReconnectAttemptTime = Time.unscaledTime + 8f;
        }
    }

    private void PumpWebSocketMessages()
    {
        if (webSocketClient == null)
        {
            return;
        }

        RoomMessage message;
        while (webSocketClient.TryDequeueMessage(out message))
        {
            if (message == null)
            {
                continue;
            }

            string payload = JsonRegexUtility.ExtractObject(message.dataJson, "data");
            if (string.IsNullOrWhiteSpace(payload))
            {
                payload = message.dataJson;
            }

            if (EncounterBoardController.Instance != null)
            {
                EncounterBoardController.Instance.OnWebSocketMessage(message.type, payload);
            }

            if (HandleAdvancedRealtimeMessage(message, payload))
            {
                continue;
            }

            switch (message.type)
            {
                case "system":
                case "error":
                    AppendSystemMessage(message.content);
                    break;
                case "chat":
                    string chatText = JsonRegexUtility.ExtractString(payload, "text");
                    AppendChatMessage(string.IsNullOrEmpty(message.sender) ? "Server" : message.sender, string.IsNullOrWhiteSpace(chatText) ? message.content : chatText);
                    break;
                case "join":
                    AppendSystemMessage((string.IsNullOrWhiteSpace(message.sender) ? "Player" : message.sender) + " joined the room.");
                    _ = LoadLiveRoomDataAsync();
                    break;
                case "leave":
                    AppendSystemMessage((string.IsNullOrWhiteSpace(message.sender) ? "Player" : message.sender) + " left the room.");
                    _ = LoadLiveRoomDataAsync();
                    break;
                case "sync":
                    AppendSystemMessage("Realtime sync received.");
                    if (!string.IsNullOrWhiteSpace(JsonRegexUtility.ExtractString(payload, "active_encounter_map_id")))
                    {
                        BackendConfig.EncounterMapId = JsonRegexUtility.ExtractString(payload, "active_encounter_map_id");
                    }
                    _ = LoadLiveRoomDataAsync();
                    _ = RefreshSelectedCharacterDetailsAsync();
                    break;
                case "roll_result":
                    string breakdown = JsonRegexUtility.ExtractString(payload, "breakdown");
                    AppendSystemMessage("Roll result: " + (string.IsNullOrWhiteSpace(breakdown) ? message.content : breakdown));
                    break;
                case "initiative_update":
                    AppendSystemMessage("Initiative order updated.");
                    _ = RefreshSelectedCharacterDetailsAsync();
                    break;
                case "combat_start":
                    AppendSystemMessage("Combat started.");
                    break;
                case "combat_end":
                    AppendSystemMessage("Combat ended.");
                    break;
                case "dm_approval_result":
                    AppendSystemMessage("DM approval result received.");
                    _ = LoadLiveRoomDataAsync();
                    _ = RefreshAuditPanelAsync();
                    _ = RefreshSelectedCharacterDetailsAsync();
                    break;
                default:
                    if (!string.IsNullOrWhiteSpace(message.content))
                    {
                        AppendChatMessage(string.IsNullOrEmpty(message.sender) ? "Server" : message.sender, message.content);
                    }
                    break;
            }
        }
    }

    public async void GenerateSceneFromBackend()
    {
        if (!RoomSessionContext.IsDM)
        {
            AppendSystemMessage("Only DM can generate scenes.");
            return;
        }

        string prompt = scenePromptInput != null ? scenePromptInput.text.Trim() : string.Empty;
        if (string.IsNullOrEmpty(prompt))
        {
            AppendSystemMessage("Scene prompt is empty.");
            return;
        }

        AppendSystemMessage("Generating scene for map " + BackendConfig.EncounterMapId + "...");
        SceneGenerationResult result = await sceneApiService.GenerateSceneAsync(prompt);
        ApplySceneResult(result);

        if (result.success)
        {
            AppendSystemMessage("New scene generated: " + result.sceneName + " (" + result.source + ")");
        }
        else
        {
            AppendSystemMessage("Scene generation failed: " + result.description);
        }
    }

    private void ApplySceneResult(SceneGenerationResult result)
    {
        if (result == null)
        {
            return;
        }

        if (sceneTitleText != null) sceneTitleText.text = "Current Scene";
        if (sceneDescriptionText != null) sceneDescriptionText.text = result.description;
        if (scenePreviewLabelText != null) scenePreviewLabelText.text = result.sceneName;
        if (scenePreviewImage != null)
        {
            if (result.imageBytes != null && result.imageBytes.Length > 0)
            {
                if (currentSceneTexture != null)
                {
                    Destroy(currentSceneTexture);
                }

                currentSceneTexture = new Texture2D(2, 2);
                bool loaded = currentSceneTexture.LoadImage(result.imageBytes);
                if (loaded)
                {
                    Rect rect = new Rect(0, 0, currentSceneTexture.width, currentSceneTexture.height);
                    Sprite sprite = Sprite.Create(currentSceneTexture, rect, new Vector2(0.5f, 0.5f));
                    scenePreviewImage.sprite = sprite;
                    scenePreviewImage.color = Color.white;
                    scenePreviewImage.preserveAspect = true;
                }
                else
                {
                    scenePreviewImage.sprite = null;
                    scenePreviewImage.color = result.previewColor;
                    scenePreviewImage.preserveAspect = true;
                }
            }
            else
            {
                scenePreviewImage.sprite = null;
                scenePreviewImage.color = result.previewColor;
                scenePreviewImage.preserveAspect = true;
            }
        }

        ApplyAmbientPreset(result.ambientPreset);
    }

    private Canvas ResolveUiCanvas()
    {
        if (roomInfoText != null && roomInfoText.canvas != null) return roomInfoText.canvas;
        if (chatLogText != null && chatLogText.canvas != null) return chatLogText.canvas;
        if (scenePromptInput != null)
        {
            Canvas sceneCanvas = scenePromptInput.GetComponentInParent<Canvas>();
            if (sceneCanvas != null) return sceneCanvas;
        }
        if (viewDetailsButton != null)
        {
            Canvas detailCanvas = viewDetailsButton.GetComponentInParent<Canvas>();
            if (detailCanvas != null) return detailCanvas;
        }
        return FindFirstObjectByType<Canvas>();
    }

    private void BuildRuntimeOverlay()
    {
        Canvas canvas = ResolveUiCanvas();
        if (canvas == null)
        {
            return;
        }

        Transform oldStrip = canvas.transform.Find("RuntimeBottomStrip");
        if (oldStrip != null)
        {
            Destroy(oldStrip.gameObject);
        }

        Transform oldStatus = canvas.transform.Find("RuntimeStatusPanel");
        if (oldStatus != null)
        {
            Destroy(oldStatus.gameObject);
        }

        Transform oldAudit = canvas.transform.Find("RuntimeAuditPanel");
        if (oldAudit != null)
        {
            Destroy(oldAudit.gameObject);
        }

        TMP_FontAsset fontAsset = TMP_Settings.defaultFontAsset;
        if (fontAsset == null && chatLogText != null)
        {
            fontAsset = chatLogText.font;
        }

        Transform parent = canvas.transform;

        GameObject strip = CreatePanel("RuntimeBottomStrip", parent, new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0.5f, 0f), new Vector2(0f, 18f), new Vector2(880f, 36f), new Color(0.10f, 0.15f, 0.22f, 0.92f));
        HorizontalLayoutGroup stripLayout = strip.AddComponent<HorizontalLayoutGroup>();
        stripLayout.spacing = 6f;
        stripLayout.padding = new RectOffset(8, 8, 4, 4);
        stripLayout.childForceExpandHeight = true;
        stripLayout.childForceExpandWidth = false;

        modeToggleButton = CreateButton("ModeToggleButton", strip.transform, "Mode: Chat", fontAsset, ToggleInputMode);
        reconnectButton = CreateButton("ReconnectButton", strip.transform, "Reconnect", fontAsset, ReconnectBackend);
        rollD20Button = CreateButton("RollD20Button", strip.transform, "Roll d20", fontAsset, RollQuickD20);
        loadLocalImageButton = CreateButton("LoadLocalImageButton", strip.transform, "Load Local", fontAsset, LoadLocalSceneImage);
        bgmToggleButton = CreateButton("BgmToggleButton", strip.transform, "BGM On", fontAsset, ToggleBgm);
        volumeDownButton = CreateButton("BgmVolumeDownButton", strip.transform, "Vol-", fontAsset, DecreaseBgmVolume);
        volumeUpButton = CreateButton("BgmVolumeUpButton", strip.transform, "Vol+", fontAsset, IncreaseBgmVolume);

        GameObject statusPanel = CreatePanel("RuntimeStatusPanel", parent, new Vector2(1f, 1f), new Vector2(1f, 1f), new Vector2(1f, 1f), new Vector2(-12f, -12f), new Vector2(240f, 56f), new Color(0.08f, 0.12f, 0.18f, 0.88f));
        VerticalLayoutGroup statusLayout = statusPanel.AddComponent<VerticalLayoutGroup>();
        statusLayout.spacing = 4f;
        statusLayout.padding = new RectOffset(8, 8, 6, 6);
        statusLayout.childAlignment = TextAnchor.MiddleLeft;
        statusLayout.childForceExpandHeight = true;
        statusLayout.childForceExpandWidth = true;

        connectionStatusText = CreateLabel("ConnectionStatusText", statusPanel.transform, fontAsset, 18f, TextAlignmentOptions.Left, "Connection: pending");
        modeStatusText = CreateLabel("ModeStatusText", statusPanel.transform, fontAsset, 18f, TextAlignmentOptions.Left, "Input Mode: Chat");

        GameObject auditPanel = CreatePanel("RuntimeAuditPanel", parent, new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(0f, 1f), new Vector2(254f, -96f), new Vector2(332f, 150f), new Color(0.11f, 0.15f, 0.22f, 0.94f));
        VerticalLayoutGroup auditLayout = auditPanel.AddComponent<VerticalLayoutGroup>();
        auditLayout.spacing = 4f;
        auditLayout.padding = new RectOffset(8, 8, 6, 6);
        auditLayout.childAlignment = TextAnchor.UpperLeft;
        auditLayout.childForceExpandHeight = false;
        auditLayout.childForceExpandWidth = true;

        CreateLabel("AuditPanelTitle", auditPanel.transform, fontAsset, 17f, TextAlignmentOptions.Left, "Character Audit");
        auditStatusText = CreateLabel("AuditStatusText", auditPanel.transform, fontAsset, 13f, TextAlignmentOptions.TopLeft, "Waiting for audit...");

        GameObject auditButtonRow = new GameObject("AuditButtonRow", typeof(RectTransform));
        auditButtonRow.transform.SetParent(auditPanel.transform, false);
        HorizontalLayoutGroup auditButtonLayout = auditButtonRow.AddComponent<HorizontalLayoutGroup>();
        auditButtonLayout.spacing = 4f;
        auditButtonLayout.childForceExpandHeight = true;
        auditButtonLayout.childForceExpandWidth = true;

        approveAuditButton = CreateButton("ApproveAuditButton", auditButtonRow.transform, "Approve", fontAsset, () => SubmitAuditDecision("Approved"));
        rejectAuditButton = CreateButton("RejectAuditButton", auditButtonRow.transform, "Reject", fontAsset, () => SubmitAuditDecision("Rejected"));
        requestChangesButton = CreateButton("RequestChangesAuditButton", auditButtonRow.transform, "Changes", fontAsset, () => SubmitAuditDecision("Request Changes"));

        ApplyAuditButtonStyle(approveAuditButton, 100f, 24f, 11f);
        ApplyAuditButtonStyle(rejectAuditButton, 100f, 24f, 11f);
        ApplyAuditButtonStyle(requestChangesButton, 100f, 24f, 11f);

        SetAuditButtonsVisible(RoomSessionContext.IsDM);
    }

    private void ApplyAuditButtonStyle(Button button, float width, float height, float fontSize)
    {
        if (button == null)
        {
            return;
        }

        LayoutElement layout = button.GetComponent<LayoutElement>();
        if (layout != null)
        {
            layout.preferredWidth = width;
            layout.preferredHeight = height;
            layout.minWidth = width;
            layout.minHeight = height;
            layout.flexibleWidth = 0f;
        }

        RectTransform rect = button.GetComponent<RectTransform>();
        if (rect != null)
        {
            rect.sizeDelta = new Vector2(width, height);
        }

        TextMeshProUGUI label = button.GetComponentInChildren<TextMeshProUGUI>();
        if (label != null)
        {
            label.fontSize = fontSize;
            label.enableWordWrapping = false;
            label.overflowMode = TextOverflowModes.Ellipsis;
        }
    }

    private GameObject CreatePanel(string name, Transform parent, Vector2 anchorMin, Vector2 anchorMax, Vector2 pivot, Vector2 anchoredPosition, Vector2 size, Color color)
    {
        GameObject panel = new GameObject(name, typeof(RectTransform), typeof(Image));
        panel.transform.SetParent(parent, false);
        RectTransform rect = panel.GetComponent<RectTransform>();
        rect.anchorMin = anchorMin;
        rect.anchorMax = anchorMax;
        rect.pivot = pivot;
        rect.sizeDelta = size;
        rect.anchoredPosition = anchoredPosition;
        Image image = panel.GetComponent<Image>();
        image.color = color;
        return panel;
    }

    private Button CreateButton(string name, Transform parent, string label, TMP_FontAsset fontAsset, UnityAction action)
    {
        GameObject buttonObject = new GameObject(name, typeof(RectTransform), typeof(Image), typeof(Button), typeof(LayoutElement));
        buttonObject.transform.SetParent(parent, false);
        buttonObject.GetComponent<Image>().color = new Color(0.18f, 0.26f, 0.38f, 1f);
        LayoutElement layout = buttonObject.GetComponent<LayoutElement>();
        layout.preferredWidth = 110f;
        layout.preferredHeight = 28f;

        Button button = buttonObject.GetComponent<Button>();
        button.onClick.AddListener(action);

        GameObject labelObject = new GameObject("Label", typeof(RectTransform));
        labelObject.transform.SetParent(buttonObject.transform, false);
        RectTransform labelRect = labelObject.GetComponent<RectTransform>();
        labelRect.anchorMin = Vector2.zero;
        labelRect.anchorMax = Vector2.one;
        labelRect.offsetMin = Vector2.zero;
        labelRect.offsetMax = Vector2.zero;

        TextMeshProUGUI text = labelObject.AddComponent<TextMeshProUGUI>();
        text.font = fontAsset;
        text.text = label;
        text.fontSize = 16f;
        text.alignment = TextAlignmentOptions.Center;
        text.color = Color.white;

        return button;
    }

    private TMP_Text CreateLabel(string name, Transform parent, TMP_FontAsset fontAsset, float fontSize, TextAlignmentOptions alignment, string value)
    {
        GameObject textObject = new GameObject(name, typeof(RectTransform), typeof(LayoutElement));
        textObject.transform.SetParent(parent, false);
        LayoutElement layout = textObject.GetComponent<LayoutElement>();
        layout.minHeight = fontSize + 8f;
        layout.preferredHeight = fontSize + 10f;

        TextMeshProUGUI text = textObject.AddComponent<TextMeshProUGUI>();
        text.font = fontAsset;
        text.fontSize = fontSize;
        text.alignment = alignment;
        text.color = Color.white;
        text.text = value;
        text.textWrappingMode = TextWrappingModes.Normal;
        return text;
    }

    private void SetConnectionStatus(string value)
    {
        if (connectionStatusText != null)
        {
            connectionStatusText.text = "Connection: " + value;
        }
    }

    private void ToggleInputMode()
    {
        currentInputMode = currentInputMode == InputMode.Chat ? InputMode.RuleAi : InputMode.Chat;
        UpdateModeUi();
        AppendSystemMessage("Input mode switched to " + (currentInputMode == InputMode.Chat ? "Chat" : "Rule AI") + ".");
    }

    private async void ReconnectBackend()
    {
        AppendSystemMessage("Reconnecting backend...");
        if (webSocketClient != null)
        {
            await webSocketClient.DisconnectAsync();
            webSocketClient = null;
        }

        await InitializeRoomConnectionAsync();
    }

    private void UpdateModeUi()
    {
        string label = currentInputMode == InputMode.Chat ? "Chat" : "Rule AI";

        if (modeStatusText != null)
        {
            modeStatusText.text = "Input Mode: " + label + " | API: " + (BackendConfig.UseMockServices ? "Mock" : "Live");
        }

        if (modeToggleButton != null)
        {
            TMP_Text buttonLabel = modeToggleButton.GetComponentInChildren<TMP_Text>();
            if (buttonLabel != null)
            {
                buttonLabel.text = "Mode: " + label;
            }
        }
    }

    private void InitializeAmbientAudio()
    {
        ambientAudioSource = GetComponent<AudioSource>();
        if (ambientAudioSource == null)
        {
            ambientAudioSource = gameObject.AddComponent<AudioSource>();
        }

        ambientAudioSource.loop = true;
        ambientAudioSource.playOnAwake = false;
        ambientAudioSource.volume = BackendConfig.BgmVolume;
        ApplyAmbientPreset("neutral");

        if (BackendConfig.BgmEnabled)
        {
            ambientAudioSource.Play();
        }
    }

    private void ApplyAmbientPreset(string preset)
    {
        if (ambientAudioSource == null)
        {
            return;
        }

        if (currentAmbientClip != null)
        {
            ambientAudioSource.Stop();
            Destroy(currentAmbientClip);
        }

        currentAmbientClip = CreateAmbientClip(string.IsNullOrEmpty(preset) ? "neutral" : preset);
        ambientAudioSource.clip = currentAmbientClip;
        ambientAudioSource.volume = BackendConfig.BgmVolume;

        if (BackendConfig.BgmEnabled)
        {
            ambientAudioSource.Play();
        }

        UpdateBgmUi();
    }

    private AudioClip CreateAmbientClip(string preset)
    {
        int sampleRate = 22050;
        float durationSeconds = 2.5f;
        int sampleCount = Mathf.RoundToInt(sampleRate * durationSeconds);
        float[] samples = new float[sampleCount];

        float baseFrequency = 110f;
        float overtone = 220f;
        float noiseAmount = 0.02f;

        switch (preset)
        {
            case "alchemy":
                baseFrequency = 175f;
                overtone = 350f;
                noiseAmount = 0.018f;
                break;
            case "rain":
                baseFrequency = 96f;
                overtone = 144f;
                noiseAmount = 0.04f;
                break;
            case "forest":
                baseFrequency = 130f;
                overtone = 260f;
                noiseAmount = 0.015f;
                break;
            case "cave":
                baseFrequency = 70f;
                overtone = 105f;
                noiseAmount = 0.01f;
                break;
            case "town":
                baseFrequency = 150f;
                overtone = 300f;
                noiseAmount = 0.012f;
                break;
        }

        for (int i = 0; i < sampleCount; i++)
        {
            float t = i / (float)sampleRate;
            float wave = Mathf.Sin(2f * Mathf.PI * baseFrequency * t) * 0.12f;
            wave += Mathf.Sin(2f * Mathf.PI * overtone * t) * 0.05f;
            wave += (UnityEngine.Random.value * 2f - 1f) * noiseAmount;
            samples[i] = wave;
        }

        AudioClip clip = AudioClip.Create("Ambient_" + preset, sampleCount, 1, sampleRate, false);
        clip.SetData(samples, 0);
        return clip;
    }

    private void ToggleBgm()
    {
        BackendConfig.BgmEnabled = !BackendConfig.BgmEnabled;

        if (ambientAudioSource != null)
        {
            if (BackendConfig.BgmEnabled)
            {
                ambientAudioSource.volume = BackendConfig.BgmVolume;
                ambientAudioSource.Play();
            }
            else
            {
                ambientAudioSource.Stop();
            }
        }

        UpdateBgmUi();
        AppendSystemMessage("BGM " + (BackendConfig.BgmEnabled ? "enabled" : "disabled") + ".");
    }

    private void IncreaseBgmVolume()
    {
        BackendConfig.BgmVolume = Mathf.Clamp01(BackendConfig.BgmVolume + 0.1f);
        if (ambientAudioSource != null)
        {
            ambientAudioSource.volume = BackendConfig.BgmVolume;
        }
        UpdateBgmUi();
    }

    private void DecreaseBgmVolume()
    {
        BackendConfig.BgmVolume = Mathf.Clamp01(BackendConfig.BgmVolume - 0.1f);
        if (ambientAudioSource != null)
        {
            ambientAudioSource.volume = BackendConfig.BgmVolume;
        }
        UpdateBgmUi();
    }

    private void UpdateBgmUi()
    {
        if (bgmToggleButton != null)
        {
            TMP_Text label = bgmToggleButton.GetComponentInChildren<TMP_Text>();
            if (label != null)
            {
                int volumePercent = Mathf.RoundToInt(BackendConfig.BgmVolume * 100f);
                label.text = BackendConfig.BgmEnabled ? "BGM " + volumePercent + "%" : "BGM Off";
            }
        }
    }

    private async System.Threading.Tasks.Task RefreshAuditPanelAsync()
    {
        CharacterData character = GetUploadedOrSelectedCharacter();

        if (character != null && character.id == UploadWorkflowContext.UploadedCharacterId && UploadWorkflowContext.LastAuditResult != null)
        {
            currentAuditResult = UploadWorkflowContext.LastAuditResult;
        }
        else
        {
            currentAuditResult = await characterApiService.AuditCharacterAsync(character);
        }

        UpdateAuditUi(character, currentAuditResult);
    }

    private void UpdateAuditUi(CharacterData character, CharacterAuditResult audit)
    {
        if (auditStatusText == null)
        {
            return;
        }

        string characterName = character != null ? character.characterName : "No Character";
        string status = audit != null ? audit.status : "Unavailable";
        string summary = audit != null ? audit.summary : "No audit data.";
        string issues = audit != null ? audit.issues : "-";
        string uploadSummary = UploadWorkflowContext.LastUploadResult != null && character != null && character.id == UploadWorkflowContext.UploadedCharacterId
            ? UploadWorkflowContext.LastUploadResult.summary
            : "No pending upload record.";

        string shortUploadSummary = uploadSummary;
        if (!string.IsNullOrWhiteSpace(shortUploadSummary) && shortUploadSummary.Length > 48)
        {
            shortUploadSummary = shortUploadSummary.Substring(0, 45) + "...";
        }

        string shortIssues = string.IsNullOrWhiteSpace(issues) ? "-" : issues.Replace("\r", " ").Replace("\n", " | ");
        if (shortIssues.Length > 84)
        {
            shortIssues = shortIssues.Substring(0, 81) + "...";
        }

        auditStatusText.text =
            "Character: " + characterName +
            "\nStatus: " + status +
            "\nSummary: " + summary +
            "\nUpload: " + shortUploadSummary +
            "\nIssues: " + shortIssues;

        bool showDecisionButtons = RoomSessionContext.IsDM && character != null;
        SetAuditButtonsVisible(showDecisionButtons);
    }

    private void SetAuditButtonsVisible(bool visible)
    {
        if (approveAuditButton != null) approveAuditButton.gameObject.SetActive(visible);
        if (rejectAuditButton != null) rejectAuditButton.gameObject.SetActive(visible);
        if (requestChangesButton != null) requestChangesButton.gameObject.SetActive(visible);
    }

    private async void SubmitAuditDecision(string decision)
    {
        CharacterData character = GetUploadedOrSelectedCharacter();
        currentAuditResult = await characterApiService.SubmitDecisionAsync(character, decision);
        UpdateAuditUi(character, currentAuditResult);
        AppendSystemMessage(currentAuditResult != null && currentAuditResult.success
            ? "Audit decision submitted: " + decision + "."
            : "Audit decision failed: " + (currentAuditResult != null ? currentAuditResult.summary : "unknown error") + ".");
    }

    public async void SendChatMessage()
    {
        if (chatInput == null)
        {
            return;
        }

        string message = chatInput.text.Trim();
        if (string.IsNullOrEmpty(message))
        {
            return;
        }

        chatInput.text = string.Empty;
        chatInput.ActivateInputField();

        if (HandleLocalCommand(message))
        {
            return;
        }

        if (currentInputMode == InputMode.RuleAi)
        {
            AppendSystemMessage("Rule AI is thinking...");
            string activeCharacterId = GetUploadedOrSelectedCharacter() != null ? GetUploadedOrSelectedCharacter().id : null;
            string answer = await ruleAiApiService.AskRuleAsync(message, activeCharacterId);
            AppendRuleAiMessage(answer);
            return;
        }

        if (webSocketClient != null && webSocketClient.IsConnected)
        {
            await webSocketClient.SendMessageAsync(new RoomMessage
            {
                type = "chat",
                sender = BackendConfig.OwnerId,
                content = message
            });
        }
        else
        {
            AppendChatMessage(BackendConfig.OwnerId, message);
        }
    }

    private bool HandleLocalCommand(string message)
    {
        if (HandleAdvancedLocalCommand(message))
        {
            return true;
        }

        if (message.StartsWith("/rule ", StringComparison.OrdinalIgnoreCase))
        {
            currentInputMode = InputMode.RuleAi;
            UpdateModeUi();
            string question = message.Substring(6).Trim();
            if (!string.IsNullOrEmpty(question))
            {
                AppendSystemMessage("Rule AI mode activated from command.");
                chatInput.text = question;
                SendChatMessage();
            }
            return true;
        }

        if (message.StartsWith("/roll ", StringComparison.OrdinalIgnoreCase))
        {
            string notation = message.Substring(6).Trim();
            RollDice(notation);
            return true;
        }

        if (message.Equals("/d20", StringComparison.OrdinalIgnoreCase))
        {
            RollQuickD20();
            return true;
        }

        if (message.StartsWith("/load ", StringComparison.OrdinalIgnoreCase))
        {
            string path = message.Substring(6).Trim();
            LoadLocalSceneImageFromPath(path);
            return true;
        }

        if (message.Equals("/reconnect", StringComparison.OrdinalIgnoreCase))
        {
            ReconnectBackend();
            return true;
        }

        if (message.StartsWith("/mock ", StringComparison.OrdinalIgnoreCase))
        {
            string value = message.Substring(6).Trim().ToLowerInvariant();
            BackendConfig.UseMockServices = value != "off" && value != "false" && value != "0";
            AppendSystemMessage("Mock services " + (BackendConfig.UseMockServices ? "enabled" : "disabled") + ".");
            return true;
        }

        if (message.StartsWith("/backend ", StringComparison.OrdinalIgnoreCase))
        {
            string value = message.Substring(9).Trim();
            string[] parts = value.Split(':');
            if (parts.Length == 2 && int.TryParse(parts[1], out int parsedPort))
            {
                BackendConfig.HttpHost = parts[0];
                BackendConfig.HttpPort = parsedPort;
                BackendConfig.WsHost = parts[0];
                BackendConfig.WsPort = parsedPort;
                AppendSystemMessage("HTTP backend set to " + BackendConfig.HttpHost + ":" + BackendConfig.HttpPort + ". WS endpoint synced to the same host and port.");
                ReconnectBackend();
            }
            else
            {
                AppendSystemMessage("Use /backend host:port  e.g. /backend 127.0.0.1:8000");
            }
            return true;
        }

        if (message.StartsWith("/ws ", StringComparison.OrdinalIgnoreCase))
        {
            string value = message.Substring(4).Trim();
            string[] parts = value.Split(':');
            if (parts.Length == 2 && int.TryParse(parts[1], out int parsedWsPort))
            {
                BackendConfig.WsHost = parts[0];
                BackendConfig.WsPort = parsedWsPort;
                AppendSystemMessage("WebSocket endpoint set to " + BackendConfig.WsHost + ":" + BackendConfig.WsPort + ".");
                ReconnectBackend();
            }
            else
            {
                AppendSystemMessage("Use /ws host:port  e.g. /ws 127.0.0.1:8000");
            }
            return true;
        }

        if (message.StartsWith("/owner ", StringComparison.OrdinalIgnoreCase))
        {
            BackendConfig.OwnerId = message.Substring(7).Trim();
            RoomSessionContext.SetSession(RoomSessionContext.roomId, RoomSessionContext.role);
            AppendSystemMessage("Owner ID set to " + BackendConfig.OwnerId + ".");
            return true;
        }

        if (message.StartsWith("/map ", StringComparison.OrdinalIgnoreCase))
        {
            BackendConfig.EncounterMapId = message.Substring(5).Trim();
            AppendSystemMessage("Encounter map id set to " + BackendConfig.EncounterMapId + ".");
            return true;
        }

        if (message.Equals("/help", StringComparison.OrdinalIgnoreCase))
        {
            AppendSystemMessage("Commands: /help, /status, /rule <question>, /roll <dice>, /d20, /scene <prompt>, /load <path>, /audit, /reconnect, /backend host:port, /ws host:port, /owner <id>, /map <id>, /mock on|off, /home.");
            return true;
        }

        if (message.Equals("/status", StringComparison.OrdinalIgnoreCase))
        {
            string socketState = webSocketClient != null && webSocketClient.IsConnected ? "connected" : "offline";
            AppendSystemMessage("HTTP=" + BackendConfig.HttpHost + ":" + BackendConfig.HttpPort + " | WS=" + BackendConfig.WsHost + ":" + BackendConfig.WsPort + " | owner=" + BackendConfig.OwnerId + " | map=" + BackendConfig.EncounterMapId + " | mock=" + (BackendConfig.UseMockServices ? "on" : "off") + " | socket=" + socketState + " | mode=" + (currentInputMode == InputMode.Chat ? "Chat" : "Rule AI") + ".");
            return true;
        }

        if (message.Equals("/audit", StringComparison.OrdinalIgnoreCase))
        {
            _ = RefreshAuditPanelAsync();
            AppendSystemMessage("Audit refresh requested.");
            return true;
        }

        if (message.StartsWith("/scene ", StringComparison.OrdinalIgnoreCase))
        {
            if (scenePromptInput != null)
            {
                scenePromptInput.text = message.Substring(7).Trim();
            }
            GenerateSceneFromBackend();
            return true;
        }

        if (message.Equals("/home", StringComparison.OrdinalIgnoreCase))
        {
            ReturnToHomeScene();
            return true;
        }

        return false;
    }

    private void AppendChatMessage(string sender, string message)
    {
        AddLogLine((string.IsNullOrEmpty(sender) ? "Player" : sender) + ": " + (message ?? string.Empty));
    }

    private void AppendRuleAiMessage(string message)
    {
        AddLogLine("Rule AI: " + message);
    }

    private void AppendSystemMessage(string message)
    {
        AddLogLine("System: " + message);
    }

    private void JumpLogToLatest()
    {
        followLatestLog = true;
        logViewStartIndex = Mathf.Max(0, fullLogLines.Count - VisibleLogLineCount);
        RenderChatLog();
    }

    private void SetLogWindowStart(int requestedStart)
    {
        int maxStart = Mathf.Max(0, fullLogLines.Count - VisibleLogLineCount);
        logViewStartIndex = Mathf.Clamp(requestedStart, 0, maxStart);
        followLatestLog = logViewStartIndex >= maxStart;
        RenderChatLog();
    }

    private void RenderChatLog()
    {
        if (chatLogText == null)
        {
            return;
        }

        int maxStart = Mathf.Max(0, fullLogLines.Count - VisibleLogLineCount);
        if (followLatestLog)
        {
            logViewStartIndex = maxStart;
        }
        else
        {
            logViewStartIndex = Mathf.Clamp(logViewStartIndex, 0, maxStart);
        }

        int availableCount = Mathf.Max(0, fullLogLines.Count - logViewStartIndex);
        int visibleCount = Mathf.Min(VisibleLogLineCount, availableCount);
        List<string> visibleLines = visibleCount > 0
            ? fullLogLines.GetRange(logViewStartIndex, visibleCount)
            : new List<string>();

        for (int i = 0; i < visibleLines.Count; i++)
        {
            visibleLines[i] = CompactLogLineForDisplay(visibleLines[i]);
        }

        chatLogText.text = string.Join("\n", visibleLines.ToArray());
    }

    private void AddLogLine(string line)
    {
        if (string.IsNullOrEmpty(line))
        {
            return;
        }

        fullLogLines.Add(line);
        if (fullLogLines.Count > 120)
        {
            fullLogLines.RemoveAt(0);
            if (logViewStartIndex > 0)
            {
                logViewStartIndex--;
            }
        }

        if (followLatestLog)
        {
            JumpLogToLatest();
        }
        else
        {
            RenderChatLog();
        }
    }

    private string CompactLogLineForDisplay(string value)
    {
        if (string.IsNullOrWhiteSpace(value))
        {
            return string.Empty;
        }

        string compact = value.Replace("\r", " ").Replace("\n", " ").Trim();
        compact = Regex.Replace(compact, @"\s+", " ");

        if (MaxDisplayedLineLength > 0 && compact.Length > MaxDisplayedLineLength)
        {
            compact = compact.Substring(0, MaxDisplayedLineLength - 3) + "...";
        }

        return compact;
    }

    private async void AutoReconnectIfNeeded()
    {
        if (Time.unscaledTime < nextReconnectAttemptTime)
        {
            return;
        }

        if (webSocketClient != null && webSocketClient.IsConnected)
        {
            nextReconnectAttemptTime = Time.unscaledTime + 10f;
            return;
        }

        nextReconnectAttemptTime = Time.unscaledTime + 8f;

        if (BackendConfig.UseMockServices)
        {
            return;
        }

        BackendProbeResult probe = await roomApiService.ProbeBackendAsync();
        if (!probe.reachable)
        {
            SetConnectionStatus("Offline");
            return;
        }

        AppendSystemMessage("Auto reconnect attempt...");
        await InitializeRoomConnectionAsync();
    }

    private void RollQuickD20()
    {
        RollDice("d20");
    }

    private void RollDice(string notation)
    {
        int diceCount;
        int faces;
        int modifier;

        if (!TryParseDiceNotation(notation, out diceCount, out faces, out modifier))
        {
            AppendSystemMessage("Invalid dice notation. Use formats like d20, 2d6, 1d8+3.");
            return;
        }

        List<int> rolls = new List<int>();
        int total = modifier;

        for (int i = 0; i < diceCount; i++)
        {
            int roll = UnityEngine.Random.Range(1, faces + 1);
            rolls.Add(roll);
            total += roll;
        }

        string modifierText = modifier == 0 ? string.Empty : (modifier > 0 ? " + " + modifier : " - " + Mathf.Abs(modifier));
        AppendSystemMessage(RoomSessionContext.role + " rolled " + notation + " -> [" + string.Join(", ", rolls.ConvertAll(v => v.ToString()).ToArray()) + "]" + modifierText + " = " + total);
    }

    private bool TryParseDiceNotation(string notation, out int diceCount, out int faces, out int modifier)
    {
        diceCount = 0;
        faces = 0;
        modifier = 0;

        if (string.IsNullOrWhiteSpace(notation))
        {
            return false;
        }

        Match match = Regex.Match(notation.Trim().ToLowerInvariant(), @"^(\d*)d(\d+)([\+\-]\d+)?$");
        if (!match.Success)
        {
            return false;
        }

        diceCount = string.IsNullOrEmpty(match.Groups[1].Value) ? 1 : int.Parse(match.Groups[1].Value);
        faces = int.Parse(match.Groups[2].Value);
        modifier = string.IsNullOrEmpty(match.Groups[3].Value) ? 0 : int.Parse(match.Groups[3].Value);
        return diceCount > 0 && faces > 1;
    }

    private void LoadLocalSceneImage()
    {
        string path = string.Empty;

#if UNITY_EDITOR
        path = UnityEditor.EditorUtility.OpenFilePanel("Select Scene Image", "", "png,jpg,jpeg");
#endif

        if (string.IsNullOrWhiteSpace(path) && scenePromptInput != null)
        {
            path = scenePromptInput.text.Trim();
            if (path.StartsWith("file:", StringComparison.OrdinalIgnoreCase))
            {
                path = path.Substring(5).Trim();
            }
        }

        LoadLocalSceneImageFromPath(path);
    }

    private void LoadLocalSceneImageFromPath(string path)
    {
        if (string.IsNullOrWhiteSpace(path))
        {
            AppendSystemMessage("No local image selected. In builds, type the file path into the scene prompt box or use /load <path>.");
            return;
        }

        if (!File.Exists(path))
        {
            AppendSystemMessage("Local image not found: " + path);
            return;
        }

        try
        {
            byte[] bytes = File.ReadAllBytes(path);

            if (currentSceneTexture != null)
            {
                Destroy(currentSceneTexture);
            }

            currentSceneTexture = new Texture2D(2, 2);
            bool loaded = currentSceneTexture.LoadImage(bytes);

            if (!loaded)
            {
                AppendSystemMessage("Failed to decode selected image.");
                return;
            }

            if (scenePreviewImage != null)
            {
                Rect rect = new Rect(0, 0, currentSceneTexture.width, currentSceneTexture.height);
                Sprite sprite = Sprite.Create(currentSceneTexture, rect, new Vector2(0.5f, 0.5f));
                scenePreviewImage.sprite = sprite;
                scenePreviewImage.color = Color.white;
                scenePreviewImage.preserveAspect = true;
            }

            if (scenePreviewLabelText != null)
            {
                scenePreviewLabelText.text = Path.GetFileNameWithoutExtension(path);
            }

            if (sceneDescriptionText != null)
            {
                sceneDescriptionText.text = "Loaded local scene image: " + Path.GetFileName(path);
            }

            ApplyAmbientPreset("neutral");
            AppendSystemMessage("Loaded local scene image: " + Path.GetFileName(path));
        }
        catch (Exception ex)
        {
            AppendSystemMessage("Failed to load local image: " + ex.Message);
        }
    }
}
