import os
import pandas as pd
import folium
from folium.plugins import HeatMap
from shapely.geometry import LineString
import geopandas as gpd
from linebot import LineBotApi, WebhookHandler
from linebot.exceptions import InvalidSignatureError
from linebot.models import (
    MessageEvent, TextMessage, ImageSendMessage, TextSendMessage,
    LocationMessage, TemplateSendMessage, ButtonsTemplate, LocationAction,
    RichMenu, RichMenuSize, RichMenuArea, RichMenuBounds, PostbackAction, MessageAction,
    FlexSendMessage
)
from flask import Flask, request, abort, render_template, send_from_directory, jsonify
import requests
from selenium import webdriver
import time
from math import radians, cos, sin, sqrt, atan2
from collections import defaultdict
import threading
from datetime import datetime

# 定義 Google Maps API Key
api_key = 'AIzaSyBmKpxSthTqntMDNjP-k3YCS-ckkxDxYew'

# 設置LINE Messaging API
line_bot_api = LineBotApi('083ucgudP5l8xvi9aZYxixex1uVNLsVDYduULynHj2SMsaJ8UyPa8q7AakTuDGSsiRaulUIqEz4sgQL97GRpc+QE+DUBKwRaD6Pr3HcZ+CpE5m0wtVUAIplYxyq4urWyNC21vx/2zht/9bNKglm0ZgdB04t89/1O/w1cDnyilFU=')
handler = WebhookHandler('58bfe9545c80505fc9c02add849dee96')

# 加載和清理數據
file_path = '/Users/chinlin/Desktop/test/0_ALL_108-112_CBI.csv'
df = pd.read_csv(file_path)
df_cleaned = df.dropna(subset=['經度', '緯度'])
df_cleaned['CBI值'] = df_cleaned['事件類別'].apply(lambda x: 3 if x == 'A1' else 1)
gdf = gpd.GeoDataFrame(df_cleaned, geometry=gpd.points_from_xy(df_cleaned.經度, df_cleaned.緯度))

# LINE Notify API 設置
line_notify_token = 'z6hz7ANxXzfXai58No7vVs15D4OMFYtbHEKlMYAs3qp'

# 初始化 Flask 應用
app = Flask(__name__, static_folder='/Users/chinlin/Desktop/test/templates/static')

# 初始化位置數據存儲
user_locations = defaultdict(lambda: {'start': None, 'end': None})
lock = threading.Lock()

# Haversine公式來計算兩個地理座標之間的距離
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # 地球半徑（公里）
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

# LINE Notify 的功能路由
@app.route('/', methods=['POST'])
def receive_location():
    data = request.json
    latitude = data.get('latitude')
    longitude = data.get('longitude')

    if latitude is None or longitude is None:
        return jsonify({"status": "error", "message": "Missing latitude or longitude"}), 400

    try:
        latitude = float(latitude)
        longitude = float(longitude)
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid latitude or longitude format"}), 400

    # 檢查使用者位置與事故熱點的距離
    for idx, row in gdf.iterrows():
        distance_km = haversine(latitude, longitude, row.geometry.y, row.geometry.x)
        if distance_km <= 0.1:  # 假設100米作為閾值
            message = f"您看護的長者距離最近的行人事故熱點僅有{distance_km * 1000:.2f}米，請注意安全！"
            send_line_notify(message)
            return jsonify({"status": "warning", "message": message}), 200

    message = f"您看護的長者附近沒有行人事故熱點"
    send_line_notify(message)
    return jsonify({"status": "safe", "message":"您看護的長者附近沒有行人事故熱點"}), 200

def send_line_notify(message):
    headers = {
        "Authorization": f"Bearer {line_notify_token}",
        "Content-Type": "application/x-www-form-urlencoded"
    }
    data = {'message': message}
    requests.post("https://notify-api.line.me/api/notify", headers=headers, data=data)

# LINE Bot 的功能路由
@app.route("/callback", methods=['POST'])
def callback():
    signature = request.headers['X-Line-Signature']
    body = request.get_data(as_text=True)
    app.logger.info(f"Request body: {body}")
    try:
        handler.handle(body, signature)
    except InvalidSignatureError:
        app.logger.error("Invalid signature. Check your channel secret and access token.")
        abort(400)
    except Exception as e:
        app.logger.error(f"An error occurred: {str(e)}")
        abort(500)
    return 'OK'

@app.route('/test')
def send_report():
    return render_template('accidents_map_line.html')

@app.route('/static/<path:filename>')
def static_files(filename):
    return send_from_directory(app.static_folder, filename)

# 建立 Rich Menu
def create_rich_menu():
    rich_menu_to_create = RichMenu(
        size=RichMenuSize(width=2500, height=843),
        selected=False,
        name="Rich Menu",
        chat_bar_text="確認路徑是否有交通事故熱點",
        areas=[
            RichMenuArea(
                bounds=RichMenuBounds(x=0, y=0, width=1250, height=843),
                action=MessageAction(label="開始", text="請傳送您的起點")
            ),
            RichMenuArea(
                bounds=RichMenuBounds(x=1250, y=0, width=1250, height=843),
                action=MessageAction(label="結束", text="請傳送您的終點")
            )
        ]
    )
    
    rich_menu_id = line_bot_api.create_rich_menu(rich_menu=rich_menu_to_create)
    with open("/Users/chinlin/Desktop/test/20240812_6.jpg", 'rb') as f:
        line_bot_api.set_rich_menu_image(rich_menu_id, "image/jpeg", f)
    line_bot_api.set_default_rich_menu(rich_menu_id)

create_rich_menu()

@handler.add(MessageEvent, message=TextMessage)
def handle_message(event):
    try:
        user_id = event.source.user_id
        app.logger.info(f"User ID: {user_id}")

        if event.message.text == "請傳送您的起點":
            start_buttons_template = ButtonsTemplate(
                title='請傳送您的起點位置',
                text='點擊下方按鈕傳送起點位置',
                actions=[LocationAction(label='傳送起點位置')]
            )
            template_message = TemplateSendMessage(alt_text='請傳送您的起點位置', template=start_buttons_template)
            line_bot_api.reply_message(event.reply_token, template_message)

        elif event.message.text == "請傳送您的終點":
            end_buttons_template = ButtonsTemplate(
                title='請傳送您的終點位置',
                text='點擊下方按鈕傳送終點位置',
                actions=[LocationAction(label='傳送終點位置')]
            )
            template_message = TemplateSendMessage(alt_text='請傳送您的終點位置', template=end_buttons_template)
            line_bot_api.reply_message(event.reply_token, template_message)

    except Exception as e:
        app.logger.error(f"Error handling message: {e}")
        line_bot_api.reply_message(
            event.reply_token,
            TextMessage(text=f"Error: {e}")
        )

@handler.add(MessageEvent, message=LocationMessage)
def handle_location_message(event):
    user_id = event.source.user_id
    location = (event.message.latitude, event.message.longitude)
    
    with lock:
        if user_locations[user_id]['start'] is None:
            user_locations[user_id]['start'] = location
            app.logger.info(f"Set start location for user {user_id}: {location}")
            line_bot_api.reply_message(
                event.reply_token,
                TextSendMessage(text=f"起點位置已設置: {location}，請選擇並傳送終點位置。")
            )
        elif user_locations[user_id]['end'] is None:
            user_locations[user_id]['end'] = location
            start_location = user_locations[user_id]['start']
            end_location = user_locations[user_id]['end']
            
            line_bot_api.push_message(
                user_id,
                TextSendMessage(text="正在根據您輸入的位置與交通事故熱點確認中，請稍候...")
            )
            
            user_locations[user_id] = {'start': None, 'end': None}
            thread = threading.Thread(target=send_route_plan, args=(start_location, end_location, user_id))
            thread.start()

def send_route_plan(start_location, end_location, user_id):
    try:
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        unique_filename = f"{user_id}_{timestamp}"

        route = get_route(start_location, end_location, api_key)

        route_points = [(lat, lng) for lat, lng in route]
        route_line = LineString(route_points)

        latitudes = [point[0] for point in route_points]
        longitudes = [point[1] for point in route_points]
        route_center = (sum(latitudes) / len(latitudes), sum(longitudes) / len(longitudes))

        lat_span = max(latitudes) - min(latitudes)
        lon_span = max(longitudes) - min(longitudes)
        max_span = max(lat_span, lon_span)

        if max_span < 0.005:
            zoom = 18
        elif max_span < 0.01:
            zoom = 16
        elif max_span < 0.05:
            zoom = 14
        elif max_span < 0.1:
            zoom = 12
        elif max_span < 0.5:
            zoom = 10
        else:
            zoom = 8

        m = folium.Map(location=route_center, zoom_start=zoom)
        m.fit_bounds([[min(latitudes), min(longitudes)], [max(latitudes), max(longitudes)]])

        folium.TileLayer('OpenStreetMap').add_to(m)
        folium.TileLayer(
            tiles='https://mt1.google.com/vt/lyrs=r&x={x}&y={y}&z={z}',
            attr='Google',
            name='Google Maps'
        ).add_to(m)

        folium.PolyLine(route_points, color="blue", weight=2.5, opacity=1).add_to(m)

        radius_km = 1.0
        threshold = 3
        heatmap_data = []
        hotspot_counts = defaultdict(int)

        for route_point in route:
            for idx, row in gdf.iterrows():
                accident_point = row['geometry']
                distance_km = haversine(route_point[0], route_point[1], accident_point.y, accident_point.x)
                if distance_km <= radius_km:
                    heatmap_data.append([accident_point.y, accident_point.x, row['CBI值']])
                    if distance_km <= 0.010:
                        hotspot_counts[(route_point[0], route_point[1])] += 1

        for (lat, lon), count in hotspot_counts.items():
            if count >= threshold:
                folium.Marker(
                    location=[lat, lon],
                    popup=f"周圍12米內事故點數: {count}",
                    icon=folium.Icon(color='red')
                ).add_to(m)

        HeatMap(data=heatmap_data, radius=15).add_to(m)

        map_html_path = f'/Users/chinlin/Desktop/test/templates/accidents_map_line_{unique_filename}.html'
        map_png_path = f'/Users/chinlin/Desktop/test/templates/accidents_map_line_{unique_filename}.png'
        
        m.save(map_html_path)

        options = webdriver.ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        driver = webdriver.Chrome(options=options)
        driver.get(f'file://{map_html_path}')
        time.sleep(2)
        driver.save_screenshot(map_png_path)
        driver.quit()

        flex_message = {
            "type": "bubble",
            "hero": {
                "type": "image",
                "url": f'https://d669-123-51-152-222.ngrok-free.app/static/{os.path.basename(map_png_path)}',
                "size": "full",
                "aspectRatio": "20:13",
                "aspectMode": "cover",
                "action": {
                    "type": "uri",
                    "uri": f'https://d669-123-51-152-222.ngrok-free.app/static/{os.path.basename(map_html_path)}'
                }
            },
            "body": {
                "type": "box",
                "layout": "vertical",
                "contents": [
                    {
                        "type": "text",
                        "text": "走路不要滑手機",
                        "weight": "bold",
                        "size": "xl"
                    },
                    {
                        "type": "button",
                        "style": "primary",
                        "action": {
                            "type": "uri",
                            "label": "查看完整地圖",
                            "uri": f'https://d669-123-51-152-222.ngrok-free.app/static/{os.path.basename(map_html_path)}'
                        }
                    }
                ]
            }
        }

        line_bot_api.push_message(user_id, FlexSendMessage(alt_text="路徑地圖已生成", contents=flex_message))

    except Exception as e:
        line_bot_api.push_message(
            user_id,
            TextSendMessage(text=f"生成路徑時出現錯誤: {str(e)}")
        )


def get_route(start, end, api_key):
    base_url = "https://maps.googleapis.com/maps/api/directions/json"
    params = {
        "origin": f"{start[0]},{start[1]}",
        "destination": f"{end[0]},{end[1]}",
        "mode": "walking",
        "key": api_key
    }
    response = requests.get(base_url, params=params)
    data = response.json()
    if data['status'] == 'OK':
        polyline = data['routes'][0]['overview_polyline']['points']
        return decode_polyline(polyline)
    else:
        raise Exception(f"Error fetching route: {data['status']}")

def decode_polyline(polyline_str):
    index, lat, lng = 0, 0, 0
    coordinates = []

    while index < len(polyline_str):
        shift, result = 0, 0

        while True:
            byte = ord(polyline_str[index]) - 63
            index += 1
            result |= (byte & 0x1f) << shift
            shift += 5
            if not (byte >= 0x20):
                break

        dlat = ~(result >> 1) if (result & 1) else (result >> 1)
        lat += dlat

        shift, result = 0, 0

        while True:
            byte = ord(polyline_str[index]) - 63
            index += 1
            result |= (byte & 0x1f) << shift
            shift += 5
            if not (byte >= 0x20):
                break

        dlng = ~(result >> 1) if (result & 1) else (result >> 1)
        lng += dlng

        coordinates.append((lat / 1e5, lng / 1e5))

    return coordinates

if __name__ == "__main__":
    app.run(port=8000, debug=True)
