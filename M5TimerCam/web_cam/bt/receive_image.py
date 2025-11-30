#!/usr/bin/env python3
"""
TimerCAM BLE Image Receiver
ESP32からBTLE経由で画像を受信し、保存・表示するPythonアプリ
"""

import asyncio
import struct
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

try:
    from bleak import BleakClient, BleakScanner
    from PIL import Image
    import io
except ImportError as e:
    print(f"必要なライブラリがインストールされていません: {e}")
    print("以下のコマンドでインストールしてください:")
    print("  pip install bleak pillow")
    exit(1)

# BLE設定（ESP32側と一致させる）
SERVICE_UUID = "4fafc201-1fb5-459e-8fcc-c5c9c331914b"
CHARACTERISTIC_UUID = "beb5483e-36e1-4688-b7f5-ea07361b26a8"
DEVICE_NAME = "TimerCAM-Image"

# 画像保存ディレクトリ
OUTPUT_DIR = Path("received_images")
OUTPUT_DIR.mkdir(exist_ok=True)


class ImageReceiver:
    def __init__(self):
        self.client: Optional[BleakClient] = None
        self.image_size = 0
        self.received_packets = {}  # パケット番号をキーとして保存
        self.current_image_id = 0
        self.image_received = False
        self.packet_size = 500  # ESP32側と一致
        self.receiving_image = False

    async def scan_and_connect(
        self, device_name: str = DEVICE_NAME, timeout: float = 10.0
    ):
        """デバイスをスキャンして接続"""
        print(f"'{device_name}' をスキャン中...")

        devices = await BleakScanner.discover(timeout=timeout)

        target_device = None
        for device in devices:
            if device.name == device_name:
                target_device = device
                break

        if target_device is None:
            print(f"エラー: '{device_name}' が見つかりませんでした")
            print("利用可能なデバイス:")
            for device in devices:
                print(f"  - {device.name} ({device.address})")
            return False

        print(f"デバイス発見: {device_name} ({target_device.address})")
        print("接続中...")

        self.client = BleakClient(target_device.address)
        try:
            await self.client.connect()
            print("接続成功!")
            return True
        except Exception as e:
            print(f"接続エラー: {e}")
            return False

    def notification_handler(self, sender, data: bytearray):
        """BLE通知ハンドラー"""
        if len(data) == 0:
            return

        # 画像サイズヘッダー（4バイト）の受信
        if len(data) == 4 and not self.receiving_image:
            self.image_size = struct.unpack(">I", data)[
                0
            ]  # ビッグエンディアンで32bit整数
            self.received_packets = {}
            self.image_received = False
            self.receiving_image = True
            print(
                f"\n新しい画像を受信開始: {self.image_size} bytes ({self.image_size/1024:.1f} KB)"
            )
            return

        # 終了マーカー（0xFF, 0xFF）の受信
        if len(data) == 2 and data[0] == 0xFF and data[1] == 0xFF:
            if not self.receiving_image or self.image_received:
                return  # 既に処理済みまたは受信中でない

            # 画像データを復元
            image_bytes = self._reconstruct_image()
            if image_bytes:
                self._save_image(image_bytes)
                self.image_received = True
                self.current_image_id += 1

            # 次の画像受信の準備
            self.receiving_image = False
            self.received_packets = {}
            return

        # データパケットの受信（パケット番号2バイト + データ）
        if len(data) >= 2 and self.receiving_image:
            packet_num = struct.unpack(">H", data[:2])[
                0
            ]  # ビッグエンディアンで16bit整数
            packet_data = data[2:]

            # パケットを保存（重複は無視）
            if packet_num not in self.received_packets:
                self.received_packets[packet_num] = packet_data

                # 進捗表示（受信したパケット数から計算）
                total_packets = len(self.received_packets)
                estimated_bytes = sum(len(p) for p in self.received_packets.values())
                if self.image_size > 0:
                    progress = (estimated_bytes / self.image_size) * 100
                    print(
                        f"\r受信中: {total_packets} パケット, {estimated_bytes}/{self.image_size} bytes ({progress:.1f}%)",
                        end="",
                        flush=True,
                    )

    def _reconstruct_image(self) -> Optional[bytes]:
        """受信したパケットから画像データを復元"""
        if not self.received_packets:
            print("\n警告: 受信パケットがありません")
            return None

        # パケットを順番に並べ替えて結合
        sorted_packets = sorted(self.received_packets.items())
        reconstructed = bytearray()
        for packet_num, packet_data in sorted_packets:
            reconstructed.extend(packet_data)

        total_received = len(reconstructed)
        if total_received != self.image_size:
            print(
                f"\n警告: 受信データサイズが一致しません ({total_received} != {self.image_size})"
            )
            if total_received < self.image_size:
                print(f"  不足: {self.image_size - total_received} bytes")
                # 不足分を0で埋める（不完全な画像になる可能性がある）
                reconstructed.extend(b"\x00" * (self.image_size - total_received))
            else:
                # 超過分を切り詰める
                reconstructed = reconstructed[: self.image_size]

        return bytes(reconstructed)

    def _save_image(self, image_bytes: bytes):
        """画像を保存"""
        try:
            # JPEG形式で保存
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            filename = OUTPUT_DIR / f"image_{self.current_image_id:04d}_{timestamp}.jpg"

            with open(filename, "wb") as f:
                f.write(image_bytes)

            file_size = len(image_bytes)
            print(f"\n画像を保存しました: {filename} ({file_size/1024:.1f} KB)")

            # 画像の検証（PILで開けるか確認）
            try:
                img = Image.open(io.BytesIO(image_bytes))
                print(f"  解像度: {img.size[0]}x{img.size[1]}")
            except Exception as e:
                print(f"  警告: 画像の検証に失敗しました: {e}")

        except Exception as e:
            print(f"\nエラー: 画像の保存に失敗しました: {e}")

    async def start_receiving(self):
        """画像受信を開始"""
        if not self.client or not self.client.is_connected:
            print("エラー: デバイスに接続されていません")
            return

        # 通知を有効化
        await self.client.start_notify(CHARACTERISTIC_UUID, self.notification_handler)
        print("\n画像受信を開始しました...")
        print("Ctrl+C で終了\n")

    async def stop_receiving(self):
        """画像受信を停止"""
        if self.client and self.client.is_connected:
            await self.client.stop_notify(CHARACTERISTIC_UUID)
            await self.client.disconnect()
            print("\n接続を切断しました")

    async def run(self, device_name: str = DEVICE_NAME):
        """メインループ"""
        try:
            # デバイスに接続
            if not await self.scan_and_connect(device_name):
                return

            # 画像受信を開始
            await self.start_receiving()

            # 無限ループ（Ctrl+Cで終了）
            while True:
                await asyncio.sleep(1)

        except KeyboardInterrupt:
            print("\n\n受信を停止します...")
        except Exception as e:
            print(f"\nエラー: {e}")
        finally:
            await self.stop_receiving()


async def main():
    """メイン関数"""
    print("=" * 50)
    print("TimerCAM BLE Image Receiver")
    print("=" * 50)

    receiver = ImageReceiver()
    await receiver.run()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nプログラムを終了します")
