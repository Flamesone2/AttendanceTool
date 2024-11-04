from database.db_utils import (
    connect_to_postgres,
    create_database_if_needed,
    create_user_if_needed,
    connect_to_db_as_dekanat_user,
    grant_privileges_to_dekanat_user,
    create_tables_if_needed,
    read_json_file,
    insert_data_to_db,
)
from database.db_config import (
    db_name_postgr,
    super_user,
    host,
    db_name_attend,
    dekanat_usr,
    password,
)


def main_db_script(json_schedule_path, json_skud_path):
    # Подключение к базе данных
    conn = connect_to_postgres()
    try:
        create_database_if_needed(conn)
        create_user_if_needed(conn)
        grant_privileges_to_dekanat_user(conn)  # Убедитесь, что права предоставлены
        conn.close()  # Закрываем соединение с сервером
        conn = connect_to_db_as_dekanat_user()
        # Проверяем права на создание объектов
        with conn.cursor() as cursor:
            cursor.execute(
                f"SELECT has_schema_privilege('{dekanat_usr}', 'public', 'CREATE')"
            )
        create_tables_if_needed(conn)  # Теперь создаем таблицы
        schedule_data = read_json_file(json_schedule_path)
        skud_data = read_json_file(json_skud_path)
        insert_data_to_db(conn, schedule_data, skud_data)
    except Exception as e:
        print(f"Произошла ошибка: {e}")
    finally:
        if conn:
            conn.close()
