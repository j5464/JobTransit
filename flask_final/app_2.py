from flask import Flask, render_template, request
from pymysql import connect
import pymysql
from collections import defaultdict
import os
from dotenv import load_dotenv
import json
import math

app = Flask(__name__)

# ----------------------------------------------------
# MySQL 資料庫連線設定
# ----------------------------------------------------
def conn_to_mysql_gold():
    load_dotenv()
    db_name = os.getenv("MYSQL_GOLD_DATABASE")
    user = os.getenv("MYSQL_USER")
    password = os.getenv("MYSQL_ROOT_PASSWORD")
    conn_ip = "127.0.0.1" or os.getenv("MYSQL_HOST")
    raw_port = os.getenv("MYSQL_PORT")
    port = int(raw_port) if raw_port else 3307
    print(f"Connecting to: host={conn_ip}, port={port}, user={user}, db={db_name}")
    try:
        return connect(
            host=conn_ip,
            port=port,
            user=user,
            password=password,
            database=db_name,
            connect_timeout=10,
            read_timeout=30,
            write_timeout=30,
            autocommit=False
        )
    except Exception as exc:
        print(f"連線失敗，請確認 MySQL 伺服器是否有啟動。錯誤訊息: {exc}")
        return None

# ----------------------------------------------------
# 方案 A：固定閾值映射函數 (Score -> 1~5 Stars)
# ----------------------------------------------------
def calculate_stars(score):
    if score >= 25.0:
        return 5
    elif score >= 18.0:
        return 4
    elif score >= 10.0:
        return 3
    elif score >= 4.0:
        return 2
    else:
        return 1

# 第一頁：技能勾選頁
@app.route('/', methods=['GET'])
def page1_skills():
    conn = conn_to_mysql_gold()
    skill_categories = defaultdict(list)

    if conn:
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # 查詢技能維度表中的分類與標準技能名稱
                sql = """
                    SELECT 
                        COALESCE(skill_category, '其他技能') AS skill_category, 
                        std_skill_name 
                    FROM dim_skill_option 
                    GROUP BY skill_category, std_skill_name
                    ORDER BY skill_category, std_skill_name;
                """
                cursor.execute(sql)
                rows = cursor.fetchall()
                
                # 整理資料成 { "程式語言與開發工具": ["Python", "MySQL"], ... }
                for row in rows:
                    category = row['skill_category']
                    skill_name = row['std_skill_name']
                    if skill_name not in skill_categories[category]:
                        skill_categories[category].append(skill_name)
        except Exception as e:
            print(f"讀取 dim_skill_option 資料失敗: {e}")
        finally:
            conn.close()
    else:
        # 備用 Mock 資料 (若連線失敗時使用)
        skill_categories = {
            "程式語言與開發工具": ["Python", "SQL", "Java", "C++", "R"],
            "資料庫與大數據技術": ["MySQL", "PostgreSQL", "MongoDB", "Hadoop", "Spark"],
            "雲端與 DevOps 平台": ["AWS", "GCP", "Docker", "Kubernetes", "Git"]
        }

    return render_template('page1.html', skill_categories=dict(skill_categories))


@app.route('/categories', methods=['GET', 'POST'])
def step2_recommendations():
    # 1. 取得第一頁傳過來的勾選技能列表 (相容 'skills' 或 'skills[]')
    if request.method == 'POST':
        selected_skills = request.form.getlist('skills') or request.form.getlist('skills[]')
    else:
        # GET 測試用的預設技能組合
        selected_skills = request.args.getlist('skills') or ['Python', 'MySQL', 'GCP','Git / GitHub 版本控制','ETL 資料萃取轉換']

    conn = conn_to_mysql_gold()
    if not conn:
        return "資料庫連線失敗，請確認 .env 設定與 MySQL 服務狀態。", 500

    try:
        with conn.cursor() as cursor:
            # 2.1 撈取所有職業類別的資訊與敘述 (fact_job_ratio)
            # 包含 category_desc (訴求 3)
            sql_ratio = """
                SELECT category_code, category_name, category_job_ratio, category_desc 
                FROM fact_job_ratio
            """
            cursor.execute(sql_ratio)
            ratios_raw = cursor.fetchall()
            ratios = {}
            for row in ratios_raw:
                if isinstance(row, dict):
                    ratios[row['category_code']] = row
                else:
                    ratios[row[0]] = {
                        'category_code': row[0], 
                        'category_name': row[1], 
                        'category_job_ratio': row[2],
                        'category_desc': row[3] if len(row) > 3 else ''
                    }

            # 2.2 撈取所有職業類別與技能權重 (fact_category_skill_weight)
            sql_weight = """
                SELECT category_code, std_skill_name, weight, is_core_skill
                FROM fact_category_skill_weight
                ORDER BY category_code, weight DESC
            """
            cursor.execute(sql_weight)
            weights_data = cursor.fetchall()

    finally:
        conn.close()

    # 3. 整理資料結構：計算各職業的總權重、命中權重，並收集技能清單
    # 新增 'skills': [] 用於收集該職業對應的所有技能
    category_stats = defaultdict(lambda: {
        'total_weight': 0.0, 
        'matched_weight': 0.0,
        'skills': []
    })
    selected_skills_set = set(selected_skills)

    for row in weights_data:
        # 假設 row 回傳 dict 或 tuple
        cat_code = row['category_code'] if isinstance(row, dict) else row[0]
        skill_name = row['std_skill_name'] if isinstance(row, dict) else row[1]
        w = float(row['weight'] if isinstance(row, dict) else row[2])
        is_core = bool(row['is_core_skill'] if isinstance(row, dict) else row[3])

        category_stats[cat_code]['total_weight'] += w
        category_stats[cat_code]['skills'].append({
            'name': skill_name,
            'is_core': is_core
        })

        if skill_name in selected_skills_set:
            category_stats[cat_code]['matched_weight'] += w

    # 4. 計算 Match % 與 Score，並進行過濾與星級轉換
    processed_list = []

    for cat_code, stats in category_stats.items():
        total_w = stats['total_weight']
        matched_w = stats['matched_weight']

        if total_w == 0:
            continue

        # 計算技能契合度 Match %
        match_percent = (matched_w / total_w) * 100.0

        # 不顯示技能符合度為 0.00% 的類別
        if match_percent <= 0.0001:
            continue

        ratio_info = ratios.get(cat_code, {})
        job_ratio = float(ratio_info.get('category_job_ratio', 0.0000))
        cat_name = ratio_info.get('category_name', cat_code)

        # 計算推薦分值 Score 並計算星級
        score = match_percent * job_ratio * 100.0
        stars = calculate_stars(score)

        # 【修復重點】：直接從 stats['skills'] 拿出該職業的所有技能進行比對
        category_all_skills = stats['skills']
        
        # 訴求 2：計算已具備 (交集) 與 建議補強 (差集)
        # ⭕ 正確寫法：取出字典裡的技能名稱字串 (s['name']) 來進行集合比對
        matched_skills = [s['name'] for s in category_all_skills if s['name'] in selected_skills_set]

        # 找出未具備的字典物件清單
        missing_skills_objs = [s for s in category_all_skills if s['name'] not in selected_skills_set]
        # 分離核心與非核心技能
        core_skills = [sk['name'] for sk in missing_skills_objs if sk.get('is_core') is True]
        non_core_skills = [sk['name'] for sk in missing_skills_objs if not sk.get('is_core')]

        # 核心技能全留 + 非核心技能補滿至至少 10 個
        needed_non_core_count = max(0, 10 - len(core_skills))
        final_missing_skills = core_skills + non_core_skills[:needed_non_core_count]

        processed_list.append({
            'category_code': cat_code,
            'category_name': cat_name,
            'category_desc': ratio_info.get('category_desc', ''), # 訴求 3：職業簡介
            'match_percent': round(match_percent, 2),
            # 🔴 1. 新增此行：將計算出的原始 Score 傳給前端 (觀測數據用)
            'score': round(score, 2),
            'matched_skills': matched_skills, # 訴求 2：已具備
            'missing_skills': final_missing_skills,
            'stars': stars
        })

    # 5. 進行分群與排序
    processed_list.sort(key=lambda x: x['match_percent'], reverse=True)

    grouped_results = {5: [], 4: [], 3: [], 2: [], 1: []}
    for item in processed_list:
        grouped_results[item['stars']].append(item)

    grouped_results = {stars: items for stars, items in grouped_results.items() if len(items) > 0}

    return render_template(
        'page2.html',
        grouped_results=grouped_results,
        selected_skills=selected_skills
    )

# ==========================================
# P3 專用：對照表與區域英文代碼轉換函式
# ==========================================
SALARY_UNIT_MAP = {
    "ALL": "",
    "10": "待遇面議",
    "20": "元/件",
    "30": "元/時",
    "40": "元/日",
    "50": "元/月",
    "60": "元/年",
    "70": "元/週"
}

def match_region_key(raw_text):
    if not raw_text:
        return "北部"
    
    raw_text = str(raw_text).strip().upper()
    
    # 1. 對應資料庫中的英文區域代碼 (N, E, S, W, OI, OS)
    code_map = {
        'N': '北部',
        'E': '中部',
        'S': '南部',
        'W': '東部',
        'OI': '離島',
        'OS': '海外'
    }
    if raw_text in code_map:
        return code_map[raw_text]
        
    # 2. 備用文字比對 (防止部分欄位存中文)
    if any(k in raw_text for k in ["離島", "澎湖", "金門", "馬祖", "連江", "綠島"]):
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
        
    return "北部"

# ==========================================
# P3 專屬 Route：全台區域與薪資地圖 
# ==========================================
@app.route("/map", methods=["GET", "POST"])
# @app.route("/page3", methods=["GET", "POST"])
def page3():
    """
    載入指定職業類別在全台 6 大區域的職缺數量與不同年資之薪資統計
    """
    category_code = request.form.get("category_code") or request.args.get("category") or request.args.get("category_code")
    category_name_req = request.form.get("category_name") or request.args.get("category_name")
    # 🔴 新增：讀取前端傳入的 region_group 參數 (預設給 'N' 表示北部，或可為 'ALL')
    region_group = request.form.get("region_group") or request.args.get("region_group") or request.args.get("region")
    
    # 確保 salary_type 預設為 '50' (月薪)
    salary_type = str(request.args.get("salary_type", "50")).strip()
    if not salary_type or salary_type == 'None':
        salary_type = "50"

    if not category_code or not category_code.strip():
        category_code = "2010002005"
    else:
        category_code = str(category_code).strip()

    unit_text = SALARY_UNIT_MAP.get(salary_type, "")

    # 初始化 6 大區域字典
    regions = {r: {
        "count": 0,
        "unit": unit_text,
        "exp_any": "尚無資料",
        "exp_1to3": "尚無資料",
        "exp_4to6": "尚無資料",
        "exp_7to9": "尚無資料",
        "exp_10plus": "尚無資料"
    } for r in ["北部", "中部", "南部", "東部", "離島", "海外"]}

    category_name = category_name_req if category_name_req else category_code

    try:
        conn = conn_to_mysql_gold()
        if conn:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                cat_code_str = str(category_code).strip()

                # 1. 補全職業中文名稱
                if not category_name_req or category_name_req == category_code:
                    sql_cat = """
                        SELECT category_name FROM fact_job_ratio 
                        WHERE category_code = %s AND category_name IS NOT NULL AND category_name != ''
                        LIMIT 1;
                    """
                    cursor.execute(sql_cat, (cat_code_str,))
                    cat_row = cursor.fetchone()
                    if cat_row and cat_row.get("category_name"):
                        category_name = cat_row.get("category_name")

                # 2. 精準查詢統計表
                sql_stat = """
                    SELECT 
                        region_group,
                        exp_level,
                        job_count,
                        avg_salary_mid,
                        median_salary,
                        avg_salary_min,
                        avg_salary_max
                    FROM fact_category_salary_stat
                    WHERE category_code = %s 
                      AND (CAST(salary_type_code AS CHAR) = %s OR salary_type_code = %s);
                """
                cursor.execute(sql_stat, (cat_code_str, salary_type, int(salary_type) if salary_type.isdigit() else 50))
                job_rows = cursor.fetchall()

                # 3. 區域資料解析
                exp_stats = {r: {"exp_any": [], "exp_1to3": [], "exp_4to6": [], "exp_7to9": [], "exp_10plus": []} for r in regions.keys()}
                region_max_counts = defaultdict(int)

                for j in job_rows:
                    r_key = match_region_key(j.get("region_group"))
                    if r_key not in exp_stats:
                        r_key = "北部"

                    cnt = j.get("job_count") or 0
                    
                    region_max_counts[r_key] += cnt

                    exp_level = str(j.get("exp_level", "不拘"))
                    min_sal = j.get("avg_salary_min")
                    max_sal = j.get("avg_salary_max")
                    mid_sal = j.get("avg_salary_mid") or j.get("median_salary")

                    if min_sal and max_sal and float(min_sal) > 0:
                        sal_display = f"({int(float(min_sal)):,} ~ {int(float(max_sal)):,} 元)"
                    elif mid_sal and float(mid_sal) > 0:
                        sal_display = f"(均價約 {int(float(mid_sal)):,} 元)"
                    else:
                        sal_display = "(待遇面議)"

                    if "10年" in exp_level:
                        group = "exp_10plus"
                    elif "7~9" in exp_level or "7-9" in exp_level:
                        group = "exp_7to9"
                    elif "4~6" in exp_level or "4-6" in exp_level:
                        group = "exp_4to6"
                    elif "1~3" in exp_level or "1-3" in exp_level:
                        group = "exp_1to3"
                    else:
                        group = "exp_any"

                    exp_stats[r_key][group].append(f"共 {cnt} 筆 {sal_display}")

                # 4. 填回區域總數與細項
                for r_key in regions.keys():
                    regions[r_key]["count"] = region_max_counts[r_key]
                    for g_key, info_list in exp_stats[r_key].items():
                        if info_list:
                            regions[r_key][g_key] = " / ".join(info_list)

            conn.close()
    except Exception as e:
        print(f"MySQL P3 讀取失敗: {e}")

    return render_template(
        "page3.html", 
        category_code=category_code, 
        category_name=category_name,
        region_group = region_group,
        current_salary_type=salary_type, 
        regions=regions
    )

# 區域代碼 mapping 對照表
REGION_MAP_PAGE4 = {
    'ALL': '全部區域',
    'N': '北部',
    'E': '中部',
    'S': '南部',
    'W': '東部',
    'OI': '離島/海外',
    'OS': '其他'
}

# def load_salary_type_map():
#     salary_map = {}
#     conn = conn_to_mysql_gold()
#     if conn:
#         try:
#             with conn.cursor(pymysql.cursors.DictCursor) as cursor:
#                 sql = """
#                     SELECT salary_type_code, salary_raw_text 
#                     FROM gold_db.fact_category_salary_stat
#                     GROUP BY salary_type_code, salary_raw_text
#                 """
#                 cursor.execute(sql)
#                 rows = cursor.fetchall()
#                 for row in rows:
#                     if row['salary_type_code']:
#                         # 轉為字串確保 key 類型一致 (例如 '60': '年薪(已除12月)')
#                         salary_map[str(row['salary_type_code'])] = row['salary_raw_text']
#         except Exception as e:
#             print(f"載入 SALARY_TYPE_MAP 失敗: {e}")
#         finally:
#             conn.close()
    
#     # 若資料庫無資料或連線失敗，提供預設備用對照
#     if not salary_map:
#         salary_map = {
#             '10': '待遇面議', '20': '論件計酬', '30': '時薪',
#             '40': '日薪', '50': '月薪', '60': '年薪(已除12月)', '70': '部分工時'
#         }
#     return salary_map

# SALARY_TYPE_MAP = load_salary_type_map()

@app.route('/jobs', methods=['GET', 'POST'])
def page4_jobs():
    # 1. 接收基本參數
    if request.method == 'POST':
        category_code = request.form.get('category_code') or request.form.get('category') or request.args.get('category') or request.args.get('category_code')
        selected_region = (request.form.get('region') or request.args.get('region', 'ALL')).upper()
        salary_type_code = request.form.get('salary_type') or request.args.get('salary_type') or request.args.get('salary_text')
        page = int(request.form.get('page', 1))
    else:
        category_code = request.args.get('category') or request.args.get('category_code')
        selected_region = request.args.get('region', 'ALL').upper()
        salary_type_code = request.args.get('salary_type') or request.args.get('salary_text')
        page = request.args.get('page', 1, type=int)

    # 將代碼轉為中文標籤 (若找不到對照表則維持原值，確保相容性)[cite: 8, 10]
    # salary_type_label = SALARY_TYPE_MAP.get(str(salary_type_code), salary_type_code)

    per_page = 20  # 每頁顯示 20 筆[cite: 8]
    offset = (page - 1) * per_page

    jobs = []
    category_name = None
    total_count = 0
    total_pages = 1
    conn = conn_to_mysql_gold()
    
    if conn:
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                # A. 撈取職業名稱
                if category_code:
                    cursor.execute("""
                        SELECT category_name 
                        FROM gold_db.bridge_job_category 
                        WHERE category_code = %s 
                        LIMIT 1;
                    """, (category_code,))
                    cat_row = cursor.fetchone()
                    if cat_row and cat_row.get('category_name'):
                        category_name = cat_row['category_name']

                # B. 動態組裝 WHERE 條件
                where_clauses = []
                params = []
                join_clause = ""

                if category_code:
                    join_clause = " INNER JOIN gold_db.bridge_job_category b ON f.job_id = b.job_id"
                    where_clauses.append("b.category_code = %s")
                    params.append(category_code)

                if selected_region != 'ALL':
                    where_clauses.append("f.region_group = %s")
                    params.append(selected_region)

                # 修正點 1：正確且精準比對 salary_type_code
                if salary_type_code:
                    where_clauses.append("f.salary_type_code = %s")
                    params.append(salary_type_code)

                where_sql = (" WHERE " + " AND ".join(where_clauses)) if where_clauses else ""

                # C. 先算符合條件的【總筆數】
                count_query = f"SELECT COUNT(DISTINCT f.job_id) AS total FROM gold_db.fact_job_cards f {join_clause} {where_sql}"
                cursor.execute(count_query, params)
                total_count = cursor.fetchone()['total'] or 0
                total_pages = max(1, math.ceil(total_count / per_page))

                # D. 分頁查詢職缺列表
                query = f"""
                    SELECT DISTINCT
                        f.job_id, f.region_group, f.salary_type_code, f.job_title AS title,
                        f.company_name AS company, f.industry_name AS industry,
                        f.location_text AS location, f.salary_text AS salary,
                        f.exp_edu_text AS exp, f.work_mode, f.skills_json,
                        f.job_desc_short AS desc_text, f.job_url AS url
                    FROM gold_db.fact_job_cards f
                    {join_clause}
                    {where_sql}
                    ORDER BY f.job_id DESC
                    LIMIT %s OFFSET %s;
                """
                query_params = params + [per_page, offset]
                cursor.execute(query, query_params)
                rows = cursor.fetchall()

                for row in rows:
                    raw_skills = row['skills_json']
                    if isinstance(raw_skills, str):
                        try:
                            skills = json.loads(raw_skills)
                        except json.JSONDecodeError:
                            skills = []
                    elif isinstance(raw_skills, list):
                        skills = raw_skills
                    else:
                        skills = []

                    jobs.append({
                        'id': row['job_id'],
                        'title': row['title'],
                        'company': row['company'],
                        'industry': row['industry'] or '未提供產業',
                        'location': row['location'] or '未提供地點',
                        'salary': row['salary'] or '面議',
                        'exp': row['exp'] or '不限',
                        'work_mode': row['work_mode'] or '公司未提供此資訊',
                        'skills': skills,
                        'desc': row['desc_text'] or '無詳細說明',
                        'url': row['url']
                    })
        except Exception as e:
            print(f"Database Query Error: {e}")
        finally:
            conn.close()

    current_region_label = REGION_MAP_PAGE4.get(selected_region, '全部區域')

    # 修正點 2：將 salary_type_label (中文顯示) 帶給前端
    return render_template(
        'page4.html',
        jobs=jobs,
        category_code=category_code,
        category_name=category_name,
        current_region=selected_region,
        current_region_label=current_region_label,
        salary_type=salary_type_code, # 供按鈕 URL 傳參繼續使用 code
        # salary_type_label=salary_type_label, # 供前端文字顯示
        current_page=page,
        total_pages=total_pages,
        total_count=total_count
    )

if __name__ == '__main__':
    conn_to_mysql_gold()
    app.run(debug=True, port=5000)