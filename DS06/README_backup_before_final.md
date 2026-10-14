# DS-06 — Model Scoring API & Dashboard

## 1. Mục tiêu

DS-06 triển khai các model đã được lựa chọn ở DS-05 thành một pipeline scoring có thể kết nối trực tiếp với ERPNext.

DS-06 gồm 2 bài toán:

- **Delay Risk**: dự đoán rủi ro chậm tiến độ của Project.
- **Win Probability**: dự đoán xác suất thắng của Opportunity.

Kết quả prediction được ghi trực tiếp vào các Custom Field trên ERPNext.

---

## 2. Kiến trúc

```text
                         ERPNext HIDECC
                              │
                ┌─────────────┴─────────────┐
                │                           │
             Project                   Opportunity
                │                           │
                ▼                           ▼
        Delay Feature Builder       Win Feature Builder
                │                           │
                ▼                           ▼
          Random Forest                 CatBoost
                │                           │
                └─────────────┬─────────────┘
                              ▼
                         FastAPI DS-06
                              │
                    ┌─────────┴─────────┐
                    │                   │
                    ▼                   ▼
             Write back ERPNext    Streamlit Dashboard
```

Dashboard đọc score hiện có từ ERPNext. Dashboard không train lại model.

---

## 3. Cấu trúc thư mục

```text
DS06/
├── .venv/
├── app/
│   ├── __init__.py
│   ├── main.py
│   ├── erpnext_client.py
│   ├── feature_builder.py
│   ├── win_feature_builder.py
│   ├── predictors.py
│   └── schemas.py
│
├── models/
│   ├── delay_risk_rf.joblib
│   └── win_probability_catboost.cbm
│
├── tests/
│   └── ...
│
├── dashboard.py
├── .env
├── .gitignore
├── model_metadata.json
├── README.md
└── requirements.txt
```

### Vai trò chính

| File | Vai trò |
|---|---|
| `app/main.py` | FastAPI endpoints |
| `app/erpnext_client.py` | Kết nối REST API với ERPNext |
| `app/feature_builder.py` | Tạo feature cho Delay Risk |
| `app/win_feature_builder.py` | Tạo feature cho Win Probability |
| `app/predictors.py` | Load model và inference |
| `app/schemas.py` | Request schema |
| `models/delay_risk_rf.joblib` | Random Forest Delay Risk |
| `models/win_probability_catboost.cbm` | CatBoost Win Probability |
| `dashboard.py` | Streamlit Dashboard |
| `.env` | Cấu hình ERPNext/API |

---

# 4. Yêu cầu môi trường

Khuyến nghị:

- Windows
- Python virtual environment
- ERPNext server có thể truy cập qua REST API
- Có API Key và API Secret của ERPNext
- FastAPI/Uvicorn
- Streamlit

Không cần cài ERPNext/Frappe local nếu sử dụng ERPNext server từ API.

---

# 5. Thiết lập môi trường

Mở PowerShell tại thư mục DS06:

```powershell
cd nơi chứa project
```

Nếu `.venv` đã tồn tại:

```powershell
.\.venv\Scripts\Activate.ps1
```

Kiểm tra:

```powershell
python --version
```

---

## 6. Cài dependencies

Cài dependencies của DS-06:

```powershell
python -m pip install -r requirements.txt
```

Dashboard cần Streamlit. Nếu chưa có:

```powershell
python -m pip install streamlit
```

Nếu CatBoost chưa được cài:

```powershell
python -m pip install catboost
```

Kiểm tra CatBoost:

```powershell
python -c "import catboost; print(catboost.__version__)"
```

---

# 7. Cấu hình `.env`

Tạo/kiểm tra file:

```text
nơi chứa projeck\DS06\.env
```

Cấu hình dạng:

```env
ERPNEXT_BASE_URL=https://your-erpnext-host
ERPNEXT_API_KEY=your_api_key
ERPNEXT_API_SECRET=your_api_secret

DELAY_MEDIUM_THRESHOLD=0.40
DELAY_HIGH_THRESHOLD=0.70

WIN_MEDIUM_THRESHOLD=0.40
WIN_HIGH_THRESHOLD=0.70

DELAY_PROBABILITY_FIELD=custom_delay_risk_score
DELAY_BAND_FIELD=custom_risk_band

WIN_PROBABILITY_FIELD=custom_win_probability
WIN_BAND_FIELD=custom_win_band
```

> Không commit `.env` hoặc API Secret vào Git.

API authentication sử dụng:

```text
Authorization: token API_KEY:API_SECRET
```

---

# 8. Chạy FastAPI

Từ thư mục gốc DS06:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Nếu chạy thành công:

```text
http://127.0.0.1:8001
```

Swagger:

```text
http://127.0.0.1:8001/docs
```

Health check:

```text
http://127.0.0.1:8001/health
```

---

# 9. Các FastAPI endpoint

## 9.1. Delay Risk

### Predict từ feature đầu vào

```text
POST /predict_project_delay
```

### Lấy feature từ ERPNext

```text
GET /erpnext/project/{project_name}/features
```

### Ghi score trực tiếp vào ERPNext

```text
POST /set_project_delay_score/{project_name}
```

### End-to-end scoring

```text
POST /score_project_from_erpnext/{project_name}
```

Pipeline:

```text
ERPNext Project
      ↓
Feature Builder
      ↓
Random Forest
      ↓
Delay Probability
      ↓
Risk Band
      ↓
PUT vào ERPNext
      ↓
GET lại để verify
```

---

## 9.2. Win Probability

### Predict từ feature đầu vào

```text
POST /predict_opportunity_success
```

### Lấy feature từ ERPNext

```text
GET /erpnext/opportunity/{opportunity_name}/features
```

### Ghi score trực tiếp vào ERPNext

```text
POST /set_opportunity_win_score/{opportunity_name}
```

### End-to-end scoring

```text
POST /score_opportunity_from_erpnext/{opportunity_name}
```

Pipeline:

```text
ERPNext Opportunity
        ↓
Win Feature Builder
        ↓
CatBoost
        ↓
Win Probability
        ↓
Win Band
        ↓
PUT vào ERPNext
        ↓
GET lại để verify
```

---

# 10. Custom Field trên ERPNext

## Project — Delay Risk

Kết quả được ghi vào:

```text
custom_delay_risk_score
custom_risk_band
```

Ví dụ:

```text
custom_delay_risk_score = 0.731451589
custom_risk_band = Cao
```

## Opportunity — Win Probability

Kết quả được ghi vào:

```text
custom_win_probability
custom_win_band
```

Ví dụ:

```text
custom_win_probability = 0.324008524
custom_win_band = Thấp
```

Các giá trị Band đang sử dụng:

```text
Cao
Trung bình
Thấp
```

---

# 11. Chạy Dashboard

Giữ FastAPI chạy ở Terminal 1:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Mở Terminal 2:

```powershell
nơi chứa project\DS06
```

Chạy:

```powershell
streamlit run dashboard.py
```

Dashboard mặc định:

```text
http://localhost:8501
```

---

# 12. Chức năng Dashboard

Dashboard hiện có 3 khu vực:

## Tổng quan

Hiển thị:

- Tổng số Project
- Delay đã score
- Delay chưa score
- Tổng số Opportunity
- Win đã score
- Win chưa score
- Phân bố Delay Risk Band
- Phân bố Win Probability Band

## Delay Risk

Có thể:

- Xem danh sách Project.
- Lọc theo Risk Band.
- Lọc theo trạng thái scoring.
- Lọc theo probability.
- Score lại một Project.
- Score hàng loạt các Project chưa score.

## Win Probability

Có thể:

- Xem danh sách Opportunity.
- Lọc theo Win Band.
- Lọc theo trạng thái scoring.
- Lọc theo probability.
- Score lại một Opportunity.
- Score hàng loạt các Opportunity chưa score.

---

# 13. Ý nghĩa trạng thái scoring

Dashboard phân biệt:

### Đã score

ERPNext có Band:

```text
Cao
Trung bình
Thấp
```

và probability tương ứng.

### Chưa score

Band đang trống.

Trong prototype hiện tại, ERPNext có thể trả:

```text
probability = 0
band = ""
```

đối với record chưa từng được scoring.

Dashboard **không hiển thị trường hợp này là prediction 0%**.

Nó hiển thị:

```text
—
Chưa score
```

Điều này tránh nhầm giữa:

```text
0% prediction
```

và:

```text
chưa chạy scoring
```

> Trạng thái `Chưa score` hiện chỉ phản ánh việc chưa có score được ghi vào ERPNext. Không tự động kết luận rằng record thiếu dữ liệu.

---

# 14. Batch Scoring

Không cần bấm Score từng Project/Opportunity.

Trong Dashboard có:

```text
Score tất cả X Project chưa score
```

và:

```text
Score tất cả X Opportunity chưa score
```

Batch scoring hoạt động bằng cách gọi lần lượt các endpoint FastAPI hiện có.

Ví dụ:

```text
Dashboard
    ↓
/score_project_from_erpnext/PROJ-0002
    ↓
/score_project_from_erpnext/PROJ-0003
    ↓
/score_project_from_erpnext/PROJ-0004
    ↓
...
```

Nếu một record không scoring được, Dashboard giữ lại kết quả của các record thành công và hiển thị lỗi của record thất bại.

---

# 15. Quy trình chạy đầy đủ

Mỗi lần sử dụng:

### Terminal 1

```powershell
cd nơi chứa project\DS06
.\.venv\Scripts\Activate.ps1

uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

### Terminal 2

```powershell
cd nơi chứa project\DS06
.\.venv\Scripts\Activate.ps1

streamlit run dashboard.py
```

Sau đó:

```text
FastAPI:
http://127.0.0.1:8001/docs

Dashboard:
http://localhost:8501
```

---

# 16. Khi gửi DS06 cho người khác

Không cần train lại model.

Các model đã được lưu:

```text
models/
├── delay_risk_rf.joblib
└── win_probability_catboost.cbm
```

Nếu người nhận sử dụng **cùng ERPNext server** và cấu hình `.env` trỏ tới server đó:

```text
DS06
   ↓
cùng ERPNext
```

Dashboard có thể đọc các score đã được lưu trên ERPNext.

Không cần score lại chỉ để xem các kết quả đã tồn tại.

Nếu sử dụng một ERPNext khác:

```text
DS06
   ↓
ERPNext mới
```

thì ERPNext mới sẽ chưa có score và cần thực hiện scoring trên dữ liệu của hệ thống đó.

---

# 17. Kiểm thử đã thực hiện

## Delay Risk

Đã kiểm thử end-to-end trên Project thực tế:

```text
PROJ-0001
```

Kết quả đã được ghi và đọc xác nhận từ ERPNext:

```text
custom_delay_risk_score = 0.731451589...
custom_risk_band = Cao
```

Sau đó tiếp tục kiểm thử scoring trên các Project khác trong Dashboard.

## Win Probability

Đã kiểm thử end-to-end trên các Opportunity thực tế.

Một số kết quả UAT:

| Opportunity | Probability | Band | Write | Verify |
|---|---:|---|---|---|
| CRM-OPP-2026-00002 | 32.40% | Thấp | OK | OK |
| CRM-OPP-2026-00003 | 60.60% | Trung bình | OK | OK |
| CRM-OPP-2026-00004 | 10.41% | Thấp | OK | OK |
| CRM-OPP-2026-00005 | 11.80% | Thấp | OK | OK |

Một số Opportunity có thể thiếu thông tin Lead/Quotation cần thiết cho feature builder. Không nên tạo giá trị giả để làm đầy feature.

---

# 18. Model

## Delay Risk

Model được chọn ở DS-05:

```text
Random Forest
```

Artifact:

```text
models/delay_risk_rf.joblib
```

Feature đầu vào:

```text
contract_value
planned_duration_days
n_disciplines_known_at_snapshot
n_open_disciplines_at_snapshot
total_workload_pct
pct_staff_overloaded_at_snapshot
n_open_overdue_tasks_at_snapshot
pm_historic_late_rate
customer_historic_late_rate
project_type
discipline
```

## Win Probability

Model được chọn ở DS-05:

```text
CatBoost
```

Artifact:

```text
models/win_probability_catboost.cbm
```

Feature đầu vào:

```text
lead_source
customer_segment
territory
opportunity_amount
days_lead_to_opp
discount_rate_at_first_quotation
```

Các output field:

```text
custom_win_probability
custom_win_band
```

---

# 19. Lưu ý quan trọng

### Không đưa reverse-scoring field làm input

Các field:

```text
custom_win_probability
custom_win_band
custom_delay_risk_score
custom_risk_band
```

là **output**, không phải feature đầu vào của model.

### Không train lại trong DS-06

DS-06 là tầng:

```text
Inference / Scoring / Integration
```

Model đã được lựa chọn và train ở DS-05.

### Không chia sẻ API Secret

File `.env` phải được giữ riêng.

Không commit:

```text
.env
```

vào repository.

### Không hiểu probability là xác suất chắc chắn

Ví dụ:

```text
Win Probability = 60.60%
```

không có nghĩa Opportunity chắc chắn thắng.

Nó là score/xác suất do model tạo ra theo dữ liệu và cách huấn luyện đã được xác định ở DS-05.

---

# 20. Troubleshooting

## `ModuleNotFoundError: No module named 'app'`

Đảm bảo terminal đang ở thư mục gốc:

```powershell
cd nơi chứa project\DS06
```

Kiểm tra:

```powershell
python -c "import app; print(app.__file__)"
```

Chạy FastAPI:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

---

## `File does not exist: dashboard.py`

Kiểm tra:

```powershell
dir dashboard.py
```

File phải nằm tại:

```text
nơi chứa project\DS06\dashboard.py
```

Sau đó:

```powershell
streamlit run dashboard.py
```

---

## FastAPI trả HTTP 500

Kiểm tra terminal đang chạy Uvicorn để xem traceback.

Nếu lỗi liên quan:

```text
numpy.int64
numpy.float64
```

cần chuyển các giá trị NumPy sang kiểu Python native trước khi trả JSON.

---

## ERPNext trả lỗi 417 khi ghi Band

Kiểm tra giá trị Select option của field.

DS-06 hiện sử dụng:

```text
Cao
Trung bình
Thấp
```

Không sử dụng:

```text
High
Medium
Low
```

nếu Custom Field của ERPNext đang cấu hình tiếng Việt.

---

# 21. Trạng thái DS-06

DS-06 hiện đã có:

- Load Delay Risk model
- Load Win Probability model
- ERPNext REST client
- Delay feature builder
- Win feature builder
- FastAPI scoring API
- Write Delay score vào ERPNext
- Verify Delay score
- Write Win score vào ERPNext
- Verify Win score
- Streamlit Dashboard prototype
- Batch scoring trên Dashboard
- Phân biệt record đã score/chưa score

Dashboard hiện là **prototype phục vụ kiểm thử và đánh giá giao diện**. Các thay đổi UI/UX tiếp theo có thể thực hiện sau khi thống nhất cách trình bày với người dùng cuối.
