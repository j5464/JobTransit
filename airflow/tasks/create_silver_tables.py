import importlib.util
from pathlib import Path
import sqlalchemy as sa

def _load_conn_to_mysql():
    """Load the shared MySQL helper from the project."""
    candidates = [
        Path(__file__).resolve().parents[3] / "airflow" / "utils" / "conn_to_mysql.py",
        Path(__file__).resolve().parents[4] / "airflow" / "utils" / "conn_to_mysql.py",
        Path("/opt/airflow/utils/conn_to_mysql.py"),
    ]

    for file_path in candidates:
        if file_path.exists():
            spec = importlib.util.spec_from_file_location("_jobtransit_conn_to_mysql", file_path)
            if spec and spec.loader:
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)
                return module.conn_to_mysql

    try:
        from airflow.utils.conn_to_mysql import conn_to_mysql as imported_conn_to_mysql
        return imported_conn_to_mysql
    except ImportError as exc:
        raise ImportError(
            "Unable to import conn_to_mysql."
        ) from exc


def create_silver_tables(engine):
    """具體執行 SQL CREATE TABLE 建表的實體邏輯"""
    ddl = [
            # 1) 公司維度表：保留公司基本資訊與來源批次資訊
            """
            CREATE TABLE IF NOT EXISTS company (
                cust_no VARCHAR(50) PRIMARY KEY,
                cust_name VARCHAR(200) NULL,
                cust_url VARCHAR(500) NULL,
                industry_name VARCHAR(200) NULL,
                industry_no VARCHAR(50) NULL,
                employees_count INT NULL,
                employees_raw VARCHAR(50) NULL,
                _silver_updated_at DATETIME NULL,
                _source_batch_id VARCHAR(50) NULL
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Silver: 公司維度表';
            """,
    
            # 2) 職缺主表：保存每一筆職缺的核心資料
            """
            CREATE TABLE IF NOT EXISTS job (
                job_id VARCHAR(50) PRIMARY KEY,
                cust_no VARCHAR(50) NOT NULL,
                job_name VARCHAR(300) NULL,
                appear_date DATE NULL,
                close_date DATE NULL,
                job_description TEXT NULL,
                salary_raw_text VARCHAR(200) NULL,
                salary_min INT NULL,
                salary_max INT NULL,
                salary_type_code INT NULL,
                is_salary_negotiable BOOLEAN NULL,
                job_type_code INT NULL,
                work_exp_requirement VARCHAR(100) NULL,
                edu_requirement VARCHAR(100) NULL,
                postal_code VARCHAR(10) NULL,
                address_region VARCHAR(100) NULL,
                address_area VARCHAR(100) NULL,
                address_detail VARCHAR(200) NULL,
                landmark VARCHAR(200) NULL,
                longitude DECIMAL(10,6) NULL,
                latitude DECIMAL(10,6) NULL,
                remote_work_status VARCHAR(20) NULL,
                remote_work_description VARCHAR(500) NULL,
                vacation_policy_text VARCHAR(200) NULL,
                business_trip_text VARCHAR(200) NULL,
                manage_resp_text VARCHAR(200) NULL,
                start_working_day_text VARCHAR(100) NULL,
                need_emp_count_text VARCHAR(50) NULL,
                hr_behavior_pr DECIMAL(5,4) NULL,
                contact_email VARCHAR(200) NULL,
                welfare_description TEXT NULL,
                analysis_url VARCHAR(500) NULL,
                updated_at DATETIME NULL,
                source_batch_id VARCHAR(50) NULL,
                CONSTRAINT fk_job_company FOREIGN KEY (cust_no) REFERENCES company(cust_no)
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Silver: 職缺主表';
            """,
    
            # 3) 職缺分類表：一個職缺可能有多個類別，採用 (job_id, category_code) 做主鍵
            """
            CREATE TABLE IF NOT EXISTS job_category (
                job_id VARCHAR(50) NOT NULL,
                category_code VARCHAR(50) NOT NULL,
                category_description VARCHAR(200) NULL,
                seq_no INT NULL,
                PRIMARY KEY (job_id, category_code),
                CONSTRAINT fk_job_category_job FOREIGN KEY (job_id) REFERENCES job(job_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Silver: 職缺類別表';
            """,
    
            # 4) 技能需求表：使用 job_id + skill_code 去重，避免重複技能被重複寫入
            """
            CREATE TABLE IF NOT EXISTS job_skill (
                job_id VARCHAR(50) NOT NULL,
                skill_code VARCHAR(50) NOT NULL,
                skill_description VARCHAR(200) NULL,
                PRIMARY KEY (job_id, skill_code),
                CONSTRAINT fk_job_skill_job FOREIGN KEY (job_id) REFERENCES job(job_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Silver: 技能需求表';
            """,
    
            # 5) 專長需求表：保存專長與其代碼
            """
            CREATE TABLE IF NOT EXISTS job_specialty (
                job_id VARCHAR(50) NOT NULL,
                specialty_code VARCHAR(50) NOT NULL,
                specialty_name VARCHAR(200) NULL,
                PRIMARY KEY (job_id, specialty_code),
                CONSTRAINT fk_job_specialty_job FOREIGN KEY (job_id) REFERENCES job(job_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Silver: 專長需求表';
            """,
    
            # 6) 語言需求橋接表：職缺與語言能力的多對多關係表
            """
            CREATE TABLE IF NOT EXISTS bridge_job_language (
                job_id VARCHAR(50) NOT NULL,
                language_code VARCHAR(50) NOT NULL,
                language_name VARCHAR(50) NULL,
                listening_level VARCHAR(20) NULL,
                speaking_level VARCHAR(20) NULL,
                reading_level VARCHAR(20) NULL,
                writing_level VARCHAR(20) NULL,
                PRIMARY KEY (job_id, language_code),
                CONSTRAINT fk_bridge_language_job FOREIGN KEY (job_id) REFERENCES job(job_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Silver: 語言需求橋接表';
            """,
    
            # 7) 通用條件表：例如 major / certificate / driver_license 等多值條件
            """
            CREATE TABLE IF NOT EXISTS job_requirement (
                job_id VARCHAR(50) NOT NULL,
                requirement_type VARCHAR(50) NOT NULL,
                requirement_value VARCHAR(200) NOT NULL,
                PRIMARY KEY (job_id, requirement_type, requirement_value),
                CONSTRAINT fk_job_requirement_job FOREIGN KEY (job_id) REFERENCES job(job_id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='Silver: 其他通用條件表';
            """,
    ]

    with engine.begin() as conn:
        for sql in ddl:
            conn.execute(sa.text(sql))

    return True
