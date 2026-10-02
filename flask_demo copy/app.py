import os
import json
import pymysql
from dotenv import load_dotenv
from flask import Flask, render_template, request, redirect

load_dotenv()

app = Flask(__name__, template_folder="templates", static_folder="static")

def get_db_connection():
    gold_db = os.getenv("MYSQL_GOLD_DATABASE", "gold_db")
    return pymysql.connect(
        host=os.getenv("MYSQL_HOST", "127.0.0.1"),
        port=int(os.getenv("MYSQL_PORT", 3307)),
        user=os.getenv("MYSQL_USER", "root"),
        password=os.getenv("MYSQL_PASSWORD", os.getenv("MYSQL_ROOT_PASSWORD", "")),
        database=gold_db,
        cursorclass=pymysql.cursors.DictCursor
    )

CATEGORY_MAP = {
    "DE": [
        "DE", "2007001000", "2007001004", "2007001010", 
        "2007002006", "2007002007", "2010002003"
    ],
    "DS": [
        "DS", "2007002000", "2007001005", "2007002006"
    ],
    "DA": [
        "DA", "2007003000", "2007001006", "2004003005", "2004003009"
    ]
}

CATEGORY_NAME_MAP = {
    "DE": "資料工程師",
    "DS": "資料科學家",
    "DA": "資料分析師"
}

SALARY_UNIT_MAP = {
    "50": "元/月",
    "60": "元/年",
    "30": "元/時",
    "10": "",
    "20": "元/件"
}

def match_region_key(raw_text):
    """靈活模糊比對區域"""
    if not raw_text:
        return None
    raw_text = str(raw_text)
    if any(k in raw_text for k in ["離島", "澎湖", "金門", "馬祖", "連江"]):
        return "離島"
    elif "北" in raw_text:
        return "北部"
    elif "中" in raw_text:
        return "中部"
    elif "南" in raw_text:
        return "南部"
    elif "東" in raw_text:
        return "東部"
    elif any(k in raw_text for k in ["海外", "國外"]):
        return "海外"
    return None


@app.route("/")
def index():
    return redirect("/page1")


@app.route("/page1")
def page1():
    skill_categories = {
        "程式語言與核心": ["Python", "Java", "C++", "R", "SQL", "Go"],
        "資料庫與資料架構": ["MySQL", "PostgreSQL", "MongoDB", "Redis", "ETL", "Data Pipeline"],
        "大數據與雲端": ["Docker", "Kubernetes", "AWS", "GCP", "Airflow", "Kafka", "Spark"],
        "分析與機器學習": ["Pandas", "NumPy", "Scikit-Learn", "PyTorch", "TensorFlow", "Tableau", "Power BI"]
    }
    return render_template("page1.html", skill_categories=skill_categories)


@app.route("/page2", methods=["GET", "POST"])
def page2():
    if request.method == "POST":
        selected_skills = request.form.getlist("skills")
    else:
        selected_skills = []

    recommendations = [
        {
            "code": "DE",
            "name": "資料工程師 (Data Engineer)",
            "desc": "負責資料管道建置、ETL 流程自動化與資料庫架構維護。",
            "match_score": 85,
            "matched_skills": [s for s in selected_skills if s in ["Python", "SQL", "MySQL", "Docker", "ETL"]],
            "missing_skills": ["Airflow", "Spark"]
        },
        {
            "code": "DS",
            "name": "資料科學家 (Data Scientist)",
            "desc": "負責機器學習模型建立、統計分析與商業洞察提煉。",
            "match_score": 70,
            "matched_skills": [s for s in selected_skills if s in ["Python", "R", "Pandas", "Scikit-Learn"]],
            "missing_skills": ["PyTorch", "Deep Learning"]
        },
        {
            "code": "DA",
            "name": "資料分析師 (Data Analyst)",
            "desc": "負責商業報表製作、SQL 數據調取與營運指標追蹤。",
            "match_score": 60,
            "matched_skills": [s for s in selected_skills if s in ["SQL", "Tableau", "Excel", "Power BI"]],
            "missing_skills": ["Advanced SQL", "Statistics"]
        }
    ]

    return render_template("page2.html", selected_skills=selected_skills, recommendations=recommendations)


@app.route("/page3", methods=["GET", "POST"])
def page3():
    category_code = request.form.get("category_code") if request.method == "POST" else request.args.get("category_code")
    salary_type = str(request.args.get("salary_type", "50")).strip()

    if not category_code or not category_code.strip():
        category_code = "DE"

    possible_codes = CATEGORY_MAP.get(category_code.upper(), [category_code])
    unit_text = SALARY_UNIT_MAP.get(salary_type, "元")

    regions = {}
    for r in ["北部", "中部", "南部", "東部", "離島", "海外"]:
        regions[r] = {
            "count": 0,
            "unit": unit_text,
            "exp_any": "尚無資料",
            "exp_1to5": "尚無資料",
            "exp_6to10": "尚無資料",
            "exp_11plus": "尚無資料"
        }

    category_name = CATEGORY_NAME_MAP.get(category_code.upper(), category_code)

    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            format_strings = ','.join(['%s'] * len(possible_codes))

            # 1. 向金表查詢真實 category_name
            sql_cat = f"""
                SELECT category_name FROM fact_category_salary_stat 
                WHERE category_code IN ({format_strings}) AND category_name IS NOT NULL AND category_name != ''
                LIMIT 1
            """
            cursor.execute(sql_cat, possible_codes)
            cat_row = cursor.fetchone()
            if cat_row and cat_row.get("category_name"):
                category_name = cat_row.get("category_name")

            # 2. 統一以 fact_job_cards 做為單一事實來源 (Single Source of Truth)
            # 同時依據職業代碼與計薪型態查詢
            salary_type_int = int(salary_type) if salary_type.isdigit() else 50
            sql_cards = f"""
                SELECT 
                    region_group,
                    exp_edu_text,
                    salary_text
                FROM fact_job_cards
                WHERE category_code IN ({format_strings})
                  AND (salary_type_code = %s OR salary_type_code = %s)
            """
            cursor.execute(sql_cards, possible_codes + [salary_type, salary_type_int])
            job_rows = cursor.fetchall()

            exp_stats = {r: {"exp_any": [], "exp_1to5": [], "exp_6to10": [], "exp_11plus": []} for r in regions.keys()}

            for j in job_rows:
                r_key = match_region_key(j.get("region_group"))
                if not r_key or r_key not in exp_stats:
                    continue

                # 每符合一筆職缺，該區域總計數即 +1
                regions[r_key]["count"] += 1

                exp_str = str(j.get("exp_edu_text", ""))
                sal_str = str(j.get("salary_text", "")).strip()

                # 精準年資分組
                if any(x in exp_str for x in ["1年", "2年", "3年", "4年", "5年", "1~5", "1-5"]):
                    group = "exp_1to5"
                elif any(x in exp_str for x in ["6年", "7年", "8年", "9年", "10年", "6~10", "6-10"]):
                    group = "exp_6to10"
                elif any(x in exp_str for x in ["11年", "12年", "15年", "10年以上"]):
                    group = "exp_11plus"
                else:
                    group = "exp_any"

                exp_stats[r_key][group].append(sal_str if sal_str else "面議")

            # 將結果填入 regions 字典，確保右側筆數相加等於總量
            for r_key, groups in exp_stats.items():
                for g_key, sal_list in groups.items():
                    cnt = len(sal_list)
                    if cnt > 0:
                        sample_sal = max(set(sal_list), key=sal_list.count)
                        regions[r_key][g_key] = f"共 {cnt} 筆（行情：{sample_sal}）"

        conn.close()
    except Exception as e:
        print(f"MySQL P3 讀取失敗: {e}")

    return render_template(
        "page3.html", 
        category_code=category_code, 
        category_name=category_name,
        current_salary_type=salary_type, 
        regions=regions
    )


@app.route("/page4", methods=["GET"])
def page4():
    category_code = request.args.get("category_code", "DE")
    region = request.args.get("region", "ALL")
    possible_codes = CATEGORY_MAP.get(category_code.upper(), [category_code])

    jobs = []
    try:
        conn = get_db_connection()
        with conn.cursor() as cursor:
            format_strings = ','.join(['%s'] * len(possible_codes))
            
            if region == "ALL" or not region:
                sql = f"SELECT * FROM fact_job_cards WHERE category_code IN ({format_strings}) LIMIT 50"
                cursor.execute(sql, possible_codes)
            else:
                sql = f"SELECT * FROM fact_job_cards WHERE category_code IN ({format_strings}) AND region_group LIKE %s LIMIT 50"
                cursor.execute(sql, possible_codes + [f"%{region}%"])
            
            raw_jobs = cursor.fetchall()

            if not raw_jobs:
                cursor.execute("SELECT * FROM fact_job_cards LIMIT 50")
                raw_jobs = cursor.fetchall()

            for j in raw_jobs:
                skills_raw = j.get("skills_json", "[]")
                try:
                    skills_list = json.loads(skills_raw) if isinstance(skills_raw, str) else skills_raw
                except:
                    skills_list = []

                jobs.append({
                    "title": j.get("job_title", "未命名職缺"),
                    "company": j.get("company_name", "知名企業"),
                    "industry": j.get("industry_name", "資訊軟體業"),
                    "location": j.get("location_text", "台灣"),
                    "salary": j.get("salary_text", "面議"),
                    "exp": j.get("exp_edu_text", "不拘"),
                    "work_mode": j.get("work_mode", "全職"),
                    "skills": skills_list if skills_list else ["無標籤"],
                    "tools": "詳見職缺簡述",
                    "desc": j.get("job_desc_short", "無職缺說明"),
                    "url": j.get("job_url", "https://www.104.com.tw")
                })
        conn.close()
    except Exception as e:
        print(f"MySQL P4 讀取失敗: {e}")

    return render_template(
        "page4.html",
        category_code=category_code,
        current_region=region,
        jobs=jobs
    )


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5001)