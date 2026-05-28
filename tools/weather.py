"""
XF 模具智能体平台 - 天气查询工具（Open-Meteo，免费无需 API Key）
"""
import requests
from langchain_core.tools import tool


GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"
WEATHER_URL = "https://api.open-meteo.com/v1/forecast"

# WMO 天气代码 → 中文描述
_WMO_CODES = {
    0: "晴朗",
    1: "大部晴朗",
    2: "多云",
    3: "阴天",
    45: "雾",
    48: "雾凇",
    51: "小毛毛雨",
    53: "中毛毛雨",
    55: "大毛毛雨",
    56: "冻毛毛雨",
    57: "冻毛毛雨",
    61: "小雨",
    63: "中雨",
    65: "大雨",
    66: "冻雨",
    67: "冻雨",
    71: "小雪",
    73: "中雪",
    75: "大雪",
    77: "雪粒",
    80: "小阵雨",
    81: "中阵雨",
    82: "大阵雨",
    85: "小阵雪",
    86: "大阵雪",
    95: "雷暴",
    96: "雷暴伴冰雹",
    99: "雷暴伴冰雹",
}


def _weather_code_to_desc(code: int) -> str:
    return _WMO_CODES.get(code, f"未知（代码 {code}）")


@tool
def get_weather(city: str) -> str:
    """
    获取指定城市的实时天气。
    输入城市名称，支持中文（如"北京"、"上海"、"广州"、"纽约"等）。
    """
    try:
        # 1. 地理编码：城市名 → 经纬度
        geo_resp = requests.get(
            GEOCODING_URL,
            params={"name": city, "count": 1, "language": "zh"},
            timeout=10,
        )
        geo_resp.raise_for_status()
        geo_data = geo_resp.json()

        if not geo_data.get("results"):
            return f"未找到城市「{city}」的信息，请检查城市名称是否正确。"

        loc = geo_data["results"][0]
        lat, lon = loc["latitude"], loc["longitude"]
        city_name = loc.get("name", city)
        country = loc.get("country", "")
        admin = loc.get("admin1", "")

        # 2. 获取实时天气
        weather_resp = requests.get(
            WEATHER_URL,
            params={
                "latitude": lat,
                "longitude": lon,
                "current_weather": "true",
                "timezone": "Asia/Shanghai",
            },
            timeout=10,
        )
        weather_resp.raise_for_status()
        wdata = weather_resp.json()

        cw = wdata.get("current_weather", {})
        temp = cw.get("temperature", "?")
        windspeed = cw.get("windspeed", "?")
        code = cw.get("weathercode", 0)

        desc = _weather_code_to_desc(code)

        location_parts = [city_name, admin, country]
        location = "，".join(p for p in location_parts if p)

        return (
            f"📍 {location}\n"
            f"🌡 温度：{temp}°C\n"
            f"🌤 天气：{desc}\n"
            f"💨 风速：{windspeed} km/h"
        )

    except requests.RequestException as e:
        return f"查询天气时网络出错：{e}，请稍后重试。"
    except Exception as e:
        return f"查询天气时发生错误：{e}"
