from m5stack import *
from m5ui import *
from uiflow import *
import imu

setScreenColor(0x111111)

imu0 = imu.IMU()

import math

w,h = lcd.screensize()

while True:
    lcd.clear()
    x,y,z = imu0.acceleration
    r = (x*x + y*y + z*z)**0.5
    x /= r
    y /= r
    z /= r
    cx = w/2
    cy = h/2
    R = 20*math.exp(-z/2)
    LR = R*5
    L = LR-R
    if z > 0:
        lcd.circle(int(cx-x*LR),int(cy+y*LR),int(R),fillcolor=0xff0000)
    lcd.line(int(cx), int(cy), int(cx-x*L), int(cy+y*L), 0xffffff)
    if z < 0:
        lcd.circle(int(cx-x*LR),int(cy+y*LR),int(R),fillcolor=0x0000ff)
    wait_ms(2)
