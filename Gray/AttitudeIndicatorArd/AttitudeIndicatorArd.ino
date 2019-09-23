#include <M5Stack.h>
//#include <utility/Sprite.h>
// Uses MPU9250 by hideakitai instead of M5Stack std lib
// because latter does not work with M5 gray

#include "MPU9250.h"

MPU9250 mpu;
TFT_eSprite img = TFT_eSprite(&M5.Lcd);  // Create Sprite object "img" with pointer to "tft" object

int sevenseg[] = {0b1110111, 0b0010010, 0b1011101, 0b1011011, 0b0111010, 0b1101011,0b0101111,0b1010010,0b1111111,0b1111010};

void setup() {
  // put your setup code here, to run once:
    M5.begin();
    //M5.Lcd.setRotation(0);
    M5.Lcd.fillScreen(TFT_NAVY);
    M5.Power.begin();
    Serial.begin(115200);
    Wire.begin();
    delay(200);
    mpu.setup();
    img.setColorDepth(8);
    img.createSprite(320,240);
}

//raddar
void fillPoly(int n, int x[], int y[], long c)
{
  int i=0;
  int j=n-1;
  while(1){
    img.fillTriangle(x[i],y[i],x[i+1],y[i+1],x[j],y[j],c);
    if ( i+2==j )
      return;
    img.fillTriangle(x[i+1],y[i+1],x[j-1],y[j-1],x[j],y[j],c);
    i ++;
    j --;
    if ( i+1>=j )
      return;
  }
}

//fan
void fillPoly2(int n, int x[], int y[], long c)
{
  for(int i=1; i<n-1;i++){
    img.fillTriangle(x[0],y[0],x[i],y[i],x[i+1],y[i+1],c);
  }
}


void letter(char L, int x, int y, int dx, int dy, long c)
{
    if (L & 0b1000000)
        img.drawLine(x+dy,y-dx,x+dx+dy,y+dy-dx,c);
    if (L & 0b0100000)
        img.drawLine(x,y,x+dy,y-dx,c);
    if (L & 0b0010000)
        img.drawLine(x+dx+dy,y+dy-dx,x+dx,y+dy,c);
    if (L & 0b0001000)
        img.drawLine(x,y,x+dx,y+dy,c);
    if (L & 0b0000100)
        img.drawLine(x,y,x-dy,y+dx,c);
    if (L & 0b0000010)
        img.drawLine(x+dx,y+dy,x+dx-dy,y+dy+dx,c);
    if (L & 0b0000001)
        img.drawLine(x-dy,y+dx,x+dx-dy,y+dy+dx,c);
}
    
void
number(int v, int x, int y, int dx, int dy,long c)
{
    int h = v / 10;
    letter(sevenseg[h], x,y,dx,dy,c);
    int l = v % 10;
    x += dx*3/2;
    y += dy;
    letter(sevenseg[l], x,y,dx,dy,c);
}

    
int w = 320; //M5.Lcd.width();
int h = 240; //M5.Lcd.height(); //h = lcd.screensize()
int cx = w/2;
int cy = h/2;


float angles[] = {-60,-45,-30,-20,-10,0,10,20,30,45,60};
int Len[]      = {2,1,2,1,1,2,1,1,2,1,2};

// brown #6c5735
// 01101100 01011110 00110101
// 01101 010111 00110
int brown = 0b0110101000000110;
int orange = 0xfbe4;

void loop() {
  // put your main code here, to run repeatedly:
  mpu.update();
  
  float x = mpu.getAcc(0);
  float y = mpu.getAcc(1);
  float z = mpu.getAcc(2);
  float br = sqrt(x*x+y*y);
  int bx = (int)(x/br*100);
  int by = (int)(y/br*100);
  float ba = atan2(x,y);
  float pitch = atan2(z,y)*180/3.14;
  float r = h/2 - 30;
  int L = 15;
  //blue back
  //img.fillScreen(BLACK);
  //blue
  //img.fillCircle(cx,cy,r+L*2,0x51d);
  //img.fillRect(0,0,w,h/2,0x51d);
  //img.fillRect(0,h/2,w,h,0x7bef);
  //img.fillCircle(cx,cy,r,0x51d);
    
  //img.drawLine(cx-by*2,cy-bx*2,cx+by*2,cy+bx*2,0xffff);
  int xx[64];
  int yy[64];
  int qx = (int)(x/br*pitch*3);
  int qy = (int)(y/br*pitch*3);
  xx[0] = cx-by+qx;
  yy[0] = cy-bx-qy;
  xx[1] = cx+by+qx;
  yy[1] = cy+bx-qy;
  xx[2] = cx+by+qx-bx*2;
  yy[2] = cy+bx-qy+by*2;
  xx[3] = cx-by+qx-bx*2;
  yy[3] = cy-bx-qy+by*2;
  fillPoly(4, xx,yy, brown);
  //xx[0] = cx-by+qx;
  //yy[0] = cy-bx-qy;
  //xx[1] = cx+by+qx;
  //yy[1] = cy+bx-qy;
  xx[2] = cx+by+qx+bx*2;
  yy[2] = cy+bx-qy-by*2;
  xx[3] = cx-by+qx+bx*2;
  yy[3] = cy-bx-qy-by*2;
  fillPoly(4, xx,yy, 0x51d);
  for(int i=-6;i <= 6; i++){
    int px = (int)(x/br*(pitch+i*5)*3);
    int py = (int)(y/br*(pitch+i*5)*3);
    int scale = abs(i) + 1;
    if ( i % 2 != 0 )
      scale = 1;
    img.drawLine(cx-by*scale/12+px,cy-bx*scale/12-py,cx+by*scale/12+px,cy+bx*scale/12-py,0xffff);
    if ( i == 0 )
      continue;
    if ( i % 2 != 0 )
      continue;
    number(abs(i*5), cx+by*(scale+1)/12+px, cy+bx*(scale+1)/12-py, by/12, bx/12, 0xffff);
    number(abs(i*5), cx-by*(scale+4)/12+px, cy-bx*(scale+4)/12-py, by/12, bx/12, 0xffff);
  }
  // orange fixed
  img.fillRect(cx-70,cy-1,50,3,orange);
  img.fillRect(cx+20,cy-1,50,3,orange);
  img.fillTriangle(cx,L*2,cx+10,L*2+20,cx-10,L*2+20,orange);
  //outer ring blue
  for(int i=0;i<16;i++){
    float c = cos(i*3.1416/15-ba);
    float s = sin(i*3.1416/15-ba);
    //upper half
    xx[i] = (int)(r*c)+cx;
    yy[i] = -(int)(r*s)+cy;
    xx[31-i] = (int)((r+L*2)*c)+cx;
    yy[31-i] = -(int)((r+L*2)*s)+cy;
    xx[32+i] = -(int)(r*c)+cx;
    yy[32+i] = (int)(r*s)+cy;
    xx[63-i] = -(int)((r+L*2)*c)+cx;
    yy[63-i] = (int)((r+L*2)*s)+cy;
  }
  fillPoly(32, xx, yy, 0x51d);
  fillPoly(32, &xx[32], &yy[32], brown);
  for(int i=0;i<11;i++){
    float a = angles[i];
    float l = Len[i];
    float aa = ba + a*3.14/180;
    float c = cos(aa);
    float s = sin(aa);
    l = l*L+r;
    int rc = (int)(r*c);
    int rs = (int)(r*s);
    int lc = (int)(l*c); 
    int ls = (int)(l*s); 
    img.drawLine(cx+rs,cy-rc,cx+ls, cy-lc, 0xffff);
  }
  //black frame
  xx[0] = 0;
  yy[0] = -1;
  xx[1] = 0;
  yy[1] = cy;
  for(int i=0;i<8;i++){
    float c = cos(i*3.1416/15);
    float s = sin(i*3.1416/15);
    //upper half
    xx[i+2] = -(int)((r+L*2)*c)+cx;
    yy[i+2] = -(int)((r+L*2)*s)+cy;
  }
  fillPoly2(10, xx, yy, 0x0);
  xx[0] = w;
  yy[0] = -1;
  xx[1] = w;
  yy[1] = cy;
  for(int i=0;i<8;i++){
    float c = cos(i*3.1416/15);
    float s = sin(i*3.1416/15);
    //upper half
    xx[i+2] = +(int)((r+L*2)*c)+cx;
    yy[i+2] = -(int)((r+L*2)*s)+cy;
  }
  fillPoly2(10, xx, yy, 0x0);
  xx[0] = 0;
  yy[0] = h;
  xx[1] = 0;
  yy[1] = cy;
  for(int i=0;i<8;i++){
    float c = cos(i*3.1416/15);
    float s = sin(i*3.1416/15);
    //upper half
    xx[i+2] = -(int)((r+L*2)*c)+cx;
    yy[i+2] = (int)((r+L*2)*s)+cy;
  }
  fillPoly2(10, xx, yy, 0x0);
  xx[0] = w;
  yy[0] = h;
  xx[1] = w;
  yy[1] = cy;
  for(int i=0;i<8;i++){
    float c = cos(i*3.1416/15);
    float s = sin(i*3.1416/15);
    //upper half
    xx[i+2] = (int)((r+L*2)*c)+cx;
    yy[i+2] = (int)((r+L*2)*s)+cy;
  }
  fillPoly2(10, xx, yy, 0x0);
  img.pushSprite(0, 0);
  //M5.update();
  delay(100);
}
