import requests
import pandas as pd
import json
from datetime import datetime, timedelta
import time

def get_twse_data():
    print("⏳ 正在啟動 [復古籌碼雷達] 系統...")
    
    # 為了確保抓到有開盤的日子，實務上可用迴圈往前推，這裡簡化抓取最新資料日
    # 這裡以證交所 API 為例，你需要分別抓取「三大法人買賣超(T86)」與「借券賣出餘額(TWT93U)」
    
    # 模擬當前日期 (實務上若逢假日需寫迴圈遞減日期)
    today_str = datetime.now().strftime("%Y%m%d")
    
    print(f"📡 正在請求 {today_str} 三大法人買賣超資料...")
    url_t86 = f"https://www.twse.com.tw/fund/T86?response=json&date={today_str}&selectType=ALL"
    res_t86 = requests.get(url_t86).json()
    
    # 簡單防錯：如果當天沒資料，就中止 (實務上可以寫 while 往前找工作日)
    if res_t86.get('stat') != 'OK':
        print("⚠️ 今日無資料或尚未更新，請稍後再試或調整日期。")
        return
        
    print(f"📡 正在請求 {today_str} 借券賣出資料...")
    url_short = f"https://www.twse.com.tw/exchangeReport/TWT93U?response=json&date={today_str}"
    res_short = requests.get(url_short).json()

    # --- 資料清洗與整理 (將證交所原始資料轉為 DataFrame) ---
    # 1. 整理三大法人買賣超
    fields_t86 = res_t86['fields']
    data_t86 = res_t86['data']
    df_t86 = pd.DataFrame(data_t86, columns=fields_t86)
    df_t86 = df_t86[['證券代號', '證券名稱', '外陸資買賣超股數(不含外資自營商)', '投信買賣超股數', '自營商買賣超股數']]
    df_t86.columns = ['StockID', 'Name', 'Foreign_Net', 'Trust_Net', 'Dealer_Net']
    
    # 2. 整理借券賣出 (包含外資/投信/自營商的借券賣出，通常外資佔大宗)
    # 證交所 TWT93U 欄位通常包含: 證券代號, 證券名稱, 本日借券賣出數量...等
    fields_short = res_short['fields']
    data_short = res_short['data']
    df_short = pd.DataFrame(data_short, columns=fields_short)
    # 欄位因應證交所格式可能變動，通常第4欄(index 4)或第5欄是「本日借券賣出數量」
    # 這裡我們取 '證券代號' 和 '本日借券賣出數量'
    df_short = df_short[[fields_short[0], fields_short[4]]] 
    df_short.columns = ['StockID', 'Short_Sell_Vol']

    # --- 數值轉型與資料合併 ---
    # 將字串中的逗號去除並轉為整數
    for col in ['Foreign_Net', 'Trust_Net', 'Dealer_Net']:
        df_t86[col] = df_t86[col].astype(str).str.replace(',', '').astype(float)
    df_short['Short_Sell_Vol'] = df_short['Short_Sell_Vol'].astype(str).str.replace(',', '').astype(float)

    # 將兩個表依據「股票代號」合併
    df_merge = pd.merge(df_t86, df_short, on='StockID', how='left').fillna(0)

    # --- 核心運算：真實做多 (扣除借券賣出) ---
    # 註：實務上借券賣出難以完美拆分是外資、投信還是自營商做的，但 90% 以上是外資
    # 為了嚴格標準，我們將「總借券賣出數量」全部視為外資的扣減項 (或者按比例扣)，這裡示範直接扣在外資上
    df_merge['Foreign_True_Long'] = df_merge['Foreign_Net'] - df_merge['Short_Sell_Vol']
    df_merge['Trust_True_Long'] = df_merge['Trust_Net'] # 投信較少借券，維持買賣超
    df_merge['Dealer_True_Long'] = df_merge['Dealer_Net']
    
    # 篩選條件：三大法人【真實做多】全部大於 0
    condition = (df_merge['Foreign_True_Long'] > 0) & (df_merge['Trust_True_Long'] > 0) & (df_merge['Dealer_True_Long'] > 0)
    final_df = df_merge[condition].copy()

    # 排序：以外資真實做多數量由大到小排序
    final_df = final_df.sort_values(by='Foreign_True_Long', ascending=False)

    # 將單位轉為「張」並取整數
    final_df['Foreign_True_Long'] = (final_df['Foreign_True_Long'] / 1000).astype(int)
    final_df['Trust_True_Long'] = (final_df['Trust_True_Long'] / 1000).astype(int)
    final_df['Dealer_True_Long'] = (final_df['Dealer_True_Long'] / 1000).astype(int)

    # 轉出 JSON 給前端
    output_data = {
        "update_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "total_count": len(final_df),
        "data": final_df[['StockID', 'Name', 'Foreign_True_Long', 'Trust_True_Long', 'Dealer_True_Long']].to_dict(orient='records')
    }

    with open('chips_data.json', 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4)
        
    print(f"✅ 運算完成！共找出 {len(final_df)} 檔三大法人全數真實做多股票。資料已存為 chips_data.json")

if __name__ == "__main__":
    get_twse_data()
