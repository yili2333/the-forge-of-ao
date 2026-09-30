using System.Collections.Generic;
using System.Threading.Tasks;
using TMPro;
using UnityEngine;
using UnityEngine.Networking;
using UnityEngine.SceneManagement;
using UnityEngine.UI;
using UnityEngine.EventSystems;

public class RegionMapSceneController : MonoBehaviour
{
    private readonly AdvancedBackendApiService api = new AdvancedBackendApiService();

    private TextMeshProUGUI titleText;
    private TextMeshProUGUI statusText;
    private TextMeshProUGUI descriptionText;
    private Image previewImage;

    private async void Start()
    {
        BuildUi();
        await RefreshAsync();
    }

    private async Task RefreshAsync()
    {
        string campaignId = RoomSessionContext.roomId;
        string regionId = MapNavigationContext.SelectedRegionMapId;

        if (string.IsNullOrWhiteSpace(regionId))
        {
            List<RegionMapSummaryLite> regions = await api.GetRegionMapsAsync(campaignId);
            if (regions != null && regions.Count > 0)
            {
                regionId = regions[0].id;
                MapNavigationContext.SelectedRegionMapId = regionId;
            }
        }

        if (string.IsNullOrWhiteSpace(regionId))
        {
            statusText.text = "No region map id selected.";
            return;
        }

        titleText.text = "Region Map";
        statusText.text = "Loading region map...";
        descriptionText.text = "";

        RegionMapLite region = await api.GetRegionMapAsync(campaignId, regionId);
        if (region == null || !region.success)
        {
            statusText.text = region != null ? region.summary : "Region map unavailable.";
            return;
        }

        titleText.text = string.IsNullOrWhiteSpace(region.name) ? "Region Map" : region.name;
        statusText.text = region.summary;
        descriptionText.text = BuildDescription(region);

        if (!string.IsNullOrWhiteSpace(region.imageUrl))
        {
            Sprite sprite = await DownloadSpriteAsync(region.imageUrl);
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

    private string BuildDescription(RegionMapLite region)
    {
        string text = string.IsNullOrWhiteSpace(region.description)
            ? "No description returned by backend."
            : region.description;

        if (!string.IsNullOrWhiteSpace(region.regionType))
        {
            text += "\n\nType: " + region.regionType;
        }

        text += "\nPOIs: " + region.poiCount;
        text += "\nRegion ID: " + region.id;
        return text;
    }

    private void BackToWorld()
    {
        SceneManager.LoadScene("WorldMapScene");
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

        titleText = CreateText("Title", topBar.transform, "Region Map", font, 28, FontStyles.Bold);
        LayoutElement titleLayout = titleText.gameObject.AddComponent<LayoutElement>();
        titleLayout.minWidth = 420f;

        CreateButton("Refresh", topBar.transform, "Refresh", font, async () => await RefreshAsync());
        CreateButton("BackWorld", topBar.transform, "Back To World", font, BackToWorld);
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
        descLE.flexibleHeight = 1f;
        descLE.minHeight = 320f;
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
                Debug.Log("[RegionMapSceneController] image load failed: " + req.error + " | " + url);
                return null;
            }

            Texture2D tex = DownloadHandlerTexture.GetContent(req);
            if (tex == null) return null;
            return Sprite.Create(tex, new Rect(0, 0, tex.width, tex.height), new Vector2(0.5f, 0.5f));
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
