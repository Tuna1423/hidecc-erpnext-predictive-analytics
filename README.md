# HIDECC ERPNext — Data Science Project

> End-to-end Data Science project for **HIDECC ERPNext**, covering data understanding, feature/label definition, baseline modeling, model selection, explainability, inference, ERPNext integration, and dashboard visualization.

---

## 1. Project Overview

Project này xây dựng hai bài toán Machine Learning trên dữ liệu ERPNext thực tế:

1. **Project Delay Risk** — dự đoán rủi ro một Project/Discipline Allocation bị trễ.
2. **Opportunity Win Probability** — ước lượng xác suất một Opportunity có Quotation sẽ đạt trạng thái Won.

Project được triển khai theo chuỗi **DS-01 → DS-06**.

Các task đầu tiên chủ yếu dùng để làm quen với hệ thống ERPNext, hiểu dữ liệu và xác định bài toán. Phần đặc tả feature/label được tổng hợp và chốt trong **Feature Dictionary v5**. Từ đó, DS-04 tập trung vào baseline modeling, DS-05 vào model selection và explainability/error analysis, còn DS-06 đưa model vào tầng scoring và tích hợp với ERPNext.

---

## 2. Business Objectives

### 2.1. Project Delay Risk

Mục tiêu là cung cấp một score cho Project để hỗ trợ nhận diện sớm các trường hợp có nguy cơ chậm tiến độ.

Output:

```text
custom_delay_risk_score
custom_risk_band
```

Trong đó:

- `custom_delay_risk_score`: xác suất dự đoán `P(delay)`
- `custom_risk_band`: phân nhóm `Thấp / Trung bình / Cao`

### 2.2. Opportunity Win Probability

Mục tiêu là cung cấp một score cho Opportunity đã có ít nhất một Quotation để hỗ trợ ưu tiên các cơ hội bán hàng.

Output:

```text
custom_win_probability
custom_win_band
```

Trong đó:

- `custom_win_probability`: xác suất dự đoán `P(WON)`
- `custom_win_band`: phân nhóm `Thấp / Trung bình / Cao`

> Probability là score hỗ trợ ra quyết định, không phải cam kết rằng Project chắc chắn trễ hoặc Opportunity chắc chắn thắng.

---

## 3. Project Roadmap

```text
DS-01
  │
  │  Làm quen ERPNext + hiểu bài toán
  ▼
DS-02
  │
  │  Data understanding / exploration
  ▼
DS-03
  │
  │  Xác định dữ liệu, feature, label và các vấn đề dữ liệu
  ▼
Feature Dictionary v5
  │
  │  Chốt feature / label / cutoff / phạm vi
  ▼
DS-04
  │
  │  Dataset rebuild + 3 baselines + CV + evaluation
  ▼
DS-05
  │
  │  Model selection + explainability + error analysis
  ▼
DS-06
  │
  │  Model artifact + FastAPI + ERPNext integration
  │  + Streamlit Dashboard + UAT
  ▼
ERPNext
```

### Trạng thái

| Task | Nội dung chính | Trạng thái |
|---|---|---|
| DS-01 | Làm quen hệ thống / bài toán | Completed |
| DS-02 | Data understanding / exploration | Completed |
| DS-03 | Data preparation / feature & label definition | Completed |
| Feature Dictionary v5 | Đặc tả feature và phạm vi modeling | Completed |
| DS-04 | Baseline modeling | Completed |
| DS-05 | Selection + explainability + error analysis | Completed |
| DS-06 | Scoring API + ERPNext integration + Dashboard | Completed / UAT verified |

---

# 4. End-to-End Architecture

```text
                         HIDECC ERPNext
                              │
               ┌──────────────┴──────────────┐
               │                             │
            Project                      Opportunity
               │                             │
               ▼                             ▼
      Delay Feature Builder          Win Feature Builder
               │                             │
               ▼                             ▼
         Random Forest                  CatBoost
               │                             │
               └──────────────┬──────────────┘
                              │
                              ▼
                       DS-06 FastAPI
                              │
                 ┌────────────┴────────────┐
                 │                         │
                 ▼                         ▼
          Write score back          Streamlit Dashboard
             to ERPNext
                 │
                 ▼
              ERPNext
```

Nguyên tắc chính:

- ERPNext là nguồn dữ liệu nghiệp vụ.
- Feature Builder tái tạo logic feature đã dùng khi train.
- Model artifact được load để inference.
- Score được ghi trở lại Custom Field trên ERPNext.
- Dashboard đọc score từ ERPNext và cung cấp giao diện theo dõi/score lại.
- DS-06 **không train lại hoặc retune model**.

---

# 5. Data Source

Nguồn dữ liệu chính của project là **ERPNext thực tế của HIDECC**, truy cập thông qua REST API.

## 5.1. Delay Risk

Các nguồn dữ liệu chính gồm:

- `Project`
- `Design Discipline Assignment`
- `Discipline Allocation`
- `Sales Order`
- `Task`
- `Employee`

`Discipline Allocation` là child table của `Design Discipline Assignment`, vì vậy khi truy xuất qua ERPNext API cần truyền parent tương ứng.

Một số mapping quan trọng:

```text
Project
 ├── project_type
 ├── expected_start_date
 ├── expected_end_date
 └── customer

Design Discipline Assignment
 ├── project
 └── project_manager

Discipline Allocation
 ├── employee
 ├── discipline
 ├── workload_percent
 ├── planned_hours
 ├── start_date
 ├── end_date
 ├── actual_hours
 └── actual_close_date

Sales Order
 ├── project
 ├── grand_total
 └── docstatus
```

`contract_value` được xây từ các **submitted Sales Order** liên quan đến Project.

## 5.2. Win Probability

Các nguồn dữ liệu chính gồm:

- `Opportunity`
- `Quotation`
- `Lead`
- các thông tin customer/territory liên quan

Một số mapping nghiệp vụ:

```text
Quotation
 ├── opportunity
 ├── additional_discount_percentage
 ├── opportunity_owner
 ├── utm_source
 ├── party_name
 └── expected_closing

Opportunity
 ├── customer_group
 └── territory
```

Do Opportunity không có trực tiếp field tương ứng với một số feature ban đầu, project sử dụng:

```text
utm_source      → lead_source proxy
customer_group  → customer_segment
territory       → territory
```

---

# 6. Feature & Label Definition

**Feature Dictionary v5** được sử dụng làm tài liệu chốt cho phần feature engineering và label definition.

Một nguyên tắc quan trọng của project là feature phải được tính theo thông tin **có thể biết tại thời điểm snapshot**, tránh sử dụng thông tin xảy ra sau thời điểm dự đoán.

---

## 6.1. Delay Risk

Đơn vị modeling:

```text
1 row = 1 Project × 1 Discipline Allocation
```

Snapshot chính dựa trên:

```text
as_of_date = Discipline Allocation.start_date
```

Các feature cuối cùng:

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

### Một số nguyên tắc xây feature

- Chỉ sử dụng các discipline đã biết tại snapshot.
- Workload được tính từ các allocation đang mở tại snapshot.
- Staff overload dựa trên số allocation đang mở.
- Historical late rate chỉ dùng các quan sát đã đóng trước snapshot.
- Historical rate được smoothing với `k = 5` và global rate fallback.
- `contract_value` sử dụng submitted Sales Order.
- `assignee_id` không được đưa vào model cuối.

### Label

Delay label được xác định từ trạng thái hoàn thành thực tế của Discipline Allocation và xử lý riêng trường hợp **right-censoring**.

Nếu một observation chưa đủ thông tin để xác định outcome tại cutoff thì không ép thành label giả; observation đó được đánh dấu `censored` và loại khỏi tập train/test.

---

## 6.2. Win Probability

Đơn vị modeling:

```text
1 row = 1 Opportunity có ít nhất 1 Quotation
```

Snapshot:

```text
as_of_date = ngày Quotation đầu tiên
```

Các feature cuối cùng:

```text
lead_source
customer_segment
territory
opportunity_amount
days_lead_to_opp
discount_rate_at_first_quotation
```

### Scope

Opportunity chưa từng có Quotation được xem là:

```text
out_of_scope_no_quotation
```

chứ không được xem là một Opportunity bị Lost.

Tại dataset rebuild:

```text
Total Opportunity                 = 183
Opportunity có Quotation          = 119
Out of scope, không có Quotation  = 64
Closed Lost                       = 64
Closed Won                        = 55
Trainable                         = 119
Won rate trên trainable           = 46.2%
Train                              = 84
Test                               = 35
```

### Leakage prevention

Các feature có nguy cơ sử dụng thông tin hậu nghiệm đã được loại khỏi baseline, bao gồm:

```text
n_quotation_total
owner_historic_win_rate
opportunity_type
```

Các reverse-scoring field cũng tuyệt đối không được dùng làm model input:

```text
custom_win_probability
custom_win_band
custom_delay_risk_score
custom_risk_band
```

---

# 7. DS-04 — Baseline Modeling

DS-04 thực hiện baseline modeling cho cả hai bài toán.

Mục tiêu không phải tìm một metric "đẹp", mà là:

- tạo baseline có thể tái lập;
- kiểm tra tín hiệu trong dữ liệu;
- kiểm tra leakage;
- đánh giá độ ổn định bằng cross-validation;
- tạo cơ sở khách quan cho DS-05 model selection.

---

## 7.1. Delay Risk

Ba baseline:

```text
Logistic Regression
Random Forest
CatBoost
```

Primary holdout được chia ở **Project level**, tránh việc các Discipline Allocation của cùng Project xuất hiện đồng thời ở train và test.

Cross-validation:

```text
GroupKFold(5)
group = project_id
```

Kết quả baseline chính:

| Model | CV ROC-AUC | Test ROC-AUC | Precision | Recall | F1 |
|---|---:|---:|---:|---:|---:|
| Logistic Regression | 0.621 ± 0.060 | 0.614 | 0.581 | 0.566 | 0.573 |
| **Random Forest** | **0.646 ± 0.053** | **0.640** | **0.613** | **0.605** | **0.609** |
| CatBoost | 0.603 ± 0.051 | 0.614 | 0.606 | 0.526 | 0.563 |

Random Forest được chọn cho Delay Risk vì đạt test ROC-AUC cao nhất trong các baseline được đánh giá.

---

## 7.2. Win Probability

Ba baseline:

```text
Logistic Regression
Random Forest
CatBoost
```

Primary split là **time-based split**, đảm bảo:

```text
max(train.as_of_date) <= min(test.as_of_date)
```

Kết quả baseline:

| Model | CV ROC-AUC | Test ROC-AUC | PR-AUC | Top-30% Precision |
|---|---:|---:|---:|---:|
| Logistic Regression | 0.540 ± 0.141 | 0.457 | 0.621 | 0.455 |
| Random Forest | 0.622 ± 0.138 | 0.527 | 0.652 | 0.545 |
| **CatBoost** | **0.604 ± 0.090** | ~0.50 | 0.652 | **0.636** |

CatBoost được chọn không phải vì có ROC-AUC cao nhất, mà vì bài toán Win Probability được định hướng như một **ranking / prioritization problem**.

Metric vận hành được ưu tiên:

```text
Precision trong Top 30%
```

CatBoost đạt Top-30% Precision cao nhất trong baseline comparison.

> Test set chỉ có 35 Opportunity. Vì vậy ROC-AUC và các metric trên test cần được diễn giải thận trọng; kết quả hiện tại cho thấy tín hiệu dự đoán còn yếu.

---

# 8. DS-05 — Model Selection & Explainability

DS-05 thực hiện:

- so sánh các baseline;
- chọn model theo mục tiêu nghiệp vụ;
- phân tích feature importance;
- permutation importance;
- SHAP diagnostic;
- ablation;
- error analysis;
- kiểm tra các limitation của dữ liệu/model.

---

## 8.1. Selected Models

| Problem | Selected Model | Artifact |
|---|---|---|
| Delay Risk | Random Forest | `models/delay_risk_rf.joblib` |
| Win Probability | CatBoost | `models/win_probability_catboost.cbm` |

### Delay Risk — Random Forest

Configuration:

```text
n_estimators = 300
min_samples_leaf = 3
class_weight = balanced
random_state = 42
n_jobs = -1
```

### Win Probability — CatBoost

Configuration:

```text
iterations = 300
depth = 5
learning_rate = 0.05
loss_function = Logloss
random_seed = 42
```

Categorical features:

```text
lead_source
customer_segment
territory
```

---

## 8.2. Delay Risk Explainability

Một số feature có mức importance cao trong model gồm:

- `customer_historic_late_rate`
- `pm_historic_late_rate`
- `pct_staff_overloaded_at_snapshot`
- `planned_duration_days`
- `discipline`

Tuy nhiên, importance **không được diễn giải là quan hệ nhân quả**.

Đặc biệt, historical customer/PM rates được model sử dụng khá nhiều nhưng dữ liệu thiết kế cho bài toán có caveat về tín hiệu của các feature lịch sử. Vì vậy chúng được xem là feature có giá trị dự báo trong artifact hiện tại, không phải bằng chứng rằng customer/PM history là nguyên nhân gây delay.

Ablation khi loại các historical rate cho thấy AUC giảm so với full feature set. Đây là một kết quả diagnostic dùng để hiểu model dependence, không phải bằng chứng causal.

---

## 8.3. Error Analysis

Error analysis tập trung vào:

```text
False Positive
False Negative
```

Mục tiêu là xác định:

- trường hợp model cảnh báo nhưng outcome không xảy ra;
- trường hợp model bỏ sót delay;
- các record có probability ở vùng biên;
- các limitation của feature/data.

Error analysis được dùng để đánh giá tính hợp lý của model, không dùng để chọn riêng các ví dụ "đẹp".

---

## 8.4. Win Probability Explainability

Do test set nhỏ và ROC-AUC thấp, explainability của Win Probability được sử dụng chủ yếu ở vai trò **diagnostic**.

Không sử dụng feature importance để đưa ra kết luận kinh doanh mạnh khi chưa có đủ bằng chứng.

---

# 9. Data Quality & Modeling Limitations

Đây là phần quan trọng của project.

## 9.1. Right-censoring — Delay Risk

Một số Discipline Allocation chưa đóng tại cutoff.

Ví dụ:

```text
actual_close_date = NULL
```

không tự động có nghĩa là "delay".

Nếu observation chưa đủ thông tin để xác định outcome tại cutoff, observation được xem là:

```text
censored
```

và không dùng để train/test.

Right-censoring là một limitation của dataset và cần được xem xét khi diễn giải metric.

---

## 9.2. Missing Actual End Date

Dữ liệu `Timesheet Detail` thực tế không có daily logging đầy đủ.

Do đó:

```text
actual_end_date / act_end_date
```

không được dùng làm nguồn label chính.

Thay vào đó, Delay Risk sử dụng:

```text
Discipline Allocation.actual_close_date
```

để xác định trạng thái hoàn thành.

---

## 9.3. Win Probability — No Quotation

Opportunity không có Quotation nằm ngoài phạm vi scoring:

```text
out_of_scope_no_quotation
```

DS-06 không tạo giá trị giả để cố score các record này.

Dashboard cũng tách nhóm Opportunity chưa có Quotation khỏi nhóm Opportunity đủ điều kiện scoring.

---

## 9.4. Win Labeling Assumption

Trong quá trình build label Win Probability có business assumption đối với một số Opportunity đang mở:

```text
ASSUME_STALE_OPEN_AS_LOST
```

Nếu bật assumption này, Opportunity mở nhưng đã quá expected closing date có thể được gán Lost.

Đây là **business assumption**, không nên xem là ground truth nếu chưa được Sales/CRM xác nhận.

---

## 9.5. Dataset Size

Dataset hiện tại tương đối nhỏ cho một bài toán Machine Learning production-grade.

Đặc biệt:

- Delay Risk có số lượng Project hữu hạn.
- Win Probability có 119 Opportunity trainable.
- Test của Win Probability chỉ có 35 Opportunity.

Do đó:

> Các model hiện tại nên được xem là **baseline/scoring prototype đã tích hợp**, chưa phải hệ thống dự báo có độ tin cậy cao cho mọi trường hợp nghiệp vụ.

---

# 10. DS-06 — Deployment & Scoring

DS-06 không train lại model.

Nó thực hiện:

```text
Load artifact
     ↓
Get data from ERPNext
     ↓
Build point-in-time features
     ↓
Inference
     ↓
Probability
     ↓
Risk / Win Band
     ↓
Write back to ERPNext
     ↓
Verify
```

---

# 11. DS-06 Project Structure

```text
DS06/
├── models/
│   ├── delay_risk_rf.joblib
│   └── win_probability_catboost.cbm
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
├── tests/
│   └── ...
│
├── scripts/
│   └── score_to_erpnext.py
│
├── dashboard.py
├── .env
├── .env.example
├── .gitignore
├── model_metadata.json
├── README.md
└── requirements.txt
```

### Vai trò

| File | Vai trò |
|---|---|
| `app/main.py` | FastAPI API |
| `app/erpnext_client.py` | ERPNext REST client |
| `app/feature_builder.py` | Delay feature engineering |
| `app/win_feature_builder.py` | Win feature engineering |
| `app/predictors.py` | Load model + inference |
| `app/schemas.py` | API request schema |
| `models/delay_risk_rf.joblib` | Delay Risk model |
| `models/win_probability_catboost.cbm` | Win Probability model |
| `scripts/score_to_erpnext.py` | Score và POST trực tiếp tới ERPNext |
| `dashboard.py` | Streamlit Dashboard |
| `model_metadata.json` | Model/config metadata |

---

# 12. FastAPI

FastAPI service cung cấp các nhóm endpoint cho:

- health check;
- prediction từ feature;
- lấy feature từ ERPNext;
- ghi score;
- end-to-end scoring.

## Delay Risk

```text
POST /predict_project_delay

GET /erpnext/project/{project_name}/features

POST /set_project_delay_score/{project_name}

POST /score_project_from_erpnext/{project_name}
```

Pipeline:

```text
ERPNext Project
      ↓
Delay Feature Builder
      ↓
Random Forest
      ↓
P(delay)
      ↓
Risk Band
      ↓
Write to ERPNext
      ↓
GET verify
```

## Win Probability

```text
POST /predict_opportunity_success

GET /erpnext/opportunity/{opportunity_name}/features

POST /set_opportunity_win_score/{opportunity_name}

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
P(WON)
      ↓
Win Band
      ↓
Write to ERPNext
      ↓
GET verify
```

---

# 13. ERPNext Integration

Authentication sử dụng:

```text
Authorization: token API_KEY:API_SECRET
```

Credentials được đọc từ environment:

```text
ERPNEXT_BASE_URL
ERPNEXT_API_KEY
ERPNEXT_API_SECRET
```

Không hard-code API Secret trong source code.

## Write-back methods

### Delay Risk

```text
hidecc_consulting.api.set_project_delay_score
```

Input:

```text
project
score
band
```

Output fields:

```text
custom_delay_risk_score
custom_risk_band
```

### Win Probability

```text
hidecc_consulting.api.set_opportunity_win_score
```

Input:

```text
opportunity
score
band
```

Output fields:

```text
custom_win_probability
custom_win_band
```

---

# 14. Score Band

Cả hai bài toán hiện sử dụng cùng ngưỡng:

```text
Probability < 0.40
    → Thấp

0.40 ≤ Probability < 0.70
    → Trung bình

Probability ≥ 0.70
    → Cao
```

Các threshold được cấu hình bằng environment variables:

```text
DELAY_MEDIUM_THRESHOLD
DELAY_HIGH_THRESHOLD

WIN_MEDIUM_THRESHOLD
WIN_HIGH_THRESHOLD
```

---

# 15. Streamlit Dashboard

Dashboard là lớp giao diện phục vụ theo dõi và scoring.

Dashboard không train model.

Dashboard có các khu vực chính:

### Overview

- Tổng số Project
- Delay đã score
- Delay chưa score
- Tổng số Opportunity
- Win đã score
- Win chưa score
- Phân bố Risk Band
- Phân bố Win Band

### Delay Risk

Có thể:

- xem danh sách Project;
- lọc theo Risk Band;
- lọc theo trạng thái scoring;
- lọc theo probability;
- score lại một Project;
- score hàng loạt Project chưa có score.

### Win Probability

Có thể:

- xem danh sách Opportunity;
- lọc theo score/band;
- score lại Opportunity;
- batch score các Opportunity đủ điều kiện.

Opportunity không có Quotation được tách riêng và không được score.

---

# 16. Installation

## 16.1. Environment

Khuyến nghị:

```text
Python virtual environment
ERPNext server có thể truy cập qua REST API
API Key + API Secret
```

Không cần cài ERPNext/Frappe local để chạy DS-06 nếu đã có ERPNext server.

Tạo virtual environment:

```powershell
python -m venv .venv
```

Activate:

```powershell
.\.venv\Scripts\Activate.ps1
```

---

## 16.2. Install dependencies

```powershell
python -m pip install -r requirements.txt
```

Dashboard sử dụng Streamlit. Nếu `requirements.txt` chưa bao gồm Streamlit trong phiên bản hiện tại:

```powershell
python -m pip install streamlit
```

---

# 17. Configuration

Tạo file:

```text
.env
```

Ví dụ:

```env
ERPNEXT_BASE_URL=https://your-erpnext-server
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

**Không commit `.env`.**

Có thể dùng `.env.example` để mô tả cấu hình mà không chứa credential thật.

---

# 18. Running DS-06

## 18.1. Start FastAPI

Tại thư mục `DS06`:

```powershell
uvicorn app.main:app --host 127.0.0.1 --port 8001 --reload
```

Health check:

```text
http://127.0.0.1:8001/health
```

Expected:

```json
{
  "status": "ok",
  "service": "HIDECC DS-06 Scoring API"
}
```

---

## 18.2. Start Dashboard

Mở terminal thứ hai:

```powershell
python -m streamlit run dashboard.py
```

Dashboard:

```text
http://localhost:8501
```

FastAPI phải đang chạy nếu Dashboard thực hiện prediction/scoring.

---

# 19. Direct ERPNext Scoring Script

Ngoài FastAPI, project có script:

```text
scripts/score_to_erpnext.py
```

Mục đích:

```text
ERPNext
   ↓
GET raw data
   ↓
Build feature
   ↓
Local model inference
   ↓
POST whitelist method
   ↓
GET verify
```

Đây là cách kiểm thử trực tiếp đường đi:

```text
DS-06 → ERPNext
```

mà không yêu cầu ERPNext phải gọi ngược vào FastAPI.

---

# 20. UAT / Verification

DS-06 đã được kiểm thử end-to-end trên dữ liệu ERPNext thực tế.

## Delay Risk

Project:

```text
PROJ-0001
```

Kết quả:

```text
custom_delay_risk_score = 0.731451589...
custom_risk_band = Cao
```

Kết quả đã được write vào ERPNext và GET lại để verify.

## Win Probability

Một số Opportunity đã được kiểm thử:

| Opportunity | Probability | Band | Write | Verify |
|---|---:|---|---|---|
| CRM-OPP-2026-00002 | 32.40% | Thấp | OK | OK |
| CRM-OPP-2026-00003 | 60.60% | Trung bình | OK | OK |
| CRM-OPP-2026-00004 | 10.41% | Thấp | OK | OK |
| CRM-OPP-2026-00005 | 11.80% | Thấp | OK | OK |

Acceptance criterion chính:

```text
Prediction
   ↓
Correct ERPNext Custom Field
   ↓
GET lại record
   ↓
Score khớp
```

---

# 21. Reproducibility

Project ưu tiên reproducibility thông qua:

- fixed `random_state`;
- fixed data cutoff;
- explicit feature dictionary;
- point-in-time feature construction;
- GroupKFold cho Delay Risk;
- time-based split cho Win Probability;
- model artifacts được lưu riêng;
- DS-06 không thay đổi model;
- credentials được quản lý bằng environment variables.

### Delay Risk

Primary holdout:

```text
Random split theo project_id
```

CV:

```text
GroupKFold(5)
```

### Win Probability

Primary holdout:

```text
Time-based split theo as_of_date
```

Điều kiện:

```text
max(train.as_of_date) <= min(test.as_of_date)
```

---

# 22. Important Modeling Constraints

## Không sử dụng leakage

Không sử dụng thông tin chỉ xuất hiện sau snapshot/outcome.

## Không sử dụng reverse-scoring fields làm input

```text
custom_win_probability
custom_win_band
custom_delay_risk_score
custom_risk_band
```

là output.

Không được dùng chúng làm feature.

## Không retune model trong DS-06

DS-06 chỉ:

```text
Inference
Scoring
Integration
Dashboard
```

## Không tạo dữ liệu giả

Nếu ERPNext thiếu dữ liệu cần thiết:

```text
Không tự sinh giá trị
Không dùng mock value cho production scoring
```

Mock data chỉ có thể được sử dụng để kiểm thử kỹ thuật pipeline; không dùng để báo cáo chất lượng model.

## Không overclaim metric

Metric thấp, test set nhỏ, right-censoring hoặc calibration chưa ổn định phải được ghi nhận thay vì cố tuning để tạo kết quả đẹp.

---

# 23. Current Model Metadata

## Delay Risk

```text
Model:
RandomForestClassifier

Artifact:
models/delay_risk_rf.joblib

Output:
P(label=1) = P(delay)
```

Features:

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

```text
Model:
CatBoostClassifier

Artifact:
models/win_probability_catboost.cbm

Output:
P(label=1) = P(WON)
```

Features:

```text
lead_source
customer_segment
territory
opportunity_amount
days_lead_to_opp
discount_rate_at_first_quotation
```

Scope:

```text
Requires at least one Quotation
```

---

# 24. Project Limitations

Các limitation chính hiện tại:

1. **Dataset còn nhỏ**, đặc biệt với Win Probability.
2. **Win test set chỉ có 35 Opportunity**, vì vậy metric có variance cao.
3. **Delay Risk có right-censoring**.
4. Một số dữ liệu nghiệp vụ chưa được logging đầy đủ.
5. Historical features có thể tạo dependence giữa train/test và cần được xem xét thêm nếu mở rộng dataset.
6. Một số Win labels phụ thuộc business assumption về stale open Opportunity.
7. Model hiện tại chưa nên được hiểu là hệ thống dự báo có độ chính xác cao cho mọi Project/Opportunity.
8. Probability hiện tại nên được sử dụng như **decision-support score**, không phải certainty.

---

# 25. Recommended Future Improvements

Nếu tiếp tục phát triển project, các hướng ưu tiên:

### Data

- tăng số lượng Project và Opportunity;
- cải thiện Timesheet logging;
- chuẩn hóa actual completion date;
- chuẩn hóa Opportunity/Quotation lifecycle;
- xác nhận business rule cho stale open Opportunity.

### Modeling

- đánh giá lại model khi có thêm dữ liệu;
- kiểm tra temporal/generalization stability;
- calibration khi có đủ test samples;
- đánh giá threshold theo chi phí business;
- xem xét survival/time-to-event modeling cho Delay Risk nếu right-censoring vẫn đáng kể.

### Production

- scheduled scoring;
- model/version registry;
- monitoring data drift;
- monitoring prediction distribution;
- monitoring missing feature rate;
- logging prediction và model version;
- retraining policy khi có đủ dữ liệu mới.

---

# 26. Final Project Status

```text
DS-01  ─────────────── Completed
DS-02  ─────────────── Completed
DS-03  ─────────────── Completed
Feature Dictionary v5  Completed
DS-04  ─────────────── Completed
DS-05  ─────────────── Completed
DS-06  ─────────────── Completed / UAT verified
```

### Final pipeline

```text
                  ┌──────────────────────┐
                  │      ERPNext         │
                  └──────────┬───────────┘
                             │
                             ▼
                  ┌──────────────────────┐
                  │ Data / Feature Spec  │
                  │ Feature Dictionary   │
                  └──────────┬───────────┘
                             │
                ┌────────────┴────────────┐
                ▼                         ▼
       ┌─────────────────┐      ┌─────────────────┐
       │   Delay Risk    │      │ Win Probability │
       │ Random Forest   │      │    CatBoost     │
       └────────┬────────┘      └────────┬────────┘
                │                         │
                └────────────┬────────────┘
                             ▼
                    ┌─────────────────┐
                    │   DS-06 API     │
                    │    FastAPI      │
                    └────────┬────────┘
                             │
                  ┌──────────┴──────────┐
                  ▼                     ▼
          ┌───────────────┐     ┌────────────────┐
          │   ERPNext     │     │   Streamlit    │
          │  Custom Field │     │   Dashboard    │
          └───────────────┘     └────────────────┘
```

---

## 27. Summary

Project HIDECC ERPNext đã đi từ giai đoạn tìm hiểu dữ liệu và xác định bài toán đến một pipeline có thể:

- xây dựng feature theo snapshot;
- train và đánh giá baseline;
- lựa chọn model;
- phân tích explainability/error;
- load model artifact;
- lấy dữ liệu trực tiếp từ ERPNext;
- thực hiện inference;
- ghi prediction vào ERPNext;
- verify kết quả;
- theo dõi và score qua Streamlit Dashboard.

Hai model cuối cùng:

```text
Delay Risk       → Random Forest
Win Probability  → CatBoost
```

được triển khai như các artifact độc lập và sử dụng lại trong DS-06.

**Điểm quan trọng của project không chỉ là tạo ra prediction, mà là xây dựng một quy trình có thể kiểm tra, tái lập và tích hợp vào ERPNext mà vẫn giữ rõ các giới hạn của dữ liệu và model.**
