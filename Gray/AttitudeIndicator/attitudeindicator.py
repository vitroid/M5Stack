from m5stack import *
from m5ui import *
from uiflow import *
import imu

setScreenColor(0x111111)

sevenseg = [0b1110111, 0b0010010, 0b1011101, 0b1011011, 0b0111010, 0b1101011,0b0101111,0b1010010,0b1111111,0b1111010]

imu0 = imu.IMU()

def letter(L,x,y,dx,dy,c):
    if L & 0b1000000:
        lcd.line(x+dy,y-dx,x+dx+dy,y+dy-dx,c)
    if L & 0b0100000:
        lcd.line(x,y,x+dy,y-dx,c)
    if L & 0b0010000:
        lcd.line(x+dx+dy,y+dy-dx,x+dx,y+dy,c)
    if L & 0b0001000:
        lcd.line(x,y,x+dx,y+dy,c)
    if L & 0b0000100:
        lcd.line(x,y,x-dy,y+dx,c)
    if L & 0b0000010:
        lcd.line(x+dx,y+dy,x+dx-dy,y+dy+dx,c)
    if L & 0b0000001:
        lcd.line(x-dy,y+dx,x+dx-dy,y+dy+dx,c)
    
def number(v,x,y,dx,dy,c):
    x0, y0 = x,y
    for L in str(v):
        letter(sevenseg[int(L)], x0,y0,dx,dy,c)
        x0 += dx*3//2
        y0 += dy
    
import math

w,h = lcd.screensize()
cx, cy = w//2, h//2
hist = []
sx, sy, sz = 0,0,0
while True:
    x,y,z = imu0.acceleration
    hist.append((x,y,z))
    sx, sy, sz = sx+x, sy+y, sz+z
    if len(hist)>3:
        x,y,z = hist.pop(0)
        sx, sy, sz = sx-x, sy-y, sz-z
    # bank = math.atan(x,y)
    # average
    x,y,z = sx/3, sy/3, sz/3
    br = (x**2+y**2)**0.5
    bx = int(x/br*100)
    by = int(y/br*100)
    ba = math.atan2(x,y)
    pitch = math.atan2(z,y)*180/3.14
    r = h/2 - 20
    L = 10
    lcd.clear()
    for a,l in ((-60,2),(-45,1),(-30,2),(-20,1),(-10,1),(0,2),(10,1),(20,1),(30,2),(45,1),(60,2)):
        aa = ba + a*3.14/180
        c,s = math.cos(aa),math.sin(aa)
        l = l*L+r
        lcd.line(cx+int(r*s),cy-int(r*c),cx+int(l*s), cy-int(l*c), 0x008000)
    lcd.line(cx-100,cy,cx-20,cy,0x808080)
    lcd.line(cx+20,cy,cx+100,cy,0x808080)
    lcd.line(cx,20,cx+10,40,0x808080)
    lcd.line(cx,20,cx-10,40,0x808080)
  
    lcd.line(cx-by*2,cy-bx*2,cx+by*2,cy+bx*2,0x008000)
    for i in range(-3,4):
        px = int(x/br*(pitch+i*10)*3)
        py = int(y/br*(pitch+i*10)*3)
        scale = abs(i) + 1
        lcd.line(cx-by*scale//6+px,cy-bx*scale//6-py,cx+by*scale//6+px,cy+bx*scale//6-py,0x008000)
        number(abs(i*10), cx+by*(scale+1)//6+px, cy+bx*(scale+1)//6-py, by//12, bx//12, 0x008000)
        number(abs(i*10), cx-by*(scale+2)//6+px, cy-bx*(scale+2)//6-py, by//12, bx//12, 0x008000)
    wait_ms(1)
