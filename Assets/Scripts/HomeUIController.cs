using TMPro;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.SceneManagement;
using UnityEngine.UI;

public class HomeUIController : MonoBehaviour
{
    public InputField roomInput;
    public Dropdown roleDropdown;
    public GameObject settingsPanel;

    private readonly RoomApiService roomApiService = new RoomApiService();

    private bool settingsUiBuilt;
    private InputField httpHostInput;
    private InputField httpPortInput;
    private InputField wsHostInput;
    private InputField wsPortInput;
    private InputField ownerIdInput;
    private InputField mapIdInput;
    private Toggle useMockToggle;
    private TMP_Text settingsStatusText;

    private void Start()
    {
        AutoBindReferences();

        bool settingsInitiallyActive = settingsPanel != null && settingsPanel.activeSelf;
        if (settingsPanel != null && !settingsInitiallyActive)
        {
            settingsPanel.SetActive(true);
        }

        EnsureSettingsUiBuilt();
        RefreshSettingsUiFromConfig();
        ForceRebuildSettingsLayout();

        if (settingsPanel != null && !settingsInitiallyActive)
        {
            settingsPanel.SetActive(false);
        }

        if (roomInput != null && string.IsNullOrWhiteSpace(roomInput.text))
        {
            roomInput.text = RoomSessionContext.roomId;
        }
    }

    private void Update()
    {
        Keyboard keyboard = Keyboard.current;
        if (keyboard == null)
        {
            return;
        }

        if (settingsPanel != null && settingsPanel.activeSelf && keyboard.escapeKey.wasPressedThisFrame)
        {
            CloseSettings();
            return;
        }

        if (keyboard.enterKey.wasPressedThisFrame || keyboard.numpadEnterKey.wasPressedThisFrame)
        {
            bool typingInInput = roomInput != null && roomInput.isFocused;
            if (!typingInInput && (settingsPanel == null || !settingsPanel.activeSelf))
            {
                EnterRoom();
            }
        }
    }

    public async void EnterRoom()
    {
        string roomId = roomInput != null ? roomInput.text.Trim() : string.Empty;
        if (string.IsNullOrEmpty(roomId))
        {
            roomId = "ROOM-001";
        }

        string role = "Player";
        if (roleDropdown != null && roleDropdown.options != null && roleDropdown.options.Count > 0)
        {
            role = roleDropdown.options[roleDropdown.value].text;
        }

        ApplyBackendSettings();
        RoomSessionContext.SetSession(roomId, role);
        await roomApiService.JoinRoomAsync(roomId, role);
        SceneManager.LoadScene("RoomScene");
    }

    public void OpenSettings()
    {
        EnsureSettingsUiBuilt();
        RefreshSettingsUiFromConfig();

        if (settingsPanel != null)
        {
            settingsPanel.SetActive(true);
            ForceRebuildSettingsLayout();
        }
    }

    public void CloseSettings()
    {
        if (settingsPanel != null)
        {
            settingsPanel.SetActive(false);
        }
    }

    public void OpenCharacterVault()
    {
        SceneManager.LoadScene("CharacterVaultScene");
    }

    public void ExitGame()
    {
        Application.Quit();
    }

    private void AutoBindReferences()
    {
        if (roomInput == null) roomInput = FindComponentByName<InputField>("RoomInput");
        if (roleDropdown == null) roleDropdown = FindComponentByName<Dropdown>("RoleDropdown");
        if (settingsPanel == null)
        {
            Transform panel = FindTransformByName("SettingsPanel");
            if (panel != null) settingsPanel = panel.gameObject;
        }
    }

    private T FindComponentByName<T>(string objectName) where T : Component
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

    private Transform FindTransformByName(string objectName)
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

    private void ForceRebuildSettingsLayout()
    {
        if (settingsPanel == null)
        {
            return;
        }

        Canvas.ForceUpdateCanvases();

        RectTransform panelRect = settingsPanel.GetComponent<RectTransform>();
        if (panelRect != null)
        {
            LayoutRebuilder.ForceRebuildLayoutImmediate(panelRect);
        }

        Transform runtimeContent = settingsPanel.transform.Find("RuntimeSettingsContent");
        if (runtimeContent != null)
        {
            RectTransform contentRect = runtimeContent.GetComponent<RectTransform>();
            if (contentRect != null)
            {
                LayoutRebuilder.ForceRebuildLayoutImmediate(contentRect);
            }
        }

        Canvas.ForceUpdateCanvases();
    }

    private void EnsureSettingsUiBuilt()
    {
        if (settingsUiBuilt || settingsPanel == null)
        {
            return;
        }

        settingsUiBuilt = true;

        Transform existingContainer = settingsPanel.transform.Find("RuntimeSettingsContent");
        if (existingContainer != null)
        {
            return;
        }

        Font arial = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
        TMP_FontAsset tmpFont = TMP_Settings.defaultFontAsset;

        GameObject container = new GameObject("RuntimeSettingsContent", typeof(RectTransform), typeof(VerticalLayoutGroup));
        container.transform.SetParent(settingsPanel.transform, false);
        RectTransform containerRect = container.GetComponent<RectTransform>();
        containerRect.anchorMin = new Vector2(0f, 0f);
        containerRect.anchorMax = new Vector2(1f, 1f);
        containerRect.offsetMin = new Vector2(28f, 22f);
        containerRect.offsetMax = new Vector2(-28f, -70f);

        VerticalLayoutGroup layout = container.GetComponent<VerticalLayoutGroup>();
        layout.spacing = 6f;
        layout.padding = new RectOffset(0, 0, 30, 0);
        layout.childControlHeight = false;
        layout.childForceExpandHeight = false;
        layout.childControlWidth = true;

        CreateSectionLabel(container.transform, tmpFont, "HTTP Host");
        httpHostInput = CreateInputField(container.transform, arial, "127.0.0.1");
        CreateSectionLabel(container.transform, tmpFont, "HTTP Port");
        httpPortInput = CreateInputField(container.transform, arial, "8000");
        CreateSectionLabel(container.transform, tmpFont, "WS Host");
        wsHostInput = CreateInputField(container.transform, arial, "127.0.0.1");
        CreateSectionLabel(container.transform, tmpFont, "WS Port");
        wsPortInput = CreateInputField(container.transform, arial, "8000");
        CreateSectionLabel(container.transform, tmpFont, "Owner ID");
        ownerIdInput = CreateInputField(container.transform, arial, "Alice#1234");
        CreateSectionLabel(container.transform, tmpFont, "Encounter Map ID");
        mapIdInput = CreateInputField(container.transform, arial, "main");

        useMockToggle = CreateToggle(container.transform, arial, tmpFont, "Use fallback mock services when backend is offline");

        GameObject buttonRow = new GameObject("SettingsButtonRow", typeof(RectTransform), typeof(HorizontalLayoutGroup));
        buttonRow.transform.SetParent(container.transform, false);
        HorizontalLayoutGroup rowLayout = buttonRow.GetComponent<HorizontalLayoutGroup>();
        rowLayout.spacing = 10f;
        rowLayout.childForceExpandWidth = true;
        rowLayout.childForceExpandHeight = false;
        LayoutElement rowElement = buttonRow.AddComponent<LayoutElement>();
        rowElement.preferredHeight = 36f;

        CreateButton(buttonRow.transform, arial, tmpFont, "Apply", ApplyBackendSettings);
        CreateButton(buttonRow.transform, arial, tmpFont, "Test", TestBackendConnection);
        CreateButton(buttonRow.transform, arial, tmpFont, "Same Server", CopyHttpToWs);
        CreateButton(buttonRow.transform, arial, tmpFont, "Reset", ResetBackendSettings);

        settingsStatusText = CreateSectionLabel(container.transform, tmpFont, "Status: backend config ready.");
        settingsStatusText.textWrappingMode = TextWrappingModes.Normal;
        settingsStatusText.fontSize = 18f;
    }

    private TMP_Text CreateSectionLabel(Transform parent, TMP_FontAsset fontAsset, string value)
    {
        GameObject labelObject = new GameObject("RuntimeLabel", typeof(RectTransform));
        labelObject.transform.SetParent(parent, false);
        LayoutElement layout = labelObject.AddComponent<LayoutElement>();
        layout.preferredHeight = 22f;

        TextMeshProUGUI text = labelObject.AddComponent<TextMeshProUGUI>();
        text.font = fontAsset;
        text.fontSize = 20f;
        text.color = Color.white;
        text.alignment = TextAlignmentOptions.Left;
        text.text = value;
        return text;
    }

    private InputField CreateInputField(Transform parent, Font font, string placeholderValue)
    {
        GameObject root = new GameObject("RuntimeInput", typeof(RectTransform), typeof(Image), typeof(InputField));
        root.transform.SetParent(parent, false);
        root.GetComponent<Image>().color = Color.white;
        LayoutElement layout = root.AddComponent<LayoutElement>();
        layout.preferredHeight = 32f;

        RectTransform rootRect = root.GetComponent<RectTransform>();
        rootRect.sizeDelta = new Vector2(0f, 32f);

        GameObject textObject = new GameObject("Text", typeof(RectTransform), typeof(Text));
        textObject.transform.SetParent(root.transform, false);
        RectTransform textRect = textObject.GetComponent<RectTransform>();
        textRect.anchorMin = Vector2.zero;
        textRect.anchorMax = Vector2.one;
        textRect.offsetMin = new Vector2(10f, 6f);
        textRect.offsetMax = new Vector2(-10f, -6f);

        Text text = textObject.GetComponent<Text>();
        text.font = font;
        text.fontSize = 18;
        text.color = new Color(0.12f, 0.12f, 0.12f, 1f);
        text.alignment = TextAnchor.MiddleLeft;

        GameObject placeholderObject = new GameObject("Placeholder", typeof(RectTransform), typeof(Text));
        placeholderObject.transform.SetParent(root.transform, false);
        RectTransform placeholderRect = placeholderObject.GetComponent<RectTransform>();
        placeholderRect.anchorMin = Vector2.zero;
        placeholderRect.anchorMax = Vector2.one;
        placeholderRect.offsetMin = new Vector2(10f, 6f);
        placeholderRect.offsetMax = new Vector2(-10f, -6f);

        Text placeholder = placeholderObject.GetComponent<Text>();
        placeholder.font = font;
        placeholder.fontSize = 18;
        placeholder.color = new Color(0.45f, 0.45f, 0.45f, 1f);
        placeholder.alignment = TextAnchor.MiddleLeft;
        placeholder.text = placeholderValue;

        InputField input = root.GetComponent<InputField>();
        input.textComponent = text;
        input.placeholder = placeholder;
        input.lineType = InputField.LineType.SingleLine;
        return input;
    }

    private Toggle CreateToggle(Transform parent, Font font, TMP_FontAsset tmpFont, string labelValue)
    {
        GameObject root = new GameObject("RuntimeToggle", typeof(RectTransform), typeof(Toggle), typeof(LayoutElement));
        root.transform.SetParent(parent, false);
        root.GetComponent<LayoutElement>().preferredHeight = 28f;
        Toggle toggle = root.GetComponent<Toggle>();

        GameObject background = new GameObject("Background", typeof(RectTransform), typeof(Image));
        background.transform.SetParent(root.transform, false);
        RectTransform backgroundRect = background.GetComponent<RectTransform>();
        backgroundRect.anchorMin = new Vector2(0f, 0.5f);
        backgroundRect.anchorMax = new Vector2(0f, 0.5f);
        backgroundRect.sizeDelta = new Vector2(20f, 20f);
        backgroundRect.anchoredPosition = new Vector2(10f, 0f);
        Image backgroundImage = background.GetComponent<Image>();
        backgroundImage.color = Color.white;

        GameObject checkmark = new GameObject("Checkmark", typeof(RectTransform), typeof(Image));
        checkmark.transform.SetParent(background.transform, false);
        RectTransform checkRect = checkmark.GetComponent<RectTransform>();
        checkRect.anchorMin = new Vector2(0.15f, 0.15f);
        checkRect.anchorMax = new Vector2(0.85f, 0.85f);
        checkRect.offsetMin = Vector2.zero;
        checkRect.offsetMax = Vector2.zero;
        Image checkImage = checkmark.GetComponent<Image>();
        checkImage.color = new Color(0.18f, 0.42f, 0.75f, 1f);

        GameObject labelObject = new GameObject("Label", typeof(RectTransform));
        labelObject.transform.SetParent(root.transform, false);
        RectTransform labelRect = labelObject.GetComponent<RectTransform>();
        labelRect.anchorMin = Vector2.zero;
        labelRect.anchorMax = Vector2.one;
        labelRect.offsetMin = new Vector2(40f, 0f);
        labelRect.offsetMax = new Vector2(0f, 0f);
        TextMeshProUGUI label = labelObject.AddComponent<TextMeshProUGUI>();
        label.font = tmpFont;
        label.fontSize = 18f;
        label.color = Color.white;
        label.alignment = TextAlignmentOptions.Left;
        label.text = labelValue;

        toggle.targetGraphic = backgroundImage;
        toggle.graphic = checkImage;
        return toggle;
    }

    private Button CreateButton(Transform parent, Font font, TMP_FontAsset tmpFont, string labelValue, UnityEngine.Events.UnityAction action)
    {
        GameObject root = new GameObject(labelValue + "Button", typeof(RectTransform), typeof(Image), typeof(Button), typeof(LayoutElement));
        root.transform.SetParent(parent, false);
        root.GetComponent<Image>().color = Color.white;
        root.GetComponent<LayoutElement>().preferredHeight = 34f;

        Button button = root.GetComponent<Button>();
        button.onClick.AddListener(action);

        GameObject labelObject = new GameObject("Label", typeof(RectTransform));
        labelObject.transform.SetParent(root.transform, false);
        RectTransform labelRect = labelObject.GetComponent<RectTransform>();
        labelRect.anchorMin = Vector2.zero;
        labelRect.anchorMax = Vector2.one;
        labelRect.offsetMin = Vector2.zero;
        labelRect.offsetMax = Vector2.zero;

        TextMeshProUGUI label = labelObject.AddComponent<TextMeshProUGUI>();
        label.font = tmpFont;
        label.fontSize = 18f;
        label.color = new Color(0.18f, 0.18f, 0.18f, 1f);
        label.alignment = TextAlignmentOptions.Center;
        label.text = labelValue;

        return button;
    }

    private void RefreshSettingsUiFromConfig()
    {
        if (httpHostInput != null) httpHostInput.text = BackendConfig.HttpHost;
        if (httpPortInput != null) httpPortInput.text = BackendConfig.HttpPort.ToString();
        if (wsHostInput != null) wsHostInput.text = BackendConfig.WsHost;
        if (wsPortInput != null) wsPortInput.text = BackendConfig.WsPort.ToString();
        if (ownerIdInput != null) ownerIdInput.text = BackendConfig.OwnerId;
        if (mapIdInput != null) mapIdInput.text = BackendConfig.EncounterMapId;
        if (useMockToggle != null) useMockToggle.isOn = BackendConfig.UseMockServices;
        if (settingsStatusText != null)
        {
            settingsStatusText.text = "Status: HTTP " + BackendConfig.HttpHost + ":" + BackendConfig.HttpPort +
                                      " | WS " + BackendConfig.WsHost + ":" + BackendConfig.WsPort +
                                      " | owner " + BackendConfig.OwnerId +
                                      " | map " + BackendConfig.EncounterMapId +
                                      " | mocks " + (BackendConfig.UseMockServices ? "on" : "off") + ".";
        }
    }

    private void CopyHttpToWs()
    {
        if (httpHostInput != null && wsHostInput != null) wsHostInput.text = httpHostInput.text;
        if (wsPortInput != null && string.IsNullOrWhiteSpace(wsPortInput.text)) wsPortInput.text = "8000";
        if (settingsStatusText != null) settingsStatusText.text = "Status: copied HTTP host into WS host. Keep WS port at 8000 unless your backend changed it.";
    }

    private void ApplyBackendSettings()
    {
        if (httpHostInput != null) BackendConfig.HttpHost = httpHostInput.text;
        if (httpPortInput != null && int.TryParse(httpPortInput.text, out int httpPort)) BackendConfig.HttpPort = httpPort;
        if (wsHostInput != null) BackendConfig.WsHost = wsHostInput.text;
        if (wsPortInput != null && int.TryParse(wsPortInput.text, out int wsPort)) BackendConfig.WsPort = wsPort;
        if (ownerIdInput != null) BackendConfig.OwnerId = ownerIdInput.text;
        if (mapIdInput != null) BackendConfig.EncounterMapId = mapIdInput.text;
        if (useMockToggle != null) BackendConfig.UseMockServices = useMockToggle.isOn;

        RefreshSettingsUiFromConfig();
        if (settingsStatusText != null)
        {
            settingsStatusText.text += "\nApplied. New room connections will use this config.";
        }
    }

    private async void TestBackendConnection()
    {
        ApplyBackendSettings();
        if (settingsStatusText != null)
        {
            settingsStatusText.text = "Status: testing backend...";
        }

        BackendProbeResult probe = await roomApiService.ProbeBackendAsync();
        if (settingsStatusText != null)
        {
            settingsStatusText.text = probe.reachable
                ? "Status: backend reachable.\n" + probe.summary
                : "Status: backend offline.\n" + probe.summary;
        }
    }

    private void ResetBackendSettings()
    {
        BackendConfig.ResetDefaults();
        RefreshSettingsUiFromConfig();
        if (settingsStatusText != null)
        {
            settingsStatusText.text += "\nReset to default local settings.";
        }
    }
}
