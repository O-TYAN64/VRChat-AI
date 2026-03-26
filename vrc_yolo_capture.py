import cv2
import numpy as np
import time
import ctypes
import win32gui
import win32ui
import win32con

from ultralytics import YOLO

# ===============================
# VRChat ウィンドウキャプチャ
# ===============================
def capture_window(hwnd):
    rect = win32gui.GetClientRect(hwnd)
    w, h = rect[2], rect[3]

    hwndDC = win32gui.GetWindowDC(hwnd)
    mfcDC = win32ui.CreateDCFromHandle(hwndDC)
    saveDC = mfcDC.CreateCompatibleDC()

    saveBitMap = win32ui.CreateBitmap()
    saveBitMap.CreateCompatibleBitmap(mfcDC, w, h)
    saveDC.SelectObject(saveBitMap)

    # Backbuffer含めてキャプチャ
    result = ctypes.windll.user32.PrintWindow(hwnd, saveDC.GetSafeHdc(), 2)

    bmpstr = saveBitMap.GetBitmapBits(True)
    img = np.frombuffer(bmpstr, dtype=np.uint8)
    img.shape = (h, w, 4)

    win32gui.DeleteObject(saveBitMap.GetHandle())
    saveDC.DeleteDC()
    mfcDC.DeleteDC()
    win32gui.ReleaseDC(hwnd, hwndDC)

    if result != 1:
        return None

    return cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

# ===============================
# VRChat ウィンドウ検索
# ===============================
def find_vrchat_window():
    def callback(hwnd, result):
        title = win32gui.GetWindowText(hwnd)
        if "VRChat" in title:
            result.append(hwnd)

    result = []
    win32gui.EnumWindows(callback, result)
    return result[0] if result else None

# ===============================
# メイン
# ===============================
def main():
    print("🔍 VRChat window searching...")
    hwnd = find_vrchat_window()

    if hwnd is None:
        print("❌ VRChat window not found")
        return

    print("✅ VRChat window found")

    # YOLO モデル読み込み
    model = YOLO("pretrained.pt")  # 軽量・リアルタイム向け

    while True:
        frame = capture_window(hwnd)
        if frame is None:
            print("⚠ capture failed")
            time.sleep(0.1)
            continue

        # YOLO 推論
        results = model(frame, conf=0.4, verbose=False)

        # 描画
        annotated = results[0].plot()
        cv2.imshow("VRChat + YOLO", annotated)

        # qで終了
        if cv2.waitKey(1) & 0xFF == ord("q"):
            break

        time.sleep(0.03)  # 約30FPS

    cv2.destroyAllWindows()

if __name__ == "__main__":
    main()