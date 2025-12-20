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

# --- 場所の管理（セッションを使って座標を保持） ---
if 'lat' not in st.session_state:
    st.session_state.lat = 31.34  # 高須沖
    st.session_state.lon = 130.79

# --- サイドメニュー ---
st.sidebar.header("場所の設定")
use_map = st.sidebar.checkbox("地図から場所を選択する")

if use_map:
    st.info("地図上の好きな場所を【クリック】してください。その地点の予報に切り替わります。")
    # 地図の作成
    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=11)
    # 現在地にピンを立てる
    folium.Marker([st.session_state.lat, st.session_state.lon]).add_to(m)
    
    # 地図を表示し、クリック位置を取得
    # スクロールを邪魔しないよう、マウスホイールズームを無効化
    out = st_folium(m, width=700, height=400, scrolling=False)
    
    # 地図がクリックされたら座標を更新
    if out and out.get("last_clicked"):
        st.session_state.lat = out["last_clicked"]["lat"]
        st.session_state.lon = out["last_clicked"]["lng"]
        st.rerun() # 座標が変わったら即座に再描画

lat, lon = st.session_state.lat, st.session_state.lon
place_display = f"指定地点 ({lat:.2f}, {lon:.2f})" if use_map else "高須沖(鹿児島県)"

days = st.sidebar.slider("表示日数", 1, 7, 7)
danger_v = st.sidebar.number_input("危険風速(m/s)", value=10)

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
    if speed > danger_v: return "crimson", "⚠️", "危険"
    is_takasu = (31.0 <= lat <= 31.5 and 130.5 <= lon <= 131.0)
    if is_takasu and 5 <= speed <= 10 and direction == "北西": return "gold", "★", "最高"
    if 5 <= speed <= 10 and direction in ["西", "南西"]: return "orange", "○", "良好"
    if 5 <= speed <= 10: return "skyblue", "", "ジャスト"
    return "lightgray", "", "微風"

res_all = df.apply(judge_condition, axis=1)
df['color'] = [r[0] for r in res_all]
df['mark'] = [r[1] for r in res_all]
df['cond_name'] = [r[2] for r in res_all]

# 狙い目表示
best_times = df[df['cond_name'] == "最高"]
if not best_times.empty:
    st.success(f"🏆 【{place_display} 狙い目！】\n" + ", ".join(best_times['time'].dt.strftime('%m/%d(%a) %H:%M')))

# --- グラフ作成 ---
graph_width_px = max(800, days * 350)
fig_w = graph_width_px / 100
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(fig_w, 8), dpi=DPI_QUALITY, sharex=True, gridspec_kw={'height_ratios': [3.5, 1.5]})
plt.subplots_adjust(hspace=0.6)

bars = ax1.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.8, width=0.03, align='center')
ax1.axhline(y=danger_v, color='red', linestyle='--', alpha=0.5)
ax1.set_ylabel('風速 (m/s)', fontsize=LABEL_SIZE)
ax1.set_ylim(0, max(df['wind_speed_10m'].max(), danger_v) + 6.5)
ax1.grid(True, axis='both', linestyle=':', alpha=0.5)
ax1.axvline(datetime.now(), color='blue', linestyle='-', alpha=0.4, linewidth=2)
ax1.set_xlim(df['time'].iloc[0], df['time'].iloc[-1])

for i, bar in enumerate(bars):
    t = df['time'].iloc[i]
    w_str = jp_weeks[t.weekday()]
    if i % WIND_STEP == 0:
        h = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., h + 0.4, 
                 f"{df['mark'].iloc[i]}\n{df['dir_name'].iloc[i]}\n{df['arrow'].iloc[i]}", 
                 ha='center', va='bottom', fontsize=GRAPH_FONT_SIZE, fontweight='bold')
    if i % TIME_LABEL_STEP == 0:
        time_str = t.strftime('%m/%d') + f"\n({w_str})\n" + t.strftime('%H:%M')
        ax1.text(bar.get_x() + bar.get_width()/2., -0.8, 
                 time_str, ha='center', va='top', fontsize=GRAPH_FONT_SIZE - 1, color='#555555')

ax2.plot(df['time'], df['temperature_2m'], color='#444444', linewidth=2)
ax2.set_ylabel('気温 (℃)', fontsize=LABEL_SIZE)
ax2.grid(True, linestyle=':', alpha=0.5)

def format_func(x, pos=None):
    dt = mdates.num2date(x)
    return dt.strftime('%m/%d') + f'\n({jp_weeks[dt.weekday()]})\n' + dt.strftime('%H:%M')
ax2.xaxis.set_major_formatter(plt.FuncFormatter(format_func))
ax2.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))

buf = io.BytesIO()
fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.2)
base64_img = base64.b64encode(buf.getvalue()).decode()

# 凡例表示
st.markdown(f"""
<div style="font-size: 14px; margin-bottom: 10px; line-height: 1.6;">
    <span style="color: gold;">■</span> 最高(北西) &nbsp;&nbsp;
    <span style="color: orange;">■</span> 良好(西・南西) &nbsp;&nbsp;
    <span style="color: skyblue;">■</span> ジャスト &nbsp;&nbsp;
    <span style="color: crimson;">■</span> 危険({danger_v}m/s超) &nbsp;&nbsp;
    <span style="color: blue; font-weight: bold;">―</span> 現在時刻
</div>
""", unsafe_allow_html=True)

st.markdown(f'<p style="font-size:{SUBTITLE_SIZE}px; font-weight:bold; margin-bottom:0;">{place_display} 週間予報</p>', unsafe_allow_html=True)

html_code = f"""
<div style="overflow-x: auto; width: 100%; border-radius: 8px; border: 1px solid #eee; background-color: white;">
    <img src="data:image/png;base64,{base64_img}" style="height: 600px; width: auto; max-width: none;">
</div>
"""
st.markdown(html_code, unsafe_allow_html=True)
