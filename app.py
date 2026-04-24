import time

from core import talk_ai
from vision import vrc_person_speaker_listener


if __name__ == "__main__":
    print("🚀 VRChat-AI 起動")
    #vrc_person_speaker_listener.yolo_run()  # 別スレッドで YOLO を起動
    time.sleep(1)  # マイク・デバイス安定待ち
    talk_ai.start_talk_ai()
