import serial, struct
import constants, Encoder, Writer
import atexit, time, pygame
import stellarium_connect
import info
import multiprocessing

def exit_handler():
    w.close()
    stellarium_connect.close_socket()

atexit.register(exit_handler)


ser = serial.Serial('/dev/ttyACM0', 115200, timeout=1)
w = Writer.StreamWriter(ser, 1)

# printer distance to 1deg
az_1deg = 389.16 # 35100/90 = 390
alt_1deg = 668.6 # 40116/60 = 668.6
# TODO: need to calibrate alt more? az is pretty good

latitude = info.latitude
longitude = info.longitude


# current alt, az
current_alt = 0
current_az = 0


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
    if tracking == False:
        print("target reached!")

    return target_alt, target_az
    

# TODO: 2 star alignment to reduce error in using 1 star to calibrate
# error seems large when using camera with 2x barlow
def align():
    print("Center bright star in eyepiece (press q when done)")
    movement_window()
    print("Slew in Stellarium")
    ra_deg, dec_deg = stellarium_connect.get_slew()
    star_alt, star_az = stellarium_connect.ra_dec_to_alt_az(ra_deg, dec_deg, latitude, longitude)
    print(f"Star alt: {star_alt}, Star az: {star_az}")

    print("Alignment complete!")
    return star_alt, star_az


def second_star_align(target_alt, target_az, start_alt, start_az):
    movement_window()
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
            pos[0],pos[1],0,0,0,
            speed,
            Encoder.encode_axes(['z']),
            1,
            1
        )
    elif focus == True:
        payload = struct.pack(
            '<BiiiiiIBfh', # 32 bytes (512 byte buffer size)
            constants.host_action_command_dict['QUEUE_EXTENDED_POINT_ACCELERATED'],
            0,0,pos,0,0,
            speed,
            Encoder.encode_axes(['x', 'y']),
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
        return unpackedResponse[3]


def set_pos(alt, az):
    payload = struct.pack(
        '<Biiiii',
        constants.host_action_command_dict['SET_EXTENDED_POSITION'],
        alt, az, 0, 0, 0
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


# TODO: fix ctrl+c to stop tracking kills focus window
def focus_window():
    pygame.init()
    screen = pygame.display.set_mode((200, 200))
    pygame.display.set_caption('Focus')
    clock = pygame.time.Clock()
    running = True
    step_speed = [500, 250, 100, 50, 20]
    current_speed = 0
    tickrate = 10

    font = pygame.font.Font(None, 32)

    

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q or event.key == pygame.K_ESCAPE:
                    running = False
                if event.key == pygame.K_l:
                    if current_speed != 0:
                        current_speed -= 1
                elif event.key == pygame.K_k:
                    if current_speed != len(step_speed) - 1:
                        current_speed += 1

        keys = pygame.key.get_pressed()

        d = 0

        if keys[pygame.K_i]:
            d -= round(step_speed[current_speed] / tickrate)
        if keys[pygame.K_o]:
            d += round(step_speed[current_speed] / tickrate)

        if d != 0:
            if queue_status() == 1:
                move_to(get_pos(True) + d, step_speed[current_speed], True)

        text = font.render(f"{step_speed[current_speed]}", True, (255, 255, 255), (100,100,100))

        textRect = text.get_rect()
        textRect.center = (100, 100)
        screen.fill((100,100,100))
        screen.blit(text, textRect)
        pygame.display.update()

        clock.tick(tickrate)

    pygame.quit()


# TODO: move away from stop() b/c it causes issues with focuser motor
def movement_window():
    pygame.init()
    screen = pygame.display.set_mode((200, 200))
    pygame.display.set_caption('Alignment')
    clock = pygame.time.Clock()
    running = True
    moving = False
    step_speed = 500
    tickrate = 10

    font = pygame.font.Font(None, 32)

    

    while running:
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_q or event.key == pygame.K_ESCAPE:
                    running = False
                if event.key == pygame.K_UP:
                    step_speed += 50
                elif event.key == pygame.K_DOWN:
                    step_speed -= 50

        keys = pygame.key.get_pressed()

        dx = 0
        dy = 0

        if keys[pygame.K_d]:
            dx += az_1deg
        if keys[pygame.K_a]:
            dx -= az_1deg

        if keys[pygame.K_w]:
            dy += alt_1deg
        if keys[pygame.K_s]:
            dy -= alt_1deg

        if dx != 0 or dy != 0:
            if queue_status() == 1:
                move_to([round(get_pos(False)[0] + dy), round(get_pos(False)[1] + dx)], step_speed, False)
                moving = True
        else:
            if moving:
                stop()
                moving = False

        text = font.render(f"{step_speed}", True, (255, 255, 255), (0,0,0))

        textRect = text.get_rect()
        textRect.center = (100, 100)
        screen.fill((0,0,0))
        screen.blit(text, textRect)
        pygame.display.update()

        clock.tick(tickrate)

    pygame.quit()


# TODO: stop using KeyboardInterrupt to stop tracking, do something more elegant
def tracking(ra_deg, dec_deg):
    global current_alt, current_az
    delta_time = 1
    try:
        while True:
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
            current_alt, current_az = slew(next_alt, next_az, speed, True)
            time.sleep(delta_time)
    except KeyboardInterrupt:
        pass


# TODO: potentially move to a pygame ui instead of 2 windows + tracking in cli + cli menu
def loop():
    while True:
        option = input("goto (1), goto w/ tracking (2), cal 2nd star (4), or quit (3): ")
        while not (option == '1' or option == '2' or option == '3' or option == '4'):
            print("invalid answer")
            option = input("goto (1), goto w/ tracking (2), cal 2nd star (4), or quit (3): ")
        if option == '3':
            focus_process.terminate()
            break
        else:
            global current_alt, current_az
            ra_deg, dec_deg = stellarium_connect.get_slew()
            target_alt, target_az = stellarium_connect.ra_dec_to_alt_az(ra_deg, dec_deg, latitude, longitude)
            temp_alt = current_alt
            temp_az = current_az
            current_alt, current_az = slew(target_alt, target_az, 500, False)
            if option == '4':
                target_alt, target_az = stellarium_connect.ra_dec_to_alt_az(ra_deg, dec_deg, latitude, longitude)
                slew(target_alt, target_az, 500, False)
                second_star_align(target_alt, target_az, temp_alt, temp_az)
            if option == '2':
                print("ctrl+c to stop tracking")
                tracking(ra_deg, dec_deg)

                

    
#stop()
if __name__ == "__main__":
    stellarium_connect.start_socket()
    focus_process = multiprocessing.Process(target=focus_window)
    focus_process.start()
    current_alt, current_az = align()
    set_pos(round(current_alt * alt_1deg), round(current_az * az_1deg))
    loop()
    focus_process.join()
    stellarium_connect.close_socket()

#movement_window()

# notes: 
# az movement pos -> ccw, neg -> cw
# 1deg az is about 5mm
# moves same distance regardless of speed, moves same speed regardless of distance
# speed in units/sec, same units as distance (eg move 1000 at 1000 takes 1s, 1000 at 500 is 2s, 1000 at 2000 is 0.5s, etc)
