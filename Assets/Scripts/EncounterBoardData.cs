using System;
using System.Collections.Generic;

// ========== 棋盘数据模型 ==========
// 这个文件定义了棋盘相关的所有数据结构
// 字段命名对应 front.md 里后端返回的 JSON 格式（snake_case）

[Serializable]
public class EncounterMapData
{
    public string id;                    // 棋盘ID
    public string campaign_id;           // 战役ID
    public string name;                  // 棋盘名称
    public int grid_cols = 20;           // 列数（横向格子数）
    public int grid_rows = 15;           // 行数（纵向格子数）
    public int cell_size_ft = 5;         // 每格对应的英尺数（D&D标准是5ft）
    public string image_url;             // 背景图URL
    public List<MapCreatureData> creatures = new List<MapCreatureData>();

    // 地形数据：cells[row][col] = 地形类型字符串
    // 为简化，我们先用字符串表示（"open"/"wall"/"difficult"等）
    public List<List<string>> cells;
}

[Serializable]
public class MapCreatureData
{
    public string instance_id;           // 棋子唯一ID（后端分配的UUID）
    public string name;                  // 显示名
    public string monster_id;            // 怪物模板ID（如果是怪物）
    public string character_id;          // 角色ID（如果是玩家）
    public int x;                        // 列坐标（0=最左）
    public int y;                        // 行坐标（0=最上）
    public int hp_current;
    public int hp_max;
    public int speed = 30;               // 移动速度（英尺）
    public int movement_used = 0;        // 本回合已用移动力
    public bool is_player;               // true=玩家角色,false=怪物
    public bool is_hidden;               // true=对玩家隐藏（只有DM能看到）
    public int initiative;               // 先攻值
    public List<string> conditions = new List<string>();

    // 行动资源
    public bool action_used;
    public bool bonus_action_used;
    public bool reaction_used;
}

// ========== 地形类型常量 ==========
public static class TerrainType
{
    public const string Open = "open";
    public const string Difficult = "difficult";
    public const string Wall = "wall";
    public const string Water = "water";
    public const string Door = "door";
    public const string CoverHalf = "cover_half";
    public const string CoverFull = "cover_full";
}