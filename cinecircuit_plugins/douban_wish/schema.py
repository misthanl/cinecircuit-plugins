"""Configuration rendered by the existing host schema fields."""
FIELDS = [
    {"key": "users", "input_type": "textarea", "rows": 1, "label": "豆瓣用户ID", "default": "", "placeholder": "多个用户用逗号或换行分隔", "description": "同步公开动态RSS中的想看条目；填写个人主页中的用户ID。"},
    {"key": "cron", "input_type": "cron", "label": "执行周期", "default": "", "description": "留空时每30分钟同步，可通过插件菜单立即运行。"},
    {"key": "days", "input_type": "number", "label": "同步天数", "default": 7, "validation": {"minimum": 1, "maximum": 3650}, "description": "只处理此时间范围内的想看记录。"},
    {"key": "proxy", "input_type": "switch", "label": "使用系统代理服务器", "default": False},
    {"key": "notification_enabled", "input_type": "switch", "label": "发送同步通知", "default": False},
    {"key": "clear", "input_type": "switch", "label": "下次执行前清理同步历史", "default": False, "description": "仅清理本插件的去重与订阅记录，不删除已有订阅；清理后重新检查。"},
]
