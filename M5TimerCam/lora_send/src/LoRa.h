//
//  920MHz LoRa/FSK RF module ES920LR3
//
#ifndef LoRa_h
#define LoRa_h

#include "Arduino.h"

int LoRaInit(int rx, int tx, int reset, int boot);
int LoRaCommand(String s);

#endif
