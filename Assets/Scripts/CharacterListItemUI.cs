using TMPro;
using UnityEngine;
using UnityEngine.UI;

public class CharacterListItemUI : MonoBehaviour
{
    public TMP_Text nameText;
    public TMP_Text classText;
    public Button button;
    public Image background;

    private CharacterData characterData;
    private CharacterVaultUIController owner;

    public string BoundCharacterId
    {
        get
        {
            return characterData != null ? characterData.id : "";
        }
    }

    public void Setup(CharacterData data, CharacterVaultUIController controller)
    {
        characterData = data;
        owner = controller;

        nameText.text = data.characterName;
        classText.text = data.characterClass;

        button.onClick.RemoveAllListeners();
        button.onClick.AddListener(() => owner.SelectCharacter(characterData));
    }

    public void SetSelected(bool selected)
    {
        if (background == null) return;

        background.color = selected
            ? new Color(0.75f, 0.82f, 0.95f, 1f)
            : new Color(1f, 1f, 1f, 0.9f);
    }
}