using System.Collections.Generic;
using System.Threading.Tasks;
using TMPro;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.SceneManagement;
using UnityEngine.UI;
using UnityEngine.EventSystems;

public class WorldMapSceneController : MonoBehaviour
{
    private readonly AdvancedBackendApiService api = new AdvancedBackendApiService();

    private TextMeshProUGUI titleText;
    private TextMeshProUGUI statusText;
    private TextMeshProUGUI descriptionText;
    private Image previewImage;
    private Transform regionListRoot;

    private async void Start()
    {
        BuildUi();
        await RefreshAsync();
    }

    private async Task RefreshAsync()
    {
        string campaignId = RoomSessionContext.roomId;
        titleText.text = "World Map";
        statusText.text = "Loading world map...";
        descriptionText.text = "";
        ClearChildren(regionListRoot);

        WorldMapLite world = await api.GetWorldMapAsync(campaignId);
        List<RegionMapSummaryLite> regions = await api.GetRegionMapsAsync(campaignId);

        if (world == null || !world.success)
        {
            statusText.text = world != null ? world.summary : "World map unavailable.";
        }
        else
        {
            titleText.text = string.IsNullOrWhiteSpace(world.name) ? "World Map" : world.name;
            descriptionText.text = string.IsNullOrWhiteSpace(world.description)
                ? "No description returned by backend."
                : world.description;
            statusText.text = world.summary;
            if (!string.IsNullOrWhiteSpace(world.imageUrl))
            {
                Sprite sprite = await DownloadSpriteAsync(world.imageUrl);
                if (sprite != null)
                {
                    previewImage.sprite = sprite;
                    previewImage.color = Color.white;
                    previewImage.preserveAspect = true;
                }
                else
                {
                    previewImage.color = new Color(0.16f, 0.18f, 0.24f, 1f);
                }
            }
        }

        if (regions == null || regions.Count == 0)
        {
            CreateRegionButton("No region maps returned", false, null);
            return;
        }

        for (int i = 0; i < regions.Count; i++)
        {
            RegionMapSummaryLite region = regions[i];
            string label = string.IsNullOrWhiteSpace(region.regionType)
                ? region.name
                : region.name + "  [" + region.regionType + "]";
            CreateRegionButton(label, true, () => OpenRegion(region.id));
        }
    }

    private void OpenRegion(string regionId)
    {
        MapNavigationContext.SelectedRegionMapId = regionId;
        SceneManager.LoadScene("RegionMapScene");
    }

    private void BackToRoom()
    {
        SceneManager.LoadScene("RoomScene");
    }

    private void BuildUi()
    {
        EnsureEventSystem();
        Canvas canvas = EnsureCanvas();
        TMP_FontAsset font = TMP_Settings.defaultFontAsset;

        GameObject root = CreateUiObject("Root", canvas.transform);
        RectTransform rootRect = root.AddComponent<RectTransform>();
        rootRect.anchorMin = Vector2.zero;
        rootRect.anchorMax = Vector2.one;
        rootRect.offsetMin = new Vector2(20f, 20f);
        rootRect.offsetMax = new Vector2(-20f, -20f);

        VerticalLayoutGroup rootLayout = root.AddComponent<VerticalLayoutGroup>();
        rootLayout.spacing = 12f;
        rootLayout.childControlWidth = true;
        rootLayout.childControlHeight = true;
        rootLayout.childForceExpandWidth = true;
        rootLayout.childForceExpandHeight = false;

        GameObject topBar = CreatePanel("TopBar", root.transform, new Color(0.10f, 0.12f, 0.18f, 0.92f), new Vector2(0f, 72f));
        HorizontalLayoutGroup topLayout = topBar.AddComponent<HorizontalLayoutGroup>();
        topLayout.spacing = 10f;
        topLayout.padding = new RectOffset(16, 16, 12, 12);
        topLayout.childControlWidth = false;
        topLayout.childControlHeight = true;
        topLayout.childForceExpandWidth = false;

        titleText = CreateText("Title", topBar.transform, "World Map", font, 28, FontStyles.Bold);
        LayoutElement titleLayout = titleText.gameObject.AddComponent<LayoutElement>();
        titleLayout.minWidth = 420f;

        CreateButton("Refresh", topBar.transform, "Refresh", font, async () => await RefreshAsync());
        CreateButton("BackRoom", topBar.transform, "Back To Room", font, BackToRoom);

        GameObject body = CreateUiObject("Body", root.transform);
        HorizontalLayoutGroup bodyLayout = body.AddComponent<HorizontalLayoutGroup>();
        bodyLayout.spacing = 12f;
        bodyLayout.childControlWidth = true;
        bodyLayout.childControlHeight = true;
        bodyLayout.childForceExpandWidth = true;
        bodyLayout.childForceExpandHeight = true;
        LayoutElement bodyLE = body.AddComponent<LayoutElement>();
        bodyLE.flexibleHeight = 1f;

        GameObject imagePanel = CreatePanel("ImagePanel", body.transform, new Color(0.08f, 0.10f, 0.15f, 0.94f), Vector2.zero, true);
        LayoutElement imageLE = imagePanel.AddComponent<LayoutElement>();
        imageLE.flexibleWidth = 1.8f;
        previewImage = CreateImage("Preview", imagePanel.transform, new Color(0.16f, 0.18f, 0.24f, 1f));
        Stretch(previewImage.rectTransform, 12f);
        previewImage.preserveAspect = true;

        GameObject rightPanel = CreatePanel("RightPanel", body.transform, new Color(0.10f, 0.12f, 0.18f, 0.94f), Vector2.zero, true);
        LayoutElement rightLE = rightPanel.AddComponent<LayoutElement>();
        rightLE.preferredWidth = 380f;
        rightLE.flexibleWidth = 0.8f;
        VerticalLayoutGroup rightLayout = rightPanel.AddComponent<VerticalLayoutGroup>();
        rightLayout.spacing = 10f;
        rightLayout.padding = new RectOffset(14, 14, 14, 14);
        rightLayout.childControlWidth = true;
        rightLayout.childControlHeight = false;
        rightLayout.childForceExpandHeight = false;

        statusText = CreateText("Status", rightPanel.transform, "Status", font, 20, FontStyles.Bold);
        descriptionText = CreateText("Description", rightPanel.transform, "", font, 18, FontStyles.Normal);
        descriptionText.textWrappingMode = TextWrappingModes.Normal;
        LayoutElement descLE = descriptionText.gameObject.AddComponent<LayoutElement>();
        descLE.minHeight = 120f;

        TextMeshProUGUI regionHeader = CreateText("RegionHeader", rightPanel.transform, "Regions", font, 22, FontStyles.Bold);
        regionHeader.margin = new Vector4(0, 10, 0, 6);

        GameObject scroll = CreatePanel("RegionScroll", rightPanel.transform, new Color(0.06f, 0.08f, 0.12f, 0.95f), Vector2.zero, true);
        LayoutElement scrollLE = scroll.AddComponent<LayoutElement>();
        scrollLE.flexibleHeight = 1f;
        scrollLE.minHeight = 260f;
        ScrollRect scrollRect = scroll.AddComponent<ScrollRect>();
        scrollRect.horizontal = false;

        GameObject viewport = CreateUiObject("Viewport", scroll.transform);
        RectTransform viewportRect = viewport.AddComponent<RectTransform>();
        Stretch(viewportRect, 6f);
        Image viewportImage = viewport.AddComponent<Image>();
        viewportImage.color = new Color(1f, 1f, 1f, 0.02f);
        Mask mask = viewport.AddComponent<Mask>();
        mask.showMaskGraphic = false;

        GameObject content = CreateUiObject("Content", viewport.transform);
        RectTransform contentRect = content.AddComponent<RectTransform>();
        contentRect.anchorMin = new Vector2(0f, 1f);
        contentRect.anchorMax = new Vector2(1f, 1f);
        contentRect.pivot = new Vector2(0.5f, 1f);
        contentRect.anchoredPosition = Vector2.zero;
        contentRect.sizeDelta = new Vector2(0f, 0f);
        VerticalLayoutGroup contentLayout = content.AddComponent<VerticalLayoutGroup>();
        contentLayout.spacing = 8f;
        contentLayout.padding = new RectOffset(8, 8, 8, 8);
        contentLayout.childControlWidth = true;
        contentLayout.childControlHeight = true;
        contentLayout.childForceExpandHeight = false;
        ContentSizeFitter fitter = content.AddComponent<ContentSizeFitter>();
        fitter.verticalFit = ContentSizeFitter.FitMode.PreferredSize;

        scrollRect.viewport = viewportRect;
        scrollRect.content = contentRect;
        regionListRoot = content.transform;
    }

    private void CreateRegionButton(string label, bool interactable, UnityEngine.Events.UnityAction onClick)
    {
        TMP_FontAsset font = TMP_Settings.defaultFontAsset;
        Button button = CreateButton("RegionButton", regionListRoot, label, font, onClick);
        button.interactable = interactable;
        LayoutElement le = button.gameObject.AddComponent<LayoutElement>();
        le.minHeight = 48f;
    }

    private async Task<Sprite> DownloadSpriteAsync(string url)
    {
        using (UnityWebRequest req = UnityWebRequestTexture.GetTexture(url))
        {
            var op = req.SendWebRequest();
            while (!op.isDone)
            {
                await Task.Yield();
            }

#if UNITY_2020_1_OR_NEWER
            if (req.result != UnityWebRequest.Result.Success)
#else
            if (req.isNetworkError || req.isHttpError)
#endif
            {
                Debug.Log("[WorldMapSceneController] image load failed: " + req.error + " | " + url);
                return null;
            }

            Texture2D tex = DownloadHandlerTexture.GetContent(req);
            if (tex == null) return null;
            return Sprite.Create(tex, new Rect(0, 0, tex.width, tex.height), new Vector2(0.5f, 0.5f));
        }
    }

    private static void ClearChildren(Transform root)
    {
        if (root == null) return;
        for (int i = root.childCount - 1; i >= 0; i--)
        {
            Destroy(root.GetChild(i).gameObject);
        }
    }

    private static Canvas EnsureCanvas()
    {
        Canvas existing = Object.FindFirstObjectByType<Canvas>();
        if (existing != null) return existing;

        GameObject go = new GameObject("Canvas", typeof(Canvas), typeof(CanvasScaler), typeof(GraphicRaycaster));
        Canvas canvas = go.GetComponent<Canvas>();
        canvas.renderMode = RenderMode.ScreenSpaceOverlay;
        CanvasScaler scaler = go.GetComponent<CanvasScaler>();
        scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
        scaler.referenceResolution = new Vector2(1920f, 1080f);
        return canvas;
    }

    private static void EnsureEventSystem()
    {
        if (Object.FindFirstObjectByType<EventSystem>() != null) return;
        new GameObject("EventSystem", typeof(EventSystem), typeof(StandaloneInputModule));
    }

    private static GameObject CreateUiObject(string name, Transform parent)
    {
        GameObject go = new GameObject(name);
        go.transform.SetParent(parent, false);
        return go;
    }

    private static GameObject CreatePanel(string name, Transform parent, Color color, Vector2 size, bool stretch = false)
    {
        GameObject go = CreateUiObject(name, parent);
        RectTransform rt = go.AddComponent<RectTransform>();
        if (stretch)
        {
            rt.anchorMin = Vector2.zero;
            rt.anchorMax = Vector2.one;
            rt.offsetMin = Vector2.zero;
            rt.offsetMax = Vector2.zero;
        }
        else
        {
            rt.sizeDelta = size;
        }
        Image img = go.AddComponent<Image>();
        img.color = color;
        return go;
    }

    private static TextMeshProUGUI CreateText(string name, Transform parent, string text, TMP_FontAsset font, float size, FontStyles style)
    {
        GameObject go = CreateUiObject(name, parent);
        TextMeshProUGUI tmp = go.AddComponent<TextMeshProUGUI>();
        tmp.text = text;
        tmp.font = font;
        tmp.fontSize = size;
        tmp.fontStyle = style;
        tmp.color = Color.white;
        tmp.textWrappingMode = TextWrappingModes.Normal;
        return tmp;
    }

    private static Button CreateButton(string name, Transform parent, string label, TMP_FontAsset font, UnityEngine.Events.UnityAction onClick)
    {
        GameObject go = CreateUiObject(name, parent);
        Image img = go.AddComponent<Image>();
        img.color = new Color(0.20f, 0.28f, 0.42f, 1f);
        Button btn = go.AddComponent<Button>();
        btn.onClick.AddListener(onClick);

        RectTransform rt = go.GetComponent<RectTransform>();
        rt.sizeDelta = new Vector2(180f, 44f);

        GameObject labelGo = CreateUiObject("Label", go.transform);
        RectTransform labelRt = labelGo.AddComponent<RectTransform>();
        Stretch(labelRt, 0f);
        TextMeshProUGUI tmp = labelGo.AddComponent<TextMeshProUGUI>();
        tmp.text = label;
        tmp.font = font;
        tmp.fontSize = 18;
        tmp.color = Color.white;
        tmp.alignment = TextAlignmentOptions.Center;
        return btn;
    }

    private static Image CreateImage(string name, Transform parent, Color color)
    {
        GameObject go = CreateUiObject(name, parent);
        Image img = go.AddComponent<Image>();
        img.color = color;
        return img;
    }

    private static void Stretch(RectTransform rt, float padding)
    {
        rt.anchorMin = Vector2.zero;
        rt.anchorMax = Vector2.one;
        rt.offsetMin = new Vector2(padding, padding);
        rt.offsetMax = new Vector2(-padding, -padding);
    }
}
