import socket, atexit, struct, math, time

def ra_dec_to_alt_az(ra_deg, dec_deg, lat_deg, lon_deg, t=None):
    # Current time
    if t is None:
        t = time.time()

    # Julian Date
    jd = t / 86400.0 + 2440587.5

    # Greenwich Sidereal Time
    gst = 280.46061837 + 360.98564736629 * (jd - 2451545.0)
    gst = gst % 360

    # Local Sidereal Time
    lst = (gst + lon_deg) % 360

    # Hour Angle
    ha = (lst - ra_deg) % 360
    if ha > 180:
        ha -= 360

    # Convert to radians
    ha_rad  = math.radians(ha)
    dec_rad = math.radians(dec_deg)
    lat_rad = math.radians(lat_deg)

    # Altitude
    sin_alt = (math.sin(dec_rad) * math.sin(lat_rad) +
               math.cos(dec_rad) * math.cos(lat_rad) * math.cos(ha_rad))
    alt = math.asin(sin_alt)

    # Azimuth
    cos_az = ((math.sin(dec_rad) - math.sin(alt) * math.sin(lat_rad)) /
              (math.cos(alt) * math.cos(lat_rad)))
    az = math.acos(cos_az)

    # Fix quadrant
    if math.sin(ha_rad) > 0:
        az = 2 * math.pi - az

    # Convert to degrees
    alt_deg = math.degrees(alt)
    az_deg  = math.degrees(az)

    # to convert from stellarium thinks that pos = cw, this thinks neg = cw
    az_deg = (360 - az_deg) % 360

    return alt_deg, az_deg


conn = None
sock = None


def start_socket():
    global conn, sock

    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    sock.bind(('127.0.0.1', 10001))

    sock.listen(1)
    print("Server is listening...")

    conn, addr = sock.accept()
    print("connected to stellarium")


def close_socket():
    global conn, sock
    conn.close()
    sock.close()



# def exit_handler():
#     sock.close()

# atexit.register(exit_handler)


def get_slew():
    data = conn.recv(1024)
    length, commandType, systemTime, ra_int, dec_int = struct.unpack("<HHQIi", data)

    ra_deg  = (ra_int / 2**32) * 360.0
    dec_deg = (dec_int / 2**32) * 360.0
    # print(f"Length: {length}")
    # print(f"Type: {commandType}")
    # print(f"Time: {systemTime}")
    # print(f"RA: {ra_int}")
    # print(f"RA (deg): {ra_deg}")
    # print(f"Dec: {dec_int}")
    # print(f"Dec (deg): {dec_deg}")
    print("Slew recieved")

    return ra_deg, dec_deg
