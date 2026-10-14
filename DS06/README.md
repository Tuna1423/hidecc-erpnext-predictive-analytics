# DS-06 — Model Scoring API & Dashboard

## 1. Tổng quan

DS-06 là tầng **inference / scoring / integration** cho các model đã được lựa chọn và huấn luyện ở DS-05.

DS-06 **không train lại và không retune model**. Nhiệm vụ chính là:

1. Đọc dữ liệu hiện có từ ERPNext.
2. Xây dựng đúng bộ feature đã dùng khi train model.
3. Load model artifact và tạo prediction.
4. Chuyển prediction thành Risk/Win Band.
5. Ghi kết quả vào Custom Field trên ERPNext.
6. Cung cấp FastAPI để scoring.
7. Cung cấp Streamlit Dashboard để theo dõi và batch scoring.

DS-06 gồm 2 bài toán:

- **Delay Risk** — dự đoán rủi ro chậm tiến độ của Project.
- **Win Probability** — dự đoán xác suất thắng của Opportunity.

> **Nguyên tắc:** không tạo dữ liệu giả để thay thế dữ liệu ERPNext bị thiếu và không đưa các reverse-scoring field vào model input.

---

## 2. Kiến trúc tổng thể

DS-06 có **hai luồng sử dụng chính**.

### 2.1. Luồng Dashboard / FastAPI

```text
                         ERPNext
                            │
             ┌──────────────┴──────────────┐
             │                             │
          Project                       Opportunity
             │                             │
             ▼                             ▼
      Delay Feature Builder         Win Feature Builder
             │                             │
             ▼                             ▼
       Random Forest                   CatBoost
             │                             │
             └──────────────┬──────────────┘
                            ▼
                         FastAPI
                            │
                 ┌──────────┴──────────┐
                 │                     │
                 ▼                     ▼
          Write to ERPNext      Streamlit Dashboard
                 │
                 ▼
              Verify
```

Dashboard gọi FastAPI để thực hiện scoring. FastAPI lấy dữ liệu từ ERPNext, tạo feature, chạy model và ghi score trở lại ERPNext.

Dashboard **không train model**.

### 2.2. Luồng tích hợp trực tiếp qua Whitelisted Method

Ngoài Dashboard, DS-06 có script độc lập để thực hiện UAT/integration trực tiếp với ERPNext:

```text
ERPNext data
    │
    ▼
DS06 script
    │
    ├── Feature Builder
    ├── Local Model
    └── Prediction
    │
    ▼
POST ERPNext Whitelisted Method
    │
    ▼
ERPNext Custom Field
    │
    ▼
GET lại để verify
```

Script này **không yêu cầu FastAPI phải chạy**.

---

## 3. Cấu trúc thư mục

```text
DS06/
│
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
├── scripts/
│   ├── __init__.py
│   └── score_to_erpnext.py
│
├── tests/
│   └── ...
│
├── dashboard.py
├── .env
├── .env.example
├── .gitignore
├── model_metadata.json
├── README.md
└── requirements.txt
```

### Vai trò của các file chính

| File | Vai trò |
|---|---|
| `app/main.py` | FastAPI endpoints và scoring pipeline |
| `app/erpnext_client.py` | REST client kết nối ERPNext |
| `app/feature_builder.py` | Xây dựng feature cho Delay Risk |
| `app/win_feature_builder.py` | Xây dựng feature cho Win Probability |
| `app/predictors.py` | Load model và inference |
| `app/schemas.py` | Request/response schema |
| `models/delay_risk_rf.joblib` | Random Forest Delay Risk |
| `models/win_probability_catboost.cbm` | CatBoost Win Probability |
| `scripts/score_to_erpnext.py` | Scoring và ghi score trực tiếp qua ERPNext Whitelisted Method |
| `dashboard.py` | Streamlit Dashboard |
| `model_metadata.json` | Metadata model, feature và integration |
| `.env` | Cấu hình môi trường và credentials |

---

## 4. Môi trường

Khuyến nghị:

- Windows
- Python virtual environment
- ERPNext server có thể truy cập qua REST API
- ERPNext API Key và API Secret
- FastAPI + Uvicorn
- Streamlit

**Không cần cài ERPNext/Frappe local** nếu chỉ sử dụng ERPNext server thông qua API.

---

## 5. Cài đặt

Mở PowerShell tại thư mục `DS06`.

### 5.1. Tạo virtual environment

Nếu chưa có:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

Nếu `.venv` đã có:

```powershell
.\.venv\Scripts\Activate.ps1
```

Kiểm tra:

```powershell
python --version
```

### 5.2. Cài dependencies

```powershell
python -m pip install -r requirements.txt
```

`requirements.txt` cần có tối thiểu các package chính:

```text
fastapi
uvicorn[standard]
pandas
numpy
scikit-learn
joblib
catboost
requests
python-dotenv
pytest
streamlit
```

---

## 6. Cấu hình `.env`

Tạo file `.env` tại thư mục gốc `DS06`.

Có thể dùng `.env.example` làm template.

```env
ERPNEXT_BASE_URL=https://your-erpnext-host
ERPNEXT_API_KEY=your_api_key
ERPNEXT_API_SECRET=your_api_secret

FASTAPI_BASE_URL=http://127.0.0.1:8001

DELAY_MEDIUM_THRESHOLD=0.40
DELAY_HIGH_THRESHOLD=0.70
WIN_MEDIUM_THRESHOLD=0.40
WIN_HIGH_THRESHOLD=0.70

DELAY_PROBABILITY_FIELD=custom_delay_risk_score
DELAY_BAND_FIELD=custom_risk_band
WIN_PROBABILITY_FIELD=custom_win_probability
WIN_BAND_FIELD=custom_win_band
```

ERPNext authentication sử dụng:

```text
Authorization: token API_KEY:API_SECRET
```

> **Bảo mật:** không đưa API Secret vào source code và không commit `.env` vào repository.

---

## 7. Model và feature input

### 7.1. Delay Risk

**Model:** Random Forest Classifier

**Artifact:**

```text
models/delay_risk_rf.joblib
```

**11 feature input:**

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

Categorical features:

```text
project_type
discipline
```

Prediction:

```text
P(label=1) = P(delay)
```

### 7.2. Win Probability

**Model:** CatBoost Classifier

**Artifact:**

```text
models/win_probability_catboost.cbm
```

**6 feature input:**

```text
lead_source
customer_segment
territory
opportunity_amount
days_lead_to_opp
discount_rate_at_first_quotation
```

Categorical features:

```text
lead_source
customer_segment
territory
```

Prediction:

```text
P(label=1) = P(WON)
```

**Điều kiện áp dụng:** Opportunity phải có **ít nhất một Quotation**. Opportunity chưa có Quotation sẽ không được đưa vào batch Win Probability scoring.

---

## 8. Risk / Win Band

DS-06 sử dụng cùng nguyên tắc threshold cho hai bài toán:

| Probability | Band |
|---:|---|
| `< 0.40` | Thấp |
| `0.40 – < 0.70` | Trung bình |
| `>= 0.70` | Cao |

Các threshold có thể cấu hình qua `.env`.

> Threshold phải được xác nhận với business requirement khi thực hiện UAT chính thức.

---

## 9. FastAPI

### 9.1. Khởi động

Từ thư mục gốc `DS06`:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Các địa chỉ chính:

```text
API:     http://127.0.0.1:8001
Swagger: http://127.0.0.1:8001/docs
Health:  http://127.0.0.1:8001/health
```

### 9.2. Delay Risk endpoints

| Method | Endpoint | Mục đích |
|---|---|---|
| `POST` | `/predict_project_delay` | Predict từ feature input |
| `GET` | `/erpnext/project/{project_name}/features` | Lấy feature từ ERPNext |
| `POST` | `/set_project_delay_score/{project_name}` | Ghi score vào ERPNext |
| `POST` | `/score_project_from_erpnext/{project_name}` | End-to-end scoring |

End-to-end:

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
Write to ERPNext
      ↓
GET lại để verify
```

### 9.3. Win Probability endpoints

| Method | Endpoint | Mục đích |
|---|---|---|
| `POST` | `/predict_opportunity_success` | Predict từ feature input |
| `GET` | `/erpnext/opportunity/{opportunity_name}/features` | Lấy feature từ ERPNext |
| `POST` | `/set_opportunity_win_score/{opportunity_name}` | Ghi score vào ERPNext |
| `POST` | `/score_opportunity_from_erpnext/{opportunity_name}` | End-to-end scoring |

End-to-end:

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
Write to ERPNext
      ↓
GET lại để verify
```

Nếu Opportunity không có Quotation, Win Feature Builder không đủ điều kiện để scoring.

---

## 10. Ghi score vào ERPNext

### 10.1. Delay Risk

Kết quả được ghi vào Project:

```text
custom_delay_risk_score
custom_risk_band
```

Ví dụ UAT:

```text
custom_delay_risk_score = 0.731451589...
custom_risk_band = Cao
```

### 10.2. Win Probability

Kết quả được ghi vào Opportunity:

```text
custom_win_probability
custom_win_band
```

Ví dụ UAT:

```text
custom_win_probability = 0.324008524...
custom_win_band = Thấp
```

---

## 11. Integration trực tiếp với ERPNext Whitelisted Method

Đây là luồng integration dùng để kiểm thử/ghi score trực tiếp vào ERPNext.

Script:

```text
scripts/score_to_erpnext.py
```

### 11.1. Delay Risk

```powershell
python -m scripts.score_to_erpnext project PROJ-0001
```

Script thực hiện:

```text
1. GET Project bundle từ ERPNext
2. Build Delay features
3. Load Random Forest local
4. Predict probability + band
5. POST tới Whitelisted Method của ERPNext
6. GET lại Project
7. Verify custom_delay_risk_score + custom_risk_band
```

Whitelisted Method:

```text
/api/method/hidecc_consulting.api.set_project_delay_score
```

Payload:

```json
{
  "project": "PROJ-0001",
  "score": 0.731451589,
  "band": "Cao"
}
```

### 11.2. Win Probability

```powershell
python -m scripts.score_to_erpnext opportunity CRM-OPP-2026-00002
```

Script thực hiện:

```text
1. GET Opportunity bundle từ ERPNext
2. Kiểm tra Opportunity có Quotation
3. Build Win features
4. Load CatBoost local
5. Predict probability + band
6. POST tới Whitelisted Method của ERPNext
7. GET lại Opportunity
8. Verify custom_win_probability + custom_win_band
```

Whitelisted Method:

```text
/api/method/hidecc_consulting.api.set_opportunity_win_score
```

Payload:

```json
{
  "opportunity": "CRM-OPP-2026-00002",
  "score": 0.324008524,
  "band": "Thấp"
}
```

### 11.3. Authentication

Cả hai request sử dụng:

```text
Authorization: token API_KEY:API_SECRET
```

Credentials được đọc từ `.env`.

> **Quan trọng:** trong luồng này, **DS-06 script gọi ERPNext**. ERPNext không gọi ngược vào FastAPI.

---

## 12. Streamlit Dashboard

### 12.1. Khởi động

Giữ FastAPI chạy ở Terminal 1:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Mở Terminal 2:

```powershell
.\.venv\Scripts\Activate.ps1
streamlit run dashboard.py
```

Dashboard mặc định:

```text
http://localhost:8501
```

### 12.2. Dashboard có gì?

#### Tổng quan

- Tổng số Project
- Delay đã score
- Delay chưa score
- Tổng số Opportunity
- Win đã score
- Win chưa score
- Phân bố Delay Risk Band
- Phân bố Win Probability Band

#### Delay Risk

- Danh sách Project
- Lọc theo Risk Band
- Lọc theo trạng thái scoring
- Lọc theo probability
- Score lại một Project
- Batch score Project chưa score

#### Win Probability

- Danh sách Opportunity
- Lọc theo Win Band
- Lọc theo trạng thái scoring
- Lọc theo probability
- Score lại một Opportunity
- Batch score Opportunity đủ điều kiện

---

## 13. Trạng thái scoring trên Dashboard

Dashboard phân biệt rõ:

### Đã score

ERPNext có probability và Band hợp lệ:

```text
Cao
Trung bình
Thấp
```

### Chưa score

Band đang trống.

Trong prototype hiện tại, ERPNext có thể trả:

```text
probability = 0
band = ""
```

Dashboard **không diễn giải trường hợp này thành prediction 0%**.

Nó hiển thị:

```text
—
Chưa score
```

Mục đích là phân biệt:

```text
0% prediction
```

với:

```text
chưa chạy scoring
```

> `Chưa score` chỉ phản ánh trạng thái score hiện có trên ERPNext; không tự động kết luận rằng record thiếu dữ liệu.

---

## 14. Batch Scoring

Batch scoring giúp chạy nhiều record mà không cần score từng record thủ công.

### 14.1. Delay Risk

Dashboard lấy các Project chưa score và lần lượt gọi:

```text
/score_project_from_erpnext/{project_name}
```

Ví dụ:

```text
Dashboard
   ↓
PROJ-0002
   ↓
PROJ-0003
   ↓
PROJ-0004
   ↓
...
```

### 14.2. Win Probability

Win Probability có một điều kiện quan trọng:

> **Chỉ Opportunity có ít nhất một Quotation mới đủ điều kiện scoring.**

Do đó Dashboard chia logic thành:

```text
All Opportunities
        │
        ├── Có Quotation ──→ Có thể Win-score
        │
        └── Không Quotation → Không score
```

Batch Win chỉ lấy các Opportunity:

1. Chưa có Win score.
2. Có ít nhất một Quotation.

Opportunity không có Quotation được bỏ qua, không tạo feature giả và không được xem là prediction thất bại.

Nếu một record trong batch lỗi, Dashboard giữ lại kết quả của các record thành công và hiển thị lỗi của record thất bại.

---

## 15. Quy trình sử dụng hàng ngày

Nếu sử dụng **Dashboard**, chạy hai terminal:

### Terminal 1 — FastAPI

```powershell
cd <path>\DS06
.\.venv\Scripts\Activate.ps1
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

### Terminal 2 — Dashboard

```powershell
cd <path>\DS06
.\.venv\Scripts\Activate.ps1
streamlit run dashboard.py
```

Sau đó mở:

```text
FastAPI:   http://127.0.0.1:8001/docs
Dashboard: http://localhost:8501
```

Nếu chỉ cần kiểm thử integration trực tiếp với ERPNext, có thể dùng script mà **không cần chạy FastAPI**:

```powershell
python -m scripts.score_to_erpnext project PROJ-0001
python -m scripts.score_to_erpnext opportunity CRM-OPP-2026-00002
```

---

## 16. UAT / kiểm thử đã thực hiện

### 16.1. Delay Risk

Project đã kiểm thử end-to-end:

```text
PROJ-0001
```

Kết quả được ghi và GET lại từ ERPNext:

```text
custom_delay_risk_score = 0.731451589...
custom_risk_band = Cao
```

Trạng thái:

```text
Write:  OK
Verify: OK
```

### 16.2. Win Probability

Một số Opportunity đã kiểm thử end-to-end:

| Opportunity | Probability | Band | Write | Verify |
|---|---:|---|---|---|
| CRM-OPP-2026-00002 | 32.40% | Thấp | OK | OK |
| CRM-OPP-2026-00003 | 60.60% | Trung bình | OK | OK |
| CRM-OPP-2026-00004 | 10.41% | Thấp | OK | OK |
| CRM-OPP-2026-00005 | 11.80% | Thấp | OK | OK |

Opportunity thiếu thông tin cần thiết cho feature builder không được thay thế bằng dữ liệu giả.

---

## 17. Các ràng buộc quan trọng

### 17.1. Reverse-scoring fields không phải model input

Các field sau là **output**:

```text
custom_delay_risk_score
custom_risk_band
custom_win_probability
custom_win_band
```

Không được đưa chúng trở lại làm feature input cho model.

### 17.2. Không train lại trong DS-06

DS-06 chỉ thực hiện:

```text
Inference
Scoring
Integration
Dashboard
```

Model đã được lựa chọn và train ở DS-05.

### 17.3. Không retune model trong DS-06

Không thay đổi model chỉ nhằm mục đích làm metric hoặc UAT score đẹp hơn.

### 17.4. Không thêm feature mới

Feature input phải giữ đúng whitelist đã xác định ở DS-05.

### 17.5. Không tạo dữ liệu giả

Nếu dữ liệu ERPNext cần thiết cho feature builder không tồn tại hoặc không đủ điều kiện, không tự tạo giá trị giả để ép model chạy.

### 17.6. Probability không phải kết luận chắc chắn

Ví dụ:

```text
Win Probability = 60.60%
```

không có nghĩa Opportunity chắc chắn thắng. Đây là prediction/score do model tạo ra dựa trên dữ liệu và cách huấn luyện đã xác định ở DS-05.

### 17.7. Credentials

API Key/Secret phải được lấy từ environment `.env`, không hard-code vào source code.

---

## 18. Troubleshooting

### `ModuleNotFoundError: No module named 'app'`

Đảm bảo terminal đang ở thư mục gốc `DS06`:

```powershell
cd <path>\DS06
```

Kiểm tra:

```powershell
python -c "import app; print(app.__file__)"
```

Sau đó chạy:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

### `File does not exist: dashboard.py`

Kiểm tra:

```powershell
dir dashboard.py
```

File phải nằm tại:

```text
DS06\dashboard.py
```

Sau đó:

```powershell
streamlit run dashboard.py
```

### FastAPI trả HTTP 500

Kiểm tra traceback trong terminal đang chạy Uvicorn.

Nếu response chứa kiểu NumPy như:

```text
numpy.int64
numpy.float64
```

cần chuyển sang Python native type trước khi trả JSON.

### ERPNext trả lỗi 417 khi ghi Band

Kiểm tra Select option của Custom Field.

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

nếu Custom Field đang cấu hình theo giá trị tiếng Việt.

### Win Probability không score được Opportunity

Kiểm tra trước tiên:

1. Opportunity có tồn tại.
2. Opportunity có ít nhất một Quotation.
3. Các field cần thiết cho Win Feature Builder có dữ liệu hợp lệ.
4. FastAPI đang chạy nếu scoring qua Dashboard.

Không tạo dữ liệu giả để vượt qua điều kiện này.

---

## 19. Khi bàn giao DS-06

Không cần train lại model nếu bàn giao đúng các artifact đã được sử dụng ở DS-05.

Các artifact chính:

```text
models/delay_risk_rf.joblib
models/win_probability_catboost.cbm
```

Cần bàn giao thêm:

```text
app/
scripts/
dashboard.py
model_metadata.json
requirements.txt
README.md
.env.example
```

`.env` chứa credentials nên **không chia sẻ công khai**.

Nếu sử dụng cùng ERPNext server, DS-06 có thể đọc các score đã tồn tại trên ERPNext.

Nếu sử dụng ERPNext khác, cần cấu hình `.env` trỏ tới server mới và thực hiện scoring trên dữ liệu của hệ thống đó.

---

## 20. Trạng thái DS-06

| Hạng mục | Trạng thái |
|---|---|
| Load Delay Risk model | Done |
| Load Win Probability model | Done |
| ERPNext REST client | Done |
| Delay Feature Builder | Done |
| Win Feature Builder | Done |
| FastAPI scoring API | Done |
| Delay write-back | Done |
| Delay verification | Done |
| Win write-back | Done |
| Win verification | Done |
| Direct Whitelisted Method integration | Done |
| Streamlit Dashboard | Done — prototype |
| Batch Delay scoring | Done |
| Batch Win scoring có kiểm tra Quotation | Done |
| Đã score / Chưa score handling | Done |

### Giới hạn hiện tại

- Dashboard hiện được xem là **prototype phục vụ kiểm thử và đánh giá giao diện**.
- UI/UX có thể tiếp tục hoàn thiện sau khi thống nhất cách trình bày với người dùng cuối.
- DS-06 không thay đổi hoặc đánh giá lại model training của DS-05.

---

## 21. Tóm tắt nhanh

Nếu chỉ cần nhớ cách chạy:

### Dashboard

```powershell
# Terminal 1
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload

# Terminal 2
streamlit run dashboard.py
```

### Direct ERPNext integration

```powershell
python -m scripts.score_to_erpnext project PROJ-0001
python -m scripts.score_to_erpnext opportunity CRM-OPP-2026-00002
```

### Hai output chính trên ERPNext

**Project:**

```text
custom_delay_risk_score
custom_risk_band
```

**Opportunity:**

```text
custom_win_probability
custom_win_band
```

**Điểm cần nhớ nhất:** Win Probability chỉ áp dụng cho Opportunity **đã có ít nhất một Quotation**; các reverse-scoring field là **output, không phải input**; DS-06 chỉ inference/integration, **không train hoặc retune model**.
