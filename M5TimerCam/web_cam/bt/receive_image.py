#!/usr/bin/env python3
"""
TimerCAM BLE Image Receiver
ESP32からBTLE経由で画像を1枚受信し、保存・表示するPythonアプリ
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
        self.expected_packet_count = 0  # 期待されるパケット数
        self.end_marker_received = False  # 終了マーカー受信フラグ

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
            self.expected_packet_count = 0  # リセット
            self.end_marker_received = False  # リセット
            print(
                f"\n新しい画像を受信開始: {self.image_size} bytes ({self.image_size/1024:.1f} KB)"
            )
            return

        # 終了マーカー（0xFF, 0xFF + 総パケット数2バイト）の受信
        if len(data) >= 2 and data[0] == 0xFF and data[1] == 0xFF:
            if not self.receiving_image or self.image_received:
                return  # 既に処理済みまたは受信中でない

            # 総パケット数を取得（4バイトの場合）
            if len(data) >= 4:
                self.expected_packet_count = struct.unpack(">H", data[2:4])[0]
                print(
                    f"\n終了マーカー受信: 期待されるパケット数 = {self.expected_packet_count}"
                )
            else:
                # 旧形式（2バイトのみ）の場合は画像サイズから計算
                if self.image_size > 0:
                    self.expected_packet_count = (
                        self.image_size + self.packet_size - 1
                    ) // self.packet_size

            self.end_marker_received = True

            # 全パケットが揃っているか確認
            if self._all_packets_received():
                # 画像データを復元
                image_bytes = self._reconstruct_image()
                if image_bytes:
                    self._save_image(image_bytes)
                    self.image_received = True
                    self.current_image_id += 1

                # 次の画像受信の準備
                self.receiving_image = False
                self.received_packets = {}
                self.end_marker_received = False
            else:
                # パケットが揃っていない場合は待機
                missing = self._get_missing_packets()
                print(
                    f"\n警告: 全パケットが揃っていません。欠けているパケット: {missing}"
                )
                print("残りのパケットを待機中...")
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

                # 期待されるパケット数を表示
                expected_info = ""
                if self.expected_packet_count > 0:
                    expected_info = f"/{self.expected_packet_count}"

                if self.image_size > 0:
                    progress = (estimated_bytes / self.image_size) * 100
                    print(
                        f"\r受信中: {total_packets}{expected_info} パケット, {estimated_bytes}/{self.image_size} bytes ({progress:.1f}%)",
                        end="",
                        flush=True,
                    )

                # 終了マーカーを受信済みで、全パケットが揃った場合は処理
                if self.end_marker_received and self._all_packets_received():
                    image_bytes = self._reconstruct_image()
                    if image_bytes:
                        self._save_image(image_bytes)
                        self.image_received = True
                        self.current_image_id += 1

                    # 次の画像受信の準備
                    self.receiving_image = False
                    self.received_packets = {}
                    self.end_marker_received = False

    def _all_packets_received(self) -> bool:
        """全パケットが揃っているか確認"""
        if self.expected_packet_count == 0:
            # 期待されるパケット数が不明な場合は、画像サイズから計算
            if self.image_size > 0:
                expected = (self.image_size + self.packet_size - 1) // self.packet_size
            else:
                return False
        else:
            expected = self.expected_packet_count

        # 0からexpected-1までのパケットが全て揃っているか確認
        return len(self.received_packets) == expected and all(
            i in self.received_packets for i in range(expected)
        )

    def _get_missing_packets(self) -> list:
        """欠けているパケット番号のリストを返す"""
        if self.expected_packet_count == 0:
            if self.image_size > 0:
                expected = (self.image_size + self.packet_size - 1) // self.packet_size
            else:
                return []
        else:
            expected = self.expected_packet_count

        missing = []
        for i in range(expected):
            if i not in self.received_packets:
                missing.append(i)
        return missing

    def _reconstruct_image(self) -> Optional[bytes]:
        """受信したパケットから画像データを復元"""
        if not self.received_packets:
            print("\n警告: 受信パケットがありません")
            return None

        # 期待されるパケット数を確認
        if self.expected_packet_count > 0:
            expected = self.expected_packet_count
        elif self.image_size > 0:
            expected = (self.image_size + self.packet_size - 1) // self.packet_size
        else:
            expected = (
                max(self.received_packets.keys()) + 1 if self.received_packets else 0
            )

        # 欠けているパケットを確認
        missing = self._get_missing_packets()
        if missing:
            print(
                f"\n警告: {len(missing)}個のパケットが欠けています: {missing[:10]}{'...' if len(missing) > 10 else ''}"
            )

        # パケットを順番に並べ替えて結合
        sorted_packets = sorted(self.received_packets.items())
        reconstructed = bytearray()
        last_packet_num = -1

        for packet_num, packet_data in sorted_packets:
            # パケット番号の連続性を確認
            if last_packet_num >= 0 and packet_num != last_packet_num + 1:
                print(
                    f"\n警告: パケット番号が連続していません: {last_packet_num} -> {packet_num}"
                )

            reconstructed.extend(packet_data)
            last_packet_num = packet_num

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
        print("1枚の画像を受信したら終了します\n")

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

            # 1枚の画像を受信するまで待機（タイムアウト付き）
            timeout_seconds = 30  # 30秒のタイムアウト
            start_time = time.time()

            while not self.image_received:
                await asyncio.sleep(0.1)  # 短い間隔でチェック

                # タイムアウトチェック
                if time.time() - start_time > timeout_seconds:
                    print(
                        f"\nタイムアウト: {timeout_seconds}秒以内に画像の受信が完了しませんでした"
                    )
                    if self.receiving_image:
                        print(
                            f"受信済みパケット: {len(self.received_packets)}/{self.expected_packet_count if self.expected_packet_count > 0 else '?'}"
                        )
                        missing = self._get_missing_packets()
                        if missing:
                            print(
                                f"欠けているパケット: {missing[:20]}{'...' if len(missing) > 20 else ''}"
                            )
                    break

            if self.image_received:
                print("\n画像の受信が完了しました。")

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
