# TimerCAM BLE Image Receiver

ESP32 TimerCAMからBTLE経由で画像を受信するPythonアプリケーション

## セットアップ

### 必要なライブラリのインストール

```bash
pip install -r requirements.txt
```

または個別にインストール:

```bash
pip install bleak pillow
```

### システム要件

- Python 3.7以上
- macOS/Linux/Windows
- Bluetooth Low Energy対応デバイス

**注意**: macOSでは、Bluetoothの権限が必要な場合があります。システム環境設定 > セキュリティとプライバシー > プライバシー > Bluetooth でPythonに権限を付与してください。

## 使用方法

1. ESP32にBTLE画像送信プログラムをアップロード
2. ESP32を起動し、BTLEアドバタイズを開始
3. Pythonアプリを実行:

```bash
python receive_image.py
```

4. アプリが自動的に "TimerCAM-Image" デバイスを検出して接続します
5. 受信した画像は `received_images/` ディレクトリに自動保存されます

## 受信画像の保存先

受信した画像は以下の形式で保存されます:

```
received_images/image_0001_20240102_123456.jpg
```

ファイル名の形式: `image_{連番}_{タイムスタンプ}.jpg`

## トラブルシューティング

### デバイスが見つからない場合

- ESP32が起動していることを確認
- ESP32のシリアルモニターで "BLE Server Started" が表示されていることを確認
- Bluetoothが有効になっていることを確認
- デバイス名が "TimerCAM-Image" であることを確認

### 接続エラーが発生する場合

- 他のBTLEクライアントが接続していないことを確認
- ESP32を再起動してから再度試行
- Bluetoothアダプターを再起動

### 画像が正しく受信できない場合

- ESP32のシリアルモニターで送信ログを確認
- 受信データサイズが一致しているか確認
- パケットロスがないか確認

## カスタマイズ

### デバイス名の変更

`receive_image.py` の `DEVICE_NAME` 変数を変更:

```python
DEVICE_NAME = "YourDeviceName"
```

### 保存ディレクトリの変更

`OUTPUT_DIR` 変数を変更:

```python
OUTPUT_DIR = Path("your_directory")
```

