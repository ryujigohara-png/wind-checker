import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import urllib.request
import os
import io
import base64
import warnings
from datetime import datetime
import matplotlib.dates as mdates
from streamlit_folium import st_folium
import folium

# ==========================================
# ★設定エリア★
# ==========================================
TITLE_SIZE = 20
SUBTITLE_SIZE = 16
GRAPH_FONT_SIZE = 10
LABEL_SIZE = 12
DPI_QUALITY = 300
WIND_STEP = 3         
TIME_LABEL_STEP = 6   
# ==========================================

# --- 日本語フォント設定 ---
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
FONT_PATH = "NotoSansJP.ttf"
if not os.path.exists(FONT_PATH):
    urllib.request.urlretrieve(FONT_URL, FONT_PATH)
fm.fontManager.addfont(FONT_PATH)
plt.rc('font', family='Noto Sans JP', size=GRAPH_FONT_SIZE)

st.set_page_config(page_title="風況チェッカー", layout="wide")
warnings.simplefilter('ignore', UserWarning)

st.markdown(f'<h1 style="font-size:{TITLE_SIZE}px;">⛵ 風況チェッカー</h1>', unsafe_allow_html=True)

# --- セッション状態で座標を保持（初期値：高須沖） ---
if 'lat' not in st.session_state:
    st.session_state.lat = 31.3420
    st.session_state.lon = 130.7870

# --- サイドメニュー ---
st.sidebar.header("場所の設定")
use_map = st.sidebar.checkbox("地図から場所を選択（中心の座標を取得）")

if use_map:
    st.info("地図をドラッグして動かしてください。常に【中心（╋マーク）】の座標が予報地点になります。")
    
    # 地図の初期表示設定
    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=12)
    
    # 中心を示す「╋」をアイコンとして追加（擬似的な中心十字）
    folium.Marker(
        [st.session_state.lat, st.session_state.lon],
        icon=folium.Icon(color='red', icon='plus', prefix='fa'),
        tooltip="予報地点（地図の中心）"
    ).add_to(m)

    # 地図の描画（中心移動イベントをキャッチする）
    # 戻り値を安全に受け取るための構成
    map_out = st_folium(m, width="100%", height=400)

    # 地図の移動（中心点が変わった時）に座標を更新
    # 読み込み時のエラー回避のためキーの存在を確認
    if map_out and map_out.get("center"):
        new_lat = map_out["center"]["lat"]
        new_lon = map_out["center"]["lng"]
        
        # 座標が大きく変わった時だけ再読み込みして負荷を減らす
        if abs(st.session_state.lat - new_lat) > 0.0001 or abs(st.session_state.lon - new_lon) > 0.0001:
            st.session_state.lat = new_lat
            st.session_state.lon = new_lon
            st.rerun()

lat, lon = st.session_state.lat, st.session_state.lon
place_display = f"指定地点 (北緯:{lat:.3f} 東経:{lon:.3f})" if use_map else "高須沖(鹿児島県)"

st.sidebar.markdown("---")
days = st.sidebar.slider("表示日数", 1, 7, 7)
danger_v = st.sidebar.number_input("危険風速(m/s)", value=10)

# --- データ取得 ---
url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m&timezone=Asia%2FTokyo&wind_speed_unit=ms&forecast_days=8"
data = requests.get(url).json()

# 以下、グラフ描画コード（前回同様のため省略。そのまま引き継ぎます）
# ...（中略）...
