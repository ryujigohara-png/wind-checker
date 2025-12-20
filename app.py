import requests
import pandas as pd
import matplotlib.pyplot as plt
import japanize_matplotlib
import warnings
from datetime import datetime
import matplotlib.dates as mdates

# 警告非表示
warnings.simplefilter('ignore', UserWarning)

#@title ⛵ 高須沖・風況チェッカー（高精細テスト版） { display-mode: "form" }

#@markdown ---
場所 = "高須沖(鹿児島県)" #@param ["高須沖(鹿児島県)", "錦江湾(鹿児島県)"]
表示日数 = 7 #@param {type:"slider", min:1, max:7, step:1}
危険風速 = 10 #@param {type:"number"}
#@markdown ---

# 1. データ取得
LAT, LON = (31.34, 130.79) if 場所 == "高須沖(鹿児島県)" else (31.59, 130.60)
url = f"https://api.open-meteo.com/v1/forecast?latitude={LAT}&longitude={LON}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m&timezone=Asia%2FTokyo&wind_speed_unit=ms"
data = requests.get(url).json()

# 2. データの加工
df = pd.DataFrame(data["hourly"])
df['time'] = pd.to_datetime(df['time'])
df = df.head(24 * 表示日数) 

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
    if speed > 危険風速: return "crimson", "⚠️", "危険"
    if 5 <= speed <= 10 and direction == "北西": return "gold", "★", "最高"
    if 5 <= speed <= 10 and direction in ["西", "南西"]: return "orange", "○", "良好"
    if 5 <= speed <= 10: return "skyblue", "", "ジャスト"
    return "lightgray", "", "微風"

res_all = df.apply(judge_condition, axis=1)
df['color'] = [r[0] for r in res_all]
df['mark'] = [r[1] for r in res_all]
df['cond_name'] = [r[2] for r in res_all]

# 3. グラフの描画（★dpi=200を設定して高解像度化★）
# layout='constrained' を使うと文字の重なりを自動で防いでくれます
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 10), dpi=200, 
                               gridspec_kw={'height_ratios': [3, 1]},
                               layout='constrained')

# 上段：風速
bars = ax1.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.8, width=0.03)
ax1.axhline(y=危険風速, color='red', linestyle='--', linewidth=1, alpha=0.5)
ax1.set_ylabel('風速 (m/s)', fontsize=12)
ax1.set_title(f'⛵ {場所} 風況チェッカー ({表示日数}日間)', fontsize=18, fontweight='bold')
ax1.set_ylim(0, max(df['wind_speed_10m'].max(), 危険風速) + 5)
ax1.grid(True, axis='y', linestyle=':', alpha=0.5)

# 表示ステップの計算
step = 2 if 表示日数 <= 2 else (4 if 表示日数 <= 4 else 6)

for i, bar in enumerate(bars):
    if i % step == 0: 
        height = bar.get_height()
        display_text = f"{df['mark'].iloc[i]}\n{df['dir_name'].iloc[i]}\n{df['arrow'].iloc[i]}"
        ax1.text(bar.get_x() + bar.get_width()/2., height + 0.3, 
                 display_text, ha='center', va='bottom', 
                 fontsize=8 if 表示日数 > 4 else 10, fontweight='bold')

# 下段：気温
ax2.plot(df['time'], df['temperature_2m'], color='#555555', linewidth=1.5, alpha=0.7)
ax2.fill_between(df['time'], df['temperature_2m'], color='gray', alpha=0.1)
ax2.set_ylabel('気温 (℃)', fontsize=10)
ax2.grid(True, axis='y', linestyle=':', alpha=0.5)

# X軸の設定
ax2.xaxis.set_major_formatter(mdates.DateFormatter('%m/%d(%a)'))
ax2.xaxis.set_major_locator(mdates.DayLocator())
ax2.xaxis.set_minor_locator(mdates.HourLocator(byhour=[0, 6, 12, 18]))
ax2.tick_params(axis='x', which='major', labelsize=11, rotation=0)

plt.show()

# 狙い目情報の表示
best_times = df[df['cond_name'] == "最高"]
if not best_times.empty:
    print(f"\n🏆 【狙い目！最高コンディション】")
    print(" ・ " + "  ・ ".join(best_times['time'].dt.strftime('%m/%d(%a) %H:%M')))
