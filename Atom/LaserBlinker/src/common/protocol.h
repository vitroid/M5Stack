#pragma once

// 前後共通の簡易テキストプロトコル（1行）
// Core → Atom:  S,turn=L|R|0,brake=0|1\n
// Atom → Core:  ACK\n  /  FAULT,reason\n  （ver0 は ACK のみ任意）

#define LINK_BAUD 9600

#define TURN_OFF '0'
#define TURN_L   'L'
#define TURN_R   'R'
