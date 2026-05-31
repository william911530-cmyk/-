import requests
import pandas as pd
import json
from datetime import datetime, timedelta
import time

def get_latest_data():
    print("⏳ 正在啟動 [復古籌碼雷達] 系統...")
    
    # 設定最多往前找幾天 (避免連續長假無限迴圈)
    max_lookback = 10
    current_date = datetime.now()
    
    res_t86 = None
    res_short = None
    target_date_str = ""

    # 迴圈往前推，尋找最近一個有開盤且有資料的日子
    for i in range(max_lookback):
        target_date_str = current_date.strftime("%Y%m%d")
        print(f"📡 嘗試抓取 {target_date_str} 資料...")
        
        url_t86 = f"https://www.twse.com.tw/fund/T86?response=json&date={target_date_str}&selectType=ALL"
        
        try:
            res = requests.get(url_t86)
            res_t86 = res.json()
            
            # 證交所如果有資料，stat 會回傳 'OK'
            if res_t86.get('stat') == 'OK':
                print(f"✅ 成功找到 {target_date_str} 的三大法人資料！")
                break
            else:
                print(f"⚠️ {target_date_str} 無資料，往前推一天...")
                current_date -= timedelta(days=1)
                time.sleep(3) # 避免被證交所 ban IP
        except Exception as e:
            print(f"❌ 請求失敗: {e}")
            current_date -= timedelta(days=1)
            time.sleep(3)

    if not res_t86 or res_t86.get('stat') != 'OK':
        print("🚨 錯誤：連續多日皆無資料，系統中止。")
        return

    # 確定有三大法人資料後，用同一天去抓借券賣出資料
    print(f"📡 正在請求 {target_date_str} 借券賣出資料...")
    url_short = f"https://www.twse.com.tw/exchangeReport/TWT93U?response=json&date={target_date_str}"
    res_short = requests.get(url_short).json()

    # --- 資料清洗與合併 ---
    fields_t86 = res_t86['fields']
    df_t86 = pd.DataFrame(res_t86['data'], columns=fields_t86)
    df_t86 = df_t86[['證券代號', '證券名稱', '外陸資買賣超股數(不含外資自營商)', '投信買賣超股數', '自營商買賣超股數']]
    df_t86.columns = ['StockID', 'Name', 'Foreign_Net', 'Trust_Net', 'Dealer_Net']
    
    fields_short = res_short['fields']
    df_short = pd.DataFrame(res_short['data'], columns=fields_short)
    # TWT93U 第 0 欄通常是代號，第 4 欄是「本日借券賣出數量」
    df_short = df_short[[fields_short[0], fields_short[4]]] 
    df_short.columns = ['StockID', 'Short_Sell_Vol']

    # 去除逗號並轉數字
    for col in ['Foreign_Net', 'Trust_Net', 'Dealer_Net']:
        df_t86[col] = df_t86[col].astype(str).str.replace(',', '').astype(float)
    df_short['Short_Sell_Vol'] = df_short['Short_Sell_Vol'].astype(str).str.replace(',', '').astype(float)

    # 合併兩表 (缺值補 0)
    df_merge = pd.merge(df_t86, df_short, on='StockID', how='left').fillna(0)

    # --- 核心運算：真實做多 (買超減去借券賣出) ---
    df_merge['Foreign_True_Long'] = df_merge['Foreign_Net'] - df_merge['Short_Sell_Vol']
    df_merge['Trust_True_Long'] = df_merge['Trust_Net'] 
    df_merge['Dealer_True_Long'] = df_merge['Dealer_Net']
    
    # 條件：三大法人【真實做多】全部大於 0
    condition = (df_merge['Foreign_True_Long'] > 0) & (df_merge['Trust_True_Long'] > 0) & (df_merge['Dealer_True_Long'] > 0)
    final_df = df_merge[condition].copy()

    # 以外資真實做多數量由大到小排序
    final_df = final_df.sort_values(by='Foreign_True_Long', ascending=False)

    # 單位轉「張」
    for col in ['Foreign_True_Long', 'Trust_True_Long', 'Dealer_True_Long']:
        final_df[col] = (final_df[col] / 1000).astype(int)

    # 輸出 JSON
    output_data = {
        "update_time": f"資料日期: {target_date_str} (更新於 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')})",
        "total_count": len(final_df),
        "data": final_df[['StockID', 'Name', 'Foreign_True_Long', 'Trust_True_Long', 'Dealer_True_Long']].to_dict(orient='records')
    }

    with open('chips_data.json', 'w', encoding='utf-8') as f:
        json.dump(output_data, f, ensure_ascii=False, indent=4)
        
    print(f"✅ 運算完成！共找出 {len(final_df)} 檔股票。已覆蓋 chips_data.json")

if __name__ == "__main__":
    get_latest_data()
