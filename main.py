import serial, struct
import constants, Encoder, Writer
import atexit, time, pygame
import stellarium_connect
import info
import threading
import queue

def exit_handler():
    w.close()
    stellarium_connect.close_socket()

atexit.register(exit_handler)


ser = serial.Serial('/dev/ttyACM0', 115200, timeout=1)
w = Writer.StreamWriter(ser, 1)

# printer distance to 1deg
az_1deg = 389.16 # 35100/90 = 390
alt_1deg = 664.44 # 40116/60 = 668.6 661.38
# TODO: need to calibrate alt more? az is pretty good

latitude = info.latitude
longitude = info.longitude


# current alt, az
current_alt = 0
current_az = 0

currentlyTracking = False


command_queue = queue.Queue()


def slew(target_alt, target_az, speed, tracking):
    effective_az = target_az

    if target_az - current_az > 180:
        effective_az = target_az - 360
    if target_az - current_az < -180:
        effective_az = target_az + 360

    move_to([round(target_alt * alt_1deg), round(effective_az * az_1deg)], speed, False)

    if tracking == False:
        print("slewing...")
        while get_pos(False) != (round(target_alt * alt_1deg), round(effective_az * az_1deg)):
            time.sleep(0.1)
        print("target reached!")

    return target_alt, target_az
    

# TODO: 2 star alignment to reduce error in using 1 star to calibrate
# error seems large when using camera with 2x barlow
def align():
    print("Center bright star in eyepiece, slew in Stellarium when done (press e in window to exit alignment mode)")
    ra_deg, dec_deg = stellarium_connect.get_slew()
    star_alt, star_az = stellarium_connect.ra_dec_to_alt_az(ra_deg, dec_deg, latitude, longitude)
    print(f"Star alt: {star_alt}, Star az: {star_az}")

    print("Alignment complete!")
    return star_alt, star_az


# TODO: update for new window system if using
def second_star_align(target_alt, target_az, start_alt, start_az):
    #movement_window()
    global current_alt, current_az
    current_az = get_pos(False)[1] / az_1deg
    current_alt = get_pos(False)[0] / alt_1deg

    print(f"alt: current {current_alt} - target {target_alt} = {current_alt - target_alt}, start {start_alt}")
    print(f"updated alt_1deg: {alt_1deg * ((target_alt - start_alt) / (current_alt - start_alt))}")
    print(f"az: current {current_az} - target {target_az} = {current_az - target_az}, start {start_az}")
    print(f"updated az_1deg: {az_1deg * ((target_az - start_az + 180) % 360 - 180) / ((current_az - start_az + 180) % 360 - 180)}")


def move_to(pos, speed, focus):
    if focus == False:
        payload = struct.pack(
            '<BiiiiiIBfh', # 32 bytes (512 byte buffer size)
            constants.host_action_command_dict['QUEUE_EXTENDED_POINT_ACCELERATED'],
            pos[0],pos[1],0,get_pos(True),0,
            speed,
            Encoder.encode_axes([]),
            1,
            1
        )
    elif focus == True:
        payload = struct.pack(
            '<BiiiiiIBfh', # 32 bytes (512 byte buffer size)
            constants.host_action_command_dict['QUEUE_EXTENDED_POINT_ACCELERATED'],
            get_pos(False)[0],get_pos(False)[1],0,pos,0,
            speed,
            Encoder.encode_axes([]),
            1,
            1
        )

    w.send_action_payload(payload)


def stop():
    payload = struct.pack(
        '<BB', 
        constants.host_query_command_dict['EXTENDED_STOP'], 
        (1<<0) | (1<<2)
    )

    w.send_action_payload(payload)


def get_pos(focus):
    payload = struct.pack(
        '<B',
        constants.host_query_command_dict['GET_EXTENDED_POSITION']
    )

    response = w.send_query_payload(payload)
    unpackedResponse = struct.unpack('<BiiiiiH', response)
    if focus == False:
        return unpackedResponse[1], unpackedResponse[2]
    elif focus == True:
        return unpackedResponse[4]


def set_pos(alt, az, focus):
    payload = struct.pack(
        '<Biiiii',
        constants.host_action_command_dict['SET_EXTENDED_POSITION'],
        alt, az, 0, focus, 0
    )

    w.send_action_payload(payload)


def queue_status():
    payload = struct.pack(
        '<B',
        constants.host_query_command_dict['IS_FINISHED']
    )

    response = w.send_query_payload(payload)
    unpackedResponse = struct.unpack('<BB', response)
    return unpackedResponse[1]


def read_eeprom():
    payload = struct.pack(
        '<BHB',
        constants.host_query_command_dict['READ_FROM_EEPROM'],
        0x014A, 1
    )

    response = w.send_query_payload(payload)
    unpackedResponse = struct.unpack('<BB', response)
    return unpackedResponse[1]


def write_eeprom():
    payload = struct.pack(
        '<BHBB',
        constants.host_query_command_dict['WRITE_TO_EEPROM'],
        0x014A, 1, 0
    )

    response = w.send_query_payload(payload)
    unpackedResponse = struct.unpack('<BB', response)
    return unpackedResponse


# TODO: fix focus+tracking same time issue
def window():
    global currentlyTracking
    global current_alt, current_az

    pygame.init()
    screen = pygame.display.set_mode((580, 300))
    pygame.display.set_caption('Terminator Control')
    clock = pygame.time.Clock()
    running = True
    aligning = True
    movement_step_speed = 500
    tickrate = 10

    focus_step_speed = [500, 250, 100, 50, 20]
    current_focus_speed = 0

    font = pygame.font.Font(None, 32)
    controls_font = pygame.font.Font(None, 24)

    alignment_color = (50,50,50)
    focus_color = (100,100,100)
    tracking_color_active = (0, 150, 0)
    tracking_color_inactive = (150, 0, 0)
    current_tracking_color = tracking_color_inactive
    tracking_bg_color = (75, 75, 75)

    alignment_title = font.render("Alignment", True, (255, 255, 255), alignment_color)
    focus_title = font.render("Focus", True, (255, 255, 255), focus_color)
    alignment_title_rect = alignment_title.get_rect(center=(100, 67))
    focus_title_rect = focus_title.get_rect(center=(300, 67))

    controls = ["W: move up", "S: move down", "A: move cw", "D: move ccw", "UP: move speed +", "DOWN: move speed -", "E: disable alignment", "I: focus in", "O: focus out", "L: focus speed +", "K: focus speed -", "", "T: goto and track", "", "ESC: exit"]
    controls_text = []
    controls_rects = []
    for index, c in enumerate(controls):
        current_control = controls_font.render(c, True, (255,255,255), (0,0,0))
        controls_text.append(current_control)
        current_rect = current_control.get_rect()
        if index == 0:
            current_rect.left = 403
            current_rect.centery = 12
        else:
            current_rect.left = controls_rects[index - 1].left
            current_rect.centery = controls_rects[index - 1].centery + 20
        controls_rects.append(current_rect)
    
    for i in range(len(controls)):
        screen.blit(controls_text[i], controls_rects[i])
    


    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    running = False

                if event.key == pygame.K_e:
                    aligning = not aligning

                if aligning:
                    if event.key == pygame.K_UP:
                        movement_step_speed += 50
                    elif event.key == pygame.K_DOWN:
                        movement_step_speed -= 50

                if event.key == pygame.K_l:
                    if current_focus_speed != 0:
                        current_focus_speed -= 1
                elif event.key == pygame.K_k:
                    if current_focus_speed != len(focus_step_speed) - 1:
                        current_focus_speed += 1

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


def tracking(ra_deg, dec_deg):
    global current_alt, current_az
    delta_time = 1
    while currentlyTracking:
        next_alt, next_az = stellarium_connect.ra_dec_to_alt_az(ra_deg, dec_deg, latitude, longitude, time.time() + delta_time)
        delta_alt = next_alt - current_alt
        if next_az - current_az > 180:
            next_az = next_az - 360
        if next_az - current_az < -180:
            next_az = next_az + 360
        delta_az = next_az - current_az
        # TODO: figure out how to deal with speed
        # in general, it seems like the speed required is around 1.1, but the motors are just too low resolution to effectively track (maybe, need to test)
        # idea: put gear reducers on both, which if i do the 4:1 ones should 4x the resolution
        # maybe dont need to but will find out tonight
        speed = round((((alt_1deg * delta_alt) ** 2 + (az_1deg * delta_az) ** 2) ** 0.5) / delta_time)
        command_queue.put((slew, next_alt, next_az, speed, True))
        #slew(next_alt, next_az, speed, True)
        time.sleep(delta_time)
        current_alt, current_az = next_alt, next_az


def worker():
    while True:
        while queue_status() == 0:
            pass
        items = command_queue.get()
        func = items[0]
        args = items[1:]
        func(*args)
        command_queue.task_done()

    
#stop()
if __name__ == "__main__":
    stellarium_connect.start_socket()
    threading.Thread(target=worker, daemon=True).start()
    window_thread = threading.Thread(target=window)
    window_thread.start()
    current_alt, current_az = align()
    set_pos(round(current_alt * alt_1deg), round(current_az * az_1deg), 0)
    window_thread.join()
    command_queue.join()
    stellarium_connect.close_socket()

# notes: 
# az movement pos -> ccw, neg -> cw
# 1deg az is about 5mm
# moves same distance regardless of speed, moves same speed regardless of distance
# speed in units/sec, same units as distance (eg move 1000 at 1000 takes 1s, 1000 at 500 is 2s, 1000 at 2000 is 0.5s, etc)
