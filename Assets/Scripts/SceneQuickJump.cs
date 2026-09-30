using UnityEngine;
using UnityEngine.SceneManagement;

public class SceneQuickJump : MonoBehaviour
{
    public void OpenWorldMapScene()
    {
        SceneManager.LoadScene("WorldMapScene");
    }

    public void OpenRegionMapScene()
    {
        SceneManager.LoadScene("RegionMapScene");
    }

    public void OpenRoomScene()
    {
        SceneManager.LoadScene("RoomScene");
    }
}
