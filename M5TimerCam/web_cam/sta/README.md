# M5TimerCam STA Mode (WiFi Station Mode) セットアップガイド

このガイドでは、Mac で M5TimerCam に`sta.ino`を書き込むための完全な手順を説明します。

## 概要

このプログラムは、M5TimerCam を既存の WiFi ルーターに接続し、Web ブラウザから 1 ショット画像を取得できるようにします。mDNS（Bonjour）に対応しているため、`http://m5timercam.local`でアクセスできます。

## 必要なもの

- Mac（macOS 10.14 以上推奨）
- M5TimerCam
- USB C ケーブル（データ転送対応）
- WiFi ルーター（既存のネットワーク）

## ステップ 1: PlatformIO CLI のインストール

PlatformIO CLI をインストールします。ターミナルアプリを開いて、以下のコマンドを実行してください。

### Homebrew を使用する場合（推奨）

```bash
# Homebrewがインストールされていない場合
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"

# PlatformIOをインストール
brew install platformio
```

### pip を使用する場合

```bash
# Pythonがインストールされていない場合は、まずPythonをインストール
# https://www.python.org/downloads/ からダウンロード

# PlatformIOをインストール
pip install platformio
```

インストールが完了したら、以下のコマンドでバージョンを確認してください：

```bash
pio --version
```

## ステップ 2: WiFi 設定ファイルの作成

プロジェクトのルートディレクトリ（`M5TimerCam`）に`wifi_config.h`ファイルを作成し、WiFi ルーターの SSID とパスワードを設定します。

1. ターミナルでプロジェクトルートに移動：

```bash
cd /Users/matto/Dropbox/gitbox/M5Stack/M5TimerCam
```

2. `wifi_config.h`ファイルを作成：

```bash
cat > wifi_config.h << 'EOF'
/**
 * @file wifi_config.h
 * @brief WiFi設定ファイル
 *
 * このファイルにはWiFiのSSIDとパスワードを定義します。
 * このファイルを.gitignoreに追加することを推奨します。
 */

#ifndef WIFI_CONFIG_H
#define WIFI_CONFIG_H

// WiFi AP設定
const char* ssid     = "あなたのWiFi_SSID";
const char* password = "あなたのWiFiパスワード";

#endif // WIFI_CONFIG_H
EOF
```

3. エディタで`wifi_config.h`を開き、実際の WiFi SSID とパスワードに置き換えてください：

```c
const char* ssid     = "YourWiFiSSID";      // ここにWiFiルーターのSSIDを入力
const char* password = "YourWiFiPassword";  // ここにWiFiパスワードを入力
```

**重要**: このファイルには機密情報が含まれるため、Git にコミットしないようにしてください。

## ステップ 3: M5TimerCam を Mac に接続

1. USB ケーブルで M5TimerCam を Mac に接続します
2. 接続されたシリアルポートを確認：

```bash
ls /dev/cu.usb*
```

または：

```bash
ls /dev/tty.usb*
```

通常、`/dev/cu.usbserial-XXXXX`のような形式で表示されます。ポート名をメモしておいてください。

## ステップ 4: プロジェクトのビルド

1. `sta`ディレクトリに移動：

```bash
cd web_cam/sta
```

2. 依存ライブラリをダウンロードし、プロジェクトをビルド：

```bash
pio run
```

初回実行時は、必要なライブラリのダウンロードとビルドに数分かかる場合があります。

ビルドが成功すると、以下のようなメッセージが表示されます：

```
========================= [SUCCESS] Took X.XX seconds =========================
```

## ステップ 5: M5TimerCam への書き込み

1. ビルドが成功したら、以下のコマンドでファームウェアを書き込みます：

```bash
pio run --target upload
```

2. 書き込み中は、M5TimerCam の LED が点滅する場合があります

3. 書き込みが完了すると、以下のようなメッセージが表示されます：

```
========================= [SUCCESS] Took X.XX seconds =========================
```

### 書き込みエラーが発生した場合

- **ポートが見つからないエラー**: `platformio.ini`の`upload_port`を指定してください

  - `platformio.ini`を開き、以下の行のコメント（`;`）を外してポート名を指定：

  ```ini
  upload_port = /dev/cu.usbserial-XXXXX  ; 実際のポート名に置き換え
  ```

- **書き込み権限エラー**: シリアルポートのパーミッションを確認してください

  - ユーザーを`dialout`グループに追加するか、`sudo`を使用（非推奨）

- **デバイスが検出されない**:
  - USB ケーブルがデータ転送対応か確認
  - 別の USB ポートやケーブルで試す
  - M5TimerCam を再起動（電源ボタンを長押し）

## ステップ 6: シリアルモニターで動作確認

1. シリアルモニターを開いて出力を確認：

```bash
pio device monitor
```

または：

```bash
pio run --target monitor
```

2. 正常に動作している場合、以下のような出力が表示されます：

```
Camera Init Success
Connecting to YourWiFiSSID
......
Connected to YourWiFiSSID
IP address: 192.168.1.100
mDNS responder started
Access via hostname: http://m5timercam.local
Or via IP: http://192.168.1.100
```

3. 10 秒ごとにステータス情報が表示されます：

```
--- Status ---
IP address: 192.168.1.100
mDNS hostname: http://m5timercam.local
Battery: 85% (4200mV)
-------------
```

## ステップ 7: Web ブラウザからアクセス

1. 同じ WiFi ネットワークに接続されている Mac の Web ブラウザを開きます

2. 以下のいずれかの方法でアクセス：

   - **mDNS 名を使用（推奨）**: `http://m5timercam.local`
   - **IP アドレスを使用**: `http://192.168.1.100`（シリアルモニターに表示された IP アドレス）

3. ページを開くと、カメラで撮影した 1 枚の画像が表示されます

4. 画像を更新するには、ブラウザのリロードボタンをクリックしてください（毎回新しい画像が撮影されます）

## トラブルシューティング

### WiFi に接続できない

- `wifi_config.h`の SSID とパスワードが正しいか確認
- WiFi ルーターが 2.4GHz に対応しているか確認（ESP32 は 5GHz には対応していません）
- シリアルモニターで接続エラーメッセージを確認

### mDNS 名でアクセスできない

- Mac と M5TimerCam が同じ WiFi ネットワークに接続されているか確認
- IP アドレスで直接アクセスできるか確認
- ルーターが mDNS（Bonjour）パケットをブロックしていないか確認
- ファイアウォール設定を確認

### 画像が表示されない

- シリアルモニターでエラーメッセージを確認
- カメラが正しく初期化されているか確認（"Camera Init Success"が表示されているか）
- ブラウザの開発者ツール（F12）でネットワークエラーを確認

### ビルドエラーが発生する

- PlatformIO のバージョンを確認：`pio --version`
- ライブラリの依存関係を再インストール：
  ```bash
  pio lib install
  ```
- ビルドキャッシュをクリア：
  ```bash
  pio run --target clean
  ```

### シリアルモニターが表示されない

- ポートが正しく接続されているか確認
- 別のアプリケーションがシリアルポートを使用していないか確認
- ボーレートが 115200 に設定されているか確認

## カスタマイズ

### mDNS ホスト名の変更

`src/sta.ino`の以下の行を編集：

```cpp
const char* mdns_hostname = "m5timercam";  // ここを変更
```

変更後、再度ビルドして書き込んでください。

### ステータス表示間隔の変更

`src/sta.ino`の以下の行を編集：

```cpp
const unsigned long STATUS_DISPLAY_INTERVAL = 10000;  // ミリ秒（10000 = 10秒）
```

## 参考情報

- [M5Stack 公式サイト](https://m5stack.com/)
- [PlatformIO 公式ドキュメント](https://docs.platformio.org/)
- [ESP32 公式ドキュメント](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/)

## ライセンス

このプロジェクトは、元の M5Stack のサンプルコードをベースにしています。
