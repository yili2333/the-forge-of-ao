using System;
using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class PartyMemberItemUI : MonoBehaviour
{
    public TMP_Text nameText;
    public TMP_Text classText;
    public TMP_Text levelText;
    public TMP_Text hpText;

    [Header("Optional")]
    public Image backgroundImage;

    private CharacterData characterData;
    private Action<CharacterData> onClickAction;

    public void Setup(CharacterData data, bool isUploadedCharacter, bool isSelected, Action<CharacterData> onClick)
    {
        characterData = data;
        onClickAction = onClick;

        if (nameText != null)
        {
            string suffix = isUploadedCharacter ? " (You)" : string.Empty;
            nameText.text = data.DisplayName + suffix;
        }

        if (classText != null)
        {
            string classLine = "Class: " + data.DisplayClass;
            if (!string.IsNullOrWhiteSpace(data.ownerDisplay))
            {
                classLine += " | Owner: " + data.ownerDisplay;
            }
            classText.text = classLine;
        }

        if (levelText != null)
        {
            levelText.text = "Lv. " + Mathf.Max(1, data.level) + (data.dmApproved ? " | Approved" : string.Empty);
        }

        if (hpText != null)
        {
            string hpValue = data.hp > 0 ? data.hp.ToString() : "?";
            if (data.armorClass > 0)
            {
                hpText.text = "HP: " + hpValue + " | AC: " + data.armorClass;
            }
            else
            {
                hpText.text = "HP: " + hpValue;
            }
        }

        if (backgroundImage != null)
        {
            backgroundImage.color = isSelected
                ? new Color(0.10f, 0.38f, 0.55f, 1f)
                : new Color(0.20f, 0.20f, 0.20f, 1f);
        }
    }

    public void OnClickItem()
    {
        if (characterData != null && onClickAction != null)
        {
            onClickAction.Invoke(characterData);
        }
    }
}
