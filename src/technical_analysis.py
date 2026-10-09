"""TV2: technical analysis. Accepts TV1 DataFrame, never fetches data."""
from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt


def analyze_technical(price_df: pd.DataFrame, chart_dir='charts') -> dict:
    def unavailable(message):
        return {'data_available':False,'technical_score':None,'score':None,'label':'Unavailable',
                'positives':[],'risks':[],'technical_view':message,'commentary':message,
                'charts':{},'error':message}
    required = ['Date','Open','High','Low','Close','Volume']
    if not isinstance(price_df, pd.DataFrame):
        return unavailable('Đầu vào không phải DataFrame.')
    missing = [c for c in required if c not in price_df]
    if missing:
        return unavailable('Thiếu cột: ' + ', '.join(missing))
    df = price_df[required].copy()
    df['Date'] = pd.to_datetime(df['Date'], errors='coerce')
    for c in required[1:]:
        df[c] = pd.to_numeric(df[c], errors='coerce')
    df = df.dropna().sort_values('Date').drop_duplicates('Date', keep='last')
    df = df[(df['Low']>0)&(df['Volume']>=0)&(df['High']>=df[['Open','Close','Low']].max(axis=1))&
            (df['Low']<=df[['Open','Close']].min(axis=1))].reset_index(drop=True)
    if len(df) < 51:
        return unavailable(f'Cần ít nhất 51 phiên hợp lệ; hiện có {len(df)}.')
    c = df['Close']
    df['MA20'] = c.rolling(20).mean()
    df['MA50'] = c.rolling(50).mean()
    delta = c.diff()
    gains, losses = delta.clip(lower=0).rolling(14).mean(), (-delta.clip(upper=0)).rolling(14).mean()
    df['RSI'] = 100 - 100/(1 + gains/losses.replace(0,np.nan))
    df.loc[(losses==0)&(gains>0),'RSI']=100
    df.loc[(losses==0)&(gains==0),'RSI']=50
    df['MACD'] = c.ewm(span=12,adjust=False).mean()-c.ewm(span=26,adjust=False).mean()
    df['MACD_Signal'] = df['MACD'].ewm(span=9,adjust=False).mean()
    df['MACD_Histogram'] = df['MACD']-df['MACD_Signal']
    df['AvgVolume20'] = df['Volume'].rolling(20).mean()
    df['VolumeRatio'] = df['Volume']/df['AvgVolume20'].replace(0,np.nan)
    df['DailyReturn'] = c.pct_change()
    df['Volatility20'] = df['DailyReturn'].rolling(20).std()*np.sqrt(252)
    last = df.iloc[-1]
    close, ma20, ma50 = (float(last[k]) for k in ('Close','MA20','MA50'))
    rsi, macd, signal = (float(last[k]) for k in ('RSI','MACD','MACD_Signal'))
    vol = float(last['Volatility20'])
    ratio = float(last['VolumeRatio']) if pd.notna(last['VolumeRatio']) else None
    if not all(np.isfinite(v) for v in (close,ma20,ma50,rsi,macd,signal,vol)):
        return unavailable('Một số chỉ báo không tính được.')
    positives, risks, signals = [], [], {}
    def add(name, status, score, reason=None):
        signals[name]={'signal':status,'score':score}
        if reason:
            (positives if status=='Positive' else risks).append(reason)
        return score
    if close>ma20>ma50:
        s_ma=add('MA','Positive',100,'Giá trên MA20 và MA20 trên MA50.')
    elif close<ma20<ma50:
        s_ma=add('MA','Negative',0,'Giá dưới MA20 và MA20 dưới MA50.')
    else:
        s_ma=add('MA','Neutral',50)
    if rsi>70:
        s_rsi=add('RSI','Negative',25,f'RSI {rsi:.1f}: vùng quá mua.')
    elif rsi<30:
        s_rsi=add('RSI','Neutral',50,f'RSI {rsi:.1f}: vùng quá bán, cần thận trọng.')
    else:
        s_rsi=add('RSI','Positive',100,f'RSI {rsi:.1f}: chưa vào vùng cực trị.')
    if macd>signal:
        s_macd=add('MACD','Positive',100,'MACD nằm trên đường tín hiệu.')
    elif macd<signal:
        s_macd=add('MACD','Negative',0,'MACD nằm dưới đường tín hiệu.')
    else:
        s_macd=add('MACD','Neutral',50)
    price_change=close-float(df.iloc[-2]['Close'])
    if ratio is not None and ratio>=1.2 and price_change>0:
        s_volume=add('Volume','Positive',100,'Khối lượng tăng cùng chiều giá.')
    elif ratio is not None and ratio>=1.2 and price_change<0:
        s_volume=add('Volume','Negative',25,'Khối lượng cao trong phiên giảm giá.')
    else:
        s_volume=add('Volume','Neutral',50)
    if vol<0.20:
        s_vol=add('Volatility','Positive',100,'Biến động 20 phiên ở mức thấp theo ngưỡng mô hình.')
    elif vol<=0.40:
        s_vol=add('Volatility','Neutral',50)
    else:
        s_vol=add('Volatility','Negative',0,f'Biến động thường niên hóa cao: {vol:.1%}.')
    score=round(.30*s_ma+.20*s_rsi+.25*s_macd+.10*s_volume+.15*s_vol,2)
    label='Positive' if score>=70 else 'Neutral' if score>=40 else 'Negative'
    view=(f'Technical Score {score}/100 ({label}). Close {close:,.2f}; MA20 {ma20:,.2f}; '
          f'MA50 {ma50:,.2f}; RSI {rsi:.1f}; MACD {macd:.3f}; biến động {vol:.1%}. '
          'Đây là điểm heuristic, không phải dự báo chắc chắn.')
    out=Path(chart_dir); out.mkdir(parents=True,exist_ok=True)
    paths={}
    def save(fig,key):
        path=out/f'technical_{key}.png'
        fig.tight_layout(); fig.savefig(path,dpi=135,bbox_inches='tight'); plt.close(fig)
        paths[key]=str(path)
    fig,ax=plt.subplots(figsize=(9,3.5))
    for key in ['Close','MA20','MA50']:
        ax.plot(df['Date'],df[key],label=key)
    ax.legend(); ax.grid(alpha=.2); ax.set_title('Price & Moving Averages'); fig.autofmt_xdate(); save(fig,'price_ma')
    fig,ax=plt.subplots(figsize=(9,2.8))
    ax.plot(df['Date'],df['RSI']); ax.axhline(70,ls='--',color='red'); ax.axhline(30,ls='--',color='green')
    ax.set_ylim(0,100); ax.grid(alpha=.2); ax.set_title('RSI (14)'); fig.autofmt_xdate(); save(fig,'rsi')
    fig,ax=plt.subplots(figsize=(9,2.8))
    ax.plot(df['Date'],df['MACD'],label='MACD'); ax.plot(df['Date'],df['MACD_Signal'],label='Signal')
    ax.bar(df['Date'],df['MACD_Histogram'],alpha=.25,label='Histogram'); ax.legend(); ax.grid(alpha=.2)
    ax.set_title('MACD (12,26,9)'); fig.autofmt_xdate(); save(fig,'macd')
    return {'data_available':True,'technical_score':score,'score':score,'label':label,
            'analysis_date':str(last['Date'].date()),'observations':len(df),
            'close':close,'ma20':ma20,'ma50':ma50,'rsi':rsi,'macd':macd,'macd_signal':signal,
            'macd_histogram':float(last['MACD_Histogram']),'volume':float(last['Volume']),
            'avg_volume_20':float(last['AvgVolume20']),'volume_ratio':ratio,'volatility':vol,
            'signals':signals,'positives':positives,'risks':risks,'technical_view':view,
            'commentary':view,'charts':paths,'data':df}
