using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
using TMPro;

/// <summary>
/// 单个棋子的视图与交互（拖拽、点击）
/// </summary>
public class CreatureTokenView : MonoBehaviour, IBeginDragHandler, IDragHandler, IEndDragHandler, IPointerClickHandler
{
    public MapCreatureData creature;

    private EncounterBoardController boardController;
    private RectTransform rectTransform;
    private RectTransform parentLayer;

    private Vector2 dragStartAnchoredPosition;
    private Vector2 dragPointerOffset;
    private bool isDragging;

    public void Initialize(MapCreatureData data, EncounterBoardController controller)
    {
        creature = data;
        boardController = controller;
        rectTransform = GetComponent<RectTransform>();
        parentLayer = transform.parent as RectTransform;
    }

    public void OnBeginDrag(PointerEventData eventData)
    {
        if (!RoomSessionContext.IsDM)
        {
            return;
        }

        isDragging = true;
        dragStartAnchoredPosition = rectTransform.anchoredPosition;

        Vector2 localMouse;
        RectTransformUtility.ScreenPointToLocalPointInRectangle(
            parentLayer, eventData.position, eventData.pressEventCamera, out localMouse);
        dragPointerOffset = rectTransform.anchoredPosition - localMouse;

        transform.SetAsLastSibling();
    }

    public void OnDrag(PointerEventData eventData)
    {
        if (!isDragging) return;

        Vector2 localMouse;
        RectTransformUtility.ScreenPointToLocalPointInRectangle(
            parentLayer, eventData.position, eventData.pressEventCamera, out localMouse);

        rectTransform.anchoredPosition = localMouse + dragPointerOffset;
    }

    public void OnEndDrag(PointerEventData eventData)
    {
        if (!isDragging) return;
        isDragging = false;

        Vector2 tokenPosition = rectTransform.anchoredPosition;

        int newCol, newRow;
        boardController.LocalPointToGrid(tokenPosition, out newCol, out newRow);

        if (!boardController.IsValidGrid(newCol, newRow))
        {
            rectTransform.anchoredPosition = dragStartAnchoredPosition;
            Debug.Log("[Token] 拖到棋盘外，回退");
            return;
        }

        if (boardController.IsWall(newCol, newRow))
        {
            rectTransform.anchoredPosition = dragStartAnchoredPosition;
            Debug.Log("[Token] 目标是墙壁，回退");
            return;
        }

        boardController.MoveCreature(creature.instance_id, newCol, newRow);
    }

    public void OnPointerClick(PointerEventData eventData)
  {
    if (isDragging) return;
    Debug.Log("[Token] 点击了 " + creature.name);
    boardController.ShowMovementRange(creature.instance_id);
  }
}