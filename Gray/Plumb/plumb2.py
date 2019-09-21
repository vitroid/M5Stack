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
  

x,y,z = 0,10,0
vx,vy,vz = 0,0,0
eL = 100
# k / m
km = 0.01
dump = 0.01
import utime
last = utime.ticks_ms()

while True:
  now = utime.ticks_ms()
  dt = (now - last)/10
  last = now
  
  ax,ay,az = imu0.acceleration
  L = (x**2+y**2+z**2)**0.5
  ax -= vx*dump
  ay -= vy*dump
  az -= vz*dump
  if L > eL:
    F = -km*(L-eL) / L
    ax += x*F
    ay += y*F
    az += z*F
  vx += ax*dt
  vy += ay*dt
  vz += az*dt
  x += vx*dt
  y += vy*dt
  z += vz*dt
  lcd.clear()
  draw(x,y,z,20)
  wait_ms(2)
