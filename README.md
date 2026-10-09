StockLens — Investment Intelligence Platform
StockLens là hệ thống phân tích và đánh giá cơ hội đầu tư cổ phiếu, được xây dựng theo dạng equity research dashboard. Hệ thống hỗ trợ nhiều mã cổ phiếu Việt Nam, tổng hợp dữ liệu thị trường, phân tích kỹ thuật, tài chính, định giá, tin tức và rủi ro thành một Investment Score thống nhất.
> Dự án phục vụ mục đích học tập và nghiên cứu. Kết quả không phải khuyến nghị mua, bán hoặc nắm giữ chứng khoán.
---
1. Chức năng chính
Nhập mã cổ phiếu linh hoạt như `FPT`, `HPG`, `MWG`, `VNM`, `ACB`, `TCB`...
Chọn ngày bắt đầu, ngày kết thúc và hồ sơ nhà đầu tư.
Dữ liệu giá và khối lượng từ DNSE OpenAPI.
Báo cáo tài chính và chỉ số tài chính từ vnstock / KBS.
Tin tức từ Google News RSS.
Không hard-code một mã cổ phiếu cụ thể.
Một lần phân tích tương ứng với một mã cổ phiếu.
Khi dữ liệu thiếu, hệ thống hiển thị `N/A` hoặc cảnh báo thay vì tự tạo số liệu giả.
Phân tích kỹ thuật
StockLens sử dụng các chỉ báo:
MA20
MA50
RSI(14)
MACD(12, 26, 9)
Volume Ratio
Volatility
Maximum Drawdown
Phân tích tài chính
Đối với doanh nghiệp thông thường, Fundamental Score sử dụng các nhóm chỉ tiêu như:
ROE
ROA
Biên lợi nhuận ròng
Tăng trưởng doanh thu
Debt/Equity
Current Ratio
Đối với ngân hàng/tổ chức tài chính, StockLens sử dụng bộ chỉ tiêu phù hợp hơn với đặc thù ngành và không ép các chỉ tiêu như Current Ratio hoặc Debt/Equity của doanh nghiệp thông thường vào mô hình. Tùy dữ liệu KBS có sẵn, hệ thống có thể sử dụng:
ROE
ROA
Tăng trưởng lợi nhuận sau thuế
Tăng trưởng tổng tài sản
Vốn chủ sở hữu / Tổng tài sản
Tăng trưởng thu nhập hoạt động
Chỉ tiêu không có dữ liệu được loại khỏi mẫu số thay vì bị chấm 0.
Phân tích định giá
StockLens hiện sử dụng hai lớp định giá:
1. Historical Valuation
So sánh định giá hiện tại của doanh nghiệp với lịch sử của chính doanh nghiệp:
P/E hiện tại
P/B hiện tại
Median P/E lịch sử
Median P/B lịch sử
Valuation Score gốc được tính từ:
P/E hiện tại: 30%
P/B hiện tại: 25%
P/E so với median lịch sử: 25%
P/B so với median lịch sử: 20%
2. Peer Valuation
StockLens bổ sung so sánh với các doanh nghiệp cùng ngành theo phân loại ICB:
Peer Score
Median P/E của peers
Median P/B của peers
Giá hàm ý theo P/E
Giá hàm ý theo P/B
Peer Fair Value
Upside / Downside
Chất lượng bộ peer
Cảnh báo peer thiếu dữ liệu, ROE âm hoặc độ phân tán multiples lớn
Peer Valuation là lớp phân tích bổ sung và không thay thế Valuation Score gốc trong Investment Score.
`Peer Fair Value` là giá trị hàm ý tương đối theo multiples của nhóm so sánh, không phải target price và không phải định giá nội tại DCF.
Tin tức và triển vọng
Thu thập tin từ Google News RSS.
Chấm News Score bằng heuristic sentiment theo tiêu đề và độ mới của tin.
Không xem News Score là mô hình NLP toàn văn.
Investment Score
Công thức cố định của dự án:
```text
Investment Score
= 25% Fundamental
+ 25% Valuation
+ 25% Technical
+ 15% News
+ 10% Risk/Safety
```
Phân loại:
```text
80–100   Cơ hội cao
65–<80   Tích cực
50–<65   Trung lập
<50      Thận trọng
```
Ngoài Investment Score cơ sở, giao diện còn hiển thị góc nhìn theo ba hồ sơ:
Thận trọng
Cân bằng
Tăng trưởng
---
2. Giao diện
Dashboard StockLens gồm các khu vực chính:
Tổng quan đầu tư
Phân tích kỹ thuật
Phân tích tài chính
Phân tích định giá
Tin tức & triển vọng
Báo cáo đầu tư
Giao diện sử dụng KPI cards, biểu đồ giá/khối lượng, biểu đồ kỹ thuật, bảng BCTC, bảng peer comparison và các cảnh báo dữ liệu.
---
3. Báo cáo PDF
StockLens có thể xuất Equity Research PDF 8 trang từ chính kết quả đang hiển thị trên dashboard.
Báo cáo bao gồm:
Research Snapshot
Technical Analysis
Market Risk & Liquidity
Financial Performance
Balance Sheet & Financial Health
Valuation, Peer Valuation & News
Investment Score & Investor Profiles
Financial Appendix, Methodology & Disclaimer
Người dùng có thể lựa chọn các nhóm nội dung cần đưa vào PDF.
---
4. Cài đặt
Khuyến nghị sử dụng Python 3.12.
Mở terminal tại thư mục chứa `app.py`:
```powershell
python -m pip install -r requirements.txt
```
Nếu máy có nhiều phiên bản Python, cần bảo đảm terminal đang dùng môi trường Python đã cài `vnstock`, `streamlit` và các thư viện của dự án.
Ví dụ với Anaconda:
```powershell
C:\Users\HP\anaconda3\python.exe -m pip install -r requirements.txt
```
---
5. Cấu hình DNSE
Dữ liệu OHLCV được lấy qua DNSE OpenAPI.
Thông tin xác thực DNSE nên được lưu trong file `.env` theo cấu hình mà `market_data.py` sử dụng.
Không commit file `.env` lên GitHub.
Nên có trong `.gitignore`:
```text
.env
__pycache__/
*.pyc
```
---
6. Chạy StockLens
```powershell
python -m streamlit run app.py
```
Hoặc với môi trường Anaconda:
```powershell
C:\Users\HP\anaconda3\python.exe -m streamlit run app.py
```
Sau khi Streamlit khởi động, mở địa chỉ local mà terminal cung cấp và nhập mã cổ phiếu cần phân tích.
---
7. Cấu trúc project
```text
StockLens/
│
├── app.py
├── market_data.py
├── requirements.txt
├── .env
│
├── src/
│   ├── technical_analysis.py
│   ├── vnstock_data.py
│   ├── fundamental_analysis.py
│   ├── valuation.py
│   ├── peer_valuation.py
│   ├── news_analysis.py
│   ├── scoring.py
│   └── report.py
│
├── charts/
├── assets/
└── README.md
```
---
8. Luồng xử lý
```text
Người dùng nhập ticker
        ↓
DNSE OpenAPI
Giá + OHLCV
        ↓
vnstock / KBS
BCTC + ratios
        ↓
Technical Analysis
Fundamental Analysis
Historical Valuation
Peer Valuation
News Analysis
Risk/Safety
        ↓
Investment Score
        ↓
Dashboard + PDF Report
```
---
9. Nguồn dữ liệu
Khối	Nguồn / phương pháp
Giá & OHLCV	DNSE OpenAPI
BCTC & ratios	vnstock / KBS
Technical	MA20, MA50, RSI(14), MACD, Volume Ratio, Volatility, Drawdown
Fundamental	Bộ chỉ tiêu phù hợp theo loại doanh nghiệp
Historical Valuation	P/E, P/B hiện tại và lịch sử doanh nghiệp
Peer Valuation	vnstock Reference + Fundamental ratio, phân nhóm theo ICB
News	Google News RSS
Investment Score	Mô hình heuristic của StockLens
---
10. Giới hạn
Investment Score là mô hình heuristic phục vụ học tập, chưa được backtest như một chiến lược giao dịch.
Dữ liệu DNSE, vnstock/KBS và Google News có thể thay đổi, cập nhật chậm hoặc thiếu một số trường.
Với ngành đặc thù như ngân hàng, StockLens sử dụng bộ chỉ tiêu phù hợp hơn thay vì ép cùng một mô hình với doanh nghiệp sản xuất/dịch vụ.
Peer Valuation phụ thuộc số lượng và chất lượng doanh nghiệp cùng ngành có dữ liệu P/E, P/B hợp lệ.
Khi số peer hợp lệ ít hoặc multiples phân tán mạnh, StockLens hiển thị cảnh báo chất lượng.
`Peer Fair Value` chỉ là giá trị hàm ý tương đối, không phải giá mục tiêu chính thức.
StockLens hiện không triển khai DCF; đây là giới hạn được giữ có chủ đích để tránh tạo giá trị nội tại từ các giả định chưa đủ cơ sở.
Dữ liệu thiếu được hiển thị `N/A` hoặc loại khỏi phép tính phù hợp; hệ thống không tự bịa số để lấp dữ liệu.
Kết quả không cấu thành tư vấn đầu tư cá nhân.
---
11. Phạm vi dự án
StockLens tập trung vào việc hỗ trợ phân tích cơ hội đầu tư một cổ phiếu, không phải hệ thống giao dịch chứng khoán.
Dự án không bao gồm:
Đặt lệnh mua/bán
Quản lý tài khoản chứng khoán
Thanh toán
Đăng nhập/đăng ký người dùng
Cam kết hoặc dự báo chắc chắn lợi nhuận
Mục tiêu chính là tạo một quy trình nghiên cứu có cấu trúc, minh bạch về nguồn dữ liệu, phương pháp chấm điểm và giới hạn của mô hình.