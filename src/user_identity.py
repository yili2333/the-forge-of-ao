"""
用户身份模块

负责本地用户身份的创建、加载、修改与持久化。

设计要点:
- owner_id 格式: "昵称#4位随机数"，例如 "Tanrui#7281"
- discriminator 一旦生成不可变（避免破坏已创建角色的归属）
- email 可选，用于跨设备识别同一玩家
- 配置文件位于 ~/.dnd-rules-ai/user.toml，可手动编辑
- stable_key: 数据库中 owner_id 的实际存储值（邮箱优先，否则 nickname#disc）
"""

from __future__ import annotations

import os
import random
import re
import sys
from dataclasses import dataclass, field, asdict
from datetime import datetime
from pathlib import Path

# Python 3.11+ 自带 tomllib (只读)
try:
    import tomllib
except ImportError:
    tomllib = None  # type: ignore


# ============================================================
#  路径
# ============================================================

CONFIG_DIR = Path.home() / ".dnd-rules-ai"
CONFIG_FILE = CONFIG_DIR / "user.toml"


# ============================================================
#  数据模型
# ============================================================

@dataclass
class UserIdentity:
    """本地用户身份"""
    nickname: str                       # "Tanrui"
    discriminator: str                  # "7281"  (4 位数字字符串)
    email: str = ""                     # 可选
    default_role: str = "player"        # "player" / "dm"
    last_campaign: str = ""             # 上次进入的战役 id
    created_at: str = ""

    # ----- 派生属性 -----

    @property
    def owner_id(self) -> str:
        """显示用 ID: Tanrui#7281"""
        return f"{self.nickname}#{self.discriminator}"

    @property
    def stable_key(self) -> str:
        """
        数据库存储用的稳定标识符。
        - 邮箱优先（跨设备一致）
        - 否则用 owner_id（本机一致）
        """
        return self.email.lower().strip() if self.email else self.owner_id

    @property
    def display_name(self) -> str:
        """同 owner_id，仅作语义区分"""
        return self.owner_id


# ============================================================
#  校验
# ============================================================

NICKNAME_PATTERN = re.compile(r"^[^\s#]+$")
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validate_nickname(name: str) -> str:
    """校验昵称并返回规范化后的值"""
    name = name.strip()
    if not name:
        raise ValueError("昵称不能为空")
    if len(name) > 16:
        raise ValueError("昵称最长 16 字符")
    if not NICKNAME_PATTERN.match(name):
        raise ValueError("昵称不能包含 '#' 或空白字符")
    return name


def validate_email(email: str) -> str:
    """校验邮箱（允许空）"""
    email = email.strip()
    if not email:
        return ""
    if not EMAIL_PATTERN.match(email):
        raise ValueError(f"邮箱格式不合法: {email}")
    return email


def generate_discriminator() -> str:
    """生成 4 位数字 discriminator (0000-9999)"""
    return f"{random.randint(0, 9999):04d}"


# ============================================================
#  TOML 读写（手写最简实现，不引入 tomli_w 依赖）
# ============================================================

def _serialize_toml(identity: UserIdentity) -> str:
    """
    把 UserIdentity 序列化为 TOML 文本。
    我们的 schema 很简单，手写比引入依赖更轻。
    """
    def esc(s: str) -> str:
        # TOML 字符串需要转义反斜杠和双引号
        return s.replace("\\", "\\\\").replace('"', '\\"')

    lines = [
        "# D&D Rules AI - 本地用户身份配置",
        "# 这个文件决定你在联机时的身份标识",
        "# 可以手动编辑，但 discriminator 一旦生成请勿修改",
        "# 否则数据库中已创建角色的归属会丢失",
        "",
        "[identity]",
        f'nickname = "{esc(identity.nickname)}"',
        f'discriminator = "{esc(identity.discriminator)}"',
        f'email = "{esc(identity.email)}"',
        f'created_at = "{esc(identity.created_at)}"',
        "",
        "[preferences]",
        f'default_role = "{esc(identity.default_role)}"',
        f'last_campaign = "{esc(identity.last_campaign)}"',
        "",
    ]
    return "\n".join(lines)


def _parse_toml(text: str) -> dict:
    """
    解析 TOML 文件。优先使用标准库 tomllib，失败时降级到一个最简手写解析器
    （只支持本模块写出的格式：section + key="value"）
    """
    if tomllib is not None:
        try:
            return tomllib.loads(text)
        except Exception:
            pass

    # 降级解析器
    result: dict = {}
    current_section: dict | None = None
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("[") and line.endswith("]"):
            section_name = line[1:-1].strip()
            current_section = {}
            result[section_name] = current_section
            continue
        if "=" in line and current_section is not None:
            k, _, v = line.partition("=")
            k = k.strip()
            v = v.strip()
            if v.startswith('"') and v.endswith('"'):
                v = v[1:-1].replace('\\"', '"').replace("\\\\", "\\")
            current_section[k] = v
    return result


# ============================================================
#  IdentityManager
# ============================================================

class IdentityManager:
    """
    用户身份管理器。

    使用方式:
        identity = IdentityManager.load_or_create()
        print(identity.owner_id)

        # 修改昵称
        identity = IdentityManager.update(nickname="NewName")
    """

    @staticmethod
    def config_path() -> Path:
        return CONFIG_FILE

    @staticmethod
    def exists() -> bool:
        return CONFIG_FILE.exists()

    # ---------- 加载 ----------

    @staticmethod
    def load() -> UserIdentity:
        """从配置文件加载，文件必须存在"""
        if not CONFIG_FILE.exists():
            raise FileNotFoundError(f"配置文件不存在: {CONFIG_FILE}")

        text = CONFIG_FILE.read_text(encoding="utf-8")
        data = _parse_toml(text)

        identity_section = data.get("identity", {})
        prefs_section = data.get("preferences", {})

        # 校验关键字段
        nickname = identity_section.get("nickname", "")
        discriminator = identity_section.get("discriminator", "")
        if not nickname or not discriminator:
            raise ValueError(
                f"配置文件 {CONFIG_FILE} 缺少 nickname 或 discriminator"
            )

        return UserIdentity(
            nickname=nickname,
            discriminator=discriminator,
            email=identity_section.get("email", ""),
            created_at=identity_section.get("created_at", ""),
            default_role=prefs_section.get("default_role", "player"),
            last_campaign=prefs_section.get("last_campaign", ""),
        )

    @staticmethod
    def load_or_create(interactive: bool = True) -> UserIdentity:
        """
        启动入口。配置存在则加载，否则交互式创建。

        非交互模式 (interactive=False) 用于测试，会自动用 'TestUser' 创建。
        """
        if CONFIG_FILE.exists():
            return IdentityManager.load()
        if interactive:
            return IdentityManager._interactive_setup()
        return IdentityManager._create_default()

    # ---------- 创建 ----------

    @staticmethod
    def _interactive_setup() -> UserIdentity:
        """首次启动的交互式向导"""
        print("=" * 50)
        print("首次启动 - 创建本地身份")
        print("=" * 50)
        print(f"配置将保存到: {CONFIG_FILE}")
        print()

        # 昵称（重试直到合法）
        while True:
            try:
                raw = input("请输入昵称 (1-16 字符, 不含 # 和空格): ")
                nickname = validate_nickname(raw)
                break
            except ValueError as e:
                print(f"  错误: {e}")
            except (KeyboardInterrupt, EOFError):
                print("\n已取消")
                sys.exit(1)

        # 邮箱（可选）
        while True:
            try:
                raw = input("绑定邮箱 (可选, 回车跳过): ")
                email = validate_email(raw)
                break
            except ValueError as e:
                print(f"  错误: {e}")
            except (KeyboardInterrupt, EOFError):
                email = ""
                break

        identity = UserIdentity(
            nickname=nickname,
            discriminator=generate_discriminator(),
            email=email,
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
        IdentityManager.save(identity)

        print()
        print(f"身份已创建: {identity.owner_id}")
        if email:
            print(f"已绑定邮箱: {email}")
        print(f"配置文件: {CONFIG_FILE}")
        print()
        return identity

    @staticmethod
    def _create_default() -> UserIdentity:
        """非交互场景：创建一个默认身份（用于自动化测试）"""
        identity = UserIdentity(
            nickname="TestUser",
            discriminator=generate_discriminator(),
            created_at=datetime.now().isoformat(timespec="seconds"),
        )
        IdentityManager.save(identity)
        return identity

    # ---------- 保存 ----------

    @staticmethod
    def save(identity: UserIdentity) -> None:
        CONFIG_DIR.mkdir(parents=True, exist_ok=True)
        CONFIG_FILE.write_text(
            _serialize_toml(identity),
            encoding="utf-8",
        )

    # ---------- 修改 ----------

    @staticmethod
    def update(
        nickname: str | None = None,
        email: str | None = None,
        default_role: str | None = None,
        last_campaign: str | None = None,
    ) -> UserIdentity:
        """
        修改部分字段并持久化。
        注意: discriminator 不在可修改字段中（一旦生成不变）。
        """
        current = IdentityManager.load()

        if nickname is not None:
            current.nickname = validate_nickname(nickname)
        if email is not None:
            current.email = validate_email(email)
        if default_role is not None:
            if default_role not in ("player", "dm"):
                raise ValueError(f"role 必须是 'player' 或 'dm'，得到 {default_role}")
            current.default_role = default_role
        if last_campaign is not None:
            current.last_campaign = last_campaign

        IdentityManager.save(current)
        return current

    # ---------- 工具 ----------

    @staticmethod
    def reset() -> None:
        """删除配置文件（谨慎使用，仅用于测试或玩家明确请求）"""
        if CONFIG_FILE.exists():
            CONFIG_FILE.unlink()


# ============================================================
#  CLI 入口（python -m user_identity）
# ============================================================

def _cli():
    """命令行查看/修改身份"""
    import argparse
    parser = argparse.ArgumentParser(description="管理本地用户身份")
    sub = parser.add_subparsers(dest="cmd")

    sub.add_parser("show", help="显示当前身份")
    sub.add_parser("create", help="交互式创建（已存在则报错）")

    p_update = sub.add_parser("update", help="修改字段")
    p_update.add_argument("--nickname")
    p_update.add_argument("--email")
    p_update.add_argument("--role", choices=["player", "dm"])

    sub.add_parser("path", help="显示配置文件路径")
    sub.add_parser("reset", help="删除配置（危险）")

    args = parser.parse_args()

    if args.cmd == "show" or args.cmd is None:
        if not IdentityManager.exists():
            print("尚未创建身份。运行 'create' 或直接启动主程序。")
            return
        i = IdentityManager.load()
        print(f"owner_id    : {i.owner_id}")
        print(f"stable_key  : {i.stable_key}")
        print(f"email       : {i.email or '(未绑定)'}")
        print(f"role        : {i.default_role}")
        print(f"created_at  : {i.created_at}")
        print(f"config path : {CONFIG_FILE}")

    elif args.cmd == "create":
        if IdentityManager.exists():
            print(f"配置已存在: {CONFIG_FILE}")
            print("如需重建请先运行 'reset'")
            sys.exit(1)
        IdentityManager._interactive_setup()

    elif args.cmd == "update":
        i = IdentityManager.update(
            nickname=args.nickname,
            email=args.email,
            default_role=args.role,
        )
        print(f"已更新: {i.owner_id}")

    elif args.cmd == "path":
        print(CONFIG_FILE)

    elif args.cmd == "reset":
        confirm = input(f"将删除 {CONFIG_FILE}，确认? (yes/no): ")
        if confirm.lower() == "yes":
            IdentityManager.reset()
            print("已删除")
        else:
            print("已取消")


if __name__ == "__main__":
    _cli()
