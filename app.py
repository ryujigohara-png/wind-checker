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
from datetime import datetime, timedelta, timezone
import matplotlib.dates as mdates
from streamlit_folium import st_folium
import folium

# ==========================================
# ★設定エリア★
# ==========================================
TITLE_SIZE = 20
SUBTITLE_SIZE = 16
GRAPH_FONT_SIZE = 9
LABEL_SIZE = 12
DPI_QUALITY = 300
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

# --- セッション状態で座標保持 ---
if 'lat' not in st.session_state:
    st.session_state.lat = 31.3420
    st.session_state.lon = 130.7870

# --- サイドメニュー ---
st.sidebar.header("設定")
use_map = st.sidebar.checkbox("地図から場所を選択")

if use_map:
    st.info("地図をドラッグして、中央の【╋】に合わせると予報が切り替わります。")
    # 地図オブジェクトの作成
    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=12)
    
    # CSSではなく、地図自体に「十字線」を画像のように書き込む（FloatImage的なアプローチ）
    # これにより、地図のフレーム内に確実に収まります
    icon_style = "font-size: 30px; color: red; font-weight: bold; background: none; border: none;"
    folium.Marker(
        [st.session_state.lat, st.session_state.lon],
        icon=folium.DivIcon(
            html=f'<div style="{icon_style}">╋</div>',
            icon_anchor=(15, 23) # 十字の見た目の中心を合わせる調整
        )
    ).add_to(m)

    map_out = st_folium(m, width=700, height=400, key="fixed_map_new")

    if map_out and map_out.get("center"):
        new_lat = map_out["center"]["lat"]
        new_lon = map_out["center"]["lng"]
        if abs(st.session_state.lat - new_lat) > 0.0001 or abs(st.session_state.lon - new_lon) > 0.0001:
            st.session_state.lat = new_lat
            st.session_state.lon = new_lon
            st.rerun()

lat, lon = st.session_state.lat, st.session_state.lon
place_display = f"指定地点 ({lat:.3f}, {lon:.3f})" if use_map else "高須沖(鹿児島県)"

days = st.sidebar.slider("表示日数", 1, 7, 7)
danger_v = st.sidebar.number_input("危険風速(m/s)", value=10)

# --- 日数に応じた間引き設定 ---
if days == 1:
    WIND_STEP = 1      # 全時間
    TIME_STEP = 3      # 3時間ごと
elif days == 2:
    WIND_STEP = 2      # 2時間ごと
    TIME_STEP = 6      # 6時間ごと
else:
    WIND_STEP = 3      # 3時間ごと
    TIME_STEP = 6      # 3〜7日は一律6時間ごと

# --- データ取得 ---
url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m&timezone=Asia%2FTokyo&wind_speed_unit=ms&forecast_days=8"
data = requests.get(url).json()

df = pd.DataFrame(data["hourly"])
df['time'] = pd.to_datetime(df['time'])
df = df.head(24 * days).reset_index(drop=True)

jp_weeks = ["月", "火", "水", "木", "金", "土", "日"]

def get_wind_info(deg):
    dirs = ["北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東", "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西", "北"]
    arrows = ["↓", "↙", "↙", "↙", "←", "↖", "↖", "↖", "↑", "↗", "↗", "↗", "→", "↘", "↘", "↘", "↓"]
    idx = int((deg + 11.25) / 22.5) % 16
    return dirs[idx], arrows[idx]

df['wind_data'] = df['wind_direction_10m'].apply(get_wind_info)
df['dir_name'] = df['wind_data'].apply(lambda x: x[0])
df['arrow'] = df['wind_data'].apply(lambda x: x[1])

def judge_condition(row):
    speed = row['wind_speed_10m']
    direction = row['dir_name']
    if speed > danger_v: return "crimson", "⚠️"
    is_takasu = (31.0 <= lat <= 31.5 and 130.5 <= lon <= 131.0)
    if is_takasu and 5 <= speed <= 10 and direction == "北西": return "gold", "★"
    if 5 <= speed <= 10 and direction in ["西", "南西"]: return "orange", "○"
    if 5 <= speed <= 10: return "skyblue", ""
    return "lightgray", ""

res_all = df.apply(judge_condition, axis=1)
df['color'] = [r[0] for r in res_all]
df['mark'] = [r[1] for r in res_all]

# --- グラフ作成 ---
graph_width_px = max(900, days * 400) 
fig_w = graph_width_px / 100
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(fig_w, 8), dpi=DPI_QUALITY, sharex=True, gridspec_kw={'height_ratios': [3.5, 1.5]})
plt.subplots_adjust(hspace=0.6)

bars = ax1.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.8, width=0.03, align='center')
ax1.axhline(y=danger_v, color='red', linestyle='--', alpha=0.5)
ax1.set_ylabel('風速 (m/s)', fontsize=LABEL_SIZE)
ax1.set_ylim(0, max(df['wind_speed_10m'].max(), danger_v) + 7.5)
ax1.grid(True, axis='both', linestyle=':', alpha=0.5)

# 現在時刻（JST）
jst = timezone(timedelta(hours=9))
now_jst = datetime.now(jst).replace(tzinfo=None)
ax1.axvline(now_jst, color='blue', linestyle='-', alpha=0.6, linewidth=2.5)

ax1.set_xlim(df['time'].iloc[0], df['time'].iloc[-1])

# 棒グラフ上のテキスト
for i, bar in enumerate(bars):
    if i % WIND_STEP == 0:
        h = bar.get_height()
        speed_val = round(df['wind_speed_10m'].iloc[i])
        label_text = f"{df['mark'].iloc[i]}\n{df['dir_name'].iloc[i]}\n{df['arrow'].iloc[i]}\n{speed_val}m"
        ax1.text(bar.get_x() + bar.get_width()/2., h + 0.3, 
                 label_text, ha='center', va='bottom', fontsize=GRAPH_FONT_SIZE, fontweight='bold')

# --- 時間軸のラベル設定（センター合わせ） ---
def format_func(x, pos=None):
    dt = mdates.num2date(x)
    return dt.strftime('%m/%d') + f'\n({jp_weeks[dt.weekday()]})\n' + dt.strftime('%H:%M')

ax2.plot(df['time'], df['temperature_2m'], color='#444444', linewidth=2)
ax2.set_ylabel('気温 (℃)', fontsize=LABEL_SIZE)
ax2.grid(True, linestyle=':', alpha=0.5)

# X軸の目盛りとラベルを同期させる
ax2.xaxis.set_major_locator(mdates.HourLocator(interval=TIME_STEP))
ax2.xaxis.set_major_formatter(plt.FuncFormatter(format_func))

# ラベルの中央揃え設定
plt.setp(ax2.get_xticklabels(), ha='center')

buf = io.BytesIO()
fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.2)
base64_img = base64.b64encode(buf.getvalue()).decode()

# 凡例・表示
st.markdown(f"""
<div style="font-size: 14px; margin-bottom: 10px; line-height: 1.6;">
    <span style="color: gold;">■</span> 最高(北西) &nbsp;&nbsp; <span style="color: orange;">■</span> 良好(西・南西) &nbsp;&nbsp;
    <span style="color: skyblue;">■</span> ジャスト &nbsp;&nbsp; <span style="color: crimson;">■</span> 危険({danger_v}m/s超) &nbsp;&nbsp;
    <span style="color: blue; font-weight: bold;">―</span> 現在時刻
</div>
""", unsafe_allow_html=True)

st.markdown(f'<p style="font-size:{SUBTITLE_SIZE}px; font-weight:bold; margin-bottom:0;">{place_display} 予報</p>', unsafe_allow_html=True)

st.markdown(f"""
<div style="overflow-x: auto; width: 100%; border-radius: 8px; border: 1px solid #eee; background-color: white;">
    <img src="data:image/png;base64,{base64_img}" style="height: 600px; width: auto; max-width: none;">
</div>
""", unsafe_allow_html=True)
