import streamlit as st
import requests
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
import urllib.request
import os
import warnings
from datetime import datetime
import matplotlib.dates as mdates

# --- 日本語フォント設定 ---
FONT_URL = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
FONT_PATH = "NotoSansJP.ttf"
if not os.path.exists(FONT_PATH):
    urllib.request.urlretrieve(FONT_URL, FONT_PATH)
fm.fontManager.addfont(FONT_PATH)
plt.rc('font', family='Noto Sans JP')

st.set_page_config(page_title="高須沖・風況チェッカー", layout="wide")
warnings.simplefilter('ignore', UserWarning)

st.title("⛵ 高須沖・風況チェッカー")

# サイドメニュー
st.sidebar.header("設定")
basho = st.sidebar.selectbox("場所", ["高須沖(鹿児島県)", "錦江湾(鹿児島県)"])
days = st.sidebar.slider("表示日数", 1, 7, 7)
danger_v = st.sidebar.number_input("危険風速(m/s)", value=10)

# データ取得
lat, lon = (31.34, 130.79) if basho == "高須沖(鹿児島県)" else (31.59, 130.60)
url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m&timezone=Asia%2FTokyo&wind_speed_unit=ms"
data = requests.get(url).json()

df = pd.DataFrame(data["hourly"])
df['time'] = pd.to_datetime(df['time'])
df = df.head(24 * days)

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

# --- グラフの描画部分のみ差し替え ---

# 1日あたり8インチの幅。1週間なら56インチ。
dynamic_width = max(12, days * 8) 

fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(dynamic_width, 8), dpi=200, 
                               sharex=True, gridspec_kw={'height_ratios': [3, 1]})
plt.subplots_adjust(hspace=0.2)

# 風速バーの描画
bars = ax1.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.8)
ax1.axhline(y=danger_v, color='red', linestyle='--', alpha=0.5)
ax1.set_ylabel('風速 (m/s)', fontsize=14)
ax1.set_ylim(0, max(df['wind_speed_10m'].max(), danger_v) + 5)
ax1.grid(True, axis='y', linestyle=':', alpha=0.5)

# 文字の書き込み
step = 1 if days <= 2 else 2
for i, bar in enumerate(bars):
    if i % step == 0:
        h = bar.get_height()
        ax1.text(bar.get_x() + bar.get_width()/2., h + 0.3, 
                 f"{df['mark'].iloc[i]}\n{df['dir_name'].iloc[i]}\n{df['arrow'].iloc[i]}", 
                 ha='center', va='bottom', fontsize=9, fontweight='bold')

# 気温の描画
ax2.plot(df['time'], df['temperature_2m'], color='#444444', linewidth=2)
ax2.fill_between(df['time'], df['temperature_2m'], color='gray', alpha=0.1)
ax2.set_ylabel('気温 (℃)', fontsize=12)
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d(%a)\n%H:%M'))
ax2.xaxis.set_major_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))

# --- 【ここがポイント】横スクロール枠を強制的に作成 ---
# HTMLとCSSを使って、幅2000px以上の「横に長い箱」の中にグラフを閉じ込めます
import streamlit.components.v1 as components

st.write("### 週間予報（右にスワイプして確認）")

# グラフを一度画像として保存せず、そのままスクロール可能なdivの中に入れる設定
# overflow-x: auto でスクロールを発生させます
st.markdown(
    """
    <style>
    .scroll-container {
        overflow-x: auto;
        white-space: nowrap;
        width: 100%;
    }
    .scroll-container img {
        max-width: none !important; /* ブラウザの自動縮小を禁止 */
        width: auto !important;
    }
    </style>
    """,
    unsafe_allow_html=True
)

with st.container():
    # スクロール用の箱を作成
    st.markdown('<div class="scroll-container">', unsafe_allow_html=True)
    # ここでグラフを表示（use_container_width=Falseが必須）
    st.pyplot(fig, use_container_width=False)
    st.markdown('</div>', unsafe_allow_html=True)

st.write(f"凡例: 金色=最高(北西) / 橙色=良好(西・南西) / 赤色=危険({danger_v}m/s超)")
