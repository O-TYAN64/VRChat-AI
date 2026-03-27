import threading
import time

import vrc_yolo_capture
import talk_ai


def start_yolo():
    """
    VRChat + YOLO を起動
    """
    try:
        vrc_yolo_capture.capture()
    except Exception as e:
        print("❌ YOLOスレッドでエラー:", e)


def start_talk_ai():
    """
    音声会話AIを起動
    talk_ai.py は import 時点で無限ループに入るため
    関数化せずそのまま動かす
    """
    try:
        # talk_ai.py は import だけで実行される設計
        pass
    except Exception as e:
        print("❌ Talk AI エラー:", e)


if __name__ == "__main__":
    print("🚀 main.py 起動")

    # YOLO を別スレッドで起動
    yolo_thread = threading.Thread(
        target=start_yolo,
        daemon=True
    )
    yolo_thread.start()

    # 少し待ってから音声AI開始（デバイス競合防止）
    time.sleep(1)

    # 音声AI（メインスレッド）
    start_talk_ai()
