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
from datetime import datetime, timedelta
import matplotlib.dates as mdates

# ==========================================
# ★設定エリア：ここを書き換えて調整してください★
# ==========================================
TITLE_SIZE = 20       # メインタイトルの大きさ
SUBTITLE_SIZE = 16    # 「週間予報」などの見出しの大きさ
GRAPH_FONT_SIZE = 10  # グラフ内の文字（風向・矢印・日時）
LABEL_SIZE = 12       # 縦軸ラベルの大きさ
DPI_QUALITY = 300     # 画質（300が最高品質）
WIND_STEP = 3         # 風向・矢印を表示する間隔（3なら3時間おき）
# ==========================================

# --- 日本語フォント設定 ---
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
FONT_PATH = "NotoSansJP.ttf"
if not os.path.exists(FONT_PATH):
    urllib.request.urlretrieve(FONT_URL, FONT_PATH)
fm.fontManager.addfont(FONT_PATH)
plt.rc('font', family='Noto Sans JP', size=GRAPH_FONT_SIZE)

st.set_page_config(page_title="高須沖・風況チェッカー", layout="wide")
warnings.simplefilter('ignore', UserWarning)

# タイトル
st.markdown(f'<h1 style="font-size:{TITLE_SIZE}px;">⛵ 高須沖・風況チェッカー</h1>', unsafe_allow_html=True)

# サイドメニュー
st.sidebar.header("設定")
basho = st.sidebar.selectbox("場所", ["高須沖(鹿児島県)", "錦江湾(鹿児島県)"])
days = st.sidebar.slider("表示日数", 1, 7, 7)
danger_v = st.sidebar.number_input("危険風速(m/s)", value=10)

# --- データ取得 ---
lat, lon = (31.34, 130.79) if basho == "高須沖(鹿児島県)" else (31.59, 130.60)
url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m&timezone=Asia%2FTokyo&wind_speed_unit=ms&past_days=1"
data = requests.get(url).json()

df = pd.DataFrame(data["hourly"])
df['time'] = pd.to_datetime(df['time'])

# 今日の0時以降を抽出
today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
df = df[df['time'] >= today_start].head(24 * days)

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
    if 5 <= speed <= 10 and direction == "北西": return "gold", "★", "最高"
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
    st.success(f"🏆 【狙い目！最高コンディション】\n" + ", ".join(best_times['time'].dt.strftime('%m/%d(%a) %H:%M')))

# --- グラフ作成 ---
graph_width_px = max(800, days * 350) # 横幅を少し広げて重なりを緩和
fig_w = graph_width_px / 100

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(fig_w, 8), dpi=DPI_QUALITY, sharex=True, gridspec_kw={'height_ratios': [4, 1]})
plt.subplots_adjust(hspace=0.4) # 上下の間隔を少し広げる

# 風速グラフ
bars = ax1.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.8, width=0.03)
ax1.axhline(y=danger_v, color='red', linestyle='--', alpha=0.5)
ax1.set_ylabel('風速 (m/s)', fontsize=LABEL_SIZE)
ax1.set_ylim(0, max(df['wind_speed_10m'].max(), danger_v) + 6)
ax1.grid(True, axis='both', linestyle=':', alpha=0.5)

# 現在時刻の線
now = datetime.now()
ax1.axvline(now, color='blue', linestyle='-', alpha=0.4, linewidth=2)

# 風向・矢印・日時テキスト
for i, bar in enumerate(bars):
    if i % WIND_STEP == 0:
        h = bar.get_height()
        t = df['time'].iloc[i]
        # 日時を3行（日付、曜日、時刻）で作成
        time_str = t.strftime('%m/%d\n(%a)\n%H:%M')
        # 風情報のラベル
        ax1.text(bar.get_x() + bar.get_width()/2., h + 0.5, 
                 f"{df['mark'].iloc[i]}\n{df['dir_name'].iloc[i]}\n{df['arrow'].iloc[i]}", 
                 ha='center', va='bottom', fontsize=GRAPH_FONT_SIZE, fontweight='bold')
        # 日時をグラフ上部（または下部）に追加
        ax1.text(bar.get_x() + bar.get_width()/2., -1.5, # 棒の下側に配置
                 time_str, ha='center', va='top', fontsize=GRAPH_FONT_SIZE - 1)

# 気温グラフ
ax2.plot(df['time'], df['temperature_2m'], color='#444444', linewidth=2)
ax2.set_ylabel('気温 (℃)', fontsize=LABEL_SIZE)
ax2.grid(True, linestyle=':', alpha=0.5)

# X軸の目盛り設定（下段）
# ここでも3行（日付、曜日、時刻）で表示
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d\n(%a)\n%H:%M'))
ax2.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))
plt.xticks(fontsize=GRAPH_FONT_SIZE)

# 仕上げ
buf = io.BytesIO()
fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.2)
base64_img = base64.b64encode(buf.getvalue()).decode()

st.markdown(f'<p style="font-size:{SUBTITLE_SIZE}px; font-weight:bold; margin-bottom:0;">週間予報（横にスクロール）</p>', unsafe_allow_html=True)

html_code = f"""
<div style="overflow-x: auto; width: 100%; border-radius: 8px; border: 1px solid #eee; background-color: white;">
    <img src="data:image/png;base64,{base64_img}" style="height: 600px; width: auto; max-width: none;">
</div>
"""
st.markdown(html_code, unsafe_allow_html=True)

st.write(f"凡例: 金色=最高(北西) / 橙色=良好(西・南西) / 赤色=危険({danger_v}m/s超) / 青線=現在時刻")
