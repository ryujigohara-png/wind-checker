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

# --- 設定 ---
CONFIG = {
    "TITLE_SIZE": 20,
    "SUBTITLE_SIZE": 16,
    "GRAPH_FONT_SIZE": 14,  # ① 14ポイントに変更
    "LABEL_SIZE": 14,
    "DPI": 300,
    "MAP_WIDTH": 700,
    "MAP_HEIGHT": 400
}

#=================================================================================================
def setup_font():
#=================================================================================================
    font_url = "https://github.com/google/fonts/raw/main/ofl/notosansjp/NotoSansJP%5Bwght%5D.ttf"
    font_path = "NotoSansJP.ttf"
    if not os.path.exists(font_path):
        urllib.request.urlretrieve(font_url, font_path)
    fm.fontManager.addfont(font_path)
    plt.rc('font', family='Noto Sans JP', size=CONFIG["GRAPH_FONT_SIZE"])

#=================================================================================================
def fetch_weather_data(lat, lon, days):
#=================================================================================================
    url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&hourly=temperature_2m,wind_speed_10m,wind_direction_10m,weather_code&timezone=Asia%2FTokyo&wind_speed_unit=ms&forecast_days={days}"
    try:
        data = requests.get(url).json()
        df = pd.DataFrame(data["hourly"])
        df['time'] = pd.to_datetime(df['time'])
        df = df.head(24 * days).reset_index(drop=True)
        
        first_time = df['time'].iloc[0]
        padding = pd.DataFrame({
            'time': [first_time - timedelta(hours=i) for i in range(3, 0, -1)],
            'temperature_2m': [None]*3,
            'wind_speed_10m': [None]*3,
            'wind_direction_10m': [None]*3,
            'weather_code': [None]*3
        })
        return pd.concat([padding, df], ignore_index=True)
    except Exception as e:
        st.error(f"データ取得エラー: {e}")
        return None

#=================================================================================================
def get_weather_info(code):
#=================================================================================================
    # ③ 天気カラーを3系統に整理
    if code is None: return "", "black"
    if code <= 2: return "晴", "#FF8C00"       # 晴系（濃いオレンジ）
    if code <= 48: return "曇", "#696969"      # 曇・霧系（ダークグレー）
    if code <= 99: return "雨", "#0000FF"      # 雨系（純粋な青）
    return "？", "black"

#=================================================================================================
def process_wind_data(df, lat, lon, danger_v):
#=================================================================================================
    dirs = ["北", "北北東", "北東", "東北東", "東", "東南東", "南東", "南南東", "南", "南南西", "南西", "西南西", "西", "西北西", "北西", "北北西", "北"]
    arrows = ["↓", "↙", "↙", "↙", "←", "↖", "↖", "↖", "↑", "↗", "↗", "↗", "→", "↘", "↘", "↘", "↓"]
    def get_info(deg):
        if pd.isna(deg): return "", ""
        idx = int((deg + 11.25) / 22.5) % 16
        return dirs[idx], arrows[idx]
    
    df['res'] = df['wind_direction_10m'].apply(get_info)
    df['dir_name'] = df['res'].apply(lambda x: x[0])
    df['arrow'] = df['res'].apply(lambda x: x[1])
    
    weather_res = df['weather_code'].apply(get_weather_info)
    df['w_text'] = [r[0] for r in weather_res]
    df['w_color'] = [r[1] for r in weather_res]

    def judge(row):
        speed = row['wind_speed_10m']
        if pd.isna(speed): return "none", ""
        direction = row['dir_name']
        
        if speed >= 10: 
            return "crimson", ""
        
        target_dirs = ["南" ,"南南西" ,"南西", "西南西", "西", "西北西", "北西", "北北西"]
        if 6 <= speed < 10 and direction in target_dirs:
            return "orange", ""
        
        if 3 <= speed < 6 and direction in target_dirs:
            return "skyblue", ""
            
        return "#D3D3D3", "" # 少し薄いグレー
    
    res_all = df.apply(judge, axis=1)
    df['color'] = [r[0] for r in res_all]
    df['mark'] = [r[1] for r in res_all]
    return df

#=================================================================================================
def create_graph(df, days, danger_v, wind_step, time_step):
#=================================================================================================
    fig_w = max(10, days * 4.5)
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(fig_w, 8), dpi=CONFIG["DPI"], 
                                   gridspec_kw={'height_ratios': [4, 1]})
    plt.subplots_adjust(hspace=0.8)

    jp_weeks = ["月", "火", "水", "木", "金", "土", "日"]
    def formatter(x, p):
        dt = mdates.num2date(x)
        if dt.hour == 0:
            return dt.strftime('%m/%d') + f'\n({jp_weeks[dt.weekday()]})\n' + dt.strftime('%H:%M')
        else:
            return dt.strftime('%H:%M')

    bars = ax1.bar(df['time'], df['wind_speed_10m'], color=df['color'], alpha=0.9, width=0.03)
    ax1.axhline(y=danger_v, color='red', linestyle='--', alpha=0.6)
    ax1.set_ylabel('風速 (m/s)', fontsize=CONFIG["LABEL_SIZE"], color='black')
    ax1.set_ylim(0, max(df['wind_speed_10m'].dropna().max() if not df['wind_speed_10m'].dropna().empty else 0, danger_v) + 11) 
    
    jst = timezone(timedelta(hours=9))
    now_jst = datetime.now(jst).replace(tzinfo=None)
    ax1.axvline(now_jst, color='blue', linestyle='-', alpha=0.6, linewidth=2.5)

    for ax in [ax1, ax2]:
        ax.xaxis.set_major_locator(mdates.HourLocator(byhour=range(0, 24, time_step)))
        ax.xaxis.set_major_formatter(plt.FuncFormatter(formatter))
        ax.set_xlim(df['time'].iloc[0], df['time'].iloc[-1])
        # ④ 軸と文字の色を黒にして鮮明化
        ax.grid(True, linestyle=':', alpha=0.4, color='#000000')
        ax.tick_params(colors='black', labelsize=CONFIG["GRAPH_FONT_SIZE"])
        for spine in ax.spines.values():
            spine.set_edgecolor('black')
            spine.set_linewidth(1.0)
        plt.setp(ax.get_xticklabels(), ha='center', color='black')

    for i, bar in enumerate(bars):
        if not pd.isna(df['wind_speed_10m'].iloc[i]) and i % wind_step == 0:
            h = bar.get_height()
            v = round(df['wind_speed_10m'].iloc[i])
            # ② 天気文字(w_text)をさらに上に配置して重なりを回避
            ax1.text(bar.get_x() + bar.get_width()/2., h + 5.5, df['w_text'].iloc[i], 
                    ha='center', va='bottom', color=df['w_color'].iloc[i], fontweight='bold', fontsize=12)
            
            txt = f"{df['dir_name'].iloc[i]}\n{df['arrow'].iloc[i]}\n{v}m"
            ax1.text(bar.get_x() + bar.get_width()/2., h + 0.3, txt, ha='center', va='bottom', fontweight='bold', color='black')

    ax2.plot(df['time'], df['temperature_2m'], color='black', linewidth=1.5) # 気温線も黒に
    ax2.set_ylabel('気温 (℃)', fontsize=CONFIG["LABEL_SIZE"], color='black')

    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches='tight', pad_inches=0.1)
    return base64.b64encode(buf.getvalue()).decode()

#=================================================================================================
def display_map_selector():
#=================================================================================================
    st.info("ドラッグして地図を動かし、下のボタン「場所は、地図中央地点で確定」を押してください。")
    m = folium.Map(location=[st.session_state.lat, st.session_state.lon], zoom_start=st.session_state.zoom)
    folium.Marker(
        [st.session_state.lat, st.session_state.lon],
        icon=folium.DivIcon(html=f'<div style="font-size: 24pt; color: red; font-weight: bold; text-align: center; width: 50px; margin-left: -25px; margin-top: -25px;">╋</div>')
    ).add_to(m)
    map_out = st_folium(m, width=CONFIG["MAP_WIDTH"], height=CONFIG["MAP_HEIGHT"], key="map_selector")
    if map_out and map_out.get("center"):
        c = map_out["center"]
        z = map_out["zoom"]
        if st.button("場所は、地図中央地点で確定（グラフ更新）", use_container_width=True):
            st.session_state.lat = c["lat"]
            st.session_state.lon = c["lng"]
            st.session_state.zoom = z
            st.rerun()

#=================================================================================================
def main():
#=================================================================================================
    setup_font()
    st.markdown(f'<h1 style="font-size:{CONFIG["TITLE_SIZE"]}px;">⛵ 高須風チェッカー</h1>', unsafe_allow_html=True)

    if 'lat' not in st.session_state:
        st.session_state.lat, st.session_state.lon = 31.337, 130.795
    if 'zoom' not in st.session_state:
        st.session_state.zoom = 12
    if 'last_basho' not in st.session_state:
        st.session_state.last_basho = "高須沖(鹿児島県)"

    st.sidebar.header("設定")
    basho = st.sidebar.selectbox("場所", [
        "高須沖(鹿児島県)", "柏原沖(鹿児島県)", "垂水港(鹿児島県)", 
        "海潟(鹿児島県)", "磯海岸沖(鹿児島県)", "江口浜沖(鹿児島県)", 
        "錦江湾(鹿児島県)", "地図で指定"
    ])
    
    if st.session_state.last_basho != basho:
        if basho == "高須沖(鹿児島県)":
            st.session_state.lat, st.session_state.lon = 31.337, 130.795
        elif basho == "柏原沖(鹿児島県)":
            st.session_state.lat, st.session_state.lon = 31.380, 131.020
        elif basho == "垂水港(鹿児島県)":
            st.session_state.lat, st.session_state.lon = 31.478, 130.668
        elif basho == "海潟(鹿児島県)":
            st.session_state.lat, st.session_state.lon = 31.539, 130.706
        elif basho == "磯海岸沖(鹿児島県)":
            st.session_state.lat, st.session_state.lon = 31.614, 130.577
        elif basho == "江口浜沖(鹿児島県)":
            st.session_state.lat, st.session_state.lon = 31.643, 130.322
        elif basho == "錦江湾(鹿児島県)":
            st.session_state.lat, st.session_state.lon = 31.590, 130.600
        
        st.session_state.zoom = 13
        st.session_state.last_basho = basho

    current_place_name = basho
    use_map = st.sidebar.checkbox("地図で指定する", value=False)
    
    if use_map or basho == "地図で指定":
        current_place_name = f"地図指定地点 ({st.session_state.lat:.3f}, {st.session_state.lon:.3f})"
        display_map_selector()

    days = st.sidebar.slider("表示日数", 1, 8, 8)
    danger_v = st.sidebar.number_input("危険風速(m/s)", value=10)
    w_step = 1 if days <= 1 else (2 if days <= 3 else 3)
    t_step = 3 if days <= 2 else 6

    df = fetch_weather_data(st.session_state.lat, st.session_state.lon, days)
    if df is not None:
        df = process_wind_data(df, st.session_state.lat, st.session_state.lon, danger_v)
        img_base64 = create_graph(df, days, danger_v, w_step, t_step)

        # ⑤ 凡例の順序を「アンダー、ジャスト、オーバー、現在時刻」に変更
        st.markdown(f'''
            <p style="font-size:16px; font-weight:bold;">
                <span style="color:skyblue;">■</span>アンダー(3-6m) 
                <span style="color:orange;">■</span>ジャスト(6-10m) &nbsp;&nbsp;&nbsp; 
                <span style="color:crimson;">---</span> オーバー {danger_v}m/s以上 &nbsp;&nbsp;&nbsp; 
                <span style="color:blue;">―</span>現在時刻
            </p>
            ''', unsafe_allow_html=True)
        
        st.markdown(f'<p style="font-weight:bold; font-size:16px; color:black;">地点: {current_place_name}</p>', unsafe_allow_html=True)
        
        st.markdown(f"""
            <div style="overflow-x: auto; white-space: nowrap; background: white; border-radius: 8px; border: 1px solid #eee;">
                <img src="data:image/png;base64,{img_base64}" style="height: 550px; max-width: none;">
            </div>
        """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
