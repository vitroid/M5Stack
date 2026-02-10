#include <M5Atom.h>

extern void my_wifi_setup();
extern void set_server_mode(int);
extern int get_server_mode();
extern int get_server_health();

//Atom LEDs
uint8_t DisBuff[2 + 5 * 5 * 3];

// WiFi リンク状態 (1〜25)。25: 正常、1: ほぼ断（視覚化には現在未使用だが、将来用に保持）
int link_level = 25;

// prox / tinyweb のヘルス状態
// -1: 未取得 or HTTP失敗, 0: 正常(HTTP 200), 1: prox死(HTTP 503), 2: その他HTTPエラー
int health_status = -1;

void setBuff(uint8_t Gdata, uint8_t Rdata, uint8_t Bdata)
{
    DisBuff[0] = 0x05;
    DisBuff[1] = 0x05;
    for (int i = 0; i < 25; i++)
    {
        DisBuff[2 + i * 3 + 0] = Gdata;
        DisBuff[2 + i * 3 + 1] = Rdata;
        DisBuff[2 + i * 3 + 2] = Bdata;
    }
}

// 先頭の n 個だけ点灯させる（残りは消灯）
void setBuffN(uint8_t Gdata, uint8_t Rdata, uint8_t Bdata, int n)
{
    if (n < 0) n = 0;
    if (n > 25) n = 25;
    DisBuff[0] = 0x05;
    DisBuff[1] = 0x05;
    for (int i = 0; i < 25; i++)
    {
        if (i < n)
        {
            DisBuff[2 + i * 3 + 0] = Gdata;
            DisBuff[2 + i * 3 + 1] = Rdata;
            DisBuff[2 + i * 3 + 2] = Bdata;
        }
        else
        {
            DisBuff[2 + i * 3 + 0] = 0;
            DisBuff[2 + i * 3 + 1] = 0;
            DisBuff[2 + i * 3 + 2] = 0;
        }
    }
}

void setBuff1(uint8_t Gdata, uint8_t Rdata, uint8_t Bdata)
{
    DisBuff[0] = 0x05;
    DisBuff[1] = 0x05;
    for (int i = 0; i < 25; i++)
    {
        DisBuff[2 + i * 3 + 0] = 0;
        DisBuff[2 + i * 3 + 1] = 0;
        DisBuff[2 + i * 3 + 2] = 0;
    }
    DisBuff[2 + 0 * 3 + 0] = Gdata;
    DisBuff[2 + 0 * 3 + 1] = Rdata;
    DisBuff[2 + 0 * 3 + 2] = Bdata;
}

// 中央 3x3 を「ふわっと」点灯させる
// outer: 外周の 16 ピクセルを常時ベース色で点灯させるかどうか
void setCenterGlow(uint8_t Gbase, uint8_t Rbase, uint8_t Bbase, int cycle, bool outer)
{
    DisBuff[0] = 0x05;
    DisBuff[1] = 0x05;

    // 0〜39 の三角波を 0〜255 の輝度にマップ
    int phase = cycle % 40; // 0.0〜約2秒周期 (50ms * 40)
    uint8_t glow;
    if (phase < 20)
    {
        glow = (uint8_t)((phase * 255) / 19); // 0→255
    }
    else
    {
        glow = (uint8_t)(((39 - phase) * 255) / 19); // 255→0
    }

    for (int y = 0; y < 5; y++)
    {
        for (int x = 0; x < 5; x++)
        {
            int i = y * 5 + x;
            bool is_center = (x >= 1 && x <= 3 && y >= 1 && y <= 3);
            uint8_t g = 0, r = 0, b = 0;
            if (is_center)
            {
                // 中央 3x3 をベース色の明るさを変えながら点灯
                g = (uint8_t)((uint16_t)Gbase * glow / 255);
                r = (uint8_t)((uint16_t)Rbase * glow / 255);
                b = (uint8_t)((uint16_t)Bbase * glow / 255);
            }
            else if (outer)
            {
                // 外周は常時ベース色
                g = Gbase;
                r = Rbase;
                b = Bbase;
            }
            DisBuff[2 + i * 3 + 0] = g;
            DisBuff[2 + i * 3 + 1] = r;
            DisBuff[2 + i * 3 + 2] = b;
        }
    }
}


int demo = 0; // in demo mode, LED state is locally determined.
int pub=0; // in pub mode, key press and set status are disabled.

int cycle=0;
// servermode は setup() 後に取得する。起動直後は normal(1) としておく。
int servermode = 1;
int curmode = 1;
int lastmode = 1;
int querycycle = 1;
int presscycle=0;


void setup(){
    M5.begin(true, false, true);
    Serial.begin(115200);
    Serial.println("AtomSwitch setup start");
    setBuff(0xff,0x00,0x00);
    M5.dis.displaybuff(DisBuff);
    delay(50);
    if (!demo) {
        my_wifi_setup();
        // 起動直後に一度だけサーバのモードを取得
        int m = get_server_mode();
        if (m > 0) {
            servermode = m;
            curmode    = m;
            lastmode   = m;
            Serial.print("Initial server mode = ");
            Serial.println(servermode);
        } else {
            Serial.println("Initial get_server_mode() failed");
        }
    }
}




void disp(int servermode, int cycle)
{
    if ( servermode == 0 ){ // or server is in security mode
      if ( cycle%30 < 1 ){
        // 不在時: 青1ピクセル点滅
        setBuff1(0x00,0x00,0xff); //blue
        M5.dis.displaybuff(DisBuff);
      }
      else{
        setBuff1(0x00,0x00,0x00); //black
        M5.dis.displaybuff(DisBuff);
      }
    }
    else if ( servermode == 1 ){ //normal (green)
        if (health_status == 0){
            // 通信正常(200): 全面を通常どおり点灯
            setBuff(0xff,0x00,0x00);
        } else {
            // 通信不安定/エラー(非200): 中央3x3のみをふわっと点滅（周囲は消灯）
            setCenterGlow(0xff,0x00,0x00, cycle, false);
        }
        M5.dis.displaybuff(DisBuff);
    }
    else if ( servermode == 2 ){ //busy == yellow
        if (health_status == 0){
            setBuff(0xff,0xff,0x00);
        } else {
            setCenterGlow(0xff,0xff,0x00, cycle, false);
        }
        M5.dis.displaybuff(DisBuff);
    }
    else if ( servermode == 3 ){ // stealth (red)
        if (health_status == 0){
            setBuff(0x00,0xff,0x00);
        } else {
            setCenterGlow(0x00,0xff,0x00, cycle, false);
        }
        M5.dis.displaybuff(DisBuff);
    }
    else if ( servermode == 4 ){ // bed
        if (health_status == 0 || health_status == 1){
            // 不在(画面消灯)だがサーバからの応答はある:
            // 黒画面だと点滅がわからないので、赤一点を常時点灯
            setBuff1(0x00,0xff,0x00); //red
        } else {
            setBuff(0x00,0x00,0x00); //black
        }
        M5.dis.displaybuff(DisBuff);
    }
}


void loop(){
  if (! M5.Btn.isPressed()){
    // 50 ms x 20 == 1 sec
    if (presscycle > 20) {
      // long press
      curmode = 4; //bed mode
    }
    else if ( presscycle > 0 ){
      // short press
      if ( curmode == 4 ){
        curmode = 3; // still stealth, do not unlock.
      }
      else{
        curmode++; //cycle between 1 and 3
        if ( curmode >= 4 )
          curmode = 1;
      }
    }
    presscycle=0;
  }
  else{ // is pressed,
    if ( !pub ){
      presscycle += 1;
    }
  }

  // mode change
  if ( lastmode != curmode ){
    // report to the server (HTTP)
    Serial.print("Local mode changed to ");
    Serial.println(curmode);
    if(!demo && !pub)
        set_server_mode(curmode);
        
    // only once when mode changes.
    lastmode = curmode;

    // get the server mode immediately.
    // the mode may be overridden by the server.
    if(!demo)
        servermode = get_server_mode();
  }
  
  //LED control
  if (demo){
    disp(curmode, cycle);
    // other case: server is busy 
  }
  else{
    // control the LED based on server status
    querycycle -= 1;
    if ( querycycle <= 0 ){
      //query every 15 seconds
      int newmode = get_server_mode();
      // ヘルスチェックもあわせて実行
      int hs = get_server_health();
      if (hs >= 0) {
        health_status = hs;
      } else {
        health_status = -1;
      }
      if (newmode < 0) {
        // 通信失敗: link_level を 1 ずつ減らす（0 まで）
        if (link_level > 1) { // 最低1ピクセルは残す
          link_level -= 1;
        }
        Serial.print("Ping failed. link_level=");
        Serial.println(link_level);
      } else {
        // 通信成功: サーバモード更新 & link_level をリセット
        servermode = newmode;
        link_level = 25;
        // 2台以上同時利用時: サーバの状態をローカルに反映（他デバイスが押した変更を表示）
        if (newmode >= 0 && (curmode != newmode || lastmode != newmode)) {
          curmode = newmode;
          lastmode = newmode;
          Serial.print("Synced from server, mode = ");
          Serial.println(servermode);
        } else {
          Serial.print("Server mode is ");
          Serial.println(servermode);
        }
      }
      querycycle = 2*20; // 2秒ごとにサーバ状態を取得（2台同時利用時の表示ずれを防ぐ）
    }
    disp(servermode, cycle);
    // other case: server is busy 
    
  }
  delay(50);
  cycle++;
  M5.update();
}
