import json

import psycopg2
from jsonpath_ng import parse

from database.db_config import (
    db_name_postgr,
    super_user,
    host,
    db_name_attend,
    dekanat_usr,
    password,
)


def connect_to_postgres():
    try:
        conn = psycopg2.connect(dbname=db_name_postgr, user=super_user, host=host)
        conn.autocommit = True
        print("Успешно подключено к базе данных PostgreSQL.")
        return conn
    except Exception as e:
        print(f"Ошибка подключения к базе данных PostgreSQL: {e}")
        return None


def grant_privileges_to_dekanat_user(conn):
    with conn.cursor() as cursor:
        try:
            # Предоставляем права на схему public
            cursor.execute(f"GRANT ALL PRIVILEGES ON SCHEMA public TO {dekanat_usr}")
            # Предоставляем права на все таблицы в схеме public
            cursor.execute(
                f"GRANT ALL PRIVILEGES ON ALL TABLES IN SCHEMA public TO {dekanat_usr}"
            )
            # Предоставляем права на все последовательности в схеме public
            cursor.execute(
                f"GRANT ALL PRIVILEGES ON ALL SEQUENCES IN SCHEMA public TO {dekanat_usr}"
            )
            # Устанавливаем права по умолчанию для новых таблиц
            cursor.execute(
                f"ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL PRIVILEGES ON TABLES TO {dekanat_usr}"
            )

            # Проверяем, были ли предоставлены права на создание объектов
            cursor.execute(
                f"SELECT has_schema_privilege('{dekanat_usr}', 'public', 'CREATE')"
            )
            has_create_privilege = cursor.fetchone()[0]
            if has_create_privilege:
                print(
                    "Все необходимые права предоставлены пользователю 'dekanat_user'."
                )
            else:
                print(
                    "Права на создание объектов в схеме public не были предоставлены."
                )

        except Exception as e:
            print(f"Ошибка при предоставлении прав пользователю '{dekanat_usr}': {e}")


def create_user_if_needed(conn):
    with conn.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_roles WHERE rolname = 'dekanat_user'")
        exists = cursor.fetchone()
        if not exists:
            cursor.execute(
                "CREATE ROLE dekanat_user WITH LOGIN PASSWORD 'your_password' SUPERUSER"
            )
            print("Пользователь 'dekanat_user' создан с правами суперпользователя.")
        else:
            print("Пользователь 'dekanat_user' уже существует.")

        cursor.execute(
            "SELECT has_schema_privilege('dekanat_user', 'public', 'CREATE')"
        )


def create_database_if_needed(conn):
    with conn.cursor() as cursor:
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = 'attendance'")
        exists = cursor.fetchone()
        if not exists:
            cursor.execute("CREATE DATABASE attendance")
            print("База данных 'attendance' создана.")
        else:
            print("База данных 'attendance' уже существует.")

            def connect_to_db_as_dekanat_user():
                try:
                    conn = psycopg2.connect(
                        dbname=db_name_attend, user=super_user, host=host, password=password
                    )
                    conn.autocommit = True
                    print("Успешно подключено к базе данных 'attendance'.")
                    return conn
                except Exception as e:
                    print(f"Ошибка подключения к базе данных 'attendance': {e}")
                    return None


def connect_to_db_as_dekanat_user():
    try:
        conn = psycopg2.connect(
            dbname=db_name_attend, user=super_user, host=host, password=password
        )
        conn.autocommit = True
        print("Успешно подключено к базе данных 'attendance'.")
        return conn
    except Exception as e:
        print(f"Ошибка подключения к базе данных 'attendance': {e}")
        return None


def read_json_file(file_path):
    with open(file_path, "r", encoding="utf-8") as file:
        return json.load(file)


def create_tables_if_needed(conn):
    with conn.cursor() as cursor:
        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS groups (
            groupCode TEXT PRIMARY KEY,  
            groupNum TEXT
        )
        """
        )

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS students (
            student_id SERIAL PRIMARY KEY,
            studUID TEXT NOT NULL,
            studFIO TEXT NOT NULL,
            groupCode TEXT,
            speciality TEXT,  
            FOREIGN KEY (groupCode) REFERENCES groups(groupCode) ON DELETE CASCADE,
            UNIQUE (studUID, groupCode)
        )
        """
        )

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS schedule (
            id SERIAL PRIMARY KEY,
            area TEXT,
            groupCode TEXT,
            date DATE,
            tutor TEXT,
            workStart TIME,
            workEnd TIME,
            FOREIGN KEY (groupCode) REFERENCES groups(groupCode) ON DELETE CASCADE,
            UNIQUE (area, groupCode, date, tutor, workStart, workEnd)
        )
        """
        )

        cursor.execute(
            """
        CREATE TABLE IF NOT EXISTS SKUD (
            record_id SERIAL PRIMARY KEY,
            studUID TEXT,
            groupCode TEXT,
            date DATE,
            timeIN TIME,
            timeOUT TIME,
            FOREIGN KEY (studUID, groupCode) REFERENCES students(studUID, groupCode) ON DELETE CASCADE,
            UNIQUE (studUID, groupCode, date, timeIN, timeOUT)
        )
        """
        )

        print("Все таблицы успешно созданы или уже существуют.")


def insert_data_to_db(conn, data, skud_data):
    # Используем jsonpath для извлечения расписания
    jsonpath_expr_schedule = parse("sheduler[*]")
    sheduler_items = jsonpath_expr_schedule.find(data)

    # Используем множества для исключения дубликатов и ускорения поиска
    insert_groups_values = set()
    insert_students_values = set()
    insert_schedule_values = set()
    insert_skud_values = set()

    # Извлечение данных для групп и студентов
    for group in data["groups"]:
        groupCode = group["groupCode"]
        groupNum = group["groupNum"]
        insert_groups_values.add((groupCode, groupNum))

        for student in group["students"]:
            studUID = student["studentUID"]
            studFIO = student["studentFIO"]
            speciality = student["speciality"]
            insert_students_values.add((studUID, studFIO, groupCode, speciality))

    # Вставка групп и студентов в базу данных
    with conn.cursor() as cursor:
        try:
            conn.autocommit = False  # Отключаем автокоммит

            # Вставка групп
            if insert_groups_values:
                cursor.executemany(
                    """
                    INSERT INTO groups (groupCode, groupNum)
                    VALUES (%s, %s)
                    ON CONFLICT (groupCode) DO NOTHING;
                """,
                    list(insert_groups_values),
                )

            # Вставка студентов
            if insert_students_values:
                cursor.executemany(
                    """
                    INSERT INTO students (studUID, studFIO, groupCode, speciality)
                    VALUES (%s, %s, %s, %s)
                    ON CONFLICT (studUID, groupCode) DO NOTHING;
                """,
                    list(insert_students_values),
                )

            conn.commit()  # Фиксируем транзакцию
            print("Группы и студенты успешно добавлены.")
        except psycopg2.Error as e:
            conn.rollback()
            print(f"Ошибка при вставке групп и студентов: {e.pgcode} - {e.pgerror}")
            return

    # Загрузка studUID и groupCode из таблицы students
    with conn.cursor() as cursor:
        cursor.execute("SELECT studUID, groupCode FROM students;")
        rows = cursor.fetchall()
        studuid_to_groupcodes = {}
        for studUID, groupCode in rows:
            studuid_to_groupcodes.setdefault(studUID, set()).add(groupCode)
    student_uids_set = set(studuid_to_groupcodes.keys())

    # Загрузка существующих записей расписания
    with conn.cursor() as cursor:
        cursor.execute(
            "SELECT area, groupCode, date, tutor, workStart, workEnd FROM schedule"
        )
        existing_schedule_entries = set(cursor.fetchall())

    # Извлечение данных для расписания
    for sheduler_item in sheduler_items:
        work_year = sheduler_item.value["workYear"]
        work_month = sheduler_item.value["workMonth"]
        work_date = sheduler_item.value["workDate"]
        work_sheduler_items = sheduler_item.value["workSheduler"]

        for work in work_sheduler_items:
            date = f"{work_year}-{work_month:02d}-{work_date:02d}"
            workStart = work["workStart"]
            workEnd = work["workEnd"]
            area = work["area"]
            tutor = work["tutor"]

            for group in work.get("groups", []):
                group_code = group["groupCode"]
                schedule_entry = (area, group_code, date, tutor, workStart, workEnd)
                if schedule_entry not in existing_schedule_entries:
                    insert_schedule_values.add(schedule_entry)

    # Извлечение данных для SKUD
    for record in skud_data:
        for studUID, entries in record.items():
            if studUID not in student_uids_set:
                continue  # Пропускаем неизвестных студентов

            groupCodes = studuid_to_groupcodes[studUID]

            for entry in entries:
                date = entry["Day"][:10]
                timeIn = entry["TimeIn"][11:19]
                timeOut = entry["TimeOut"][11:19]

                for groupCode in groupCodes:
                    skud_entry = (studUID, groupCode, date, timeIn, timeOut)
                    insert_skud_values.add(skud_entry)

    # Вставка расписания и данных SKUD
    with conn.cursor() as cursor:
        try:
            # Вставка расписания
            if insert_schedule_values:
                cursor.executemany(
                    """
                    INSERT INTO schedule(area, groupCode, date, tutor, workStart, workEnd)
                    VALUES (%s, %s, %s::DATE, %s, %s::TIME, %s::TIME)
                    ON CONFLICT (area, groupCode, date, tutor, workStart, workEnd) DO NOTHING;
                """,
                    list(insert_schedule_values),
                )

            # Вставка данных SKUD
            if insert_skud_values:
                cursor.executemany(
                    """
                    INSERT INTO SKUD (studUID, groupCode, date, timeIN, timeOUT)
                    VALUES (%s, %s, %s::DATE, %s::TIME, %s::TIME)
                    ON CONFLICT (studUID, groupCode, date, timeIN, timeOUT) DO NOTHING;
                """,
                    list(insert_skud_values),
                )

            conn.commit()  # Фиксируем транзакцию
            print("Расписание и данные SKUD успешно добавлены.")
        except psycopg2.Error as e:
            conn.rollback()
            print(
                f"Ошибка при вставке расписания и данных SKUD: {e.pgcode} - {e.pgerror}"
            )


def get_subjects():
    conn = connect_to_db_as_dekanat_user()  # Подключаемся к базе данных
    subjects = []
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DISTINCT area FROM schedule;")  # Пример запроса
            subjects = [row[0] for row in cursor.fetchall()]
    except Exception as e:
        print(f"Ошибка при получении предметов: {e}")
    finally:
        if conn:
            conn.close()  # Закрываем соединение
    return subjects


def get_groups():
    conn = connect_to_db_as_dekanat_user()
    groups = []
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT groupNum FROM groups;")  # Используем groupNum
            groups = [row[0] for row in cursor.fetchall()]
    except Exception as e:
        print(f"Ошибка при получении групп: {e}")
    finally:
        if conn:
            conn.close()
    return groups


def get_students_for_group(group_num):
    conn = connect_to_db_as_dekanat_user()
    students = []
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                """
                SELECT s.studFIO
                FROM students s
                JOIN groups g ON s.groupCode = g.groupCode
                WHERE g.groupNum = %s;
                """,
                (group_num,),
            )
            students = [row[0] for row in cursor.fetchall()]
    except Exception as e:
        print(f"Ошибка при получении студентов для группы {group_num}: {e}")
    finally:
        if conn:
            conn.close()
    return students


def get_teachers():
    conn = connect_to_db_as_dekanat_user()  # Подключаемся к базе данных
    teachers = []
    try:
        with conn.cursor() as cursor:
            cursor.execute("SELECT DISTINCT tutor FROM schedule;")  # Пример запроса
            teachers = [row[0] for row in cursor.fetchall()]
    except Exception as e:
        print(f"Ошибка при получении преподавателей: {e}")
    finally:
        if conn:
            conn.close()  # Закрываем соединение
    return teachers


def get_attendance_data(subjects, groups, students, teachers, start_date, end_date):
    conn = connect_to_db_as_dekanat_user()
    attendance_data = []
    try:
        with conn.cursor() as cursor:
            # Базовый SQL-запрос
            query = """
                SELECT
                    s.studUID,
                    s.studFIO,
                    g.groupNum,
                    sch.date,
                    sch.area,
                    sch.workStart,
                    sch.workEnd,
                    sk.timeIN,
                    sk.timeOUT,
                    CASE
                        WHEN sk.studUID IS NOT NULL AND sk.timeOUT > sch.workStart AND sk.timeIN < sch.workEnd THEN 'Присутствовал'
                        ELSE 'Отсутствовал'
                    END AS attendance
                FROM
                    students s
                JOIN
                    groups g ON s.groupCode = g.groupCode  -- Соединяем с таблицей групп
                JOIN
                    schedule sch ON s.groupCode = sch.groupCode
                LEFT JOIN
                    SKUD sk ON s.studUID = sk.studUID
                              AND s.groupCode = sk.groupCode
                              AND sk.date = sch.date
                WHERE
                    sch.date BETWEEN %s AND %s
            """

            conditions = []
            params = [start_date, end_date]  # Начальные параметры даты

            if subjects:
                conditions.append("sch.area IN %s")
                params.append(tuple(subjects))
            if groups:
                conditions.append("g.groupNum IN %s")  # Фильтрация по groupNum
                params.append(tuple(groups))
            if students:
                conditions.append("s.studFIO IN %s")
                params.append(tuple(students))
            if teachers:
                conditions.append("sch.tutor IN %s")
                params.append(tuple(teachers))

            # Если есть условия, добавляем их в запрос
            if conditions:
                query += " AND " + " AND ".join(conditions)

            # Выполнение запроса
            cursor.execute(query, params)
            attendance_data = cursor.fetchall()
            print(f"SQL запрос: {query}")
            print(
                f"Параметры: start_date={start_date}, end_date={end_date}, subjects={subjects}, groups={groups}, students={students}, teachers={teachers}"
            )

    except Exception as e:
        print(f"Ошибка при получении данных о посещаемости: {e}")
    finally:
        if conn:
            conn.close()
    return attendance_data


def get_groups_for_teacher(teacher_name):
    conn = connect_to_db_as_dekanat_user()
    groups = []
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT DISTINCT g.groupNum
                FROM groups g
                JOIN schedule sch ON g.groupCode = sch.groupCode
                WHERE sch.tutor = %s;
            """
            cursor.execute(query, (teacher_name,))
            result = cursor.fetchall()
            groups = [
                row[0] for row in result
            ]  # Преобразуем результат в список groupNum
    except Exception as e:
        print(f"Ошибка при получении групп для преподавателя: {e}")
    finally:
        if conn:
            conn.close()
    return groups


def get_groups_for_subject(subject_name):
    conn = connect_to_db_as_dekanat_user()
    groups = []
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT DISTINCT g.groupNum
                FROM groups g
                JOIN schedule sch ON g.groupCode = sch.groupCode
                WHERE sch.area = %s;
            """
            cursor.execute(query, (subject_name,))
            result = cursor.fetchall()
            groups = [
                row[0] for row in result
            ]  # Преобразуем результат в список groupNum
    except Exception as e:
        print(f"Ошибка при получении групп для предмета: {e}")
    finally:
        if conn:
            conn.close()
    return groups
