import sys
from PyQt5 import QtWidgets
from GUI.guimenu import AttendanceTool


if __name__ == "__main__":
    app = QtWidgets.QApplication(sys.argv)
    window = AttendanceTool()
    window.show()
    sys.exit(app.exec_())
