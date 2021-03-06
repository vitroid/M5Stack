from m5stack import *
from m5ui import *
from uiflow import *
import imu

setScreenColor(0x111111)

imu0 = imu.IMU()

import math

w,h = lcd.screensize()
cx = w//2
cy = h//2

def draw(x,y,z,r):
  scale = math.exp(-z/200)
  r = int(r*scale)
  x = int(x*scale)
  y = int(y*scale)
  if z > 0:
    lcd.circle(cx-x, cy+y, r, fillcolor=0xff0000)
  lcd.line(cx, cy, cx-x, cy+y, 0xffffff)
  if z < 0:
    lcd.circle(cx-x, cy+y, r, fillcolor=0x0000ff)
  


while True:
  lcd.clear()
  x,y,z = imu0.acceleration
  r = 100 / (x*x + y*y + z*z)**0.5
  x *= r
  y *= r
  z *= r
  draw(x,y,z,20)
  wait_ms(2)
