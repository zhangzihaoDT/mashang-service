from datetime import datetime


def get_current_time(format="%Y-%m-%d %H:%M:%S"):
    return datetime.now().strftime(format)


GET_CURRENT_TIME_TOOL_SCHEMA = {
    "type": "function",
    "function": {
        "name": "get_current_time",
        "description": "获取当前时间。当用户询问现在几点、日期或时间时使用。",
        "parameters": {
            "type": "object",
            "properties": {
                "format": {
                    "type": "string",
                    "description": "时间格式，例如 '%Y-%m-%d %H:%M:%S'。默认为 '%Y-%m-%d %H:%M:%S'。",
                }
            },
            "required": [],
        },
    },
}


TIME_TOOL_SCHEMA = GET_CURRENT_TIME_TOOL_SCHEMA
