from flask import Flask, render_template, request
from pymysql import connect
import pymysql
from collections import defaultdict
import os
from dotenv import load_dotenv

import os
import math
from collections import defaultdict
from flask import Flask, render_template, request, redirect, url_for, flash
from dotenv import load_dotenv

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

    return render_template('test_1.html', skill_categories=dict(skill_categories))


@app.route('/categoriesA', methods=['GET', 'POST'])
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
        'test_2_A.html',
        grouped_results=grouped_results,
        selected_skills=selected_skills
    )

# 佔位用的第三頁路由，避免點選「選擇此職業」按鈕時跳出 404 Not Found
@app.route('/map')
def step3_map():
    category = request.args.get('category', '')
    return f"<h3>已成功選擇職業類別：{category}！這是第三頁區域地圖 (開發中)</h3><a href='/categories'>← 返回第二頁</a>"

if __name__ == '__main__':
    conn_to_mysql_gold()
    app.run(debug=True, port=5000)