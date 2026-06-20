import sys

import threading

from PySide6 import QtCore, QtWidgets, QtGui
from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QLabel, 
    QHBoxLayout,
    QGroupBox,
    QVBoxLayout,
    QPushButton,
    QLineEdit
)

class ControlWidget(QtWidgets.QWidget):
    def __init__(self):
        super().__init__()

        self.build_ui()

        self.setFixedSize(580, 300)

    def build_ui(self):
        root = QVBoxLayout()
        top = QHBoxLayout()
        bottom = QHBoxLayout()


        speed_filter = QtGui.QIntValidator()
        speed_filter.setRange(1, 9999)

        alignment_layout = QVBoxLayout()
        
        alignment_title = QLabel("Alignment")
        alignment_speed = QLineEdit()
        alignment_speed.setValidator(speed_filter)
        alignment_speed.editingFinished.connect(self.on_edit_finished)
        alignment_speed.setMaximumWidth(80)
        alignment_layout.addWidget(alignment_title)
        alignment_layout.addWidget(alignment_speed)

        focus_layout = QVBoxLayout()
        focus_title = QLabel("Focus")
        focus_speed = QLineEdit()
        focus_speed.setValidator(speed_filter)
        focus_speed.editingFinished.connect(self.on_edit_finished)
        focus_speed.setMaximumWidth(80)
        focus_layout.addWidget(focus_title)
        focus_layout.addWidget(focus_speed)

        top.addStretch()
        top.addLayout(alignment_layout)
        top.addStretch()
        top.addLayout(focus_layout)
        top.addStretch()

        top.setAlignment(Qt.AlignCenter)


        self.tracking_status = QPushButton("Tracking")
        self.tracking_status.setMinimumHeight(40)
        self.tracking_status.setMaximumWidth(300)


        bottom.addWidget(self.tracking_status)

        self.hidden_widget = QtWidgets.QWidget()
        self.hidden_widget.setFocusPolicy(Qt.StrongFocus)
        self.hidden_widget.setMaximumHeight(0)

        root.addWidget(self.hidden_widget)
        
        root.addLayout(top)
        root.addLayout(bottom)

        controls = QLabel("ESC: Exit      E: Toggle Aligning      T: Track\nW: Move up      S: Move down      A: Move cw      D: Move ccw\nI: Focus in      O: Focus out")
        controls.setAlignment(Qt.AlignCenter)
        controls.setMaximumHeight(60)
        root.addWidget(controls)

        self.setLayout(root)

    def on_edit_finished(self):
        line_edit = self.sender()
        line_edit.clearFocus()
        print(line_edit.text())

    def tracking_status_color_update(self, condition):
        color = "green" if condition else "red"
        self.tracking_status.setStyleSheet(
            f"background-color: {color}; color: white;"
        )

    def keyPressEvent(self, event):
        key = event.key()

        if key == Qt.Key.Key_Escape:
            self.close()
        elif key == Qt.Key.Key_T:
            self.tracking_status_color_update(True)
            if currentlyTracking == True:
                
        elif key == Qt.Key.Key_E:
            aligning = not aligning
        else:
            super().keyPressEvent(event)



# TODO: fix focus+tracking same time issue
def window():
    global currentlyTracking
    global current_alt, current_az

    aligning = True


    while running:
        for event in pygame.event.get():

                if event.key == pygame.K_t:
                    if currentlyTracking == True:
                        print("stopping tracking")
                        currentlyTracking = False
                        tracking_thread.join()
                    elif currentlyTracking == False:
                        if aligning == True:
                            print("exit aligning mode before tracking")
                        else:
                            print("send slew from stellarium")
                            ra_deg, dec_deg = stellarium_connect.get_slew()
                            target_alt, target_az = stellarium_connect.ra_dec_to_alt_az(ra_deg, dec_deg, latitude, longitude)
                            current_alt, current_az = slew(target_alt, target_az, 500, False)
                            currentlyTracking = True
                            tracking_thread = threading.Thread(target=tracking, args=(ra_deg, dec_deg, ))
                            tracking_thread.start()
                            print("tracking...")
                        

        keys = pygame.key.get_pressed()

        dx = 0
        dy = 0

        d = 0

        if keys[pygame.K_o]:
            d -= round(focus_step_speed[current_focus_speed] / tickrate)
        if keys[pygame.K_i]:
            d += round(focus_step_speed[current_focus_speed] / tickrate)

        if aligning:
            if keys[pygame.K_d]:
                dx += (movement_step_speed / tickrate)
            if keys[pygame.K_a]:
                dx -= (movement_step_speed / tickrate)

            if keys[pygame.K_w]:
                dy += (movement_step_speed / tickrate)
            if keys[pygame.K_s]:
                dy -= (movement_step_speed / tickrate)


        
        if aligning:
            if dx != 0 or dy != 0:
                if queue_status() == 1:
                    move_to([round(get_pos(False)[0] + dy), round(get_pos(False)[1] + dx)], movement_step_speed, False)

        if d != 0:
            if queue_status() == 1:
                command_queue.put((move_to, get_pos(True) + d, focus_step_speed[current_focus_speed], True))
                #move_to(get_pos(True) + d, focus_step_speed[current_focus_speed], True)

        if currentlyTracking:
            current_tracking_color = tracking_color_active
        else:
            current_tracking_color = tracking_color_inactive

        tracking_text = font.render("Tracking", True, (255, 255, 255), current_tracking_color)
        tracking_text_rect = tracking_text.get_rect(center=(200, 250))
        tracking_bg = pygame.Rect(0, 200, 400, 100)
        pygame.draw.rect(screen, tracking_bg_color, tracking_bg)
        tracking_bg_small = pygame.Rect(125, 225, 150, 50)
        pygame.draw.rect(screen, current_tracking_color, tracking_bg_small)
        screen.blit(tracking_text, tracking_text_rect)

        if aligning:
            movement_text = font.render(f"{movement_step_speed}", True, (255, 255, 255), alignment_color)
        else:
            movement_text = font.render("---", True, (255, 255, 255), alignment_color)
        focus_text = font.render(f"{focus_step_speed[current_focus_speed]}", True, (255, 255, 255), focus_color)

        movement_textRect = movement_text.get_rect(center=(100, 100))
        focus_textRect = focus_text.get_rect(center=(300, 100))

        movement_bg = pygame.Rect(0, 0, 200, 200)
        focus_bg = pygame.Rect(200, 0, 200, 200)

        pygame.draw.rect(screen, alignment_color, movement_bg)
        pygame.draw.rect(screen, focus_color, focus_bg)

        screen.blit(movement_text, movement_textRect)
        screen.blit(focus_text, focus_textRect)
        screen.blit(alignment_title, alignment_title_rect)
        screen.blit(focus_title, focus_title_rect)

        pygame.display.update()

        clock.tick(tickrate)

    pygame.quit()
    if currentlyTracking == True:
        currentlyTracking = False
        tracking_thread.join()



if __name__ == "__main__":
    app = QtWidgets.QApplication([])

    app.setPalette(QtGui.QPalette(QtGui.QColor("#222222")))

    widget = ControlWidget()
    widget.show()

    sys.exit(app.exec())