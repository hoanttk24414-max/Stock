# StockLens — Investment Intelligence Platform

Bộ code hoàn chỉnh cho hệ thống phân tích cơ hội đầu tư cổ phiếu với giao diện research dashboard theo mockup StockLens, hỗ trợ **nhiều mã cổ phiếu** thay vì hard-code một mã.

## 1. Chức năng

- Nhập ticker linh hoạt: `FPT`, `HPG`, `MWG`, `VNM`, `ACB`...; StockLens thử `TICKER.VN` trước cho cổ phiếu Việt Nam. Nếu không có dữ liệu, hệ thống thử ticker gốc (hữu ích cho `AAPL`, `MSFT`...).
- Chọn ngày bắt đầu, ngày kết thúc và hồ sơ nhà đầu tư.
- Dữ liệu OHLCV từ Yahoo Finance qua `yfinance`.
- Kỹ thuật: MA20, MA50, RSI(14), MACD(12,26,9), Volume Ratio, Volatility 20.
- Fundamental, Valuation, News Sentiment, Market Risk/Safety.
- Investment Score cố định: `25% Fundamental + 25% Valuation + 25% Technical + 15% News + 10% Risk/Safety`.
- Why This Score và 3 profile: Thận trọng, Cân bằng, Tăng trưởng.
- Giao diện dashboard gồm: KPI cards, chart giá + volume, donut score, thông tin nhanh, 6 tab chi tiết.
- Xuất báo cáo Equity Research PDF khoảng 15 trang.
- Thiếu dữ liệu được ghi rõ; không tự tạo số liệu giả.

## 2. Cài đặt Windows

Mở thư mục có `app.py`, sau đó chạy:

```powershell
python -m pip install -r requirements.txt
```

Hoặc double-click `INSTALL_WINDOWS.bat`.

## 3. Chạy StockLens

```powershell
python -m streamlit run app.py
```

Hoặc double-click `START_STOCKLENS.bat`.

## 4. Kiểm thử

```powershell
python -m unittest tests.test_modules -v
```

## 5. Cấu trúc

```text
app.py
market_data.py
requirements.txt
src/
  technical_analysis.py
  fundamental_analysis.py
  valuation.py
  news_analysis.py
  scoring.py
  report.py
tests/
  test_modules.py
```

## 6. Nguồn và giới hạn

- Price/volume + company metadata: Yahoo Finance via `yfinance`.
- News: Google News RSS.
- Các điểm số là heuristic của dự án và chưa được backtest như một chiến lược giao dịch.
- Metadata tài chính bên thứ ba cần được đối chiếu BCTC công bố khi sử dụng thực tế.
- StockLens không tự tạo target price/peer comparison/forecast khi không có mô hình hoặc dữ liệu hỗ trợ.
- Dự án phục vụ học tập, không phải tư vấn đầu tư.
