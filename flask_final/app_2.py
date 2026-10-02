from flask import Flask, render_template, request
from pymysql import connect
import pymysql
from collections import defaultdict
import os
from dotenv import load_dotenv
import json

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

# 六大區域配置[cite: 1, 2, 4]
REGION_MAP = {
    'N': {'name': '北部地區', 'color': '#10b981'},
    'E': {'name': '中部 / 西部', 'color': '#3b82f6'},
    'S': {'name': '南部地區', 'color': '#ef4444'},
    'W': {'name': '東部地區', 'color': '#8b5cf6'},
    'OI': {'name': '離島地區', 'color': '#f59e0b'},
    'OS': {'name': '海外地區', 'color': '#64748b'}
}

# 定義 SQL 代碼與前端中文名稱的對照表 (固定順序)
EXP_MAP = {
    'not_requir': '不拘',
    '1to3': '1~3年',
    '4to6': '4~6年',
    '7to9': '7~9年',
    'over10': '10年以上'
}


@app.route('/map', methods=['GET', 'POST'])
def page3_map():
    # 支援 GET 或 POST 取得 category_code
    if request.method == 'POST':
        category_code = request.form.get('category_code') or request.args.get('category', '2007001022')
    else:
        category_code = request.args.get('category', '2007001022')

    conn = conn_to_mysql_gold()
    available_salary_texts = []
    
    try:
        with conn.cursor(pymysql.cursors.DictCursor) as cursor:
            # 1. 撈取該類別下存在的 salary_raw_text 作為切換按鈕
            cursor.execute("""
                SELECT DISTINCT salary_raw_text, salary_type_code 
                FROM fact_category_salary_stat 
                WHERE category_code = %s
                ORDER BY salary_type_code
            """, (category_code,))
            raw_results = cursor.fetchall()
            available_salary_texts = [r['salary_raw_text'] for r in raw_results]

            if not available_salary_texts:
                available_salary_texts = ['月薪', '時薪', '年薪', '待遇面議', '論件計酬']

            selected_salary_text = request.args.get('salary_text', available_salary_texts[0])

            # 2. 撈取資料 (區域 x exp_level 聚合數據)
            sql = """
                SELECT 
                    region_group,
                    exp_level,
                    SUM(job_count) AS total_jobs,
                    MIN(salary_min) AS group_min,
                    MAX(salary_max) AS group_max,
                    ROUND(AVG(avg_salary_mid), 1) AS group_mid
                FROM fact_category_salary_stat
                WHERE category_code = %s 
                  AND salary_raw_text = %s
                GROUP BY region_group, exp_level
            """
            cursor.execute(sql, (category_code, selected_salary_text))
            query_data = cursor.fetchall()

            # 3. 初始化數據結構，預設 5 個年資區間皆為空資料
            regions_data = {}
            for code, meta in REGION_MAP.items():
                regions_data[code] = {
                    'name': meta['name'],
                    'color': meta['color'],
                    'total_count': 0,
                    'exp_data': {
                        exp_code: {'label': label, 'min': None, 'max': None, 'mid': None, 'count': 0} 
                        for exp_code, label in EXP_MAP.items()
                    }
                }

            # 4. 將查詢結果填入結構中
            for row in query_data:
                r_code = row['region_group']
                exp_code = row['exp_level']
                
                if r_code in regions_data:
                    regions_data[r_code]['total_count'] += (row['total_jobs'] or 0)
                    if exp_code in regions_data[r_code]['exp_data']:
                        regions_data[r_code]['exp_data'][exp_code].update({
                            'min': row['group_min'],
                            'max': row['group_max'],
                            'mid': row['group_mid'],
                            'count': row['total_jobs'] or 0
                        })

    finally:
        conn.close()

    return render_template(
        'page3.html',
        category_code=category_code,
        available_salary_texts=available_salary_texts,
        current_salary_text=selected_salary_text,
        regions=regions_data,
        exp_codes=list(EXP_MAP.keys())  # 傳遞 key 列表以維持固定顯示順序
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

@app.route('/jobs', methods=['GET', 'POST'])
def page4_jobs():
    # 1. 同時支援 POST (表單) 或 GET (URL 參數) 接收 category 與 region
    if request.method == 'POST':
        category_code = request.form.get('category_code') or request.args.get('category')
        selected_region = (request.form.get('region') or request.args.get('region', 'ALL')).upper()
    else:
        category_code = request.args.get('category')
        selected_region = request.args.get('region', 'ALL').upper()

    jobs = []
    conn = conn_to_mysql_gold()
    
    if conn:
        try:
            with conn.cursor(pymysql.cursors.DictCursor) as cursor:
                query = """
                    SELECT 
                        job_id,
                        region_group,
                        salary_type_code,
                        job_title AS title,
                        company_name AS company,
                        industry_name AS industry,
                        location_text AS location,
                        salary_text AS salary,
                        exp_edu_text AS exp,
                        work_mode,
                        skills_json,
                        job_desc_short AS desc_text,
                        job_url AS url
                    FROM gold_db.fact_job_search_card
                    WHERE 1=1
                """
                params = []

                # 如果有傳入職業類別代碼，則加入篩選
                if category_code:
                    query += " AND category_code = %s"
                    params.append(category_code)
                
                # 如果有選擇特定區域，則加入篩選
                if selected_region != 'ALL':
                    query += " AND region_group = %s"
                    params.append(selected_region)
                    
                query += " ORDER BY job_id DESC LIMIT 100;"
                
                cursor.execute(query, params)
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
    
    return render_template(
        'page4.html', 
        jobs=jobs, 
        category_code=category_code,
        current_region=selected_region,
        current_region_label=current_region_label
    )

if __name__ == '__main__':
    conn_to_mysql_gold()
    app.run(debug=True, port=5000)