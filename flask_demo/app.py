from flask import Flask, render_template, request, redirect, url_for

app = Flask(__name__)

# --- 模擬資料庫 (Mock Database) ---

# 1. 技能維度資料 (用於第一頁)
MOCK_SKILL_CATEGORIES = {
    "程式語言與開發工具": ["Python", "SQL", "Java", "R", "HTML / CSS", "JavaScript"],
    "資料庫、雲端與 ETL 工具": ["MySQL", "PostgreSQL", "GCP", "AWS", "Docker", "Airflow"],
    "分析軟體與商業智慧 (BI)": ["Power BI", "Excel", "Google Analytics", "Tableau"],
    "專業領域與工作技能": ["數據分析", "資料庫系統管理維護", "報表開發", "Data Modeling"]
}

# 2. 職業類別及其核心技能對應表 (用於第二頁符合度計算)
MOCK_JOB_CATEGORIES = [
    {
        "id": "de",
        "name": "資料工程師 (Data Engineer)",
        "desc": "負責構建資料流水線 (ETL)、維護資料庫系統與雲端資料架構。",
        "required_skills": ["Python", "SQL", "GCP", "Docker", "Airflow", "MySQL", "PostgreSQL", "資料庫系統管理維護"]
    },
    {
        "id": "da",
        "name": "數據/商業分析師 (Data/BI Analyst)",
        "desc": "解讀數據趨勢、製作視覺化儀表板並提供商業洞察報告。",
        "required_skills": ["SQL", "Power BI", "Excel", "數據分析", "Python", "Tableau", "報表開發"]
    },
    {
        "id": "fe",
        "name": "前端工程師 (Frontend Engineer)",
        "desc": "負責使用者介面 (UI) 開發、Web 前端互動與 API 資料串接。",
        "required_skills": ["HTML / CSS", "JavaScript", "React", "Vue"]
    }
]

# 3. 區域統計數據 (用於第三頁)
MOCK_REGIONS = {
    "北部": {"count": 750, "avg_salary": "NT$ 55,000 - 85,000", "skills": "Python, GCP, Airflow"},
    "中部": {"count": 210, "avg_salary": "NT$ 42,000 - 68,000", "skills": "Python, SQL, Docker"},
    "南部": {"count": 180, "avg_salary": "NT$ 40,000 - 65,000", "skills": "Python, MySQL, Linux"},
    "東部/西部": {"count": 110, "avg_salary": "NT$ 38,000 - 60,000", "skills": "SQL, Excel, ETL"}
}

# 4. 職缺詳細卡片資料 (用於第四頁)
MOCK_JOBS = [
    {
        "id": 1,
        "title": "雲端資深資料工程師 (Senior Data Engineer)",
        "company": "台灣積體電路製造股份有限公司 (TSMC)",
        "industry": "半導體製造業",
        "location": "台北市 信義區",
        "region": "北部",
        "salary": "NT$ 70,000 - 110,000 / 月",
        "exp": "經驗 3 年以上 ｜ 學士以上",
        "work_mode": "可部分遠距 (Hybrid)",
        "skills": ["Python", "SQL", "GCP", "BigQuery", "Airflow", "Docker"],
        "tools": "需熟悉 Spark, Git 版本管制，並具備 CI/CD 自動化經驗",
        "desc": "負責設計、建構與維護大規模 Data Pipeline，確保資料即時與批次 ETL 流暢運作...",
        "url": "https://www.104.com.tw"
    },
    {
        "id": 2,
        "title": "Data Engineer 資料工程師",
        "company": "綠界科技股份有限公司",
        "industry": "網際網路相關業",
        "location": "新北市 汐止區",
        "region": "北部",
        "salary": "NT$ 50,000 - 75,000 / 月",
        "exp": "經驗 1-3 年 ｜ 專科以上",
        "work_mode": "全到勤",
        "skills": ["Python", "MySQL", "PostgreSQL", "ETL", "Linux"],
        "tools": "熟悉 Redis, Shell Scripting",
        "desc": "維護與開發金流交易資料庫 ETL 流程，監控數據庫運作狀態，進行效能調優...",
        "url": "https://www.104.com.tw"
    },
    {
        "id": 3,
        "title": "Junior/初階 ETL 資料工程師",
        "company": "和碩聯合科技股份有限公司",
        "industry": "電腦軟體服務業",
        "location": "台中市 西屯區",
        "region": "中部",
        "salary": "面議 (經常性薪資達4萬元以上)",
        "exp": "不拘 (歡迎應屆畢業生) ｜ 學士以上",
        "work_mode": "全到勤",
        "skills": ["Python", "SQL", "Git"],
        "tools": "加分條件：熟悉 Pandas, NumPy, MS SQL",
        "desc": "協助團隊進行自動化腳本撰寫、每日 API 資料抓取與清洗...",
        "url": "https://www.104.com.tw"
    }
]


# --- 路由與控制邏輯 (Routes) ---

# 第一頁：技能勾選頁
@app.route('/', methods=['GET'])
def page1_skills():
    return render_template('page1_skills.html', skill_categories=MOCK_SKILL_CATEGORIES)


# 第二頁：職業類別推薦頁 (動態計算符合度)
@app.route('/categories', methods=['GET', 'POST'])
def page2_categories():
    # 取得第一頁送出的技能清單
    if request.method == 'POST':
        selected_skills = request.form.getlist('skills')
    else:
        # GET 測試預設值
        selected_skills = request.args.getlist('skills') or ["Python", "SQL", "GCP", "Power BI", "Excel", "數據分析"]

    # 動態計算加權符合度 (Match %)
    recommendations = []
    for cat in MOCK_JOB_CATEGORIES:
        req = set(cat['required_skills'])
        user = set(selected_skills)
        matched = list(user.intersection(req))
        missing = list(req - user)
        
        # 計算符合度 %
        match_score = int((len(matched) / len(req)) * 100) if req else 0
        
        recommendations.append({
            "id": cat['id'],
            "name": cat['name'],
            "desc": cat['desc'],
            "match_score": min(match_score, 100), # 限制上限 100%
            "matched_skills": matched,
            "missing_skills": missing
        })

    # 依照符合度由高到低排序
    recommendations.sort(key=lambda x: x['match_score'], reverse=True)

    return render_template('page2_categories.html', selected_skills=selected_skills, recommendations=recommendations)


# 第三頁：區域地圖與薪資分析
@app.route('/map')
def page3_map():
    category_id = request.args.get('category', 'de')
    # 接收薪資類型參數，預設 50 (月薪)
    # Code 參考: 10:面議, 30:時薪, 40:日薪, 50:月薪, 60:年薪[cite: 1, 2]
    salary_type = request.args.get('salary_type', '50')

    # 模擬資料庫/金層依照 (category_id, salary_type) 查出來的五大區域數據
    # 在真實 MySQL 中，這會是: SELECT * FROM fact_category_region_stats WHERE salary_type_code = :salary_type
    MOCK_MAP_DATA = {
        '50': { # 月薪[cite: 1, 2]
            "北部": {"count": 750, "avg_salary": "NT$ 55,000 - 85,000", "unit": "/ 月"},
            "中部": {"count": 210, "avg_salary": "NT$ 42,000 - 68,000", "unit": "/ 月"},
            "南部": {"count": 180, "avg_salary": "NT$ 40,000 - 65,000", "unit": "/ 月"},
            "東部/西部": {"count": 110, "avg_salary": "NT$ 38,000 - 60,000", "unit": "/ 月"}
        },
        '30': { # 時薪[cite: 1, 2]
            "北部": {"count": 45, "avg_salary": "NT$ 220 - 320", "unit": "/ 小時"},
            "中部": {"count": 15, "avg_salary": "NT$ 195 - 250", "unit": "/ 小時"},
            "南部": {"count": 12, "avg_salary": "NT$ 185 - 220", "unit": "/ 小時"},
            "東部/西部": {"count": 5, "avg_salary": "NT$ 185 - 200", "unit": "/ 小時"}
        },
        '10': { # 面議 (面議只顯示職缺數，無平均數值)[cite: 1, 2]
            "北部": {"count": 120, "avg_salary": "依法規月薪 4 萬以上", "unit": " (面議職缺)"},
            "中部": {"count": 30, "avg_salary": "依法規月薪 4 萬以上", "unit": " (面議職缺)"},
            "南部": {"count": 25, "avg_salary": "依法規月薪 4 萬以上", "unit": " (面議職缺)"},
            "東部/西部": {"count": 10, "avg_salary": "依法規月薪 4 萬以上", "unit": " (面議職缺)"}
        }
    }

    # 取得對應類型的區域統計資料 (若選到沒有資料的類型則預設抓月薪)
    current_regions = MOCK_MAP_DATA.get(salary_type, MOCK_MAP_DATA['50'])

    return render_template(
        'page3_map.html', 
        category_id=category_id, 
        current_salary_type=salary_type,
        regions=current_regions
    )

# 第四頁：職缺列表
@app.route('/jobs')
def page4_jobs():
    selected_region = request.args.get('region', 'ALL')
    if selected_region != 'ALL':
        filtered_jobs = [j for j in MOCK_JOBS if j['region'] == selected_region]
    else:
        filtered_jobs = MOCK_JOBS
    return render_template('page4_jobs.html', jobs=filtered_jobs, current_region=selected_region)


if __name__ == '__main__':
    app.run(debug=True, port=5000)