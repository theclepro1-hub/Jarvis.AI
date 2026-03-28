from typing import Optional


class Theme:
    mode = "dark"
    PALETTES = {
        "dark": {
            "BG": "#0a0c0f",
            "BG_LIGHT": "#0f1317",
            "FG": "#f5f7fb",
            "FG_SECONDARY": "#99a3af",
            "ACCENT": "#39d98a",
            "BOT_MSG": "#151a20",
            "USER_MSG": "#112129",
            "BORDER": "#1b2128",
            "BUTTON_BG": "#14191f",
            "CARD_BG": "#11161b",
            "INPUT_BG": "#0d1115",
            "INPUT_BORDER": "#262f38",
            "CHAT_TIME_FG": "#7f8a97",
            "TOOLTIP_BG": "#151b22",
            "MIC_ICON_FG": "#f6f8fb",
            "STATUS_OK": "#39d98a",
            "STATUS_BUSY": "#67b6ff",
            "STATUS_WARN": "#f7b955",
            "STATUS_ERROR": "#ff7c86",
            "ONLINE": "#39d98a",
            "OFFLINE": "#ff7c86",
        },
        "light": {
            "BG": "#edf1f4",
            "BG_LIGHT": "#f8fbfd",
            "FG": "#16212b",
            "FG_SECONDARY": "#5e6d7d",
            "ACCENT": "#118f76",
            "BOT_MSG": "#f4f7fa",
            "USER_MSG": "#e1eef0",
            "BORDER": "#d6dde4",
            "BUTTON_BG": "#e7edf2",
            "CARD_BG": "#ffffff",
            "INPUT_BG": "#ffffff",
            "INPUT_BORDER": "#c9d2db",
            "CHAT_TIME_FG": "#637181",
            "TOOLTIP_BG": "#eef4f7",
            "MIC_ICON_FG": "#18232d",
            "STATUS_OK": "#027a48",
            "STATUS_BUSY": "#026aa2",
            "STATUS_WARN": "#b54708",
            "STATUS_ERROR": "#b42318",
            "ONLINE": "#027a48",
            "OFFLINE": "#b42318",
        },
    }
    BG_ROLE_KEYS = ("BG", "BG_LIGHT", "CARD_BG", "BUTTON_BG", "INPUT_BG", "BOT_MSG", "USER_MSG", "TOOLTIP_BG", "ACCENT")
    FG_ROLE_KEYS = ("FG", "FG_SECONDARY", "CHAT_TIME_FG", "MIC_ICON_FG", "ACCENT", "STATUS_OK", "STATUS_BUSY", "STATUS_WARN", "STATUS_ERROR", "ONLINE", "OFFLINE")
    LEGACY_BG_KEYS = {
        "#050505": "BG",
        "#0a0a0a": "BG_LIGHT",
        "#1e1e1e": "CARD_BG",
        "#005a9e": "USER_MSG",
        "#151515": "BUTTON_BG",
        "#0b0b0b": "CARD_BG",
        "#111111": "INPUT_BG",
        "#f4f6f8": "BG",
        "#ffffff": "BG_LIGHT",
        "#e9edf3": "BOT_MSG",
        "#dbeafe": "USER_MSG",
        "#e4e7ec": "BUTTON_BG",
        "#f7f9fc": "CARD_BG",
        "#f2f4f7": "TOOLTIP_BG",
    }
    LEGACY_FG_KEYS = {
        "#ffffff": "FG",
        "#9ca3af": "FG_SECONDARY",
        "#2563eb": "ACCENT",
        "#b8b8b8": "CHAT_TIME_FG",
        "#86efac": "STATUS_OK",
        "#7dd3fc": "STATUS_BUSY",
        "#fbbf24": "STATUS_WARN",
        "#fca5a5": "STATUS_ERROR",
        "#101828": "FG",
        "#475467": "FG_SECONDARY",
        "#027a48": "STATUS_OK",
        "#026aa2": "STATUS_BUSY",
        "#b54708": "STATUS_WARN",
        "#b42318": "STATUS_ERROR",
    }

    BG = PALETTES["dark"]["BG"]
    BG_LIGHT = PALETTES["dark"]["BG_LIGHT"]
    FG = PALETTES["dark"]["FG"]
    FG_SECONDARY = PALETTES["dark"]["FG_SECONDARY"]
    ACCENT = PALETTES["dark"]["ACCENT"]
    BOT_MSG = PALETTES["dark"]["BOT_MSG"]
    USER_MSG = PALETTES["dark"]["USER_MSG"]
    BORDER = PALETTES["dark"]["BORDER"]
    BUTTON_BG = PALETTES["dark"]["BUTTON_BG"]
    CARD_BG = PALETTES["dark"]["CARD_BG"]
    INPUT_BG = PALETTES["dark"]["INPUT_BG"]
    INPUT_BORDER = PALETTES["dark"]["INPUT_BORDER"]
    CHAT_TIME_FG = PALETTES["dark"]["CHAT_TIME_FG"]
    TOOLTIP_BG = PALETTES["dark"]["TOOLTIP_BG"]
    MIC_ICON_FG = PALETTES["dark"]["MIC_ICON_FG"]
    STATUS_OK = PALETTES["dark"]["STATUS_OK"]
    STATUS_BUSY = PALETTES["dark"]["STATUS_BUSY"]
    STATUS_WARN = PALETTES["dark"]["STATUS_WARN"]
    STATUS_ERROR = PALETTES["dark"]["STATUS_ERROR"]
    ONLINE = PALETTES["dark"]["ONLINE"]
    OFFLINE = PALETTES["dark"]["OFFLINE"]

    @classmethod
    def apply_mode(cls, mode: str):
        mode = str(mode or "dark").strip().lower()
        if mode not in cls.PALETTES:
            mode = "dark"
        cls.mode = mode
        palette = cls.PALETTES[mode]
        for key, value in palette.items():
            setattr(cls, key, value)

    @classmethod
    def _normalize_color(cls, color: str) -> str:
        return str(color or "").strip().lower()

    @classmethod
    def color_for_key(cls, key: str) -> Optional[str]:
        key = str(key or "").strip().upper()
        return getattr(cls, key, None) if key else None

    @classmethod
    def semantic_key_for_color(cls, color: str, role: str = "bg") -> Optional[str]:
        normalized = cls._normalize_color(color)
        if not normalized:
            return None
        role = str(role or "bg").strip().lower()
        keys = cls.BG_ROLE_KEYS if role == "bg" else cls.FG_ROLE_KEYS
        for palette in cls.PALETTES.values():
            for key in keys:
                value = str(palette.get(key, "")).strip().lower()
                if value and value == normalized:
                    return key
        legacy = cls.LEGACY_BG_KEYS if role == "bg" else cls.LEGACY_FG_KEYS
        return legacy.get(normalized)

    @classmethod
    def resolve_color(cls, color: str, role: str = "bg") -> Optional[str]:
        key = cls.semantic_key_for_color(color, role=role)
        return cls.color_for_key(key) if key else None
