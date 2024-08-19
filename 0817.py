from flask import Flask, request, jsonify
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
import requests
from math import radians, sin, cos, sqrt, atan2

# 初始化Flask应用
app = Flask(__name__)

# 加载交通事故热点数据
file_path = '/Users/chinlin/Desktop/test/0_ALL_108-112_CBI.csv'
df = pd.read_csv(file_path)
df_cleaned = df.dropna(subset=['經度', '緯度'])
df_cleaned['CBI值'] = df_cleaned['事件類別'].apply(lambda x: 3 if x == 'A1' else 1)
gdf = gpd.GeoDataFrame(df_cleaned, geometry=gpd.points_from_xy(df_cleaned.經度, df_cleaned.緯度))

# LINE Notify API设置
line_notify_token = 'zhYZA7ShKGXR7toroizFIsTEkp7JdRtVRx1p7c8jg2d'  # 替换为你的LINE Notify Token

# Haversine公式来计算两个地理坐标之间的距离
def haversine(lat1, lon1, lat2, lon2):
    R = 6371  # 地球半径（公里）
    dlat = radians(lat2 - lat1)
    dlon = radians(lon2 - lon1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlon / 2) ** 2
    c = 2 * atan2(sqrt(a), sqrt(1 - a))
    return R * c

# 接收来自Android应用的定位数据
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

    # 检查用户位置与事故热点的距离
    for idx, row in gdf.iterrows():
        distance_km = haversine(latitude, longitude, row.geometry.y, row.geometry.x)
        if distance_km <= 0.1:  # 假设100米作为阈值
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

if __name__ == "__main__":
    app.run(host='0.0.0.0', port=8000)