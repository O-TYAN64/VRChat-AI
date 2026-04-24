import time

from core import talk_ai


if __name__ == "__main__":
    print("🚀 VRChat-AI 起動")
    time.sleep(1)  # マイク・デバイス安定待ち
    talk_ai.start_talk_ai()
