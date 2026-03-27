import time

import vrc_yolo_capture
import talk_ai 


if __name__ == "__main__":
    print("🚀 main.py 起動")    
    vrc_yolo_capture.capture()
    # 少し待つ（マイク・デバイス安定）
    time.sleep(1)
    talk_ai.start_talk_ai()
