from PyQt5.uic import loadUi
from fontTools.misc.plistlib import end_date
import sys

from database import main_db_script  # Импортируйте вашу функцию для обработки данных
from database.db_utils import (
    get_subjects,
    get_groups,
    get_teachers,
    get_students_for_group,
    connect_to_db_as_dekanat_user,
    get_attendance_data,
    get_groups_for_subject,
    get_groups_for_teacher,
)
import warnings

warnings.filterwarnings("ignore", category=UserWarning, module="matplotlib")

from PyQt5.QtWidgets import (
    QMainWindow,
    QFileDialog,
    QTabWidget,
    QLineEdit,
    QPushButton,
    QTextEdit,
    QTreeView,
    QDateEdit,
    QMessageBox,
    QDialog,
    QCalendarWidget,
    QTableWidget,
    QTableWidgetItem,
    QLabel,
    QVBoxLayout,
    QWidget,
    QApplication,
    qApp
)
from PyQt5.QtGui import QStandardItemModel, QStandardItem
from PyQt5.QtCore import Qt, QModelIndex, QDate
import matplotlib.pyplot as plt
from PyQt5.QtCore import QThread, pyqtSignal
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import os
import pandas as pd
import matplotlib.dates as mdates


class AttendanceTool(QMainWindow):

    def __init__(self):
        super(AttendanceTool, self).__init__()
        self.editing_start = None
        self.editing_end = None
        loadUi("AttendanceTool.ui", self)  # Загрузка интерфейса из .ui файла
        self.conn = connect_to_db_as_dekanat_user()

        # Создаем таблицу для отображения результатов
        self.attendanceTable = QTableWidget(self)
        self.attendanceTable.setColumnCount(2)  # Два столбца: имя студента и статус
        self.attendanceTable.setHorizontalHeaderLabels(["Студент", "Статус"])

        # Поле для вывода процента посещаемости
        self.attendancePercentageLabel = QLabel("Процент посещаемости: 0%", self)

        # Добавляем элементы на новую вкладку
        self.resultsTab = QWidget()
        layout = QVBoxLayout()
        layout.addWidget(self.attendanceTable)
        layout.addWidget(self.attendancePercentageLabel)
        self.resultsTab.setLayout(layout)
        # Изменение названия вкладки
        self.tabWidget = self.findChild(
            QTabWidget, "tabWidget"
        )  # Получаем доступ к QTabWidget
        self.tabWidget.setTabText(0, "Поиск файлов")
        self.tabWidget.setTabText(1, "Настройка выборки")
        # Добавляем новую вкладку
        self.tabWidget = self.findChild(
            QTabWidget, "tabWidget"
        )  # Найдите и установите tabWidget
        self.buttonExportToExcel = QPushButton("Экспорт в Excel", self)
        self.buttonExportToExcel.clicked.connect(self.export_to_excel)
        self.tabWidget.addTab(self.resultsTab, "Результаты посещаемости")
        self.tabWidget.widget(2).layout().addWidget(self.buttonExportToExcel)
        self.last_saved_directory = None
        # Инициализация флагов для отслеживания активного поля
        self.editing_start = False
        self.editing_end = False

        # Инициализация элементов управления
        self.dateEditStart = self.findChild(QDateEdit, "dateEditStart")
        self.dateEditEnd = self.findChild(QDateEdit, "dateEditEnd")
        self.calendarEdit = self.findChild(QCalendarWidget, "calendarEdit")

        # Скрываем календарь по умолчанию
        self.calendarEdit.setHidden(True)

        # Подключаем события для нажатия на QDateEdit
        self.dateEditStart.mousePressEvent = self.open_calendar_start
        self.dateEditEnd.mousePressEvent = self.open_calendar_end

        # Подключаем событие выбора даты в календаре
        self.calendarEdit.clicked.connect(self.update_date)

        # Инициализация элементов управления
        self.ButtonBrowse = self.findChild(QPushButton, "ButtonBrowse")
        self.ButtonBrowse.clicked.connect(self.browse_folder)

        self.lineEditDirectory = self.findChild(QLineEdit, "lineEditDirectory")
        self.textEdit = self.findChild(QTextEdit, "textEdit")
        self.textEdit.setHtml(
            "<p>Выберите расположение, в котором находятся файлы расписания и СКУД:</p>"
        )

        # Вкладка 2
        self.lineEditSearch = self.findChild(QLineEdit, "lineEditSearch")
        self.lineEditSearch.textChanged.connect(self.filter_trees)
        self.buttonSearch = self.findChild(QPushButton, "buttonGetAttendance")
        self.buttonSearch.clicked.connect(self.calculate_attendance)

        self.subjectTreeView = self.findChild(QTreeView, "Subjects")
        self.groupTreeView = self.findChild(QTreeView, "Groups")
        self.teacherTreeView = self.findChild(QTreeView, "Teachers")

        # Модели для QTreeView
        self.subjectModel = QStandardItemModel()
        self.groupModel = QStandardItemModel()
        self.teacherModel = QStandardItemModel()

        # Устанавливаем заголовки
        self.subjectModel.setHorizontalHeaderLabels(["Дисциплины"])
        self.groupModel.setHorizontalHeaderLabels(["Группы"])
        self.teacherModel.setHorizontalHeaderLabels(["Преподаватели"])

        # Устанавливаем модели для QTreeView
        self.subjectTreeView.setModel(self.subjectModel)
        self.groupTreeView.setModel(self.groupModel)
        self.teacherTreeView.setModel(self.teacherModel)

        self.subjectTreeView.setHeaderHidden(True)
        self.groupTreeView.setHeaderHidden(True)
        self.teacherTreeView.setHeaderHidden(True)

        # Добавление вкладки аналитики
        self.add_analytics_tab()

        # Заполнение деревьев
        if self.conn:
            self.populate_subjects()
            self.populate_groups()
            self.populate_teachers()
            self.populate_date_range()
            self.groupModel.itemChanged.connect(self.on_item_changed)

    def filter_trees(self):
        search_text = self.lineEditSearch.text()  # Получаем текст из поля поиска
        self.filter_tree(self.subjectTreeView, self.subjectModel, search_text)
        self.filter_tree(self.groupTreeView, self.groupModel, search_text)
        self.filter_tree(self.teacherTreeView, self.teacherModel, search_text)

    def filter_tree(self, tree_view, model, text):
        text = (
            text.lower()
        )  # Приводим текст к нижнему регистру для нечувствительного поиска
        for i in range(model.rowCount()):
            item = model.item(i)
            # Проверяем, должен ли родительский элемент быть видимым
            item_visible = text in item.text().lower()
            tree_view.setRowHidden(
                i, QModelIndex(), not item_visible
            )  # Устанавливаем видимость родительского элемента
            self.filter_child_items(
                tree_view, model, item, text, i
            )  # Фильтруем дочерние элементы

    def filter_child_items(self, tree_view, model, parent_item, text, parent_index):
        for i in range(parent_item.rowCount()):
            child_item = parent_item.child(i)
            # Проверяем, должен ли дочерний элемент быть видимым
            child_visible = text in child_item.text().lower()
            child_index = model.index(
                parent_index, i
            )  # Получаем индекс дочернего элемента
            tree_view.setRowHidden(
                child_index.row(), QModelIndex(), not child_visible
            )  # Устанавливаем видимость дочернего элемента
            self.filter_child_items(
                tree_view, model, child_item, text, parent_index
            )  # Рекурсивно фильтруем дочерние элементы

    def closeEvent(self, event):
        # Закрываем подключение к базе данных при закрытии окна
        if self.conn:
            self.conn.close()
            print("Подключение к базе данных закрыто.")
        event.accept()

    def update_date_end_range(self):
        # Устанавливаем минимальную дату для dateEnd равной dateStart
        start_date = self.dateStart.date()
        self.dateEnd.setMinimumDate(start_date)

    # Остальные методы остаются без изменений
    def populate_subjects(self):
        subjects = get_subjects()  # Получаем данные из базы данных
        print("Subjects:", subjects)  # Отладочное сообщение
        self.subjectModel.clear()  # Очищаем модель перед заполнением
        for subject in subjects:
            item = QStandardItem(subject)
            item.setCheckable(True)  # Делаем элемент чекбоксом
            self.subjectModel.appendRow(item)
        print(
            "Total subjects added:", self.subjectModel.rowCount()
        )  # Количество добавленных элементов

    def populate_groups(self):
        try:
            print("Заполнение групп начато.")
            groups = get_groups()  # Получаем группы из базы данных
            self.groupModel.clear()  # Очищаем модель перед заполнением

            for group in groups:
                print(f"Обработка группы: {group}")
                group_item = QStandardItem(group)  # Используем QStandardItem

                # Получаем студентов для текущей группы
                students = get_students_for_group(group)  # Передаем группы
                for student in students:
                    print(f"Добавление студента: {student}")
                    student_item = QStandardItem(
                        student
                    )  # Используем QStandardItem для студентов
                    student_item.setCheckable(True)  # Делаем элемент чекбоксом
                    group_item.appendRow(
                        student_item
                    )  # Добавляем студента как дочерний элемент

                self.groupModel.appendRow(
                    group_item
                )  # Добавляем группу как родительский элемент

                # Устанавливаем состояние галочки для группы
                group_item.setCheckable(True)
            print("Заполнение групп завершено.")
        except Exception as e:
            print(f"Ошибка в populate_groups: {e}")

    def on_item_changed(self, item):
        # Отключаем сигнал, чтобы избежать рекурсии
        self.groupModel.itemChanged.disconnect(self.on_item_changed)

        try:
            print(
                f"Item changed: {item.text()}, State: {item.checkState()}"
            )  # Отладочное сообщение

            if item.checkState() == Qt.Checked:
                if item.hasChildren():  # Если это группа
                    index = self.groupModel.indexFromItem(item).row()
                    if index >= 10:  # Если группа не в первых десяти позициях
                        self.move_item_to_top(item)
                    self.update_student_checkboxes(
                        item, Qt.Checked
                    )  # Установите галочки у всех студентов
                else:  # Если это предмет или преподаватель
                    # Проверяем, является ли элемент предметом
                    subject_items = self.subjectModel.findItems(item.text())
                    if subject_items:  # Если предмет найден
                        self.on_subject_item_changed(item)
                        index = self.subjectModel.indexFromItem(item).row()
                        if index >= 10:  # Если предмет не в первых десяти позициях
                            self.move_item_to_top(item)
                        return  # Выходим, чтобы не выполнять дальнейшую логику

                    # Проверяем, является ли элемент учителем
                    teacher_items = self.teacherModel.findItems(item.text())
                    if teacher_items:  # Если учитель найден
                        self.on_teacher_item_changed(item)
                        index = self.teacherModel.indexFromItem(item).row()
                        if index >= 10:  # Если учитель не в первых десяти позициях
                            self.move_item_to_top(item)
                        return  # Выходим, чтобы не выполнять дальнейшую логику

                # Если это студент
                group_item = item.parent()  # Получаем родительский элемент (группу)
                if group_item:  # Проверяем, что group_item не None
                    item.setCheckState(
                        Qt.Checked
                    )  # Устанавливаем состояние галочки для студента
                    self.update_group_check_state(
                        group_item
                    )  # Обновляем состояние группы
            else:
                if item.hasChildren():  # Если это группа
                    self.update_student_checkboxes(
                        item, Qt.Unchecked
                    )  # Снимаем галочки у всех студентов
                else:  # Если это предмет или преподаватель
                    item.setCheckState(
                        Qt.Unchecked
                    )  # Снимаем галочку у предмета или преподавателя
                    group_item = item.parent()  # Получаем родительский элемент (группу)
                    if group_item:  # Проверяем, что group_item не None
                        self.update_group_check_state(
                            group_item
                        )  # Обновляем состояние группы
                    else:
                        print("Error: group_item is None")  # Отладочное сообщение

            # Обновляем состояние галочки группы
            self.update_group_check_state(item)

        finally:
            # Включаем сигнал обратно
            self.groupModel.itemChanged.connect(self.on_item_changed)

    def move_item_to_top(self, item):
        model = item.model()
        row = model.indexFromItem(item).row()
        print(
            f"Moving item: {item.text()} from row {row} to top"
        )  # Отладочное сообщение

        # Удаляем элемент из текущей позиции
        model.takeRow(row)  # Удаляем оригинал
        model.insertRow(0, item)  # Вставляем оригинал в начало

        # Если это группа, нужно также переместить студентов
        if item.hasChildren():
            for i in range(item.rowCount()):
                student_item = item.child(i)
                student_item.setCheckable(
                    True
                )  # Убедитесь, что студенты остаются чекбоксами
        # Устанавливаем состояние развернутости группы
        tree_view = self.groupTreeView  # Предполагаем, что это дерево групп
        index = model.indexFromItem(item)  # Получаем индекс элемента

    def on_subject_item_changed(self, item):
        index = self.subjectModel.indexFromItem(item).row()
        print(
            f"Subject item changed: {item.text()}, Index: {index}"
        )  # Отладочное сообщение
        if index >= 10:  # Если предмет не в первых десяти позициях
            print("Moving subject item to top")  # Отладочное сообщение
            self.move_item_to_top(item)  # Используем существующий метод

    def on_teacher_item_changed(self, item):
        index = self.teacherModel.indexFromItem(item).row()
        print(
            f"Teacher item changed: {item.text()}, Index: {index}"
        )  # Отладочное сообщение
        if index >= 10:  # Если учитель не в первых десяти позициях
            print("Moving teacher item to top")  # Отладочное сообщение
            self.move_item_to_top(item)  # Используем существующий метод

    def update_student_checkboxes(self, group_item, state):
        for i in range(group_item.rowCount()):
            student_item = group_item.child(i)
            student_item.setCheckState(
                state
            )  # Устанавливаем состояние галочки у студентов
            print(
                f"Студент {student_item.text()} выбран: {student_item.checkState() == Qt.Checked}"
            )

    def update_group_check_state(self, group_item):
        if group_item is None:  # Проверяем, что group_item не None
            print(
                "Error: group_item is None in update_group_check_state"
            )  # Отладочное сообщение
            return

        # Проверяем, что это действительно группа
        if not group_item.hasChildren():
            print(f"Error: {group_item.text()} is not a group.")  # Отладочное сообщение
            return

        # Проверяем состояние студентов в группе
        checked_count = 0
        total_count = group_item.rowCount()

        for i in range(total_count):
            student_item = group_item.child(i)
            if student_item.checkState() == Qt.Checked:
                checked_count += 1

        print(
            f"Group: {group_item.text()}, Checked: {checked_count}, Total: {total_count}"
        )  # Отладочное сообщение

        # Обновляем состояние группы на основе количества отмеченных студентов
        if checked_count == total_count:
            group_item.setCheckState(Qt.Checked)  # Все студенты отмечены
            print(
                f"Group {group_item.text()} is fully checked."
            )  # Отладочное сообщение
        elif checked_count > 0:
            group_item.setCheckState(Qt.PartiallyChecked)  # Частично отмечены
            print(
                f"Group {group_item.text()} is partially checked."
            )  # Отладочное сообщение
        else:
            group_item.setCheckState(Qt.Unchecked)  # Ни один студент не отмечен
            print(f"Group {group_item.text()} is unchecked.")  # Отладочное сообщение

    def populate_teachers(self):
        conn = connect_to_db_as_dekanat_user()  # Подключаемся к базе данных
        if conn is None:
            print("Ошибка: не удалось подключиться к базе данных 'attendance'.")
            return  # Выходим из функции, если соединение не удалось

        # Получаем преподавателей
        teachers = get_teachers()
        self.teacherModel.clear()  # Очищаем модель перед заполнением
        for teacher in teachers:
            item = QStandardItem(teacher)
            item.setCheckable(True)
            self.teacherModel.appendRow(item)

        if conn:
            conn.close()  # Закрываем соединение после использования

    def restart_application(self):
        qApp.exit()  # Закрыть текущее приложение
        QApplication(sys.argv)  # Создать новый экземпляр приложения
        qApp.exec_()  # Запустить цикл событий

    def browse_folder(self):
        # Открывает диалог выбора папки
        folder = QFileDialog.getExistingDirectory(self, "Выберите папку")
        if folder:
            self.lineEditDirectory.setText(
                folder
            )  # Устанавливает выбранную папку в строку
            self.process_json_files(folder)

    def process_json_files(self, folder):
        # Создаем и показываем LoadingDialog
        self.loading_dialog = LoadingDialog(self)
        self.loading_dialog.setModal(True)  # Делаем окно модальным
        self.loading_dialog.show()  # Показываем сообщение

        # Создаем и запускаем поток для обработки файлов
        self.file_processor = FileProcessor(
            folder,
            self.populate_subjects,
            self.populate_groups,
            self.populate_teachers,
            self.loading_dialog,

        )
        self.file_processor.finished.connect(
            self.loading_dialog.close
        )  # Закрываем диалог по завершении

        self.file_processor.start()  # Запускаем поток

    def populate_date_range(self):
        # здесь получаются доступные даты из базы данных
        conn = connect_to_db_as_dekanat_user()  # Подключение к базе
        available_dates = self.get_available_dates_from_db(conn)

        if available_dates:
            min_date = min(available_dates)
            max_date = max(available_dates)

            # Устанавливаем диапазон дат в QDateEdit и QCalendarWidget
            self.dateEditStart.setMinimumDate(min_date)
            self.dateEditStart.setMaximumDate(max_date)
            self.dateEditEnd.setMinimumDate(min_date)
            self.dateEditEnd.setMaximumDate(max_date)

            self.calendarEdit.setMinimumDate(min_date)
            self.calendarEdit.setMaximumDate(max_date)
            print(f"Диапазон доступных дат: с {min_date} по {max_date}")

    def get_available_dates_from_db(self, conn):
        # Получаем список доступных дат из базы данных
        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT DISTINCT date FROM schedule;")
                result = cursor.fetchall()
                available_dates = [
                    QDate.fromString(str(date[0]), "yyyy-MM-dd") for date in result
                ]
                return available_dates
        except Exception as e:
            print(f"Ошибка при получении диапазона дат: {e}")
            return []

    def open_calendar_start(self, event):
        self.editing_start = True
        self.editing_end = False
        self.calendarEdit.setSelectedDate(self.dateEditStart.date())
        self.show_calendar(self.dateEditStart)

    def open_calendar_end(self, event):
        self.editing_start = False
        self.editing_end = True
        self.calendarEdit.setSelectedDate(self.dateEditEnd.date())
        self.show_calendar(self.dateEditEnd)

    def show_calendar(self, date_edit_widget):
        # Отображаем календарь рядом с QDateEdit
        self.calendarEdit.setGeometry(
            date_edit_widget.geometry().x(),
            date_edit_widget.geometry().y() + date_edit_widget.height(),
            300,
            200,
        )
        self.calendarEdit.show()

    def update_date(self):
        selected_date = self.calendarEdit.selectedDate()

        # Проверка, что дата в диапазоне
        if (
                self.calendarEdit.minimumDate()
                <= selected_date
                <= self.calendarEdit.maximumDate()
        ):
            if self.editing_start:
                self.dateEditStart.setDate(selected_date)
            elif self.editing_end:
                self.dateEditEnd.setDate(selected_date)
        else:
            # Сообщение о недопустимой дате
            QMessageBox.warning(
                self,
                "Недопустимая дата",
                "Указанная дата выходит за пределы доступного диапазона.",
            )

        # Скрываем календарь после выбора даты
        self.calendarEdit.hide()

    def add_analytics_tab(self):
        self.analyticsTab = AnalyticsTab(self)
        self.tabWidget.addTab(self.analyticsTab, "Аналитика")

    def update_attendance_percentage(self, percentage):
        """Обновляет отображение процента посещаемости."""
        # Проверяем, что объект QLabel существует
        if self.attendancePercentageLabel:
            self.attendancePercentageLabel.setText(
                f"Процент посещаемости: {percentage:.2f}%"
            )
        else:
            print("Ошибка: attendancePercentageLabel не существует")

    def calculate_attendance_percentage(self, total_students, present_students):
        """Вычисление процента посещаемости."""
        if total_students == 0:
            return 0
        return (present_students / total_students) * 100

    def update_graphs_in_main_thread(self, attendance_data):
        # Функция для отрисовки графиков, которая будет вызвана в основном потоке
        self.analyticsTab.update_attendance_graph(attendance_data)

    def calculate_attendance(self):
        # Создаем и показываем уведомление о загрузке
        self.loading_dialog = LoadingDialog(self)
        self.loading_dialog.setWindowTitle("Обработка данных")
        self.loading_dialog.setModal(True)
        self.loading_dialog.show()

        # Собираем данные для передачи в поток
        selected_subjects = [
            self.subjectModel.item(i).text()
            for i in range(self.subjectModel.rowCount())
            if self.subjectModel.item(i).checkState() == Qt.Checked
        ]
        selected_groups = [
            self.groupModel.item(i).text()
            for i in range(self.groupModel.rowCount())
            if self.groupModel.item(i).checkState() == Qt.Checked
        ]
        selected_students = []
        for i in range(self.groupModel.rowCount()):
            group_item = self.groupModel.item(i)
            for j in range(group_item.rowCount()):
                student_item = group_item.child(j)
                if student_item.checkState() == Qt.Checked:
                    selected_students.append(student_item.text())

        selected_teachers = [
            self.teacherModel.item(i).text()
            for i in range(self.teacherModel.rowCount())
            if self.teacherModel.item(i).checkState() == Qt.Checked
        ]

        start_date = self.dateEditStart.date().toString("yyyy-MM-dd")
        end_date = self.dateEditEnd.date().toString("yyyy-MM-dd")

        # Создаем рабочий объект
        self.attendance_worker = AttendanceWorker(
            selected_subjects,
            selected_groups,
            selected_students,
            selected_teachers,
            start_date,
            end_date,
        )

        # Создаем поток и перемещаем объект рабочего в этот поток
        self.attendance_thread = QThread()
        self.attendance_worker.moveToThread(self.attendance_thread)

        # Подключаем сигналы и слоты
        self.attendance_worker.finished.connect(self.loading_dialog.close_dialog)
        self.attendance_worker.data_processed.connect(self.on_data_processed)
        self.attendance_worker.finished.connect(self.attendance_thread.quit)
        self.attendance_thread.started.connect(self.attendance_worker.run)

        # Запускаем поток
        self.attendance_thread.start()

    def on_data_processed(self, attendance_data, attendance_percentage):
        """Обрабатывает результат, полученный из потока."""
        # Обновляем процент посещаемости в UI
        self.update_attendance_percentage(attendance_percentage)

        # Обновляем таблицу
        self.populate_attendance_table(attendance_data)

        # Обновляем графики в аналитике
        self.analyticsTab.update_attendance_graph(attendance_data)
        self.analyticsTab.update_attendance_percentage(attendance_percentage)

    def fetch_and_display_attendance(self):
        """
        Функция для получения данных о посещаемости на основе выбранных фильтров
        и отображения их в таблице.
        """
        selected_subjects = [
            self.subjectModel.item(i).text()
            for i in range(self.subjectModel.rowCount())
            if self.subjectModel.item(i).checkState() == Qt.Checked
        ]
        selected_groups = [
            self.groupModel.item(i).text()
            for i in range(self.groupModel.rowCount())
            if self.groupModel.item(i).checkState() == Qt.Checked
        ]
        selected_students = []
        selected_teachers = [
            self.teacherModel.item(i).text()
            for i in range(self.teacherModel.rowCount())
            if self.teacherModel.item(i).checkState() == Qt.Checked
        ]

        # Собираем выбранных студентов
        for i in range(self.groupModel.rowCount()):
            group_item = self.groupModel.item(i)
            for j in range(group_item.rowCount()):
                student_item = group_item.child(j)
                if student_item.checkState() == Qt.Checked:
                    selected_students.append(student_item.text())

        # Получаем выбранный диапазон дат
        start_date = self.dateEditStart.date().toString("yyyy-MM-dd")
        end_date = self.dateEditEnd.date().toString("yyyy-MM-dd")

        # Получаем данные о посещаемости через функцию из db_utils
        attendance_data = get_attendance_data(
            selected_subjects,
            selected_groups,
            selected_students,
            selected_teachers,
            start_date,
            end_date,
        )

        # Вызываем функцию для отображения данных в таблице
        self.populate_attendance_table(attendance_data)

    def populate_attendance_table(self, attendance_data):
        """
        Заполняет таблицу данными о посещаемости, полученными из базы данных.
        attendance_data: Список кортежей с данными о посещаемости студентов.
        """

        # Устанавливаем количество столбцов, чтобы отобразить все данные
        self.attendanceTable.setColumnCount(9)  # 9 столбцов для отображения всех полей
        self.attendanceTable.setHorizontalHeaderLabels(
            [
                "ФИО студента",
                "Группа",
                "Дата",
                "Предмет",
                "Время начала",
                "Время окончания",
                "Время входа",
                "Время выхода",
                "Статус",
            ]
        )

        # Устанавливаем количество строк в таблице
        self.attendanceTable.setRowCount(len(attendance_data))
        print(f"Количество строк в таблице установлено: {len(attendance_data)}")

        for row, (
                studUID,
                studFIO,
                groupCode,
                date,
                area,
                workStart,
                workEnd,
                timeIN,
                timeOUT,
                attendance,
        ) in enumerate(attendance_data):
            # Преобразуем время в строку для корректного отображения
            workStart_str = workStart.strftime("%H:%M") if workStart else "—"
            workEnd_str = workEnd.strftime("%H:%M") if workEnd else "—"
            timeIN_str = timeIN.strftime("%H:%M") if timeIN else "—"
            timeOUT_str = timeOUT.strftime("%H:%M") if timeOUT else "—"

            # Заполняем строки таблицы реальными данными
            self.attendanceTable.setItem(
                row, 0, QTableWidgetItem(studFIO)
            )  # ФИО студента
            self.attendanceTable.setItem(row, 1, QTableWidgetItem(groupCode))  # Группа
            self.attendanceTable.setItem(
                row, 2, QTableWidgetItem(date.strftime("%Y-%m-%d"))
            )  # Дата
            self.attendanceTable.setItem(
                row, 3, QTableWidgetItem(area)
            )  # Предмет (дисциплина)
            self.attendanceTable.setItem(
                row, 4, QTableWidgetItem(workStart_str)
            )  # Время начала занятия
            self.attendanceTable.setItem(
                row, 5, QTableWidgetItem(workEnd_str)
            )  # Время окончания занятия
            self.attendanceTable.setItem(
                row, 6, QTableWidgetItem(timeIN_str)
            )  # Время входа
            self.attendanceTable.setItem(
                row, 7, QTableWidgetItem(timeOUT_str)
            )  # Время выхода
            self.attendanceTable.setItem(
                row, 8, QTableWidgetItem(attendance)
            )  # Статус ("Присутствовал" или "Отсутствовал")
        print("Таблица успешно обновлена.")

    def on_item_selected(self, item):
        if item.checkState() == Qt.Checked:
            if item in self.teacherModel.findItems(item.text()):
                self.filter_groups_by_teacher(item.text())
            elif item in self.groupModel.findItems(item.text()):
                self.filter_students_by_group(item.text())
            elif item in self.subjectModel.findItems(item.text()):
                self.filter_groups_by_subject(item.text())

    def filter_groups_by_teacher(self, teacher_name):
        # Запрос к базе данных для получения групп, которые ведет выбранный преподаватель
        groups = get_groups_for_teacher(teacher_name)
        # Обновляем QTreeView с этими группами
        self.groupModel.clear()
        for group in groups:
            item = QStandardItem(group)
            item.setCheckable(True)
            self.groupModel.appendRow(item)

    def filter_groups_by_subject(self, subject_name):
        # Запрос к базе данных для получения групп, связанных с выбранным предметом
        groups = get_groups_for_subject(subject_name)
        self.groupModel.clear()
        for group in groups:
            item = QStandardItem(group)
            item.setCheckable(True)
            self.groupModel.appendRow(item)

    def draw_attendance_graph(self):
        # Очистим фигуру
        self.figure.clear()

        # Пример данных для графика (замените реальными данными)
        days = ["2023-03-01", "2023-03-02", "2023-03-03", "2023-03-04"]
        attendance_values = [80, 90, 75, 85]  # Пример данных о посещаемости

        # Построение графика по дням
        ax1 = self.figure.add_subplot(121)
        ax1.plot(days, attendance_values, marker="o")
        ax1.set_title("Посещаемость по дням")
        ax1.set_xlabel("Дата")
        ax1.set_ylabel("Процент посещаемости")

        # Построение круговой диаграммы посещаемости
        present = sum(attendance_values)
        absent = 100 * len(attendance_values) - present

        ax2 = self.figure.add_subplot(122)
        ax2.pie(
            [present, absent],
            labels=["Присутствовали", "Отсутствовали"],
            autopct="%1.1f%%",
            startangle=90,
        )
        ax2.set_title("Диаграмма посещаемости")

        # Перерисовка графиков
        self.canvas.draw()

    def export_to_excel(self):
        # Создаем и показываем диалог загрузки
        self.loading_dialog = LoadingDialog(self)
        self.loading_dialog.setModal(True)
        self.loading_dialog.show()

        # Открываем диалог выбора места сохранения
        options = QFileDialog.Options()
        options |= QFileDialog.DontUseNativeDialog
        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Сохранить файл",
            self.last_saved_directory or "",
            "Excel Files (*.xlsx)",
            options=options,
        )

        # Если пользователь нажал "Отмена" и не выбрал файл, закрываем диалог загрузки
        if not file_path:
            self.loading_dialog.close_dialog()
            return  # Завершаем выполнение функции

        if not file_path.endswith(".xlsx"):
            file_path += ".xlsx"  # Убедимся, что файл имеет правильное расширение

        try:
            # Собираем данные из таблицы
            data = []
            for row in range(self.attendanceTable.rowCount()):
                row_data = []
                for column in range(self.attendanceTable.columnCount()):
                    item = self.attendanceTable.item(row, column)
                    row_data.append(item.text() if item else "")
                data.append(row_data)

            # Создаем DataFrame и сохраняем его в Excel
            df = pd.DataFrame(
                data,
                columns=[
                    self.attendanceTable.horizontalHeaderItem(i).text()
                    for i in range(self.attendanceTable.columnCount())
                ],
            )
            df.to_excel(file_path, index=False, engine="openpyxl")

            # Сохраняем последний каталог
            self.last_saved_directory = os.path.dirname(file_path)

            # Показываем уведомление об успешном сохранении
            QMessageBox.information(self, "Успех", "Файл успешно сохранен!")
        except Exception as e:
            QMessageBox.critical(
                self, "Ошибка", f"Произошла ошибка при сохранении файла: {e}"
            )
        finally:
            # Закрываем диалог загрузки после сохранения
            self.loading_dialog.close_dialog()


class FileProcessor(QThread):
    finished = pyqtSignal()

    def __init__(
            self,
            folder,
            populate_subjects,
            populate_groups,
            populate_teachers,
            loading_dialog,

    ):
        super().__init__()
        self.folder = folder
        self.populate_subjects = populate_subjects
        self.populate_groups = populate_groups
        self.populate_teachers = populate_teachers
        self.loading_dialog = loading_dialog  # Сохраняем ссылку на диалог

    def run(self):
        # Ищем файлы с нужными названиями
        json_schedule_files = []
        json_skud_files = []

        for filename in os.listdir(self.folder):
            if filename.startswith("shedulerData") and filename.endswith(".json"):
                json_schedule_files.append(os.path.join(self.folder, filename))
            elif filename.startswith("passing_ctrl") and filename.endswith(".json"):
                json_skud_files.append(os.path.join(self.folder, filename))

        if json_schedule_files and json_skud_files:
            # Если найдены файлы, вызываем main_db_script для каждой пары
            for schedule_file in json_schedule_files:
                for skud_file in json_skud_files:
                    main_db_script(schedule_file, skud_file)

            # Заполняем предметы и группы из базы данных
            conn = connect_to_db_as_dekanat_user()  # Подключаемся к базе данных
            # if conn:
            #     self.populate_subjects()  # Заполняем предметы
            #     self.populate_groups()  # Заполняем группы
            #     self.populate_teachers()  # Заполняем преподавателей
            #     conn.close()  # Закрываем соединение после использования

        self.loading_dialog.close_dialog()  # Закрываем диалог

        self.finished.emit()  # Сигнал о завершении обработки


class LoadingDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Загрузка")
        self.setFixedHeight(120)
        self.setFixedWidth(240)

        layout = QVBoxLayout()
        label = QLabel("Обработка файлов...")
        layout.addWidget(label)
        self.setLayout(layout)

        # Устанавливаем модальность
        self.setModal(True)

        # Убираем кнопку закрытия
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowCloseButtonHint)

    def closeEvent(self, event):
        # Игнорируем событие закрытия
        event.ignore()

    def close_dialog(self):
        self.accept()  # Закрываем диалог


class AnalyticsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.layout = QVBoxLayout(self)

        # Создаем холст для графика
        self.figure = Figure()
        self.canvas = FigureCanvas(self.figure)
        self.layout.addWidget(self.canvas)

        # Добавляем процент посещаемости
        self.attendanceLabel = QLabel("Процент посещаемости: 0%", self)
        self.layout.addWidget(self.attendanceLabel)

        # Устанавливаем макет
        self.setLayout(self.layout)

    def update_attendance_graph(self, attendance_data):
        # Очищаем старый график
        self.figure.clear()

        # Подготовка данных
        dates = [entry[3] for entry in attendance_data]  # Даты
        present_students_per_day = {}  # Словарь для подсчета присутствующих по датам
        total_students_per_day = {}  # Словарь для подсчета всех студентов по датам

        # Подсчет количества студентов, присутствующих и всех, для каждой даты
        for entry in attendance_data:
            date = entry[3]
            if date not in present_students_per_day:
                present_students_per_day[date] = 0
                total_students_per_day[date] = 0

            total_students_per_day[date] += 1
            if entry[9] == "Присутствовал":
                present_students_per_day[date] += 1

        # Подготовка данных для графика
        sorted_dates = sorted(present_students_per_day.keys())  # Сортируем даты
        present_counts = [present_students_per_day[date] for date in sorted_dates]
        absent_counts = [
            total_students_per_day[date] - present_students_per_day[date]
            for date in sorted_dates
        ]  # Отсутствующие

        # Преобразуем даты в числовой формат для корректного отображения
        sorted_dates_numeric = [mdates.date2num(date) for date in sorted_dates]

        # Построение столбчатой диаграммы посещаемости
        ax1 = self.figure.add_subplot(121)
        width = 0.2 if len(sorted_dates) == 1 else 0.4  # Меняем ширину для одного дня

        # Явно задаем цвета для столбцов
        present_color = "green"
        absent_color = "red"

        ax1.bar(
            sorted_dates_numeric,
            present_counts,
            width=width,
            color=present_color,
            label="Присутствовали",
        )
        ax1.bar(
            sorted_dates_numeric,
            absent_counts,
            width=width,
            color=absent_color,
            bottom=present_counts,
            label="Отсутствовали",
        )

        # Форматирование оси X для отображения дат
        if (
                len(set([date.year for date in sorted_dates])) == 1
        ):  # Если все даты из одного года
            ax1.xaxis.set_major_formatter(mdates.DateFormatter("%d-%m"))  # Убираем год
        else:
            ax1.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))

        ax1.xaxis.set_major_locator(mdates.AutoDateLocator())
        ax1.set_xlabel("Дата")
        ax1.set_ylabel("Количество студентов")
        ax1.set_title("Посещаемость по дням")
        ax1.legend()

        # Увеличиваем расстояние между датами на оси X
        plt.xticks(rotation=45, ha="right")

        # Если много дат, расширяем ось X, чтобы столбцы не сливались
        if len(sorted_dates) > 1:
            ax1.set_xlim(sorted_dates_numeric[0] - 1, sorted_dates_numeric[-1] + 1)

        # Круговая диаграмма присутствия и отсутствия
        total_present = sum(present_counts)
        total_absent = sum(absent_counts)

        # Проверяем, есть ли данные для круговой диаграммы
        if total_present > 0 or total_absent > 0:
            ax2 = self.figure.add_subplot(122)
            ax2.pie(
                [total_present, total_absent],
                labels=["Присутствовали", "Отсутствовали"],
                colors=[present_color, absent_color],
                autopct="%1.1f%%",
                startangle=90,
            )
            ax2.set_title("Диаграмма посещаемости")
        else:
            print("Нет данных для построения круговой диаграммы")

        # Перерисовка холста
        self.canvas.draw()

    def update_attendance_percentage(self, percentage):
        self.attendanceLabel.setText(f"Процент посещаемости: {percentage:.2f}%")


from PyQt5.QtCore import QObject, QThread, pyqtSignal


class AttendanceWorker(QObject):
    finished = pyqtSignal()  # Сигнал, указывающий на завершение работы
    data_processed = pyqtSignal(list, float)  # Сигнал для передачи обработанных данных

    def __init__(self, subjects, groups, students, teachers, start_date, end_date):
        super().__init__()
        self.subjects = subjects
        self.groups = groups
        self.students = students
        self.teachers = teachers
        self.start_date = start_date
        self.end_date = end_date

    def run(self):
        """Основной метод обработки данных."""
        try:
            # Получаем данные о посещаемости
            attendance_data = get_attendance_data(
                self.subjects,
                self.groups,
                self.students,
                self.teachers,
                self.start_date,
                self.end_date,
            )

            print(f"Полученные данные: {attendance_data}")

            # Подсчитываем количество студентов и присутствующих
            total_students = len(attendance_data)
            present_students = sum(
                1 for row in attendance_data if row[9] == "Присутствовал"
            )

            attendance_percentage = (
                (present_students / total_students) * 100 if total_students > 0 else 0
            )

            # Передаем обработанные данные через сигнал
            self.data_processed.emit(attendance_data, attendance_percentage)

        finally:
            self.finished.emit()  # Сигнал о завершении работы
